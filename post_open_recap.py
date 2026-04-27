#!/usr/bin/env python3
"""post_open_recap.py — Market-open recap post for Catalyst Edge.

Fires at 9:30am ET (market open) on weekdays.
Posts a tweet showing today's picks with opening prices — sets the stage
and drives newsletter signups from traders just starting their day.

Gated by .open_posted_{date} flag (once per day only).

Required env vars: TWITTER_API_KEY, TWITTER_API_SECRET,
                   TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
"""
from __future__ import annotations

import base64, csv, datetime, hashlib, hmac, json
import os, time, urllib.parse, urllib.request, uuid
from pathlib import Path

ROOT           = Path(__file__).parent
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")
TWITTER_URL    = "https://api.twitter.com/2/tweets"
YAHOO_SPARK    = "https://query2.finance.yahoo.com/v8/finance/spark?symbols={}&range=1d&interval=1m"


# ── OAuth helpers ──────────────────────────────────────────────────────────────

def _pct_enc(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def _oauth_header(method: str, url: str, ck: str, cs: str, tok: str, ts: str) -> str:
    oauth = {
        "oauth_consumer_key":     ck,
        "oauth_nonce":            uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            tok,
        "oauth_version":          "1.0",
    }
    param_str = "&".join(f"{_pct_enc(k)}={_pct_enc(v)}" for k, v in sorted(oauth.items()))
    base = f"{method.upper()}&{_pct_enc(url)}&{_pct_enc(param_str)}"
    key  = f"{_pct_enc(cs)}&{_pct_enc(ts)}"
    sig  = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_pct_enc(k)}="{_pct_enc(v)}"' for k, v in sorted(oauth.items()))


