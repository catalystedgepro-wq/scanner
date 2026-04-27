#!/usr/bin/env python3
"""Post the Catalyst Edge origin story to high-traffic subreddits.

This is a ONE-TIME post (not daily) designed to introduce the pipeline
to developer/trader communities and drive initial subscriber growth.

Target subreddits (post manually or run once per sub with --sub flag):
  r/algotrading      — builders audience, loves technical detail
  r/stocks           — general traders, respond to free tools
  r/SecurityAnalysis — serious investors, respond to methodology
  r/investing        — broad audience, keep tone measured

Usage:
    python3 post_origin_story.py --sub algotrading
    python3 post_origin_story.py --sub stocks
    python3 post_origin_story.py --sub SecurityAnalysis
    python3 post_origin_story.py --dry-run   # print without posting
"""
from __future__ import annotations

import argparse
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
NEWSLETTER_URL = "https://catalystedge.agency"
AGENCY_URL     = "https://www.catalystedge.agency/"
FLAG_DIR       = ROOT

# ── Content ──────────────────────────────────────────────────────────────────

POSTS: dict[str, dict[str, str]] = {

    "algotrading": {
        "title": "I built a fully automated SEC filing scanner that runs at 4 AM every day — here's the architecture",
        "body": """
Every morning before 4 AM ET my pipeline does this automatically:

1. Fetches 300+ fresh SEC filings from EDGAR (8-K, Form 4, S-3, 13-D/G)
2. Maps CIKs to tickers using the SEC company_tickers.json endpoint
3. Scores each ticker across three dimensions: Gapper potential, Value signals, Institutional moat
4. Fetches price + volume data via Stooq (no paid API needed)
5. Pulls filing full-text and runs keyword sentiment scoring
6. Runs a squeeze hunter (short interest + options gamma + insider cluster detection)
7. Adds news momentum from public RSS feeds (MarketWatch, Yahoo Finance, EIA, NOAA)
8. Runs 8 intelligence layers: dark pool proxies, smart money signals, merger radar, lockup calendar, revenue inflection, convergence scoring
9. Auto-tunes scoring weights daily based on backtested next-day outcomes
10. Builds an HTML newsletter and posts it to Beehiiv, Twitter, Instagram, LinkedIn, TikTok, Reddit, Discord, StockTwits, Blogger, Medium, YouTube
11. Updates an ElevenLabs voice AI agent with today's picks so visitors can ask questions by voice

**The entire stack is Python + Node.js, stdlib only — no paid data providers.**

---

**Tech stack:**
- Python (stdlib only — no pandas, no numpy, no pip dependencies for the pipeline)
- Node.js + Playwright for browser-based posting
- Stooq for price data (free, no API key)
- SEC EDGAR RSS + EDGAR full-text search
- ElevenLabs ConvAI for the voice agent
- Vercel for the landing page
- Beehiiv for newsletter distribution
- Cron on WSL2 for scheduling

**Scoring model:**
Each ticker gets a gapper_score, value_score, and moat_score based on keyword hits in the filing text, weighted by recency (filing age in minutes), price, volume, and market cap filters. Weights are auto-tuned daily by comparing yesterday's picks against actual next-day open/close outcomes.

**What I track for squeeze setups:**
Short interest %, float size, options gamma exposure, insider cluster buys (2+ Form 4s at same company), and convergence (ticker appearing in 3+ signal layers simultaneously).

---

**The output:**
A free daily newsletter with the top picks, full scoring breakdown, squeeze radar, insider alerts, and sector momentum. Runs completely unattended.

I built this because I was tired of paying $200/month for stock screeners that didn't show me the underlying SEC data. Everything here is from public sources.

Newsletter (free): """ + NEWSLETTER_URL + """
Voice AI (ask about today's picks): """ + AGENCY_URL + """

Happy to answer questions about any part of the architecture.

*Not financial advice.*
""",
    },

    "stocks": {
        "title": "I built a free tool that scans 300+ SEC filings every morning and surfaces the highest-conviction setups — here's what it found today",
        "body": """
Every morning my automated pipeline scans hundreds of fresh SEC filings before 4 AM ET — 8-Ks, Form 4 insider trades, Schedule 13D activist positions — and scores each ticker across three categories:

**⚡ Gapper plays** — material events likely to cause a gap at open (FDA approvals, merger agreements, guidance raises, contract awards)

**💎 Value plays** — buybacks, dividend increases, debt reduction, activist positions building

**🏰 Moat plays** — recurring revenue signals, patent filings, exclusive agreements, institutional accumulation

It also runs a squeeze scanner (short interest + options gamma + insider clusters) and adds news momentum scoring.

**Everything is sourced directly from public SEC EDGAR data. Free. No paywall.**

I also built a voice AI you can literally talk to and ask "what's the top pick today and why?" — it knows this morning's full briefing.

Newsletter (free daily): """ + NEWSLETTER_URL + """
Talk to Catalyst AI: """ + AGENCY_URL + """

*Not financial advice. Always do your own research.*
""",
    },

    "SecurityAnalysis": {
        "title": "Built an automated SEC catalyst scanner — scoring methodology and architecture overview",
        "body": """
I've been running an automated SEC filing analysis pipeline for several months and wanted to share the methodology with this community.

**Data sources:**
- SEC EDGAR RSS feeds (8-K, Form 4, S-3, 13-D/G, 6-K) — fetched every morning via the EDGAR browsing API
- Full filing text fetched from SEC EDGAR for keyword sentiment scoring
- Price and volume from Stooq (60-day daily bars for avg volume calculation)
- Public news RSS feeds for sector momentum overlay

**Scoring dimensions:**

*Gapper score* — weighted sum of positive catalyst keywords (FDA approval, definitive agreement, contract award, earnings beat, guidance raise) minus dilution/offering penalties. Adjusted for filing recency (minutes since filing).

*Value score* — shareholder return signals (buyback authorization, dividend increase, special dividend, debt reduction) plus activist filings (13-D). Penalized for dilutive events.

*Moat score* — competitive advantage signals (patent filing, exclusive agreement, recurring revenue language, multi-year contract, backlog growth). Penalized for customer concentration and contract terminations.

**Quality filters:**
- Minimum price: $3 (gappers), $5 (value/moat)
- Minimum 3-month avg volume: 250K (gappers), 500K (value/moat)
- Minimum market cap: $300M (general), $2B (moat core)
- Automatic exclusion of warrants, preferred shares, unit tickers

**Auto-tuning:**
Scoring weights are adjusted daily by comparing yesterday's picks against actual next-day open → intraday high outcomes. Hit rate (≥3% move) and avg max run are tracked per list.

**Output:**
Free daily newsletter with full scoring breakdown.

Newsletter: """ + NEWSLETTER_URL + """
Voice AI assistant (talks through today's picks): """ + AGENCY_URL + """

I'm interested in feedback on the scoring methodology — particularly whether anyone has found better proxies for squeeze potential than the short interest % + float size combination I'm currently using.

*Informational only. Not investment advice.*
""",
    },

    "investing": {
        "title": "I built a free daily SEC filing intelligence newsletter — fully automated, no paywall",
        "body": """
For the past several months I've been running an automated pipeline that scans SEC EDGAR filings every morning before 4 AM ET and identifies the highest-conviction setups across three categories:

- **Event-driven plays** — 8-K material events: FDA approvals, merger agreements, major contract awards
- **Value plays** — buyback authorizations, dividend increases, activist 13-D positions
- **Quality/moat plays** — patent filings, recurring revenue signals, institutional accumulation via Form 4

The pipeline also tracks squeeze setups (short interest, options flow, insider cluster buying) and adds sector momentum signals from public news feeds.

**It's completely free.** I built it because good SEC-based research tools are expensive and most retail investors don't have access to real-time filing data.

I also built a voice AI you can ask questions to — "what triggered today's top pick?" or "which sectors are moving?" — and it gives you a real answer based on this morning's actual data.

Free newsletter: """ + NEWSLETTER_URL + """
Voice AI: """ + AGENCY_URL + """

*Not financial advice. Data sourced from public SEC EDGAR filings.*
""",
    },
}

