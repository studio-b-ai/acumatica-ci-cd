# 3PL Customer Portal — Design (v1)

**Date:** 2026-04-07
**Status:** Approved in concept; implementation blocked on AesthetikWMS multi-tenancy RFC Phase D
**Repos:** webhook-router (sync + server), optionally HubSpot configuration
**Pilot customer:** Bakerloo Collection

## Context

HF needs a customer-facing portal where 3PL customers can see their inventory, inbound containers, recent shipments, and invoices. Two existing assets could serve this:

1. **HubSpot Marketing Enterprise** — custom objects, Private Content for gated pages, existing CRM integration, already used for order entry by retailers/designers.
2. **portal.asthetik.com** — existing customer portal in webhook-router with Entra SSO, company-scoped views, Fastify/HTML pattern, and a tracker API already built for HF customers (see fabric-tracker-design.md). This was the intended home for 3PL from the original build — confirmed 2026-04-07.

## Key discovery during design

The fabric tracker work on portal.asthetik.com (2026-03-31) already built most of what a 3PL customer portal needs:
- SSO + company scoping
- Customer-scoped tracker API
- HTML rendering pattern
- Notification worker
- Existing container event normalization

**Recommendation (confirmed by Kevin 2026-04-07):** Use `portal.asthetik.com` as the 3PL portal, not HubSpot. HubSpot remains the CRM and HF's retail order-entry tool; the 3PL surface is an extension of the existing customer portal infrastructure, which was the intended home for 3PL from the original portal build.

**Why this beats HubSpot:**
- No Content Hub license dependency (was a hard gate for HubSpot approach).
- Reuses existing Entra SSO and company scoping — Bakerloo gets an SSO setup like any other portal customer.
- Faster iteration — Fastify routes in a repo we control, not HubL templates + HubSpot limits.
- Consistent branding with existing HF portal surface.
- Same notification worker can drive customer emails.
- Tracker API shape already matches what 3PL customers need.

HubSpot still plays a role:
- 3PL customer Company record lives in HubSpot (source of truth for contact/company data).
- `hubspot_company_id` on the `owners` table links WMS to HubSpot.
- Notifications (invoice posted, container arrived) can push to HubSpot as activities for the sales team to see alongside order activity.
- But the customer-facing UI lives in `portal.asthetik.com`, not HubSpot Private Content.

## Goals

1. Bakerloo can log into `portal.asthetik.com`, see their inventory, inbound containers, and shipments.
2. Data sync from AesthetikWMS to the portal API happens within 5-15 minutes.
3. Strict owner isolation — one customer cannot see another's data.
4. First pilot live within 2-3 weeks of AesthetikWMS multi-tenancy Phase D.

## Non-goals

- Real-time sub-minute inventory updates.
- Mobile-first UX (desktop primary, mobile passable).
- White-label branding (HF brand only v1).
- EDI.
- Customer financial analytics beyond invoice viewing.

## Architecture

```
  Bakerloo user browser
          │
          ▼
  portal.asthetik.com (webhook-router, Fastify)
     ├── Entra SSO
     ├── Company-scoped session
     ├── Tracker API (existing)
     └── NEW: 3PL portal routes
          ├── /3pl/inventory
          ├── /3pl/containers
          ├── /3pl/shipments
          └── /3pl/invoices
          │
          ▼
  webhook-router backend
     ├── Polls or subscribes to AesthetikWMS changes
     ├── Maintains materialized view of 3PL data per owner
     └── Renders HTML via existing template system
          │
          ▼
  AesthetikWMS Postgres (source of truth)
     └── Scoped by owner_id
```

## New portal routes

| Route | Purpose |
|---|---|
| `/3pl` | Landing tiles: open containers, inventory value, open shipments, latest invoice |
| `/3pl/containers` | Filterable list of owner's inbound containers |
| `/3pl/containers/:id` | Detail: events, docs, ETA history |
| `/3pl/inventory` | SKU list with qty on hand, allocated, available |
| `/3pl/inventory/:sku` | SKU detail: last movements, location summary |
| `/3pl/shipments` | Outbound shipment list |
| `/3pl/shipments/:id` | Shipment detail: tracking, contents |
| `/3pl/invoices` | Invoice list with PDF download |
| `/3pl/documents/upload` | Customer-uploaded docs (CI, PL, etc.) for inbound containers |

## New API routes

| Route | Purpose |
|---|---|
| `GET /api/3pl/:companyId/summary` | Tile data |
| `GET /api/3pl/:companyId/containers` | Container list |
| `GET /api/3pl/:companyId/containers/:id` | Container detail |
| `GET /api/3pl/:companyId/inventory` | Inventory list |
| `GET /api/3pl/:companyId/shipments` | Shipment list |
| `GET /api/3pl/:companyId/invoices` | Invoice list |
| `POST /api/3pl/:companyId/requests/release` | Request stock release → WMS pick task |
| `POST /api/3pl/:companyId/requests/damage-claim` | File damage claim → WMS ticket |

All `/api/3pl/:companyId/*` routes enforce `req.session.companyId === :companyId` at the middleware level.

## Sync pipeline

**Pattern:** webhook-router polls AesthetikWMS every N minutes OR subscribes to Postgres LISTEN/NOTIFY (preferred if feasible in the Railway Postgres config).

**Projection:** each WMS entity is projected to a portal-safe view that excludes cost, margin, and internal notes. Projections live in `webhook-router/src/projections/3pl/`.

**Cache:** portal API reads a cached materialized view in webhook-router's Postgres, not directly from WMS. Sync frequency 5-15 minutes. Last-updated timestamp shown in portal UI.

## Security

- Every API route scoped by session `companyId`.
- `portal.asthetik.com` session middleware verifies Entra SSO.
- Cross-customer test: attempt to load another customer's data by URL manipulation; must 403.
- Audit log in webhook-router for every portal view.
- Projection excludes all HF-sensitive fields.

## Phases

| Phase | Scope | Est. |
|---|---|---|
| A | New portal routes (read-only, hardcoded test data) | 2 days |
| B | Sync from WMS to webhook-router cache | 3 days |
| C | API endpoints + projection layer | 2 days |
| D | Request routes (release, damage-claim) → WMS back-sync | 2 days |
| E | Notifications (email via existing worker) | 1 day |
| F | Bakerloo onboarding + walkthrough | 1 day + customer time |

**Total:** ~11 days focused work.

## Relationship to HubSpot

HubSpot remains the CRM and activity log:
- 3PL customer Company + Contacts live in HubSpot.
- Portal login still goes through Entra SSO, but the customer record of truth is HubSpot.
- Key activities (invoice posted, container arrived) push to HubSpot as activities/tasks for HF sales visibility.
- Webhook-router syncs owner data from HubSpot Company records to WMS `owners` table.

This gives HF's sales team single-pane visibility ("Bakerloo had a container land last week and their invoice is $4,200 MTD") without forcing Bakerloo to log into HubSpot for an ops view.

## Open questions

1. Is Bakerloo on Entra SSO already or do they need to be provisioned? Check with HF IT.
2. Does webhook-router's current tracker API response shape match what a 3PL customer needs, or do we need a separate 3PL-specific API? Recommendation: separate namespace `/api/3pl/*` to keep customer types isolated.
3. Do we want a single sign-on story where Bakerloo users can see both HF's order-entry (if they're also an HF customer) and 3PL views from one login? Defer — not a v1 concern.
