# Phase 2: Knowledge Base Consolidation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify all knowledge into `studiob-knowledge`, replace both validation scripts with `verify.py`, and wire auto-ingestion so every deploy incident feeds the KB.

**Architecture:** Two parallel work streams — (A) unified `verify.py` in acumatica-ci-cd replacing `validate-publish.py` + `smoke-e2e.py`, and (B) Qdrant migration + AcuDev service update in the acudev repo. Stream A produces the structured JSON that Phase 3's AI agent will consume. Stream B makes `studiob-knowledge` the single brain.

**Tech Stack:** Python 3.11 (verify.py), Node.js/TypeScript (AcuDev), Qdrant REST API, Voyage AI voyage-3, GitHub Actions YAML.

**Cross-repo dependencies:**
- `acumatica-ci-cd` — verify.py, workflow update, auto-ingestion step
- `acudev` (at `/Users/kevin/code/studio-b/heritage-fabrics/acudev`) — collection migration, search update, ingestion endpoint update
- `acuops-pipeline` (checked out as `pipeline/` in GH Actions from `studio-b-ai/acuops-pipeline`) — this is where `validate-publish.py` and `smoke-e2e.py` currently live

---

## Stream A: Unified verify.py

### Task 1: Write verify.py test scaffolding

**Files:**
- Create: `scripts/verify.py`
- Create: `tests/test_verify.py`

**Step 1: Write the failing test for structured JSON output**

```python
# tests/test_verify.py
"""Tests for unified verify.py — structured JSON output."""
import json
import pytest


def test_verify_result_schema():
    """verify.py must return structured JSON with per-check results."""
    from scripts.verify import VerifyResult, CheckResult, CheckStatus

    result = VerifyResult(
        overall="pass",
        environment="sandbox",
        checks=[
            CheckResult(name="login", status=CheckStatus.PASS, detail="Authenticated as api-bot"),
            CheckResult(name="entity:PurchaseOrder", status=CheckStatus.PASS, detail="200 OK"),
        ],
        summary="2/2 checks passed",
    )
    d = result.to_dict()
    assert d["overall"] == "pass"
    assert d["environment"] == "sandbox"
    assert len(d["checks"]) == 2
    assert d["checks"][0]["name"] == "login"
    assert d["checks"][0]["status"] == "pass"
    # Must be valid JSON
    json.loads(json.dumps(d))


def test_verify_result_with_warn():
    """403 responses should produce WARN, not FAIL."""
    from scripts.verify import VerifyResult, CheckResult, CheckStatus

    result = VerifyResult(
        overall="pass",
        environment="production",
        checks=[
            CheckResult(name="entity:PurchaseOrder", status=CheckStatus.WARN, detail="403 Forbidden"),
        ],
        summary="0 fail, 1 warn, 0 pass",
    )
    d = result.to_dict()
    assert d["overall"] == "pass"  # warns don't fail
    assert d["checks"][0]["status"] == "warn"


def test_verify_result_with_fail():
    """500 responses should produce FAIL and overall=fail."""
    from scripts.verify import VerifyResult, CheckResult, CheckStatus

    result = VerifyResult(
        overall="fail",
        environment="production",
        checks=[
            CheckResult(name="entity:StockItem", status=CheckStatus.FAIL, detail="500 Internal Server Error"),
        ],
        summary="1 fail",
    )
    d = result.to_dict()
    assert d["overall"] == "fail"
    assert d["checks"][0]["status"] == "fail"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/test_verify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.verify'`

**Step 3: Implement the data model**

```python
# scripts/verify.py
"""
Unified post-publish verification script.

Replaces validate-publish.py + smoke-e2e.py with a single script that produces
structured JSON output for AI agent consumption (Phase 3).

Checks:
  1. Login smoke test (can we authenticate?)
  2. Entity reachability (HTTP GET each declared entity)
  3. Custom field existence (check $adHocSchema)
  4. E2E view probes (force DAC extension loading)
  5. GI subsystem health (detect corruption)

HTTP response rules (single source of truth):
  200/204 → PASS
  401     → FAIL (auth broken)
  403     → WARN (permission issue, not code bug)
  404     → FAIL (entity/field missing)
  500+    → FAIL (server error)

Output: JSON to stdout, human-readable to stderr.
Exit 0 if overall=pass, exit 1 if overall=fail.
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
import urllib.parse
import os
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    detail: str
    http_code: Optional[int] = None

    def to_dict(self):
        d = {"name": self.name, "status": self.status.value, "detail": self.detail}
        if self.http_code is not None:
            d["http_code"] = self.http_code
        return d


@dataclass
class VerifyResult:
    overall: str  # "pass" or "fail"
    environment: str
    checks: list  # list of CheckResult
    summary: str

    def to_dict(self):
        return {
            "overall": self.overall,
            "environment": self.environment,
            "checks": [c.to_dict() for c in self.checks],
            "summary": self.summary,
        }
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/test_verify.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add scripts/verify.py tests/test_verify.py
git commit -m "feat: verify.py data model with structured JSON output"
```

---

### Task 2: Implement the Acumatica session and login check

**Files:**
- Modify: `scripts/verify.py`
- Modify: `tests/test_verify.py`

**Step 1: Write the failing test for login check**

Add to `tests/test_verify.py`:

```python
def test_classify_http_response():
    """HTTP status codes map to correct CheckStatus values."""
    from scripts.verify import classify_http_status

    assert classify_http_status(200) == ("pass", "200 OK")
    assert classify_http_status(204) == ("pass", "204 No Content")
    assert classify_http_status(401) == ("fail", "401 Unauthorized")
    assert classify_http_status(403) == ("warn", "403 Forbidden — permission issue, not code bug")
    assert classify_http_status(404) == ("fail", "404 Not Found")
    assert classify_http_status(500) == ("fail", "500 Server Error")
    assert classify_http_status(503) == ("fail", "503 Server Error")
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/test_verify.py::test_classify_http_response -v`
Expected: FAIL with `cannot import name 'classify_http_status'`

**Step 3: Implement classify_http_status and AcumaticaSession**

Add to `scripts/verify.py`:

