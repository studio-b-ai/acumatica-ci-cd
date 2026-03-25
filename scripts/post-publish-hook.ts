/**
 * Acumatica CI/CD integration: auto-dispatch test config after customization publish.
 *
 * INSTALLATION (in studio-b-ai/acumatica-ci-cd):
 *
 * 1. Copy dispatch-test-config.ts to scripts/dispatch-test-config.ts
 * 2. Add GH_PAT_DISPATCH to GitHub Actions secrets
 * 3. Add a post-publish step to the deploy workflow (see below)
 *
 * This script parses the customization project to find new DAC extension
 * fields, then dispatches a test config update for each one.
 *
 * ── Sources scanned (in priority order) ──────────────────────────────────────
 * 1. project.xml  — inline CDATA blocks inside <Graph> elements.
 *    This is the primary source for Heritage Fabrics: all C# customization
 *    code is embedded here as CDATA and compiled directly by Acumatica.
 * 2. Standalone *.cs files in the project directory root (e.g.
 *    ShipmentLabelAutoPrint.cs alongside project.xml).  These are kept as
 *    developer-readable reference copies of the CDATA content.
 * 3. Code/ subdirectory *.cs files — the conventional location used by
 *    some Acumatica CI/CD setups.  Scanned for forward-compatibility.
 *
 * De-duplication is applied across all sources: if the same DAC+field pair
 * is found in more than one source it is only dispatched once.
 */

import { readFileSync, existsSync, readdirSync } from 'fs';
import { resolve, join } from 'path';
import { dispatchCustomField } from './dispatch-test-config.js';

// ── REST-API dispatch skip list ────────────────────────────────────────────
//
// Some Usr* DAC extension fields exist in SQL (and are validated via the
// `sql_columns` section of publish-manifest.json) but are NOT surfaced via
// the Acumatica REST API $adHocSchema endpoint.  Dispatching test-config
// updates for these fields would cause the ui-test-suite workflow to add
// REST field checks that can never pass, generating permanent false failures.
//
// Add an entry here whenever a field is intentionally excluded from REST API
// validation.  The key is "EntityName.fieldName" (entity from DAC_TO_ENTITY,
// fieldName as declared in the DAC extension class).
//
// Current exclusions (cross-reference with publish-manifest.json _notes):
//   • Shipment.UsrBoxLabelPrinted       — server-side idempotency flag for Device
//     Hub auto-print; not surfaced via REST API adHocSchema.
//     Validate via sql_columns only.
//   • Customer.UsrDisablePayLink        — CustomerExt field on BAccount table; not
//     exposed via REST API $adHocSchema for the Customer entity.
//     Validate via sql_columns only.
//   • SalesOrder.UsrWMSStatus          — Kensium WMS pick-status field; set by the
//     WMS integration, not surfaced via REST API $adHocSchema.
//     Validate via sql_columns only.
//   • SalesOrder.UsrComplianceHold     — DAC + SQL column exist; field not yet
//     visible in REST API $adHocSchema (re-enable once confirmed in schema).
//     Validate via sql_columns only.
//   • SalesOrder.UsrComplianceHoldReason — Same REST API visibility caveat as
//     UsrComplianceHold. Validate via sql_columns only.

const DISPATCH_SKIP: ReadonlySet<string> = new Set([
  'Shipment.UsrBoxLabelPrinted',
  'Customer.UsrDisablePayLink',
  'SalesOrder.UsrWMSStatus',
  'SalesOrder.UsrComplianceHold',
  'SalesOrder.UsrComplianceHoldReason',
]);

// ── Entity mapping: DAC name → Acumatica REST API entity name ──────────────
//
// Both fully-qualified names (e.g. 'PX.Objects.SO.SOShipment') and
// unqualified short names (e.g. 'SOShipment') are listed.  Heritage Fabrics'
// C# sources use unqualified names with `using` directives, so we must
// recognise both forms to correctly identify extension fields.

const DAC_TO_ENTITY: Record<string, string> = {
  // Fully-qualified names
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
  // Unqualified short names (used in Heritage Fabrics' C# source with `using` directives)
  'SOOrder': 'SalesOrder',
  'POOrder': 'PurchaseOrder',
  'POLine': 'PurchaseOrder',
  'Customer': 'Customer',
  'InventoryItem': 'StockItem',
  'SOShipment': 'Shipment',
  'ARInvoice': 'Invoice',
  'EPEmployee': 'Employee',
  'CRLead': 'Lead',
  'Contact': 'Contact',
  'Vendor': 'Vendor',
  'CRCase': 'Case',
  'APInvoice': 'Bill',
  'ARPayment': 'Payment',
  'SOLine': 'SalesOrder',
  'CROpportunity': 'Opportunity',
};

