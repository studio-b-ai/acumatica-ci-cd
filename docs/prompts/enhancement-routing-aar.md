# AAR: Enhancement Branch Routing + Portal Review

## Background for the agent

You're working with Kevin Bibelhausen, Principal at Studio B AI. Studio B builds AI-powered tools for Acumatica VARs. Kevin's primary client is Ästhetik / Heritage Fabrics.

Studio B has an **enhancement request portal** (served by webhook-router at internal.asthetik.com) where Heritage Fabrics staff submit feature requests and bug reports. These become HubSpot tickets that flow through a 10-stage pipeline (submitted → triage → planning → scheduled → feedback → approved → in development → testing → deployed → closed).

When a ticket reaches the "in development" stage, the **enhancement-executor** (a BullMQ worker in webhook-router) auto-generates code and pushes it to a GitHub branch named `enhancement/{ticketId}-{slug}`.

### The problem

During a branch cleanup on 2026-04-02, we discovered that **all 16 enhancement branches landed in the webhook-router repo** — even though at least 8-9 of them are Acumatica customization work (GIs, DAC fields, screen buttons) that should have gone to `studio-b-ai/acumatica-ci-cd`. The executor appears to default everything to webhook-router regardless of the ticket's domain.

This means:
- Customization code never reaches the Acumatica CI/CD pipeline
- Code review happens in the wrong context
- The generated code can't be tested or deployed through the proper pipeline
- 59 commits worth of work on one ticket (auto-print-box-label) went nowhere useful

### Key repos

