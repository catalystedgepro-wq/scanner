#!/usr/bin/env python3
"""Post daily Catalyst Edge watchlist to a Discord server via Incoming Webhook.

No bot token or library required — just a webhook URL.
Creates 3 rich embeds: daily picks, squeeze radar, event radar (M&A + lockups).

Required env var (set in .sec_email_env):
  DISCORD_WEBHOOK_URL

Optional:
  NEWSLETTER_URL  (defaults to https://catalystedge.agency)
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")

# Brand colors (decimal, as Discord expects)
BLUE   = 0x3B82F6
ORANGE = 0xF59E0B
GREEN  = 0x10B981
RED    = 0xEF4444


# ── Data helpers ────────────────────────────────────────────────────────────

def _load_picks() -> dict:
    p = ROOT / "newsletter_picks.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


def _load_csv(name: str) -> list[dict]:
    p = ROOT / name
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _fmt_pct(v) -> str:
    try:
        return f"{float(v):.1f}%"
    except (ValueError, TypeError):
        return "—"


def _fmt_float(v, decimals: int = 1) -> str:
    try:
        return f"{float(v):.{decimals}f}"
    except (ValueError, TypeError):
        return "—"


# ── Embed builders ──────────────────────────────────────────────────────────

def _embed_picks(picks: dict, convergence_rows: list[dict]) -> dict:
    today     = datetime.date.today().strftime("%A, %B %-d, %Y")
    top_pick  = picks.get("top_pick", "—")
    top5      = picks.get("top5_tickers", [])
    gappers   = int(picks.get("gapper_count",  0) or 0)
    value_cnt = int(picks.get("value_count",   0) or 0)
    moat      = int(picks.get("moat_count",    0) or 0)
    total_scanned = picks.get("total_combined", 0)

    desc = (
        f"**Today's #1 Pick: ${top_pick}**\n"
        f"Scanned **{total_scanned}** tickers from 300+ SEC filings\n"
        f"Results: **{gappers}** Gappers · **{value_cnt}** Value · **{moat}** Moat\n\n"
        f"[📰 Read the full newsletter]({NEWSLETTER_URL})"
    )

    fields = []

    # Top 5 tickers
    if top5:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        picks_str = "\n".join(
            f"{medals[i]} **${t}**" for i, t in enumerate(top5[:5])
        )
        fields.append({"name": "Today's Top Picks", "value": picks_str, "inline": True})

    # Top convergence alerts
    top_conv = [r for r in convergence_rows
                if r.get("conviction_level") in ("HIGH", "ELEVATED")][:5]
    if top_conv:
        lines = []
        for r in top_conv:
            icon    = "🔴" if r.get("conviction_level") == "HIGH" else "🟡"
            signals = r.get("signals_fired", "").replace(";", " · ")
            score   = r.get("convergence_score", "")
            lines.append(f"{icon} **${r['ticker']}** score {score}\n↳ {signals}")
        fields.append({"name": "⚡ Convergence Alerts", "value": "\n".join(lines), "inline": False})

    return {
        "title":       f"⚡ Catalyst Edge — {today}",
        "description": desc,
        "color":       BLUE,
        "fields":      fields,
        "footer":      {"text": "Free daily SEC catalyst intelligence · catalystedge.agency · 🎙️ Talk to Catalyst AI: catalystedge.agency"},
        "timestamp":   datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _embed_squeeze(squeeze_rows: list[dict]) -> dict | None:
    coiled   = [r for r in squeeze_rows if r.get("stage") == "COILED"]
    ignition = [r for r in squeeze_rows if r.get("stage") == "IGNITION"]
    active   = [r for r in squeeze_rows if r.get("stage") == "ACTIVE"]
    watch    = [r for r in squeeze_rows if r.get("stage") == "WATCH"]

    highlighted = (coiled + ignition + active)[:6]
    if not highlighted and not watch:
        return None

    # If nothing in prime stages, show top WATCH by score
    if not highlighted:
        highlighted = sorted(watch, key=lambda r: -int(r.get("squeeze_score", 0) or 0))[:5]

    lines = []
    for r in highlighted:
        emoji = r.get("stage_emoji", "")
        stage = r.get("stage", "")
        si    = _fmt_pct(r.get("short_pct_float"))
        dtc   = f"{_fmt_float(r.get('days_to_cover'))}d"
        score = r.get("squeeze_score", "")
        act   = " 🎯ACT" if r.get("activist_signal") == "YES" else ""
        ins   = " 👥INS" if r.get("insider_cluster") == "YES" else ""
        lines.append(
            f"{emoji} **${r['ticker']}** `{stage}` — SI {si} · DTC {dtc} · score **{score}**{act}{ins}"
        )

    stage_counts = []
    if coiled:   stage_counts.append(f"🔒 {len(coiled)} COILED")
    if ignition: stage_counts.append(f"🔥 {len(ignition)} IGNITION")
    if active:   stage_counts.append(f"⚡ {len(active)} ACTIVE")
    summary = " · ".join(stage_counts) if stage_counts else f"{len(watch)} WATCH"

    return {
        "title":       f"🔒 Squeeze Radar — {summary}",
        "description": "\n".join(lines),
        "color":       ORANGE,
        "footer":      {
            "text": (
                "COILED = undiscovered + high SI + catalyst · "
                "IGNITION = WSB discovering · "
                "ACTIVE = squeeze in progress"
            )
        },
    }


def _embed_events(lockup_rows: list[dict], merger_rows: list[dict],
                  deepvalue_rows: list[dict]) -> dict | None:
    fields = []

    # M&A signals
    if merger_rows:
        lines = []
        for r in merger_rows[:5]:
            signal = r.get("signal_type", "")
            date   = r.get("latest_date", "")
            icon   = "🎯" if "TENDER" in signal else "🔍" if "STRATEGIC" in signal else "📡"
            lines.append(f"{icon} **${r['ticker']}** — {signal} ({date})")
        fields.append({"name": "🏦 M&A Signals", "value": "\n".join(lines), "inline": True})

    # Lockup expirations in next 7 days
    today_dt = datetime.date.today()
    week_end = today_dt + datetime.timedelta(days=7)
    imminent = []
    for r in lockup_rows:
        try:
            exp = datetime.date.fromisoformat(r.get("lockup_expiry_date", ""))
            if today_dt <= exp <= week_end:
                imminent.append((exp, r))
        except (ValueError, TypeError):
            pass
    if imminent:
        imminent.sort(key=lambda x: x[0])
        lines = []
        for exp, r in imminent[:5]:
            ticker  = r.get("ticker", "")
            insider = " 👥" if r.get("insider_bought_after") == "True" else ""
            lines.append(f"📅 **${ticker}** — {exp}{insider}")
        fields.append({"name": "📅 Lockup Expirations (7 days)", "value": "\n".join(lines), "inline": True})

    # DeepValue top picks
    top_dv = [r for r in deepvalue_rows if int(r.get("grade_score", 0) or 0) >= 55][:4]
    if top_dv:
        lines = []
        for r in top_dv:
            grade = r.get("grade", "")
            score = r.get("grade_score", "")
            pb    = _fmt_float(r.get("pb_ratio"), 1)
            lines.append(f"💎 **${r['ticker']}** Grade **{grade}** (score {score}) P/B {pb}x")
        fields.append({"name": "💎 DeepValue Screen", "value": "\n".join(lines), "inline": False})

    if not fields:
        return None

    return {
        "title":  "📡 Event & Value Radar",
        "color":  GREEN,
        "fields": fields,
        "footer": {"text": "M&A from EDGAR · Lockups from S-1 filings · DeepValue = Keith Gill framework"},
    }


# ── Post ────────────────────────────────────────────────────────────────────

def post_webhook(webhook_url: str, embeds: list[dict]) -> None:
    payload = json.dumps({"embeds": embeds}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://catalystedge.agency, 1.0)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        status = resp.status
    # Discord returns 204 No Content on success
    if status not in (200, 204):
        raise RuntimeError(f"Discord webhook HTTP {status}")


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        print("post_to_discord: DISCORD_WEBHOOK_URL not set — skipping")
        return 0

    stamp = datetime.date.today().isoformat()
    flag  = ROOT / f".discord_posted_{stamp}"
    if flag.exists():
        print(f"post_to_discord: already posted today ({stamp}) — skipping")
        return 0

    picks            = _load_picks()
    squeeze_rows     = _load_csv("squeeze_candidates.csv")
    convergence_rows = _load_csv("convergence_alerts.csv")
    lockup_rows      = _load_csv("lockup_calendar.csv")
    merger_rows      = _load_csv("merger_signals.csv")
    deepvalue_rows   = _load_csv("deepvalue_screen.csv")

    embeds: list[dict] = []

    embeds.append(_embed_picks(picks, convergence_rows))

    sq_embed = _embed_squeeze(squeeze_rows)
    if sq_embed:
        embeds.append(sq_embed)

    ev_embed = _embed_events(lockup_rows, merger_rows, deepvalue_rows)
    if ev_embed:
        embeds.append(ev_embed)

    print(f"post_to_discord: posting {len(embeds)} embeds")
    try:
        post_webhook(webhook_url, embeds)
        print("post_to_discord: OK")
        flag.touch()
    except Exception as e:
        print(f"post_to_discord: ERROR — {e}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
