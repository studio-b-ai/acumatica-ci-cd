# DRP Phase 0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the data foundation (signals, custom fields, MOQ intake, lead-time learning, ABC baseline, stockout logger, email watcher) that the DRP agent needs before it can compute a single recommendation.

**Architecture:** Parallelizable streams across 5 repos. No stream depends on another stream's completion; they can land in any order. Phase 1 (advisor / paper-trading) can start the moment any two signals are live — it does not block on Phase 0 finishing.

**Tech Stack:** Acumatica 24.x (SM208030 GIs, `AesthetikContainers` customization package), heritage-wms (React + Express + Postgres), webhook-router (TypeScript Express + Microsoft Graph + Claude SDK), studiob-api (Python FastAPI), cs-order-entry (Node.js).

**Design reference:** `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-09-drp-implementation-design.md` — every task in this plan maps back to a section there. Read the relevant section before starting the task.

---

## Execution Notes

- **One task = one PR.** Each task's "Commit" step should also open the PR.
- **TDD where tests exist.** heritage-wms, webhook-router, cs-order-entry have test infra — use it. Acumatica customization tasks don't have unit tests; verification is via Playwright against the live sandbox after deploy (see `superpowers:verification-before-completion`).
- **Business-hours discipline.** Tasks P0-1.1, P0-1.2, P0-1.3, P0-1.4, P0-2.1, P0-2.2 deploy to Acumatica and restart the app pool — they run outside 06:00-18:00 ET. All other tasks are zero-downtime.
- **Reuse-over-rebuild audit.** Each task header lists what's being reused. If the developer can't find that code where specified, STOP and ask before rewriting.
- **Absolute paths always.** No `./` or `../`.

---

## Stream A — Acumatica Data Exposure (1 week, off-hours)

### Task P0-A.1: Register `DRP_VelocityHistory` Generic Inquiry via SM208030

