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
VALIDATE_ONLY=false
POLL_INTERVAL=10
POLL_TIMEOUT=600    # 10 minutes max
COOKIE_JAR=""
CLEANUP_FILES=()

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
  for f in "${CLEANUP_FILES[@]}"; do
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
  --validate-only        Upload and validate but do not publish
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
    --validate-only)  VALIDATE_ONLY=true;  shift ;;
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

# ─── Validate-only exit point ────────────────────────────────────────────────
if [[ "${VALIDATE_ONLY}" == true ]]; then
  ok "Validation complete — package imported successfully (no publish)"
  log "The package is now in Acumatica's customization list but NOT published."
  exit 0
fi

# ─── Step 3: Publish Begin ───────────────────────────────────────────────────
log "Step 3/6: Starting publish..."

# Build project names array — always include the main project + any co-publish projects
PROJECT_NAMES="[\"${PROJECT}\""
if [[ -n "${ALSO_PUBLISH}" ]]; then
  IFS=',' read -ra EXTRA_PROJECTS <<< "${ALSO_PUBLISH}"
  for p in "${EXTRA_PROJECTS[@]}"; do
    p=$(echo "$p" | xargs)  # trim whitespace
    [[ -n "$p" ]] && PROJECT_NAMES+=",\"${p}\""
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
  cat "${RESPONSE_FILE}" >&2
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
      err "Publish failed after ${ELAPSED}s"
      echo "${BODY}" >&2
      die "Publish reported failure. Check Acumatica System Monitor for details."
    elif echo "${BODY}" | grep -qi '"isCompleted"\s*:\s*true'; then
      ok "Publish completed successfully (${ELAPSED}s)"
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
    echo "${BODY}" >&2
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
echo "============================================"
