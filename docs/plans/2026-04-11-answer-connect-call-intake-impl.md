# Answer Connect Call Intake — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Retool cs-order-entry from an order-taking app into a call intake & intent capture tool for Answer Connect agents, logging all call data to HubSpot.

**Architecture:** Keep existing inventory search + customer search. Replace OrderEntry page with a CallIntake page that captures caller ID, intent type, items discussed, and outcome. Log calls as HubSpot engagements. Auto-create HubSpot tickets on L2 escalation. Remove order creation and queue features.

**Tech Stack:** React 19, Fastify 5, HubSpot Engagements API v3, PostgreSQL, existing Acumatica gateway for inventory lookups.

**Repo:** `/Users/kevin/dev/cs-order-entry`

---

### Task 1: Database Migration — call_intake_log Table

**Files:**
- Create: `src/db/migrations/004_call_intake_log.sql`

**Step 1: Write the migration**

```sql
CREATE TABLE IF NOT EXISTS call_intake_log (
  id SERIAL PRIMARY KEY,
  hubspot_contact_id TEXT,
  hubspot_company_id TEXT,
  caller_name TEXT NOT NULL,
  caller_company TEXT,
  caller_phone TEXT,
  intent_type TEXT NOT NULL CHECK (intent_type IN ('stock_check', 'price_check', 'info_request', 'escalation', 'other')),
  items_discussed JSONB DEFAULT '[]',
  outcome TEXT NOT NULL CHECK (outcome IN ('answered', 'out_of_stock', 'escalated', 'callback', 'resolved')),
  agent_name TEXT,
  notes TEXT,
  hubspot_engagement_id TEXT,
  hubspot_ticket_id TEXT,
  duration_seconds INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_call_intake_created_at ON call_intake_log(created_at);
CREATE INDEX idx_call_intake_intent ON call_intake_log(intent_type);
CREATE INDEX idx_call_intake_contact ON call_intake_log(hubspot_contact_id);
```

**Step 2: Verify migration runs**

Run: `psql "$DATABASE_URL" -f src/db/migrations/004_call_intake_log.sql`
Expected: CREATE TABLE, CREATE INDEX x3

**Step 3: Commit**

```bash
git add src/db/migrations/004_call_intake_log.sql
git commit -m "feat: add call_intake_log table for Answer Connect"
```

---

### Task 2: Call Intake Types

**Files:**
- Create: `src/api/call-intake-types.ts`

**Step 1: Write the types**

```typescript
import { z } from 'zod';

export const IntentType = z.enum([
  'stock_check',
  'price_check',
  'info_request',
  'escalation',
  'other',
]);

export const Outcome = z.enum([
  'answered',
  'out_of_stock',
  'escalated',
  'callback',
  'resolved',
]);

export const ItemDiscussed = z.object({
  inventoryID: z.string(),
  description: z.string().optional(),
  qtyRequested: z.number().optional(),
  qtyAvailable: z.number().optional(),
  priceQuoted: z.number().optional(),
  uom: z.string().optional(),
  inStock: z.boolean().optional(),
});

export const CallIntakeRequest = z.object({
  hubspotContactId: z.string().optional(),
  hubspotCompanyId: z.string().optional(),
  callerName: z.string().min(1),
  callerCompany: z.string().optional(),
  callerPhone: z.string().optional(),
  intentType: IntentType,
  items: z.array(ItemDiscussed).default([]),
  outcome: Outcome,
  agentName: z.string().optional(),
  notes: z.string().optional(),
  durationSeconds: z.number().optional(),
});

export type IntentTypeValue = z.infer<typeof IntentType>;
export type OutcomeValue = z.infer<typeof Outcome>;
export type ItemDiscussedValue = z.infer<typeof ItemDiscussed>;
export type CallIntakeRequestValue = z.infer<typeof CallIntakeRequest>;
```

**Step 2: Commit**

```bash
git add src/api/call-intake-types.ts
git commit -m "feat: add call intake Zod schemas and types"
```

