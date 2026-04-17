#!/usr/bin/env python3
"""Post-deploy NRE probe — detects the 2026-04-17 class of Acumatica outage.

After a successful `publishBegin/publishEnd` cycle the Acumatica app pool's
in-memory DAC / UserRecords registry can be poisoned such that the next
`CustProject` write returns HTTP 500 with `NullReferenceException` in
`UserRecordsDBUpdater.UpdateFavoriteRecordsCachedContentForAllUsers`.

The publish itself reports `isCompleted=true, isFailed=false`, so the deploy
pipeline sees "success" while the *next* code path that touches the Customization
API is broken. On 2026-04-17 this left heritagefabrics.acumatica.com in a
14-hour partial outage (reads fine, admin writes dead).

This script closes that gap. It performs a minimal Import + delete cycle
against the production instance right after the publish reports success.
If either response body contains the `NullReferenceException` marker, the
deploy just landed a poisoned state and this script exits 1 so the
workflow job fails.

References:
  - docs/AAR-2026-04-17-custproject-nre-transient.md (full AAR)
  - CLAUDE.md rule #18 (NRE in-memory signature + diagnostic)
  - ops/orphan-cleanup/cleanup-orphans.py (same NRE substring check)
  - scripts/qualify.py -> check_orphan_scan (identical heuristic)

Usage (from acuops-deploy.yml):
    python3 scripts/post-deploy-probe.py --name HealthProbe20260417160000
    python3 scripts/post-deploy-probe.py --cleanup --name HealthProbe20260417160000

Env vars required:
    ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT

Env vars used for the Slack alert (optional, probe still runs without them):
    SLACK_WEBHOOK_URL   — incoming webhook (alert skipped if empty)
    GITHUB_RUN_URL      — link back to the workflow run
    GITHUB_SHA          — deploy commit
    PR_NUMBER           — associated PR (if any)

Exit codes:
    0  Probe passed — CustProject write path is healthy
    1  Probe failed — NullReferenceException detected (Rule #18 signature)
    2  Probe errored — bad args, missing env, unreachable instance, etc.
"""
import argparse
import base64
import io
import os
import re
import sys
import zipfile

import requests  # type: ignore


NRE_MARKER = "NullReferenceException"
SLACK_PREVIEW_LEN = 400
LOGIN_TIMEOUT = 30
IMPORT_TIMEOUT = 60
DELETE_TIMEOUT = 60
SLACK_TIMEOUT = 15

STUB_PROJECT_XML = (
    b'<?xml version="1.0" encoding="utf-8"?>\n'
    b'<Customization level="0" description="post-deploy probe" '
    b'product-version="24.208"></Customization>\n'
)


