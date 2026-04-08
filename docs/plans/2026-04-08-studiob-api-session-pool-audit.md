# P1.3 — studiob-api Session Pool & verify.py 401 Storm Audit

> **Deliverable** from `docs/prompts/2026-04-08-execute-phase3-convergence.md` — No-regret backlog item P1.3.
> **Scope:** audit only. No code changes. The recommendation section names exactly what the follow-up PR should do.
> **Status when complete:** Kevin reviews the recommendation and approves the fix PR(s).

## Executive summary

**Root cause (confirmed):** the verify.py 401 storm during deploy runs is caused by Heritage Fabrics' Acumatica `API Login Limit` being saturated by the studiob-api gateway on the same Acumatica user (`api-bot`) that verify.py uses. When verify.py logs in, the initial 204 succeeds but every subsequent entity call returns 401 because the new session is immediately invalidated by Acumatica's license policy.

**Recommendation:** ship **(c) dedicated `api-verify` Acumatica user** as the next fix. It's small, has zero dependencies on the in-flight studiob-api gateway refactor, requires no code in studiob itself, and completely isolates verify.py's license seat from every other Acumatica consumer. Infrastructure prereq: Kevin creates the `api-verify` user in the Acumatica Users screen on both the prod instance and the sandbox instance with read-only Contract-Based API permissions.

The full fix pattern per the KB (`studiob-knowledge` doc "verify.py needs dedicated Acumatica license seat — api-verify pattern") is **(b) + (c)** — session reuse inside studiob-api AND a dedicated user for verify.py. This audit confirms (c) can ship independently and should go first because it closes the bleeder without touching the gateway's moving parts.

## Evidence — the 2026-04-08 failed run

AcuOps Deploy run `24111687164` (2026-04-08T00:48:31Z → 18m54s → conclusion `failure`):

```
2026-04-08T00:56:05Z  ##[group]Run python scripts/verify.py \
2026-04-08T00:59:02Z  [FAIL] entity:PurchaseOrder (HTTP 401): auth broken — 401 Unauthorized
2026-04-08T00:59:02Z  [FAIL] entity:SalesOrder    (HTTP 401): auth broken — 401 Unauthorized
2026-04-08T00:59:02Z  [FAIL] entity:Customer      (HTTP 401): auth broken — 401 Unauthorized
2026-04-08T00:59:02Z  [FAIL] entity:Vendor        (HTTP 401): auth broken — 401 Unauthorized
2026-04-08T00:59:02Z  [FAIL] entity:Invoice       (HTTP 401): auth broken — 401 Unauthorized
2026-04-08T00:59:02Z  [FAIL] entity:Shipment      (HTTP 401): auth broken — 401 Unauthorized
2026-04-08T00:59:02Z  [FAIL] entity:StockItem     (HTTP 401): auth broken — 401 Unauthorized
2026-04-08T00:59:02Z  [FAIL] field:PurchaseOrder.UsrExpArrivalDate (HTTP 401): schema endpoint: auth broken — 401 Unauthorized
2026-04-08T00:59:02Z  [FAIL] field:PurchaseOrder.UsrActArrivalDate (HTTP 401): schema endpoint: auth broken — 401 Unauthorized
2026-04-08T00:59:02Z  [FAIL] field:PurchaseOrder.UsrContainerRef   (HTTP 401): schema endpoint: auth broken — 401 Unauthorized
2026-04-08T00:59:02Z  [FAIL] e2e:Vendor           (HTTP 401): auth broken — 401 Unauthorized
... (every entity + e2e probe fails identically)
```

This matches the KB pattern exactly — every call after login returns 401 with the same error shape.

## Audit findings

### 1. `verify.py` lives in this repo, not acuops-pipeline

`scripts/verify.py` is a 701-line Heritage-specific script in `acumatica-ci-cd`, not in the upstream `acuops-pipeline` package. It uses pure `urllib`, authenticates with session cookies via `POST /entity/auth/login`, and has minimal 401 retry logic (retries ONCE after a 10-second sleep, `verify.py:168–176`). It reads its credentials directly from `ACUMATICA_USERNAME` / `ACUMATICA_PASSWORD` / `ACUMATICA_TENANT` env vars, which the workflow populates from the `ACUMATICA_SANDBOX_*` / `ACUMATICA_PROD_*` secrets depending on the job.

