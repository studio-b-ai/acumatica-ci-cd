#!/usr/bin/env python3
"""
PCC Recovery — Minimal-list publish to land SB501000/SB501200 ASPX on prod.

Root cause: publishBegin with 11 co-publish projects causes PXPageIndexingService
to scan too many ASPX pages, hitting the server-side ~75s thread timeout
(ThreadAbortException). Sandbox only co-publishes 3 projects → succeeds.

Fix: Publish with merge=true but only AesthetikContainers in projectNames.
merge=true preserves already-published ISV packages. Fewer projects in the
list = fewer ASPX pages to re-index = faster website copy phase.

Fallback: If single-project still fails, try isOnlyDbUpdates=true first
(DB/compile only, no website copy), then isOnlyDbUpdates=false (website copy
with fresh app pool state).

Usage:
  # Creds from Railway cs-order-entry service
  export ACUMATICA_URL=https://heritagefabrics.acumatica.com
  export ACUMATICA_USERNAME=api-bot
  export ACUMATICA_PASSWORD='pedhek-hugpid-4Gokge'
  export ACUMATICA_TENANT='Heritage Fabrics'

  python3 scripts/recover-pcc-publish.py
"""

import json
import os
import sys
import time

import requests

# ─── Config ─────────────────────────────────────────────────────────────────
URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com").rstrip("/")
USER = os.environ.get("ACUMATICA_USERNAME", "api-bot")
PASS = os.environ.get("ACUMATICA_PASSWORD", "")
TENANT = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

# Only the project that owns SB501000/SB501200 ASPX files.
# merge=true keeps existing published ISV packages intact.
PRIMARY_PROJECT = "AesthetikContainers"

# Full list for fallback attempts (matches prod SM204505 state)
FULL_PROJECTS = [
    "AesthetikContainers",
    "AesthetikWMS",
    "AsthetikTheme",
    "StudioBAcuOps",
    "PXLotSertialNbrAttributeExtPkg",
    "Ramp",
    "AcumaticaPacejetCustomFields24.1001",
    "KNCentralizedLicense[24.200.0118][19NOV2024][V03]3",
    "FusionWMSBasic[9.4.11][24.201.0052]",
    "FusionWMSAdvanced[9.4.11][24.201.0052]",
    "WMSynergy.HF.CutHangTagLabel",
]

POLL_INTERVAL = 10
POLL_TIMEOUT = 1200  # 20 min — budget for app pool restart + website copy


def log(msg, style="info"):
    prefix = {
        "info": "[INFO ]",
        "ok":   "[  OK ]",
        "warn": "[ WARN]",
        "err":  "[ERROR]",
    }.get(style, "[INFO ]")
    print(f"{prefix} {time.strftime('%H:%M:%S')} {msg}", flush=True)


def login(session):
    """Authenticate with retry for API Login Limit."""
    payload = {"name": USER, "password": PASS}
    if TENANT:
        payload["tenant"] = TENANT

    for attempt in range(6):
        resp = session.post(f"{URL}/entity/auth/login", json=payload, timeout=60)
        if resp.status_code == 204:
            log("Authenticated", style="ok")
            return
        if "API Login Limit" in resp.text:
            wait = 30 * (attempt + 1)
            log(f"API Login Limit — waiting {wait}s (attempt {attempt + 1}/6)", style="warn")
            time.sleep(wait)
            continue
        raise RuntimeError(f"Login failed HTTP {resp.status_code}: {resp.text[:300]}")

    raise RuntimeError("Login failed after 6 attempts (API Login Limit)")


def logout(session):
    try:
        session.post(f"{URL}/entity/auth/logout", timeout=10)
    except Exception:
        pass


