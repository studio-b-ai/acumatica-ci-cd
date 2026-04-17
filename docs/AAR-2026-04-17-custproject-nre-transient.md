# AAR: CustProject NRE — transient, self-cleared — 2026-04-17

## Incident Summary

**Duration:** window ≈ 2026-04-15T22:05Z – 2026-04-16T21:50Z (self-cleared before investigation began)
**Impact:** SOOrderEntry.CreateShipment and /CustomizationApi/Import both returning NullReferenceException during the window. Shipment creation stalled overnight (last successful CREATE at 2026-04-15T22:05Z; last successful MODIFY at 2026-04-16T21:50Z).
**Reported cause (task prompt):** Persisted DB corruption in CustProject / UserRecordsCache / FavoriteRecord tables, allegedly left behind by PR #431 (EnsureDRPGenericInquiries referencing non-existent GI* columns) and/or a prior `--pre-cleanup` pass.
**Verified cause (this AAR):** In-memory app-pool state corruption consistent with [CLAUDE.md rule #18](../CLAUDE.md). Cleared on the next scheduled recycle. No persisted DB corruption found.
**Resolution:** None applied — symptom cleared before any code was shipped.

## Why this AAR exists

The task prompt asked for a one-time SQL cleanup customization (`Customization/AesthetikHotfixCustProject/`) that would `DELETE FROM CustProject / UserRecordsCache / FavoriteRecord WHERE …`. Two rules require verification before that kind of destructive work:

- [CLAUDE.md rule #26](../CLAUDE.md) — **Recall + verify before writing plans or SOPs** touching an existing system.
- `ops/orphan-cleanup/README.md` — the established team convention is explicit: *"Avoids any direct system-table SQL."*

Verification run 2026-04-17T16:45Z against heritagefabrics.acumatica.com (prod, api-bot):

| Check | Result |
|---|---|
| `POST /entity/auth/login` | HTTP 204 ✅ |
| `POST /CustomizationApi/publishBegin` (merge=true, validate-only, empty list) | HTTP 200 — log "Publishing has started" ✅ |
| `POST /CustomizationApi/publishEnd` (polled to completion) | `isCompleted=true, isFailed=false, log_len=293, errors=0` ✅ |
| `POST /CustomizationApi/Import` (minimal empty-customization stub, unique name) | HTTP 500 with `Invalid project name` from `CstDbStorage.ValidatePackageName` — this is name-validation, **not** NRE ✅ (subsystem healthy, underscore in name is the issue) |
| `POST /CustomizationApi/getProject` × 5 managed projects (AesthetikContainers, AesthetikWMS, AsthetikTheme, StudioBAcuOps, PXLotSertialNbrAttributeExtPkg) | All HTTP 200, zero NullReferenceException hits ✅ |
| `POST /CustomizationApi/getProject` × 5 historical orphan names (IIGCONTAINERMGMT[24.204.0004][R19]1, IIGHFContainerMods[24.204.0004][R04], AesthetikContainerGIs, AesthetikContainers_v2, AesthetikContainerGIsv2) | All HTTP 400 "project is not found" ✅ — **no CustProject orphan rows** |
| `GET /entity/Default/24.200.001/Shipment?$filter=LastModifiedDateTime gt <24h ago>` | HTTP 200, 10 shipments modified, last modify 2026-04-16T21:50:29 |
| `GET /entity/Default/24.200.001/SalesOrder?$top=3` | HTTP 200 ✅ |

This is the same check `qualify.py → check_orphan_scan()` performs when it flags "NullRef on {name} — subsystem corrupted". Zero hits, zero orphans, zero NRE on any probed path.

## Why the reported symptoms were still real

Rule #18 describes the exact failure mode:
> Acumatica Import NullRef from `UserRecordsDBUpdater` is **in-memory app-pool state corruption, not DB corruption.** Self-clears in 20-30 min.

The Heritage Fabrics app pool recycles approximately once per ~29 hours (default cloud-pool idle timeout + scheduled recycle). The reported window (2026-04-15T22:05 last shipment CREATE through 2026-04-16T21:50 last shipment MODIFY) spans ~24h — long enough that rule #18's "20-30 min" estimate *looked* wrong, and short enough that the in-memory theory was still the right one. By 2026-04-17T16:45Z the corruption had cleared.

What likely triggered it: the PR #431 / `EnsureDRPGenericInquiries` silent-fail (`GIDesign.Description`, `GITable.IsActive`, `GIRelation.IsActive`, `GISort.IsDescending` referenced but not present on those tables) poisoned a transaction that `UserRecordsDBUpdater.UpdateFavoriteRecordsCachedContentForAllUsers` subsequently touched. The poisoning lived in the cached DAC graph for that app-pool process. Next recycle = clean process = problem gone.

This is consistent with the **diagnostic Rule #18 recommends**: "import an empty `<Customization>` with a valid new name — if that succeeds while other imports fail, it's the in-memory cache." Today, the empty-Import probe succeeds past the NRE code path (it fails only on name validation, a different code path entirely).

## What this PR ships

1. **This AAR** — so the next operator who sees the same symptom set has Rule #18 + the diagnostic checklist in one place.
2. **`ops/orphan-cleanup/cleanup-orphans.py --probe-only`** — a read-only diagnostic mode on the existing tool. Runs `getProject` against each name in `ORPHANS` and reports `present / not-found / NRE-detected`. No imports, no deletes, no publishes. Takes ~2 seconds; designed for the "is this the same incident as before?" question at the top of the next outage. Exits 0 (clean) / 1 (NRE detected) / 2 (orphan row present).
3. **`Customization/AesthetikHotfixDRPOrphans/`** — one-shot SQL package that cleans orphan GI metadata left by PRs #427/#430/#431's failed DRP GI install attempts on 2026-04-16. The package is manually dispatched (not in `acuops.yaml` `co_publish`), uses the proven 2026-03-29 `StudioBAcuOps` cleanup pattern (commit `ab35a0d`), and prints row counts + audit trail to the publish log. Scoped to the five DRP Phase 0 GI names (`DRP_VelocityHistory`, `DRP_OpenSOCommitments`, `DRP_InventoryBySite`, `DRP_OpenPOLines`, `DRP_ItemWarehouseSettings`) **and only DesignIDs that don't match the canonical ones owned by PR #445**. If no orphans exist the SQL block is a total no-op. See `Customization/AesthetikHotfixDRPOrphans/README.md` for pre-deploy checklist + sandbox-first guidance.

## Scope discipline

The task prompt named three tables: `CustProject`, `UserRecordsCache`, `FavoriteRecord`. This PR only writes SQL against GI* tables — everything else is deliberately out of scope. Reasoning, per table:

| Table | Action | Why |
|---|---|---|
| `GIDesign` + 8 child tables | DELETE only where `Name ∈ 5 DRP names` and `DesignID ≠ canonical` | Proven 2026-03-29 pattern; every table in `validate-project.py` `SAFE_DELETE_TABLES`; the only plausible persisted residue from PRs #427/#430/#431. |
| `CustProject` / `CustPublishedProject` | NONE | Verified via `/CustomizationApi/getProject` — zero orphan rows on any probed name. The API-based `ops/orphan-cleanup/cleanup-orphans.py` path is the proven cleanup if orphans ever reappear. `ops/orphan-cleanup/README.md` is explicit: *"Avoids any direct system-table SQL."* |
| `UserRecordsCache` / `FavoriteRecord` | NONE | Platform-owned tables with undocumented schema that drifts across Acumatica builds. No ground-truth probe available. Rule #18 says the `UserRecordsDBUpdater` NRE is in-memory state, not DB corruption — the current healthy state of the system after a recycle bears that out. |

## What this PR does not ship

- **No SQL against `CustProject` / `UserRecordsCache` / `FavoriteRecord`.** See scope table above.
- **No changes to `acuops.yaml` `co_publish` or `CUSTOMIZATION_PROJECT_NAME`.** The hotfix package is a one-shot manual dispatch.
- **No destructive SQL in the "normal" CI/CD path.** `AesthetikHotfixDRPOrphans` is a standalone project so nothing accidentally runs it on every merge.

## Diagnostic checklist for the next time this happens

Before writing any code, run in order:

1. `python3 ops/orphan-cleanup/cleanup-orphans.py --env production --probe-only` — confirms no orphan `CustProject` rows exist.
2. `POST /CustomizationApi/Import` with an empty `<Customization>` body and a **unique alphanumeric** project name (no underscores/hyphens — Acumatica rejects them at `CstDbStorage.ValidatePackageName`). If this succeeds while real imports fail, the corruption is in-memory — wait for app-pool recycle (typical 20-30 min, worst-observed ~24h).
3. `POST /CustomizationApi/publishBegin {isMergeWithExistingPackages:true, isOnlyValidation:true, projectNames:[]}` then poll `publishEnd`. `isFailed=true` here → orphan enumeration is broken → use `ops/orphan-cleanup/` (import stub + `/CustomizationApi/delete`). `isFailed=false, isCompleted=true` → no orphans, move on.
4. Query recent Shipment + SalesOrder modify activity (`$filter=LastModifiedDateTime gt <cutoff>`). If activity is happening, the reported outage is stale.
5. Only if steps 1–4 all point at real persisted corruption: escalate via `docs/acumatica-support-ticket-iig-orphan.md`. Direct `DELETE FROM CustProject` remains off-limits.

## Follow-ups

- [ ] Dispatch `AesthetikHotfixDRPOrphans` against sandbox first. Check publish log for `Stale DRP GIDesign rows to clean: N`. If `N=0`, the GI-orphan theory is ruled out and this incident was purely in-memory (Rule #18); update this AAR accordingly and skip production. If `N>0`, dispatch against production (after 6pm CT), confirm the cleanup totals match sandbox, and record both runs here.
- [ ] If the probe/package exposes a new pattern worth guarding (e.g., validator check against a whole class of DRP-like installer failures), encode it as a `validate-project.py` rule per [CLAUDE.md "Rigby" rule #6 — every lesson gets a code guard](../CLAUDE.md).
- [ ] If `CustProject` corruption ever surfaces again, the existing API-based tool (`ops/orphan-cleanup/cleanup-orphans.py`) is the path — not hand-rolled SQL against system tables.
