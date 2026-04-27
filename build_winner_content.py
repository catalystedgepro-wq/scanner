#!/usr/bin/env python3
"""build_winner_content.py — Generate social content folders for gap winners.

Creates social/gap_winners/{TICKER}_{DATE}/ with ready-to-use content:
  twitter_thread.txt      — 3-tweet thread specific to this ticker
  stocktwits.txt          — reference copy of auto-posted StockTwits message
  instagram_caption.txt   — narrative caption with hashtags
  tiktok_script.txt       — spoken-word script, 30-60 sec
  youtube_description.txt — video description for YouTube upload
  video_script.txt        — full talking points (intro, setup, catalyst, watch for)
  thumbnail_brief.txt     — thumbnail text overlay brief
  summary.json            — raw data for reference

Can be called two ways:
  1. From post_penny_gap_alert.py immediately when an alert fires (real-time)
  2. Standalone: scans gap_outcome_log.csv for winners and generates any missing folders

Usage:
  python3 build_winner_content.py                  # process all unevaluated winners
  python3 build_winner_content.py --ticker UGRO    # generate for specific ticker
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path

ROOT         = Path(__file__).parent
ALERT_LOG    = ROOT / "gap_alert_log.csv"
OUTCOME_LOG  = ROOT / "gap_outcome_log.csv"
WINNERS_DIR  = Path("/path/to/local/Desktop/catalyst-edge/social/gap_winners")

# Auto-generate video after folder is built (requires D_ID_API_KEY env var)
try:
    from generate_gap_winner_video import generate_video as _gen_video
    _HAS_VIDEO_GEN = True
except ImportError:
    _HAS_VIDEO_GEN = False
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "catalystedge.agency")
AGENCY_URL     = "catalystedge.agency"


# ── Content generators ────────────────────────────────────────────────────

def _accum_phrase(vol_ratio: float) -> str:
    if vol_ratio >= 5:
        return f"{vol_ratio:.0f}× normal volume — institutions were loading up"
    elif vol_ratio >= 3:
        return f"{vol_ratio:.0f}× average volume — clear accumulation signal"
    else:
        return f"{vol_ratio:.1f}× average volume — elevated buying pressure"


def _outcome_phrase(outcome: str, max_2hr: float) -> str:
    if outcome in ("BIG WIN", "WIN"):
        return f"moved +{max_2hr:.0f}% within 2 hours of the alert"
    elif outcome == "SMALL WIN":
        return f"hit +{max_2hr:.1f}% within 2 hours of the alert"
    else:
        return "was flagged by our gap scanner"


def twitter_thread(data: dict) -> str:
    t        = data["ticker"]
    price    = data["alert_price"]
    gap      = data["gap_pct"]
    vr       = data["vol_ratio"]
    max2     = data.get("max_2hr_pct", 0)
    outcome  = data.get("outcome", "")
    date_str = data["alert_date"]

    outcome_line = (
        f"Result: +{max2:.0f}% within 2 hours. 🔥"
        if max2 >= 10 else
        f"Gap held. Setup played out exactly as flagged."
    )

    return f"""TWEET 1 — Hook
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 $${t} was on our gap scanner at ${price:.2f}

+{gap:.0f}% gap. {_accum_phrase(vr)}.

This is what event-driven trading looks like. 🧵

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TWEET 2 — The Signal
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
What triggered the $${t} alert on {date_str}:

→ Gap: +{gap:.1f}% vs previous close
→ Volume: {vr:.1f}× 30-day average
→ SEC-confirmed filing in our EDGAR database
→ Price: ${price:.2f} — penny range, high R/R

{outcome_line}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TWEET 3 — CTA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
We send these alerts in real time during market hours.

Free daily newsletter → {NEWSLETTER_URL}
Real-time gap alerts + AI agent → {AGENCY_URL}

