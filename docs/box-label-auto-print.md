# Box Label Printing — Device Hub Setup & Usage Guide

**Platform:** Heritage Fabrics / Studio B — Acumatica 24.208  
**Customization Project:** `ShipmentLabelAutoPrint`  
**Last Updated:** 2025

---

## 1. Overview

Box labels for shipments are printed to the warehouse thermal printer via **Acumatica Device Hub** in two ways:

| Mode | Trigger | When to use |
|------|---------|-------------|
| **Auto-Print** | Shipment's WMS Pick Status transitions to **Committed** (`C`) while status is **Confirmed** | Normal warehouse workflow — no user action needed |
| **Manual Print** | User clicks **Actions → Print Box Labels** on the Shipments screen (SO302000) | Reprints after a printer jam, after correcting packages, or when the auto-print was missed |

**One label is printed per package** on the shipment (`SOPackageDetailEx` rows). Each package generates a separate Device Hub print job for the `BoxLabel4x6` report.

### How It Works (Summary)

1. **Auto-path:** A warehouse user (or the WMS integration) sets the shipment's Pick Status to **Committed** on the Shipments screen. The `SOShipmentEntry_LabelAutoPrint` graph extension detects the status transition, verifies the shipment is **Confirmed** and that labels have not already been printed (idempotency guard), and queues one `SMPrintJob` per package.
2. **Manual path:** A user clicks **Actions → Print Box Labels** on any shipment with packages. The extension resets `UsrBoxLabelPrinted` to `false`, re-queues all package labels through the same Device Hub pipeline, then saves the record with `UsrBoxLabelPrinted = true`.
3. In both paths, Device Hub picks up the queued jobs and dispatches them to the configured thermal printer.

> **Printer used:** The **Device Hub printer configured in the current user's Acumatica User Preferences** (SM202010 → Printer Name). Each user who triggers a label print (auto or manual) must have a printer assigned there.

---

## 2. Prerequisites

Before the feature will work, confirm all of the following are in place:

| # | Requirement | Notes |
|---|-------------|-------|
| 1 | **Acumatica Device Hub** installed and running on the warehouse print server | The Windows service must be running and connected to the Acumatica instance |
| 2 | **4×6 thermal label printer** connected and configured on the print server | Tested with Zebra ZD420, ZT230; any 4×6 thermal printer with a Windows driver is supported |
| 3 | **`BoxLabel4x6.rpx` report** published to the Acumatica instance | The report is included in the customization project (`Customization/_project/BoxLabel4x6.rpx`) and published automatically. It must appear in Report Designer (SM208000) with Report ID `BoxLabel4x6` exactly — the code matches this ID case-sensitively |
| 4 | **`ShipmentLabelAutoPrint` customization project** published | Deploys `SOShipmentLabelExt` (DAC), `SOShipmentEntry_LabelAutoPrint` (graph extension with both auto-print and manual action), and `ShipmentLabelSchemaInstaller` (adds `UsrBoxLabelPrinted` column to `SOShipment`) |
| 5 | **`UsrBoxLabelPrinted` column** present on the `SOShipment` SQL table | Created automatically on first publish by `ShipmentLabelSchemaInstaller`. Verify via `validate-publish.py` (`sql_columns` check) |
| 6 | **Kensium WMS** installed and the `UsrFRPickStatus` field present on shipments | Required for auto-print only. The extension reads this field by name at runtime; if absent, the auto-print trigger never fires (manual print still works) |

---

## 3. Device Hub Configuration Steps

### 3a. Verify the Printer in Device Hub

1. Open **Device Hub Printers** — navigate to screen **SM206530** in Acumatica, or open the Device Hub configuration application on the print server.
2. Confirm the thermal printer is listed. If not, click **Add** and enter the printer details.
3. Set the **Paper Size** to **4×6** (4 inches wide × 6 inches tall).
4. Ensure the printer **Status** is set to **Active**.

### 3b. Map the BoxLabel4x6 Report to the Printer

