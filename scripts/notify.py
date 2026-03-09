#!/usr/bin/env python3
"""
Maintenance notification sender for Acumatica CI/CD deployments.

Sends countdown warnings (20/5/1 min), "system online", and "deploy failed"
notifications via Microsoft Graph API email and Slack incoming webhook.

Best-effort delivery: notification failures log warnings but exit 0 so
they never abort the deploy pipeline.

Usage:
  python notify.py --type countdown --minutes 20 \
    --recipients "user1@hf.com,user2@hf.com" \
    --sender "kevin@heritagefabrics.com" \
    --project "HeritageFabricsPOv5" \
    --environment production \
    --slack-webhook "$SLACK_WEBHOOK_URL"

Environment variable fallbacks for Microsoft Graph API credentials:
  AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests


# ─── Logging ────────────────────────────────────────────────────────────────

def _log(msg: str, style: str = "info") -> None:
    styles = {
        "info": "\033[0;34m[NOTIFY]\033[0m",
        "ok": "\033[0;32m[  OK  ]\033[0m",
        "warn": "\033[1;33m[ WARN ]\033[0m",
        "err": "\033[0;31m[ERROR ]\033[0m",
    }
    prefix = styles.get(style, styles["info"])
    print(f"{prefix} {msg}")


# ─── Microsoft Graph API Email ──────────────────────────────────────────────

class GraphMailSender:
    """Send email via Microsoft Graph API using client credentials flow."""

    TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    SEND_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None

    def _get_token(self) -> str:
        """Acquire OAuth2 token via client credentials grant."""
        if self._token:
            return self._token

        url = self.TOKEN_URL.format(tenant_id=self.tenant_id)
        resp = requests.post(
            url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Graph token request failed (HTTP {resp.status_code}): {resp.text[:300]}"
            )

        self._token = resp.json()["access_token"]
        return self._token

    def send_mail(
        self,
        sender: str,
        recipients: list[str],
        subject: str,
        body_html: str,
    ) -> None:
        """Send email via POST /v1.0/users/{sender}/sendMail."""
        token = self._get_token()
        url = self.SEND_URL.format(sender=sender)

        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html,
                },
                "toRecipients": [
                    {"emailAddress": {"address": r.strip()}}
                    for r in recipients
                    if r.strip()
                ],
            },
            "saveToSentItems": False,
        }

        resp = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            _log(f"Rate limited — retrying in {retry_after}s", style="warn")
            import time
            time.sleep(retry_after)
            resp = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

        if resp.status_code not in (200, 202):
            raise RuntimeError(
                f"Graph sendMail failed (HTTP {resp.status_code}): {resp.text[:300]}"
            )


# ─── Slack ──────────────────────────────────────────────────────────────────

def send_slack(webhook_url: str, text: str) -> None:
    """Send Slack notification via incoming webhook."""
    if not webhook_url:
        return
    try:
        requests.post(
            webhook_url,
            json={"text": text},
            timeout=10,
        )
    except Exception as exc:
        _log(f"Slack notification failed: {exc}", style="warn")


# ─── Message Templates ─────────────────────────────────────────────────────

def _html_wrapper(title: str, body: str, urgency: str = "info") -> str:
    """Wrap body content in a styled HTML email template."""
    colors = {
        "info": "#2563eb",      # blue
        "warning": "#d97706",   # amber
        "urgent": "#dc2626",    # red
        "success": "#16a34a",   # green
        "error": "#dc2626",     # red
    }
    accent = colors.get(urgency, colors["info"])

    return f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">
  <div style="border-left: 4px solid {accent}; padding: 16px 20px; background: #f8fafc; border-radius: 4px;">
    <h2 style="margin: 0 0 12px; color: #1e293b; font-size: 18px;">{title}</h2>
    {body}
  </div>
  <p style="color: #94a3b8; font-size: 12px; margin-top: 16px;">
    Automated notification from Studio B CI/CD Pipeline
  </p>
</div>"""


def build_countdown_message(
    minutes: int, project: str, environment: str
) -> tuple[str, str, str]:
    """Return (subject, html_body, slack_text) for countdown warning."""
    if minutes >= 20:
        subject = "[Acumatica] Scheduled Maintenance in 20 Minutes"
        urgency = "info"
        action = "Please save your work and complete any in-progress transactions."
        emoji = ":calendar:"
    elif minutes >= 5:
        subject = "[Acumatica] Maintenance Starting in 5 Minutes"
        urgency = "warning"
        action = "Please save all open work immediately. Avoid starting new transactions."
        emoji = ":warning:"
    else:
        subject = "[Acumatica] MAINTENANCE STARTING NOW \u2014 Save Your Work"
        urgency = "urgent"
        action = "<strong>Save your work NOW.</strong> All active sessions will be terminated in approximately 1 minute."
        emoji = ":rotating_light:"

    body = f"""\
    <p style="color: #334155; line-height: 1.6; margin: 0 0 12px;">
      A system update will be applied to <strong>Acumatica ({environment})</strong> in
      approximately <strong>{minutes} minute{"s" if minutes != 1 else ""}</strong>.
    </p>
    <p style="color: #334155; line-height: 1.6; margin: 0 0 12px;">
      {action}
    </p>
    <table style="font-size: 14px; color: #475569; margin: 12px 0;">
      <tr><td style="padding: 2px 12px 2px 0; font-weight: 600;">Project:</td><td>{project}</td></tr>
      <tr><td style="padding: 2px 12px 2px 0; font-weight: 600;">Estimated downtime:</td><td>2\u20135 minutes</td></tr>
      <tr><td style="padding: 2px 12px 2px 0; font-weight: 600;">Impact:</td><td>Active sessions will be terminated during restart</td></tr>
    </table>"""

    html = _html_wrapper(f"Maintenance in {minutes} Minute{'s' if minutes != 1 else ''}", body, urgency)

    slack = (
        f"{emoji} *Acumatica Maintenance \u2014 {minutes} minute{'s' if minutes != 1 else ''} remaining*\n"
        f"Project: `{project}` on `{environment}`\n"
        f"{action.replace('<strong>', '*').replace('</strong>', '*')}"
    )

    return subject, html, slack


