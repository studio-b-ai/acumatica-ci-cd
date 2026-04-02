# Fabric Tracker — Design

**Date:** 2026-03-31
**Status:** Approved
**Repo:** studio-b-ai/webhook-router (portal routes + tracker API + notification worker)
**Product:** AcuOps Container Tracker (Studio B add-on)

## Goal

Give Heritage Fabrics customers a Domino's Pizza Tracker experience for fabric delivery. Customer logs into the Ästhetik portal, sees every open order with line-item level container tracking, vessel info, and predicted ETAs. Internal team sees the same view. Status reflected in HubSpot and Acumatica for single-pane-of-glass customer service.

## Architecture

Portal-native — new routes and views in webhook-router (`help.asthetik.com`). Same Entra SSO auth, same Fastify/HTML pattern as the enhancement portal. No new services.

### Data Chain

```
Customer → Sales Orders → SO Lines → PO Lines → UsrContainerPOLink → UsrContainer → UsrContainerEvent
```

All entities already exist in Acumatica. The tracker API walks this chain and returns a structured JSON response.

### Existing Infrastructure (Already Built)

| Layer | Status |
|-------|--------|
| Customer portal (`help.asthetik.com`) | Live — Entra SSO, company view |
| Container DACs (UsrContainer, UsrContainerEvent, UsrContainerPOLink) | Deployed |
| 10-event normalized lifecycle (BOOKED → DELIVERED) | Deployed |
| Carrier webhook endpoints (OTS, CHR, Maersk) | Deployed, awaiting carrier data |
| ContainerMaint screen (SB501000) | Deployed |
| Sales Order → PO → Container link chain | Acumatica native + UsrContainerPOLink |

## Tracker API

**Endpoint:** `GET /portal/api/tracker/:customerID`

Returns all open orders for a customer with container status at line-item granularity.

```json
{
  "customer": { "id": "QUILTCRAFT", "name": "QuiltCraft Interiors" },
  "orders": [
    {
      "orderNbr": "SO-005412",
      "orderDate": "2026-03-15",
      "status": "Open",
      "lines": [
        {
          "lineNbr": 1,
          "sku": "LINEN-NAT-54",
          "description": "Natural Linen 54\"",
          "qtyOrdered": 500,
          "uom": "YDS",
          "container": {
            "containerCD": "MSCU7234561",
            "carrier": "Maersk",
            "vessel": "MSC Lorena",
            "status": "IN_TRANSIT",
            "portOfLoading": "Shanghai",
            "portOfDischarge": "Savannah",
            "currentStage": 3,
            "stages": [
              { "code": "BOOKED", "label": "Booked", "completed": true, "date": "2026-03-01" },
              { "code": "DEPARTED", "label": "Departed", "completed": true, "date": "2026-03-08" },
              { "code": "IN_TRANSIT", "label": "In Transit", "completed": true, "date": "2026-03-08" },
              { "code": "ARRIVED", "label": "Port Arrived", "completed": false, "eta": "2026-04-14" },
              { "code": "CUSTOMS_CLEARED", "label": "Customs", "completed": false },
              { "code": "DELIVERED", "label": "Delivered", "completed": false }
            ],
            "eta": "2026-04-14",
            "etaSource": "carrier"
          }
        },
        {
          "lineNbr": 2,
          "sku": "VELVET-BLU-60",
          "description": "Blue Velvet 60\"",
          "qtyOrdered": 200,
          "uom": "YDS",
          "container": null
        }
      ]
    }
  ]
}
```

Lines without a container link show **"Awaiting Vessel"** in the UI.

## Tracker UI

Lives at `/portal/tracker` on `help.asthetik.com`. Server-side rendered HTML + minimal inline JS for pulse animation.

### Order List View (`/portal/tracker`)

Card layout showing all open orders. Each card: order number, date, line count, overall status (worst-case container across all lines). Internal team sees a company selector.

### Order Detail View (`/portal/tracker/:orderNbr`)

Line-item level tracking. Each line gets its own row:

