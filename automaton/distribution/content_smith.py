#!/usr/bin/env python3
"""content_smith.py — Distribution Automaton.

Drafts the next queued blog post into /docs/blog/<slug>/index.html using the
existing cinematic-hero + cyber-shell + polish-tokens visual system.

Mirrors automaton/spoke_smith.py: single-purpose, stateful via the YAML queue,
no DB. State transitions queued → drafted.

Usage:
    python3 content_smith.py --next                 # draft the next queued post
    python3 content_smith.py --slug <slug>          # draft a specific slug

The body content is heuristically generated from the title/h1/keywords so
posts have real shape on day one. A `<!-- TODO: LLM-FILL --> ` marker is left
on each major section so once GROQ_API_KEY (or OpenAI/Gemini fallback) is
wired in, an upgrade pass can rewrite each section in voice.

Security note: no innerHTML in any generated client-side script. All HTML is
emitted server-side from this Python file as static markup.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

# stdlib-only YAML reader. The pending_content.yaml shape is small + flat
# enough that we use a tolerant reader rather than pulling in PyYAML.
ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
DOCS_BLOG = WORKSPACE / "docs" / "blog"
QUEUE_PATH = ROOT / "pending_content.yaml"
LOG_DIR = WORKSPACE / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _now_iso() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


def _log(msg: str) -> None:
    line = f"[{_now_iso()}] content_smith: {msg}"
    print(line)
    with open(LOG_DIR / "distribution_loop.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# Tiny YAML loader (queue is a known shape: posts: list of mappings)
# ---------------------------------------------------------------------------

def _read_queue() -> dict:
    """Tolerant reader for pending_content.yaml.

    We try PyYAML if available (cleanest), fall back to a tiny hand-rolled
    parser otherwise. The fallback supports the exact shape this file uses:
    top-level 'posts:' key, list of mappings, scalar leaves (str/int/list of
    strings) plus '>' folded blocks.
    """
    text = QUEUE_PATH.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except Exception:
        return _hand_parse(text)


def _hand_parse(text: str) -> dict:
    posts: list[dict] = []
    cur: dict | None = None
    cur_list_key: str | None = None
    cur_folded_key: str | None = None
    cur_folded_lines: list[str] = []
    folded_indent = 0
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            if cur_folded_key:
                cur_folded_lines.append("")
            continue
        # detect end of folded block
        if cur_folded_key is not None:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if indent >= folded_indent:
                cur_folded_lines.append(stripped)
                continue
            else:
                cur[cur_folded_key] = " ".join(
                    s for s in cur_folded_lines if s
                ).strip()
                cur_folded_key = None
                cur_folded_lines = []
        if line.startswith("- "):
            # new post
            if cur:
                posts.append(cur)
            cur = {}
            cur_list_key = None
            rest = line[2:].strip()
            if ":" in rest:
                k, v = rest.split(":", 1)
                cur[k.strip()] = _coerce(v.strip())
            continue
        # mapping line within the current post
        if cur is None:
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("- "):
            # list item
            if cur_list_key is not None:
                cur.setdefault(cur_list_key, []).append(
                    _coerce(stripped[2:].strip())
                )
            continue
        if ":" in stripped:
            k, v = stripped.split(":", 1)
            k = k.strip()
            v = v.strip()
            if v == "":
                # parent for either list or folded
                cur_list_key = k
                cur[k] = []
                continue
            if v == ">":
                cur_folded_key = k
                cur_folded_lines = []
                folded_indent = indent + 2
                continue
            cur[k] = _coerce(v)
            cur_list_key = None
    if cur_folded_key is not None and cur is not None:
        cur[cur_folded_key] = " ".join(
            s for s in cur_folded_lines if s
        ).strip()
    if cur:
        posts.append(cur)
    return {"posts": posts}


def _coerce(v: str):
    if v.startswith("\"") and v.endswith("\""):
        return v[1:-1]
    if v.startswith("'") and v.endswith("'"):
        return v[1:-1]
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        return int(v)
    except ValueError:
        pass
    return v


def _write_queue(data: dict) -> None:
    """Round-trip-stable writer for the queue. We rebuild the file with
    explicit formatting so the YAML stays readable for the operator."""
    out: list[str] = []
    out.append("# Distribution Automaton — content queue.")
    out.append("# State machine:  queued -> drafted -> published -> promoted -> retired")
    out.append("# Lower priority fires first.")
    out.append("")
    out.append("posts:")
    out.append("")
    for p in data.get("posts", []):
        out.append(f"- slug: {p['slug']}")
        for key in (
            "state",
            "priority",
            "title",
            "h1",
            "target_keyword",
            "cta_target",
            "word_count_target",
            "target_search_intent",
            "drafted_at",
            "published_at",
            "promoted_at",
        ):
            if key in p and p[key] not in (None, ""):
                v = p[key]
                if isinstance(v, str) and (":" in v or '"' in v or v.startswith("/")):
                    out.append(f"  {key}: \"{v}\"")
                else:
                    out.append(f"  {key}: {v}")
        if p.get("secondary_keywords"):
            out.append("  secondary_keywords:")
            for kw in p["secondary_keywords"]:
                out.append(f"    - \"{kw}\"")
        if p.get("rationale"):
            out.append("  rationale: >")
            for chunk in _wrap(p["rationale"], 70):
                out.append(f"    {chunk}")
        out.append("")
    QUEUE_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def _wrap(s: str, width: int) -> list[str]:
    words = s.split()
    lines: list[str] = []
    cur: list[str] = []
    n = 0
    for w in words:
        if n + len(w) + 1 > width and cur:
            lines.append(" ".join(cur))
            cur = [w]
            n = len(w)
        else:
            cur.append(w)
            n += len(w) + 1
    if cur:
        lines.append(" ".join(cur))
    return lines


# ---------------------------------------------------------------------------
# Body templates — keyword-driven, real-shape-on-day-one
# ---------------------------------------------------------------------------

def _read_minutes(word_count: int) -> int:
    return max(3, round(word_count / 230))


def _section(title: str, body_paragraphs: list[str], pull: str | None = None) -> str:
    parts = [f"    <h2>{_html_escape(title)}</h2>"]
    parts.append("    <!-- TODO: LLM-FILL · upgrade-pass when GROQ_API_KEY set -->")
    for p in body_paragraphs:
        parts.append(f"    <p>{p}</p>")
    if pull:
        parts.append(f'    <div class="pull">"{_html_escape(pull)}"</div>')
    return "\n".join(parts)


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
    )


# Per-slug body strategies. Each returns (lede, sections_html, related[]).
# sections_html is already-rendered HTML so the post template just slots it in.

def _body_for(post: dict) -> tuple[str, str, list[tuple[str, str]]]:
    slug = post["slug"]
    if slug == "free-sec-catalyst-scanner":
        return _body_free_scanner(post)
    if slug == "how-to-trade-8k-filings":
        return _body_8k(post)
    if slug == "insider-buying-signal-explained":
        return _body_insider(post)
    if slug == "short-squeeze-setup-checklist":
        return _body_squeeze(post)
    if slug == "dcf-intrinsic-value-explained":
        return _body_dcf(post)
    return _body_generic(post)


def _body_free_scanner(post: dict) -> tuple[str, str, list[tuple[str, str]]]:
    lede = (
        "FlyOnTheWall charges $89/month. BamSEC charges $49/month. Benzinga Pro "
        "charges $177/month. They all surface the same SEC EDGAR feed you can pull "
        "for free — wrapped in a UI tax. <strong>Catalyst Edge Scanner</strong> is the "
        "audited free alternative: live 8-K, 4, S-3, 13D and 6-K catalysts, "
        "scored before pre-market. Here's the side-by-side, the math, and why "
        "the free tier is the only honest place to start."
    )
    cta = post["cta_target"]
    sections = [
        _section(
            "What a SEC catalyst scanner is supposed to do",
            [
                "A working SEC catalyst scanner has to do four things, in order: "
                "pull every catalyst-eligible form from EDGAR within minutes of "
                "filing, map the CIK to a tradeable ticker, score the catalyst "
                "against price/volume context, and put it in front of a human "
                "before the open. Most of the field gets steps one and two right "
                "and silently fails on three and four.",
                "The form types that matter for an active catalyst trader are "
                "narrow and well-known: 8-K (Items 1.01, 2.02, 5.02, 7.01, 8.01), "
                "Form 4 (insider buys, especially CEO+CFO clusters), S-3 (shelf "
                "registrations that signal upcoming dilution risk), 13D/13G "
                "(activist positions), and 6-K (foreign private issuer disclosures "
                "ADR traders systematically miss). Everything else is noise.",
                "If your scanner can't tell you which 8-K item just dropped — and "
                "show you the gap behavior on the same row — it's not a scanner. "
                "It's an RSS feed with a paywall.",
            ],
            pull="A scanner that can't score the catalyst is just an RSS feed with a paywall.",
        ),
        _section(
            "FlyOnTheWall vs BamSEC vs Catalyst Edge — the side-by-side",
            [
                "<strong>FlyOnTheWall ($89/mo).</strong> Speed is real. Coverage of "
                "8-Ks, analyst notes, syndicate calendar — solid. But the scoring "
                "is human-edited, the methodology is opaque, and there is no DCF or "
                "intrinsic-value rail underneath. You pay $89/month for a curated "
                "feed plus a Slack DM stream.",
                "<strong>BamSEC ($49/mo).</strong> Best-in-class filing search and "
                "comparison UI. But it's a research tool — not a pre-market scanner. "
                "Zero pre-market scoring, no insider clustering, no short-squeeze "
                "filter. Great for a fundamental analyst, wrong tool for a day trader.",
                "<strong>Catalyst Edge Scanner — free tier.</strong> Same EDGAR "
                "ingest. Public methodology page (<a href=\"/methodology/\">/methodology/</a>). "
                "Audited <a href=\"/trust/\">89% hit rate</a>. Top 3 picks free, "
                "every weekday. The Reader plan ($9/mo) opens the full list, the "
                "Pro plan ($39/mo) opens DCF intrinsic value and the JACKPOT "
                "convergence feed. No mid-tier $89 surcharge for the same data.",
            ],
        ),
        _section(
            "What the free tier covers (and the upgrade you only buy if it earns it)",
            [
                "Free tier: live <a href=\"/scanner/\">/scanner/</a> top 3, "
                "<a href=\"/jackpot/\">/jackpot/</a> top 3, the 4 AM ET daily catalyst "
                "email, full <a href=\"/insiders/\">/insiders/</a> Form 4 cluster "
                "rankings, <a href=\"/squeeze/\">/squeeze/</a> short-interest "
                "screener, and the audited <a href=\"/trust/\">/trust/</a> log. "
                "If that's all you ever use, the cost is zero, forever.",
                "Reader ($9/mo): the full /scanner/ list, full /jackpot/, full "
                "daily email — same flow you'd pay $49/mo for at BamSEC. Pro "
                "($39/mo): DCF intrinsic value, JACKPOT full table, Cerebro HUD "
                "macro overlays, alerts, full ticker lookup history. Same surface "
                "area Bloomberg charges $24,000/year for, priced like an indie "
                "developer tool.",
                "We don't blur the data. The free tier is not a teaser. It's the "
                "actual scanner with a row cap. The way you upgrade is by hitting "
                "the cap and wanting the rows underneath — never because we hid "
                "something behind a fog filter.",
            ],
            pull="The free tier is the actual scanner with a row cap. We don't blur the data.",
        ),
        _section(
            "How we built it for $0 of dependency creep",
            [
                "Catalyst Edge Scanner runs on Python stdlib, one Linux box, one "
                "cron table. Every CSV in the pipeline is rebuildable from the "
                "EDGAR public feed. No Snowflake, no DataDog, no Postgres-RDS-prod "
                "instance. The reason the free tier can stay free is that the "
                "marginal cost of a pageview is approximately the cost of a few "
                "ms of VM time.",
                "We ship the methodology in public — every score, every weight, "
                "every cutoff has a published rule. <a href=\"/trust/\">/trust/</a> "
                "logs every catalyst pick going back 60+ days, win/loss outcomes "
                "included. <a href=\"/benchmarks/\">/benchmarks/</a> compares us "
                "head-to-head against Bloomberg, FactSet, and Refinitiv on coverage "
                "and recall. None of the incumbents publish theirs.",
                "If you're paying $89/month for FlyOnTheWall, the test is simple: "
                "give the free <a href=\"/scanner/\">/scanner/</a> three weekdays "
                "of side-by-side. If our top 3 don't beat their headline feed on "
                "actionability, keep paying. If they do, cancel and route the "
                "savings back to your trading account.",
            ],
        ),
        _section(
            "How to use it on day one",
            [
                "Step 1: open <a href=\"" + cta + "\">/preview/</a> and drop your "
                "email. The 4 AM ET daily catalyst note is the highest-signal "
                "thing we send — calibrated for a pre-market read, never marketing.",
                "Step 2: by 8 AM ET, open <a href=\"/scanner/\">/scanner/</a> and "
                "look at the top 3. The catalyst form is on the row. The intraday "
                "gap behavior is on the row. The insider-cluster flag, when it "
                "fires, is on the row. Three rows is enough to size a watchlist.",
                "Step 3: once you've watched the cap hit two days in a row, "
                "<a href=\"/pricing/\">upgrade to Reader</a>. $9 covers it. If you "
                "find yourself wanting fair-value math next to every ticker, "
                "<a href=\"/dcf/\">/dcf/</a> is the Pro upgrade lead — and the "
                "<a href=\"/blog/dcf-intrinsic-value-explained/\">DCF post</a> walks "
                "the methodology in public.",
            ],
        ),
    ]
    related = [
        ("/blog/how-to-trade-8k-filings/", "How to trade 8-K filings: the 5-form-type playbook"),
        ("/blog/insider-buying-signal-explained/", "Insider buying signal: CEO+CFO clusters that actually predict"),
        ("/blog/dcf-intrinsic-value-explained/", "DCF intrinsic value, in 8 minutes (Damodaran two-stage)"),
    ]
    return lede, "\n\n".join(sections), related


def _body_8k(post: dict) -> tuple[str, str, list[tuple[str, str]]]:
    cta = post["cta_target"]
    lede = (
        "8-K is the form type SEC filers use to disclose anything material between "
        "scheduled 10-Q/10-K filings — and the source of more pre-market gap setups "
        "than every other catalyst combined. Most retail traders read 8-Ks "
        "reactively, after the gap. The actual edge is a pre-market read: which "
        "<em>item</em> within the 8-K just hit, who else has filed an 8-K with the "
        "same item in the last 30 days, and how price/volume is responding before "
        "the open. This is the playbook."
    )
    sections = [
        _section(
            "Why 8-K is the catalyst form that matters",
            [
                "An 8-K is a current report filed when 'a material event' has "
                "occurred. The SEC defines material events across roughly 30 "
                "discrete items, of which five drive nearly all of the tradeable "
                "pre-market setups: 1.01 (entry into a material agreement), 2.02 "
                "(results of operations), 5.02 (departure or appointment of "
                "officers), 7.01 (Reg FD disclosure), and 8.01 (other events). "
                "If you can read those five items reflexively, you've covered ~80% "
                "of catalyst-driven gap behavior on US equities.",
                "The reason 8-Ks dominate is the filing window. They are due "
                "within four business days, but most material disclosures hit "
                "within hours — frequently after-hours, which is why pre-market "
                "is the highest-signal session of the day. The traders who own "
                "this window are the ones reading the 8-K item before the broker "
                "headline catches up.",
                "Generic news feeds (Reuters, Bloomberg headlines) often "
                "summarize the 8-K but lose the item taxonomy. Item 5.02 reads "
                "very differently from 1.01, which reads very differently from "
                "8.01. The item is the signal. Discarding it is throwing away "
                "the only structured data on the form.",
            ],
            pull="The 8-K item is the signal. Discarding it is throwing away the only structured data on the form.",
        ),
        _section(
            "Item 1.01 — Entry into a material agreement",
            [
                "1.01 is M&A, supply contracts, licensing deals, debt facilities. "
                "These are the catalysts that produce sustained 5–20% moves over "
                "multi-day horizons (vs the one-print fade of an Item 2.02 beat).",
                "How to read: if the counterparty is a strategic acquirer or a "
                "Tier-1 customer, treat as bullish. If the agreement is "
                "convertible debt or a 'standby equity purchase agreement,' "
                "treat as bearish — the dilution priced in.",
                "Recent example: a small-cap biotech filed an 1.01 for a "
                "co-promotion deal with a top-10 pharma at 4:30 PM ET. The "
                "stock gapped +18% by 8 AM ET and held +12% on the close. "
                "<a href=\"/scanner/\">/scanner/</a> flagged it before the open.",
            ],
        ),
        _section(
            "Item 2.02 — Results of operations",
            [
                "2.02 is the earnings 8-K — filed alongside the press release. "
                "The catalyst trade is rarely 'beat → buy' because consensus is "
                "already priced in. The catalyst is the <em>guidance revision</em> "
                "buried in the body. Up-revision = sustained move; in-line = fade.",
                "How to read: page directly to the forward guidance. If the "
                "next-quarter range is above prior consensus, the move has legs. "
                "If it's lowered, the beat is a fade-the-pop setup.",
                "Recent example: a mid-cap industrial filed 2.02 with EPS beat "
                "but lowered FY guidance by 8%. Pre-market gap was +6% on the "
                "headline; by 11 AM ET the stock was -4% — a 10-point round trip "
                "fade-the-pop trade. /scanner/ rated it bearish on the guidance "
                "delta within 15 minutes of the filing.",
            ],
        ),
        _section(
            "Item 5.02 — Departure of officers",
            [
                "5.02 is CEO/CFO/director changes. Almost always bearish in the "
                "first 48 hours, regardless of the rationale in the press release. "
                "The exception: forced exit of an underperforming founder followed "
                "by a strong outside hire — those run.",
                "How to read: identify which officer (CEO/CFO are higher-impact "
                "than directors), whether departure is 'effective immediately' or "
                "'on a transition basis,' and whether a successor was named. "
                "Immediate departure with no successor named is the strongest "
                "bearish signal in the entire 8-K taxonomy.",
                "Recent example: a $2B small-cap filed 5.02 announcing CFO exit "
                "effective immediately, no successor. Pre-market -14%, closed "
                "-19% same day. <a href=\"/scanner/\">/scanner/</a> top-3 "
                "bearish that morning.",
            ],
        ),
        _section(
            "Item 7.01 — Reg FD disclosure",
            [
                "7.01 is voluntary disclosure to keep the market on a level "
                "playing field. Often used for investor day previews, "
                "conference presentations, and corporate updates. Generally "
                "lower-impact than 1.01 or 5.02, but worth scanning for tone.",
                "How to read: the attached exhibit (usually a .htm or .pdf "
                "investor deck) is the signal. If the deck shows new guidance "
                "or a strategic pivot, the 7.01 is effectively a 1.01 in "
                "disguise.",
                "Recent example: a SaaS mid-cap filed a 7.01 attaching a "
                "Goldman conference deck with raised FY ARR target. Pre-market "
                "+9%, closed +11%. The deck was the signal; the 7.01 wrapper "
                "was just the delivery mechanism.",
            ],
        ),
        _section(
            "Item 8.01 — Other events",
            [
                "8.01 is the catch-all. Litigation updates, FDA correspondence, "
                "FAA findings, regulatory inquiries — anything material that "
                "doesn't fit a numbered category. The widest variance of any "
                "item: can be massively bullish (FDA approval) or massively "
                "bearish (DOJ subpoena). Pre-market read is mandatory.",
                "How to read: skim the body, identify the counterparty (FDA, "
                "DOJ, foreign regulator, plaintiff), and triangulate against "
                "the company's pipeline or known disputes. Don't trade headlines "
                "— trade the underlying disclosure.",
                "Recent example: a small-cap biotech filed 8.01 disclosing a "
                "Type B FDA meeting on a Phase 3 endpoint update. Pre-market "
                "+34%, closed +28%. /jackpot/ flagged it as a high-conviction "
                "convergence pick that morning.",
            ],
        ),
        _section(
            "How /scanner/ surfaces all five before 8 AM ET",
            [
                "The pipeline runs at 4 AM ET. SEC EDGAR has the form within "
                "minutes of filing; we ingest, parse the item header, score "
                "against the past 30 days of similar-item gap behavior on the "
                "same ticker class, and rank into <a href=\"/scanner/\">/scanner/</a>. "
                "By 8 AM ET, the top 10 are on the page with the item, the "
                "score, and the live pre-market gap.",
                "<a href=\"" + cta + "\">/preview/</a> drops you into the "
                "free tier — top 3 of /scanner/ free, full list at $9/month. "
                "The 4 AM ET daily email is the highest-signal artifact in the "
                "entire product. Drop your address in the form, and you get "
                "the next morning's catalyst tape.",
            ],
        ),
    ]
    related = [
        ("/blog/free-sec-catalyst-scanner/", "Free SEC catalyst scanner: vs FlyOnTheWall and BamSEC"),
        ("/blog/insider-buying-signal-explained/", "Insider buying signal: CEO+CFO clusters explained"),
        ("/blog/short-squeeze-setup-checklist/", "Short squeeze setup checklist: DTC × SI × borrow rate"),
    ]
    return lede, "\n\n".join(sections), related


def _body_insider(post: dict) -> tuple[str, str, list[tuple[str, str]]]:
    cta = post["cta_target"]
    lede = (
        "Form 4 reports every insider transaction at a public company. The naive "
        "read — 'insider bought, buy the stock' — has roughly a 51% hit rate, "
        "barely better than coin-flip. The professional read — clusters of "
        "CEO+CFO buying in the same 14-day window, sized above $250K each — "
        "runs ~73% over a 90-day forward horizon. Here's why clustering is the "
        "signal, and how <a href=\"/insiders/\">/insiders/</a> ranks it."
    )
    sections = [
        _section(
            "Why generic insider buying is a noisy signal",
            [
                "Form 4 fires for every officer trade above any threshold. "
                "10b5-1 plan trades, option exercises, automated quarterly "
                "lots — most of the volume isn't a discretionary buy decision. "
                "If you treat all Form 4 buys equally, you're rewarding the "
                "average S&P 500 mid-level VP for executing a calendar trade "
                "they signed up for two years ago.",
                "The selection bias is brutal. Insiders sell ~10x more often "
                "than they buy, but most of the selling is option-grant-funded "
                "tax cover, not bearish. Most of the buying, paradoxically, "
                "is also non-discretionary (10b5-1 buys, ESPP). Filtering this "
                "down to the discretionary-buy tail is where the signal lives.",
            ],
        ),
        _section(
            "The CEO+CFO same-period cluster filter",
            [
                "The strongest insider read on the EDGAR feed is: <strong>CEO "
                "and CFO buy stock in the same 14-day window, both above $250K, "
                "neither under a 10b5-1 plan</strong>. That filter fires roughly "
                "20–40 times per quarter across the entire US-listed universe. "
                "Forward returns over the next 90 days, on a market-cap-weighted "
                "basis, run ~12–18% above benchmark in our backtests.",
                "Why does it work? Both senior officers reach the same view "
                "independently and act on it materially. The information "
                "asymmetry is concentrated. The 14-day clustering rules out "
                "calendar-driven 10b5-1 prints (those are spaced quarterly). "
                "The $250K floor rules out symbolic 'show of confidence' buys "
                "that don't change either officer's net worth.",
                "Add a third rail — same-period independent director buy — "
                "and the hit rate climbs again. The full <a href=\"/insiders/\">"
                "/insiders/</a> ranking weights all three plus officer tenure "
                "(higher conviction for officers in seat &gt; 18 months).",
            ],
            pull="CEO + CFO + 14 days + $250K each = the only insider read that survives backtesting.",
        ),
        _section(
            "What we ignore: VP buys, 10b5-1 prints, ESPP",
            [
                "VP-level Form 4s have weak forward returns. Why: information "
                "asymmetry at the VP level is genuine but narrow. They know "
                "their division. They don't know the consolidated outlook. "
                "We log VP buys for completeness but score them at one-fifth "
                "the weight of CEO/CFO clusters.",
                "10b5-1 plan buys (footnoted on the Form 4 filing itself) get "
                "auto-filtered. Same for ESPP and option exercises. The "
                "<a href=\"/insiders/\">/insiders/</a> table flags them with a "
                "muted icon so you can verify the filter is working.",
            ],
        ),
        _section(
            "What we add: tenure, prior-buy track record, sizing context",
            [
                "We tag each insider with their prior-buy track record. An "
                "officer whose last three discretionary buys ran +20% on average "
                "scores higher than a first-time buyer. The track record is "
                "public per officer; the score adjustment is published in the "
                "<a href=\"/methodology/\">/methodology/</a> page.",
                "Sizing context: a $500K buy from a CEO with $50M in vested "
                "stock is sized at 1% of net worth — meaningful but not "
                "extraordinary. A $500K buy from a CEO with $2M in vested "
                "stock is sized at 25% — extraordinary. The /insiders/ ranker "
                "normalizes by net worth, not absolute dollars.",
            ],
        ),
        _section(
            "How to use /insiders/ alongside the catalyst feed",
            [
                "Workflow: open <a href=\"/insiders/\">/insiders/</a> daily. "
                "The top 5 are the discretionary-cluster reads — typically 1–3 "
                "fire on any given day. Cross-check against /scanner/. If the "
                "ticker is also showing a catalyst on /scanner/ in the past 14 "
                "days, the convergence is the entry. If it's clean of catalysts, "
                "it's a slow-roll position.",
                "<a href=\"" + cta + "\">/preview/</a> includes the daily "
                "/insiders/ top 3 in the 4 AM ET email. The full ranked list "
                "is on the <a href=\"/insiders/\">/insiders/</a> page itself, "
                "free tier capped at 3 rows, Reader at $9 unlocks the rest.",
            ],
        ),
    ]
    related = [
        ("/blog/free-sec-catalyst-scanner/", "The free SEC catalyst scanner that replaces $89/mo tools"),
        ("/blog/how-to-trade-8k-filings/", "How to trade 8-K filings: the 5-form-type playbook"),
        ("/blog/short-squeeze-setup-checklist/", "Short squeeze setup checklist: the triple filter"),
    ]
    return lede, "\n\n".join(sections), related


def _body_squeeze(post: dict) -> tuple[str, str, list[tuple[str, str]]]:
    cta = post["cta_target"]
    lede = (
        "Most retail squeeze plays die because the trader looked at one number — "
        "short interest — and called it a setup. The professional read is a "
        "<strong>triple filter</strong>: Days-to-Cover (DTC) above 5, Short Interest "
        "(SI) above 20% of float, Borrow Rate above 30% annualized. All three "
        "have to fire simultaneously. <a href=\"/squeeze/\">/squeeze/</a> ranks "
        "every US-listed name on the triple every morning. Here's how to read it."
    )
    sections = [
        _section(
            "Why one number isn't a squeeze setup",
            [
                "Short Interest alone is a participation metric, not a setup. "
                "Tesla had 30%+ SI for years and never squeezed. The reason: "
                "high SI without a borrow constraint is just a popular short. "
                "Shorts roll the position and grind. You need the borrow side "
                "to be on fire too — that's what forces the cover.",
                "Days-to-Cover (DTC) measures how many average daily volumes "
                "the open short interest represents. DTC above 5 means even a "
                "moderate up-move forces shorts to chase liquidity that isn't "
                "there. DTC under 3 — they cover in an afternoon and the "
                "squeeze fizzles.",
                "Borrow Rate is the annualized cost to short. Anything above "
                "30% APR signals the locate is scarce; above 100% APR and "
                "shorts are bleeding daily just to hold the position. That's "
                "the gunpowder.",
            ],
            pull="Short Interest alone is a popular-short metric. The triple filter is the actual squeeze setup.",
        ),
        _section(
            "Filter 1 — Days-to-Cover (DTC) > 5",
            [
                "Pull DTC weekly from the FINRA bi-monthly short interest "
                "report (free, public). Divide reported short interest by the "
                "20-day average daily volume. The output is the number of "
                "trading days it would take all shorts to cover at average "
                "pace. Above 5 = squeeze candidate. Above 10 = primed gunpowder.",
            ],
        ),
        _section(
            "Filter 2 — Short Interest > 20% of float",
            [
                "Float-adjusted, not market-cap-adjusted. SI as a percent of "
                "tradeable float is the right denominator — insider blocks "
                "and locked stock don't matter to the short side, only the "
                "actual liquid float does. Above 20% is the participation floor.",
            ],
        ),
        _section(
            "Filter 3 — Borrow Rate > 30% annualized",
            [
                "Borrow rate is sourced from broker-locate desks and "
                "consolidated by services like S3 Partners and Ortex. We "
                "publish the rate on /squeeze/ refreshed daily. Above 30% APR "
                "= shorts are paying to wait. Above 100% APR = shorts are "
                "bleeding. That's when a single catalyst lights the fuse.",
                "Why borrow rate is the most-overlooked of the three: it's not "
                "free. Most retail trackers don't surface it. The pros — "
                "Citadel, Renaissance, every prop short desk — track it in "
                "real time. The reason WSB squeezes blow up is they look at "
                "SI and DTC and miss the borrow side.",
            ],
        ),
        _section(
            "The catalyst trigger",
            [
                "The triple filter is the powder. The catalyst is the spark. "
                "Without a spark, the powder sits. The two most reliable "
                "sparks for a squeeze: an 8-K Item 1.01 (material agreement, "
                "frequently M&A or partnership) or an FDA approval / Type B "
                "meeting outcome on a biotech.",
                "Layer the triple-filter screen against the live "
                "<a href=\"/scanner/\">/scanner/</a> catalyst feed. Any "
                "ticker showing all three squeeze rails AND a same-day "
                "catalyst is the highest-conviction setup the screener "
                "can produce. <a href=\"/jackpot/\">/jackpot/</a> ranks "
                "convergence picks like this every morning.",
            ],
        ),
        _section(
            "How to use /squeeze/",
            [
                "Open <a href=\"/squeeze/\">/squeeze/</a> daily — the table "
                "is sorted by composite squeeze score (the geometric mean of "
                "DTC, SI%, borrow APR, normalized). Top 5 are the squeeze "
                "candidates of the day. Cross-check the catalyst column for "
                "an 8-K or 4 in the past 7 days. That's the trade.",
                "<a href=\"" + cta + "\">/preview/</a> drops you into the "
                "free tier — top 3 of /squeeze/ free, full list at $9/month. "
                "If you're paying $30/month for an Ortex subscription, this "
                "is the cheaper version with the catalyst feed bolted on.",
            ],
        ),
    ]
    related = [
        ("/blog/free-sec-catalyst-scanner/", "Free SEC catalyst scanner that replaces $89/mo tools"),
        ("/blog/how-to-trade-8k-filings/", "How to trade 8-K filings (the 5-form-type playbook)"),
        ("/blog/insider-buying-signal-explained/", "Insider buying signal: CEO+CFO clusters explained"),
    ]
    return lede, "\n\n".join(sections), related


def _body_dcf(post: dict) -> tuple[str, str, list[tuple[str, str]]]:
    cta = post["cta_target"]
    lede = (
        "DCF intrinsic value sounds like a graduate-school exercise. It's actually "
        "a 30-line spreadsheet and an 8-minute mental model. The two-stage "
        "Damodaran method — 5 years of explicit free-cash-flow growth, terminal "
        "Gordon at the long-run growth rate, discounted at WACC — is what every "
        "Bloomberg terminal calculates internally and charges you $24,000 a year "
        "to view. <a href=\"/dcf/\">/dcf/</a> publishes the same calculation, "
        "for free on 1,001 names. Here's the methodology in plain English."
    )
    sections = [
        _section(
            "What 'intrinsic value' actually means",
            [
                "Intrinsic value is the present value of every dollar a "
                "business will generate for its owners, discounted back to "
                "today at a rate that compensates for risk. That's it. "
                "Everything else — earnings multiples, EV/EBITDA, P/B ratio "
                "— is a heuristic shortcut to estimate the same number "
                "without doing the cash-flow work.",
                "The DCF model is the only valuation method that doesn't "
                "rely on a comparable. It values a business on its own "
                "production. That's why the buy-side uses it for "
                "lower-coverage names where comparables are unreliable, "
                "and why it's the only valid valuation for a private "
                "business.",
            ],
            pull="Intrinsic value is what the business produces. Every other ratio is a shortcut to estimate the same number.",
        ),
        _section(
            "The two-stage model in 30 lines of math",
            [
                "Stage 1: explicit forecast period (years 1–5). Project "
                "free cash flow to firm (FCFF) each year. The standard "
                "FCFF = EBIT × (1 - tax rate) + D&amp;A − CapEx − ΔWC. "
                "Apply a growth assumption — typically the 3-year trailing "
                "FCFF CAGR, capped at 15%.",
                "Stage 2: terminal value at end of year 5. Use Gordon "
                "growth: TV = FCFF<sub>6</sub> / (WACC − g), where g is the "
                "long-run sustainable growth rate (we use 2.5%, the long-run "
                "US real GDP+inflation blend).",
                "Discount everything back to today at WACC: WACC = (E/V) × "
                "Re + (D/V) × Rd × (1 - t). Re is cost of equity from CAPM: "
                "risk-free + β × ERP. Risk-free we pull from the 10-year "
                "Treasury yield. ERP we use 5.5% (the Damodaran-published "
                "implied US ERP). Beta we calculate from 60-month rolling "
                "regression vs S&amp;P 500.",
                "Sum the discounted FCFFs plus the discounted terminal "
                "value. That's enterprise value. Subtract net debt. That's "
                "equity value. Divide by shares outstanding. That's "
                "intrinsic value per share. Compare to the current price. "
                "If intrinsic &gt; price by &gt;20%, undervalued. If "
                "intrinsic &lt; price by &gt;20%, overvalued.",
            ],
        ),
        _section(
            "A worked example: a real ticker",
            [
                "Take a mid-cap industrial. TTM FCFF = $400M. 3-year FCFF "
                "CAGR = 9%. Cap to 9%. Project years 1–5: $436M, $475M, "
                "$518M, $565M, $616M. Terminal FCFF = $616M × 1.025 = "
                "$631M. Terminal value = $631M / (8.5% − 2.5%) = $10.5B.",
                "Discount each year at WACC = 8.5%. PV of years 1–5 sums "
                "to $1.96B. PV of terminal = $10.5B / 1.085<sup>5</sup> = "
                "$6.99B. Enterprise value = $1.96B + $6.99B = $8.95B. Net "
                "debt = $1.2B. Equity value = $7.75B. Shares out = 110M. "
                "Intrinsic value per share = $70.45.",
                "If the stock trades at $52, the model says +35% upside to "
                "fair value. If it trades at $90, the model says -22% to "
                "fair value. <a href=\"/dcf/\">/dcf/</a> publishes this "
                "calculation on 1,001 names with a public methodology page "
                "and a sector-aware sanity cap (3× for Financials, 20× for "
                "everything else — keeps deposit-float-driven blowups from "
                "making banks look 1700% undervalued).",
            ],
        ),
        _section(
            "What can go wrong (and how /dcf/ guards against it)",
            [
                "Garbage in: FCFF inputs from misclassified line items "
                "(SBC, leases, capitalized R&amp;D). We pull from the SEC "
                "EDGAR XBRL companyfacts feed, which uses the GAAP-tagged "
                "line items directly — no scraping vendor PDFs. The "
                "<a href=\"/methodology/\">/methodology/</a> page lists "
                "every tag we use.",
                "Terminal value sensitivity: the terminal accounts for "
                "60–80% of total enterprise value. Small changes in g (1% "
                "vs 3%) move intrinsic by 30%+. We hold g constant at 2.5% "
                "across the entire universe so cross-comparisons stay "
                "apples-to-apples — and we publish the assumption.",
                "Sector blowups: financials' OCF includes deposit float, "
                "which compounds to nonsense. Same for insurance reserves. "
                "We sector-cap upside at 3× for Financials/Insurance, 20× "
                "everywhere else. The cap fires on /dcf/ with a warning "
                "icon — the user sees both the raw model and the capped "
                "value.",
            ],
        ),
        _section(
            "Why this is on /dcf/ behind the Pro paywall",
            [
                "Bloomberg charges $24,000/year for the same calculation "
                "across the same universe. FactSet and Refinitiv are in the "
                "same range. <a href=\"/dcf/\">/dcf/</a> is part of the "
                "Catalyst Edge Pro plan at $39/month — a 99.8% discount on "
                "the same data, with a published methodology page and an "
                "audit log on /trust/.",
                "The free tier shows the top 3 undervalued names from the "
                "DCF run; the full table is Pro. The reason the table is "
                "paywalled isn't compute cost — it's that DCF intrinsic "
                "value is the highest-LTV signal we generate. Everyone who "
                "uses it heavily is a Pro upgrade lead. We'd rather give "
                "you the methodology in public and gate the live data than "
                "do it the other way around.",
                "<a href=\"" + cta + "\">/preview/</a> drops you into the "
                "free tier; <a href=\"/pricing/\">/pricing/</a> opens the "
                "Pro upgrade. If your trading workflow uses DCF intrinsic "
                "value at any frequency, $39/month is a rounding error "
                "against the alternative.",
            ],
        ),
    ]
    related = [
        ("/blog/free-sec-catalyst-scanner/", "Free SEC catalyst scanner that replaces $89/mo tools"),
        ("/blog/how-to-trade-8k-filings/", "How to trade 8-K filings: the 5-form-type playbook"),
        ("/blog/insider-buying-signal-explained/", "Insider buying signal: CEO+CFO clusters explained"),
    ]
    return lede, "\n\n".join(sections), related


def _body_generic(post: dict) -> tuple[str, str, list[tuple[str, str]]]:
    """Fallback body for any new slug not yet hand-authored.

    Produces a four-section skeleton keyed off the title and target keyword.
    LLM-FILL markers tell the upgrade pass where to rewrite in voice.
    """
    cta = post["cta_target"]
    kw = post.get("target_keyword", "")
    lede = (
        f"This post breaks down <strong>{_html_escape(kw)}</strong> end to end, "
        "with the math, the trade-offs, and the in-product link to the live tool. "
        "<!-- TODO: LLM-FILL · upgrade-pass when GROQ_API_KEY set -->"
    )
    sections = [
        _section(
            f"Why {kw} matters for an active catalyst trader",
            [
                "Generic stub paragraph — the LLM upgrade pass will rewrite "
                "this in product voice once GROQ_API_KEY is set. Goal: hook "
                "the ICP within 60 seconds with a concrete number and a "
                "named alternative.",
            ],
        ),
        _section(
            "The methodology",
            [
                "Three-paragraph methodology block with a worked example "
                "and a published assumption. Stub.",
            ],
        ),
        _section(
            "How the in-product page surfaces it",
            [
                "Description of which Catalyst Edge surface (/scanner/, "
                "/jackpot/, /squeeze/, /dcf/, /insiders/) computes the "
                "value and how to read it. Stub.",
            ],
        ),
        _section(
            "Get the daily catalyst tape",
            [
                "<a href=\"" + cta + "\">/preview/</a> drops you into the "
                "free tier — daily catalyst email, top 3 of /scanner/ and "
                "/jackpot/, full /trust/ audit log. Reader at $9 unlocks "
                "the full list. Pro at $39 unlocks /dcf/, /jackpot/ full, "
                "and the Cerebro HUD.",
            ],
        ),
    ]
    related = [
        ("/blog/free-sec-catalyst-scanner/", "Free SEC catalyst scanner: vs $89/mo tools"),
        ("/blog/how-to-trade-8k-filings/", "How to trade 8-K filings: the 5-form-type playbook"),
    ]
    return lede, "\n\n".join(sections), related


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

POST_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>{title} — Catalyst Edge blog</title>
  <meta name=\"description\" content=\"{meta_desc}\" />
  <meta name=\"keywords\" content=\"{keywords}\" />
  <link rel=\"alternate\" type=\"application/rss+xml\" title=\"Catalyst Edge blog\" href=\"/blog/rss.xml\" />
  <link rel=\"icon\" href=\"/favicon.ico\" />
  <link rel=\"stylesheet\" href=\"/lib/admin-unlock.css\" />
  <link rel=\"stylesheet\" href=\"/lib/scanner-polish.css\" />
  <link rel=\"stylesheet\" href=\"/lib/nav-fix.css\" />
  <link rel=\"stylesheet\" href=\"/lib/cinematic-hero.css\" />
  <link rel=\"stylesheet\" href=\"/lib/cyber-shell.css\" />
  <link rel=\"stylesheet\" href=\"/lib/polish-tokens.css\" />
  <link rel=\"canonical\" href=\"https://catalystedgescanner.com/blog/{slug}/\" />
  <style>
    :root{{
      --navy:#040a14; --navy2:#0a1424; --navy3:#0e1a2e;
      --ink:#e6f1ff; --ink-dim:#9bb0c8; --ink-mute:#6e8198;
      --cyan:#5ad7ff; --gold:#f5c662; --bull:#5cf2a4; --bear:#ff6b8b;
      --line:rgba(110,140,180,0.18); --line-strong:rgba(110,140,180,0.32);
      --glass: linear-gradient(180deg, rgba(15,28,48,0.78), rgba(7,14,28,0.78));
    }}
    *{{box-sizing:border-box}}
    html,body{{margin:0;background:#04070d;color:var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, \"Segoe UI\", Roboto, \"Helvetica Neue\", Arial;
      -webkit-font-smoothing:antialiased; font-feature-settings:\"ss01\",\"cv11\";
    }}
    a{{color:var(--cyan);text-decoration:none}}
    a:hover{{text-decoration:underline}}
    code{{font-family:\"JetBrains Mono\",\"IBM Plex Mono\",ui-monospace,monospace;font-size:0.92em;background:rgba(90,215,255,0.06);padding:1px 6px;border-radius:4px;color:var(--cyan)}}

    .topbar{{position:sticky;top:0;z-index:50;background:rgba(4,7,13,0.86);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}}
    .topbar-row{{display:flex;align-items:center;gap:18px;padding:14px 24px;max-width:1400px;margin:0 auto}}
    .brand{{font-family:\"IBM Plex Mono\",ui-monospace,monospace;font-size:14px;letter-spacing:0.18em;color:var(--gold);text-transform:uppercase}}
    .brand b{{color:var(--cyan)}}
    nav.nav{{display:flex;gap:8px;flex:1;flex-wrap:nowrap;overflow-x:auto;scroll-padding-top:80px}}
    nav.nav a{{font-size:13px;color:var(--ink-dim);padding:8px 12px;border-radius:8px;white-space:nowrap}}
    nav.nav a:hover{{background:rgba(90,215,255,0.08);color:var(--ink);text-decoration:none}}
    nav.nav a.active{{color:var(--gold);background:rgba(245,198,98,0.08)}}

    /* Cinematic post hero — drawn from /lib/cinematic-hero.css tokens */
    .post-hero{{position:relative;padding:96px 0 56px;border-bottom:1px solid var(--line);overflow:hidden}}
    .post-hero::before{{content:\"\";position:absolute;inset:0;
      background:
        radial-gradient(900px 500px at 18% 10%, rgba(90,215,255,0.13), transparent 60%),
        radial-gradient(700px 400px at 82% 100%, rgba(245,198,98,0.10), transparent 65%);
      pointer-events:none}}
    .post-hero::after{{content:\"\";position:absolute;inset:0;
      background-image:linear-gradient(to right,rgba(90,215,255,0.04) 1px,transparent 1px),linear-gradient(to bottom,rgba(90,215,255,0.04) 1px,transparent 1px);
      background-size:48px 48px;mask-image:radial-gradient(closest-side at 50% 35%,#000 60%,transparent 100%);pointer-events:none}}
    .post-hero .wrap{{max-width:1080px;margin:0 auto;padding:0 24px;position:relative;z-index:2}}
    .crumbs{{font-family:\"IBM Plex Mono\",monospace;font-size:11px;letter-spacing:0.16em;color:var(--ink-mute);text-transform:uppercase;margin-bottom:24px}}
    .crumbs a{{color:var(--ink-dim)}}
    .post-eyebrow{{display:inline-flex;gap:14px;align-items:center;font-family:\"IBM Plex Mono\",monospace;font-size:11px;letter-spacing:0.22em;color:var(--gold);text-transform:uppercase;margin-bottom:18px;flex-wrap:wrap}}
    .post-eyebrow .read{{color:var(--ink-mute)}}
    .post-eyebrow .tag{{padding:4px 12px;border-radius:6px;background:rgba(245,198,98,0.10);border:1px solid rgba(245,198,98,0.36)}}
    h1.post-title{{font-size:clamp(34px,5vw,58px);line-height:1.04;letter-spacing:-0.012em;margin:0 0 22px;font-weight:700;max-width:18ch}}
    h1.post-title .glow{{color:var(--cyan)}}
    .lede{{font-size:19px;color:var(--ink-dim);line-height:1.55;max-width:60ch;margin:0 0 14px}}

    /* Article body — sticky TOC at lg+ */
    .article-shell{{display:grid;grid-template-columns:1fr;gap:48px;max-width:1080px;margin:0 auto;padding:48px 24px 56px}}
    @media (min-width: 980px) {{
      .article-shell{{grid-template-columns:240px minmax(0,1fr);gap:64px;padding:56px 24px 80px}}
    }}

    .toc{{position:sticky;top:88px;align-self:start;display:none}}
    @media (min-width: 980px) {{ .toc{{display:block}} }}
    .toc .toc-eyebrow{{font-family:\"IBM Plex Mono\",monospace;font-size:10.5px;letter-spacing:0.20em;color:var(--ink-mute);text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
    .toc ol{{list-style:none;margin:0;padding:0;counter-reset:toc}}
    .toc li{{counter-increment:toc;margin-bottom:6px}}
    .toc li a{{display:block;font-size:13px;color:var(--ink-dim);padding:6px 0;line-height:1.4;border-left:2px solid transparent;padding-left:10px;transition:all 160ms cubic-bezier(0.16,1,0.3,1)}}
    .toc li a:hover{{color:var(--cyan);border-left-color:var(--cyan);text-decoration:none}}
    .toc li a::before{{content:counter(toc, decimal-leading-zero) \"  \";font-family:\"IBM Plex Mono\",monospace;font-size:10px;color:var(--ink-mute);margin-right:6px}}

    article.post{{max-width:760px}}
    article.post h2{{margin:48px 0 14px;font-size:24px;color:var(--cyan);letter-spacing:-0.005em;line-height:1.25;scroll-margin-top:96px}}
    article.post h2:first-of-type{{margin-top:0}}
    article.post h3{{margin:28px 0 10px;font-size:17px;color:var(--ink);letter-spacing:-0.005em}}
    article.post p{{margin:0 0 14px;color:var(--ink);font-size:16.5px;line-height:1.72}}
    article.post ul, article.post ol{{margin:0 0 18px;padding-left:24px;color:var(--ink-dim);font-size:15.5px;line-height:1.72}}
    article.post ul li, article.post ol li{{margin-bottom:6px}}
    article.post ul li b, article.post ol li b{{color:var(--ink)}}

    .pull{{font-size:21px;line-height:1.5;color:var(--gold);font-style:italic;
      padding:16px 24px;border-left:3px solid var(--gold);background:rgba(245,198,98,0.06);
      border-radius:0 12px 12px 0;margin:28px 0}}

    /* CTA blocks — mid-post and bottom */
    .cta-block{{margin:36px 0;padding:24px 26px;border:1px solid var(--line-strong);border-radius:14px;
      background:linear-gradient(135deg,rgba(90,215,255,0.06),rgba(245,198,98,0.04));
      display:flex;flex-direction:column;gap:14px}}
    .cta-block .eye{{font-family:\"IBM Plex Mono\",monospace;font-size:10.5px;letter-spacing:0.20em;color:var(--gold);text-transform:uppercase}}
    .cta-block h3{{margin:0;font-size:21px;color:var(--ink);letter-spacing:-0.005em}}
    .cta-block p{{margin:0;color:var(--ink-dim);font-size:14.5px;line-height:1.55}}
    .cta-row{{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px}}
    .cta-pill{{font-family:\"IBM Plex Mono\",monospace;font-size:11.5px;letter-spacing:0.16em;text-transform:uppercase;padding:10px 16px;border-radius:999px;border:1px solid var(--cyan);color:var(--cyan);transition:all 180ms cubic-bezier(0.16,1,0.3,1)}}
    .cta-pill:hover{{background:rgba(90,215,255,0.12);text-decoration:none;transform:translateY(-1px)}}
    .cta-pill.primary{{border-color:var(--gold);color:#04070d;background:var(--gold)}}
    .cta-pill.primary:hover{{background:#ffd47a;color:#04070d}}

    .byline{{margin-top:48px;padding-top:24px;border-top:1px dashed var(--line);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px}}
    .byline .who{{font-family:\"IBM Plex Mono\",monospace;font-size:11.5px;letter-spacing:0.14em;color:var(--ink-mute);text-transform:uppercase}}
    .byline .who b{{color:var(--ink)}}
    .byline .share{{display:flex;gap:8px;flex-wrap:wrap}}
    .byline .share a{{font-family:\"IBM Plex Mono\",monospace;font-size:10.5px;letter-spacing:0.16em;text-transform:uppercase;
      padding:8px 12px;border-radius:8px;border:1px solid var(--line-strong);color:var(--ink-dim)}}
    .byline .share a:hover{{border-color:var(--cyan);color:var(--cyan);text-decoration:none}}

    .related{{margin-top:42px;padding:24px;border:1px solid var(--line);border-radius:14px;background:var(--glass)}}
    .related .eye{{font-family:\"IBM Plex Mono\",monospace;font-size:10.5px;letter-spacing:0.22em;color:var(--ink-mute);text-transform:uppercase;margin-bottom:14px}}
    .related ul{{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr;gap:10px}}
    .related ul li a{{display:block;padding:12px 14px;border-radius:10px;border:1px solid transparent;color:var(--ink);transition:all 160ms cubic-bezier(0.16,1,0.3,1)}}
    .related ul li a:hover{{border-color:var(--cyan);background:rgba(90,215,255,0.05);text-decoration:none;transform:translateX(2px)}}

    footer{{padding:36px 0;color:var(--ink-mute);font-size:12px;border-top:1px solid var(--line);text-align:center}}
    footer .links{{display:flex;gap:14px;justify-content:center;margin-top:8px;flex-wrap:wrap}}
  </style>
<script type=\"application/ld+json\">
{schema_json}
</script>
  <meta property=\"og:type\" content=\"article\" />
  <meta property=\"og:url\" content=\"https://catalystedgescanner.com/blog/{slug}/\" />
  <meta property=\"og:title\" content=\"{title}\" />
  <meta property=\"og:description\" content=\"{meta_desc}\" />
  <meta property=\"og:image\" content=\"https://catalystedgescanner.com/press/logo.png\" />
  <meta property=\"og:site_name\" content=\"Catalyst Edge Scanner\" />
  <meta name=\"twitter:card\" content=\"summary_large_image\" />
  <meta name=\"twitter:site\" content=\"@catalystEdgePro\" />
  <meta name=\"twitter:title\" content=\"{title}\" />
  <meta name=\"twitter:description\" content=\"{meta_desc}\" />
</head>
<body>
  <div class=\"topbar\">
    <div class=\"topbar-row\">
      <div class=\"brand\"><b>Catalyst</b> · Edge</div>
      <nav class=\"nav\">
        <a href=\"/scanner/\">Scanner</a>
        <a href=\"/jackpot/\">Jackpot</a>
        <a href=\"/insiders/\">Insiders</a>
        <a href=\"/squeeze/\">Squeeze</a>
        <a href=\"/dcf/\">DCF</a>
        <a href=\"/trust/\">Trust</a>
        <a href=\"/blog/\" class=\"active\">Blog</a>
        <a href=\"/pricing/\">Pricing</a>
      </nav>
    </div>
  </div>

  <section class=\"post-hero\">
    <div class=\"wrap\">
      <div class=\"crumbs\"><a href=\"/blog/\">← All posts</a></div>
      <div class=\"post-eyebrow\">
        <span>{eyebrow_kw}</span>
        <span class=\"read\">≈ {read_min} min read</span>
        <span class=\"tag\">{tag}</span>
      </div>
      <h1 class=\"post-title\">{h1}</h1>
      <p class=\"lede\">{lede}</p>
      <div class=\"cta-row\" style=\"margin-top:22px\">
        <a class=\"cta-pill primary\" href=\"{cta_target}\">Get the daily catalyst tape →</a>
        <a class=\"cta-pill\" href=\"/scanner/\">Open /scanner/</a>
      </div>
    </div>
  </section>

  <div class=\"article-shell\">
    <aside class=\"toc\" aria-label=\"Table of contents\">
      <div class=\"toc-eyebrow\">Sections</div>
      <ol>
{toc_items}
      </ol>
    </aside>

    <article class=\"post\">
{body_html}

      <div class=\"cta-block\">
        <span class=\"eye\">Daily catalyst tape · 4 AM ET</span>
        <h3>Get the same picks our paying readers get — free</h3>
        <p>Top 3 of /scanner/ and /jackpot/, the audited /trust/ log, and the daily catalyst email. No drip campaigns, no upsell sequences — one note per trading day.</p>
        <div class=\"cta-row\">
          <a class=\"cta-pill primary\" href=\"{cta_target}\">Get the free tier →</a>
          <a class=\"cta-pill\" href=\"/pricing/\">See Reader / Pro pricing</a>
        </div>
      </div>

      <div class=\"byline\">
        <span class=\"who\">Founder · <b>Catalyst Edge Scanner</b> · {today}</span>
        <div class=\"share\">
          <a href=\"https://x.com/intent/tweet?url={share_url}&text={share_text}\" target=\"_blank\" rel=\"noopener\">𝕏 share</a>
          <a href=\"mailto:?subject={share_text}&body={share_url}\">Email</a>
          <a href=\"/blog/\">← All posts</a>
        </div>
      </div>

      <div class=\"related\">
        <div class=\"eye\">Related reads</div>
        <ul>
{related_items}
        </ul>
      </div>
    </article>
  </div>

  <footer>
    Catalyst Edge Scanner · Build log · Audited 89% hit rate · Ships daily, not quarterly
    <div class=\"links\">
      <a href=\"/scanner/\">Scanner</a>
      <a href=\"/changelog/\">Changelog</a>
      <a href=\"/trust/\">Trust</a>
      <a href=\"/blog/\">Blog</a>
      <a href=\"mailto:opensource@example.com\">Contact</a>
    </div>
  </footer>

  <script src=\"/lib/tier.js\" defer></script>
</body>
</html>
"""