1. In Device Hub (or SM206530), open the printer record for the thermal label printer.
2. Navigate to the **Reports** tab (or equivalent mapping section).
3. Add a mapping: **Report ID** = `BoxLabel4x6` → **Printer** = your thermal printer.
4. Save the record.

> **Why this matters:** Without the report-to-printer mapping, Device Hub will not know which physical printer to use when it receives a `BoxLabel4x6` print job, and the job will remain in a pending state.

### 3c. Set Each User's Default Printer (SM202010)

Each warehouse user who may trigger label printing (auto or manual) must have a printer assigned in their personal preferences:

1. Go to **User Preferences** — screen **SM202010** — (or the user icon → Preferences).
2. In the **Printer Name** field, select the thermal label printer.
3. Save.

> **This is the printer both the auto-print and manual Print Box Labels button use.** If no printer is set for the logged-in user, labels will not be queued, and a yellow warning banner will appear on the Shipments screen.

---

## 4. Using the Manual "Print Box Labels" Button

### Location

The button is in the **Actions** drop-down menu at the top of the Shipments screen (**SO302000**):

```
Actions ▾
  ├─ Confirm Shipment
  ├─ Create Invoice
  ├─ ...
  └─ Print Box Labels   ← custom button
```

### Enabled / Disabled State

| Condition | Button state |
|-----------|-------------|
| Shipment has ≥ 1 package on the Packages tab | **Enabled** |
| Shipment has no packages | **Disabled** (grayed out) |

The button is always **visible** regardless of shipment status — this is intentional so users know the feature exists even before packages are added. It is never hidden, only disabled when there is nothing to print.

### What Happens When Clicked

1. `UsrBoxLabelPrinted` is reset to `false` on the current shipment (allowing re-queuing regardless of previous print state).
2. All `SOPackageDetailEx` rows for the shipment are fetched.
3. The current user's Device Hub printer is resolved from User Preferences.
4. One `SMPrintJob` is submitted per package.
5. On success, `UsrBoxLabelPrinted` is set to `true` and the shipment is saved.
6. A **green confirmation message** appears on the shipment header field:

   > *Box labels queued for printing (3 labels).*

   If some packages failed, the message includes a partial-failure note:

   > *Box labels queued for printing (2 labels) (1 package(s) failed — check Device Hub logs).*

7. If no printer is configured for the user, or Device Hub is unavailable, an **orange warning banner** appears with instructions, and no labels are queued.

### Error Messages

| Message | Cause | Resolution |
|---------|-------|------------|
| *No packages are defined on this shipment...* | Packages tab is empty | Add packages before printing |
| *No Device Hub printer is configured for your user account...* | `PrinterName` blank in SM202010 | Set a printer in User Preferences |
| *Box labels could not be printed. Device Hub may be offline...* | All package jobs threw exceptions | Check Device Hub service, check SM205070 trace log for `[BoxLabel]` entries |
| *Box label auto-print encountered an error: ...* | Unexpected exception | Check trace log; the exact error is in the message |

---

## 5. Report File — Data Linkage

The `BoxLabel4x6.rpx` report file is included in the customization project at `Customization/_project/BoxLabel4x6.rpx` and is registered in `project.xml` as:

```xml
<Report Name="BoxLabel4x6" FileName="BoxLabel4x6.rpx" />
```

It is published to the Acumatica instance automatically as part of the customization publish.

### Data Linkage (Packages → Contents)

The report builds its label content by joining four Acumatica tables:

```
SOShipment          [filtered: ShipmentNbr = @ShipmentNbr]
  │
  ├─ SOPackageDetailEx  [filtered: LineNbr = @PackageLineNbr]
  │    Box header row: weight, box type, dimensions.
  │    Drives the "Box X of Y" counter.
  │
  └─ SOShipmentLine    [ShipmentNbr = SOShipment.ShipmentNbr]
       One row per inventory item on the shipment.
       │
       ├─ InventoryItem  [InventoryID = SOShipmentLine.InventoryID]
       │    Provides: InventoryCD (SKU), Descr (description)
       │
       └─ INItemXRef     [InventoryID + AlternateType='CPN' + BAccountID = CustomerID]
            Provides: AlternateID (customer part number / Alternate ID column)
            LEFT JOINed — blank if no cross-reference is configured for the item.
```

