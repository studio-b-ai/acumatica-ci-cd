# Container Tracking GI Cleanup + AcuDev KB Lessons

**Date:** 2026-04-05
**Status:** Design
**Deploy target:** Monday 2026-04-07

## Background

AesthetikContainers replaced IIG Container Management. IIG had working GIs (XML-based in the ISV package). Our replacement attempted to create GIs via SQL INSERTs in `UpdateDatabase()`. This failed across 18 deploys on 2026-04-04 because:

1. SQL INSERTs don't set `ObjectName` — the GI engine needs it to resolve DAC-to-table mapping
2. Missing NOT NULL columns discovered iteratively via failed deploys
3. Broken GI rows crashed SM208000 (GI Designer) for all users
4. Emergency cleanup deleted the rows, but `EnsureContainerTrackingGIs()` re-creates them on every publish
5. XML import (branch `claude/musing-neumann`) failed 3 times — likely blocked by SQL-era zombie rows in GIDesign

**Root cause never investigated:** Nobody queried GIDesign to see what the import engine actually did. Every deploy was hypothesis-driven.

## Phase 1: Clean Navigation for Monday

### Goal

End-user logs in Monday and sees: Container Tracking workspace with 5 working form screens. No broken GI links. No navigation changes from what they'd expect post-IIG removal.

### Changes to `project.xml`

#### Remove

1. **`EnsureContainerTrackingGIs()` method** (line ~1674–1811) — entire method. This SQL-based GI creation produces broken rows that crash SM208000 or render as empty screens.

2. **Call to `EnsureContainerTrackingGIs()`** (line 1240) — remove from the per-company loop.

3. **5 GI entries from `EnsureContainerTrackingSiteMap()`** (line ~1822–1827) — remove the SB401000–SB401040 entries. Keep the 4 form screen entries (SB302000, SB302010, SB302020, SB302030).

4. **SB401000–SB401040 from IGCM cleanup whitelist** (lines 1646–1647 and 1661–1662) — remove from the `NOT IN` list so existing broken SiteMap entries get cleaned up by `CleanupIGCMArtifacts()`.

5. **Dead code methods** — `SetSiteMapGraphType`, `GrantScreenAccess`, `DiagnoseAccessRights` (lines ~1303–1420). Marked dead since before the GI work.

#### Keep

- Container Tracking workspace (ParentID `9c89e3db-...`)
- `<ScreenWithRights>` XML for SB501000, SB302000–SB302030 (correct registration mechanism)
- `EnsureContainerTrackingSiteMap()` for the 4 form screens only
- Emergency delete block for the 5 GI names (cleans zombie GIDesign rows)
- `CleanupIGCMArtifacts()` (removes old IIG entries)
- `MigrateIGCMContainers()`, seed data, all DAC extensions — unrelated to GI problem
- All `<File>` and `<Graph>` elements — container tracking data model is intact

#### Verify before deploy

- SiteMap entries: only form screens under Container Tracking workspace
- No GI SiteMap entries for SB401000–SB401040
- Emergency delete still runs to clean any existing zombie rows
- SM208000 is stable (no broken GI definitions to crash it)

### Screens after deploy

| Screen ID | Title | Type | Status |
|-----------|-------|------|--------|
| SB501000 | Container Maintenance | Form | Working |
| SB302000 | Freight Forwarders | Form | Working |
| SB302010 | Container Types | Form | Working |
| SB302020 | Destinations/Ports | Form | Working |
| SB302030 | Container Preferences | Form | Working |
| SB401000 | PO Containers | GI | Removed (Phase 2) |
| SB401010 | SO Containers | GI | Removed (Phase 2) |
| SB401020 | Container Events | GI | Removed (Phase 2) |
| SB401030 | Custom Classification | GI | Removed (Phase 2) |
| SB401040 | PO Container Lines | GI | Removed (Phase 2) |

## Phase 2: GIs Done Right (future)

### Prerequisites

1. Query GIDesign to confirm database is clean (the step that should have happened before all 18 deploys)
2. Confirm no zombie rows remain after Phase 1 deploy
3. Study IIG's XML GI format — it works on this exact Acumatica instance

### Approach

- Create GIs via `GenericInquiryScreen_*.xml` files (XML import, not SQL)
- Follow IIG's exact pattern: `relations-version="20240308"`, layout section, PrimaryScreenIDNew
- Register GI screens in `<ScreenWithRights>` XML (not SQL SiteMap INSERTs)
- Remove emergency delete code once GIs are stable
- Verify in browser before merging

### Data model note

GIs are just queries — removing them loses no data. All container data lives in UsrContainer, UsrContainerEvent, UsrContainerLine, etc. Phase 2 just points new GIs at the same tables.

## AcuDev KB Deliverables

Encode lessons into AcuDev knowledge base at `/Users/kevin/dev/acudev/src/ingest/examples/`:

### 1. `generic-inquiry-anti-patterns.md` (new)

Hard lessons from 18 failed deploys:

- **Never create GIs via SQL INSERT** — ObjectName, layout metadata, and relations data are required by the GI engine but not settable via raw SQL. Use XML import.
- **GI XML import silently drops child rows on Name collision** — if GIDesign already has a row with the same (CompanyID, Name), child data (GITable, GIResult, etc.) may be orphaned with a mismatched DesignID.
- **Always query GIDesign before any GI operation** — `SELECT DesignID, Name, CompanyID FROM GIDesign WHERE Name = '...'`. Don't deploy hypotheses.
- **SM208000 (GI Designer) crashes on broken GI rows** — incomplete GI definitions cause "An item with the same key has already been added" in `PXGenericInqGrph+Definition`, taking down the screen for all users.
- **SQL-created GI headers block XML import** — unique constraint on (CompanyID, Name) means the XML import can't replace a SQL-created header with the correct DesignID.

### 2. `acumatica-screen-registration.md` (new)

- **Use `<ScreenWithRights>` XML for navigation** — this is the correct mechanism for registering screens, SiteMap entries, and access rights in Acumatica customization packages.
- **Do not use SQL SiteMap INSERTs** — they create parallel entries that conflict with XML-managed SiteMap rows and require separate cleanup code.
- **GI screens use `~/GenericInquiry/GenericInquiry.aspx?id=<DesignID>`** — the DesignID must match a working GI definition. If the GI doesn't exist, the link is dead.

### 3. Update `generic-inquiry-creation.md` (existing, already rewritten)

Add the Phase 2 pattern once GIs are working — concrete XML examples from our own codebase, not just "don't do SQL."

### 4. `acumatica-deploy-discipline.md` (new)

- Every publish restarts the app pool and disrupts users
- Query INFORMATION_SCHEMA before writing SQL against system tables
- Query actual data before writing migration SQL
- Verify in the running system before claiming success
- One deploy per change — no "quick fix" iterations against production

### Ingest

Push all new/updated KB docs to AcuDev via `POST /knowledge/ingest` after writing them.
