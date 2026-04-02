#!/usr/bin/env python3
"""Emergency deploy using session-based auth with aggressive retries.

Replaces the original basic-auth approach which returned HTTP 401 against
Acumatica's CustomizationApi endpoints (they require session cookies, not
HTTP Basic Auth).  See incident 2026-03-29.
"""
import base64, json, os, sys, time, zipfile, io, requests

# ---------------------------------------------------------------------------
# Make sibling modules importable
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))
from validate_publish_gi import check_gi_health

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
URL = os.environ["ACUMATICA_URL"].rstrip("/")
USER = os.environ["ACUMATICA_USERNAME"]
PASS = os.environ["ACUMATICA_PASSWORD"]
TENANT = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")
PROJECT = os.environ.get("PROJECT_NAME", "AesthetikContainers")
ALSO = os.environ.get("ALSO_PUBLISH_PROJECTS", "")
ZIP_DIR = os.environ.get("PACKAGE_DIR", "package")
IMPORT_ONLY = os.environ.get("IMPORT_ONLY", "").lower() in ("true", "1", "yes")
OPERATOR = os.environ.get("OPERATOR", os.environ.get("GITHUB_ACTOR", "unknown"))

headers = {"Content-Type": "application/json"}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Session-based login with aggressive retries
# ---------------------------------------------------------------------------
def emergency_login(url, username, password, tenant="", max_retries=5, delay=15):
    """Attempt session login with aggressive retries for emergency deploys."""
    session = requests.Session()
    for attempt in range(1, max_retries + 1):
        try:
            payload = {"name": username, "password": password}
            if tenant:
                payload["tenant"] = tenant
            resp = session.post(
                f"{url}/entity/auth/login",
                json=payload,
                timeout=30,
            )
            if resp.status_code in (200, 204):
                print(f"[EMERGENCY] Login succeeded on attempt {attempt}")
                return session
            print(f"[EMERGENCY] Login attempt {attempt}/{max_retries}: HTTP {resp.status_code}")
        except Exception as exc:
            print(f"[EMERGENCY] Login attempt {attempt}/{max_retries}: {exc}")
        if attempt < max_retries:
            time.sleep(delay)
    raise RuntimeError(f"Emergency login failed after {max_retries} attempts")


# ---------------------------------------------------------------------------
# Slack notification
# ---------------------------------------------------------------------------
def notify_slack(outcome, operator="unknown"):
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("[EMERGENCY] No SLACK_WEBHOOK_URL set — skipping notification")
        return
    try:
        requests.post(webhook, json={
            "text": f":rotating_light: *EMERGENCY DEPLOY* by {operator}\nOutcome: {outcome}"
        }, timeout=10)
    except Exception as exc:
        print(f"[EMERGENCY] Slack notification failed: {exc}")


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

# Step 0: Authenticate via session login
log("Authenticating via session login (not basic auth)...")
try:
    session = emergency_login(URL, USER, PASS, tenant=TENANT)
except RuntimeError as exc:
    log(f"FATAL: {exc}")
    notify_slack("FAILED — could not authenticate", operator=OPERATOR)
    sys.exit(1)

# Step 1: Build zip from package dir
log(f"Building zip from {ZIP_DIR}/...")
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    import pathlib
    for f in pathlib.Path(ZIP_DIR).rglob("*"):
        if f.is_file():
            zf.write(f, f.relative_to(ZIP_DIR))
content_b64 = base64.b64encode(buf.getvalue()).decode()
log(f"Package size: {len(buf.getvalue())} bytes")

# Step 2: Import via authenticated session
log(f"Importing {PROJECT} via session auth...")
import_payload = {
    "projectName": PROJECT,
    "projectDescription": f"Emergency deploy {time.strftime('%Y-%m-%dT%H:%M:%SZ')}",
    "projectLevel": 0,
    "isReplaceIfExists": True,
    "projectContentBase64": content_b64
}