```python
def classify_http_status(code: int) -> tuple:
    """Single source of truth for HTTP response classification."""
    if code in (200, 204):
        return ("pass", f"{code} OK" if code == 200 else "204 No Content")
    elif code == 401:
        return ("fail", "401 Unauthorized")
    elif code == 403:
        return ("warn", "403 Forbidden — permission issue, not code bug")
    elif code == 404:
        return ("fail", "404 Not Found")
    else:
        return ("fail", f"{code} Server Error")


class AcumaticaSession:
    """Minimal urllib-based REST client (no external deps)."""

    def __init__(self, base_url: str, username: str, password: str, tenant: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.tenant = tenant
        self.cookie = None

    def login(self, max_retries=10, retry_delay=20):
        """Authenticate, retrying during app pool restarts."""
        url = f"{self.base_url}/entity/auth/login"
        payload = json.dumps({
            "name": self.username,
            "password": self.password,
            "tenant": self.tenant,
        }).encode()

        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(url, data=payload,
                    headers={"Content-Type": "application/json"})
                resp = urllib.request.urlopen(req, timeout=30)
                self.cookie = resp.headers.get("Set-Cookie")
                return CheckResult(name="login", status=CheckStatus.PASS,
                    detail=f"Authenticated as {self.username} (attempt {attempt})",
                    http_code=resp.getcode())
            except urllib.error.HTTPError as e:
                if attempt == max_retries:
                    status, detail = classify_http_status(e.code)
                    return CheckResult(name="login", status=CheckStatus(status),
                        detail=f"Login failed after {max_retries} attempts: {detail}",
                        http_code=e.code)
                time.sleep(retry_delay)
            except Exception as e:
                if attempt == max_retries:
                    return CheckResult(name="login", status=CheckStatus.FAIL,
                        detail=f"Login error: {str(e)}")
                time.sleep(retry_delay)

    def logout(self):
        """Release API session."""
        if not self.cookie:
            return
        try:
            req = urllib.request.Request(f"{self.base_url}/entity/auth/logout",
                method="POST", headers={"Cookie": self.cookie})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass  # best effort

    def get(self, path: str, timeout=30) -> tuple:
        """GET request, returns (http_code, response_body_or_None)."""
        url = f"{self.base_url}{path}"
        try:
            req = urllib.request.Request(url, headers={"Cookie": self.cookie or ""})
            resp = urllib.request.urlopen(req, timeout=timeout)
            body = resp.read().decode()
            return (resp.getcode(), body)
        except urllib.error.HTTPError as e:
            return (e.code, e.read().decode() if e.fp else None)
        except Exception as e:
            return (0, str(e))
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/test_verify.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add scripts/verify.py tests/test_verify.py
git commit -m "feat: verify.py HTTP classification and Acumatica session"
```

---

### Task 3: Implement entity reachability + custom field checks

**Files:**
- Modify: `scripts/verify.py`
- Modify: `tests/test_verify.py`

**Step 1: Write the failing test**

Add to `tests/test_verify.py`:

```python
def test_check_entity_reachability_pass():
    """Entity returning 200 → PASS."""
    from scripts.verify import check_entity_reachability, CheckStatus
    # Mock session that returns 200
    class FakeSession:
        base_url = "https://example.com"
        cookie = "fake"
        def get(self, path, timeout=30):
            return (200, '{"value":[]}')
    result = check_entity_reachability(FakeSession(), "PurchaseOrder", "24.200.001")
    assert result.status == CheckStatus.PASS
    assert result.http_code == 200


def test_check_entity_reachability_403_is_warn():
    """Entity returning 403 → WARN (not FAIL)."""
    from scripts.verify import check_entity_reachability, CheckStatus
    class FakeSession:
        base_url = "https://example.com"
        cookie = "fake"
        def get(self, path, timeout=30):
            return (403, "Forbidden")
    result = check_entity_reachability(FakeSession(), "PurchaseOrder", "24.200.001")
    assert result.status == CheckStatus.WARN


def test_check_entity_reachability_500_is_fail():
    """Entity returning 500 → FAIL."""
    from scripts.verify import check_entity_reachability, CheckStatus
    class FakeSession:
        base_url = "https://example.com"
        cookie = "fake"
        def get(self, path, timeout=30):
            return (500, "Internal Server Error")
    result = check_entity_reachability(FakeSession(), "PurchaseOrder", "24.200.001")
    assert result.status == CheckStatus.FAIL


def test_check_custom_fields():
    """Custom field check against $adHocSchema response."""
    from scripts.verify import check_custom_fields, CheckStatus
    class FakeSession:
        base_url = "https://example.com"
        cookie = "fake"
        def get(self, path, timeout=30):
            schema = {"custom.Document.UsrExpArrivalDate": {"type": "string"}}
            return (200, json.dumps(schema))
    results = check_custom_fields(
        FakeSession(), "PurchaseOrder", "24.200.001",
        ["custom.Document.UsrExpArrivalDate"]
    )
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS


def test_check_custom_fields_missing():
    """Missing custom field → FAIL."""
    from scripts.verify import check_custom_fields, CheckStatus
    class FakeSession:
        base_url = "https://example.com"
        cookie = "fake"
        def get(self, path, timeout=30):
            return (200, json.dumps({}))
    results = check_custom_fields(
        FakeSession(), "PurchaseOrder", "24.200.001",
        ["custom.Document.UsrMissing"]
    )
    assert len(results) == 1
    assert results[0].status == CheckStatus.FAIL
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/test_verify.py -k "reachability or custom_fields" -v`
Expected: FAIL

**Step 3: Implement the check functions**

Add to `scripts/verify.py`:

```python
ENDPOINT_VERSION = os.environ.get("ACUMATICA_ENDPOINT_VERSION", "24.200.001")


def check_entity_reachability(session, entity_name: str, endpoint_version: str) -> CheckResult:
    """Check if entity endpoint returns a response."""
    path = f"/entity/Default/{endpoint_version}/{entity_name}?$top=1"
    code, body = session.get(path)
    status, detail = classify_http_status(code)
    return CheckResult(
        name=f"entity:{entity_name}",
        status=CheckStatus(status),
        detail=detail,
        http_code=code,
    )


def check_custom_fields(session, entity_name: str, endpoint_version: str,
                         custom_fields: list) -> list:
    """Check custom fields exist in $adHocSchema response."""
    if not custom_fields:
        return []

    path = f"/entity/Default/{endpoint_version}/{entity_name}/$adHocSchema"
    code, body = session.get(path)

    if code != 200:
        status, detail = classify_http_status(code)
        return [CheckResult(
            name=f"schema:{entity_name}",
            status=CheckStatus(status),
            detail=f"Cannot fetch schema: {detail}",
            http_code=code,
        )]

    try:
        schema = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        schema = {}

    results = []
    for field_path in custom_fields:
        # Check if field exists in schema (may be nested or flat key)
        found = field_path in schema
        if not found:
            # Try dotted path traversal
            parts = field_path.split(".")
            obj = schema
            for part in parts:
                if isinstance(obj, dict) and part in obj:
                    obj = obj[part]
                    found = True
                else:
                    found = False
                    break

        results.append(CheckResult(
            name=f"field:{entity_name}.{field_path}",
            status=CheckStatus.PASS if found else CheckStatus.FAIL,
            detail=f"Found in schema" if found else f"Missing from $adHocSchema",
        ))

    return results
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/test_verify.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add scripts/verify.py tests/test_verify.py
git commit -m "feat: verify.py entity reachability + custom field checks"
```

