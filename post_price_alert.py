#!/usr/bin/env python3
"""post_price_alert.py — Real-time price alert poster for Catalyst Edge.

Runs every 30 min during market hours via GitHub Actions cron.
Fires an immediate 2-tweet thread when any of today's picks moves
≥ BULL_PCT% up or ≤ BEAR_PCT% down from the previous close.

Each ticker alerts at most once per day (flag: .alert_{TICKER}_{date}).
Falls back to saving text file if Twitter creds are absent.

Required env vars (for live posting):
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
"""
from __future__ import annotations

import base64, csv, datetime, hashlib, hmac, json
import os, smtplib, time, urllib.parse, urllib.request, uuid
from email.message import EmailMessage
from pathlib import Path

ROOT           = Path(__file__).parent
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")
TWITTER_URL    = "https://api.twitter.com/2/tweets"
YAHOO_SPARK    = "https://query2.finance.yahoo.com/v8/finance/spark?symbols={}&range=1d&interval=5m"

BULL_PCT = 3.0    # % gain → bullish alert
BEAR_PCT = -4.0   # % drop → bearish alert (wider to filter noise)


# ── OAuth helpers (shared pattern) ────────────────────────────────────────────

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

def fetch_prices(tickers: list[str]) -> dict[str, dict]:
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
        print(f"  fetch_prices error: {e}")
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


def load_catalyst_context(ticker: str) -> dict:
    """Pull signal/form from any clean CSV for the ticker."""
    for fname in ["sec_clean_gappers.csv", "sec_clean_value.csv",
                  "sec_top_gappers.csv", "sec_top_value.csv"]:
        p = ROOT / fname
        if not p.exists():
            continue
        try:
            with p.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("ticker", "").upper() == ticker.upper():
                        return row
        except Exception:
            pass
    return {}


def signal_label(ctx: dict) -> str:
    tags = (ctx.get("tags") or "").lower()
    tag_map = [
        ("fda_approval",         "FDA approval"),
        ("fda_clearance",        "FDA clearance"),
        ("definitive_agreement", "definitive merger agreement"),
        ("merger_agreement",     "merger agreement"),
        ("contract_award",       "contract award"),
        ("raises_guidance",      "raised guidance"),
        ("record_revenue",       "record revenue"),
        ("earnings_beat",        "earnings beat"),
        ("share_repurchase",     "buyback authorized"),
        ("insider_buy",          "insider buying (Form 4)"),
        ("patent",               "patent filing"),
        ("special_dividend",     "special dividend"),
    ]
    for key, label in tag_map:
        if key in tags:
            return label
    form_map = {"8-K": "8-K event filing", "4": "Form 4 insider buy",
                "SC 13D": "activist 13D", "6-K": "6-K foreign filing"}
    return form_map.get(ctx.get("form", ""), "SEC catalyst filing")


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


# ── Alert tweet builder ────────────────────────────────────────────────────────

