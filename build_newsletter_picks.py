#!/usr/bin/env python3
"""Build a subscriber-ready HTML newsletter from daily SEC catalyst pipeline outputs."""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).parent
NEWSLETTER_DIR = Path(__file__).parent / "newsletter"
ARCHIVE_DIR = Path(__file__).parent / "archive"
TEMPLATE_PATH = NEWSLETTER_DIR / "template.html"
TEMPLATE_PREMIUM_PATH = NEWSLETTER_DIR / "template_premium.html"


def _is_derivative(ticker: str) -> bool:
    """Exclude warrant/preferred/unit tickers from newsletter picks."""
    if "-" in ticker:
        return True
    if ticker.endswith(("WW", "WS", "WT")):
        return True
    if len(ticker) >= 5 and ticker.endswith("W"):
        return True
    return False

# Tag → human-readable catalyst description
TAG_NARRATIVE: dict[str, str] = {
    "+fda approval": "received FDA approval — a major binary catalyst that typically drives significant gap moves",
    "+fda clearance": "received FDA clearance — removing regulatory overhang and opening commercial pathway",
    "+fda breakthrough": "awarded FDA Breakthrough Therapy designation — accelerating development timeline",
    "+definitive agreement": "announced a definitive merger/acquisition agreement — expect deal premium pricing",
    "+merger agreement": "signed a definitive merger agreement — hard catalyst with defined exit price",
    "+contract award": "won a significant contract award — adds revenue visibility and backlog",
    "+awarded contract": "secured a major contract — backlog growth with immediate revenue impact",
    "+raises guidance": "raised forward guidance above consensus — management signaling strong momentum",
    "+record revenue": "reported record revenue — top-line beat with operating leverage implications",
    "+earnings beat": "beat Wall Street earnings estimates — fundamental strength confirmed",
    "+share repurchase": "announced a share buyback program — management signaling stock is undervalued",
    "+buyback": "launched a buyback program — capital return signals management confidence",
    "+dividend": "announced or raised a dividend — yield support with income investor appeal",
    "+insider_buy_p": "saw significant CEO/Director insider buying — insiders putting capital at risk alongside you",
    "+patent": "filed or received a key patent — IP moat expansion protecting competitive advantage",
    "+exclusive": "secured exclusive rights or license — defensible revenue stream with pricing power",
    "+recurring revenue": "highlighted recurring revenue growth — subscription model visibility commands premium valuation",
    "+market share gains": "reported market share gains — taking share in a competitive market",
    "+cost reduction": "announced a major cost reduction plan — margin expansion catalyst",
    "+restructuring": "initiated a strategic restructuring — operational reset for improved profitability",
    "+strategic review": "launched a formal strategic alternatives review — potential sale process underway",
    "+partnership": "announced a major strategic partnership — distribution or technology leverage",
    "+joint venture": "formed a joint venture — shared risk with accelerated market entry",
    "+guidance": "updated financial guidance — management transparency on near-term trajectory",
}

FORM_CONTEXT: dict[str, str] = {
    "8-K": "via 8-K event disclosure",
    "6-K": "via 6-K foreign private issuer disclosure",
    "4": "per Form 4 insider transaction filing",
    "SC 13D": "following Schedule 13D activist position disclosure",
    "SC 13G": "following Schedule 13G institutional position filing",
    "S-3": "via S-3 shelf registration (watch for dilution risk)",
    "424B4": "via 424B4 prospectus filing",
    "NT 10-Q": "via NT 10-Q late filing notice (potential negative catalyst)",
    "NT 10-K": "via NT 10-K late filing notice (potential negative catalyst)",
}


def fmt_price(v: str) -> str:
    try:
        return f"${float(v):.2f}"
    except (ValueError, TypeError):
        return "N/A"


def fmt_vol(v: str) -> str:
    try:
        n = float(v)
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K"
        return str(int(n))
    except (ValueError, TypeError):
        return "N/A"


def fmt_mcap(v: str) -> str:
    try:
        n = float(v)
        if n >= 1_000_000_000:
            return f"${n / 1_000_000_000:.1f}B"
        if n >= 1_000_000:
            return f"${n / 1_000_000:.0f}M"
        return f"${n:,.0f}"
    except (ValueError, TypeError):
        return "N/A"


def _company_name(ticker: str) -> str:
    """Try to resolve ticker to company name from SEC company_tickers cache."""
    try:
        import urllib.request, json as _json
        cache = ROOT / ".sec_company_names.json"
        if cache.exists():
            data = _json.loads(cache.read_text(encoding="utf-8"))
            return data.get(ticker.upper(), "")
        # Fetch from SEC (cache for future use)
        url = "https://www.sec.gov/files/company_tickers.json"
        ua = "CatalystEdge/1.0 (opensource@example.com)"
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = _json.loads(r.read())
        mapping = {v["ticker"]: v["title"] for v in raw.values()}
        cache.write_text(_json.dumps(mapping), encoding="utf-8")
        return mapping.get(ticker.upper(), "")
    except Exception:
        return ""


# Form-specific fallback narratives that sound more professional
FORM_FALLBACK = {
    "8-K": "filed a material event disclosure (8-K) — review for corporate developments",
    "6-K": "filed a foreign private issuer event disclosure (6-K)",
    "4": "reported insider transaction activity via Form 4 — watch direction",
    "SC 13D": "triggered a Schedule 13D activist disclosure — potential change of control signal",
    "SC 13G": "triggered a Schedule 13G institutional position disclosure",
    "NT 10-Q": "filed a late quarterly report notice — monitor for restatement risk",
    "NT 10-K": "filed a late annual report notice — monitor for restatement risk",
    "S-3": "filed a shelf registration statement — potential capital raise ahead",
}


