#!/usr/bin/env python3
"""Post daily Catalyst Edge signal summary to Twitter/X.

Uses Twitter API v2 with OAuth 1.0a — stdlib only, no pip required.

Required env vars (set in .sec_email_env):
  TWITTER_API_KEY
  TWITTER_API_SECRET
  TWITTER_ACCESS_TOKEN
  TWITTER_ACCESS_SECRET

Optional:
  NEWSLETTER_URL  (defaults to https://catalystedge.agency)
"""
from __future__ import annotations

import base64
import csv
import datetime
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
SCANNER_URL      = "https://catalystedgescanner.com"
NEWSLETTER_URL   = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")
TWITTER_POST_URL = "https://api.twitter.com/2/tweets"


# ── OAuth 1.0a ─────────────────────────────────────────────────────────────

def _pct(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def _oauth_header(method: str, url: str,
                  consumer_key: str, consumer_secret: str,
                  token: str, token_secret: str) -> str:
    """Build OAuth 1.0a Authorization header for a JSON-body POST."""
    oauth: dict[str, str] = {
        "oauth_consumer_key":     consumer_key,
        "oauth_nonce":            uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            token,
        "oauth_version":          "1.0",
    }
    # Only OAuth params in base string for JSON body requests (no body params)
    param_str = "&".join(
        f"{_pct(k)}={_pct(v)}" for k, v in sorted(oauth.items())
    )
    base = f"{method.upper()}&{_pct(url)}&{_pct(param_str)}"
    key  = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    sig  = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(
        f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items())
    )


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


# ── Tweet builder ───────────────────────────────────────────────────────────

def _twitter_len(text: str) -> int:
    """Approximate Twitter length — URLs counted as 23 chars regardless."""
    words = text.split()
    length = 0
    for i, word in enumerate(words):
        if word.startswith("http://") or word.startswith("https://"):
            length += 23
        else:
            length += len(word)
        if i < len(words) - 1:
            length += 1  # space
    # Also count newlines
    length += text.count("\n")
    return length


_HOOKS = [
    "Scanned 300+ SEC filings before the open. Here's what stood out:",
    "Most traders won't see this until it's too late. Today's SEC scan:",
    "I run an automated scanner over every 8-K and Form 4 filed overnight. Today's picks:",
    "Wall Street reads SEC filings at 6am. So does my scanner. Here's today's output:",
    "The edge is in the filings. Here's what the SEC revealed this morning:",
    "Before the algos front-run it — today's catalyst scan:",
    "300+ SEC filings. One scanner. Here's what moved to the top:",
]

_TAGS = "#fintwit #stockstowatch #SEC #daytrading"


def build_tweet(picks: dict, squeeze_rows: list[dict],
                convergence_rows: list[dict]) -> str:
    import random
    today = datetime.date.today()

    top_pick  = picks.get("top_pick", "")
    gappers   = int(picks.get("gapper_count", 0) or 0)
    value     = int(picks.get("value_count",  0) or 0)
    moat      = int(picks.get("moat_count",   0) or 0)
    total     = gappers + value + moat
    scanned   = int(picks.get("total_combined", 0) or 300)

    coiled   = [r for r in squeeze_rows if r.get("stage") == "COILED"]
    ignition = [r for r in squeeze_rows if r.get("stage") == "IGNITION"]
    squeeze_highlight = (coiled + ignition)[:2]

    top_conv = [r for r in convergence_rows
                if r.get("conviction_level") in ("HIGH", "ELEVATED")][:2]

    # Pick a hook deterministically by day so same tweet goes out if retried
    hook = _HOOKS[today.toordinal() % len(_HOOKS)]

    lines: list[str] = [hook, ""]

    if top_pick:
        lines.append(f"📌 Top pick: ${top_pick}")

    if squeeze_highlight:
        tickers = " ".join(f"${r['ticker']}" for r in squeeze_highlight)
        stage   = "COILED" if coiled else "IGNITION"
        lines.append(f"🔥 Squeeze {stage}: {tickers}")

    if top_conv:
        tickers = " ".join(f"${r['ticker']}" for r in top_conv)
        lines.append(f"⚡ Multi-signal convergence: {tickers}")

    if total > 0:
        lines.append(f"📊 {total} picks from {scanned} tickers scanned today")

    lines.extend([
        "",
        f"Live scanner (free, no login) →",
        SCANNER_URL,
        "",
        _TAGS,
    ])

    tweet = "\n".join(lines)

    # Trim if over 280: drop convergence first, then squeeze
    if _twitter_len(tweet) > 280:
        lines = [l for l in lines if not l.startswith("⚡")]
        tweet = "\n".join(lines)
    if _twitter_len(tweet) > 280:
        lines = [l for l in lines if not l.startswith("🔥")]
        tweet = "\n".join(lines)

    return tweet


# ── Polymarket thread builder ────────────────────────────────────────────────

def _load_polymarket() -> list[dict]:
    p = ROOT / "polymarket_signals.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        # Reject if generated more than 36 hours ago — stale signals mislead
        generated = data.get("generated_at", "")
        if generated:
            from datetime import timezone as _tz
            age_hours = (datetime.datetime.now(_tz.utc) -
                         datetime.datetime.fromisoformat(generated)).total_seconds() / 3600
            if age_hours > 36:
                print("post_to_twitter: polymarket_signals.json is stale — skipping")
                return []
        return [s for s in data.get("signals", []) if 1 <= s.get("probability", 0) <= 99]
    except Exception:
        return []


