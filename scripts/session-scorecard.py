#!/usr/bin/env python3
"""Generate a rolling 7-day session efficiency scorecard from Qdrant.

Reads per-session metrics from the `session-metrics` Qdrant collection,
computes aggregate stats, compares to prior periods and baseline,
and posts a formatted report to Slack #ops.

Designed to run in GitHub Actions (no local file access needed).

Requires: QDRANT_URL, SLACK_BOT_TOKEN
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta


QDRANT_URL = os.environ.get("QDRANT_URL", "").rstrip("/")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = "C0AR2UW2S66"  # #ops in studiob-ai
METRICS_COLLECTION = "session-metrics"


def _curl_json(url: str, body: dict) -> dict:
    """POST JSON via curl (avoids macOS SSL issues with urllib)."""
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", url,
         "-H", "Content-Type: application/json",
         "-d", json.dumps(body)],
        capture_output=True, text=True, timeout=30,
    )
    return json.loads(result.stdout)


def qdrant_scroll(date_gte: str, date_lte: str | None = None, limit: int = 500) -> list[dict]:
    """Scroll all session metrics from Qdrant within a date range."""
    all_points = []
    offset = None
    while True:
        body: dict = {
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        if offset:
            body["offset"] = offset
        resp = _curl_json(
            f"{QDRANT_URL}/collections/{METRICS_COLLECTION}/points/scroll",
            body,
        )
        points = resp.get("result", {}).get("points", [])
        next_offset = resp.get("result", {}).get("next_page_offset")
        for p in points:
            payload = p.get("payload", {})
            d = payload.get("date", "")
            if d >= date_gte and (date_lte is None or d <= date_lte):
                all_points.append(payload)
        if not next_offset or not points:
            break
        offset = next_offset
    return all_points


def compute_metrics(sessions: list[dict]) -> dict:
    """Compute aggregate metrics for a list of session payloads."""
    if not sessions:
        return {
            "sessions": 0, "total_msgs": 0, "avg_msgs": 0, "marathons": 0,
            "retry_rate": 0.0, "total_screenshots": 0, "total_retries": 0,
            "total_kb": 0, "avg_kb": 0, "sessions_per_day": 0.0,
            "worst_session": None,
        }

    total_msgs = sum(s.get("msgs", 0) for s in sessions)
    total_retries = sum(s.get("retries", 0) for s in sessions)
    total_screenshots = sum(s.get("screenshots", 0) for s in sessions)
    total_kb = sum(s.get("size_kb", 0) for s in sessions)
    marathons = sum(1 for s in sessions if s.get("is_marathon"))
    unique_days = len(set(s.get("date", "") for s in sessions))

    worst = None
    worst_rate = 0
    for s in sessions:
        msgs = s.get("msgs", 0)
        retries = s.get("retries", 0)
        if msgs > 10:
            rate = retries / msgs
            if rate > worst_rate:
                worst_rate = rate
                worst = s

    return {
        "sessions": len(sessions),
        "total_msgs": total_msgs,
        "avg_msgs": round(total_msgs / len(sessions)) if sessions else 0,
        "marathons": marathons,
        "retry_rate": round(total_retries / total_msgs, 2) if total_msgs else 0,
        "total_screenshots": total_screenshots,
        "total_retries": total_retries,
        "total_kb": round(total_kb),
        "avg_kb": round(total_kb / len(sessions)) if sessions else 0,
        "sessions_per_day": round(len(sessions) / max(unique_days, 1), 1),
        "worst_session": worst,
    }


def trend_arrow(current: float, previous: float) -> str:
    if previous == 0:
        return "—"
    pct = ((current - previous) / previous) * 100
    if abs(pct) < 5:
        return "→"
    return f"↓ {abs(pct):.0f}%" if pct < 0 else f"↑ {abs(pct):.0f}%"


def grade(m: dict) -> str:
    score = 100
    rr = m["retry_rate"]
    if rr > 0.4: score -= 30
    elif rr > 0.2: score -= 15
    elif rr > 0.1: score -= 5

    mar = m["marathons"]
    if mar >= 6: score -= 20
    elif mar >= 3: score -= 10
    elif mar >= 1: score -= 5

    if m["total_screenshots"] > 50: score -= 15
    elif m["total_screenshots"] > 20: score -= 5

    if m["sessions_per_day"] > 12: score -= 15
    elif m["sessions_per_day"] > 8: score -= 5

    if m["avg_msgs"] > 40: score -= 10
    elif m["avg_msgs"] > 30: score -= 5

    if score >= 90: return "A"
    if score >= 80: return "A-"
    if score >= 70: return "B+"
    if score >= 60: return "B"
    if score >= 50: return "C"
    if score >= 40: return "D"
    return "F"


BASELINE = {
    "sessions": 101, "total_msgs": 1824, "avg_msgs": 18, "marathons": 8,
    "retry_rate": 1.53, "total_screenshots": 276, "total_retries": 2809,
    "total_kb": 5252, "avg_kb": 52, "sessions_per_day": 14.4,
    "worst_session": None,
}


def format_message(cur: dict, prev: dict, avg30: dict, base: dict, cur_g: str, prev_g: str) -> str:
    emoji_map = {"A": ":large_green_circle:", "A-": ":large_green_circle:",
                 "B+": ":large_yellow_circle:", "B": ":large_yellow_circle:",
                 "C": ":warning:", "D": ":red_circle:", "F": ":red_circle:"}
    emoji = emoji_map.get(cur_g, ":white_circle:")
    grade_ord = ["F", "D", "C", "B", "B+", "A-", "A"]
    gt = ""
    if prev_g and prev_g != cur_g:
        gt = " ↑" if grade_ord.index(cur_g) > grade_ord.index(prev_g) else " ↓"

    lines = [
        f"{emoji} *Claude Session Efficiency — Rolling 7 Days*  Grade: *{cur_g}{gt}*",
        "",
        f"*Sessions:* {cur['sessions']}  ({cur['sessions_per_day']}/day)  |  *Messages:* {cur['total_msgs']}  (avg {cur['avg_msgs']}/session)",
        "",
        "```",
        f"{'Metric':<24} {'This Week':>10} {'Last Week':>10} {'Trend':>8} {'30d Avg':>10} {'Baseline':>10}",
        f"{'-'*24} {'-'*10} {'-'*10} {'-'*8} {'-'*10} {'-'*10}",
    ]

    rows = [
        ("Retry rate", f"{cur['retry_rate']:.2f}", f"{prev['retry_rate']:.2f}",
         trend_arrow(cur['retry_rate'], prev['retry_rate']),
         f"{avg30['retry_rate']:.2f}", f"{base['retry_rate']:.2f}"),
        ("50+ msg sessions", str(cur['marathons']), str(prev['marathons']),
         trend_arrow(cur['marathons'], prev['marathons']),
         str(avg30['marathons']), str(base['marathons'])),
        ("Screenshots", str(cur['total_screenshots']), str(prev['total_screenshots']),
         trend_arrow(cur['total_screenshots'], prev['total_screenshots']),
         str(avg30['total_screenshots']), str(base['total_screenshots'])),
        ("Avg msgs/session", str(cur['avg_msgs']), str(prev['avg_msgs']),
         trend_arrow(cur['avg_msgs'], prev['avg_msgs']),
         str(avg30['avg_msgs']), str(base['avg_msgs'])),
        ("Sessions/day", f"{cur['sessions_per_day']:.1f}", f"{prev['sessions_per_day']:.1f}",
         trend_arrow(cur['sessions_per_day'], prev['sessions_per_day']),
         f"{avg30['sessions_per_day']:.1f}", f"{base['sessions_per_day']:.1f}"),
        ("Avg session KB", str(cur['avg_kb']), str(prev['avg_kb']),
         trend_arrow(cur['avg_kb'], prev['avg_kb']),
         str(avg30['avg_kb']), str(base['avg_kb'])),
    ]
    for label, c, p, t, a, b in rows:
        lines.append(f"{label:<24} {c:>10} {p:>10} {t:>8} {a:>10} {b:>10}")
    lines.append("```")

    ws = cur.get("worst_session")
    if ws and ws.get("msgs", 0) > 0 and ws.get("retries", 0) / ws["msgs"] > 0.5:
        lines.extend(["", f":eyes: *Worst session:* {ws['date']} — _{ws.get('title','')[:60]}_ — {ws['msgs']} msgs, {ws['retries']} retries ({ws['retries']/ws['msgs']:.1f}x rate)"])

    tips = []
    if cur["retry_rate"] > 0.3:
        tips.append("Retry rate is high — kill sessions after 3 failed attempts and re-scope")
    if cur["marathons"] > 0:
        tips.append(f"{cur['marathons']} marathon session(s) — break at 50 messages")
    if cur["total_screenshots"] > 30:
        tips.append("Screenshot-heavy week — describe changes in text after the first image")
    if cur["sessions_per_day"] > 10:
        tips.append(f"{cur['sessions_per_day']:.0f} sessions/day — batch related work into fewer sessions")
    if tips:
        lines.extend(["", "*Action items:*"] + [f"• {t}" for t in tips])

    return "\n".join(lines)


def post_to_slack(message: str) -> bool:
    if not SLACK_BOT_TOKEN:
        print("SLACK_BOT_TOKEN not set", file=sys.stderr)
        return False
    payload = json.dumps({"channel": SLACK_CHANNEL, "text": message, "unfurl_links": False})
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", "https://slack.com/api/chat.postMessage",
         "-H", "Content-Type: application/json; charset=utf-8",
         "-H", f"Authorization: Bearer {SLACK_BOT_TOKEN}",
         "-d", payload],
        capture_output=True, text=True, timeout=15,
    )
    resp = json.loads(result.stdout)
    if not resp.get("ok"):
        print(f"Slack error: {resp.get('error')}", file=sys.stderr)
        return False
    return True


def main():
    if not QDRANT_URL:
        print("QDRANT_URL required", file=sys.stderr)
        sys.exit(1)

    today = datetime.now().date()

    # Fetch sessions for each period
    d7 = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    d14 = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    d30 = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    d7_minus1 = (today - timedelta(days=8)).strftime("%Y-%m-%d")

    print("Fetching session metrics from Qdrant...")
    all_sessions = qdrant_scroll(d30, today_str)
    print(f"  Found {len(all_sessions)} sessions in last 30 days")

    current_7d = [s for s in all_sessions if s.get("date", "") >= d7]
    prev_7d = [s for s in all_sessions if d14 <= s.get("date", "") < d7]
    all_30d = all_sessions

    cur = compute_metrics(current_7d)
    prev = compute_metrics(prev_7d)
    raw30 = compute_metrics(all_30d)

    # Normalize 30d totals to per-week
    unique_days_30 = len(set(s.get("date", "") for s in all_30d))
    weeks = max(unique_days_30, 1) / 7
    avg30 = dict(raw30)
    for key in ["marathons", "total_screenshots", "total_retries"]:
        avg30[key] = round(raw30[key] / max(weeks, 1))

    cur_g = grade(cur)
    prev_g = grade(prev)

    message = format_message(cur, prev, avg30, BASELINE, cur_g, prev_g)
    print(message)

    if SLACK_BOT_TOKEN:
        if post_to_slack(message):
            print("\n✅ Posted to #ops")
        else:
            print("\n❌ Failed to post", file=sys.stderr)
            sys.exit(1)
    else:
        print("\nNo SLACK_BOT_TOKEN — dry run only")


if __name__ == "__main__":
    main()
