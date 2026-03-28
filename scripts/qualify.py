#!/usr/bin/env python3
"""
Agentic pre-deploy qualification gate.
Runs 6 checks and returns pass/warn/fail for each.
Exit 0 = proceed, exit 1 = halt.
Outputs JSON summary to stdout for workflow consumption.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import http.cookiejar
from datetime import datetime, timezone

# Force unbuffered output so GH Actions shows progress in real time
os.environ["PYTHONUNBUFFERED"] = "1"


def _print(msg: str) -> None:
    """Print with explicit flush for GH Actions visibility."""
    print(msg, flush=True)

# ─── Check Results ────────────────────────────────────────────────────

PASS = "pass"
WARN = "warn"
FAIL = "fail"


def check_acumatica_health(url, username, password, tenant):
    """Check 1: Can we login and query StockItem?"""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    body = json.dumps({"name": username, "password": password, "tenant": tenant}).encode()
    req = urllib.request.Request(
        f"{url}/entity/auth/login", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        resp = opener.open(req, timeout=30)
    except Exception as e:
        return FAIL, f"Login failed: {e}"

    # Check for NullRef (corruption)
    if hasattr(resp, "read"):
        text = resp.read().decode() if resp.status != 204 else ""
        if "NullReferenceException" in text:
            return FAIL, "NullReferenceException on login — subsystem corrupted"

    # Query StockItem
    try:
        req2 = urllib.request.Request(
            f"{url}/entity/Default/24.200.001/StockItem?$top=1&$select=InventoryID",
            method="GET",
        )
        resp2 = opener.open(req2, timeout=30)
        if resp2.status == 200:
            # Logout
            try:
                opener.open(urllib.request.Request(f"{url}/entity/auth/logout", method="POST"), timeout=10)
            except Exception:
                pass
            return PASS, "API healthy"
        return FAIL, f"StockItem query returned HTTP {resp2.status}"
    except Exception as e:
        return FAIL, f"StockItem query failed: {e}"


def check_orphan_scan(url, username, password, tenant, known_projects):
    """Check 2: Drift detection — are deprecated projects still on the instance?

    Uses instance-manifest.json to identify deprecated projects that should
    have been deleted. If any exist on the instance, they could get compiled
    during the next publish and cause runtime errors (like the 2026-03-26
    StockItemExt incident).
    """
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    body = json.dumps({"name": username, "password": password, "tenant": tenant}).encode()
    req = urllib.request.Request(
        f"{url}/entity/auth/login", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        opener.open(req, timeout=30)
    except Exception as e:
        return WARN, f"Could not login for drift scan: {e}"

    # Load instance manifest
    manifest = _load_instance_manifest()
    deprecated_names = []
    managed_names = []
    if manifest:
        for name, info in manifest.get("projects", {}).items():
            cat = info.get("category", "")
            if cat == "deprecated":
                deprecated_names.append(name)
            elif cat == "managed":
                managed_names.append(name)

    issues = []

    # Check managed projects for NullRef (corruption indicator)
    check_names = managed_names if managed_names else known_projects
    for name in check_names:
        try:
            req2 = urllib.request.Request(
                f"{url}/CustomizationApi/getProject",
                data=json.dumps({"projectName": name}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            opener.open(req2, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code == 400:
                pass  # Not on instance — OK
            else:
                error_body = e.read().decode() if e.fp else ""
                if "NullReferenceException" in error_body:
                    issues.append(f"NullRef on {name} — subsystem corrupted")

    # Check deprecated projects aren't lingering on instance
    for name in deprecated_names:
        try:
            req2 = urllib.request.Request(
                f"{url}/CustomizationApi/getProject",
                data=json.dumps({"projectName": name}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            opener.open(req2, timeout=30)
            # 200 = project exists — should have been deleted
            issues.append(f"DRIFT: deprecated '{name}' still on instance — delete via SM204505")
        except urllib.error.HTTPError:
            pass  # 400 = not found — good
        except Exception:
            pass

    try:
        opener.open(urllib.request.Request(f"{url}/entity/auth/logout", method="POST"), timeout=10)
    except Exception:
        pass

    if any("DRIFT" in i for i in issues):
        return FAIL, "; ".join(issues)
    if issues:
        return WARN, "; ".join(issues)
    return PASS, f"No drift detected ({len(check_names)} managed, {len(deprecated_names)} deprecated checked)"


def _load_instance_manifest():
    """Load instance-manifest.json from repo root."""
    for path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "instance-manifest.json"),
        "instance-manifest.json",
    ]:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return None


def check_diff_scope(isv_packages):
    """Check 3: Are changes code-only, or do they touch SQL/ISV/project.xml structure?

    Severity levels:
    - FAIL: ISV package modifications (third-party, we don't control the code)
    - WARN: project.xml or SQL changes (routine — every DAC/graph extension
            modifies project.xml, and SQL scripts are expected for column creation)
    - PASS: Code-only changes (.cs, .aspx, .py, etc.)
    """
    # Find last deploy tag
    result = subprocess.run(
        ["git", "tag", "-l", "deploy/prod/*", "--sort=-creatordate"],
        capture_output=True, text=True,
    )
    tags = result.stdout.strip().split("\n")
    # Filter out rolled-back tags
    clean_tags = [t for t in tags if t and "ROLLED-BACK" not in t]

    if not clean_tags:
        return WARN, "No previous deploy tags found — cannot diff"

    last_tag = clean_tags[0]

    # Get changed files
    result = subprocess.run(
        ["git", "diff", "--name-only", last_tag, "HEAD"],
        capture_output=True, text=True,
    )
    changed = result.stdout.strip().split("\n") if result.stdout.strip() else []

    if not changed:
        return PASS, "No changes since last deploy"

    isv_issues = []
    warnings = []

    for f in changed:
        # ISV package touched? → FAIL (third-party code we don't control)
        for isv in isv_packages:
            if f.startswith(f"Customization/{isv}/"):
                isv_issues.append(f"ISV package modified: {isv} ({f})")

        # SQL changes? → WARN (routine for column creation)
        if f.endswith(".sql") or "SqlScript" in f:
            warnings.append(f"SQL change: {f}")

        # project.xml change? → WARN (routine — every DAC/graph extension touches this)
        if f.endswith("project.xml"):
            warnings.append(f"project.xml modified: {f}")

    # ISV modifications are the only hard failure
    if isv_issues:
        return FAIL, "; ".join(isv_issues + warnings)

    if warnings:
        return WARN, "; ".join(warnings)

    return PASS, "Code-only changes"


def check_failure_history(repo, workflow_name):
    """Check 4: How many failures in the last 24h?"""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/actions/workflows/{workflow_name}/runs",
             "--jq", '.workflow_runs[:10] | map(select(.conclusion == "failure")) | length'],
            capture_output=True, text=True, timeout=30,
        )
        failure_count = int(result.stdout.strip() or "0")
        if failure_count >= 2:
            return FAIL, f"{failure_count} failures in recent runs"
        elif failure_count == 1:
            return WARN, "1 failure in recent runs"
        return PASS, "0 recent failures"
    except Exception as e:
        return WARN, f"Could not check failure history: {e}"


def check_deploy_cooldown(repo, workflow_name):
    """Check 5: Has it been >60 min since the last deploy?"""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/actions/workflows/{workflow_name}/runs",
             "--jq", '.workflow_runs[0].updated_at'],
            capture_output=True, text=True, timeout=30,
        )
        last_run = result.stdout.strip()
        if not last_run:
            return PASS, "No previous runs"

        last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60

        if elapsed < 30:
            return WARN, f"Last deploy {elapsed:.0f} min ago (<30 min cooldown)"
        elif elapsed < 60:
            return WARN, f"Last deploy {elapsed:.0f} min ago"
        return PASS, f"Last deploy {elapsed:.0f} min ago"
    except Exception as e:
        return WARN, f"Could not check cooldown: {e}"


def check_timing():
    """Check 6: Is it after 6pm CT / weekend?"""
    import zoneinfo
    ct = datetime.now(zoneinfo.ZoneInfo("America/Chicago"))
    hour = ct.hour
    weekday = ct.weekday()  # 0=Mon, 6=Sun

    if weekday >= 5:  # Weekend
        return PASS, f"Weekend ({ct.strftime('%A %H:%M CT')})"
    if hour >= 18 or hour < 6:
        return PASS, f"After hours ({ct.strftime('%H:%M CT')})"
    return WARN, f"Business hours ({ct.strftime('%H:%M CT')}) — countdown required"


def post_slack(webhook_url, message):
    """Post a message to Slack."""
    if not webhook_url:
        return
    try:
        data = json.dumps({"text": message}).encode()
        req = urllib.request.Request(
            webhook_url, data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def main():
    url = os.environ.get("ACUMATICA_URL", "")
    username = os.environ.get("ACUMATICA_USERNAME", "")
    password = os.environ.get("ACUMATICA_PASSWORD", "")
    tenant = os.environ.get("ACUMATICA_TENANT", "")
    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    known_str = os.environ.get("KNOWN_PROJECTS", "")
    isv_str = os.environ.get("ISV_PACKAGES", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "studio-b-ai/acumatica-ci-cd")
    workflow = "deploy-customization.yml"
    project_name = os.environ.get("PROJECT_NAME", "AesthetikWMS")
    max_retries = int(os.environ.get("QUALIFY_MAX_RETRIES", "1"))
    retry_delay = int(os.environ.get("QUALIFY_RETRY_DELAY", "60"))  # 60s (was 1800s — caused GH Actions timeout)

    known_projects = [p.strip() for p in known_str.split(",") if p.strip()]
    isv_packages = [p.strip() for p in isv_str.split(",") if p.strip()]

    for attempt in range(max_retries + 1):
        if attempt > 0:
            _print(f"\n--- Retry {attempt}/{max_retries} (waiting {retry_delay}s) ---")
            post_slack(slack_url, f"Deploy qualification retry {attempt}/{max_retries} — {project_name} -> production\nRe-checking in {retry_delay // 60} minutes...")
            time.sleep(retry_delay)

        results = {}
        results["Health"] = check_acumatica_health(url, username, password, tenant)
        results["Orphans"] = check_orphan_scan(url, username, password, tenant, known_projects)
        results["Scope"] = check_diff_scope(isv_packages)
        results["Failures"] = check_failure_history(repo, workflow)
        results["Cooldown"] = check_deploy_cooldown(repo, workflow)
        results["Timing"] = check_timing()

        # Summarize
        has_fail = any(r[0] == FAIL for r in results.values())
        has_warn = any(r[0] == WARN for r in results.values())
        needs_countdown = results["Timing"][0] == WARN

        summary_parts = [f"{name}: {r[0]}" for name, r in results.items()]
        summary_line = " | ".join(summary_parts)

        for name, (status, detail) in results.items():
            icon = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[status]
            _print(f"[{icon}] {name}: {detail}")

        if not has_fail:
            # Proceed
            if has_warn:
                msg = f"Deploy qualified with warnings — {project_name} -> production\n  {summary_line}"
                post_slack(slack_url, msg)
            else:
                msg = f"Deploy qualified — {project_name} -> production\n  {summary_line}"
                post_slack(slack_url, msg)

            # Output for workflow
            gh_output = os.environ.get("GITHUB_OUTPUT", "")
            if gh_output:
                with open(gh_output, "a") as f:
                    f.write(f"decision=proceed\n")
                    f.write(f"needs_countdown={'true' if needs_countdown else 'false'}\n")
                    f.write(f"summary={summary_line}\n")
            sys.exit(0)

        # Has failures
        if attempt < max_retries:
            msg = f"Deploy HALTED — {project_name} -> production\n  {summary_line}\n  Retrying in {retry_delay // 60} minutes (attempt {attempt + 1}/{max_retries})..."
            post_slack(slack_url, msg)
            _print(f"\nHALTED — retrying in {retry_delay}s")
            continue

        # Exhausted retries — escalate
        override_url = f"https://github.com/{repo}/actions/workflows/{workflow}"
        msg = (
            f"Deploy requires manual override — {project_name} -> production\n"
            f"  {summary_line}\n"
            f"  {max_retries} retry attempts failed.\n"
            f"  Override: {override_url}\n"
            f"  Use workflow_dispatch with force_qualify=true"
        )
        post_slack(slack_url, msg)
        _print(f"\nESCALATED — retries exhausted. Manual override required.")

        gh_output = os.environ.get("GITHUB_OUTPUT", "")
        if gh_output:
            with open(gh_output, "a") as f:
                f.write(f"decision=halt\n")
                f.write(f"needs_countdown=false\n")
                f.write(f"summary={summary_line}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
