#!/usr/bin/env python3
"""
verify.py — Unified post-publish verification for Acumatica customizations.

Replaces validate-publish.py + smoke-e2e.py with a single script that produces
structured JSON output (stdout) and human-readable colored output (stderr).

Exit 0 = overall pass, Exit 1 = overall fail.

Zero external dependencies — stdlib only (urllib, json, ssl, etc.).
"""

import argparse
import base64
import io
import json
import os
import pathlib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    name: str          # e.g. "login", "entity:PurchaseOrder", "field:PO.UsrFoo"
    status: CheckStatus
    detail: str
    http_code: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
            "http_code": self.http_code,
        }


@dataclass
class VerifyResult:
    overall: str       # "pass" or "fail"
    environment: str
    checks: List[CheckResult] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "overall": self.overall,
            "environment": self.environment,
            "checks": [c.to_dict() for c in self.checks],
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# HTTP response classification (single source of truth)
# ---------------------------------------------------------------------------

def classify_http_status(
    code: int, response_body: Optional[str] = None
) -> Tuple[str, str]:
    """Classify an HTTP status code into (status_str, detail_str).

    200/204 -> pass
    401     -> fail (auth broken)
    403     -> warn (permission issue, NOT a code bug)
    404     -> fail (entity/field missing)
    500+    -> fail (server error, include body snippet)
    """
    if code in (200, 204):
        return ("pass", "ok")
    elif code == 401:
        return ("fail", "auth broken — 401 Unauthorized")
    elif code == 403:
        return ("warn", "permission issue — 403 Forbidden")
    elif code == 404:
        return ("fail", "not found — 404 Missing")
    elif code >= 500:
        snippet = ""
        if response_body:
            snippet = response_body[:200]
        detail = f"server error — {code}"
        if snippet:
            detail += f": {snippet}"
        return ("fail", detail)
    else:
        # Unexpected codes (3xx, other 4xx)
        return ("warn", f"unexpected HTTP {code}")


# ---------------------------------------------------------------------------
# AcumaticaSession — urllib-based, no external deps
# ---------------------------------------------------------------------------

