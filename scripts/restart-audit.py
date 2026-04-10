#!/usr/bin/env python3
"""Daily Acumatica app pool restart audit.

Queries GitHub Actions for deploy workflows that cause app pool restarts,
classifies by environment, and DMs a summary to Kevin via Slack.

Requires: GH_TOKEN (or gh CLI auth), SLACK_BOT_TOKEN, SLACK_KEVIN_USER_ID
"""

import json
import os
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

ET = timezone(timedelta(hours=-4))  # EDT — adjust to -5 for EST
REPO = os.environ.get("GITHUB_REPOSITORY", "studio-b-ai/acumatica-ci-cd")

RESTART_WORKFLOWS = [
    "AcuOps Deploy",
    "Deploy Hotfix Package",
    "Sync Test Environment",
]

# Job name patterns that indicate an actual deploy (not just CI)
DEPLOY_JOB_PATTERNS = {
    "Sandbox Publish": "SANDBOX",
    "Deploy to production": "PRODUCTION",
    "Deploy to staging": "PROD (staging tenant)",
    "Invoke Deploy Agent": "PROD (via agent)",
}


def gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"gh {' '.join(args[:4])}... failed: {result.stderr[:200]}", file=sys.stderr)
        return "[]"
    return result.stdout


def query_runs(workflow: str, days: int = 7) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw = gh(
        "run", "list",
        f"--repo={REPO}",
        f"--workflow={workflow}",
        "--limit=200",
        "--json=conclusion,startedAt,displayTitle,databaseId",
    )
    runs = json.loads(raw)
    return [r for r in runs if r.get("startedAt", "") >= since]


def get_successful_deploy_jobs(run_id: int) -> list[str]:
    raw = gh("run", "view", str(run_id), f"--repo={REPO}", "--json=jobs")
    try:
        jobs = json.loads(raw).get("jobs", [])
    except (json.JSONDecodeError, TypeError):
        return []
    return [
        j["name"]
        for j in jobs
        if j.get("conclusion") == "success"
    ]


def classify_restarts(days: int = 7) -> list[dict]:
    restarts = []

    for workflow in RESTART_WORKFLOWS:
        runs = query_runs(workflow, days)

        for run in runs:
            rid = run["databaseId"]
            started = run["startedAt"]
            title = run.get("displayTitle", "")[:80]
            conclusion = run.get("conclusion", "")

            if workflow == "Deploy Hotfix Package":
                if conclusion == "success":
                    restarts.append(make_entry("PRODUCTION", started, title, "Deploy Hotfix"))
                continue

            if workflow == "Sync Test Environment":
                if conclusion == "success":
                    restarts.append(make_entry("PROD (test sync)", started, title, "Sync Test Env"))
                continue

            # AcuOps Deploy — need job-level inspection
            jobs = get_successful_deploy_jobs(rid)
            for job_name in jobs:
                for pattern, env in DEPLOY_JOB_PATTERNS.items():
                    if pattern in job_name:
                        restarts.append(make_entry(env, started, title, "AcuOps Deploy"))
                        break

    restarts.sort(key=lambda x: x["time_utc"])
    return restarts


def make_entry(env: str, started_at: str, title: str, workflow: str) -> dict:
    ts = datetime.fromisoformat(started_at.replace("Z", "+00:00")).astimezone(ET)
    return {
        "env": env,
        "time_utc": started_at[:19],
        "time_et": ts.strftime("%Y-%m-%d %I:%M %p ET"),
        "date_et": ts.strftime("%Y-%m-%d"),
        "hour_et": ts.hour,
        "weekday": ts.weekday(),
        "trigger": title,
        "workflow": workflow,
    }


def is_business_hours(entry: dict) -> bool:
    return entry["weekday"] < 5 and 9 <= entry["hour_et"] < 17


def format_slack_message(restarts: list[dict]) -> str:
    yesterday = (datetime.now(ET) - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_restarts = [r for r in restarts if r["date_et"] == yesterday]
    biz_hours = [r for r in restarts if is_business_hours(r)]

    # Rolling 7-day totals
    env_counts = Counter(r["env"] for r in restarts)
    total = len(restarts)

    # Prod impact (everything except sandbox)
    prod_impact = sum(c for env, c in env_counts.items() if env != "SANDBOX")

    lines = [f"*Acumatica Restart Audit — {yesterday}*"]
    lines.append("")

    # Yesterday section
    if yesterday_restarts:
        lines.append(f"*Yesterday:* {len(yesterday_restarts)} restart(s)")
        for r in yesterday_restarts:
            biz = " :warning:" if is_business_hours(r) else ""
            lines.append(f"  • {r['time_et']} — {r['env']} — {r['trigger'][:50]}{biz}")
    else:
        lines.append("*Yesterday:* No restarts :white_check_mark:")

    lines.append("")

    # 7-day rolling
    lines.append(f"*7-day rolling:* {total} total ({prod_impact} prod impact)")
    for env, count in env_counts.most_common():
        lines.append(f"  • {env}: {count}")

    # Business hours violations
    lines.append("")
    if biz_hours:
        lines.append(f":warning: *Business-hours restarts (7d):* {len(biz_hours)}")
        for r in biz_hours:
            lines.append(f"  • {r['time_et']} — {r['env']} — {r['trigger'][:50]}")
    else:
        lines.append("*Business-hours restarts (7d):* None :white_check_mark:")

    return "\n".join(lines)


def post_to_slack(message: str) -> None:
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel_id = os.environ.get("SLACK_CHANNEL_ID", "")

    if not bot_token or not channel_id:
        print("SLACK_BOT_TOKEN or SLACK_CHANNEL_ID not set — printing to stdout instead")
        print(message)
        return

    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": channel_id, "text": message}).encode(),
        headers=headers,
        method="POST",
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("ok"):
        print(f"Sent restart audit to channel {channel_id}")
    else:
        print(f"Slack error: {resp.get('error')}", file=sys.stderr)
        sys.exit(1)


def main():
    print("Querying GitHub Actions for restart-causing workflows (last 7 days)...")
    restarts = classify_restarts(days=7)
    print(f"Found {len(restarts)} restarts")

    message = format_slack_message(restarts)
    print("\n--- Message Preview ---")
    print(message)
    print("--- End Preview ---\n")

    post_to_slack(message)


if __name__ == "__main__":
    main()