**Why `SOPackageDetailEx` instead of `SOPackageDetail`:**  
`SOPackageDetailEx` is the extended DAC that carries additional fields (box type, dimensions, weight, custom fields added by the WMS). The base `SOPackageDetail` drops these fields. The C# code and the report both use `SOPackageDetailEx` to ensure full data availability.

**Box X of Y counter:**  
The `@PackageLineNbr` parameter holds the current box's line number (1, 2, 3...). The report calculates the total box count using `Count([SOPackageDetailEx.LineNbr])` across all package rows for the shipment. This produces "Box 1 of 3", "Box 2 of 3", etc.

---

## 6. Report Parameters

The `BoxLabel4x6` report accepts exactly two parameters. These are automatically populated by the customization code — no manual entry is needed during normal operation.

| Parameter | Type | Description |
|-----------|------|-------------|
| `ShipmentNbr` | String | The shipment number (e.g., `000123`) — identifies which shipment to print |
| `PackageLineNbr` | Integer | The line number of the specific package within the shipment — drives the "Box X of X" display |

These same parameters can be used when **manually re-running** the report from the Report Designer or the Shipments screen.

---

## 7. Label Layout

Each printed label is 4 inches × 6 inches and contains the following information:

### Header Section (top of label)

| Field | Source |
|-------|--------|
| **Customer Name** | Customer on the sales order linked to the shipment |
| **Ship ID** | Shipment number (`ShipmentNbr`) |
| **Ship Date** | Shipment date |
| **Box X of X** | Current package line number out of total packages on the shipment (e.g., "Box 2 of 5") |

### Detail Table (body of label)

One row per inventory line within the package:

| Column | Source |
|--------|--------|
| **Inventory ID** | Stock item inventory ID (`InventoryCD`) |
| **Alternate ID** | Customer cross-reference from `INItemXRef` (customer part number) |
| **Description** | Item description |
| **Lot / Serial** | Lot or serial number, if applicable |
| **Qty** | Quantity of that item in this box |

---

## 8. Troubleshooting

### Labels are not printing at all

| Check | Action |
|-------|--------|
| **Device Hub service** | On the print server, open Windows Services and confirm `Acumatica Device Hub` is **Running**. Restart it if needed. |
| **User printer setting** | Go to SM202010 for the user who triggered the print. Confirm a printer is assigned in the **Printer Name** field. Without this, the code logs a warning and skips queuing. |
| **Printer mapping** | In SM206530, confirm `BoxLabel4x6` is mapped to the thermal printer and the printer is **Active**. |
| **Auto-print only — shipment status** | Auto-print only fires when the shipment status is **Confirmed** (`N`) *and* Pick Status transitions to **Committed** (`C`). Manual print has no status requirement. |
| **`UsrBoxLabelPrinted` flag** | Open the shipment in SO302000. If the **Box Labels Printed** checkbox is already checked (`true`), the auto-print treated labels as already sent. The manual button ignores this flag and always reprints. |
| **Acumatica Trace Log** | Go to **SM205070** (Trace Log) and search for `[BoxLabel]` entries. Errors and warnings from the customization are logged with this prefix. |

### Duplicate labels are printing

The `UsrBoxLabelPrinted` flag prevents duplicates on re-save for the **auto-print path**. If duplicates occur:

1. Open the shipment in SO302000.
2. Check the **Box Labels Printed** field — if it reads `false` (unchecked) while labels have already printed, the flag may not have been saved (e.g., the session was interrupted after queuing but before the database commit).
3. If an external process or integration is repeatedly setting Pick Status to `C` → something else → `C`, that re-triggers the auto-print each time. Coordinate with the WMS team.
4. Note: clicking **Print Box Labels** manually always resets and reprints — this is by design for the manual path. Do not click it multiple times rapidly.

### Alternate ID (customer part number) is blank on the label

The label pulls the customer cross-reference from `INItemXRef`. If this column is blank:

1. Go to **IN202500** (Stock Items) for the affected item.
2. Open the **Cross-References** tab.
3. Add a cross-reference entry with **Type** = `Customer`, **Business Account** = the customer, and the customer's part number in the **Alternate ID** field.
4. Save. The next label printed for that item will show the Alternate ID.

### Box count is wrong (e.g., "Box 1 of 1" when there are multiple boxes)

The label reads the total package count from the packages already saved on the shipment at print time. The count will be wrong if packages were added after labels were printed.

**Resolution:** Make sure all boxes are added to the shipment (Packages tab on SO302000) **before** printing labels, then use **Actions → Print Box Labels** to reprint with the correct count.

---

## 9. Re-printing Labels

Use these steps when labels need to be re-printed — for example, after a printer jam, after correcting package contents, or after a wrong label was produced.

### Option A — Use the "Print Box Labels" Button (Recommended)

This is the fastest method and is available directly on the screen:

1. Open the shipment in **SO302000**.
2. Click **Actions → Print Box Labels**.
3. Labels for all packages are immediately re-queued to your Device Hub printer.
4. The `UsrBoxLabelPrinted` flag is automatically reset and then re-set to `true` after successful queuing.

> No need to manually uncheck the **Box Labels Printed** field — the button handles the reset internally.

### Option B — Reset the Flag and Re-trigger Auto-Print

This re-triggers the auto-print pipeline through the WMS workflow:

1. Open the shipment in **SO302000**.
2. Locate the **Box Labels Printed** field (visible on the shipment header).
3. Uncheck the checkbox to set it to `false`.
4. Save the shipment.
5. Ask your WMS team to toggle the Pick Status away from **Committed** and back to **Committed**. This re-triggers the auto-print gate check.

### Option C — Manually Run the Report

This prints labels immediately without touching the `UsrBoxLabelPrinted` flag:

1. Navigate to **SM208000** (Report Designer) or the Shipments screen print actions.
2. Select the report **`BoxLabel4x6`**.
3. Enter the parameters:
   - `ShipmentNbr` = the shipment number (e.g., `000123`)
   - `PackageLineNbr` = the specific package line to reprint (repeat for each box)
4. Choose the thermal printer and print.

### Option D — Reset the Flag via SQL (Admin / Emergency Use Only)

If the screen is inaccessible or a bulk reset is needed, a database administrator can run:

```sql
-- Reset the flag for a single shipment
UPDATE SOShipment
SET UsrBoxLabelPrinted = 0
WHERE ShipmentNbr = '000123';   -- replace with actual shipment number

-- Reset the flag for all unconfirmed shipments (bulk cleanup)
UPDATE SOShipment
SET UsrBoxLabelPrinted = 0
WHERE Status <> 'N';            -- non-Confirmed shipments
```

> ⚠️ Always take a backup before running manual SQL updates against the Acumatica database. Coordinate with your Acumatica partner before doing bulk resets in a production environment.

---

## 10. Code Architecture — Shared Print Method

Both print paths share the same private `ExecuteBoxLabelPrint()` method in `SOShipmentEntry_LabelAutoPrint`. This ensures identical Device Hub logic, parameter building, and error handling regardless of how printing is triggered.

```
RowUpdated (auto-print)          printBoxLabels action (manual)
        │                                   │
        │ isManualAction = false             │ isManualAction = true
        └─────────────┬─────────────────────┘
                      ▼
          ExecuteBoxLabelPrint()
          ┌─────────────────────────────────────────┐
          │ 1. Query SOPackageDetailEx for shipment  │
          │ 2. Resolve printer from UserPreferences  │
          │ 3. QueueSingleLabelJob() per package     │
          │    └─ SMPrintJobMaint.PrintJob.Insert()  │
          │    └─ AttachReportParameter() x2         │
          │    └─ SMPrintJobMaint.Actions.PressSave()│
          │ 4. SetValueExt UsrBoxLabelPrinted = true │
          │ 5a. [auto] PXTrace.WriteInformation      │
          │ 5b. [manual] RaiseExceptionHandling msg  │
          └─────────────────────────────────────────┘
```

