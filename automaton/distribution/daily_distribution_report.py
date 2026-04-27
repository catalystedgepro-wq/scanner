#!/usr/bin/env python3
"""daily_distribution_report.py — Daily marketing summary email.

Sent to opensource@example.com once a day. Reads:
  - distribution_loop.log: posts drafted/published/rotated last 24h
  - dispatch_inbox.log: webhook + Playwright dispatch outcomes
  - pending_content.yaml: queue depth + next 5 posts up
  - conversion_tracker output (if Monday): weekly leaderboard

Goal: operator sees what shipped, what failed, and what's coming — without
having to grep logs.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
LOG_DIR = WORKSPACE / "logs"
DIST_LOG = LOG_DIR / "distribution_loop.log"
DISPATCH_LOG = LOG_DIR / "dispatch_inbox.log"

sys.path.insert(0, str(ROOT))
from content_smith import _read_queue, _now_iso  # type: ignore


def _read_recent(path: Path, hours: int = 24) -> list[str]:
    if not path.exists():
        return []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    keep: list[str] = []
    pat = re.compile(r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\]")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line)
        if not m:
            continue
        try:
            t = dt.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
        except Exception:
            continue
        if t >= cutoff:
            keep.append(line)
    return keep


def _summarize_loop(lines: list[str]) -> dict:
    fires = []
    for line in lines:
        if "distribution_loop fired" in line:
            fires.append(line.split("distribution_loop:")[-1].strip())
    smith_ok = sum(1 for l in lines if "smith: drafted a post" in l)
    publisher_ok = sum(1 for l in lines if "publisher: published" in l)
    rotator_ok = sum(1 for l in lines if "rotator: social_inbox updated" in l)
    return {
        "fires": fires,
        "drafted": smith_ok,
        "published": publisher_ok,
        "rotated": rotator_ok,
    }


def _summarize_dispatch(lines: list[str]) -> dict:
    tg = sum(1 for l in lines if "telegram: posted" in l)
    dc = sum(1 for l in lines if "discord: posted" in l)
    pw_ok = sum(1 for l in lines if re.search(r"playwright: \w+ OK", l))
    pw_fail = sum(1 for l in lines if re.search(r"playwright: \w+ FAILED", l))
    end_lines = [l for l in lines if "dispatch_inbox END" in l]
    return {
        "telegram_posts": tg,
        "discord_posts": dc,
        "playwright_ok": pw_ok,
        "playwright_failed": pw_fail,
        "drains": len(end_lines),
    }


def _queue_status() -> dict:
    queue = _read_queue()
    posts = queue.get("posts", [])
    by_state: dict[str, int] = {}
    for p in posts:
        s = p.get("state", "unknown")
        by_state[s] = by_state.get(s, 0) + 1
    queued = sorted(
        (p for p in posts if p.get("state") == "queued"),
        key=lambda p: p.get("priority", 999),
    )
    next_up = [(p["priority"], p["slug"], p.get("target_keyword", "")) for p in queued[:5]]
    return {"by_state": by_state, "next_up": next_up, "total": len(posts)}


def _build_html(loop: dict, disp: dict, queue: dict) -> str:
    next_up_rows = "".join(
        f"<tr><td style='padding:6px 12px'>{pri}</td>"
        f"<td style='padding:6px 12px'><code>{slug}</code></td>"
        f"<td style='padding:6px 12px'>{kw}</td></tr>"
        for pri, slug, kw in queue["next_up"]
    ) or "<tr><td colspan=3 style='padding:6px 12px'>queue empty — content_scout will top up</td></tr>"

    by_state_rows = "".join(
        f"<tr><td style='padding:6px 12px'>{s}</td><td style='padding:6px 12px'>{n}</td></tr>"
        for s, n in sorted(queue["by_state"].items())
    )

    today = dt.date.today().isoformat()
    return f"""<html><body style="font-family:system-ui,-apple-system,sans-serif;color:#0f172a">
<h2 style="color:#0c4a6e">📊 Catalyst Edge — Daily Distribution Report ({today})</h2>

<h3>Last 24 hours</h3>
<table style="border-collapse:collapse;border:1px solid #e2e8f0">
<tr><td style="padding:6px 12px;background:#f0f9ff">Loop fires</td>
    <td style="padding:6px 12px"><strong>{len(loop['fires'])}</strong></td></tr>
