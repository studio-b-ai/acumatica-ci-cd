#!/usr/bin/env bash
#
# rotate-secrets.sh — Push secrets from 1Password to GitHub + Railway targets
#
# Usage: rotate-secrets.sh <category> [--dry-run] [--verify-only]
#
# Categories: acumatica | gateway | anthropic | hubspot | azure | slack |
#             voyage | github | ci | npm | railway | all | verify
#
# Reads scripts/secrets-map.env (relative to this script's directory).
# Stop-on-first-failure: exits immediately if any push fails.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAP_FILE="${SCRIPT_DIR}/secrets-map.env"
OP="/opt/homebrew/bin/op"
GH="/opt/homebrew/bin/gh"
RAILWAY="/opt/homebrew/bin/railway"
GH_ORG="studio-b-ai"

# ─── Parse args ───────────────────────────────────────────────────────────────

CATEGORY="${1:-}"
DRY_RUN=false
VERIFY_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --verify-only) VERIFY_ONLY=true ;;
  esac
done

if [[ -z "$CATEGORY" ]]; then
  echo "Usage: rotate-secrets.sh <category> [--dry-run] [--verify-only]"
  echo ""
  echo "Categories: acumatica | gateway | anthropic | hubspot | azure | slack |"
  echo "            voyage | github | ci | npm | railway | all | verify"
  exit 1
fi

# ─── Pre-flight checks ───────────────────────────────────────────────────────

echo "=== Pre-flight checks ==="

if ! "$OP" read "op://Studio B Infrastructure/voyage-ai-key/credential" &>/dev/null; then
  echo "ERROR: 1Password CLI not authenticated. Run: op signin"
  exit 1
fi
echo "  ✓ 1Password CLI authenticated"

if ! "$GH" auth status &>/dev/null; then
  echo "ERROR: GitHub CLI not authenticated. Run: gh auth login"
  exit 1
fi
echo "  ✓ GitHub CLI authenticated"

if ! "$RAILWAY" whoami &>/dev/null; then
  echo "ERROR: Railway CLI not authenticated. Run: railway login"
  exit 1
fi
echo "  ✓ Railway CLI authenticated"

if [[ ! -f "$MAP_FILE" ]]; then
  echo "ERROR: Map file not found: $MAP_FILE"
  exit 1
fi
echo "  ✓ Map file found: $MAP_FILE"
echo ""

# ─── Verify mode ──────────────────────────────────────────────────────────────

