# Answer Connect Go-Live — Heritage Fabrics

**Date:** 2026-04-11
**Status:** Approved
**Owner:** Kevin Bibelhausen

## Problem

Heritage Fabrics customer service can't answer phones fast enough. Call volume is 20-50/day. Stock check and price check are the most common L1 inquiries, and the tooling already exists to handle them — but nobody's answering the phone.

## Decision

Outsource L1 phone coverage to Answer Connect. Retool the existing cs-order-entry app (`cs-order-entry-production.up.railway.app`) from an order-taking tool into a **call intake & intent capture** tool. All intent data flows to HubSpot.

## Service Scope

### L1 — Answer Connect Handles

- **Stock check** — search inventory in cs-order-entry, report availability by warehouse
- **Price check** — search inventory in cs-order-entry, quote default price + UOM
- **Basic account info** — look up customer contacts, addresses, account details in HubSpot
- **Contact updates** — note changes in HubSpot or create ticket if system change required

### L2 — Escalate via HubSpot Ticket

- Order status inquiries
- Shipping / tracking questions
- Returns / claims
- Complaints
- Complex orders or anything AC agent can't resolve in <2 minutes

**Escalation path:** AC agent creates HubSpot ticket in the existing HF CS pipeline, appropriately categorized. Includes: customer name, callback number, issue category, agent notes. Kevin + HF staff work tickets from the queue.

## cs-order-entry Transformation

### Current State

Order entry tool — inventory search, line items, order creation, fulfillment queue. No auth required (open URL). Deployed on Railway.

### New State

**Call Intake & Intent Capture** tool. AC agent uses it on every inbound call.

### Core Flow

1. **Caller identification** — AC agent searches by company name or phone number (HubSpot contact/company lookup). Links the call to a HubSpot record.
2. **Intent capture** — What did the caller want?
   - Stock check (which items, quantities, which warehouse)
   - Price check (which items, quantity breaks)
   - Basic info request (address, contact update, general question)
   - Other / escalation
3. **Inventory + price lookup** — Existing search stays. AC agent looks up stock/price and gives the answer live on the phone.
4. **Outcome logging** — What happened?
   - Answered (had stock / quoted price)
   - Out of stock (captures unmet demand signal)
   - Escalated to L2 (auto-creates HubSpot ticket)
   - Customer said they'll call back / think about it
5. **Save to HubSpot** — Call logged as an engagement activity on the contact record with structured properties.

### What Gets Cut

- Actual order creation (AC agents don't take orders — that's L2)
- Fulfillment queue (not relevant for AC agents)

### What Gets Added

- Caller identification step (HubSpot contact/company search)
- Intent type selector
- Outcome capture with structured fields
- Auto-ticket creation on L2 escalation (into existing HF CS pipeline)
- Call log summary → HubSpot Engagements API

## HubSpot Data Model

### Call Activity (Engagements API, logged on each call)

- Contact/Company association (from caller ID step)
- Call type: Stock Check / Price Check / Info Request / Escalation
- Items inquired (array): InventoryID, Description, Qty requested, Availability result, Price quoted
- Outcome: Answered / Out of Stock / Escalated / Callback
- AC agent name
- Timestamp + duration estimate

### L2 Escalation Ticket (existing HF CS pipeline)

- Appropriate category tag for the inquiry type
- Caller name + callback number
- Items discussed
- Agent notes
- Associated to contact/company record

### Reporting Value

- **Item demand signals:** Filter call activities by items inquired. Spot patterns — frequently asked items you don't stock, items always out of stock.
- **Customer journey:** See a contact's full inquiry history before they order. How many calls before conversion, what they asked about.
- **AC agent performance:** Call volume, resolution rate, escalation rate.
- **Unmet demand:** Aggregate "Out of Stock" outcomes by item.

## Operational Setup

### Answer Connect Configuration

- Sign up for AC account (20-50 calls/day plan, business hours ET)
- Phone routing: forward Heritage Fabrics main line to AC
- AC agents get bookmarked access to:
  - `cs-order-entry-production.up.railway.app` (stock/price lookup + call logging)
  - HubSpot (customer lookup, ticket visibility)

### Call Script (Decision Tree)

```
Inbound call
├── Greeting: "Heritage Fabrics, how can I help you?"
├── Stock check
│   → Open cs-order-entry → Search item → Report availability → Log call
├── Price check
│   → Open cs-order-entry → Search item → Quote price + UOM → Log call
├── Account info
│   → Open HubSpot → Look up contact/company → Answer or log update needed
└── Anything else (order status, shipping, returns, complaints, complex orders)
    → "Let me get someone from our team to help with that.
       Can I get your name and best callback number?"
    → Log call as Escalation → Auto-creates HubSpot ticket
    → "Someone will call you back within [2 hours / by end of day]."
```

### HubSpot Setup

- Restricted seat or shared service account for AC agents
- Verify existing HF CS pipeline has category options covering: Stock Inquiry, Price Inquiry, Order Status, Shipping/Tracking, Return/Claim, Complaint, Other

## Implementation Summary

### No-Code (Day 1)

- AC account + phone routing
- Call script document (PDF for AC reference)
- HubSpot seat for AC agents
- Verify HF CS pipeline ticket categories

### App Changes (cs-order-entry)

- Remove order creation flow
- Remove fulfillment queue
- Add caller identification (HubSpot search)
- Add intent type selector
- Add outcome logging
- Add HubSpot Engagements API integration (call log)
- Add auto-ticket creation on escalation

### Cross-Repo

- **cs-order-entry** (studiob monorepo) — UI + API changes
- **HubSpot** — pipeline category verification, AC agent seat
- **Answer Connect** — account, script, phone routing