---

### Task 3: HubSpot Engagement Helper

**Files:**
- Modify: `src/hubspot/client.ts` (add `createEngagement` method)

**Step 1: Read the existing HubSpot client**

Read: `src/hubspot/client.ts` — understand the existing class structure, `fetchWithRateLimit`, and base URL patterns.

**Step 2: Add createEngagement method to HubSpotClient**

Add after the existing `createAssociation` method:

```typescript
async createEngagement(engagement: {
  type: 'CALL';
  timestamp: number;
  ownerId?: string;
  metadata: Record<string, string>;
  associations: {
    contactIds?: string[];
    companyIds?: string[];
    ticketIds?: string[];
  };
}): Promise<{ id: string }> {
  // Use Engagements v3 API
  const body = {
    properties: {
      hs_timestamp: String(engagement.timestamp),
      hs_call_body: engagement.metadata.body || '',
      hs_call_title: engagement.metadata.title || 'Inbound Call',
      hs_call_direction: 'INBOUND',
      hs_call_disposition: engagement.metadata.disposition || '',
      hs_call_duration: engagement.metadata.durationMs || '0',
      hs_call_status: 'COMPLETED',
      ...Object.fromEntries(
        Object.entries(engagement.metadata).filter(
          ([k]) => !['body', 'title', 'disposition', 'durationMs'].includes(k)
        )
      ),
    },
    associations: [
      ...(engagement.associations.contactIds || []).map((id) => ({
        to: { id },
        types: [{ associationCategory: 'HUBSPOT_DEFINED', associationTypeId: 194 }],
      })),
      ...(engagement.associations.companyIds || []).map((id) => ({
        to: { id },
        types: [{ associationCategory: 'HUBSPOT_DEFINED', associationTypeId: 186 }],
      })),
      ...(engagement.associations.ticketIds || []).map((id) => ({
        to: { id },
        types: [{ associationCategory: 'HUBSPOT_DEFINED', associationTypeId: 220 }],
      })),
    ],
  };

  return this.create('calls', body.properties, body.associations);
}
```

Note: The existing `create()` method on `HubSpotClient` may not accept associations. Check the signature — if it only takes `(objectType, properties)`, extend it to accept an optional associations array, or call the API directly via `fetchWithRateLimit`. Adapt to the actual method signature found in step 1.

**Step 3: Commit**

```bash
git add src/hubspot/client.ts
git commit -m "feat: add HubSpot call engagement creation"
```

---

### Task 4: Call Intake API Route

**Files:**
- Create: `src/api/call-intake.ts`
- Modify: `src/index.ts` (register new route)

**Step 1: Write the API route**