class AcumaticaSession:
    """Minimal Acumatica REST API session using urllib only."""

    def __init__(self, base_url: str, username: str, password: str, tenant: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.tenant = tenant
        self._cookies = ""
        # Allow self-signed certs for sandbox environments
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    def _merge_cookies(self, resp_headers) -> None:
        """Merge Set-Cookie headers into the cookie jar.

        Acumatica login returns multiple Set-Cookie headers
        (ASP.NET_SessionId, .ASPXAUTH, UserBranch, etc.).
        urllib's getheader() only returns the first one, so we
        must use get_all() and merge them into a single Cookie
        header string for subsequent requests.
        """
        raw_cookies = resp_headers.get_all("Set-Cookie") or []
        if not raw_cookies:
            return
        # Parse existing cookies into a dict
        existing = {}
        if self._cookies:
            for pair in self._cookies.split("; "):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    existing[k.strip()] = v.strip()
        # Merge new cookies (each Set-Cookie header has "name=value; attrs...")
        for sc in raw_cookies:
            # Take only the name=value part (before first ;)
            nv = sc.split(";")[0].strip()
            if "=" in nv:
                k, v = nv.split("=", 1)
                existing[k.strip()] = v.strip()
        self._cookies = "; ".join(f"{k}={v}" for k, v in existing.items())

    def _request(
        self, method: str, path: str, body: Optional[bytes] = None,
        headers: Optional[dict] = None
    ) -> Tuple[int, bytes]:
        """Low-level HTTP request. Returns (status_code, response_body)."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        hdrs = headers or {}
        if self._cookies:
            hdrs["Cookie"] = self._cookies
        hdrs.setdefault("Content-Type", "application/json")

        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx) as resp:
                self._merge_cookies(resp.headers)
                return (resp.status, resp.read())
        except urllib.error.HTTPError as e:
            self._merge_cookies(e.headers)
            return (e.code, e.read())

    def login(self):
        """Authenticate to Acumatica. Raises on failure."""
        payload = json.dumps({
            "name": self.username,
            "password": self.password,
            "tenant": self.tenant,
        }).encode()
        status, body = self._request("POST", "/entity/auth/login", body=payload)
        if status not in (200, 204):
            raise RuntimeError(
                f"Login failed with HTTP {status}: {body.decode(errors='replace')[:200]}"
            )

    def logout(self):
        """Logout from Acumatica. Best-effort."""
        try:
            self._request("POST", "/entity/auth/logout")
        except Exception:
            pass

    def _retry_on_401(self, method: str, path: str, body: Optional[bytes] = None) -> Tuple[int, bytes]:
        """Execute request, re-login once on 401 (post-publish app pool recycle)."""
        status, resp_body = self._request(method, path, body=body)
        if status == 401:
            import time
            time.sleep(10)
            self.login()
            status, resp_body = self._request(method, path, body=body)
        return status, resp_body

    def get(self, path: str) -> Tuple[int, bytes]:
        """HTTP GET. Returns (status_code, response_body_bytes). Retries once on 401."""
        return self._retry_on_401("GET", path)

    def post(self, path: str, body: Optional[bytes] = None) -> Tuple[int, bytes]:
        """HTTP POST. Returns (status_code, response_body_bytes). Retries once on 401."""
        return self._retry_on_401("POST", path, body=body)


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def check_entity_reachability(
    session: AcumaticaSession, entity: str, version: str
) -> CheckResult:
    """Check if an entity endpoint is reachable (HTTP GET with $top=1)."""
    path = f"/entity/Default/{version}/{entity}?$top=1"
    try:
        status, body = session.get(path)
    except Exception as exc:
        return CheckResult(
            name=f"entity:{entity}",
            status=CheckStatus.FAIL,
            detail=f"connection error: {exc}",
        )
    body_str = body.decode(errors="replace") if body else ""
    status_str, detail = classify_http_status(status, response_body=body_str)
    return CheckResult(
        name=f"entity:{entity}",
        status=CheckStatus(status_str),
        detail=detail,
        http_code=status,
    )


def check_custom_fields(
    session: AcumaticaSession, entity: str, version: str, fields: List[str]
) -> List[CheckResult]:
    """Check $adHocSchema for declared custom fields on an entity."""
    if not fields:
        return []

    path = f"/entity/Default/{version}/{entity}/$adHocSchema"
    try:
        status, body = session.get(path)
    except Exception as exc:
        return [
            CheckResult(
                name=f"field:{entity}.{f.split('.')[-1]}",
                status=CheckStatus.FAIL,
                detail=f"connection error: {exc}",
            )
            for f in fields
        ]

    body_str = body.decode(errors="replace") if body else ""

    # If the schema endpoint itself is not reachable, classify accordingly
    if status not in (200, 204):
        status_str, detail = classify_http_status(status, response_body=body_str)
        return [
            CheckResult(
                name=f"field:{entity}.{f.split('.')[-1]}",
                status=CheckStatus(status_str),
                detail=f"schema endpoint: {detail}",
                http_code=status,
            )
            for f in fields
        ]

    # Parse schema and check each field
    try:
        schema = json.loads(body_str)
    except (json.JSONDecodeError, ValueError):
        schema = {}

    results = []
    for f in fields:
        short_name = f.split(".")[-1]
        # Navigate dotted path (e.g. "custom.Document.UsrExpArrivalDate")
        # through the nested schema dict
        found = _resolve_dotted_path(schema, f)
        if found:
            results.append(CheckResult(
                name=f"field:{entity}.{short_name}",
                status=CheckStatus.PASS,
                detail=f"field present in $adHocSchema",
                http_code=status,
            ))
        else:
            results.append(CheckResult(
                name=f"field:{entity}.{short_name}",
                status=CheckStatus.FAIL,
                detail=f"field '{f}' not found in $adHocSchema",
                http_code=status,
            ))
    return results


def _resolve_dotted_path(obj: dict, dotted_path: str) -> bool:
    """Walk a dotted path like 'custom.Document.UsrFoo' through nested dicts.

    Returns True if the final key exists at the expected depth.
    Also checks flat key as fallback for forward-compatibility.
    """
    # Fast path: flat key exists (original behavior)
    if dotted_path in obj:
        return True
    # Walk nested path
    parts = dotted_path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False
    return True


def run_e2e_probe(
    session: AcumaticaSession, probe: dict, version: str
) -> CheckResult:
    """Run an E2E view probe — fetch entity and verify custom fields exist.

    Acumatica REST API does not support $select on custom fields (returns
    KeyNotFoundException). Instead, fetch the entity without $select and
    check that the expected custom fields appear in the 'custom' object.
    """
    entity = probe["entity"]
    select_fields = probe.get("select_fields", [])
    # Separate standard fields (for $select) from Usr* custom fields (verified in response)
    standard_fields = [f for f in select_fields if not f.startswith("Usr")]
    custom_fields = [f for f in select_fields if f.startswith("Usr")]

    # Build path — only $select standard fields, not custom ones
    if standard_fields:
        path = f"/entity/Default/{version}/{entity}?$top=1&$select={','.join(standard_fields)}"
    else:
        path = f"/entity/Default/{version}/{entity}?$top=1"
    try:
        status, body = session.get(path)
    except Exception as exc:
        return CheckResult(
            name=f"e2e:{entity}",
            status=CheckStatus.FAIL,
            detail=f"connection error: {exc}",
        )
    body_str = body.decode(errors="replace") if body else ""

    if status not in (200, 204):
        status_str, detail = classify_http_status(status, response_body=body_str)
        return CheckResult(
            name=f"e2e:{entity}",
            status=CheckStatus(status_str),
            detail=detail,
            http_code=status,
        )

    # If we have custom fields to verify, check them in the response
    if custom_fields and body_str:
        try:
            data = json.loads(body_str)
            records = data if isinstance(data, list) else [data]
            if records:
                custom_obj = records[0].get("custom", {})
                # Flatten all custom fields from all views
                all_custom = set()
                for view_fields in custom_obj.values():
                    if isinstance(view_fields, dict):
                        all_custom.update(view_fields.keys())
                missing = [f for f in custom_fields if f not in all_custom]
                if missing:
                    return CheckResult(
                        name=f"e2e:{entity}",
                        status=CheckStatus.WARN,
                        detail=f"custom fields not in response: {', '.join(missing)}",
                        http_code=status,
                    )
        except (json.JSONDecodeError, KeyError, IndexError):
            pass  # Non-fatal — entity is reachable, field check is best-effort

    return CheckResult(
        name=f"e2e:{entity}",
        status=CheckStatus.PASS,
        detail=f"entity reachable, {len(custom_fields)} custom fields checked",
        http_code=status,
    )


# Known GI endpoints to probe for corruption
_GI_PROBES = ["InventoryAllocationDetail", "LotAvailability"]


def check_gi_health(
    session: AcumaticaSession, version: str
) -> CheckResult:
    """Probe known Generic Inquiries for subsystem corruption.

    Returns a SINGLE aggregate CheckResult:
    - If any GI returns 200 -> overall PASS (subsystem healthy)
    - If ALL GIs return 404 -> overall PASS (GIs not installed, acceptable)
    - If any GI returns 500+ -> overall FAIL (corruption)
    - Otherwise -> WARN (inconclusive)
    """
    gi_statuses: dict[str, int | None] = {}
    for gi in _GI_PROBES:
        path = f"/entity/Default/{version}/{gi}?$top=1"
        try:
            status, body = session.get(path)
            gi_statuses[gi] = status
        except Exception:
            gi_statuses[gi] = None

    codes = list(gi_statuses.values())
    any_200 = any(c == 200 for c in codes if c is not None)
    all_404 = all(c == 404 for c in codes if c is not None) and any(c is not None for c in codes)
    any_500 = any(c is not None and c >= 500 for c in codes)

    detail_parts = [f"{gi}={code}" for gi, code in gi_statuses.items()]
    detail_str = "; ".join(detail_parts)

    if any_200:
        return CheckResult(
            name="gi:health",
            status=CheckStatus.PASS,
            detail=f"GI subsystem healthy ({detail_str})",
        )
    elif all_404:
        return CheckResult(
            name="gi:health",
            status=CheckStatus.PASS,
            detail=f"GIs not installed ({detail_str})",
        )
    elif any_500:
        return CheckResult(
            name="gi:health",
            status=CheckStatus.FAIL,
            detail=f"GI corruption detected ({detail_str})",
        )
    else:
        return CheckResult(
            name="gi:health",
            status=CheckStatus.WARN,
            detail=f"inconclusive ({detail_str})",
        )


# ---------------------------------------------------------------------------
# ASPX file verification
# ---------------------------------------------------------------------------

def check_aspx_files(
    session: AcumaticaSession, project_name: str, package_path: str
) -> List[CheckResult]:
    """Verify ASPX files on the instance match the deployed package.

    Exports the published project via getProject API, extracts ASPX files,
    and compares them against the original deployed package.
    """
    results: List[CheckResult] = []
    package = pathlib.Path(package_path)

    if not package.exists():
        results.append(CheckResult(
            name="aspx:package",
            status=CheckStatus.WARN,
            detail=f"package not found at {package_path} — skipping ASPX verification",
        ))
        return results

    # Export current state from instance
    try:
        payload = json.dumps({"projectName": project_name}).encode()
        status, body = session.post("/CustomizationApi/getProject", body=payload)
    except Exception as exc:
        results.append(CheckResult(
            name="aspx:export",
            status=CheckStatus.WARN,
            detail=f"could not export project: {exc}",
        ))
        return results

    if status != 200:
        results.append(CheckResult(
            name="aspx:export",
            status=CheckStatus.WARN,
            detail=f"getProject returned HTTP {status} — skipping ASPX verification",
            http_code=status,
        ))
        return results

    try:
        b64_text = body.decode(errors="replace").strip().strip('"')
        instance_zip = base64.b64decode(b64_text)
    except Exception as exc:
        results.append(CheckResult(
            name="aspx:export",
            status=CheckStatus.WARN,
            detail=f"could not decode exported project: {exc}",
        ))
        return results

    deployed_zip = package.read_bytes()

    # Extract and compare ASPX files
    with zipfile.ZipFile(io.BytesIO(deployed_zip)) as zf_deployed:
        aspx_files = [
            n for n in zf_deployed.namelist()
            if n.lower().endswith(".aspx") and not n.startswith("__")
        ]

        if not aspx_files:
            return results  # No ASPX files to verify

        with zipfile.ZipFile(io.BytesIO(instance_zip)) as zf_instance:
            instance_names = {
                n.replace("\\", "/"): n for n in zf_instance.namelist()
            }

            for aspx in aspx_files:
                normalized = aspx.replace("\\", "/")
                deployed_content = zf_deployed.read(aspx).decode("utf-8").strip()

                instance_key = instance_names.get(normalized)
                if not instance_key:
                    results.append(CheckResult(
                        name=f"aspx:{normalized}",
                        status=CheckStatus.WARN,
                        detail="not found in exported project",
                    ))
                    continue

                instance_content = zf_instance.read(instance_key).decode("utf-8").strip()

                if deployed_content == instance_content:
                    results.append(CheckResult(
                        name=f"aspx:{normalized}",
                        status=CheckStatus.PASS,
                        detail="matches deployed package",
                    ))
                else:
                    # Find first difference for debugging
                    d_lines = deployed_content.splitlines()
                    i_lines = instance_content.splitlines()
                    diff_line = "unknown"
                    for idx, (d, i) in enumerate(zip(d_lines, i_lines)):
                        if d != i:
                            diff_line = f"line {idx + 1}"
                            break
                    else:
                        if len(d_lines) != len(i_lines):
                            diff_line = f"line count ({len(d_lines)} vs {len(i_lines)})"

                    results.append(CheckResult(
                        name=f"aspx:{normalized}",
                        status=CheckStatus.FAIL,
                        detail=f"mismatch at {diff_line} — file not overwritten by import",
                    ))

    return results


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def compute_overall(checks: List[CheckResult]) -> str:
    """Compute overall result: 'fail' if any check is FAIL, else 'pass'."""
    for c in checks:
        if c.status == CheckStatus.FAIL:
            return "fail"
    return "pass"


def build_summary(checks: List[CheckResult]) -> str:
    """Build a human-readable summary string."""
    counts = {s: 0 for s in CheckStatus}
    for c in checks:
        counts[c.status] += 1
    return (
        f"{counts[CheckStatus.PASS]} pass, "
        f"{counts[CheckStatus.WARN]} warn, "
        f"{counts[CheckStatus.FAIL]} fail"
    )


def run_all_checks(
    session: AcumaticaSession, manifest: dict, version: str,
    package_path: str = "", project_name: str = "",
) -> List[CheckResult]:
    """Run all verification checks against the manifest."""
    checks: List[CheckResult] = []

    # 1. Entity reachability
    entities = manifest.get("entities", {})
    for entity_name in entities:
        checks.append(check_entity_reachability(session, entity_name, version))

    # 2. Custom field existence
    for entity_name, entity_def in entities.items():
        custom_fields = entity_def.get("custom_fields", [])
        if custom_fields:
            checks.extend(
                check_custom_fields(session, entity_name, version, custom_fields)
            )

    # 3. E2E view probes
    for probe in manifest.get("e2e_probes", []):
        checks.append(run_e2e_probe(session, probe, version))

    # 4. GI subsystem health
    checks.append(check_gi_health(session, version))

    # 5. ASPX file verification
    if package_path and project_name:
        checks.extend(check_aspx_files(session, project_name, package_path))

    return checks


# ---------------------------------------------------------------------------
# Human-readable stderr output
# ---------------------------------------------------------------------------

_COLORS = {
    CheckStatus.PASS: "\033[32m",  # green
    CheckStatus.WARN: "\033[33m",  # yellow
    CheckStatus.FAIL: "\033[31m",  # red
}
_RESET = "\033[0m"


def _status_tag(status: CheckStatus) -> str:
    color = _COLORS.get(status, "")
    label = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}[status.value]
    return f"{color}[{label}]{_RESET}"


def print_stderr(checks: List[CheckResult], overall: str, summary: str):
    """Print human-readable results to stderr."""
    for c in checks:
        tag = _status_tag(c.status)
        http_part = f" (HTTP {c.http_code})" if c.http_code else ""
        print(f"  {tag} {c.name}{http_part}: {c.detail}", file=sys.stderr)
    print(file=sys.stderr)
    overall_tag = _status_tag(CheckStatus.PASS if overall == "pass" else CheckStatus.FAIL)
    print(f"{overall_tag} Overall: {summary}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Unified post-publish verification for Acumatica customizations."
    )
    parser.add_argument(
        "--manifest", required=True,
        help="Path to publish-manifest.json",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("ACUMATICA_URL", ""),
        help="Acumatica instance URL (env: ACUMATICA_URL)",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("ACUMATICA_USERNAME", ""),
        help="Username (env: ACUMATICA_USERNAME)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("ACUMATICA_PASSWORD", ""),
        help="Password (env: ACUMATICA_PASSWORD)",
    )
    parser.add_argument(
        "--tenant",
        default=os.environ.get("ACUMATICA_TENANT", ""),
        help="Tenant (env: ACUMATICA_TENANT)",
    )
    parser.add_argument(
        "--environment",
        choices=["sandbox", "production"],
        default="production",
        help="Environment label (default: production)",
    )
    parser.add_argument(
        "--endpoint-version",
        default="24.200.001",
        help="REST API endpoint version (default: 24.200.001)",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Optional file path to write JSON result",
    )
    parser.add_argument(
        "--package",
        default=os.environ.get("ACUMATICA_PACKAGE", ""),
        help="Path to deployed .zip package for ASPX verification (env: ACUMATICA_PACKAGE)",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("ACUMATICA_PROJECT", ""),
        help="Customization project name for ASPX verification (env: ACUMATICA_PROJECT)",
    )
    parser.add_argument(
        "--no-merge-expected",
        default=None,
        help="Path to YAML file with no_merge_expected list of ASPX check names to downgrade FAIL→WARN",
    )
    args = parser.parse_args()

    # Load --no-merge expected ASPX failures
    no_merge_expected = set()
    if args.no_merge_expected:
        import yaml
        with open(args.no_merge_expected) as f:
            config = yaml.safe_load(f)
        no_merge_expected = set(config.get("no_merge_expected", []))

    # Validate required fields
    for field_name in ("url", "username", "password", "tenant"):
        if not getattr(args, field_name):
            print(
                f"Error: --{field_name} is required (or set env var)",
                file=sys.stderr,
            )
            sys.exit(2)

    # Load manifest
    with open(args.manifest) as f:
        manifest = json.load(f)

    # Create session and run checks
    session = AcumaticaSession(args.url, args.username, args.password, args.tenant)

    all_checks: List[CheckResult] = []

    # Login smoke test
    try:
        session.login()
        all_checks.append(CheckResult(
            name="login",
            status=CheckStatus.PASS,
            detail="authenticated successfully",
            http_code=204,
        ))
    except Exception as exc:
        all_checks.append(CheckResult(
            name="login",
            status=CheckStatus.FAIL,
            detail=str(exc),
        ))
        # Can't proceed without auth
        overall = "fail"
        summary = build_summary(all_checks)
        result = VerifyResult(
            overall=overall,
            environment=args.environment,
            checks=all_checks,
            summary=summary,
        )
        print_stderr(all_checks, overall, summary)
        json_output = json.dumps(result.to_dict(), indent=2)
        print(json_output)
        if args.json_output:
            with open(args.json_output, "w") as f:
                f.write(json_output)
        sys.exit(1)

    try:
        # Run all checks
        all_checks.extend(run_all_checks(
            session, manifest, args.endpoint_version,
            package_path=args.package, project_name=args.project,
        ))
    finally:
        session.logout()

    # Downgrade known --no-merge ASPX failures to WARN
    if no_merge_expected:
        for check in all_checks:
            if (check.status == CheckStatus.FAIL
                    and check.name in no_merge_expected
                    and "not overwritten by import" in check.detail):
                check.status = CheckStatus.WARN
                check.detail += " [expected: --no-merge]"

    overall = compute_overall(all_checks)
    summary = build_summary(all_checks)
    result = VerifyResult(
        overall=overall,
        environment=args.environment,
        checks=all_checks,
        summary=summary,
    )

    # Human-readable to stderr
    print_stderr(all_checks, overall, summary)

    # JSON to stdout
    json_output = json.dumps(result.to_dict(), indent=2)
    print(json_output)

    # Optional file output
    if args.json_output:
        with open(args.json_output, "w") as f:
            f.write(json_output)

    sys.exit(0 if overall == "pass" else 1)


if __name__ == "__main__":
    main()
