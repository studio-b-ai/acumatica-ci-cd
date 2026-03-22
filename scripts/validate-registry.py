#!/usr/bin/env python3
"""
validate-registry.py — Pre-deploy safety check.

Validates that config/package-registry.json matches what's actually
installed on an Acumatica instance and that custom packages have
corresponding repo directories.

Usage:
    python3 scripts/validate-registry.py \
        --registry config/package-registry.json \
        --environment production \
        --url https://heritagefabrics.acumatica.com \
        --username api-bot --password SECRET --tenant "Heritage Fabrics"

    python3 scripts/validate-registry.py \
        --registry config/package-registry.json \
        --environment sandbox --offline
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


def load_registry(registry_path: str, environment: str) -> dict:
    """Load and validate the package registry JSON."""
    with open(registry_path, "r") as f:
        registry = json.load(f)

    if environment not in registry:
        print(f"ERROR: Environment '{environment}' not found in registry. "
              f"Available: {', '.join(registry.keys())}", file=sys.stderr)
        sys.exit(1)

    return registry[environment]


def get_installed_projects(url: str, username: str, password: str, tenant: str) -> list[str] | None:
    """Query Acumatica CustomizationApi to list installed projects.

    Returns a list of project names, or None if the API is unavailable.
    """
    base = url.rstrip("/")
    session = requests.Session()

    # Login
    login_payload = {"name": username, "password": password, "tenant": tenant}
    try:
        resp = session.post(f"{base}/entity/auth/login", json=login_payload, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR: Failed to authenticate with Acumatica: {e}", file=sys.stderr)
        return None

    # Get projects
    installed = None
    try:
        resp = session.post(f"{base}/CustomizationApi/getProjects", json={}, timeout=30)
        if resp.status_code in (404, 405, 500, 501):
            print(f"WARNING: CustomizationApi/getProjects returned {resp.status_code} — "
                  "endpoint may not exist on this Acumatica version. Skipping API check.")
            installed = None
        else:
            resp.raise_for_status()
            data = resp.json()
            # Response is a list of project info objects or strings
            if isinstance(data, list):
                installed = []
                for item in data:
                    if isinstance(item, str):
                        installed.append(item)
                    elif isinstance(item, dict):
                        # Try common field names
                        name = item.get("name") or item.get("Name") or item.get("projectName") or item.get("ProjectName")
                        if name:
                            installed.append(name)
                        else:
                            # Use first string value as fallback
                            for v in item.values():
                                if isinstance(v, str) and v:
                                    installed.append(v)
                                    break
            else:
                print(f"WARNING: Unexpected response format from getProjects: {type(data).__name__}. "
                      "Skipping API check.")
    except requests.RequestException as e:
        print(f"WARNING: Failed to query installed projects: {e}. Skipping API check.")

    # Logout (best-effort)
    try:
        session.post(f"{base}/entity/auth/logout", timeout=10)
    except requests.RequestException:
        pass

    return installed


def find_repo_root(registry_path: str) -> Path:
    """Find the repo root relative to the registry file path."""
    # Registry is at config/package-registry.json, repo root is one level up
    return Path(registry_path).resolve().parent.parent


def validate(registry_path: str, environment: str, installed_projects: list[str] | None,
             repo_root: Path) -> tuple[list[str], list[str], list[str]]:
    """Run all validation checks.

    Returns (ok_messages, warning_messages, error_messages).
    """
    env_config = load_registry(registry_path, environment)
    packages = env_config.get("packages", {})
    custom_packages = packages.get("custom", [])
    isv_packages = packages.get("isv", [])
    all_registry = custom_packages + isv_packages

    ok: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    # --- Check 1: Registry vs installed (if we have API data) ---
    if installed_projects is not None:
        installed_set = set(installed_projects)
        registry_set = set(all_registry)

        # Packages in both registry and instance
        matched = registry_set & installed_set
        for pkg in sorted(matched):
            ok.append(f"Package '{pkg}' is in registry and installed on instance")

        # Installed but not in registry (ghosts)
        ghosts = installed_set - registry_set
        for pkg in sorted(ghosts):
            warnings.append(f"Package '{pkg}' is installed on instance but NOT in registry (ghost)")

        # In registry but not installed
        missing_on_instance = registry_set - installed_set
        for pkg in sorted(missing_on_instance):
            warnings.append(f"Package '{pkg}' is in registry but NOT installed on instance")
    else:
        ok.append(f"API check skipped — {len(all_registry)} packages in registry for '{environment}'")

    # --- Check 2: Custom packages must have repo directories ---
    customization_dir = repo_root / "Customization"
    for pkg in custom_packages:
        pkg_dir = customization_dir / pkg
        if pkg_dir.is_dir():
            ok.append(f"Custom package '{pkg}' has repo directory: Customization/{pkg}/")
        else:
            errors.append(f"Custom package '{pkg}' is in registry but has NO repo directory "
                          f"(expected: Customization/{pkg}/)")

    # --- Check 3: Repo directories not in registry (informational) ---
    if customization_dir.is_dir():
        repo_dirs = {d.name for d in customization_dir.iterdir()
                     if d.is_dir() and not d.name.startswith(("_", "."))}
        custom_set = set(custom_packages)
        orphan_dirs = repo_dirs - custom_set
        for d in sorted(orphan_dirs):
            warnings.append(f"Repo directory 'Customization/{d}/' exists but is not in "
                            f"'{environment}' registry (may be used by another environment)")

    return ok, warnings, errors


def print_report(ok: list[str], warnings: list[str], errors: list[str], environment: str) -> None:
    """Print a formatted validation report."""
    total = len(ok) + len(warnings) + len(errors)

    print()
    print(f"{'=' * 60}")
    print(f"  Registry Validation Report — {environment}")
    print(f"{'=' * 60}")
    print()

    if ok:
        for msg in ok:
            print(f"  OK       {msg}")
        print()

    if warnings:
        for msg in warnings:
            print(f"  WARNING  {msg}")
        print()

    if errors:
        for msg in errors:
            print(f"  ERROR    {msg}")
        print()

    print(f"{'-' * 60}")
    print(f"  Summary: {len(ok)} ok, {len(warnings)} warnings, {len(errors)} errors")
    print(f"{'-' * 60}")
    print()

    if errors:
        print("  RESULT: FAIL — errors must be resolved before deploy")
    elif warnings:
        print("  RESULT: PASS (with warnings)")
    else:
        print("  RESULT: PASS")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Validate package-registry.json against Acumatica instance and repo directories."
    )
    parser.add_argument("--registry", required=True,
                        help="Path to package-registry.json")
    parser.add_argument("--environment", required=True, choices=["sandbox", "production"],
                        help="Environment to validate")
    parser.add_argument("--url", default=None,
                        help="Acumatica instance URL (e.g. https://heritagefabrics.acumatica.com)")
    parser.add_argument("--username", default=None, help="Acumatica API username")
    parser.add_argument("--password", default=None, help="Acumatica API password")
    parser.add_argument("--tenant", default=None, help="Acumatica tenant name")
    parser.add_argument("--offline", action="store_true",
                        help="Skip Acumatica API check, only verify repo directories")

    args = parser.parse_args()

    # Validate registry file exists
    if not os.path.isfile(args.registry):
        print(f"ERROR: Registry file not found: {args.registry}", file=sys.stderr)
        sys.exit(1)

    # Load registry to validate JSON early
    env_config = load_registry(args.registry, args.environment)

    # Determine if we can do API check
    installed_projects = None
    if not args.offline:
        has_creds = all([args.url, args.username, args.password, args.tenant])
        if has_creds:
            url = args.url if args.url.startswith("http") else f"https://{args.url}"
            print(f"Querying Acumatica instance: {url} ...")
            installed_projects = get_installed_projects(url, args.username, args.password, args.tenant)
        else:
            # Try environment variables as fallback
            env_url = args.url or os.environ.get("ACUMATICA_URL") or f"https://{env_config.get('url', '')}"
            env_user = args.username or os.environ.get("ACUMATICA_USERNAME")
            env_pass = args.password or os.environ.get("ACUMATICA_PASSWORD")
            env_tenant = args.tenant or os.environ.get("ACUMATICA_TENANT") or env_config.get("tenant")

            if all([env_url, env_user, env_pass, env_tenant]):
                url = env_url if env_url.startswith("http") else f"https://{env_url}"
                print(f"Querying Acumatica instance (env vars): {url} ...")
                installed_projects = get_installed_projects(url, env_user, env_pass, env_tenant)
            else:
                print("No Acumatica credentials provided — running in offline mode.")
    else:
        print("Offline mode — skipping Acumatica API check.")

    # Run validation
    repo_root = find_repo_root(args.registry)
    ok, warnings, errors = validate(args.registry, args.environment, installed_projects, repo_root)

    # Print report
    print_report(ok, warnings, errors, args.environment)

    # Exit code
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
