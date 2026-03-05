#!/usr/bin/env bash
# ============================================================================
# Acumatica Customization Deployment via MCP Server
# ============================================================================
# Deploys a customization package through the Acumatica MCP server instead of
# direct Acumatica API login. This avoids consuming an API session slot
# (Acumatica license limits concurrent sessions to ~2-3).
#
# MCP Flow:
#   1. Base64-encode the .zip package
#   2. Call acumatica_customization_import via MCP JSON-RPC
#   3. Call acumatica_customization_publish via MCP JSON-RPC
#   4. Poll acumatica_customization_publish_status until complete
#
# Usage:
#   ./deploy-via-mcp.sh \
#     --project HeritageFabricsPO \
#     --package dist/HeritageFabricsPO.zip \
#     --also-publish "HeritageFabricsPO" \
#     --validate-only
#
# Environment variables:
#   ACUMATICA_MCP_URL   — MCP server URL (default: https://acumatica-mcp-production.up.railway.app)
#   ACUMATICA_MCP_TOKEN — MCP auth token
# ============================================================================

set -euo pipefail

# ─── Defaults ────────────────────────────────────────────────────────────────
MCP_URL="${ACUMATICA_MCP_URL:-https://acumatica-mcp-production.up.railway.app}"
MCP_TOKEN="${ACUMATICA_MCP_TOKEN:-}"
PROJECT=""
PACKAGE=""
ALSO_PUBLISH=""
VALIDATE_ONLY=false
POLL_INTERVAL=10
POLL_TIMEOUT=600

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ─── Helpers ─────────────────────────────────────────────────────────────────
CLEANUP_FILES=()
cleanup() {
  for f in "${CLEANUP_FILES[@]}"; do
    rm -f "$f" 2>/dev/null || true
  done
}
trap cleanup EXIT

log()   { echo -e "${BLUE}[DEPLOY]${NC} $*"; }
ok()    { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()   { echo -e "${RED}[ERROR ]${NC} $*" >&2; }
die()   { err "$@"; exit 1; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Deploys Acumatica customization via MCP server (no direct API session needed).

Options:
  --project NAME         Customization project name in Acumatica
  --package FILE         Path to .zip package to deploy
  --also-publish NAMES   Comma-separated project names to co-publish
  --validate-only        Upload only, do not publish
  --mcp-url URL          MCP server URL (or ACUMATICA_MCP_URL env)
  --mcp-token TOKEN      MCP auth token (or ACUMATICA_MCP_TOKEN env)
  --poll-interval SECS   Seconds between status checks (default: 10)
  --poll-timeout SECS    Max seconds to wait for publish (default: 600)
  -h, --help             Show this help
EOF
  exit 0
}

# MCP session ID (set after initialize)
MCP_SESSION_ID=""

# Initialize MCP session
mcp_init() {
  local tmp_headers
  tmp_headers=$(mktemp)

  local response
  response=$(curl -s --max-time 30 \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -D "${tmp_headers}" \
    "${MCP_URL}/mcp?token=${MCP_TOKEN}" \
    -d "{
      \"jsonrpc\": \"2.0\",
      \"id\": 1,
      \"method\": \"initialize\",
      \"params\": {
        \"protocolVersion\": \"2024-11-05\",
        \"capabilities\": {},
        \"clientInfo\": { \"name\": \"ci-cd-deploy\", \"version\": \"1.0.0\" }
      }
    }" 2>&1)

  local exit_code=$?
  if [[ ${exit_code} -ne 0 ]]; then
    rm -f "${tmp_headers}"
    die "MCP initialize failed (curl exit ${exit_code}): ${response}"
  fi

  # Extract session ID from Mcp-Session-Id header
  MCP_SESSION_ID=$(grep -i "mcp-session-id" "${tmp_headers}" | sed 's/.*: //' | tr -d '\r\n' || true)
  rm -f "${tmp_headers}"

  if [[ -z "${MCP_SESSION_ID}" ]]; then
    # Some MCP servers don't use sessions — proceed without
    warn "No MCP session ID returned (server may not require sessions)"
  fi

  # Send initialized notification
  curl -s --max-time 10 \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    ${MCP_SESSION_ID:+-H "Mcp-Session-Id: ${MCP_SESSION_ID}"} \
    "${MCP_URL}/mcp?token=${MCP_TOKEN}" \
    -d '{"jsonrpc": "2.0", "method": "notifications/initialized"}' \
    -o /dev/null 2>/dev/null || true
}

