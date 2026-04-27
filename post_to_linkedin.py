#!/usr/bin/env python3
"""post_to_linkedin.py — Post daily Catalyst Edge scan summary to LinkedIn.

Uses LinkedIn UGC Posts API v2 with a long-lived access token.

Required env vars:
  LINKEDIN_ACCESS_TOKEN   — OAuth 2.0 access token (valid 60 days)
  LINKEDIN_AUTHOR_URN     — e.g. urn:li:person:XXXXXXXX (your profile URN)

Optional (loaded from .sec_email_env as fallback):
  NEWSLETTER_URL
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT           = Path(__file__).parent
SCANNER_URL    = "https://catalystedgescanner.com"
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")
API_URL        = "https://api.linkedin.com/v2/ugcPosts"


# ── Env loader ────────────────────────────────────────────────────────

def _load_env() -> None:
    env_file = ROOT / ".sec_email_env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k not in os.environ:
            os.environ[k] = v.strip()


# ── Flag gating ───────────────────────────────────────────────────────

def already_posted(date_str: str) -> bool:
    return (ROOT / f".linkedin_posted_{date_str}").exists()

def mark_posted(date_str: str) -> None:
    (ROOT / f".linkedin_posted_{date_str}").touch()


# ── Data loaders ──────────────────────────────────────────────────────

def _load_json(name: str) -> dict:
    p = ROOT / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _load_csv(name: str) -> list[dict]:
    p = ROOT / name
    if not p.exists():
        return []
    try:
        with p.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


# ── Post builder ──────────────────────────────────────────────────────

def build_post(picks: dict, squeeze_rows: list[dict], gap_rows: list[dict]) -> str:
    today     = dt.date.today().strftime("%B %-d, %Y")
    top_pick  = picks.get("top_pick", "")
    scanned   = int(picks.get("total_combined", 0) or 300)
    gappers   = int(picks.get("gapper_count", 0) or 0)

    coiled    = [r for r in squeeze_rows if r.get("stage") == "COILED"]
    ignition  = [r for r in squeeze_rows if r.get("stage") == "IGNITION"]
    sq_top    = (ignition + coiled)[:2]

    lines = [
        f"⚡ Pre-Market Catalyst Scan — {today}",
        "",
        f"Scanned {scanned:,} SEC EDGAR filings before 4 AM ET. Here's what moved to the top:",
        "",
    ]

    if top_pick:
        lines.append(f"📌 Top pick: ${top_pick}")

    if gappers:
        lines.append(f"📊 {gappers} gap plays flagged before market open")

    if gap_rows:
        top_gaps = gap_rows[:3]
        for row in top_gaps:
            t = row.get("ticker", "").upper()
            g = row.get("gap_pct", row.get("gap", ""))
            v = row.get("vol_ratio", "")
            try:
                gap_str = f"+{float(g):.1f}%"
            except (ValueError, TypeError):
                gap_str = ""
            try:
                vol_str = f"{float(v):.1f}x vol"
            except (ValueError, TypeError):
                vol_str = ""
            stat = " | ".join(s for s in [gap_str, vol_str] if s)
            lines.append(f"   → ${t}  {stat}" if stat else f"   → ${t}")

    if sq_top:
        tickers = " ".join(f"${r['ticker']}" for r in sq_top)
        lines.append(f"🔥 Squeeze setups: {tickers}")

    lines.extend([
        "",
        "Most traders react after the move already happened.",
        "This scanner flags the setup before pre-market opens.",
        "",
        f"Free, no login, updated daily before 4 AM ET:",
        f"🖥️  {SCANNER_URL}",
        "",
        "#daytrading #stockmarket #SEC #premarket #investing #finance #catalyst",
    ])

    return "\n".join(lines)


# ── LinkedIn API ──────────────────────────────────────────────────────

def post_to_linkedin(token: str, author_urn: str, text: str) -> bool:
    payload = {
        "author":          author_urn,
        "lifecycleState":  "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary":  {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        API_URL, data=body,
        headers={
            "Authorization":  f"Bearer {token}",
            "Content-Type":   "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            post_id = resp.headers.get("x-restli-id", "?")
            print(f"  LinkedIn ✓ post id={post_id}")
            return True
    except urllib.error.HTTPError as e:
        print(f"  LinkedIn ✗ {e.code}: {e.read()[:300]}")
        return False
    except Exception as e:
        print(f"  LinkedIn ✗ {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────

def main() -> int:
    _load_env()

    today_str = dt.date.today().isoformat()

    if already_posted(today_str):
        print(f"post_to_linkedin: already posted today ({today_str}) — skipping")
        return 0

    token      = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    author_urn = os.environ.get("LINKEDIN_AUTHOR_URN", "").strip()

    if not token or not author_urn:
        print("post_to_linkedin: LINKEDIN_ACCESS_TOKEN or LINKEDIN_AUTHOR_URN not set — skipping")
        return 0

    picks       = _load_json("newsletter_picks.json")
    squeeze     = _load_csv("squeeze_candidates.csv")
    gap_rows    = _load_csv("gap_scanner_top.csv")

    text = build_post(picks, squeeze, gap_rows)

    print(f"post_to_linkedin: posting ({len(text)} chars)")
    print(f"\n{text}\n")

    if post_to_linkedin(token, author_urn, text):
        mark_posted(today_str)
        print("post_to_linkedin: done")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
