#!/usr/bin/env python3
"""social_rotator.py — Distribution Automaton.

Picks the most recently published blog post and writes platform-specific
post bodies into /home/operator/.openclaw/workspace/social_inbox/<slug>_<platform>.txt.
The existing run_social_posts.sh cron picks them up.

Generated platforms (all hand-crafted in Catalyst Edge voice — terse, no
marketing-speak, polish-tokens vibe: confident, technical, audited):

  - x          (~280 chars + link)
  - linkedin   (~600 chars + link, more context)
  - reddit     (~1500 chars + link, post-shape, no bullet salads)

Usage:
    python3 social_rotator.py --latest               # use the most recently published
    python3 social_rotator.py --slug <slug>          # specific slug

Output files:
    social_inbox/<slug>_x.txt
    social_inbox/<slug>_linkedin.txt
    social_inbox/<slug>_reddit.txt

NOTE: state transitions to 'promoted' after the social_inbox files are
written. The actual posting is owned by run_social_posts.sh on its own
cadence, NOT by this script.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
SOCIAL_INBOX = WORKSPACE / "social_inbox"
SOCIAL_INBOX.mkdir(exist_ok=True)
LOG_PATH = WORKSPACE / "logs" / "distribution_loop.log"

sys.path.insert(0, str(ROOT))
from content_smith import _read_queue, _write_queue, _now_iso, _today  # type: ignore


def _log(msg: str) -> None:
    line = f"[{_now_iso()}] social_rotator: {msg}"
    print(line)
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _post_url(slug: str) -> str:
    return f"https://catalystedgescanner.com/blog/{slug}/"


# ---------------------------------------------------------------------------
# Voice templates — keyed off slug so each post's social copy is bespoke.
# ---------------------------------------------------------------------------

def _voice_x(post: dict) -> str:
    slug = post["slug"]
    url = _post_url(slug)
    if slug == "free-sec-catalyst-scanner":
        body = (
            "FlyOnTheWall: $89/mo. BamSEC: $49/mo.\n\n"
            "Same SEC EDGAR feed, paywalled.\n\n"
            "Catalyst Edge: free, audited, 89% hit rate published in public.\n\n"
        )
    elif slug == "how-to-trade-8k-filings":
        body = (
            "8-K Items 1.01, 2.02, 5.02, 7.01, 8.01 = ~80% of catalyst pre-market gaps.\n\n"
            "Most retail traders read 8-Ks reactively, after the gap.\n\n"
            "The actual edge is which item just hit. Playbook with 5 real examples →\n\n"
        )
    elif slug == "insider-buying-signal-explained":
        body = (
            "Generic insider buying = 51% hit rate (coin flip).\n\n"
            "CEO+CFO same-period clusters > $250K each, no 10b5-1 = ~73% over 90 days.\n\n"
            "Why clustering is the only insider read that survives backtesting →\n\n"
        )
    elif slug == "short-squeeze-setup-checklist":
        body = (
            "Most retail squeezes die because the trader looked at one number.\n\n"
            "The pro read is a triple filter:\n"
            "• DTC > 5\n"
            "• SI > 20% float\n"
            "• Borrow rate > 30% APR\n\n"
            "All three, simultaneously. Plus a catalyst. Then it's a setup →\n\n"
        )
    elif slug == "dcf-intrinsic-value-explained":
        body = (
            "Bloomberg charges $24,000/yr for DCF intrinsic value across 1,000+ names.\n\n"
            "It's a 30-line spreadsheet and an 8-min mental model.\n\n"
            "Two-stage Damodaran walkthrough with one ticker, free →\n\n"
        )
    else:
        body = f"New post: {post['title']}\n\n"
    full = body + url
    # X 280 char hard cap (URLs count as ~23). We aim for under 280 chars.
    if len(full) > 280:
        # trim body
        excess = len(full) - 277
        body = body[: -excess - 1].rstrip() + "…\n"
        full = body + url
    return full


def _voice_linkedin(post: dict) -> str:
    slug = post["slug"]
    url = _post_url(slug)
    if slug == "free-sec-catalyst-scanner":
        body = (
            "FlyOnTheWall ($89/mo), BamSEC ($49/mo), and Benzinga Pro ($177/mo) all wrap "
            "the same SEC EDGAR feed in a paywall.\n\n"
            "Catalyst Edge Scanner is the audited free alternative.\n\n"
            "What you get free, every weekday:\n"
            "• Top 3 of /scanner/ — live SEC catalysts scored before 8 AM ET\n"
            "• Top 3 of /jackpot/ — convergence picks\n"
            "• /trust/ audit log — every pick going back 60+ days, win/loss outcomes published\n"
            "• 4 AM ET daily catalyst email\n\n"
            "Reader at $9/mo opens the full lists. Pro at $39/mo opens DCF intrinsic value, "
            "Cerebro HUD macro overlays, and alerts.\n\n"
            "If you're paying for a catalyst feed today, the test is one week of side-by-side.\n\n"
        )
    elif slug == "how-to-trade-8k-filings":
        body = (
            "8-Ks drive more pre-market gap setups than every other catalyst combined.\n\n"
            "But there are ~30 distinct 8-K items, and 5 of them produce ~80% of the "
            "tradeable behavior:\n\n"
            "1.01 — material agreement (M&A, supply, debt)\n"
            "2.02 — results of operations (read the guidance, not the EPS line)\n"
            "5.02 — officer departure (immediate + no successor = strongest bearish read on EDGAR)\n"
            "7.01 — Reg FD disclosure (the attached deck is the signal)\n"
            "8.01 — other events (FDA, DOJ, regulators — widest variance)\n\n"
            "Posted the full playbook with 5 real recent setups, plus how /scanner/ surfaces "
            "them by 8 AM ET.\n\n"
        )
    elif slug == "insider-buying-signal-explained":
        body = (
            "The naive read of insider buying — 'they bought, buy the stock' — has a 51% hit "
            "rate. Roughly coin-flip.\n\n"
            "The professional read: CEO and CFO buy in the same 14-day window, both above "
            "$250K, neither under a 10b5-1 plan. ~73% hit rate over a 90-day forward horizon "
            "in our backtests.\n\n"
            "Why clustering works: two senior officers reach the same view independently and "
            "act on it materially. Information asymmetry concentrates. The 14-day window rules "
            "out calendar-driven 10b5-1 prints. The $250K floor rules out symbolic 'show of "
            "confidence' buys.\n\n"
            "Full breakdown of why generic Form 4 feeds are noisy and how /insiders/ ranks the "
            "discretionary-cluster reads.\n\n"
        )
    elif slug == "short-squeeze-setup-checklist":
        body = (
            "Most retail squeeze plays die because the trader looked at short interest in "
            "isolation. SI alone is a participation metric, not a setup.\n\n"
            "The professional read is a triple filter, all three rails firing simultaneously:\n\n"
            "• DTC > 5 trading days (forces shorts to chase liquidity that isn't there)\n"
            "• SI > 20% of float (the participation floor)\n"
            "• Borrow rate > 30% APR (the financing pain that forces the cover)\n\n"
            "Layer that against a fresh catalyst (8-K Item 1.01 or FDA correspondence) and "
            "you have the gunpowder + the spark.\n\n"
            "/squeeze/ ranks every US-listed name on the composite squeeze score. Top 5 "
            "daily, free tier capped at 3.\n\n"
        )
    elif slug == "dcf-intrinsic-value-explained":
        body = (
            "DCF intrinsic value sounds like a graduate-school exercise. It's actually a "
            "30-line spreadsheet and an 8-minute mental model.\n\n"
            "Two-stage Damodaran:\n"
            "1. Project free cash flow to firm for years 1–5\n"
            "2. Terminal value at Gordon growth (long-run g = 2.5%)\n"
            "3. Discount everything at WACC (CAPM-derived cost of equity + after-tax debt)\n"
            "4. Subtract net debt, divide by shares outstanding → intrinsic value/share\n\n"
            "Bloomberg charges $24,000/year for the same calculation across 1,000+ names. "
            "/dcf/ on Catalyst Edge publishes it for free with a public methodology page and "
            "a sector-aware sanity cap (3× for Financials, 20× for everything else).\n\n"
            "Walkthrough with one real ticker, plus what can go wrong and how /dcf/ guards "
            "against it.\n\n"
        )
    else:
        body = f"New post: {post['title']}\n\n"
    return body + url


def _voice_reddit(post: dict) -> str:
    slug = post["slug"]
    url = _post_url(slug)
    if slug == "free-sec-catalyst-scanner":
        body = (
            "**Free SEC catalyst scanner — vs FlyOnTheWall ($89/mo) and BamSEC ($49/mo)**\n\n"
            "I've been building a free alternative to the paid SEC catalyst tools. Posting "
            "here because the audience overlaps with what most of you already pay for.\n\n"
            "**The thesis:** FlyOnTheWall, BamSEC, and Benzinga Pro all wrap the same SEC "
            "EDGAR feed in a paywall. The data is public. The methodology is opaque. There's "
            "no audit on accuracy.\n\n"
            "**What's in the free tier (no signup gate, top 3 free, full list at $9/mo):**\n\n"
            "- Live /scanner/ — every catalyst-eligible 8-K, 4, S-3, 13D, 6-K scored "
            "before 8 AM ET\n"
            "- /jackpot/ — convergence picks (catalyst + insider + squeeze rails firing "
            "simultaneously)\n"
            "- /insiders/ — Form 4 cluster ranker (CEO+CFO same period > generic VP buys)\n"
            "- /squeeze/ — DTC × SI × borrow-rate triple filter, daily refresh\n"
            "- /dcf/ — intrinsic value across 1,000+ names (free top 3, full at $39/mo)\n"
            "- /trust/ — audit log of every pick going back 60+ days, with win/loss outcomes\n"
            "- 4 AM ET daily catalyst email\n\n"
            "**Why I built it this way:**\n\n"
            "1. **Audit in public on day one.** /trust/ logs every pick. Hit rate published. "
            "Embarrassing rows included.\n"
            "2. **No blurred data.** The free tier is the actual scanner with a row cap. "
            "Not a fog filter.\n"
            "3. **Stdlib only.** Whole pipeline runs on one Linux box, one cron, no SaaS "
            "stack — that's why the free tier can stay free.\n\n"
            "Full post breaks down the side-by-side vs the paid alternatives plus how to "
            "use it on day one.\n\n"
            f"{url}\n\n"
            "Happy to answer questions on the methodology in the comments. Not pushing the "
            "$9 — the free tier is enough for most setups."
        )
    elif slug == "how-to-trade-8k-filings":
        body = (
            "**How to trade 8-K filings — the 5-form-type playbook**\n\n"
            "Wrote up the playbook I use for reading 8-Ks pre-market. Posting because the "
            "way most retail traders read 8-Ks reactively (after the gap) is leaving the "
            "actual edge on the table.\n\n"
            "**The five items that drive ~80% of tradeable pre-market 8-K behavior:**\n\n"
            "1. **Item 1.01** — Entry into a material agreement. M&A, supply contracts, "
            "licensing, debt facilities. Sustained 5–20% multi-day moves vs the one-print "
            "fade of 2.02.\n"
            "2. **Item 2.02** — Results of operations. The trade is rarely 'beat → buy' "
            "(consensus is priced). Read the **guidance revision** in the body — up-revision "
            "= legs, in-line = fade.\n"
            "3. **Item 5.02** — Departure of officers. Immediate departure with no successor "
            "named is the strongest bearish signal in the whole 8-K taxonomy.\n"
            "4. **Item 7.01** — Reg FD disclosure. The attached exhibit (investor deck) is "
            "the actual signal.\n"
            "5. **Item 8.01** — Other events. Widest variance — FDA approval, DOJ subpoena, "
            "FAA findings. Pre-market read mandatory.\n\n"
            "Post has 5 real recent setups (one per item) plus how the scoring runs at 4 AM "
            "ET so the top 10 are on the board by 8.\n\n"
            f"{url}"
        )
    elif slug == "insider-buying-signal-explained":
        body = (
            "**Why generic insider buying is a coin flip — and what actually predicts**\n\n"
            "The naive read of Form 4 — 'insider bought, buy the stock' — runs ~51% hit "
            "rate. Barely better than random.\n\n"
            "The reason: most Form 4 volume isn't a discretionary buy. 10b5-1 plan trades, "
            "ESPP, option exercises, automated quarterly lots. If you treat them all "
            "equally, you're rewarding average mid-level VPs for executing a calendar trade "
            "they signed up for two years ago.\n\n"
            "**The filter that actually works:**\n\n"
            "CEO and CFO buy stock in the same 14-day window, both above $250K, neither "
            "under a 10b5-1 plan.\n\n"
            "That filter fires roughly 20–40 times per quarter across the whole US-listed "
            "universe. Forward returns over 90 days, market-cap-weighted, run ~12–18% above "
            "benchmark.\n\n"
            "**Why it works:** two senior officers independently reach the same view and "
            "act on it materially. The information asymmetry concentrates. The 14-day "
            "clustering rules out calendar-driven 10b5-1 prints (those are spaced "
            "quarterly). The $250K floor rules out symbolic 'show of confidence' buys.\n\n"
            "Add tenure (>18 months in seat), sizing-by-net-worth (a $500K buy from someone "
            "with $2M vested = 25% of net worth = extraordinary), and the prior-buy track "
            "record, and you've got the actual ranker.\n\n"
            "Full post + how /insiders/ ranks the discretionary cluster reads:\n\n"
            f"{url}"
        )
    elif slug == "short-squeeze-setup-checklist":
        body = (
            "**Short squeeze setup checklist — the triple filter (DTC × SI × Borrow Rate)**\n\n"
            "Most retail squeeze plays die because the trader looked at short interest in "
            "isolation and called it a setup. SI alone is a popular-short metric, not a "
            "squeeze. Tesla had 30%+ SI for years and never squeezed.\n\n"
            "**The triple filter — all three have to fire simultaneously:**\n\n"
            "1. **Days-to-Cover (DTC) > 5.** Pull weekly from FINRA. SI ÷ 20-day average "
            "volume. Above 5 means even a moderate up-move forces shorts to chase liquidity "
            "that isn't there.\n"
            "2. **Short Interest > 20% of float.** Float-adjusted, not market-cap-adjusted. "
            "Insider blocks and locked stock don't matter to the short side. 20% is the "
            "participation floor.\n"
            "3. **Borrow Rate > 30% APR.** This is the most-overlooked rail. Most retail "
            "trackers don't surface it. Above 30% APR shorts are paying to wait. Above "
            "100% APR they're bleeding daily. That's the gunpowder.\n\n"
            "**The catalyst trigger:** triple filter is the powder, an 8-K Item 1.01 "
            "(material agreement) or an FDA / Type B meeting outcome is the spark. Without "
            "a spark, the powder sits.\n\n"
            "Free /squeeze/ tool ranks every US-listed name on the composite squeeze score "
            "daily. Cross-checks against the live catalyst feed for the convergence picks.\n\n"
            f"{url}"
        )
    elif slug == "dcf-intrinsic-value-explained":
        body = (
            "**DCF intrinsic value, in 8 minutes — the two-stage Damodaran method**\n\n"
            "DCF sounds like a graduate-school exercise. It's actually a 30-line spreadsheet "
            "and an 8-minute mental model. Bloomberg, FactSet, and Refinitiv charge "
            "$15K–$24K/year for the same calculation. The math is public.\n\n"
            "**The two-stage model:**\n\n"
            "1. **Stage 1 — explicit forecast (years 1–5).** Project free cash flow to firm "
            "(FCFF). Standard formula: EBIT × (1 − tax rate) + D&A − CapEx − ΔWC. Apply "
            "growth — usually trailing 3-year FCFF CAGR, capped at 15%.\n"
            "2. **Stage 2 — terminal (year 6+).** Gordon growth: TV = FCFF₆ ÷ (WACC − g). "
            "Use g = 2.5% (long-run US real GDP+inflation blend).\n"
            "3. **Discount everything at WACC.** WACC = (E/V)·Re + (D/V)·Rd·(1−t). Re from "
            "CAPM: risk-free + β·ERP. Risk-free from 10-year Treasury, ERP = 5.5% "
            "(Damodaran-published implied US ERP), β from 60-month rolling regression.\n"
            "4. **Equity value.** Sum of discounted FCFFs + discounted TV − net debt. "
            "Divide by shares outstanding → intrinsic value per share. Compare to market "
            "price.\n\n"
            "**What can go wrong:**\n\n"
            "- Garbage FCFF inputs from misclassified line items. Pull from SEC EDGAR XBRL, "
            "use the GAAP-tagged values directly.\n"
            "- Terminal value sensitivity (60–80% of EV). Hold g constant at 2.5% across "
            "the universe so cross-comparisons stay apples-to-apples.\n"
            "- Sector blowups: financials' OCF includes deposit float and compounds to "
            "nonsense. Sector-cap upside (3× for Financials, 20× elsewhere).\n\n"
            "Walkthrough with a worked example on a real ticker:\n\n"
            f"{url}"
        )
    else:
        body = f"{post['title']}\n\n{url}"
    return body


def _voice_instagram(post: dict) -> str:
    """Instagram caption — LinkedIn-style narrative + hashtag block."""
    body = _voice_linkedin(post)
    tags = "\n\n#daytrading #swingtrading #stockmarket #SECfilings #catalyststocks #fintwit #stocks #trading"
    out = body + tags
    return out[:2197] if len(out) > 2200 else out


def _voice_tiktok(post: dict) -> str:
    """TikTok caption — short X-style hook + hashtag block."""
    hook = _voice_x(post)
    tags = "\n\n#fintwit #daytrading #stocktok #swingtrading #stockmarket #trading"
    out = hook + tags
    return out[:2197] if len(out) > 2200 else out


def _voice_youtube(post: dict) -> str:
    """YouTube — first line is the title, rest is description (LinkedIn voice + tags)."""
    title = post.get("title") or post.get("h1") or post.get("slug", "")
    title = title.strip()[:95]
    body = _voice_linkedin(post)
    tags = "\n\n#daytrading #SECfilings #stocks #catalyst"
    return f"{title}\n{body}{tags}"[:4990]


def _emit_for(post: dict) -> list[Path]:
    slug = post["slug"]
    out: list[Path] = []
    for platform, body in (
        ("x", _voice_x(post)),
        ("linkedin", _voice_linkedin(post)),
        ("reddit", _voice_reddit(post)),
        ("instagram", _voice_instagram(post)),
        ("tiktok", _voice_tiktok(post)),
        ("youtube", _voice_youtube(post)),
    ):
        path = SOCIAL_INBOX / f"{slug}_{platform}.txt"
        path.write_text(body, encoding="utf-8")
        out.append(path)
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--latest", action="store_true",
                        help="rotate the most recently published post")
    parser.add_argument("--slug", help="rotate a specific slug")
    args = parser.parse_args(argv)

    queue = _read_queue()
    posts = queue.get("posts", [])
    target: dict | None = None
    if args.slug:
        target = next((p for p in posts if p.get("slug") == args.slug), None)
        if target is None:
            _log(f"ERROR: slug not found {args.slug}")
            return 2
    elif args.latest:
        # Only pick posts that haven't been rotated yet. Already-promoted posts
        # belong to repromote.py with cooldown rules, not to --latest.
        published = [p for p in posts if p.get("state") == "published"]
        if not published:
            _log("no fresh published posts to rotate (use repromote.py for promoted ones)")
            return 1
        published.sort(key=lambda p: str(p.get("published_at", "")), reverse=True)
        target = published[0]
    else:
        parser.print_help()
        return 0

    out = _emit_for(target)
    for p in out:
        _log(f"social_inbox WROTE {p.name} bytes={p.stat().st_size}")
    target["state"] = "promoted"
    target["promoted_at"] = _today()
    _write_queue(queue)
    _log(f"PROMOTED slug={target['slug']} -> {len(out)} platform files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
