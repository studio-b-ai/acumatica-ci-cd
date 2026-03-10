#!/usr/bin/env bash
# ============================================================================
# Acumatica Customization Deployment Script
# ============================================================================
# Deploys a customization package via the Acumatica Customization API.
#
# API Flow:
#   1. POST /entity/auth/login            — Authenticate session
#   2. POST /CustomizationApi/Import      — Upload .zip package
#   3. POST /CustomizationApi/publishBegin — Start publish (merges with existing)
#   4. POST /CustomizationApi/publishEnd   — Poll until publish completes
#   5. Smoke test — Re-auth + query to verify app pool restarted cleanly
#   6. POST /entity/auth/logout           — Release session
#
# Usage:
#   ./deploy.sh \
#     --url https://instance.acumatica.com \
#     --username admin \
#     --password secret \
#     --tenant MyTenant \
#     --project MyProject \
#     --package dist/MyProject.zip \
#     --also-publish "VARPackage,ShopifyConnector" \
#     --validate-only
#
# Environment variable fallbacks:
#   ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT
# ============================================================================

set -euo pipefail

# ─── Defaults ────────────────────────────────────────────────────────────────
URL="${ACUMATICA_URL:-}"
USERNAME="${ACUMATICA_USERNAME:-}"
PASSWORD="${ACUMATICA_PASSWORD:-}"
TENANT="${ACUMATICA_TENANT:-}"
PROJECT=""
PACKAGE=""
ALSO_PUBLISH=""
EXTRA_IMPORTS=()
VALIDATE_ONLY=false
BACKUP=false
MANIFEST=""
POLL_INTERVAL=10
POLL_TIMEOUT=600    # 10 minutes max
COOKIE_JAR=""
CLEANUP_FILES=()
BACKUP_FILE=""

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ─── Helpers ─────────────────────────────────────────────────────────────────
log()   { echo -e "${BLUE}[DEPLOY]${NC} $*"; }
ok()    { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()   { echo -e "${RED}[ERROR ]${NC} $*" >&2; }
die()   { err "$@"; cleanup; exit 1; }

cleanup() {
  # Attempt logout if we have a session
  if [[ -n "${COOKIE_JAR}" && -f "${COOKIE_JAR}" ]]; then
    curl -s -o /dev/null \
      -X POST \
      -b "${COOKIE_JAR}" \
      "${URL}/entity/auth/logout" 2>/dev/null || true
    log "Session logged out"
  fi

  # Remove temp files
  for f in ${CLEANUP_FILES[@]+"${CLEANUP_FILES[@]}"}; do
    rm -f "$f" 2>/dev/null || true
  done
}

trap cleanup EXIT

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --url URL              Acumatica instance URL (or ACUMATICA_URL env)
  --username USER        API username (or ACUMATICA_USERNAME env)
  --password PASS        API password (or ACUMATICA_PASSWORD env)
  --tenant TENANT        Tenant name (or ACUMATICA_TENANT env)
  --project NAME         Customization project name in Acumatica
  --package FILE         Path to .zip package to deploy
  --also-publish NAMES   Comma-separated project names to co-publish for conflict check
  --extra-import NAME:FILE  Additional package to import (NAME=project name, FILE=zip path; repeatable)
  --validate-only        Upload and validate but do not publish
  --backup               Download existing package before deploying (enables rollback)
  --manifest FILE        Post-publish validation manifest (publish-manifest.json)
  --poll-interval SECS   Seconds between publish status checks (default: 10)
  --poll-timeout SECS    Max seconds to wait for publish (default: 600)
  -h, --help             Show this help

Examples:
  # Deploy to production
  ./deploy.sh --url https://prod.acumatica.com --project MyCustom --package dist/MyCustom.zip

  # Validate only (PR checks)
  ./deploy.sh --validate-only --project MyCustom --package dist/MyCustom.zip

  # Co-publish with VAR package
  ./deploy.sh --project MyCustom --package dist/MyCustom.zip --also-publish "VARPackage,ShopifyExt"

  # Deploy multiple projects together
  ./deploy.sh --project Main --package dist/Main.zip \
    --extra-import "Addon:dist/Addon.zip" \
    --also-publish "Main,Addon"
EOF
  exit 0
}

