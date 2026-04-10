# DRP Phase 1 — Session 3 (Post-Fix Verification)

**Prior session ended:** 2026-04-10 ~1:15 PM ET (Session 2)
**Session 2 outcome:** Nightly run diagnosed (3 bugs), worker fixed, OData GI access unblocked on sandbox, PR #118 opened. Production OData exposure still needed.

## Read in order before doing anything

1. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_drp_implementation.md`
2. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_pcc_redesign.md`
3. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md`

## What happened in Session 2

### PR opened
| PR | Repo | What |
|---|---|---|
| [aesthetik-platform#118](https://github.com/studio-b-ai/aesthetik-platform/pull/118) | aesthetik-platform | Fix nightly DRP signal sync — wire orchestrator, OData GI Basic Auth, field name mapping |

### Three bugs fixed in PR #118

1. **Worker didn't call orchestrator.** `drp-signal-sync.ts` called 5 sync functions directly instead of `runNightlyPipeline()`. No forecast, no recs, no brief, no events logged.

2. **No error recovery.** When the worker threw (Acumatica GI 404), BullMQ caught it but nobody updated `drp_agent_runs.status` to `failed`. Run stuck as `running` forever. Added catch block that marks the run failed with error details.

3. **Wrong GI endpoint.** Sync service called `acumatica.query('GenericInquiry/DRP_VelocityHistory')` which hits the entity REST API — but GIs aren't entities. Added `queryGI()` method that uses the OData GI endpoint (`/t/<tenant>/api/odata/gi/<GIName>`) with **Basic Auth** (not session cookies — OData GI requires Basic Auth per Acumatica docs).

### OData GI field name mismatch (also fixed in PR #118)
OData GI returns Caption-derived column names, not DAC field names:
- `ShippedQty` not `QtyShipped`, `Site` not `SiteID`, `ShippedDate` not `TranDate`
- `SONbr` not `OrderNbr`, `Customer` not `CustomerID`, `ReqShipDate` not `ShipDate`
- `PONbr` not `OrderNbr`, `Vendor` not `VendorID`, `Received` not `ReceivedQty`
- `VendorAck'd` not `UsrAcknowledgedDate`, `FactoryReady` not `UsrFactoryReadyDate`

All field mappings updated with fallbacks for both formats. 549/549 tests pass.

### Acumatica configuration done in Session 2
- **BI role** added to `api-verify`, `api-bot`, `api-test` on all 3 tenants (sandbox, Heritage Test, prod) — required for OData GI access
- **"Expose via OData"** enabled on sandbox SM208000 for all 4 DRP GIs (Kevin did manually)
- **api-verify** has Administrator + BI + Customizer on production Heritage Fabrics tenant

### Other Session 2 deliverables
- Vendors UI verified: 6/6 routes pass on wms.asthetik.com
- Stuck run `aa189383-fb5c-47bf-9ad1-cae70a9872b0` marked as `failed` in DB
- Design doc line 354 updated: "complementary" not "mirrors" for SB501100 vs heritage-wms
- Kevin's Entra password stored in 1P as `entra-kevin-heritagefabrics`
- `acumatica-api-bot` 1P password doesn't match Railway `ACUMATICA_PASSWORD` — rotation drift

### Known: DRP GIs don't exist on Heritage Test tenant
The CI pipeline deploys customizations to Heritage Fabrics (production tenant), not Heritage Test. Heritage Test shares compiled code but doesn't get the GI definitions. The nightly run targets Heritage Test (per `ACUMATICA_TENANT` env var on Railway). **This is a problem** — the nightly run will 404 on GIs even after OData exposure because the GIs aren't on Heritage Test.

Options:
- A. Change `ACUMATICA_TENANT` to `Heritage Fabrics` on Railway (nightly reads from prod data — this is actually what we want for real recommendations)
- B. Deploy customization to Heritage Test separately
- Kevin needs to decide.

## Session 3 priorities

### Priority 1: Merge PR #118 + verify deploy

Check if PR #118 has been merged. If not, merge it. Heritage-wms auto-deploys from main on Railway.

### Priority 2: Enable "Expose via OData" on production

Use Playwright to log into `heritagefabrics.acumatica.com` as `api-verify` on **Heritage Fabrics** tenant (NOT Heritage Test). Navigate to SM208000 via the Main shell. For each of the 4 DRP GIs:

1. Click the magnifying glass 🔍 next to "Inquiry Title" — opens lookup popup
2. Search for the GI name in the popup search box
3. Click the GI row to select it — loads the GI into the form
4. Check "Expose via OData" checkbox
5. Ctrl+S to save

GI names: `DRP_VelocityHistory`, `DRP_OpenSOCommitments`, `DRP_OpenPOLines`, `DRP_InventoryBySite`

**Playwright pattern (TESTED in Session 2 — search KB for `playwright-odata-gi`):**

