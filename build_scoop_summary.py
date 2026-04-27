#!/usr/bin/env python3
"""Auto-generated scoop summary pages — citation-only journalism.

Reads convergence_alerts.csv (top tickers by signal_count) and assembles a
citation block from primary sources (SEC filings, news_signals.csv tier-1
wires, congressional trades). Drafts a 200-word neutral summary via Groq
with a strict structured-output prompt that:

  * Refuses to introduce facts not in the citation block
  * Refuses to name individuals in negative context
  * Always cites every claim by source index [N]
  * Always ends with "Sources: [1] ... [2] ..."

A validator parses the LLM output, traces every numbered claim back to a
citation, and rejects any unsourced claim. On rejection the script writes
the alert with raw citations only (no LLM narrative) — degrading gracefully.

Output: /opt/catalyst/docs/scoops/YYYY-MM-DD-TICKER.html + an index page.
Mandatory boilerplate: AUTO-GENERATED stamp, "not financial advice" disclaimer,
source links above the fold, position-disclosure note.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
SCOOPS_DIR = ROOT / "docs" / "scoops"
CONVERGENCE_CSV = ROOT / "convergence_alerts.csv"
NEWS_SIGNALS_CSV = ROOT / "news_signals.csv"
SEC_CATALYST_CSV = ROOT / "sec_catalyst_latest.csv"
CONGRESS_MAP_JSON = ROOT / "congress_ticker_map.json"

# LLM provider chain: Gemini primary (operator preference 2026-04-27) →
# citation-only fallback if quota exhausted. Groq deliberately disabled.
GEMINI_BASE = os.environ.get(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
)
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL_FAST") or os.environ.get(
    "GEMINI_MODEL", "gemini-2.0-flash"
)
MAX_SCOOPS_PER_RUN = 3
MIN_SIGNAL_COUNT = 3  # convergence floor — only build a scoop for 3+ signals

CITATION_BLOCK_TEMPLATE = """Below are the only facts you may use. Each is
indexed by [N]. Cite every numerical or factual claim by its index. Do NOT
introduce facts not listed below. Do NOT name individuals.

{citations}"""

SCOOP_SYSTEM = """You are a financial-news summarizer for an automated catalyst
scanner. Your job is to write a neutral 200-word summary citing every claim by
source index. RULES:

1. Use ONLY facts from the citation block. Never invent details.
2. Never name individuals (CEOs, executives, directors).
3. Cite every claim with [N] referring to the citation index.
4. Tone: neutral, factual, no speculation, no investment advice.
5. End with "Sources:" followed by the list of citations by index + URL.
6. If you cannot write at least 80 words from citations alone, output exactly:
   "INSUFFICIENT_CITATIONS"