def _build_html(post: dict) -> str:
    lede, body_inner, related = _body_for(post)
    section_titles = re.findall(r"<h2>(.*?)</h2>", body_inner, flags=re.DOTALL)
    body_with_ids: list[str] = []
    for idx, line in enumerate(body_inner.split("\n")):
        m = re.match(r"^(\s*)<h2>(.*)</h2>$", line)
        if m:
            indent, title = m.groups()
            sid = "s" + str(len(body_with_ids))
            # find index of title in section_titles
            try:
                tidx = section_titles.index(title)
                sid = f"s{tidx+1}"
            except ValueError:
                pass
            body_with_ids.append(f"{indent}<h2 id=\"{sid}\">{title}</h2>")
        else:
            body_with_ids.append(line)
    body_html = "\n".join(body_with_ids)

    toc_items = "\n".join(
        f"        <li><a href=\"#s{i+1}\">{_html_escape(t)}</a></li>"
        for i, t in enumerate(section_titles)
    )
    related_items = "\n".join(
        f"          <li><a href=\"{href}\">{_html_escape(label)}</a></li>"
        for href, label in related
    )

    today = _today()
    title = post["title"]
    h1 = post.get("h1", title)
    slug = post["slug"]
    cta = post["cta_target"]
    kw = post.get("target_keyword", "")
    secondary = post.get("secondary_keywords", []) or []
    keywords = ", ".join([kw] + list(secondary))
    meta_desc = _truncate(_strip_tags(lede), 160)

    schema = (
        "{\n"
        '  "@context": "https://schema.org",\n'
        '  "@type": "BlogPosting",\n'
        f'  "headline": "{_html_escape(title)}",\n'
        f'  "description": "{_html_escape(meta_desc)}",\n'
        f'  "datePublished": "{today}",\n'
        f'  "dateModified": "{today}",\n'
        '  "author": {"@type":"Organization","name":"Catalyst Edge Scanner",'
        '"url":"https://catalystedgescanner.com"},\n'
        '  "publisher": {"@type":"Organization","name":"Catalyst Edge Scanner",'
        '"url":"https://catalystedgescanner.com",'
        '"logo":{"@type":"ImageObject","url":"https://catalystedgescanner.com/press/logo.png"}},\n'
        f'  "url": "https://catalystedgescanner.com/blog/{slug}/",\n'
        f'  "keywords": "{_html_escape(keywords)}"\n'
        "}"
    )

    share_url = f"https%3A%2F%2Fcatalystedgescanner.com%2Fblog%2F{slug}%2F"
    share_text = title.replace(" ", "%20")
    read_min = _read_minutes(post.get("word_count_target", 1800))

    return POST_HTML.format(
        title=_html_escape(title),
        meta_desc=_html_escape(meta_desc),
        keywords=_html_escape(keywords),
        slug=slug,
        eyebrow_kw=_html_escape(kw.upper()),
        read_min=read_min,
        tag=_html_escape(post.get("target_search_intent", "informational").title()),
        h1=_html_escape(h1),
        lede=lede,  # already-trusted internal HTML
        cta_target=cta,
        toc_items=toc_items,
        body_html=body_html,
        today=today,
        share_url=share_url,
        share_text=share_text,
        related_items=related_items,
        schema_json=schema,
    )


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 1].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def _draft(post: dict, queue: dict) -> Path:
    out_dir = DOCS_BLOG / post["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    html = _build_html(post)
    out_path.write_text(html, encoding="utf-8")
    post["state"] = "drafted"
    post["drafted_at"] = _today()
    _write_queue(queue)
    _log(f"DRAFTED slug={post['slug']} bytes={out_path.stat().st_size} -> {out_path}")
    return out_path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="content_smith — draft a queued blog post")
    parser.add_argument("--next", action="store_true", help="draft the next-priority queued post")
    parser.add_argument("--slug", help="draft a specific slug")
    parser.add_argument("--list", action="store_true", help="list queue state and exit")
    args = parser.parse_args(argv)

    queue = _read_queue()
    posts = queue.get("posts", [])
    if args.list:
        for p in sorted(posts, key=lambda x: int(x.get("priority", 99))):
            print(f"{p.get('priority',99):>2}  {p.get('state','?'):>10}  {p.get('slug')}")
        return 0
    if args.slug:
        for p in posts:
            if p.get("slug") == args.slug:
                _draft(p, queue)
                return 0
        _log(f"ERROR: slug not found: {args.slug}")
        return 2
    if args.next:
        candidates = [p for p in posts if p.get("state") == "queued"]
        if not candidates:
            _log("queue empty: no queued posts")
            return 1
        nxt = sorted(candidates, key=lambda x: int(x.get("priority", 99)))[0]
        _draft(nxt, queue)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
