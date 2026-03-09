#!/usr/bin/env python3
"""
Pre-deploy snapshot tool for Acumatica customization projects.

Downloads the currently-published customization project as a .zip backup
before deploying a new version. Uses the existing AcumaticaCustomizationClient
from deploy.py.

The backup is saved to the specified output directory and intended to be
uploaded as a GitHub Actions artifact.

Non-blocking: exits 0 even on failure (snapshot is advisory, not a gate).

Usage:
  python snapshot.py --project HeritageFabricsPOv5 --output backups/
  python snapshot.py --project HeritageFabricsPOv5 --also-snapshot StudioBPORelations
"""

import argparse
import os
import sys
from pathlib import Path

# Import client from adjacent deploy.py
sys.path.insert(0, str(Path(__file__).parent))
from deploy import AcumaticaCustomizationClient, _log


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Acumatica customization project backup"
    )
    parser.add_argument("--project", required=True, help="Primary project name")
    parser.add_argument("--output", default="backups", help="Output directory")
    parser.add_argument(
        "--also-snapshot",
        nargs="*",
        default=[],
        help="Additional project names to download",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("ACUMATICA_URL", ""),
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("ACUMATICA_USERNAME", ""),
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("ACUMATICA_PASSWORD", ""),
    )
    parser.add_argument(
        "--tenant",
        default=os.environ.get("ACUMATICA_TENANT", ""),
    )

    args = parser.parse_args()

    if not all([args.url, args.username, args.password]):
        parser.error("--url, --username, --password required (or set env vars)")

    projects = [args.project] + args.also_snapshot

    _log(f"Taking pre-deploy snapshot of {len(projects)} project(s)")

    try:
        with AcumaticaCustomizationClient(
            url=args.url,
            username=args.username,
            password=args.password,
            tenant=args.tenant,
        ) as client:
            for proj in projects:
                backup_path = client.download_package(proj, output_dir=args.output)
                _log(f"Snapshot saved: {backup_path}", style="ok")

        _log(f"All {len(projects)} snapshot(s) complete", style="ok")

    except Exception as exc:
        _log(f"Snapshot failed: {exc}", style="err")
        _log("Continuing with deploy (snapshot is advisory)", style="warn")
        # Exit 0 deliberately — snapshot failure should NOT block the deploy
        sys.exit(0)


if __name__ == "__main__":
    main()