# ── Reddit API helpers ────────────────────────────────────────────────────────

def _load_env() -> dict[str, str]:
    result: dict[str, str] = {}
    env_file = ROOT / ".sec_email_env"
    if not env_file.exists():
        return result
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v.strip()
    return result


def _get_token(client_id: str, client_secret: str, username: str, password: str) -> str:
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "password",
        "username": username,
        "password": password,
    }).encode()
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=body,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": f"CatalystEdge/1.0 by u/{username}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    token = data.get("access_token", "")
    if not token:
        raise RuntimeError(f"Reddit token error: {data}")
    return token


def _submit_post(token: str, username: str, subreddit: str, title: str, body: str) -> str:
    payload = urllib.parse.urlencode({
        "api_type": "json",
        "kind": "self",
        "sr": subreddit,
        "title": title,
        "text": body,
        "nsfw": "false",
        "spoiler": "false",
    }).encode()
    req = urllib.request.Request(
        "https://oauth.reddit.com/api/submit",
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "User-Agent": f"CatalystEdge/1.0 by u/{username}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    errors = data.get("json", {}).get("errors", [])
    if errors:
        raise RuntimeError(f"Reddit submit errors: {errors}")
    url = data.get("json", {}).get("data", {}).get("url", "")
    return url


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Post Catalyst Edge origin story to Reddit.")
    parser.add_argument("--sub", default="algotrading",
                        choices=list(POSTS.keys()),
                        help="Target subreddit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print post content without submitting")
    args = parser.parse_args()

    post = POSTS[args.sub]
    title = post["title"]
    body = post["body"].strip()

    print(f"Subreddit: r/{args.sub}")
    print(f"Title: {title}")
    print(f"Body ({len(body)} chars):")
    print("─" * 60)
    print(body)
    print("─" * 60)

    if args.dry_run:
        print("\n[DRY RUN] Not submitting.")
        return 0

    # Check if already posted to this sub
    flag = FLAG_DIR / f".origin_story_posted_{args.sub}"
    if flag.exists():
        print(f"Already posted to r/{args.sub} (flag: {flag}). Delete flag to repost.")
        return 0

    env = _load_env()
    for key in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"):
        if not env.get(key):
            print(f"Missing env var: {key} — add to .sec_email_env")
            return 1

    try:
        token = _get_token(
            env["REDDIT_CLIENT_ID"], env["REDDIT_CLIENT_SECRET"],
            env["REDDIT_USERNAME"], env["REDDIT_PASSWORD"],
        )
        url = _submit_post(token, env["REDDIT_USERNAME"], args.sub, title, body)
        flag.touch()
        print(f"\nPosted successfully: {url}")
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