<tr><td style="padding:6px 12px">Posts drafted</td>
    <td style="padding:6px 12px"><strong>{loop['drafted']}</strong></td></tr>
<tr><td style="padding:6px 12px;background:#f0f9ff">Posts published</td>
    <td style="padding:6px 12px"><strong>{loop['published']}</strong></td></tr>
<tr><td style="padding:6px 12px">Posts rotated to inbox</td>
    <td style="padding:6px 12px"><strong>{loop['rotated']}</strong></td></tr>
<tr><td style="padding:6px 12px;background:#f0f9ff">Inbox drains</td>
    <td style="padding:6px 12px"><strong>{disp['drains']}</strong></td></tr>
<tr><td style="padding:6px 12px">Telegram posts (HTTP 200)</td>
    <td style="padding:6px 12px"><strong>{disp['telegram_posts']}</strong></td></tr>
<tr><td style="padding:6px 12px;background:#f0f9ff">Discord posts (HTTP 204)</td>
    <td style="padding:6px 12px"><strong>{disp['discord_posts']}</strong></td></tr>
<tr><td style="padding:6px 12px">Playwright OK</td>
    <td style="padding:6px 12px"><strong>{disp['playwright_ok']}</strong></td></tr>
<tr><td style="padding:6px 12px;background:#fef2f2">Playwright FAILED</td>
    <td style="padding:6px 12px"><strong style="color:#b91c1c">{disp['playwright_failed']}</strong></td></tr>
</table>

<h3>Queue health (total {queue['total']})</h3>
<table style="border-collapse:collapse;border:1px solid #e2e8f0">
<tr><th style="padding:6px 12px;background:#f1f5f9;text-align:left">State</th>
    <th style="padding:6px 12px;background:#f1f5f9;text-align:left">Count</th></tr>
{by_state_rows}
</table>

<h3>Next 5 posts up</h3>
<table style="border-collapse:collapse;border:1px solid #e2e8f0">
<tr><th style="padding:6px 12px;background:#f1f5f9;text-align:left">Priority</th>
    <th style="padding:6px 12px;background:#f1f5f9;text-align:left">Slug</th>
    <th style="padding:6px 12px;background:#f1f5f9;text-align:left">Target keyword</th></tr>
{next_up_rows}
</table>

<p style="color:#64748b;font-size:13px;margin-top:24px">
If Playwright FAILED &gt; 0, refresh sessions: <code>bash setup_social_profiles.sh --only &lt;platform&gt;</code>.
Telegram + Discord webhooks always work — those numbers should grow daily.
</p>
</body></html>"""


def _send_email(subject: str, html: str) -> bool:
    env_path = WORKSPACE / ".sec_email_env"
    env: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

    smtp_host = env.get("SMTP_HOST") or os.environ.get("SMTP_HOST")
    smtp_port = int(env.get("SMTP_PORT") or os.environ.get("SMTP_PORT") or "587")
    smtp_user = env.get("SMTP_USER") or os.environ.get("SMTP_USER")
    smtp_pass = env.get("SMTP_PASS") or os.environ.get("SMTP_PASS")
    if not (smtp_host and smtp_user and smtp_pass):
        print("[daily_distribution_report] ERROR: SMTP env not configured")
        return False

    to_addr = "opensource@example.com"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, [to_addr], msg.as_string())
        print(f"[daily_distribution_report] sent to {to_addr}")
        return True
    except Exception as e:
        print(f"[daily_distribution_report] ERROR sending: {e}")
        return False


def main() -> int:
    loop = _summarize_loop(_read_recent(DIST_LOG, hours=24))
    disp = _summarize_dispatch(_read_recent(DISPATCH_LOG, hours=24))
    queue = _queue_status()
    html = _build_html(loop, disp, queue)
    today = dt.date.today().isoformat()
    subject = (
        f"Catalyst Edge dist report {today} — "
        f"{loop['published']} pub · "
        f"{disp['telegram_posts'] + disp['discord_posts']} webhook posts · "
        f"{queue['by_state'].get('queued', 0)} queued"
    )
    return 0 if _send_email(subject, html) else 2


if __name__ == "__main__":
    sys.exit(main())