def publish_and_poll(session, project_names, merge=True, db_only=False, label=""):
    """Start publish and poll until completion.

    Returns: (success: bool, log_text: str)
    """
    tag = label or f"publish({','.join(project_names[:3])}{'...' if len(project_names) > 3 else ''})"

    payload = {
        "isMergeWithExistingPackages": merge,
        "isOnlyValidation": False,
        "isOnlyDbUpdates": db_only,
        "projectNames": project_names,
        "tenantMode": "Current",
    }

    log(f"[{tag}] publishBegin — merge={merge}, dbOnly={db_only}, projects={len(project_names)}")
    resp = session.post(f"{URL}/CustomizationApi/publishBegin", json=payload, timeout=120)

    if resp.status_code not in (200, 204):
        log(f"[{tag}] publishBegin FAILED HTTP {resp.status_code}: {resp.text[:300]}", style="err")
        return False, resp.text[:500]

    log(f"[{tag}] publishBegin accepted — polling...", style="ok")

    elapsed = 0
    conn_errors = 0
    max_conn_errors = 12  # 120s for app pool restart
    last_log_lines = ""

    while elapsed < POLL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        try:
            resp = session.post(f"{URL}/CustomizationApi/publishEnd", json={}, timeout=120)
        except Exception as exc:
            conn_errors += 1
            if conn_errors <= max_conn_errors:
                log(f"[{tag}] Connection lost ({conn_errors}/{max_conn_errors}) — "
                    f"app pool restarting ({elapsed}s)", style="warn")
                continue
            return False, f"App pool did not recover after {conn_errors} connection failures"

        conn_errors = 0

        if resp.status_code in (500, 502, 503, 504):
            conn_errors += 1
            log(f"[{tag}] HTTP {resp.status_code} — app pool restarting ({elapsed}s)", style="warn")
            continue

        body = resp.text.strip()

        # JSON response (Acumatica 24.2+)
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                # Extract log for diagnostics
                log_data = data.get("log", "")
                if isinstance(log_data, list):
                    recent = [
                        e.get("message", str(e))[:200]
                        for e in log_data[-5:]
                        if isinstance(e, dict)
                    ]
                    log_text = "\n".join(recent)
                else:
                    log_text = str(log_data)[-500:]

                if log_text != last_log_lines and log_text.strip():
                    # Print new log lines for visibility
                    for line in log_text.split("\n"):
                        line = line.strip()
                        if line:
                            s = "warn" if any(k in line.lower() for k in ("error", "exception", "warning", "failed")) else "info"
                            log(f"[{tag}] PUBLISH LOG: {line[:200]}", style=s)
                    last_log_lines = log_text

                if data.get("isCompleted"):
                    if data.get("isFailed"):
                        log(f"[{tag}] PUBLISH FAILED after {elapsed}s", style="err")
                        return False, log_text
                    log(f"[{tag}] PUBLISH COMPLETED in {elapsed}s", style="ok")
                    return True, log_text
                else:
                    if elapsed % 60 < POLL_INTERVAL:
                        log(f"[{tag}] Still publishing... ({elapsed}s / {POLL_TIMEOUT}s)")
                    continue
        except json.JSONDecodeError:
            pass

        # Plain text response
        if body.lower() in ('"true"', 'true'):
            log(f"[{tag}] PUBLISH COMPLETED in {elapsed}s", style="ok")
            return True, ""
        elif body.lower() in ('"false"', 'false'):
            if elapsed % 60 < POLL_INTERVAL:
                log(f"[{tag}] Still publishing... ({elapsed}s / {POLL_TIMEOUT}s)")
            continue

    return False, f"Timed out after {POLL_TIMEOUT}s"


def smoke_test(session):
    """Re-auth and query to verify app pool is healthy."""
    log("Running smoke test...")
    logout(session)
    time.sleep(10)

    new_session = requests.Session()
    new_session.headers.update({"Content-Type": "application/json"})

    for attempt in range(6):
        try:
            payload = {"name": USER, "password": PASS}
            if TENANT:
                payload["tenant"] = TENANT
            resp = new_session.post(f"{URL}/entity/auth/login", json=payload, timeout=30)
            if resp.status_code == 204:
                # Query to verify DLLs loaded
                resp2 = new_session.get(
                    f"{URL}/entity/default/24.200.001/StockItem",
                    params={"$top": "1", "$select": "InventoryID"},
                    timeout=30,
                )
                if resp2.status_code == 200:
                    log("Smoke test PASSED", style="ok")
                    logout(new_session)
                    return True
                log(f"Smoke test query: HTTP {resp2.status_code}", style="warn")
            else:
                log(f"Smoke test login: HTTP {resp.status_code}", style="warn")
        except Exception as exc:
            log(f"Smoke test attempt {attempt + 1}: {exc}", style="warn")
        time.sleep(15)

    log("Smoke test FAILED — manual verification required", style="warn")
    return False


