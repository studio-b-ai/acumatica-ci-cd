# E2E Smoke Test Design — View-Level Custom Field Validation

**Date:** 2026-03-30
**Trigger:** Prod outage — `Invalid column name '[Vendor_Vendor].[UsrDefaultInTransitSiteID]'` on Stock Items (IN2020). Existing smoke tests (REST `$top=1`) and `$adHocSchema` checks passed while the screen was broken.
**Related:** AAR-StudioBPORelations-2026-03-09 (same class of bug), PR #95 (hotfix)

## Problem

The CI/CD pipeline has two post-publish validation mechanisms:

1. **`deploy.py` smoke test** — `GET StockItem?$top=1&$select=InventoryID` → HTTP 200. Only tests that the app pool restarted and the API bot can log in. Does not exercise custom DAC extensions.

2. **`validate-publish.py`** — Checks `$adHocSchema` for custom field definitions. Tests schema *metadata registration*, not actual *SQL query execution*. A field can appear in `$adHocSchema` while the underlying view fails at query time.

Neither mechanism forces Acumatica to generate SQL that references custom columns on the target view/table. The `Vendor_Vendor` view error was invisible to both.

Additionally, `publish-manifest.json` has empty `custom_fields` arrays for every entity, so even the existing `$adHocSchema` checks are no-ops.

## Solution

### 1. Populate `publish-manifest.json`

Fill in `custom_fields` arrays for entities where `$adHocSchema` exposes custom fields:

| Entity | Custom Fields (schema path) | Package |
|--------|---------------------------|---------|
| PurchaseOrder | `custom.Document.UsrExpArrivalDate`, `custom.Document.UsrActArrivalDate`, `custom.Document.UsrContainerRef` | AesthetikContainers |
| SalesOrder | `custom.Document.UsrHubSpotDealId` | AesthetikWMS |
| StockItem | `custom.ItemSettings.UsrHTSCode`, `custom.ItemSettings.UsrDutyRate`, `custom.ItemSettings.UsrCountryOfOrigin`, `custom.ItemSettings.UsrFiberContent`, `custom.ItemSettings.UsrPreferentialTariff`, `custom.ItemSettings.UsrFreightClass` | AesthetikContainers |

Note: `Customer.UsrDisablePayLink` and `Vendor.UsrDefaultInTransitSiteID/UsrDefaultCarrierCode` are NOT exposed via `$adHocSchema`. They require the e2e probe mechanism below.

### 2. Add `e2e_probes` section to manifest

New section in `publish-manifest.json` — entities + fields to query via `$select`:

```json
"e2e_probes": [
  {"entity": "Vendor", "select_fields": ["VendorID", "UsrDefaultInTransitSiteID", "UsrDefaultCarrierCode"], "note": "BAccount extension — forces Vendor_Vendor view resolution"},
  {"entity": "PurchaseOrder", "select_fields": ["OrderNbr", "UsrExpArrivalDate", "UsrActArrivalDate", "UsrContainerRef"]},
  {"entity": "StockItem", "select_fields": ["InventoryID", "UsrHTSCode", "UsrDutyRate", "UsrCountryOfOrigin"]},
  {"entity": "SalesOrder", "select_fields": ["OrderNbr", "UsrHubSpotDealId"]},
  {"entity": "Shipment", "select_fields": ["ShipmentNbr", "UsrIncludeInContainer", "UsrContainerID"]}
]
```

### 3. New script: `scripts/smoke-e2e.py`

**Purpose:** Execute `$select` queries that force SQL column resolution on every custom field. Catches view/table mismatches that `$adHocSchema` and `$top=1` miss.

**How it works:**

For each probe in `e2e_probes`, the script executes:

```
GET /entity/Default/24.200.001/{entity}?$top=1&$select={comma-separated fields}
```

When Acumatica processes this request, the ORM generates SQL like:

```sql
SELECT TOP 1 [Vendor_Vendor].[VendorID],
             [Vendor_Vendor].[UsrDefaultInTransitSiteID],
             [Vendor_Vendor].[UsrDefaultCarrierCode]
FROM [Vendor_Vendor]
```

If the column doesn't exist on the view, SQL Server throws `Invalid column name` → HTTP 500 → probe fails → pipeline blocks.

**Response handling:**

| HTTP Code | Body Contains | Result | Meaning |
|-----------|--------------|--------|---------|
| 200 | — | PASS | Query executed, DAC extension resolved |
| 204 | — | PASS | Query executed, no records (still proves view resolution) |
| 500 | "Invalid column name" | FAIL | View/table mismatch — the bug we're catching |
| 500 | other | FAIL | Graph extension or compilation error |
| 401/403 | — | WARN | Permission issue, not a code bug |

**Implementation details:**
- Reuses `AcumaticaSession` from `validate-publish.py` (login retry logic for post-publish app pool restart)
- No new dependencies — pure `urllib`, same as existing scripts
- Parses HTTP 500 body to surface the actual SQL error in pipeline output
- 30s timeout per probe (matches existing entity queries)
- Exit 0 if all passed, exit 1 if any failed

### 4. Pipeline wiring: `deploy-customization.yml`

Add a new step after each existing `validate-publish.py` call — three places:

| Gate | After Step | New Step Name |
|------|-----------|---------------|
| Sandbox Gate | "Validate custom fields on sandbox" | "E2E view-level smoke test" |
| Heritage Test Gate | "Validate Heritage Test" | "E2E view-level smoke test" |
| Production Deploy | "Post-publish field validation" | "E2E view-level smoke test" |

Each step runs:

```bash
python scripts/smoke-e2e.py --manifest publish-manifest.json
```

Same env vars as the existing validation steps (`ACUMATICA_URL`, `ACUMATICA_USERNAME`, `ACUMATICA_PASSWORD`, `ACUMATICA_TENANT`). No new secrets needed.

**Failure behavior:** Hard fail — blocks the next gate if any probe returns HTTP 500.

## Why this catches today's bug

Today's error: `VendorExt : PXCacheExtension<Vendor>` with columns on `BAccount` table. The `Vendor_Vendor` view doesn't expose `Usr*` columns.

The e2e probe for Vendor would execute:
```
GET /entity/Default/24.200.001/Vendor?$top=1&$select=VendorID,UsrDefaultInTransitSiteID,UsrDefaultCarrierCode
```

Acumatica generates: `SELECT [Vendor_Vendor].[UsrDefaultInTransitSiteID] FROM [Vendor_Vendor]` → SQL error → HTTP 500 → pipeline fails at sandbox gate → production never touched.

## Deliverables

1. **`publish-manifest.json`** — populated `custom_fields` + new `e2e_probes` section
2. **`scripts/smoke-e2e.py`** — new script, ~100 lines, pure urllib
3. **`deploy-customization.yml`** — three new pipeline steps (one per gate)
