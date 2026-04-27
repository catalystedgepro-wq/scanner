#!/usr/bin/env python3
"""post_midday_update.py — Midday performance update for Catalyst Edge.

Posts to X/Twitter and StockTwits around 1pm ET showing how today's
picks are actually moving. Real performance data = highest engagement.

Gated by a daily flag so it only fires once per day.
Skips if today's picks aren't available (pipeline hasn't run yet).

Required env vars: TWITTER_API_KEY, TWITTER_API_SECRET,
                   TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
Optional: BEEHIIV_PUB_ID, BEEHIIV_API_KEY (for StockTwits session check)
"""
from __future__ import annotations

import base64, csv, datetime, hashlib, hmac, json
import os, time, urllib.parse, urllib.request, uuid
from pathlib import Path

ROOT           = Path(__file__).parent
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")
TWITTER_URL    = "https://api.twitter.com/2/tweets"
YAHOO_SPARK    = "https://query2.finance.yahoo.com/v8/finance/spark?symbols={}&range=1d&interval=5m"

# ── Price fetching ────────────────────────────────────────────────────────────

def fetch_prices(tickers: list[str]) -> dict[str, dict]:
    """Fetch intraday price data via Yahoo Spark API."""
    if not tickers:
        return {}
    url = YAHOO_SPARK.format(",".join(tickers))
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        out = {}
        spark = data.get("spark", {}).get("result") or []
        for item in spark:
            sym = item.get("symbol", "").upper()
            response = (item.get("response") or [{}])[0]
            meta = response.get("meta", {})
            closes = response.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            closes = [c for c in closes if c is not None]
            if not closes:
                continue
            prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
            current    = closes[-1]
            if prev_close and prev_close > 0:
                pct = ((current - prev_close) / prev_close) * 100
            else:
                pct = 0.0
            out[sym] = {
                "price":      round(current, 2),
                "prev_close": round(prev_close, 2) if prev_close else None,
                "pct_change": round(pct, 2),
                "high":       round(max(closes), 2),
                "low":        round(min(closes), 2),
            }
        return out
    except Exception as e:
        print(f"  fetch_prices error: {e}")
        return {}


# ── Data loaders ─────────────────────────────────────────────────────────────

def load_picks() -> dict:
    p = ROOT / "newsletter_picks.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_polymarket() -> dict | None:
    p = ROOT / "polymarket_signals.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        generated = data.get("generated_at", "")
        if generated:
            age_h = (datetime.datetime.now(datetime.timezone.utc) -
                     datetime.datetime.fromisoformat(generated)).total_seconds() / 3600
            if age_h > 36:
                return None
        sigs = [s for s in data.get("signals", []) if 10 <= s.get("probability", 0) <= 90]
        return min(sigs, key=lambda x: abs(x["probability"] - 50)) if sigs else None
    except Exception:
        return None


# ── Tweet builder ─────────────────────────────────────────────────────────────

def arrow(pct: float) -> str:
    if pct >= 2:   return "🚀"
    if pct >= 0.5: return "📈"
    if pct >= 0:   return "➡️"
    if pct >= -1:  return "📉"
    return "🔴"