```
┌─────────────────────────────────────────────────────────────────┐
│ SO-005412 · QuiltCraft Interiors · Mar 15, 2026                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ LINEN-NAT-54 · Natural Linen 54" · 500 YDS                    │
│ ● Booked ── ● Departed ── ◉ In Transit ── ○ Arrived ── ○ ── ○ │
│                            MSC Lorena · Maersk                  │
│                                         ETA: Apr 14, 2026      │
│                                                                 │
│ VELVET-BLU-60 · Blue Velvet 60" · 200 YDS                     │
│ ◌ Awaiting Vessel                                              │
│                                                                 │
│ SILK-IVR-48 · Ivory Silk 48" · 300 YDS                        │
│ ● Booked ── ● Departed ── ● In Transit ── ● Arrived ── ◉ ── ○ │
│                                             Customs · Savannah  │
│                                         ETA: Apr 2, 2026       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Timeline stages:** Booked → Departed → In Transit → Port Arrived → Customs → Delivered

**Branding:** Ästhetik design system — DM Serif Display headers, Inter body, terracotta (#C2705A) accent on active stage, cream background, pulse animation on current milestone.

## Notification Emails

Sent via **HubSpot Transactional Email API**. Branded templates with merge fields. Emails land on contact timeline for CS visibility.

### Triggers (4 milestones)

| Event | Subject Line |
|-------|-------------|
| DEPARTED | "Your order SO-005412 has left Shanghai" |
| ARRIVED | "Your order SO-005412 has arrived at Savannah" |
| CUSTOMS_CLEARED | "Your order SO-005412 has cleared customs" |
| DELIVERED | "Your order SO-005412 has been delivered to our warehouse" |

Port names from `UsrContainer.PortOfLoading` and `UsrContainer.PortOfDischarge`.

### Email Body

Line-item specific per container — only the SKUs on this specific container appear in the email:

> The following items from your order SO-005412 have departed Shanghai aboard MSC Lorena (Maersk):
>
> - LINEN-NAT-54 · Natural Linen 54" · 500 YDS
> - COTTON-WHT-60 · White Cotton 60" · 300 YDS
>
> Estimated arrival at Savannah: April 14, 2026
>
> [Track your order →](https://help.asthetik.com/portal/tracker/SO-005412)

### Internal Slack

Same events post to `#container-updates` with customer name, order, and status.

## HubSpot + Acumatica Reflection

### HubSpot (new deal properties)

| Property | Source | Purpose |
|----------|--------|---------|
| `container_status` | Highest-priority container status across all lines | CS sees "In Transit" at a glance |
| `container_eta` | Earliest ETA across containers on this order | "When is this order arriving?" |
| `container_numbers` | Comma-separated container CDs | Quick reference |
| `container_vessel` | Vessel name(s) | "What ship is it on?" |

Updated by the existing sync worker on the 15-min cron.

### Acumatica (already built)

- `UsrContainer` fields (status, ETA, vessel, ports) on ContainerMaint (SB501000)
- `UsrContainerEvent` — full event history
- `UsrContainerPOLink` — PO line → container mapping
- PO header fields (`UsrExpArrivalDate`, `UsrContainerRef`) on PO301000

## Predicted ETA Engine

### Phase 1 (MVP): Carrier-Reported ETA

Display `UsrContainer.ETA` as reported by the carrier. Labeled "Carrier estimate" in the UI.

### Phase 2 (after ~6 months of data): Own Prediction Model

**Training data:** Accumulated `UsrContainerEvent` timestamps — actual days between each milestone pair per route/carrier/season.

**Features:**
- Route: `PortOfLoading` → `PortOfDischarge`
- Carrier: `CarrierCode`
- Season: month/week of departure
- Day-of-week effects (customs doesn't clear weekends)

**Model:** Gradient boosted regression (XGBoost/LightGBM). One model per milestone transition. Input: carrier, route, season. Output: predicted days to next milestone.

Heritage Fabrics' narrow lane set (5-10 routes) means even 50 containers of history gives meaningful signal. The model learns that "Maersk from Shanghai to Savannah is consistently 3 days slower than reported ETA in Q4" — something VesselFinder's generic model can't know.

**Runtime:** Python worker on Railway, triggered by BullMQ when a new event arrives. Writes `PredictedETA` + `PredictionConfidence` back to `UsrContainer`.

**Productization:** Per-client model — each Acumatica instance trains on its own data. Same training pipeline, different data. Ships as AcuOps Container Tracker add-on.

## Contact Data Quality Gate (Pre-Launch Prerequisite)

No tracker emails fire until contacts are clean and opted in.

### Phase 1: Automated Audit (we run)

Script scans HubSpot contacts with `acumatica_customer_id`, flags:
- Garbage names (business names as person names — the old P0 bug)
- Missing/bounced emails
- Duplicate contacts
- No associated company
- Not reconciled against Acumatica `Customer.MainContact`

Output: Cleanup task list pushed to a HubSpot list or exported as spreadsheet. Clear, actionable, with issue type per contact.

### Phase 2: Manual Review (team does)

Team works the list in HubSpot:
- Verify/update email addresses
- Confirm correct contact person per customer for shipping notifications
- Add additional contacts (buyer AND warehouse manager)
- Set `tracker_notifications_enabled = true` on each verified contact
- Delete/archive garbage contacts

**Default: zero emails.** `tracker_notifications_enabled` defaults to `false`. The team opts contacts in, not out. We verify the enabled count before go-live.

## Studio B Product Play

The Fabric Tracker is Heritage Fabrics' reference implementation. The entire stack is carrier-agnostic and client-agnostic:
- Normalized event model works with any ocean carrier
- Prediction model trains per-client on their own routes
- Portal UI is templated (Ästhetik branding swappable)
- HubSpot + Acumatica sync is config-driven

**Product name:** AcuOps Container Tracker
**Positioning:** No textile distributor, no Acumatica VAR, no ISV offers this. Predicted ETAs trained on your own data is a genuine competitive moat.