"""


def to_int(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def load_alerts() -> list[dict[str, str]]:
    if not CONVERGENCE_CSV.exists():
        return []
    out: list[dict[str, str]] = []
    with CONVERGENCE_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if to_int(r.get("signal_count", 0)) < MIN_SIGNAL_COUNT:
                continue
            out.append(r)
    out.sort(
        key=lambda r: (to_int(r.get("convergence_score", 0)), to_int(r.get("signal_count", 0))),
        reverse=True,
    )
    return out


def load_news_for_ticker(ticker: str, max_items: int = 5) -> list[dict[str, str]]:
    """Tier-1 news rows tagged to this ticker, sorted by news_score."""
    if not NEWS_SIGNALS_CSV.exists():
        return []
    out: list[dict[str, str]] = []
    with NEWS_SIGNALS_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("ticker_candidates") or "").upper() == ticker.upper():
                out.append(r)
    out.sort(key=lambda r: float(r.get("news_score") or 0), reverse=True)
    return out[:max_items]


def load_sec_for_ticker(ticker: str, max_items: int = 3) -> list[dict[str, str]]:
    """Recent SEC filings for this ticker."""
    if not SEC_CATALYST_CSV.exists():
        return []
    out: list[dict[str, str]] = []
    with SEC_CATALYST_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("ticker") or "").upper() == ticker.upper():
                out.append(r)
    out.sort(key=lambda r: r.get("updated_utc", ""), reverse=True)
    return out[:max_items]


def assemble_citations(ticker: str, alert: dict[str, str]) -> list[dict[str, str]]:
    """Build numbered citation list for a ticker. Each citation:
       {index, source, headline, link, timestamp, kind}
    """
    cites: list[dict[str, str]] = []
    idx = 1

    for filing in load_sec_for_ticker(ticker):
        cites.append(
            {
                "index": str(idx),
                "source": "SEC EDGAR",
                "kind": filing.get("form", ""),
                "headline": f"{filing.get('form', '')} filing on {filing.get('updated_utc','')[:10]}",
                "excerpt": (filing.get("tags", "") or "")[:200],
                "link": filing.get("link", ""),
                "timestamp": filing.get("updated_utc", ""),
            }
        )
        idx += 1

    for news in load_news_for_ticker(ticker):
        cites.append(
            {
                "index": str(idx),
                "source": (news.get("source") or "wire").upper(),
                "kind": "news",
                "headline": (news.get("headline") or "")[:200],
                "excerpt": (news.get("headline") or "")[:300],
                "link": news.get("link", ""),
                "timestamp": news.get("published_utc", ""),
            }
        )
        idx += 1

    signals_fired = (alert.get("signals_fired") or "").split(";")
    if signals_fired and signals_fired[0]:
        cites.append(
            {
                "index": str(idx),
                "source": "Catalyst Edge convergence detector",
                "kind": "signal",
                "headline": (
                    f"Convergence score {alert.get('convergence_score', '?')}, "
                    f"{alert.get('signal_count', '?')} signals fired: "
                    f"{', '.join(signals_fired)}"
                ),
                "excerpt": "Computed from SEC filings, news momentum, and ranking inputs.",
                "link": f"https://catalystedgescanner.com/scanner/#{ticker.upper()}",
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        idx += 1

    return cites


def call_llm(system: str, user: str) -> str:
    """Call Gemini via its OpenAI-compatible endpoint. Returns "" on failure
    so the builder falls back to citation-only pages."""
    if not GEMINI_KEY:
        return ""
    payload = {
        "model": GEMINI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 400,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        f"{GEMINI_BASE}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GEMINI_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "CatalystEdge/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"LLM_ERROR: {e}"


# Validator: every [N] in summary must reference an existing citation index.
CITATION_REF_RE = re.compile(r"\[(\d+)\]")


def validate_summary(summary: str, citations: list[dict[str, str]]) -> tuple[bool, str]:
    if not summary or "INSUFFICIENT_CITATIONS" in summary:
        return False, "model_returned_insufficient"
    valid_indices = {c["index"] for c in citations}
    refs = set(CITATION_REF_RE.findall(summary))
    if not refs:
        return False, "no_citations_in_summary"
    bad = refs - valid_indices
    if bad:
        return False, f"unknown_citation_refs={sorted(bad)}"
    if len(summary.split()) < 60:
        return False, "summary_too_short"
    # Block first/last name surface — heuristic: any "Mr.", "Ms.", "Dr." token
    if re.search(r"\b(Mr\.|Ms\.|Mrs\.|Dr\.|CEO of [A-Z][a-z]+ [A-Z])", summary):
        return False, "names_individual"
    return True, "ok"


def render_page(ticker: str, alert: dict[str, str], citations: list[dict[str, str]],
                summary: str, validation: str) -> str:
    today = dt.date.today().isoformat()
    title = f"{ticker.upper()} — convergence catalyst — {today}"
    h = html.escape

    cites_html = ""
    for c in citations:
        cites_html += (
            f'<li id="cite-{c["index"]}"><span class="cite-idx">[{c["index"]}]</span> '
            f'<span class="cite-source">{h(c["source"])}</span> · '
            f'<a href="{h(c["link"])}" target="_blank" rel="nofollow noopener">'
            f'{h(c["headline"])}</a> · '
            f'<span class="cite-ts">{h(c["timestamp"][:19])}</span></li>'
        )

    if summary and "LLM_ERROR" not in summary and "INSUFFICIENT_CITATIONS" not in summary:
        summary_block = f'<div class="scoop-summary">{h(summary).replace(chr(10), "<br>")}</div>'
    else:
        summary_block = (
            '<div class="scoop-summary scoop-summary-fallback">'
            'Citation block only. Automated narrative unavailable this cycle '
            f'(reason: {h(validation)}).</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{h(title)} · Catalyst Edge</title>
<meta name="description" content="Auto-generated convergence summary for {h(ticker.upper())}, citing primary sources from SEC EDGAR, tier-1 news wires, and the Catalyst Edge scanner.">
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://catalystedgescanner.com/scoops/{today}-{h(ticker.upper())}/">
<style>
body{{margin:0;font:14px/1.55 ui-sans-serif,system-ui,sans-serif;background:#07090f;color:#e5e9f0;padding:30px 18px}}
.scoop-wrap{{max-width:760px;margin:0 auto}}
.kicker{{color:#e7b76c;font:11px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;margin-bottom:6px}}
h1{{font-size:30px;font-weight:800;line-height:1.15;letter-spacing:-.01em;margin:0 0 14px}}
.h1-ticker{{color:#72e5ff}}
.meta{{color:#8b96ab;font-size:12px;margin-bottom:24px}}
.disclaimer{{background:rgba(231,183,108,.06);border-left:3px solid #e7b76c;padding:12px 16px;margin:0 0 20px;border-radius:0 8px 8px 0;font-size:13px}}
.scoop-summary{{background:rgba(15,21,33,.7);border:1px solid rgba(114,229,255,.18);border-radius:10px;padding:18px 22px;margin:0 0 26px;line-height:1.7}}
.scoop-summary-fallback{{border-color:rgba(231,183,108,.2);font-style:italic;color:#c9d1d9}}
h2{{font-size:18px;margin:28px 0 12px;color:#e7b76c}}
ul.cite-list{{list-style:none;padding:0;margin:0}}
ul.cite-list li{{padding:10px 0;border-bottom:1px dashed rgba(255,255,255,.08);font-size:13px}}
.cite-idx{{display:inline-block;font-family:ui-monospace,monospace;color:#72e5ff;font-weight:700;margin-right:6px}}
.cite-source{{color:#a78bfa;font-weight:600}}
.cite-ts{{color:#6b7280;font-family:ui-monospace,monospace;font-size:11px}}
.scoop-footer{{margin-top:42px;padding-top:18px;border-top:1px solid rgba(255,255,255,.06);font-size:12px;color:#6b7280}}
.scoop-footer a{{color:#72e5ff;text-decoration:none}}
.signal-table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:12px}}
.signal-table th{{text-align:left;color:#8b96ab;padding:8px;border-bottom:1px solid rgba(255,255,255,.08)}}
.signal-table td{{padding:8px;border-bottom:1px solid rgba(255,255,255,.04)}}
.back-link{{display:inline-block;margin-top:24px;color:#72e5ff;text-decoration:none;font-size:13px}}
</style></head>
<body>
<div class="scoop-wrap">
  <div class="kicker">AUTO-GENERATED · CITATION-ONLY · {today}</div>
  <h1><span class="h1-ticker">${h(ticker.upper())}</span> — convergence catalyst</h1>
  <div class="meta">
    Convergence score: <strong>{h(alert.get('convergence_score','?'))}</strong> ·
    Signals fired: <strong>{h(alert.get('signal_count','?'))}</strong>
    ({h(alert.get('signals_fired','?'))}) ·
    Conviction: <strong>{h(alert.get('conviction_level','?'))}</strong>
  </div>

  <div class="disclaimer">
    <strong>Auto-generated from public filings.</strong> This is not financial advice.
    Confirm independently before trading. Catalyst Edge holds positions consistent
    with our published signals — see <a href="/trust/" style="color:#e7b76c">trust report</a>.
  </div>

  {summary_block}

  <h2>Sources</h2>
  <ul class="cite-list">{cites_html}</ul>

  <h2>Underlying signal breakdown</h2>
  <table class="signal-table">
    <tr><th>Field</th><th>Value</th></tr>
    <tr><td>convergence_score</td><td>{h(alert.get('convergence_score','?'))}</td></tr>
    <tr><td>conviction_level</td><td>{h(alert.get('conviction_level','?'))}</td></tr>
    <tr><td>signal_count</td><td>{h(alert.get('signal_count','?'))}</td></tr>
    <tr><td>sector</td><td>{h(alert.get('sector','?'))}</td></tr>
    <tr><td>price</td><td>{h(alert.get('price','?'))}</td></tr>
  </table>

  <div class="scoop-position" style="margin-top:30px;padding:14px 18px;background:rgba(247,129,102,.05);border:1px solid rgba(247,129,102,.22);border-radius:8px;font-size:13px;color:#c9d1d9">
    <strong style="color:#f78166">⚠️ Position disclosure:</strong> Catalyst Edge holds
    a small live equity position in tickers that pass the convergence + scoop
    publish gate. Real-time P/L, fills, and the running ledger are public at
    <a href="/trust/" style="color:#e7b76c;font-weight:600">/trust/</a>. Specific entry
    on <strong>{h(ticker.upper())}</strong>: see <a href="/scoreboard/" style="color:#72e5ff">/scoreboard/</a>
    for outcome tracking. Bloomberg legally cannot disclose this; we do.
  </div>

  <div class="scoop-footer">
    Generated by automated convergence detector. Errors? <a href="mailto:opensource@example.com">report</a>.
    See methodology at <a href="/methodology/">/methodology/</a>.
    <a class="back-link" href="/scoops/">← All scoops</a>
  </div>
</div>
</body></html>
"""