# Call an MCP tool via JSON-RPC
mcp_call() {
  local tool_name="$1"
  local arguments="$2"

  # Write request body to temp file (handles large payloads like base64 .zip)
  local request_file args_file
  request_file=$(mktemp)
  args_file=$(mktemp)
  CLEANUP_FILES+=("${request_file}" "${args_file}")

  # Write arguments to file first (avoids ARG_MAX for large base64 payloads)
  echo "${arguments}" > "${args_file}"

  python3 -c "
import json, sys
with open(sys.argv[3]) as f:
    args = json.load(f)
body = {
    'jsonrpc': '2.0',
    'id': int(sys.argv[1]),
    'method': 'tools/call',
    'params': {
        'name': sys.argv[2],
        'arguments': args
    }
}
json.dump(body, open(sys.argv[4], 'w'))
" "$(date +%s)" "${tool_name}" "${args_file}" "${request_file}" || {
    err "Failed to build JSON-RPC request for ${tool_name}"
    return 1
  }

  local response
  local http_code
  local response_file
  response_file=$(mktemp)
  CLEANUP_FILES+=("${response_file}")

  http_code=$(curl -s -o "${response_file}" -w "%{http_code}" --max-time 120 \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    ${MCP_SESSION_ID:+-H "Mcp-Session-Id: ${MCP_SESSION_ID}"} \
    "${MCP_URL}/mcp?token=${MCP_TOKEN}" \
    -d "@${request_file}" 2>&1)

  local exit_code=$?
  response=$(cat "${response_file}")

  if [[ ${exit_code} -ne 0 ]]; then
    die "MCP call to ${tool_name} failed (curl exit ${exit_code}, HTTP ${http_code}): ${response}"
  fi

  if [[ "${http_code}" != "200" ]]; then
    die "MCP call to ${tool_name} returned HTTP ${http_code}: ${response}"
  fi

  echo "${response}"
}

# Extract text content from MCP response
extract_content() {
  local response="$1"
  # MCP responses have result.content[0].text
  echo "${response}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'result' in data and 'content' in data['result']:
        for item in data['result']['content']:
            if item.get('type') == 'text':
                print(item['text'])
                break
    elif 'error' in data:
        print('ERROR: ' + json.dumps(data['error']), file=sys.stderr)
        sys.exit(1)
    else:
        print(json.dumps(data))
except Exception as e:
    print(f'Parse error: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1
}

# ─── Parse Arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)        PROJECT="$2";        shift 2 ;;
    --package)        PACKAGE="$2";        shift 2 ;;
    --also-publish)   ALSO_PUBLISH="$2";   shift 2 ;;
    --validate-only)  VALIDATE_ONLY=true;  shift ;;
    --mcp-url)        MCP_URL="$2";        shift 2 ;;
    --mcp-token)      MCP_TOKEN="$2";      shift 2 ;;
    --poll-interval)  POLL_INTERVAL="$2";  shift 2 ;;
    --poll-timeout)   POLL_TIMEOUT="$2";   shift 2 ;;
    -h|--help)        usage ;;
    *) die "Unknown option: $1" ;;
  esac
done

# ─── Validate Inputs ────────────────────────────────────────────────────────
[[ -z "${MCP_TOKEN}" ]] && die "Missing --mcp-token (or set ACUMATICA_MCP_TOKEN)"
[[ -z "${PROJECT}" ]]   && die "Missing --project"
[[ -z "${PACKAGE}" ]]   && die "Missing --package"
[[ ! -f "${PACKAGE}" ]] && die "Package file not found: ${PACKAGE}"

