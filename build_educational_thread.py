#!/usr/bin/env python3
"""Generate weekly educational Twitter/X threads for Catalyst Edge.

Rotates through topic categories week by week so the content stays
fresh. Threads explain HOW the pipeline works — builds credibility,
attracts followers, and drives newsletter signups better than picks posts.

These are written to a file for review before posting. The daily picks
posts are automated — these are meant to be posted manually or reviewed
first since they're educational/brand content.

Output: /home/operator/catalyst-edge/social/edu_thread_{date}.txt
        /path/to/local/Desktop/catalyst-edge/social/edu_thread_{date}.txt

Usage:
    python3 build_educational_thread.py
"""
from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

ROOT         = Path(__file__).parent
SOCIAL_DIR   = Path(__file__).parent / "social"
WIN_SOCIAL   = Path(__file__).parent / "social"
PICKS_JSON   = ROOT / "newsletter_picks.json"
COMBINED_CSV = ROOT / "combined_priority.csv"

NEWSLETTER_URL = "https://catalystedge.agency"
AGENCY_URL     = "https://www.catalystedge.agency/"

# ── Topic rotation (week number mod len) ─────────────────────────────────────

TOPICS = [
    "how_sec_works",
    "form_4_insider",
    "what_is_8k",
    "squeeze_anatomy",
    "scoring_explained",
    "pipeline_architecture",
    "gapper_vs_value",
    "free_data_sources",
]


def _week_topic() -> str:
    week = datetime.date.today().isocalendar()[1]
    return TOPICS[week % len(TOPICS)]


