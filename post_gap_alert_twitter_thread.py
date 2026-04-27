#!/usr/bin/env python3
"""post_gap_alert_twitter_thread.py — Post a full 5-tweet thread for gap alerts.

Reads gap_alert_log.csv for alerts fired today, and posts a 5-tweet
thread for each one that doesn't already have a .gap_thread_{ticker}_{date} flag.

Can also be called with explicit args:
  python3 post_gap_alert_twitter_thread.py \\
      --ticker OLPX --price 2.01 --gap 50.0 --vol-ratio 8.5 --premarket

Thread format (5 tweets, chained as replies):
  1. Hook — ticker flagged, gap%, vol
  2. Data breakdown — price, gap, volume, time
  3. SEC context — from sec_top_gappers.csv / gap_scanner_top.csv
  4. Trade setup — gap-and-go rules, stop loss
  5. CTA — newsletter + Telegram

Required env vars:
  TWITTER_API_KEY
  TWITTER_API_SECRET
  TWITTER_ACCESS_TOKEN
  TWITTER_ACCESS_SECRET

Optional (loaded from .sec_email_env as fallback for local testing):
  NEWSLETTER_URL
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT           = Path(__file__).parent
ALERT_LOG      = ROOT / "gap_alert_log.csv"
GAP_TOP_CSV    = ROOT / "gap_scanner_top.csv"
GAPPERS_CSV    = ROOT / "sec_top_gappers.csv"
TWITTER_URL    = "https://api.twitter.com/2/tweets"
SCANNER_URL    = "https://catalystedgescanner.com"
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")


# ── Env loader ───────────────────────────────────────────────────────────────

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


# ── OAuth 1.0a ───────────────────────────────────────────────────────────────

def _pct(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(str(s), safe="")


def _oauth_header(method: str, url: str,
                  consumer_key: str, consumer_secret: str,
                  token: str, token_secret: str) -> str:
    oauth: dict[str, str] = {
        "oauth_consumer_key":     consumer_key,
        "oauth_nonce":            uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            token,
        "oauth_version":          "1.0",
    }
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


# ── Twitter post ─────────────────────────────────────────────────────────────

def post_tweet(text: str, api_key: str, api_secret: str,
               access_token: str, access_secret: str,
               reply_to_id: str | None = None) -> str | None:
    """Post a tweet. Returns tweet ID on success, None on failure."""
    payload: dict = {"text": text}
    if reply_to_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}
    body = json.dumps(payload).encode("utf-8")
    auth = _oauth_header("POST", TWITTER_URL, api_key, api_secret, access_token, access_secret)
    req  = urllib.request.Request(
        TWITTER_URL, data=body,
        headers={
            "Authorization": auth,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        return result.get("data", {}).get("id")
    except urllib.error.HTTPError as e:
        print(f"  twitter error: {e.code} {e.read()[:200]}")
        return None
    except Exception as e:
        print(f"  twitter error: {e}")
        return None


# ── Flag gating ──────────────────────────────────────────────────────────────

def already_threaded(ticker: str, date_str: str) -> bool:
    return (ROOT / f".gap_thread_{ticker}_{date_str}").exists()


def mark_threaded(ticker: str, date_str: str) -> None:
    (ROOT / f".gap_thread_{ticker}_{date_str}").touch()


# ── SEC context lookup ───────────────────────────────────────────────────────

def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def get_sec_context(ticker: str) -> tuple[str, str]:
    """Return (signal_text, form_type) from scanner CSVs, or defaults."""
    tag_map = [
        ("fda_approval",         "FDA approval catalyst"),
        ("fda_clearance",        "FDA clearance catalyst"),
        ("definitive_agreement", "Merger/acquisition agreement"),
        ("contract_award",       "Major contract award"),
        ("raises_guidance",      "Raised forward guidance"),
        ("record_revenue",       "Record revenue reported"),
        ("earnings_beat",        "Earnings beat catalyst"),
        ("share_repurchase",     "Share buyback announced"),
        ("insider_buy",          "Insider buying activity"),
        ("special_dividend",     "Special dividend declared"),
        ("patent",               "Patent filing activity"),
    ]
    form_map = {
        "8-K": "8-K event filing",
        "4":   "Form 4 insider trade",
        "SC 13D": "Activist 13D filing",
        "6-K": "6-K international filing",
        "S-3": "S-3 shelf registration",
    }

    for csv_path in [GAPPERS_CSV, GAP_TOP_CSV]:
        for row in _read_csv(csv_path):
            if row.get("ticker", "").upper() != ticker.upper():
                continue
            tags = (row.get("tags") or "").lower()
            for key, label in tag_map:
                if key in tags:
                    return label, form_map.get(row.get("form", ""), "")
            form = row.get("form", "")
            return "Recent SEC filing activity", form_map.get(form, form)

    return "Recent SEC filing activity", ""


# ── Thread builder ───────────────────────────────────────────────────────────

def _twitter_len(text: str) -> int:
    words  = text.split()
    length = 0
    for i, word in enumerate(words):
        length += 23 if word.startswith("http://") or word.startswith("https://") else len(word)
        if i < len(words) - 1:
            length += 1
    length += text.count("\n")
    return length


def build_thread(ticker: str, price: float, gap_pct: float, vol_ratio: float,
                 premarket: bool, alert_time: str) -> list[str]:
    """Build a 5-tweet gap alert thread. Each tweet <= 280 chars."""
    label   = "pre-market" if premarket else "regular session"
    sign    = "+" if gap_pct >= 0 else ""
    vol_str = f"{vol_ratio:.1f}x"
    gap_str = f"{sign}{gap_pct:.1f}%"

    signal, form = get_sec_context(ticker)
    if form:
        sec_line = f"{signal}\n{form}"
    else:
        sec_line = signal

    # Tweet 1 — hook
    t1 = (
        f"\U0001f6a8 ${ticker} flagged by our pre-market scanner\n\n"
        f"{gap_str} gap vs yesterday close\n"
        f"{vol_str} average volume -- {label}\n\n"
        f"Here's the full breakdown \U0001f447"
    )

    # Tweet 2 — data
    t2 = (
        f"${ticker} -- What the scanner caught:\n\n"
        f"\U0001f4ca Pre-market price: ${price:.2f}\n"
        f"\U0001f4c8 Gap vs prev close: {gap_str}\n"
        f"\U0001f525 Volume: {vol_str} daily average\n"
        f"\u23f0 Flagged at: {alert_time} ET\n\n"
        f"This is why we scan 1,600 tickers before 4am"
    )

    # Tweet 3 — SEC context
    t3 = (
        f"${ticker} catalyst context:\n\n"
        f"{sec_line}\n\n"
        f"We flag these before the algos front-run them"
    )

    # Tweet 4 — trade setup
    t4 = (
        f"${ticker} trade setup:\n\n"
        f"\u2705 Gap-and-go if holds pre-market highs\n"
        f"\u2705 Volume confirmation is key\n"
        f"\u274c Hard stop below pre-market low\n"
        f"\u26a0\ufe0f High-risk/high-reward -- size accordingly\n\n"
        f"Not financial advice. Do your own DD."
    )

    # Tweet 5 — CTA
    t5 = (
        f"Full scanner — free, no login, updated before 4am ET:\n\n"
        f"\U0001f5a5\ufe0f {SCANNER_URL}\n"
        f"\U0001f4ec {NEWSLETTER_URL}\n"
        f"\U0001f4f2 t.me/CatalystEdgePro\n\n"
        f"#pennystocks #gapup #premarket #daytrading #fintwit"
    )

    tweets = [t1, t2, t3, t4, t5]
    # Truncate anything that somehow exceeds 280
    return [t[:280] for t in tweets]


# ── Alert log reader ─────────────────────────────────────────────────────────

def load_today_alerts() -> list[dict]:
    """Read gap_alert_log.csv and return rows for today."""
    today = dt.date.today().isoformat()
    rows  = _read_csv(ALERT_LOG)
    return [r for r in rows if r.get("alert_date") == today]


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    _load_env()

    # ── CLI args (optional manual trigger) ───────────────────────────────────
    parser = argparse.ArgumentParser(description="Post gap alert Twitter thread")
    parser.add_argument("--ticker",    default="")
    parser.add_argument("--price",     type=float, default=0.0)
    parser.add_argument("--gap",       type=float, default=0.0)
    parser.add_argument("--vol-ratio", type=float, default=0.0, dest="vol_ratio")
    parser.add_argument("--premarket", action="store_true")
    parser.add_argument("--time",      default="")
    args = parser.parse_args()

    api_key      = os.environ.get("TWITTER_API_KEY", "")
    api_secret   = os.environ.get("TWITTER_API_SECRET", "")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    access_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")

    if not all([api_key, api_secret, access_token, access_secret]):
        print("post_gap_alert_twitter_thread: TWITTER_* env vars not set — skipping")
        return 0

    today_str = dt.date.today().isoformat()

    # Build list of alerts to thread
    alerts: list[dict] = []

    if args.ticker:
        # Explicit invocation
        alerts.append({
            "ticker":     args.ticker.upper(),
            "alert_price": str(args.price),
            "gap_pct":    str(args.gap),
            "vol_ratio":  str(args.vol_ratio),
            "premarket":  args.premarket,
            "alert_time": args.time or dt.datetime.now().strftime("%H:%M"),
        })
    else:
        # Auto-mode: read today's alert log
        for row in load_today_alerts():
            ticker = row.get("ticker", "").upper()
            if ticker and not already_threaded(ticker, today_str):
                alerts.append({
                    "ticker":      ticker,
                    "alert_price": row.get("alert_price", "0"),
                    "gap_pct":     row.get("gap_pct", "0"),
                    "vol_ratio":   row.get("vol_ratio", "0"),
                    "premarket":   False,
                    "alert_time":  row.get("alert_time", ""),
                })

    if not alerts:
        print("post_gap_alert_twitter_thread: no new alerts to thread today — skipping")
        return 0

    print(f"post_gap_alert_twitter_thread: threading {len(alerts)} alert(s)")

    for alert in alerts:
        ticker = alert["ticker"]
        try:
            price     = float(alert.get("alert_price") or 0)
            gap_pct   = float(alert.get("gap_pct") or 0)
            vol_ratio = float(alert.get("vol_ratio") or 0)
        except (TypeError, ValueError):
            price, gap_pct, vol_ratio = 0.0, 0.0, 0.0

        premarket  = bool(alert.get("premarket", False))
        alert_time = alert.get("alert_time", "")

        if already_threaded(ticker, today_str) and not args.ticker:
            print(f"  ${ticker}: thread already posted today — skipping")
            continue

        thread = build_thread(ticker, price, gap_pct, vol_ratio, premarket, alert_time)
        print(f"\n  Posting 5-tweet thread for ${ticker}...")

        # Load state file to allow partial resume
        state_file = ROOT / f".gap_thread_state_{ticker}_{today_str}.json"
        state: dict = {}
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
            except Exception:
                state = {}

        last_id  = state.get("last_id")
        start_i  = state.get("next_tweet", 0)
        success  = True

        for i in range(start_i, len(thread)):
            tweet_id = post_tweet(
                thread[i], api_key, api_secret, access_token, access_secret,
                reply_to_id=last_id,
            )
            if not tweet_id:
                print(f"  ERROR posting tweet {i+1} for ${ticker} — aborting thread")
                state_file.write_text(json.dumps({"last_id": last_id, "next_tweet": i}))
                success = False
                break
            last_id = tweet_id
            state_file.write_text(json.dumps({"last_id": last_id, "next_tweet": i + 1}))
            print(f"    tweet {i+1}/5 OK id={tweet_id}")
            if i < len(thread) - 1:
                time.sleep(2)

        if success:
            mark_threaded(ticker, today_str)
            state_file.unlink(missing_ok=True)
            print(f"  ${ticker}: thread complete")

        time.sleep(3)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
