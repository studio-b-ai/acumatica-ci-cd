# Container Tracking Phase 2 & 3 — Design

**Date:** 2026-04-04
**Status:** Approved
**Prereq:** Phase 1 complete (PR #162 merged — 5 screens). AesthetikContainers publish pending.

## Phase 2: Push-Based Container Events + Enable Worker

### What Already Exists (webhook-router)

The `container-tracking` worker is fully implemented:
- `src/workers/container-tracking.ts` — BullMQ worker with carrier polling, event normalization
- `src/lib/acumatica-containers.ts` — Full CRUD: getActiveContainers, upsertContainer, writeNewEvents, autoLinkPOs
- `src/routes/carrier-webhooks.ts` — CHR and OTS webhook receivers
- `src/routes/track-container.ts` — Manual enrollment endpoint
- Event normalization: carrier-specific codes → standard (BOOKED, DEPARTED, IN_TRANSIT, ARRIVED, etc.)
- ETA/ATA propagation to PO headers via `updatePODate()`
- Feature-flagged: `CONTAINER_TABLE_TRACKING_ENABLED`

### What Needs to Change

#### 2a. Push Instead of Poll

Current: 4-hour cron polling. Desired: push on container save.

**Approach:** Acumatica `ContainerMaint.Persist()` override fires HTTP POST to webhook-router after save. The worker then re-queries the carrier API for the latest events.

- Add webhook endpoint: `POST /webhook/acumatica/container-update` on webhook-router
- Modify `ContainerMaint.Persist()` to POST container data after successful save
- Worker receives push, looks up carrier, queries for events, writes to UsrContainerEvent, propagates dates
- Keep daily poll as fallback safety net (reduce from 4h to 24h)

#### 2b. Enable the Worker

- Set `CONTAINER_TABLE_TRACKING_ENABLED=true` in Railway env vars
- Verify carrier registry configuration (CHR API key, OTS credentials)
- Test carrier API connectivity

#### 2c. E2E Verification

- Create container in SB501000
- Trigger tracking via RefreshTracking button or container save
- Verify events appear in Events tab (SB401020 GI)
- Verify PO dates update on linked POs

---

## Phase 3: Master Data Screens (4 screens)

### 3a. PO Container Lines GI (SB401040)

**Purpose:** Detail view showing which PO lines are on which containers.

| Attribute | Value |
|-----------|-------|
| Screen ID | `SB401040` |
| Type | Generic Inquiry |
| Build method | gi_builder.py → CustomizationPlugin SQL |
| Data sources | `UsrContainerPOLink` JOIN `UsrContainer` JOIN `POOrder` JOIN `POLine` JOIN `InventoryItem` |

**Columns:**

| # | Field | Source | Caption | Width |
|---|-------|--------|---------|-------|
| 1 | ContainerCD | UsrContainer | Container | 120 |
| 2 | Status | UsrContainer | Status | 100 |
| 3 | ETA | UsrContainer | ETA | 100 |
| 4 | OrderType | UsrContainerPOLink | Type | 60 |
| 5 | OrderNbr | UsrContainerPOLink | PO Nbr | 120 |
| 6 | LineNbr | UsrContainerPOLink | Line | 60 |
| 7 | InventoryCD | InventoryItem | Item | 120 |
| 8 | OrderQty | POLine | Qty | 80 |
| 9 | UnitPrice | POLine | Price | 80 |

**Filters:** ContainerCD, OrderNbr
**Sort:** ContainerCD ASC, OrderNbr ASC

---

### 3b. Container Types (SB302010)

**Purpose:** Master table for container size types (replaces hardcoded enum).

**New DAC: `UsrContainerType`**

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| CompanyID | int | NO | DEFAULT 0 |
| ContainerTypeID | int IDENTITY | NO | PK |
| TypeCD | nvarchar(10) | NO | Natural key (20GP, 40HC, etc.) |
| Description | nvarchar(60) | YES | Full name |
| LengthFt | decimal(6,1) | YES | Length in feet |
| WidthFt | decimal(6,1) | YES | Width in feet |
| HeightFt | decimal(6,1) | YES | Height in feet |
| MaxWeightKg | decimal(10,0) | YES | Max gross weight |
| Active | bit | NO | DEFAULT 1 |
| NoteID, audit, tstamp | — | — | Standard |

**Seed data:** 20GP (20'), 40GP (40'), 40HC (40' high-cube), 45HC (45' high-cube), 20RF (20' reefer), 40RF (40' reefer)

**DAC change:** `UsrContainer.ContainerType` changes from `PXStringList` to `PXSelector` referencing `UsrContainerType.typeCD`

**Screen:** Simple FormView maintenance (SB302010.aspx)

---

### 3c. Destinations/Ports (SB302020)

**Purpose:** Port master table using UN/LOCODE format.

**New DAC: `UsrPort`**

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| CompanyID | int | NO | DEFAULT 0 |
| PortID | int IDENTITY | NO | PK |
| PortCode | nvarchar(10) | NO | Natural key (UN/LOCODE: CNSHA, USLAX, etc.) |
| PortName | nvarchar(100) | NO | Full name |
| Country | nvarchar(2) | YES | ISO country code |
| Active | bit | NO | DEFAULT 1 |
| NoteID, audit, tstamp | — | — | Standard |

**Seed data:** ~20 ports Heritage uses most (CNSHA, CNYTN, CNNGB, USLAX, USLGB, USSAV, USNYC, USNWK, USCHI, etc.)

**DAC change:** `UsrContainer.PortOfLoading` and `PortOfDischarge` change from free-text `PXDBString` to `PXSelector` referencing `UsrPort.portCode`

**Screen:** Simple FormView maintenance (SB302020.aspx)

---

### 3d. Container Preferences (SB302030)

**Purpose:** Single-record settings for the container tracking module.

**New DAC: `UsrContainerPrefs`**

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| CompanyID | int | NO | DEFAULT 0 |
| PrefsID | int | NO | DEFAULT 1 (single record) |
| DefaultCarrierCode | nvarchar(20) | YES | Default carrier for new containers |
| DefaultContainerType | nvarchar(10) | YES | FK → UsrContainerType |
| DefaultInTransitWarehouse | nvarchar(30) | YES | Warehouse for in-transit inventory |
| AutoLinkPOsByRef | bit | NO | DEFAULT 1 — auto-link POs by ContainerRef |
| TrackingPollIntervalHours | int | NO | DEFAULT 24 — fallback poll frequency |
| NoteID, audit, tstamp | — | — | Standard |

**Screen:** Single-record FormView (SB302030.aspx) — like Acumatica preferences screens

---

## SiteMap Registration

All 4 new screens under "Container Tracking" workspace:

```
Container Tracking (workspace)
├── Container Maintenance (SB501000) — existing
├── PO Containers (SB401000) — Phase 1
├── SO Containers (SB401010) — Phase 1
├── Container Events (SB401020) — Phase 1
├── Freight Forwarders (SB302000) — Phase 1
├── Custom Classification (SB401030) — Phase 1
├── PO Container Lines (SB401040) — Phase 3 NEW
├── Container Types (SB302010) — Phase 3 NEW
├── Destinations/Ports (SB302020) — Phase 3 NEW
└── Container Preferences (SB302030) — Phase 3 NEW
```

## Playwright Tests

Same pattern as Phase 1 — each screen gets load + content tests with pre-publish skip logic.

## Out of Scope

- Distribution analytics GI (deferred)
- Duty/Tariff by Container GI (deferred)
- Seatrates carrier adapter (future — CHR and OTS already exist)