def build_midday_tweets(picks: dict, prices: dict) -> list[str]:
    today  = datetime.date.today().strftime("%b %-d")
    top5   = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]

    # Build performance lines
    perf_lines = []
    movers = []
    for t in top5[:5]:
        q = prices.get(t.upper())
        if not q:
            perf_lines.append(f"  ${t} — price unavailable")
            continue
        pct = q["pct_change"]
        em  = arrow(pct)
        sign = "+" if pct >= 0 else ""
        perf_lines.append(f"  {em} ${t}  {sign}{pct:.1f}%  (${q['price']})")
        if abs(pct) >= 1:
            movers.append((t, pct))

    movers.sort(key=lambda x: abs(x[1]), reverse=True)

    # Tweet 1 — midday scoreboard
    t1_lines = [
        f"Midday check-in — {today}",
        "",
        "How our morning picks are moving:",
        "",
    ] + perf_lines + [
        "",
        f"Full context → {NEWSLETTER_URL}",
    ]
    t1 = "\n".join(t1_lines)[:280]

    # Tweet 2 — insight + Polymarket angle
    pm = load_polymarket()
    if movers and pm:
        top_mover, top_pct = movers[0]
        sign = "+" if top_pct >= 0 else ""
        t2 = (
            f"${top_mover} is the standout at {sign}{top_pct:.1f}% midday.\n\n"
            f"Polymarket context: {pm['probability']:.0f}% odds on \"{pm['title'][:55]}\"\n"
            f"That's moving {pm['impact'].lower()}.\n\n"
            f"Free daily picks → {NEWSLETTER_URL}"
        )[:280]
    elif movers:
        top_mover, top_pct = movers[0]
        sign = "+" if top_pct >= 0 else ""
        t2 = (
            f"${top_mover} leading the pack at {sign}{top_pct:.1f}% today.\n\n"
            f"We flagged it this morning from SEC filings before the open.\n\n"
            f"Tomorrow's picks drop at 4am ET — free:\n{NEWSLETTER_URL}"
        )[:280]
    else:
        t2 = (
            f"Mixed session so far on today's picks.\n\n"
            f"The edge isn't always same-day — catalyst setups play out over 2-5 days.\n\n"
            f"Tomorrow's scan drops at 4am ET:\n{NEWSLETTER_URL}\n\n"
            f"#fintwit #SEC #stockstowatch"
        )[:280]

    return [t1, t2]


# ── OAuth + post ──────────────────────────────────────────────────────────────

def _pct_enc(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def _oauth_header(method, url, ck, cs, tok, ts) -> str:
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    stamp = datetime.date.today().isoformat()
    flag  = ROOT / f".midday_posted_{stamp}"
    if flag.exists():
        print(f"post_midday_update: already posted today ({stamp}) — skipping")
        return 0

    picks = load_picks()
    if not picks:
        print("post_midday_update: no picks found — pipeline hasn't run yet today")
        return 0

    top5 = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]

    if not top5:
        print("post_midday_update: no tickers in picks — skipping")
        return 0

    print(f"post_midday_update: fetching prices for {top5}")
    prices = fetch_prices(top5)
    print(f"  Got prices for: {list(prices.keys())}")

    tweets = build_midday_tweets(picks, prices)
    for i, t in enumerate(tweets):
        print(f"\n  Tweet {i+1}:\n{t}")

    # Post to Twitter
    api_key      = os.environ.get("TWITTER_API_KEY", "")
    api_secret   = os.environ.get("TWITTER_API_SECRET", "")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    access_secret= os.environ.get("TWITTER_ACCESS_SECRET", "")

    if not all([api_key, api_secret, access_token, access_secret]):
        print("\npost_midday_update: Twitter creds not set — saving to file only")
        out = ROOT / "social" / f"midday_post_{stamp}.txt"
        out.parent.mkdir(exist_ok=True)
        out.write_text("\n\n---\n\n".join(tweets), encoding="utf-8")
        win_out = Path(f"/path/to/local/Desktop/catalyst-edge/social/midday_post_{stamp}.txt")
        try:
            win_out.write_text("\n\n---\n\n".join(tweets), encoding="utf-8")
        except OSError:
            pass
        print(f"  Saved to {out}")
        flag.touch()
        return 0

    creds = {"key": api_key, "secret": api_secret,
             "token": access_token, "token_secret": access_secret}
    try:
        last_id = None
        for i, text in enumerate(tweets):
            last_id = post_tweet(text, creds, reply_to=last_id)
            print(f"post_midday_update: tweet {i+1} posted id={last_id}")
            if i < len(tweets) - 1:
                time.sleep(2)
        flag.touch()
        print(f"post_midday_update: done — {len(tweets)} tweets posted")
    except Exception as e:
        print(f"post_midday_update: Twitter error — {e}")
        return 1

    return 0


def refresh_agent() -> None:
    """Refresh agent knowledge after posting."""
    import subprocess, sys as _sys
    try:
        result = subprocess.run(
            [_sys.executable, str(ROOT / "update_agent_knowledge.py")],
            timeout=30, capture_output=True, text=True
        )
        print(result.stdout.strip())
    except Exception as e:
        print(f"  agent_refresh skipped: {e}")


if __name__ == "__main__":
    rc = main()
    if rc == 0:
        refresh_agent()
    raise SystemExit(rc)
