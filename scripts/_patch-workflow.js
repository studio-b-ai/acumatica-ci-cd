const fs = require('fs');
let c = fs.readFileSync('.github/workflows/deploy-customization.yml', 'utf8');
const marker = '      # \u2500\u2500 Post-deploy notifications';
const idx = c.indexOf(marker);
if (idx < 0) { console.error('Marker not found'); process.exit(1); }

const insertion =
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

const newContent = c.slice(0, idx) + insertion + c.slice(idx);
fs.writeFileSync('.github/workflows/deploy-customization.yml', newContent);
console.log('Workflow patched successfully at index', idx);
