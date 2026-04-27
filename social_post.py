#!/usr/bin/env python3
"""Generate daily social media posts for Catalyst Edge newsletter.

Reads today's top picks from newsletter_picks.json and combined_priority.csv,
then generates Twitter/X (280 chars) and LinkedIn (500 chars) posts and saves
them to /home/operator/catalyst-edge/social/.

These are for manual copying until a Twitter API key is obtained.

Usage:
  python3 social_post.py
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
from pathlib import Path


ROOT = Path(__file__).parent
NEWSLETTER_PICKS = ROOT / "newsletter_picks.json"
COMBINED_PRIORITY = ROOT / "combined_priority.csv"
GAPPERS_CSV = ROOT / "sec_top_gappers.csv"
VALUE_CSV = ROOT / "sec_top_value.csv"

SOCIAL_DIR = Path(__file__).parent / "social"
# Also write to Windows-accessible social directory
WIN_SOCIAL_DIR = Path(__file__).parent / "social"
# Tickers list read by Node.js posting scripts
COMBINED_TICKERS_TXT = ROOT / "combined_priority_tickers.txt"

SCANNER_URL  = "https://catalystedgescanner.com"
SITE_URL     = "https://catalystedgescanner.com"
AGENCY_URL   = "https://www.catalystedge.agency/"
YOUTUBE_URL  = "https://www.youtube.com/@CatalystEdgePro"
X_HANDLE     = "@CatalystEdgePro"
IG_HANDLE    = "@yourhandle"
TT_HANDLE    = "@catalystedge"
TWITTER_MAX  = 280
LINKEDIN_MAX = 500


# ---------------------------------------------------------------------------
# Data readers
# ---------------------------------------------------------------------------

def load_newsletter_picks() -> dict:
    if not NEWSLETTER_PICKS.exists():
        return {}
    try:
        return json.loads(NEWSLETTER_PICKS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def get_top5_from_combined(n: int = 5) -> list[str]:
    rows = read_csv(COMBINED_PRIORITY)
    tickers: list[str] = []
    seen: set[str] = set()
    for row in rows:
        t = (row.get("ticker") or "").strip().upper()
        if t and t not in seen and not _is_derivative(t):
            tickers.append(t)
            seen.add(t)
        if len(tickers) >= n:
            break
    return tickers


def _is_derivative(ticker: str) -> bool:
    if "-" in ticker:
        return True
    if ticker.endswith(("WW", "WS", "WT")):
        return True
    if len(ticker) >= 5 and ticker.endswith("W"):
        return True
    return False


def get_catalyst_context(ticker: str) -> dict:
    """Return form, tags, gapper_score, value_score for a ticker from gappers/value CSVs."""
    for csv_path in [GAPPERS_CSV, VALUE_CSV]:
        rows = read_csv(csv_path)
        for row in rows:
            if (row.get("ticker") or "").strip().upper() == ticker.upper():
                return {
                    "form": row.get("form", ""),
                    "tags": row.get("tags", ""),
                    "gapper_score": row.get("gapper_score", ""),
                    "value_score": row.get("value_score", ""),
                    "price": row.get("price", ""),
                    "link": row.get("link", ""),
                }
    return {}


TAG_NARRATIVE: dict[str, str] = {
    "+fda approval": "received FDA approval",
    "+fda clearance": "received FDA clearance",
    "+definitive agreement": "announced a definitive merger/acquisition agreement",
    "+merger agreement": "entered into a merger agreement",
    "+contract award": "won a significant contract award",
    "+awarded contract": "won a significant contract award",
    "+raises guidance": "raised forward earnings/revenue guidance",
    "+record revenue": "reported record revenue",
    "+earnings beat": "beat Wall Street earnings estimates",
    "+share repurchase": "announced a share buyback program",
    "+buyback": "announced a share buyback program",
    "+insider_buy_p": "saw significant CEO/Director insider buying (Form 4)",
    "+patent": "filed or received a key patent",
    "+exclusive": "secured an exclusive agreement or license",
    "+recurring revenue": "highlighted recurring revenue strength",
    "+market share gains": "disclosed market share gains",
    "+cost reduction": "announced a significant cost reduction plan",
    "+schedule 13d": "attracted activist investor filing (Schedule 13D)",
    "+preliminary results": "disclosed preliminary financial results",
    "+business combination agreement": "announced a business combination agreement",
    "+share repurchase program": "launched a share repurchase program",
}

FORM_LABEL: dict[str, str] = {
    "8-K": "8-K event filing",
    "6-K": "6-K foreign private issuer filing",
    "4": "Form 4 insider purchase filing",
    "SC 13D": "Schedule 13D activist disclosure",
    "SC 13G": "Schedule 13G institutional filing",
    "S-3": "S-3 registration statement",
    "424B4": "424B4 prospectus",
}


def build_catalyst_narrative(ticker: str, ctx: dict) -> str:
    """Build a 1-sentence catalyst description for the ticker."""
    tags_raw = ctx.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(";") if t.strip()]
    form = ctx.get("form", "")

    for tag in tags:
        for key, narrative in TAG_NARRATIVE.items():
            if tag.lower().startswith(key.lower()):
                form_ctx = FORM_LABEL.get(form, form or "SEC filing")
                return f"${ticker} {narrative} per {form_ctx}."

    if form:
        form_ctx = FORM_LABEL.get(form, form)
        return f"${ticker} filed a fresh {form_ctx} — potential catalyst signal."

    return f"${ticker} shows a high-conviction catalyst pattern from SEC EDGAR data."


# ---------------------------------------------------------------------------
# Reply prompt generator
# ---------------------------------------------------------------------------

# ── Fintwit target accounts ───────────────────────────────────────────────────
# Organized by focus area — reply to posts that match each account's specialty

_REPLY_TARGETS = [
    # High-follower fintwit accounts (reply for maximum reach)
    ("@unusual_whales",    "options flow / dark pool data",         "options"),
    ("@StockMKTNewz",      "breaking market news",                  "news"),
    ("@unusual_activity_", "unusual options activity",              "options"),
    ("@open_insider",      "Form 4 insider tracking",               "insider"),
    ("@OptionsHawk",       "live options flow alerts",              "options"),
    ("@SqueezeMetrics",    "short squeeze / GEX analysis",          "squeeze"),
    ("@10kdiver",          "SEC filing and earnings deep dives",     "filings"),
    ("@iancassel",         "micro-cap / small-cap research",        "smallcap"),
    ("@investorslive",     "day trading / momentum plays",          "momentum"),
    ("@RedDogT3",          "technical analysis / tape reading",     "technicals"),
    ("@Charlie_Bilello",   "macro data / market history",           "macro"),
    ("@neilcataldi",       "biotech SEC catalyst / PDUFA plays",    "biotech"),
    ("@marketplunger",     "momentum and breakout trades",          "momentum"),
    ("@ShortSqueezeCom",   "short squeeze tracking",                "squeeze"),
    ("@wallstmemes",       "viral finance content / retail sentiment", "retail"),
]

# Account-specific reply templates by their specialty
_REPLY_TEMPLATES = {
    "options": [
        "Our SEC scanner flagged ${ticker} this morning — ${signal}. "
        "Options flow should be interesting to watch today. "
        "We track 300+ EDGAR filings daily: catalystedgescanner.com",

        "The EDGAR filing on ${ticker} hit before the open — ${signal}. "
        "Curious if you're seeing unusual flow there. "
        "Free catalyst scan: catalystedgescanner.com",
    ],
    "insider": [
        "Form 4 on ${ticker} showed open-market buys at ${price} this morning. "
        "Top-ranked across {scanned} filings in our scan. "
        "Full breakdown: catalystedgescanner.com",

        "Matched your radar — ${ticker} Form 4 was in our scan too. "
        "${signal}. Score {score}/10 across our signal layers. "
        "catalystedgescanner.com",
    ],
    "squeeze": [
        "We have ${ticker} in COILED stage in our squeeze model — SI elevated, "
        "catalyst in the 8-K, DTC rising. Flagged at 4am. "
        "Free scan: catalystedgescanner.com",

        "SEC filing + elevated short interest on ${ticker} today. "
        "Classic catalyst-into-squeeze setup. {scanned} filings scanned this morning. "
        "catalystedgescanner.com",
    ],
    "filings": [
        "Scanned {scanned} EDGAR filings this morning. ${ticker} topped our list — "
        "${signal}. Full scoring breakdown in today's free issue: catalystedgescanner.com",

        "The ${ticker} filing went live on EDGAR at 6am — ${signal}. "
        "We rank these by catalyst strength across 8 layers. "
        "catalystedgescanner.com",
    ],
    "smallcap": [
        "Found ${ticker} in today's micro-cap EDGAR scan — ${signal}. "
        "Score {score}/10. These are the plays the terminals miss at open. "
        "Free daily: catalystedgescanner.com",

        "Our scanner picked up ${ticker} pre-market — ${signal}. "
        "Small-cap catalyst before the crowd notices. "
        "catalystedgescanner.com",
    ],
    "momentum": [
        "Momentum setup on ${ticker} backed by SEC catalyst — ${signal}. "
        "We flagged it from the EDGAR feed this morning. "
        "Free picks: catalystedgescanner.com",

        "${ticker} showed up in our 4am EDGAR scan — ${signal}. "
        "Could be the catalyst behind today's move. "
        "catalystedgescanner.com",
    ],
    "news": [
        "That news ties to the 8-K filed this morning — ${signal}. "
        "We had ${ticker} in our pre-market scan before the headline. "
        "catalystedgescanner.com",

        "SEC filing dropped before the news — ${ticker}, ${signal}. "
        "EDGAR almost always files before the press release. "
        "Free daily scan: catalystedgescanner.com",
    ],
    "macro": [
        "Interesting macro angle — Polymarket has {pm_prob}% on \"{pm_title}\". "
        "That's moving our ${ticker} play today ({signal}). "
        "catalystedgescanner.com",

        "Combining macro with EDGAR today: ${ticker} catalyst + "
        "Polymarket at {pm_prob}% on \"{pm_title}\". "
        "Free breakdown: catalystedgescanner.com",
    ],
    "biotech": [
        "PDUFA / FDA filing on ${ticker} hit EDGAR this morning — ${signal}. "
        "Flagged it in our 4am scan across {scanned} biotech filings. "
        "catalystedgescanner.com",

        "Biotech 8-K on ${ticker}: ${signal}. "
        "Binary catalyst with clean setup. Score {score}/10 in our model. "
        "catalystedgescanner.com",
    ],
    "technicals": [
        "Technical setup on ${ticker} has fundamental backing — "
        "${signal} filed this morning. EDGAR + chart alignment. "
        "catalystedgescanner.com",

        "The breakout on ${ticker} might be SEC-catalyst driven — "
        "${signal}. We flagged it pre-market from the EDGAR feed. "
        "catalystedgescanner.com",
    ],
    "retail": [
        "WSB is going to find this one eventually — ${ticker}, "
        "${signal}, {scanned} filings scanned this morning. "
        "catalystedgescanner.com",

        "Reading SEC filings before retail wakes up. "
        "${ticker} top pick today — ${signal}. "
        "Free daily: catalystedgescanner.com",
    ],
}

# Default fallback template
_DEFAULT_REPLY = (
    "Ran {scanned} EDGAR filings this morning. ${ticker} came out on top — "
    "{catalyst}. Free daily breakdown: catalystedgescanner.com"
)

# ── Daily follow list ─────────────────────────────────────────────────────────
# Tiered by follower count — follow 20/day, rotate through the list

_FOLLOW_TIER1 = [  # 100k+ followers — reply for exposure, don't expect follow-back
    "@unusual_whales", "@StockMKTNewz", "@CNBC", "@MarketWatch",
    "@WSJ", "@business", "@Forbes", "@TheStreet",
]

_FOLLOW_TIER2 = [  # 10k-100k — high follow-back rate, core fintwit community
    "@open_insider", "@OptionsHawk", "@SqueezeMetrics", "@10kdiver",
    "@iancassel", "@neilcataldi", "@investorslive", "@RedDogT3",
    "@Charlie_Bilello", "@marketplunger", "@ShortSqueezeCom",
    "@MikeSPD", "@TraderStewie", "@JasonBondPicks", "@TradingwithLance",
    "@Option_Guru", "@OddStatsTrader", "@GrowthStockWire",
    "@HedgelyFunds", "@SECFilingAlerts", "@EDGAROnline",
]

_FOLLOW_TIER3 = [  # 1k-10k — high engagement, niche fintwit, likely to follow back
    "@SEC_Insider", "@secfilingsbot", "@EdgarFilingsBot",
    "@CatalystTrader", "@FormFourFilings", "@InsiderFinance_",
    "@StockCatalysts", "@BigtechBear", "@FDATracker",
    "@clinicalstage", "@SECTracker", "@InsiderAlert_",
]


def _load_polymarket_signal() -> dict | None:
    """Load top Polymarket signal if fresh (< 36h old)."""
    import json as _json
    p = ROOT / "polymarket_signals.json"
    if not p.exists():
        return None
    try:
        data = _json.loads(p.read_text(encoding="utf-8"))
        generated = data.get("generated_at", "")
        if generated:
            age_h = (dt.datetime.now(dt.timezone.utc) -
                     dt.datetime.fromisoformat(generated)).total_seconds() / 3600
            if age_h > 36:
                return None
        sigs = [s for s in data.get("signals", []) if 10 <= s.get("probability", 0) <= 90]
        return min(sigs, key=lambda x: abs(x["probability"] - 50)) if sigs else None
    except Exception:
        return None


def build_reply_prompts(picks: dict, squeeze_rows: list, top5: list[str]) -> str:
    """Generate 5 ready-to-copy reply prompts targeting key fintwit accounts."""
    today    = dt.date.today()
    top_pick = (picks.get("top_pick") or (top5[0] if top5 else "N/A")).upper()
    scanned  = int(picks.get("total_combined", 0) or 300)
    price    = ""

    # Get price and score
    score_str = ""
    if COMBINED_PRIORITY.exists():
        try:
            with COMBINED_PRIORITY.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("ticker", "").upper() == top_pick:
                        price = row.get("price", "")
                        break
        except Exception:
            pass

    # Build catalyst context for top pick
    ctx = {}
    for csv_path in [GAPPERS_CSV, VALUE_CSV]:
        if csv_path.exists():
            try:
                with csv_path.open(newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if row.get("ticker", "").upper() == top_pick:
                            ctx = row
                            break
            except Exception:
                pass
            if ctx:
                break

    catalyst  = build_catalyst_narrative(top_pick, ctx) if ctx else f"${top_pick} flagged via SEC catalyst scan"
    for col in ["total_score", "gapper_score", "value_score"]:
        try:
            v = float(ctx.get(col, ""))
            score_str = f"{v:.1f}"
            break
        except (ValueError, TypeError):
            pass

    # Short signal description
    tags = (ctx.get("tags") or "").lower()
    tag_map = [
        ("fda_approval", "FDA approval"), ("merger_agreement", "merger agreement"),
        ("contract_award", "contract award"), ("raises_guidance", "raised guidance"),
        ("record_revenue", "record revenue"), ("earnings_beat", "earnings beat"),
        ("share_repurchase", "buyback"), ("insider_buy", "insider buying"),
        ("special_dividend", "special dividend"), ("patent", "patent filing"),
    ]
    signal = next((desc for key, desc in tag_map if key in tags), None)
    if not signal:
        form_map = {"8-K": "8-K event filing", "4": "Form 4 insider buy",
                    "SC 13D": "activist 13D"}
        signal = form_map.get(ctx.get("form", ""), "SEC catalyst filing")

    # Squeeze tickers
    coiled = [r.get("ticker", "").upper() for r in squeeze_rows
              if r.get("stage") in ("COILED", "IGNITION")][:2]
    squeeze_ticker = coiled[0] if coiled else top_pick

    pm = _load_polymarket_signal()
    pm_prob  = f"{pm['probability']:.0f}" if pm else "50"
    pm_title = (pm["title"][:50] + "...") if pm and len(pm.get("title","")) > 50 else (pm["title"] if pm else "market direction")

    # Header
    lines = [
        f"CATALYST EDGE — DAILY REPLY PROMPTS — {today.strftime('%B %-d, %Y')}",
        "=" * 60,
        "Reply within 30 min of their post for maximum reach.",
        "NEVER copy-paste identical text — always vary slightly.",
        "",
    ]

    if pm:
        lines += [
            f"TODAY'S MACRO HOOK (use in macro/Fed/sector replies):",
            f"  Polymarket: {pm_prob}% on \"{pm['title'][:55]}\" — {pm['impact']}.",
            "",
        ]

    # Pick 5 targets + their specialty-matched templates
    # Rotate daily so we hit different accounts each day
    all_targets = _REPLY_TARGETS
    start = today.toordinal() % len(all_targets)
    daily_targets = (all_targets[start:] + all_targets[:start])[:5]

    for handle, focus, specialty in daily_targets:
        templates = _REPLY_TEMPLATES.get(specialty, [_DEFAULT_REPLY])
        # Rotate template within specialty by day
        tmpl = templates[today.toordinal() % len(templates)]

        ticker = squeeze_ticker if specialty == "squeeze" else top_pick

        text = (tmpl
            .replace("${ticker}", ticker)
            .replace("${signal}", signal)
            .replace("${price}", price if price else "current price")
            .replace("{scanned}", str(scanned))
            .replace("{score}", score_str if score_str else "8.5")
            .replace("{catalyst}", catalyst)
            .replace("{pm_prob}", pm_prob)
            .replace("{pm_title}", pm_title)
        )

        lines += [
            f"─── {handle} ({focus}) ───",
            text,
            "",
        ]

    # Daily follow list
    lines += build_follow_list(today)

    lines += [
        "=" * 60,
        "ENGAGEMENT RULES:",
        "1. Reply to their most recent post (check their profile first).",
        "2. If they just posted about a stock you cover — lead with their ticker.",
        "3. Don't reply twice to the same account in one day.",
        "4. Pin a reply to your most-performing alert tweet when a pick moves 5%+.",
    ]

    return "\n".join(lines)


def build_follow_list(today: dt.date) -> list[str]:
    """Generate a daily follow list of 20 fintwit accounts, rotating through tiers."""
    day = today.toordinal()

    # Pick 5 from T1 (rotating), 10 from T2 (rotating), 5 from T3 (rotating)
    t1 = (_FOLLOW_TIER1 * 4)[day % len(_FOLLOW_TIER1):][:5]
    t2 = (_FOLLOW_TIER2 * 4)[day % len(_FOLLOW_TIER2):][:10]
    t3 = (_FOLLOW_TIER3 * 4)[day % len(_FOLLOW_TIER3):][:5]

    lines = [
        "=" * 60,
        f"DAILY FOLLOW LIST — {today.strftime('%b %-d')} (follow all 20 today)",
        "",
        "HIGH-REACH (reply to these for exposure):",
        "  " + "  ".join(t1),
        "",
        "CORE FINTWIT (likely follow-back, high engagement):",
        "  " + "  ".join(t2[:5]),
        "  " + "  ".join(t2[5:]),
        "",
        "NICHE SEC/CATALYST (very targeted, active in our space):",
        "  " + "  ".join(t3),
        "",
        "TIP: After following, immediately reply to their latest post with",
        "     something genuinely useful — not promotional. This triggers",
        "     notifications and dramatically increases follow-back rate.",
        "",
    ]
    return lines


# ---------------------------------------------------------------------------
# Post generators
# ---------------------------------------------------------------------------

def build_twitter_post(date_str: str, top_pick: str, top5: list[str]) -> str:
    """Build a Twitter/X post <= 280 chars."""
    watchers = [f"${t}" for t in top5 if t != top_pick][:4]
    watching_str = " ".join(watchers)

    base = (
        f"⚡ Catalyst Edge — {date_str}\n"
        f"Top Pick: ${top_pick}\n"
        f"Also watching: {watching_str}\n"
        f"🎙️ Talk to Catalyst AI → catalystedge.agency\n"
        f"#SEC #Catalyst #Trading\n"
        f"{SCANNER_URL}"
    )

    if len(base) <= TWITTER_MAX:
        return base

    # Trim watchers to fit
    for n in range(len(watchers) - 1, -1, -1):
        watching_str = " ".join(watchers[:n])
        candidate = (
            f"⚡ Catalyst Edge — {date_str}\n"
            f"Top Pick: ${top_pick}\n"
            f"Also watching: {watching_str}\n"
            f"🎙️ Talk to Catalyst AI → catalystedge.agency\n"
            f"#SEC #Catalyst #Trading\n"
            f"{SITE_URL}"
        )
        if len(candidate) <= TWITTER_MAX:
            return candidate

    # Minimal fallback
    return (
        f"⚡ Catalyst Edge — {date_str}\n"
        f"Top Pick: ${top_pick}\n"
        f"🎙️ Talk to Catalyst AI → catalystedge.agency\n"
        f"#SEC #Catalyst #Trading\n"
        f"{SCANNER_URL}"
    )[:TWITTER_MAX]


def build_instagram_caption(date_str: str, top_pick: str, top5: list[str]) -> str:
    """Build an Instagram caption with emojis and hashtags."""
    ctx = get_catalyst_context(top_pick)
    narrative = build_catalyst_narrative(top_pick, ctx)

    # Emoji per position
    emojis = ["🔴", "💎", "🏰", "📈", "📊"]
    ticker_lines = "\n".join(
        f"{emojis[i] if i < len(emojis) else '📌'} ${t}"
        for i, t in enumerate(top5)
    )

    caption = (
        f"⚡ Today's Top SEC Catalyst Plays — {date_str}\n"
        f"\n"
        f"{ticker_lines}\n"
        f"\n"
        f"{narrative}\n"
        f"\n"
        f"All picks sourced from live SEC EDGAR filings — 8-Ks, Form 4s, Schedule 13Ds.\n"
        f"Full breakdown: catalystedgescanner.com\n"
        f"🎙️ Talk to Catalyst AI → catalystedge.agency\n"
        f"\n"
        f"#SECFilings #StockCatalyst #Trading #Investing #Finance "
        f"#Stocks #DayTrading #SwingTrading #Catalyst #8K #Form4"
    )
    return caption


def build_linkedin_post(date_str: str, top_pick: str, top5: list[str]) -> str:
    """Build a LinkedIn post <= 500 chars with more context."""
    ctx = get_catalyst_context(top_pick)
    narrative = build_catalyst_narrative(top_pick, ctx)
    gapper_score = ctx.get("gapper_score", "")
    form = ctx.get("form", "")

    score_line = ""
    if gapper_score:
        score_line = f"Gapper Score: {gapper_score}/20+ | Form: {form}\n"

    watchers = [f"${t}" for t in top5 if t != top_pick][:4]
    watching_str = " ".join(watchers)

    post = (
        f"⚡ Catalyst Edge Daily — {date_str}\n\n"
        f"Top Catalyst Pick: ${top_pick}\n"
        f"{narrative}\n"
        f"{score_line}\n"
        f"Also on the radar: {watching_str}\n\n"
        f"All picks sourced from live SEC EDGAR filings — "
        f"8-Ks, Form 4s, Schedule 13Ds — scored and ranked daily.\n\n"
        f"🎙️ Talk to Catalyst AI → {AGENCY_URL}\n"
        f"🖥️ Live scanner: {SCANNER_URL}\n"
        f"#SECFilings #StockCatalyst #Trading #InvestmentResearch"
    )

    if len(post) <= LINKEDIN_MAX:
        return post

    # Shorten narrative
    if len(narrative) > 80:
        narrative = narrative[:77] + "..."

    post = (
        f"⚡ Catalyst Edge — {date_str}\n\n"
        f"Top Pick: ${top_pick}\n"
        f"{narrative}\n\n"
        f"Also watching: {watching_str}\n\n"
        f"🎙️ Talk to Catalyst AI → {AGENCY_URL}\n"
        f"🖥️ Scanner: {SCANNER_URL}\n"
        f"#SECFilings #Catalyst #Trading"
    )
    return post[:LINKEDIN_MAX]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    today = dt.date.today()
    date_str = today.isoformat()

    # Load picks data
    picks = load_newsletter_picks()
    top_pick = (picks.get("top_pick") or "").strip().upper()

    # Get top 5 from combined_priority (most authoritative sorted list)
    top5 = get_top5_from_combined(5)

    if not top_pick and top5:
        top_pick = top5[0]
    elif not top_pick:
        print("ERROR: No top pick found in newsletter_picks.json and combined_priority.csv is empty")
        return 1

    # Ensure top_pick is in top5 list
    if top_pick not in top5:
        top5 = [top_pick] + top5[:4]
    elif top5[0] != top_pick:
        top5 = [top_pick] + [t for t in top5 if t != top_pick][:4]

    # Build posts
    twitter_post = build_twitter_post(date_str, top_pick, top5)
    linkedin_post = build_linkedin_post(date_str, top_pick, top5)
    instagram_caption = build_instagram_caption(date_str, top_pick, top5)

    # Ensure output directories exist
    SOCIAL_DIR.mkdir(parents=True, exist_ok=True)
    WIN_SOCIAL_DIR.mkdir(parents=True, exist_ok=True)

    # Save Twitter post (WSL social dir + Windows social dir)
    twitter_file = SOCIAL_DIR / f"twitter_post_{date_str}.txt"
    twitter_file.write_text(twitter_post + "\n", encoding="utf-8")
    win_twitter_file = WIN_SOCIAL_DIR / f"twitter_post_{date_str}.txt"
    try:
        win_twitter_file.write_text(twitter_post + "\n", encoding="utf-8")
    except OSError:
        pass

    # Save LinkedIn post
    linkedin_file = SOCIAL_DIR / f"linkedin_post_{date_str}.txt"
    linkedin_file.write_text(linkedin_post + "\n", encoding="utf-8")
    win_linkedin_file = WIN_SOCIAL_DIR / f"linkedin_post_{date_str}.txt"
    try:
        win_linkedin_file.write_text(linkedin_post + "\n", encoding="utf-8")
    except OSError:
        pass

    # Save Instagram caption (WSL social dir + Windows social dir)
    instagram_caption_file = SOCIAL_DIR / f"instagram_caption_{date_str}.txt"
    instagram_caption_file.write_text(instagram_caption + "\n", encoding="utf-8")
    win_ig_caption_file = WIN_SOCIAL_DIR / f"instagram_caption_{date_str}.txt"
    try:
        win_ig_caption_file.write_text(instagram_caption + "\n", encoding="utf-8")
    except OSError:
        pass

    # Save reply prompts + daily follow list
    squeeze_rows = read_csv(ROOT / "squeeze_candidates.csv")
    reply_prompts = build_reply_prompts(picks, squeeze_rows, top5)
    reply_file = SOCIAL_DIR / f"reply_prompts_{date_str}.txt"
    reply_file.write_text(reply_prompts + "\n", encoding="utf-8")
    win_reply_file = WIN_SOCIAL_DIR / f"reply_prompts_{date_str}.txt"
    try:
        win_reply_file.write_text(reply_prompts + "\n", encoding="utf-8")
    except OSError:
        pass
    print(f"Reply prompts + follow list: {reply_file}")

    # Write combined_priority_tickers.txt — read by Node.js posting scripts
    tickers_txt = "\n".join(top5) + "\n"
    try:
        COMBINED_TICKERS_TXT.write_text(tickers_txt, encoding="utf-8")
    except OSError:
        pass

    # Print summary
    print(f"social_posts_generated date={date_str} top_pick={top_pick} top5={','.join(top5)}")
    print(f"Twitter ({len(twitter_post)} chars): {twitter_file}")
    print(f"LinkedIn ({len(linkedin_post)} chars): {linkedin_file}")
    print(f"Instagram caption ({len(instagram_caption)} chars): {instagram_caption_file}")
    print()
    print("=== TWITTER POST ===")
    print(twitter_post)
    print()
    print("=== LINKEDIN POST ===")
    print(linkedin_post)
    print()
    print("=== INSTAGRAM CAPTION ===")
    print(instagram_caption)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