// ── DAC view mapping: which View the field belongs to in REST API ───────────

const DAC_TO_VIEW: Record<string, string> = {
  // Fully-qualified names
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
  // Unqualified short names (mirrors DAC_TO_ENTITY above)
  'SOOrder': 'Document',
  'POOrder': 'Document',
  'POLine': 'Transactions',
  'Customer': 'BAccount',
  'InventoryItem': 'Item',
  'SOShipment': 'Document',
  'ARInvoice': 'Document',
  'EPEmployee': 'Contact',
  'CRLead': 'Lead',
  'Contact': 'Contact',
  'Vendor': 'BAccount',
  'CRCase': 'Case',
  'APInvoice': 'Document',
  'ARPayment': 'Document',
  'SOLine': 'Transactions',
  'CROpportunity': 'Opportunity',
};

interface DacField {
  dacName: string;
  fieldName: string;
  entity: string;
  view: string;
  path: string;
}

/**
 * Extract Usr* DAC extension fields from a block of C# source code.
 *
 * Handles two declaration styles:
 *   a) BQL marker class:  public abstract class UsrFieldName : BqlXxx.Field<UsrFieldName> {}
 *   b) Property:          public string? UsrFieldName { get; set; }
 *
 * Returns an array of DacField entries for each Usr* field whose parent DAC
 * is in DAC_TO_ENTITY / DAC_TO_VIEW.  If a DAC extension is not mapped,
 * it is silently skipped (graph extensions, installers, etc.).
 */