---

### Task 4: Implement E2E probes and GI health check

**Files:**
- Modify: `scripts/verify.py`
- Modify: `tests/test_verify.py`

**Step 1: Write the failing test**

Add to `tests/test_verify.py`:

```python
def test_run_e2e_probe_pass():
    """E2E probe: entity query with $select forces DAC extension loading."""
    from scripts.verify import run_e2e_probe, CheckStatus
    class FakeSession:
        base_url = "https://example.com"
        cookie = "fake"
        def get(self, path, timeout=30):
            return (200, '{"value":[{"OrderNbr":"PO000042"}]}')
    probe = {"entity": "PurchaseOrder", "select_fields": ["OrderNbr", "UsrExpArrivalDate"]}
    result = run_e2e_probe(FakeSession(), probe, "24.200.001")
    assert result.status == CheckStatus.PASS


def test_run_e2e_probe_500_is_fail():
    """E2E probe returning 500 → broken DAC extension."""
    from scripts.verify import run_e2e_probe, CheckStatus
    class FakeSession:
        base_url = "https://example.com"
        cookie = "fake"
        def get(self, path, timeout=30):
            return (500, "Invalid column name 'UsrBogus'")
    probe = {"entity": "StockItem", "select_fields": ["InventoryID", "UsrBogus"]}
    result = run_e2e_probe(FakeSession(), probe, "24.200.001")
    assert result.status == CheckStatus.FAIL
    assert "Invalid column" in result.detail


def test_check_gi_health_pass():
    """GI health: at least one GI returning 200 = healthy."""
    from scripts.verify import check_gi_health, CheckStatus
    class FakeSession:
        base_url = "https://example.com"
        cookie = "fake"
        def get(self, path, timeout=30):
            return (200, '{"value":[]}')
    result = check_gi_health(FakeSession(), "24.200.001")
    assert result.status == CheckStatus.PASS


def test_check_gi_health_all_500():
    """GI health: all GIs returning 500 = corruption."""
    from scripts.verify import check_gi_health, CheckStatus
    class FakeSession:
        base_url = "https://example.com"
        cookie = "fake"
        def get(self, path, timeout=30):
            return (500, "NullReferenceException")
    result = check_gi_health(FakeSession(), "24.200.001")
    assert result.status == CheckStatus.FAIL
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/test_verify.py -k "e2e or gi_health" -v`
Expected: FAIL

**Step 3: Implement E2E probes and GI health**

Add to `scripts/verify.py`:

```python
# Known GIs to probe for subsystem health
GI_PROBES = ["InventoryAllocationDetail", "LotAvailability"]


def run_e2e_probe(session, probe: dict, endpoint_version: str) -> CheckResult:
    """Run a single E2E probe — query entity with $select to force DAC loading."""
    entity = probe["entity"]
    select_fields = probe.get("select_fields", [])
    select_param = ",".join(select_fields) if select_fields else ""
    path = f"/entity/Default/{endpoint_version}/{entity}?$top=1"
    if select_param:
        path += f"&$select={select_param}"

    code, body = session.get(path)
    status, detail = classify_http_status(code)

    # Include response body snippet for 500s (often contains the real error)
    if code >= 500 and body:
        snippet = body[:200].strip()
        detail = f"{detail}: {snippet}"

    return CheckResult(
        name=f"e2e:{entity}",
        status=CheckStatus(status),
        detail=detail,
        http_code=code,
    )


def check_gi_health(session, endpoint_version: str) -> CheckResult:
    """Probe known GIs to detect subsystem corruption."""
    statuses = []
    for gi_name in GI_PROBES:
        path = f"/entity/Default/{endpoint_version}/{gi_name}?$top=1"
        code, _ = session.get(path)
        statuses.append((gi_name, code))

    any_200 = any(code == 200 for _, code in statuses)
    all_404 = all(code == 404 for _, code in statuses)
    any_500 = any(code >= 500 for _, code in statuses)

    if any_200 or all_404:
        return CheckResult(name="gi_health", status=CheckStatus.PASS,
            detail=f"GI subsystem healthy: {statuses}")
    elif any_500:
        return CheckResult(name="gi_health", status=CheckStatus.FAIL,
            detail=f"GI subsystem unhealthy (500+): {statuses}")
    else:
        return CheckResult(name="gi_health", status=CheckStatus.WARN,
            detail=f"GI subsystem inconclusive: {statuses}")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/test_verify.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add scripts/verify.py tests/test_verify.py
git commit -m "feat: verify.py E2E probes and GI health check"
```

---

### Task 5: Implement main() — CLI + orchestration + JSON output

**Files:**
- Modify: `scripts/verify.py`
- Modify: `tests/test_verify.py`

**Step 1: Write the failing test**

Add to `tests/test_verify.py`:

```python
def test_compute_overall_pass():
    """All PASS/WARN → overall pass."""
    from scripts.verify import compute_overall, CheckResult, CheckStatus
    checks = [
        CheckResult(name="login", status=CheckStatus.PASS, detail="ok"),
        CheckResult(name="entity:PO", status=CheckStatus.WARN, detail="403"),
    ]
    assert compute_overall(checks) == "pass"


def test_compute_overall_fail():
    """Any FAIL → overall fail."""
    from scripts.verify import compute_overall, CheckResult, CheckStatus
    checks = [
        CheckResult(name="login", status=CheckStatus.PASS, detail="ok"),
        CheckResult(name="entity:PO", status=CheckStatus.FAIL, detail="500"),
    ]
    assert compute_overall(checks) == "fail"


def test_build_summary():
    """Summary counts pass/warn/fail."""
    from scripts.verify import build_summary, CheckResult, CheckStatus
    checks = [
        CheckResult(name="a", status=CheckStatus.PASS, detail=""),
        CheckResult(name="b", status=CheckStatus.WARN, detail=""),
        CheckResult(name="c", status=CheckStatus.FAIL, detail=""),
        CheckResult(name="d", status=CheckStatus.PASS, detail=""),
    ]
    summary = build_summary(checks)
    assert "2 pass" in summary
    assert "1 warn" in summary
    assert "1 fail" in summary
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/test_verify.py -k "compute_overall or build_summary" -v`
Expected: FAIL