def build_online_message(
    project: str, environment: str
) -> tuple[str, str, str]:
    """Return (subject, html_body, slack_text) for system-back-online."""
    subject = "[Acumatica] System Back Online"

    body = f"""\
    <p style="color: #334155; line-height: 1.6; margin: 0 0 12px;">
      The scheduled maintenance for <strong>Acumatica ({environment})</strong> has completed successfully.
      The system is available for normal use.
    </p>
    <table style="font-size: 14px; color: #475569; margin: 12px 0;">
      <tr><td style="padding: 2px 12px 2px 0; font-weight: 600;">Project:</td><td>{project}</td></tr>
      <tr><td style="padding: 2px 12px 2px 0; font-weight: 600;">Status:</td><td style="color: #16a34a; font-weight: 600;">Online</td></tr>
    </table>"""

    html = _html_wrapper("System Back Online", body, "success")
    slack = (
        f":white_check_mark: *Acumatica \u2014 System Back Online*\n"
        f"Project: `{project}` on `{environment}`\n"
        f"Maintenance completed successfully. System is available."
    )
    return subject, html, slack


def build_failed_message(
    project: str, environment: str
) -> tuple[str, str, str]:
    """Return (subject, html_body, slack_text) for deploy failure."""
    subject = "[Acumatica] Maintenance Issue \u2014 Status Update"

    body = f"""\
    <p style="color: #334155; line-height: 1.6; margin: 0 0 12px;">
      The scheduled deployment for <strong>Acumatica ({environment})</strong> encountered an issue.
      The IT team is investigating. You may experience intermittent availability.
    </p>
    <table style="font-size: 14px; color: #475569; margin: 12px 0;">
      <tr><td style="padding: 2px 12px 2px 0; font-weight: 600;">Project:</td><td>{project}</td></tr>
      <tr><td style="padding: 2px 12px 2px 0; font-weight: 600;">Status:</td><td style="color: #dc2626; font-weight: 600;">Issue Detected</td></tr>
    </table>
    <p style="color: #334155; line-height: 1.6; margin: 0;">
      No action is required from you. We will send a follow-up once the system is confirmed stable.
    </p>"""

    html = _html_wrapper("Maintenance Issue", body, "error")
    slack = (
        f":x: *Acumatica \u2014 Deploy Issue Detected*\n"
        f"Project: `{project}` on `{environment}`\n"
        f"Deployment encountered an issue. Investigating."
    )
    return subject, html, slack


# ─── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send Acumatica maintenance notifications (email + Slack)"
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=["countdown", "online", "failed"],
        help="Notification type",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        help="Minutes remaining (required for countdown type)",
    )
    parser.add_argument(
        "--recipients",
        required=True,
        help="Comma-separated email addresses",
    )
    parser.add_argument(
        "--sender",
        required=True,
        help="Sender email address",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Customization project name",
    )
    parser.add_argument(
        "--environment",
        default="production",
        help="Target environment (default: production)",
    )
    parser.add_argument(
        "--slack-webhook",
        default=os.environ.get("SLACK_WEBHOOK_URL", ""),
        help="Slack incoming webhook URL",
    )
    parser.add_argument(
        "--tenant-id",
        default=os.environ.get("AZURE_TENANT_ID", ""),
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("AZURE_CLIENT_ID", ""),
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("AZURE_CLIENT_SECRET", ""),
    )

    args = parser.parse_args()

    if args.type == "countdown" and not args.minutes:
        parser.error("--minutes is required for countdown type")

    # Build message
    if args.type == "countdown":
        subject, html, slack_text = build_countdown_message(
            args.minutes, args.project, args.environment
        )
    elif args.type == "online":
        subject, html, slack_text = build_online_message(
            args.project, args.environment
        )
    else:
        subject, html, slack_text = build_failed_message(
            args.project, args.environment
        )

    recipients = [r.strip() for r in args.recipients.split(",") if r.strip()]

    _log(f"Sending {args.type} notification to {len(recipients)} recipient(s)")

    # Send email via Microsoft Graph API
    if args.tenant_id and args.client_id and args.client_secret:
        try:
            sender = GraphMailSender(
                args.tenant_id, args.client_id, args.client_secret
            )
            sender.send_mail(args.sender, recipients, subject, html)
            _log(f"Email sent: {subject}", style="ok")
        except Exception as exc:
            _log(f"Email failed: {exc}", style="warn")
    else:
        _log("Graph API credentials not configured \u2014 skipping email", style="warn")

    # Send Slack notification
    send_slack(args.slack_webhook, slack_text)
    if args.slack_webhook:
        _log("Slack notification sent", style="ok")

    _log("Notification complete", style="ok")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _log(f"Notification error: {exc}", style="err")
        # Best-effort: never abort the pipeline
        sys.exit(0)
