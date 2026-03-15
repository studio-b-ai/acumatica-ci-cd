# Auto Print Box Label — Device Hub Setup Guide

**Platform:** Heritage Fabrics / Studio B — Acumatica 24.208  
**Customization Project:** `ShipmentLabelAutoPrint`  
**Last Updated:** 2025

---

## 1. Overview

When a shipment's **Kensium WMS Pick Status** is set to **Committed** (`C`) and the shipment is in **Confirmed** status, box labels are automatically sent to the warehouse thermal printer via **Acumatica Device Hub** — no manual button press required.

**One label is printed per package** on the shipment (`SOPackageDetailEx` rows). The system queues a separate Device Hub print job for each package, targeting the `BoxLabel4x6` report.

### How It Works (Summary)

1. A warehouse user (or the WMS integration) sets the shipment's Pick Status to **Committed** on the Shipments screen (SO302000).
2. The `SOShipmentEntry_LabelAutoPrint` graph extension detects the status transition.
3. It verifies the shipment is in **Confirmed** status (`N`) and that labels have not already been printed for this shipment (idempotency guard).
4. One `SMPrintJob` record is created per package, carrying `ShipmentNbr` and `PackageLineNbr` as report parameters.
5. Device Hub picks up the queued jobs and dispatches them to the configured thermal printer.
6. The `UsrBoxLabelPrinted` flag on the shipment is set to `true` to prevent duplicate prints on subsequent saves.

> **Note:** The printer used is the **Device Hub printer configured in the current user's Acumatica User Preferences** (SM202010 → Printer Name). Each user who triggers a label print must have a printer assigned there.

---

## 2. Prerequisites

Before the feature will work, confirm all of the following are in place:

| # | Requirement | Notes |
|---|-------------|-------|
| 1 | **Acumatica Device Hub** installed and running on the warehouse print server | The Windows service must be running and connected to the Acumatica instance |
| 2 | **4×6 thermal label printer** connected and configured on the print server | Tested with Zebra ZD420, ZT230; any 4×6 thermal printer with a Windows driver is supported |
| 3 | **`BoxLabel4x6.rpx` report** published to the Acumatica instance | The report must be registered in Report Designer (SM208000) with Report ID `BoxLabel4x6` exactly — the code matches this ID case-sensitively |
| 4 | **`ShipmentLabelAutoPrint` customization project** published | Deploys `SOShipmentLabelExt` (DAC), `SOShipmentEntry_LabelAutoPrint` (graph extension), and `ShipmentLabelSchemaInstaller` (adds `UsrBoxLabelPrinted` column to `SOShipment`) |
| 5 | **`UsrBoxLabelPrinted` column** present on the `SOShipment` SQL table | Created automatically on first publish by `ShipmentLabelSchemaInstaller`. Verify via `validate-publish.py` (`sql_columns` check) |
| 6 | **Kensium WMS** installed and the `UsrFRPickStatus` field present on shipments | The extension reads this field by name at runtime; if absent, the trigger simply never fires |

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

Each warehouse user who may trigger label printing must have a printer assigned in their personal preferences:

1. Go to **User Preferences** — screen **SM202010** — (or the user icon → Preferences).
2. In the **Printer Name** field, select the thermal label printer.
3. Save.

> **This is the printer the auto-print code uses.** If no printer is set for the logged-in user, labels will not be queued, and a yellow warning banner will appear on the Shipments screen.

---

## 4. Report Parameters

The `BoxLabel4x6` report accepts exactly two parameters. These are automatically populated by the customization code — no manual entry is needed during normal operation.

| Parameter | Type | Description |
|-----------|------|-------------|
| `ShipmentNbr` | String | The shipment number (e.g., `000123`) — identifies which shipment to print |
| `PackageLineNbr` | Integer | The line number of the specific package within the shipment — drives the "Box X of X" display |

These same parameters can be used when **manually re-running** the report from the Report Designer or the Shipments screen.

---

## 5. Label Layout

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

## 6. Troubleshooting

### Labels are not printing at all