**Implication:** verify.py has no dependency on the studiob-api gateway or the SessionPool infrastructure. It talks directly to Acumatica. The fix is a credential change, not a code change.

### 2. `SessionPool` exists in the monorepo and is solid

`/Users/kevin/dev/studiob/packages/clients/src/acumatica/session-pool.ts` (770 lines) implements a proper session pool:

- Redis-backed checkout/checkin with cookie reuse
- `maxSize` cap with backpressure via poll loop
- Stale-checkout reclaim (`staleCheckoutMs`, default 120s)
- Idle-session keepalive with 401 detection and automatic eviction (`keepaliveMs`, default 10 min)
- Circuit breaker for `AccountLockedError`
- Degraded in-memory mode when Redis is unreachable

Wired up by `packages/mcp-acumatica/src/lib/session-manager.ts:29` using config from `packages/mcp-acumatica/src/config.ts:34–37`:

```typescript
redis: {
  url: optional('REDIS_URL', ''),
  maxConcurrent: optionalInt('SESSION_GATE_MAX_CONCURRENT', 2),
}
```

**Default pool size is 2 slots.** The `studiob-api` Railway service does **not** set `SESSION_GATE_MAX_CONCURRENT` — it defaults to 2.

### 3. The deployed `studiob-api` code path is uncertain

Current `main` in `studiob` has `packages/api/src/routes/acumatica.ts`, `packages/api/src/app.ts`, and `apps/server/src/index.ts` all at **0 lines** (stubs). Yet `railway logs --service studiob-api` shows a firehose of `GET /api/v1/acumatica/query/{Entity}` requests returning 200s in production.

**Interpretation:** either the deployed service is running an older git ref where these files had content, or the wire-up is coming from a package I didn't trace (possibly `packages/mcp-acumatica` being served directly as HTTP routes). There's an in-flight gateway refactor visible in recent commits:

```
4322411 merge: resolve conflicts with main
f6c8551 fix(mcp-acumatica): add missing getOData method to local client
698a9cb docs: update plan with gateway deploy steps and staging status
fe490ba feat(mcp-acumatica): gateway route translation + pool-managed proxy
52b1aa5 ci: clients publish triggers downstream MCP rebuild
```

**Action deferred (not required for the (c) fix):** a follow-up audit should (1) confirm which git SHA Railway is serving via the Railway deployment metadata, (2) confirm whether the deployed code actually uses `SessionPool` or is still on an older direct-login pattern, (3) set `SESSION_GATE_MAX_CONCURRENT` explicitly to a known value.

### 4. `api-bot` is a shared pool across multiple services

From `railway variables --service <name> --kv` across the `studiob-platform` Railway project:

| Service | Acumatica access | User |
|---|---|---|
| `studiob-api` | direct (gateway origin) | `api-bot` |
| `webhook-router` | via gateway (`ACUMATICA_GATEWAY_URL=https://studiob-api-production-2df4.up.railway.app`) | `api-bot` (inherited) |
| `acusync` | via gateway (`ACUMATICA_GATEWAY_URL=http://studiob-api.railway.internal`) | `api-bot` (inherited) |
| `business-dashboard` | direct | `api-dashboard` ✅ already isolated |
| `verify.py` (acuops-pipeline runtime in GH Actions) | direct (bypasses gateway) | `api-bot` — via `ACUMATICA_SANDBOX_USERNAME` / `ACUMATICA_PROD_USERNAME` secrets |

**Finding:** every real-time service that hits Acumatica today funnels through `api-bot` except `business-dashboard`. When `studiob-api` is handling its normal load (SalesOrder polling for webhook-router, acusync sync cycles, etc.), `api-bot`'s seat cap is effectively owned by studiob-api's worker pool. verify.py shows up during a deploy and gets starved.

### 5. Prior art: the team has already split workloads across multiple Acumatica users

git log on `studiob` shows the team has done exactly this pattern before:

```
d9a8f33 fix: use api-provision for SOAP to avoid api-bot session limit
4230f11 [AUDIT] Fix OData auth — use Basic Auth instead of session cookies
ae9ca85 [LOT-ALLOC] Query lot data via OData Basic Auth (not entity session)
```