**Design ref:** Section 4.1, Section 6 (signal #1), Section 1.6 (blind spot — SalesOrder gateway 7-row cap)
**Reuses:** Existing GI builder + registration pipeline in `acumatica-ci-cd/scripts/` (see `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-03-29-gi-builder-engine-design.md`)
**Deploys during:** off-hours window

**Files:**
- Create: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainerGIs/GenericInquiries/DRP_VelocityHistory.xml`
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainerGIs/project.xml` (add GI to `Items` list)
- Test: `/Users/kevin/dev/acumatica-ci-cd/tests/integration/test_drp_velocity_gi.py`

**Step 1: Read existing GI as template**

Read `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainerGIs/GenericInquiries/ContainerTracking.xml` to understand the XML structure used by the existing registration pipeline. Match its format exactly.

**Step 2: Write the failing integration test**

```python
# tests/integration/test_drp_velocity_gi.py
def test_drp_velocity_history_gi_returns_nonempty_rows(studiob_api_client):
    resp = studiob_api_client.get("/acumatica/gi/DRP_VelocityHistory",
                                   params={"limit": 10, "$filter": "ShippedDate gt '2026-01-01'"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) > 0
    assert "InventoryID" in rows[0]
    assert "ShippedQty" in rows[0]
    assert "ShippedDate" in rows[0]
```

**Step 3: Run test to confirm it fails**

Run: `pytest tests/integration/test_drp_velocity_gi.py::test_drp_velocity_history_gi_returns_nonempty_rows -v`
Expected: `404` or `GI not found` — the GI does not exist yet.

**Step 4: Author the GI XML**

Table: `INTran` joined to `INRegister` filtered to shipment/invoice transactions. Columns: `InventoryID`, `ShippedQty` (Qty with sign), `ShippedDate` (TranDate), `SOType`, `SONbr`, `CustomerID`, `SiteID`. Filter: `TranType in ('INV','CRM','SHP')` and date range parameter (default 365 days back). Row limit disabled (return all matching rows).

**Step 5: Register GI in project.xml**

Add `<Item FullName="DRP_VelocityHistory" FileName="GenericInquiries\DRP_VelocityHistory.xml" />` to the `<Items>` list in `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainerGIs/project.xml`.

**Step 6: Deploy to test tenant via pipeline**

Run: `gh workflow run acumatica-deploy.yml -R studio-b-ai/acumatica-ci-cd -f target=test -f packages=AesthetikContainerGIs`
Expected: pipeline completes with "Import and publish customization: SUCCESS".

**Step 7: Verify in Acumatica UI (Playwright)**

Navigate to SM208000 (Generic Inquiry), filter ScreenID = `DRP_VelocityHistory`, confirm it exists and opens without error. Pull 100 rows and spot-check that ShippedQty is signed correctly (returns negative for credits).

**Step 8: Re-run the integration test**

Run: `pytest tests/integration/test_drp_velocity_gi.py::test_drp_velocity_history_gi_returns_nonempty_rows -v`
Expected: PASS.

**Step 9: Commit + PR**

```bash
git add Customization/AesthetikContainerGIs/GenericInquiries/DRP_VelocityHistory.xml \
         Customization/AesthetikContainerGIs/project.xml \
         tests/integration/test_drp_velocity_gi.py
git commit -m "feat(drp): register DRP_VelocityHistory GI for shipment history signal"
gh pr create --title "feat(drp): register DRP_VelocityHistory GI" --body "Phase 0 Task P0-A.1. Exposes shipment velocity history for DRP forecast engine. Unblocks SalesOrder gateway 7-row cap."
```

---

### Task P0-A.2: Register `DRP_OpenSOCommitments` Generic Inquiry

**Design ref:** Section 4.1, Section 6 (signal #2)
**Reuses:** Same GI registration pipeline as P0-A.1
**Deploys during:** off-hours

**Files:**
- Create: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainerGIs/GenericInquiries/DRP_OpenSOCommitments.xml`
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainerGIs/project.xml`
- Test: `/Users/kevin/dev/acumatica-ci-cd/tests/integration/test_drp_open_so_gi.py`

**Step 1: Write failing test**

Test pulls ≥1 row, asserts columns `InventoryID`, `SONbr`, `SOLineNbr`, `OrderQty`, `ShippedQty`, `OpenQty`, `RequestedShipDate`, `CustomerID`, `SOType`.

**Step 2: Author GI XML**

Table `SOLine` joined to `SOOrder`. Filter: `LineType='GoodsForInventory' AND OpenQty > 0 AND SOType in ('CO','SO')`. Columns as in step 1.

**Step 3: Register + deploy + verify + commit** (steps 3-7 mirror P0-A.1 steps 5-9)

---

### Task P0-A.3: Register `DRP_OpenPOLines` Generic Inquiry

**Design ref:** Section 4.1, Section 6 (signal #3), Section 1.6 (api-bot 403 on PurchaseOrder)
**Reuses:** Same pipeline
**Deploys during:** off-hours

**Files:**
- Create: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainerGIs/GenericInquiries/DRP_OpenPOLines.xml`
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainerGIs/project.xml`
- Test: `/Users/kevin/dev/acumatica-ci-cd/tests/integration/test_drp_open_po_gi.py`

**Step 1: Write failing test**

Assert columns `POOrderNbr`, `POLineNbr`, `InventoryID`, `VendorID`, `OrderQty`, `ReceivedQty`, `OpenQty`, `PromisedDate`, `UsrContainerNbr` (from `UsrContainerPOLink`), `UsrAcknowledgedDate`, `UsrFactoryReadyDate` (will be null until Task P0-B.1 lands).

**Step 2: Author GI**

Join `POLine` → `POOrder` → `UsrContainerPOLink` (left join) → `POOrderExt` (for Usr* fields). Filter `POLine.LineType='GoodsForInventory' AND OpenQty > 0`.

**Step 3-7: Register + deploy + verify + commit**

---

### Task P0-A.4: Register `InventoryAllocDetEnq` as SM208030 endpoint

**Design ref:** Section 4.1, Section 6 (signal #4)
**Reuses:** The inquiry already exists in Acumatica — we just need to register it for REST access
**Deploys during:** off-hours

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainerGIs/project.xml`
- Test: `/Users/kevin/dev/acumatica-ci-cd/tests/integration/test_drp_inv_alloc_gi.py`

**Step 1-5: Add `<Item>` entry, deploy, test, verify, commit**

See PXInquiry registration pattern for `InventoryAllocDetEnq` in Acumatica docs (search `studiob-knowledge` Qdrant for `inventoryallocdetenq rest`).

---

### Task P0-A.5: Add studiob-api gateway routes for the 4 new GIs

**Design ref:** Section 4.1 (last bullet)
**Reuses:** Existing GI-call helper in `/Users/kevin/code/studio-b/studiob-api/src/acumatica/gi_client.py`
**Deploys during:** anytime (zero downtime)

**Files:**
- Modify: `/Users/kevin/code/studio-b/studiob-api/src/routes/drp.py` (create if missing)
- Test: `/Users/kevin/code/studio-b/studiob-api/tests/routes/test_drp.py`

**Step 1: Write failing route tests**

One test per route: `GET /drp/velocity-history`, `GET /drp/open-so-commitments`, `GET /drp/open-po-lines`, `GET /drp/inventory-allocation`. Assert 200 + JSON list + at least one expected column.

**Step 2: Implement 4 thin wrappers**

Each wrapper: pull query params, call `gi_client.query("DRP_*")` with params, return JSON. No business logic.

**Step 3-5: Run tests, verify against live sandbox, commit**

---

## Stream B — Acumatica Custom Fields (1 week, off-hours)

### Task P0-B.1: Add `POOrder.UsrAcknowledgedDate` and `POOrder.UsrFactoryReadyDate`

**Design ref:** Section 4.2, Section 5.1
**Reuses:** Existing `POOrderExt` class in `AesthetikContainers`
**Deploys during:** off-hours (app pool restart)

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/Code/POOrderExt.cs` (or create if missing — verify first with `ls`)
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/Pages/PO/PO301000.aspx` (add fields to container-tracking panel)
- Test: `/Users/kevin/dev/acumatica-ci-cd/tests/e2e/test_po_custom_fields.py`

**Step 1: Verify package ground truth**

Run: `ls /Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/Code/ | grep -i POOrder`
Confirm `POOrderExt.cs` exists. If not, stop and check `git log --all -- 'Customization/AesthetikContainers/Code/POOrder*'` before assuming.

**Step 2: Write the failing Playwright test**

Test navigates to PO301000, opens any PO, asserts two new fields (`Vendor Acknowledged Date`, `Factory Ready Date`) are present in the container-tracking panel.

**Step 3: Add DAC fields**

```csharp
[PXDBDate]
[PXUIField(DisplayName = "Vendor Acknowledged Date")]
public virtual DateTime? UsrAcknowledgedDate { get; set; }
public abstract class usrAcknowledgedDate : PX.Data.BQL.BqlDateTime.Field<usrAcknowledgedDate> { }

[PXDBDate]
[PXUIField(DisplayName = "Factory Ready Date")]
public virtual DateTime? UsrFactoryReadyDate { get; set; }
public abstract class usrFactoryReadyDate : PX.Data.BQL.BqlDateTime.Field<usrFactoryReadyDate> { }
```

**Step 4: Add fields to ASPX**

Add two `<px:PXDateTimeEdit>` controls to the existing container-tracking panel in PO301000.aspx (find the panel by grepping for `UsrContainer` in the file).

**Step 5: Deploy to test tenant off-hours**

Follow standard deploy runbook. Watch for `--no-merge` ASPX drift — run the ASPX tripwire test if the file was touched. Verify publish SUCCESS.

**Step 6: Run Playwright verification**

Run: `python scripts/verify-container-tracking.py` (or the equivalent Playwright runner) — confirm fields visible, editable, save, reload, persist.

**Step 7: Commit + PR**

---

## Stream C — MOQ Intake (3 weeks)

### Task P0-C.1: Database migrations for `drp_vendor_moq_*` tables

**Design ref:** Section 4.3, Section 5.2
**Reuses:** heritage-wms migration framework (Drizzle or whatever's in `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/db/migrations/`)
**Deploys during:** anytime

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/db/migrations/NNNN_drp_moq.sql`
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/tests/db/test_drp_moq_schema.ts`

**Step 1: Write failing schema test**

Test opens a psql connection, runs `SELECT * FROM drp_vendor_moq_profiles LIMIT 0`, asserts columns exist.

**Step 2: Author migration SQL**

3 tables per Section 5.2:
- `drp_vendor_moq_profiles` (id, vendor_id, confidence, source_file_id, created_at, approved_at, approved_by)
- `drp_vendor_moqs` (id, profile_id, inventory_id, moq_qty, moq_uom, currency, unit_cost)
- `drp_vendor_moq_extractions` (id, vendor_guess, file_hash, raw_llm_output_jsonb, parsed_jsonb, confidence, review_status, reviewed_by, reviewed_at)

Plus indices: `(vendor_id, created_at)`, `(inventory_id, vendor_id)`, `(review_status)`.

**Step 3: Run migration locally, run test, commit**

---

### Task P0-C.2: `MOQIntake.tsx` page + `/routes/moq.ts` + `moq-intake-service.ts`

**Design ref:** Section 4.3
**Reuses:** `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/client/src/pages/ImportPackingSlip.tsx` (page template), `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/routes/receive.ts` (route shape), `smart-parser.ts` + `packing-slip-ocr.ts` + `column-mapper.ts` + `sku-matcher.ts` + `learning-store.ts` (parser stack, ~2000 LoC)

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/client/src/pages/MOQIntake.tsx`
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/routes/moq.ts`
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/moq-intake-service.ts` (~200 LoC)
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/tests/services/moq-intake-service.test.ts`

**Step 1: Read `ImportPackingSlip.tsx` fully**

Understand the upload → parse → review → approve flow. Copy it, don't reinvent it.

**Step 2: Write service-level failing tests**

Tests:
- `extracts MOQ from xlsx vendor quote with "Minimum Order Quantity" column`
- `extracts MOQ from pdf vendor quote via LLM fallback`
- `persists extraction rows with confidence scores`
- `writes approved profile to drp_vendor_moq_profiles`

Use realistic test fixtures from vendor quote samples (ask Kevin for 3-5 fixtures from past emails if none are checked in).

**Step 3: Implement service (thin wrapper over existing parsers)**

`parseAndExtract(file, vendorGuess)` → existing smart-parser → column-mapper extension → persist to extraction table. Learning handled by existing learning-store.

**Step 4: Add MOQ header patterns to column-mapper**

```typescript
// heritage-wms/src/services/column-mapper.ts
const MOQ_HEADER_PATTERNS = [
  /minimum\s*order\s*(quantity|qty)/i,
  /moq/i,
  /min\.?\s*order/i,
  /mindestbestellmenge/i,          // German
  /quantité\s*minimum/i,           // French
  /cantidad\s*mínima/i,            // Spanish
  /minimo.*ordine/i,               // Italian
  /minimo.*quantidade/i,           // Portuguese
];
```

**Step 5: Build route + page (thin)**

Route wraps the service; page wraps the existing ImportPackingSlip UI with MOQ-specific copy + review queue to `drp_vendor_moq_extractions`.

**Step 6-8: Run tests, manual smoke test, commit + PR**

---

### Task P0-C.3: `MOQBulkIntake.tsx` + `moq-bulk-orchestrator.ts`

**Design ref:** Section 4.4
**Reuses:** Concurrency pool and LLM cost tracking patterns from the smart-parser already in the repo

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/client/src/pages/MOQBulkIntake.tsx`
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/moq-bulk-orchestrator.ts` (~400 LoC)
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/tests/services/moq-bulk-orchestrator.test.ts`

**Step 1: Tests first**

- `processes 20 files concurrently with a limit of 8`
- `dedups files by MD5 before parsing`
- `guesses vendor from filename (case-insensitive substring match against Vendor.Name)`
- `tracks cumulative $ cost across all LLM calls in a run`
- `ranks extractions by confidence for the review queue`
- `bulk-approves selected extractions`

**Step 2: Implement orchestrator**

Use `p-limit` or built-in Promise concurrency for the 8-parallel pool. Store run state in `drp_vendor_moq_extraction_runs` (new table, add in an inline migration or fold into P0-C.1).

**Step 3: Build the bulk page**

Drag-drop zone → progress bar → review table → bulk-approve action.

**Step 4-6: Tests, smoke test, commit**

---

### Task P0-C.4: MOQ write-back to Acumatica `StockItem.VendorDetails.MinOrderQty`

**Design ref:** Section 4.3 (write-back bullet)
**Reuses:** studiob-api gateway client, existing StockItem PUT endpoint

**Files:**
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/moq-intake-service.ts` (approvedHook)
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/tests/services/moq-writeback.test.ts`

**Step 1: Failing test**

Test mocks studiob-api, asserts that approving a profile issues one `PUT /acumatica/stock-items/{inv_id}/vendor-details/{vendor_id}` with `MinOrderQty` in the payload, per item on the profile.

**Step 2: Implement write-back path**

On approval: iterate profile rows, call studiob-api PUT for each, log results to `drp_vendor_moq_writeback_log` (new small table, 2 cols: extraction_id, status, written_at, error). If studiob-api returns non-2xx, mark the row as `writeback_failed` so the review queue can re-try.

**Step 3: Verify end-to-end against sandbox**

Upload a known vendor quote, approve, verify in Acumatica SA202000 (Inventory → Stock Items) that VendorDetails shows the new MinOrderQty.

**Step 4: Commit + PR**

---

## Stream D — Vendor Lead Time Learning (1.5 weeks)

### Task P0-D.1: `drp_lead_time_samples` + `drp_vendor_lead_time_stats` migrations

**Design ref:** Section 4.5, Section 5.2, Section 12
**Reuses:** heritage-wms migration framework

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/db/migrations/NNNN_drp_lead_time.sql`
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/tests/db/test_drp_lead_time_schema.ts`

**Step 1: Schema tests first**

- `drp_lead_time_samples` columns: `id, po_nbr, po_line_nbr, vendor_id, inventory_id, po_placed_at, vendor_acked_at, factory_ready_at, shipped_at, arrived_at, received_at, ack_lag_days, production_days, transit_days, port_to_dock_days, total_lead_days, flagged_as_outlier, outlier_reason, created_at`
- `drp_vendor_lead_time_stats` (materialized view, refreshed nightly): `vendor_id, stage, mean, stddev, n_samples, p10, p50, p90, p95, last_sample_at, distribution_kind, lead_time_bias_days, country_beta`
- `drp_vendor_lead_time_regimes`: `vendor_id, start_at, end_at, regime_label, prior_stats_jsonb`

**Step 2: Author SQL**

Plain table + matview with indexed `(vendor_id, stage)` on the matview.

**Step 3: Run, test, commit**

---

### Task P0-D.2: Extend `vendor-scorecard-service.ts` with 4-stage distributions

**Design ref:** Section 4.5, Section 12.2, Section 12.3
**Reuses:** `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/vendor-scorecard-service.ts`

**Files:**
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/vendor-scorecard-service.ts`
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/lead-time-learner.ts` (new — keeps distribution math separate from scorecard rendering)
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/tests/services/lead-time-learner.test.ts`

**Step 1: Tests first (one per concept)**

- `computes 4-stage intervals from a sample with all 5 timestamps`
- `handles missing vendor_acked_at by nulling ack_lag_days and production_days but keeping total_lead_days`
- `rejects a sample with z > 3 from running mean (n≥10)`
- `folds in first 10 samples without outlier check`
- `fits lognormal or gamma and chooses the better-fitting one (Shapiro-Wilk)`
- `falls back to empirical quantiles when n < 10`
- `computes lead_time_bias_days from last 20 receipts vs promised`

**Step 2: Implement `lead-time-learner.ts`**

Pure functions. No database calls — takes arrays of samples and stats in, returns updated stats out. Database glue lives in the nightly mining job (Task P0-D.3).

**Step 3: Run tests, commit**

---

### Task P0-D.3: Nightly lead-time mining job

**Design ref:** Section 4.5, Section 12
**Reuses:** studiob-api PO receipts query, existing cron runner in heritage-wms

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/jobs/lead-time-mining-job.ts`
- Modify: heritage-wms cron registration file
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/tests/jobs/lead-time-mining-job.test.ts`

**Step 1: Failing integration test**

Mock studiob-api with 50 synthetic completed receipts from 5 vendors; assert that after the job runs:
- `drp_lead_time_samples` has 50 rows
- `drp_vendor_lead_time_stats` matview has 5 * 4 = 20 rows (5 vendors × 4 stages)
- Outliers (z>3) are flagged, not folded
- `lead_time_bias_days` populated

**Step 2: Implement job**

```
1. Query studiob-api for receipts completed since last_run_at
2. For each receipt, fetch linked PO + containers to build the 5 timestamps
3. Insert samples via lead-time-learner outlier check
4. Refresh drp_vendor_lead_time_stats materialized view
5. Run CUSUM regime check per vendor, archive regime changes to drp_vendor_lead_time_regimes
6. Write last_run_at
```

**Step 3: Run test, smoke test against sandbox, commit**

---

### Task P0-D.4: Weekly `Vendor.LeadTimedays` write-back

**Design ref:** Section 12.8

**Files:**
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/jobs/lead-time-mining-job.ts` (add weekly branch)
- Test: extend P0-D.3 test file

**Step 1: Failing test**

On Sunday runs, for vendors with n_samples≥10 on `total_lead_days` AND not in a regime-change state, assert the job calls studiob-api `PUT /acumatica/vendors/{id}` with `LeadTimedays=round(p50)`.

**Step 2: Implement Sunday branch**

Wrap in `if (isSunday(runDate))`. Small function — ~20 lines.

**Step 3: Verify against sandbox, commit**

---

### Task P0-D.5: `VendorScorecard.tsx` — 4 new columns

**Design ref:** Section 4.5

**Files:**
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/client/src/pages/VendorScorecard.tsx`
- Modify: corresponding route for enriched payload

**Step 1: Snapshot test failing**

Add vendor with known stats to test fixture, snapshot render includes `Ack Lag p50`, `Production p50`, `Transit p50`, `Total Lead p50`.

**Step 2: Update route + page to include the 4 stats, commit**

---

## Stream E — ABC Classification Baseline (3 days)

### Task P0-E.1: `drp_abc_schemes` + `drp_abc_classification_runs` + `drp_abc_classifications` + `drp_abc_backtest_results` migrations

**Design ref:** Section 4.6, Section 5.2, Section 9.1

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/db/migrations/NNNN_drp_abc.sql`
- Test: schema test

**Step 1: Tests for each table's columns**
**Step 2: Author SQL (4 tables, 1 initial row in `drp_abc_schemes` for `revenue_weighted_90`)**
**Step 3: Test + commit**

---

### Task P0-E.2: ABC classifier service + initial run

**Design ref:** Section 4.6, Section 9.1

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/abc-classifier.ts`
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/tests/services/abc-classifier.test.ts`
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/jobs/abc-classification-job.ts`

**Step 1: Failing tests**

- `revenue_weighted_90 scheme weights last 90 days 2x over prior 275 days`
- `classifies into A/B/C at 70/25/5 thresholds by cumulative revenue`
- `writes drp_abc_classifications row per item`
- `writes single drp_abc_classification_runs row with scheme_id + is_shadow=false`
- `active scheme and shadow schemes both run when shadow schemes exist`

**Step 2: Implement classifier + job**
**Step 3: Run classifier against sandbox data, spot-check top 20 A items are the expected bestsellers**
**Step 4: Commit**

---

### Task P0-E.3: Write-back `StockItem.ABCCode` to Acumatica

**Design ref:** Section 4.6
**Reuses:** studiob-api StockItem PUT endpoint

**Files:**
- Modify: `abc-classification-job.ts` (add write-back after classifier run)
- Test: assert the job issues one PUT per changed item

**Step 1: Failing test**
**Step 2: Implement — batched in groups of 50 to avoid Acumatica session exhaustion**
**Step 3: Verify in Acumatica UI, commit**

---

## Stream F — cs-order-entry Stockout Logger (2 days)

### Task P0-F.1: Stockout event emit + `drp_lost_demand_events` table

**Design ref:** Section 4.7, Section 5.2, Section 11.3 (stockout as censored demand)
**Reuses:** Existing cs-order-entry inventory badge logic

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/db/migrations/NNNN_drp_lost_demand.sql`
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/cs-order-entry/src/api/inventory.ts`
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/cs-order-entry/tests/api/inventory-stockout.test.ts`

**Step 1: Migration for `drp_lost_demand_events`**

Columns: `id, event_at, inventory_id, requested_qty, available_qty, customer_id, customer_class, so_nbr (nullable), session_id`.

**Step 2: Failing cs-order-entry test**

Simulate a request for qty 100 when only 40 is available. Assert a `drp_lost_demand_events` row is written with `requested_qty=100, available_qty=40`.

**Step 3: Implement ~40-line event emit**

At the point where the stockout badge is decided, fire-and-forget insert into the Postgres table via the existing heritage-wms DB pool. Must NOT block the response.

**Step 4: Test, smoke test, commit**

---

## Stream G — Vendor Acknowledgment Email Watcher (4 days)

### Task P0-G.1: `drp_signal_email_raw` + `drp_signal_email_parsed` migrations

**Design ref:** Section 4.8, Section 5.2

**Files:**
- Create: `/Users/kevin/dev/webhook-router/src/db/migrations/NNNN_drp_email.sql`
- Test: schema test

**Step 1-3: Tests, SQL, commit**

---

### Task P0-G.2: `po-email-watcher.ts` worker

**Design ref:** Section 4.8, Section 6 (signal #13)
**Reuses:** Existing Microsoft Graph subscription in webhook-router, existing Claude SDK wrapper, existing vendor-scorecard parser service as pattern reference

**Files:**
- Create: `/Users/kevin/dev/webhook-router/src/workers/po-email-watcher.ts`
- Test: `/Users/kevin/dev/webhook-router/tests/workers/po-email-watcher.test.ts`

**Step 1: Verify Graph subscription covers procurement inbox**

Run: `curl <graph subscription list endpoint>` — confirm `purchasing@heritagefabrics.com` (or whichever address per open question #4) is in the subscription. If NOT, add a subtask before proceeding.

**Step 2: Failing worker tests**

- `parses email with "We confirm your PO #123 is ready to ship by March 15"`
- `confidence ≥0.85 auto-writes UsrFactoryReadyDate via studiob-api`
- `confidence 0.60-0.85 writes to drp_signal_email_parsed with status='review'`
- `confidence <0.60 is ignored and logged`
- `raw email stored in drp_signal_email_raw regardless`

**Step 3: Implement worker**

Webhook handler → fetch message → Claude extraction (prompt template) → confidence bucket → write-back or queue.

**Step 4: Write the LLM extraction prompt**

Prompt returns JSON: `{ po_nbr, ack_date, factory_ready_date, confidence, evidence }`. Few-shot with 3 real sample emails (get from Kevin's procurement history).

**Step 5: Tests, smoke test against a captured real inbox message, commit**

---

### Task P0-G.3: Studiob-api writeback for `POOrder.UsrAcknowledgedDate` / `UsrFactoryReadyDate`

**Design ref:** Section 4.8 (write path)
**Depends on:** P0-B.1 (custom fields must exist before write-back works)

**Files:**
- Modify: `/Users/kevin/code/studio-b/studiob-api/src/routes/acumatica/purchase_orders.py`
- Test: `/Users/kevin/code/studio-b/studiob-api/tests/routes/test_po_writeback.py`

**Step 1: Failing test**

PATCH `/acumatica/purchase-orders/{nbr}` with `{"UsrAcknowledgedDate": "2026-04-15"}` — assert 200, field updated in Acumatica (integration test against sandbox).

**Step 2: Implement PATCH handler**
**Step 3: Verify against sandbox, commit**

---

## Stream H — DataLifecycleManager Policies (1 day)

### Task P0-H.1: Register `drp_*` policies

**Design ref:** Section 4 (reuse bullet), Section 5.3
**Reuses:** `/Users/kevin/dev/webhook-router/src/lib/data-lifecycle/` + `policies.ts` registry

**Files:**
- Modify: `/Users/kevin/dev/webhook-router/src/lib/data-lifecycle/policies.ts`
- Test: `/Users/kevin/dev/webhook-router/tests/lib/data-lifecycle/drp-policies.test.ts`

**Step 1: Failing test**

Assert that `DataLifecycleManager.getPolicy('drp-recommendations')` returns the expected hot/warm/cold configuration (90d/365d/GCS).

**Step 2: Add 5 policy entries**

Per Section 5.3 of the design:
- `drp-recommendations` (hot 90d, warm 365d, cold GCS)
- `drp-lead-time-samples` (hot 365d, warm 1095d, cold GCS)
- `drp-forecast-state` (hot 30d, warm 365d, weekly snapshots)
- `drp-agent-runs` (hot 90d, warm 365d)
- `drp-moq-extractions` (hot 180d, warm 730d, never prune)

**Step 3: Test + commit**

---

## Stream I — Signal Freshness + `drp_agent_runs` skeleton (optional in Phase 0, enables Phase 1 start)

### Task P0-I.1: Create `drp_agent_runs` + `drp_agent_run_events` tables

**Design ref:** Section 14.1, Section 14.7
**Rationale:** Phase 1 advisor mode can start the moment this table exists. It doesn't block Phase 0 completion but it lets paper-trading kick off early.

**Files:**
- Create: migration under heritage-wms
- Test: schema test

**Step 1-3: Tests, SQL, commit**

---

### Task P0-I.2: `drp_phase_config` singleton

**Design ref:** Section 8 (safety rails), Section 14.2, Section 15

**Files:**
- Create: migration
- Seed: single row with `phase='advisor', write_enabled=false`, full default config blob

**Step 1-3: Tests, SQL, commit**

---

## Post-Phase-0 Verification

Once all Phase 0 tasks land, run the end-to-end verification checklist:

1. All 4 DRP GIs return rows via studiob-api without auth errors
2. `POOrder.UsrAcknowledgedDate` editable in PO301000 UI (Playwright)
3. MOQ intake: upload a sample vendor quote, approve, confirm MinOrderQty appears in Acumatica SA202000
4. Lead-time mining job produces non-empty `drp_vendor_lead_time_stats` rows
5. ABC classifier writes A/B/C codes to StockItem for top 500 items
6. Stockout event logger writes a `drp_lost_demand_events` row on an intentional cs-order-entry stockout simulation
7. Email watcher parses a real captured vendor ack email and writes `UsrFactoryReadyDate`
8. DLM policies list shows the 5 new `drp-*` entries
9. `drp_phase_config` exists with `phase='advisor'` singleton

When all 9 pass, Phase 0 is DONE. Phase 1 advisor mode can be scheduled.

---

## Commit + PR hygiene

- Each task's commit message starts with `feat(drp):` or `chore(drp):` or `test(drp):`
- Reference the task ID in the PR title: `feat(drp): P0-A.1 DRP_VelocityHistory GI`
- PR body references the design doc section
- All PRs target `main` of their respective repo
- Cross-repo dependencies (P0-G.3 depends on P0-B.1) are called out in the PR body

---

## Unblockers / open questions gating Phase 0

Before starting, confirm with Kevin:

1. Procurement shared inbox identity (design Section 16, open Q #4) — single or multi address? Blocks P0-G.2.
2. SO types to exclude from cross-dock matching — default CO/SO only? Blocks P0-A.2 GI filter.
3. `StockItem.UsrCbmPerUnit` coverage — audit blocks the freight-consolidation math in Phase 2 but does not block Phase 0; schedule the audit as part of Phase 1 paper-trading insights.
4. Shadow-scheme promotion authority — procurement or Kevin? Affects Task P0-E.1 seed data.

None of these block the first several tasks. Stream A can start immediately.
