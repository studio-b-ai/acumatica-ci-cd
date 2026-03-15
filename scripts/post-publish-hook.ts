/**
 * Acumatica CI/CD integration: auto-dispatch test config after customization publish.
 *
 * INSTALLATION (in studio-b-ai/acumatica-ci-cd):
 *
 * 1. Copy dispatch-test-config.ts to scripts/dispatch-test-config.ts
 * 2. Add GH_PAT_DISPATCH to GitHub Actions secrets
 * 3. Add a post-publish step to the deploy workflow (see below)
 *
 * This script parses the customization project XML to find new DAC extension
 * fields, then dispatches a test config update for each one.
 */

import { readFileSync, existsSync, readdirSync } from 'fs';
import { resolve, join } from 'path';
import { dispatchCustomField } from './dispatch-test-config.js';

// ── Entity mapping: DAC name → Acumatica REST API entity name ──────────────

const DAC_TO_ENTITY: Record<string, string> = {
  'PX.Objects.SO.SOOrder': 'SalesOrder',
  'PX.Objects.PO.POOrder': 'PurchaseOrder',
  'PX.Objects.PO.POLine': 'PurchaseOrder',
  'PX.Objects.AR.Customer': 'Customer',
  'PX.Objects.IN.InventoryItem': 'StockItem',
  'PX.Objects.SO.SOShipment': 'Shipment',
  'PX.Objects.AR.ARInvoice': 'Invoice',
  'PX.Objects.EP.EPEmployee': 'Employee',
  'PX.Objects.CR.CRLead': 'Lead',
  'PX.Objects.CR.Contact': 'Contact',
  'PX.Objects.AP.Vendor': 'Vendor',
  'PX.Objects.CR.CRCase': 'Case',
  'PX.Objects.AP.APInvoice': 'Bill',
  'PX.Objects.AR.ARPayment': 'Payment',
  'PX.Objects.SO.SOLine': 'SalesOrder',
  'PX.Objects.CR.CROpportunity': 'Opportunity',
};

// ── DAC view mapping: which View the field belongs to in REST API ───────────

const DAC_TO_VIEW: Record<string, string> = {
  'PX.Objects.SO.SOOrder': 'Document',
  'PX.Objects.PO.POOrder': 'Document',
  'PX.Objects.PO.POLine': 'Transactions',
  'PX.Objects.AR.Customer': 'BAccount',
  'PX.Objects.IN.InventoryItem': 'Item',
  'PX.Objects.SO.SOShipment': 'Document',
  'PX.Objects.AR.ARInvoice': 'Document',
  'PX.Objects.EP.EPEmployee': 'Contact',
  'PX.Objects.CR.CRLead': 'Lead',
  'PX.Objects.CR.Contact': 'Contact',
  'PX.Objects.AP.Vendor': 'BAccount',
  'PX.Objects.CR.CRCase': 'Case',
  'PX.Objects.AP.APInvoice': 'Document',
  'PX.Objects.AR.ARPayment': 'Document',
  'PX.Objects.SO.SOLine': 'Transactions',
  'PX.Objects.CR.CROpportunity': 'Opportunity',
};

interface DacField {
  dacName: string;
  fieldName: string;
  entity: string;
  view: string;
  path: string;
}

/**
 * Parse C# DAC extension files to find Usr* fields.
 * Looks for patterns like: public abstract class UsrFieldName : PX.Data.BQL.Bql...
 * or: public string UsrFieldName { get; set; }
 */
function parseDacExtensions(projectDir: string): DacField[] {
  const codeDir = join(projectDir, 'Code');
  if (!existsSync(codeDir)) return [];

  const fields: DacField[] = [];
  const files = readdirSync(codeDir).filter((f) => f.endsWith('.cs'));

  for (const file of files) {
    const content = readFileSync(join(codeDir, file), 'utf-8');

    // Find DAC extension class: public class SomeExt : PXCacheExtension<PX.Objects.SO.SOOrder>
    const classMatch = content.match(
      /class\s+\w+\s*:\s*PXCacheExtension<([^>]+)>/,
    );
    if (!classMatch) continue;

    const dacName = classMatch[1].trim();
    const entity = DAC_TO_ENTITY[dacName];
    const view = DAC_TO_VIEW[dacName];
    if (!entity || !view) continue;

    // Find Usr* field declarations: public abstract class UsrFieldName
    const fieldPattern = /public\s+(?:abstract\s+)?class\s+(Usr\w+)\s*:/g;
    let match: RegExpExecArray | null;
    while ((match = fieldPattern.exec(content)) !== null) {
      const fieldName = match[1];
      fields.push({
        dacName,
        fieldName,
        entity,
        view,
        path: `custom.${view}.${fieldName}`,
      });
    }

    // Also find property declarations: public string UsrFieldName { get; set; }
    const propPattern = /public\s+\w+\??\s+(Usr\w+)\s*\{/g;
    while ((match = propPattern.exec(content)) !== null) {
      const fieldName = match[1];
      // Skip if already found via abstract class pattern
      if (fields.some((f) => f.fieldName === fieldName && f.dacName === dacName)) continue;
      fields.push({
        dacName,
        fieldName,
        entity,
        view,
        path: `custom.${view}.${fieldName}`,
      });
    }
  }

  return fields;
}

/**
 * Main: parse the customization project and dispatch test config updates.
 *
 * Usage (from acumatica-ci-cd repo root):
 *   npx tsx scripts/post-publish-hook.ts Customization/_project
 */
async function main() {
  const projectDir = process.argv[2] || 'Customization/_project';
  const resolvedDir = resolve(projectDir);

  if (!existsSync(resolvedDir)) {
    console.error(`[post-publish] Project directory not found: ${resolvedDir}`);
    process.exit(1);
  }

  console.log(`[post-publish] Scanning ${resolvedDir} for DAC extensions...`);
  const fields = parseDacExtensions(resolvedDir);

  if (fields.length === 0) {
    console.log('[post-publish] No Usr* fields found — nothing to dispatch');
    return;
  }

  console.log(`[post-publish] Found ${fields.length} custom field(s):`);
  for (const f of fields) {
    console.log(`  ${f.entity}.${f.path} (${f.dacName}.${f.fieldName})`);
  }

  let dispatched = 0;
  for (const f of fields) {
    const label = f.fieldName
      .replace(/^Usr/, '')
      .replace(/([A-Z])/g, ' $1')
      .trim();

    const success = await dispatchCustomField(f.entity, f.path, label, 'inline');
    if (success) dispatched++;
  }

  console.log(`[post-publish] Dispatched ${dispatched}/${fields.length} test config updates`);
}

main().catch((err) => {
  console.error('[post-publish] Error:', err);
  process.exit(1);
});
