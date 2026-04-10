# Error Signature Canonicalization — Pipeline Reference

> **Status:** v1 — acuops-deploy surface only
> **Owner:** Studio B AI
> **Created:** 2026-04-09
> **Related:** `~/dev/studiob/docs/architecture/larry-loop.md` (open question #1)

## Purpose

Every deploy incident ingested into `studiob-knowledge` gets a canonical `error_signature` string. Larry Loop uses this as the primary KB search key in its KB-first step (invariant #1). Signatures must be:

1. **Stable** — same root cause produces the same signature across runs
2. **Searchable** — exact-match filtering before semantic fallback
3. **Human-readable** — operators can scan them without decoding

## Format

```
{surface}:{check}-{detail}
```

- `surface` — pipeline stage that produced the error
- `check` — specific check or operation that failed
- `detail` — HTTP status code, error class, or qualifier

All lowercase, colon-separated, no spaces. Hyphens within segments only.

## Signature Catalog — acuops-deploy surface

### verify (post-publish verification via verify.py)

verify.py produces `verify-result.json` with checks array. Each check has `name`, `status`, `detail`.

| Signature | Trigger | Resolution hint |
|-----------|---------|-----------------|
| `verify:login-401` | Login returns 401 | Check ACUMATICA_PROD_USERNAME/PASSWORD secrets |
| `verify:login-500` | Login returns 500 | API Login Limit — wait for session slots to free |
| `verify:entity:{name}-401` | Entity GET returns 401 after successful login | Session cookie bug in verify.py (known: P1.3) |
| `verify:entity:{name}-404` | Entity GET returns 404 | Custom entity not deployed or API not enabled |
| `verify:entity:{name}-500` | Entity GET returns 500 | App pool unstable post-publish |
| `verify:field:{entity}.{field}-404` | Custom field not found in $adHocSchema | Field not in DAC extension or publish didn't include project |
| `verify:gi:health-500` | GI subsystem returns 500+ | GI corruption post-publish — check System Monitor |
| `verify:aspx:{screen}-mismatch` | ASPX file on instance doesn't match deployed package | `--no-merge` skipped ASPX extraction (known: PR #150 pattern) |
| `verify:unknown` | No checks failed but overall status is fail | Unexpected verify.py output — inspect logs |

### deploy (publish via deploy.sh / deploy.py)

| Signature | Trigger | Resolution hint |
|-----------|---------|-----------------|
| `deploy:login-401` | Login returns 401 | Bad credentials |
| `deploy:login-limit-500` | Login returns 500 (retried 5x) | API Login Limit — all session slots consumed |
| `deploy:api-unavailable-404` | Customization API returns 404/405 | API not enabled on instance |
| `deploy:preflight-400` | Pre-flight validation returns 400 | XML/compile error in project — check pre-flight logs |
| `deploy:preflight-500` | Pre-flight returns 500 | Server error — check System Monitor, retry |
| `deploy:import-500` | Package import returns 500 | Import failed — publish may be in progress |
| `deploy:publish-begin-500` | publishBegin returns 500 | Publish in progress or app pool issue |
| `deploy:publish-500` | Publish fails after begin | Compilation/SQL error during publish |
| `deploy:publish-timeout` | Publish exceeds POLL_TIMEOUT (600s default) | Increase timeout or check System Monitor |
| `deploy:smoke-500` | Post-publish smoke test returns 500 | App pool didn't restart cleanly |
| `deploy:db-corruption-nre` | NullReferenceException during publish | **NEVER RETRY** — file Acumatica support ticket |
| `deploy:unpublish-audit-{projects}` | Pre-publish audit detects projects that would be unpublished | Review co-publish manifest |
| `deploy:target-mismatch` | PROD_URL/TENANT don't match expected values | Check secrets — safety assertion failed |

### build (dotnet build + Acuminator on Windows)

| Signature | Trigger | Resolution hint |
|-----------|---------|-----------------|
| `build:compile-{CSxxxx}` | C# compiler error | Fix source code — error code in detail |
| `build:dll-missing-{project}` | DLL not produced after build | Check .csproj, dotnet restore |
| `build:sdk-missing` | SDK DLLs not found (local or GCS) | Check GCS bucket or local lib/ |
| `build:acuminator-{PXxxxx}` | Acuminator diagnostic (advisory, non-blocking) | Style issue — fix when convenient |

### sandbox (sandbox-gate job)

| Signature | Trigger | Resolution hint |
|-----------|---------|-----------------|
| `sandbox:host-mismatch` | SANDBOX_URL doesn't point to sandbox instance | Check ACUMATICA_SANDBOX_URL secret |
| `sandbox:tenant-prod` | SANDBOX_TENANT = "Heritage Test" (prod instance tenant) | Check ACUMATICA_SANDBOX_TENANT secret |
| `sandbox:publish-500` | Sandbox publish returns 500 | App pool issue on sandbox |
| `sandbox:publish-timeout` | Sandbox publish exceeds timeout | Check sandbox System Monitor |
| `sandbox:smoke-500` | Post-publish smoke test on sandbox returns 500 | Sandbox app pool unstable |
| `sandbox:odata-404-fixtures` | OData 404 during UI fixture generation | Workflow extractor failure (P1.1) |
| `sandbox:ui-tests-fail` | Playwright UI tests fail on sandbox | Business logic regression |

## Special signatures

### NEVER-RETRY list

These signatures cause Larry Loop to escalate immediately without retrying:

- `deploy:db-corruption-nre` — database corruption requires human investigation
- `sandbox:host-mismatch` — misconfigured secrets, agent can't fix
- `sandbox:tenant-prod` — misconfigured secrets, agent can't fix
- `deploy:target-mismatch` — misconfigured secrets, agent can't fix

### Compound signatures

When multiple checks fail, use the **first failure** as the primary signature. Store the full list in `error_detail` for context.

## Derivation logic

### From verify-result.json

```python
import json

def derive_verify_signature(result_path: str) -> str:
    d = json.load(open(result_path))
    fails = [c for c in d.get('checks', []) if c['status'] == 'fail']
    if not fails:
        return 'verify:unknown'
    c = fails[0]
    name = c['name'].lower().replace(' ', '-')
    detail = c.get('detail', '')
    suffix = ''
    if '401' in detail: suffix = '-401'
    elif '404' in detail: suffix = '-404'
    elif '500' in detail: suffix = '-500'
    elif 'timeout' in detail.lower(): suffix = '-timeout'
    elif 'mismatch' in detail.lower(): suffix = '-mismatch'
    return f'verify:{name}{suffix}'
```

### From deploy.sh exit

deploy.sh writes structured output to stdout. The calling workflow captures the exit code and last error line. Derivation:

```bash
# In acuops-deploy.yml after deploy step failure:
if grep -q "NullReferenceException" deploy-output.log; then
  ERROR_SIGNATURE="deploy:db-corruption-nre"
elif grep -q "API Login Limit" deploy-output.log; then
  ERROR_SIGNATURE="deploy:login-limit-500"
elif grep -q "pre-flight.*400" deploy-output.log; then
  ERROR_SIGNATURE="deploy:preflight-400"
# ... etc
fi
```

## Qdrant metadata schema

New incidents include `error_signature` in the chunk metadata:

```json
{
  "domain": "pipeline",
  "client": "aesthetik",
  "source_type": "incident",
  "event": "verification_failed",
  "error_signature": "verify:entity:SOOrder-401",
  "project": "AesthetikWMS",
  "environment": "production",
  "commit": "abc123ef",
  "timestamp": "2026-04-09T22:30:00Z"
}
```

Larry Loop's KB-first query filters on `error_signature` (exact match) before falling back to semantic search on the `text` field.

## Future surfaces

When new surfaces implement Larry (portal, DRP, WMS), add their signature catalogs here following the same format. The `{surface}:{check}-{detail}` pattern extends naturally:

- `portal:planner-timeout` — Opus planner exceeded budget
- `portal:executor-branch-routing` — Wrong repo routed
- `drp:signal-parse-fail` — DRP signal email couldn't be parsed
- `wms:sentry-{fingerprint}` — Runtime error from Sentry webhook
