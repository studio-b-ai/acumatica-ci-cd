#!/usr/bin/env python3
"""
Acumatica Customization Deployment Script (Python)

Deploys customization packages via the Acumatica Customization API with
additional features over the bash version:
  - Download existing packages for backup (--download)
  - Co-publish multiple projects for conflict detection (--also-publish)
  - Reusable AcumaticaCustomizationClient class

API Flow:
  1. POST /entity/auth/login            - Authenticate session
  2. PUT  /CustomizationApi/import       - Upload .zip package
  3. POST /CustomizationApi/publishBegin - Start publish
  4. GET  /CustomizationApi/publishEnd   - Poll until complete
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

  # Co-publish with other active projects
  python deploy.py --project MyProject --package dist/MyProject.zip \\
    --also-publish VARPackage ShopifyConnector
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

    def login(self) -> None:
        """Authenticate and establish a session cookie."""
        payload = {"name": self.username, "password": self.password}
        if self.tenant:
            payload["tenant"] = self.tenant

        resp = self.session.post(
            f"{self.base_url}/entity/auth/login",
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code != 204:
            raise RuntimeError(
                f"Login failed (HTTP {resp.status_code}): {resp.text[:500]}"
            )

        self._authenticated = True
        _log("Authenticated", style="ok")

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
            "projectContent": content_b64,
        }

        _log(f"Importing {path.name} ({_filesize(path)})...")
        resp = self.session.put(
            f"{self.base_url}/CustomizationApi/import",
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code not in (200, 204):
            raise RuntimeError(
                f"Import failed (HTTP {resp.status_code}): {resp.text[:500]}"
            )

        _log(f"Package imported: {project_name}", style="ok")

    def publish(
        self,
        project_names: list[str],
        poll_interval: int = 10,
        poll_timeout: int = 600,
        validation_only: bool = False,
    ) -> None:
        """Publish one or more customization projects and wait for completion."""
        _log(f"Publishing: {', '.join(project_names)}")

        payload = {
            "isMergeWithExistingPackages": False,
            "isOnlyValidation": validation_only,
            "isOnlyDbUpdates": False,
            "projectNames": project_names,
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
        while elapsed < poll_timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval

            resp = self.session.get(
                f"{self.base_url}/CustomizationApi/publishEnd",
                timeout=self.timeout,
            )

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Publish poll error (HTTP {resp.status_code}): {resp.text[:500]}"
                )

            body = resp.text.strip()

            # Handle JSON response
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    if data.get("isFailed"):
                        log_text = data.get("log", "No details")
                        raise RuntimeError(f"Publish failed: {log_text[:1000]}")
                    if data.get("isCompleted"):
                        action = "Validation" if validation_only else "Publish"
                        _log(
                            f"{action} completed ({elapsed}s)",
                            style="ok",
                        )
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

    def download_package(
        self,
        project_name: str,
        output_dir: str = ".",
    ) -> str:
        """Download an existing customization package from Acumatica."""
        _log(f"Downloading package: {project_name}")

        resp = self.session.get(
            f"{self.base_url}/CustomizationApi/export",
            params={"projectName": project_name},
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
    print(f"{prefix} {msg}")


def _filesize(path: Path) -> str:
    size = path.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


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

    args = parser.parse_args()

    # Validate required args
    if not args.url:
        parser.error("--url is required (or set ACUMATICA_URL)")
    if not args.username:
        parser.error("--username is required (or set ACUMATICA_USERNAME)")
    if not args.password:
        parser.error("--password is required (or set ACUMATICA_PASSWORD)")
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

            # Import new package
            if args.package:
                _log("Importing package...")
                client.import_package(args.project, args.package)

                if not args.validate_only:
                    # Build full project list for publish
                    all_projects = [args.project] + also_publish

                    _log("Publishing...")
                    client.publish(
                        project_names=all_projects,
                        poll_interval=args.poll_interval,
                        poll_timeout=args.poll_timeout,
                    )

            _log("Deployment complete!", style="ok")

    except Exception as exc:
        _log(str(exc), style="err")
        sys.exit(1)


if __name__ == "__main__":
    main()
