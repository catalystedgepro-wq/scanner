#!/usr/bin/env python3
"""post_eod_recap.py — End-of-day performance recap for Catalyst Edge.

Fires around 4:15pm ET (after market close) on weekdays.
Shows final performance of today's picks — builds credibility by showing
verified calls and drives newsletter signups from the EOD crowd.

Gated by .eod_posted_{date} flag (once per day only).

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
YAHOO_SPARK    = "https://query2.finance.yahoo.com/v8/finance/spark?symbols={}&range=1d&interval=5m"


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

def fetch_final_prices(tickers: list[str]) -> dict[str, dict]:
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
            sym      = item.get("symbol", "").upper()
            response = (item.get("response") or [{}])[0]
            meta     = response.get("meta", {})
            closes   = response.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            closes   = [c for c in closes if c is not None]
            if not closes:
                continue
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")
            curr = closes[-1]
            pct  = ((curr - prev) / prev * 100) if prev and prev > 0 else 0.0
            out[sym] = {
                "price":      round(curr, 2),
                "pct_change": round(pct, 2),
                "high":       round(max(closes), 2),
                "low":        round(min(closes), 2),
            }
        return out
    except Exception as e:
        print(f"  fetch_final_prices error: {e}")
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

def perf_emoji(pct: float) -> str:
    if pct >= 5:   return "🚀"
    if pct >= 2:   return "📈"
    if pct >= 0:   return "➡️"
    if pct >= -2:  return "📉"
    return "🔴"


def build_eod_tweets(picks: dict, prices: dict) -> list[str]:
    today    = datetime.date.today().strftime("%b %-d")
    top5     = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]

    # Build result lines
    perf_lines = []
    winners, losers = [], []
    for t in top5[:5]:
        q = prices.get(t.upper())
        if not q:
            perf_lines.append(f"  ${t} — data unavailable")
            continue
        pct  = q["pct_change"]
        sign = "+" if pct >= 0 else ""
        em   = perf_emoji(pct)
        perf_lines.append(f"  {em} ${t}  {sign}{pct:.1f}%  (${q['price']})")
        if pct > 0:
            winners.append((t, pct))
        else:
            losers.append((t, pct))

    winners.sort(key=lambda x: x[1], reverse=True)

    # Summary line
    win_count = len(winners)
    total = len([t for t in top5[:5] if prices.get(t.upper())])
    if win_count == total and total > 0:
        summary = f"✅ {win_count}/{total} picks closed green today."
    elif win_count >= total // 2 and total > 0:
        summary = f"📊 {win_count}/{total} picks closed green today."
    else:
        summary = f"📊 Tough session — catalyst setups play out over 2-5 days."

    pm = load_polymarket()

    # Tweet 1: scoreboard
    t1_lines = [
        f"📊 EOD recap — {today}",
        "",
        "Today's SEC picks final score:",
        "",
    ] + perf_lines + [
        "",
        summary,
        "",
        f"Tomorrow's picks drop at 4am ET → {NEWSLETTER_URL}",
    ]
    t1 = "\n".join(t1_lines)[:280]

    # Tweet 2: credibility + CTA
    best = f"${winners[0][0]} (+{winners[0][1]:.1f}%)" if winners else "tomorrow's picks"
    pm_line = ""
    if pm:
        pm_line = (f"Macro for tomorrow: Polymarket at {pm['probability']:.0f}% on "
                   f'"{pm["title"][:45]}"\n\n')

    t2 = (
        f"Best performer today: {best}\n\n"
        f"{pm_line}"
        f"Every pick sourced from live SEC EDGAR filings — 8-Ks, Form 4s, 13Ds.\n"
        f"No guesswork. Just filings.\n\n"
        f"Free daily breakdown → {NEWSLETTER_URL}\n\n"
        f"#fintwit #SEC #stocks #stockstowatch #wallstreetbets"
    )[:280]

    return [t1, t2]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    stamp = datetime.date.today().isoformat()
    flag  = ROOT / f".eod_posted_{stamp}"
    if flag.exists():
        print(f"post_eod_recap: already posted today ({stamp}) — skipping")
        return 0

    picks = load_picks()
    if not picks:
        print("post_eod_recap: no picks found — skipping")
        return 0

    top5 = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]
    if not top5:
        print("post_eod_recap: no tickers — skipping")
        return 0

    print(f"post_eod_recap: fetching final prices for {top5}")
    prices = fetch_final_prices(top5)
    print(f"  got: {list(prices.keys())}")

    tweets = build_eod_tweets(picks, prices)
    for i, t in enumerate(tweets):
        print(f"\n  Tweet {i+1}:\n{t}")

    api_key       = os.environ.get("TWITTER_API_KEY", "")
    api_secret    = os.environ.get("TWITTER_API_SECRET", "")
    access_token  = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    access_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")

    if not all([api_key, api_secret, access_token, access_secret]):
        print("\npost_eod_recap: no Twitter creds — saving to file")
        out = ROOT / "social" / f"eod_recap_{stamp}.txt"
        out.parent.mkdir(exist_ok=True)
        out.write_text("\n\n---\n\n".join(tweets), encoding="utf-8")
        win_out = Path(f"/path/to/local/Desktop/catalyst-edge/social/eod_recap_{stamp}.txt")
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
            print(f"post_eod_recap: tweet {i+1} posted id={last_id}")
            if i < len(tweets) - 1:
                time.sleep(2)
        flag.touch()
        print(f"post_eod_recap: done — {len(tweets)} tweets posted")
    except Exception as e:
        print(f"post_eod_recap: Twitter error — {e}")
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
