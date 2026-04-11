# PCC Data Seeding + Design Finalization

**Prior session:** 2026-04-11 Session 7 (DRP debugging + PCC brainstorming)
**Session 7 outcome:** DRP pipeline runs end-to-end. 6 PRs merged (aesthetik-platform #120-#125). PR #353 merged (acumatica-ci-cd). PCC design 80% locked.

## Read in order before doing anything

1. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_pcc_redesign.md`
2. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_drp_implementation.md`
3. `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-09-drp-implementation-design.md` §7.1-7.3

## PCC Design Decisions (LOCKED — do not re-litigate)

| # | Decision | Choice |
|---|----------|--------|
| 1 | DRP cross-reference | **D — defer to follow-up.** Ship structural changes only. |
| 2 | Delivery | **A — single PR** for SB501000 + SB501200. One app pool restart. |
| 3 | KPI layout | **B — two rows.** Keep existing filter tiles + add new metrics row below. |
| 4 | Timeline stages | **B — hybrid.** First 3 from PO dates, last 4 from container status. |
| 5 | SB501100 | **B — defer** until DRP recommendations flow. PLAN NEXT ORDER deep-links to heritage-wms. |

## Step 1: Seed DRP Signal Caches (BLOCKING — do this first)

The DRP pipeline ran successfully at 14:16 UTC on 2026-04-11. Velocity cache has 77,238 rows. But 4 of 5 signals returned 0 rows:

| Signal | GI Name | Rows | Issue |
|--------|---------|------|-------|
| velocity | DRP_VelocityHistory | 77,238 | ✅ Working |
| inventory | DRP_InventoryBySite | 0 | GI returns 200 but 0 rows — check GI filter conditions |
| open_so | DRP_OpenSOCommitments | 0 | GI returns 200 but 0 rows — check GI filter conditions |
| open_po | DRP_OpenPOLines | 0 | GI returns 200 but 0 rows — check GI filter conditions |
| item_warehouse | DRP_ItemWarehouseSnapshot | 0 | GI doesn't exist (404). Uses StockItem REST entity which 500s on session login (KeyNotFoundException). |

### Debugging steps

1. **Test each GI directly via OData** from the shell — same pattern used in this session:
   ```bash
   # Credentials from Railway:
   cd ~/dev/aesthetik-platform
   railway variables --service heritage-wms --json
   # Then:
   curl "https://heritagefabrics.acumatica.com/t/Heritage%20Fabrics/api/odata/gi/{GI_NAME}?\$top=5" \
     -H "Authorization: Basic $(echo -n 'api-bot:{PASSWORD}' | base64)"
   ```

2. **For GIs returning 0 rows**: Open SM208000 (Generic Inquiries) in Acumatica via Playwright. Check the WHERE conditions on each GI. The GI definitions are in `acumatica-ci-cd/Customization/AesthetikContainers/project.xml` — search for `<GenericInquiryScreen>` blocks with DRP_ names.

3. **For DRP_ItemWarehouseSnapshot (404)**: This GI was never created. Need to:
   - Create the GI in AesthetikContainers/project.xml
   - Expose via OData (checkbox in SM208000)
   - Deploy to production (after-hours, bundles with PCC deploy)
   - Update `syncItemWarehouseCache` in aesthetik-platform to use `queryGI` instead of `getAll('StockItem', ...)`

4. **After fixing GI issues, trigger pipeline manually**:
   ```
   curl -X POST https://wms.asthetik.com/api/drp/config/run-now
   ```
   Then verify:
   ```sql
   SELECT 'velocity' as signal, count(*) FROM drp_signal_velocity_cache
   UNION ALL SELECT 'inventory', count(*) FROM drp_signal_inventory_snapshot
   UNION ALL SELECT 'open_so', count(*) FROM drp_signal_open_so_cache
   UNION ALL SELECT 'open_po', count(*) FROM drp_signal_open_po_cache
   UNION ALL SELECT 'item_wh', count(*) FROM drp_signal_item_warehouse_cache;
   ```

## Step 2: Write PCC Design Doc

Once signals are flowing, write the design doc:
- Path: `docs/plans/2026-04-11-pcc-redesign-design.md`
- Use the locked decisions above + §7.1-7.3 from the DRP design doc
- Invoke `writing-plans` skill to produce implementation plan

## Step 3: Implement SB501000 Refactor

Priority order within SB501000:
1. **7-stage lifecycle timeline** — extend `TimelineHtml` builder in ContainerMaint graph
2. **KPI retheme** — new metrics row (Position/Cross-Dock/Speculation) using Acumatica-native aggregates
3. **LEAD TIME tab** — 6th tab, PO-native data (order date, acknowledged, factory ready, ETA)
4. **PLAN NEXT ORDER action** — deep-link to `https://wms.asthetik.com/vendors/{vendorId}`
5. **SiteMap rename** — "Procurement Command Center"

## Step 4: Implement SB501200 (Supplier Intake)

Thin shell — external link to `https://wms.asthetik.com/moq-intake?vendor={id}` or `/moq-bulk`.
New ASPX + code-behind + SiteMap + workspace entry. Add to `--no-merge-expected` list in `acuops.yaml`.

## Repos in play

- `acumatica-ci-cd` at `/Users/kevin/dev/acumatica-ci-cd/` — Acumatica screens + GI definitions
- `aesthetik-platform` at `/Users/kevin/dev/aesthetik-platform/` — heritage-wms + DRP pipeline

## Database connection

```
DATABASE_URL="postgresql://wms:41PNF7MJujb7I0yfikMUYdpV@nozomi.proxy.rlwy.net:38241/heritage_wms"
```
Use `/opt/homebrew/Cellar/postgresql@16/16.13/bin/psql` (not in PATH).

## Deploy constraints

- Acumatica screens require after-hours deploy (app pool restart). Heritage Fabrics timezone: America/New_York.
- heritage-wms (Railway) can deploy anytime.
- SB501200 ASPX needs adding to `--no-merge-expected` list in `acuops.yaml`.

## Session 7 PRs for context

| PR | Repo | Fix |
|---|---|---|
| #353 | acumatica-ci-cd | Sandbox reliability (PO3010PL, --no-merge, entity sync) |
| #120 | aesthetik-platform | Orchestrator column names + sync-run spam + LotSerialStatus 404 + supervisor 401 |
| #121 | aesthetik-platform | POST /api/drp/config/run-now manual trigger |
| #122 | aesthetik-platform | run-now public path |
| #123 | aesthetik-platform | Skip session login for GI-only pipeline |
| #124 | aesthetik-platform | ItemWarehouse sync graceful degradation |
| #125 | aesthetik-platform | error_text column name fix in drp_agent_run_events |

## Known issues (not in scope unless blocking)

- `[sync] Unknown job: sync-run` — stale BullMQ repeatable, cleanup logged but may need Redis flush
- `LotSerialStatus` 404 — needs GI, not REST entity. Tracked but not blocking PCC.
- 2 stuck `running` rows in drp_agent_runs — clean up with UPDATE SET status='failed'
- `wms_config.acumatica_tenant` was stale ("Heritage Test") — fixed to "Heritage Fabrics" in DB
