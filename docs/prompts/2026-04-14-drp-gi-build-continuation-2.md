# DRP GI Build — Continuation Prompt #2 (2026-04-14)

## Context

Building 3 DRP Generic Inquiries on Heritage Fabrics production via browser automation of SM208000. This is the second continuation — the first continuation prompt is at `docs/prompts/2026-04-14-drp-gi-build-continuation.md` and contains the full spec for all 3 GIs plus the Playwright automation pattern.

## What's Done

### DRP_InventoryBySite — SAVED ✅
- Data Sources: InventoryItem, INSiteStatus
- Relation: InventoryItem LEFT JOIN INSiteStatus ON InventoryID
- Conditions: StkItem=True AND (ItemStatus=AC OR ItemStatus=NS)
- Sort Order: InventoryItem.InventoryCD ASC, INSiteStatus.SiteID ASC
- Results Grid: 9 fields (InventoryCD, Descr, ItemStatus, ItemClassID, SiteID, QtyOnHand, QtyAvail, QtyHardAvail, QtyAllocated)
- **Note:** QtyAllocated has a ⚠ warning — may not exist on INSiteStatus DAC. Verify after publish.

### DRP_OpenSOCommitments — SAVED (partially) ⚠
- Data Sources: SOLine (alias SOLine), SOOrder (alias SOOrder) ✅
- Relation: SOLine LEFT JOIN SOOrder ON OrderType + OrderNbr ✅
- Conditions: 5 rows ✅
  1. SOLine.LineType Equals GI — And
  2. SOLine.OpenQty Is Greater Than 0 — And
  3. ( SOLine.OrderType Equals SO — Or
  4. SOLine.OrderType Equals CO — Or
  5. SOLine.OrderType Equals PC ) — And
- Sort Order: SOLine.RequestDate ASC ✅
- Results Grid: **1 of 11 fields done** (SOLine.InventoryID only)
  - Still need to add: OrderType, OrderNbr, LineNbr, OrderQty, ShippedQty, OpenQty, RequestDate (all SOLine), CustomerID (SOOrder), SiteID, UOM (SOLine)

### DRP_OpenPOLines — NOT STARTED
- Full spec in first continuation prompt

## What Needs To Be Done

### 1. Finish DRP_OpenSOCommitments Results Grid
Navigate to SM208000, load DRP_OpenSOCommitments. Go to RESULTS GRID tab. Add these 10 fields (Object | Data Field):

| # | Object | Data Field |
|---|--------|-----------|
| 2 | SOLine | OrderType |
| 3 | SOLine | OrderNbr |
| 4 | SOLine | LineNbr |
| 5 | SOLine | OrderQty |
| 6 | SOLine | ShippedQty |
| 7 | SOLine | OpenQty |
| 8 | SOLine | RequestDate |
| 9 | SOOrder | CustomerID |
| 10 | SOLine | SiteID |
| 11 | SOLine | UOM |

Note: Row 9 (CustomerID) needs Object changed to SOOrder. All others stay as SOLine.

Save after adding all fields.

### 2. Build DRP_OpenPOLines (full GI from scratch)

#### Data Sources
| Source Name | Alias |
|------------|-------|
| PX.Objects.PO.POLine | POLine |
| PX.Objects.PO.POOrder | POOrder |

#### Relations
POLine LEFT JOIN POOrder:
- POLine.OrderType = POOrder.OrderType
- POLine.OrderNbr = POOrder.OrderNbr

#### Conditions
| Open Br | Data Field | Condition | Value 1 | Close Br | Operator |
|---------|-----------|-----------|---------|----------|----------|
| | POLine.LineType | Equals | GI | | And |
| | POLine.OpenQty | Is Greater Than | 0 | | And |
| ( | POOrder.Status | Equals | N | | Or |
| | POOrder.Status | Equals | O | ) | And |

#### Results Grid (11 fields)
| # | Object | Data Field |
|---|--------|-----------|
| 1 | POLine | OrderNbr |
| 2 | POLine | LineNbr |
| 3 | POLine | InventoryID |
| 4 | POOrder | VendorID |
| 5 | POLine | OrderQty |
| 6 | POLine | ReceivedQty |
| 7 | POLine | OpenQty |
| 8 | POOrder | OrderDate |
| 9 | POLine | PromisedDate |
| 10 | POLine | SiteID |
| 11 | POLine | UOM |

#### Sort Order
POLine.PromisedDate — Ascending

Save after complete.

### 3. Publish All GIs & Enable OData

For each of the 3 GIs (DRP_InventoryBySite, DRP_OpenSOCommitments, DRP_OpenPOLines):
1. Load in SM208000
2. Click PUBLISH TO THE UI
3. Check "Expose via OData" checkbox
4. Save (Ctrl+S)

### 4. Verify OData

```bash
for gi in DRP_InventoryBySite DRP_OpenSOCommitments DRP_OpenPOLines; do
  curl -s -o /dev/null -w "$gi: HTTP %{http_code}\n" \
    -H "Authorization: Basic $(echo -n 'api-bot:pedhek-hugpid-4Gokge' | base64)" \
    "https://heritagefabrics.acumatica.com/odata/Heritage%20Fabrics/${gi}?\$top=1"
done
```

## SM208000 Browser Pattern (quick reference)

- **Add row:** Click "+" button in grid toolbar
- **Set field:** Double-click cell → type value → Tab to commit
- **Object dropdown:** Double-click Object cell → select from dropdown
- **Condition dropdown:** Double-click → click dropdown arrow → select
- **Brackets:** Double-click Brackets cell → select from dropdown (watch for `((` vs `(`)
- **Close Brackets column** is narrow — click precisely to the RIGHT of Value 2, LEFT of Operator
- **Avoid clicking the pencil icon** next to Value 2 — it opens a formula editor dialog
- **Save:** Click floppy disk icon in main toolbar (not Ctrl+S which may not work consistently)
- **After save:** URL gets `&Name=GI_NAME` and VIEW INQUIRY button appears