**Step 3: Implement main orchestration**

Add to `scripts/verify.py`:

```python
def compute_overall(checks: list) -> str:
    """Overall result: fail if any check failed, pass otherwise."""
    return "fail" if any(c.status == CheckStatus.FAIL for c in checks) else "pass"


def build_summary(checks: list) -> str:
    """Human-readable summary of check results."""
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for c in checks:
        counts[c.status.value] += 1
    return f"{counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail"


def run_all_checks(session, manifest: dict, endpoint_version: str) -> list:
    """Run all verification checks against a live Acumatica instance."""
    checks = []

    # 1. Login (already done — passed in as session)
    # login check is added by caller

    # 2. Entity reachability
    for entity_name, config in manifest.get("entities", {}).items():
        checks.append(check_entity_reachability(session, entity_name, endpoint_version))

        # 3. Custom field checks
        custom_fields = config.get("custom_fields", [])
        checks.extend(check_custom_fields(session, entity_name, endpoint_version, custom_fields))

    # 4. E2E probes
    for probe in manifest.get("e2e_probes", []):
        checks.append(run_e2e_probe(session, probe, endpoint_version))

    # 5. GI health
    checks.append(check_gi_health(session, endpoint_version))

    return checks


def main():
    parser = argparse.ArgumentParser(description="Unified post-publish verification")
    parser.add_argument("--manifest", required=True, help="Path to publish-manifest.json")
    parser.add_argument("--url", default=os.environ.get("ACUMATICA_URL"))
    parser.add_argument("--username", default=os.environ.get("ACUMATICA_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("ACUMATICA_PASSWORD"))
    parser.add_argument("--tenant", default=os.environ.get("ACUMATICA_TENANT"))
    parser.add_argument("--environment", default="production", choices=["sandbox", "production"])
    parser.add_argument("--endpoint-version", default=os.environ.get("ACUMATICA_ENDPOINT_VERSION", "24.200.001"))
    parser.add_argument("--json-output", help="Write JSON result to file (also prints to stdout)")
    args = parser.parse_args()

    if not all([args.url, args.username, args.password, args.tenant]):
        print("ERROR: --url, --username, --password, --tenant required (or set env vars)", file=sys.stderr)
        sys.exit(1)

    # Load manifest
    with open(args.manifest) as f:
        manifest = json.load(f)

    # Create session + login
    session = AcumaticaSession(args.url, args.username, args.password, args.tenant)
    login_result = session.login()
    checks = [login_result]

    if login_result.status == CheckStatus.FAIL:
        # Can't continue if login failed
        print(f"[FAIL] {login_result.detail}", file=sys.stderr)
    else:
        try:
            checks.extend(run_all_checks(session, manifest, args.endpoint_version))
        finally:
            session.logout()

    # Build result
    overall = compute_overall(checks)
    summary = build_summary(checks)
    result = VerifyResult(overall=overall, environment=args.environment,
                          checks=checks, summary=summary)

    # JSON to stdout (for AI agent consumption)
    result_json = json.dumps(result.to_dict(), indent=2)
    print(result_json)

    # Human-readable to stderr
    for c in checks:
        icon = {"pass": "[OK]", "warn": "[WARN]", "fail": "[FAIL]"}[c.status.value]
        print(f"  {icon} {c.name}: {c.detail}", file=sys.stderr)
    print(f"\n{'PASSED' if overall == 'pass' else 'FAILED'} — {summary}", file=sys.stderr)

    # Optional: write JSON to file
    if args.json_output:
        with open(args.json_output, "w") as f:
            f.write(result_json)

    sys.exit(0 if overall == "pass" else 1)


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/test_verify.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add scripts/verify.py tests/test_verify.py
git commit -m "feat: verify.py main orchestration with JSON output"
```

---

### Task 6: Update GitHub Actions workflow to use verify.py

**Files:**
- Modify: `.github/workflows/acuops-deploy.yml`

**Context:** The workflow currently runs `validate-publish.py` and `smoke-e2e.py` as separate steps from the `pipeline/` checkout (acuops-pipeline repo). We replace both with a single `verify.py` call from this repo's `scripts/` directory.

**Step 1: Replace the test-tenant-gate validation steps**

In `.github/workflows/acuops-deploy.yml`, find the test-tenant-gate job's validation steps (around lines 576-600) and replace:

```yaml
      # OLD: Two separate validation scripts from pipeline/
      # - name: Post-publish field validation (test-tenant)
      #   run: cd pipeline/scripts && python validate-publish.py ...
      # - name: E2E view-level smoke test (test-tenant)
      #   run: python pipeline/scripts/smoke-e2e.py ...

      # NEW: Unified verify.py from this repo
      - name: Verify test tenant
        id: verify
        continue-on-error: true
        env:
          ACUMATICA_URL: ${{ secrets.ACUMATICA_PROD_URL }}
          ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
          ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
          ACUMATICA_TENANT: ${{ vars.ACUMATICA_TEST_TENANT }}
        run: |
          python scripts/verify.py \
            --manifest publish-manifest.json \
            --environment sandbox \
            --json-output verify-result.json
```

**Step 2: Replace the prod deploy validation steps**

Find the deploy job's post-publish validation (around lines 905-920) and replace similarly:

```yaml
      # NEW: Unified verify.py replaces both validate-publish.py and smoke-e2e.py
      - name: Verify production deploy
        id: verify
        if: steps.deploy.outcome == 'success'
        continue-on-error: true
        env:
          ACUMATICA_URL: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_URL || (secrets.ACUMATICA_STG_URL || secrets.ACUMATICA_PROD_URL) }}
          ACUMATICA_USERNAME: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_USERNAME || (secrets.ACUMATICA_STG_USERNAME || secrets.ACUMATICA_PROD_USERNAME) }}
          ACUMATICA_PASSWORD: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_PASSWORD || (secrets.ACUMATICA_STG_PASSWORD || secrets.ACUMATICA_PROD_PASSWORD) }}
          ACUMATICA_TENANT: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_TENANT || (secrets.ACUMATICA_STG_TENANT || secrets.ACUMATICA_PROD_TENANT) }}
        run: |
          python scripts/verify.py \
            --manifest publish-manifest.json \
            --environment ${{ steps.env.outputs.target }} \
            --json-output verify-result.json
```