# ─── Parse Arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)            URL="$2";            shift 2 ;;
    --username)       USERNAME="$2";       shift 2 ;;
    --password)       PASSWORD="$2";       shift 2 ;;
    --tenant)         TENANT="$2";         shift 2 ;;
    --project)        PROJECT="$2";        shift 2 ;;
    --package)        PACKAGE="$2";        shift 2 ;;
    --also-publish)   ALSO_PUBLISH="$2";   shift 2 ;;
    --extra-import)   EXTRA_IMPORTS+=("$2"); shift 2 ;;
    --validate-only)  VALIDATE_ONLY=true;  shift ;;
    --backup)         BACKUP=true;         shift ;;
    --manifest)       MANIFEST="$2";       shift 2 ;;
    --poll-interval)  POLL_INTERVAL="$2";  shift 2 ;;
    --poll-timeout)   POLL_TIMEOUT="$2";   shift 2 ;;
    -h|--help)        usage ;;
    *) die "Unknown option: $1" ;;
  esac
done

# ─── Validate Inputs ────────────────────────────────────────────────────────
[[ -z "${URL}" ]]      && die "Missing --url (or set ACUMATICA_URL)"
[[ -z "${USERNAME}" ]] && die "Missing --username (or set ACUMATICA_USERNAME)"
[[ -z "${PASSWORD}" ]] && die "Missing --password (or set ACUMATICA_PASSWORD)"
[[ -z "${PROJECT}" ]]  && die "Missing --project"
[[ -z "${PACKAGE}" ]]  && die "Missing --package"
[[ ! -f "${PACKAGE}" ]] && die "Package file not found: ${PACKAGE}"

# Strip trailing slash from URL
URL="${URL%/}"

log "Target:  ${URL}"
log "Project: ${PROJECT}"
log "Package: ${PACKAGE} ($(du -h "${PACKAGE}" | cut -f1))"
[[ -n "${ALSO_PUBLISH}" ]] && log "Co-publish with: ${ALSO_PUBLISH}"
for extra in ${EXTRA_IMPORTS[@]+"${EXTRA_IMPORTS[@]}"}; do
  EXTRA_FILE="${extra#*:}"
  EXTRA_PROJ="${extra%%:*}"
  [[ ! -f "${EXTRA_FILE}" ]] && die "Extra import file not found: ${EXTRA_FILE}"
  log "Extra import: ${EXTRA_PROJ} → ${EXTRA_FILE} ($(du -h "${EXTRA_FILE}" | cut -f1))"
done
[[ "${VALIDATE_ONLY}" == true ]] && warn "VALIDATE ONLY — will not publish"

# ─── Step 1: Login (with retry for API Login Limit) ─────────────────────────
log "Step 1/6: Authenticating..."

COOKIE_JAR=$(mktemp)
CLEANUP_FILES+=("${COOKIE_JAR}")

LOGIN_BODY=$(cat <<EOF
{
  "name": "${USERNAME}",
  "password": "${PASSWORD}"
  $([ -n "${TENANT}" ] && echo ", \"tenant\": \"${TENANT}\"")
}
EOF
)

LOGIN_MAX_RETRIES=5
LOGIN_RETRY_DELAY=15
LOGIN_ATTEMPT=0
LOGIN_SUCCESS=false

while [[ ${LOGIN_ATTEMPT} -lt ${LOGIN_MAX_RETRIES} ]]; do
  LOGIN_ATTEMPT=$((LOGIN_ATTEMPT + 1))

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -c "${COOKIE_JAR}" \
    -d "${LOGIN_BODY}" \
    "${URL}/entity/auth/login")

  if [[ "${HTTP_CODE}" == "204" ]]; then
    LOGIN_SUCCESS=true
    break
  fi

  if [[ "${HTTP_CODE}" == "500" && ${LOGIN_ATTEMPT} -lt ${LOGIN_MAX_RETRIES} ]]; then
    # HTTP 500 is often the API Login Limit — all session slots consumed
    # by MCP server, sync workers, etc. Wait and retry.
    WAIT=$((LOGIN_RETRY_DELAY * LOGIN_ATTEMPT))
    warn "Login returned HTTP 500 (likely API Login Limit). Retry ${LOGIN_ATTEMPT}/${LOGIN_MAX_RETRIES} in ${WAIT}s..."
    sleep "${WAIT}"
  elif [[ ${LOGIN_ATTEMPT} -lt ${LOGIN_MAX_RETRIES} ]]; then
    WAIT=$((LOGIN_RETRY_DELAY * LOGIN_ATTEMPT))
    warn "Login returned HTTP ${HTTP_CODE}. Retry ${LOGIN_ATTEMPT}/${LOGIN_MAX_RETRIES} in ${WAIT}s..."
    sleep "${WAIT}"
  fi
done

if [[ "${LOGIN_SUCCESS}" != true ]]; then
  die "Login failed after ${LOGIN_MAX_RETRIES} attempts (last HTTP ${HTTP_CODE}). Check credentials, URL, or API Login Limit."