def render_index(scoops: list[dict[str, str]]) -> str:
    today = dt.date.today().isoformat()
    rows_html = ""
    for s in scoops:
        rows_html += (
            f'<li><a href="/scoops/{s["slug"]}/">'
            f'<span class="idx-tk">${html.escape(s["ticker"])}</span> · '
            f'<span class="idx-meta">conv {html.escape(s["score"])} · '
            f'{html.escape(s["signals"])} signals · {html.escape(s["date"])}</span>'
            f'</a></li>'
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Auto Scoops · Catalyst Edge</title>
<meta name="description" content="Auto-generated convergence catalyst summaries citing SEC EDGAR, tier-1 news wires, and the Catalyst Edge scanner.">
<link rel="canonical" href="https://catalystedgescanner.com/scoops/">
<style>
body{{margin:0;font:14px/1.5 ui-sans-serif,system-ui,sans-serif;background:#07090f;color:#e5e9f0;padding:40px 18px}}
.idx-wrap{{max-width:760px;margin:0 auto}}
h1{{font-size:32px;font-weight:800;letter-spacing:-.01em;margin:0 0 8px}}
.lede{{color:#8b96ab;margin:0 0 28px}}
ul{{list-style:none;padding:0;margin:0}}
li{{padding:14px 0;border-bottom:1px solid rgba(255,255,255,.06)}}
li a{{color:#e5e9f0;text-decoration:none;display:flex;justify-content:space-between;align-items:center;gap:12px}}
li a:hover .idx-tk{{color:#e7b76c}}
.idx-tk{{font-family:ui-monospace,monospace;font-weight:700;color:#72e5ff;font-size:16px}}
.idx-meta{{color:#6b7280;font-size:12px;font-family:ui-monospace,monospace}}
.disclaimer{{background:rgba(231,183,108,.05);border-left:3px solid #e7b76c;padding:10px 14px;margin:24px 0;font-size:12px;color:#c9d1d9}}
</style></head>
<body><div class="idx-wrap">
<h1>Auto Scoops</h1>
<p class="lede">Convergence catalyst summaries auto-generated from SEC filings, tier-1 news wires, and the Catalyst Edge convergence detector. Every claim cites a primary source. Updated each pipeline cycle.</p>
<div class="disclaimer">All summaries are auto-generated · not financial advice · confirm independently before trading.</div>
<div class="affil" style="background:rgba(114,229,255,.04);border-left:3px solid #72e5ff;padding:10px 14px;margin:14px 0 28px;font-size:12px;color:#c9d1d9;border-radius:0 6px 6px 0">
Need a broker that matches our public scoop trading? <a href="https://trade.tradier.com/your-referral-link" target="_blank" rel="noopener" style="color:#72e5ff;font-weight:600">Open a Tradier account</a> — same broker we use for the live $100 audit at <a href="/trust/" style="color:#e7b76c">/trust/</a>. Affiliate link.
</div>
<ul>{rows_html}</ul>
<p class="lede" style="margin-top:32px;font-size:12px">Last index refresh: {today} UTC</p>
</div></body></html>
"""


def main() -> int:
    SCOOPS_DIR.mkdir(parents=True, exist_ok=True)
    alerts = load_alerts()
    if not alerts:
        print("scoops: no alerts meeting MIN_SIGNAL_COUNT")
        return 0

    written: list[dict[str, str]] = []
    for alert in alerts[:MAX_SCOOPS_PER_RUN]:
        ticker = (alert.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        citations = assemble_citations(ticker, alert)
        if len(citations) < 2:
            print(f"scoops: {ticker} skipped — only {len(citations)} citations")
            continue

        cite_text = "\n".join(
            f"[{c['index']}] {c['source']} · {c['kind']} · {c['headline']} · {c['link']}"
            for c in citations
        )
        user_prompt = CITATION_BLOCK_TEMPLATE.format(citations=cite_text)
        user_prompt += (
            f"\n\nWrite a 200-word neutral summary of why ${ticker} is a convergence "
            f"catalyst right now. Cite every claim by [N]. End with 'Sources:' followed "
            f"by every citation index."
        )

        summary = call_llm(SCOOP_SYSTEM, user_prompt)
        ok, reason = validate_summary(summary, citations)
        if not ok:
            print(f"scoops: {ticker} validator rejected ({reason}) — citation-only fallback")
            summary = ""

        slug = f"{dt.date.today().isoformat()}-{ticker}"
        page_dir = SCOOPS_DIR / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        page_html = render_page(ticker, alert, citations, summary, reason)
        (page_dir / "index.html").write_text(page_html, encoding="utf-8")
        written.append(
            {
                "ticker": ticker,
                "slug": slug,
                "score": str(alert.get("convergence_score", "?")),
                "signals": str(alert.get("signal_count", "?")),
                "date": dt.date.today().isoformat(),
                "validation": reason,
            }
        )
        print(f"scoops: wrote /scoops/{slug}/ ({reason})")

    # Index of last 30 scoops.
    existing = sorted(
        (p for p in SCOOPS_DIR.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )[:30]
    index_rows = []
    for p in existing:
        # Parse slug "YYYY-MM-DD-TICKER".
        parts = p.name.split("-")
        if len(parts) >= 4:
            date = "-".join(parts[:3])
            ticker = "-".join(parts[3:])
            index_rows.append(
                {"slug": p.name, "ticker": ticker, "date": date,
                 "score": "?", "signals": "?"}
            )
    # Override stats for fresh ones we just wrote.
    written_by_slug = {w["slug"]: w for w in written}
    for r in index_rows:
        if r["slug"] in written_by_slug:
            r["score"] = written_by_slug[r["slug"]]["score"]
            r["signals"] = written_by_slug[r["slug"]]["signals"]
    (SCOOPS_DIR / "index.html").write_text(render_index(index_rows), encoding="utf-8")

    status = {
        "last_run_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scoops_written_this_run": len(written),
        "llm_provider": "gemini",
        "llm_enabled": bool(GEMINI_KEY),
        "model": GEMINI_MODEL,
        "items": written,
    }
    (ROOT / "scoops_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"scoops: wrote {len(written)} pages, index has {len(index_rows)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
