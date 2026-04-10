# DRP Phase 1 — Post-Deploy Verification (Session 2)

**Prior session ended:** 2026-04-10 ~midnight ET (Session 7 / Phase 1 Session 1)
**Session 7 outcome:** Phase 1 100% code-complete. All PRs merged. Migrations applied. Phase config seeded. heritage-wms deployed with Vendors section.

## Read in order before doing anything

1. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_drp_implementation.md` — project memory (updated by session 7)
2. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_pcc_redesign.md` — PCC Acumatica redesign scope (deferred)
3. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md` — full memory index

## What happened in Session 7

### Merged PRs
| PR | Repo | What |
|---|---|---|
| aesthetik-platform#116 | aesthetik-platform | Migrations (029-031) + signal sync service + BullMQ worker (12 tests) |
| aesthetik-platform#117 | aesthetik-platform | Forecast engine + rec engine + orchestrator + daily brief + phase config route + Vendors section UI (85 tests) |
| acumatica-ci-cd#318 | acumatica-ci-cd | UsrCbmPerUnit on StockItem (published to sandbox) |
| webhook-router#71 | webhook-router | H.1 DLM retention policies |

### Production state
- **heritage-wms**: deployed at wms.asthetik.com with Vendors section (`/vendors`, `/vendors/recommendations`, `/vendors/:vendorId`)
- **Database**: 24 DRP tables live, `drp_phase_config` seeded (phase=advisor, write_enabled=false)
- **Nightly cron**: `drp-signal-sync` scheduled at 06:00 UTC (1:00 AM ET)
- **Slack**: `#drp-advisor` channel needs to be created (couldn't do via API — manual step for Kevin)

### Known issues from Session 7
1. **Cst_POReceiptEntry prod bug** — Sarah (admin) gets "insufficient rights" on PO301000. Root cause: our `POReceiptEntry_LandedCostExt` graph extension in StudioB.Containers. Fix: SM201010 Access Rights → grant access to Cst_POReceiptEntry. Admin config fix, no deploy needed.
2. **UsrCbmPerUnit sandbox verification** — field published via CI but post-publish smoke test returned HTTP 500 (app pool restart transient). Needs UI verification on IN202500.
3. **AcuDev deploy pipeline** — smoke test failure pattern on sandbox deploys. The 500s are transient (app pool warmup) but the pipeline marks the run as failed. May need to increase retry count or add longer warmup delay.

## Session 2 priorities

### Priority 1: Verify nightly run fired correctly

The first nightly agent run should have fired at 1:00 AM ET (06:00 UTC) on 2026-04-10.

**Check steps:**
1. Check BullMQ job status — look for `drp-signal-sync` completed job in Redis
2. Query `drp_agent_runs` for today's run:
   ```sql
   SELECT id, run_date, status, run_state, started_at, finished_at, summary
   FROM drp_agent_runs WHERE run_date = '2026-04-10' ORDER BY started_at DESC LIMIT 1;
   ```
3. Check signal cache tables have data:
   ```sql
   SELECT 'velocity' AS signal, COUNT(*) FROM drp_signal_velocity_cache WHERE run_id = '<run_id>'
   UNION ALL SELECT 'inventory', COUNT(*) FROM drp_signal_inventory_snapshot WHERE run_id = '<run_id>'
   UNION ALL SELECT 'open_so', COUNT(*) FROM drp_signal_open_so_cache WHERE run_id = '<run_id>'
   UNION ALL SELECT 'open_po', COUNT(*) FROM drp_signal_open_po_cache WHERE run_id = '<run_id>'
   UNION ALL SELECT 'item_warehouse', COUNT(*) FROM drp_signal_item_warehouse_cache WHERE run_id = '<run_id>';
   ```
4. Check recommendations generated:
   ```sql
   SELECT COUNT(*), abc_class, flagged_review FROM drp_recommendations
   WHERE run_id = '<run_id>' GROUP BY abc_class, flagged_review;
   ```
5. Check if Slack brief was posted to #drp-advisor (if channel exists)

**If the run didn't fire:**
- Check heritage-wms logs: `railway logs -n 50` on heritage-wms service
- Look for `[drp-signal-sync]` log lines
- Check if Redis/BullMQ is connected (REDIS_URL env var)
- Check if the worker registered on startup: `[drp-signal-sync] Scheduled nightly cron`

**If the run failed:**
- Check `drp_agent_run_events` for error details
- Most likely cause: Acumatica gateway auth or GI query format issues
- The signal sync uses `client.query('GenericInquiry/DRP_VelocityHistory')` — verify the GI name matches what's deployed on sandbox vs production
- Note: the nightly run targets the Acumatica instance configured in heritage-wms env vars (ACUMATICA_GATEWAY_URL). Verify this points to the right instance.

### Priority 2: Verify heritage-wms Vendors section

Load https://wms.asthetik.com/vendors in a browser (or Playwright):
1. Sidebar shows consolidated Vendors section under Operations
2. `/vendors` page loads (may be empty until first agent run populates caches)
3. `/vendors/recommendations` loads with filter bar
4. `/vendors/scorecard` loads (existing VendorScorecard, relocated)
5. `/vendors/moq` loads (existing MOQ Intake, relocated)
6. Old paths redirect: `/moq/intake` → `/vendors/moq`, `/analytics/vendors` → `/vendors/scorecard`

### Priority 3: Fix Cst_POReceiptEntry for Sarah

On production Acumatica (heritagefabrics.acumatica.com):
1. Navigate to SM201010 (Access Rights)
2. Search for `Cst_POReceiptEntry` or browse the StudioB.Containers module
3. Ensure Sarah's admin role has full access
4. If the graph entity isn't visible in SM201010, check SM204505 (Customization Projects) for the published state of AesthetikContainers

### Priority 4: Write continuation prompt for Session 3

Per standing requirements — save to `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/`.

## Repos in play

- `aesthetik-platform` at `/Users/kevin/dev/aesthetik-platform/` — primary (heritage-wms)
- `acumatica-ci-cd` at `/Users/kevin/dev/acumatica-ci-cd/` — PCC redesign when ready
- `webhook-router` at `/Users/kevin/dev/webhook-router/` — DLM policies (merged)

## Database connection for verification

Public proxy (for local queries):
```
DATABASE_URL="postgresql://wms:41PNF7MJujb7I0yfikMUYdpV@nozomi.proxy.rlwy.net:38241/heritage_wms"
```

## What's NOT in scope for Session 2

- PCC Acumatica redesign (SB501000/SB501100/SB501200) — deferred, see `project_pcc_redesign.md`
- Phase 2 implementation — blocked on 60 days of Phase 1 paper trading data
- Exogenous signal integration (HubSpot, Shopify, stockout events) — Phase 1.5
- Accuracy tracking (§11.6) — needs real forecast data first