```typescript
import { FastifyInstance } from 'fastify';
import { Pool } from 'pg';
import { HubSpotClient } from '../hubspot/client.js';
import { CallIntakeRequest } from './call-intake-types.js';
import { sendSlackAlert } from '../alerts/slack.js';

interface CallIntakeDeps {
  db: Pool;
  hubspot: HubSpotClient;
}

export function registerCallIntakeRoutes(
  app: FastifyInstance,
  deps: CallIntakeDeps
) {
  // POST /api/calls — log a call
  app.post('/api/calls', async (req, reply) => {
    const parsed = CallIntakeRequest.safeParse(req.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: parsed.error.flatten() });
    }
    const call = parsed.data;

    // 1. Create HubSpot call engagement
    let engagementId: string | undefined;
    try {
      const result = await deps.hubspot.createEngagement({
        type: 'CALL',
        timestamp: Date.now(),
        metadata: {
          title: `Inbound Call — ${call.intentType.replace('_', ' ')}`,
          body: formatCallBody(call),
          durationMs: String((call.durationSeconds || 0) * 1000),
          disposition: call.outcome,
        },
        associations: {
          contactIds: call.hubspotContactId ? [call.hubspotContactId] : [],
          companyIds: call.hubspotCompanyId ? [call.hubspotCompanyId] : [],
        },
      });
      engagementId = result.id;
    } catch (err) {
      req.log.error({ err }, 'Failed to create HubSpot engagement');
    }

    // 2. Auto-create ticket on escalation
    let ticketId: string | undefined;
    if (call.outcome === 'escalated') {
      try {
        const ticket = await deps.hubspot.create('tickets', {
          subject: `Escalation: ${call.callerName} — ${call.intentType.replace('_', ' ')}`,
          content: formatTicketBody(call),
          hs_pipeline: process.env.CS_PIPELINE_ID || '',
          hs_pipeline_stage: process.env.CS_PIPELINE_STAGE_ID || '',
          hs_ticket_priority: 'HIGH',
        });
        ticketId = ticket.id;

        // Associate ticket to contact/company
        if (call.hubspotContactId) {
          await deps.hubspot.createAssociation(
            'tickets', ticketId, 'contacts', call.hubspotContactId
          );
        }
        if (call.hubspotCompanyId) {
          await deps.hubspot.createAssociation(
            'tickets', ticketId, 'companies', call.hubspotCompanyId
          );
        }
      } catch (err) {
        req.log.error({ err }, 'Failed to create escalation ticket');
      }
    }

    // 3. Log to database
    const { rows } = await deps.db.query(
      `INSERT INTO call_intake_log
       (hubspot_contact_id, hubspot_company_id, caller_name, caller_company,
        caller_phone, intent_type, items_discussed, outcome, agent_name,
        notes, hubspot_engagement_id, hubspot_ticket_id, duration_seconds)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
       RETURNING id`,
      [
        call.hubspotContactId, call.hubspotCompanyId, call.callerName,
        call.callerCompany, call.callerPhone, call.intentType,
        JSON.stringify(call.items), call.outcome, call.agentName,
        call.notes, engagementId, ticketId, call.durationSeconds,
      ]
    );

    // 4. Slack alert on escalation
    if (call.outcome === 'escalated') {
      await sendSlackAlert({
        text: `📞 Escalation from ${call.callerName} (${call.callerCompany || 'unknown'}) — ${call.intentType.replace('_', ' ')}. Ticket created.`,
      }).catch((err) => req.log.error({ err }, 'Slack alert failed'));
    }

    return reply.send({
      status: 'logged',
      callId: rows[0].id,
      engagementId,
      ticketId,
    });
  });

  // GET /api/calls/recent — last N calls for dashboard
  app.get('/api/calls/recent', async (req, reply) => {
    const limit = Math.min(Number((req.query as any).limit) || 25, 100);
    const { rows } = await deps.db.query(
      `SELECT * FROM call_intake_log ORDER BY created_at DESC LIMIT $1`,
      [limit]
    );
    return reply.send({ calls: rows });
  });
}

function formatCallBody(call: any): string {
  const lines = [
    `Caller: ${call.callerName}`,
    call.callerCompany && `Company: ${call.callerCompany}`,
    call.callerPhone && `Phone: ${call.callerPhone}`,
    `Intent: ${call.intentType.replace('_', ' ')}`,
    `Outcome: ${call.outcome}`,
  ].filter(Boolean);

  if (call.items.length > 0) {
    lines.push('', 'Items Discussed:');
    for (const item of call.items) {
      const parts = [item.inventoryID];
      if (item.qtyRequested) parts.push(`qty: ${item.qtyRequested}`);
      if (item.qtyAvailable !== undefined) parts.push(`avail: ${item.qtyAvailable}`);
      if (item.priceQuoted) parts.push(`price: $${item.priceQuoted}`);
      lines.push(`  • ${parts.join(' | ')}`);
    }
  }

  if (call.notes) lines.push('', `Notes: ${call.notes}`);
  return lines.join('\n');
}

function formatTicketBody(call: any): string {
  return [
    `Callback: ${call.callerPhone || 'not provided'}`,
    `Intent: ${call.intentType.replace('_', ' ')}`,
    call.items.length > 0 && `Items: ${call.items.map((i: any) => i.inventoryID).join(', ')}`,
    call.notes && `Agent Notes: ${call.notes}`,
    `Logged by: ${call.agentName || 'Answer Connect'}`,
  ].filter(Boolean).join('\n');
}
```