def _load_picks() -> dict:
    if PICKS_JSON.exists():
        try:
            return json.loads(PICKS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _top_pick() -> str:
    picks = _load_picks()
    top5 = picks.get("top5_tickers", [])
    return top5[0] if top5 else "XYZ"


# ── Thread builders ───────────────────────────────────────────────────────────

def thread_how_sec_works(pick: str) -> list[str]:
    return [
        f"🧵 Most traders ignore the SEC's public filing database. Here's why that's a mistake — and how we use it to find setups like ${pick} every morning. (1/8)",
        "The SEC requires every public company to disclose material events within 4 business days. That filing is called an 8-K. It goes live on EDGAR the moment it's submitted. (2/8)",
        "What counts as material? Mergers. FDA decisions. Major contracts. Guidance changes. CEO resignations. Share buybacks. Dividend announcements. All of it hits EDGAR in real time. (3/8)",
        "Most retail traders find out about these events from news articles — hours or days after the filing. By then the move has already happened. (4/8)",
        "We scan EDGAR's RSS feeds every morning before 4 AM ET. Every new 8-K, Form 4 insider trade, and Schedule 13D gets pulled and scored before the market opens. (5/8)",
        "The scoring looks at: what keywords appear in the filing text, how recently it was filed, the company's price/volume/market cap, and whether insiders are buying simultaneously. (6/8)",
        "The result: a ranked list of the highest-conviction setups sourced directly from public government data. No analyst opinions. No delayed news. Raw signal. (7/8)",
        f"Free daily newsletter → {NEWSLETTER_URL}\n🎙️ Ask Catalyst AI about today's picks → {AGENCY_URL}\n\n#SEC #EDGAR #StockCatalyst #Trading #Investing",
    ]


def thread_form_4_insider(pick: str) -> list[str]:
    return [
        "🧵 Form 4 is one of the most underrated signals in the market. Here's what it is, why insiders file it, and how we use it to spot conviction setups. (1/7)",
        "Every time a company insider (CEO, CFO, Director, 10%+ shareholder) buys or sells stock, they must report it to the SEC within 2 business days. That report is Form 4. (2/7)",
        "Open market purchases are the signal. When a CEO buys $500K of their own stock on the open market — not options, actual shares — that's real money at risk. Insiders don't do that unless they're confident. (3/7)",
        "What makes it even stronger: CLUSTER buys. When 2+ insiders at the same company file Form 4 purchases in the same week, the conviction is compounding. Our pipeline flags these automatically. (4/7)",
        "The pattern we look for: Form 4 insider buy + 8-K positive catalyst + short interest above 15% = three signals pointing the same direction. That's a convergence alert. (5/7)",
        "All of this data is 100% public and free on SEC EDGAR. We just automated the scanning, scoring, and delivery so you get it before 4 AM ET every day. (6/7)",
        f"Free daily newsletter → {NEWSLETTER_URL}\n🎙️ Talk to Catalyst AI → {AGENCY_URL}\n\n#Form4 #InsiderTrading #SEC #StockCatalyst #Investing",
    ]


def thread_what_is_8k(pick: str) -> list[str]:
    return [
        f"🧵 ${pick} triggered our scanner this morning via an 8-K filing. Most traders don't know what that means. Here's a quick breakdown. (1/7)",
        "An 8-K is a 'current report' — a public company's way of telling the SEC (and therefore everyone) that something significant just happened. It must be filed within 4 business days. (2/7)",
        "The items that trigger an 8-K:\n• Mergers and acquisitions\n• FDA approvals or rejections\n• Major contract wins or losses\n• Earnings guidance changes\n• CEO/CFO changes\n• Bankruptcy filings\n• Share buyback authorizations (3/7)",
        "Not all 8-Ks are equal. An 8-K announcing an FDA approval for a biotech is a massive binary catalyst. An 8-K announcing a new office lease is noise. Our scoring separates them. (4/7)",
        "We score each 8-K by scanning the full filing text for positive and negative keywords, weighted by recency. A filing from 2 hours ago scores higher than one from yesterday. (5/7)",
        "Then we layer on: price filter ($3+), volume filter (250K+ avg), market cap filter ($300M+). Only quality setups make the final list. No penny stock traps. (6/7)",
        f"Get the full scored list every morning, free → {NEWSLETTER_URL}\n🎙️ Ask about any pick by voice → {AGENCY_URL}\n\n#8K #SEC #StockCatalyst #Trading #EventDriven",
    ]


def thread_squeeze_anatomy(pick: str) -> list[str]:
    return [
        "🧵 Short squeezes don't happen randomly. There's a anatomy to them. Here's exactly what we scan for every morning. (1/8)",
        "Step 1: High short interest. If 20%+ of the float is short, there's fuel. The shorts need to buy back eventually — the question is just what lights the match. (2/8)",
        "Step 2: Low float. Fewer shares outstanding = less stock to buy to move the price. A 5M share float squeezes much faster than a 500M share float. Same demand, 100x less supply. (3/8)",
        "Step 3: Options gamma. When a stock has heavy call open interest at strikes just above current price, market makers are forced to buy shares as the price rises (delta hedging). This accelerates the move. (4/8)",
        "Step 4: Insider buying via Form 4. When the CEO starts buying their own stock while short interest is elevated, that's a squeeze setup with a fundamental backstop. (5/8)",
        "Step 5: A catalyst. The match. Usually an 8-K — earnings beat, FDA approval, contract win. Something that forces the shorts to reconsider their thesis all at once. (6/8)",
        "Our squeeze hunter scores all five factors daily. Tickers that hit COILED or IGNITION stage get flagged in the newsletter with their short interest %, float, and catalyst status. (7/8)",
        f"Free daily squeeze radar + full picks → {NEWSLETTER_URL}\n🎙️ Ask Catalyst AI which setups are coiled today → {AGENCY_URL}\n\n#ShortSqueeze #SEC #Trading #Stocks #SqueezePlay",
    ]


def thread_scoring_explained(pick: str) -> list[str]:
    return [
        f"🧵 How does ${pick} end up as today's top pick? Here's exactly how our scoring model works — weights, filters, and all. (1/7)",
        "Every ticker gets three scores:\n• Gapper score — catalyst strength for a gap at open\n• Value score — shareholder return & balance sheet signals\n• Moat score — competitive advantage & recurring revenue signals\n\nCombined = total conviction score. (2/7)",
        "Gapper score positive signals: FDA approval (+4), definitive merger agreement (+4), earnings beat (+3), contract award (+3), guidance raise (+3), record revenue (+2).\n\nNegative: dilution offering (-3), going concern (-4). (3/7)",
        "Value score positive signals: share buyback (+3), dividend increase (+3), special dividend (+2), debt reduction (+2), activist 13-D position (+2), free cash flow language (+1).\n\nFilters: price $5+, volume 500K+. (4/7)",
        "Moat score positive signals: patent filing (+2), exclusive agreement (+2), multi-year contract (+2), recurring revenue (+2), backlog growth (+1), market share gains (+1).\n\nFilters: market cap $2B+. (5/7)",
        "Weights are auto-tuned daily. Yesterday's picks are compared against actual next-day outcomes (open → intraday high). If gapper picks outperformed last week, gapper weights increase. (6/7)",
        f"The full scored list, free every morning → {NEWSLETTER_URL}\n🎙️ Ask about the scoring on any pick → {AGENCY_URL}\n\n#AlgoTrading #SEC #Quant #StockScreener #Investing",
    ]


def thread_pipeline_architecture(pick: str) -> list[str]:
    return [
        "🧵 I automated an entire trading research pipeline that runs at 4 AM every day. Here's the full architecture — no paid APIs, all public data. (1/9)",
        "Step 1: Fetch SEC EDGAR RSS feeds for 8-K, Form 4, S-3, 13-D/G. Map CIKs to tickers using SEC's company_tickers.json. Result: 300+ fresh filings with tickers attached. (2/9)",
        "Step 2: Fetch full filing text from EDGAR for each entry. Run keyword scoring (positive catalysts vs. negative flags). Cache results for 48 hours to avoid hammering the server. (3/9)",
        "Step 3: Fetch 60-day price/volume history from Stooq (free, no API key). Calculate avg volume, current price. Apply investability filters. (4/9)",
        "Step 4: Classify into Gapper/Value/Moat/Income tracks. Run squeeze hunter (short interest proxy + options gamma estimate + Form 4 cluster detection). (5/9)",
        "Step 5: Pull news RSS from MarketWatch, Yahoo Finance, EIA, NOAA. Score sector momentum. Merge with SEC signals into a combined priority list. (6/9)",
        "Step 6: Auto-tune scoring weights by backtesting yesterday's picks against actual next-day open/close outcomes. (7/9)",
        "Step 7: Build HTML newsletter, update ElevenLabs voice agent system prompt with today's data, distribute to 10+ platforms via Python + Playwright. All automated via cron at 4:05 AM ET. (8/9)",
        f"The output is a free daily newsletter anyone can subscribe to.\n\n📧 {NEWSLETTER_URL}\n🎙️ {AGENCY_URL}\n\n#AlgoTrading #Python #Automation #SEC #FinTech",
    ]


def thread_gapper_vs_value(pick: str) -> list[str]:
    return [
        "🧵 Gapper play vs. value play — what's the difference and why does it matter for how you trade them? (1/7)",
        "A GAPPER play is event-driven. Something just happened — FDA approval, merger announcement, earnings beat — that wasn't priced in. The stock gaps at open. You're trading the reaction. Time horizon: hours to days. (2/7)",
        "A VALUE play is signal-driven. The company is doing something that improves intrinsic value — buyback, dividend raise, debt paydown — but the market may not have reacted yet. Time horizon: days to weeks. (3/7)",
        "How you size them differently:\nGapper — smaller position, wider stop, faster target. The move is sharp or it isn't.\nValue — larger position, tighter stop (thesis-based), longer hold. You have a reason to stay. (4/7)",
        "The overlap is the sweet spot. When a ticker shows up in BOTH the gapper list AND the value list — a buyback announced via 8-K with positive earnings language — that's double confirmation. (5/7)",
        "Our pipeline scores both independently and surfaces the overlap. Tickers appearing in multiple categories get flagged as convergence alerts — highest conviction in the list. (6/7)",
        f"Free daily breakdown of both lists → {NEWSLETTER_URL}\n🎙️ Ask Catalyst AI which category today's top pick is in → {AGENCY_URL}\n\n#StockCatalyst #EventDriven #ValueInvesting #Trading",
    ]


def thread_free_data_sources(pick: str) -> list[str]:
    return [
        "🧵 You don't need to pay for stock data. Here are the free public sources our entire pipeline runs on — bookmarked for keeps. (1/8)",
        "1. SEC EDGAR RSS feeds\nedgar.sec.gov/cgi-bin/browse-edgar\nReal-time filings for any form type. No API key. Updated continuously. This is where the alpha lives. (2/8)",
        "2. SEC company_tickers.json\nsec.gov/files/company_tickers.json\nMaps every CIK to a ticker symbol. Free. Updated daily. Essential for turning EDGAR filings into tradeable tickers. (3/8)",
        "3. Stooq\nstooq.com\nFree daily price/volume data in CSV format. No API key, no rate limits if you're polite. Covers US equities going back decades. (4/8)",
        "4. SEC XBRL company facts\ndata.sec.gov/api/xbrl/companyfacts/CIK{cik}.json\nFundamental data (revenue, shares outstanding, debt) straight from company filings. Completely free. (5/8)",
        "5. MarketWatch, Yahoo Finance, EIA, NOAA RSS\nAll have public RSS feeds with sector and macro data. No scraping needed — proper feeds with structured data. (6/8)",
        "6. EDGAR full-text search\nefts.sec.gov/efts-api\nSearch the content of all filings. Incredibly powerful for finding filings that mention specific products, competitors, or events. Free. (7/8)",
        f"We built an entire automated trading research pipeline on these sources alone. Free daily output → {NEWSLETTER_URL}\n🎙️ {AGENCY_URL}\n\n#FreeTool #StockResearch #SEC #AlgoTrading #FinTech",
    ]


# ── Main ─────────────────────────────────────────────────────────────────────

THREAD_BUILDERS = {
    "how_sec_works":         thread_how_sec_works,
    "form_4_insider":        thread_form_4_insider,
    "what_is_8k":            thread_what_is_8k,
    "squeeze_anatomy":       thread_squeeze_anatomy,
    "scoring_explained":     thread_scoring_explained,
    "pipeline_architecture": thread_pipeline_architecture,
    "gapper_vs_value":       thread_gapper_vs_value,
    "free_data_sources":     thread_free_data_sources,
}


def main() -> int:
    today = datetime.date.today().isoformat()
    pick = _top_pick()
    topic = _week_topic()

    builder = THREAD_BUILDERS[topic]
    tweets = builder(pick)

    output_lines = [
        f"=== EDUCATIONAL THREAD — {today} ===",
        f"Topic: {topic.replace('_', ' ').title()}",
        f"Top pick context: ${pick}",
        f"Tweets: {len(tweets)}",
        "",
    ]
    for i, tweet in enumerate(tweets, 1):
        output_lines.append(f"--- Tweet {i} ({len(tweet)} chars) ---")
        output_lines.append(tweet)
        output_lines.append("")

    content = "\n".join(output_lines)
    print(content)

    SOCIAL_DIR.mkdir(parents=True, exist_ok=True)
    out = SOCIAL_DIR / f"edu_thread_{today}.txt"
    out.write_text(content, encoding="utf-8")
    print(f"\nSaved → {out}")

    try:
        WIN_SOCIAL.mkdir(parents=True, exist_ok=True)
        (WIN_SOCIAL / f"edu_thread_{today}.txt").write_text(content, encoding="utf-8")
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