def post_tweet(text: str, creds: dict, reply_to: str | None = None) -> str:
    payload: dict = {"text": text}
    if reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to}
    body = json.dumps(payload).encode()
    auth = _oauth_header("POST", TWITTER_URL,
                         creds["key"], creds["secret"],
                         creds["token"], creds["token_secret"])
    req = urllib.request.Request(TWITTER_URL, data=body, headers={
        "Authorization": auth,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data.get("data", {}).get("id", "")


# ── Price fetching ─────────────────────────────────────────────────────────────

def fetch_opening_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch the latest price for each ticker."""
    if not tickers:
        return {}
    url = YAHOO_SPARK.format(",".join(tickers))
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        out = {}
        for item in (data.get("spark", {}).get("result") or []):
            sym    = item.get("symbol", "").upper()
            resp_  = (item.get("response") or [{}])[0]
            closes = resp_.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            closes = [c for c in closes if c is not None]
            if closes:
                out[sym] = round(closes[-1], 2)
        return out
    except Exception as e:
        print(f"  fetch_opening_prices error: {e}")
        return {}


# ── Data loaders ──────────────────────────────────────────────────────────────

def load_picks() -> dict:
    p = ROOT / "newsletter_picks.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_catalyst_signals() -> dict[str, str]:
    """Map ticker → short signal description from CSV files."""
    signals: dict[str, str] = {}
    tag_map = [
        ("fda_approval",         "FDA approval"),
        ("fda_clearance",        "FDA clearance"),
        ("definitive_agreement", "merger agreement"),
        ("contract_award",       "contract award"),
        ("raises_guidance",      "guidance raised"),
        ("record_revenue",       "record revenue"),
        ("earnings_beat",        "earnings beat"),
        ("share_repurchase",     "buyback"),
        ("insider_buy",          "insider buying"),
        ("special_dividend",     "special dividend"),
        ("patent",               "patent filing"),
    ]
    form_map = {"8-K": "8-K event", "4": "Form 4 buy",
                "SC 13D": "activist 13D", "6-K": "6-K filing"}

    for fname in ["sec_clean_gappers.csv", "sec_clean_value.csv",
                  "sec_top_gappers.csv", "sec_top_value.csv"]:
        p = ROOT / fname
        if not p.exists():
            continue
        try:
            with p.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = (row.get("ticker") or "").upper()
                    if not t or t in signals:
                        continue
                    tags = (row.get("tags") or "").lower()
                    label = None
                    for key, desc in tag_map:
                        if key in tags:
                            label = desc
                            break
                    if not label:
                        label = form_map.get(row.get("form", ""), "SEC filing")
                    signals[t] = label
        except Exception:
            pass
    return signals


def load_polymarket() -> dict | None:
    p = ROOT / "polymarket_signals.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        age_h = (datetime.datetime.now(datetime.timezone.utc) -
                 datetime.datetime.fromisoformat(data.get("generated_at", "1970-01-01T00:00:00+00:00"))
                 ).total_seconds() / 3600
        if age_h > 36:
            return None
        sigs = [s for s in data.get("signals", []) if 10 <= s.get("probability", 0) <= 90]
        return min(sigs, key=lambda x: abs(x["probability"] - 50)) if sigs else None
    except Exception:
        return None


# ── Tweet builder ──────────────────────────────────────────────────────────────

def build_open_tweets(picks: dict, prices: dict[str, float],
                      signals: dict[str, str]) -> list[str]:
    today    = datetime.date.today().strftime("%b %-d")
    top5     = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]

    # Build pick lines with opening price
    pick_lines = []
    for t in top5[:5]:
        price = prices.get(t.upper())
        sig   = signals.get(t.upper(), "SEC catalyst")
        price_str = f" @ ${price}" if price else ""
        pick_lines.append(f"  📌 ${t}{price_str} — {sig}")

    pm = load_polymarket()

    # Tweet 1: picks list
    t1_lines = [
        f"🔔 Market open — {today}",
        "",
        "Today's picks from our 4am SEC scan are live:",
        "",
    ] + pick_lines + [
        "",
        f"Full breakdown → {NEWSLETTER_URL}",
    ]
    t1 = "\n".join(t1_lines)[:280]

    # Tweet 2: methodology + macro
    if pm:
        t2 = (
            f"How we find these: scan 300+ EDGAR filings before 4am.\n\n"
            f"8-Ks, Form 4s, Schedule 13Ds — sorted by catalyst strength.\n\n"
            f"Today's macro context: Polymarket at {pm['probability']:.0f}% on "
            f'"{pm["title"][:50]}"\n\n'
            f"Free daily picks → {NEWSLETTER_URL}\n\n"
            f"#fintwit #SEC #stocks #stockstowatch"
        )[:280]
    else:
        t2 = (
            f"How we find these: scan 300+ EDGAR filings before 4am.\n\n"
            f"8-Ks, Form 4s, Schedule 13Ds — catalyst strength scored across "
            f"8 signal layers.\n\n"
            f"Free picks drop at 4am ET every weekday → {NEWSLETTER_URL}\n\n"
            f"#fintwit #SEC #stocks #stockstowatch #daytrading"
        )[:280]

    return [t1, t2]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    stamp = datetime.date.today().isoformat()
    flag  = ROOT / f".open_posted_{stamp}"
    if flag.exists():
        print(f"post_open_recap: already posted today ({stamp}) — skipping")
        return 0

    picks = load_picks()
    if not picks:
        print("post_open_recap: no picks found — pipeline hasn't run yet")
        return 0

    top5 = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]
    if not top5:
        print("post_open_recap: no tickers — skipping")
        return 0

    print(f"post_open_recap: fetching opening prices for {top5}")
    prices  = fetch_opening_prices(top5)
    signals = load_catalyst_signals()
    print(f"  prices: {prices}")

    tweets = build_open_tweets(picks, prices, signals)
    for i, t in enumerate(tweets):
        print(f"\n  Tweet {i+1}:\n{t}")

    api_key       = os.environ.get("TWITTER_API_KEY", "")
    api_secret    = os.environ.get("TWITTER_API_SECRET", "")
    access_token  = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    access_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")

    if not all([api_key, api_secret, access_token, access_secret]):
        print("\npost_open_recap: no Twitter creds — saving to file")
        out = ROOT / "social" / f"open_recap_{stamp}.txt"
        out.parent.mkdir(exist_ok=True)
        out.write_text("\n\n---\n\n".join(tweets), encoding="utf-8")
        win_out = Path(f"/path/to/local/Desktop/catalyst-edge/social/open_recap_{stamp}.txt")
        try:
            win_out.write_text("\n\n---\n\n".join(tweets), encoding="utf-8")
        except OSError:
            pass
        print(f"  saved to {out}")
        flag.touch()
        return 0

    creds = {"key": api_key, "secret": api_secret,
             "token": access_token, "token_secret": access_secret}
    try:
        last_id = None
        for i, text in enumerate(tweets):
            last_id = post_tweet(text, creds, reply_to=last_id)
            print(f"post_open_recap: tweet {i+1} posted id={last_id}")
            if i < len(tweets) - 1:
                time.sleep(2)
        flag.touch()
        print(f"post_open_recap: done — {len(tweets)} tweets posted")
    except Exception as e:
        print(f"post_open_recap: Twitter error — {e}")
        return 1

    return 0


def refresh_agent() -> None:
    """Refresh agent knowledge after posting — keeps catalystedge.agency current."""
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "update_agent_knowledge.py")],
            timeout=30, capture_output=True, text=True
        )
        print(result.stdout.strip())
        if result.returncode != 0 and result.stderr:
            print(f"  agent_refresh warning: {result.stderr[:100]}")
    except Exception as e:
        print(f"  agent_refresh skipped: {e}")


if __name__ == "__main__":
    import sys
    rc = main()
    if rc == 0:
        refresh_agent()
    raise SystemExit(rc)