def build_stub_zip() -> bytes:
    """Minimal Acumatica customization package — just project.xml, no artifacts."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.xml", STUB_PROJECT_XML)
    return buf.getvalue()


class AcuClient:
    def __init__(self, base_url: str, username: str, password: str, tenant: str):
        self.base = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.tenant = tenant
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"

    def login(self) -> None:
        r = self.session.post(
            f"{self.base}/entity/auth/login",
            json={
                "name": self.username,
                "password": self.password,
                "company": self.tenant,
            },
            timeout=LOGIN_TIMEOUT,
        )
        r.raise_for_status()

    def logout(self) -> None:
        try:
            self.session.post(f"{self.base}/entity/auth/logout", timeout=10)
        except Exception:
            pass

    def import_stub(self, name: str, content_b64: str) -> dict:
        r = self.session.post(
            f"{self.base}/CustomizationApi/Import",
            json={
                "projectName": name,
                "projectDescription": "post-deploy NRE probe (Rule #18)",
                "projectLevel": 0,
                "isReplaceIfExists": True,
                "projectContentBase64": content_b64,
            },
            timeout=IMPORT_TIMEOUT,
        )
        return {"http_code": r.status_code, "body": r.text or ""}

    def delete_project(self, name: str) -> dict:
        r = self.session.post(
            f"{self.base}/CustomizationApi/delete",
            json={"projectName": name},
            timeout=DELETE_TIMEOUT,
        )
        return {"http_code": r.status_code, "body": r.text or ""}


def scrub_tokens(text: str) -> str:
    """Best-effort scrub for Slack alert body.

    The probe only sees CLR exception stacks, not HTTP headers, so most
    sensitive data isn't in the text to begin with. Guard against future
    regressions that include Authorization/password/Set-Cookie anyway.
    """
    text = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)\S+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(password['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(set-cookie\s*:\s*)[^\r\n]+",
        r"\1[REDACTED]",
        text,
    )
    return text


def post_slack_alert(
    webhook: str,
    *,
    sha: str,
    pr_number: str,
    run_url: str,
    phase: str,
    body_excerpt: str,
) -> None:
    if not webhook:
        print("⚠️  SLACK_WEBHOOK_URL not set — skipping Slack alert", file=sys.stderr)
        return

    excerpt = scrub_tokens(body_excerpt)[:SLACK_PREVIEW_LEN]
    sha_short = (sha or "")[:8] or "(unknown)"
    pr_ref = f"PR #{pr_number}" if pr_number else "(non-PR deploy)"
    run_link = f"<{run_url}|open workflow run>" if run_url else "(no run url)"
    remediation = (
        "Publish reported success but post-deploy Import probe hit NRE. "
        "Force a full `isOnlyDbUpdates=false` republish of any managed "
        "package to restart the app pool (see CLAUDE.md rule #18 corollary). "
        "Do NOT retry this deploy until the probe passes."
    )
    payload = {
        "text": f":rotating_light: Post-deploy NRE probe FAILED — {sha_short} ({pr_ref})",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 Post-deploy NRE probe FAILED (Rule #18)",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*SHA*\n`{sha_short}`"},
                    {"type": "mrkdwn", "text": f"*PR*\n{pr_ref}"},
                    {"type": "mrkdwn", "text": f"*Phase*\n{phase}"},
                    {"type": "mrkdwn", "text": f"*Run*\n{run_link}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Stack (first {SLACK_PREVIEW_LEN} chars, tokens scrubbed):*\n"
                        f"```{excerpt}```"
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Remediation:* {remediation}",
                },
            },
        ],
    }
    try:
        r = requests.post(webhook, json=payload, timeout=SLACK_TIMEOUT)
        if r.status_code != 200:
            print(
                f"⚠️  Slack webhook returned {r.status_code}: {r.text[:200]}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"⚠️  Slack webhook failed: {e}", file=sys.stderr)


def require_env(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        print(f"ERROR: {name} is required", file=sys.stderr)
        sys.exit(2)
    return val


def validate_project_name(name: str) -> None:
    """Acumatica rejects non-alphanumeric project names (verified 2026-04-17).

    In particular, underscores and hyphens trigger CstDbStorage.ValidatePackageName
    rejection. HealthProbe<timestamp> format stays inside the allowed set.
    """
    if not name:
        print("ERROR: --name must not be empty", file=sys.stderr)
        sys.exit(2)
    if not name.isalnum():
        print(
            f"ERROR: --name must be alphanumeric (got: {name!r}). "
            f"Acumatica rejects underscores and hyphens in project names.",
            file=sys.stderr,
        )
        sys.exit(2)


def run_probe(name: str) -> int:
    base_url = require_env("ACUMATICA_URL").rstrip("/")
    username = require_env("ACUMATICA_USERNAME")
    password = require_env("ACUMATICA_PASSWORD")
    tenant = require_env("ACUMATICA_TENANT")

    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    run_url = os.environ.get("GITHUB_RUN_URL", "")
    sha = os.environ.get("GITHUB_SHA", "")
    pr_number = os.environ.get("PR_NUMBER", "")

    print("── Post-deploy NRE probe (Rule #18) ──")
    print(f"Instance: {base_url}")
    print(f"Tenant:   {tenant}")
    print(f"Probe:    {name}")
    print()

    client = AcuClient(base_url, username, password, tenant)
    stub_b64 = base64.b64encode(build_stub_zip()).decode("ascii")

    nre_found = False
    failure_phase = ""
    failure_body = ""

    try:
        client.login()
        print("✓ Logged in")

        # ── Phase 1: Import ────────────────────────────────────────────
        print(f"→ POST /CustomizationApi/Import  {name}")
        try:
            imp = client.import_stub(name, stub_b64)
            print(f"  HTTP {imp['http_code']}, body {len(imp['body'])} bytes")
            if NRE_MARKER in imp["body"]:
                nre_found = True
                failure_phase = "Import"
                failure_body = imp["body"]
                print(f"  ❌ {NRE_MARKER} detected in Import response")
        except requests.Timeout:
            print(f"  ❌ Import timed out after {IMPORT_TIMEOUT}s")
            return 2
        except Exception as e:
            print(f"  ❌ Import raised: {e}")
            return 2

        # ── Phase 2: Delete ─────────────────────────────────────────────
        # Always attempt even if Import hit NRE: (a) the delete body also
        # gets checked, (b) cleans up the stub row on the instance.
        print(f"→ POST /CustomizationApi/delete  {name}")
        try:
            d = client.delete_project(name)
            print(f"  HTTP {d['http_code']}, body {len(d['body'])} bytes")
            if NRE_MARKER in d["body"]:
                nre_found = True
                if not failure_phase:
                    failure_phase = "Delete"
                    failure_body = d["body"]
                else:
                    failure_phase = "Import+Delete"
                print(f"  ❌ {NRE_MARKER} detected in Delete response")
        except requests.Timeout:
            print(f"  ⚠️  Delete timed out after {DELETE_TIMEOUT}s — cleanup step will retry")
        except Exception as e:
            print(f"  ⚠️  Delete raised: {e} — cleanup step will retry")
    finally:
        client.logout()

    print()
    if nre_found:
        print(f"❌ POST-DEPLOY NRE PROBE FAILED — {failure_phase} phase returned {NRE_MARKER}")
        print("   This is the Rule #18 in-memory app-pool state corruption signature.")
        print("   The publish reported success but the instance is poisoned.")
        print("   See docs/AAR-2026-04-17-custproject-nre-transient.md")
        post_slack_alert(
            webhook,
            sha=sha,
            pr_number=pr_number,
            run_url=run_url,
            phase=failure_phase,
            body_excerpt=failure_body,
        )
        return 1

    print("✅ POST-DEPLOY NRE PROBE PASSED — CustProject write path is healthy.")
    return 0


def run_cleanup(name: str) -> int:
    """Idempotent delete of the probe stub.

    Always returns 0 — this runs in `if: always()` and must not mask the
    real probe failure. Second delete of an already-deleted stub just
    returns "not found", which is fine.
    """
    missing = [
        v
        for v in ("ACUMATICA_URL", "ACUMATICA_USERNAME", "ACUMATICA_PASSWORD", "ACUMATICA_TENANT")
        if not os.environ.get(v)
    ]
    if missing:
        print(f"⚠️  Cleanup skipped — missing env vars: {', '.join(missing)}")
        return 0

    base_url = os.environ["ACUMATICA_URL"].rstrip("/")
    username = os.environ["ACUMATICA_USERNAME"]
    password = os.environ["ACUMATICA_PASSWORD"]
    tenant = os.environ["ACUMATICA_TENANT"]

    print(f"── Post-deploy probe cleanup — {name} ──")
    client = AcuClient(base_url, username, password, tenant)
    try:
        client.login()
        try:
            d = client.delete_project(name)
            print(f"  HTTP {d['http_code']} — delete sent (idempotent)")
        except Exception as e:
            print(f"  ⚠️  Delete failed (ignored): {e}")
    except Exception as e:
        print(f"  ⚠️  Cleanup login failed (ignored): {e}")
    finally:
        client.logout()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Post-deploy NullReferenceException probe (Rule #18)."
    )
    ap.add_argument(
        "--name",
        required=True,
        help="Stub project name, e.g. HealthProbe20260417160000 "
        "(must be alphanumeric — Acumatica rejects underscores/hyphens).",
    )
    ap.add_argument(
        "--cleanup",
        action="store_true",
        help="Idempotent delete of the stub — intended for an `if: always()` "
        "workflow step so a failed Import still cleans up its row.",
    )
    args = ap.parse_args()

    validate_project_name(args.name)

    if args.cleanup:
        return run_cleanup(args.name)
    return run_probe(args.name)


if __name__ == "__main__":
    sys.exit(main())