**Step 3: Update the alert step to use verify-result.json**

The alert step currently checks `steps.verify.outcome` and `steps.e2e.outcome` separately. Update to check only `steps.verify.outcome`:

```yaml
      - name: Alert on verification failure
        id: alert
        if: >
          steps.deploy.outcome == 'success' &&
          steps.verify.outcome == 'failure' &&
          steps.env.outputs.target == 'production' &&
          github.event.inputs.dry_run != 'true'
```

**Step 4: Upload verify-result.json as artifact**

Add after the verify step:

```yaml
      - name: Upload verification result
        if: always() && steps.verify.outcome != 'skipped'
        uses: actions/upload-artifact@v4
        with:
          name: verify-result-${{ steps.env.outputs.target }}
          path: verify-result.json
```

**Step 5: Commit**

```bash
git add .github/workflows/acuops-deploy.yml
git commit -m "feat: replace validate-publish.py + smoke-e2e.py with unified verify.py in workflow"
```

---

## Stream B: Knowledge Base Migration (acudev repo)

> **Cross-repo:** Tasks 7-11 are in the AcuDev repo at `/Users/kevin/code/studio-b/heritage-fabrics/acudev`. Open a separate worktree or session for this work.

### Task 7: Update Qdrant collection constants and SearchFilter

**Files:**
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/ingest/qdrant-ingest.ts`

**Step 1: Write the failing test**

Create `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/ingest/__tests__/collection-migration.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { COLLECTIONS, STUDIOB_COLLECTION } from '../qdrant-ingest.js';

