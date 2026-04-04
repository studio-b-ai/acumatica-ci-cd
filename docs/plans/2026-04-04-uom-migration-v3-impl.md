# UOM Migration v3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Change base UOM from PIECE to YDS across Heritage Test by inserting missing YDS→YDS self-conversions, then flipping BaseUnit/SalesUnit — without touching existing INUnit records.

**Architecture:** Two-phase approach. Phase A: diagnostic plugin inserts ONE test YDS→YDS record and we verify visibility via Playwright. Phase B: full migration plugin inserts all missing YDS→YDS records, flips BaseUnit/SalesUnit, renames UOM on transaction tables, and renames PIECENBR→BOLTID. Both phases deploy via the Customization API (REST), not manual UI publish.

**Tech Stack:** Acumatica CustomizationPlugin (C#), Playwright (Python, sync API), Customization API (REST)

**Design doc:** `docs/plans/2026-04-04-uom-migration-v3-design.md`

---

### Task 1: Phase A — Single-Item INSERT Proof of Concept

**Files:**
- Modify: `Customization/UomDiagnostic/project.xml` (rewrite for single-item INSERT test)

**Context:** The v1 AAR documented that raw SQL INSERT into INUnit created ORM-invisible records. Before committing to the full migration, we test with ONE item. We pick an item that has PIECE→PIECE but NOT YDS→YDS at Type=1, insert a YDS→YDS record by copying all columns from the PIECE→PIECE record, then verify it appears in the Acumatica UI via Playwright.

**Step 1: Rewrite UomDiagnostic to insert a single test record**

Rewrite `Customization/UomDiagnostic/project.xml` with this plugin code:

```csharp
public class UomDiagnostic : CustomizationPlugin
{
    public override void UpdateDatabase()
    {
        WriteLog("=== UomDiagnostic v4: Single-item YDS→YDS INSERT test ===");

        var cs = System.Configuration.ConfigurationManager.ConnectionStrings["ProjectX"];
        if (cs == null) { WriteLog("ERROR: No connection string."); return; }

        string connStr = cs.ConnectionString + ";TrustServerCertificate=True";
        try
        {
            using (var conn = new Microsoft.Data.SqlClient.SqlConnection(connStr))
            {
                conn.Open();

                // Find ONE item that has PIECE→PIECE but NOT YDS→YDS at Type=1
                int testInventoryID = 0;
                string testInventoryCD = "";
                using (var cmd = conn.CreateCommand())
                {
                    cmd.CommandText = @"
                        SELECT TOP 1 src.InventoryID, i.InventoryCD
                        FROM INUnit src
                        INNER JOIN InventoryItem i ON i.InventoryID = src.InventoryID AND i.CompanyID = src.CompanyID
                        WHERE src.UnitType = 1 AND src.FromUnit = 'PIECE' AND src.ToUnit = 'PIECE'
                        AND NOT EXISTS (
                            SELECT 1 FROM INUnit dup
                            WHERE dup.CompanyID = src.CompanyID AND dup.UnitType = 1
                            AND dup.InventoryID = src.InventoryID
                            AND dup.FromUnit = 'YDS' AND dup.ToUnit = 'YDS'
                        )
                        ORDER BY src.InventoryID";
                    cmd.CommandTimeout = 30;
                    using (var rdr = cmd.ExecuteReader())
                    {
                        if (rdr.Read())
                        {
                            testInventoryID = rdr.GetInt32(0);
                            testInventoryCD = rdr.GetString(1).Trim();
                        }
                    }
                }

                if (testInventoryID == 0)
                {
                    WriteLog("No eligible item found (all items already have YDS→YDS). Skipping test.");
                    return;
                }

                WriteLog($"Test item: {testInventoryCD} (InventoryID={testInventoryID})");

                // INSERT one YDS→YDS record by copying from PIECE→PIECE
                using (var cmd = conn.CreateCommand())
                {
                    cmd.CommandText = @"
                        INSERT INTO INUnit (CompanyID, UnitType, ItemClassID, InventoryID,
                                            FromUnit, ToUnit, UnitRate, UnitMultDiv,
                                            PriceAdjustmentMultiplier, CompanyMask,
                                            CreatedByID, CreatedByScreenID, CreatedDateTime,
                                            LastModifiedByID, LastModifiedByScreenID, LastModifiedDateTime)
                        SELECT CompanyID, UnitType, ItemClassID, InventoryID,
                               'YDS', 'YDS', UnitRate, UnitMultDiv,
                               PriceAdjustmentMultiplier, CompanyMask,
                               CreatedByID, CreatedByScreenID, GETUTCDATE(),
                               LastModifiedByID, LastModifiedByScreenID, GETUTCDATE()
                        FROM INUnit
                        WHERE UnitType = 1 AND InventoryID = @invID
                        AND FromUnit = 'PIECE' AND ToUnit = 'PIECE'";
                    cmd.Parameters.AddWithValue("@invID", testInventoryID);
                    cmd.CommandTimeout = 30;
                    int rows = cmd.ExecuteNonQuery();
                    WriteLog($"Inserted {rows} YDS→YDS record(s) for {testInventoryCD}");
                }

                // Verify the record exists
                using (var cmd = conn.CreateCommand())
                {
                    cmd.CommandText = @"
                        SELECT COUNT(*) FROM INUnit
                        WHERE UnitType = 1 AND InventoryID = @invID
                        AND FromUnit = 'YDS' AND ToUnit = 'YDS'";
                    cmd.Parameters.AddWithValue("@invID", testInventoryID);
                    cmd.CommandTimeout = 10;
                    var count = cmd.ExecuteScalar();
                    WriteLog($"Verification: {count} YDS→YDS record(s) found for {testInventoryCD}");
                }

                // Store the test item CD in item 00004's Note for Playwright to read
                using (var cmd = conn.CreateCommand())
                {
                    cmd.CommandText = @"
                        UPDATE Note SET NoteText = @text
                        WHERE NoteID = (
                            SELECT TOP 1 NoteID FROM InventoryItem
                            WHERE StkItem = 1 ORDER BY InventoryID
                        )";
                    cmd.Parameters.AddWithValue("@text", $"UOM_TEST_ITEM={testInventoryCD}");
                    cmd.CommandTimeout = 10;
                    cmd.ExecuteNonQuery();
                }

                WriteLog($"Test item CD stored in first item Note: {testInventoryCD}");
            }
        }
        catch (Exception ex)
        {
            WriteLog($"ERROR: {ex.Message}");
        }

        WriteLog("=== UomDiagnostic v4 COMPLETE ===");
    }
}
```

**Step 2: Deploy via Customization API and read publish log**

Use this Python script to import, publish, and verify:

```python
# scripts/deploy_diagnostic.py (run locally, not committed)
import requests, base64, time, json, warnings
warnings.filterwarnings("ignore")

URL = "https://heritagefabrics.acumatica.com"
session = requests.Session()
session.post(f"{URL}/entity/auth/login", json={
    "name": "api-bot", "password": "pedhek-hugpid-4Gokge", "tenant": "Heritage Test"
})

with open("Customization/UomDiagnostic/UomDiagnostic.zip", "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")

session.post(f"{URL}/CustomizationApi/Import", json={
    "projectName": "UomDiagnostic", "projectLevel": 0,
    "isReplaceIfExists": True, "projectContentBase64": b64
})

session.post(f"{URL}/CustomizationApi/publishBegin", json={
    "isMergeWithExistingPackages": True,
    "projectNames": ["UomDiagnostic", "AesthetikWMS", "AesthetikContainers", "Ramp", "StudioBAcuOps"],
    "tenantMode": "Current"
})

for i in range(30):
    time.sleep(10)
    r = session.post(f"{URL}/CustomizationApi/publishEnd", json={})
    d = r.json()
    if d.get("isCompleted"):
        for log in d.get("log", []):
            msg = log.get("message", "")
            if "UomDiag" in msg or "YDS" in msg or "PIECE" in msg or "Test item" in msg:
                print(msg)
        break

# Wait for restart, re-login
time.sleep(45)
for a in range(8):
    try:
        r = session.post(f"{URL}/entity/auth/login", json={
            "name": "api-bot", "password": "pedhek-hugpid-4Gokge", "tenant": "Heritage Test"
        }, timeout=30)
        if r.status_code == 204: break
    except: pass
    time.sleep(15)

# Read test item CD from Note
r = session.get(f"{URL}/entity/Default/24.200.001/StockItem", params={
    "$top": "1", "$filter": "InventoryID eq '00004'"
}, headers={"Accept": "application/json"})
data = r.json()
note = data[0].get("note", {}).get("value", "") if data else ""
print(f"Test item note: {note}")
session.post(f"{URL}/entity/auth/logout")
```

**Step 3: Verify via Playwright that the inserted YDS→YDS record is visible**

Run Playwright to navigate to the test item on IN202500 and check if YDS appears in the conversions grid. The test item CD is in the Note field of item 00004.

```bash
# Read the test item CD, then check its conversions
python3 << 'EOF'
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, ignore_https_errors=True)
    page = ctx.new_page()

    # Login
    page.goto("https://heritagefabrics.acumatica.com/Frames/Login.aspx", wait_until="networkidle", timeout=60000)
    page.fill("#txtUser", "api-bot")
    page.fill("#txtPass", "pedhek-hugpid-4Gokge")
    page.locator("#cmbCompany").select_option(label="Heritage Test")
    page.click("#btnLogin")
    page.wait_for_timeout(5000)
    agree = page.locator('button:has-text("Agree")')
    if agree.count() > 0:
        agree.first.click()
    page.wait_for_timeout(10000)

    # Navigate to test item (get CD from REST API first)
    import requests
    s = requests.Session()
    s.post("https://heritagefabrics.acumatica.com/entity/auth/login", json={
        "name": "api-bot", "password": "pedhek-hugpid-4Gokge", "tenant": "Heritage Test"
    })
    r = s.get("https://heritagefabrics.acumatica.com/entity/Default/24.200.001/StockItem",
        params={"$top": "1", "$filter": "InventoryID eq '00004'"},
        headers={"Accept": "application/json"})
    note = r.json()[0].get("note", {}).get("value", "")
    s.post("https://heritagefabrics.acumatica.com/entity/auth/logout")

    test_item = note.replace("UOM_TEST_ITEM=", "").strip()
    print(f"Test item: {test_item}")

    # Navigate to that item
    page.goto(f"https://heritagefabrics.acumatica.com/Main?CompanyID=Heritage+Test&ScreenId=IN202500&InventoryCD={test_item}",
        wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(5000)

    main_frame = page.frame("main")
    body = main_frame.locator("body").inner_text()

    if "YDS" in body:
        print("PASS: YDS appears on the stock item screen")
        # Check conversions grid specifically
        grid_text = main_frame.evaluate('''() => {
            var rows = document.querySelectorAll('[id*="gridUnits"] tr');
            var result = [];
            for (var i = 0; i < rows.length; i++) {
                result.push(rows[i].textContent.trim());
            }
            return result.join("\\n");
        }''')
        if "YDS" in grid_text:
            print("PASS: YDS→YDS visible in conversions grid")
            print(f"Grid content: {grid_text[:500]}")
        else:
            print("FAIL: YDS not in conversions grid")
            print(f"Grid: {grid_text[:500]}")
    else:
        print("FAIL: YDS does not appear on the stock item screen")

    browser.close()
EOF
```

**Expected outcome:** "PASS: YDS→YDS visible in conversions grid." If FAIL, the INSERT approach doesn't work and we need a different strategy.

**Step 4: Commit**

```bash
git add Customization/UomDiagnostic/project.xml
git commit -m "feat: Phase A — single-item INSERT test for UOM migration v3"
```

---

### Task 2: Phase B — Full Migration Plugin

**Prerequisite:** Task 1 PASSED (YDS→YDS INSERT produced ORM-visible record).

**Files:**
- Create: `Customization/UomMigrationV3/project.xml`

**Step 1: Write the full migration plugin**

Create `Customization/UomMigrationV3/project.xml` with a CustomizationPlugin that does:

1. Pre-flight counts (PIECE references, YDS→YDS counts)
2. Section 1: INSERT missing YDS→YDS self-conversions (all UnitTypes)
3. Section 2: UPDATE InventoryItem BaseUnit/SalesUnit PIECE→YDS
4. Section 3: UPDATE INItemClass BaseUnit/SalesUnit PIECE→YDS
5. Sections 4-8: UPDATE UOM on transaction tables (SOLine, POLine, INTran, ARTran, APTran, etc.)
6. Section 9: Rename PIECENBR→BOLTID
7. Post-flight counts

All wrapped in a transaction. Uses `Safe()` helper for tables that may not exist. Company-scoped via `TARGET_COMPANY = "Heritage Test"`.

Key difference from v2: Section 1 is INSERT (not UPDATE/DELETE), and INUnit is never modified — only added to.

**Step 2: Deploy via Customization API**

Same pattern as Task 1 — import, publish, read publish log from `publishEnd` response.

**Step 3: Commit**

```bash
git add Customization/UomMigrationV3/project.xml
git commit -m "feat: UOM migration v3 — INSERT-then-flip (Heritage Test scoped)"
```

---

### Task 3: Playwright e2e Smoke Tests

**Prerequisite:** Task 2 completed (migration published and ran successfully).

**Files:**
- Modify: `tests/ui/test_uom_migration.py` (fix item CDs for Heritage Test)

**Step 1: Fix test item constants**

Heritage Test uses item CDs like `00004`, `00005` — not `28021`. Update `ITEM_CD` in the test file. Also update `CUSTOMER_ID` if the Drapery House customer doesn't exist in Heritage Test.

First, query Heritage Test to find a valid PIECENBR (now BOLTID) item and a valid customer:

```bash
# Find a valid item and customer
python3 -c "
import requests, warnings; warnings.filterwarnings('ignore')
s = requests.Session()
s.post('https://heritagefabrics.acumatica.com/entity/auth/login', json={
    'name': 'api-bot', 'password': 'pedhek-hugpid-4Gokge', 'tenant': 'Heritage Test'})
# Items
r = s.get('https://heritagefabrics.acumatica.com/entity/Default/24.200.001/StockItem',
    params={'\$top': '3', '\$select': 'InventoryID,BaseUOM,LotSerialClass'},
    headers={'Accept': 'application/json'})
for i in r.json():
    print(f'Item: {i[\"InventoryID\"][\"value\"]} Base={i[\"BaseUOM\"][\"value\"]} Lot={i.get(\"LotSerialClass\",{}).get(\"value\",\"\")}')
# Customers
r = s.get('https://heritagefabrics.acumatica.com/entity/Default/24.200.001/Customer',
    params={'\$top': '3', '\$select': 'CustomerID,CustomerName'},
    headers={'Accept': 'application/json'})
for c in r.json():
    print(f'Customer: {c[\"CustomerID\"][\"value\"]} {c.get(\"CustomerName\",{}).get(\"value\",\"\")}')
s.post('https://heritagefabrics.acumatica.com/entity/auth/logout')
"
```

**Step 2: Update test constants and run**

Update `ITEM_CD`, `EXPECTED_UOM`, `EXPECTED_LOT_CLASS`, and customer ID based on actual Heritage Test data. Then run:

```bash
ACUMATICA_URL="https://heritagefabrics.acumatica.com" \
ACUMATICA_USERNAME="api-bot" \
ACUMATICA_PASSWORD="pedhek-hugpid-4Gokge" \
ACUMATICA_TENANT="Heritage Test" \
pytest tests/ui/test_uom_migration.py -v --tb=short
```

All 7 checks must pass:
- `test_stock_item_base_uom_is_yds` — BaseUnit = YDS
- `test_inunit_conversions_on_stock_item` — YDS→YDS visible
- `test_inunit_conversions_screen` — IN209000 shows conversions
- `test_unallocated_piece_goods_gi_loads` — GI with BOLTID filter
- `test_existing_sales_order_loads_with_details` — no UOM errors
- `test_create_pc_order_with_boltid_item` — new order saves
- Cleanup: test order deleted

**Step 3: Commit**

```bash
git add tests/ui/test_uom_migration.py
git commit -m "fix: update Playwright test constants for Heritage Test item CDs"
```

---

### Task 4: Push and Create PR

**Step 1: Push branch**

```bash
git push -u origin claude/uom-migration-v2-clean
```

**Step 2: Create PR**

Target: `main`
Title: `UOM migration v3: INSERT-then-flip + Playwright e2e`
Body: Reference design doc, Phase A proof of concept result, Phase B migration log, Playwright test results.