Splitting a workload off `api-bot` onto a dedicated user is a proven, low-risk pattern. `api-provision` already exists for the SOAP side. `api-dashboard` already exists for the dashboard side. `api-verify` for the verification side is the next obvious split.

### 6. `deploy.py` already handles license-limit saturation with retry

Upstream `acuops-pipeline/scripts/deploy.py:149–254` has explicit detection of "API Login Limit" in login error responses and a retry loop with a circuit breaker after 3 consecutive identical failures. That's why deploys usually survive a saturated `api-bot` — they wait it out. **verify.py has no equivalent logic** — just a single 10-second retry. This is the second-order reason verify.py fails loudest during the license-limit window.

## Recommendation

Ship fix (c) next. Exact runbook below.

### Fix (c) — Dedicated `api-verify` Acumatica user

**Prereq (manual, Kevin):** create `api-verify` user in Acumatica:

1. **Prod instance** (`heritagefabrics.acumatica.com`):
   - Users screen → add `api-verify` with a strong password
   - Role: "Read Only (Contract-Based API)" — or create a minimal role if one doesn't exist with: read on `PurchaseOrder`, `SalesOrder`, `Customer`, `Vendor`, `Invoice`, `Shipment`, `StockItem`, plus GetSchema and ASPX export endpoints
   - Tenants: grant access to BOTH `Heritage Fabrics` (prod) and `Heritage Test` (test tenant on prod instance)
2. **Sandbox instance** (`heritagefabrics-sandbox.acumatica.com`):
   - Same user, same role, sandbox tenant

**Code/config fix (follow-up PR in `acumatica-ci-cd`):**

Add the credentials as GH secrets:

- `ACUMATICA_PROD_VERIFY_USERNAME` / `ACUMATICA_PROD_VERIFY_PASSWORD`
- `ACUMATICA_SANDBOX_VERIFY_USERNAME` / `ACUMATICA_SANDBOX_VERIFY_PASSWORD`
- `ACUMATICA_STG_VERIFY_USERNAME` / `ACUMATICA_STG_VERIFY_PASSWORD` (same user as PROD_VERIFY_* since staging = prod instance + Heritage Test tenant; or just reuse PROD_VERIFY_*)

Modify `.github/workflows/acuops-deploy.yml` at the **4 verify.py invocation sites** (lines `801`, `1319`, `1781`, `1870`) so the step `env:` block uses the `*_VERIFY_*` secret when set, falling back to the publish user:

```yaml
- name: Verify sandbox
  id: verify
  continue-on-error: true
  env:
    ACUMATICA_URL: ${{ secrets.ACUMATICA_SANDBOX_URL }}
    ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_SANDBOX_VERIFY_USERNAME || secrets.ACUMATICA_SANDBOX_USERNAME }}
    ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_SANDBOX_VERIFY_PASSWORD || secrets.ACUMATICA_SANDBOX_PASSWORD }}
    ACUMATICA_TENANT: ${{ secrets.ACUMATICA_SANDBOX_TENANT }}
  run: |
    python scripts/verify.py \
      --manifest publish-manifest.json \
      --environment sandbox \
      --json-output verify-result.json
```

(Same pattern at the 3 prod/staging verify invocations — sub in `ACUMATICA_PROD_VERIFY_*` / `ACUMATICA_STG_VERIFY_*`.)

**No changes required in `studiob` or `studiob-api`** for this fix. The gateway's current behavior is unchanged; `api-bot` continues to own the gateway's pool; verify.py simply stops competing for that user's license seats.

### Why not fix (a) "reduce studiob-api pool size"

- `SESSION_GATE_MAX_CONCURRENT` already defaults to 2 and isn't set explicitly on Railway — nothing to reduce
- Even if it were higher, reducing it doesn't isolate verify.py; any future traffic spike on studiob-api would re-saturate `api-bot` and starve verify.py again
- It doesn't address the other services (webhook-router, acusync) whose traffic is also on `api-bot` via the gateway

### Why not fix (b) "add session reuse to studiob-api"