**Step 2: Register the route in index.ts**

In `src/index.ts`, find where other routes are registered (around lines 82-86). Add:

```typescript
import { registerCallIntakeRoutes } from './api/call-intake.js';
// ... in the route registration block:
registerCallIntakeRoutes(app, { db: pool, hubspot });
```

**Step 3: Add env vars to config.ts**

In `src/config.ts`, add to the Zod schema:

```typescript
CS_PIPELINE_ID: z.string().optional(),
CS_PIPELINE_STAGE_ID: z.string().optional(),
```

**Step 4: Commit**

```bash
git add src/api/call-intake.ts src/index.ts src/config.ts
git commit -m "feat: POST /api/calls route with HubSpot engagement + escalation tickets"
```

---

### Task 5: Frontend — CallIntake Page

**Files:**
- Create: `frontend/src/pages/CallIntake.tsx`
- Create: `frontend/src/components/OutcomeSelector.tsx`
- Create: `frontend/src/components/IntentSelector.tsx`
- Create: `frontend/src/components/ItemsDiscussed.tsx`

**Step 1: Build IntentSelector component**

Simple radio button group for intent types. Display labels: "Stock Check", "Price Check", "General Info", "Escalation", "Other".

**Step 2: Build OutcomeSelector component**

Radio button group for outcomes. Display labels: "Answered", "Out of Stock", "Escalated to L2", "Customer Will Call Back", "Resolved".

**Step 3: Build ItemsDiscussed component**

Reuses existing `InventorySearch` component for item lookup. Each searched item gets added to a list showing: InventoryID, Description, Qty Requested (input), Qty Available (auto-filled from search), Price (auto-filled), In Stock badge. Allow adding multiple items.

**Step 4: Build CallIntake page**

Full page flow matching the call script:

```
┌─────────────────────────────────────┐
│ 1. CALLER                           │
│ [Customer Search] (existing comp)   │
│ Name: [________] Phone: [________]  │
│                                     │
│ 2. WHAT DO THEY NEED?               │
│ ○ Stock Check  ○ Price Check        │
│ ○ General Info ○ Escalation ○ Other │
│                                     │
│ 3. ITEMS DISCUSSED                  │
│ [Inventory Search] (existing comp)  │
│ • BLU-001 | qty: 50 | avail: 120   │
│ • RED-003 | qty: 25 | avail: 0 ❌  │
│                                     │
│ 4. OUTCOME                          │
│ ○ Answered  ○ Out of Stock          │
│ ○ Escalated ○ Callback  ○ Resolved  │
│                                     │
│ 5. NOTES                            │
│ [____________________________]      │
│ Agent: [________]                   │
│                                     │
│ [Log Call]                          │
│                                     │
│ ── Recent Calls ──                  │
│ 10:30 | ACME Corp | Stock Check ✅  │
│ 10:15 | XYZ Mfg   | Escalated 🎫   │
└─────────────────────────────────────┘
```

After "Log Call" succeeds:
- Show success toast with call ID
- If escalated, show ticket link
- Reset form for next call
- Refresh recent calls list

**Step 5: Commit**

```bash
git add frontend/src/pages/CallIntake.tsx frontend/src/components/OutcomeSelector.tsx frontend/src/components/IntentSelector.tsx frontend/src/components/ItemsDiscussed.tsx
git commit -m "feat: CallIntake page with intent capture and outcome logging"
```

---

