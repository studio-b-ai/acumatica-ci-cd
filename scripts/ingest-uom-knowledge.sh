#!/usr/bin/env bash
# Ingest UOM migration knowledge into AcuDev's Qdrant KB.
# Requires: ACUDEV_AUTH_TOKEN env var (get from Railway: acudev service)
#
# Usage:
#   ACUDEV_AUTH_TOKEN=<token> bash scripts/ingest-uom-knowledge.sh
set -euo pipefail

ACUDEV_URL="${ACUDEV_URL:-https://acudev-production-407f.up.railway.app}"
AUTH_TOKEN="${ACUDEV_AUTH_TOKEN:?Set ACUDEV_AUTH_TOKEN (Railway → acudev service → env vars)}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD="${SCRIPT_DIR}/../docs/kb/uom-knowledge.json"

if [ ! -f "$PAYLOAD" ]; then
  echo "ERROR: Payload not found at $PAYLOAD"
  exit 1
fi

echo "Ingesting UOM knowledge into AcuDev KB..."
echo "  Endpoint: ${ACUDEV_URL}/knowledge/ingest"
echo "  Payload:  ${PAYLOAD}"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${ACUDEV_URL}/knowledge/ingest" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @"${PAYLOAD}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "  HTTP:     ${HTTP_CODE}"
echo "  Response: ${BODY}"

if [ "$HTTP_CODE" -ne 200 ]; then
  echo "ERROR: Ingestion failed (HTTP ${HTTP_CODE})"
  exit 1
fi

echo "Done."
