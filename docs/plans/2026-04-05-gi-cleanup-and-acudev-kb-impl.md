# GI Cleanup + AcuDev KB Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove broken GI SQL code and navigation links so Monday's user experience is clean, then encode lessons into AcuDev KB.

**Architecture:** All changes are in one file (`Customization/AesthetikContainers/project.xml`) — removing SQL methods and SiteMap entries for 5 broken GI screens while keeping the 5 working form screens. AcuDev KB docs are new files in a separate repo.

**Tech Stack:** Acumatica customization XML (CDATA C#), AcuDev knowledge base (markdown + REST ingest)

---

### Task 1: Remove `EnsureContainerTrackingGIs()` call from per-company loop

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml:1240`

**Step 1: Remove the call**

In the per-company try block (line ~1240), delete the line:
```csharp
                            EnsureContainerTrackingGIs(conn, companyId);
```

The block should go from:
```csharp
                            CleanupIGCMArtifacts(conn, companyId);
                            EnsureContainerTrackingGIs(conn, companyId);
                            EnsureContainerTrackingSiteMap(conn, companyId);
```
To:
```csharp
                            CleanupIGCMArtifacts(conn, companyId);
                            EnsureContainerTrackingSiteMap(conn, companyId);
```

**Step 2: Verify no other callers**

Search for `EnsureContainerTrackingGIs` — should only appear in the method definition (which we remove in Task 2).

**Step 3: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "fix: remove EnsureContainerTrackingGIs call — stop creating broken GI rows"
```

---

### Task 2: Delete `EnsureContainerTrackingGIs()` method

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml:1674-1812`

**Step 1: Delete the entire method**

Remove lines ~1674–1812 — from `private void EnsureContainerTrackingGIs(` through the closing brace and the blank line after it. This is ~138 lines of SQL INSERT code that creates broken GI rows.

The method starts with:
```csharp
        private void EnsureContainerTrackingGIs(SqlConnection conn, int companyId)
        {
```

And ends with:
```csharp
            WriteLog(string.Format("[AesthetikContainers] Container Tracking GIs (4) for CompanyID={0} — OK", companyId));
        }
```

**Step 2: Verify clean removal**

Search for `EnsureContainerTrackingGIs` — should return zero results.

**Step 3: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "fix: delete EnsureContainerTrackingGIs method — SQL GI creation is broken by design"
```

---

### Task 3: Remove GI entries from `EnsureContainerTrackingSiteMap()`

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml:1820-1831` (line numbers will have shifted after Task 2)

**Step 1: Remove 5 GI entries from the entries array**

The `entries` array currently has 9 items. Remove the 5 GI entries (SB401000–SB401040), keeping only the 4 form screen entries.

Change from:
```csharp
            string[][] entries = new[]
            {
                new[] { "SB401000", "PO Containers", "~/GenericInquiry/GenericInquiry.aspx?id=SB401000", "7.6" },
                new[] { "SB401010", "SO Containers", "~/GenericInquiry/GenericInquiry.aspx?id=SB401010", "7.7" },
                new[] { "SB401020", "Container Events", "~/GenericInquiry/GenericInquiry.aspx?id=SB401020", "7.8" },
                new[] { "SB302000", "Freight Forwarders", "~/Pages/SB/SB302000.aspx", "7.9" },
                new[] { "SB401030", "Custom Classification", "~/GenericInquiry/GenericInquiry.aspx?id=SB401030", "8.0" },
                new[] { "SB401040", "PO Container Lines", "~/GenericInquiry/GenericInquiry.aspx?id=SB401040", "8.1" },
                new[] { "SB302010", "Container Types", "~/Pages/SB/SB302010.aspx", "8.2" },
                new[] { "SB302020", "Destinations/Ports", "~/Pages/SB/SB302020.aspx", "8.3" },
                new[] { "SB302030", "Container Preferences", "~/Pages/SB/SB302030.aspx", "8.4" },
            };
```

To:
```csharp
            string[][] entries = new[]
            {
                new[] { "SB302000", "Freight Forwarders", "~/Pages/SB/SB302000.aspx", "7.9" },
                new[] { "SB302010", "Container Types", "~/Pages/SB/SB302010.aspx", "8.2" },
                new[] { "SB302020", "Destinations/Ports", "~/Pages/SB/SB302020.aspx", "8.3" },
                new[] { "SB302030", "Container Preferences", "~/Pages/SB/SB302030.aspx", "8.4" },
            };
```

**Step 2: Update the log message**

Change:
```csharp
            WriteLog(string.Format("[AesthetikContainers] Container Tracking SiteMap (9 screens) for CompanyID={0} — OK", companyId));
```
To:
```csharp
            WriteLog(string.Format("[AesthetikContainers] Container Tracking SiteMap (4 form screens) for CompanyID={0} — OK", companyId));
```

**Step 3: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "fix: remove 5 broken GI links from Container Tracking SiteMap"
```

---

### Task 4: Remove GI screen IDs from IGCM cleanup whitelist

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml` — two `NOT IN` clauses in `CleanupIGCMArtifacts()`

**Step 1: Update Step 3 whitelist (workspace cleanup)**

Find the first `NOT IN` list (workspace SiteMap cleanup). Change from:
```sql
                  AND ScreenID NOT IN ('SB501000','SB401000','SB401010','SB401020','SB302000','SB401030',
                                       'SB401040','SB302010','SB302020','SB302030')
```
To:
```sql
                  AND ScreenID NOT IN ('SB501000','SB302000','SB302010','SB302020','SB302030')
```

**Step 2: Update Step 3b whitelist (outside-workspace cleanup)**

Find the second `NOT IN` list. Same change:
```sql
                  AND ScreenID NOT IN ('SB501000','SB401000','SB401010','SB401020','SB302000','SB401030',
                                       'SB401040','SB302010','SB302020','SB302030')
```
To:
```sql
                  AND ScreenID NOT IN ('SB501000','SB302000','SB302010','SB302020','SB302030')
```

This means `CleanupIGCMArtifacts()` will now delete any existing SiteMap entries for SB401000–SB401040, cleaning up the broken GI links.

**Step 3: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "fix: remove GI screen IDs from IGCM cleanup whitelist — let cleanup sweep broken entries"
```

---

### Task 5: Delete dead code methods

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml:1298-1423` (line numbers shifted from prior tasks)

**Step 1: Delete dead code block**

Remove the comment block and three dead methods:
- The `// NOTE: SetSiteMapGraphType, GrantScreenAccess, DiagnoseAccessRights are dead code.` comment (3 lines)
- `SetSiteMapGraphType()` method (~lines 1303–1327)
- `GrantScreenAccess()` method (~lines 1329–1343)
- `DiagnoseAccessRights()` method (~lines 1345–1423)

Total removal: ~126 lines of dead diagnostic/registration code.

**Step 2: Verify no callers**

Search for `SetSiteMapGraphType`, `GrantScreenAccess`, `DiagnoseAccessRights` — should return zero results after removal.

**Step 3: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "chore: remove dead code — SetSiteMapGraphType, GrantScreenAccess, DiagnoseAccessRights"
```

---

### Task 6: Verify the XML is well-formed

**Step 1: Count CDATA open/close pairs**

The `project.xml` uses CDATA sections extensively. After all edits, verify the file is well-formed:

```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('Customization/AesthetikContainers/project.xml'); print('XML valid')"
```

Expected: `XML valid`

**Step 2: Verify key elements still present**

```bash
grep -c "EnsureContainerTrackingGIs" Customization/AesthetikContainers/project.xml
# Expected: 0

grep -c "EnsureContainerTrackingSiteMap" Customization/AesthetikContainers/project.xml
# Expected: 2 (method definition + call)

grep -c "SB401000" Customization/AesthetikContainers/project.xml
# Expected: 0 (all GI references removed)

grep -c "SB302000" Customization/AesthetikContainers/project.xml
# Expected: >0 (form screens retained)

grep -c "SetSiteMapGraphType" Customization/AesthetikContainers/project.xml
# Expected: 0

grep -c "ScreenWithRights" Customization/AesthetikContainers/project.xml
# Expected: 2 (open + close tags)
```

**Step 3: Commit (no-op if all prior commits are clean)**

Already committed per-task. This is verification only.

---

### Task 7: Write AcuDev KB — Generic Inquiry Anti-Patterns

**Files:**
- Create: `/Users/kevin/dev/acudev/src/ingest/examples/generic-inquiry-anti-patterns.md`

**Step 1: Write the KB doc**

```markdown
# Generic Inquiry Anti-Patterns — Lessons from Production

## NEVER Create GIs via SQL INSERT

SQL INSERTs into GI system tables (GIDesign, GITable, GIResult, etc.) produce incomplete GI definitions that:

1. **Miss ObjectName** — The GI engine requires ObjectName on GIResult rows to resolve DAC-to-column mapping. The XML import engine sets this automatically from the parent GITable element. SQL INSERTs don't.

2. **Crash SM208000** — Incomplete GI definitions cause "An item with the same key has already been added" in PXGenericInqGrph+Definition. This crashes the GI Designer screen for ALL users, not just the broken GI.

3. **Miss audit columns** — NOT NULL columns like CreatedByID, CreatedDateTime, LastModifiedByID vary by Acumatica version. Missing any one causes a silent INSERT failure.

4. **Block XML import** — GIDesign has a unique constraint on (CompanyID, Name). SQL-created headers prevent the XML import engine from creating the correct definition. The import may silently skip or orphan child rows.

## Always Query Before Operating on GIs

Before any GI operation (create, modify, delete), query the database:

```sql
-- What GI headers exist?
SELECT CompanyID, DesignID, Name, PrimaryScreenIDNew
FROM GIDesign
WHERE Name = N'YourGIName'
ORDER BY CompanyID;

-- Do they have child data?
SELECT d.Name, d.CompanyID,
  (SELECT COUNT(*) FROM GITable t WHERE t.DesignID = d.DesignID AND t.CompanyID = d.CompanyID) as Tables,
  (SELECT COUNT(*) FROM GIResult r WHERE r.DesignID = d.DesignID AND r.CompanyID = d.CompanyID) as Results
FROM GIDesign d
WHERE d.Name = N'YourGIName';
```

Never deploy GI changes based on hypotheses. Every failed deploy restarts the app pool and disrupts production users.

## GI XML Import Can Silently Fail

When `<GenericInquiryScreen>` XML is imported and GIDesign already has a row with the same (CompanyID, Name) but a different DesignID, the import engine may:
- Update the header row but orphan child rows (they reference the XML's DesignID, not the existing one)
- Skip the import entirely without error
- Import child rows under a DesignID that doesn't match the header

**Prevention:** Clean up any SQL-era GI rows before attempting XML import. Use DELETE statements targeting the specific GI names across all companies.

## The Correct Approach: XML Import

See `acumatica-gi-xml-import-format.md` for the definitive format reference. Key points:
- One `GenericInquiryScreen_*.xml` file per GI
- Follow the IIG Container Management package pattern exactly
- Use `relations-version="20240308"` with full layout section
- All GUIDs must be valid hex UUIDs
- Register GI screens in `<ScreenWithRights>` XML, not SQL SiteMap INSERTs
```

**Step 2: Commit**

```bash
cd /Users/kevin/dev/acudev
git add src/ingest/examples/generic-inquiry-anti-patterns.md
git commit -m "docs: GI anti-patterns KB — lessons from 18 failed deploys"
```

---

### Task 8: Write AcuDev KB — Screen Registration

**Files:**
- Create: `/Users/kevin/dev/acudev/src/ingest/examples/acumatica-screen-registration.md`

**Step 1: Write the KB doc**

```markdown
# Acumatica Screen Registration — Correct Patterns

## Use `<ScreenWithRights>` XML for Navigation

The correct way to register screens in an Acumatica customization package is via `<ScreenWithRights>` XML elements in project.xml. This handles:
- SiteMap entry creation (URL, title, position, workspace assignment)
- Access rights (role-based permissions via RolesInGraph/RolesInCache/RolesInMember)
- Idempotent import (same NodeID = update, not duplicate)

### Example: Form Screen Registration

```xml
<ScreenWithRights AccessRightsMergeRule="ApplyAndKeep">
    <data-set>
        <relations format-version="3" relations-version="20240201" main-table="SiteMap">
            <link from="RolesInCache (ScreenID)" to="SiteMap (ScreenID)" />
            <link from="RolesInGraph (ScreenID)" to="SiteMap (ScreenID)" />
            <link from="RolesInMember (ScreenID)" to="SiteMap (ScreenID)" />
            <link from="Roles (Rolename, ApplicationName)" to="RolesInCache (Rolename, ApplicationName)" type="FromMaster" updateable="False" />
            <link from="Roles (Rolename, ApplicationName)" to="RolesInGraph (Rolename, ApplicationName)" type="FromMaster" updateable="False" />
            <link from="Roles (Rolename, ApplicationName)" to="RolesInMember (Rolename, ApplicationName)" type="FromMaster" updateable="False" />
        </relations>
        <layout>
            <table name="SiteMap">
                <table name="RolesInCache" uplink="(ScreenID) = (ScreenID)" />
                <table name="RolesInGraph" uplink="(ScreenID) = (ScreenID)" />
                <table name="RolesInMember" uplink="(ScreenID) = (ScreenID)" />
            </table>
            <table name="Roles" />
        </layout>
        <data>
            <SiteMap>
                <row Position="7.5" Title="Screen Title" Url="~/Pages/SB/SB501000.aspx"
                     ScreenID="SB501000" NodeID="b88b362d-cad6-44c3-8656-a418f2f08923"
                     ParentID="9c89e3db-7c47-43c0-8554-5d2c9f2c0e87" SelectedUI="E">
                    <RolesInGraph Rolename="Administrator" ApplicationName="/" Accessrights="4" />
                    <RolesInGraph Rolename="*" ApplicationName="/" Accessrights="0" />
                </row>
            </SiteMap>
            <Roles>
                <row Rolename="Administrator" ApplicationName="/" Descr="System Administrator" Guest="0" />
            </Roles>
        </data>
    </data-set>
</ScreenWithRights>
```

### Key Fields
- **ParentID** — The workspace GUID. Determines which workspace/folder the screen appears under.
- **NodeID** — Unique identifier for this SiteMap entry. Use a fixed GUID (not NEWID()) so re-imports update rather than duplicate.
- **Position** — Sort order within the workspace (decimal, e.g., "7.5", "8.2").
- **SelectedUI** — "E" = shown in sidebar. Other values control visibility.
- **Accessrights** — "4" = full access for the role. "0" = inherited/default.

## Do NOT Use SQL SiteMap INSERTs

SQL-based SiteMap registration creates entries that:
- Conflict with XML-managed entries (duplicate ScreenIDs)
- Use NEWID() for NodeID, creating new entries on every publish
- Require separate cleanup code to manage
- Don't set access rights properly

If you see `INSERT INTO SiteMap` in a CustomizationPlugin, it should be replaced with `<ScreenWithRights>` XML.

## GI Screen URLs

Generic Inquiry screens use a special URL pattern:
```
~/GenericInquiry/GenericInquiry.aspx?id=<DesignID>
```

The DesignID must match a working GI definition in GIDesign. If the GI doesn't exist, the link shows "This generic inquiry does not exist anymore."

For GI screens, the SiteMap entry should only be created AFTER the GI definition is confirmed working. The `<GenericInquiryScreen>` XML import handles SiteMap creation automatically — do not create separate SiteMap entries for GIs.
```

**Step 2: Commit**

```bash
cd /Users/kevin/dev/acudev
git add src/ingest/examples/acumatica-screen-registration.md
git commit -m "docs: screen registration KB — ScreenWithRights XML vs SQL SiteMap"
```

---

### Task 9: Write AcuDev KB — Deploy Discipline

**Files:**
- Create: `/Users/kevin/dev/acudev/src/ingest/examples/acumatica-deploy-discipline.md`

**Step 1: Write the KB doc**

```markdown
# Acumatica Deploy Discipline

## Every Publish Restarts the App Pool

When you call `publishBegin` on the Acumatica Customization API, it:
1. Compiles all customization projects
2. Restarts the application pool
3. Disconnects all active user sessions
4. Takes 2-5 minutes to come back online

There is no "quick fix" deploy. Every publish has the same cost. Plan accordingly.

## Query Before You Write

### System Tables
Before writing SQL against Acumatica system tables (GIDesign, SiteMap, SMGraphPermission, etc.):
1. Query `INFORMATION_SCHEMA.COLUMNS` to get actual column names
2. Deploy the diagnostic FIRST
3. Read the publish log
4. THEN write the correct SQL

Column names change between Acumatica versions (e.g., ScreenID vs PrimaryScreenIDNew). Table names change too (FilterPresets was removed in 24.2). Never guess.

### Data Tables
Before writing migration SQL:
1. Query the actual data to understand current state
2. Document baseline counts
3. Write migration SQL that handles what actually exists
4. If you can't query the data, say so — don't guess

### GI Tables
Before any GI operation:
1. Query GIDesign for the target GI name
2. Check if child rows exist (GITable, GIResult)
3. Understand whether you're creating, updating, or conflicting
4. Never deploy GI changes based on hypotheses

## Verify in the Running System

"XML validates" is not verification. "The SQL ran without errors" is not verification. "The publish log says OK" is not verification.

Verification means: open the screen in a browser, see the data, confirm it works. Until you've done that, the work is not done.

## One Change Per Deploy

Don't batch unrelated changes into a single deploy to "save time." If the deploy fails, you won't know which change caused it. If you need to roll back, you roll back everything.

Exception: pure code removal (deleting dead methods, removing broken features) can be batched because removal can't introduce new failures.
```

**Step 2: Commit**

```bash
cd /Users/kevin/dev/acudev
git add src/ingest/examples/acumatica-deploy-discipline.md
git commit -m "docs: deploy discipline KB — lessons from 18-deploy incident"
```

---

### Task 10: Ingest KB docs to AcuDev

**Step 1: Get the auth token**

```bash
cd /Users/kevin/dev/acudev && ACUDEV_TOKEN=$(/opt/homebrew/bin/railway variables --json | python3 -c "import sys,json; print(json.load(sys.stdin)['ACUDEV_AUTH_TOKEN'])")
```

**Step 2: Ingest all 3 new docs**

```bash
cd /Users/kevin/dev/acudev

# Read file contents and ingest
python3 -c "
import json, subprocess, sys

docs = [
    'src/ingest/examples/generic-inquiry-anti-patterns.md',
    'src/ingest/examples/acumatica-screen-registration.md',
    'src/ingest/examples/acumatica-deploy-discipline.md',
]

documents = []
for path in docs:
    with open(path) as f:
        content = f.read()
    title = content.split('\n')[0].lstrip('# ').strip()
    documents.append({
        'title': title,
        'content': content,
        'metadata': {'source': path.split('/')[-1], 'type': 'knowledge-base'}
    })

payload = json.dumps({'documents': documents})
print(f'Ingesting {len(documents)} docs...')
print(payload[:200])
" > /tmp/acudev-ingest-payload.json

# Then POST it
curl -s -X POST https://acudev-production-407f.up.railway.app/knowledge/ingest \
  -H "Authorization: Bearer $ACUDEV_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/acudev-ingest-payload.json
```

Expected: `{"status":"ok","ingested":3,"chunks":N,"collection":"acudev-knowledge"}`

**Step 3: Verify**

Check the response shows all 3 docs ingested with a reasonable chunk count.

---

### Task 11: Create PR

**Step 1: Push and create PR**

```bash
cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/reverent-bartik
git push -u origin claude/reverent-bartik
gh pr create --title "fix: remove broken GI code and navigation links" --body "$(cat <<'EOF'
## Summary
- Remove `EnsureContainerTrackingGIs()` — SQL GI creation that produced broken rows on every publish
- Remove 5 GI entries (SB401000–SB401040) from SiteMap creation — broken links in Container Tracking workspace
- Remove GI screen IDs from IGCM cleanup whitelist — let cleanup sweep existing broken entries
- Remove dead code: SetSiteMapGraphType, GrantScreenAccess, DiagnoseAccessRights

## Context
18 deploys on 2026-04-04 failed to create working GIs via SQL. The GI headers exist but render as empty/broken screens. This PR removes the broken code so Monday's user experience is clean: Container Tracking workspace with 5 working form screens, no broken GI links.

GIs will be re-added in Phase 2 via XML import (the correct mechanism, as IIG demonstrated).

## Test plan
- [ ] Publish completes without errors
- [ ] Container Tracking workspace shows 5 form screens (SB501000, SB302000–SB302030)
- [ ] No GI links visible (SB401000–SB401040 gone)
- [ ] SM208000 (GI Designer) loads without errors
- [ ] All form screens open and function normally

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
