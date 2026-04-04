# Container Tracking Gap Analysis — IIG vs AesthetikContainers

**Date:** 2026-04-04
**Status:** AesthetikContainers covers ~40% of IIG functionality (data layer complete, UI missing)

## Executive Summary

AesthetikContainers has the full data layer but is missing 10 of 15 user-facing screens and webhook integration. The IIG ISV has been unpublished and all artifacts cleaned up (PRs #154-159).

## What AesthetikContainers Provides

- UsrContainer DAC (vessel, ETD/ETA/ATA, carrier, booking ref, BOL)
- UsrContainerEvent DAC (timestamped events with location, vessel, raw payload)
- UsrContainerPOLink DAC (maps containers to PO headers/lines)
- POOrderExt: UsrExpArrivalDate, UsrActArrivalDate, UsrContainerRef
- POLineExt: UsrExpArrivalDate, UsrActArrivalDate, UsrQtyOnContainers (virtual)
- POReceiptLineExt: UsrActualDutyAmt, UsrActualFreightAmt, UsrBrokerageAmt, UsrLandedCostPerUnit
- StockItemExt: UsrFiberContent, UsrDutyRate, UsrPreferentialTariff, UsrFreightClass
- ShipmentExt: UsrIncludeInContainer, UsrContainerID
- ContainerDatePropagation (propagates ETA to linked POs on save)
- SB501000 (Container Maintenance — form + Events tab + PO Links tab)
- CONTAINER TRACKING button on PO301000

## Gap Analysis

| IIG Screen | Name | Type | Priority | Action | AesthetikContainers Status |
|-----------|------|------|----------|--------|--------------------------|
| IG.CM.01.02 | PO Containers | GI | CRITICAL | BUILD | UsrContainer DAC exists, no GI |
| IG.CM.01.04 | SO Containers | GI | CRITICAL | BUILD | ShipmentExt exists, no GI |
| IG.CM.01.06 | Container Events | GI | CRITICAL | BUILD | UsrContainerEvent DAC exists, no GI |
| IG.CM.30.91 | Freight Forwarders | ASPX | CRITICAL | BUILD | No DAC or UI |
| IG.CM.30.93 | Custom Classification | ASPX | CRITICAL | BUILD | StockItemExt exists, no UI |
| IG.CM.00.09 | PO Container Lines | GI | USEFUL | BUILD | UsrContainerPOLink exists, no GI |
| IG.CM.10.10 | Container Preferences | ASPX | USEFUL | BUILD | No config UI |
| IG.CM.20.92 | Container Types | ASPX | USEFUL | BUILD | No master table |
| IG.CM.20.94 | Destinations/Ports | ASPX | USEFUL | BUILD | No master table |
| IG.CM.20.96 | PO Container Statuses | ASPX | USEFUL | BUILD | Hardcoded enum, no master |
| IG.CM.30.94 | SO Containers (form) | ASPX | CRITICAL | BUILD | ShipmentExt exists, no form |
| IG.CM.20.93 | Logistics Services | ASPX | USEFUL | BUILD | No master table |
| IG.CM.10.99 | Classification Origin | ASPX | USEFUL | BUILD | No DAC |
| IG.CM.30.95 | SO Container Statuses | ASPX | USEFUL | BUILD | No master table |
| IG.CM.01.03 | Container Distributions | GI | LOW | DEFER | Analytics; not blocking |
| IG.CM.05.91 | Duty/Tariff by Container | GI | LOW | DEFER | Can query via SQL initially |
| IG.CM.20.95 | Customer Payment Statuses | ASPX | LOW | SKIP | Rarely changed; hardcode |
| IG.CM.20.97 | Duty/Tariff Prefs | ASPX | LOW | DEFER | Advanced config |

## Webhook Router Integration Gap

**Current state:** RefreshTracking action on SB501000 is a placeholder. No carrier event ingestion exists.

**Required:**
1. `container-event-worker.ts` in webhook-router (BullMQ)
2. Webhook schema for Seatrates/carrier payloads
3. Event normalization mapping (carrier-specific -> standard codes: DEP, ARR, CLR, DLV)
4. Upsert UsrContainerEvent on each webhook
5. Update UsrContainer.ETA/ATA/Status on arrival/delivery events
6. Trigger ContainerDatePropagation to update linked POs

## Technical Debt

| Issue | Risk | Mitigation |
|-------|------|-----------|
| Hardcoded status enums | Medium | Convert to FK master table before users customize |
| No carrier API polling | High | Support both push (webhooks) + pull (periodic API) |
| Event normalization hardcoded | High | Create mapping table, not hardcoded in worker |
| Landed cost assumes 1:1 receipt:container | Medium | Plan N:1 allocation strategy |
| SO container assignment has no UI | Medium | ShipmentExt.UsrContainerID needs form or automation |

## Build Roadmap

### Phase 1 — Critical UI (2-3 weeks)
| # | Screen | Type | Effort | Dependencies |
|---|--------|------|--------|-------------|
| 1 | PO Containers | GI | 2d | UsrContainer (exists) |
| 2 | SO Containers | GI | 2d | ShipmentExt (exists) |
| 3 | Container Events | GI | 2d | UsrContainerEvent (exists) |
| 4 | Freight Forwarders | ASPX | 3d | New DAC |
| 5 | Custom Classification | ASPX | 3d | StockItemExt (exists) |

### Phase 2 — Webhook Integration (1-2 weeks)
- container-event-worker in webhook-router (3d)
- Event normalization schema (2d)
- RefreshTracking wiring (1d)
- ETA propagation testing (2d)

### Phase 3 — Master Data (1 week)
- Container Types, Destinations, Preferences, PO Container Lines GI (1d each)

### Phase 4 — Defer
- Distribution analytics, Duty/Tariff GI, advanced prefs

**Total to full parity: ~6-8 weeks**