describe('Collection constants', () => {
  it('primary collection is studiob-knowledge', () => {
    expect(STUDIOB_COLLECTION).toBe('studiob-knowledge');
    expect(COLLECTIONS.knowledge).toBe('studiob-knowledge');
  });

  it('supplemental collections unchanged', () => {
    expect(COLLECTIONS.community).toBe('acumatica-community');
    expect(COLLECTIONS.stackoverflow).toBe('acumatica-stackoverflow');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kevin/code/studio-b/heritage-fabrics/acudev && npx vitest run src/ingest/__tests__/collection-migration.test.ts`
Expected: FAIL — `STUDIOB_COLLECTION` not exported

**Step 3: Update the constants**

In `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/ingest/qdrant-ingest.ts`, change:

```typescript
// OLD
export const ACUDEV_COLLECTION = 'acudev-knowledge';
export const COLLECTIONS = {
  knowledge: 'acudev-knowledge',
  community: 'acumatica-community',
  stackoverflow: 'acumatica-stackoverflow',
} as const;

// NEW
export const STUDIOB_COLLECTION = 'studiob-knowledge';
/** @deprecated Use STUDIOB_COLLECTION */
export const ACUDEV_COLLECTION = STUDIOB_COLLECTION;

export const COLLECTIONS = {
  knowledge: 'studiob-knowledge',
  community: 'acumatica-community',
  stackoverflow: 'acumatica-stackoverflow',
} as const;
```

Also update all default parameter values in the file that reference `ACUDEV_COLLECTION`:
- `ensureCollection(qdrantUrl, collectionName = STUDIOB_COLLECTION)`
- `upsertPoints(qdrantUrl, points, collectionName = STUDIOB_COLLECTION)`
- `searchKnowledge(qdrantUrl, queryVector, limit, filter, collectionName = STUDIOB_COLLECTION)`

**Step 4: Run test to verify it passes**

Run: `cd /Users/kevin/code/studio-b/heritage-fabrics/acudev && npx vitest run src/ingest/__tests__/collection-migration.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
cd /Users/kevin/code/studio-b/heritage-fabrics/acudev
git add src/ingest/qdrant-ingest.ts src/ingest/__tests__/collection-migration.test.ts
git commit -m "feat: switch primary collection to studiob-knowledge"
```

---

### Task 8: Extend SearchFilter with domain/client/source tags

**Files:**
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/ingest/qdrant-ingest.ts`

**Step 1: Write the failing test**

Add to the test file from Task 7:

```typescript
import { SearchFilter } from '../qdrant-ingest.js';

describe('SearchFilter extended tags', () => {
  it('accepts domain, client, source filters', () => {
    const filter: SearchFilter = {
      domain: 'acumatica',
      client: 'aesthetik',
      source: 'incident',
    };
    expect(filter.domain).toBe('acumatica');
    expect(filter.client).toBe('aesthetik');
    expect(filter.source).toBe('incident');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kevin/code/studio-b/heritage-fabrics/acudev && npx vitest run src/ingest/__tests__/collection-migration.test.ts`
Expected: FAIL — `domain` not in SearchFilter

**Step 3: Extend SearchFilter and searchKnowledge**

In `qdrant-ingest.ts`, update:

```typescript
/** Filter options for knowledge search */
export interface SearchFilter {
  topic?: string;
  version?: string;
  /** Filter by domain: acumatica | pipeline | infrastructure | business | product */
  domain?: string;
  /** Filter by client: aesthetik | wasala | studiob | personal */
  client?: string;
  /** Filter by source: official | incident | policy | runbook | architecture | lessons-learned | acumatica-skill */
  source?: string;
}
```

Update `searchKnowledge` to include new filters in the must clauses:

```typescript
export async function searchKnowledge(
  qdrantUrl: string,
  queryVector: number[],
  limit = 10,
  filter?: SearchFilter,
  collectionName: string = STUDIOB_COLLECTION,
): Promise<SearchResult[]> {
  const body: Record<string, unknown> = {
    vector: queryVector,
    limit,
    with_payload: true,
  };

  if (filter) {
    const mustClauses: Array<Record<string, unknown>> = [];
    const filterKeys: Array<keyof SearchFilter> = ['topic', 'version', 'domain', 'client', 'source'];

    for (const key of filterKeys) {
      if (filter[key]) {
        mustClauses.push({ key, match: { value: filter[key] } });
      }
    }

    if (mustClauses.length > 0) {
      body.filter = { must: mustClauses };
    }
  }

  // ... rest unchanged
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/kevin/code/studio-b/heritage-fabrics/acudev && npx vitest run src/ingest/__tests__/collection-migration.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ingest/qdrant-ingest.ts src/ingest/__tests__/collection-migration.test.ts
git commit -m "feat: extend SearchFilter with domain/client/source tags"
```

---

### Task 9: Write migration script — copy acudev-knowledge → studiob-knowledge with tags

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/ingest/migrate-collection.ts`

**Step 1: Write the migration script**

```typescript
/**
 * One-time migration: copy all points from acudev-knowledge to studiob-knowledge
 * with domain/client/source tags added to each payload.
 *
 * Usage:
 *   QDRANT_URL=... npx tsx src/ingest/migrate-collection.ts [--dry-run]
 *
 * Safe to re-run (upsert is idempotent).
 */

const BATCH_SIZE = 100;
const SOURCE_COLLECTION = 'acudev-knowledge';
const TARGET_COLLECTION = 'studiob-knowledge';

interface Point {
  id: string;
  vector: number[];
  payload: Record<string, unknown>;
}

/**
 * Infer domain/client/source tags from existing payload metadata.
 */
function inferTags(payload: Record<string, unknown>): {
  domain: string;
  client: string | null;
  source: string;
} {
  const existingSource = (payload.source as string) || '';

  // Source mapping
  let source = 'official';
  if (existingSource === 'lessons-learned') source = 'incident';
  else if (existingSource === 'acumatica-skill') source = 'runbook';
  else if (existingSource === 'acumatica-community') source = 'official';
  else if (existingSource === 'stackoverflow') source = 'official';
  else if (existingSource.includes('help-portal')) source = 'official';
  else if (existingSource.includes('examples')) source = 'official';

  // Domain: almost everything in acudev-knowledge is acumatica domain
  const domain = 'acumatica';

  // Client: acudev-knowledge is generic Acumatica docs, not client-specific
  const client = null;

  return { domain, client, source };
}

async function scrollCollection(
  qdrantUrl: string,
  collection: string,
  offset: string | null,
  limit: number,
): Promise<{ points: Point[]; next_page_offset: string | null }> {
  const body: Record<string, unknown> = {
    limit,
    with_payload: true,
    with_vector: true,
  };
  if (offset) body.offset = offset;

  const res = await fetch(`${qdrantUrl}/collections/${collection}/points/scroll`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) throw new Error(`Scroll failed: ${res.status} ${await res.text()}`);
  const json = await res.json() as {
    result: { points: Point[]; next_page_offset: string | null };
  };
  return json.result;
}

async function upsertBatch(
  qdrantUrl: string,
  collection: string,
  points: Point[],
): Promise<void> {
  const res = await fetch(`${qdrantUrl}/collections/${collection}/points`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ points }),
  });
  if (!res.ok) throw new Error(`Upsert failed: ${res.status} ${await res.text()}`);
}

async function main() {
  const qdrantUrl = process.env.QDRANT_URL;
  if (!qdrantUrl) throw new Error('QDRANT_URL required');

  const dryRun = process.argv.includes('--dry-run');

  console.log(`Migrating ${SOURCE_COLLECTION} → ${TARGET_COLLECTION}`);
  if (dryRun) console.log('DRY RUN — no writes');

  // Ensure target collection exists (same vector config)
  const check = await fetch(`${qdrantUrl}/collections/${TARGET_COLLECTION}`);
  if (!check.ok) {
    console.log(`Creating ${TARGET_COLLECTION}...`);
    if (!dryRun) {
      const res = await fetch(`${qdrantUrl}/collections/${TARGET_COLLECTION}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vectors: { size: 1024, distance: 'Cosine' } }),
      });
      if (!res.ok) throw new Error(`Create collection failed: ${await res.text()}`);
    }
  }

  let offset: string | null = null;
  let totalMigrated = 0;
  let tagCounts: Record<string, number> = {};

  do {
    const { points, next_page_offset } = await scrollCollection(
      qdrantUrl, SOURCE_COLLECTION, offset, BATCH_SIZE,
    );

    if (points.length === 0) break;

    // Add tags to each point
    const taggedPoints = points.map((p) => {
      const tags = inferTags(p.payload);
      return {
        id: p.id,
        vector: p.vector,
        payload: {
          ...p.payload,
          domain: tags.domain,
          client: tags.client,
          source_type: tags.source,  // renamed to avoid collision with existing 'source' field
        },
      };
    });

    if (!dryRun) {
      await upsertBatch(qdrantUrl, TARGET_COLLECTION, taggedPoints);
    }

    totalMigrated += points.length;

    // Track tag distribution
    for (const p of taggedPoints) {
      const key = `${p.payload.domain}/${p.payload.source_type}`;
      tagCounts[key] = (tagCounts[key] || 0) + 1;
    }

    console.log(`  Migrated ${totalMigrated} points...`);
    offset = next_page_offset;
  } while (offset);

  console.log(`\nMigration complete: ${totalMigrated} points`);
  console.log('Tag distribution:');
  for (const [key, count] of Object.entries(tagCounts).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${key}: ${count}`);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

**Step 2: Test with --dry-run**

Run:
```bash
cd /Users/kevin/code/studio-b/heritage-fabrics/acudev
railway link -p studiob-platform
export QDRANT_URL=$(railway variables --service qdrant --json | python3 -c "import sys,json; print(json.load(sys.stdin)['QDRANT_URL'])")
npx tsx src/ingest/migrate-collection.ts --dry-run
```

Expected: Scrolls through acudev-knowledge, prints point count and tag distribution, no writes.

**Step 3: Run the real migration**

Run: `npx tsx src/ingest/migrate-collection.ts`
Expected: ~126K points migrated with domain=acumatica tags.

**Step 4: Verify migration**

```bash
# Check point count in studiob-knowledge
curl -s "$QDRANT_URL/collections/studiob-knowledge" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Points: {d[\"result\"][\"points_count\"]}')"
```

Expected: ~126K + the existing 53 operational points = ~126K+ total.

**Step 5: Commit**

```bash
git add src/ingest/migrate-collection.ts
git commit -m "feat: migration script for acudev-knowledge → studiob-knowledge"
```

---

### Task 10: Update ingestion endpoint default tags

**Files:**
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/ingest/ingest-orchestrator.ts`
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/ingest/pdf-extractor.ts` (if metadata is built there)

**Step 1: Review how metadata is attached during ingestion**

Read the ingestion orchestrator to find where `source`, `version`, `topic` are set. All new ingestions must include `domain`, `client`, `source_type` tags.

**Step 2: Add default tags to the PDF ingestion pipeline**

In the orchestrator, wherever chunks are built, ensure they include:

```typescript
// Add to every chunk's metadata before upsert
const enrichedChunks = chunks.map(c => ({
  ...c,
  metadata: {
    ...c.metadata,
    domain: 'acumatica',
    client: null,           // generic docs aren't client-specific
    source_type: 'official', // PDFs and help portal are official docs
  },
}));
```

**Step 3: Add default tags to lessons-learned ingestion**

In the lessons-ingestion path:

```typescript
metadata: {
  ...existingMetadata,
  domain: 'pipeline',       // lessons are about pipeline operations
  client: 'aesthetik',      // HF-specific lessons
  source_type: 'incident',  // these are incident lessons
}
```

**Step 4: Add default tags to community/SO ingestion**

```typescript
// Community forum
metadata: { ...existing, domain: 'acumatica', client: null, source_type: 'official' }

// Stack Overflow
metadata: { ...existing, domain: 'acumatica', client: null, source_type: 'official' }
```

**Step 5: Run existing tests**

Run: `cd /Users/kevin/code/studio-b/heritage-fabrics/acudev && npx vitest run`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/ingest/ingest-orchestrator.ts src/ingest/pdf-extractor.ts src/ingest/lessons-ingestion.ts
git commit -m "feat: add domain/client/source_type tags to all ingestion pipelines"
```

---

### Task 11: Add auto-ingestion endpoint for deploy incidents

**Files:**
- Modify: `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/index.ts`
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/ingest/incident-ingestion.ts`

**Step 1: Write the incident ingestion module**

```typescript
// src/ingest/incident-ingestion.ts
/**
 * Ingest deploy incident reports into studiob-knowledge.
 *
 * Called by the GitHub Actions workflow when a deploy fails or succeeds after recovery.
 * Each incident becomes 1-3 chunks with domain=pipeline, client=aesthetik, source_type=incident.
 */
import { embedAndUpsert, STUDIOB_COLLECTION } from './qdrant-ingest.js';

export interface DeployIncident {
  /** What happened: "publish_failed", "verification_failed", "recovery_succeeded" */
  event: string;
  /** Project name */
  project: string;
  /** Environment: "sandbox" | "production" */
  environment: string;
  /** Short commit SHA */
  commit: string;
  /** Error message or verification JSON */
  error_detail: string;
  /** What fix was applied (if any) */
  resolution?: string;
  /** GitHub Actions run URL */
  run_url: string;
  /** ISO timestamp */
  timestamp: string;
}

export async function ingestIncident(
  qdrantUrl: string,
  voyageApiKey: string,
  incident: DeployIncident,
): Promise<number> {
  const chunks: Array<{ text: string; metadata: object }> = [];

  // Chunk 1: The incident summary
  chunks.push({
    text: `Deploy incident: ${incident.event} on ${incident.project} (${incident.environment}). ` +
      `Commit: ${incident.commit}. Error: ${incident.error_detail}`,
    metadata: {
      domain: 'pipeline',
      client: 'aesthetik',
      source_type: 'incident',
      source: 'auto-ingestion',
      event: incident.event,
      project: incident.project,
      environment: incident.environment,
      commit: incident.commit,
      run_url: incident.run_url,
      timestamp: incident.timestamp,
    },
  });

  // Chunk 2: Resolution (if provided)
  if (incident.resolution) {
    chunks.push({
      text: `Resolution for ${incident.event} on ${incident.project}: ${incident.resolution}`,
      metadata: {
        domain: 'pipeline',
        client: 'aesthetik',
        source_type: 'incident',
        source: 'auto-ingestion',
        event: `${incident.event}_resolution`,
        project: incident.project,
        timestamp: incident.timestamp,
      },
    });
  }

  return embedAndUpsert(qdrantUrl, voyageApiKey, STUDIOB_COLLECTION, chunks);
}
```

**Step 2: Add the HTTP endpoint**

In `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/index.ts`, add:

```typescript
import { ingestIncident, DeployIncident } from './ingest/incident-ingestion.js';

// POST /ingest/incident — auto-ingestion from pipeline
app.post('/ingest/incident', async (request, reply) => {
  const incident = request.body as DeployIncident;

  if (!incident.event || !incident.project || !incident.error_detail) {
    return reply.status(400).send({ error: 'event, project, error_detail required' });
  }

  const qdrantUrl = process.env.QDRANT_URL!;
  const voyageApiKey = process.env.VOYAGE_API_KEY!;

  const count = await ingestIncident(qdrantUrl, voyageApiKey, incident);
  return { message: `Ingested ${count} chunks`, incident: incident.event };
});
```

**Step 3: Run existing tests**

Run: `cd /Users/kevin/code/studio-b/heritage-fabrics/acudev && npx vitest run`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/ingest/incident-ingestion.ts src/index.ts
git commit -m "feat: POST /ingest/incident endpoint for pipeline auto-ingestion"
```

---

## Stream A (continued): Wire auto-ingestion into the pipeline

### Task 12: Add auto-ingestion step to GitHub Actions workflow

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml`

**Step 1: Add ingestion step after verification failure alert**

After the "Alert on verification failure" step, add:

```yaml
      - name: Auto-ingest deploy incident
        if: >
          always() &&
          steps.deploy.outcome == 'success' &&
          steps.verify.outcome == 'failure'
        env:
          ACUDEV_URL: ${{ secrets.ACUDEV_URL }}
          ACUDEV_API_KEY: ${{ secrets.ACUDEV_API_KEY }}
        run: |
          # Read verify-result.json for structured error detail
          ERROR_DETAIL="Verification failed"
          if [ -f verify-result.json ]; then
            ERROR_DETAIL=$(cat verify-result.json | python3 -c "
          import sys, json
          d = json.load(sys.stdin)
          fails = [c for c in d.get('checks', []) if c['status'] == 'fail']
          print('; '.join(f\"{c['name']}: {c['detail']}\" for c in fails[:5]))
          " 2>/dev/null || echo "Verification failed — see logs")
          fi

          curl -sf -X POST "${ACUDEV_URL}/ingest/incident" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${ACUDEV_API_KEY}" \
            -d "{
              \"event\": \"verification_failed\",
              \"project\": \"${{ needs.build.outputs.project_name }}\",
              \"environment\": \"${{ steps.env.outputs.target }}\",
              \"commit\": \"${GITHUB_SHA::8}\",
              \"error_detail\": $(echo "$ERROR_DETAIL" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))'),
              \"run_url\": \"${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}\",
              \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
            }" || echo "[WARN] Auto-ingestion failed — non-blocking"
```

**Step 2: Add success ingestion (for recovery tracking)**

```yaml
      - name: Auto-ingest deploy success
        if: >
          steps.deploy.outcome == 'success' &&
          steps.verify.outcome == 'success' &&
          steps.env.outputs.target == 'production'
        env:
          ACUDEV_URL: ${{ secrets.ACUDEV_URL }}
          ACUDEV_API_KEY: ${{ secrets.ACUDEV_API_KEY }}
        run: |
          curl -sf -X POST "${ACUDEV_URL}/ingest/incident" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${ACUDEV_API_KEY}" \
            -d "{
              \"event\": \"deploy_succeeded\",
              \"project\": \"${{ needs.build.outputs.project_name }}\",
              \"environment\": \"production\",
              \"commit\": \"${GITHUB_SHA::8}\",
              \"error_detail\": \"All checks passed\",
              \"run_url\": \"${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}\",
              \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
            }" || echo "[WARN] Auto-ingestion failed — non-blocking"
```

**Step 3: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add .github/workflows/acuops-deploy.yml
git commit -m "feat: auto-ingest deploy incidents into studiob-knowledge"
```

---

### Task 13: Verify search quality across domains

**Files:**
- Create: `/Users/kevin/code/studio-b/heritage-fabrics/acudev/src/ingest/__tests__/search-quality.test.ts`

**Step 1: Write search quality tests**

```typescript
/**
 * Search quality tests — verify cross-domain retrieval.
 * These require a running Qdrant instance with migrated data.
 * Run manually: QDRANT_URL=... VOYAGE_API_KEY=... npx vitest run src/ingest/__tests__/search-quality.test.ts
 */
import { describe, it, expect } from 'vitest';
import { embedTexts, searchKnowledge, STUDIOB_COLLECTION } from '../qdrant-ingest.js';

const QDRANT_URL = process.env.QDRANT_URL;
const VOYAGE_API_KEY = process.env.VOYAGE_API_KEY;

describe.skipIf(!QDRANT_URL || !VOYAGE_API_KEY)('Search quality', () => {
  async function search(query: string, filter?: Record<string, string>) {
    const vectors = await embedTexts([query], VOYAGE_API_KEY!);
    return searchKnowledge(QDRANT_URL!, vectors[0], 5, filter, STUDIOB_COLLECTION);
  }

  it('finds Acumatica DAC extension docs', async () => {
    const results = await search('how to create a DAC extension in Acumatica', { domain: 'acumatica' });
    expect(results.length).toBeGreaterThan(0);
    expect(results[0].score).toBeGreaterThan(0.5);
  });

  it('finds pipeline incident patterns', async () => {
    const results = await search('why did publish break navigation', { domain: 'pipeline' });
    expect(results.length).toBeGreaterThan(0);
  });

  it('cross-domain query returns relevant results', async () => {
    const results = await search('publishBegin causes app pool restart timeout');
    expect(results.length).toBeGreaterThan(0);
    // Should find both Acumatica docs AND pipeline incidents
  });
});
```

**Step 2: Run manually against live Qdrant (after migration)**

Run:
```bash
cd /Users/kevin/code/studio-b/heritage-fabrics/acudev
export QDRANT_URL=$(railway variables --service qdrant --json | python3 -c "import sys,json; print(json.load(sys.stdin)['QDRANT_URL'])")
export VOYAGE_API_KEY=$(railway variables --service acudev --json | python3 -c "import sys,json; print(json.load(sys.stdin)['VOYAGE_API_KEY'])")
npx vitest run src/ingest/__tests__/search-quality.test.ts
```

**Step 3: Commit**

```bash
git add src/ingest/__tests__/search-quality.test.ts
git commit -m "test: search quality tests for cross-domain retrieval"
```

---

### Task 14: Deploy AcuDev service and delete acudev-knowledge

**Step 1: Deploy updated AcuDev to Railway**

```bash
cd /Users/kevin/code/studio-b/heritage-fabrics/acudev
git push origin main
# Railway auto-deploys from main
```

**Step 2: Verify AcuDev queries studiob-knowledge**

```bash
# Hit the AcuDev search endpoint and verify it returns results from studiob-knowledge
curl -s "${ACUDEV_URL}/search?q=DAC+extension" | python3 -c "
import sys,json
d = json.load(sys.stdin)
print(f'Results: {len(d.get(\"results\", []))}')
for r in d.get('results', [])[:3]:
    print(f'  score={r[\"score\"]:.3f} domain={r[\"payload\"].get(\"domain\",\"?\")} source={r[\"payload\"].get(\"source\",\"?\")}')"
```

**Step 3: Delete acudev-knowledge collection**

Only after confirming AcuDev works with studiob-knowledge:

```bash
export QDRANT_URL=$(railway variables --service qdrant --json | python3 -c "import sys,json; print(json.load(sys.stdin)['QDRANT_URL'])")
curl -X DELETE "$QDRANT_URL/collections/acudev-knowledge"
```

**Step 4: Verify deletion**

```bash
curl -s "$QDRANT_URL/collections" | python3 -c "
import sys,json
d = json.load(sys.stdin)
names = [c['name'] for c in d['result']['collections']]
print('Collections:', names)
assert 'acudev-knowledge' not in names, 'acudev-knowledge still exists!'
assert 'studiob-knowledge' in names, 'studiob-knowledge missing!'
print('OK — acudev-knowledge deleted, studiob-knowledge exists')
"
```

---

## GitHub Secrets Needed

Before Task 12 can work in CI, these secrets must be set in `acumatica-ci-cd` repo settings:

| Secret | Value | Purpose |
|--------|-------|---------|
| `ACUDEV_URL` | `https://acudev-production.up.railway.app` | AcuDev service URL |
| `ACUDEV_API_KEY` | (from Railway acudev service env) | Auth for ingestion endpoint |

---

## Execution Order

Tasks 1-6 (Stream A) and Tasks 7-11 (Stream B) are independent and can run in parallel.

Task 12 depends on both Task 6 (workflow updated) and Task 11 (ingestion endpoint exists).

Task 13 depends on Task 9 (migration complete).

Task 14 depends on Tasks 7-11 (AcuDev updated and deployed).

```
Stream A (acumatica-ci-cd):     Stream B (acudev):
  Task 1 ─┐                       Task 7 ─┐
  Task 2 ─┤                       Task 8 ─┤
  Task 3 ─┤ (parallel)            Task 9 ─┤ (parallel)
  Task 4 ─┤                       Task 10 ┤
  Task 5 ─┤                       Task 11 ┘
  Task 6 ─┘                          │
      │                               │
      └──────── Task 12 ─────────────┘
                   │
               Task 13
                   │
               Task 14
```