if [[ "$CATEGORY" == "verify" ]] || [[ "$VERIFY_ONLY" == "true" ]]; then
  echo "=== Verification Mode ==="
  FAILURES=0

  # Check GitHub secrets exist (can't read values, just confirm set)
  for repo in acumatica-ci-cd webhook-router studiob; do
    count=$("$GH" secret list --repo "${GH_ORG}/${repo}" 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$count" -gt 0 ]]; then
      echo "  ✓ ${repo}: ${count} secrets"
    else
      echo "  ✗ ${repo}: no secrets found"
      FAILURES=$((FAILURES + 1))
    fi
  done

  # Check Railway services are reachable
  for project_service in \
    "studiob-platform/acudev" \
    "studiob-platform/webhook-router" \
    "studiob-platform/studiob-api" \
    "studiob-platform/studiob-agents" \
    "aesthetik-production/heritage-wms"; do
    project="${project_service%%/*}"
    service="${project_service##*/}"
    var_count=$(cd ~/dev/acudev && "$RAILWAY" variables --service "$service" -p "$project" --json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    if [[ "$var_count" -gt 0 ]]; then
      echo "  ✓ ${project}/${service}: ${var_count} vars"
    else
      echo "  ✗ ${project}/${service}: unreachable"
      FAILURES=$((FAILURES + 1))
    fi
  done

  if [[ "$FAILURES" -gt 0 ]]; then
    echo ""
    echo "FAILED: ${FAILURES} check(s) failed"
    exit 1
  else
    echo ""
    echo "All checks passed."
    exit 0
  fi
fi

# ─── Push mode ────────────────────────────────────────────────────────────────

echo "=== Pushing secrets (category: ${CATEGORY}) ==="
if [[ "$DRY_RUN" == "true" ]]; then
  echo "    (DRY RUN — no writes)"
fi
echo ""

SUCCESS=0
FAILED=0
SKIPPED=0

# Track Railway project linking to avoid unnecessary re-links
CURRENT_RAILWAY_PROJECT=""

while IFS='|' read -r cat op_item op_field target_type target_location secret_name; do
  # Skip comments and blank lines
  [[ "$cat" =~ ^[[:space:]]*# ]] && continue
  [[ -z "$cat" ]] && continue

  # Filter by category
  if [[ "$CATEGORY" != "all" ]] && [[ "$cat" != "$CATEGORY" ]]; then
    continue
  fi

  # Read value from 1Password
  op_path="op://Studio B Infrastructure/${op_item}/${op_field}"
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY] ${cat} | ${op_item}/${op_field} → ${target_type}:${target_location}/${secret_name}"
    SUCCESS=$((SUCCESS + 1))
    continue
  fi

  value=$("$OP" read "$op_path" 2>/dev/null) || {
    echo "  ✗ FAILED to read: ${op_path}"
    FAILED=$((FAILED + 1))
    echo ""
    echo "STOP: Failed to read from 1Password. ${SUCCESS} succeeded, ${FAILED} failed."
    exit 1
  }

  if [[ -z "$value" ]]; then
    echo "  ✗ EMPTY value from: ${op_path}"
    FAILED=$((FAILED + 1))
    echo ""
    echo "STOP: Empty value from 1Password. ${SUCCESS} succeeded, ${FAILED} failed."
    exit 1
  fi

  # Push to target
  case "$target_type" in
    gh)
      "$GH" secret set "$secret_name" --repo "${GH_ORG}/${target_location}" --body "$value" 2>/dev/null || {
        echo "  ✗ FAILED: gh secret set ${secret_name} on ${target_location}"
        FAILED=$((FAILED + 1))
        echo ""
        echo "STOP: GitHub push failed. ${SUCCESS} succeeded, ${FAILED} failed."
        exit 1
      }
      echo "  ✓ gh:${target_location}/${secret_name}"
      SUCCESS=$((SUCCESS + 1))
      ;;
    rw)
      project="${target_location%%/*}"
      service="${target_location##*/}"

      # Link to project if needed
      if [[ "$CURRENT_RAILWAY_PROJECT" != "$project" ]]; then
        cd ~/dev/acudev
        "$RAILWAY" link -p "$project" -e production &>/dev/null || {
          echo "  ✗ FAILED: railway link to ${project}"
          FAILED=$((FAILED + 1))
          echo ""
          echo "STOP: Railway link failed. ${SUCCESS} succeeded, ${FAILED} failed."
          exit 1
        }
        CURRENT_RAILWAY_PROJECT="$project"
      fi

      "$RAILWAY" variables set "${secret_name}=${value}" --service "$service" 2>/dev/null || {
        echo "  ✗ FAILED: railway set ${secret_name} on ${project}/${service}"
        FAILED=$((FAILED + 1))
        echo ""
        echo "STOP: Railway push failed. ${SUCCESS} succeeded, ${FAILED} failed."
        exit 1
      }
      echo "  ✓ rw:${project}/${service}/${secret_name}"
      SUCCESS=$((SUCCESS + 1))
      ;;
    *)
      echo "  ? Unknown target type: ${target_type} (skipping)"
      SKIPPED=$((SKIPPED + 1))
      ;;
  esac

done < "$MAP_FILE"

echo ""
echo "=== Complete ==="
echo "  Succeeded: ${SUCCESS}"
echo "  Failed:    ${FAILED}"
echo "  Skipped:   ${SKIPPED}"

if [[ "$FAILED" -gt 0 ]]; then
  exit 1
fi
