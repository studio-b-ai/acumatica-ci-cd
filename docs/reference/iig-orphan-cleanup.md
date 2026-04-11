# IIG Orphan Row Cleanup — September 2026

## Context

Three ISV/internal packages were removed from Heritage Fabrics production
but left orphaned metadata in the Acumatica publish registry. This forces
`--no-merge` mode (`isMergeWithExistingPackages=false`) for all publishes,
which skips ASPX extraction for co-published projects.

Acumatica quoted an SOW for cleanup. Heritage Fabrics gets DB access in
September 2026.

## Orphaned Projects

| Project Name | Origin |
|---|---|
| `IIGCONTAINERMGMT[24.204.0004][R19]1` | IIG Container Management ISV |
| `IIGHFContainerMods[24.204.0004][R04]` | IIG HF Container Modifications |
| `AesthetikContainerGIs` | Internal — duplicated AesthetikContainers GIs |

## Cleanup SQL

Run against the Heritage Fabrics production database after obtaining access.

**IMPORTANT:** Take a database backup before running. Test on sandbox first.

```sql
-- Step 1: Identify orphan rows
SELECT CompanyID, Name, Level, IsPublished
FROM CustProject
WHERE Name IN (
    'IIGCONTAINERMGMT[24.204.0004][R19]1',
    'IIGHFContainerMods[24.204.0004][R04]',
    'AesthetikContainerGIs'
);

-- Step 2: Delete orphan project metadata (cascade to related tables)
DELETE FROM CustProjectMeta WHERE ProjectID IN (
    SELECT ProjectID FROM CustProject WHERE Name IN (
        'IIGCONTAINERMGMT[24.204.0004][R19]1',
        'IIGHFContainerMods[24.204.0004][R04]',
        'AesthetikContainerGIs'
    )
);

DELETE FROM CustPublishedProject WHERE Name IN (
    'IIGCONTAINERMGMT[24.204.0004][R19]1',
    'IIGHFContainerMods[24.204.0004][R04]',
    'AesthetikContainerGIs'
);

DELETE FROM CustProject WHERE Name IN (
    'IIGCONTAINERMGMT[24.204.0004][R19]1',
    'IIGHFContainerMods[24.204.0004][R04]',
    'AesthetikContainerGIs'
);

-- Step 3: Verify cleanup
SELECT COUNT(*) AS remaining FROM CustProject
WHERE Name LIKE 'IIG%' OR Name = 'AesthetikContainerGIs';
-- Expected: 0
```

## After Cleanup

1. Remove `--no-merge` from deploy.py invocations in `acuops-deploy.yml`
2. Remove `no_merge_expected` section from `acuops.yaml`
3. Remove `--no-merge-expected` flag from verify.py invocations in workflow
4. Test a publish with `isMergeWithExistingPackages=true` on sandbox first
