#!/usr/bin/env python3
"""
Acumatica Customization Deployment Script (Python)

Deploys customization packages via the Acumatica Customization API with
additional features over the bash version:
  - Download existing packages for backup (--download)
  - Co-publish multiple projects for conflict detection (--also-publish)
  - Reusable AcumaticaCustomizationClient class

API Flow:
  1. POST /entity/auth/login             - Authenticate session
  2. POST /CustomizationApi/Import       - Upload .zip package
  3. POST /CustomizationApi/publishBegin - Start publish
  4. POST /CustomizationApi/publishEnd   - Poll until complete
  5. POST /entity/auth/logout            - Release session

Usage:
  python deploy.py \\
    --url https://instance.acumatica.com \\
    --username admin \\
    --password secret \\
    --project MyProject \\
    --package dist/MyProject.zip

  # Download existing package before deploying (backup)
  python deploy.py --download --project MyProject --output backups/

  # Validate only (no publish)
  python deploy.py --validate-only --project MyProject --package dist/MyProject.zip

  # Co-publish with other managed projects
  python deploy.py --project AesthetikWMS --package dist/AesthetikWMS.zip \\
    --also-publish AesthetikContainers StudioBAcuOps
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Force unbuffered output — critical for GitHub Actions log visibility
os.environ["PYTHONUNBUFFERED"] = "1"


class CustomizationCorruptionError(RuntimeError):
    """Raised when NullReferenceException indicates database corruption.

    The Acumatica customization subsystem has corrupted CustProject records.
    DO NOT RETRY — each attempt makes corruption worse.
    See: 2026-03-22 incident (AesthetikWMSv2/v3 orphans).
    """
    pass


class AcumaticaCustomizationClient:
    """Client for the Acumatica Customization API."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        tenant: str = "",
        timeout: int = 120,
    ):
        self.base_url = url.rstrip("/")
        self.username = username
        self.password = password
        self.tenant = tenant
        self.timeout = timeout
        self.session = self._create_session()
        self._authenticated = False

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"Content-Type": "application/json"})
        return session

    def _check_circuit_breaker(self, response_text: str, context: str) -> None:
        """Halt immediately if NullReferenceException detected."""
        if "NullReferenceException" not in response_text:
            return
        _log(
            f"CIRCUIT BREAKER: NullReferenceException in {context}\n"
            "The Acumatica customization subsystem is corrupted.\n"
            "DO NOT RETRY — each attempt makes it worse.\n"
            "Action: File Acumatica support ticket to clean CustProject table.\n"
            "See: 2026-03-22 incident",
            style="err",
        )
        raise CustomizationCorruptionError(
            f"Database corruption detected in {context}. HALTED."
        )

    def login(self, max_retries: int = 12, retry_delay: float = 30.0) -> None:
        """Authenticate and establish a session cookie.

        Retries on:
        - API Login Limit: concurrent session cap reached by Railway sync workers
        - TargetInvocationException: Acumatica app pool crash/recovery cycle caused
          by a CustomizationPlugin.UpdateDatabase() failure. The app pool auto-restarts;
          retry until the recovery window is available (up to ~6 min).

        Circuit breaker (AAR 2026-03-28):
        - 3 consecutive IDENTICAL errors = abort immediately
        - Prevents retry storms from exhausting API session limit
        - Triggers auto-lockout via LOCKOUT_URL if configured
        """
        import time as _time
        payload = {"name": self.username, "password": self.password}
        if self.tenant:
            payload["tenant"] = self.tenant

        consecutive_same_error = 0
        last_error_sig = None

        for attempt in range(max_retries + 1):
            resp = self.session.post(
                f"{self.base_url}/entity/auth/login",
                json=payload,
                timeout=self.timeout,
            )

            if resp.status_code == 204:
                self._authenticated = True
                _log("Authenticated", style="ok")
                return

            is_login_limit = "API Login Limit" in resp.text
            is_app_pool_crash = "TargetInvocationException" in resp.text
            is_invalid_column = "Invalid column name" in resp.text

            # ── Circuit breaker: 3 consecutive identical errors = abort ──
            # Prevents retry storms that compound outages (AAR 2026-03-28:
            # 4 GHA runs × 12 retries + Railway services exhausted API sessions)
            error_sig = f"{resp.status_code}:{resp.text[:200]}"
            if error_sig == last_error_sig:
                consecutive_same_error += 1
            else:
                consecutive_same_error = 1
                last_error_sig = error_sig

            if consecutive_same_error >= 3:
                _log(
                    f"CIRCUIT BREAKER: 3 consecutive identical errors. "
                    f"Aborting to prevent retry storm.\n"
                    f"  Error: {resp.text[:300]}",
                    style="error",
                )
                # Auto-trigger Redis lockout if URL configured
                lockout_url = os.environ.get("LOCKOUT_URL", "")
                if lockout_url:
                    try:
                        import requests as _req
                        _req.post(
                            f"{lockout_url}/maintenance/start",
                            json={"ttl": 3600, "reason": "Deploy circuit breaker — 3 consecutive identical login failures"},
                            timeout=5,
                        )
                        _log("Auto-lockout enabled (1 hour)", style="warn")
                    except Exception:
                        pass
                raise RuntimeError(
                    f"CIRCUIT BREAKER TRIPPED: Login failed with same error 3 times. "
                    f"Manual intervention required. Error: {resp.text[:300]}"
                )

            # ── Invalid column name = persistent failure, no retry ──
            # This is the exact pattern from 2026-03-28: [PXDB*] field without
            # SQL column. Retrying will NEVER fix it — only wastes sessions.
            if is_invalid_column:
                _log(
                    f"FATAL: 'Invalid column name' in login response. "
                    f"This is a persistent failure — retrying will not fix it.\n"
                    f"  Error: {resp.text[:300]}",
                    style="error",
                )
                raise RuntimeError(
                    f"PERSISTENT LOGIN FAILURE — Invalid column name detected. "
                    f"A [PXDB*] field references a column that doesn't exist. "
                    f"Fix: unpublish the offending package via Acumatica Cloud Support. "
                    f"Error: {resp.text[:500]}"
                )

            if (is_login_limit or is_app_pool_crash) and attempt < max_retries:
                wait = retry_delay * (attempt + 1)
                reason = (
                    "app pool crash (Acumatica recovering — will retry)"
                    if is_app_pool_crash
                    else "login limit (sessions full — waiting for Railway workers)"
                )
                _log(
                    f"  {reason} (attempt {attempt + 1}/{max_retries}) — waiting {int(wait)}s",
                    style="warn",
                )
                _time.sleep(wait)
                continue

            # Circuit breaker: NullReferenceException outside app pool crash = DB corruption.
            # TargetInvocationException already handled above — don't circuit-break for it.
            if not is_app_pool_crash:
                self._check_circuit_breaker(resp.text, "login")

            raise RuntimeError(
                f"Login failed (HTTP {resp.status_code}): {resp.text[:500]}"
            )

    def logout(self) -> None:
        """Release the session."""
        if not self._authenticated:
            return
        try:
            self.session.post(
                f"{self.base_url}/entity/auth/logout", timeout=30
            )
        except Exception:
            pass
        self._authenticated = False
        _log("Session closed", style="ok")

    def import_package(
        self,
        project_name: str,
        package_path: str,
        description: str = "",
        replace_if_exists: bool = True,
    ) -> None:
        """Upload a customization .zip package."""
        path = Path(package_path)
        if not path.exists():
            raise FileNotFoundError(f"Package not found: {package_path}")

        content_b64 = base64.b64encode(path.read_bytes()).decode("ascii")

        if not description:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            description = f"Deployed via CI/CD at {ts}"

        payload = {
            "projectName": project_name,
            "projectDescription": description,
            "projectLevel": 0,
            "isReplaceIfExists": replace_if_exists,
            "projectContentBase64": content_b64,
        }

        _log(f"Importing {path.name} ({_filesize(path)})...")
        resp = self.session.post(
            f"{self.base_url}/CustomizationApi/Import",
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code not in (200, 204):
            self._check_circuit_breaker(resp.text, "import")
            raise RuntimeError(
                f"Import failed (HTTP {resp.status_code}): {resp.text[:500]}"
            )

        _log(f"Package imported: {project_name}", style="ok")

    def preflight_validate(self, project_name: str, package_path: str) -> None:
        """Dry-run import to catch XML/format errors before real import."""
        path = Path(package_path)
        content_b64 = base64.b64encode(path.read_bytes()).decode("ascii")

        payload = {
            "projectName": project_name,
            "projectDescription": "Pre-flight validation",
            "projectLevel": 0,
            "isReplaceIfExists": True,
            "projectContentBase64": content_b64,
        }

        _log("Pre-flight validation...")
        resp = self.session.post(
            f"{self.base_url}/CustomizationApi/Import?validateOnly=true",
            json=payload,
            timeout=self.timeout,
        )

        # 404/405 = endpoint not supported, skip gracefully
        if resp.status_code in (404, 405):
            _log("Pre-flight endpoint not available — skipping", style="warn")
            return

        self._check_circuit_breaker(resp.text, "pre-flight")

        if resp.status_code not in (200, 204):
            raise RuntimeError(
                f"Pre-flight failed (HTTP {resp.status_code}): {resp.text[:500]}"
            )
        _log("Pre-flight passed", style="ok")

    def cleanup_orphan(self, project_name: str) -> bool:
        """Attempt to delete a project, with fallback for corrupted CustProject rows.

        If the standard delete API fails (corrupted CustProject entry returns
        NullReferenceException), falls back to importing a minimal empty project
        to overwrite the corrupted row, then deletes the clean entry.
        """
        _log(f"Cleaning up potentially orphaned project '{project_name}'...", style="warn")

        # Attempt 1: standard delete
        try:
            resp = self.session.post(
                f"{self.base_url}/CustomizationApi/delete",
                json={"projectName": project_name},
                timeout=30,
            )
            if resp.status_code in (200, 204):
                _log(f"Cleaned up orphan '{project_name}'", style="ok")
                return True
            _log(f"Delete returned HTTP {resp.status_code}: {resp.text[:200]}", style="warn")
        except Exception as e:
            _log(f"Delete threw: {e}", style="warn")

        # Attempt 2: overwrite corrupted entry with a minimal empty project,
        # then delete. The import overwrites the corrupted CustProject row with
        # a clean one, making deletion possible.
        _log(f"Attempting overwrite-then-delete for '{project_name}'...", style="warn")
        try:
            minimal_xml = (
                '<Customization level="0" description="cleanup placeholder" '
                'product-version="24.208"><Graph /></Customization>'
            )
            content_b64 = base64.b64encode(minimal_xml.encode("utf-8")).decode("ascii")
            import_resp = self.session.post(
                f"{self.base_url}/CustomizationApi/Import",
                json={
                    "projectName": project_name,
                    "projectDescription": "cleanup placeholder",
                    "projectLevel": 0,
                    "isReplaceIfExists": True,
                    "projectContentBase64": content_b64,
                },
                timeout=30,
            )
            if import_resp.status_code in (200, 204):
                _log(f"Overwrote corrupted entry for '{project_name}', now deleting...", style="warn")
                del_resp = self.session.post(
                    f"{self.base_url}/CustomizationApi/delete",
                    json={"projectName": project_name},
                    timeout=30,
                )
                if del_resp.status_code in (200, 204):
                    _log(f"Cleaned up '{project_name}' via overwrite-then-delete", style="ok")
                    return True
                _log(f"Post-overwrite delete returned HTTP {del_resp.status_code}: {del_resp.text[:200]}", style="warn")
            else:
                _log(f"Overwrite import returned HTTP {import_resp.status_code}: {import_resp.text[:200]}", style="warn")
        except Exception as e:
            _log(f"Overwrite-then-delete threw: {e}", style="warn")

        _log(f"Could not clean up '{project_name}' — manual SM204505 cleanup required", style="warn")
        return False

    def publish(
        self,
        project_names: list[str],
        poll_interval: int = 10,
        poll_timeout: int = 1800,
        validation_only: bool = False,
        merge_with_existing: bool = True,
    ) -> None:
        """Publish one or more customization projects and wait for completion."""
        _log(f"Publishing: {', '.join(project_names)} (merge={merge_with_existing})")

        payload = {
            "isMergeWithExistingPackages": merge_with_existing,
            "isOnlyValidation": validation_only,
            "isOnlyDbUpdates": False,
            "projectNames": project_names,
            "tenantMode": "Current",
        }

        resp = self.session.post(
            f"{self.base_url}/CustomizationApi/publishBegin",
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code not in (200, 204):
            raise RuntimeError(
                f"Publish begin failed (HTTP {resp.status_code}): {resp.text[:500]}"
            )

        _log("Publish started — polling for completion...", style="ok")

        elapsed = 0
        connection_errors = 0
        max_connection_errors = 6  # Allow up to 6 consecutive connection failures (60s at 10s interval)
        while elapsed < poll_timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                resp = self.session.post(
                    f"{self.base_url}/CustomizationApi/publishEnd",
                    json={},
                    timeout=self.timeout,
                )
            except Exception as exc:
                # App pool restart kills connections — this is EXPECTED during publish.
                # Keep polling until the app pool comes back or we exhaust retries.
                connection_errors += 1
                _log(
                    f"  Connection lost during poll ({connection_errors}/{max_connection_errors}) "
                    f"— app pool likely restarting ({elapsed}s)",
                    style="warn",
                )
                if connection_errors >= max_connection_errors:
                    raise TimeoutError(
                        f"App pool did not recover after {connection_errors} connection failures "
                        f"({elapsed}s elapsed). Check Acumatica System Monitor."
                    ) from exc
                continue

            # Reset connection error counter on successful response
            connection_errors = 0

            # publishEnd returns JSON with isCompleted/isFailed on both 200 and 400.
            # During app pool restart, 500/502/503 are expected — treat like connection errors.
            if resp.status_code in (500, 502, 503, 504):
                connection_errors += 1
                _log(
                    f"  HTTP {resp.status_code} during poll ({connection_errors}/{max_connection_errors}) "
                    f"— app pool likely restarting ({elapsed}s)",
                    style="warn",
                )
                if connection_errors >= max_connection_errors:
                    raise RuntimeError(
                        f"Publish poll returned HTTP {resp.status_code} after "
                        f"{connection_errors} attempts ({elapsed}s). "
                        f"Response: {resp.text[:300]}"
                    )
                continue

            if resp.status_code not in (200, 400):
                raise RuntimeError(
                    f"Publish poll error (HTTP {resp.status_code}): {resp.text[:500]}"
                )

            body = resp.text.strip()

            # Handle JSON response
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    if data.get("isFailed"):
                        log_entries = data.get("log", "No details")
                        # Extract only error/warning entries — info messages (file patching) bury the real errors
                        if isinstance(log_entries, list):
                            error_entries = [
                                e for e in log_entries
                                if isinstance(e, dict) and e.get("logType") in ("error", "warning")
                            ]
                            if error_entries:
                                log_text = "\n".join(str(x) for x in error_entries)
                            else:
                                # No error entries found — dump last 5 entries for context
                                log_text = "\n".join(str(x) for x in log_entries[-5:])
                        else:
                            log_text = str(log_entries)
                        raise RuntimeError(f"Publish failed: {log_text[:2000]}")
                    if data.get("isCompleted"):
                        action = "Validation" if validation_only else "Publish"
                        _log(
                            f"{action} completed ({elapsed}s)",
                            style="ok",
                        )
                        # Dump publish log for SQL diagnostics
                        log_text = data.get("log", "")
                        if log_text:
                            # log may be a list (Acumatica returns array) or string
                            if isinstance(log_text, list):
                                lines = log_text
                            else:
                                lines = log_text.split("\n")
                            for line in lines:
                                if not isinstance(line, str):
                                    line = str(line)
                                line = line.strip()
                                if not line:
                                    continue
                                low = line.lower()
                                if any(kw in low for kw in ("error", "warning", "sql", "table", "create", "failed", "exception")):
                                    _log(f"  PUBLISH LOG: {line[:300]}", style="warn")
                        return
            except json.JSONDecodeError:
                pass

            # Handle plain text responses
            if body.lower() == "true":
                action = "Validation" if validation_only else "Publish"
                _log(f"{action} completed ({elapsed}s)", style="ok")
                return
            elif body.lower() == "false":
                _log(f"  Still publishing... ({elapsed}s / {poll_timeout}s)")
                continue
            else:
                _log(f"  In progress... ({elapsed}s)")

        raise TimeoutError(
            f"Publish timed out after {poll_timeout}s. "
            "Check Acumatica System Monitor for status."
        )

    def smoke_test(self, max_retries: int = 6, retry_delay: int = 10) -> bool:
        """Post-publish smoke test — re-auth and query to verify app pool restarted."""
        _log("Running post-publish smoke test...")

        for attempt in range(1, max_retries + 1):
            time.sleep(retry_delay)

            try:
                # Re-authenticate (app pool restart kills previous session)
                self.logout()
                self.login()

                # Lightweight query to verify customization DLLs loaded
                resp = self.session.get(
                    f"{self.base_url}/entity/default/24.200.001/StockItem",
                    params={"$top": "1", "$select": "InventoryID"},
                    timeout=30,
                )

                if resp.status_code == 200:
                    _log("Post-publish smoke test passed", style="ok")
                    return True

                _log(
                    f"  Smoke test attempt {attempt}/{max_retries}: "
                    f"HTTP {resp.status_code}",
                )
            except Exception as exc:
                _log(
                    f"  Smoke test attempt {attempt}/{max_retries}: {exc}",
                )

        _log(
            f"Smoke test FAILED after {max_retries} attempts — "
            "manual verification required",
            style="warn",
        )
        return False

    def download_package(
        self,
        project_name: str,
        output_dir: str = ".",
    ) -> str:
        """Download an existing customization package from Acumatica."""
        _log(f"Downloading package: {project_name}")

        resp = self.session.post(
            f"{self.base_url}/CustomizationApi/getProject",
            json={"projectName": project_name},
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Download failed (HTTP {resp.status_code}): {resp.text[:500]}"
            )

        # Response is base64-encoded zip content
        try:
            content = base64.b64decode(resp.text.strip().strip('"'))
        except Exception:
            # Some versions return raw binary
            content = resp.content

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{project_name}_backup_{ts}.zip"
        filepath = out_path / filename

        filepath.write_bytes(content)
        _log(f"Downloaded: {filepath} ({_filesize(filepath)})", style="ok")
        return str(filepath)

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, *args):
        self.logout()


# ─── Utilities ───────────────────────────────────────────────────────────────

STYLES = {
    "info": "\033[0;34m[DEPLOY]\033[0m",
    "ok": "\033[0;32m[  OK  ]\033[0m",
    "warn": "\033[1;33m[ WARN ]\033[0m",
    "err": "\033[0;31m[ERROR ]\033[0m",
}


def _log(msg: str, style: str = "info") -> None:
    prefix = STYLES.get(style, STYLES["info"])
    print(f"{prefix} {msg}", flush=True)


def _filesize(path: Path) -> str:
    size = path.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


# ─── Rollback ────────────────────────────────────────────────────────────────


def _rollback(args) -> None:
    """Rollback to a previous deploy by reimporting a snapshot or git-tagged version.

    Three modes:
      1. --rollback-from-snapshot path.zip  → Reimport a specific .zip file
      2. --rollback-to-tag deploy/prod/...  → Checkout that tag, build .zip, reimport
      3. --rollback (bare)                  → Find latest non-ROLLED-BACK tag automatically
    """
    import subprocess

    also_publish = []
    for item in args.also_publish:
        also_publish.extend([p.strip() for p in item.split(",") if p.strip()])

    snapshot_path = args.rollback_from_snapshot

    if not snapshot_path:
        # Find the tag to rollback to
        tag = args.rollback_to_tag
        if not tag:
            result = subprocess.run(
                ["git", "tag", "-l", "deploy/prod/*", "--sort=-creatordate"],
                capture_output=True, text=True,
            )
            tags = [
                t for t in result.stdout.strip().split("\n")
                if t and "ROLLED-BACK" not in t
            ]
            if len(tags) < 2:
                _log("Cannot find previous deploy tag to rollback to", style="err")
                sys.exit(1)
            # tags[0] is current deploy, tags[1] is the one before
            tag = tags[1]

        _log(f"Rolling back to tag: {tag}")

        # Checkout the tag into a temp dir and build the .zip
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                ["git", "archive", "--format=zip", "--prefix=",
                 f"{tag}", f"Customization/{args.project}/"],
                capture_output=True,
            )
            if result.returncode != 0:
                _log(f"git archive failed: {result.stderr.decode()}", style="err")
                sys.exit(1)

            snapshot_path = os.path.join(tmpdir, f"{args.project}_rollback.zip")

            # git archive includes the directory prefix — we need to strip it
            # and repackage just the project contents
            import zipfile
            with open(os.path.join(tmpdir, "raw.zip"), "wb") as f:
                f.write(result.stdout)

            prefix = f"Customization/{args.project}/"
            with zipfile.ZipFile(os.path.join(tmpdir, "raw.zip"), "r") as zin:
                with zipfile.ZipFile(snapshot_path, "w") as zout:
                    for item in zin.infolist():
                        if item.filename.startswith(prefix):
                            item.filename = item.filename[len(prefix):]
                            if item.filename:  # skip empty string (directory itself)
                                zout.writestr(item, zin.read(item.orig_filename))

            _log(f"Built rollback package from {tag}: {_filesize(Path(snapshot_path))}")

            # Now deploy it
            _deploy_snapshot(args, snapshot_path, also_publish, tag)
            return

    if not Path(snapshot_path).exists():
        _log(f"Snapshot not found: {snapshot_path}", style="err")
        sys.exit(1)

    _log(f"Rolling back from snapshot: {snapshot_path}")
    _deploy_snapshot(args, snapshot_path, also_publish, "snapshot")


