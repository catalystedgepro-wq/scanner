#!/usr/bin/env python3
"""content_scout.py — Auto-topup pending_content.yaml when queue runs low.

Marketing agent role: keep the content pipeline always full so the
distribution_loop never starves. Reads pending_content.yaml — when fewer than
THRESHOLD posts remain in 'queued' state, mints N new spec stanzas from a
keyword bank scoped to the ICP (active SEC-catalyst day/swing trader).

The keyword bank is a curated list of high-intent search phrases mapped to
existing scanner tools. Each new spec gets:
  - slug derived from primary keyword
  - title (commercial/informational mix)
  - h1, target_keyword, secondary_keywords
  - cta_target with utm tagging
  - rationale paragraph

Idempotent: never re-mints a slug that already exists in the queue.

Usage:
    python3 content_scout.py                    # auto: top up if below threshold
    python3 content_scout.py --threshold 8 --topup 5
    python3 content_scout.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
LOG_PATH = WORKSPACE / "logs" / "distribution_loop.log"

sys.path.insert(0, str(ROOT))
from content_smith import _read_queue, _write_queue, _now_iso  # type: ignore


# Keyword bank — tuples of (priority_band, primary_kw, h1, secondaries, intent, tool_path, rationale).
# Priority bands let us interleave informational + commercial. Add more here
# any time — the scout just picks ones whose slug isn't already in queue.
BANK: list[dict] = [
    {
        "kw": "free SEC EDGAR scanner",
        "h1": "Free SEC EDGAR scanner — full-text + catalyst tagging",
        "title": "Free SEC EDGAR scanner: full-text search + auto-catalyst tagging in one place",
        "secondary": ["EDGAR full-text search", "free EDGAR search", "SEC filings free"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "Bottom-funnel commercial kw. SEC EDGAR direct is hard to use. We give catalyst tagging for free.",
    },
    {
        "kw": "low float runner stocks",
        "h1": "Low-float runners — the catalyst-tagged daily list",
        "title": "Low-float runner stocks: how to trade them with the SEC catalyst tag (not the WSB lottery)",
        "secondary": ["low float scanner", "small cap runners", "low float gap up", "penny stock runner"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "Day-trader segment. Low-float scanner intent matches our catalyst tagging. Tier-1 conversion fuel.",
    },
    {
        "kw": "FDA approval calendar",
        "h1": "FDA approval calendar — every PDUFA date, scored",
        "title": "FDA approval calendar 2026: every PDUFA date, scored by squeeze risk and short interest",
        "secondary": ["PDUFA calendar", "biotech catalyst", "FDA decision date list"],
        "intent": "navigational",
        "tool": "/scanner/",
        "rationale": "High-volume seasonal kw. Re-publish annually. Drives biotech ICP traffic.",
    },
    {
        "kw": "convertible note dilution stocks",
        "h1": "Convertible note dilution — spotting the at-the-market risk early",
        "title": "Convertible note dilution: how to spot the ATM offering before the dump (S-3 + 8-K signal stack)",
        "secondary": ["ATM offering", "S-3 ASR filing", "convertible note offering", "dilution warning"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "Squeeze ICP needs to AVOID dilution traps. We surface S-3/424B5 instantly. Reader-tier conversion.",
    },
    {
        "kw": "earnings whisper trade",
        "h1": "Earnings whisper trade — the catalyst-stack approach",
        "title": "Earnings whisper trade: how to read 8-K Item 2.02 + insider Form 4 in the 24h before print",
        "secondary": ["earnings whisper", "earnings catalyst trade", "earnings 8-K", "earnings whispernumber"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "Pre-earnings searches are pure ICP. We have the EDGAR + Form 4 layer baked in.",
    },
    {
        "kw": "biotech short interest scanner",
        "h1": "Biotech short interest scanner — high-SI bio names, free",
        "title": "Biotech short interest scanner: high-SI bio names with PDUFA + Phase 2 overlay (free)",
        "secondary": ["biotech short squeeze", "biotech high short interest", "short interest biotech list"],
        "intent": "commercial",
        "tool": "/squeeze/",
        "rationale": "/squeeze/ filtered to biotech sector. Underpriced kw. High commercial intent.",
    },
    {
        "kw": "after-hours scanner free",
        "h1": "After-hours scanner — catalyst-tagged AH movers, free",
        "title": "After-hours scanner (free): catalyst-tagged AH movers with the SEC filing context Wall Street pays for",
        "secondary": ["after-hours movers", "AH stock scanner", "after-hours gap", "AH catalyst"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "AH movers + catalyst is what Benzinga charges $400/mo for. We give it free.",
    },
    {
        "kw": "Form D private placement",
        "h1": "Form D filings — catching private placements before the dilution",
        "title": "Form D private placements: the SEC filing every short-squeeze trader should be watching",
        "secondary": ["SEC Form D", "private placement filing", "Reg D filing tracker"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "Form D is underused. Pure niche moat. Our scanner surfaces it next to ticker.",
    },
    {
        "kw": "stock buyback announcement scanner",
        "h1": "Stock buyback announcements — the 8-K Item 8.01 signal",
        "title": "Stock buyback announcement scanner: 8-K Item 8.01 trigger with float-shrink scoring",
        "secondary": ["buyback announcement list", "share repurchase scanner", "buyback program"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "Buyback events drive multi-day moves. We tag and rank them automatically.",
    },
    {
        "kw": "13G filing alert",
        "h1": "13G filings — the activist signal everyone misses",
        "title": "13G filings: the activist signal scanner ($89/mo elsewhere, free here)",
        "secondary": ["SC 13G filing", "13G screener", "activist filing alert"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "13G is less famous than 13D but moves stocks. Free vs $89/mo elsewhere.",
    },
    {
        "kw": "DEF 14A proxy fight tracker",
        "h1": "Proxy fight tracker — DEF 14A as a catalyst signal",
        "title": "Proxy fight tracker: how DEF 14A filings telegraph the next M&A leak",
        "secondary": ["proxy fight stocks", "DEF 14A trade", "M&A leak signal", "activist proxy"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "Proxy fights → M&A → big moves. Niche but ICP-aligned.",
    },
    {
        "kw": "SEC comment letter trade",
        "h1": "SEC comment letters — the regulatory drag signal",
        "title": "SEC comment letter trade: when UPLOAD/CORRESP filings predict a stock's quiet bleed",
        "secondary": ["SEC UPLOAD filing", "SEC CORRESP", "comment letter stock"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "Almost no retail watches comment letters. We do. Authority signal.",
    },
    {
        "kw": "stock pump and dump detector",
        "h1": "Pump-and-dump detector — promo-mailer + low-float + S-1 stack",
        "title": "Stock pump-and-dump detector: the 4-signal stack that flags a promo before the dump",
        "secondary": ["pump and dump scanner", "stock promotion alert", "promo stock list"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "Defensive use case. Builds trust. Drives /trust/ + /scanner/ engagement.",
    },
    {
        "kw": "uplisting from OTC to Nasdaq",
        "h1": "Uplistings from OTC to Nasdaq — the catalyst stack",
        "title": "OTC to Nasdaq uplisting: the 8-A + S-3 sequence that prints 80% of the time",
        "secondary": ["OTC uplisting", "Form 8-A trade", "Nasdaq uplisting calendar"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "Uplistings are clean event-driven setups. Our scanner catches the 8-A.",
    },
    {
        "kw": "13F whale activity tracker",
        "h1": "13F whale activity — Berkshire, Burry, Ackman in one feed",
        "title": "13F whale activity tracker: Berkshire, Burry, Ackman, Tepper in one free feed",
        "secondary": ["whale watching stocks", "Whalewisdom alternative", "guru holdings tracker"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "Whalewisdom charges $40/mo for this. We undercut as free top-of-funnel.",
    },
    {
        "kw": "premarket gap scanner free",
        "h1": "Pre-market gap scanner with catalyst tags (free)",
        "title": "Pre-market gap scanner (free): every gap tagged with the underlying SEC catalyst",
        "secondary": ["premarket gappers", "premarket scanner", "gap up scanner", "morning gap"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "Direct competitor capture. Gappers + catalyst is the killer combo.",
    },
    {
        "kw": "options unusual activity scanner",
        "h1": "Unusual options activity scanner — free + audited",
        "title": "Unusual options activity scanner: the volume-spike + 8-K overlay (free, audited)",
        "secondary": ["unusual options activity", "smart money options", "unusual whales alternative"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "Unusual Whales charges $90/mo. We layer SEC catalyst on top of UOA flow.",
    },
    {
        "kw": "stock catalyst calendar 2026",
        "h1": "Stock catalyst calendar 2026 — every binary event",
        "title": "Stock catalyst calendar 2026: every binary event date scored by historical move size",
        "secondary": ["catalyst calendar", "binary event calendar", "earnings + FDA calendar"],
        "intent": "navigational",
        "tool": "/scanner/",
        "rationale": "Annually-recurring nav-intent kw. Update annually.",
    },
    {
        "kw": "best stock screener for swing trading",
        "h1": "Best stock screener for swing trading — head-to-head 2026",
        "title": "Best stock screener for swing trading 2026: Catalyst Edge vs Finviz vs TradingView",
        "secondary": ["swing trade screener", "best swing trade tool", "swing trading stocks scanner"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "Direct comparison kw. Swing trader segment is our primary ICP slice.",
    },
    {
        "kw": "stock alert service comparison",
        "h1": "Stock alert services compared — audited 2026",
        "title": "Stock alert services compared 2026: which one actually has a verified track record?",
        "secondary": ["stock alerts review", "stock pick service", "trading alert service"],
        "intent": "commercial",
        "tool": "/trust/",
        "rationale": "Skeptical-buyer kw. Routes to /trust/ audit ledger. Closes the trust objection.",
    },
    # === CRYPTO-TREASURY EXPANSION (2026-04-26) — taps existing SEC data into crypto audience ===
    {
        "kw": "Bitcoin treasury company tracker",
        "h1": "Bitcoin treasury company tracker — every public co holding BTC",
        "title": "Bitcoin treasury tracker: every public company holding BTC, scored by SEC catalyst risk",
        "secondary": ["MSTR tracker", "MicroStrategy BTC", "corporate Bitcoin holdings", "public company BTC"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "Massive crypto audience overlap with our SEC scanner — MSTR/MARA/RIOT/CIFR all file SEC docs. Underexploited niche.",
    },
    {
        "kw": "MSTR 8-K Bitcoin purchase alert",
        "h1": "MSTR 8-K Bitcoin purchase alerts — real-time SEC tagging",
        "title": "MSTR 8-K Bitcoin purchase alerts: how to catch MicroStrategy buys before the press release",
        "secondary": ["Saylor Bitcoin alert", "MicroStrategy SEC filings", "MSTR 8-K Item 8.01"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "MSTR community is huge and rabid. They want pre-press-release signal. We have the EDGAR feed.",
    },
    {
        "kw": "Bitcoin miner SEC filings",
        "h1": "Bitcoin miner SEC filings — MARA, RIOT, CIFR, IREN tracker",
        "title": "Bitcoin miner SEC filing scanner: MARA, RIOT, CIFR, IREN, BITF, CLSK in one feed",
        "secondary": ["Bitcoin mining stocks", "MARA filings", "RIOT 8-K", "miner equity catalysts"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "Miner equity catalysts — hash rate updates, financing rounds, S-3 dilution risk. Niche commercial intent.",
    },
    {
        "kw": "spot Bitcoin ETF inflows tracker",
        "h1": "Spot Bitcoin ETF inflows tracker — IBIT, FBTC, ARKB, BITB",
        "title": "Spot Bitcoin ETF inflows: which fund is winning the SEC-approved BTC ETF war",
        "secondary": ["IBIT vs FBTC", "BTC ETF flows", "ARKB inflows", "spot Bitcoin ETF AUM"],
        "intent": "navigational",
        "tool": "/scanner/",
        "rationale": "Recurring high-volume kw. ETF flows are leading indicators for BTC price.",
    },
    {
        "kw": "crypto stock catalyst calendar",
        "h1": "Crypto stock catalyst calendar — every binary event for BTC-treasury cos",
        "title": "Crypto stock catalyst calendar 2026: every binary date for COIN, MSTR, MARA, RIOT and the rest",
        "secondary": ["COIN earnings calendar", "MSTR catalysts", "Bitcoin company calendar"],
        "intent": "navigational",
        "tool": "/scanner/",
        "rationale": "Catalyst calendar for the crypto-equity intersection. Annual evergreen.",
    },
    # === INTERNATIONAL EXPANSION (2026-04-26) — English-speaking non-US audiences ===
    {
        "kw": "free SEC scanner for Indian retail traders",
        "h1": "Free SEC catalyst scanner for Indian retail traders",
        "title": "Free SEC catalyst scanner for Indian retail traders: track US stocks before NSE opens",
        "secondary": ["US stocks for Indian traders", "SEC filings India", "Indian retail US stocks"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "India has 100M+ retail traders. Many use US stocks via INDmoney/Vested. Underserved by US-only content.",
    },
    {
        "kw": "UK retail trader SEC filings",
        "h1": "UK retail traders — how to read SEC filings for US stocks",
        "title": "UK retail traders: the SEC catalyst playbook for trading US stocks at LSE close",
        "secondary": ["UK trade US stocks", "SEC filings UK access", "Hargreaves Lansdown US stocks"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "UK has retail trader culture (HL/AJ Bell). Time-zone arbitrage to US opening is a natural angle.",
    },
    {
        "kw": "Australia trade US stocks scanner",
        "h1": "Australia retail traders — pre-market US scanner",
        "title": "Australia retail traders: pre-market US catalyst scanner for the AEDT timezone",
        "secondary": ["Australian US stock scanner", "ASX trader US catalysts", "AU retail US stocks"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "AU retail trades US opening at 11:30 PM AEDT. Pre-market scanner is morning-coffee tool for them.",
    },
    {
        "kw": "Singapore retail traders SEC filings",
        "h1": "Singapore retail traders — SEC catalyst scanner",
        "title": "Singapore retail traders: free SEC catalyst scanner for SGX-fatigued investors looking at US",
        "secondary": ["SG retail US stocks", "Tiger Brokers US scanner", "moomoo SEC filings"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "SG retail trader population uses Tiger/moomoo for US stocks. English-speaking, high-income, underserved.",
    },
    {
        "kw": "Philippines free US stock scanner",
        "h1": "Philippines free US stock scanner — SEC catalyst alerts",
        "title": "Philippines free US stock scanner: real-time SEC catalyst alerts (no subscription)",
        "secondary": ["GoTrade US stocks", "PH retail US trading", "Filipino US stock scanner"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "PH retail trader population is huge and growing on GoTrade/eToro. English-speaking SEO win.",
    },
    # === CHANNELS ABOVE THE STANDARD PIPELINE (2026-04-26) ===
    {
        "kw": "Hacker News trading tools",
        "h1": "Trading tools for HN-style devs and quants",
        "title": "Show HN: free SEC catalyst scanner with audited track record (open methodology)",
        "secondary": ["quant trader tools", "developer trading API", "HN finance tools"],
        "intent": "informational",
        "tool": "/scanner/",
        "rationale": "Optimize one post for HN front-page submission. Tagged for dev/quant audience. /api/ as the wedge.",
    },
    {
        "kw": "Quora best free stock scanner",
        "h1": "The best free stock scanners on Quora — head-to-head answer",
        "title": "Best free stock scanner (Quora-style answer): Catalyst Edge vs Finviz vs TradingView",
        "secondary": ["Quora stock scanner", "free stock screening tools", "best free stock screener"],
        "intent": "commercial",
        "tool": "/scanner/",
        "rationale": "Quora answers rank in Google top-5 for these queries — co-opt by minting our own canonical answer + crosspost to Quora.",
    },
]


def _slugify(kw: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", kw.lower()).strip("-")
    return s[:60]


def _spec_for(entry: dict, priority: int) -> dict:
    slug = _slugify(entry["kw"])
    cta = f"/preview/?utm_source=blog&utm_campaign={slug}"
    return {
        "slug": slug,
        "state": "queued",
        "priority": priority,
        "title": entry["title"],
        "h1": entry["h1"],
        "target_keyword": entry["kw"],
        "cta_target": cta,
        "word_count_target": 2000 if entry["intent"] in ("informational", "navigational") else 1700,
        "target_search_intent": entry["intent"],
        "secondary_keywords": list(entry["secondary"]),
        "rationale": entry["rationale"],
    }


def _log(msg: str) -> None:
    line = f"[{_now_iso()}] content_scout: {msg}"
    print(line)
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=int, default=10,
                        help="topup if queued count drops below this")
    parser.add_argument("--topup", type=int, default=10,
                        help="how many fresh specs to mint when topping up")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    queue = _read_queue()
    posts = queue.get("posts", [])
    queued = [p for p in posts if p.get("state") == "queued"]
    existing_slugs = {p.get("slug") for p in posts}

    _log(f"queue depth: {len(queued)} queued (threshold={args.threshold})")

    if len(queued) >= args.threshold:
        _log("queue is healthy — no topup needed")
        return 0

    # Pick keyword bank entries that aren't already represented as a slug.
    candidates = [e for e in BANK if _slugify(e["kw"]) not in existing_slugs]
    if not candidates:
        _log("ERROR: keyword bank exhausted — add more entries to BANK list in this file")
        return 2

    # Existing max priority + 1 for new ones (lower priority = fires later in queue).
    max_pri = max((int(p.get("priority", 0)) for p in posts), default=0)
    new_specs: list[dict] = []
    for i, entry in enumerate(candidates[: args.topup]):
        spec = _spec_for(entry, max_pri + 1 + i)
        new_specs.append(spec)

    if args.dry_run:
        for s in new_specs:
            _log(f"DRY: would add slug={s['slug']} priority={s['priority']}")
        return 0

    posts.extend(new_specs)
    queue["posts"] = posts
    _write_queue(queue)
    for s in new_specs:
        _log(f"ADDED slug={s['slug']} priority={s['priority']} kw='{s['target_keyword']}'")
    _log(f"queue topped up: {len(new_specs)} new specs added")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
