# Container Tracking Feature Parity — Design

**Date:** 2026-04-04
**Status:** Approved
**Prereq:** AesthetikContainers deployed, IIG unpublished, CleanupIGCMArtifacts run (PRs #154-159)

## Overview

Build 5 user-facing screens (3 GIs + 1 ASPX + 1 GI) to replace the 10 missing IIG Container Management screens. Phase 1 covers critical UI; Phases 2-3 (webhooks, master data) deferred.

## Deliverables

### 1. PO Containers GI (SB401000) — replaces IG.CM.01.02

**Purpose:** Browse active containers with linked PO counts, ETAs, delay visibility.

| Attribute | Value |
|-----------|-------|
| Screen ID | `SB401000` |
| Type | Generic Inquiry |
| Build method | gi_builder.py → CustomizationPlugin SQL |
| Data sources | `UsrContainer` LEFT JOIN `UsrContainerPOLink` (aggregate PO count) |

**Columns:**

| # | Field | Source | Caption | Width |
|---|-------|--------|---------|-------|
| 1 | ContainerCD | UsrContainer | Container | 120 |
| 2 | Status | UsrContainer | Status | 100 |
| 3 | CarrierCode | UsrContainer | Carrier | 100 |
| 4 | VesselName | UsrContainer | Vessel | 150 |
| 5 | PortOfLoading | UsrContainer | Origin | 120 |
| 6 | PortOfDischarge | UsrContainer | Destination | 120 |
| 7 | ETD | UsrContainer | ETD | 100 |
| 8 | ETA | UsrContainer | ETA | 100 |
| 9 | ATA | UsrContainer | ATA | 100 |
| 10 | COUNT(LinkID) | UsrContainerPOLink | PO Count | 80 |

**Filters:** Status (dropdown), CarrierCode, ETA date range
**Sort:** ETA DESC
**Navigation:** Row click → SB501000 (Container Maintenance)

---

### 2. SO Containers GI (SB401010) — replaces IG.CM.01.04

**Purpose:** Outbound shipment container visibility.

| Attribute | Value |
|-----------|-------|
| Screen ID | `SB401010` |
| Type | Generic Inquiry |
| Data sources | `SOShipment` with ShipmentExt cache extension |

**Columns:**

| # | Field | Source | Caption | Width |
|---|-------|--------|---------|-------|
| 1 | ShipmentNbr | SOShipment | Shipment | 120 |
| 2 | Status | SOShipment | Status | 100 |
| 3 | CustomerID | SOShipment | Customer | 120 |
| 4 | ShipDate | SOShipment | Ship Date | 100 |
| 5 | UsrContainerID | ShipmentExt | Container | 120 |
| 6 | UsrIncludeInContainer | ShipmentExt | In Container | 80 |

**Filters:** UsrIncludeInContainer = true (default), Status
**Sort:** ShipDate DESC

---

### 3. Container Events GI (SB401020) — replaces IG.CM.01.06

**Purpose:** Tracking event timeline across all containers.

| Attribute | Value |
|-----------|-------|
| Screen ID | `SB401020` |
| Type | Generic Inquiry |
| Data sources | `UsrContainerEvent` JOIN `UsrContainer` (for ContainerCD) |

**Columns:**

| # | Field | Source | Caption | Width |
|---|-------|--------|---------|-------|
| 1 | ContainerCD | UsrContainer | Container | 120 |
| 2 | EventDateTime | UsrContainerEvent | Date/Time | 150 |
| 3 | NormalizedEventCode | UsrContainerEvent | Event | 120 |
| 4 | EventClassifier | UsrContainerEvent | Type | 80 |
| 5 | LocationName | UsrContainerEvent | Location | 150 |
| 6 | VesselName | UsrContainerEvent | Vessel | 120 |
| 7 | Description | UsrContainerEvent | Description | 200 |

**Filters:** ContainerCD, NormalizedEventCode, EventDateTime date range
**Sort:** EventDateTime DESC

---

### 4. Freight Forwarders ASPX (SB302000) — replaces IG.CM.30.91

**Purpose:** Carrier/forwarder master data + API configuration.

| Attribute | Value |
|-----------|-------|
| Screen ID | `SB302000` |
| Type | ASPX form (maintenance) |
| Graph | `FreightForwarderMaint` |
| DAC | `UsrFreightForwarder` (new) |

**New table: `UsrFreightForwarder`**

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| CompanyID | int | NO | Multi-tenant key (DEFAULT 0) |
| ForwarderID | int IDENTITY | NO | PK |
| ForwarderCD | nvarchar(15) | NO | Natural key |
| Name | nvarchar(100) | NO | Company name |
| ContactName | nvarchar(100) | YES | Primary contact |
| Phone | nvarchar(30) | YES | Phone |
| Email | nvarchar(100) | YES | Email |
| Website | nvarchar(200) | YES | Website URL |
| CarrierAPIType | nvarchar(20) | YES | SEATRATES, MAERSK, FEDEX, UPS, OTHER |
| CarrierAPIKey | nvarchar(200) | YES | Encrypted API key |
| Active | bit | NO | DEFAULT 1 |
| NoteID | uniqueidentifier | YES | Acumatica notes |
| CreatedByID | uniqueidentifier | YES | Audit |
| CreatedByScreenID | char(8) | YES | Audit |
| CreatedDateTime | datetime | YES | Audit |
| LastModifiedByID | uniqueidentifier | YES | Audit |
| LastModifiedByScreenID | char(8) | YES | Audit |
| LastModifiedDateTime | datetime | YES | Audit |
| tstamp | timestamp | NO | Concurrency |

**PK:** (CompanyID, ForwarderID)
**Index:** IX_UsrFreightForwarder_CD (CompanyID, ForwarderCD) UNIQUE

**ASPX layout:** Standard form — ForwarderCD selector at top, form body with Name, Contact, Phone, Email, Website, CarrierAPIType dropdown, Active checkbox.

---

### 5. Custom Classification GI (SB401030) — replaces IG.CM.30.93

**Purpose:** View/filter stock items by customs classification fields.

| Attribute | Value |
|-----------|-------|
| Screen ID | `SB401030` |
| Type | Generic Inquiry |
| Data sources | `InventoryItem` with StockItemExt fields |

**Columns:**

| # | Field | Source | Caption | Width |
|---|-------|--------|---------|-------|
| 1 | InventoryCD | InventoryItem | Item ID | 120 |
| 2 | Descr | InventoryItem | Description | 200 |
| 3 | ItemClassID | InventoryItem | Item Class | 120 |
| 4 | UsrFiberContent | StockItemExt | Fiber Content | 150 |
| 5 | UsrDutyRate | StockItemExt | Duty Rate | 100 |
| 6 | UsrPreferentialTariff | StockItemExt | Pref. Tariff | 100 |
| 7 | UsrFreightClass | StockItemExt | Freight Class | 100 |

**Filters:** ItemClassID, has duty rate (NOT NULL), FreightClass
**Sort:** InventoryCD ASC
**Navigation:** Row click → IN202500 (Stock Items)

---

## SiteMap Registration

All 5 screens registered under "Container Tracking" workspace via SQL in CustomizationPlugin:

```
Container Tracking (workspace)
├── Container Maintenance (SB501000) — existing
├── PO Containers (SB401000) — new GI
├── SO Containers (SB401010) — new GI
├── Container Events (SB401020) — new GI
├── Freight Forwarders (SB302000) — new ASPX
└── Custom Classification (SB401030) — new GI
```

## Playwright Tests

Each screen gets 2-3 tests in `tests/ui/test_container_tracking.py`:

| Screen | Tests |
|--------|-------|
| SB401000 (PO Containers GI) | Loads without error, grid has columns, status filter works |
| SB401010 (SO Containers GI) | Loads without error, grid visible |
| SB401020 (Container Events GI) | Loads without error, grid visible, date sort correct |
| SB302000 (Freight Forwarders) | Loads without error, form fields visible, new record button works |
| SB401030 (Classification GI) | Loads without error, grid visible, item class filter works |
| Workspace | All 6 screens appear in sidebar |

## End-User Guide

A formatted migration guide will be produced as the final deliverable:
- IIG screen → AesthetikContainers screen mapping
- What changed, what's new, what's gone
- Navigation instructions for each screen
- Suitable for distribution to Heritage Fabrics team

## Out of Scope (Phase 2-3)

- Webhook integration / carrier event ingestion
- Container Types / Destinations / Preferences master screens
- PO Container Lines detail GI
- Distribution analytics
- Duty/Tariff by Container GI
