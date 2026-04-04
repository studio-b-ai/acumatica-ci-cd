# Container Tracking — Phase 1 Cleanup + Phase 2 & 3 Implementation

## Context

On 2026-04-04, we built 5 new screens to replace the IIG Container Management ISV (PR #162, merged). The customization published successfully but two issues remain:

1. **Old IIG SiteMap entries still visible** in the Container Tracking workspace — clicking them loads forever (underlying ASPX/GI sources deleted when IIG was unpublished)
2. **GI definitions may not have been created** — the `EnsureContainerTrackingGIs()` method in the CustomizationPlugin may not have executed if the publish timed out before `UpdateDatabase()` ran

Phase 2 (push-based container events) and Phase 3 (master data screens) code is ready on branches but not merged.

## Verified State (end of 2026-04-04 session)

| Check | Result |
|-------|--------|
| `GET /entity/ContainerTracking/24.200.001/Container?$top=1` | 200 OK — entity exists |
| `GET /entity/default/24.200.001/SalesOrder?$top=1` | 200 OK — API healthy |
| `GET /entity/default/24.200.001/UsrFreightForwarder?$top=1` | 404 — not on default endpoint |
| Playwright tests (34 total) | 34 pass, 0 fail |
| Browser: Container Tracking workspace | Shows OLD IIG entries (broken) mixed with new |
| Browser: Freight Forwarders click | Infinite spinner (likely old IGCM3091 SiteMap entry) |

## Key Files

| File | Path | Purpose |
|------|------|---------|
| AesthetikContainers project.xml | `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml` | All DACs, graphs, ASPX, CustomizationPlugin |
| GI builder script | `/Users/kevin/dev/acumatica-ci-cd/scripts/heritage/gi_container_tracking.py` | Generates SQL for 5 GIs |
| Generated GI SQL | `/Users/kevin/dev/acumatica-ci-cd/data/container-tracking/*.sql` | 5 SQL files (POContainers, SOContainers, ContainerEvents, CustomClassification, POContainerLines) |
| Playwright tests | `/Users/kevin/dev/acumatica-ci-cd/tests/ui/test_container_tracking.py` | 34 tests (IIG removal + new screens) |
| Test helpers | `/Users/kevin/dev/acumatica-ci-cd/tests/ui/helpers.py` | `navigate_to_screen_safe()`, `find_custom_fields()` |
| Test conftest | `/Users/kevin/dev/acumatica-ci-cd/tests/ui/conftest.py` | `acumatica_page` fixture (session login) |
| Migration guide | `/Users/kevin/dev/acumatica-ci-cd/docs/guides/container-tracking-migration-guide.md` | End-user IIG→AesthetikContainers guide |
| Phase 2-3 design | `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-04-container-tracking-phase2-3-design.md` | Approved design |
| Phase 2-3 impl plan | `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-04-container-tracking-phase2-3-impl.md` | 12-task implementation plan |
| Push webhook route | `/Users/kevin/dev/webhook-router/src/routes/container-update.ts` | Phase 2 push endpoint (PR #58, open) |
| Emergency deploy script | `/Users/kevin/dev/acuops-pipeline/scripts/emergency-deploy.py` | Fixed publishEnd JSON parsing (PR #4, merged) |
| Deploy workflow | `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml` | CI/CD pipeline |
| Lessons learned | Memory file at `memory/context/lessons-learned.md` | 7 new lessons from this session |
| Container tracking memory | Memory file at `memory/project_container-tracking.md` | Full project state |

## Branches & PRs

### acumatica-ci-cd

| Branch | Status | Contents |
|--------|--------|----------|
| `main` | Up to date | PRs #158-167 merged (Phase 1 + fixes) |
| `feat/container-tracking-phase2-3` | Open, 4 commits ahead | Phase 2-3 design docs + PO Container Lines GI + Container Types/Ports/Preferences DACs + ASPX + DDL + seed data |

### webhook-router

| PR | Status | Contents |
|----|--------|----------|
| #58 | Open | `POST /webhook/acumatica/container-update` push endpoint |

### acuops-pipeline

| PR | Status | Contents |
|----|--------|----------|
| #4 | Merged | publishEnd JSON response fix for emergency-deploy.py |

## Credentials

- Acumatica api-bot: `op://Studio B Infrastructure/acumatica-api-bot` (username: `api-bot`)
- api-bot has API access but NO browser SiteMap access — use Kevin's credentials for browser verification

## Step 1: Fix SiteMap Cleanup (CRITICAL — do first)

The `CleanupIGCMArtifacts()` method in project.xml deletes GI definitions but NOT SiteMap entries. Add SiteMap deletion.

**File:** `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml`

Find the `CleanupIGCMArtifacts(SqlConnection conn)` method. After the existing GI cleanup SQL, add:

```csharp
// ── Delete orphaned IGCM SiteMap entries ──────────────────────
string siteMapSql = @"
    DELETE FROM SiteMap
    WHERE CompanyID = 2
    AND (ScreenID LIKE 'IGCM%' OR ScreenID LIKE 'IG%')
    AND ScreenID NOT IN ('SB501000','SB401000','SB401010','SB401020','SB302000','SB401030');
";
using (var cmd = new SqlCommand(siteMapSql, conn))
{
    int rows = cmd.ExecuteNonQuery();
    WriteLog(string.Format("[AesthetikContainers] Deleted {0} orphaned IGCM SiteMap entries", rows));
}
```

**Commit, PR, merge.** This triggers a CI deploy which will run the updated CustomizationPlugin.

## Step 2: Verify GI Definitions Exist

After Step 1 deploys, check if the 4 Phase 1 GIs were created:

```python
# Via Acumatica API or direct SQL
import requests
s = requests.Session()
s.post('https://heritagefabrics.acumatica.com/entity/auth/login', json={
    'name': 'api-bot', 'password': '<from 1password>', 'tenant': 'Heritage Fabrics'
})
# Try accessing each GI screen
for sid in ['SB401000', 'SB401010', 'SB401020', 'SB401030']:
    r = s.get(f'https://heritagefabrics.acumatica.com/entity/default/24.200.001/GenericInquiryDesign?$filter=ScreenID eq \'{sid}\'&$select=DesignID,Name,ScreenID')
    print(f'{sid}: {r.status_code} {r.text[:200]}')
s.post('https://heritagefabrics.acumatica.com/entity/auth/logout')
```

If GIs don't exist, the `EnsureContainerTrackingGIs()` SQL didn't run. Check the publish log for errors. May need to run the SQL manually via SM302050 (Direct SQL) or republish.

## Step 3: Take Browser Screenshots

After SiteMap cleanup + GI verification, log into Acumatica as Kevin and screenshot:

1. Container Tracking workspace (should show only our screens, no IGCM entries)
2. SB501000 — Container Maintenance
3. SB401000 — PO Containers GI
4. SB401010 — SO Containers GI
5. SB401020 — Container Events GI
6. SB302000 — Freight Forwarders
7. SB401030 — Custom Classification GI

Use Playwright with Kevin's credentials (not api-bot — no SiteMap access):
```bash
cd /Users/kevin/dev/acumatica-ci-cd
# Kevin logs in via browser, then navigate to each screen
```

## Step 4: Merge Phase 2-3 Branch

After Phase 1 is verified clean:

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git checkout feat/container-tracking-phase2-3
git rebase main
git push
gh pr create --title "feat: container tracking Phase 2-3 — push events + master data"
```

This adds:
- PO Container Lines GI (SB401040)
- Container Types DAC + form (SB302010) + seed data (6 types)
- Destinations/Ports DAC + form (SB302020) + seed data (20 ports)
- Container Preferences DAC + form (SB302030) + default record

## Step 5: Merge Webhook-Router PR #58

```bash
cd /Users/kevin/dev/webhook-router
gh pr merge 58 --squash
```

Then set Railway env var: `CONTAINER_TABLE_TRACKING_ENABLED=true`

## Step 6: Wire ContainerMaint.Persist() Push

Phase 2 Task 4 from the implementation plan — add HTTP POST to webhook-router in `ContainerMaint.Persist()` override. See `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-04-container-tracking-phase2-3-impl.md` Task 4 for the exact C# code.

## Step 7: Link UsrContainer to Master Tables

Phase 3 Task 10 — change `UsrContainer.ContainerType` from `PXStringList` to `PXSelector` referencing `UsrContainerType.typeCD`. Same for `PortOfLoading`/`PortOfDischarge` → `UsrPort.portCode`.

## Step 8: Add Phase 3 Playwright Tests

Add tests for SB401040, SB302010, SB302020, SB302030. Same pattern as existing tests — load + verify no ERROR redirect.

## Step 9: Update Migration Guide

Add Phase 3 screens to `/Users/kevin/dev/acumatica-ci-cd/docs/guides/container-tracking-migration-guide.md`.

## Constraints

- **After-hours deploys only** — publishes restart Acumatica app pool
- **Never commit to main** — always branch + PR
- **Physical ASPX files required** — CDATA in project.xml is NOT enough; create matching files at `Customization/AesthetikContainers/Pages/SB/`
- **`navigate_to_screen_safe()` + `wait_for_screen()`** for Playwright — never `networkidle`
- **GI SQL must include `-- REVIEWED: gi-sql-safe`** marker
- **All DDL via `EnsureTable()` / `EnsureColumn()` / `EnsureIndex()`** — idempotent
- **Container Tracking workspace ParentID:** `9c89e3db-7c47-43c0-8554-5d2c9f2c0e87`
- **Acumatica frameset URL always shows ScreenId=00000000** — this is normal, not a failure signal

## Lessons from This Session (read `memory/context/lessons-learned.md`)

1. Physical ASPX files REQUIRED alongside CDATA — zip import NullRef without them
2. Acumatica frameset URL always shows ScreenId=00000000 — screens load in main iframe
3. publishEnd returns JSON on HTTP 200 in Acumatica 24.2+ — not plain "true"/"false"
4. CleanupIGCMArtifacts must also clean SiteMap — deleting GI data leaves broken links
5. force_qualify=true triggers emergency-deploy.py, not deploy.py — different parsing logic
6. api-bot has API access but no SiteMap/screen browser access
7. GI SQL created via CustomizationPlugin needs post-publish verification