function extractFieldsFromCSharp(content: string): DacField[] {
  const fields: DacField[] = [];

  // A single .cs file (or CDATA block) may contain multiple DAC extension
  // classes.  Walk every PXCacheExtension<T> declaration found in the content.
  const classPattern = /class\s+\w+\s*:\s*PXCacheExtension<([^>]+)>/g;
  let classMatch: RegExpExecArray | null;

  while ((classMatch = classPattern.exec(content)) !== null) {
    const dacName = classMatch[1].trim();
    const entity = DAC_TO_ENTITY[dacName];
    const view = DAC_TO_VIEW[dacName];
    if (!entity || !view) continue;

    // Determine the span of this class body so we only scan its fields.
    // We find the opening brace after the class declaration and match braces.
    const bodyStart = content.indexOf('{', classMatch.index + classMatch[0].length);
    if (bodyStart === -1) continue;

    let depth = 1;
    let pos = bodyStart + 1;
    while (pos < content.length && depth > 0) {
      if (content[pos] === '{') depth++;
      else if (content[pos] === '}') depth--;
      pos++;
    }

    const classBody = content.slice(bodyStart, pos);

    // a) BQL marker inner class pattern (primary pattern for DAC fields)
    //    public abstract class UsrFieldName : BqlXxx.Field<...> { }
    const bqlPattern = /public\s+(?:abstract\s+)?class\s+(Usr\w+)\s*:/g;
    let match: RegExpExecArray | null;
    while ((match = bqlPattern.exec(classBody)) !== null) {
      const fieldName = match[1];
      if (!fields.some((f) => f.dacName === dacName && f.fieldName === fieldName)) {
        fields.push({ dacName, fieldName, entity, view, path: `custom.${view}.${fieldName}` });
      }
    }

    // b) Property pattern (fallback / alternative declaration style)
    //    public string? UsrFieldName { get; set; }
    const propPattern = /public\s+\w+\??\s+(Usr\w+)\s*\{/g;
    while ((match = propPattern.exec(classBody)) !== null) {
      const fieldName = match[1];
      if (!fields.some((f) => f.dacName === dacName && f.fieldName === fieldName)) {
        fields.push({ dacName, fieldName, entity, view, path: `custom.${view}.${fieldName}` });
      }
    }
  }

  return fields;
}

/**
 * Source 1 — Parse project.xml CDATA blocks.
 *
 * Acumatica stores each C# class as a CDATA block inside a <Graph> element:
 *   <Graph ClassName="SOShipmentLabelExt" ...>
 *     <CDATA name="Source"><![CDATA[...C# source...]]></CDATA>
 *   </Graph>
 *
 * We extract each CDATA block and run the same C# field scanner over it.
 */
function parseProjectXml(projectDir: string): DacField[] {
  const xmlPath = join(projectDir, 'project.xml');
  if (!existsSync(xmlPath)) return [];

  const xml = readFileSync(xmlPath, 'utf-8');
  const fields: DacField[] = [];

  // Match every CDATA section — project.xml may have multiple Graph entries.
  // The regex is non-greedy so it stops at the first ]]> after each <![CDATA[.
  const cdataPattern = /<!\[CDATA\[([\s\S]*?)\]\]>/g;
  let match: RegExpExecArray | null;
  while ((match = cdataPattern.exec(xml)) !== null) {
    const block = match[1];
    // Only bother scanning blocks that look like C# (skip SQL scripts, etc.)
    if (!block.includes('PXCacheExtension')) continue;

    for (const field of extractFieldsFromCSharp(block)) {
      if (!fields.some((f) => f.dacName === field.dacName && f.fieldName === field.fieldName)) {
        fields.push(field);
      }
    }
  }

  return fields;
}

/**
 * Source 2 — Parse standalone *.cs files in the project root directory.
 *
 * Developer-readable reference copies of CDATA content are kept as .cs files
 * alongside project.xml (e.g. ShipmentLabelAutoPrint.cs).  Scan these too so
 * the hook works even when CDATA hasn't been synced yet.
 */
function parseProjectRootCs(projectDir: string): DacField[] {
  const fields: DacField[] = [];

  let files: string[];
  try {
    files = readdirSync(projectDir).filter((f) => f.endsWith('.cs'));
  } catch {
    return fields;
  }

  for (const file of files) {
    const content = readFileSync(join(projectDir, file), 'utf-8');
    for (const field of extractFieldsFromCSharp(content)) {
      if (!fields.some((f) => f.dacName === field.dacName && f.fieldName === field.fieldName)) {
        fields.push(field);
      }
    }
  }

  return fields;
}

/**
 * Source 3 — Parse *.cs files in the Code/ subdirectory (legacy / forward-compat).
 *
 * Some Acumatica CI/CD setups place extension source in Code/ next to project.xml.
 * Scan this directory for forward-compatibility even though Heritage Fabrics
 * currently uses the inline CDATA approach.
 */
function parseCodeSubdir(projectDir: string): DacField[] {
  const codeDir = join(projectDir, 'Code');
  if (!existsSync(codeDir)) return [];

  const fields: DacField[] = [];
  let files: string[];
  try {
    files = readdirSync(codeDir).filter((f) => f.endsWith('.cs'));
  } catch {
    return fields;
  }

  for (const file of files) {
    const content = readFileSync(join(codeDir, file), 'utf-8');
    for (const field of extractFieldsFromCSharp(content)) {
      if (!fields.some((f) => f.dacName === field.dacName && f.fieldName === field.fieldName)) {
        fields.push(field);
      }
    }
  }

  return fields;
}

/**
 * Merge field lists from all sources, de-duplicating by dacName + fieldName.
 */
function mergeFields(...sourceLists: DacField[][]): DacField[] {
  const merged: DacField[] = [];
  for (const list of sourceLists) {
    for (const field of list) {
      if (!merged.some((f) => f.dacName === field.dacName && f.fieldName === field.fieldName)) {
        merged.push(field);
      }
    }
  }
  return merged;
}

/**
 * Main entry point: scan all sources and dispatch test config updates.
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

  console.log(`[post-publish] Scanning ${resolvedDir} for DAC extension fields...`);

  // Gather fields from all three sources
  const fromXml     = parseProjectXml(resolvedDir);
  const fromRootCs  = parseProjectRootCs(resolvedDir);
  const fromCodeDir = parseCodeSubdir(resolvedDir);

  console.log(
    `[post-publish] Sources: project.xml=${fromXml.length} field(s), ` +
    `root *.cs=${fromRootCs.length} field(s), ` +
    `Code/=${fromCodeDir.length} field(s)`,
  );

  const fields = mergeFields(fromXml, fromRootCs, fromCodeDir);

  if (fields.length === 0) {
    console.log('[post-publish] No Usr* fields found — nothing to dispatch');
    return;
  }

  console.log(`[post-publish] Found ${fields.length} unique custom field(s):`);
  for (const f of fields) {
    console.log(`  ${f.entity}.${f.path} (${f.dacName}.${f.fieldName})`);
  }

  let dispatched = 0;
  let skipped = 0;
  for (const f of fields) {
    const skipKey = `${f.entity}.${f.fieldName}`;
    if (DISPATCH_SKIP.has(skipKey)) {
      console.log(
        `[post-publish] SKIP ${skipKey} — SQL-only field, not exposed via REST API adHocSchema`,
      );
      skipped++;
      continue;
    }

    const label = f.fieldName
      .replace(/^Usr/, '')
      .replace(/([A-Z])/g, ' $1')
      .trim();

    const success = await dispatchCustomField(f.entity, f.path, label, 'inline');
    if (success) dispatched++;
  }

  console.log(
    `[post-publish] Dispatched ${dispatched}/${fields.length} test config updates` +
    (skipped > 0 ? ` (${skipped} skipped — SQL-only)` : ''),
  );
}

main().catch((err) => {
  console.error('[post-publish] Error:', err);
  process.exit(1);
});