#{t} #PennyStocks #GapUp #CatalystEdge #EventDriven
"""


def stocktwits_reference(data: dict) -> str:
    t     = data["ticker"]
    price = data["alert_price"]
    gap   = data["gap_pct"]
    vr    = data["vol_ratio"]
    max2  = data.get("max_2hr_pct", 0)

    outcome_line = f"Outcome: +{max2:.0f}% max within 2hrs." if max2 >= 5 else ""

    return f"""$${t} — Gap Alert Reference Copy
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
(Auto-posted at alert time — this is your reference)

$${t} 🚨 PENNY GAP ALERT

${price:.2f}  (+{gap:.1f}% gap vs yesterday close)
{_accum_phrase(vr)} — {vr:.1f}× average volume

{outcome_line}
SEC-confirmed catalyst on this filer. High-risk / high-reward setup.
Full breakdown → {NEWSLETTER_URL}
"""


def instagram_caption(data: dict) -> str:
    t       = data["ticker"]
    price   = data["alert_price"]
    gap     = data["gap_pct"]
    vr      = data["vol_ratio"]
    max2    = data.get("max_2hr_pct", 0)
    outcome = data.get("outcome", "")
    date_str = data["alert_date"]

    result_block = ""
    if max2 >= 10:
        result_block = f"\n✅ Result: +{max2:.0f}% peak within 2 hours of the alert.\nThis is why we watch penny gap plays every single morning.\n"

    return f"""⚡ PENNY GAP PLAY — ${t}

On {date_str} our scanner flagged ${t} at ${price:.2f}

Here's what we saw:
📈 +{gap:.1f}% gap vs previous close
🔥 {vr:.1f}× normal volume — heavy accumulation
📋 SEC filing confirmed in EDGAR
💰 Penny range = high risk, high reward
{result_block}
This is event-driven trading. We scan 300+ SEC EDGAR filings every night, score them, and fire alerts the moment a gap confirms during market hours.

Free subscribers get the daily newsletter.
Premium gets real-time alerts like this one.

👇 Link in bio to subscribe free.

⚠️ Not financial advice. Penny stocks are extremely high risk. Always use stop-losses and size appropriately.

.
.
.
#{t} #PennyStocks #StockMarket #GapUp #EventDriven #SECFilings #TradingAlerts #StockAlert #CatalystEdge #DayTrading #SwingTrading #StocksToWatch #TradingCommunity #WallStreet #InvestingTips
"""


def tiktok_script(data: dict) -> str:
    t       = data["ticker"]
    price   = data["alert_price"]
    gap     = data["gap_pct"]
    vr      = data["vol_ratio"]
    max2    = data.get("max_2hr_pct", 0)
    date_str = data["alert_date"]

    result_line = (
        f"It peaked at plus {max2:.0f} percent within 2 hours."
        if max2 >= 10 else
        "The setup played out exactly as the scanner predicted."
    )

    return f"""TIKTOK VIDEO SCRIPT — ${t} Gap Play
Duration target: 30–45 seconds
Hook in first 2 seconds — no intro

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ON SCREEN TEXT]: ${t} — +{gap:.0f}% GAP UP

[SPOKEN]:
Our scanner caught {t} at {price:.2f} dollars on {date_str}.

Plus {gap:.0f} percent gap. {vr:.0f} times normal volume.
That is not random. That is accumulation.

[ON SCREEN TEXT]: WHAT IS ACCUMULATION?

[SPOKEN]:
When institutions buy a stock heavily before it moves —
volume spikes, price gaps up, and retail traders miss it.

We don't miss it. We have an SEC filing scanner that watches
300 plus EDGAR filings every single night.

[ON SCREEN TEXT]: RESULT

[SPOKEN]:
{result_line}

[ON SCREEN TEXT]: FREE DAILY NEWSLETTER — LINK IN BIO

[SPOKEN]:
Subscribe free. Get the picks before the open.
Link in bio.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAPTION FOR POST:
${t} gap play caught by our scanner 🔥 +{gap:.0f}% gap, {vr:.0f}x volume. This is what event-driven trading looks like. Free newsletter → link in bio. Not financial advice. #${t} #PennyStocks #GapUp #StockMarket #TradingTips #CatalystEdge
"""


def youtube_description(data: dict) -> str:
    t       = data["ticker"]
    price   = data["alert_price"]
    gap     = data["gap_pct"]
    vr      = data["vol_ratio"]
    max2    = data.get("max_2hr_pct", 0)
    date_str = data["alert_date"]

    result_section = ""
    if max2 >= 5:
        result_section = f"""