| Repo | What goes here |
|------|----------------|
| `studio-b-ai/acumatica-ci-cd` | Acumatica customization projects (C# DAC/graph extensions, GI SQL, ASPX pages). Anything that touches Acumatica screens, fields, or business logic. Has CI/CD pipeline that builds, validates, and publishes to Acumatica. |
| `studio-b-ai/webhook-router` | Event processing (BullMQ workers), enhancement portal UI, intranet, HubSpot sync, Slack intake. NOT for Acumatica customization code. |
| `studio-b-ai/studiob` | Studio B platform API, MCP servers, service clients. Integration layer. |
| `studio-b-ai/skuba-apps` | Shopify connector product |
| `studio-b-ai/heritage-wms` | Warehouse management system (React PWA + Fastify) |
| `studio-b-ai/aesthetik-portal` | Customer self-service portal |

## What to do

### 1. Find the enhancement executor routing logic

The enhancement-executor worker lives in webhook-router. Key files to investigate:

- `/Users/kevin/dev/webhook-router/src/workers/enhancement-executor.ts` — the main worker
- `/Users/kevin/dev/webhook-router/src/workers/enhancement-planner.ts` — plans the enhancement steps
- Look for where it decides the target repo / creates branches / pushes code
- Look for any `repo`, `repository`, `targetRepo`, `github` config in the executor

Determine: how does it currently decide where to push code? Is it hardcoded to webhook-router? Is there a mapping? Does it read anything from the HubSpot ticket to decide?

### 2. Review the 16 misrouted tickets

Pull each ticket from HubSpot (the ticket IDs are HubSpot record IDs) to see the original request text. For each, confirm where the work should have landed.

| HubSpot Ticket ID | Description | Landed In | Should Be In |
|---|---|---|---|
| 43334182789 | Inventory with quantity detail GI | webhook-router | acumatica-ci-cd — it's a Generic Inquiry |
| 43334311684 | Auto-print box label (59 commits!) | webhook-router | acumatica-ci-cd — print action on shipment screen |
| 43341626686 | Cut/roll hang tag button missing from shipment screen | webhook-router | acumatica-ci-cd — graph extension button |
| 43343057162 | Clean up Stripe accounts | webhook-router | unclear — could be webhook-router or studiob |
| 43344995438 | HRCloud (GitHub team provisioning) | webhook-router | webhook-router — correct, it's IT provisioning |
| 43371522166 | Print purchase receipt labels missing from PO screen | webhook-router | acumatica-ci-cd — PO302000 action button |
| 43375885829 | Add comment field to samples request form | webhook-router | webhook-router — correct, it's the portal form |
| 43380479126 | Auto-allocate inventory | webhook-router | acumatica-ci-cd — SOOrderEntry graph extension |
| 43517886222 | Send customer update when backorder received | webhook-router | webhook-router — correct, it's a notification worker |
| 43519510695 | SOOrderEntry auto-allocation fix aggregate validation | webhook-router | acumatica-ci-cd — C# business logic fix |
| 43523972719 | Customer type field | webhook-router | acumatica-ci-cd — DAC field + API mapping |
| 43532137220 | GI640615 not showing SKU 39024 | webhook-router | acumatica-ci-cd — Generic Inquiry fix |
| 43538906295 | Link/button to orders on ticket | webhook-router | webhook-router — correct, portal UI |
| 43722500248 | User expected arrival date field missing (PO301000) | webhook-router | acumatica-ci-cd — DAC field on PO screen |
| 43731713929 | Announcements/newsletter system for team hub | webhook-router | webhook-router — correct, intranet feature |
| 43871285807 | Pricing box for break pricing above SKU section | webhook-router | acumatica-ci-cd — custom DAC + SO screen |

**Score: 9 misrouted to webhook-router, 7 correctly in webhook-router.**

### 3. Implement repo routing rules

Add routing logic to the enhancement executor so it picks the right repo based on ticket content. Suggested signals:

**Route to acumatica-ci-cd when:**
- Ticket mentions Acumatica screen IDs (pattern: 2 letters + 6 digits, e.g., SO301000, PO302000, IN202500)
- Ticket mentions: DAC, graph extension, GI, Generic Inquiry, customization, BQL, PXSelect
- Ticket mentions specific Acumatica tables: SOOrder, POOrder, INRegister, ARInvoice, etc.
- Ticket category (if it exists in HubSpot) is "Acumatica" or "ERP"

**Route to webhook-router when:**
- Ticket mentions: portal, form, intranet, team hub, Slack, notification, webhook
- Ticket mentions: HubSpot, CRM, sync, provisioning

**Route to other repos when:**
- Ticket mentions: Shopify, theme → skuba-apps
- Ticket mentions: WMS, warehouse, scanner → heritage-wms
- Ticket mentions: API, MCP, integration → studiob

**Default:** webhook-router (but log a warning so we can review)

### 4. Review the portal submission form

Check the enhancement request form at the portal:
- File: `/Users/kevin/dev/webhook-router/src/portal/views.ts` — look for `renderPortalNewRequest`
- File: `/Users/kevin/dev/webhook-router/src/portal/routes.ts` — look for POST handler

Questions:
- What fields does the user fill out when submitting a request?
- Is there a "system" or "category" dropdown (e.g., "Acumatica", "Portal", "Shopify")?
- If not, should we add one? That would make routing deterministic instead of heuristic.
- Are there any other UX issues with the submission flow?

### 5. Clean up the stale enhancement branches

After confirming routing fixes, delete the remaining stale branches on webhook-router. As of 2026-04-02, only two are potentially active:
- `enhancement/43722500248-user-expected-arrival-date-field-missing` (Apr 1, 27 commits)
- `feat/fabric-tracker` (Apr 1, 5 commits)

Everything else is Mar 28 or older. Delete command pattern:
```bash
gh api -X DELETE "repos/studio-b-ai/webhook-router/git/refs/heads/{branch}"
```

## Reference files

- Memory: `~/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_webhook_router_branch_aar.md` — full ticket list with routing analysis
- Enhancement executor: `/Users/kevin/dev/webhook-router/src/workers/enhancement-executor.ts`
- Enhancement planner: `/Users/kevin/dev/webhook-router/src/workers/enhancement-planner.ts`
- Portal views: `/Users/kevin/dev/webhook-router/src/portal/views.ts`
- Portal routes: `/Users/kevin/dev/webhook-router/src/portal/routes.ts`
- Kevin's global instructions: `~/.claude/CLAUDE.md`

## Deliverable

1. Root cause analysis: why the executor routes everything to webhook-router
2. Implemented fix: repo routing logic in the executor
3. Portal form update: add category/system field if missing
4. Branch cleanup: delete confirmed-stale branches
5. Recommendations for preventing this from recurring

Save the AAR to `docs/plans/YYYY-MM-DD-enhancement-routing-aar.md` in the acumatica-ci-cd repo (since that's where the routing gap was discovered).