fi
ok "Authenticated to ${URL} (attempt ${LOGIN_ATTEMPT}/${LOGIN_MAX_RETRIES})"

# ─── Step 1b: Backup existing package (if --backup) ─────────────────────────
if [[ "${BACKUP}" == true ]]; then
  log "Step 1b: Downloading backup of existing package..."
  BACKUP_DIR="${BACKUP_DIR:-dist/backup}"
  mkdir -p "${BACKUP_DIR}"
  BACKUP_FILE="${BACKUP_DIR}/${PROJECT}_backup_$(date +%Y%m%d-%H%M%S).zip"

  BACKUP_RESPONSE=$(mktemp)
  CLEANUP_FILES+=("${BACKUP_RESPONSE}")

  HTTP_CODE=$(curl -s -o "${BACKUP_RESPONSE}" -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -b "${COOKIE_JAR}" \
    -d "{\"projectName\": \"${PROJECT}\"}" \
    "${URL}/CustomizationApi/getProject")

  if [[ "${HTTP_CODE}" == "200" ]]; then
    # Response contains base64-encoded package — extract and decode
    CONTENT_B64=$(python3 -c "
import json, sys
with open('${BACKUP_RESPONSE}') as f:
    data = json.load(f)
if isinstance(data, dict) and 'projectContentBase64' in data:
    print(data['projectContentBase64'])
elif isinstance(data, str):
    print(data)
else:
    print('')
" 2>/dev/null)

    if [[ -n "${CONTENT_B64}" ]]; then
      echo "${CONTENT_B64}" | base64 -d > "${BACKUP_FILE}" 2>/dev/null || \
      echo "${CONTENT_B64}" | base64 --decode > "${BACKUP_FILE}" 2>/dev/null
      BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
      ok "Backup saved: ${BACKUP_FILE} (${BACKUP_SIZE})"
    else
      warn "Backup response did not contain package content — continuing without backup"
      BACKUP_FILE=""
    fi
  else
    warn "Could not download backup (HTTP ${HTTP_CODE}) — continuing without backup"
    BACKUP_FILE=""
  fi
fi

# ─── Step 2: Import Package ─────────────────────────────────────────────────
log "Step 2/6: Importing customization package..."

# Base64 encode the package (Linux: base64 -w0, macOS: base64 -i)
PACKAGE_B64=$(base64 -w0 "${PACKAGE}" 2>/dev/null || base64 -i "${PACKAGE}" | tr -d '\n')

IMPORT_BODY=$(cat <<EOF
{
  "projectName": "${PROJECT}",
  "projectDescription": "Deployed via CI/CD at $(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "projectLevel": 0,
  "isReplaceIfExists": true,
  "projectContentBase64": "${PACKAGE_B64}"
}
EOF
)

RESPONSE_FILE=$(mktemp)
CLEANUP_FILES+=("${RESPONSE_FILE}")

HTTP_CODE=$(curl -s -o "${RESPONSE_FILE}" -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -b "${COOKIE_JAR}" \
  -d "${IMPORT_BODY}" \
  "${URL}/CustomizationApi/Import")

if [[ "${HTTP_CODE}" == "404" || "${HTTP_CODE}" == "405" ]]; then
  err "Customization API not available (HTTP ${HTTP_CODE})"
  err "The /CustomizationApi/ endpoint is not enabled on this Acumatica instance."
  err "Cloud-hosted instances may not expose the Customization API."
  err ""
  err "Workaround: Import the package manually via Acumatica UI:"
  err "  1. Download the build artifact from GitHub Actions"
  err "  2. Go to Customization Projects (SM204505)"
  err "  3. Click Import → select the .zip file"
  err "  4. Click Publish"
  die "Customization API unavailable — manual import required"
elif [[ "${HTTP_CODE}" != "200" && "${HTTP_CODE}" != "204" ]]; then
  err "Import failed (HTTP ${HTTP_CODE})"
  cat "${RESPONSE_FILE}" >&2
  die "Package import failed"
fi
ok "Package imported: ${PROJECT}"

# ─── Step 2b: Import Extra Packages ──────────────────────────────────────────
for extra in ${EXTRA_IMPORTS[@]+"${EXTRA_IMPORTS[@]}"}; do
  EXTRA_FILE="${extra#*:}"
  EXTRA_PROJ="${extra%%:*}"
  log "Importing extra package: ${EXTRA_PROJ}..."

  EXTRA_B64=$(base64 -w0 "${EXTRA_FILE}" 2>/dev/null || base64 -i "${EXTRA_FILE}" | tr -d '\n')

  EXTRA_IMPORT_BODY=$(cat <<EOFEXTRA
{
  "projectName": "${EXTRA_PROJ}",
  "projectDescription": "Deployed via CI/CD at $(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "projectLevel": 0,
  "isReplaceIfExists": true,
  "projectContentBase64": "${EXTRA_B64}"
}
EOFEXTRA
)

  HTTP_CODE=$(curl -s -o "${RESPONSE_FILE}" -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -b "${COOKIE_JAR}" \
    -d "${EXTRA_IMPORT_BODY}" \
    "${URL}/CustomizationApi/Import")

  if [[ "${HTTP_CODE}" != "200" && "${HTTP_CODE}" != "204" ]]; then
    err "Extra import failed for ${EXTRA_PROJ} (HTTP ${HTTP_CODE})"
    cat "${RESPONSE_FILE}" >&2
    die "Extra package import failed: ${EXTRA_PROJ}"
  fi
  ok "Extra package imported: ${EXTRA_PROJ}"
done

# ─── Validate-only exit point ────────────────────────────────────────────────
if [[ "${VALIDATE_ONLY}" == true ]]; then
  ok "Validation complete — package imported successfully (no publish)"
  log "The package is now in Acumatica's customization list but NOT published."
  exit 0
fi

# ─── Step 3: Publish Begin ───────────────────────────────────────────────────
log "Step 3/6: Starting publish..."

# Build project names array — always include the main project + any co-publish projects (deduplicated)
declare -A SEEN_PROJECTS
PROJECT_NAMES="[\"${PROJECT}\""
SEEN_PROJECTS["${PROJECT}"]=1
if [[ -n "${ALSO_PUBLISH}" ]]; then
  IFS=',' read -ra EXTRA_PROJECTS <<< "${ALSO_PUBLISH}"
  for p in "${EXTRA_PROJECTS[@]}"; do
    p=$(echo "$p" | xargs)  # trim whitespace
    if [[ -n "$p" && -z "${SEEN_PROJECTS[$p]+x}" ]]; then
      PROJECT_NAMES+=",\"${p}\""
      SEEN_PROJECTS["$p"]=1
    fi
  done
fi
PROJECT_NAMES+="]"

log "Publishing projects: ${PROJECT_NAMES}"

PUBLISH_BODY=$(cat <<EOF
{
  "isMergeWithExistingPackages": true,
  "isOnlyValidation": false,
  "isOnlyDbUpdates": false,
  "projectNames": ${PROJECT_NAMES},
  "tenantMode": "Current"
}
EOF
)

HTTP_CODE=$(curl -s -o "${RESPONSE_FILE}" -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -b "${COOKIE_JAR}" \
  -d "${PUBLISH_BODY}" \
  "${URL}/CustomizationApi/publishBegin")

if [[ "${HTTP_CODE}" != "200" && "${HTTP_CODE}" != "204" ]]; then
  err "Publish begin failed (HTTP ${HTTP_CODE})"
  log "Error response body:"
  cat "${RESPONSE_FILE}"
  die "Could not start publish process"
fi
ok "Publish started"

# ─── Step 4: Poll Publish Status ─────────────────────────────────────────────
log "Step 4/6: Waiting for publish to complete..."

ELAPSED=0
while [[ ${ELAPSED} -lt ${POLL_TIMEOUT} ]]; do
  sleep "${POLL_INTERVAL}"
  ELAPSED=$((ELAPSED + POLL_INTERVAL))

  HTTP_CODE=$(curl -s -o "${RESPONSE_FILE}" -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -b "${COOKIE_JAR}" \
    -d '{}' \
    "${URL}/CustomizationApi/publishEnd")

  BODY=$(cat "${RESPONSE_FILE}")

  # publishEnd returns:
  #   - 200 with "false" → still in progress
  #   - 200 with "true"  → completed successfully
  #   - 200 with log/error content → finished (possibly with errors)
  #   - 422/500 → failed

  # publishEnd returns JSON with isCompleted/isFailed on both 200 and 400
  if [[ "${HTTP_CODE}" == "200" || "${HTTP_CODE}" == "400" ]]; then
    if echo "${BODY}" | grep -qi '"isFailed"\s*:\s*true'; then
      err "Publish failed after ${ELAPSED}s (HTTP ${HTTP_CODE})"
      err "Response body is $(wc -c < "${RESPONSE_FILE}") bytes"

      # Extract compilation errors using python3 (handles large JSON safely)
      python3 -c "
import json, sys
try:
    with open('${RESPONSE_FILE}') as f:
        data = json.load(f)

    # Response can be: {log: [...]} or [{logType, message}...] or {message, errors...}
    log_entries = []
    if isinstance(data, dict):
        log_entries = data.get('log', [])
        if not log_entries:
            # Check for direct error fields
            for key in ['message', 'exceptionMessage', 'errors', 'compilationErrors']:
                if key in data and data[key]:
                    print(f'{key}: {str(data[key])[:3000]}')
            if not any(k in data for k in ['message','exceptionMessage','errors']):
                print('Top-level keys:', list(data.keys())[:20])
    elif isinstance(data, list):
        log_entries = data

    if log_entries:
        # Filter for errors/warnings (skip info-level patching messages)
        errors = [e for e in log_entries if isinstance(e, dict) and e.get('logType','').lower() in ('error','warning','exception')]
        if errors:
            print(f'Found {len(errors)} error/warning entries:')
            for e in errors[:30]:
                print(f\"  [{e.get('logType','?')}] {e.get('message','(no message)')}\")
        else:
            # No explicit errors — show last 20 entries (errors often at end)
            print(f'No error-level entries found in {len(log_entries)} log entries. Last 20:')
            for e in log_entries[-20:]:
                if isinstance(e, dict):
                    print(f\"  [{e.get('logType','?')}] {e.get('message','(no message)')}\")
                else:
                    print(f'  {str(e)[:200]}')
except Exception as e:
    print(f'JSON parse error: {e}')
    with open('${RESPONSE_FILE}') as f:
        print(f.read(2000))
" 2>&1 || cat "${RESPONSE_FILE}" | head -c 2000

      # Write to GH Actions step summary if available
      if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        echo "### Publish Error Details" >> "${GITHUB_STEP_SUMMARY}"
        echo '```' >> "${GITHUB_STEP_SUMMARY}"
        python3 -c "
import json
with open('${RESPONSE_FILE}') as f:
    data = json.load(f)
for key in ['log', 'message', 'exceptionMessage', 'errors']:
    if key in data and data[key]:
        s = str(data[key])
        print(s[:3000])
        break
" >> "${GITHUB_STEP_SUMMARY}" 2>/dev/null || head -c 3000 "${RESPONSE_FILE}" >> "${GITHUB_STEP_SUMMARY}"
        echo '```' >> "${GITHUB_STEP_SUMMARY}"
      fi
      die "Publish reported failure. Check Acumatica System Monitor for details."
    elif echo "${BODY}" | grep -qi '"isCompleted"\s*:\s*true'; then
      ok "Publish completed successfully (${ELAPSED}s)"
      # Dump SQL-relevant publish log entries for diagnostics
      python3 -c "
import json, sys
try:
    with open('${RESPONSE_FILE}') as f:
        data = json.load(f)
    log_entries = data.get('log', []) if isinstance(data, dict) else data if isinstance(data, list) else []
    if log_entries:
        sql_lines = [e for e in log_entries if isinstance(e, dict) and any(kw in str(e.get('message','')).lower() for kw in ('sql','table','create','error','warning','exception','failed','usrpo','script','plugin','updatedatabase','studiob'))]
        if sql_lines:
            print(f'  SQL-related log entries ({len(sql_lines)}):')
            for e in sql_lines:
                print(f\"    [{e.get('logType','?')}] {e.get('message','')[:300]}\")
        else:
            print(f'  Publish log: {len(log_entries)} entries, no SQL-related messages found')
    else:
        print('  Publish log: empty (no log entries in response)')
        print(f'  Response keys: {list(data.keys()) if isinstance(data, dict) else \"not a dict\"}')
except Exception as e:
    print(f'  Log parse error: {e}')
" 2>&1 || true
      break
    elif [[ "${BODY}" == "true" ]]; then
      ok "Publish completed successfully (${ELAPSED}s)"
      break
    elif [[ "${BODY}" == "false" ]]; then
      log "  Still publishing... (${ELAPSED}s / ${POLL_TIMEOUT}s)"
      continue
    else
      # Unknown response — could be a log, keep polling
      log "  Publish in progress... (${ELAPSED}s)"
      continue
    fi
  elif [[ "${HTTP_CODE}" == "422" || "${HTTP_CODE}" == "500" ]]; then
    err "Publish error (HTTP ${HTTP_CODE})"
    log "Error response body:"
    echo "${BODY}"
    die "Publish failed with server error"
  fi
done

if [[ ${ELAPSED} -ge ${POLL_TIMEOUT} ]]; then
  die "Publish timed out after ${POLL_TIMEOUT}s. Check Acumatica System Monitor."
fi

# ─── Step 5: Post-Publish Smoke Test ─────────────────────────────────────────
log "Step 5/6: Post-publish smoke test..."

# App pool restarts after publish — wait for it to stabilize, then re-authenticate
SMOKE_MAX_RETRIES=6
SMOKE_RETRY_DELAY=10
SMOKE_PASSED=false

for i in $(seq 1 ${SMOKE_MAX_RETRIES}); do
  sleep "${SMOKE_RETRY_DELAY}"

  # Re-authenticate (previous session killed by app pool restart)
  SMOKE_COOKIE=$(mktemp)
  CLEANUP_FILES+=("${SMOKE_COOKIE}")

  SMOKE_LOGIN_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -c "${SMOKE_COOKIE}" \
    -d "${LOGIN_BODY}" \
    "${URL}/entity/auth/login" 2>/dev/null || echo "000")

  if [[ "${SMOKE_LOGIN_HTTP}" != "204" ]]; then
    log "  Smoke test login attempt ${i}/${SMOKE_MAX_RETRIES}: HTTP ${SMOKE_LOGIN_HTTP} (app pool may still be restarting)"
    continue
  fi

  # Query StockItem — lightweight probe that verifies customization DLLs loaded
  SMOKE_QUERY_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -b "${SMOKE_COOKIE}" \
    "${URL}/entity/default/24.200.001/StockItem?\$top=1&\$select=InventoryID" 2>/dev/null || echo "000")

  # Logout smoke session
  curl -s -o /dev/null -X POST -b "${SMOKE_COOKIE}" "${URL}/entity/auth/logout" 2>/dev/null || true

  if [[ "${SMOKE_QUERY_HTTP}" == "200" ]]; then
    SMOKE_PASSED=true
    break
  else
    log "  Smoke test query attempt ${i}/${SMOKE_MAX_RETRIES}: HTTP ${SMOKE_QUERY_HTTP}"
  fi
done

if [[ "${SMOKE_PASSED}" == true ]]; then
  ok "Post-publish smoke test passed — Acumatica API responding normally"
else
  err "POST-DEPLOY SMOKE TEST FAILED after ${SMOKE_MAX_RETRIES} attempts"
  err "Acumatica may not have restarted correctly after publish."
  err "Check Acumatica System Monitor and SM204505 immediately."

  # Send Slack alert if webhook URL is available
  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    curl -s -X POST "${SLACK_WEBHOOK_URL}" \
      -H "Content-Type: application/json" \
      -d "{\"text\":\":rotating_light: *CUSTOMIZATION DEPLOY WARNING*\nPost-publish smoke test failed for \`${PROJECT}\` on \`${URL}\`.\nAcumatica API is not responding after app pool restart.\nCheck System Monitor and SM204505 immediately.\"}" 2>/dev/null || true
  fi

  # Don't die — the publish itself succeeded, we just can't verify yet.
  # The app pool may just need more time. Alert and continue.
  warn "Smoke test failed but publish completed — manual verification required"
fi

# ─── Step 5b: Entity Smoke Tests ─────────────────────────────────────────────
log "Step 5b: Entity smoke tests (customized entities)..."

# Query the REST API entities that back customized screens. If the graph
# extension is broken (e.g., GetExtension failure, NullRef on extension init),
# the entity query will return a 500 error. This catches the same class of
# failures as loading the ASPX page but uses the REST API session we already have.
#
# Mapping: PO301000→PurchaseOrder, SO301000→SalesOrder, AR301000→Invoice, IN402000→InventoryAllocationDetail
declare -A ENTITY_MAP=(
  ["PO301000"]="PurchaseOrder"
  ["SO301000"]="SalesOrder"
  ["AR301000"]="Invoice"
  ["IN402000"]="StockItem"  # InventoryAllocationDetail is inquiry-only; StockItem validates the DAC
)
ENTITY_WARNINGS=0

# Authenticate a fresh session for entity tests (app pool restart invalidates old sessions)
ENTITY_COOKIE=$(mktemp)
CLEANUP_FILES+=("${ENTITY_COOKIE}")
ENTITY_RESPONSE=$(mktemp)
CLEANUP_FILES+=("${ENTITY_RESPONSE}")

ENTITY_LOGIN_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -c "${ENTITY_COOKIE}" \
  -d "${LOGIN_BODY}" \
  "${URL}/entity/auth/login" 2>/dev/null || echo "000")

if [[ "${ENTITY_LOGIN_HTTP}" != "204" ]]; then
  warn "Entity smoke test login failed (HTTP ${ENTITY_LOGIN_HTTP}) — skipping"
else

for SCREEN_ID in "${!ENTITY_MAP[@]}"; do
  ENTITY_NAME="${ENTITY_MAP[${SCREEN_ID}]}"
  ENTITY_HTTP=$(curl -s -o "${ENTITY_RESPONSE}" -w "%{http_code}" \
    -b "${ENTITY_COOKIE}" \
    "${URL}/entity/Default/24.200.001/${ENTITY_NAME}?\$top=1" 2>/dev/null || echo "000")

  if [[ "${ENTITY_HTTP}" == "200" ]]; then
    ok "Entity ${ENTITY_NAME} (${SCREEN_ID}): OK"
  elif [[ "${ENTITY_HTTP}" == "500" ]]; then
    warn "Entity ${ENTITY_NAME} (${SCREEN_ID}): HTTP 500 — graph extension may be broken"
    head -c 500 "${ENTITY_RESPONSE}" 2>/dev/null || true
    ENTITY_WARNINGS=$((ENTITY_WARNINGS + 1))
  else
    warn "Entity ${ENTITY_NAME} (${SCREEN_ID}): HTTP ${ENTITY_HTTP} (expected 200)"
    ENTITY_WARNINGS=$((ENTITY_WARNINGS + 1))
  fi
done

if [[ ${ENTITY_WARNINGS} -gt 0 ]]; then
  warn "${ENTITY_WARNINGS} entity(ies) returned warnings after publish"
  # Alert Slack — publish already succeeded, this is informational
  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    FAILED_ENTITIES=""
    for SCREEN_ID in "${!ENTITY_MAP[@]}"; do
      FAILED_ENTITIES+="\\n  - ${ENTITY_MAP[${SCREEN_ID}]} (${SCREEN_ID})"
    done
    curl -s -X POST "${SLACK_WEBHOOK_URL}" \
      -H "Content-Type: application/json" \
        -d "{\"text\":\":warning: *Customization Entity Smoke Test Warnings*\nProject: \`${PROJECT}\` on \`${URL}\`\n${ENTITY_WARNINGS} entity(ies) returned errors after publish:${FAILED_ENTITIES}\nCheck GitHub Actions run for details.\"}" 2>/dev/null || true
    fi
  else
    ok "All ${#ENTITY_MAP[@]} customized entities passed smoke test"
  fi

  # Logout entity test session
  curl -s -o /dev/null -X POST -b "${ENTITY_COOKIE}" "${URL}/entity/auth/logout" 2>/dev/null || true
fi

# ─── Step 5c: Post-Publish Manifest Validation ──────────────────────────────
MANIFEST_PASSED=true
if [[ -n "${MANIFEST}" && -f "${MANIFEST}" ]]; then
  log "Step 5c: Post-publish manifest validation..."
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  VALIDATE_SCRIPT="${SCRIPT_DIR}/validate-publish.py"

  if [[ -f "${VALIDATE_SCRIPT}" ]]; then
    if python3 "${VALIDATE_SCRIPT}" \
      --url "${URL}" \
      --username "${USERNAME}" \
      --password "${PASSWORD}" \
      --tenant "${TENANT}" \
      --manifest "${MANIFEST}"; then
      ok "Post-publish manifest validation passed"
    else
      MANIFEST_PASSED=false
      err "Post-publish manifest validation FAILED"

      # Attempt rollback if backup exists
      if [[ -n "${BACKUP_FILE}" && -f "${BACKUP_FILE}" ]]; then
        warn "Attempting rollback using backup: ${BACKUP_FILE}"

        # Re-authenticate
        ROLLBACK_COOKIE=$(mktemp)
        CLEANUP_FILES+=("${ROLLBACK_COOKIE}")

        ROLLBACK_LOGIN=$(curl -s -o /dev/null -w "%{http_code}" \
          -X POST -H "Content-Type: application/json" \
          -c "${ROLLBACK_COOKIE}" \
          -d "${LOGIN_BODY}" \
          "${URL}/entity/auth/login" 2>/dev/null || echo "000")

        if [[ "${ROLLBACK_LOGIN}" == "204" ]]; then
          # Re-import backup
          ROLLBACK_B64=$(base64 -w0 "${BACKUP_FILE}" 2>/dev/null || base64 -i "${BACKUP_FILE}" | tr -d '\n')
          ROLLBACK_BODY="{\"projectName\":\"${PROJECT}\",\"projectDescription\":\"ROLLBACK from CI/CD at $(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"projectLevel\":0,\"isReplaceIfExists\":true,\"projectContentBase64\":\"${ROLLBACK_B64}\"}"

          ROLLBACK_IMPORT=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST -H "Content-Type: application/json" \
            -b "${ROLLBACK_COOKIE}" \
            -d "${ROLLBACK_BODY}" \
            "${URL}/CustomizationApi/Import" 2>/dev/null || echo "000")

          if [[ "${ROLLBACK_IMPORT}" == "200" || "${ROLLBACK_IMPORT}" == "204" ]]; then
            ok "Backup re-imported — starting rollback publish..."

            # Re-publish with same project list
            curl -s -o /dev/null \
              -X POST -H "Content-Type: application/json" \
              -b "${ROLLBACK_COOKIE}" \
              -d "${PUBLISH_BODY}" \
              "${URL}/CustomizationApi/publishBegin" 2>/dev/null

            # Poll rollback publish (shorter timeout)
            ROLLBACK_ELAPSED=0
            ROLLBACK_TIMEOUT=300
            ROLLBACK_OK=false
            while [[ ${ROLLBACK_ELAPSED} -lt ${ROLLBACK_TIMEOUT} ]]; do
              sleep 10
              ROLLBACK_ELAPSED=$((ROLLBACK_ELAPSED + 10))
              RB_RESPONSE=$(mktemp)
              CLEANUP_FILES+=("${RB_RESPONSE}")
              RB_CODE=$(curl -s -o "${RB_RESPONSE}" -w "%{http_code}" \
                -X POST -H "Content-Type: application/json" \
                -b "${ROLLBACK_COOKIE}" -d '{}' \
                "${URL}/CustomizationApi/publishEnd" 2>/dev/null || echo "000")
              RB_BODY=$(cat "${RB_RESPONSE}")
              if echo "${RB_BODY}" | grep -qi '"isCompleted"\s*:\s*true' || [[ "${RB_BODY}" == "true" ]]; then
                ROLLBACK_OK=true
                break
              elif echo "${RB_BODY}" | grep -qi '"isFailed"\s*:\s*true'; then
                break
              fi
            done

            if [[ "${ROLLBACK_OK}" == true ]]; then
              ok "ROLLBACK COMPLETED — previous version restored"
            else
              err "ROLLBACK FAILED — manual intervention required"
            fi
          else
            err "Could not re-import backup (HTTP ${ROLLBACK_IMPORT}) — rollback failed"
          fi

          curl -s -o /dev/null -X POST -b "${ROLLBACK_COOKIE}" "${URL}/entity/auth/logout" 2>/dev/null || true
        else
          err "Could not authenticate for rollback (HTTP ${ROLLBACK_LOGIN})"
        fi

        # Alert Slack about rollback
        if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
          ROLLBACK_STATUS=$([[ "${ROLLBACK_OK:-false}" == true ]] && echo "ROLLED BACK" || echo "ROLLBACK FAILED")
          curl -s -X POST "${SLACK_WEBHOOK_URL}" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\":rotating_light: *Customization Post-Publish Validation FAILED*\nProject: \`${PROJECT}\` on \`${URL}\`\nStatus: ${ROLLBACK_STATUS}\nCustom fields missing from API response after publish.\nCheck GitHub Actions run for details.\"}" 2>/dev/null || true
        fi

        die "Post-publish validation failed — deployment rolled back"
      else
        warn "No backup available — cannot rollback automatically"
        # Alert Slack
        if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
          curl -s -X POST "${SLACK_WEBHOOK_URL}" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\":warning: *Customization Post-Publish Validation FAILED*\nProject: \`${PROJECT}\` on \`${URL}\`\nNo backup available for automatic rollback.\nCustom fields may be missing. Manual verification required.\"}" 2>/dev/null || true
        fi
      fi
    fi
  else
    warn "validate-publish.py not found — skipping manifest validation"
  fi
elif [[ -n "${MANIFEST}" ]]; then
  warn "Manifest file not found: ${MANIFEST} — skipping validation"
fi

# ─── Step 6: Logout ─────────────────────────────────────────────────────────
log "Step 6/6: Logging out..."
# Logout happens in cleanup trap, but log it explicitly
ok "Deployment complete!"

echo ""
echo "============================================"
echo "  Project:     ${PROJECT}"
echo "  Environment: ${URL}"
echo "  Package:     $(basename "${PACKAGE}")"
echo "  Duration:    ${ELAPSED}s"
echo "  Smoke test:  $(${SMOKE_PASSED} && echo 'PASSED' || echo 'FAILED')"
echo "  Manifest:    $([[ "${MANIFEST_PASSED}" == true ]] && echo 'PASSED' || echo 'FAILED')"
echo "============================================"
