#!/usr/bin/env python3
"""Emergency deploy using basic auth — bypasses broken session login."""
import base64, json, os, sys, time, zipfile, io, requests

URL = os.environ["ACUMATICA_URL"].rstrip("/")
USER = os.environ["ACUMATICA_USERNAME"]
PASS = os.environ["ACUMATICA_PASSWORD"]
TENANT = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")
PROJECT = os.environ.get("PROJECT_NAME", "AesthetikContainers")
ALSO = os.environ.get("ALSO_PUBLISH_PROJECTS", "")
ZIP_DIR = os.environ.get("PACKAGE_DIR", "package")

auth = (USER, PASS)
headers = {"Content-Type": "application/json"}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

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

# Step 2: Import via basic auth
log(f"Importing {PROJECT} via basic auth...")
import_payload = {
    "projectName": PROJECT,
    "projectDescription": f"Emergency deploy {time.strftime('%Y-%m-%dT%H:%M:%SZ')}",
    "projectLevel": 0,
    "isReplaceIfExists": True,
    "projectContentBase64": content_b64
}

for attempt in range(5):
    try:
        r = requests.post(f"{URL}/CustomizationApi/Import", auth=auth,
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
    sys.exit(1)

# Step 3: Publish
projects = [PROJECT]
if ALSO:
    projects.extend([p.strip() for p in ALSO.split(",") if p.strip()])
log(f"Publishing: {projects}")

publish_payload = {
    "isMergeWithExistingPackages": False,
    "isOnlyValidation": False,
    "isOnlyDbUpdates": False,
    "projectNames": projects,
    "tenantMode": "Current"
}

r = requests.post(f"{URL}/CustomizationApi/publishBegin", auth=auth,
                  headers=headers, json=publish_payload, timeout=120)
log(f"publishBegin: HTTP {r.status_code} — {r.text[:300]}")
if r.status_code not in (200, 204):
    log("FATAL: publishBegin failed")
    sys.exit(1)

# Step 4: Poll publishEnd
log("Polling publishEnd...")
for i in range(120):  # 20 min max
    time.sleep(10)
    try:
        r = requests.post(f"{URL}/CustomizationApi/publishEnd", auth=auth,
                         headers=headers, json={}, timeout=60)
        body = r.text.strip()

        if r.status_code == 200 and body.lower() == '"true"':
            log("PUBLISH COMPLETE — SUCCESS")
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
                        sys.exit(1)
                    log("PUBLISH COMPLETE — SUCCESS")
                    sys.exit(0)
                log(f"publishEnd 400 body: {body[:300]}")
            except json.JSONDecodeError:
                log(f"publishEnd 400 non-JSON: {body[:200]}")
        else:
            log(f"publishEnd HTTP {r.status_code}: {body[:200]}")

    except Exception as e:
        log(f"publishEnd error: {e}")

log("TIMEOUT: publish did not complete in 20 minutes")
sys.exit(1)
