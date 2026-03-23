# AcuOps CI/CD Pipeline

## Your clients' customizations deploy with automatic rollback, sandbox validation, and zero-downtime guarantees. No more praying after publish.

---

Every Acumatica partner has the story. You publish a customization project at 5:30 PM, the app pool restarts, and you spend the next hour verifying nothing broke. Sometimes it did. Sometimes you don't find out until Monday morning when the client calls.

AcuOps Validate eliminates that entire class of risk. Every customization change flows through a pipeline that validates before it touches production, rolls back automatically if something goes wrong, and proves the system is healthy before anyone logs in the next day.

---

## Pipeline Architecture

```
Code Change → Build → Qualify → Countdown → Deploy → Verify → Notify
                ↓         ↓          ↓          ↓         ↓
             Package   6 safety    20-min    Import +   66 auto
             .zip +    checks +   warning    Publish    tests +
             validate  retry      to users   + Poll     field
             XML       loop                             checks
                                               ↓
                                          On failure:
                                          Auto-rollback
                                          from snapshot
```

Every step is automated. Every step has a fallback. Every step notifies your team.

---

## Safety Features

| Feature | What It Does | What It Prevents |
|---------|-------------|-----------------|
| **Agentic Qualify Gate** | 6 pre-deploy checks (health, orphan packages, diff scope, recent failures, cooldown timer, business-hours detection). Retries automatically with Slack escalation. | Deploying into an unhealthy instance, stacking deploys on top of each other, publishing during business hours without warning |
| **Sandbox Validation** | Every pull request publishes to a sandbox instance and runs the full test suite before merge. Results posted as PR comments. | Broken code reaching production. Compilation errors discovered after hours instead of during review. |
| **Automatic Rollback** | Pre-deploy snapshot taken before every publish. If post-publish verification fails, the pipeline restores the snapshot automatically. | Extended outages from bad deploys. Manual intervention at 2 AM. |
| **Countdown Timer** | Business-hours deploys trigger a 20-minute maintenance window with notifications at 20, 5, and 1 minute. Offloaded to a BullMQ queue so the pipeline doesn't burn compute waiting. | Users losing work because the app pool restarted without warning |
| **Post-Publish Verification** | After publish, the pipeline re-authenticates and validates every custom field in a manifest against the live API schema. | Silent field loss. "It published successfully" but the DAC extension didn't compile. |
| **Maintenance Mode** | Pipeline pauses all background workers (sync, health probes, webhooks) before publishing and resumes them after. | Session gate conflicts during app pool restart. Cascading failures across dependent services. |
| **Concurrency Control** | Only one deploy runs at a time per branch. Overlapping pushes cancel the earlier run. | Parallel publishes corrupting the app pool restart sequence |

Every feature has been tested in production. The rollback was verified through deliberate failure injection on sandbox. The countdown timer was verified end-to-end through the BullMQ queue. The sandbox validation catches real errors on every pull request.

---

## Automated Test Coverage

**66 automated tests** run daily at 6 AM UTC and after every deploy:

| Suite | Tests | What It Validates |
|-------|:-----:|------------------|
| Acumatica API | 56 | Entity schemas, custom fields (UDFs, DAC extensions), sub-entity expansion, cross-reference integrity across SalesOrder, StockItem, Customer, Shipment, Invoice, PurchaseOrder, Employee, Lead, Contact, Vendor |
| HubSpot API | 10 | Sync property existence (20 order + 9 company + 2 line item + 1 contact properties), pipeline stage order, ticket properties, form field rendering |

Tests run sequentially against the live Acumatica instance with built-in account lockout detection. If the API user gets locked out, tests abort immediately instead of cascading failures.

**Failure injection testing** is run on-demand to verify the rollback mechanism works. A deliberately broken customization project is deployed to sandbox, the publish fails as expected, entity smoke tests confirm the instance is still healthy, and the broken project is cleaned up automatically.

---

## Environment Strategy

| Environment | Purpose | Data |
|-------------|---------|------|
| **Production** | Live business operations | Real, current |
| **Sandbox** | CI/CD target for PR validation and failure injection | Customization packages mirrored from production |
| **Heritage Test** | Regression baseline | Nightly entity sync from production (Customers, Items, Vendors, Employees) |

The nightly entity sync reads all records from production and upserts them to the test company using the Acumatica REST API. Two-phase design: read phase (one session), then write phase (separate session) to avoid session gate conflicts. SalesOrders are compared by count only (no write) to avoid order lifecycle complexity.

---

## Deploy Runbook

Every AcuOps Validate client gets a documented escalation path covering:

- Qualify gate blocks (health failure, orphan packages, cooldown)
- Automatic rollback scenarios (when it fires, when it doesn't, manual fallback)
- API user lockout recovery (cascading impact across all connected services)
- Post-publish field verification failures
- App pool restart timeouts
- Session gate conflict resolution

The runbook is maintained alongside the pipeline code and updated after every incident.

---

## What This Means for Your Practice

If you're an Acumatica VAR managing 10+ clients with customization projects, you know the math: every deploy is a risk event. Manual verification takes 30-60 minutes per client. Weekend deploys eat into your team's time. And when something breaks, the client calls you, not the other way around.

AcuOps Validate flips that equation. Your team pushes code. The pipeline validates it on sandbox, warns users before the maintenance window, deploys with automatic rollback, verifies every custom field, and notifies your team of the result. If something breaks, the pipeline fixes it before the client notices.

**AcuOps Validate: $449/client/month.** Includes CI/CD pipeline, 66 automated tests, sandbox validation, automatic rollback, nightly environment sync, and deploy runbook.

That's less than one hour of a senior consultant's time per month per client. For a pipeline that runs 24/7.