### Task 6: Frontend — Update Routing

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/Layout.tsx`

**Step 1: Read current routing setup**

Read `frontend/src/main.tsx` and `frontend/src/components/Layout.tsx` to understand current route structure.

**Step 2: Update routes**

- Default route (`/app` or `/`) → CallIntake (was OrderEntry)
- `/app/order` → Keep OrderEntry but behind a feature flag or hidden nav (don't delete yet — Kevin may want it later)
- `/app/queue` → Keep QueueDashboard but hidden from nav
- `/app/calls` → CallIntake (primary route)
- `/app/classify` → Keep EmailClassifier

Nav should show: **Call Intake** (primary) | Email Classifier
Hidden but accessible: Order Entry, Queue

**Step 3: Commit**

```bash
git add frontend/src/main.tsx frontend/src/components/Layout.tsx
git commit -m "feat: make CallIntake the default route, hide order/queue from nav"
```

---

### Task 7: Frontend API Client

**Files:**
- Modify: `frontend/src/api.ts`

**Step 1: Read existing api.ts**

Read `frontend/src/api.ts` to understand the fetch pattern.

**Step 2: Add call intake API functions**

```typescript
export async function logCall(call: {
  hubspotContactId?: string;
  hubspotCompanyId?: string;
  callerName: string;
  callerCompany?: string;
  callerPhone?: string;
  intentType: string;
  items: Array<{
    inventoryID: string;
    description?: string;
    qtyRequested?: number;
    qtyAvailable?: number;
    priceQuoted?: number;
    uom?: string;
    inStock?: boolean;
  }>;
  outcome: string;
  agentName?: string;
  notes?: string;
  durationSeconds?: number;
}): Promise<{ status: string; callId: number; engagementId?: string; ticketId?: string }> {
  const res = await fetch('/api/calls', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(call),
  });
  if (!res.ok) throw new Error(`Failed to log call: ${res.status}`);
  return res.json();
}

export async function getRecentCalls(limit = 25): Promise<{ calls: any[] }> {
  const res = await fetch(`/api/calls/recent?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to fetch calls: ${res.status}`);
  return res.json();
}
```

**Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat: add logCall and getRecentCalls API client functions"
```

---

### Task 8: Environment Config + Deploy

**Files:**
- Modify: Railway environment variables

**Step 1: Identify the HF CS pipeline ID**

Query HubSpot for the existing Heritage Fabrics CS pipeline:

```typescript
// Use HubSpot MCP tools or API to find pipeline ID + first stage ID
// Search for ticket pipelines
```

**Step 2: Set Railway env vars**

```bash
railway variables --set CS_PIPELINE_ID=<pipeline_id> --set CS_PIPELINE_STAGE_ID=<stage_id>
```

**Step 3: Deploy**

Push to main → Railway auto-deploys.

**Step 4: Verify**

Open `cs-order-entry-production.up.railway.app` in browser. Confirm:
- CallIntake page loads as default
- Customer search works
- Inventory search works
- Can log a test call
- Test escalation creates HubSpot ticket
- Recent calls list shows logged call

**Step 5: Commit any remaining config**

```bash
git commit -m "feat: Answer Connect call intake go-live"
```

---

## Task Dependency Graph

```
Task 1 (DB migration) ──┐
Task 2 (Types)      ────┤
Task 3 (HubSpot)    ────┼── Task 4 (API route) ──── Task 8 (Deploy)
                         │
Task 5 (Frontend UI) ────┤
Task 6 (Routing)    ────┤
Task 7 (API client) ────┘
```

Tasks 1-3, 5-7 can run in parallel. Task 4 depends on 1-3. Task 8 depends on all.

## Cross-Repo Notes

- **cs-order-entry** (`/Users/kevin/dev/cs-order-entry`) — All code changes
- **HubSpot** — Verify HF CS pipeline categories include Stock Inquiry, Price Inquiry, etc.
- **Answer Connect** — Kevin sets up account, phone routing, provides call script PDF
- **Railway** — Set CS_PIPELINE_ID and CS_PIPELINE_STAGE_ID env vars on cs-order-entry service
