#!/usr/bin/env python3
"""alert_pipeline_failure.py — Send a Telegram alert when the pipeline fails.

Usage:
    python3 alert_pipeline_failure.py "reason text"

Called from run_daily_sec_catalyst.sh on failure.
Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL env vars.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent


def send_telegram(token: str, channel: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": channel, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"alert_pipeline_failure: Telegram send failed: {e}")
        return False


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    channel = os.environ.get("TELEGRAM_CHANNEL", "").strip()

    if not token or not channel:
        # Try loading from .sec_email_env as fallback
        env_file = ROOT / ".sec_email_env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN=") and not token:
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("TELEGRAM_CHANNEL=") and not channel:
                    channel = line.split("=", 1)[1].strip().strip('"').strip("'")

    if not token or not channel:
        print("alert_pipeline_failure: TELEGRAM_BOT_TOKEN/CHANNEL not set — no alert sent")
        return

    reason = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "unknown error"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M %Z")

    message = (
        f"⚠️ <b>Catalyst Edge Pipeline Alert</b>\n\n"
        f"🕐 {now}\n"
        f"❌ <b>Failure:</b> {reason}\n\n"
        f"Newsletter and scanner may not have updated.\n"
        f"Check: <code>tail -50 sec_catalyst_cron.log</code>"
    )

    ok = send_telegram(token, channel, message)
    if ok:
        print(f"alert_pipeline_failure: alert sent to {channel}")
    else:
        print(f"alert_pipeline_failure: failed to send alert")


if __name__ == "__main__":
    main()
