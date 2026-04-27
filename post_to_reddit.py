#!/usr/bin/env python3
"""Post daily Catalyst Edge DD content to Reddit.

Posts genuine analysis (not link spam) as a self-post with the newsletter
link in the footer.  Rotates subreddits by day-of-week and adjusts tone
accordingly.

Required env vars (set in .sec_email_env):
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USERNAME
    REDDIT_PASSWORD

Daily flag: .reddit_posted_{YYYY-MM-DD} — prevents duplicate posts.

Usage:
    python3 post_to_reddit.py
"""
from __future__ import annotations

import base64
import csv
import datetime
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")

# ── Subreddit strategy ────────────────────────────────────────────────────────
# PRIMARY: always post to our own subreddit (moderator = no spam flags, full control)
# CROSS-POST: share to major subs on specific days — drives traffic back to r/CatalystEdge
# To create r/CatalystEdge: reddit.com/subreddits/create (takes 2 min)
OWN_SUBREDDIT = os.environ.get("REDDIT_OWN_SUB", "CatalystEdgePro")

# Cross-post schedule — targeting traders, not investors
# r/pennystocks (2M) and r/Daytrading (500K) are the best fit for gap scanner content
# Monday=0 … Sunday=6  (None = own sub only that day)
_CROSSPOST_SCHEDULE: dict[int, str | None] = {
    0: "pennystocks",      # Monday   — biggest penny stock community
    1: "Daytrading",       # Tuesday  — active day traders, perfect audience
    2: "pennystocks",      # Wednesday — mid-week scanner results
    3: "RobinhoodPennyStocks",  # Thursday — retail traders
    4: "Daytrading",       # Friday   — week wrap for day traders
    5: None,               # Saturday — own sub only
    6: None,               # Sunday   — own sub only
}

# Tone tags used by _build_post()
_TONE: dict[str, str] = {
    OWN_SUBREDDIT:          "wsb",
    "pennystocks":          "wsb",
    "Daytrading":           "measured",
    "RobinhoodPennyStocks": "wsb",
    "wallstreetbets":       "wsb",
    "stocks":               "measured",
    "investing":            "factual",
}

# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_env_file() -> dict[str, str]:
    result: dict[str, str] = {}
    env_file = ROOT / ".sec_email_env"
    if not env_file.exists():
        return result
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip()
    return result


def _load_picks() -> dict:
    p = ROOT / "newsletter_picks.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
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