log "MCP:     ${MCP_URL}"
log "Project: ${PROJECT}"
log "Package: ${PACKAGE} ($(du -h "${PACKAGE}" | cut -f1))"
[[ -n "${ALSO_PUBLISH}" ]] && log "Co-publish with: ${ALSO_PUBLISH}"
[[ "${VALIDATE_ONLY}" == true ]] && warn "VALIDATE ONLY — will not publish"

# ─── Step 1: Verify MCP server is reachable ──────────────────────────────────
log "Step 1/4: Checking MCP server health..."

HEALTH_RESPONSE=$(curl -sf --max-time 10 "${MCP_URL}/health" 2>&1) || die "MCP server unreachable at ${MCP_URL}"
ok "MCP server healthy"

log "Initializing MCP session..."
mcp_init
ok "MCP session established${MCP_SESSION_ID:+ (session: ${MCP_SESSION_ID:0:8}...)}"

# ─── Step 2: Import package via MCP ──────────────────────────────────────────
log "Step 2/4: Importing customization package via MCP..."

# Base64 encode the package
PACKAGE_B64=$(base64 -w0 "${PACKAGE}" 2>/dev/null || base64 "${PACKAGE}" | tr -d '\n')

# Build import args via python (reads base64 from file to avoid ARG_MAX)
PACKAGE_B64_FILE=$(mktemp)
CLEANUP_FILES+=("${PACKAGE_B64_FILE}")
echo -n "${PACKAGE_B64}" > "${PACKAGE_B64_FILE}"
log "  Base64 file: $(wc -c < "${PACKAGE_B64_FILE}") bytes"

IMPORT_ARGS_FILE=$(mktemp)
CLEANUP_FILES+=("${IMPORT_ARGS_FILE}")

DEPLOY_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 -c "
import json, sys
with open(sys.argv[2]) as f:
    b64 = f.read()
args = {
    'project_name': sys.argv[1],
    'project_content_base64': b64,
    'project_description': 'CI/CD deploy ' + sys.argv[3],
    'replace_if_exists': True
}
json.dump(args, open(sys.argv[4], 'w'))
print('Import args written: ' + str(len(json.dumps(args))) + ' bytes')
" "${PROJECT}" "${PACKAGE_B64_FILE}" "${DEPLOY_TS}" "${IMPORT_ARGS_FILE}" || die "Failed to build import args"

IMPORT_ARGS=$(cat "${IMPORT_ARGS_FILE}")
log "  Calling acumatica_customization_import..."

# Call MCP import — capture response to file to avoid subshell stderr issues
MCP_RESPONSE_FILE=$(mktemp)
CLEANUP_FILES+=("${MCP_RESPONSE_FILE}")

# Build request body
MCP_REQ_FILE=$(mktemp)
MCP_ARGS_FILE=$(mktemp)
CLEANUP_FILES+=("${MCP_REQ_FILE}" "${MCP_ARGS_FILE}")
echo "${IMPORT_ARGS}" > "${MCP_ARGS_FILE}"

python3 -c "
import json, sys
with open(sys.argv[3]) as f:
    args = json.load(f)
body = {
    'jsonrpc': '2.0',
    'id': int(sys.argv[1]),
    'method': 'tools/call',
    'params': {
        'name': sys.argv[2],
        'arguments': args
    }
}
json.dump(body, open(sys.argv[4], 'w'))
" "$(date +%s)" "acumatica_customization_import" "${MCP_ARGS_FILE}" "${MCP_REQ_FILE}" || die "Failed to build import request JSON"

log "  Request body: $(wc -c < "${MCP_REQ_FILE}") bytes"

IMPORT_HTTP_CODE=$(curl -s -o "${MCP_RESPONSE_FILE}" -w "%{http_code}" --max-time 120 \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  ${MCP_SESSION_ID:+-H "Mcp-Session-Id: ${MCP_SESSION_ID}"} \
  "${MCP_URL}/mcp?token=${MCP_TOKEN}" \
  -d "@${MCP_REQ_FILE}" 2>&1)