The Main shell wraps SM208000 in an iframe named `main`. Direct ASPX mode (`HideScript=On`) does NOT render the OData checkbox — you MUST use the Main shell.

```javascript
// 1. Get iframe offset
const iframeEl = await page.$('iframe[name="main"]');
const box = await iframeEl.boundingBox();

// 2. Click magnifying glass (iframe-relative ~373, 128)
await page.mouse.click(box.x + 373, box.y + 128);
await page.waitForTimeout(3000);
// "Select - Inquiry Title" popup opens

// 3. Click popup search box, type GI name, Enter to filter
// Search box is in the popup header — find its position from screenshot
await page.mouse.click(box.x + searchBoxX, box.y + searchBoxY);
await page.keyboard.type('DRP_VelocityHistory');
await page.keyboard.press('Enter');
await page.waitForTimeout(2000);

// 4. Click the result row to load the GI
// 5. Click "Expose via OData" checkbox
// 6. Ctrl+S to save
```

**CRITICAL DO-NOTs:**
- DO NOT use `fill('')` on the Inquiry Title — triggers "Insert new GI" error
- DO NOT set `_state` hidden inputs via JS — Acumatica ignores _state changes not triggered by the checkbox control's event handler
- DO NOT use direct ASPX mode — checkboxes don't render

### Priority 3: Verify OData endpoint works on production

```bash
ACUMATICA_URL="https://heritagefabrics.acumatica.com"
# Use api-bot (what heritage-wms uses) — password from Railway, NOT from 1P (they're mismatched)
API_BOT_PASSWORD=$(cd ~/dev/aesthetik-platform && railway variables --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['ACUMATICA_PASSWORD'])")

curl -s -u "api-bot:${API_BOT_PASSWORD}" \
  -H "Accept: application/json" \
  "https://heritagefabrics.acumatica.com/t/Heritage%20Test/api/odata/gi/DRP_VelocityHistory?\$top=3"
```

If this 404s because Heritage Test doesn't have the GIs, switch tenant to Heritage Fabrics:
```bash
curl -s -u "api-bot:${API_BOT_PASSWORD}" \
  -H "Accept: application/json" \
  "https://heritagefabrics.acumatica.com/t/Heritage%20Fabrics/api/odata/gi/DRP_VelocityHistory?\$top=3"
```

If Heritage Fabrics works but Heritage Test doesn't, Kevin needs to decide whether to change `ACUMATICA_TENANT` to `Heritage Fabrics` on Railway.

### ~~Priority 4: Resolve ACUMATICA_TENANT for nightly run~~ DONE

Changed in Session 2: `ACUMATICA_TENANT=Heritage Fabrics` on Railway. Phase 1 is read-only (`write_enabled=false`), zero risk to production. Real data needed for meaningful paper trading.

### Priority 5: Fix api-bot 1P password drift

The 1P `acumatica-api-bot` entry has a different password than what's on Railway's `ACUMATICA_PASSWORD`. Either:
- Update 1P to match Railway: `op item edit acumatica-api-bot --password="$(cd ~/dev/aesthetik-platform && railway variables --json | python3 -c "import sys,json; print(json.load(sys.stdin)['ACUMATICA_PASSWORD'])")"`
- Or update Railway to match 1P (riskier — may break existing sessions)

### Priority 6: Cst_POReceiptEntry for Sarah

SM201010 Access Rights on production — grant access to `Cst_POReceiptEntry` graph entity for Sarah's admin role. Needs admin login to production. See KB entry (Qdrant: `Cst_POReceiptEntry access rights bug`).

### Priority 7: Trigger manual nightly run

After PR #118 deployed + OData exposed + tenant resolved:
```bash
# Connect to heritage-wms Redis and trigger the job manually
# Or use the BullMQ dashboard if available
# Or wait for the next 06:00 UTC cron fire
```

Check `drp_agent_runs` for the new run:
```sql
SELECT id, run_date, status, run_state, started_at, finished_at, summary::text
FROM drp_agent_runs WHERE run_date >= '2026-04-10' ORDER BY started_at DESC LIMIT 5;
```

## Repos in play

- `aesthetik-platform` at `/Users/kevin/dev/aesthetik-platform/` (PR #118)
- `acumatica-ci-cd` at `/Users/kevin/dev/acumatica-ci-cd/` (design doc fix, uncommitted)

## Database connection

```
DATABASE_URL="postgresql://wms:41PNF7MJujb7I0yfikMUYdpV@nozomi.proxy.rlwy.net:38241/heritage_wms"
```
Use `/opt/homebrew/Cellar/postgresql@16/16.13/bin/psql` (not in PATH).

## What's NOT in scope for Session 3

- PCC Acumatica redesign (SB501000/SB501100/SB501200)
- Phase 2 implementation
- Exogenous signals (HubSpot, Shopify)
- Accuracy tracking