def _get_token(client_id: str, client_secret: str,
               username: str, password: str) -> str:
    """Fetch a fresh Reddit OAuth2 password-flow token."""
    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")
    ).decode("utf-8")
    body = urllib.parse.urlencode({
        "grant_type": "password",
        "username":   username,
        "password":   password,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
            "User-Agent":    f"CatalystEdge/1.0 by u/{username}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(f"Reddit token error: {data['error']}")
    token = data.get("access_token", "")
    if not token:
        raise RuntimeError(f"No access_token in response: {data}")
    return token


# ── Post builder ─────────────────────────────────────────────────────────────


def _build_post(
    picks: dict,
    squeeze_rows: list[dict],
    convergence_rows: list[dict],
    merger_rows: list[dict],
    lockup_rows: list[dict],
    tone: str,
    today: datetime.date,
) -> tuple[str, str]:
    """Return (title, body_markdown) for the given tone."""

    date_str   = today.strftime("%B %-d, %Y")
    top_pick   = picks.get("top_pick", "N/A")
    top5       = picks.get("top5_tickers", [])
    gappers    = int(picks.get("gapper_count",  0) or 0)
    value_cnt  = int(picks.get("value_count",   0) or 0)
    moat_cnt   = int(picks.get("moat_count",    0) or 0)
    total_scanned = int(picks.get("total_combined", 0) or 0)

    # Category label per ticker (best-effort from picks json)
    gapper_set = set(picks.get("top_gappers",   []))
    value_set  = set(picks.get("top_value",     []))
    moat_set   = set(picks.get("top_moat_core", []) + picks.get("top_moat_emerging", []))

    def _cat(ticker: str) -> str:
        if ticker in gapper_set:
            return "Gapper"
        if ticker in value_set:
            return "Value"
        if ticker in moat_set:
            return "Moat"
        return "Pick"

    # Squeeze candidates: COILED and IGNITION stages
    coiled_ignition = [
        r for r in squeeze_rows
        if r.get("stage") in ("COILED", "IGNITION")
    ]
    coiled_count = len([r for r in squeeze_rows if r.get("stage") == "COILED"])

    # Convergence alerts: any conviction level
    top_conv = convergence_rows[:5]

    # M&A signals
    ma_signals = [
        r for r in merger_rows
        if r.get("signal_type") in ("TENDER_OFFER", "STRATEGIC_REVIEW", "IN_PLAY")
    ][:5]

    # Lockup expirations this week
    week_end = today + datetime.timedelta(days=7)
    lockups_this_week = []
    for r in lockup_rows:
        try:
            exp = datetime.date.fromisoformat(r.get("lockup_expiry_date", ""))
            if today <= exp <= week_end:
                lockups_this_week.append((exp, r))
        except (ValueError, TypeError):
            pass
    lockups_this_week.sort(key=lambda x: x[0])

    total_picks = gappers + value_cnt + moat_cnt

    # ── Titles by tone ────────────────────────────────────────────────────────
    if tone == "wsb":
        title = (
            f"Daily SEC Catalyst Scan — {date_str} | "
            f"{coiled_count} squeeze setups + M&A signals + {total_picks} picks"
        )
    elif tone == "measured":
        title = (
            f"SEC Catalyst Analysis {date_str} — "
            f"{total_picks} screened picks, {coiled_count} squeeze candidates, M&A activity"
        )
    else:  # factual / investing
        title = (
            f"Daily SEC Filing Analysis {date_str}: "
            f"{total_picks} picks from {total_scanned} tickers screened"
        )

    # ── Body by tone ──────────────────────────────────────────────────────────
    lines: list[str] = []

    # Header paragraph
    if tone == "wsb":
        lines += [
            "I run an automated scanner over 300+ SEC filings every morning before the open. "
            "Here's what stood out today.",
            "",
            f"Screened **{total_scanned}** tickers across 8-K, Form 4, S-3, and other catalyst filings. "
            f"Results: **{gappers}** Gapper setups · **{value_cnt}** Deep Value · **{moat_cnt}** Wide Moat.",
            "",
        ]
    elif tone == "measured":
        lines += [
            "Every morning before market open I run an automated pipeline over 300+ SEC filings "
            "to identify catalysts across gap, value, and moat categories. "
            "Here's today's output.",
            "",
            f"Universe: **{total_scanned}** tickers screened from today's EDGAR filings. "
            f"Breakdown: **{gappers}** Gappers · **{value_cnt}** Value · **{moat_cnt}** Moat.",
            "",
        ]
    else:
        lines += [
            "Automated daily scan of SEC EDGAR filings (8-K, Form 4, S-3, DEF 14A). "
            "The pipeline scores each ticker across momentum, insider activity, short interest, "
            "and filing sentiment to surface actionable setups.",
            "",
            f"Today's universe: **{total_scanned}** tickers. "
            f"Categories: {gappers} Gapper / {value_cnt} Value / {moat_cnt} Moat.",
            "",
        ]

    # ── Section: Top Picks ────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    if tone == "wsb":
        lines.append("## Top Picks Today")
    else:
        lines.append("## Top Picks")
    lines.append("")

    if top5:
        for t in top5[:5]:
            cat = _cat(t)
            if tone == "wsb":
                lines.append(f"- **${t}** — {cat} setup")
            else:
                lines.append(f"- **${t}** ({cat})")
    else:
        lines.append(f"- **${top_pick}** — top-ranked pick today")
    lines.append("")

    # ── Section: Squeeze Radar ────────────────────────────────────────────────
    if coiled_ignition:
        lines.append("---")
        lines.append("")
        if tone == "wsb":
            lines.append("## Squeeze Radar — COILED & IGNITION Setups")
            lines.append("")
            lines.append(
                "These are the setups where short interest is elevated, "
                "a catalyst has appeared in SEC filings, and WSB is not yet piling in. "
                "The window is before the crowd notices."
            )
        elif tone == "measured":
            lines.append("## Squeeze Candidates")
            lines.append("")
            lines.append(
                "Tickers in COILED or IGNITION stage combine high short interest with a "
                "recent SEC-filed catalyst. Squeeze potential exists but carries elevated risk."
            )
        else:
            lines.append("## Short Squeeze Candidates")
            lines.append("")
            lines.append(
                "Tickers flagged for elevated short interest relative to float, "
                "combined with a catalyst event from recent SEC filings."
            )
        lines.append("")

        for r in coiled_ignition[:6]:
            stage  = r.get("stage", "")
            si_pct = _fmt_pct(r.get("short_pct_float"))
            dtc    = _fmt_float(r.get("days_to_cover"))
            score  = r.get("squeeze_score", "—")
            si_trend = _fmt_pct(r.get("si_trend_pct"))
            act    = " | Activist" if r.get("activist_signal") == "YES" else ""
            ins    = " | Insider cluster" if r.get("insider_cluster") == "YES" else ""
            lines.append(
                f"- **${r['ticker']}** `{stage}` — SI {si_pct} · DTC {dtc}d · "
                f"SI trend {si_trend} · score {score}{act}{ins}"
            )
        lines.append("")

    # ── Section: Convergence Alerts ───────────────────────────────────────────
    if top_conv:
        lines.append("---")
        lines.append("")
        if tone == "wsb":
            lines.append("## Convergence Alerts — 3+ Signals Aligning")
            lines.append("")
            lines.append(
                "When insider buying, a catalyst filing, elevated short interest, "
                "and unusual options flow all hit the same ticker at once — that's worth watching."
            )
        else:
            lines.append("## Convergence Alerts")
            lines.append("")
            lines.append("Tickers where three or more independent signals align simultaneously.")
        lines.append("")

        for r in top_conv:
            score   = r.get("convergence_score", "—")
            conv    = r.get("conviction_level",  "—")
            signals = r.get("signals_fired", "").replace(";", " · ")
            lines.append(
                f"- **${r['ticker']}** score {score} `{conv}` — {signals}"
            )
        lines.append("")

    # ── Section: M&A Signals ──────────────────────────────────────────────────
    if ma_signals:
        lines.append("---")
        lines.append("")
        if tone == "wsb":
            lines.append("## M&A Signals — Tender Offers & Strategic Reviews")
        else:
            lines.append("## M&A Activity")
        lines.append("")

        for r in ma_signals:
            sig  = r.get("signal_type", "")
            date = r.get("latest_date", "")
            lines.append(f"- **${r['ticker']}** — {sig} (filed {date})")
        lines.append("")

    # ── Section: Lockup Cliffs ────────────────────────────────────────────────
    if lockups_this_week:
        lines.append("---")
        lines.append("")
        if tone == "wsb":
            lines.append("## Lockup Cliffs This Week")
            lines.append("")
            lines.append(
                "Insider lockup expirations create predictable supply events. "
                "Watch for pressure or, if insiders don't sell, a green flag."
            )
        else:
            lines.append("## Lockup Expirations This Week")
            lines.append("")
            lines.append(
                "Post-IPO and secondary lockup expirations can create short-term supply pressure."
            )
        lines.append("")

        for exp, r in lockups_this_week[:5]:
            ticker = r.get("ticker", "")
            status = r.get("status", "")
            lines.append(f"- **${ticker}** — expires {exp}{f' ({status})' if status else ''}")
        lines.append("")

    # ── Footer ────────────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    if tone == "wsb":
        lines += [
            "Full breakdown with charts and scoring methodology at: "
            f"{NEWSLETTER_URL} — free daily newsletter, no paywall.\n\n🎙️ Talk to Catalyst AI: https://www.catalystedge.agency/",
            "",
            "*This is not financial advice. Do your own DD.*",
        ]
    elif tone == "measured":
        lines += [
            f"Full scoring methodology, charts, and historical picks: {NEWSLETTER_URL}",
            "Free daily newsletter — no paywall.",
            f"🎙️ Talk to Catalyst AI: https://www.catalystedge.agency/",
            "",
            "*Not financial advice. Past picks are for informational purposes only.*",
        ]
    else:
        lines += [
            "The full report including scoring weights, data sources, and historical accuracy "
            f"is published daily at {NEWSLETTER_URL} — free, no paywall.\n\n🎙️ Talk to Catalyst AI: https://www.catalystedge.agency/",
            "",
            "*Informational only. Not investment advice.*",
        ]

    body = "\n".join(lines)
    return title, body


# ── Reddit API call ───────────────────────────────────────────────────────────


def _submit_post(token: str, username: str,
                 subreddit: str, title: str, body: str) -> str:
    """Submit a self-post to Reddit; return the post URL."""
    params = urllib.parse.urlencode({
        "sr":       subreddit,
        "kind":     "self",
        "title":    title,
        "text":     body,
        "nsfw":     "false",
        "resubmit": "true",
        "api_type": "json",
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth.reddit.com/api/submit",
        data=params,
        headers={
            "Authorization": f"bearer {token}",
            "User-Agent":    f"CatalystEdge/1.0 by u/{username}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # Reddit wraps the response: {"json": {"errors": [], "data": {"url": ...}}}
    json_node = data.get("json", {})
    errors    = json_node.get("errors", [])
    if errors:
        raise RuntimeError(f"Reddit submit errors: {errors}")

    url = json_node.get("data", {}).get("url", "")
    if not url:
        raise RuntimeError(f"No URL in Reddit response: {data}")
    return url


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    env = _load_env_file()
    for key in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                "REDDIT_USERNAME", "REDDIT_PASSWORD"):
        if key not in env and os.environ.get(key):
            env[key] = os.environ[key]

    client_id     = env.get("REDDIT_CLIENT_ID",     "").strip()
    client_secret = env.get("REDDIT_CLIENT_SECRET", "").strip()
    username      = env.get("REDDIT_USERNAME",       "").strip()
    password      = env.get("REDDIT_PASSWORD",       "").strip()

    if not all([client_id, client_secret, username, password]):
        print("post_to_reddit: Reddit credentials not set — skipping")
        print("  Run python3 setup_reddit_auth.py for setup instructions.")
        return 0

    today = datetime.date.today()
    stamp = today.isoformat()
    flag  = ROOT / f".reddit_posted_{stamp}"
    if flag.exists():
        print(f"post_to_reddit: already posted today ({stamp}) — skipping")
        return 0

    weekday = today.weekday()

    # Load data once
    picks            = _load_picks()
    squeeze_rows     = _load_csv("squeeze_candidates.csv")
    convergence_rows = _load_csv("convergence_alerts.csv")
    merger_rows      = _load_csv("merger_signals.csv")
    lockup_rows      = _load_csv("lockup_calendar.csv")

    # Get fresh token
    try:
        token = _get_token(client_id, client_secret, username, password)
    except Exception as exc:
        print(f"post_to_reddit: ERROR getting token — {exc}")
        return 1

    success = False

    # ── Step 1: Always post to our own subreddit first ────────────────────────
    own_title, own_body = _build_post(
        picks, squeeze_rows, convergence_rows, merger_rows, lockup_rows,
        _TONE.get(OWN_SUBREDDIT, "wsb"), today,
    )
    print(f"post_to_reddit: posting to r/{OWN_SUBREDDIT} (home base)")
    print(f"  Title: {own_title[:80]}{'...' if len(own_title) > 80 else ''}")
    try:
        url = _submit_post(token, username, OWN_SUBREDDIT, own_title, own_body)
        print(f"post_to_reddit: r/{OWN_SUBREDDIT} OK — {url}")
        success = True
    except Exception as exc:
        print(f"post_to_reddit: r/{OWN_SUBREDDIT} ERROR — {exc}")
        print(f"  (Create it at reddit.com/subreddits/create → name: {OWN_SUBREDDIT})")

    # ── Step 2: Cross-post to major sub 3x/week ───────────────────────────────
    cross_sub = _CROSSPOST_SCHEDULE.get(weekday)
    if cross_sub:
        cross_tone  = _TONE.get(cross_sub, "measured")
        cross_title, cross_body = _build_post(
            picks, squeeze_rows, convergence_rows, merger_rows, lockup_rows,
            cross_tone, today,
        )
        print(f"post_to_reddit: cross-posting to r/{cross_sub} (tone={cross_tone})")
        try:
            url = _submit_post(token, username, cross_sub, cross_title, cross_body)
            print(f"post_to_reddit: r/{cross_sub} OK — {url}")
            success = True
        except Exception as exc:
            print(f"post_to_reddit: r/{cross_sub} failed (expected if account young) — {exc}")

    if success:
        flag.touch()
        return 0

    print("post_to_reddit: all attempts failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