log "  Import HTTP response: ${IMPORT_HTTP_CODE}"

if [[ "${IMPORT_HTTP_CODE}" != "200" ]]; then
  err "Import HTTP ${IMPORT_HTTP_CODE}: $(cat "${MCP_RESPONSE_FILE}")"
  die "acumatica_customization_import failed"
fi

IMPORT_RESPONSE=$(cat "${MCP_RESPONSE_FILE}")
IMPORT_CONTENT=$(extract_content "${IMPORT_RESPONSE}")

if echo "${IMPORT_CONTENT}" | grep -qi "error\|failed\|exception"; then
  err "Import response: ${IMPORT_CONTENT}"
  die "Package import failed"
fi

ok "Package imported: ${PROJECT}"
log "  ${IMPORT_CONTENT}"

# ─── Validate-only exit point ────────────────────────────────────────────────
if [[ "${VALIDATE_ONLY}" == true ]]; then
  ok "Validation complete — package imported successfully (no publish)"
  exit 0
fi

# ─── Step 3: Publish via MCP ─────────────────────────────────────────────────
log "Step 3/4: Starting publish via MCP..."

# Build project names array
PROJECT_NAMES="[\"${PROJECT}\""
if [[ -n "${ALSO_PUBLISH}" ]]; then
  IFS=',' read -ra EXTRA_PROJECTS <<< "${ALSO_PUBLISH}"
  for p in "${EXTRA_PROJECTS[@]}"; do
    p=$(echo "$p" | xargs)
    [[ -n "$p" && "$p" != "${PROJECT}" ]] && PROJECT_NAMES+=",\"${p}\""
  done
fi
PROJECT_NAMES+="]"

log "Publishing projects: ${PROJECT_NAMES}"

PUBLISH_ARGS=$(python3 -c "
import json
args = {
    'project_names': json.loads('${PROJECT_NAMES}'),
    'merge_with_existing': False
}
print(json.dumps(args))
")

PUBLISH_RESPONSE=$(mcp_call "acumatica_customization_publish" "${PUBLISH_ARGS}")
PUBLISH_CONTENT=$(extract_content "${PUBLISH_RESPONSE}")

ok "Publish started"
log "  ${PUBLISH_CONTENT}"

# ─── Step 4: Poll publish status via MCP ─────────────────────────────────────
log "Step 4/4: Waiting for publish to complete..."

ELAPSED=0
while [[ ${ELAPSED} -lt ${POLL_TIMEOUT} ]]; do
  sleep "${POLL_INTERVAL}"
  ELAPSED=$((ELAPSED + POLL_INTERVAL))

  STATUS_RESPONSE=$(mcp_call "acumatica_customization_publish_status" "{}")
  STATUS_CONTENT=$(extract_content "${STATUS_RESPONSE}")

  if echo "${STATUS_CONTENT}" | grep -qi "completed\|isCompleted.*true\|\"true\""; then
    ok "Publish completed successfully (${ELAPSED}s)"
    break
  elif echo "${STATUS_CONTENT}" | grep -qi "failed\|isFailed.*true\|error"; then
    err "Publish failed after ${ELAPSED}s"
    err "${STATUS_CONTENT}"
    die "Publish reported failure. Check Acumatica System Monitor."
  else
    log "  Still publishing... (${ELAPSED}s / ${POLL_TIMEOUT}s)"
  fi
done

if [[ ${ELAPSED} -ge ${POLL_TIMEOUT} ]]; then
  die "Publish timed out after ${POLL_TIMEOUT}s"
fi

ok "Deployment complete!"
echo ""
echo "============================================"
echo "  Project:     ${PROJECT}"
echo "  Via:         MCP (${MCP_URL})"
echo "  Package:     $(basename "${PACKAGE}")"
echo "  Duration:    ${ELAPSED}s"
echo "============================================"
