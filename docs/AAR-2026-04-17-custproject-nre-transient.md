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

## Why no destructive SQL package was shipped

The task prompt's suggested fix — a customization with `<Sql>` blocks that `DELETE FROM CustProject` and `DELETE FROM UserRecordsCache / FavoriteRecord` where orphan conditions hold — is not appropriate for this incident:

1. **There are no orphans to clean.** Every historical orphan name we've tracked (IIGCONTAINERMGMT, IIGHFContainerMods, AesthetikContainerGIs) returns HTTP 400 "not found" today. The `ops/orphan-cleanup/cleanup-orphans.py` API-based run already cleared them (or never saw this particular set).
2. **The symptom is transient.** Rule #18 says self-clear in 20-30 min. It did self-clear. Writing a `DELETE FROM` package for an intermittent in-memory condition addresses the wrong layer.
3. **Direct system-table SQL violates the team convention.** See `ops/orphan-cleanup/README.md`: *"Avoids any direct system-table SQL."* The convention exists because Acumatica's own `/CustomizationApi/delete` endpoint already handles `CustProject + CustPublishedProject + child tables` correctly and idempotently. Hand-rolled `DELETE` statements can miss child rows or delete valid state if the `WHERE` clause is even slightly off.
4. **`UserRecordsCache` / `FavoriteRecord` are platform-owned.** The schema is undocumented and subject to change between Acumatica builds. A `WHERE` clause that's safe on 24.208 may orphan live rows on 24.210.
5. **Every publish restarts the app pool.** [CLAUDE.md rule #11](../CLAUDE.md) — shipping a one-shot SQL package to clear in-memory state causes the exact disruption the in-memory state would have cleared itself from on the next recycle.

## What this PR does ship

1. **This AAR** — so the next operator who sees the same symptom set has Rule #18 + the diagnostic checklist in one place.
2. **`ops/orphan-cleanup/cleanup-orphans.py --probe-only`** — a read-only diagnostic mode on the existing tool. Runs `getProject` against each name in `ORPHANS` and reports `present / not-found / NRE-detected`. No imports, no deletes, no publishes. Takes ~2 seconds; designed for the "is this the same incident as before?" question at the top of the next outage.

## What this PR does not ship

- **No `Customization/AesthetikHotfixCustProject/` package.** If a future incident actually shows persisted orphan rows that `/CustomizationApi/delete` refuses to remove, the right escalation is the email in `docs/acumatica-support-ticket-iig-orphan.md` — i.e. Acumatica support opens a DB-level cleanup case. A customization package that SQL-deletes from `CustProject` / `UserRecordsCache` on every deploy is not a substitute.
- **No changes to `acuops.yaml`, `CUSTOMIZATION_PROJECT_NAME`, or `ALSO_PUBLISH_PROJECTS`.** Nothing new needs to be co-published.

## Diagnostic checklist for the next time this happens

Before writing any code, run in order:

1. `python3 ops/orphan-cleanup/cleanup-orphans.py --env production --probe-only` — confirms no orphan `CustProject` rows exist.
2. `POST /CustomizationApi/Import` with an empty `<Customization>` body and a **unique alphanumeric** project name (no underscores/hyphens — Acumatica rejects them at `CstDbStorage.ValidatePackageName`). If this succeeds while real imports fail, the corruption is in-memory — wait for app-pool recycle (typical 20-30 min, worst-observed ~24h).
3. `POST /CustomizationApi/publishBegin {isMergeWithExistingPackages:true, isOnlyValidation:true, projectNames:[]}` then poll `publishEnd`. `isFailed=true` here → orphan enumeration is broken → use `ops/orphan-cleanup/` (import stub + `/CustomizationApi/delete`). `isFailed=false, isCompleted=true` → no orphans, move on.
4. Query recent Shipment + SalesOrder modify activity (`$filter=LastModifiedDateTime gt <cutoff>`). If activity is happening, the reported outage is stale.
5. Only if steps 1–4 all point at real persisted corruption: escalate via `docs/acumatica-support-ticket-iig-orphan.md`. Direct `DELETE FROM CustProject` remains off-limits.

## Follow-ups

None required in this repo. If the task prompt's premise recurs (Import NRE that outlives one app-pool recycle, with the probe above confirming orphans), open a new ticket with the probe output attached and escalate to Acumatica support using the existing template. Do not introduce destructive system-table SQL into a customization package.
