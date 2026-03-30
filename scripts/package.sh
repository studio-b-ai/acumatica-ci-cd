#!/usr/bin/env bash
# =============================================================================
# MANDATORY: This script must be used for ALL customization packages.
# NEVER use raw `zip` commands to package Acumatica customizations.
#
# Why: Raw `zip` bypasses validate-project.py, semantic_checks.py, and all
# other guards that prevent production outages.
#
# AAR 2026-03-29: 20+ hotfix iterations were packaged with raw `zip` commands,
# bypassing ALL validation. Every hotfix was deployed blind. This script
# enforces validation BEFORE a zip is created — if validation fails, no zip
# is created, and the deploy cannot proceed.
#
# Usage:
#   bash scripts/package.sh <project-name-or-dir> [output-dir]
#
# Examples:
#   bash scripts/package.sh AesthetikWMS
#   bash scripts/package.sh AesthetikWMS dist/hotfix/
#   bash scripts/package.sh /tmp/rollback-pkg/ dist/
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

usage() {
    cat <<EOF
Usage: bash $0 <project-name-or-dir> [output-dir]

Packages an Acumatica customization project into a deployable .zip.
Runs validate-project.py --strict BEFORE creating the zip.
If validation fails, NO zip is created and the script exits with code 1.

Arguments:
  project-name-or-dir  Project name (under Customization/) or full path
  output-dir           Output directory for the .zip (default: dist/)

Examples:
  bash $0 AesthetikWMS                    # Packages Customization/AesthetikWMS/
  bash $0 Customization/AesthetikWMS/     # Same, explicit path
  bash $0 AesthetikWMS dist/hotfix/       # Custom output directory
  bash $0 /tmp/rollback-pkg/ dist/        # Arbitrary directory (rollback/emergency)

IMPORTANT: This is the ONLY approved way to create customization .zips.
Do NOT use: zip -r mypackage.zip Customization/MyProject/
Reason: Raw zip bypasses all validation guards.
EOF
    exit 1
}

[[ $# -lt 1 ]] && usage

INPUT="${1}"
OUTPUT_DIR="${2:-${REPO_ROOT}/dist}"

# ── Resolve project directory ─────────────────────────────────────────────
if [[ -d "${INPUT}" ]]; then
    PROJECT_DIR="$(cd "${INPUT}" && pwd)"
elif [[ -d "${REPO_ROOT}/Customization/${INPUT}" ]]; then
    PROJECT_DIR="${REPO_ROOT}/Customization/${INPUT}"
else
    echo -e "${RED}[ERROR]${NC} Cannot find project: '${INPUT}'"
    echo "  Tried: ${INPUT} (direct path)"
    echo "  Tried: ${REPO_ROOT}/Customization/${INPUT}"
    echo ""
    echo "If packaging a custom/rollback directory, pass the full path."
    exit 1
fi

PROJECT_NAME="$(basename "${PROJECT_DIR}")"
PROJECT_XML="${PROJECT_DIR}/project.xml"

echo "=== Acumatica Customization Packager ==="
echo "Project:  ${PROJECT_NAME}"
echo "Source:   ${PROJECT_DIR}"
echo "Output:   ${OUTPUT_DIR}"
echo ""

# ── Step 1: Verify project.xml exists ─────────────────────────────────────
if [[ ! -f "${PROJECT_XML}" ]]; then
    echo -e "${RED}[ERROR]${NC} project.xml not found: ${PROJECT_XML}"
    echo "Every Acumatica customization package must have a project.xml."
    echo "Check that the project directory was created with the Customization Project Editor."
    exit 1
fi

# ── Step 2: Validate project.xml BEFORE creating any zip ─────────────────
# This is the enforcement point. If validation fails here, no zip is created.
# This is what was MISSING during the 2026-03-29 UOM migration outage — all
# 20+ hotfixes were created with raw zip commands, bypassing this check entirely.
echo "--- Step 1: Validate project.xml ---"
if ! python "${SCRIPT_DIR}/validate-project.py" --strict "${PROJECT_XML}"; then
    echo ""
    echo -e "${RED}━━━ VALIDATION FAILED — NO ZIP CREATED ━━━${NC}"
    echo ""
    echo "Fix the validation errors above, then re-run this script."
    echo ""
    echo "REMINDER: Do not bypass with raw zip commands."
    echo "Root cause of 2026-03-29 UOM migration outage: 20+ hotfixes created"
    echo "with raw zip, bypassing all validation. DO NOT REPEAT."
    exit 1
fi

echo ""
echo -e "${GREEN}[OK]${NC} Validation passed — creating package"
echo ""

# ── Step 3: Create the zip ────────────────────────────────────────────────
# IMPORTANT: The internal filename MUST be project.xml.
# Bug reference: Using `zip -j rollback-project.xml` creates wrong internal name.
# Fix: cd to the project dir before zipping so files appear at root level.
echo "--- Step 2: Create zip ---"
mkdir -p "${OUTPUT_DIR}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
PACKAGE_NAME="${PROJECT_NAME}_${TIMESTAMP}.zip"
PACKAGE_PATH="${OUTPUT_DIR}/${PACKAGE_NAME}"

# Verify project.xml will be at the zip root (not nested under a directory)
cd "${PROJECT_DIR}"
zip -r "${PACKAGE_PATH}" . \
    -x "*.DS_Store" \
    -x "__MACOSX/*" \
    -x "*.user" \
    -x "bin/*" \
    -x "obj/*"
cd "${REPO_ROOT}"

FILESIZE=$(du -h "${PACKAGE_PATH}" | cut -f1)
echo -e "${GREEN}[OK]${NC} Package created: ${PACKAGE_NAME} (${FILESIZE})"
echo ""

# ── Step 4: Validate the zip packaging (sanity check) ─────────────────────
# Catches bugs like wrong internal filename or empty level="" attribute.
# These bugs caused the 2026-03-29 rollback to fail — the rollback zip was
# created with wrong filename and level="" and couldn't be uploaded to SM204505.
echo "--- Step 3: Validate zip packaging ---"
if ! python "${SCRIPT_DIR}/validate-project.py" --validate-zip "${PACKAGE_PATH}"; then
    echo ""
    echo -e "${RED}━━━ ZIP VALIDATION FAILED — PACKAGE REMOVED ━━━${NC}"
    echo ""
    echo "The zip was created but has packaging errors that will cause import to fail."
    echo "Removing the invalid package."
    rm -f "${PACKAGE_PATH}"
    echo "Removed: ${PACKAGE_PATH}"
    echo ""
    echo "Common packaging bugs:"
    echo "  1. Wrong internal filename (must be project.xml at zip root)"
    echo "  2. Empty level=\"\" attribute (must be level=\"0\")"
    exit 1
fi

echo ""
echo -e "${GREEN}━━━ PACKAGE READY ━━━${NC}"
echo "  Path:    ${PACKAGE_PATH}"
echo "  Size:    ${FILESIZE}"
echo "  Project: ${PROJECT_NAME}"
echo ""
echo "Deploy with:"
echo "  python scripts/deploy.py --project \"${PROJECT_NAME}\" --package \"${PACKAGE_PATH}\""