def _deploy_snapshot(args, snapshot_path: str, also_publish: list, source: str) -> None:
    """Import a snapshot .zip and publish it."""
    try:
        with AcumaticaCustomizationClient(
            url=args.url,
            username=args.username,
            password=args.password,
            tenant=args.tenant,
        ) as client:
            # Backup current version first
            _log("Backing up current version before rollback...")
            try:
                client.download_package(args.project, output_dir="backups")
            except Exception as exc:
                _log(f"Backup failed (continuing with rollback): {exc}", style="warn")

            # Import rollback package
            client.import_package(args.project, snapshot_path)

            # Publish
            all_projects = [args.project] + also_publish
            _log(f"Publishing rollback ({source})...")
            client.publish(
                project_names=all_projects,
                poll_interval=args.poll_interval,
                poll_timeout=args.poll_timeout,
            )

            # Smoke test
            smoke_ok = client.smoke_test()
            if smoke_ok:
                _log(f"ROLLBACK COMPLETE — restored from {source}", style="ok")
            else:
                _log("Rollback published but smoke test failed", style="warn")
                sys.exit(1)

    except Exception as exc:
        import traceback
        _log(f"ROLLBACK FAILED: {exc}", style="err")
        traceback.print_exc()
        sys.exit(1)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Deploy Acumatica customization packages via CI/CD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--url",
        default=os.environ.get("ACUMATICA_URL", ""),
        help="Acumatica instance URL (or ACUMATICA_URL env)",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("ACUMATICA_USERNAME", ""),
        help="API username (or ACUMATICA_USERNAME env)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("ACUMATICA_PASSWORD", ""),
        help="API password (or ACUMATICA_PASSWORD env)",
    )
    parser.add_argument(
        "--tenant",
        default=os.environ.get("ACUMATICA_TENANT", ""),
        help="Tenant name (or ACUMATICA_TENANT env)",
    )
    parser.add_argument("--project", required=True, help="Customization project name")
    parser.add_argument("--package", help="Path to .zip package to deploy")
    parser.add_argument(
        "--also-publish",
        nargs="*",
        default=[],
        help="Additional project names to co-publish for conflict detection",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Upload and validate without publishing",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download existing package before deploying (backup)",
    )
    parser.add_argument(
        "--output",
        default="backups",
        help="Output directory for downloaded packages (default: backups/)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Seconds between publish status checks (default: 10)",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=600,
        help="Max seconds to wait for publish (default: 600)",
    )
    parser.add_argument(
        "--extra-import",
        action="append",
        default=[],
        help="Additional package NAME:FILE to import (repeatable)",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Use isMergeWithExistingPackages=False (clean compile, sandbox only)",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback: download current package from instance, find previous git tag, "
             "checkout that version, and redeploy it",
    )
    parser.add_argument(
        "--rollback-to-tag",
        default="",
        help="Specific git tag to rollback to (default: latest non-ROLLED-BACK deploy tag)",
    )
    parser.add_argument(
        "--rollback-from-snapshot",
        default="",
        help="Path to a .zip snapshot to restore (skips git tag lookup)",
    )
    parser.add_argument(
        "--pre-cleanup",
        action="store_true",
        help="Delete project from instance before importing. Fixes NullReferenceException "
             "corruption in CustProject table.",
    )

    args = parser.parse_args()

    # Validate required args
    if not args.url:
        parser.error("--url is required (or set ACUMATICA_URL)")
    if not args.username:
        parser.error("--username is required (or set ACUMATICA_USERNAME)")
    if not args.password:
        parser.error("--password is required (or set ACUMATICA_PASSWORD)")

    # ── Rollback mode ────────────────────────────────────────────────
    if args.rollback:
        _rollback(args)
        return

    if not args.download and not args.package:
        parser.error("--package is required (or use --download to just backup)")

    # Also-publish can come as comma-separated string (from GitHub Actions)
    also_publish = []
    for item in args.also_publish:
        also_publish.extend([p.strip() for p in item.split(",") if p.strip()])

    _log(f"Target:  {args.url}")
    _log(f"Project: {args.project}")
    if args.package:
        _log(f"Package: {args.package}")
    if also_publish:
        _log(f"Co-publish with: {', '.join(also_publish)}")
    if args.validate_only:
        _log("VALIDATE ONLY — will not publish", style="warn")

    try:
        with AcumaticaCustomizationClient(
            url=args.url,
            username=args.username,
            password=args.password,
            tenant=args.tenant,
        ) as client:

            # Optional: download existing package for backup
            if args.download:
                _log("Step 0: Backing up existing package...")
                backup_path = client.download_package(
                    args.project, output_dir=args.output
                )
                _log(f"Backup saved: {backup_path}", style="ok")

            # Pre-cleanup: delete projects before import to clear corrupted CustProject state.
            if args.pre_cleanup and args.package:
                _log("Pre-cleanup: deleting projects before import (--pre-cleanup)...", style="warn")
                client.cleanup_orphan(args.project)
                for extra in args.extra_import:
                    if ":" in extra:
                        extra_name = extra.split(":", 1)[0]
                        client.cleanup_orphan(extra_name)

            # Import new package
            if args.package:
                # Pre-flight validation
                client.preflight_validate(args.project, args.package)

                # Real import (with orphan cleanup on failure)
                _log("Importing package...")
                try:
                    client.import_package(args.project, args.package)
                except RuntimeError as exc:
                    client.cleanup_orphan(args.project)
                    raise

                # Import extra packages
                for extra in args.extra_import:
                    if ":" not in extra:
                        _log(f"Invalid --extra-import format: {extra} (expected NAME:FILE)", style="err")
                        sys.exit(1)
                    extra_name, extra_file = extra.split(":", 1)
                    _log(f"Importing extra package: {extra_name}...")
                    client.import_package(extra_name, extra_file)

                if not args.validate_only:
                    # Build full project list for publish
                    all_projects = [args.project] + also_publish

                    _log("Publishing...")
                    client.publish(
                        project_names=all_projects,
                        poll_interval=args.poll_interval,
                        poll_timeout=args.poll_timeout,
                        merge_with_existing=not args.no_merge,
                    )

            # Post-publish smoke test
            if args.package and not args.validate_only:
                smoke_ok = client.smoke_test()
                if not smoke_ok:
                    _log(
                        "Smoke test failed — publish completed but API may be unstable",
                        style="warn",
                    )

            _log("Deployment complete!", style="ok")

    except Exception as exc:
        import traceback
        _log(str(exc), style="err")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
