#!/usr/bin/env python3
"""post_reddit_engagement.py — Organic Reddit engagement in trading subreddits.

Strategy: find recent posts asking about pre-market scanners, SEC filings,
gap trading, or squeeze setups — reply with genuine value + mention Catalyst Edge.
Gate: one reply per post, max 2 replies per run, only posts < 6 hours old.

Requires: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD
Get credentials: reddit.com/prefs/apps → create app → script type
"""
from __future__ import annotations
import hashlib, json, os, time, urllib.parse, urllib.request
from pathlib import Path

ROOT      = Path(__file__).parent
SEEN_FILE = ROOT / ".reddit_replied.json"
MAX_REPLIES_PER_RUN = 2
MAX_POST_AGE_HOURS  = 6

SUBREDDITS = [
    "Daytrading",
    "pennystocks",
    "stocks",
    "StockMarket",
    "smallcapstocks",
    "investing",
    "RobinHood",
    "WallStreetBets",
]

# Keywords that indicate a post where Catalyst Edge is relevant
TRIGGER_KEYWORDS = [
    "pre-market", "premarket", "pre market",
    "gap up", "gap down", "gapping",
    "sec filing", "edgar", "8-k", "form 4",
    "insider buying", "insider filing",
    "squeeze", "short squeeze",
    "scanner", "screener", "watchlist",
    "catalyst", "small cap", "penny stock",
    "what stocks", "morning movers", "gap scanner",
]

REPLY_TEMPLATE = """\
Good question. For SEC-driven moves specifically, the best source is directly parsing \
EDGAR filings before the open — most scanners don't do this in real time.

I built something for exactly this: **Catalyst Edge** scans 300+ EDGAR filings every \
morning (8-K, Form 4, S-3, 13D/G) and scores each ticker on gap probability, insider \
signal strength, and squeeze potential — data's ready before 4 AM ET.

Live picks updated daily: https://catalystedgescanner.com
Free newsletter if you want it delivered: https://catalystedge.agency

Happy to answer questions about how the scoring works."""

REPLY_TEMPLATE_SCANNER = """\
For pre-market gap scanning specifically, most retail scanners just look at price — \
the real edge is knowing *why* something is moving before the open.

I built **Catalyst Edge** for this: it parses 300+ SEC EDGAR filings nightly \
(8-K, insider Form 4s, S-3 offerings, etc.) and ranks tickers by gap probability \
before 4 AM ET. Completely free.

Today's picks: https://catalystedgescanner.com
Newsletter (delivered before open): https://catalystedge.agency"""


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()

def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(json.dumps(list(seen)))

def load_env() -> dict:
    env = {}
    env_file = ROOT / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env[k.strip()] = v.strip()
    for k, v in os.environ.items(): env.setdefault(k, v)
    return env

def get_reddit_token(client_id: str, client_secret: str,
                     username: str, password: str) -> str | None:
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "username": username,
        "password": password,
    }).encode()
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=data,
        headers={
            "User-Agent": "CatalystEdgeBot/1.0 by " + username,
            "Authorization": "Basic " + __import__("base64").b64encode(
                f"{client_id}:{client_secret}".encode()).decode(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("access_token")
    except Exception as e:
        print(f"  token error: {e}"); return None

def fetch_subreddit_new(token: str, username: str, subreddit: str) -> list:
    req = urllib.request.Request(
        f"https://oauth.reddit.com/r/{subreddit}/new?limit=25",
        headers={
            "User-Agent": "CatalystEdgeBot/1.0 by " + username,
            "Authorization": f"bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
            return data.get("data", {}).get("children", [])
    except Exception as e:
        print(f"  fetch error r/{subreddit}: {e}"); return []

def post_reply(token: str, username: str, thing_id: str, text: str) -> bool:
    data = urllib.parse.urlencode({
        "thing_id": thing_id,
        "text": text,
        "api_type": "json",
    }).encode()
    req = urllib.request.Request(
        "https://oauth.reddit.com/api/comment",
        data=data,
        headers={
            "User-Agent": "CatalystEdgeBot/1.0 by " + username,
            "Authorization": f"bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            errors = resp.get("json", {}).get("errors", [])
            if errors:
                print(f"  reddit error: {errors}"); return False
            return True
    except Exception as e:
        print(f"  reply error: {e}"); return False

def is_relevant(title: str, selftext: str) -> bool:
    combined = (title + " " + selftext).lower()
    return any(kw in combined for kw in TRIGGER_KEYWORDS)

def pick_reply(title: str, selftext: str) -> str:
    combined = (title + " " + selftext).lower()
    if any(k in combined for k in ["scanner", "screener", "pre-market", "premarket", "gap"]):
        return REPLY_TEMPLATE_SCANNER
    return REPLY_TEMPLATE

def main() -> int:
    env = load_env()
    client_id     = env.get("REDDIT_CLIENT_ID", "")
    client_secret = env.get("REDDIT_CLIENT_SECRET", "")
    username      = env.get("REDDIT_USERNAME", "")
    password      = env.get("REDDIT_PASSWORD", "")

    if not all([client_id, client_secret, username, password]):
        print("post_reddit_engagement: REDDIT credentials not configured — skipping")
        return 0

    token = get_reddit_token(client_id, client_secret, username, password)
    if not token:
        print("post_reddit_engagement: could not get token"); return 1

    seen     = load_seen()
    replied  = 0
    now      = time.time()

    for sub in SUBREDDITS:
        if replied >= MAX_REPLIES_PER_RUN:
            break
        posts = fetch_subreddit_new(token, username, sub)
        for post in posts:
            if replied >= MAX_REPLIES_PER_RUN:
                break
            d = post.get("data", {})
            post_id  = d.get("name", "")   # e.g. t3_abc123
            title    = d.get("title", "")
            selftext = d.get("selftext", "")
            created  = d.get("created_utc", 0)
            age_h    = (now - created) / 3600

            if post_id in seen: continue
            if age_h > MAX_POST_AGE_HOURS: continue
            if not is_relevant(title, selftext): continue
            if d.get("locked") or d.get("archived"): continue

            reply_text = pick_reply(title, selftext)
            print(f"  → r/{sub}: {title[:60]}")
            if post_reply(token, username, post_id, reply_text):
                seen.add(post_id)
                replied += 1
                print(f"    ✅ replied ({replied}/{MAX_REPLIES_PER_RUN})")
            else:
                print("    ❌ failed")
            time.sleep(10)  # reddit rate limit
        time.sleep(2)

    save_seen(seen)
    print(f"post_reddit_engagement: {replied} replies posted")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