for attempt in range(5):
    try:
        r = session.post(f"{URL}/CustomizationApi/Import",
                         headers=headers, json=import_payload, timeout=120)
        log(f"Import response: HTTP {r.status_code}")
        if r.status_code in (200, 204):
            log("Import SUCCESS")
            break
        log(f"Import body: {r.text[:500]}")
        if attempt < 4:
            wait = 15 * (attempt + 1)
            log(f"Retrying in {wait}s...")
            time.sleep(wait)
    except Exception as e:
        log(f"Import error: {e}")
        if attempt < 4:
            time.sleep(15)
else:
    log("FATAL: Import failed after 5 attempts")
    notify_slack("FAILED — import failed after 5 attempts", operator=OPERATOR)
    sys.exit(1)

# Step 3: Publish (skip if IMPORT_ONLY — caller will publish once at the end)
if IMPORT_ONLY:
    log(f"IMPORT_ONLY mode — skipping publish for {PROJECT}")
    session.post(f"{URL}/entity/auth/logout", headers=headers, timeout=10)
    sys.exit(0)

projects = [PROJECT]
if ALSO:
    projects.extend([p.strip() for p in ALSO.split(",") if p.strip()])
log(f"Publishing: {projects}")

publish_payload = {
    "isMergeWithExistingPackages": True,  # Keep ISV/third-party packages published alongside managed projects
    "isOnlyValidation": False,
    "isOnlyDbUpdates": False,
    "projectNames": projects,
    "tenantMode": "Current"
}

r = session.post(f"{URL}/CustomizationApi/publishBegin",
                 headers=headers, json=publish_payload, timeout=120)
log(f"publishBegin: HTTP {r.status_code} — {r.text[:300]}")
if r.status_code not in (200, 204):
    log("FATAL: publishBegin failed")
    notify_slack("FAILED — publishBegin returned HTTP {r.status_code}", operator=OPERATOR)
    sys.exit(1)

# Step 4: Poll publishEnd
log("Polling publishEnd...")
for i in range(120):  # 20 min max
    time.sleep(10)
    try:
        r = session.post(f"{URL}/CustomizationApi/publishEnd",
                         headers=headers, json={}, timeout=60)
        body = r.text.strip()

        if r.status_code == 200 and body.lower() == '"true"':
            log("PUBLISH COMPLETE — SUCCESS")

            # Post-publish GI health check
            gi_ok = check_gi_health(session, URL)
            if not gi_ok:
                log("[EMERGENCY] WARNING: GI subsystem unhealthy after emergency deploy")
                notify_slack("SUCCESS with WARNING — GI subsystem unhealthy after publish", operator=OPERATOR)
            else:
                notify_slack("SUCCESS — publish complete, GI healthy", operator=OPERATOR)
            sys.exit(0)

        if r.status_code == 200 and body.lower() == '"false"':
            if i % 6 == 0:
                log(f"Still publishing... ({i*10}s)")
            continue

        # HTTP 400 = completion (success or failure)
        if r.status_code == 400:
            try:
                data = json.loads(body)
                if data.get("isCompleted"):
                    if data.get("isFailed"):
                        log(f"PUBLISH FAILED: {data.get('log', '')[:500]}")
                        notify_slack("FAILED — publish reported failure", operator=OPERATOR)
                        sys.exit(1)
                    log("PUBLISH COMPLETE — SUCCESS")

                    # Post-publish GI health check
                    gi_ok = check_gi_health(session, URL)
                    if not gi_ok:
                        log("[EMERGENCY] WARNING: GI subsystem unhealthy after emergency deploy")
                        notify_slack("SUCCESS with WARNING — GI subsystem unhealthy after publish", operator=OPERATOR)
                    else:
                        notify_slack("SUCCESS — publish complete, GI healthy", operator=OPERATOR)
                    sys.exit(0)
                log(f"publishEnd 400 body: {body[:300]}")
            except json.JSONDecodeError:
                log(f"publishEnd 400 non-JSON: {body[:200]}")
        else:
            log(f"publishEnd HTTP {r.status_code}: {body[:200]}")

    except Exception as e:
        log(f"publishEnd error: {e}")

log("TIMEOUT: publish did not complete in 20 minutes")
notify_slack("FAILED — publish timed out after 20 minutes", operator=OPERATOR)
sys.exit(1)