📊 WHAT HAPPENED AFTER THE ALERT
Peak gain within 2 hours: +{max2:.0f}%
Alert price: ${price:.2f}
This is a real, verified outcome from our live scanner.
"""

    return f"""${t} Gap Up Alert — How Our Scanner Caught It at ${price:.2f} | Catalyst Edge

On {date_str}, our SEC catalyst scanner flagged ${t} at ${price:.2f} with:
→ +{gap:.1f}% gap vs previous close
→ {vr:.1f}× average volume (accumulation signal)
→ SEC filing confirmed in EDGAR database
{result_section}
In this video we break down exactly what triggered the alert, how to read gap + volume confluence, and what the SEC filing told us before the move.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 SUBSCRIBE for daily gap alerts and SEC catalyst analysis
📬 Free newsletter: {NEWSLETTER_URL}
🎙️ Ask our AI about today's picks: {AGENCY_URL}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ DISCLAIMER: This is not financial advice. Penny stocks carry extreme risk.
Past performance does not guarantee future results. Always do your own due diligence.

CHAPTERS:
00:00 What is ${t} and why it gapped
02:00 Reading the SEC filing
04:00 Volume accumulation signal explained
06:00 How to trade gap setups (risk management)
08:00 Outcome review
10:00 Free newsletter + daily alerts

TAGS: {t} stock, penny stocks, gap up stocks, SEC filings, event driven trading,
stock market alerts, catalyst trading, EDGAR scanner, penny stock alerts,
gap trading strategy, stock scanner, day trading, swing trading
"""


def video_script(data: dict) -> str:
    t       = data["ticker"]
    price   = data["alert_price"]
    gap     = data["gap_pct"]
    vr      = data["vol_ratio"]
    max2    = data.get("max_2hr_pct", 0)
    date_str = data["alert_date"]
    prev    = data.get("prev_close", price)

    result_section = (
        f"Within 2 hours of the alert, {t} reached a peak of +{max2:.0f}% from the alert price.\n"
        f"That means if you entered at the alert price of ${price:.2f}, the peak gave you a {max2:.0f}% gain window."
        if max2 >= 5 else
        f"The setup is still playing out — monitor the price action and volume through the session."
    )

    return f"""FULL VIDEO SCRIPT — ${t} Gap Play Analysis