**Key behavioral differences between paths:**

| Behaviour | Auto-Print (`isManualAction = false`) | Manual Button (`isManualAction = true`) |
|-----------|--------------------------------------|-----------------------------------------|
| Success feedback | Silent (PXTrace only) | Green confirmation banner on screen |
| No-packages error | PXTrace warning, returns silently | `PXException` shown to user |
| No-printer error | Warning banner, returns silently | `PXException` shown to user |
| All-jobs-failed error | Warning banner, returns silently | `PXException` shown to user |
| Unexpected exception | PXTrace + warning banner; **never throws** (protects WMS workflow) | Re-throws as `PXException` |
| PressSave after print | No (handled by normal shipment save) | Yes (explicit call in action handler) |

---

## 10. Post-Deploy Verification

After publishing the `ShipmentLabelAutoPrint` customization project to any Acumatica instance, run the included smoke test to confirm that every required component is in place:

```bash
python scripts/test-box-label.py \
    --url      https://instance.acumatica.com \
    --username admin \
    --password secret \
    --tenant   MyTenant
```

Or set environment variables and run without flags:

```bash
export ACUMATICA_URL=https://instance.acumatica.com
export ACUMATICA_USERNAME=admin
export ACUMATICA_PASSWORD=secret
export ACUMATICA_TENANT=MyTenant
python scripts/test-box-label.py
```

### What the smoke test checks

| Check | What it tests | Failure indicates |
|-------|--------------|-------------------|
| **1. Authentication** | Login to the Acumatica instance | Wrong credentials / unreachable instance |
| **2. Entity reachability** | `GET /Shipment` returns HTTP 200 (not 500) | Graph extension compile error in `SOShipmentEntry_LabelAutoPrint` |
| **3. DAC schema** | `UsrBoxLabelPrinted` in `Shipment/$adHocSchema` (informational) | DAC extension not registered *(WARN only — field is SQL-only by design)* |
| **4. SQL column** | `$expand=custom` query succeeds without column-missing error | `ShipmentLabelSchemaInstaller` did not run; column missing from `SOShipment` |
| **5. Package data** | `$expand=Packages` query on confirmed shipments succeeds | REST API version mismatch *(WARN only — C# uses PXSelect directly)* |
| **6. Field access** | Single shipment retrieval does not 500 | Graph extension is broken at runtime |
| **7. Device Hub config** | *(Informational reminder — always WARN, never FAIL)* | Check manually per §3 of this document |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All required checks passed (warnings are allowed) |
| `1` | One or more **FAIL** checks — deployment is not complete |

### CI/CD integration

The smoke test can be added as a post-deploy step in the GitHub Actions workflow. Add it after the deploy step in `.github/workflows/deploy-customization.yml`:

```yaml
- name: Box-label smoke test
  env:
    ACUMATICA_URL:      ${{ secrets.ACUMATICA_PROD_URL }}
    ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
    ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
    ACUMATICA_TENANT:   ${{ secrets.ACUMATICA_PROD_TENANT }}
  run: |
    python scripts/test-box-label.py --skip-device-hub
```

> **`--skip-device-hub`** suppresses the Device Hub reminder (Check 7) in CI output, since it cannot be automated and would always appear as a warning, cluttering the log. Run without the flag for a first-time environment audit.

---

## Quick Reference

| Topic | Location |
|-------|----------|
| **Manual Print Box Labels button** | SO302000 → Actions menu |
| **Post-deploy smoke test** | `scripts/test-box-label.py` |
| Device Hub Printers | SM206530 |
| User Preferences (printer assignment) | SM202010 |
| Shipments screen | SO302000 |
| Report Designer | SM208000 |
| Trace Log | SM205070 |
| Stock Item Cross-References | IN202500 → Cross-References tab |
| Report file (data linkage) | `Customization/_project/BoxLabel4x6.rpx` |
| Customization source | `Customization/_project/ShipmentLabelAutoPrint.cs` |
| DB column validated by | `publish-manifest.json` → `sql_columns` → `SOShipment.UsrBoxLabelPrinted` |