def build_alert_tweets(ticker: str, pct: float, price: float, ctx: dict,
                       other_picks: list[str]) -> list[str]:
    sign   = "+" if pct >= 0 else ""
    signal = signal_label(ctx)
    date   = datetime.date.today().strftime("%b %-d")
    others = " ".join(f"${t}" for t in other_picks[:3])
    pm     = load_polymarket()

    if pct >= BULL_PCT:
        headline  = f"🚨 ${ticker} is up {sign}{pct:.1f}% today"
        subtext   = "The SEC filing flagged this at 4am. Catalyst playing out."
        sentiment = "Bullish"
    else:
        headline  = f"⚠️ ${ticker} is down {pct:.1f}% today"
        subtext   = "We flagged downside risk this morning. Thesis under pressure."
        sentiment = "Watching"

    # Tweet 1: the alert itself
    t1 = (
        f"{headline}\n\n"
        f"We found this in an SEC filing before the open ({date}).\n"
        f"Signal: {signal}\n\n"
        f"{subtext}\n\n"
        f"Full breakdown + tomorrow's picks → {NEWSLETTER_URL}"
    )[:280]

    # Tweet 2: context + CTA
    pm_line = ""
    if pm:
        pm_line = (f"Macro overlay: Polymarket at {pm['probability']:.0f}% on "
                   f'"{pm["title"][:50]}" — {pm["impact"]}.\n\n')

    t2 = (
        f"{sentiment} | {date} SEC scan: ${ticker} + {others}\n\n"
        f"{pm_line}"
        f"We read 300+ EDGAR filings every morning so you don't have to.\n"
        f"Free daily picks drop at 4am ET → {NEWSLETTER_URL}\n\n"
        f"#fintwit #stockstowatch #SEC #stocks"
    )[:280]

    return [t1, t2]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    stamp = datetime.date.today().isoformat()

    picks = load_picks()
    if not picks:
        print("post_price_alert: no picks — pipeline hasn't run yet")
        return 0

    top5 = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]
    if not top5:
        print("post_price_alert: no tickers — skipping")
        return 0

    # Only check tickers that haven't fired an alert today
    pending = [t for t in top5 if not (ROOT / f".alert_{t.upper()}_{stamp}").exists()]
    if not pending:
        print(f"post_price_alert: all tickers already alerted today — done")
        return 0

    print(f"post_price_alert: checking {pending} (threshold: bull≥{BULL_PCT}% bear≤{BEAR_PCT}%)")
    prices = fetch_prices(pending)
    if not prices:
        print("  no price data — market may be closed")
        return 0

    # Twitter creds
    api_key       = os.environ.get("TWITTER_API_KEY", "")
    api_secret    = os.environ.get("TWITTER_API_SECRET", "")
    access_token  = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    access_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")
    has_creds     = all([api_key, api_secret, access_token, access_secret])
    creds = {"key": api_key, "secret": api_secret,
             "token": access_token, "token_secret": access_secret}

    alerts_fired = 0
    for ticker in pending:
        q = prices.get(ticker.upper())
        if not q:
            continue
        pct = q["pct_change"]
        if BEAR_PCT < pct < BULL_PCT:
            print(f"  ${ticker}: {pct:+.1f}% — no threshold crossed")
            continue

        ctx    = load_catalyst_context(ticker)
        others = [t for t in top5 if t != ticker]
        tweets = build_alert_tweets(ticker, pct, q["price"], ctx, others)

        print(f"\n  *** ALERT ${ticker} {pct:+.1f}% ***")
        for i, t in enumerate(tweets):
            print(f"  Tweet {i+1}:\n{t}\n")

        # Flag before posting to prevent duplicate on error
        (ROOT / f".alert_{ticker.upper()}_{stamp}").touch()

        # Email premium subscribers immediately
        send_premium_alert_email(ticker, pct, q["price"], ctx, stamp)

        if has_creds:
            try:
                last_id = None
                for i, text in enumerate(tweets):
                    last_id = post_tweet(text, creds, reply_to=last_id)
                    print(f"  posted id={last_id}")
                    if i < len(tweets) - 1:
                        time.sleep(2)
                alerts_fired += 1
            except Exception as e:
                print(f"  Twitter error: {e}")
        else:
            out = ROOT / "social" / f"alert_{ticker}_{stamp}.txt"
            out.parent.mkdir(exist_ok=True)
            out.write_text("\n\n---\n\n".join(tweets), encoding="utf-8")
            win_out = Path(f"/path/to/local/Desktop/catalyst-edge/social/alert_{ticker}_{stamp}.txt")
            try:
                win_out.write_text("\n\n---\n\n".join(tweets), encoding="utf-8")
            except OSError:
                pass
            print(f"  saved to {out}")
            alerts_fired += 1

    if alerts_fired == 0:
        print("post_price_alert: no thresholds crossed this pass")
    else:
        print(f"\npost_price_alert: {alerts_fired} alert(s) fired")
        # Refresh agent so she knows about the move too
        refresh_agent()
    return 0


def send_premium_alert_email(ticker: str, pct: float, price: float,
                              ctx: dict, stamp: str) -> None:
    """Email premium subscribers when one of their picks fires a price alert."""
    premium_to = os.environ.get("PREMIUM_EMAIL_TO", "").strip()
    if not premium_to:
        return
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    email_from = os.environ.get("EMAIL_FROM", smtp_user)
    if not all([smtp_host, smtp_user, smtp_pass]):
        return

    sign = "+" if pct >= 0 else ""
    direction = "🚀 BULLISH" if pct >= BULL_PCT else "⚠️ BEARISH"
    signal = signal_label(ctx)
    subject = f"[⚡ Premium Alert] ${ticker} {sign}{pct:.1f}% — {direction}"

    html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f0f2f5;padding:20px;">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#0a0f1e;border-radius:8px;padding:28px 32px;margin:0 auto;">
  <tr><td>
    <div style="font-size:11px;font-weight:700;color:#818cf8;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px;">⚡ Premium Catalyst Alert</div>
    <div style="font-size:28px;font-weight:900;color:#ffffff;margin-bottom:4px;">${ticker}</div>
    <div style="font-size:22px;font-weight:800;color:{"#10b981" if pct >= 0 else "#ef4444"};">{sign}{pct:.1f}% — {direction}</div>
    <div style="font-size:14px;color:#94a3b8;margin-top:8px;">Current price: <strong style="color:#fff;">${price:.2f}</strong></div>
    <div style="font-size:13px;color:#64748b;margin-top:4px;">SEC signal: {signal}</div>
    <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:20px 0;">
    <div style="font-size:12px;color:#64748b;">
      This alert fired because ${ticker} crossed the {"+" + str(BULL_PCT) if pct >= 0 else str(BEAR_PCT)}% threshold.<br>
      You're receiving this as a <strong style="color:#818cf8;">Catalyst Edge Premium</strong> subscriber.<br><br>
      <a href="{NEWSLETTER_URL}" style="color:#3b82f6;">View today's full newsletter →</a>
    </div>
  </td></tr>
</table>
</body></html>"""

    recipients = [e.strip() for e in premium_to.split(",") if e.strip()]
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            for recipient in recipients:
                msg = EmailMessage()
                msg["From"] = email_from
                msg["To"] = recipient
                msg["Subject"] = subject
                msg.set_content(f"${ticker} {sign}{pct:.1f}% — {direction}. Signal: {signal}. View newsletter: {NEWSLETTER_URL}")
                msg.add_alternative(html, subtype="html")
                smtp.send_message(msg)
        print(f"  premium_alert_email sent to {len(recipients)} subscriber(s)")
    except Exception as e:
        print(f"  premium_alert_email failed: {e}")


def refresh_agent() -> None:
    """Refresh agent knowledge when a significant move fires."""
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
    raise SystemExit(main())