- SessionPool already has session reuse. Adding more isn't the problem.
- **The real (b)-class question is whether the deployed code is using SessionPool at all.** That's answerable but requires tracing the Railway deploy source, which is a separate multi-session task (see Finding #3).
- Even if the deployed code isn't using SessionPool, wiring it up doesn't close the verify.py loophole because verify.py doesn't go through the gateway.

### Why (b) + (c) is the full long-term fix

- (c) isolates verify.py immediately — cheap, fast, low-risk
- (b) bounds the gateway's footprint on `api-bot` to a known quantity — defensive against future traffic growth
- Both can ship independently. (c) first, (b) as a follow-up in the studiob-api gateway refactor branch (where `fe490ba feat(mcp-acumatica): gateway route translation + pool-managed proxy` is already in progress)

## Next-session runbook for fix (c)

```
Session goal: provision api-verify user + update workflow secrets + ship PR

1. Manual — Kevin:
   - Log into Acumatica prod (heritagefabrics.acumatica.com) as admin
   - Users screen → add `api-verify` with strong password
   - Assign read-only Contract-Based API role scoped to the entities verify.py
     checks (grep `check_entity_reachability` calls in scripts/verify.py for the
     exact list, currently: PurchaseOrder, SalesOrder, Customer, Vendor, Invoice,
     Shipment, StockItem — plus GetSchema endpoint access)
   - Grant access to BOTH `Heritage Fabrics` and `Heritage Test` tenants
   - Log into Acumatica sandbox (heritagefabrics-sandbox.acumatica.com) as admin
   - Same user, same role, sandbox tenant

2. CLI — Claude:
   - gh secret set ACUMATICA_PROD_VERIFY_USERNAME
   - gh secret set ACUMATICA_PROD_VERIFY_PASSWORD
   - gh secret set ACUMATICA_SANDBOX_VERIFY_USERNAME
   - gh secret set ACUMATICA_SANDBOX_VERIFY_PASSWORD
   - gh secret set ACUMATICA_STG_VERIFY_USERNAME
   - gh secret set ACUMATICA_STG_VERIFY_PASSWORD

3. Code — Claude:
   - Edit .github/workflows/acuops-deploy.yml at lines ~792, ~1311, ~1775, ~1865
     (the 4 verify step blocks). For each, replace the `ACUMATICA_USERNAME` and
     `ACUMATICA_PASSWORD` env lines with the fallback pattern above.
   - Commit with a clear message referencing this audit doc.
   - Open a PR — MERGE WILL TRIGGER AN ACUOPS DEPLOY, coordinate timing.

4. Verification — Claude:
   - Wait for the merge-triggered AcuOps Deploy run to complete.
   - Check the verify-result.json artifact — all entity checks should return
     HTTP 200 not 401.
   - Confirm Acumatica licensing: run a parallel deploy (or leave studiob-api
     active) while verify.py runs. Both should succeed because they're on
     different license seats now.
   - Add a success row to docs/plans/2026-04-08-studiob-api-session-pool-audit.md
     under a new "Fix (c) shipped" section.

5. Follow-up:
   - Open a separate studiob repo issue for fix (b): confirm deployed code uses
     SessionPool, set SESSION_GATE_MAX_CONCURRENT explicitly, add pool status
     endpoint for observability.
```

## References

- `studiob-knowledge` KB: "verify.py needs dedicated Acumatica license seat — api-verify pattern" (score 0.58 vs the audit queries)
- `docs/prompts/2026-04-08-execute-phase3-convergence.md` — handoff prompt that commissioned this audit
- `docs/plans/2026-04-07-agentic-pipeline-next-stage-v2.md` — closeout log for the 2026-04-07 incident
- `scripts/verify.py:115–184` — verify.py's AcumaticaSession class
- `/Users/kevin/dev/studiob/packages/clients/src/acumatica/session-pool.ts` — SessionPool implementation
- `/Users/kevin/dev/studiob/packages/mcp-acumatica/src/lib/session-manager.ts:29` — SessionPool wire-up
- `/Users/kevin/dev/studiob/packages/mcp-acumatica/src/config.ts:34–37` — default pool config
- Failed run evidence: AcuOps Deploy `24111687164` (2026-04-08T00:48:31Z)
