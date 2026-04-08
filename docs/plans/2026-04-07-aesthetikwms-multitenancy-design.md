# AesthetikWMS Multi-Tenant Foundation for 3PL — Design

**Date:** 2026-04-07
**Status:** Approved (RFC level; implementation to start Phase A in parallel with SB501000 work)
**Repo:** studiob (app: `apps/heritage-wms` or renamed path — verify)
**Pilot customer:** Bakerloo Collection (textile brand, warm but no signed contract)

## Context

AesthetikWMS is HF's custom warehouse management app — React/Node on Railway with its own Postgres. It was built because Acumatica Distribution edition does not provide WMS primitives (LPN, sub-200ms scan, directed picking). Today it is implicitly single-tenant: every bin, LPN, scan assumes HF ownership.

HF is pivoting to offer 3PL services to outside customers (receiving, storage, pick/pack, ship). This design adds the multi-tenant foundation without touching Acumatica for 3PL inventory. Acumatica remains HF-only and sees 3PL only as AR revenue from billable events.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  AesthetikWMS (Node/React, Railway, Postgres)        │
│                                                      │
│  owners (HF, Bakerloo, ...)                          │
│  ├── inventory_items (scoped by owner_id)            │
│  ├── bins (physical, shared, tagged by stock owner)  │
│  ├── lpns (owner-scoped)                             │
│  ├── receipts → billable_event                       │
│  ├── putaway → billable_event                        │
│  ├── picks → billable_event                          │
│  ├── ships → billable_event                          │
│  └── storage (daily tick) → billable_event           │
│                                                      │
│  contracts (per owner) + rate_card_items             │
└──────────────────┬───────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────┐
│  webhook-router (Railway)                            │
│  • billable_events → Acumatica AR invoice push       │
│  • inventory + container updates → portal sync       │
└──────────────────────────────────────────────────────┘
```

Principles:
1. **Acumatica stays HF-only.** No 3PL inventory, ever.
2. **AesthetikWMS gains an `owner_id` dimension on every physical-state table.**
3. **Every billable touchpoint emits a structured event.**
4. **Month-end rolls events into AR invoices via webhook-router.**
5. **Physical bins are shared; ownership lives on the stock unit (LPN).**

## Schema additions (Postgres)

### `owners`
```sql
CREATE TABLE owners (
  id UUID PRIMARY KEY,
  owner_type TEXT NOT NULL CHECK (owner_type IN ('HF', 'TPL_CUSTOMER')),
  name TEXT NOT NULL,
  hubspot_company_id TEXT,
  acumatica_customer_id TEXT,
  segregation_mode TEXT NOT NULL DEFAULT 'DEDICATED_BINS'
    CHECK (segregation_mode IN ('DEDICATED_ZONE','DEDICATED_BINS','COMMINGLED')),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  notes TEXT
);

