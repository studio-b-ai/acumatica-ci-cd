/**
 * _patch-workflow.js
 *
 * Idempotent one-time patcher: inserts the "Box-label auto-print smoke test"
 * step into .github/workflows/deploy-customization.yml immediately before the
 * Post-deploy notifications block.
 *
 * Safe to run multiple times — if the smoke-test block is already present the
 * script exits cleanly with a success message and makes no changes.
 */

const fs = require('fs');

const WORKFLOW_PATH = '.github/workflows/deploy-customization.yml';

let content = fs.readFileSync(WORKFLOW_PATH, 'utf8');

// ── Idempotency guard ──────────────────────────────────────────────────────
// If the smoke-test block was already inserted (by a previous run or a
// prior commit), do nothing and exit cleanly.
const IDEMPOTENCY_SENTINEL = '- name: Box-label auto-print smoke test';
if (content.includes(IDEMPOTENCY_SENTINEL)) {
  console.log('_patch-workflow.js: smoke-test step already present — no changes needed.');
  process.exit(0);
}

// ── Insertion point ────────────────────────────────────────────────────────
// Insert immediately before the "Post-deploy notifications" comment block.
const MARKER = '      # \u2500\u2500 Post-deploy notifications';
const markerIdx = content.indexOf(MARKER);
if (markerIdx < 0) {
  console.error('_patch-workflow.js: insertion marker not found in workflow file.');
  console.error('Expected to find: ' + MARKER);
  process.exit(1);
}

// ── Block to insert ────────────────────────────────────────────────────────
const INSERTION =
  '      # \u2500\u2500 Box-label smoke test \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n' +
  '      # Verifies that the ShipmentLabelAutoPrint customization components\n' +
  '      # are correctly deployed: graph extension loaded, SQL column present,\n' +
  '      # and Shipment entity queryable without HTTP 500.\n' +
  '      # --skip-device-hub suppresses the manual-config reminder in CI output.\n' +
  '      - name: Box-label auto-print smoke test\n' +
  "        if: github.event.inputs.dry_run != 'true'\n" +
  '        continue-on-error: true\n' +
  '        env:\n' +
  "          ACUMATICA_URL: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_URL || (secrets.ACUMATICA_STG_URL || secrets.ACUMATICA_PROD_URL) }}\n" +
  "          ACUMATICA_USERNAME: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_USERNAME || (secrets.ACUMATICA_STG_USERNAME || secrets.ACUMATICA_PROD_USERNAME) }}\n" +
  "          ACUMATICA_PASSWORD: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_PASSWORD || (secrets.ACUMATICA_STG_PASSWORD || secrets.ACUMATICA_PROD_PASSWORD) }}\n" +
  "          ACUMATICA_TENANT: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_TENANT || (secrets.ACUMATICA_STG_TENANT || secrets.ACUMATICA_PROD_TENANT) }}\n" +
  '        run: |\n' +
  '          python scripts/test-box-label.py --skip-device-hub\n' +
  '\n';

const patched = content.slice(0, markerIdx) + INSERTION + content.slice(markerIdx);
fs.writeFileSync(WORKFLOW_PATH, patched);
console.log('_patch-workflow.js: workflow patched successfully at index', markerIdx);
