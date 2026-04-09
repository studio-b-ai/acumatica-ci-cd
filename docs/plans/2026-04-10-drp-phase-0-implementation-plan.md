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
- **Business-hours discipline.** Stream A and Stream B deploy to Acumatica and restart the app pool — they run outside 06:00-18:00 ET. All other tasks are zero-downtime.
- **Reuse-over-rebuild audit.** Each task header lists what's being reused. If the developer can't find that code where specified, STOP and ask before rewriting.
- **Absolute paths always.** No `./` or `../`.

---

## 2026-04-09 Revision Log — Wave 1 shipped, structural corrections applied

Session 3 (DRP Phase 0 execution kickoff) corrected several structural assumptions in the original plan and shipped Wave 1. Each correction is documented at the affected task below; this section is the index.

### Wave 1 — 7 PRs shipped on 2026-04-09

| Task | File / Artifact | PR |
|---|---|---|
| **P0-G.1** | `webhook-router/src/lib/drp-email/db.ts` + `__tests__/db.test.ts` | [studio-b-ai/webhook-router#68](https://github.com/studio-b-ai/webhook-router/pull/68) |
| **P0-I.1** | `src/migrations/023_drp_agent_runs.sql` | [studio-b-ai/aesthetik-platform#102](https://github.com/studio-b-ai/aesthetik-platform/pull/102) |
| **P0-I.2** | `src/migrations/024_drp_phase_config.sql` | [studio-b-ai/aesthetik-platform#103](https://github.com/studio-b-ai/aesthetik-platform/pull/103) |
| **P0-C.1** | `src/migrations/025_drp_vendor_moq.sql` | [studio-b-ai/aesthetik-platform#104](https://github.com/studio-b-ai/aesthetik-platform/pull/104) |
| **P0-D.1** | `src/migrations/026_drp_lead_time.sql` | [studio-b-ai/aesthetik-platform#105](https://github.com/studio-b-ai/aesthetik-platform/pull/105) |
| **P0-E.1** | `src/migrations/027_drp_abc.sql` (+ `revenue_weighted_90` seed) | [studio-b-ai/aesthetik-platform#106](https://github.com/studio-b-ai/aesthetik-platform/pull/106) |
| **P0-F.1 (storage half)** | `src/migrations/028_drp_lost_demand.sql` | [studio-b-ai/aesthetik-platform#107](https://github.com/studio-b-ai/aesthetik-platform/pull/107) |

All 6 heritage-wms migrations verified against a local Postgres 16 DB before PR: cleanroom apply of all 28 migrations on empty DB, idempotent re-run, CHECK constraints enforced, FK cascades verified, 302/302 vitest still passing.

### Structural corrections applied to the plan

1. **heritage-wms is now `studio-b-ai/aesthetik-platform` on GitHub.** The directory name is still `heritage-wms` locally, but the repo remote points at `aesthetik-platform.git`. All PRs open against that repo.
2. **heritage-wms migration framework** = numbered SQL files in `src/migrations/` (NOT `src/db/migrations/`), `run.ts` runner with `_migrations` tracking table. Convention allows duplicate number prefixes. The plan originally referenced a non-existent path.
3. **webhook-router has NO migration framework.** Tables are created via inline `initXxxTable(pool)` functions in `src/lib/*/db.ts` wired into `src/index.ts` startup sequence. P0-G.1 follows this pattern — new file at `src/lib/drp-email/db.ts`.
4. **Stream A GIs are inline blocks in `Customization/AesthetikContainers/project.xml`**, NOT per-file XMLs in `Customization/AesthetikContainerGIs/GenericInquiries/`. The `AesthetikContainerGIs` package was deleted on 2026-04-09 by [acumatica-ci-cd#303](https://github.com/studio-b-ai/acumatica-ci-cd/pull/303) — it was a dead duplicate of content already shipping inside `AesthetikContainers`. GIs like `POContainers` (SB401000), `ContainerEvents` (SB401020), `POContainerLines` (SB401040) already ship as inline `<GenericInquiryScreen><data-set>...` blocks inside that package's project.xml. DRP GIs follow the same pattern in the same file. **Free ScreenID slots in AesthetikContainers: SB401080, SB401090, SB401100, SB401110** (SB401000/20/40/50/60/70 taken; GI007000 taken by InventoryQuantityDetail).
5. **P0-A.1 base tables corrected** from `INTran × INRegister` to `SOShipLine × SOShipment`. The original plan's INTran approach would have mixed shipments, credits, and adjustments without a clean way to filter to just shipped sales. SOShipLine joined to SOShipment filtered on `Confirmed=1 AND Operation='I'` gives the clean shipment-qty × date stream the forecaster needs.
6. **P0-A.2 SO type filter** resolved from "default CO/SO only (confirm or override)" to `('CO','SO','PC')` per 2026-04-09 answer. The PC type exists and must be included. Verification of the `SOOrderType` code against the sandbox will happen during Stream A deploy prep (the default Acumatica REST endpoint doesn't expose the `SalesOrderType` entity so verification requires a direct sandbox query or UI check).
7. **P0-A.4 InventoryAllocDetEnq scrapped.** The original plan said "register InventoryAllocDetEnq as SM208030 endpoint" — but InventoryAllocDetEnq is a `PXProcessing` graph, not a Generic Inquiry, and SM208030 only registers GIs. The existing `GI007000 InventoryQuantityDetail` GI in AesthetikContainers is close in spirit but is hard-filtered to `SiteID = 99` (WH99 only) and returns per-item summary rows, not per-site breakdown. **P0-A.4 replacement: fresh `DRP_InventoryBySite` GI** — `InventoryItem × INSiteStatus` (no WH99 filter) returning `(InventoryID, SiteID, QtyOnHand, QtyAvail, QtyHardAvail)`. Copies the join pattern from `GI007000` but drops the filter and adds site dimensionality.
8. **P0-B.1 must land before P0-A.3.** P0-A.3's GI references `POOrderExt.UsrAcknowledgedDate` and `POOrderExt.UsrFactoryReadyDate`, which don't exist until P0-B.1 ships them. Stream A ordering: A.1 → A.2 → B.1 → A.3 → A.4. All four are off-hours deploys; sequencing constraint is "do B.1 between A.2 and A.3."
9. **Stream D WMSTL audit result.** The design doc mentioned a `WMSTLVendorLeadTimes` table joined from GI007000. Audit (2026-04-09) confirmed: table exists but has zero code references across all 5 Studio B repos (webhook-router, heritage-wms, acumatica-ci-cd, cs-order-entry, studiob-api), unknown IIG-vendor ownership, single-column schema (`LeadTimeDays`). **Decision: build fresh `drp_vendor_lead_time_*` tables, do NOT extend WMSTL.** The 4-stage distribution schema is fundamentally richer than what WMSTL provides, and ownership ambiguity makes extension risky. Shipped as part of P0-D.1 migration 026.
10. **Stream F architecture corrected.** The original plan had cs-order-entry writing `drp_lost_demand_events` directly via the heritage-wms DB pool — that's a cross-service direct-DB-write anti-pattern. **Corrected: cs-order-entry emits via `POST /drp/lost-demand` on heritage-wms**, fire-and-forget with idempotency key `{so_line_id}:{decision_timestamp}` in `source_event_id`. The storage table (P0-F.1 storage half) shipped in PR #107; the receiver endpoint and emitter client are tracked as P0-F.1 code half.
11. **Stream H (P0-H.1) DEFERRED.** The DataLifecycleManager in webhook-router is a snapshot system that captures data into a single `data_snapshots` table + GCS, with policies describing snapshot frequency and retention tiers — it's NOT a per-table retention manager for drp_* tables in another database. The 5 policy keys in the original plan describe tables that live in heritage-wms Postgres, not webhook-router's. Cross-DB capture isn't in the existing DLM architecture. Adding the policy entries as scaffolding now would be dead code. Deferred until Phase 1 resolves whether DRP snapshots belong in heritage-wms (local DLM fork) or whether webhook-router grows a cross-DB reader.
12. **Stream I promoted from optional to Wave-1 required.** The original plan flagged I.1/I.2 as "optional in Phase 0, enables Phase 1 start." That framing was backwards: Phase 1 advisor mode cannot start without `drp_agent_runs` (no place to persist run metadata) or `drp_phase_config` (no place to read kill-switches + tuning knobs). Both are small migrations and their absence would block the whole Phase 1 launch. Promoted to Wave 1, shipped 2026-04-09.
13. **P0-C.4 write-back target.** Design doc Section 4.3 says "approved MOQs sync to Acumatica `StockItem.VendorDetails.MinOrderQty`" — but the correct Acumatica entity for per-(vendor, item) MOQ is `POVendorInventory.MinOrderQty`, not `StockItem.VendorDetails`. `StockItem.VendorDetails` is a POVendorInventory rendering on the StockItem screen; the underlying PUT path is against POVendorInventory. Corrected in P0-C.4 below.

### Open questions resolved in this session (see bottom of file for unresolved)

| Question | Answer | Affects |
|---|---|---|
| Procurement shared inbox identity | `imports@heritagefabrics.com` (single address) | P0-G.2 |
| SO types to include in cross-dock matching | `CO`, `SO`, `PC` (include PC) | P0-A.2 |
| Shadow-scheme promotion authority | Kevin approval (via Slack, stamps `approved_by` column) | P0-E.1 |
| `StockItem.UsrCbmPerUnit` coverage audit | DEFERRED to Phase 1 — doesn't block Phase 0 | P2+ freight NPV math |

---

## Stream A — Acumatica Data Exposure (1 week, off-hours)

**STRUCTURAL NOTE (2026-04-09):** All four new DRP GIs are inline `<GenericInquiryScreen>` blocks inside `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml` — NOT per-file XMLs in a deleted `AesthetikContainerGIs/GenericInquiries/` directory. Pattern: copy the existing `POContainers` (ScreenID SB401000, DesignID c51f9373-0b67-4955-9fce-ea35570bb2d0) block at ~line 1872 as template. Free ScreenIDs in the SB401xxx range: **SB401080 (A.1), SB401090 (A.2), SB401100 (A.3), SB401110 (A.4).** Generate fresh UUIDs for each DesignID. Sitemap entries go in the same project.xml's SiteMap section (also already inline, see ~line 1904).

### Task P0-A.1: Add `DRP_VelocityHistory` GI (ScreenID SB401080) as inline block in AesthetikContainers

**Design ref:** Section 4.1, Section 6 (signal #1), Section 1.6 (blind spot — SalesOrder gateway 7-row cap)
**Reuses:** Existing inline `<GenericInquiryScreen>` pattern in AesthetikContainers/project.xml. Copy the POContainers block (~line 1872) as template; it's the canonical example of an SB401xxx GI in this package.
**Deploys during:** off-hours window (app pool restart)
**ScreenID:** `SB401080`
**DesignID:** generate fresh UUID — e.g. `uuidgen | tr 'A-Z' 'a-z'`

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml` (add one inline `<GenericInquiryScreen>` block + one `<row ...>` inside the existing SiteMap section)
- Test: `/Users/kevin/dev/acumatica-ci-cd/tests/integration/test_drp_velocity_gi.py`

**Step 1: Read existing GI as template**

Read the POContainers inline block starting around line 1872 of `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml`. The structure is:
```xml
<GenericInquiryScreen>
  <data-set>
    <relations format-version="3" ...>...</relations>
    <layout>...</layout>
    <data>
      <GIDesign>
        <row DesignID="..." Name="..." ScreenID="SB401xxx" ...>
          <GITable Alias="..." Name="..."><GIResult .../></GITable>
          <GIWhere ... />
          <GISort ... />
          <SiteMap linkname="toDesignById"><row Position="..." Title="..." Url="..." ScreenID="SB401xxx" NodeID="..." .../></SiteMap>
        </row>
      </GIDesign>
    </data>
  </data-set>
</GenericInquiryScreen>
```

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

**Step 4: Author the GI inline block**

Base tables: **`SOShipLine` joined to `SOShipment`** (NOT `INTran × INRegister` — the original plan's misread). SOShipLine × SOShipment gives a clean shipment-qty × shipment-date × SO-linkage stream filtered to confirmed shipments.

- Main table: `SOShipLine` (Name="PX.Objects.SO.SOShipLine")
- Join: `SOShipment` on `(ShipmentNbr)` L-join
- Join: `SOLine` on `(OrigOrderType, OrigOrderNbr, OrigLineNbr)` L-join to carry customer + SO context
- Filter (`<GIWhere>`):
  - `SOShipment.Confirmed = true`
  - `SOShipment.Operation = 'I'` (Issue, not Receipt — excludes return receipts)
  - `SOShipment.ShipDate >= @FromDate` where `@FromDate` default = today − 365d
- Columns (`<GIResult>`):
  - `SOShipLine.InventoryID` → "InventoryID"
  - `SOShipLine.ShippedQty` → "ShippedQty" (positive for Issue; use the stored sign, do NOT re-derive)
  - `SOShipment.ShipDate` → "ShippedDate"
  - `SOShipLine.OrigOrderType` → "SOType"
  - `SOShipLine.OrigOrderNbr` → "SONbr"
  - `SOLine.CustomerID` → "CustomerID"
  - `SOShipLine.SiteID` → "SiteID"
  - `SOShipLine.UOM` → "UOM"
- Sort: `SOShipment.ShipDate DESC`
- Row limit: unlimited

**Step 5: Add inline block to project.xml**

Append the `<GenericInquiryScreen>` block inside `Customization/AesthetikContainers/project.xml`, followed by a `<SiteMap><row Position="..." Title="DRP Velocity History" Url="~/GenericInquiry/GenericInquiry.aspx?id={NEW_DESIGN_ID}" ScreenID="SB401080" NodeID="{fresh UUID}" ParentID="{same ParentID as POContainers}" /></SiteMap>` entry inside the existing SiteMap section so the GI shows up in the Container Tracking workspace navigation.

**Step 6: Deploy to sandbox (off-hours)**

Business-hours lockout: after 18:00 ET. Run: `gh workflow run acuops-deploy.yml -R studio-b-ai/acumatica-ci-cd -f target=staging -f project=AesthetikContainers`
Expected: pipeline completes with "Import and publish customization: SUCCESS". Watch the deploy-countdown Slack notification, do not close terminal until post-publish verification step is green.

**Step 7: Verify in Acumatica UI (Playwright)**

Navigate to SM208000, filter ScreenID = `SB401080`, confirm `DRP_VelocityHistory` opens. Pull 100 rows, spot-check that `ShippedQty > 0` and `ShippedDate` is within the last year. **Per Kevin's rule #4, "pipeline success" is NOT verification — loading the screen in Playwright against the live sandbox IS verification.**

**Step 8: Re-run the integration test**

Run: `pytest tests/integration/test_drp_velocity_gi.py::test_drp_velocity_history_gi_returns_nonempty_rows -v`
Expected: PASS.

**Step 9: Commit + PR**

```bash
git add Customization/AesthetikContainers/project.xml \
         tests/integration/test_drp_velocity_gi.py
git commit -m "feat(drp): P0-A.1 DRP_VelocityHistory GI (SB401080) in AesthetikContainers"
gh pr create --title "feat(drp): P0-A.1 DRP_VelocityHistory GI (SB401080)" --body "Phase 0 Task P0-A.1. Adds inline SOShipLine × SOShipment GI to AesthetikContainers/project.xml. Exposes shipment velocity history as signal #1 for the DRP forecaster. Off-hours deploy because AesthetikContainers publish restarts the app pool."
```

---

### Task P0-A.2: Add `DRP_OpenSOCommitments` GI (ScreenID SB401090) as inline block in AesthetikContainers

**Design ref:** Section 4.1, Section 6 (signal #2)
**Reuses:** Same inline-block pattern as P0-A.1
**Deploys during:** off-hours (app pool restart)
**ScreenID:** `SB401090`
**DesignID:** generate fresh UUID

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml` (add inline block + SiteMap row)
- Test: `/Users/kevin/dev/acumatica-ci-cd/tests/integration/test_drp_open_so_gi.py`

**Step 1: Write failing test**

Test pulls ≥1 row, asserts columns `InventoryID`, `SONbr`, `SOLineNbr`, `OrderQty`, `ShippedQty`, `OpenQty`, `RequestedShipDate`, `CustomerID`, `SOType`.

**Step 2: Pre-deploy sanity check — confirm `PC` SOType exists in the sandbox**

The SO type filter is `('CO','SO','PC')` per the 2026-04-09 session answer. Acumatica's default REST endpoint does NOT expose the `SalesOrderType` entity, so this cannot be verified via a REST GET. Two options to confirm PC exists before the GI goes live:
- (a) Temporarily set up a throwaway `$adHocSchema` query against SO301000 to dump the distinct `OrderType` values
- (b) Manual: log into sandbox, go to SO201000 (Order Types), visually confirm PC is in the list

Do one of the two before opening the PR so the GI filter matches reality. If PC doesn't exist in sandbox, fall back to `('CO','SO')` and flag it in the PR body for Kevin to override.

**Step 3: Author GI inline block**

- Main table: `SOLine` (Name="PX.Objects.SO.SOLine")
- Join: `SOOrder` on `(OrderType, OrderNbr)` L-join
- Filter (`<GIWhere>`):
  - `SOLine.LineType = 'GoodsForInventory'`
  - `SOLine.OpenQty > 0`
  - `SOLine.OrderType IN ('CO','SO','PC')`
- Columns: `InventoryID, OrderType (→ SOType), OrderNbr (→ SONbr), LineNbr (→ SOLineNbr), OrderQty, ShippedQty, OpenQty, RequestedDate (→ RequestedShipDate), SOOrder.CustomerID, SOLine.SiteID, SOLine.UOM`

**Step 4-8: Inline block + SiteMap row + deploy + Playwright verify + commit** (mirrors P0-A.1 steps 5-9)

---

### Task P0-A.3: Add `DRP_OpenPOLines` GI (ScreenID SB401100) as inline block in AesthetikContainers

**Design ref:** Section 4.1, Section 6 (signal #3), Section 1.6 (api-bot 403 on PurchaseOrder)
**Reuses:** Same inline-block pattern as P0-A.1/A.2
**Deploys during:** off-hours (app pool restart)
**ScreenID:** `SB401100`
**DesignID:** generate fresh UUID
**⚠️ HARD DEPENDENCY: P0-B.1 MUST land first.** This GI's `<GIResult>` list references `POOrderExt.UsrAcknowledgedDate` and `POOrderExt.UsrFactoryReadyDate` which don't exist until P0-B.1 ships them. Stream A deploy ordering MUST be: A.1 → A.2 → **B.1** → A.3 → A.4. If you try to deploy A.3 before B.1, the GI will fail to publish with a "field not found" error on the DAC extension.

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml` (add inline block + SiteMap row)
- Test: `/Users/kevin/dev/acumatica-ci-cd/tests/integration/test_drp_open_po_gi.py`

**Step 1: Write failing test**

Assert columns `POOrderNbr`, `POLineNbr`, `InventoryID`, `VendorID`, `OrderQty`, `ReceivedQty`, `OpenQty`, `PromisedDate`, `ContainerNbr` (from `UsrContainerPOLink` → `UsrContainer`), `UsrAcknowledgedDate`, `UsrFactoryReadyDate`.

**Step 2: Author GI inline block**

- Main table: `POLine` (Name="PX.Objects.PO.POLine")
- Join: `POOrder` on `(OrderType, OrderNbr)` L-join
- Join: `UsrContainerPOLink` on `(OrderType, OrderNbr, LineNbr)` L-join (for container association)
- Join: `UsrContainer` on `(ContainerID)` L-join (for ContainerCD display)
- Note: `POOrderExt` fields (`UsrAcknowledgedDate`, `UsrFactoryReadyDate`) are automatically available as `POOrder.UsrAcknowledgedDate` / `POOrder.UsrFactoryReadyDate` inside a GI once the DAC extension is deployed — no separate `<GITable>` entry needed.
- Filter (`<GIWhere>`):
  - `POLine.LineType = 'GoodsForInventory'`
  - `POLine.OpenQty > 0`
  - `POOrder.Status IN ('N','O')` (Pending or Open)
- Columns: `POLine.OrderType, POLine.OrderNbr (→ POOrderNbr), POLine.LineNbr (→ POLineNbr), POLine.InventoryID, POLine.VendorID, POLine.OrderQty, POLine.ReceivedQty, POLine.OpenQty, POLine.PromisedDate, UsrContainer.ContainerCD (→ ContainerNbr), POOrder.UsrAcknowledgedDate, POOrder.UsrFactoryReadyDate`

**Step 3-7: Inline block + SiteMap row + deploy + Playwright verify + commit** (mirrors P0-A.1 steps 5-9)

---

### Task P0-A.4: Add `DRP_InventoryBySite` GI (ScreenID SB401110) as inline block in AesthetikContainers

**Design ref:** Section 4.1, Section 6 (signal #4)
**Reuses:** The `GI007000 InventoryQuantityDetail` block in AesthetikContainers/project.xml (~line 1305) provides a working `InventoryItem × INSiteStatus` join pattern to copy. The key difference: GI007000 is hard-filtered to `SiteID = 99` and returns per-item summary rows, while P0-A.4 needs per-(item × site) breakdown across ALL sites.
**Deploys during:** off-hours (app pool restart)
**ScreenID:** `SB401110`
**DesignID:** generate fresh UUID

**⚠️ ORIGINAL PLAN WAS WRONG.** The original task said "Register `InventoryAllocDetEnq` as SM208030 endpoint." That does not work — `InventoryAllocDetEnq` is a `PXProcessing` graph (Inventory Allocation Details inquiry, SM208030 source), NOT a Generic Inquiry. SM208030 only registers GIs. You can access the graph via the contract-based REST endpoint, but that's a different code path that doesn't go through the GI infrastructure. The DRP agent needs a GI for consistency with A.1/A.2/A.3 and so the studiob-api gateway (P0-A.5) can use one code path for all four signals.

**The correct approach:** build a fresh `DRP_InventoryBySite` GI that selects `InventoryItem × INSiteStatus` returning `(InventoryID, SiteID, QtyOnHand, QtyAvail, QtyHardAvail, InventoryItem.ItemStatus)` with no WH99 filter. This exposes per-site availability across the whole warehouse footprint — exactly what the DRP agent needs for cross-dock matching (which can't work if it only sees WH99).

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml` (add inline block + SiteMap row)
- Test: `/Users/kevin/dev/acumatica-ci-cd/tests/integration/test_drp_inventory_by_site_gi.py`

**Step 1: Read GI007000 as template**

Open `Customization/AesthetikContainers/project.xml` around line 1305 (`DesignID="b7e3a1d4-92f6-4c8a-b5d1-1a2b3c4d5e6f" Name="InventoryQuantityDetail" ScreenID="GI007000"`). Copy the `<GITable Alias="InventoryItem">` + `<GITable Alias="INSiteStatus">` join structure. Drop all the other joins (POVendorInventory, POLine, UsrContainer, etc.) and the `SiteID = 99` `<GIWhere>` entry.

**Step 2: Write failing test**

```python
def test_drp_inventory_by_site_gi_returns_multiple_sites(studiob_api_client):
    resp = studiob_api_client.get("/acumatica/gi/DRP_InventoryBySite", params={"limit": 500})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) > 0
    sites = set(r["SiteID"] for r in rows)
    assert len(sites) > 1, f"Expected rows from multiple sites, got only {sites}"
    for col in ("InventoryID", "SiteID", "QtyOnHand", "QtyAvail"):
        assert col in rows[0]
```

**Step 3: Author GI inline block**

- Main table: `InventoryItem` (Name="PX.Objects.IN.InventoryItem")
- Join: `INSiteStatus` on `(InventoryID)` L-join
- Filter (`<GIWhere>`):
  - `InventoryItem.StkItem = true` (stock items only; template/non-stock items are noise)
  - `InventoryItem.ItemStatus IN ('AC','NS')` (Active + No Sales, exclude Marked For Deletion + Inactive)
  - NO SiteID filter — return rows for every (item, site) combination
- Columns: `InventoryItem.InventoryCD (→ InventoryID), InventoryItem.Descr, InventoryItem.ItemStatus, InventoryItem.ItemClassID, INSiteStatus.SiteID, INSiteStatus.QtyOnHand, INSiteStatus.QtyAvail, INSiteStatus.QtyHardAvail, INSiteStatus.QtyAllocated`
- Sort: `InventoryItem.InventoryCD, INSiteStatus.SiteID`

**Step 4-8: Inline block + SiteMap row + deploy + Playwright verify + commit** (mirrors P0-A.1 steps 5-9)

**Notes for the implementer:**
- The GI will be LARGE (every stock item × every site). Set `ExposeViaOData=1` but consider NOT setting `ExposeViaMobile=1` — this isn't a user-facing GI.
- The DRP agent will call it with `?$filter=QtyAvail gt 0` or `?$filter=InventoryID in ('XYZ','ABC')` to trim the response — the filter pushes down into the SQL.
- If the GI deploy fails with a timeout, add a date or ABC-class filter as a last resort. Do not change the base table structure.

---

### Task P0-A.5: Add studiob-api gateway routes for the 4 new GIs

**Design ref:** Section 4.1 (last bullet)
**Reuses:** Existing GI-call helper in studiob-api (verify exact path via `ls` before writing — the plan's original reference to `src/acumatica/gi_client.py` is unverified and studiob-api structure may have shifted)
**Deploys during:** anytime (zero downtime, Railway service)
**Depends on:** P0-A.1, P0-A.2, P0-A.3, P0-A.4 all deployed to sandbox (GI names must resolve via SM208030 before the route test passes)

**Files:**
- Modify: studiob-api routes module (exact path TBD — verify ground truth first)
- Test: studiob-api route tests in the same repo

**Step 1: Verify studiob-api repo location + GI helper ground truth**

Before writing any code:
```bash
ls /Users/kevin/dev/studiob-api /Users/kevin/code/studio-b/studiob-api 2>&1 | head
# Use whichever exists. Remote should be git@github.com:studio-b-ai/studiob-api.git
# Find the existing GI call pattern:
grep -rn 'def.*gi\|gi_client\|SM208030' <studiob-api-path>/src --include='*.py' | head -20
```

Do not assume `src/acumatica/gi_client.py` exists — it's an unverified reference from the original plan. Find the actual existing pattern and copy it.

**Step 2: Write failing route tests**

One test per route: `GET /drp/velocity-history`, `GET /drp/open-so-commitments`, `GET /drp/open-po-lines`, `GET /drp/inventory-by-site` (NOTE: renamed from `/drp/inventory-allocation` — the route name should match the GI name per §P0-A.4 correction). Assert 200 + JSON list + at least one expected column.

**Step 3: Implement 4 thin wrappers**

Each wrapper: pull query params, call the existing GI helper with ScreenID, return JSON. No business logic in these routes — the routes are strictly a proxy layer so heritage-wms can reach the GIs without holding Acumatica credentials.

**Step 4-6: Run tests against live sandbox, verify each route returns non-empty, commit + PR**

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

### Task P0-C.1: Database migrations for `drp_vendor_moq_*` tables ✅ **SHIPPED 2026-04-09**

**Status:** [studio-b-ai/aesthetik-platform#104](https://github.com/studio-b-ai/aesthetik-platform/pull/104) — file `src/migrations/025_drp_vendor_moq.sql`
**Design ref:** Section 4.3, Section 5.2, Section 10.2 (MOQ shaping)
**Reuses:** heritage-wms migration framework — numbered SQL files in `src/migrations/` (NOT `src/db/migrations/` — the original plan's path was wrong), `run.ts` runner with `_migrations` tracking table

**Tables created:**
- `drp_vendor_moq_profiles` — per-vendor config with `strictness` (strict/advisory/unknown), `default_unit`, `preferred_column_map` JSONB for learned parser mappings
- `drp_vendor_moq_extractions` — per-upload audit log with `source_file_hash`, `parser_version`, `column_mapping`, row counts, reviewer info, `raw_jsonb` for parser debug
- `drp_vendor_moqs` — current active MOQ facts with `CHECK(moq_qty > 0)` and partial unique index `(vendor_id, inventory_id) WHERE status='active'` so history rows coexist with exactly one current row per (vendor, item)

**Verified before merge:**
- Applied against local Postgres 16 DB with all 28 migrations in order, clean
- Idempotent re-run confirmed
- Partial unique index behavior: first active INSERT wins, superseded sibling INSERT allowed, second active INSERT for same (vendor, item) rejected
- FK `source_extraction_id` → `drp_vendor_moq_extractions.id` with `ON DELETE SET NULL` verified

**No further work on this task.** The downstream C.2/C.3/C.4 tasks consume these tables.

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

### Task P0-C.4: MOQ write-back to Acumatica `POVendorInventory.MinOrderQty`

**Design ref:** Section 4.3 (write-back bullet)
**Reuses:** studiob-api gateway client
**⚠️ CORRECTED TARGET (2026-04-09):** Original plan said `StockItem.VendorDetails.MinOrderQty`. `StockItem.VendorDetails` is a UI rendering on the Stock Item screen backed by the `POVendorInventory` DAC — the correct write target for the contract-based REST PUT is the `POVendorInventory` entity, not `StockItem`. Writing to `StockItem.VendorDetails` via contract REST drops updates silently in some Acumatica versions because the `VendorDetails` sub-entity is not always exposed as editable through the parent.

**Files:**
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/moq-intake-service.ts` (approvedHook)
- Modify: studiob-api routes — add `PUT /acumatica/po-vendor-inventory/{inventory_id}/{vendor_id}` endpoint if it doesn't exist (verify first)
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/tests/services/moq-writeback.test.ts`

**Step 1: Verify the studiob-api route ground truth**

```bash
grep -rn 'POVendorInventory\|po-vendor-inventory\|vendor_inventory' <studiob-api-path>/src --include='*.py' | head -10
```

If the route exists, use it. If not, add a thin wrapper route first — this is a separate micro-task preceding the heritage-wms write-back hook.

**Step 2: Failing test (mocks studiob-api)**

Test asserts that approving a profile issues one `PUT /acumatica/po-vendor-inventory/{inventory_id}/{vendor_id}` with `MinOrderQty` in the payload, per row on the profile.

**Step 3: Implement write-back path**

On approval: iterate MOQ rows (`status='active'` only), call studiob-api PUT for each, log results inline to `drp_vendor_moq_extractions.status='applied'` + `applied_at` timestamp (table already has these fields from 025). If studiob-api returns non-2xx, set `status='failed'` and leave `parser_notes` with the error for re-try.

**Step 4: Verify end-to-end against sandbox**

Upload a known vendor quote, approve, verify in Acumatica:
- **PO302000** (Vendors → Vendor Details tab) — the authoritative rendering of `POVendorInventory`
- Verify the MOQ (displayed as "Min. Order Qty") matches

Do NOT verify on SA202000 / Stock Items — it shows the same data but via the parent-child rendering which has the silent-drop problem.

**Step 5: Commit + PR**

---

## Stream D — Vendor Lead Time Learning (1.5 weeks)

### Task P0-D.1: `drp_lead_time_*` migrations ✅ **SHIPPED 2026-04-09**

**Status:** [studio-b-ai/aesthetik-platform#105](https://github.com/studio-b-ai/aesthetik-platform/pull/105) — file `src/migrations/026_drp_lead_time.sql`
**Design ref:** Section 4.5, Section 5.2, Section 12

**WMSTL audit result:** Before writing 026, the referenced `WMSTLVendorLeadTimes` table was audited across all 5 Studio B repos. Finding: the table exists and is joined by `GI007000 InventoryQuantityDetail` in `AesthetikContainers/project.xml`, but has ZERO code references in webhook-router, heritage-wms, acumatica-ci-cd, cs-order-entry, or studiob-api. It's a single-column schema (`LeadTimeDays` only) owned by an unknown IIG vendor customization. **Decision: build fresh `drp_vendor_lead_time_*` tables — do NOT extend WMSTL.** The 4-stage distribution schema is fundamentally richer than what WMSTL holds, and touching a zero-owner vendor table is a risk we don't need.

**Tables created (5, not 2 — scope expanded from the original plan to be cohesive):**
- `drp_lead_time_samples` — raw 4-stage observations with **STORED generated columns** for `ack_lag_days`, `production_days`, `transit_days`, `port_to_dock_days`, `total_lead_days` computed directly from the 6 source date columns. NULL-safe: partial timestamps leave stage intervals NULL but `total_lead_days` still computes. `UNIQUE(po_nbr, po_line_nbr)`.
- `drp_vendor_lead_time_stats` — per `(vendor_id, stage)` rolling distribution. **Plain table, not a materialized view** — the Shapiro-Wilk + K-S distribution fit (§12.2) is application-computed, not a SQL aggregate, so an MV can't express it. The nightly agent UPSERTs this table after refitting.
- `drp_vendor_lead_time_regimes` — CUSUM-detected regime break history per §12.4 with manual `regime_label` populated during weekly review
- `drp_vendor_calendar` — per-vendor factory closures with `impact_multiplier` for the effective-lead-time overlay (§12.5)
- `drp_country_calendar` — COO-wide closures (CNY, Eid, etc.)

**Verified before merge:**
- Generated columns compute correctly: sample `(2026-01-01, 2026-01-05, 2026-02-01, 2026-02-10, 2026-03-05, 2026-03-08)` produces `(ack_lag=4, production=27, transit=23, port_to_dock=3, total=66)` exactly
- Partial timestamps: INSERT with only `po_placed_at + received_at` → stage intervals NULL but `total_lead_days=78` computed
- `UNIQUE(po_nbr, po_line_nbr)` enforced; duplicate line insert rejected
- `CHECK(end_date >= start_date)` on both calendar tables; inverted ranges rejected
- Cleanroom re-run of all 28 migrations on empty DB, clean

**No further work on this task.** P0-D.2 (lead-time-learner.ts), D.3 (nightly mining job), D.4 (weekly write-back), D.5 (scorecard UI) all consume these tables.

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

### Task P0-E.1: `drp_abc_*` migrations + `revenue_weighted_90` seed ✅ **SHIPPED 2026-04-09**

**Status:** [studio-b-ai/aesthetik-platform#106](https://github.com/studio-b-ai/aesthetik-platform/pull/106) — file `src/migrations/027_drp_abc.sql`
**Design ref:** Section 4.6, Section 5.2, Section 9.1

**Tables created:**
- `drp_abc_schemes` — scheme definitions with `signals`/`weights`/`recency_config`/`thresholds` as JSONB, `is_active` + `is_shadow` flags, `approved_by` + `approved_at` for the promotion audit trail. Seeded with `revenue_weighted_90` as active (`{"A":0.70,"B":0.95,"C":1.00}` thresholds, `{recent_window_days:90, recent_weight:2.0}` recency).
- `drp_abc_classification_runs` — per-run metadata with nullable FK to `drp_agent_runs.id` (from migration 023; explicit merge-order note in the PR body)
- `drp_abc_classifications` — item → class assignments per run with `transition` tracking (`promoted`/`demoted`/`same`/`new`), `UNIQUE(classification_run_id, inventory_id)`
- `drp_abc_backtest_results` — per-scheme composite scoring with service level, stockouts on A, overstock on C, churn rate, override agreement rate, composite score, window dates

**Promotion authority:** Kevin-approval, per the 2026-04-09 answer to open question #4. The schema enforces this at the app layer via the `approved_by` / `approved_at` columns — shadow→active promotions must stamp a human actor. Procurement-alone promotion is NOT allowed; weekly review proposes, Kevin approves in Slack.

**Verified before merge:**
- Partial unique index `uq_drp_abc_schemes_active` enforces only-one-active (inserted a second active scheme → rejected)
- `CHECK(NOT (is_active AND is_shadow))` enforces mutual exclusion (inserted `active=true, shadow=true` → rejected)
- Seed row verified via SELECT with exact field contents
- FK cascade scheme → classification_run → classification: deleted a run, child classifications dropped
- Cleanroom re-run clean

**No further work on this task.** P0-E.2 (classifier service) and P0-E.3 (backtest harness) consume these tables.

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

### Task P0-F.1: Stockout event emit + `drp_lost_demand_events` table — SPLIT INTO 3 SUB-TASKS

**⚠️ ARCHITECTURE CORRECTION (2026-04-09):** The original plan had cs-order-entry writing `drp_lost_demand_events` directly via the heritage-wms DB pool. That's a cross-service direct-DB-write anti-pattern — cs-order-entry would need heritage-wms DB credentials, schema changes would require coordinated deploys, and the blast radius of a bad row goes across service boundaries. **Corrected architecture:** cs-order-entry emits to a heritage-wms HTTP endpoint; heritage-wms owns the table and the validation layer.

Task is now split into 3 clean sub-tasks — the first is shipped.

---

#### Task P0-F.1.a: `drp_lost_demand_events` table ✅ **SHIPPED 2026-04-09**

**Status:** [studio-b-ai/aesthetik-platform#107](https://github.com/studio-b-ai/aesthetik-platform/pull/107) — file `src/migrations/028_drp_lost_demand.sql`
**Design ref:** Section 4.7, Section 5.2, Section 12 (censored-demand forecasting)

**Table created:** `drp_lost_demand_events` with `CHECK(available_qty <= requested_qty)`, partial `UNIQUE(source_app, source_event_id) WHERE source_event_id IS NOT NULL` for emitter idempotency, `CHECK(requested_qty > 0)` and `CHECK(available_qty >= 0)`.

**Verified before merge:**
- `available > requested` impossible event rejected by CHECK
- Partial unique: second INSERT with same `source_event_id` rejected; multiple NULL keys allowed (for legacy back-fills)
- Cleanroom re-run clean

---

#### Task P0-F.1.b: heritage-wms receiver route `POST /drp/lost-demand` (NOT YET STARTED)

**Status:** PENDING — depends on PR #107 merging to Railway dev
**Reuses:** Existing heritage-wms Fastify + Postgres pool pattern

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/routes/drp-signals.ts` (or extend an existing routes file — verify)
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/lost-demand-service.ts`
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/tests/services/lost-demand-service.test.ts`

**Request shape:**
```typescript
POST /drp/lost-demand
{
  "event_at":        "2026-04-09T15:30:00Z",
  "inventory_id":    "FABRIC-001",
  "site_id":         "MAIN",
  "requested_qty":   100,
  "available_qty":   40,
  "unit":            "YDS",
  "customer_id":     "C00042",
  "customer_class":  "WHOLESALE",
  "source_event_id": "so-line-12345:2026-04-09T15:30:00Z",
  "metadata":        { "screen": "order-entry", "user_agent": "..." }
}
```

**Behavior:**
- Validate payload against a zod/ajv schema. Reject 400 on missing required fields or `available > requested`.
- Insert row. On unique-key conflict (`source_event_id` replay) return 200 with `{"status":"deduplicated"}` — treating replays as idempotent successes so the emitter never needs to retry on 409.
- No auth gate in Phase 0 — the route lives on a network that only cs-order-entry can reach. Add a shared-secret header in a later hardening pass.

**TDD steps:**
1. Failing service test: inserts one event, asserts row in DB
2. Failing service test: conflict on replay returns success without inserting twice
3. Failing service test: `available > requested` returns 400
4. Implement service
5. Failing route test: POST returns 200 with valid payload
6. Implement route
7. Commit + PR

---

#### Task P0-F.1.c: cs-order-entry emitter (~40 lines, NOT YET STARTED)

**Status:** PENDING — depends on P0-F.1.b merging (need the endpoint live before emitting)
**Reuses:** Existing cs-order-entry inventory badge logic + its existing HTTP client (whatever it already uses to reach heritage-wms for other signals)

**Files:**
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/cs-order-entry/src/api/inventory.ts` — add fire-and-forget POST at the point where the stockout badge decision is computed
- Test: `/Users/kevin/code/studio-b/heritage-fabrics/cs-order-entry/tests/api/inventory-stockout.test.ts`

**Implementation notes:**
- **Fire-and-forget.** The emit MUST NOT block the HTTP response to the CS rep. Use a queue-then-flush pattern or `.catch(logError)` on the raw promise. If heritage-wms is down, orders continue to process normally.
- **Idempotency key:** `source_event_id = "${so_line_id}:${decision_iso_timestamp}"` — reliable across replays, uniquely identifies the decision point.
- **Feature flag:** Wrap emission in `config.drpLostDemandEmitEnabled` env var so it can be disabled without a deploy if it misbehaves.
- **Config:** `HERITAGE_WMS_DRP_URL` env var points at the receiver route.

**TDD steps:**
1. Failing test: simulate request for qty 100 when 40 is available, assert emitter fires POST with the exact expected payload
2. Failing test: heritage-wms returning 500 does NOT fail the order-entry response
3. Failing test: feature flag disabled → no POST fires
4. Implement emit
5. Commit + PR

---

## Stream G — Vendor Acknowledgment Email Watcher (4 days)

### Task P0-G.1: `drp_signal_email_raw` + `drp_signal_email_parsed` tables ✅ **SHIPPED 2026-04-09**

**Status:** [studio-b-ai/webhook-router#68](https://github.com/studio-b-ai/webhook-router/pull/68) — files `src/lib/drp-email/db.ts` + `src/lib/drp-email/__tests__/db.test.ts` + `src/index.ts` (wire-up)
**Design ref:** Section 4.8, Section 5.2

**⚠️ FRAMEWORK NOTE:** webhook-router has **NO migration framework.** There is no `src/db/migrations/` directory, no knex/drizzle/prisma, no tracking table. The original plan's path was wrong. The actual pattern is inline `initXxxTable(pool)` functions in `src/lib/*/db.ts` modules, wired into `src/index.ts` startup sequence alongside `initDataSnapshotsTable` and friends. Tables use `CREATE TABLE IF NOT EXISTS` for idempotency.

**Tables created:**
- `drp_signal_email_raw` — one row per Microsoft Graph-delivered message from the procurement inbox (`imports@heritagefabrics.com`), `UNIQUE` on `message_id` to dedup Graph webhook replays at the DB level
- `drp_signal_email_parsed` — Claude-extracted PO acknowledgment fields (`po_nbr`, `ack_date`, `factory_ready_date`) with `confidence NUMERIC(4,3)` and 6-state review lifecycle (`pending`/`auto_applied`/`review`/`applied`/`rejected`/`ignored`). `ON DELETE CASCADE` from `raw_id` → `drp_signal_email_raw.id` so archival pruning cleans up children.

**Verified before merge:**
- 5/5 vitest unit tests green (table columns, confidence+review fields, indexes, idempotency, message_id uniqueness)
- `tsc --noEmit` clean on changes
- Init called in `src/index.ts` right after `initDataSnapshotsTable`

**No further work on this task.** P0-G.2 (po-email-watcher worker) and P0-G.3 (studiob-api PATCH route) consume these tables.

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

## Stream H — DataLifecycleManager Policies — **DEFERRED from Phase 0**

### Task P0-H.1: Register `drp_*` policies — **DEFERRED 2026-04-09**

**Status:** DEFERRED. Not blocking Wave 1, Wave 2, Wave 3, or Wave 4. Will be revisited when Phase 1 advisor mode resolves the cross-DB capture question.

**Why deferred:**

The DataLifecycleManager in webhook-router is a **snapshot system**, not a per-table retention manager. Reading `src/lib/data-lifecycle/db.ts` + `policies.ts` + `types.ts` + `manager.ts`:
- DLM captures data into a single `data_snapshots` table (inline JSONB for hot data, GCS `$ref` for promoted/cold data)
- `DataPolicy.snapshotFrequency` is `"cycle" | "daily" | "weekly" | "on-event"` — it describes *how often to snapshot*, not how long a table's rows live
- `hotRetentionDays` / `warmRetentionDays` govern how long the *snapshots* live in Postgres vs GCS vs pruned
- Existing policies snapshot from webhook-router's own pipeline state (audit trails, SOP versions, sync entities) where the DLM has direct access

**The architecture mismatch:**

The 5 policy keys in the original plan (`drp-recommendations`, `drp-lead-time-samples`, `drp-forecast-state`, `drp-agent-runs`, `drp-moq-extractions`) describe tables that live in the **heritage-wms Postgres database**, not webhook-router's. The current DLM has no cross-DB capture path. Adding these policies to webhook-router's `ALL_POLICIES` array would create 5 entries that the DLM manager has no way to actually populate — it would query webhook-router's `data_snapshots` table, find nothing to snapshot, and do nothing.

**Two paths forward (to be decided in Phase 1):**

1. **Local heritage-wms DLM fork** — lift the `DataLifecycleManager` + `DataPolicy` types into heritage-wms as a separate instance, pointed at heritage-wms's Postgres. Duplicates ~500 lines of logic but keeps each DB's archival self-contained.
2. **webhook-router cross-DB reader** — add an adapter in webhook-router DLM that can reach into heritage-wms Postgres via a read-only connection. Single DLM instance, one archival pipeline. Cleaner architecturally but adds a cross-service coupling that violates the rest of the Studio B boundary discipline.

Neither is a Phase 0 blocker. Phase 1 advisor mode runs fine without archival — the tables grow, we measure, we decide. The decision gets made when `drp_agent_runs` has ~90 days of rows and archival starts to matter for query performance.

**Scaffolding-only PR would be dead code.** Adding the policy entries now without the capture wiring means the DLM manager queries them on every cycle, finds no source data, logs noise, and drifts further out of sync. Cleaner to add them when the capture path exists.

**No file changes. No PR. No follow-up task in Phase 0.** The original retention schedule from Section 5.3 of the design doc remains the intended target:
- `drp-recommendations` (hot 90d, warm 365d, cold GCS)
- `drp-lead-time-samples` (hot 365d, warm 1095d, cold GCS)
- `drp-forecast-state` (hot 30d, warm 365d, weekly snapshots)
- `drp-agent-runs` (hot 90d, warm 365d)
- `drp-moq-extractions` (hot 180d, warm 730d, never prune)

Tracked in the Wasala/project memory as a Phase 1 diligence item.

---

## Stream I — Agent run skeleton + Phase config (PROMOTED to Wave-1 required)

**⚠️ STATUS CHANGE (2026-04-09):** Originally framed as "optional in Phase 0." Promoted to **Wave-1 required** because Phase 1 advisor mode cannot start without either table — no place to persist run metadata, no place to read kill-switches. Both are small migrations and their absence would block the whole Phase 1 launch. Shipped 2026-04-09.

### Task P0-I.1: `drp_agent_runs` + `drp_agent_run_events` tables ✅ **SHIPPED 2026-04-09**

**Status:** [studio-b-ai/aesthetik-platform#102](https://github.com/studio-b-ai/aesthetik-platform/pull/102) — file `src/migrations/023_drp_agent_runs.sql`
**Design ref:** Section 14.1, Section 14.7

**Tables created:**
- `drp_agent_runs` — one row per nightly invocation. `CHECK(phase IN ('advisor','draft_po','autopilot'))`, `CHECK(status IN ('starting','running','complete','blocked','partial_write_failure','partial','failed','replayed'))`, default `status='starting'`, `run_state` enum (`healthy`/`degraded`/`blocked`), `config_snapshot` JSONB, `phase_error` TEXT nullable, `summary` JSONB
- `drp_agent_run_events` — per-phase structured log (`phase_name`, `step_name`, `input_hash`, `output_hash`, `rows_read`, `rows_written`, `error_text`, `status` enum), `ON DELETE CASCADE` from parent runs

**Verified before merge:**
- All CHECK constraints enforced (bad `phase` rejected, bad `status` rejected)
- FK cascade: deleted parent run → child events dropped
- Cleanroom apply clean

**This is the FK target for `drp_abc_classification_runs.agent_run_id`** — PR #102 (I.1) must merge before PR #106 (E.1) applies to any existing DB. On cleanroom apply, alphabetical ordering handles this automatically (023 < 027).

---

### Task P0-I.2: `drp_phase_config` singleton + transitions history ✅ **SHIPPED 2026-04-09**

**Status:** [studio-b-ai/aesthetik-platform#103](https://github.com/studio-b-ai/aesthetik-platform/pull/103) — file `src/migrations/024_drp_phase_config.sql`
**Design ref:** Section 8 (phase-gated rollout), Section 14.2, Section 15 (safety rails)

**Tables created:**
- `drp_phase_config` — singleton enforced by `PRIMARY KEY id=1` + `CHECK(id=1)`. All tuning knobs the nightly DRP agent reads: `forecast_quantile_by_class` JSONB (`{"A":0.9,"B":0.75,"C":0.5}` default), `max_vendor_share_per_run` (0.25), `max_country_share_per_run` (0.50), `max_collection_overhang_x` (4.00), `daily_cost_of_capital` (0.000330 ≈ 12%/year pretax), `soft_cash_cap_usd`, `max_daily_po_value_usd` (500000.00), `rail_r3_rop_change_pct` (0.200), `significant_vendor_po_usd` (50000.00), `autopilot_abc_classes` (`{C}`), `manual_override_ttl_days` (180), `manual_override_optout_ttl_days` (365), `exception_routes` JSONB, `commitment_horizon_days` (45).
- `drp_phase_config_transitions` — audit log for every promote/revert with `CHECK(from_phase <> to_phase)` blocking self-loops

**Seed row:** `phase='advisor', write_enabled=FALSE` — the Phase 0 safety invariant. Nothing writes to Acumatica until a human promotes to `draft_po`.

**Verified before merge:**
- Singleton enforcement: INSERT with `id=2` rejected by CHECK
- Idempotent seed: second apply returns `INSERT 0 0` via `ON CONFLICT(id) DO NOTHING`
- Self-loop transition rejected
- Cleanroom apply clean

---

## Post-Phase-0 Verification

Once all Phase 0 tasks land, run the end-to-end verification checklist:

1. All 4 DRP GIs (`DRP_VelocityHistory` SB401080, `DRP_OpenSOCommitments` SB401090, `DRP_OpenPOLines` SB401100, `DRP_InventoryBySite` SB401110) return rows via studiob-api without auth errors — verified via Playwright SM208000 search + REST probe
2. `POOrder.UsrAcknowledgedDate` + `POOrder.UsrFactoryReadyDate` editable in PO301000 UI (Playwright click-save-reload cycle, not just REST PUT — per KB entry on REST PUT vs UI Save for UOM validators)
3. MOQ intake: upload a sample vendor quote, approve, confirm `MinOrderQty` appears in Acumatica PO302000 (Vendors → Vendor Details) — **NOT SA202000 per the P0-C.4 correction**
4. Lead-time mining job produces non-empty `drp_vendor_lead_time_stats` rows with non-null `distribution_kind` for at least 5 vendors
5. ABC classifier writes A/B/C codes to Acumatica `StockItem.ABCCode` for top 500 items (via `StockItem` PUT, not `drp_abc_classifications` alone — the write-back to Acumatica is the verification)
6. cs-order-entry stockout emitter + heritage-wms receiver: simulate an intentional stockout (`requested=100, available=40`), assert one `drp_lost_demand_events` row lands with the correct `source_event_id`, no duplicates on replay (F.1.b idempotency)
7. Email watcher parses a real captured vendor ack email (one of the 3-5 few-shot examples), writes `UsrFactoryReadyDate` via studiob-api PATCH, verified via Playwright PO301000 reload
8. ~~DLM policies list shows the 5 new `drp-*` entries~~ — **DEFERRED, see P0-H.1 note above**
9. `drp_phase_config` exists with `phase='advisor', write_enabled=FALSE` singleton — seeded at migration time, verified by direct SQL query
10. `drp_agent_runs` accepts a test row with all CHECK constraints satisfied

When 1-7 + 9 + 10 pass (item 8 deferred), Phase 0 is DONE. Phase 1 advisor mode can be scheduled.

---

## Commit + PR hygiene

- Each task's commit message starts with `feat(drp):` or `chore(drp):` or `test(drp):`
- Reference the task ID in the PR title: `feat(drp): P0-A.1 DRP_VelocityHistory GI`
- PR body references the design doc section
- All PRs target `main` of their respective repo
- Cross-repo dependencies (P0-G.3 depends on P0-B.1) are called out in the PR body

---

## Unblockers / open questions — status as of 2026-04-09

| # | Question | Resolution | Affects |
|---|---|---|---|
| 1 | Procurement shared inbox identity | **`imports@heritagefabrics.com`** (single address, confirmed 2026-04-09 session) | P0-G.2 |
| 2 | SO types to include in cross-dock matching | **`('CO','SO','PC')`** — PC is included. Sandbox verification of the PC order type code deferred to P0-A.2 deploy prep (SO201000 visual check or ad-hoc schema query; default REST endpoint doesn't expose `SalesOrderType`) | P0-A.2 |
| 3 | `StockItem.UsrCbmPerUnit` coverage audit | **DEFERRED** to Phase 1 — doesn't block Phase 0. Freight-consolidation NPV math is Phase 2+ | P2+ |
| 4 | Shadow-scheme promotion authority | **Kevin approval** (via Slack, stamps `drp_abc_schemes.approved_by` + `approved_at`) | P0-E.1 (seeded), weekly review format |

All four questions resolved. **Stream A is unblocked and can start the next off-hours window.**

### New open questions surfaced during Wave 1 execution

| # | Question | Resolution needed by |
|---|---|---|
| 5 | **studiob-api repo location + GI client pattern** — exact path and existing helper code are unverified. The plan's original path reference (`src/acumatica/gi_client.py`) was never checked against disk. | Start of P0-A.5 |
| 6 | **DLM cross-DB capture architecture** — local fork in heritage-wms OR cross-DB reader in webhook-router? | Phase 1, not Phase 0 |
| 7 | **cs-order-entry HTTP client + config pattern** — does the app already have an HTTP client module with retry + logging, or does P0-F.1.c need to add one? | Start of P0-F.1.c |
| 8 | **Microsoft Graph subscription coverage for `imports@heritagefabrics.com`** — the existing webhook-router Graph subscription may already cover this address or may need extension via a subscription update | Start of P0-G.2 |
| 9 | **Advisor loop scaffold (P0-I.3?)** — not explicitly in the original plan. Where does the nightly agent live? Railway service `drp-agent` in studiob-platform per §14.1, but the scaffold code + Railway provisioning is an unnumbered task. | Start of Phase 1 advisor mode |