def build_thread(picks: dict, squeeze_rows: list[dict],
                 convergence_rows: list[dict]) -> list[str]:
    """Build a 3-tweet thread. Returns list of tweet texts."""
    pm_signals = _load_polymarket()
    top_pick   = picks.get("top_pick", "")
    gappers    = int(picks.get("gapper_count", 0) or 0)
    value      = int(picks.get("value_count",  0) or 0)
    moat       = int(picks.get("moat_count",   0) or 0)
    total      = gappers + value + moat
    scanned    = int(picks.get("total_combined", 0) or 300)
    today      = datetime.date.today()

    tweets = []

    # ── Tweet 1: Polymarket macro hook (if signal available) or picks hook ──
    if pm_signals:
        # Pick the most contested signal (closest to 50%) for maximum interest
        best = min(pm_signals, key=lambda s: abs(s["probability"] - 50))
        prob = best["probability"]
        title = best["title"]
        impact = best["impact"]
        hook = _HOOKS[today.toordinal() % len(_HOOKS)]

        t1 = "\n".join([
            f"Polymarket is pricing {prob:.0f}% odds on:",
            f'"{title}"',
            "",
            f"Trader impact: {impact}",
            "",
            "Here's what our SEC scanner found this morning that aligns with this \U0001f447",
        ])
        tweets.append(t1[:280])
    else:
        # Fallback — no polymarket data
        hook = _HOOKS[today.toordinal() % len(_HOOKS)]
        tweets.append((hook + f"\n\nHere's today's full scan 👇")[:280])

    # ── Tweet 2: Today's picks ──
    coiled   = [r for r in squeeze_rows if r.get("stage") == "COILED"]
    ignition = [r for r in squeeze_rows if r.get("stage") == "IGNITION"]
    squeeze_highlight = (coiled + ignition)[:2]

    lines2 = [f"Today's SEC scan — {today.strftime('%b %-d')}:", ""]
    if top_pick:
        lines2.append(f"📌 Top pick: ${top_pick}")
    if squeeze_highlight:
        tickers = " ".join(f"${r['ticker']}" for r in squeeze_highlight)
        lines2.append(f"🔥 Squeeze COILED: {tickers}")
    if total > 0:
        lines2.append(f"📊 {total} picks from {scanned} filings scanned")
    lines2.extend(["", "Full breakdown → live scanner (free, no login):", SCANNER_URL])
    tweets.append("\n".join(lines2)[:280])

    # ── Tweet 3: CTA + hashtags ──
    t3 = "\n".join([
        "Free live scanner — no login, updated before 4am ET daily.",
        "",
        "300+ SEC filings. Scored. Ranked. Ready before pre-market.",
        "",
        f"🖥️ Scanner → {SCANNER_URL}",
        f"📬 Newsletter → {NEWSLETTER_URL}",
        "📲 Live alerts → t.me/CatalystEdgePro",
        "",
        _TAGS,
    ])
    tweets.append(t3[:280])

    return tweets


# ── Post ────────────────────────────────────────────────────────────────────

def post_tweet(text: str, api_key: str, api_secret: str,
               access_token: str, access_secret: str,
               reply_to_id: str | None = None) -> dict:
    payload: dict = {"text": text}
    if reply_to_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}
    body = json.dumps(payload).encode("utf-8")
    auth = _oauth_header(
        "POST", TWITTER_POST_URL,
        api_key, api_secret, access_token, access_secret,
    )
    req = urllib.request.Request(
        TWITTER_POST_URL,
        data=body,
        headers={
            "Authorization": auth,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    api_key       = os.environ.get("TWITTER_API_KEY", "")
    api_secret    = os.environ.get("TWITTER_API_SECRET", "")
    access_token  = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    access_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")

    if not all([api_key, api_secret, access_token, access_secret]):
        print("post_to_twitter: TWITTER_* env vars not set — skipping")
        return 0

    stamp = datetime.date.today().isoformat()
    flag  = ROOT / f".twitter_posted_{stamp}"
    if flag.exists():
        print(f"post_to_twitter: already posted today ({stamp}) — skipping")
        return 0

    picks            = _load_picks()
    squeeze_rows     = _load_csv("squeeze_candidates.csv")
    convergence_rows = _load_csv("convergence_alerts.csv")

    thread = build_thread(picks, squeeze_rows, convergence_rows)
    print(f"post_to_twitter: posting {len(thread)}-tweet thread")
    for i, t in enumerate(thread):
        print(f"  Tweet {i+1} ({_twitter_len(t)} chars):\n{t}\n")

    # Persist thread state so partial failures don't re-post tweet 1
    state_file = ROOT / f".twitter_thread_state_{stamp}.json"
    state: dict = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
        except Exception:
            state = {}

    try:
        last_id = state.get("last_id")
        start_i = state.get("next_tweet", 0)
        for i in range(start_i, len(thread)):
            text   = thread[i]
            result = post_tweet(text, api_key, api_secret, access_token, access_secret,
                                reply_to_id=last_id)
            last_id = result.get("data", {}).get("id")
            state = {"last_id": last_id, "next_tweet": i + 1}
            state_file.write_text(json.dumps(state))
            print(f"post_to_twitter: tweet {i+1} OK id={last_id}")
            if i < len(thread) - 1:
                time.sleep(2)
        flag.touch()
        state_file.unlink(missing_ok=True)
    except Exception as e:
        print(f"post_to_twitter: ERROR at tweet {state.get('next_tweet',0)+1} — {e}")
        print(f"post_to_twitter: state saved — will resume remaining tweets next run")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