| Check | Action |
|-------|--------|
| **Device Hub service** | On the print server, open Windows Services and confirm `Acumatica Device Hub` is **Running**. Restart it if needed. |
| **User printer setting** | Go to SM202010 for the user who confirmed the shipment. Confirm a printer is assigned in the **Printer Name** field. Without this, the code logs a warning and skips queuing. |
| **Printer mapping** | In SM206530, confirm `BoxLabel4x6` is mapped to the thermal printer and the printer is **Active**. |
| **Shipment status** | Labels only trigger when the shipment status is **Confirmed** (`N`) *and* Pick Status transitions to **Committed** (`C`). If the shipment is still Open or already Completed, no labels will fire. |
| **`UsrBoxLabelPrinted` flag** | Open the shipment in SO302000. If the **Box Labels Printed** checkbox is already checked (`true`), the system treated labels as already sent. See [Re-printing Labels](#7-re-printing-labels). |
| **Acumatica Trace Log** | Go to **SM205070** (Trace Log) and search for `[BoxLabel]` entries. Errors and warnings from the customization are logged with this prefix. |

### Duplicate labels are printing

The `UsrBoxLabelPrinted` flag prevents duplicates on re-save. If duplicates occur:

1. Open the shipment in SO302000.
2. Check the **Box Labels Printed** field — if it reads `false` (unchecked) while labels have already printed, the flag may not have been saved (e.g., the session was interrupted after queuing but before the database commit).
3. If duplicates continue, check whether an external process or integration is repeatedly setting Pick Status to `C` → something else → `C`, which would re-trigger the auto-print each time. Coordinate with the WMS team.

### Alternate ID (customer part number) is blank on the label

The label pulls the customer cross-reference from `INItemXRef`. If this column is blank:

1. Go to **IN202500** (Stock Items) for the affected item.
2. Open the **Cross-References** tab.
3. Add a cross-reference entry with **Type** = `Customer`, **Business Account** = the customer, and the customer's part number in the **Alternate ID** field.
4. Save. The next label printed for that item will show the Alternate ID.

### Box count is wrong (e.g., "Box 1 of 1" when there are multiple boxes)

The label reads the total package count from the packages already saved on the shipment at print time. The count will be wrong if packages were added after labels were printed, or if packages were not yet added when the Pick Status was set to Committed.

**Resolution:** Make sure all boxes are added to the shipment (Packages tab on SO302000) **before** setting the Pick Status to Committed, or re-print labels after the final package count is set (see below).

---

## 7. Re-printing Labels

Use these steps when labels need to be re-printed — for example, after a printer jam, after correcting package contents, or after a wrong label was produced.

### Option A — Reset the Flag and Re-save (Recommended)

This re-triggers the auto-print pipeline through the normal workflow:

1. Open the shipment in **SO302000**.
2. Locate the **Box Labels Printed** field (visible on the shipment header; field name `UsrBoxLabelPrinted`).
3. Uncheck the checkbox to set it to `false`.
4. Save the shipment.
5. If the Pick Status is already **Committed** and the shipment is still **Confirmed**, you can now re-trigger printing by making any minor edit and saving — or ask your system administrator to toggle the Pick Status to a different value and back to **Committed**.

> If the **Box Labels Printed** field is not visible on the screen layout, an administrator can add it via the screen editor, or use Option B below.

### Option B — Manually Run the Report

This prints labels immediately without touching the `UsrBoxLabelPrinted` flag:

1. Navigate to **SM208000** (Report Designer) or the Shipments screen print actions.
2. Select the report **`BoxLabel4x6`**.
3. Enter the parameters:
   - `ShipmentNbr` = the shipment number (e.g., `000123`)
   - `PackageLineNbr` = the specific package line to reprint (repeat for each box)
4. Choose the thermal printer and print.

### Option C — Reset the Flag via SQL (Admin / Emergency Use Only)

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

## Quick Reference

| Topic | Location |
|-------|----------|
| Device Hub Printers | SM206530 |
| User Preferences (printer assignment) | SM202010 |
| Shipments screen | SO302000 |
| Report Designer | SM208000 |
| Trace Log | SM205070 |
| Stock Item Cross-References | IN202500 → Cross-References tab |
| Customization source | `Customization/_project/ShipmentLabelAutoPrint.cs` |
| DB column validated by | `publish-manifest.json` → `sql_columns` → `SOShipment.UsrBoxLabelPrinted` |