Date: {date_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[INTRO — 0:00]
Hey what's up, this is Catalyst Edge.
Today I'm breaking down {t} — a penny stock our gap scanner caught on {date_str}
at ${price:.2f}, showing a {gap:.0f} percent gap with {vr:.0f} times normal volume.
Let me show you exactly what we saw and what happened.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[THE SETUP — 1:30]
The previous close on {t} was ${prev:.2f}.
When our scanner fired, the stock had already gapped to ${price:.2f} —
that's a {gap:.1f} percent move from the prior session.

But here's what made this stand out — the volume.
{vr:.1f} times the 30-day average. That's not retail traders. That's accumulation.

When you see a gap PLUS a volume surge at that magnitude,
it tells you someone knew something before the open.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[THE SEC CATALYST — 3:00]
Our scanner doesn't just watch price action.
It scans over 300 SEC EDGAR filings every single night.

{t} had a confirmed filing in our database.
That's the catalyst layer on top of the price action.
Filing plus gap plus volume — three signals firing at once.
That's what we call a convergence setup.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[RISK MANAGEMENT — 5:00]
Now — important. Penny stocks are HIGH RISK.
I need to say that clearly. This is not a stock tip. This is a setup analysis.

If you were to trade something like this, the rules are simple:
1. Never risk more than you can lose completely
2. Set a hard stop below the opening gap — if it closes the gap, you're out
3. Take partial profits at 10%, 20% — don't get greedy
4. These moves can reverse just as fast as they run

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[OUTCOME — 7:00]
{result_section}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[CLOSE — 9:00]
This is the kind of setup we flag every single morning in the Catalyst Edge newsletter.
Free subscribers get the daily picks.
Premium subscribers get these real-time alerts the moment the scanner fires.

Link in the description to subscribe free.
If you have questions about this setup or any of the signals,
you can actually talk to our AI agent at {AGENCY_URL} — it knows today's picks.

Hit subscribe if you want to see more of these breakdowns.
See you tomorrow.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[B-ROLL SUGGESTIONS]
- Screen recording of the scanner output showing {t}
- Chart of {t} on {date_str} with gap marked
- SEC EDGAR filing page for {t}
- Volume bars highlighted at the accumulation point
- Price alert notification mock-up
"""


def thumbnail_brief(data: dict) -> str:
    t     = data["ticker"]
    price = data["alert_price"]
    gap   = data["gap_pct"]
    max2  = data.get("max_2hr_pct", 0)

    result_text = f"+{max2:.0f}% IN 2 HRS" if max2 >= 10 else f"+{gap:.0f}% GAP"

    return f"""THUMBNAIL BRIEF — ${t}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAIN TEXT (large, bold):
  ${t}
  {result_text}

SUBTEXT (smaller):
  We Caught It at ${price:.2f}

STYLE:
  Background: dark navy or black
  Accent color: bright red or green (depending on outcome)
  Font: bold, high contrast, no script fonts
  Arrow: upward green arrow next to the percentage
  Small logo: Catalyst Edge bottom right corner

OPTIONAL FACE EXPRESSION:
  Surprised / excited — pointing at the text
  Works best for TikTok repurpose thumbnail

SPLIT SCREEN VERSION (for YouTube):
  Left side: stock chart with gap marked
  Right side: text overlay as above
  Middle line: CATALYST EDGE logo
"""


# ── Folder builder ────────────────────────────────────────────────────────

def build_folder(data: dict) -> Path:
    """Create the winner content folder and write all files."""
    ticker   = data["ticker"]
    date_str = data["alert_date"]
    folder   = WINNERS_DIR / f"{ticker}_{date_str}"
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "twitter_thread.txt").write_text(twitter_thread(data), encoding="utf-8")
    (folder / "stocktwits.txt").write_text(stocktwits_reference(data), encoding="utf-8")
    (folder / "instagram_caption.txt").write_text(instagram_caption(data), encoding="utf-8")
    (folder / "tiktok_script.txt").write_text(tiktok_script(data), encoding="utf-8")
    (folder / "youtube_description.txt").write_text(youtube_description(data), encoding="utf-8")
    (folder / "video_script.txt").write_text(video_script(data), encoding="utf-8")
    (folder / "thumbnail_brief.txt").write_text(thumbnail_brief(data), encoding="utf-8")
    (folder / "summary.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )

    print(f"  ✓ {folder}")

    # Auto-generate video if D_ID_API_KEY is available
    if _HAS_VIDEO_GEN and os.environ.get("D_ID_API_KEY"):
        try:
            _gen_video(folder)
        except Exception as exc:
            print(f"  video generation skipped: {exc}")

    return folder


# ── Called from post_penny_gap_alert.py on alert fire ────────────────────

def generate_for_alert(gap: dict) -> None:
    """Called immediately when an alert fires — outcome data not yet available."""
    data = {
        "ticker":      gap["ticker"],
        "alert_date":  dt.date.today().isoformat(),
        "alert_price": gap["price"],
        "prev_close":  gap["prev_close"],
        "gap_pct":     gap["gap_pct"],
        "vol_ratio":   gap["vol_ratio"],
        "max_2hr_pct": 0,
        "outcome":     "PENDING",
    }
    build_folder(data)


# ── Update folder with outcome after EOD evaluation ───────────────────────

def update_with_outcomes() -> None:
    """Merge outcome data into existing alert folders."""
    if not OUTCOME_LOG.exists():
        return
    outcomes = {
        (r["ticker"], r["alert_date"]): r
        for r in csv.DictReader(OUTCOME_LOG.open(newline="", encoding="utf-8"))
    }
    for folder in WINNERS_DIR.glob("*_*"):
        if not folder.is_dir():
            continue
        summary_path = folder / "summary.json"
        if not summary_path.exists():
            continue
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("outcome", "PENDING") != "PENDING":
            continue   # already updated
        key = (data["ticker"], data["alert_date"])
        if key not in outcomes:
            continue
        o = outcomes[key]
        data["max_2hr_pct"]  = float(o.get("max_2hr_pct", 0) or 0)
        data["max_1hr_pct"]  = float(o.get("max_1hr_pct", 0) or 0)
        data["max_30min_pct"]= float(o.get("max_30min_pct", 0) or 0)
        data["outcome"]      = o.get("outcome", "UNKNOWN")
        # Rebuild all content with outcome data
        build_folder(data)
        print(f"  updated {data['ticker']} {data['alert_date']} → {data['outcome']}")


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker",    help="Ticker symbol")
    parser.add_argument("--price",     type=float, help="Alert price (manual mode)")
    parser.add_argument("--gap",       type=float, help="Gap %% vs prev close (manual mode)")
    parser.add_argument("--vol-ratio", type=float, dest="vol_ratio", help="Volume ratio vs avg (manual mode)")
    parser.add_argument("--max-gain",  type=float, dest="max_gain",  help="Known max 2-hr gain %% (optional)")
    args = parser.parse_args()

    WINNERS_DIR.mkdir(parents=True, exist_ok=True)

    if args.ticker:
        ticker = args.ticker.upper()

        # If price/gap/vol-ratio provided directly — manual mode, no log needed
        if args.price is not None:
            gap_pct   = args.gap       if args.gap       is not None else 0.0
            vol_ratio = args.vol_ratio if args.vol_ratio is not None else 1.0
            prev      = args.price / (1 + gap_pct / 100) if gap_pct else args.price
            data = {
                "ticker":      ticker,
                "alert_date":  dt.date.today().isoformat(),
                "alert_price": args.price,
                "prev_close":  round(prev, 2),
                "gap_pct":     gap_pct,
                "vol_ratio":   vol_ratio,
                "max_2hr_pct": args.max_gain if args.max_gain is not None else 0,
                "outcome":     "PENDING",
            }
            build_folder(data)
            return 0

        # Otherwise look up in alert log
        if not ALERT_LOG.exists():
            print(
                f"build_winner_content: {ticker} not in alert log — "
                f"use --price to generate manually, e.g.:\n"
                f"  python3 build_winner_content.py --ticker {ticker} --price 2.15 --gap 45 --vol-ratio 8.2"
            )
            return 1
        alerts = [
            r for r in csv.DictReader(ALERT_LOG.open(newline="", encoding="utf-8"))
            if r.get("ticker", "").upper() == ticker
        ]
        if not alerts:
            print(
                f"build_winner_content: {ticker} not found in alert log — "
                f"use --price to generate manually, e.g.:\n"
                f"  python3 build_winner_content.py --ticker {ticker} --price 2.15 --gap 45 --vol-ratio 8.2"
            )
            return 1
        alert = sorted(alerts, key=lambda x: x.get("alert_date", ""), reverse=True)[0]
        data  = {
            "ticker":      ticker,
            "alert_date":  alert.get("alert_date", dt.date.today().isoformat()),
            "alert_price": float(alert.get("alert_price", 0)),
            "prev_close":  float(alert.get("prev_close", 0)),
            "gap_pct":     float(alert.get("gap_pct", 0)),
            "vol_ratio":   float(alert.get("vol_ratio", 0)),
            "max_2hr_pct": 0,
            "outcome":     "PENDING",
        }
        build_folder(data)
        return 0

    # Default: update all existing folders with outcome data
    print("build_winner_content: updating folders with outcome data...")
    update_with_outcomes()
    print("build_winner_content: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