-- HF seed row
INSERT INTO owners (id, owner_type, name, segregation_mode, active)
VALUES ('00000000-0000-0000-0000-000000000001', 'HF', 'Heritage Fabrics', 'COMMINGLED', TRUE);
```

### `contracts`
```sql
CREATE TABLE contracts (
  id UUID PRIMARY KEY,
  owner_id UUID NOT NULL REFERENCES owners(id),
  effective_from DATE NOT NULL,
  effective_to DATE,
  name TEXT NOT NULL,
  free_days_at_port INT NOT NULL DEFAULT 5,
  free_days_at_warehouse INT NOT NULL DEFAULT 30,
  sla_dock_to_stock_hours INT NOT NULL DEFAULT 24,
  document_requirements JSONB NOT NULL DEFAULT '[]'::JSONB,
  coi_expiration_date DATE,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `rate_card_items`
```sql
CREATE TABLE rate_card_items (
  id UUID PRIMARY KEY,
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,      -- RECEIVE_CTN, PUTAWAY_PLT, STORAGE_PLT_DAY, PICK_LINE, PACK_ORD, SHIP_PARCEL, etc.
  unit TEXT NOT NULL,             -- CTN, PLT, DAY, LINE, ORDER, PARCEL
  rate NUMERIC(12,4) NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  acumatica_item_code TEXT NOT NULL,  -- non-stock item for AR invoicing
  minimum_charge NUMERIC(10,2),
  description TEXT
);
```

### `billable_events`
```sql
CREATE TABLE billable_events (
  id UUID PRIMARY KEY,
  owner_id UUID NOT NULL REFERENCES owners(id),
  contract_id UUID NOT NULL REFERENCES contracts(id),
  event_type TEXT NOT NULL,
  reference_type TEXT,
  reference_id UUID,
  quantity NUMERIC(12,4) NOT NULL,
  unit TEXT NOT NULL,
  rate_at_event NUMERIC(12,4) NOT NULL,    -- locked at event time, not invoice time
  amount NUMERIC(12,4) NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  invoiced_at TIMESTAMPTZ,
  invoice_ref TEXT,
  notes JSONB
);

CREATE INDEX idx_billable_events_owner_unbilled
  ON billable_events (owner_id, occurred_at)
  WHERE invoiced_at IS NULL;
```

### Column additions to existing tables

Add `owner_id UUID NOT NULL REFERENCES owners(id)` to:
- `inventory_items`, `receipts`, `orders`, `shipments`, `adjustments`, `cycle_counts`, `lpns`, `scan_events`

Backfill all existing rows to `owner_id = '00000000-0000-0000-0000-000000000001'` (HF seed).

## Application changes

### Backend (Node)
1. **Session middleware** carries `active_owner_id`; all queries scope by it.
2. **Row-level security** in Postgres as belt-and-suspenders: `SET LOCAL app.current_owner = $1` per transaction, RLS policies enforce.
3. **Billable event emission** hooked into every scan action; BullMQ async to preserve <200ms scan response.
4. **Storage tick worker** runs nightly; one event per LPN × owner × day for all LPNs in storage.
5. **Month-end close endpoint** `POST /api/billing/close-period` — collects unbilled events, returns draft invoice for review, on approve pushes to Acumatica via webhook-router.
6. **Query lint rule** — merges blocked if any new query reads a tenant-scoped table without an `owner_id` filter.

### Frontend (React + Android)
1. **Owner context switcher** at top of UI, visible to HF staff; customer users locked to their own owner.
2. **Per-owner color accent** in headers to prevent "wrong customer" mistakes.
3. **Receiving workflow** prompts for owner before scan session starts.
4. **New admin screens:** `/customers`, `/customers/:id/contract`, `/billing/events`, `/billing/close-period`.

### webhook-router
1. `POST /ae-wms/billable-events/push-to-acumatica` — month-end AR invoice creation.
2. `POST /ae-wms/inventory/sync-to-portal` — pushes inventory and container state to customer portal (see HubSpot 3PL portal design, or help.asthetik.com extension).

## Physical segregation modes

| Mode | Description | Use for |
|---|---|---|
| DEDICATED_ZONE | Fenced-off area, dedicated bins | Large customers, high-value, insurance-sensitive |
| DEDICATED_BINS | Customer-specific bins in shared zone | Medium customers, standard goods |
| COMMINGLED | Shared bins, LPN carries owner identity | Small customers, commodity goods, opt-in only |

Configured per-owner via `owners.segregation_mode`. Scanner blocks cross-owner put-away unless COMMINGLED.

## Phases

| Phase | Scope | Est. | User-visible? |
|---|---|---|---|
| A | owners table, owner_id columns (nullable), backfill, make non-null | 2 days | No |
| B | Context middleware + query scoping + RLS policies | 4 days | No (flag off) |
| C | Contracts, rate cards, billable events table + event emission | 6 days | No (flag off) |
| D | Admin UIs, month-end close, Acumatica AR push | 5 days | Yes (internal only) |
| E | First customer onboarding (Bakerloo) | 2 days + customer time | Yes (customer-facing via portal) |

**Total:** ~19 days focused work over 6-8 elapsed weeks.

## Testing

- **Unit:** every query scoping test; rate calculation tests.
- **Integration:** receive/putaway/pick/ship workflows for multiple owners, verify isolation.
- **Regression:** full HF workflow suite must produce zero billable events and zero cross-tenant leaks.
- **Data safety:** dry-run migration on prod snapshot BEFORE real cutover.
- **Isolation pen-test:** attempt cross-tenant queries via URL manipulation and API tampering.

## Risks

| Risk | Mitigation |
|---|---|
| Query scoping mistakes leak data | RLS belt-and-suspenders, lint rule, aggressive tests |
| HF production regression | Phase A non-disruptive by design; flag off until verified |
| Scan latency regression from event emission | BullMQ async emission, preserve sub-200ms target |
| Storage tick unbounded growth | Archive events > 2 years after invoicing |
| Rate card changes mid-period dispute | `rate_at_event` locks at emission time |
| Deploying while HF operations are active | Deploy during known quiet window |

## Non-goals

- 3PL inventory in Acumatica (never).
- Real-time sync to portal (5-15 min acceptable).
- EDI (944/945/947) — deferred until customer demands.
- White-label customer branding.
- International currencies (USD only v1).

## Open questions

1. Does HF's Acumatica have a REST endpoint for AR invoice create, or does webhook-router need a customization? Likely need a small Acumatica extension.
2. What Bakerloo-specific segregation mode will they need? Default `DEDICATED_BINS` unless they push for zone.
3. Bakerloo's document requirement profile — ask during contract discussion.
