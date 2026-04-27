#!/usr/bin/env python3
"""build_reddit_comments.py — Daily Reddit engagement comment generator.

Generates ready-to-copy comments for Reddit's daily discussion threads.
Strategy: Be genuinely helpful with real data. Never spam. Build karma first.

Target subreddits (all have daily discussion threads):
  - r/stocks          → "Daily Discussion" posted each morning
  - r/wallstreetbets  → "Daily Discussion Thread" posted each morning
  - r/investing       → "Daily General Discussion" (weekdays)
  - r/StockMarket     → "Daily Stock Market News and Discussion"
  - r/SecurityAnalysis → post directly (research-friendly)

Reddit karma building rules:
  1. NEVER post promo links until account has 100+ comment karma
  2. Comments must be genuinely helpful — actual data, not vague claims
  3. Reply to other comments before starting your own threads
  4. r/wallstreetbets culture: casual tone, specific tickers, confidence
  5. r/stocks / r/investing culture: analytical, sources cited, humble
  6. r/SecurityAnalysis: deep data, methodology, no hype

Karma milestones:
  0-50:   Only reply to others, no link in comments
  50-100: Can mention newsletter in context ("I track this in my newsletter")
  100+:   Can include link once per thread max

Saves to social/reddit_comments_{date}.txt for manual copy-paste.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
from pathlib import Path

ROOT        = Path(__file__).parent
SOCIAL_DIR  = ROOT / "social"
WIN_SOCIAL  = Path("/path/to/local/Desktop/catalyst-edge/social")
NEWSLETTER_URL = "catalystedge.agency"

# ── Data loaders ──────────────────────────────────────────────────────────────

def load_picks() -> dict:
    p = ROOT / "newsletter_picks.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def load_polymarket() -> dict | None:
    p = ROOT / "polymarket_signals.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        age_h = (dt.datetime.now(dt.timezone.utc) -
                 dt.datetime.fromisoformat(data.get("generated_at", "1970-01-01T00:00:00+00:00"))
                 ).total_seconds() / 3600
        if age_h > 36:
            return None
        sigs = [s for s in data.get("signals", []) if 10 <= s.get("probability", 0) <= 90]
        return min(sigs, key=lambda x: abs(x["probability"] - 50)) if sigs else None
    except Exception:
        return None


def get_catalyst_detail(ticker: str) -> dict:
    for fname in ["sec_clean_gappers.csv", "sec_clean_value.csv",
                  "sec_top_gappers.csv", "sec_top_value.csv"]:
        for row in read_csv(ROOT / fname):
            if row.get("ticker", "").upper() == ticker.upper():
                return row
    return {}


def signal_detail(ctx: dict) -> tuple[str, str]:
    """Return (short_label, detail_sentence)."""
    tags = (ctx.get("tags") or "").lower()
    form = ctx.get("form", "")
    tag_details = [
        ("fda_approval",         "FDA approval",         "FDA approval removes regulatory overhang — binary catalyst resolved."),
        ("fda_clearance",        "FDA clearance",        "FDA clearance is a major de-risking event for the stock."),
        ("definitive_agreement", "merger agreement",     "Definitive merger agreement typically locks in a deal premium."),
        ("contract_award",       "contract award",       "Contract award directly adds to backlog — quantifiable revenue event."),
        ("raises_guidance",      "raised guidance",      "Management raised guidance above consensus — strong demand signal."),
        ("record_revenue",       "record revenue",       "Record revenue quarter reported — fundamentals confirming the move."),
        ("earnings_beat",        "earnings beat",        "Beat estimates on both top and bottom line."),
        ("share_repurchase",     "buyback",              "Buyback authorization — management buying at current prices."),
        ("insider_buy",          "insider buying",       "Open-market insider buying at current prices — skin in the game."),
        ("special_dividend",     "special dividend",     "Special dividend announced — one-time capital return to shareholders."),
        ("patent",               "patent",               "Patent filing/grant — IP moat expansion with commercial implications."),
    ]
    for key, label, detail in tag_details:
        if key in tags:
            return label, detail
    form_map = {
        "8-K": ("8-K filing", "Material event disclosure filed — worth reading the actual 8-K."),
        "4":   ("Form 4",     "CEO/Director buying on the open market — not a routine transaction."),
        "SC 13D": ("13D activist", "Activist investor crossed 5% and disclosed intent — watch for pressure campaign."),
        "6-K": ("6-K filing", "Foreign private issuer disclosure — cross-border catalyst."),
    }
    return form_map.get(form, ("SEC filing", "SEC EDGAR catalyst filing — details in the filing text."))


def get_score(ctx: dict) -> str:
    for col in ["total_score", "gapper_score", "value_score", "moat_score"]:
        v = ctx.get(col, "")
        try:
            return f"{float(v):.1f}"
        except (ValueError, TypeError):
            pass
    return ""


# ── Comment builders ──────────────────────────────────────────────────────────

def build_wsb_comment(picks: dict, top5: list[str]) -> str:
    """r/wallstreetbets style: casual, confident, specific."""
    top_pick = picks.get("top_pick", top5[0] if top5 else "").upper()
    ctx = get_catalyst_detail(top_pick)
    label, detail = signal_detail(ctx)
    score = get_score(ctx)
    score_str = f" | Score {score}/10" if score else ""
    others = [f"${t}" for t in top5 if t != top_pick][:3]
    others_str = ", ".join(others) if others else ""

    pm = load_polymarket()
    pm_line = ""
    if pm:
        pm_line = f"\n\nPolymarket has {pm['probability']:.0f}% on \"{pm['title'][:60]}\" — {pm['impact']}. Worth factoring in."

    comment = f"""Ran my SEC EDGAR scanner this morning. Here's what stood out:

**${top_pick}** — {label}{score_str}

{detail}

The filing dropped early this morning on EDGAR. These catalyst plays typically move within 1-5 trading days of the filing.

Also watching: {others_str}{pm_line}

Not financial advice. Just sharing what the data shows."""
    return comment.strip()


def build_stocks_comment(picks: dict, top5: list[str]) -> str:
    """r/stocks style: analytical, data-backed, humble."""
    top_pick = picks.get("top_pick", top5[0] if top5 else "").upper()
    ctx = get_catalyst_detail(top_pick)
    label, detail = signal_detail(ctx)
    form = ctx.get("form", "SEC filing")
    score = get_score(ctx)
    total = int(picks.get("total_combined", 0) or 300)

    pm = load_polymarket()
    pm_line = ""
    if pm:
        pm_line = f"\n\n**Macro context:** Polymarket currently pricing {pm['probability']:.0f}% on \"{pm['title'][:60]}\" — {pm['impact']}."

    comment = f"""I run a daily scan of SEC EDGAR filings (8-Ks, Form 4s, Schedule 13Ds) looking for catalyst patterns. Today's top result from {total}+ filings:

**${top_pick}** ({form})
- Signal: {label}
- {detail}
{"- Score: " + score + "/10 across 8 signal layers" if score else ""}

These filings are public — the data is on EDGAR if you want to verify. The edge is in reading them before the market prices them in.{pm_line}

Happy to share the methodology if anyone's interested. DYOR."""
    return comment.strip()


def build_investing_comment(picks: dict, top5: list[str]) -> str:
    """r/investing style: educational, process-focused."""
    top_pick = picks.get("top_pick", top5[0] if top5 else "").upper()
    ctx = get_catalyst_detail(top_pick)
    label, detail = signal_detail(ctx)
    total = int(picks.get("total_combined", 0) or 300)

    comment = f"""Sharing my process for today as a discussion point:

I scan SEC EDGAR every morning for catalyst filings before the market opens — {total}+ filings sorted by signal strength. Today's highest-ranked pick was **${top_pick}** based on a **{label}** in the most recent filing.

Why SEC filings? They're required disclosures — executives can't lie in them. Material events (mergers, FDA decisions, guidance changes) have to be filed as 8-Ks within 4 business days. By the time news articles cover them, institutional traders have usually read the original filing.

The edge for retail: most people don't read the actual filings. They wait for the headline.

Anyone else using EDGAR data in their process?"""
    return comment.strip()


def build_security_analysis_post(picks: dict, top5: list[str]) -> str:
    """r/SecurityAnalysis: methodology-focused, data-rich, no hype."""
    today = dt.date.today().strftime("%B %-d, %Y")
    total = int(picks.get("total_combined", 0) or 300)

    pick_details = []
    for t in top5[:3]:
        ctx = get_catalyst_detail(t)
        label, _ = signal_detail(ctx)
        score = get_score(ctx)
        score_str = f" | Score: {score}/10" if score else ""
        pick_details.append(f"- **${t}**: {label}{score_str}")

    picks_text = "\n".join(pick_details)

    post = f"""**SEC Catalyst Screen — {today}**

Methodology post / open discussion.

I run a daily EDGAR screen that scores catalyst filings across 8 signal layers: filing type weight, insider activity, short interest, options flow, filing sentiment (NLP), macro context (Polymarket overlay), sector momentum, and multi-signal convergence.

Today's top outputs from {total}+ filings:

{picks_text}

**What I'm looking for:** filings where (a) the event is material but under-covered, (b) insider/institutional data corroborates the catalyst, and (c) macro context isn't headwind.

**Known limitations:**
- Same-day moves aren't guaranteed — typical catalyst play window is 1-5 days
- Small/micro cap filings have worse price data quality
- Filing sentiment NLP has ~15% error rate on complex 8-K language

Would be curious how others are approaching systematic EDGAR screening. Most tools (Bloomberg terminal etc.) have this built in but the raw EDGAR API is public.

Not investment advice."""
    return post.strip()