def build_narrative(row: dict) -> str:
    tags_raw = row.get("tags", "")
    form = row.get("form", "")
    ticker = row.get("ticker", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    # Find first matching positive tag
    for tag in tags:
        tag_lower = tag.lower()
        for key, narrative in TAG_NARRATIVE.items():
            if key in tag_lower:
                ctx = FORM_CONTEXT.get(form, f"{form} filing")
                return f"{narrative} ({ctx})"

    # Get company name for context
    name = _company_name(ticker)
    company = f"{name} ({ticker})" if name else ticker

    # Use form-specific fallback
    fallback = FORM_FALLBACK.get(form, f"filed a fresh {form} SEC disclosure")
    return f"{company} {fallback}"


def build_editor_note() -> str:
    """Build a 2-sentence market context string from sector momentum + top headline."""
    sector_rows = []
    sector_path = ROOT / "news_sector_momentum.csv"
    if sector_path.exists():
        with sector_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        sector_rows = sorted(rows, key=lambda r: float(r.get("sector_score", 0) or 0), reverse=True)

    signals_path = ROOT / "news_signals.csv"
    top_headline = ""
    if signals_path.exists():
        with signals_path.open(newline="", encoding="utf-8") as f:
            signal_rows = list(csv.DictReader(f))
        # Sort by news_score descending, pick first meaningful headline
        # Filter out generic baseline/seasonal entries with no event tags
        signal_rows_sorted = sorted(signal_rows, key=lambda r: float(r.get("news_score", 0) or 0), reverse=True)
        generic_keywords = ("hurricane season runs", "best high-yield", "best cd rates",
                            "money market account rates", "HELOC", "gold price today",
                            "tax refund", "401(k)", "foreclosures", "divorce")
        for row in signal_rows_sorted:
            h = row.get("headline", "").strip()
            event_tags = row.get("event_tags", "").strip()
            if not h:
                continue
            if any(kw.lower() in h.lower() for kw in generic_keywords):
                continue
            # Prefer rows with event tags or short recency
            try:
                recency = float(row.get("recency_min", 99999) or 99999)
            except (ValueError, TypeError):
                recency = 99999
            if event_tags or recency < 2000:
                top_headline = h
                break
        # Fallback: just take first non-empty, non-generic headline
        if not top_headline:
            for row in signal_rows_sorted:
                h = row.get("headline", "").strip()
                if h and not any(kw.lower() in h.lower() for kw in generic_keywords):
                    top_headline = h
                    break

    # Build sector phrase
    sector_names = []
    for r in sector_rows[:2]:
        s = r.get("sector", "").replace("_", "/").title()
        if s:
            sector_names.append(s)

    if sector_names:
        sectors_str = " and ".join(sector_names)
        sentence1 = f"{sectors_str} sectors showing elevated momentum this morning, driven by ongoing macro and geopolitical catalysts."
    else:
        sentence1 = "Broad-based market momentum this morning across multiple sectors."

    if top_headline:
        # Truncate headline if very long
        if len(top_headline) > 100:
            top_headline = top_headline[:97] + "..."
        sentence2 = f"Today's macro backdrop: {top_headline}"
    else:
        sentence2 = "Today's focus: event-driven setups with SEC catalyst confirmation across gapper, value, and moat categories."

    return f"{sentence1} {sentence2}"


def _has_market_data(row: dict) -> bool:
    """Return True if the row has usable price and volume data."""
    price = row.get("price", "")
    vol = row.get("avg_vol_3m", "")
    flags = row.get("market_flags", "")
    try:
        p = float(price)
        v = float(vol)
        return p >= 1.0 and v >= 50000 and "no_market_data" not in flags
    except (ValueError, TypeError):
        return False


def read_csv(path: Path, filter_derivatives: bool = False, require_market_data: bool = False) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if filter_derivatives:
        rows = [r for r in rows if not _is_derivative(r.get("ticker", ""))]
    if require_market_data:
        rows = [r for r in rows if _has_market_data(r)]
    return rows


def read_outcome_summary() -> list[dict]:
    rows = read_csv(ROOT / "sec_outcome_summary.csv")
    # Filter to rows that have actual data (more than just list_name and rows)
    return [r for r in rows if float(r.get("rows", 0) or 0) >= 5]


def read_sector_momentum() -> list[dict]:
    rows = read_csv(ROOT / "news_sector_momentum.csv")
    return sorted(rows, key=lambda r: float(r.get("sector_score", 0) or 0), reverse=True)[:4]


MIN_TOP5_SCORE = 8.0  # minimum total_score for top 5 inclusion


def _ticker_valid(t: str) -> bool:
    """Return True if ticker looks like a genuine common equity (not derivative)."""
    if not t or len(t) < 2 or len(t) > 5:
        return False
    if _is_derivative(t):
        return False
    return True


def build_picks_json(
    gappers: list[dict],
    value: list[dict],
    moat: list[dict],
    combined: list[dict],
) -> dict:
    # Top overall picks: prefer tickers that appear in clean presets AND meet score threshold
    clean_tickers = {r["ticker"] for r in gappers + value + moat if r.get("ticker")}

    # Detect score tie: count total_score frequency — skip if 5+ tickers share same score
    from collections import Counter
    score_counts: Counter = Counter()
    for row in combined:
        try:
            score_counts[float(row.get("total_score", 0) or 0)] += 1
        except (ValueError, TypeError):
            pass
    tied_scores = {score for score, cnt in score_counts.items() if cnt >= 5}

    top5 = []
    seen = set()

    # Pass 1: combined rows in clean preset, score > threshold, not tied
    for row in combined:
        t = row.get("ticker", "")
        if not _ticker_valid(t) or t in seen:
            continue
        try:
            score = float(row.get("total_score", 0) or 0)
        except (ValueError, TypeError):
            score = 0.0
        if score < MIN_TOP5_SCORE:
            continue
        if score in tied_scores:
            continue
        if t in clean_tickers:
            top5.append(t)
            seen.add(t)
        if len(top5) >= 5:
            break

    # Pass 2: fill from clean preset without tie restriction
    if len(top5) < 5:
        for row in combined:
            t = row.get("ticker", "")
            if not _ticker_valid(t) or t in seen:
                continue
            try:
                score = float(row.get("total_score", 0) or 0)
            except (ValueError, TypeError):
                score = 0.0
            if score < MIN_TOP5_SCORE and t in clean_tickers:
                top5.append(t)
                seen.add(t)
            elif score >= MIN_TOP5_SCORE and t in clean_tickers:
                top5.append(t)
                seen.add(t)
            if len(top5) >= 5:
                break

    # Pass 3: fallback to any valid combined ticker
    if len(top5) < 5:
        for row in combined:
            t = row.get("ticker", "")
            if not _ticker_valid(t) or t in seen:
                continue
            top5.append(t)
            seen.add(t)
            if len(top5) >= 5:
                break

    return {
        "date": dt.date.today().isoformat(),
        "top5_tickers": top5,
        "gapper_count": len(gappers),
        "value_count": len(value),
        "moat_count": len(moat),
        "total_combined": len(combined),
        "top_pick": top5[0] if top5 else "",
    }


# ── HTML helpers ────────────────────────────────────────────────────────────

COLORS = {
    "header_bg": "#0d1b2a",
    "gapper": "#e94560",
    "value": "#1565c0",
    "moat": "#6a1b9a",
    "track": "#1b5e20",
    "row_alt": "#f5f5f5",
    "border": "#e0e0e0",
    "text": "#212121",
    "muted": "#757575",
    "white": "#ffffff",
}


def pill(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;background:{color};color:#fff;'
        f'font-size:11px;font-weight:700;padding:2px 8px;border-radius:12px;'
        f'letter-spacing:0.5px">{text}</span>'
    )


def section_header(title: str, subtitle: str, color: str) -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:28px">
  <tr>
    <td style="border-left:4px solid {color};padding:4px 0 4px 14px">
      <div style="font-size:18px;font-weight:800;color:{color};font-family:Arial,sans-serif">{title}</div>
      <div style="font-size:12px;color:{COLORS['muted']};font-family:Arial,sans-serif;margin-top:2px">{subtitle}</div>
    </td>
  </tr>
</table>"""


def picks_table(rows: list[dict], score_col: str, color: str, max_rows: int = 8) -> str:
    if not rows:
        return '<p style="color:#9e9e9e;font-style:italic;font-size:13px">Quality filters active — no tickers met all criteria today. The pipeline will auto-tune thresholds overnight for tomorrow\'s scan.</p>'

    html = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="border-collapse:collapse;margin-top:10px;font-family:Arial,sans-serif;font-size:13px">
  <tr style="background:{color};color:#fff">
    <th style="padding:8px 10px;text-align:left;font-weight:700">#</th>
    <th style="padding:8px 10px;text-align:left;font-weight:700">Ticker</th>
    <th style="padding:8px 10px;text-align:left;font-weight:700">Score</th>
    <th style="padding:8px 10px;text-align:left;font-weight:700">Price</th>
    <th style="padding:8px 10px;text-align:left;font-weight:700">Avg Vol</th>
    <th style="padding:8px 10px;text-align:left;font-weight:700">Catalyst</th>
  </tr>"""

    for i, row in enumerate(rows[:max_rows]):
        bg = COLORS["white"] if i % 2 == 0 else COLORS["row_alt"]
        score = row.get(score_col) or row.get("gapper_score") or "—"
        try:
            score = f"{float(score):.1f}"
        except (ValueError, TypeError):
            score = "—"
        narrative = build_narrative(row)
        html += f"""
  <tr style="background:{bg}">
    <td style="padding:8px 10px;color:{COLORS['muted']}">{i + 1}</td>
    <td style="padding:8px 10px;font-weight:800;color:{color}">{row.get('ticker','')}</td>
    <td style="padding:8px 10px;font-weight:700">{score}</td>
    <td style="padding:8px 10px">{fmt_price(row.get('price',''))}</td>
    <td style="padding:8px 10px">{fmt_vol(row.get('avg_vol_3m',''))}</td>
    <td style="padding:8px 10px;color:{COLORS['text']}">{narrative}</td>
  </tr>"""

    html += "\n</table>"
    return html


def top5_section(combined: list[dict], gappers: list[dict], value: list[dict], moat: list[dict]) -> str:
    clean_map: dict[str, dict] = {}
    for r in gappers:
        clean_map.setdefault(r["ticker"], r)
    for r in value:
        clean_map.setdefault(r["ticker"], r)
    for r in moat:
        clean_map.setdefault(r["ticker"], r)

    clean_tickers = set(clean_map)
    from collections import Counter as _Counter2
    score_counts: _Counter2 = _Counter2()
    for row in combined:
        try:
            score_counts[float(row.get("total_score", 0) or 0)] += 1
        except (ValueError, TypeError):
            pass
    tied_scores = {score for score, cnt in score_counts.items() if cnt >= 5}

    top5: list[dict] = []
    seen: set[str] = set()

    # Pass 1: clean + score threshold + not tied
    for row in combined:
        t = row.get("ticker", "")
        if not _ticker_valid(t) or t in seen:
            continue
        try:
            score = float(row.get("total_score", 0) or 0)
        except (ValueError, TypeError):
            score = 0.0
        if score >= MIN_TOP5_SCORE and score not in tied_scores and t in clean_tickers:
            top5.append(clean_map[t])
            seen.add(t)
        if len(top5) >= 5:
            break

    # Pass 2: clean + score threshold (allow ties)
    if len(top5) < 5:
        for row in combined:
            t = row.get("ticker", "")
            if not _ticker_valid(t) or t in seen:
                continue
            try:
                score = float(row.get("total_score", 0) or 0)
            except (ValueError, TypeError):
                score = 0.0
            if score >= MIN_TOP5_SCORE and t in clean_tickers:
                top5.append(clean_map[t])
                seen.add(t)
            if len(top5) >= 5:
                break

    # Pass 3: fallback to any valid combined
    if len(top5) < 5:
        for row in combined:
            t = row.get("ticker", "")
            if not _ticker_valid(t) or t in seen:
                continue
            top5.append(clean_map.get(t, row))
            seen.add(t)
            if len(top5) >= 5:
                break

    if not top5:
        return "<p>No picks available today.</p>"

    category_color = {**{r["ticker"]: COLORS["gapper"] for r in gappers},
                      **{r["ticker"]: COLORS["value"] for r in value},
                      **{r["ticker"]: COLORS["moat"] for r in moat}}

    items = ""
    for i, row in enumerate(top5):
        t = row.get("ticker", "")
        color = category_color.get(t, "#455a64")
        narrative = build_narrative(row)
        medal = ["🥇", "🥈", "🥉", "4.", "5."][i]
        cat_label = ""
        if t in {r["ticker"] for r in gappers}:
            cat_label = pill("GAPPER", COLORS["gapper"])
            score = row.get("gapper_score") or row.get("total_score") or ""
        elif t in {r["ticker"] for r in value}:
            cat_label = pill("VALUE", COLORS["value"])
            score = row.get("value_score") or row.get("total_score") or ""
        elif t in {r["ticker"] for r in moat}:
            cat_label = pill("MOAT", COLORS["moat"])
            score = row.get("moat_score") or row.get("total_score") or ""
        else:
            score = row.get("total_score") or row.get("value_score") or row.get("moat_score") or row.get("gapper_score") or ""
        try:
            score_str = f"Score: {float(score):.1f}" if float(score) > 0 else ""
        except (ValueError, TypeError):
            score_str = ""

        items += f"""
<tr>
  <td style="padding:10px 12px;border-bottom:1px solid {COLORS['border']}">
    <span style="font-size:18px;margin-right:8px">{medal}</span>
    <strong style="font-size:16px;color:{color}">{t}</strong>
    &nbsp;{cat_label}
    <span style="font-size:12px;color:{COLORS['muted']};margin-left:10px">{score_str}</span>
    <div style="font-size:13px;color:{COLORS['text']};margin-top:4px">{narrative}</div>
  </td>
</tr>"""

    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="border-collapse:collapse;border:1px solid {COLORS['border']};border-radius:4px;margin-top:10px">
  {items}
</table>"""


def track_record_section(outcome_rows: list[dict]) -> str:
    if not outcome_rows:
        return f"""
<div style="background:#f9f9f9;border:1px solid {COLORS['border']};border-radius:4px;
  padding:14px 18px;margin-top:10px;font-family:Arial,sans-serif">
  <p style="color:{COLORS['muted']};font-size:13px;margin:0">
    Track record building — data accumulates daily. Check back in 2–4 weeks for verified win rates.
  </p>
</div>"""

    header = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
  style="border-collapse:collapse;margin-top:10px;font-family:Arial,sans-serif;font-size:13px">
  <tr style="background:{COLORS['track']};color:#fff">
    <th style="padding:8px 10px;text-align:left">List</th>
    <th style="padding:8px 10px;text-align:center">Picks</th>
    <th style="padding:8px 10px;text-align:center">Hit Rate ≥3%</th>
    <th style="padding:8px 10px;text-align:center">Avg Next-Day Move</th>
  </tr>"""

    rows_html = ""
    name_map = {
        "sec_clean_gappers": "Clean Gappers",
        "sec_clean_value": "Clean Value",
        "sec_clean_moat_core": "Moat Core",
        "combined_priority": "Combined SEC+News",
    }
    for i, r in enumerate(outcome_rows[:6]):
        bg = COLORS["white"] if i % 2 == 0 else COLORS["row_alt"]
        name = name_map.get(r.get("list_name", ""), r.get("list_name", ""))
        hit = r.get("hit_rate_3pct", "—")
        try:
            hit = f"{float(hit):.1f}%"
        except (ValueError, TypeError):
            hit = "—"
        avg_move = r.get("avg_next_day_max_run_pct") or r.get("avg_max_run_pct", "—")
        try:
            avg_move = f"+{float(avg_move):.2f}%"
        except (ValueError, TypeError):
            avg_move = "—"
        rows_html += f"""
  <tr style="background:{bg}">
    <td style="padding:8px 10px;font-weight:700">{name}</td>
    <td style="padding:8px 10px;text-align:center">{r.get('rows','—')}</td>
    <td style="padding:8px 10px;text-align:center;font-weight:700;color:{COLORS['track']}">{hit}</td>
    <td style="padding:8px 10px;text-align:center">{avg_move}</td>
  </tr>"""

    return header + rows_html + "\n</table>"


def sector_section(sector_rows: list[dict]) -> str:
    if not sector_rows:
        return ""
    items = ""
    sector_colors = {
        "defense": "#b71c1c",
        "energy": "#e65100",
        "semis_ai": "#1a237e",
        "biotech": "#00695c",
        "financials": "#1b5e20",
        "transport": "#4a148c",
        "agriculture": "#33691e",
        "weather": "#0d47a1",
    }
    for r in sector_rows:
        sector = r.get("sector", "")
        color = sector_colors.get(sector, "#455a64")
        score = float(r.get("sector_score", 0) or 0)
        mentions = r.get("mentions", "")
        items += f'&nbsp;{pill(sector.upper(), color)}&nbsp;<span style="font-size:12px;color:{COLORS["muted"]}">({score:.0f} pts, {mentions} articles)</span>&nbsp; '

    return f"""
<div style="margin-top:10px;padding:12px 16px;background:#f8f9fa;border-radius:4px;
  border:1px solid {COLORS['border']};font-family:Arial,sans-serif">
  <div style="font-size:12px;font-weight:700;color:{COLORS['muted']};margin-bottom:8px;text-transform:uppercase;letter-spacing:1px">Active Sectors in Today's News</div>
  {items}
</div>"""


def render_pick_row(row: dict, medal: str, gappers: list, value: list, moat: list) -> str:
    t = row.get("ticker", "")
    gapper_tickers = {r["ticker"] for r in gappers}
    value_tickers = {r["ticker"] for r in value}
    moat_tickers = {r["ticker"] for r in moat}

    if t in gapper_tickers:
        color, cat = "#3b82f6", "GAPPER"
        cat_bg = "#3b82f6"
    elif t in value_tickers:
        color, cat = "#10b981", "VALUE"
        cat_bg = "#10b981"
    elif t in moat_tickers:
        color, cat = "#8b5cf6", "MOAT"
        cat_bg = "#8b5cf6"
    else:
        color, cat = "#64748b", "COMBINED"
        cat_bg = "#64748b"

    narrative = build_narrative(row)
    score = row.get("total_score") or row.get("value_score") or row.get("moat_score") or row.get("gapper_score") or ""
    try:
        score_str = f"{float(score):.1f}"
    except (ValueError, TypeError):
        score_str = "—"
    price = fmt_price(row.get("price", ""))

    return f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
        <tr>
          <td style="background:#f8faff;border:1px solid #e2e8f0;border-left:4px solid {color};border-radius:0 6px 6px 0;padding:14px 16px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="vertical-align:top;">
                  <table cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="padding-right:10px;vertical-align:middle;"><span style="font-size:18px;">{medal}</span></td>
                      <td style="vertical-align:middle;">
                        <span style="font-size:17px;font-weight:900;color:{color};">{t}</span>
                        &nbsp;<span style="display:inline-block;background:{cat_bg};color:#fff;font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;">{cat}</span>
                      </td>
                    </tr>
                  </table>
                  <div style="font-size:13px;color:#475569;margin-top:6px;margin-left:30px;">{narrative}</div>
                </td>
                <td align="right" style="vertical-align:top;white-space:nowrap;padding-left:12px;">
                  <div style="font-size:16px;font-weight:800;color:#0f172a;">{price}</div>
                  <div style="font-size:11px;color:#94a3b8;margin-top:2px;">Score: {score_str}</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>"""


def render_data_table(rows: list[dict], score_col: str, accent: str, max_rows: int = 7) -> str:
    if not rows:
        return '<p style="color:#94a3b8;font-style:italic;font-size:13px;padding:12px 0;">Quality filters active — no tickers met all criteria today. The pipeline will auto-tune thresholds overnight for tomorrow\'s scan.</p>'

    header_cells = ""
    for col in ["#", "Ticker", "Score", "Price", "Avg Vol", "Mkt Cap", "Catalyst / Filing"]:
        header_cells += f'<td style="padding:10px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;white-space:nowrap;">{col}</td>'

    row_html = ""
    for i, row in enumerate(rows[:max_rows]):
        bg = "#ffffff" if i % 2 == 0 else "#f8faff"
        score = row.get(score_col, "")
        try:
            score = f"{float(score):.1f}"
        except (ValueError, TypeError):
            score = "—"
        narrative = build_narrative(row)
        row_html += f"""
        <tr style="background:{bg};">
          <td style="padding:10px 12px;font-size:12px;color:#94a3b8;font-weight:600;">{i+1}</td>
          <td style="padding:10px 12px;font-size:14px;font-weight:900;color:{accent};">{row.get('ticker','')}</td>
          <td style="padding:10px 12px;font-size:13px;font-weight:700;color:#0f172a;">{score}</td>
          <td style="padding:10px 12px;font-size:13px;color:#0f172a;">{fmt_price(row.get('price',''))}</td>
          <td style="padding:10px 12px;font-size:13px;color:#475569;">{fmt_vol(row.get('avg_vol_3m',''))}</td>
          <td style="padding:10px 12px;font-size:13px;color:#475569;">{fmt_mcap(row.get('market_cap',''))}</td>
          <td style="padding:10px 12px;font-size:12px;color:#475569;">{narrative}{' <a href="' + row.get("link","") + '" style="color:#3b82f6;font-size:11px;text-decoration:none;margin-left:4px;">📄</a>' if row.get("link") else ""}</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border-radius:6px;overflow:hidden;border:1px solid #e2e8f0;">
      <tr style="background:{accent};">{header_cells}</tr>
      {row_html}
    </table>"""


def render_track_record(outcome_rows: list[dict], premium: bool = False) -> str:
    if not outcome_rows:
        return """
    <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:16px 20px;">
      <div style="font-size:13px;color:#92400e;font-weight:600;">Building track record...</div>
      <div style="font-size:12px;color:#a16207;margin-top:4px;">Track record builds automatically. After 30 days we'll show verified hit rates, avg next-day moves, and win/loss breakdown. Stay tuned.</div>
    </div>"""

    name_map = {
        "sec_clean_gappers": "⚡ Clean Gappers",
        "sec_clean_value": "💎 Clean Value",
        "sec_clean_moat_core": "🏰 Moat Core",
        "combined_priority": "🎯 Combined SEC+News",
    }

    if not premium:
        # Free tier: show only the best list's hit rate as a single summary line
        best = max(outcome_rows, key=lambda r: float(r.get("hit_rate_3pct", 0) or 0), default=None)
        if not best:
            return ""
        hit_f = float(best.get("hit_rate_3pct", 0) or 0)
        hit_color = "#16a34a" if hit_f >= 25 else "#dc2626"
        name = name_map.get(best.get("list_name", ""), best.get("list_name", ""))
        return f"""
    <div style="background:#f8faff;border:1px solid #e2e8f0;border-radius:6px;padding:14px 18px;">
      <div style="font-size:12px;color:#64748b;margin-bottom:6px;">Best performing list (last 60 days):</div>
      <div style="font-size:18px;font-weight:800;color:{hit_color};">{hit_f:.1f}% hit rate</div>
      <div style="font-size:12px;color:#64748b;margin-top:2px;">{name}</div>
      <div style="font-size:11px;color:#94a3b8;margin-top:10px;">
        ⚡ <a href="{STRIPE_UPGRADE_URL}" style="color:#6366f1;text-decoration:none;font-weight:700;">
        Premium subscribers</a> see the full breakdown — win rates, avg moves, and per-list performance across all 4 strategies.
      </div>
    </div>"""

    # Premium tier: full breakdown table with all metrics
    rows_html = ""
    for i, r in enumerate(outcome_rows[:5]):
        bg = "#ffffff" if i % 2 == 0 else "#f8faff"
        name = name_map.get(r.get("list_name", ""), r.get("list_name", ""))
        hit = r.get("hit_rate_3pct", "—")
        try:
            hit_f = float(hit)
            hit_color = "#16a34a" if hit_f >= 25 else "#dc2626"
            hit = f'<span style="color:{hit_color};font-weight:700;">{hit_f:.1f}%</span>'
        except (ValueError, TypeError):
            hit = "—"
        avg_move = r.get("avg_next_day_max_run_pct") or r.get("avg_max_run_pct", "—")
        try:
            avg_move = f"+{float(avg_move):.2f}%"
        except (ValueError, TypeError):
            avg_move = "—"
        wins = r.get("wins", "—")
        losses = r.get("losses", "—")
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:10px 14px;font-size:13px;font-weight:700;color:#0f172a;">{name}</td>
          <td style="padding:10px 14px;font-size:13px;color:#475569;text-align:center;">{r.get('rows','—')}</td>
          <td style="padding:10px 14px;font-size:13px;text-align:center;">{hit}</td>
          <td style="padding:10px 14px;font-size:13px;color:#16a34a;font-weight:600;text-align:center;">{avg_move}</td>
          <td style="padding:10px 14px;font-size:12px;color:#475569;text-align:center;">{wins}W / {losses}L</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;">
      <tr style="background:#f59e0b;">
        <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">List</td>
        <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;text-align:center;">Picks</td>
        <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;text-align:center;">Hit Rate ≥3%</td>
        <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;text-align:center;">Avg Next-Day Move</td>
        <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;text-align:center;">Win / Loss</td>
      </tr>
      {rows_html}
    </table>"""


def render_sector_strip(sector_rows: list[dict]) -> str:
    if not sector_rows:
        return ""
    sector_colors = {
        "defense": "#dc2626", "energy": "#ea580c", "semis_ai": "#4f46e5",
        "biotech": "#0d9488", "financials": "#16a34a", "transport": "#7c3aed",
        "agriculture": "#65a30d", "weather": "#0284c7",
    }
    pills = ""
    for r in sector_rows:
        s = r.get("sector", "")
        color = sector_colors.get(s, "#475569")
        score = float(r.get("sector_score", 0) or 0)
        pills += f'<span style="display:inline-block;background:{color};color:#fff;font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;margin:3px 4px 3px 0;">{s.upper()}</span><span style="font-size:11px;color:#94a3b8;margin-right:10px;">{score:.0f}pts</span>'

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0;">
      <tr>
        <td style="background:#f8faff;border:1px solid #e2e8f0;border-radius:6px;padding:14px 16px;">
          <div style="font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px;">Active Sectors in Today's News</div>
          {pills}
        </td>
      </tr>
    </table>"""


def render_income_section(income_rows: list[dict]) -> str:
    """Conservative/income investor section — dividend & buyback signals."""
    if not income_rows:
        return ""

    accent = "#0f766e"  # teal-700

    TAG_LABELS = {
        "dividend_increase": "Dividend Increase",
        "dividend_increased": "Dividend Increase",
        "raises_dividend": "Dividend Raise",
        "quarterly_dividend_declared": "Quarterly Dividend",
        "quarterly_cash_dividend": "Quarterly Dividend",
        "special_dividend": "Special Dividend",
        "special_cash_dividend": "Special Dividend",
        "cash_dividend_declared": "Dividend Declared",
        "share_repurchase": "Share Buyback",
        "buyback_program": "Buyback Program",
        "authorized_repurchase": "Buyback Authorized",
        "debt_reduction": "Debt Reduction",
        "investment_grade": "Investment Grade",
        "free_cash_flow": "FCF Signal",
        "defensive_sector": "Defensive Sector",
    }

    rows_html = ""
    for i, r in enumerate(income_rows[:6]):
        bg = "#ffffff" if i % 2 == 0 else "#f0fdfa"
        ticker = r.get("ticker", "")
        price = fmt_price(r.get("price", ""))
        avg_vol = fmt_vol(r.get("avg_vol_3m", ""))
        score = r.get("income_score", "—")
        try:
            score = f"{float(score):.0f}"
        except (ValueError, TypeError):
            score = "—"
        link = r.get("link", "")

        # Readable signal label from first positive tag
        tags_raw = r.get("tags", "")
        signal = "Income signal"
        for tag in tags_raw.split(","):
            tag = tag.strip().lstrip("+")
            label = TAG_LABELS.get(tag, "")
            if label:
                signal = label
                break

        ticker_cell = (
            f'<a href="{link}" style="color:{accent};font-weight:900;text-decoration:none;font-size:14px;">{ticker}</a>'
            if link else
            f'<span style="color:{accent};font-weight:900;font-size:14px;">{ticker}</span>'
        )
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:9px 12px;font-size:13px;color:#6b7280;">{i+1}</td>
          <td style="padding:9px 12px;">{ticker_cell}</td>
          <td style="padding:9px 12px;font-size:13px;font-weight:700;color:#0f172a;">{score}</td>
          <td style="padding:9px 12px;font-size:13px;color:#0f172a;">{price}</td>
          <td style="padding:9px 12px;font-size:13px;color:#475569;">{avg_vol}</td>
          <td style="padding:9px 12px;font-size:12px;color:#475569;">{signal}</td>
        </tr>"""

    return f"""
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:20px 0 28px 0;"></div>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td><span style="font-size:11px;font-weight:700;color:{accent};letter-spacing:2px;text-transform:uppercase;">Income Corner</span></td></tr>
      <tr><td style="padding-bottom:4px;"><span style="font-size:19px;font-weight:800;color:#0f172a;">🛡️ Conservative Income Watch</span></td></tr>
      <tr><td style="padding-bottom:16px;"><span style="font-size:12px;color:#64748b;">Dividend declarations, buyback authorizations, and balance-sheet-strength signals from today's SEC filings — for income-focused investors</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #99f6e4;border-radius:6px;overflow:hidden;">
      <tr style="background:{accent};">
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">#</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Ticker</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Score</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Price</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Avg Vol</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Signal</td>
      </tr>
      {rows_html}
    </table>"""


STRIPE_UPGRADE_URL = "https://buy.stripe.com/your-link"


def render_upgrade_wall(section: str, total: int, shown: int) -> str:
    """Blurred lock row shown at bottom of free sections to prompt upgrade."""
    locked = total - shown
    if locked <= 0:
        return ""
    label_map = {
        "gappers": (f"+{locked} more gapper plays", "Full gapper list"),
        "value": (f"+{locked} more value picks", "Full value list"),
        "moat": (f"{total} institutional moat picks", "Full moat section"),
    }
    desc, btn_label = label_map.get(section, (f"+{locked} more picks", "Upgrade"))
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:2px;">
      <tr>
        <td style="background:linear-gradient(180deg,rgba(255,255,255,0) 0%,#f8faff 40%,#f8faff 100%);
                   border:1px solid #e2e8f0;border-radius:0 0 6px 6px;padding:18px 16px;text-align:center;">
          <div style="font-size:15px;font-weight:800;color:#0f172a;margin-bottom:4px;">🔒 {desc}</div>
          <div style="font-size:12px;color:#64748b;margin-bottom:12px;">Unlock with Catalyst Edge Premium ⚡</div>
          <a href="{STRIPE_UPGRADE_URL}"
             style="display:inline-block;background:#6366f1;color:#ffffff;font-size:13px;font-weight:800;
                    text-decoration:none;padding:10px 24px;border-radius:6px;">
            {btn_label} → $9/month
          </a>
        </td>
      </tr>
    </table>"""


def render_moat_upgrade_wall(total: int) -> str:
    """Full replacement for the moat section in free newsletter."""
    if total == 0:
        return ""
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="border:1px solid #e2e8f0;border-left:4px solid #8b5cf6;border-radius:0 6px 6px 0;
                  padding:20px 24px;background:#faf5ff;">
      <tr>
        <td style="text-align:center;">
          <div style="font-size:28px;margin-bottom:8px;">🔒</div>
          <div style="font-size:16px;font-weight:800;color:#6d28d9;margin-bottom:6px;">
            {total} Institutional Moat Picks Available Today
          </div>
          <div style="font-size:12px;color:#7c3aed;margin-bottom:16px;line-height:1.6;">
            Large-cap stocks with durable competitive advantages — sourced from Form 13D and
            institutional Schedule 13G filings. Premium-only.
          </div>
          <a href="{STRIPE_UPGRADE_URL}"
             style="display:inline-block;background:#6366f1;color:#ffffff;font-size:13px;font-weight:800;
                    text-decoration:none;padding:10px 24px;border-radius:6px;">
            Unlock Moat Picks → $9/month
          </a>
        </td>
      </tr>
    </table>"""


def render_catalyst_ai_cta() -> str:
    """Render a prominent CTA banner promoting catalystedge.agency."""
    return """
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
      <tr>
        <td style="background:linear-gradient(135deg,#0f2942 0%,#1a3a5c 100%);border-radius:8px;border:1px solid rgba(99,179,237,0.3);padding:18px 24px;text-align:center;">
          <div style="font-size:13px;font-weight:700;color:#93c5fd;letter-spacing:0.5px;margin-bottom:6px;">
            🎙️ TALK TO CATALYST AI
          </div>
          <div style="font-size:12px;color:#cbd5e1;margin-bottom:12px;line-height:1.5;">
            Ask questions about today's picks, sector signals, and SEC filing patterns — in real time.
          </div>
          <a href="https://www.catalystedge.agency/" style="display:inline-block;background:#3b82f6;color:#ffffff;font-size:12px;font-weight:700;text-decoration:none;padding:8px 22px;border-radius:4px;letter-spacing:0.5px;">
            catalystedge.agency →
          </a>
        </td>
      </tr>
    </table>"""


def render_form_type_breakdown() -> str:
    """Win rate by SEC form type — premium only."""
    import json as _json
    path = ROOT / "sec_performance_breakdown.json"
    if not path.exists():
        return ""
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("form_type_stats", [])
        total = data.get("total_picks_scored", 0)
    except Exception:
        return ""
    if not rows:
        return ""

    rows_html = ""
    for i, r in enumerate(rows[:8]):
        bg = "#ffffff" if i % 2 == 0 else "#f8faff"
        hr = r["hit_rate_3pct"]
        hr_color = "#16a34a" if hr >= 35 else "#f59e0b" if hr >= 25 else "#dc2626"
        bar_w = min(int(hr), 100)
        bar = (f'<div style="background:#e2e8f0;border-radius:3px;height:6px;margin-top:4px;">'
               f'<div style="background:{hr_color};width:{bar_w}%;height:6px;border-radius:3px;"></div></div>')
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:10px 14px;font-size:13px;font-weight:700;color:#0f172a;">{r['label']}</td>
          <td style="padding:10px 14px;font-size:13px;color:#475569;text-align:center;">{r['picks']}</td>
          <td style="padding:10px 14px;text-align:center;">
            <span style="font-size:14px;font-weight:800;color:{hr_color};">{hr:.1f}%</span>
            {bar}
          </td>
          <td style="padding:10px 14px;font-size:13px;color:#16a34a;font-weight:600;text-align:center;">+{r['avg_move']:.1f}%</td>
          <td style="padding:10px 14px;font-size:12px;color:#475569;text-align:center;">{r['wins']}W / {r['losses']}L</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td><span style="font-size:11px;font-weight:700;color:#f59e0b;letter-spacing:2px;text-transform:uppercase;">⚡ Premium Intelligence</span></td></tr>
      <tr><td style="padding-bottom:4px;"><span style="font-size:19px;font-weight:800;color:#0f172a;">📋 Win Rate by SEC Filing Type</span></td></tr>
      <tr><td style="padding-bottom:16px;">
        <span style="font-size:12px;color:#64748b;">Historical hit rates across {total:,} scored picks — which form types generate the best next-day moves</span>
      </td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;">
      <tr style="background:#0f172a;">
        <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Filing Type</td>
        <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;text-align:center;">Picks</td>
        <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;text-align:center;">Hit Rate ≥3%</td>
        <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;text-align:center;">Avg Move</td>
        <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;text-align:center;">W / L</td>
      </tr>
      {rows_html}
    </table>
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:20px 0 28px 0;"></div>"""


def render_catalyst_tag_breakdown() -> str:
    """Win rate by catalyst tag — premium only."""
    import json as _json
    path = ROOT / "sec_performance_breakdown.json"
    if not path.exists():
        return ""
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("catalyst_tag_stats", [])
    except Exception:
        return ""
    if not rows:
        return ""

    cards = ""
    for r in rows[:8]:
        hr = r["hit_rate_3pct"]
        color = "#16a34a" if hr >= 35 else "#f59e0b" if hr >= 25 else "#dc2626"
        bg    = "#f0fdf4" if hr >= 35 else "#fffbeb" if hr >= 25 else "#fef2f2"
        border= "#86efac" if hr >= 35 else "#fde68a" if hr >= 25 else "#fca5a5"
        bar_w = min(int(hr), 100)
        cards += f"""
        <td style="padding:6px 4px;width:25%;vertical-align:top;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0"
                 style="background:{bg};border:1px solid {border};border-radius:6px;padding:12px 14px;">
            <tr><td style="font-size:12px;font-weight:700;color:#0f172a;padding-bottom:4px;">{r['catalyst']}</td></tr>
            <tr><td style="font-size:20px;font-weight:900;color:{color};">{hr:.1f}%</td></tr>
            <tr><td>
              <div style="background:#e2e8f0;border-radius:3px;height:5px;margin:5px 0;">
                <div style="background:{color};width:{bar_w}%;height:5px;border-radius:3px;"></div>
              </div>
            </td></tr>
            <tr><td style="font-size:11px;color:#64748b;">{r['picks']} picks · avg +{r['avg_move']:.1f}%</td></tr>
          </table>
        </td>"""

    # Group into rows of 4
    card_rows = []
    all_cards = [r for r in rows[:8]]
    for i in range(0, len(all_cards), 4):
        chunk = all_cards[i:i+4]
        cells = ""
        for r in chunk:
            hr = r["hit_rate_3pct"]
            color = "#16a34a" if hr >= 35 else "#f59e0b" if hr >= 25 else "#dc2626"
            bg    = "#f0fdf4" if hr >= 35 else "#fffbeb" if hr >= 25 else "#fef2f2"
            border= "#86efac" if hr >= 35 else "#fde68a" if hr >= 25 else "#fca5a5"
            bar_w = min(int(hr), 100)
            cells += f"""
            <td style="padding:6px 4px;width:25%;vertical-align:top;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:{bg};border:1px solid {border};border-radius:6px;padding:12px 14px;">
                <tr><td style="font-size:12px;font-weight:700;color:#0f172a;padding-bottom:4px;">{r['catalyst']}</td></tr>
                <tr><td style="font-size:20px;font-weight:900;color:{color};">{hr:.1f}%</td></tr>
                <tr><td>
                  <div style="background:#e2e8f0;border-radius:3px;height:5px;margin:5px 0;">
                    <div style="background:{color};width:{bar_w}%;height:5px;border-radius:3px;"></div>
                  </div>
                </td></tr>
                <tr><td style="font-size:11px;color:#64748b;">{r['picks']} picks · avg +{r['avg_move']:.1f}%</td></tr>
              </table>
            </td>"""
        # Pad to 4 columns
        while len(chunk) < 4:
            cells += '<td style="width:25%;padding:6px 4px;"></td>'
            chunk.append({})
        card_rows.append(f'<tr>{cells}</tr>')

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td style="padding-bottom:4px;"><span style="font-size:19px;font-weight:800;color:#0f172a;">🎯 Hit Rate by Catalyst Type</span></td></tr>
      <tr><td style="padding-bottom:16px;">
        <span style="font-size:12px;color:#64748b;">Which SEC catalyst signals have the strongest next-day performance history</span>
      </td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      {"".join(card_rows)}
    </table>
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:20px 0 28px 0;"></div>"""


def render_penny_gappers(premium: bool = False) -> str:
    """Render penny gap-up + accumulation section. Free: top 3. Premium: top 10."""
    gap_file = ROOT / "gap_scanner_top.csv"
    if not gap_file.exists():
        return ""
    try:
        rows = list(csv.DictReader(gap_file.open(newline="", encoding="utf-8")))
    except Exception:
        return ""
    if not rows:
        return ""

    limit = 10 if premium else 3
    shown = rows[:limit]

    ACCUM_COLOR = {
        "HEAVY":    ("#dc2626", "#fef2f2"),
        "ELEVATED": ("#ea580c", "#fff7ed"),
        "MODERATE": ("#d97706", "#fffbeb"),
        "NORMAL":   ("#64748b", "#f8fafc"),
    }

    rows_html = ""
    for i, r in enumerate(shown):
        bg = "#ffffff" if i % 2 == 0 else "#f8faff"
        try:
            gap   = float(r.get("effective_gap_pct", 0))
            vr    = float(r.get("vol_ratio", 0))
            score = int(r.get("gap_score", 0))
            price = float(r.get("price", 0))
        except (ValueError, TypeError):
            gap = vr = score = price = 0

        accum = r.get("accum_label", "NORMAL")
        ac, ab = ACCUM_COLOR.get(accum, ("#64748b", "#f8fafc"))
        gap_color = "#dc2626" if gap >= 10 else "#ea580c" if gap >= 5 else "#d97706"

        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:9px 12px;font-size:13px;font-weight:700;color:#0f172a;">{r.get("ticker","")}</td>
          <td style="padding:9px 12px;font-size:13px;color:#475569;text-align:center;">${price:.2f}</td>
          <td style="padding:9px 12px;font-size:13px;font-weight:700;color:{gap_color};text-align:center;">+{gap:.1f}%</td>
          <td style="padding:9px 12px;text-align:center;">
            <span style="background:{ab};color:{ac};font-size:11px;font-weight:700;padding:2px 7px;border-radius:10px;">{accum}</span>
          </td>
          <td style="padding:9px 12px;font-size:12px;color:#475569;text-align:center;">{vr:.1f}×</td>
          <td style="padding:9px 12px;font-size:12px;font-weight:700;color:#6366f1;text-align:center;">{score}</td>
        </tr>"""

    # Upgrade wall for free tier
    wall = ""
    if not premium and len(rows) > limit:
        hidden = len(rows) - limit
        wall = f"""
        <tr><td colspan="6" style="padding:12px 16px;background:linear-gradient(90deg,#0f172a,#1e1b4b);border-radius:0 0 6px 6px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td style="font-size:12px;color:#94a3b8;">
              🔒 <strong style="color:#e2e8f0;">{hidden} more penny gappers</strong> hidden — upgrade to see the full list
            </td>
            <td align="right">
              <a href="https://buy.stripe.com/your-link"
                 style="background:#6366f1;color:#fff;font-size:11px;font-weight:700;padding:5px 12px;border-radius:4px;text-decoration:none;">
                Upgrade $9/mo →
              </a>
            </td>
          </tr></table>
        </td></tr>"""

    return f"""<tr><td style="padding:0 0 4px 0;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="border:1px solid #fee2e2;border-radius:8px;overflow:hidden;">
    <tr style="background:linear-gradient(90deg,#7f1d1d,#991b1b);">
      <td style="padding:14px 16px;">
        <span style="font-size:11px;font-weight:700;color:#fca5a5;letter-spacing:1.5px;text-transform:uppercase;">⚡ Penny Gap Plays</span><br>
        <span style="font-size:15px;font-weight:800;color:#ffffff;">High-Risk · High-Reward · SEC-Confirmed</span><br>
        <span style="font-size:11px;color:#fca5a5;">Gap ≥1% · ATR-significant · Volume surge = accumulation signal</span>
      </td>
    </tr>
    <tr style="background:#fef2f2;">
      <td style="padding:0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr style="background:#fee2e2;">
            <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#991b1b;text-align:left;text-transform:uppercase;letter-spacing:1px;">Ticker</th>
            <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#991b1b;text-align:center;text-transform:uppercase;letter-spacing:1px;">Price</th>
            <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#991b1b;text-align:center;text-transform:uppercase;letter-spacing:1px;">Gap</th>
            <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#991b1b;text-align:center;text-transform:uppercase;letter-spacing:1px;">Accum</th>
            <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#991b1b;text-align:center;text-transform:uppercase;letter-spacing:1px;">Vol×</th>
            <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#991b1b;text-align:center;text-transform:uppercase;letter-spacing:1px;">Score</th>
          </tr>
          {rows_html}
          {wall}
        </table>
      </td>
    </tr>
    <tr style="background:#fef2f2;">
      <td style="padding:8px 16px;font-size:10px;color:#991b1b;">
        ⚠️ Penny stocks carry extreme risk. These are high-velocity setups, not investment advice. Always use stop-losses.
      </td>
    </tr>
  </table>
</td></tr>"""


def render_gap_track_record(premium: bool = False) -> str:
    """Gap alert track record. Free: one honest hit-rate number. Premium: full table."""
    summary_file = ROOT / "gap_outcome_summary.json"
    if not summary_file.exists():
        return ""
    try:
        s = json.loads(summary_file.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not s or s.get("total_alerts", 0) == 0:
        return ""

    total      = s.get("total_alerts", 0)
    hit10      = s.get("hit_rate_10pct", 0)
    hit20      = s.get("hit_rate_20pct", 0)
    avg2hr     = s.get("avg_max_2hr_pct", 0)
    wins       = s.get("wins", 0)
    losses     = s.get("losses", 0)
    recent_n   = s.get("recent_30d_alerts", 0)
    recent_h10 = s.get("recent_30d_hit_rate_10pct", 0)
    best_t     = s.get("best_ticker", "")
    best_pct   = s.get("best_max_2hr_pct", 0)
    best_date  = s.get("best_date", "")

    # Load tuning note from gap_scanner_config.json
    tuning_note   = ""
    week_hit      = None
    week_n        = 0
    try:
        cfg_file = ROOT / "gap_scanner_config.json"
        if cfg_file.exists():
            cfg_data    = json.loads(cfg_file.read_text(encoding="utf-8"))
            tuning_note = cfg_data.get("tuning_note", "")
            week_hit    = cfg_data.get("week_hit_rate")
            week_n      = cfg_data.get("week_alert_count", 0)
    except Exception:
        pass

    # Performance note color
    if week_hit is None:
        note_bg, note_color = "#fffbeb", "#92400e"
    elif week_hit >= 50:
        note_bg, note_color = "#f0fdf4", "#166534"
    elif week_hit >= 35:
        note_bg, note_color = "#fffbeb", "#92400e"
    else:
        note_bg, note_color = "#fef2f2", "#991b1b"

    hit_color = "#16a34a" if hit10 >= 50 else "#d97706" if hit10 >= 30 else "#dc2626"

    perf_note_html = ""
    if tuning_note:
        perf_note_html = f"""
    <tr><td colspan="2" style="padding-top:10px;">
      <div style="background:{note_bg};border-radius:6px;padding:10px 14px;">
        <span style="font-size:11px;font-weight:700;color:{note_color};text-transform:uppercase;letter-spacing:1px;">
          📋 This Week's Performance Note
        </span><br>
        <span style="font-size:12px;color:{note_color};line-height:1.6;">{tuning_note}</span>
      </div>
    </td></tr>"""

    # ── FREE version — one honest number ─────────────────────────────────
    if not premium:
        return f"""<tr><td style="padding:0 0 4px 0;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:#fafafa;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;">
    <tr>
      <td>
        <span style="font-size:11px;font-weight:700;color:#64748b;letter-spacing:1.5px;text-transform:uppercase;">⚡ Gap Alert Track Record</span><br>
        <span style="font-size:22px;font-weight:800;color:{hit_color};">{recent_h10:.0f}%</span>
        <span style="font-size:13px;color:#475569;"> of our gap alerts hit <strong>+10%</strong> within 2 hours (last 30 days · {recent_n} alerts)</span>
      </td>
      <td align="right" style="white-space:nowrap;">
        <a href="https://buy.stripe.com/your-link"
           style="background:#6366f1;color:#fff;font-size:11px;font-weight:700;
                  padding:7px 14px;border-radius:4px;text-decoration:none;">
          See every alert → Premium
        </a>
      </td>
    </tr>
    {perf_note_html}
    <tr><td colspan="2" style="padding-top:8px;font-size:11px;color:#94a3b8;">
      Premium subscribers see each alert's exact entry price, 30-min, 1-hr and 2-hr max gain, and full win/loss breakdown.
    </td></tr>
  </table>
</td></tr>"""

    # ── PREMIUM version — full breakdown ──────────────────────────────────
    recent_outcomes = s.get("recent_outcomes", [])

    rows_html = ""
    for i, r in enumerate(recent_outcomes):
        bg   = "#ffffff" if i % 2 == 0 else "#f8faff"
        pct  = float(r.get("max_2hr_pct", 0) or 0)
        out  = r.get("outcome", "")
        hit  = r.get("hit_10pct", "0") == "1"
        pct_color  = "#16a34a" if pct >= 10 else "#d97706" if pct > 0 else "#dc2626"
        out_bg     = "#f0fdf4" if hit else "#fef2f2"
        out_color  = "#16a34a" if hit else "#dc2626"
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:9px 12px;font-size:13px;font-weight:700;color:#0f172a;">{r.get("ticker","")}</td>
          <td style="padding:9px 12px;font-size:12px;color:#475569;text-align:center;">{r.get("date","")}</td>
          <td style="padding:9px 12px;font-size:12px;color:#475569;text-align:center;">${float(r.get("alert_price",0) or 0):.2f}</td>
          <td style="padding:9px 12px;font-size:13px;font-weight:700;color:{pct_color};text-align:center;">+{pct:.1f}%</td>
          <td style="padding:9px 12px;text-align:center;">
            <span style="background:{out_bg};color:{out_color};font-size:11px;font-weight:700;
                         padding:2px 8px;border-radius:10px;">{out}</span>
          </td>
        </tr>"""

    return f"""<tr><td style="padding:0 0 4px 0;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
    <tr style="background:linear-gradient(90deg,#1e1b4b,#312e81);">
      <td style="padding:14px 16px;">
        <span style="font-size:11px;font-weight:700;color:#a5b4fc;letter-spacing:1.5px;text-transform:uppercase;">⚡ Gap Alert Track Record — Premium</span><br>
        <span style="font-size:15px;font-weight:800;color:#ffffff;">Verified outcomes on every alert we fired</span>
      </td>
    </tr>
    <tr style="background:#f8fafc;">
      <td style="padding:16px 20px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td align="center" style="padding:0 12px;">
              <div style="font-size:24px;font-weight:800;color:{hit_color};">{hit10:.0f}%</div>
              <div style="font-size:11px;color:#64748b;">Hit ≥10%<br>within 2hrs</div>
            </td>
            <td align="center" style="padding:0 12px;border-left:1px solid #e2e8f0;">
              <div style="font-size:24px;font-weight:800;color:#6366f1;">{hit20:.0f}%</div>
              <div style="font-size:11px;color:#64748b;">Hit ≥20%<br>within 2hrs</div>
            </td>
            <td align="center" style="padding:0 12px;border-left:1px solid #e2e8f0;">
              <div style="font-size:24px;font-weight:800;color:#0f172a;">+{avg2hr:.1f}%</div>
              <div style="font-size:11px;color:#64748b;">Avg max gain<br>within 2hrs</div>
            </td>
            <td align="center" style="padding:0 12px;border-left:1px solid #e2e8f0;">
              <div style="font-size:24px;font-weight:800;color:#16a34a;">{wins}W</div>
              <div style="font-size:11px;color:#64748b;">{losses}L at close<br>{total} total alerts</div>
            </td>
            {"" if not best_t else f'''<td align="center" style="padding:0 12px;border-left:1px solid #e2e8f0;">
              <div style="font-size:18px;font-weight:800;color:#ea580c;">{best_t} +{best_pct:.0f}%</div>
              <div style="font-size:11px;color:#64748b;">Best alert<br>{best_date}</div>
            </td>'''}
          </tr>
        </table>
      </td>
    </tr>
    <tr><td style="padding:0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr style="background:#f1f5f9;">
          <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#475569;text-align:left;text-transform:uppercase;">Ticker</th>
          <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#475569;text-align:center;text-transform:uppercase;">Date</th>
          <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#475569;text-align:center;text-transform:uppercase;">Entry</th>
          <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#475569;text-align:center;text-transform:uppercase;">Max 2hr</th>
          <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#475569;text-align:center;text-transform:uppercase;">Result</th>
        </tr>
        {rows_html}
      </table>
    </td></tr>
    {perf_note_html}
    <tr style="background:#f8fafc;"><td style="padding:8px 16px;font-size:10px;color:#94a3b8;">
      Max 2hr = highest price reached within 2 hours of alert. Entry = price at time of alert.
      Win/Loss at close = end-of-day price vs alert price.
    </td></tr>
  </table>
</td></tr>"""


def render_congress_overlap() -> str:
    """Render congressional trade overlap section for the newsletter."""
    overlap_file = ROOT / "congressional_overlap.csv"
    if not overlap_file.exists():
        return ""
    rows = []
    with open(overlap_file, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("ticker"):
                rows.append(row)
    if not rows:
        return ""

    items_html = ""
    for r in rows[:6]:
        ticker = r.get("ticker", "")
        member = r.get("member_name", "Unknown")
        txn = r.get("transaction_type", "").upper()
        score = r.get("catalyst_score", r.get("priority_score", ""))
        amount = r.get("amount_range", "")
        txn_color = "#22c55e" if "BUY" in txn else "#ef4444" if "SELL" in txn else "#94a3b8"
        items_html += f"""
        <tr>
          <td style="padding:6px 10px;font-weight:800;color:#d4a843;font-size:15px">{ticker}</td>
          <td style="padding:6px 10px;color:{txn_color};font-weight:700;font-size:13px">{txn}</td>
          <td style="padding:6px 10px;color:#94a3b8;font-size:13px">{member}</td>
          <td style="padding:6px 10px;color:#06b6d4;font-size:13px">{score}</td>
          <td style="padding:6px 10px;color:#64748b;font-size:12px">{amount}</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0 12px">
      <tr><td style="padding:10px 16px;background:#0f1420;border-radius:8px 8px 0 0;border-bottom:2px solid #1e293b">
        <span style="font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#3b82f6;font-weight:700">🏛️ CONGRESS + SEC OVERLAP</span>
      </td></tr>
      <tr><td style="padding:12px 16px;background:#0a0d15;border-radius:0 0 8px 8px">
        <p style="color:#94a3b8;font-size:13px;margin:0 0 10px">Tickers where congressional trades align with SEC catalyst filings:</p>
        <table width="100%" cellpadding="0" cellspacing="0" style="font-family:monospace">
          <tr style="border-bottom:1px solid #1e293b">
            <th style="padding:4px 10px;color:#64748b;font-size:11px;text-align:left">TICKER</th>
            <th style="padding:4px 10px;color:#64748b;font-size:11px;text-align:left">TYPE</th>
            <th style="padding:4px 10px;color:#64748b;font-size:11px;text-align:left">MEMBER</th>
            <th style="padding:4px 10px;color:#64748b;font-size:11px;text-align:left">SCORE</th>
            <th style="padding:4px 10px;color:#64748b;font-size:11px;text-align:left">AMOUNT</th>
          </tr>
          {items_html}
        </table>
        <p style="color:#64748b;font-size:11px;margin:10px 0 0;text-align:center">
          <a href="https://catalystedgescanner.com/congress/" style="color:#d4a843;text-decoration:none">Track all congressional trades →</a>
        </p>
      </td></tr>
    </table>"""


def render_polymarket_section() -> str:
    """Render the Polymarket prediction market pulse section for the newsletter."""
    import json as _json
    pm_file = ROOT / "polymarket_signals.json"
    if not pm_file.exists():
        return ""
    try:
        data = _json.loads(pm_file.read_text(encoding="utf-8"))
        signals = data.get("signals", [])
    except Exception:
        return ""
    if not signals:
        return ""

    # Only show top 4 most relevant (by 24h volume)
    top = [s for s in signals[:6] if 1 <= s["probability"] <= 99][:4]
    if not top:
        return ""

    rows_html = ""
    for s in top:
        pct = s["probability"]
        bar_filled = int(pct / 10)
        bar_empty  = 10 - bar_filled
        bar_color  = "#ef4444" if pct >= 70 else "#f59e0b" if pct >= 40 else "#6366f1"
        prob_color = "#ef4444" if pct >= 70 else "#f59e0b" if pct >= 40 else "#94a3b8"
        title = s["title"][:72] + ("…" if len(s["title"]) > 72 else "")
        impact = s["impact"]
        rows_html += f"""
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-size:13px;color:#e2e8f0;font-weight:600;padding-bottom:4px;">{title}</td>
                <td align="right" style="font-size:16px;font-weight:800;color:{prob_color};white-space:nowrap;padding-left:12px;">{pct:.0f}%</td>
              </tr>
              <tr>
                <td colspan="2" style="padding-bottom:4px;">
                  <span style="font-family:monospace;font-size:12px;color:{bar_color};">{"█" * bar_filled}</span><span style="font-family:monospace;font-size:12px;color:#1e293b;">{"█" * bar_empty}</span>
                </td>
              </tr>
              <tr>
                <td colspan="2" style="font-size:11px;color:#64748b;">📈 Trader impact: {impact}</td>
              </tr>
            </table>
          </td>
        </tr>"""

    return f"""<tr><td style="padding:0 0 4px 0;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:#0a0f1e;border:1px solid rgba(99,102,241,0.2);border-radius:8px;padding:20px 24px;">
    <tr>
      <td style="padding-bottom:4px;">
        <span style="font-size:11px;font-weight:700;color:#818cf8;letter-spacing:1.5px;text-transform:uppercase;">Prediction Market Pulse · polymarket.com</span>
      </td>
    </tr>
    <tr>
      <td style="padding-bottom:12px;">
        <span style="font-size:16px;font-weight:800;color:#ffffff;">What the crowd is betting on</span><br>
        <span style="font-size:12px;color:#64748b;">Live odds from the world's largest prediction market — where people put real money on macro outcomes.</span>
      </td>
    </tr>
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      {rows_html}
    </table>
    <tr><td style="padding-top:10px;">
      <span style="font-size:11px;color:#475569;">These signals inform sector positioning. High-probability events = sector tailwinds/headwinds for today's picks.</span>
    </td></tr>
  </table>
</td></tr>"""


def render_how_it_works() -> str:
    return """
    <details style="margin-top:0;">
      <summary style="cursor:pointer;font-size:11px;font-weight:700;color:#64748b;letter-spacing:1px;text-transform:uppercase;list-style:none;outline:none;">
        &#9660; How We Pick
      </summary>
      <div style="font-size:12px;color:#94a3b8;line-height:1.7;margin-top:8px;padding:12px 16px;background:#0d1221;border-radius:4px;border:1px solid rgba(255,255,255,0.06);">
        Every night the pipeline scans all new SEC EDGAR filings.
        8-K events, Form 4 insider trades, and Schedule 13D activist positions are
        scored across 3 dimensions: Gapper potential, Value signals, and Moat strength.
        Only tickers passing price ($3+), volume (250K avg), and market cap ($300M+)
        filters make the clean preset lists. Combined with live news momentum scoring
        from MarketWatch, Yahoo Finance, EIA, and NOAA feeds.
      </div>
    </details>"""


def build_html_from_template(
    date_str: str,
    date_long: str,
    gappers: list[dict],
    value: list[dict],
    moat: list[dict],
    combined: list[dict],
    outcome_rows: list[dict],
    sector_rows: list[dict],
    total_tickers: int,
    cluster_rows: list[dict] | None = None,
    pre_catalyst_rows: list[dict] | None = None,
    macro_data: dict | None = None,
    short_rows: list[dict] | None = None,
    squeeze_rows: list[dict] | None = None,
    convergence_rows: list[dict] | None = None,
    deepvalue_rows: list[dict] | None = None,
    smart_money_rows: list[dict] | None = None,
    dark_pool_rows: list[dict] | None = None,
    merger_rows: list[dict] | None = None,
    lockup_rows: list[dict] | None = None,
    nt_rows: list[dict] | None = None,
    revenue_rows: list[dict] | None = None,
    income_rows: list[dict] | None = None,
    premium: bool = False,
) -> str:
    tpl_path = TEMPLATE_PREMIUM_PATH if premium and TEMPLATE_PREMIUM_PATH.exists() else TEMPLATE_PATH
    template = tpl_path.read_text(encoding="utf-8") if tpl_path.exists() else ""

    # Build top 5 with quality filters (score threshold + clean preset preference)
    clean_map: dict[str, dict] = {}
    for r in gappers + value + moat:
        clean_map.setdefault(r["ticker"], r)
    clean_tickers = set(clean_map)

    from collections import Counter as _Counter
    score_counts: _Counter = _Counter()
    for row in combined:
        try:
            score_counts[float(row.get("total_score", 0) or 0)] += 1
        except (ValueError, TypeError):
            pass
    tied_scores = {score for score, cnt in score_counts.items() if cnt >= 5}

    top5: list[dict] = []
    seen: set[str] = set()

    # Pass 1: clean preset + score >= threshold + not tied
    for row in combined:
        t = row.get("ticker", "")
        if not _ticker_valid(t) or t in seen:
            continue
        try:
            score = float(row.get("total_score", 0) or 0)
        except (ValueError, TypeError):
            score = 0.0
        if score >= MIN_TOP5_SCORE and score not in tied_scores and t in clean_tickers:
            top5.append(clean_map[t])
            seen.add(t)
        if len(top5) >= 5:
            break

    # Pass 2: clean preset regardless of tie (but still score threshold)
    if len(top5) < 5:
        for row in combined:
            t = row.get("ticker", "")
            if not _ticker_valid(t) or t in seen:
                continue
            try:
                score = float(row.get("total_score", 0) or 0)
            except (ValueError, TypeError):
                score = 0.0
            if score >= MIN_TOP5_SCORE and t in clean_tickers:
                top5.append(clean_map[t])
                seen.add(t)
            if len(top5) >= 5:
                break

    # Pass 3: fallback — any valid combined ticker
    if len(top5) < 5:
        for row in combined:
            t = row.get("ticker", "")
            if not _ticker_valid(t) or t in seen:
                continue
            top5.append(clean_map.get(t, row))
            seen.add(t)
            if len(top5) >= 5:
                break

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    picks_html = ""
    for i, row in enumerate(top5):
        picks_html += render_pick_row(row, medals[i], gappers, value, moat)

    pick1 = top5[0] if top5 else {}
    pick1_ticker = pick1.get("ticker", "—")
    pick1_narrative = build_narrative(pick1) if pick1 else "—"
    pick1_price = fmt_price(pick1.get("price", ""))
    pick1_score = pick1.get("total_score") or pick1.get("gapper_score") or ""
    try:
        pick1_score = f"{float(pick1_score):.1f}"
    except (ValueError, TypeError):
        pick1_score = "—"
    pick1_cat = "COMBINED"
    if pick1_ticker in {r["ticker"] for r in gappers}:
        pick1_cat = "GAPPER"
    elif pick1_ticker in {r["ticker"] for r in value}:
        pick1_cat = "VALUE"
    elif pick1_ticker in {r["ticker"] for r in moat}:
        pick1_cat = "MOAT"

    picks_2_to_5 = "".join(
        render_pick_row(row, medals[i], gappers, value, moat)
        for i, row in enumerate(top5[1:5], start=1)
    )

    # Fill template placeholders
    editor_note = build_editor_note()
    html = template
    html = html.replace("{{DATE_LONG}}", date_long)
    html = html.replace("{{EDITOR_NOTE}}", editor_note)
    html = html.replace("{{CATALYST_AI_CTA}}", render_catalyst_ai_cta())
    html = html.replace("{{GAPPER_COUNT}}", str(len(gappers)))
    html = html.replace("{{VALUE_COUNT}}", str(len(value)))
    html = html.replace("{{MOAT_COUNT}}", str(len(moat)))
    html = html.replace("{{TOTAL_TICKERS}}", str(total_tickers))
    html = html.replace("{{PICK1_TICKER}}", pick1_ticker)
    html = html.replace("{{PICK1_CATEGORY}}", pick1_cat)
    html = html.replace("{{PICK1_NARRATIVE}}", pick1_narrative)
    html = html.replace("{{PICK1_PRICE}}", pick1_price)
    html = html.replace("{{PICK1_SCORE}}", pick1_score)
    html = html.replace("{{PICKS_2_TO_5}}", picks_2_to_5)
    html = html.replace("{{SECTOR_STRIP}}", render_sector_strip(sector_rows))
    if premium:
        html = html.replace("{{GAPPER_TABLE}}", render_data_table(gappers, "gapper_score", "#ef4444"))
        html = html.replace("{{VALUE_TABLE}}", render_data_table(value, "value_score", "#10b981"))
        html = html.replace("{{MOAT_TABLE}}", render_data_table(moat, "moat_score", "#8b5cf6"))
    else:
        # Free tier: top 5 gappers, top 3 value, moat locked
        html = html.replace("{{GAPPER_TABLE}}",
            render_data_table(gappers[:5], "gapper_score", "#ef4444") +
            render_upgrade_wall("gappers", len(gappers), min(5, len(gappers))))
        html = html.replace("{{VALUE_TABLE}}",
            render_data_table(value[:3], "value_score", "#10b981") +
            render_upgrade_wall("value", len(value), min(3, len(value))))
        html = html.replace("{{MOAT_TABLE}}", render_moat_upgrade_wall(len(moat)))
    html = html.replace("{{TRACK_RECORD}}", render_track_record(outcome_rows, premium=premium))
    cheat_sheet_cta = (
        '<div style="margin:20px 0;padding:16px 20px;background:#0f1629;border:1px solid rgba(212,168,67,0.3);'
        'border-radius:8px;text-align:center;">'
        '<div style="font-size:11px;color:#d4a843;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:6px;">'
        'Free Download</div>'
        '<div style="font-size:15px;font-weight:700;color:#e2e8f0;margin-bottom:8px;">'
        'SEC Filing Cheat Sheet &mdash; 12 Form Types Ranked by Win Rate</div>'
        '<div style="font-size:12px;color:#94a3b8;margin-bottom:12px;">'
        '8,400+ picks backtested. Which filings have real edge? Free, instant access.</div>'
        '<a href="https://catalystedgescanner.com/cheat-sheet/" style="display:inline-block;'
        'padding:8px 24px;background:#d4a843;color:#000;font-weight:700;border-radius:6px;'
        'text-decoration:none;font-size:13px;">Download Free &rarr;</a>'
        '</div>'
    )
    html = html.replace("{{HOW_IT_WORKS}}", render_how_it_works() + cheat_sheet_cta)
    html = html.replace("{{INSIDER_CLUSTERS}}", render_insider_clusters(cluster_rows or []))
    html = html.replace("{{PRE_CATALYST_WATCHLIST}}", render_pre_catalyst(pre_catalyst_rows or []))
    html = html.replace("{{MACRO_CONTEXT}}", render_macro_context(macro_data or {}))
    html = html.replace("{{SHORT_SQUEEZE_ALERT}}", render_short_squeeze(short_rows or []))
    html = html.replace("{{SECTOR_ROTATION}}", render_sector_rotation())
    html = html.replace("{{FILING_TREND}}", render_filing_trend())
    html = html.replace("{{SQUEEZE_RADAR}}", render_squeeze_radar(squeeze_rows or []))
    html = html.replace("{{CONVERGENCE_ALERTS}}", render_convergence_alerts(convergence_rows or []))
    html = html.replace("{{DEEPVALUE_SCREEN}}", render_deepvalue_screen(deepvalue_rows or []))
    html = html.replace("{{SMART_MONEY}}", render_smart_money(smart_money_rows or []))
    html = html.replace("{{DARK_POOL}}", render_dark_pool(dark_pool_rows or []))
    html = html.replace("{{MERGER_RADAR}}", render_merger_radar(merger_rows or []))
    html = html.replace("{{LOCKUP_CALENDAR}}", render_lockup_calendar(lockup_rows or []))
    html = html.replace("{{NT_RADAR}}", render_nt_radar(nt_rows or []))
    html = html.replace("{{REVENUE_INFLECTION}}", render_revenue_inflection(revenue_rows or []))
    html = html.replace("{{INCOME_PICKS}}", render_income_section(income_rows or []))
    html = html.replace("{{CONGRESS_OVERLAP}}", render_congress_overlap())
    html = html.replace("{{POLYMARKET_SECTION}}", render_polymarket_section())
    html = html.replace("{{PENNY_GAPPERS}}", render_penny_gappers(premium=premium))
    html = html.replace("{{GAP_TRACK_RECORD}}", render_gap_track_record(premium=premium))
    if premium:
        html = html.replace("{{FORM_TYPE_BREAKDOWN}}", render_form_type_breakdown())
        html = html.replace("{{CATALYST_TAG_BREAKDOWN}}", render_catalyst_tag_breakdown())
    else:
        html = html.replace("{{FORM_TYPE_BREAKDOWN}}", "")
        html = html.replace("{{CATALYST_TAG_BREAKDOWN}}", "")

    return html


def fmt_short_vol(v) -> str:
    try:
        n = int(v)
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.0f}K"
        return str(n)
    except (ValueError, TypeError):
        return "N/A"


def render_insider_clusters(cluster_rows: list[dict]) -> str:
    """Section 4: Insider cluster buys — 2+ Form 4s at same company."""
    buys = [r for r in cluster_rows if r.get("confirmed_buy") == "1"]
    all_rows = buys + [r for r in cluster_rows if r.get("confirmed_buy") != "1"]
    if not all_rows:
        return ""

    rows_html = ""
    for i, r in enumerate(all_rows[:6]):
        bg = "#ffffff" if i % 2 == 0 else "#f8faff"
        ticker = r.get("ticker", "")
        count = r.get("filing_count", "")
        price = fmt_price(r.get("price", ""))
        is_buy = r.get("confirmed_buy") == "1"
        badge = '<span style="display:inline-block;background:#16a34a;color:#fff;font-size:10px;font-weight:700;padding:2px 7px;border-radius:20px;margin-left:6px;">BUY</span>' if is_buy else ""
        link = r.get("primary_link", "")
        ticker_cell = f'<a href="{link}" style="color:#b45309;font-weight:900;text-decoration:none;">{ticker}</a>' if link else f'<span style="color:#b45309;font-weight:900;">{ticker}</span>'
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:9px 12px;font-size:14px;">{ticker_cell}{badge}</td>
          <td style="padding:9px 12px;font-size:13px;text-align:center;font-weight:700;color:#92400e;">{count} insiders</td>
          <td style="padding:9px 12px;font-size:13px;color:#0f172a;">{price}</td>
          <td style="padding:9px 12px;font-size:12px;color:#6b7280;">Multiple Form 4 filings detected — insider conviction signal</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0;">
      <tr>
        <td style="padding-bottom:6px;">
          <span style="font-size:11px;font-weight:700;color:#b45309;letter-spacing:2px;text-transform:uppercase;">Insider Alert</span>
        </td>
      </tr>
      <tr>
        <td style="padding-bottom:16px;">
          <span style="font-size:18px;font-weight:800;color:#0f172a;">🔥 Insider Cluster Buys</span>
          <span style="font-size:12px;color:#6b7280;margin-left:10px;">2+ Form 4 filings at the same company today</span>
        </td>
      </tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #fde68a;border-radius:6px;overflow:hidden;">
      <tr style="background:#f59e0b;">
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Ticker</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;text-align:center;">Filings</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Price</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Signal</td>
      </tr>
      {rows_html}
    </table>"""


def render_pre_catalyst(catalyst_rows: list[dict]) -> str:
    """S-3/S-1/424B4 filings = upcoming capital event watchlist."""
    if not catalyst_rows:
        return ""

    rows_html = ""
    for i, r in enumerate(catalyst_rows[:6]):
        bg = "#ffffff" if i % 2 == 0 else "#fafafa"
        ticker = r.get("ticker", "")
        form = r.get("form", "")
        link = r.get("link", "")
        ticker_cell = f'<a href="{link}" style="color:#7c3aed;font-weight:900;text-decoration:none;">{ticker}</a>' if link else f'<span style="color:#7c3aed;font-weight:900;">{ticker}</span>'
        form_desc = {
            "S-3": "Shelf registration — capital raise or secondary offering ahead",
            "S-1": "IPO/direct listing registration filed",
            "424B4": "Prospectus supplement — pricing filed for offering",
        }.get(form, f"{form} pre-event filing")
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:9px 12px;font-size:14px;">{ticker_cell}</td>
          <td style="padding:9px 12px;font-size:12px;font-weight:700;color:#6d28d9;">{form}</td>
          <td style="padding:9px 12px;font-size:12px;color:#475569;">{form_desc}</td>
        </tr>"""

    return f"""
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:20px 0 28px 0;"></div>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td><span style="font-size:11px;font-weight:700;color:#7c3aed;letter-spacing:2px;text-transform:uppercase;">Section 04</span></td></tr>
      <tr><td style="padding-bottom:4px;"><span style="font-size:19px;font-weight:800;color:#0f172a;">👁 Pre-Catalyst Watchlist</span></td></tr>
      <tr><td style="padding-bottom:16px;"><span style="font-size:12px;color:#64748b;">S-3/S-1 shelf registrations filed this week — watch for upcoming capital raises or deal announcements</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;">
      <tr style="background:#7c3aed;">
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Ticker</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Form</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">What It Means</td>
      </tr>
      {rows_html}
    </table>"""


def render_macro_context(macro: dict) -> str:
    """FRED macro indicators strip."""
    if not macro:
        return ""

    items_html = ""
    order = ["DGS10", "VIXCLS", "SP500", "FEDFUNDS", "UNRATE"]
    for series_id in order:
        m = macro.get(series_id, {})
        if not m or not m.get("value"):
            continue
        val = m["value"]
        change = m.get("change") or ""
        label = m["label"]
        # Color change: green if negative for rates/VIX, positive for SP500
        change_color = "#16a34a" if change.startswith("+") else "#dc2626"
        if series_id in ("DGS10", "VIXCLS", "FEDFUNDS", "UNRATE"):
            change_color = "#dc2626" if change.startswith("+") else "#16a34a"
        change_html = f'<span style="font-size:10px;color:{change_color};margin-left:3px;">{change}</span>' if change else ""
        items_html += f"""
        <td align="center" style="padding:0 14px;border-right:1px solid #e2e8f0;">
          <div style="font-size:15px;font-weight:800;color:#0f172a;">{val}{change_html}</div>
          <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;margin-top:2px;">{label}</div>
        </td>"""

    if not items_html:
        return ""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:16px 0;">
      <tr>
        <td style="background:#f8faff;border:1px solid #e2e8f0;border-radius:6px;padding:14px 16px;">
          <div style="font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px;">📈 Macro Backdrop — Live FRED Data</div>
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>{items_html}</tr>
          </table>
        </td>
      </tr>
    </table>"""


def render_short_squeeze(short_rows: list[dict]) -> str:
    """FINRA short interest cross-reference — squeeze candidates."""
    squeeze = [r for r in short_rows if r.get("squeeze_flag") == "1"]
    if not squeeze:
        return ""

    rows_html = ""
    for i, r in enumerate(squeeze[:6]):
        bg = "#ffffff" if i % 2 == 0 else "#fff7ed"
        ticker = r.get("ticker", "")
        short_pct = r.get("short_pct", "")
        short_vol = fmt_short_vol(r.get("short_vol", ""))
        price = fmt_price(r.get("price", ""))
        link = r.get("link", "")
        ticker_cell = f'<a href="{link}" style="color:#ea580c;font-weight:900;text-decoration:none;">{ticker}</a>' if link else f'<span style="color:#ea580c;font-weight:900;">{ticker}</span>'
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:9px 12px;font-size:14px;">{ticker_cell}</td>
          <td style="padding:9px 12px;font-size:14px;font-weight:800;color:#dc2626;">{short_pct}</td>
          <td style="padding:9px 12px;font-size:13px;color:#475569;">{short_vol}</td>
          <td style="padding:9px 12px;font-size:13px;color:#0f172a;">{price}</td>
          <td style="padding:9px 12px;font-size:12px;color:#6b7280;">Catalyst + high short interest = squeeze setup</td>
        </tr>"""

    finra_date = squeeze[0].get("finra_date", "") if squeeze else ""
    return f"""
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:20px 0 28px 0;"></div>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td><span style="font-size:11px;font-weight:700;color:#ea580c;letter-spacing:2px;text-transform:uppercase;">Short Squeeze Watch</span></td></tr>
      <tr><td style="padding-bottom:4px;"><span style="font-size:19px;font-weight:800;color:#0f172a;">🎯 Squeeze Candidates</span></td></tr>
      <tr><td style="padding-bottom:16px;"><span style="font-size:12px;color:#64748b;">Pipeline picks with FINRA short ratio ≥45% — positive catalyst + high short = squeeze setup (FINRA data: {finra_date})</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #fed7aa;border-radius:6px;overflow:hidden;">
      <tr style="background:#ea580c;">
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Ticker</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Short %</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Short Vol</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Price</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Setup</td>
      </tr>
      {rows_html}
    </table>"""


def render_squeeze_radar(squeeze_rows: list[dict]) -> str:
    """Squeeze Radar — Roaring Kitty-style short squeeze detector."""
    # Show COILED and IGNITION stages only; min score 25
    candidates = [
        r for r in squeeze_rows
        if r.get("stage") in ("COILED", "IGNITION", "ACTIVE", "WATCH")
        and int(r.get("squeeze_score", 0) or 0) >= 18
    ][:6]

    if not candidates:
        return ""

    stage_colors = {
        "COILED":   "#10b981",   # green — best entry
        "IGNITION": "#f59e0b",   # amber — momentum starting
        "ACTIVE":   "#ef4444",   # red — squeeze underway
        "LATE":     "#6b7280",   # gray — exhaustion
        "WATCH":    "#64748b",
    }
    stage_desc = {
        "COILED":   "Best Entry Window",
        "IGNITION": "Momentum Starting",
        "ACTIVE":   "Squeeze Underway",
        "LATE":     "Late Stage — Caution",
        "WATCH":    "Setup Building",
    }

    rows_html = ""
    for r in candidates:
        ticker   = r.get("ticker", "")
        score    = int(r.get("squeeze_score", 0) or 0)
        stage    = r.get("stage", "WATCH")
        emoji    = r.get("stage_emoji", "👀")
        si_pct   = float(r.get("short_pct_float", 0) or 0)
        dtc      = float(r.get("days_to_cover", 0) or 0)
        activist = r.get("activist_signal", "no") == "YES"
        insider  = r.get("insider_cluster", "no") == "YES"
        gamma    = int(r.get("gamma_score", 0) or 0)
        wsb      = int(r.get("wsb_mentions", 0) or 0)
        wsb_sent = r.get("wsb_sentiment", "none")
        si_trend = float(r.get("si_trend_pct", 0) or 0)
        trend_arrow = "▲" if si_trend > 5 else ("▼" if si_trend < -5 else "→")

        stage_color = stage_colors.get(stage, "#64748b")
        stage_label = stage_desc.get(stage, stage)

        # Signal badges
        badges = ""
        if activist:
            badges += '<span style="background:#1e3a5f;color:#60a5fa;font-size:9px;font-weight:700;padding:2px 6px;border-radius:10px;margin-right:4px;">13-D ACTIVIST</span>'
        if insider:
            badges += '<span style="background:#1a3a2a;color:#34d399;font-size:9px;font-weight:700;padding:2px 6px;border-radius:10px;margin-right:4px;">INSIDER BUY</span>'
        if gamma >= 7:
            badges += '<span style="background:#2d1b4e;color:#a78bfa;font-size:9px;font-weight:700;padding:2px 6px;border-radius:10px;margin-right:4px;">GAMMA SETUP</span>'
        if wsb > 0:
            wsb_color = "#f59e0b" if wsb > 10 else "#94a3b8"
            badges += f'<span style="background:#2a1f00;color:{wsb_color};font-size:9px;font-weight:700;padding:2px 6px;border-radius:10px;margin-right:4px;">WSB {wsb} MENTIONS</span>'

        # Score bar
        bar_pct = min(100, score)
        score_bar = (
            f'<div style="background:#1e293b;border-radius:4px;height:6px;margin-top:6px;">'
            f'<div style="background:{stage_color};width:{bar_pct}%;height:6px;border-radius:4px;"></div>'
            f'</div>'
        )

        rows_html += f"""
      <tr>
        <td style="padding:12px 0;border-bottom:1px solid #1e293b;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td style="vertical-align:top;">
                <div style="margin-bottom:4px;">
                  <span style="font-size:15px;font-weight:900;color:#f1f5f9;">{emoji} {ticker}</span>
                  &nbsp;
                  <span style="display:inline-block;background:{stage_color}22;color:{stage_color};font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;border:1px solid {stage_color}44;">{stage} — {stage_label}</span>
                </div>
                <div style="margin-bottom:5px;">{badges}</div>
                <div style="font-size:11px;color:#64748b;">
                  SI: <span style="color:#f1f5f9;font-weight:700;">{si_pct:.1f}%</span> float &nbsp;·&nbsp;
                  DTC: <span style="color:#f1f5f9;font-weight:700;">{dtc:.1f}d</span> &nbsp;·&nbsp;
                  SI trend: <span style="color:{'#ef4444' if si_trend > 5 else '#10b981'};">{trend_arrow} {abs(si_trend):.0f}% MoM</span>
                  {f'&nbsp;·&nbsp; WSB: <span style="color:#f59e0b;">{wsb_sent}</span>' if wsb > 0 else ""}
                </div>
                {score_bar}
              </td>
              <td align="right" style="vertical-align:top;white-space:nowrap;padding-left:16px;">
                <div style="font-size:22px;font-weight:900;color:{stage_color};">{score}</div>
                <div style="font-size:10px;color:#64748b;">/ 100</div>
              </td>
            </tr>
          </table>
        </td>
      </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td>
        <span style="font-size:11px;font-weight:700;color:#ef4444;letter-spacing:2px;text-transform:uppercase;">Squeeze Radar</span>
      </td></tr>
      <tr><td style="padding-bottom:4px;">
        <span style="font-size:19px;font-weight:800;color:#0f172a;">🎯 Short Squeeze Hunter</span>
      </td></tr>
      <tr><td style="padding-bottom:16px;">
        <span style="font-size:12px;color:#64748b;">7-factor Roaring Kitty model — SI%, days-to-cover, activist 13-D, insider cluster, options gamma, WSB pulse, SI trend</span>
      </td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0f172a;border-radius:8px;padding:0 20px;margin-bottom:8px;">
      <tr><td style="padding:14px 0 4px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="font-size:10px;font-weight:700;color:#3b82f6;letter-spacing:1px;text-transform:uppercase;padding-bottom:8px;">TICKER / STAGE</td>
            <td align="right" style="font-size:10px;font-weight:700;color:#3b82f6;letter-spacing:1px;text-transform:uppercase;padding-bottom:8px;">SCORE</td>
          </tr>
          {rows_html}
        </table>
      </td></tr>
      <tr><td style="padding:10px 0 14px 0;">
        <span style="font-size:10px;color:#334155;font-style:italic;">
          🔒 COILED = pre-discovery, highest conviction entry &nbsp;·&nbsp;
          🔥 IGNITION = momentum starting &nbsp;·&nbsp;
          ⚡ ACTIVE = squeeze in progress
        </span>
      </td></tr>
    </table>
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:4px 0 28px 0;"></div>
"""


def render_sector_rotation(days: int = 5) -> str:
    """5-day sector momentum trend from archived news_sector_momentum files."""
    import datetime as _dt
    sector_colors = {
        "defense": "#dc2626", "energy": "#ea580c", "semis_ai": "#4f46e5",
        "biotech": "#0d9488", "financials": "#16a34a", "transport": "#7c3aed",
        "agriculture": "#65a30d", "weather": "#0284c7",
    }

    # Collect last N available dates
    history: dict[str, list[tuple[str, float]]] = {}  # sector -> [(date, score)]
    today = _dt.date.today()
    dates_checked = 0
    dates_found = 0
    d = today
    while dates_found < days and dates_checked < 14:
        dstr = d.isoformat()
        path = ROOT / f"news_sector_momentum_{dstr}.csv"
        if path.exists():
            with path.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    sector = row.get("sector", "").strip()
                    try:
                        score = float(row.get("sector_score", 0) or 0)
                    except (ValueError, TypeError):
                        score = 0.0
                    if sector:
                        history.setdefault(sector, []).append((dstr, score))
            dates_found += 1
        d -= _dt.timedelta(days=1)
        dates_checked += 1

    if not history or dates_found < 2:
        return ""

    # Get all sectors sorted by latest score
    sorted_sectors = sorted(
        history.keys(),
        key=lambda s: history[s][0][1] if history[s] else 0,
        reverse=True,
    )[:6]

    rows_html = ""
    for i, sector in enumerate(sorted_sectors):
        bg = "#ffffff" if i % 2 == 0 else "#f8faff"
        color = sector_colors.get(sector, "#475569")
        entries = sorted(history[sector], key=lambda x: x[0], reverse=True)
        latest_score = entries[0][1] if entries else 0
        prev_score = entries[1][1] if len(entries) > 1 else latest_score
        delta = latest_score - prev_score
        arrow = "↑" if delta > 2 else ("↓" if delta < -2 else "→")
        arrow_color = "#16a34a" if delta > 2 else ("#dc2626" if delta < -2 else "#94a3b8")
        # Mini sparkline as score pills
        score_pills = ""
        for date_str, score in sorted(entries, key=lambda x: x[0]):
            score_pills += f'<span style="font-size:10px;color:#94a3b8;margin-right:6px;">{date_str[5:]}: {score:.0f}</span>'

        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:9px 12px;">
            <span style="display:inline-block;background:{color};color:#fff;font-size:11px;font-weight:700;padding:3px 9px;border-radius:20px;">{sector.upper()}</span>
          </td>
          <td style="padding:9px 12px;font-size:15px;font-weight:800;color:#0f172a;">{latest_score:.0f}</td>
          <td style="padding:9px 12px;font-size:16px;font-weight:800;color:{arrow_color};">{arrow}</td>
          <td style="padding:9px 12px;font-size:11px;color:#94a3b8;">{score_pills}</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td><span style="font-size:11px;font-weight:700;color:#0284c7;letter-spacing:2px;text-transform:uppercase;">Sector Rotation</span></td></tr>
      <tr><td style="padding-bottom:4px;"><span style="font-size:19px;font-weight:800;color:#0f172a;">📊 Sector Momentum — {days}-Day View</span></td></tr>
      <tr><td style="padding-bottom:16px;"><span style="font-size:12px;color:#64748b;">Trending up ↑ or cooling off ↓ — rotate into strength</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;">
      <tr style="background:#0284c7;">
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Sector</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Today</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">Trend</td>
        <td style="padding:9px 12px;font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:0.5px;">5-Day History</td>
      </tr>
      {rows_html}
    </table>"""


def render_filing_trend() -> str:
    """Compare today's vs yesterday's filing counts by form type."""
    import datetime as _dt
    today = _dt.date.today()
    yesterday = (today - _dt.timedelta(days=1)).isoformat()
    today_str = today.isoformat()

    def count_forms(path) -> dict[str, int]:
        if not path.exists():
            return {}
        counts: dict[str, int] = {}
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                form = row.get("form", "OTHER")
                counts[form] = counts.get(form, 0) + 1
        return counts

    today_counts = count_forms(ROOT / "sec_catalyst_latest.csv")
    yesterday_counts = count_forms(ROOT / f"sec_catalyst_{yesterday}.csv")

    if not today_counts or not yesterday_counts:
        return ""

    # Focus on most important forms
    key_forms = ["8-K", "4", "S-3", "SC 13D", "6-K"]
    items = []
    for form in key_forms:
        t = today_counts.get(form, 0)
        y = yesterday_counts.get(form, 0)
        if t == 0 and y == 0:
            continue
        if y > 0:
            pct = ((t - y) / y) * 100
            sign = "+" if pct >= 0 else ""
            arrow = "↑" if pct > 5 else ("↓" if pct < -5 else "→")
            color = "#16a34a" if pct > 5 else ("#dc2626" if pct < -5 else "#94a3b8")
            items.append(f'<span style="margin-right:16px;white-space:nowrap;"><strong style="color:#0f172a;">{form}</strong> <span style="color:{color};font-weight:700;">{arrow}{sign}{pct:.0f}%</span> <span style="color:#94a3b8;font-size:11px;">({y}→{t})</span></span>')
        else:
            items.append(f'<span style="margin-right:16px;white-space:nowrap;"><strong style="color:#0f172a;">{form}</strong> <span style="color:#94a3b8;">NEW ({t})</span></span>')

    if not items:
        return ""

    return f"""
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:12px 16px;margin:12px 0;font-family:Arial,sans-serif;font-size:13px;">
      <span style="font-size:10px;font-weight:700;color:#16a34a;letter-spacing:1.5px;text-transform:uppercase;">Filing Trend vs Yesterday</span><br style="margin-bottom:6px;">
      <div style="margin-top:6px;">{''.join(items)}</div>
    </div>"""


def render_convergence_alerts(rows: list[dict]) -> str:
    """CONVERGENCE ALERTS — master signal, top of newsletter."""
    top = [r for r in rows if r.get("conviction_level") in ("MAXIMUM", "HIGH", "ELEVATED")][:5]
    if not top:
        return ""

    conviction_colors = {
        "MAXIMUM":  ("#ef4444", "#1f0505", "🔴"),
        "HIGH":     ("#f59e0b", "#1a1000", "🟠"),
        "ELEVATED": ("#3b82f6", "#050d1f", "🔵"),
        "WATCH":    ("#64748b", "#0f1117", "⚪"),
    }

    cards = ""
    for r in top:
        ticker   = r.get("ticker", "")
        score    = int(r.get("convergence_score", 0) or 0)
        level    = r.get("conviction_level", "WATCH")
        count    = int(r.get("signal_count", 0) or 0)
        fired    = r.get("signals_fired", "")
        color, bg, dot = conviction_colors.get(level, conviction_colors["WATCH"])

        # Build signal badge list
        signal_map = {
            "sec":        ("📄", "SEC Catalyst"),
            "insider":    ("👤", "Insider Buy"),
            "deepvalue":  ("💎", "Deep Value"),
            "squeeze":    ("🔒", "Squeeze Setup"),
            "smart":      ("🏦", "Smart Money"),
            "inflection": ("📈", "Rev Inflection"),
            "darkpool":   ("🕳️", "Dark Pool"),
            "nt":         ("⏰", "NT Filing"),
            "merger":     ("🤝", "M&A Signal"),
            "keyword":    ("🔑", "Key Signal"),
        }
        badges = ""
        for sig in (fired or "").split(";"):
            sig = sig.strip()
            if sig in signal_map:
                ico, lbl = signal_map[sig]
                badges += (
                    f'<span style="display:inline-block;background:{bg};color:{color};'
                    f'font-size:10px;font-weight:700;padding:3px 8px;border-radius:12px;'
                    f'border:1px solid {color}44;margin:2px 3px 2px 0;">'
                    f'{ico} {lbl}</span>'
                )

        # Score bar
        bar_w = min(100, score)
        score_bar = (
            f'<div style="background:#1e293b;border-radius:4px;height:8px;margin-top:8px;">'
            f'<div style="background:linear-gradient(90deg,{color},{color}99);'
            f'width:{bar_w}%;height:8px;border-radius:4px;"></div></div>'
        )

        cards += f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:10px;">
        <tr>
          <td style="background:{bg};border:1px solid {color}33;border-left:4px solid {color};
                     border-radius:0 8px 8px 0;padding:14px 16px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="vertical-align:top;">
                  <div style="margin-bottom:6px;">
                    {dot} <span style="font-size:17px;font-weight:900;color:#f1f5f9;">{ticker}</span>
                    &nbsp;
                    <span style="background:{color}22;color:{color};font-size:10px;font-weight:700;
                                 padding:2px 10px;border-radius:12px;border:1px solid {color}55;">
                      {level} — {count} SIGNALS
                    </span>
                  </div>
                  <div style="margin-bottom:4px;">{badges}</div>
                  {score_bar}
                </td>
                <td align="right" style="vertical-align:top;padding-left:14px;white-space:nowrap;">
                  <div style="font-size:26px;font-weight:900;color:{color};">{score}</div>
                  <div style="font-size:10px;color:#475569;">/ 100</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td><span style="font-size:11px;font-weight:700;color:#ef4444;letter-spacing:2px;text-transform:uppercase;">Intelligence Alert</span></td></tr>
      <tr><td style="padding-bottom:4px;"><span style="font-size:22px;font-weight:800;color:#0f172a;">⚡ Convergence Alerts</span></td></tr>
      <tr><td style="padding-bottom:20px;"><span style="font-size:12px;color:#64748b;">Multiple independent signal layers firing on the same ticker — the Roaring Kitty model, automated</span></td></tr>
    </table>
    {cards}
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:4px 0 28px 0;"></div>
"""


def render_deepvalue_screen(rows: list[dict]) -> str:
    """DeepValue Screen — Keith Gill's framework automated."""
    top = [r for r in rows if r.get("grade") in ("A", "B")][:6]
    if not top:
        return ""

    grade_colors = {"A": "#10b981", "B": "#3b82f6", "C": "#f59e0b", "F": "#ef4444"}

    def metric_cell(val, label, good_fn):
        try:
            fv = float(val or 0)
        except (ValueError, TypeError):
            fv = 0.0
        color = "#10b981" if good_fn(fv) else "#ef4444"
        disp  = f"{fv:.2f}" if fv != 0.0 else "N/A"
        return (
            f'<td align="center" style="padding:6px 4px;border-right:1px solid #1e293b;">'
            f'<div style="font-size:12px;font-weight:700;color:{color};">{disp}</div>'
            f'<div style="font-size:9px;color:#475569;text-transform:uppercase;margin-top:1px;">{label}</div>'
            f'</td>'
        )

    rows_html = ""
    for r in top:
        ticker = r.get("ticker", "")
        score  = int(r.get("deepvalue_score", 0) or 0)
        grade  = r.get("grade", "C")
        gc     = grade_colors.get(grade, "#64748b")
        rows_html += f"""
        <tr style="border-bottom:1px solid #f1f5f9;">
          <td style="padding:10px 12px;font-weight:800;font-size:14px;color:#0f172a;border-right:1px solid #e2e8f0;">
            {ticker}
            <div style="margin-top:2px;">
              <span style="background:{gc}22;color:{gc};font-size:10px;font-weight:700;padding:1px 7px;border-radius:10px;border:1px solid {gc}44;">
                Grade {grade} &nbsp; {score}pts
              </span>
            </div>
          </td>
          {metric_cell(r.get("pb_ratio"), "P/B", lambda v: 0 < v < 2)}
          {metric_cell(r.get("insider_own_pct"), "Insdr%", lambda v: v > 5)}
          {metric_cell(r.get("roe_pct"), "ROE%", lambda v: v > 8)}
          {metric_cell(r.get("debt_eq"), "Debt/Eq", lambda v: 0 <= v < 1)}
          {metric_cell(r.get("short_float_pct"), "SI%", lambda v: v > 10)}
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td><span style="font-size:11px;font-weight:700;color:#10b981;letter-spacing:2px;text-transform:uppercase;">Section 04</span></td></tr>
      <tr><td style="padding-bottom:4px;"><span style="font-size:19px;font-weight:800;color:#0f172a;">💎 DeepValue Screen</span></td></tr>
      <tr><td style="padding-bottom:16px;"><span style="font-size:12px;color:#64748b;">Keith Gill's 7-factor model: P/B · P/FCF · Debt/Equity · Insider Ownership · ROE · EPS growth · Short interest</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:8px;">
      <tr style="background:#f8faff;">
        <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;border-right:1px solid #e2e8f0;">TICKER</th>
        <th style="padding:8px 4px;text-align:center;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;border-right:1px solid #e2e8f0;">P/B</th>
        <th style="padding:8px 4px;text-align:center;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;border-right:1px solid #e2e8f0;">INSDR%</th>
        <th style="padding:8px 4px;text-align:center;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;border-right:1px solid #e2e8f0;">ROE%</th>
        <th style="padding:8px 4px;text-align:center;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;border-right:1px solid #e2e8f0;">DEBT/EQ</th>
        <th style="padding:8px 4px;text-align:center;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;">SI%</th>
      </tr>
      {rows_html}
    </table>
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:12px 0 28px 0;"></div>
"""


def render_smart_money(rows: list[dict]) -> str:
    """Smart Money — 13-F institutional tracker."""
    top = [r for r in rows if int(r.get("fund_count", 0) or 0) >= 2][:5]
    if not top:
        return ""

    items = ""
    for r in top:
        ticker  = r.get("ticker", "")
        funds   = int(r.get("fund_count", 0) or 0)
        name    = (r.get("latest_fund_name") or "").split("(")[0].strip()[:40]
        filed   = r.get("latest_filed_date", "")[:10]
        signal  = r.get("signal", "WATCH")
        s_color = "#10b981" if signal == "INSTITUTIONAL_INTEREST" else "#64748b"
        items += f"""
      <tr style="border-bottom:1px solid #f1f5f9;">
        <td style="padding:10px 12px;">
          <span style="font-weight:800;font-size:14px;color:#0f172a;">{ticker}</span>
          <div style="font-size:11px;color:#64748b;margin-top:2px;">Latest: {name}</div>
        </td>
        <td style="padding:10px 12px;text-align:center;">
          <div style="font-size:16px;font-weight:800;color:{s_color};">{funds}</div>
          <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;">Funds</div>
        </td>
        <td style="padding:10px 12px;text-align:right;">
          <span style="background:{s_color}15;color:{s_color};font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;">{signal.replace("_"," ")}</span>
          <div style="font-size:10px;color:#94a3b8;margin-top:3px;">{filed}</div>
        </td>
      </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td><span style="font-size:11px;font-weight:700;color:#8b5cf6;letter-spacing:2px;text-transform:uppercase;">Section 05</span></td></tr>
      <tr><td style="padding-bottom:4px;"><span style="font-size:19px;font-weight:800;color:#0f172a;">🏦 Smart Money Tracker</span></td></tr>
      <tr><td style="padding-bottom:16px;"><span style="font-size:12px;color:#64748b;">13-F filings — institutions that filed new positions in pipeline tickers this quarter</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:8px;">
      <tr style="background:#f8faff;">
        <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;">TICKER / FUND</th>
        <th style="padding:8px 12px;text-align:center;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;"># FUNDS</th>
        <th style="padding:8px 12px;text-align:right;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;">SIGNAL</th>
      </tr>
      {items}
    </table>
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:12px 0 28px 0;"></div>
"""


def render_dark_pool(rows: list[dict]) -> str:
    """Dark Pool / Volume Anomaly radar."""
    flagged = [r for r in rows if r.get("dark_pool_flag") in ("True", True)][:5]
    if not flagged:
        return ""

    sig_colors = {
        "ACCUMULATION":    ("#10b981", "Stealth Buy"),
        "UNUSUAL_VOLUME":  ("#f59e0b", "Vol Spike"),
        "STEALTH_BUILD":   ("#8b5cf6", "Buildup"),
    }

    items = ""
    for r in flagged:
        ticker = r.get("ticker", "")
        sig    = r.get("signal_type", "UNUSUAL_VOLUME")
        ratio  = float(r.get("volume_ratio", 0) or 0)
        pct    = float(r.get("price_change_pct", 0) or 0)
        color, label = sig_colors.get(sig, ("#64748b", sig))
        price_color = "#10b981" if pct > 0 else ("#ef4444" if pct < 0 else "#64748b")
        items += f"""
      <tr style="border-bottom:1px solid #f1f5f9;">
        <td style="padding:10px 12px;font-weight:800;font-size:14px;color:#0f172a;">{ticker}</td>
        <td style="padding:10px 12px;text-align:center;">
          <span style="background:{color}15;color:{color};font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;">{label}</span>
        </td>
        <td style="padding:10px 12px;text-align:center;">
          <div style="font-size:14px;font-weight:700;color:{color};">{ratio:.1f}x</div>
          <div style="font-size:9px;color:#94a3b8;">vs avg vol</div>
        </td>
        <td style="padding:10px 12px;text-align:right;">
          <div style="font-size:13px;font-weight:700;color:{price_color};">{pct:+.1f}%</div>
          <div style="font-size:9px;color:#94a3b8;">price chg</div>
        </td>
      </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td style="padding-bottom:4px;"><span style="font-size:17px;font-weight:800;color:#0f172a;">🕳️ Dark Pool Pulse</span></td></tr>
      <tr><td style="padding-bottom:14px;"><span style="font-size:12px;color:#64748b;">Volume anomalies vs 30-day average — institutions accumulate quietly before announcements</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:8px;">
      <tr style="background:#f8faff;">
        <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;">TICKER</th>
        <th style="padding:8px 12px;text-align:center;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;">SIGNAL</th>
        <th style="padding:8px 12px;text-align:center;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;">VOL RATIO</th>
        <th style="padding:8px 12px;text-align:right;font-size:10px;color:#64748b;font-weight:700;letter-spacing:1px;text-transform:uppercase;">PRICE CHG</th>
      </tr>
      {items}
    </table>
"""


def render_merger_radar(rows: list[dict]) -> str:
    """M&A pre-announcement signal radar."""
    if not rows:
        return ""

    sig_styles = {
        "TENDER_OFFER":     ("#ef4444", "🚨 TENDER OFFER"),
        "IN_PLAY":          ("#f59e0b", "🎯 IN PLAY"),
        "STRATEGIC_REVIEW": ("#8b5cf6", "🔍 STRATEGIC REVIEW"),
        "ACTIVIST_DEAL":    ("#3b82f6", "⚔️ ACTIVIST DEAL"),
    }

    cards = ""
    for r in rows[:4]:
        ticker = r.get("ticker", "")
        sig    = r.get("signal_type", "IN_PLAY")
        form   = r.get("form", "")
        date   = r.get("latest_date", "")[:10]
        desc   = r.get("description", "")
        link   = r.get("link", "#")
        color, label = sig_styles.get(sig, ("#64748b", sig))
        cards += f"""
      <tr style="border-bottom:1px solid #f1f5f9;">
        <td style="padding:10px 12px;">
          <span style="font-weight:800;font-size:14px;color:#0f172a;">{ticker}</span>
          <div style="font-size:11px;color:#64748b;margin-top:2px;">{form} · {date}</div>
        </td>
        <td style="padding:10px 12px;">
          <span style="background:{color}15;color:{color};font-size:10px;font-weight:700;padding:3px 8px;border-radius:10px;border:1px solid {color}33;">{label}</span>
          <div style="font-size:10px;color:#94a3b8;margin-top:3px;">{desc}</div>
        </td>
        <td align="right" style="padding:10px 12px;">
          <a href="{link}" style="font-size:10px;color:#3b82f6;text-decoration:none;">SEC ↗</a>
        </td>
      </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td style="padding-bottom:4px;"><span style="font-size:17px;font-weight:800;color:#0f172a;">🤝 Merger Radar</span></td></tr>
      <tr><td style="padding-bottom:14px;"><span style="font-size:12px;color:#64748b;">Tender offers, strategic reviews &amp; activist M&amp;A signals from EDGAR filings</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:8px;">
      {cards}
    </table>
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:12px 0 28px 0;"></div>
"""


def render_lockup_calendar(rows: list[dict]) -> str:
    """IPO Lockup Expiry Calendar."""
    relevant = [r for r in rows if r.get("status") in ("EXPIRES_THIS_WEEK", "UPCOMING_30D", "RECENTLY_EXPIRED")][:6]
    if not relevant:
        return ""

    status_styles = {
        "EXPIRES_THIS_WEEK": ("#ef4444", "⏰ THIS WEEK"),
        "UPCOMING_30D":      ("#f59e0b", "📅 NEXT 30 DAYS"),
        "RECENTLY_EXPIRED":  ("#64748b", "🔓 JUST EXPIRED"),
    }

    items = ""
    for r in relevant:
        ticker  = r.get("ticker", "")
        company = (r.get("company_name") or "").split("(")[0].strip()[:35]
        expiry  = r.get("lockup_expiry_date", "")[:10]
        days    = r.get("days_until_expiry", "")
        status  = r.get("status", "UPCOMING_30D")
        ins_buy = r.get("insider_bought_after") in ("True", True, "1")
        color, label = status_styles.get(status, ("#64748b", status))
        insider_badge = (
            '<span style="background:#0a2e1a;color:#10b981;font-size:9px;font-weight:700;'
            'padding:1px 6px;border-radius:8px;margin-left:4px;">INSIDER BUYING ✓</span>'
            if ins_buy else ""
        )
        items += f"""
      <tr style="border-bottom:1px solid #f1f5f9;">
        <td style="padding:9px 12px;">
          <span style="font-weight:800;font-size:13px;color:#0f172a;">{ticker}</span>{insider_badge}
          <div style="font-size:10px;color:#94a3b8;margin-top:1px;">{company}</div>
        </td>
        <td style="padding:9px 12px;text-align:center;">
          <div style="font-size:12px;font-weight:700;color:{color};">{expiry}</div>
          <div style="font-size:9px;color:#94a3b8;">{days}d</div>
        </td>
        <td align="right" style="padding:9px 12px;">
          <span style="background:{color}15;color:{color};font-size:9px;font-weight:700;padding:2px 7px;border-radius:8px;">{label}</span>
        </td>
      </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td style="padding-bottom:4px;"><span style="font-size:17px;font-weight:800;color:#0f172a;">🔓 IPO Lockup Calendar</span></td></tr>
      <tr><td style="padding-bottom:14px;"><span style="font-size:12px;color:#64748b;">180-day lockup expiries — insider action after expiry = extreme bullish signal</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:8px;">
      {items}
    </table>
"""


def render_nt_radar(rows: list[dict]) -> str:
    """NT Filing Radar — late filers with insider buying = deal signal."""
    positives = [r for r in rows if r.get("signal_type") == "POSITIVE_NT"][:4]
    cautions  = [r for r in rows if r.get("signal_type") == "CAUTION_NT"][:3]

    if not positives and not cautions:
        return ""

    def _row(r, color, icon):
        ticker  = r.get("ticker", "")
        form    = r.get("nt_form", "")
        date    = r.get("filed_date", "")[:10]
        filer   = (r.get("filer_name") or "").split("(")[0].strip()[:35]
        ins_cnt = r.get("insider_count", "")
        return (
            f'<tr style="border-bottom:1px solid #f1f5f9;">'
            f'<td style="padding:9px 12px;font-weight:800;font-size:13px;color:#0f172a;">'
            f'{icon} {ticker}<div style="font-size:10px;color:#94a3b8;font-weight:400;">{filer}</div></td>'
            f'<td style="padding:9px 12px;text-align:center;font-size:11px;color:#64748b;">{form}<br>{date}</td>'
            f'<td align="right" style="padding:9px 12px;">'
            f'<span style="background:{color}15;color:{color};font-size:9px;font-weight:700;padding:2px 7px;border-radius:8px;">'
            f'{"DEAL SIGNAL" if color=="#10b981" else "CAUTION"}'
            f'{"  Insiders: " + str(ins_cnt) if ins_cnt else ""}</span></td></tr>'
        )

    rows_html = "".join(_row(r, "#10b981", "🟢") for r in positives)
    rows_html += "".join(_row(r, "#f59e0b", "🟡") for r in cautions)

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td style="padding-bottom:4px;"><span style="font-size:17px;font-weight:800;color:#0f172a;">⏰ NT Filing Radar</span></td></tr>
      <tr><td style="padding-bottom:14px;"><span style="font-size:12px;color:#64748b;">Late filing + insider buying = deal in progress. NT alone = monitor closely.</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:8px;">
      {rows_html}
    </table>
"""


def render_revenue_inflection(rows: list[dict]) -> str:
    """Revenue Inflection — first positive 8-K after silence."""
    strong = [r for r in rows if r.get("signal_strength") in ("STRONG", "MODERATE")][:5]
    if not strong:
        return ""

    strength_colors = {"STRONG": "#10b981", "MODERATE": "#3b82f6", "MILD": "#64748b"}

    items = ""
    for r in strong:
        ticker  = r.get("ticker", "")
        kw      = r.get("positive_keyword", "")
        days    = r.get("days_since_last_positive", "?")
        strength = r.get("signal_strength", "MILD")
        form    = r.get("form", "8-K")
        link    = r.get("link", "#")
        color   = strength_colors.get(strength, "#64748b")
        items += f"""
      <tr style="border-bottom:1px solid #f1f5f9;">
        <td style="padding:10px 12px;font-weight:800;font-size:14px;color:#0f172a;">{ticker}</td>
        <td style="padding:10px 12px;">
          <span style="background:{color}15;color:{color};font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;">{strength}</span>
          <div style="font-size:11px;color:#64748b;margin-top:3px;">{kw.title()}</div>
        </td>
        <td style="padding:10px 12px;text-align:center;">
          <div style="font-size:14px;font-weight:700;color:{color};">{days}d</div>
          <div style="font-size:9px;color:#94a3b8;">silence broken</div>
        </td>
        <td align="right" style="padding:10px 12px;">
          <a href="{link}" style="font-size:10px;color:#3b82f6;text-decoration:none;">{form} ↗</a>
        </td>
      </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
      <tr><td style="padding-bottom:4px;"><span style="font-size:17px;font-weight:800;color:#0f172a;">📈 Revenue Inflection</span></td></tr>
      <tr><td style="padding-bottom:14px;"><span style="font-size:12px;color:#64748b;">First positive 8-K signal after a streak of silence — when the narrative changes, the stock re-rates</span></td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:8px;">
      {items}
    </table>
    <div style="height:28px;border-bottom:1px solid #f1f5f9;margin:12px 0 28px 0;"></div>
"""


def main() -> int:
    today = dt.date.today()
    date_str = today.isoformat()
    date_long = today.strftime("%A, %B %d, %Y")

    gappers = read_csv(ROOT / "sec_clean_gappers.csv", filter_derivatives=True, require_market_data=True)
    value = read_csv(ROOT / "sec_clean_value.csv", filter_derivatives=True, require_market_data=True)
    moat = read_csv(ROOT / "sec_clean_moat_core.csv", filter_derivatives=True, require_market_data=True)
    combined = read_csv(ROOT / "combined_priority.csv", filter_derivatives=True)
    outcome_rows = read_outcome_summary()
    sector_rows = read_sector_momentum()
    total_tickers = len(read_csv(ROOT / "sec_catalyst_latest.csv"))

    # Load enhancement data
    cluster_rows = read_csv(ROOT / "insider_clusters.csv") if (ROOT / "insider_clusters.csv").exists() else []
    short_rows = read_csv(ROOT / "short_interest.csv") if (ROOT / "short_interest.csv").exists() else []
    squeeze_rows = read_csv(ROOT / "squeeze_candidates.csv") if (ROOT / "squeeze_candidates.csv").exists() else []

    # Load 8 intelligence layers
    def _load(name: str) -> list[dict]:
        p = ROOT / name
        return read_csv(p) if p.exists() else []

    congress_overlap = _load("congressional_overlap.csv")
    convergence_rows = _load("convergence_alerts.csv")
    deepvalue_rows   = _load("deepvalue_screen.csv")
    smart_money_rows = _load("smart_money.csv")
    dark_pool_rows   = _load("dark_pool.csv")
    merger_rows      = _load("merger_signals.csv")
    lockup_rows      = _load("lockup_calendar.csv")
    nt_rows          = _load("nt_radar.csv")
    revenue_rows     = _load("revenue_inflection.csv")
    income_rows      = _load("sec_income_picks.csv")

    # Pre-catalyst: S-3/S-1/424B4 from today's catalyst list
    catalyst_latest = read_csv(ROOT / "sec_catalyst_latest.csv")
    pre_catalyst_rows = [r for r in catalyst_latest if r.get("form") in ("S-3", "S-1", "424B4")][:8]

    # Macro context
    macro_data: dict = {}
    macro_path = ROOT / "macro_context.json"
    if macro_path.exists():
        try:
            macro_data = json.loads(macro_path.read_text(encoding="utf-8"))
        except Exception:
            macro_data = {}

    picks = build_picks_json(gappers, value, moat, combined)

    shared_kwargs = dict(
        cluster_rows=cluster_rows,
        pre_catalyst_rows=pre_catalyst_rows,
        macro_data=macro_data,
        short_rows=short_rows,
        squeeze_rows=squeeze_rows,
        convergence_rows=convergence_rows,
        deepvalue_rows=deepvalue_rows,
        smart_money_rows=smart_money_rows,
        dark_pool_rows=dark_pool_rows,
        merger_rows=merger_rows,
        lockup_rows=lockup_rows,
        nt_rows=nt_rows,
        revenue_rows=revenue_rows,
        income_rows=income_rows,
    )

    html = build_html_from_template(
        date_str, date_long, gappers, value, moat,
        combined, outcome_rows, sector_rows, total_tickers,
        **shared_kwargs,
        premium=False,
    )
    html_premium = build_html_from_template(
        date_str, date_long, gappers, value, moat,
        combined, outcome_rows, sector_rows, total_tickers,
        **shared_kwargs,
        premium=True,
    )

    # Stamp ISO date as HTML comment so freshness checks can grep for it
    iso_stamp = f"<!-- newsletter-date:{date_str} -->\n"
    (ROOT / "newsletter_picks.json").write_text(json.dumps(picks, indent=2), encoding="utf-8")
    (ROOT / "newsletter_body.html").write_text(iso_stamp + html, encoding="utf-8")
    (ROOT / "newsletter_body_premium.html").write_text(iso_stamp + html_premium, encoding="utf-8")

    # Save to catalyst-edge newsletter folder + daily archive
    NEWSLETTER_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    (NEWSLETTER_DIR / "latest.html").write_text(html, encoding="utf-8")
    (ARCHIVE_DIR / f"newsletter_{date_str}.html").write_text(html, encoding="utf-8")
    (ARCHIVE_DIR / f"newsletter_{date_str}.json").write_text(json.dumps(picks, indent=2), encoding="utf-8")

    top_pick = picks.get("top_pick", "")
    print(
        f"newsletter_built date={date_str} top_pick={top_pick} "
        f"gappers={picks['gapper_count']} value={picks['value_count']} moat={picks['moat_count']}"
    )
    print(f"saved → {NEWSLETTER_DIR}/latest.html")
    print(f"archived → {ARCHIVE_DIR}/newsletter_{date_str}.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