# ─── Main Recovery Flow ─────────────────────────────────────────────────────

def main():
    if not PASS:
        log("ACUMATICA_PASSWORD not set", style="err")
        sys.exit(1)

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    # ── Attempt 1: Single-project publish (merge=true) ──────────────
    # Only AesthetikContainers → minimal ASPX page indexing
    log("=" * 60)
    log("ATTEMPT 1: Single-project publish (AesthetikContainers only)")
    log("  merge=true → existing ISV packages stay published")
    log("  Reduced page indexing scope should avoid ThreadAbortException")
    log("=" * 60)

    login(session)
    ok, log_text = publish_and_poll(
        session,
        project_names=[PRIMARY_PROJECT],
        merge=True,
        db_only=False,
        label="ATTEMPT-1",
    )

    if ok:
        log("ATTEMPT 1 SUCCEEDED — ASPX files should be deployed", style="ok")
        smoke_test(session)
        logout(session)
        sys.exit(0)

    log(f"ATTEMPT 1 FAILED: {log_text[:300]}", style="err")
    logout(session)

    # ── Attempt 2: Split deploy — DB-only first, then website files ──
    log("")
    log("=" * 60)
    log("ATTEMPT 2: Split deploy (isOnlyDbUpdates=true first)")
    log("  Phase A: DB-only (compile + schema, skip website copy)")
    log("  Phase B: Full publish (website copy with fresh app pool)")
    log("=" * 60)

    time.sleep(30)  # Let app pool settle after failed attempt

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    login(session)

    # Phase A: DB-only
    ok_a, log_a = publish_and_poll(
        session,
        project_names=[PRIMARY_PROJECT],
        merge=True,
        db_only=True,
        label="ATTEMPT-2A-DBONLY",
    )

    if not ok_a:
        log(f"ATTEMPT 2A (DB-only) FAILED: {log_a[:300]}", style="err")
        logout(session)
        log("All automated recovery attempts failed. Manual intervention required.", style="err")
        sys.exit(1)

    log("Phase A (DB-only) succeeded — waiting for app pool restart...", style="ok")
    logout(session)
    time.sleep(60)  # Wait for app pool to fully restart

    # Phase B: Full publish (website files)
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    login(session)

    ok_b, log_b = publish_and_poll(
        session,
        project_names=[PRIMARY_PROJECT],
        merge=True,
        db_only=False,
        label="ATTEMPT-2B-FULL",
    )

    if ok_b:
        log("ATTEMPT 2 SUCCEEDED — website files deployed", style="ok")
        smoke_test(session)
        logout(session)
        sys.exit(0)

    log(f"ATTEMPT 2B (full) FAILED: {log_b[:300]}", style="err")
    logout(session)

    # ── Attempt 3: Publish with custom Aesthetik subset ──────────────
    log("")
    log("=" * 60)
    log("ATTEMPT 3: Aesthetik-only subset (4 projects, merge=true)")
    log("=" * 60)

    time.sleep(30)
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    login(session)

    aesthetik_subset = [
        "AesthetikContainers",
        "AesthetikWMS",
        "AsthetikTheme",
        "StudioBAcuOps",
    ]

    ok, log_text = publish_and_poll(
        session,
        project_names=aesthetik_subset,
        merge=True,
        db_only=False,
        label="ATTEMPT-3",
    )

    if ok:
        log("ATTEMPT 3 SUCCEEDED", style="ok")
        smoke_test(session)
        logout(session)
        sys.exit(0)

    log(f"ATTEMPT 3 FAILED: {log_text[:300]}", style="err")
    logout(session)

    log("")
    log("ALL AUTOMATED RECOVERY ATTEMPTS FAILED", style="err")
    log("Possible next steps:", style="err")
    log("  1. File Acumatica support ticket to increase executionTimeout", style="err")
    log("  2. Try manual SM204505 publish from Acumatica UI", style="err")
    log("  3. Contact Acumatica Cloud Support for server-side assistance", style="err")
    sys.exit(1)


if __name__ == "__main__":
    main()