def build_stockmarket_comment(picks: dict, top5: list[str]) -> str:
    """r/StockMarket: market-discussion style, medium depth."""
    top_pick = picks.get("top_pick", top5[0] if top5 else "").upper()
    ctx = get_catalyst_detail(top_pick)
    label, detail = signal_detail(ctx)
    others = [f"${t}" for t in top5 if t != top_pick][:4]
    others_str = " / ".join(others)

    comment = f"""Daily EDGAR scan results for today's discussion:

**Top catalyst pick: ${top_pick}**
Signal: {label}
{detail}

Also flagged: {others_str}

All sourced from public SEC filings — 8-Ks, Form 4s, Schedule 13Ds. The filing hit EDGAR early this morning before market open.

What's everyone else watching today?"""
    return comment.strip()


# ── Strategy guide ────────────────────────────────────────────────────────────

def build_karma_strategy(today: dt.date) -> str:
    day_num = today.toordinal()

    # Rotate the tip of the day
    tips = [
        "Reply to 3 top-level comments before posting your own — this builds goodwill.",
        "Find a daily discussion thread and answer someone's question with real data.",
        "Look for posts about stocks that match your picks and add substantive data.",
        "Upvote quality analysis in your target subreddits — the algorithm notices participation.",
        "Post a question in r/stocks or r/investing asking about EDGAR screening — community loves teaching.",
        "Share a mini-analysis (no promotion) about one of today's picks using public data.",
        "React to breaking news posts with data from the actual SEC filing — adds credibility.",
    ]
    tip = tips[day_num % len(tips)]

    strategy = f"""
{'='*60}
REDDIT KARMA BUILDING STRATEGY
{'='*60}

Current phase: Build karma before direct promotion
Target: 100+ comment karma across target subreddits

TODAY'S TASK: {tip}

SUBREDDITS TO TARGET (in order of SEO + audience fit):
  1. r/stocks — 6.5M members, daily discussion thread
  2. r/wallstreetbets — 16M members, high-energy, trading-focused
  3. r/investing — 2.5M members, long-term, analytical
  4. r/StockMarket — 1.5M members, broad market discussion
  5. r/SecurityAnalysis — 500K members, deep analysis welcome

WHAT TO POST:
  - Data first, opinion second
  - Cite EDGAR.SEC.GOV as your source (public government data = credible)
  - Never say "this will moon" — say "the filing shows X, market hasn't priced it"
  - Keep it under 300 words in r/wsb, up to 800 in r/SecurityAnalysis

WHAT TO AVOID:
  - Never post your link in the same comment as your pick (shadow-banned)
  - Don't post identical text in multiple subreddits same day
  - Avoid r/investing for individual stock picks (moderators remove them)
  - Don't mention "newsletter" until karma > 50

HOW TO FIND DAILY THREADS:
  - r/stocks daily thread: Posted at market open, title "Daily Discussion..."
  - r/wsb daily thread: Posted by u/VisualMod each morning
  - r/investing: Posted M-F, title "Daily General Discussion"
{'='*60}
"""
    return strategy


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    today = dt.date.today()
    stamp = today.isoformat()

    picks = load_picks()
    if not picks:
        print("build_reddit_comments: no picks found — skipping")
        return 0

    top5 = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]
    if not top5:
        print("build_reddit_comments: no tickers — skipping")
        return 0

    print(f"build_reddit_comments: building comments for {top5}")

    sections = [
        f"CATALYST EDGE — REDDIT COMMENTS — {today.strftime('%B %-d, %Y')}",
        "=" * 60,
        "Copy the appropriate comment into the matching subreddit's daily discussion thread.",
        "Do NOT post all of them — pick ONE per day, rotate subreddits.",
        "",

        "─── r/wallstreetbets (Daily Discussion Thread) ───",
        build_wsb_comment(picks, top5),
        "",

        "─── r/stocks (Daily Discussion) ───",
        build_stocks_comment(picks, top5),
        "",

        "─── r/StockMarket (Daily Discussion) ───",
        build_stockmarket_comment(picks, top5),
        "",

        "─── r/investing (Daily General Discussion) ───",
        build_investing_comment(picks, top5),
        "",

        "─── r/SecurityAnalysis (can post as its own thread) ───",
        build_security_analysis_post(picks, top5),

        build_karma_strategy(today),
    ]

    output = "\n".join(sections)

    SOCIAL_DIR.mkdir(parents=True, exist_ok=True)
    out = SOCIAL_DIR / f"reddit_comments_{stamp}.txt"
    out.write_text(output, encoding="utf-8")
    print(f"  saved: {out}")

    try:
        WIN_SOCIAL.mkdir(parents=True, exist_ok=True)
        (WIN_SOCIAL / f"reddit_comments_{stamp}.txt").write_text(output, encoding="utf-8")
    except OSError:
        pass

    print(f"build_reddit_comments: done — {len(top5)} picks, 4 subreddit comments generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
