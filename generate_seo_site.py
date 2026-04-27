#!/usr/bin/env python3
"""generate_seo_site.py — Rich, designed public SEO page from all pipeline outputs.

Design principles:
- Sticky nav with section jump links
- Top Pick spotlight card
- Countdown to next update
- Color-coded score system with legend
- Mobile-first responsive tables
- Floating subscribe CTA
- Score tooltips and explanations
"""
from __future__ import annotations
import csv, datetime, html as html_mod, json, math, os, re
from pathlib import Path
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

ROOT    = Path(__file__).parent
FREE_GAP_LIMIT  = 3   # show 3 gap cards free, gate the rest
FREE_RANK_LIMIT = 5   # show 5 ranked rows free, gate the rest
STRIPE_READER   = "https://buy.stripe.com/your-link"
STRIPE_PRO      = "https://buy.stripe.com/your-link"
DOCS    = ROOT / "docs"
DOCS.mkdir(exist_ok=True)
ICONS   = DOCS / "icons"
ICONS.mkdir(exist_ok=True)
OUT        = DOCS / "index.html"
STATUS_OUT = ROOT / "scanner_artifact_status.json"
SITE       = "https://catalystedgescanner.com"
CEREBRO_HUD = "https://catalystedgescanner.com/cerebro/app/"
ET_TZ      = ZoneInfo("America/New_York")
NOW        = datetime.datetime.now(ET_TZ)
TODAY      = NOW.strftime("%B %d, %Y")
ISODATE    = NOW.date().isoformat()
DOW        = NOW.strftime("%A")
NOW_ET     = NOW.strftime("%-I:%M %p ET")
SCANNER_PWA_VERSION = "ce-v3"
SCANNER_ENABLE_FINNHUB_WS = os.getenv("SCANNER_ENABLE_FINNHUB_WS", "0") == "1"
SCANNER_ENABLE_POLYMARKET_REFRESH = os.getenv("SCANNER_ENABLE_POLYMARKET_REFRESH", "0") == "1"
SCANNER_ENABLE_CLIENT_QUOTES = os.getenv("SCANNER_ENABLE_CLIENT_QUOTES", "1") == "1"

# ── Sector lookup ──────────────────────────────────────────────────────────────
_sector_lookup: dict = {}
_sector_lookup_path = ROOT / "sector_lookup.json"
if _sector_lookup_path.exists():
    try:
        _sector_lookup = json.loads(_sector_lookup_path.read_text(encoding="utf-8"))
    except Exception:
        _sector_lookup = {}

# ── GICS Hierarchy lookup (4-level drill-down: Sector→IG→Industry→Sub-Industry)
_hier_lookup: dict = {}
_hier_lookup_path = ROOT / "industry_hierarchy_lookup.json"
if _hier_lookup_path.exists():
    try:
        _hier_lookup = json.loads(_hier_lookup_path.read_text(encoding="utf-8"))
    except Exception:
        _hier_lookup = {}

# ── Macro Atmospheric Pressure (from macro_engine.py) ────────────────────────
_macro_pressure: dict = {}
_macro_pressure_path = ROOT / "macro_pressure.json"
if _macro_pressure_path.exists():
    try:
        _mp = json.loads(_macro_pressure_path.read_text(encoding="utf-8"))
        _macro_pressure = {
            s: d.get("multiplier", 1.0)
            for s, d in _mp.get("pressures", {}).items()
        }
        _macro_tnx_live    = _mp.get("tnx_live")
        _macro_tnx_delta   = _mp.get("tnx_delta", 0.0)
        _macro_spike_alert = _mp.get("spike_alert", False)
        _macro_signals     = {
            s: d.get("signal", "neutral")
            for s, d in _mp.get("pressures", {}).items()
        }
    except Exception:
        _macro_tnx_live = _macro_tnx_delta = None
        _macro_spike_alert = False
        _macro_signals = {}
else:
    _macro_tnx_live = _macro_tnx_delta = None
    _macro_spike_alert = False
    _macro_signals = {}

def get_sector_attr(ticker: str) -> str:
    """Return data-sector and class attributes for a table row."""
    sectors = _sector_lookup.get(ticker.upper(), [])
    if not sectors:
        return "data-sector='other' class='sr sector-other'"
    sec_str = " ".join(sectors)
    cls_str = " ".join(f"sector-{s}" for s in sectors)
    return f"data-sector='{sec_str}' class='sr {cls_str}'"


def cerebro_handoff_url(
    ticker: str,
    *,
    source: str = "scanner",
    rank=None,
    score=None,
    form: str = "",
    reason: str = "",
    channel: str = "",
) -> str:
    params = {
        "ticker": (ticker or "").strip().upper(),
        "source": source,
    }
    if rank not in (None, ""):
        params["rank"] = str(rank)
    if score not in (None, ""):
        params["score"] = str(score)
    if form:
        params["form"] = str(form).strip().upper()
    if reason:
        params["reason"] = " ".join(str(reason).split())[:88]
    if channel:
        params["channel"] = channel
    if source == "scanner":
        params["return_to"] = SITE
    return f"{CEREBRO_HUD}?{urlencode(params, quote_via=quote)}"


# ── Filing Summary helpers ────────────────────────────────────────────────────
_TAG_SENTENCES: dict = {
    "+record revenue":              "Record revenue reported in this filing",
    "+cash flow":                   "Positive cash flow or liquidity update",
    "+intellectual property":       "Patent, IP, or licensing development",
    "+merger agreement":            "Merger or acquisition agreement signed",
    "+business combination agreement": "Business combination / M&A activity",
    "+definitive agreement":        "Definitive agreement executed",
    "+acquired":                    "Acquisition completed or announced",
    "+buyback":                     "Share buyback authorized",
    "+share repurchase":            "Share repurchase program disclosed",
    "+share repurchase program":    "Board-authorized share repurchase plan",
    "+fda clearance":               "FDA clearance or drug approval received",
    "+patent":                      "Patent granted or new IP filing",
    "+ceo":                         "CEO-level action or statement filed",
    "+form 4":                      "Executive insider stock transaction",
    "+gross margin expansion":      "Gross margin improvement reported",
    "+recurring revenue":           "Recurring / subscription revenue highlighted",
    "+renewal":                     "Contract or agreement renewal",
    "+subscription":                "Subscription growth or revenue noted",
    "+exclusive":                   "Exclusive contract or license granted",
    "-offering":                    "Share offering filed — dilution risk",
    "-at-the-market":               "ATM equity offering active — ongoing dilution",
    "-registered direct":           "Registered direct offering — dilution",
    "-private placement":           "Private placement — dilution risk",
    "-convertible note":            "Convertible note issued — dilution risk",
    "-warrant":                     "Warrant issuance or exercise disclosed",
    "-dilution":                    "Share dilution event disclosed",
    "-impairment":                  "Asset impairment charge recognized",
    "-default":                     "Default or covenant violation noted",
    "-bankruptcy":                  "Bankruptcy-related event detected",
    "-customer concentration":      "Revenue concentrated in single customer",
}

_FORM_CONTEXT: dict = {
    "8-K":    "Material corporate event — company required to disclose significant news",
    "Form 4": "Insider transaction — executive or director buying or selling shares",
    "S-3":    "Securities registration — company preparing to issue new shares",
    "13D":    "Activist position — entity disclosed 5%+ stake with strategic intent",
    "13G":    "Institutional position — passive 5%+ stake disclosed",
    "6-K":    "Foreign issuer disclosure — international company material report",
    "NT":     "Late filing notice — company missed standard deadline",
    "424B3":  "Prospectus supplement — offering terms and risk factors",
    "424B4":  "Prospectus supplement — offering terms and risk factors",
    "424B5":  "Prospectus supplement — offering terms and risk factors",
    "424B2":  "Prospectus supplement — offering terms and risk factors",
    "S-1":    "IPO registration — company registering shares for public offering",
    "10-K":   "Annual report — full-year financial results and business outlook",
    "10-Q":   "Quarterly report — three-month financial results",
}

# 8-K Item labels. Populated on the form-badge tooltip so a retail reader
# sees "8-K 2.02 = Earnings" instead of just "8-K".
_EIGHTK_ITEM_LABELS: dict[str, str] = {
    "1.01": "Material Agreement",
    "1.02": "Terminated Agreement",
    "1.03": "Bankruptcy",
    "2.01": "Acquisition / Disposition",
    "2.02": "Earnings",
    "2.03": "Debt Obligation",
    "2.04": "Debt Acceleration",
    "2.05": "Exit / Disposal Costs",
    "2.06": "Impairment",
    "3.01": "Delisting Notice",
    "3.02": "Unregistered Sale",
    "3.03": "Security Modification",
    "4.01": "Auditor Change",
    "4.02": "Non-Reliance / Restatement",
    "5.01": "Change of Control",
    "5.02": "Exec Departure / Appointment",
    "5.03": "Charter Amendment",
    "5.07": "Shareholder Vote",
    "7.01": "Reg FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Exhibits",
}


def form_badge_html(form: str, items: str = "") -> str:
    """Render the form code as a badge with a human-readable tooltip.

    For 8-K filings with an `items` list, the first recognized item is
    appended to the visible badge text (e.g. "8-K · 2.02"). The tooltip
    expands into plain English: "8-K Item 2.02 — Earnings".
    """
    form_clean = (form or "").strip()
    if not form_clean:
        return ""
    ctx = _FORM_CONTEXT.get(form_clean, "")
    items_list = [x.strip() for x in (items or "").split(";") if x.strip()]
    primary_item = items_list[0] if items_list else ""

    if form_clean.upper().startswith("8-K") and primary_item:
        label = _EIGHTK_ITEM_LABELS.get(primary_item, "")
        extra = f" Item {primary_item} — {label}" if label else f" Item {primary_item}"
        tip = f"{form_clean}{extra}"
        visible = f"{form_clean} · {primary_item}"
    else:
        tip = ctx or form_clean
        visible = form_clean

    return (
        f'<span class="form-badge" data-tip="{html_mod.escape(tip)}" '
        f'title="{html_mod.escape(tip)}">{html_mod.escape(visible)}</span>'
    )


def norm_score_0_100(raw, hi: float) -> int:
    """Normalize a raw score to a 0–100 conviction scale.

    hi is the table-specific ceiling that maps to 100. Below 0 clips to 0;
    above hi clips to 100. Used to render a shared "conviction" pill so the
    Gap / Ranked / Squeeze numbers can be visually compared.
    """
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0
    if v <= 0 or hi <= 0:
        return 0
    return max(0, min(100, round(100 * v / hi)))


def load_congress_map(max_age_days: int = 45) -> dict[str, dict]:
    """Build {ticker → latest-trade dict} from congressional_trades.csv.

    Used to tag scanner rows when a senator or representative recently traded
    the same ticker. Returns only the most recent trade per ticker within
    max_age_days of today.
    """
    path = Path(__file__).resolve().parent / "congressional_trades.csv"
    if not path.exists():
        return {}
    today = datetime.date.today()
    cutoff = (today - datetime.timedelta(days=max_age_days)).isoformat()
    out: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            td = (row.get("transaction_date") or row.get("disclosure_date") or "").strip()
            if td < cutoff:
                continue
            prev = out.get(ticker)
            if prev is None or td > prev.get("_sortkey", ""):
                out[ticker] = {
                    "member_name": (row.get("member_name") or "").strip(),
                    "party": (row.get("party") or "").strip(),
                    "chamber": (row.get("chamber") or "").strip(),
                    "transaction_type": (row.get("transaction_type") or "").strip(),
                    "amount_range": (row.get("amount_range") or "").strip(),
                    "transaction_date": td,
                    "_sortkey": td,
                }
    return out


def congress_badge(ticker: str, cmap: dict) -> str:
    """Render a small Capitol badge when a congressional trade exists for ticker."""
    if not cmap:
        return ""
    hit = cmap.get((ticker or "").upper())
    if not hit:
        return ""
    party = hit.get("party", "") or "?"
    pcolor = "#58a6ff" if party.upper() == "D" else "#f85149" if party.upper() == "R" else "#8b949e"
    member = hit.get("member_name", "Unknown")
    chamber = hit.get("chamber", "")
    txn = (hit.get("transaction_type") or "").lower()
    amt = hit.get("amount_range", "")
    date = hit.get("transaction_date", "")
    txn_label = "bought" if txn == "buy" else "sold" if txn == "sell" else txn or "traded"
    tip = f"🏛️ {member} ({party}, {chamber}) {txn_label} {amt} on {date}"
    return (
        f'<span class="congress-badge" data-tip="{html_mod.escape(tip)}" '
        f'title="{html_mod.escape(tip)}" style="background:#0d1117;color:{pcolor};'
        f'padding:1px 6px;border-radius:10px;font-size:0.72em;font-weight:700;'
        f'border:1px solid {pcolor}55;margin-left:4px">🏛️ {party}</span>'
    )


def build_combo_set(*table_rows_lists) -> dict[str, int]:
    """Return {ticker → count} of how many tables a ticker appears in.

    Used for the combo-conviction badge: 2+ means the same ticker surfaced
    in multiple scanner lanes today.
    """
    seen: dict[str, set[int]] = {}
    for idx, rows in enumerate(table_rows_lists):
        for r in rows or []:
            t = (r.get("ticker") or "").strip().upper()
            if not t:
                continue
            seen.setdefault(t, set()).add(idx)
    return {t: len(ix) for t, ix in seen.items() if len(ix) >= 2}


def combo_badge(ticker: str, combo_map: dict) -> str:
    """Render a stacked-signal badge for tickers appearing in 2+ scanner lanes."""
    if not combo_map:
        return ""
    count = combo_map.get((ticker or "").upper(), 0)
    if count < 2:
        return ""
    tip = f"⛓ {count}-signal stack — this ticker appears in {count} scanner lanes today"
    color = "#f78166" if count >= 3 else "#a371f7"
    return (
        f'<span class="combo-badge" data-tip="{html_mod.escape(tip)}" '
        f'title="{html_mod.escape(tip)}" style="background:#0d1117;color:{color};'
        f'padding:1px 6px;border-radius:10px;font-size:0.72em;font-weight:800;'
        f'border:1px solid {color}66;margin-left:4px">⛓ {count}×</span>'
    )


def age_human(recency_min) -> str:
    """Format recency_min (minutes) as 'Nm', 'Nh', or 'Nd' for the Age column."""
    try:
        m = int(recency_min)
    except (TypeError, ValueError):
        return "—"
    if m < 60:
        return f"{m}m"
    if m < 60 * 24:
        return f"{m // 60}h"
    return f"{m // (60 * 24)}d"


def mini_options_badge(opt_info: dict | None) -> str:
    """Compact options signal chip for the Ranked / Squeeze / Insider tables."""
    if not opt_info:
        return ""
    sig = (opt_info.get("signal") or "").strip().lower()
    if not sig or sig == "neutral":
        return ""
    color = "#3fb950" if "bullish" in sig else "#f78166"
    label = "CALL" if "bullish" in sig else "PUT"
    tip = f"Options flow: {sig.title()}"
    return (
        f'<span class="opt-chip" data-tip="{html_mod.escape(tip)}" '
        f'title="{html_mod.escape(tip)}" style="background:#0d1117;color:{color};'
        f'padding:1px 6px;border-radius:10px;font-size:0.72em;font-weight:700;'
        f'border:1px solid {color}55;margin-left:4px">{label}</span>'
    )


def today_pct_change(ticker: str, cache: dict) -> str:
    """Compute % change from the last two closes in the Stooq cache."""
    if not cache:
        return ""
    series = cache.get((ticker or "").upper())
    if not series or len(series) < 2:
        return ""
    try:
        prev = float(series[-2])
        last = float(series[-1])
        if prev <= 0:
            return ""
        pct = (last - prev) / prev * 100.0
        return f"{pct:+.1f}%"
    except (TypeError, ValueError, IndexError):
        return ""


def conviction_pill(raw, hi: float, raw_label: str = "") -> str:
    """Render the normalized conviction with the raw score visible on hover."""
    n = norm_score_0_100(raw, hi)
    if n >= 75:
        bg, fg = "#0f2e17", "#3fb950"
    elif n >= 50:
        bg, fg = "#2a220f", "#d29922"
    elif n >= 25:
        bg, fg = "#2a1a0f", "#f0883e"
    else:
        bg, fg = "#1a1a1f", "#8b949e"
    tip = f"raw={raw_label or raw} · 0–100 conviction scale"
    return (
        f'<span class="conviction-pill" data-tip="{html_mod.escape(tip)}" '
        f'style="background:{bg};color:{fg};padding:3px 10px;border-radius:12px;'
        f'font-weight:700;font-size:0.88em;border:1px solid {fg}33">'
        f'{n}<span style="opacity:0.6;font-size:0.8em">/100</span></span>'
    )

def _tactical_top_ticker(rows: list, score_key: str) -> tuple[str, float]:
    """Return (ticker, score) of the row with the highest numeric score_key."""
    best_t, best_s = "", 0.0
    for r in rows or []:
        try:
            s = float(r.get(score_key) or 0)
        except (TypeError, ValueError):
            s = 0.0
        if s > best_s:
            best_s = s
            best_t = (r.get("ticker") or "").upper().strip()
    return best_t, best_s


def _load_mergers_live() -> list[dict]:
    """Read merger_signals.csv for tactical strip headline numbers."""
    path = ROOT / "merger_signals.csv"
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return []
    # Rank order mirrors build_merger_radar.py SIGNAL_RANK
    rank = {"TENDER_OFFER": 4, "ACTIVIST_DEAL": 3, "STRATEGIC_REVIEW": 2, "IN_PLAY": 1}
    rows.sort(key=lambda r: (-rank.get(r.get("signal_type", ""), 0),
                             -int(r.get("signal_count") or 0)))
    return rows


def _load_csv(filename: str) -> list[dict]:
    """Safe CSV loader for tactical strip helpers. Returns [] on any failure."""
    path = ROOT / filename
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _num(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _load_darkpool_live() -> list[dict]:
    rows = _load_csv("dark_pool.csv")
    rows.sort(key=lambda r: -_num(r.get("volume_ratio")))
    return rows


def _load_deepvalue_live() -> list[dict]:
    rows = _load_csv("deepvalue_screen.csv")
    rows.sort(key=lambda r: -_num(r.get("deepvalue_score")))
    return rows


def _load_convergence_live() -> list[dict]:
    rows = _load_csv("convergence_alerts.csv")
    rank = {"EXTREME": 4, "HIGH": 3, "ELEVATED": 2, "MODERATE": 1}
    rows.sort(key=lambda r: (-rank.get((r.get("conviction_level") or "").strip(), 0),
                             -_num(r.get("convergence_score"))))
    return rows


def _load_smart_money_live() -> list[dict]:
    rows = _load_csv("smart_money.csv")
    rows.sort(key=lambda r: -_num(r.get("fund_count")))
    return rows


def _load_sympathy_live() -> list[dict]:
    rows = _load_csv("sympathy_events.csv")
    # Most recent date first, then biggest gap_score
    rows.sort(key=lambda r: (r.get("date") or "", _num(r.get("gap_score"))),
              reverse=True)
    return rows


def _load_lockups_live() -> list[dict]:
    rows = _load_csv("lockup_calendar.csv")
    # Closest expiry first (smallest days_until_expiry, but >= 0)
    def _k(r):
        d = _num(r.get("days_until_expiry"), 9999)
        return (d if d >= 0 else 9999, -_num(r.get("insider_bought_after") == "True"))
    rows.sort(key=_k)
    return rows


# ── Spotlight intelligence helpers ────────────────────────────────────────────
# Base rate, 8-K item extraction, trade frame. Each degrades gracefully when
# source data is missing. Call sites must handle empty returns.

_OUTCOME_CACHE: list[dict] | None = None
_8K_ITEM_LABELS = {
    "1.01": "Material Definitive Agreement",
    "1.02": "Agreement Termination",
    "1.03": "Bankruptcy / Receivership",
    "2.01": "Completed Acquisition/Disposal",
    "2.02": "Results of Operations",
    "2.03": "Material Off-Balance Sheet Arrangement",
    "2.04": "Triggering Event — Direct Financial Obligation",
    "2.05": "Costs Associated with Exit Activities",
    "2.06": "Material Impairment",
    "3.01": "Delisting Notice",
    "3.02": "Unregistered Equity Sale",
    "3.03": "Security-Holder Rights Modification",
    "4.01": "Auditor Change",
    "4.02": "Non-Reliance on Prior Financials",
    "5.01": "Control Change",
    "5.02": "Director/Officer Change",
    "5.03": "Bylaw/Charter Amendment",
    "5.07": "Shareholder Vote Results",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Material Event",
    "9.01": "Exhibits Attached",
}


def _load_outcome_history() -> list[dict]:
    global _OUTCOME_CACHE
    if _OUTCOME_CACHE is not None:
        return _OUTCOME_CACHE
    rows = _load_csv("sec_outcome_rows.csv")
    _OUTCOME_CACHE = rows
    return rows


def _compute_base_rate(form: str, score, window_days: int = 90) -> dict:
    """Return base-rate stats for similar setups.

    Matches same `form` and gap score within ±3 (widens to ±5, then ±∞ if n<10).
    Returns {"n": int, "hit2": float, "hit5": float, "bucket": str} or {}.
    """
    try:
        s = float(score)
    except (TypeError, ValueError):
        return {}
    if not form:
        return {}
    today = datetime.date.today()
    cutoff = (today - datetime.timedelta(days=window_days)).isoformat()
    rows = [r for r in _load_outcome_history()
            if (r.get("form") or "").strip() == form.strip()
            and (r.get("list_date") or "") >= cutoff]
    if not rows:
        return {}

    def _bucket(rows, tol):
        return [r for r in rows if abs(_num(r.get("base_score")) - s) <= tol]

    for tol, label in [(3, f"score {int(s)}±3"),
                       (5, f"score {int(s)}±5"),
                       (999, "all scores")]:
        b = _bucket(rows, tol)
        if len(b) >= 10:
            hit2 = sum(_num(r.get("hit_2pct")) for r in b) / len(b)
            hit5 = sum(_num(r.get("hit_5pct")) for r in b) / len(b)
            return {"n": len(b), "hit2": hit2, "hit5": hit5, "bucket": label,
                    "window": window_days, "form": form}
    return {}


def _extract_8k_items(link: str, cache: dict | None = None) -> list[tuple[str, str]]:
    """Pull (item_number, description) pairs from cached 8-K index text.

    Returns [] when cache missing or no items found. Descriptions are mapped
    through _8K_ITEM_LABELS for a cleaner render when the cached text is noisy.
    """
    if not link:
        return []
    if cache is None:
        cache = _filing_cache()
    txt = (cache.get(link, {}) or {}).get("text", "") or ""
    if not txt:
        return []
    compact = re.sub(r"\s+", " ", txt)
    # Pattern: "1.01 — Entry into a Material Definitive Agreement 7.01 — ..."
    found = re.findall(
        r"(\d+\.\d+)\s*[—\-:]?\s*([A-Z][A-Za-z ,/&\-]{8,140}?)(?=\s+(?:\d+\.\d+|$))",
        compact,
    )
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for num, desc in found:
        if num in seen:
            continue
        seen.add(num)
        label = _8K_ITEM_LABELS.get(num)
        out.append((num, label or desc.strip(" .·")[:80]))
        if len(out) >= 4:
            break
    return out


_FILING_CACHE_MEMO: dict | None = None


def _filing_cache() -> dict:
    global _FILING_CACHE_MEMO
    if _FILING_CACHE_MEMO is not None:
        return _FILING_CACHE_MEMO
    path = ROOT / ".sec_filing_text_cache.json"
    if not path.exists():
        _FILING_CACHE_MEMO = {}
        return _FILING_CACHE_MEMO
    try:
        with path.open(encoding="utf-8") as f:
            _FILING_CACHE_MEMO = json.load(f)
    except Exception:
        _FILING_CACHE_MEMO = {}
    return _FILING_CACHE_MEMO


def _fmt_money(n: float) -> str:
    if n >= 1_000_000_000:
        return f"${n/1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"${n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"${n/1_000:.0f}K"
    return f"${n:.0f}"


def _fmt_shares(n: float) -> str:
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return f"{n:.0f}"


_QUOTE_CACHE_LOOKUP: dict | None = None
_YAHOO_PRICE_CACHE: dict = {}  # ticker → {"price": float, "atr14": float, "avg_vol": float}


def _lookup_price(ticker: str) -> dict:
    """Return {price, atr14, avg_vol} for ticker.

    Source order: quote cache (price only) → Yahoo v8 chart API (price + ATR14 + avg vol) → zeros.
    Results cached in-process — one Yahoo hit per ticker per generation run.
    """
    global _QUOTE_CACHE_LOOKUP
    if not ticker:
        return {"price": 0.0, "atr14": 0.0, "avg_vol": 0.0}
    ticker = ticker.upper().strip()
    if ticker in _YAHOO_PRICE_CACHE:
        return _YAHOO_PRICE_CACHE[ticker]

    result = {"price": 0.0, "atr14": 0.0, "avg_vol": 0.0}

    # 1. Quote cache (price only)
    if _QUOTE_CACHE_LOOKUP is None:
        import json as _j
        from pathlib import Path as _P
        p = _P(__file__).parent / ".sec_quote_cache.json"
        try:
            raw = _j.loads(p.read_text(encoding="utf-8"))
            _QUOTE_CACHE_LOOKUP = {k: (v.get("data") or {}) for k, v in raw.items()
                                   if isinstance(v, dict)}
        except Exception:
            _QUOTE_CACHE_LOOKUP = {}
    q = _QUOTE_CACHE_LOOKUP.get(ticker, {}) or {}
    try:
        px = float(q.get("price") or 0)
        if px > 0:
            result["price"] = px
    except (TypeError, ValueError):
        pass
    try:
        v = float(q.get("avg_vol_3m") or 0)
        if v > 0:
            result["avg_vol"] = v
    except (TypeError, ValueError):
        pass

    # 2. Yahoo v8 chart API — 30-day daily OHLC for price + 14-day ATR
    try:
        import urllib.request, json as _j
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1d&range=30d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            d = _j.loads(r.read())
        results = d.get("chart", {}).get("result") or []
        if results:
            meta = results[0].get("meta") or {}
            px = float(meta.get("regularMarketPrice") or 0)
            if px > 0 and result["price"] == 0:
                result["price"] = px
            # 14-day ATR: mean of true range over last 14 bars
            # TR_i = max(high_i - low_i, |high_i - close_{i-1}|, |low_i - close_{i-1}|)
            ind = results[0].get("indicators", {}).get("quote", [{}])[0]
            highs = ind.get("high") or []
            lows  = ind.get("low")  or []
            closes = ind.get("close") or []
            vols   = ind.get("volume") or []
            # Zip the 3 parallel lists, drop None entries
            bars = [(h, l, c) for h, l, c in zip(highs, lows, closes)
                    if h is not None and l is not None and c is not None]
            if len(bars) >= 15:
                trs = []
                for i in range(1, len(bars)):
                    h, l, _ = bars[i]
                    _, _, prev_c = bars[i-1]
                    tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
                    trs.append(tr)
                atr14 = sum(trs[-14:]) / 14
                if atr14 > 0:
                    result["atr14"] = atr14
            if vols and result["avg_vol"] == 0:
                vs = [v for v in vols if v is not None]
                if vs:
                    result["avg_vol"] = sum(vs) / len(vs)
    except Exception:
        pass

    _YAHOO_PRICE_CACHE[ticker] = result
    return result


def _compute_trade_frame(row: dict) -> dict:
    """Derive Entry / Stop / Target1 / Target2 from gapper row + live ATR.

    Preferred stop: entry − 1 × ATR14 (adapts to the stock's own volatility).
    Fallback stop: fixed % if ATR unavailable — 12% <$1, 8% <$5, 5% otherwise.
    R = entry − stop; Target1 = entry + 1R, Target2 = entry + 2R.
    Always emits a trade frame so the spotlight card never goes sloppy.
    """
    out: dict = {}
    price = _num(row.get("price"))
    vol   = _num(row.get("avg_vol_3m"))
    cap   = _num(row.get("market_cap"))
    score = _num(row.get("gapper_score"))
    atr   = 0.0

    # Fallback lookup (price + ATR14 + avg_vol) if row is thin.
    if price <= 0 or vol <= 0:
        lk = _lookup_price(row.get("ticker", ""))
        if price <= 0:
            price = lk.get("price", 0.0)
        if vol <= 0:
            vol = lk.get("avg_vol", 0.0)
        atr = lk.get("atr14", 0.0)
    else:
        # Still grab ATR even if row already had price.
        lk = _lookup_price(row.get("ticker", ""))
        atr = lk.get("atr14", 0.0)

    if price > 0:
        out["price"] = price
        # ATR-based stop preferred; fixed-% fallback.
        if atr > 0:
            stop = max(0.01, price - atr)
            out["stop"] = round(stop, 2)
            out["atr14"] = round(atr, 3)
            out["stop_method"] = "ATR14"
        else:
            stop_pct = 0.12 if price < 1 else 0.08 if price < 5 else 0.05
            stop = price * (1 - stop_pct)
            out["stop"] = round(stop, 2)
            out["stop_method"] = "fixed"
        # Two-target R-multiple ladder. R = entry − stop.
        R = max(0.01, price - out["stop"])
        out["target1"] = round(price + R,       2)      # 1R
        out["target2"] = round(price + 2 * R,   2)      # 2R
        out["r_usd"]   = round(R, 2)
        out["r_pct"]   = round(R / price * 100, 1)
        # Score-tilt: on lower-conviction picks, emphasize Target1 only.
        out["conviction_tag"] = "2R ladder" if score >= 15 else "1R focus"
    if cap > 0:
        out["cap"] = cap
    if vol > 0:
        out["avg_vol"] = vol
    if cap > 0 and price > 0:
        out["float_approx"] = cap / price
    return out


def _score_tier(score) -> tuple[str, str]:
    """Map gap score to tier label + color hex. Scale anchored at 30 max."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return ("—", "#8891a3")
    if s >= 18: return ("EXTREME", "#ff6b6b")
    if s >= 14: return ("HIGH",    "#f0883e")
    if s >= 9:  return ("ELEVATED","#d29922")
    if s >= 5:  return ("MODERATE","#7ddcff")
    return ("LOW", "#8891a3")


def tactical_strip_html(gappers, squeezes, insiders, darkpool,
                        congress_map: dict, mergers_live: list,
                        darkpool_live: list | None = None,
                        deepvalue_live: list | None = None,
                        convergence_live: list | None = None,
                        smart_money_live: list | None = None,
                        sympathy_live: list | None = None,
                        lockups_live: list | None = None) -> str:
    """Rotating tactical strip between nav and primary content.

    ~90px band that cycles all Signal Dashboard tools (one headline number
    each) with pause-on-hover + dot nav. CTA points to the All Tools suite.
    """
    # Card 1 — Gap Plays
    g_top_t, g_top_s = _tactical_top_ticker(gappers, "gapper_score")
    g_n = len(gappers or [])
    g_headline = (f"{g_n} gap {'play' if g_n == 1 else 'plays'}"
                  if g_n else "Pipeline quiet")
    g_detail = (f"top: <b>{g_top_t}</b> at {g_top_s:.0f}"
                if g_top_t else "live scanner refresh pending")

    # Card 2 — Squeeze Hunter
    s_top_t, s_top_s = _tactical_top_ticker(squeezes, "squeeze_score")
    if not s_top_t:
        s_top_t, s_top_s = _tactical_top_ticker(squeezes, "raw_score")
    s_n = len(squeezes or [])
    s_headline = (f"{s_n} squeeze setup{'' if s_n == 1 else 's'}"
                  if s_n else "No active squeeze")
    s_detail = (f"top: <b>{s_top_t}</b> at {s_top_s:.0f}/110"
                if s_top_t else "scan pending")

    # Card 3 — Insider Clusters
    # Never publish "0 confirmed buys" — that reads as broken to first-time visitors.
    # When no confirmed open-market buys land today, show Form 4 filing volume instead
    # so the card always conveys real activity rather than an empty status.
    i_n = len(insiders or [])
    i_confirmed = sum(1 for r in (insiders or [])
                      if str(r.get("confirmed_buy", "")).strip() == "1")
    i_filings = sum(int(_num(r.get("filing_count"))) for r in (insiders or []))
    i_top_t, _ = _tactical_top_ticker(insiders, "filing_count")
    i_headline = (f"{i_n} insider cluster{'' if i_n == 1 else 's'}"
                  if i_n else "No clusters today")
    if i_confirmed > 0:
        i_detail = (f"<b>{i_confirmed}</b> confirmed buy{'' if i_confirmed == 1 else 's'}"
                    + (f" · top: <b>{i_top_t}</b>" if i_top_t else ""))
    elif i_filings > 0:
        i_detail = (f"<b>{i_filings}</b> Form 4 filing{'' if i_filings == 1 else 's'}"
                    + (f" · top: <b>{i_top_t}</b>" if i_top_t else ""))
    else:
        i_detail = (f"top: <b>{i_top_t}</b> · watching cluster formation" if i_top_t
                    else "watching Form 4 cluster formation")

    # Card 4 — Congress overlaps
    # congress_map keys are tickers with recent Capitol Hill trades
    c_overlap = 0
    c_top_t = ""
    all_scanner_tickers = {(r.get("ticker") or "").upper()
                           for r in (gappers or []) + (squeezes or []) +
                                    (insiders or []) + (darkpool or [])}
    for t in all_scanner_tickers:
        if t and t in congress_map:
            c_overlap += 1
            if not c_top_t:
                c_top_t = t
    c_headline = (f"{c_overlap} Capitol Hill overlap{'' if c_overlap == 1 else 's'}"
                  if c_overlap else "No overlaps today")
    c_detail = (f"top: <b>{c_top_t}</b>" if c_top_t
                else "tracking 45-day window")

    # Card 5 — M&A radar
    m_n = len(mergers_live or [])
    m_top = (mergers_live or [{}])[0] if mergers_live else {}
    m_top_t = (m_top.get("ticker") or "").upper()
    m_top_type = (m_top.get("signal_type") or "").replace("_", " ").title()
    m_headline = (f"{m_n} M&A event{'' if m_n == 1 else 's'}"
                  if m_n else "M&A feed quiet")
    m_detail = (f"top: <b>{m_top_t}</b> · {m_top_type}"
                if m_top_t else "scanning SC TO-T · 13D/A")

    # Card 6 — Dark Pool (unusual volume prints)
    dp_n = len(darkpool_live or [])
    dp_top = (darkpool_live or [{}])[0] if darkpool_live else {}
    dp_top_t = (dp_top.get("ticker") or "").upper()
    dp_top_r = _num(dp_top.get("volume_ratio"))
    dp_headline = (f"{dp_n} dark print{'' if dp_n == 1 else 's'}"
                   if dp_n else "Volume feed quiet")
    dp_detail = (f"top: <b>{dp_top_t}</b> · {dp_top_r:.1f}× avg"
                 if dp_top_t else "tracking >2× 30d volume")

    # Card 7 — Deep Value
    dv_n = len(deepvalue_live or [])
    dv_a_b = sum(1 for r in (deepvalue_live or [])
                 if (r.get("grade") or "").strip().upper() in ("A", "B"))
    dv_top = (deepvalue_live or [{}])[0] if deepvalue_live else {}
    dv_top_t = (dv_top.get("ticker") or "").upper()
    dv_top_s = _num(dv_top.get("deepvalue_score"))
    dv_headline = (f"{dv_n} deep-value name{'' if dv_n == 1 else 's'}"
                   if dv_n else "Value screen empty")
    dv_detail = (f"top: <b>{dv_top_t}</b> at {dv_top_s:.0f} · {dv_a_b} A/B"
                 if dv_top_t else "P/B · P/FCF · insider own")

    # Card 8 — Convergence (multi-signal conviction)
    cv_list = convergence_live or []
    cv_high = sum(1 for r in cv_list
                  if (r.get("conviction_level") or "").strip().upper()
                  in ("HIGH", "EXTREME"))
    cv_top = cv_list[0] if cv_list else {}
    cv_top_t = (cv_top.get("ticker") or "").upper()
    cv_top_n = int(_num(cv_top.get("signal_count")))
    cv_headline = (f"{cv_high} high-conviction overlap{'' if cv_high == 1 else 's'}"
                   if cv_high else (f"{len(cv_list)} tracked"
                                     if cv_list else "No overlaps today"))
    cv_detail = (f"top: <b>{cv_top_t}</b> · {cv_top_n} signals"
                 if cv_top_t else "stacking insider · squeeze · value")

    # Card 9 — Smart Money (13F institutional interest)
    sm_list = smart_money_live or []
    sm_top = sm_list[0] if sm_list else {}
    sm_top_t = (sm_top.get("ticker") or "").upper()
    sm_top_n = int(_num(sm_top.get("fund_count")))
    sm_headline = (f"{len(sm_list)} smart-money name{'' if len(sm_list) == 1 else 's'}"
                   if sm_list else "13F feed refreshing")
    sm_detail = (f"top: <b>{sm_top_t}</b> · {sm_top_n} funds in"
                 if sm_top_t else "tracking 13F institutional flow")

    # Card 10 — Sympathy Plays (peer reaction to catalyst)
    # Skip rows with literal "unknown" sector — those leaked onto the storefront
    # as "top: ASBP · unknown" during the 2026-04-17 audit. Prefer the first row
    # whose sector is a real GICS bucket; fall back to peer count if all rows
    # are unclassified so the card never publishes the word "unknown".
    _SECTOR_BAD = {"", "unknown", "unclassified", "nan", "none", "-"}
    sp_list = sympathy_live or []
    sp_clean = [r for r in sp_list
                if (r.get("sector") or "").strip().lower() not in _SECTOR_BAD]
    sp_top = sp_clean[0] if sp_clean else (sp_list[0] if sp_list else {})
    sp_top_t = (sp_top.get("trigger_ticker") or "").upper()
    sp_top_sector_raw = (sp_top.get("sector") or "").strip()
    sp_top_sector = ("" if sp_top_sector_raw.lower() in _SECTOR_BAD
                     else sp_top_sector_raw)
    sp_top_peers = [p for p in (sp_top.get("peers") or "").split(",") if p.strip()]
    sp_headline = (f"{len(sp_list)} sympathy trigger{'' if len(sp_list) == 1 else 's'}"
                   if sp_list else "No sympathy setups")
    if sp_top_t and sp_top_sector:
        sp_detail = f"top: <b>{sp_top_t}</b> · {sp_top_sector}"
    elif sp_top_t and sp_top_peers:
        sp_detail = f"top: <b>{sp_top_t}</b> · {len(sp_top_peers)} peer{'s' if len(sp_top_peers) != 1 else ''}"
    elif sp_top_t:
        sp_detail = f"top: <b>{sp_top_t}</b>"
    else:
        sp_detail = "peer-basket catalyst spillover"

    # Card 11 — Lockup Expirations
    lu_list = lockups_live or []
    lu_week = sum(1 for r in lu_list
                  if (r.get("status") or "").strip().upper() == "EXPIRES_THIS_WEEK")
    lu_top = lu_list[0] if lu_list else {}
    lu_top_t = (lu_top.get("ticker") or "").upper()
    lu_top_d = int(_num(lu_top.get("days_until_expiry"), 999))
    lu_headline = (f"{lu_week} expir{'y' if lu_week == 1 else 'ies'} this week"
                   if lu_week else (f"{len(lu_list)} on calendar"
                                     if lu_list else "Lockup slate clear"))
    lu_detail = (f"next: <b>{lu_top_t}</b> in {lu_top_d}d"
                 if lu_top_t and lu_top_d < 999
                 else "IPO 180d · SPAC 12mo windows")

    # Explicit hex — `--brass` / `--cyan` aren't defined on every page.
    # Order mirrors Signal Dashboards suite priority: hero products → catalysts → conviction → flow → calendar.
    cards = [
        {"icon": "🎯", "tint": "#22c55e", "label": "JACKPOT",
         "headline": "89% audited hit rate", "detail": "SEC catalyst + gap confirmation overlap · 90-day window",
         "href": "/jackpot/"},
        {"icon": "💰", "tint": "#06b6d4", "label": "DCF Intrinsic Value",
         "headline": "Damodaran 2-stage DCF", "detail": "1,600 US tickers · every input traces to SEC EDGAR XBRL",
         "href": "/dcf/"},
        {"icon": "🌍", "tint": "#22d3ee", "label": "DCF (International)",
         "headline": "36 countries · 255 graded", "detail": "Two-stage Damodaran via Yahoo fundamentals · A/B/C/D/F",
         "href": "/dcf/international/"},
        {"icon": "🤖", "tint": "#a855f7", "label": "Numerai Signals",
         "headline": "Live submission, hedge fund grade", "detail": "1,879 predictions · model on signals.numer.ai",
         "href": "/numerai/"},
        {"icon": "🌍", "tint": "#22d3ee", "label": "International Scanner",
         "headline": "38 markets · 414 tickers", "detail": "Gap, sympathy chains, regional sector heatmap",
         "href": "/international/"},
        {"icon": "🔗", "tint": "#f5c443", "label": "Cross-Border Convergence",
         "headline": "ADR ↔ home convergence", "detail": "50 entity pairs · TRADE / STRONG conviction",
         "href": "/cross-border/"},
        {"icon": "⛓", "tint": "#fb923c", "label": "DeFi & BTC ETF Tape",
         "headline": "BTC ETF flow + DeFi liquidations", "detail": "11 spot ETFs · 300 protocols · cascade alerts",
         "href": "/defi/"},
        {"icon": "📈", "tint": "#3fb950", "label": "Gap Plays",
         "headline": g_headline, "detail": g_detail, "href": "/gaps/"},
        {"icon": "🔥", "tint": "#f0883e", "label": "Squeeze Hunter",
         "headline": s_headline, "detail": s_detail, "href": "/squeeze/"},
        {"icon": "💼", "tint": "#79c0ff", "label": "Insider Clusters",
         "headline": i_headline, "detail": i_detail, "href": "/insiders/"},
        {"icon": "🎯", "tint": "#ff7b72", "label": "Convergence",
         "headline": cv_headline, "detail": cv_detail, "href": "/convergence/"},
        {"icon": "💎", "tint": "#56d364", "label": "Deep Value",
         "headline": dv_headline, "detail": dv_detail, "href": "/deepvalue/"},
        {"icon": "🌑", "tint": "#a5a5f5", "label": "Dark Pool",
         "headline": dp_headline, "detail": dp_detail, "href": "/darkpool/"},
        {"icon": "🧠", "tint": "#ffa657", "label": "Smart Money",
         "headline": sm_headline, "detail": sm_detail, "href": "/smart-money/"},
        {"icon": "🤝", "tint": "#bc8cff", "label": "M&A Radar",
         "headline": m_headline, "detail": m_detail, "href": "/mergers/"},
        {"icon": "🔗", "tint": "#39d0d8", "label": "Sympathy Plays",
         "headline": sp_headline, "detail": sp_detail, "href": "/sympathy/"},
        {"icon": "📅", "tint": "#e6a1a1", "label": "Lockup Expirations",
         "headline": lu_headline, "detail": lu_detail, "href": "/lockups/"},
        {"icon": "🏛️", "tint": "#d29922", "label": "Congress Trades",
         "headline": c_headline, "detail": c_detail, "href": "/congress/"},
    ]

    card_html = ""
    dot_html = ""
    for idx, c in enumerate(cards):
        active = " ts-active" if idx == 0 else ""
        card_html += (
            f'<a class="ts-card{active}" data-idx="{idx}" href="{c["href"]}" '
            f'style="--ts-tint:{c["tint"]}">'
            f'<span class="ts-icon" aria-hidden="true">{c["icon"]}</span>'
            f'<span class="ts-body">'
            f'<span class="ts-label">{c["label"]}</span>'
            f'<span class="ts-headline">{c["headline"]}</span>'
            f'<span class="ts-detail">{c["detail"]}</span>'
            f'</span>'
            f'<span class="ts-arrow" aria-hidden="true">›</span>'
            f'</a>'
        )
        dot_html += (f'<button class="ts-dot{" ts-dot-active" if idx == 0 else ""}" '
                     f'data-idx="{idx}" type="button" '
                     f'aria-label="Show {c["label"]} card"></button>')

    cta_html = (
        '<a class="ts-cta" href="javascript:void(0)" '
        'onclick="document.getElementById(\'suite-overlay\').classList.add(\'open\');'
        'document.getElementById(\'suite-mega\').classList.add(\'open\');'
        'document.body.style.overflow=\'hidden\'" '
        'data-tip="Open full tool suite">'
        '<span class="ts-cta-label">All Tools</span>'
        '<span class="ts-cta-sub">Full suite ▸</span>'
        '</a>'
    )

    return f"""
<!-- ROTATING TACTICAL STRIP — live headline numbers across every Signal Dashboard tool -->
<style>
.tactical-strip {{
  position: relative;
  z-index: 10;
  background:
    radial-gradient(ellipse at 12% 0%, rgba(210,153,34,.16), transparent 55%),
    radial-gradient(ellipse at 88% 100%, rgba(121,192,255,.10), transparent 52%),
    linear-gradient(180deg, rgba(210,153,34,.05), rgba(210,153,34,0) 60%),
    linear-gradient(90deg,#161d2a 0%,#1b2336 50%,#161d2a 100%);
  border-top: 1px solid rgba(210,153,34,.28);
  border-bottom: 1px solid #2a3348;
  box-shadow:
    0 1px 0 rgba(255,255,255,.04) inset,
    0 8px 24px -18px rgba(0,0,0,.9);
}}
.tactical-strip::after {{
  content:""; position:absolute; left:0; right:0; top:0; height:1px;
  background: linear-gradient(90deg, transparent, rgba(210,153,34,.55), transparent);
  pointer-events: none;
}}
.ts-wrap {{
  display: flex; align-items: stretch; gap: 0;
  max-width: 1400px; margin: 0 auto; padding: 0 16px;
  min-height: 90px; position: relative;
}}
.ts-rail {{
  flex: 1 1 auto; position: relative; overflow: hidden;
  display: flex; align-items: center;
}}
.ts-card {{
  position: absolute; inset: 0;
  display: flex; align-items: center; gap: 14px;
  padding: 12px 18px; text-decoration: none; color: inherit;
  opacity: 0; transform: translateX(24px);
  transition: opacity .55s cubic-bezier(.22,1,.36,1),
              transform .55s cubic-bezier(.22,1,.36,1);
  pointer-events: none;
}}
.ts-card.ts-active {{ opacity: 1; transform: translateX(0); pointer-events: auto; }}
.ts-icon {{
  flex: 0 0 auto;
  width: 44px; height: 44px;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px;
  background: linear-gradient(135deg, color-mix(in oklab, var(--ts-tint) 18%, transparent) 0%,
                                      color-mix(in oklab, var(--ts-tint) 6%, transparent) 100%);
  border: 1px solid color-mix(in oklab, var(--ts-tint) 35%, transparent);
  border-radius: 10px;
  box-shadow: 0 0 18px color-mix(in oklab, var(--ts-tint) 12%, transparent);
}}
.ts-body {{
  display: flex; flex-direction: column; gap: 2px;
  min-width: 0; flex: 1 1 auto;
}}
.ts-label {{
  font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--ts-tint); font-weight: 700;
}}
.ts-headline {{
  font-size: 17px; font-weight: 700; color: var(--text);
  font-feature-settings: "tnum" 1; letter-spacing: -.01em;
}}
.ts-detail {{
  font-size: 12.5px; color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.ts-detail b {{ color: var(--ts-tint); font-weight: 700; }}
.ts-arrow {{
  font-size: 22px; color: var(--muted); opacity: .5;
  transition: transform .25s, opacity .25s, color .25s;
}}
.ts-card:hover {{ background: rgba(255,255,255,.015); }}
.ts-card:hover .ts-arrow {{ transform: translateX(4px); opacity: 1; color: var(--ts-tint); }}
.ts-dots {{
  display: flex; align-items: center; gap: 5px;
  padding: 0 14px; border-left: 1px solid #1f2937;
  flex-wrap: nowrap;
}}
.ts-dot {{
  width: 6px; height: 6px; border-radius: 50%;
  background: #30363d; border: none; padding: 0; cursor: pointer;
  transition: background .25s, transform .25s;
  flex: 0 0 auto;
}}
.ts-dot:hover {{ transform: scale(1.25); }}
.ts-dot-active {{ background: var(--brass); box-shadow: 0 0 8px rgba(210,153,34,.5); }}
.ts-cta {{
  display: flex; flex-direction: column; align-items: flex-end; justify-content: center;
  padding: 0 18px 0 14px;
  border-left: 1px solid #1f2937;
  text-decoration: none; cursor: pointer;
  position: relative;
}}
.ts-cta::before {{
  content: "▸"; position: absolute; left: -6px; top: 50%;
  transform: translateY(-50%);
  color: var(--brass); opacity: .35; font-size: 14px;
}}
.ts-cta-label {{
  font-size: 13px; font-weight: 700; color: var(--text); letter-spacing: .02em;
}}
.ts-cta-sub {{
  font-size: 11px; color: var(--brass); letter-spacing: .08em;
  text-transform: uppercase; font-weight: 700;
  transition: transform .25s;
}}
.ts-cta:hover .ts-cta-sub {{ transform: translateX(3px); }}
.ts-progress {{
  position: absolute; left: 0; right: 0; bottom: 0; height: 1px;
  background: linear-gradient(90deg, transparent, var(--brass), transparent);
  transform-origin: left center;
  transform: scaleX(0);
  opacity: .6;
  pointer-events: none;
}}
.ts-progress.ts-run {{
  animation: ts-sweep 5s linear infinite;
}}
@keyframes ts-sweep {{
  0%   {{ transform: scaleX(0); opacity: .2; }}
  8%   {{ opacity: .8; }}
  100% {{ transform: scaleX(1); opacity: .2; }}
}}
@media (max-width: 720px) {{
  .ts-wrap {{ padding: 0 10px; }}
  .ts-icon {{ width: 38px; height: 38px; font-size: 18px; }}
  .ts-headline {{ font-size: 15px; }}
  .ts-detail {{ font-size: 11.5px; }}
  .ts-cta-sub {{ font-size: 10px; }}
  .ts-dots {{ padding: 0 6px; gap: 3px; }}
  .ts-dot {{ width: 5px; height: 5px; }}
  .ts-arrow {{ display: none; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .ts-card {{ transition: opacity .2s; transform: none; }}
  .ts-progress {{ display: none; }}
}}
</style>
<section class="tactical-strip" aria-label="Live tool pulse">
  <div class="ts-wrap">
    <div class="ts-rail" id="ts-rail" role="region" aria-live="polite">
      {card_html}
    </div>
    <div class="ts-dots" id="ts-dots" role="tablist" aria-label="Tool pulse navigation">
      {dot_html}
    </div>
    {cta_html}
  </div>
  <div class="ts-progress ts-run" id="ts-progress" aria-hidden="true"></div>
</section>
<script>
(function(){{
  var rail = document.getElementById('ts-rail');
  var dotsBox = document.getElementById('ts-dots');
  var progress = document.getElementById('ts-progress');
  if (!rail || !dotsBox) return;
  var cards = rail.querySelectorAll('.ts-card');
  var dots = dotsBox.querySelectorAll('.ts-dot');
  if (!cards.length) return;
  var idx = 0;
  var paused = false;
  var timer = null;
  var INTERVAL = 5000;
  function show(n){{
    idx = (n + cards.length) % cards.length;
    cards.forEach(function(c, i){{ c.classList.toggle('ts-active', i === idx); }});
    dots.forEach(function(d, i){{ d.classList.toggle('ts-dot-active', i === idx); }});
    if (progress) {{
      progress.classList.remove('ts-run');
      void progress.offsetWidth;
      if (!paused) progress.classList.add('ts-run');
    }}
  }}
  function next(){{ show(idx + 1); }}
  function start(){{
    stop();
    timer = setInterval(function(){{ if (!paused) next(); }}, INTERVAL);
  }}
  function stop(){{ if (timer) {{ clearInterval(timer); timer = null; }} }}
  var strip = rail.closest('.tactical-strip');
  if (strip) {{
    strip.addEventListener('mouseenter', function(){{
      paused = true;
      if (progress) progress.classList.remove('ts-run');
    }});
    strip.addEventListener('mouseleave', function(){{
      paused = false;
      if (progress) progress.classList.add('ts-run');
    }});
  }}
  dots.forEach(function(d){{
    d.addEventListener('click', function(){{
      show(parseInt(d.getAttribute('data-idx'), 10) || 0);
      start();
    }});
  }});
  var mql = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (!mql.matches) start();
}})();
</script>
"""


def build_filing_summary(form: str, tags_raw: str, score) -> str:
    """Return a pipe-separated 3-bullet summary string for data-summary attr."""
    bullets: list[str] = []

    # Bullet 1: form context
    ctx = _FORM_CONTEXT.get(form.strip(), f"{form} filing — review EDGAR for details")
    bullets.append(ctx)

    pos, neg = [], []
    for t in tags_raw.split(";"):
        t = t.strip()
        if not t:
            continue
        sent = _TAG_SENTENCES.get(t)
        if not sent:
            continue
        (pos if t.startswith("+") else neg).append(sent)

    # Bullet 2: strongest positive keyword or score context
    if pos:
        bullets.append(f"Keyword signal detected: {pos[0]}")
    else:
        try:
            sc = float(score)
            if sc >= 14: bullets.append(f"High-conviction setup — gap score {sc:.0f}")
            elif sc >= 9: bullets.append(f"Strong catalyst setup — gap score {sc:.0f}")
            else:         bullets.append(f"Watch setup — gap score {sc:.0f}")
        except Exception:
            bullets.append("Review filing for catalyst details")

    # Bullet 3: risk flag or second positive
    if neg:
        bullets.append(f"Risk flag detected: {neg[0]}")
    elif len(pos) > 1:
        bullets.append(f"Secondary keyword signal: {pos[1]}")
    else:
        bullets.append("No additional risk keywords were detected in the filing scan")

    return "|".join(bullets[:3])


def humanize_signal_summary(value: str, max_parts: int = 3) -> str:
    parts = [chunk.strip() for chunk in str(value or "").split("|") if chunk.strip()]
    if not parts:
        return "Catalyst packet attached"
    return " · ".join(parts[:max_parts])


# ── Sector Heatmap ────────────────────────────────────────────────────────────
_NEG_HEATMAP_TAGS = frozenset([
    "offering", "registered direct", "private placement", "atm program",
    "at-the-market", "dilution", "going concern", "bankruptcy", "chapter 11",
    "delist", "non-compliance", "impairment", "default", "miss", "loss",
])

# Form types that are inherently dilutive/bearish even without explicit tags.
_BEARISH_FORMS = frozenset([
    "S-3", "S-3/A", "S-3ASR",       # Shelf registration — prep for offering
    "424B2", "424B3", "424B5",       # Prospectus supplement — active offering
    "SC 13E-3", "SC TO-T",          # Going-private / tender offer
    "NT 10-K", "NT 10-Q",           # Late filing notice — red flag
    "15-12G",                        # Deregistration — delisting
])

def build_heatmap_data(all_rows: list) -> list:
    """Compute sector→cumulative gap score for the heatmap treemap.
    Returns sorted list of dicts with name, label, score, pulse, top_ticker,
    bullish_count, bearish_count, sentiment (0=all bearish, 1=all bullish).
    Pulse (⚡) is reserved for the top-3 conviction sectors today (ranked by
    cumulative score with a per-sector top-ticker score >= 15 floor) so it
    stays a differentiating marker instead of saturating to every tile.
    """
    sectors: dict = {}
    seen_tickers: set = set()  # deduplicate — same ticker can appear in both CSV sources
    for r in all_rows:
        ticker = r.get("ticker", "").upper().strip()
        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        try:
            score = float(r.get("gapper_score") or r.get("priority_score") or 0)
        except Exception:
            score = 0
        form = r.get("form", "")
        tags = (r.get("tags") or "").lower()

        # Sentiment classification — three-way: bullish / bearish / neutral.
        # Upstream taggers emit semicolon-separated prefixed tags like
        # "-offering", "+merger agreement", "-warrant;-dilution", etc.
        #
        # Rules (audited 2026-04-17):
        #   1. Parse ALL semicolon-separated tags; count explicit + and - prefixes.
        #   2. If more - than + → bearish.  More + than - → bullish.  Tied → neutral.
        #   3. No tags at all + bearish form type (S-3, 424B*, NT 10-*) → bearish.
        #   4. No tags at all + non-bearish form → neutral (NOT bullish).
        #   5. Fallback keyword check against _NEG_HEATMAP_TAGS for untagged-but-texted.
        #
        # This prevents the "every sector 0 bearish" artifact where 80% of filings
        # had no tags and silently defaulted to bullish.
        polarity = None  # None = neutral/unknown
        if tags:
            parts = [t.strip() for t in tags.split(";") if t.strip()]
            pos_count = sum(1 for p in parts if p.startswith("+"))
            neg_count = sum(1 for p in parts if p.startswith("-"))
            kw_neg = 1 if any(neg in tags for neg in _NEG_HEATMAP_TAGS) else 0
            neg_count += kw_neg
            if neg_count > pos_count:
                polarity = "bearish"
            elif pos_count > neg_count:
                polarity = "bullish"
            # else tied → neutral
        elif form.upper() in _BEARISH_FORMS:
            polarity = "bearish"
        # else: no tags, non-bearish form → neutral

        # Per-ticker pulse candidate: genuine high-conviction (score >= 15, or activist >= 10).
        # We track it here; final pulse assignment happens AFTER sector ranking so that
        # ⚡ only surfaces on the top-3 conviction sectors today (see post-loop step).
        pulse_candidate = (score >= 15) or (form in ("13D", "13G") and score >= 10)

        _h  = _hier_lookup.get(ticker, {})
        ig  = _h.get("ig", "")
        ind = _h.get("i", "")
        si  = _h.get("si", "")
        for s in _sector_lookup.get(ticker, []):
            if s == "other":
                continue
            if s not in sectors:
                sectors[s] = {
                    "score": 0.0, "pulse": False, "pulse_eligible": False,
                    "top_score": 0.0, "top_ticker": "",
                    "bullish": 0, "bearish": 0, "neutral": 0,
                    "bullish_weight": 0.0, "bearish_weight": 0.0,
                    "ig": {},
                }
            sectors[s]["score"] += score
            # Weight each polar filing by its own gapper_score so a score-15
            # bearish (e.g. S-3 offering) outweighs a score-2 bullish (routine
            # 8-K). Floor at 1.0 so zero-scored filings still register on their
            # side instead of vanishing.
            _w = max(score, 1.0)
            if polarity == "bearish":
                sectors[s]["bearish"] += 1
                sectors[s]["bearish_weight"] += _w
            elif polarity == "bullish":
                sectors[s]["bullish"] += 1
                sectors[s]["bullish_weight"] += _w
            else:
                sectors[s]["neutral"] += 1
            if pulse_candidate:
                sectors[s]["pulse_eligible"] = True
            if score > sectors[s]["top_score"]:
                sectors[s]["top_score"] = score
                sectors[s]["top_ticker"] = ticker
            # Track full GICS hierarchy (IG → Industry → Sub-Industry)
            if ig:
                ig_dict = sectors[s]["ig"]
                if ig not in ig_dict:
                    ig_dict[ig] = {"count": 0, "top_score": 0.0, "top_ticker": "",
                                   "industries": {}}
                ig_dict[ig]["count"] += 1
                if score > ig_dict[ig]["top_score"]:
                    ig_dict[ig]["top_score"] = score
                    ig_dict[ig]["top_ticker"] = ticker
                if ind:
                    ind_dict = ig_dict[ig]["industries"]
                    if ind not in ind_dict:
                        ind_dict[ind] = {"count": 0, "top_score": 0.0,
                                         "top_ticker": "", "sub_industries": {}}
                    ind_dict[ind]["count"] += 1
                    if score > ind_dict[ind]["top_score"]:
                        ind_dict[ind]["top_score"] = score
                        ind_dict[ind]["top_ticker"] = ticker
                    if si:
                        si_dict = ind_dict[ind]["sub_industries"]
                        if si not in si_dict:
                            si_dict[si] = {"count": 0, "top_score": 0.0,
                                           "top_ticker": "", "tickers": []}
                        si_dict[si]["count"] += 1
                        if score > si_dict[si]["top_score"]:
                            si_dict[si]["top_score"] = score
                            si_dict[si]["top_ticker"] = ticker
                        if len(si_dict[si]["tickers"]) < 8:
                            si_dict[si]["tickers"].append(ticker)

    # Build per-sector Akerlof signal count from today's Nobel signals
    _sector_akerlof: dict = {}
    try:
        _nf = ROOT / "nobel_signals.json"
        if _nf.exists():
            _nd = json.loads(_nf.read_text())
            for _tk, _ns in _nd.get("tickers", {}).items():
                _ak = _ns.get("akerlof", {})
                if _ak.get("filing_opacity", 0) > 0.5 or _ak.get("asymmetry_score", 0) > 0.3:
                    for _sec in _sector_lookup.get(_tk, []):
                        if _sec != "other":
                            _sector_akerlof[_sec] = _sector_akerlof.get(_sec, 0) + 1
    except Exception:
        pass

    # Assign ⚡ to at most the top-3 eligible sectors by cumulative score.
    # "Eligible" = sector contains at least one ticker with score >= 15 (or 13D/G >= 10).
    # This keeps ⚡ a rare, meaningful differentiator instead of firing for every sector.
    _ranked_eligible = sorted(
        (n for n, dd in sectors.items() if dd.get("pulse_eligible") and dd["score"] >= 1),
        key=lambda n: -sectors[n]["score"],
    )[:3]
    for _n in _ranked_eligible:
        sectors[_n]["pulse"] = True

    result = []
    for name, d in sectors.items():
        if d["score"] < 1:
            continue
        # Conviction-weighted sentiment: a sector with one score-15 bearish and
        # one score-2 bullish reads bearish even though raw counts are 1:1.
        scored_weight = d["bullish_weight"] + d["bearish_weight"]
        sentiment = round(d["bullish_weight"] / scored_weight, 2) if scored_weight > 0 else 0.5
        result.append({
            "name":          name,
            "label":         name.replace("_", " ").title(),
            "score":         round(d["score"], 1),
            "pulse":         d["pulse"],
            "topTicker":     d["top_ticker"],
            "topScore":      round(d["top_score"], 1),
            "bullish":       d["bullish"],
            "bearish":       d["bearish"],
            "neutral":       d["neutral"],
            "bullishWeight": round(d["bullish_weight"], 1),
            "bearishWeight": round(d["bearish_weight"], 1),
            "sentiment":     sentiment,  # 0.0 = all bearish weight, 1.0 = all bullish weight (neutral excluded)
            "akerlofCount":  _sector_akerlof.get(name, 0),
            "macroPressure": round(_macro_pressure.get(name, 1.0), 4),
            "macroSignal":   _macro_signals.get(name, "neutral"),
            "industryGroups": sorted(
                [
                    {
                        "name":      ig_name,
                        "count":     igd["count"],
                        "topScore":  round(igd["top_score"], 1),
                        "topTicker": igd["top_ticker"],
                        "industries": sorted(
                            [
                                {
                                    "name":      ind_name,
                                    "count":     indd["count"],
                                    "topScore":  round(indd["top_score"], 1),
                                    "topTicker": indd["top_ticker"],
                                    "subIndustries": sorted(
                                        [
                                            {
                                                "name":      si_name,
                                                "count":     sid["count"],
                                                "topScore":  round(sid["top_score"], 1),
                                                "topTicker": sid["top_ticker"],
                                                "tickers":   sid["tickers"],
                                            }
                                            for si_name, sid in indd["sub_industries"].items()
                                        ],
                                        key=lambda x: -x["count"],
                                    ),
                                }
                                for ind_name, indd in igd["industries"].items()
                            ],
                            key=lambda x: -x["count"],
                        ),
                    }
                    for ig_name, igd in d["ig"].items()
                ],
                key=lambda x: -x["count"],
            ),
        })
    result.sort(key=lambda x: -x["score"])
    return result


def make_icon_png(size: int) -> bytes:
    """Generate a PNG icon: dark bg with green pulse ring + lighter center."""
    import zlib, struct
    W = H = size
    cx, cy = W / 2.0, H / 2.0
    BG    = (13, 17, 23)
    GREEN = (46, 160, 67)
    LGREEN= (63, 185, 80)
    rows  = []
    r_out = W * 0.46
    r_in  = W * 0.30
    for y in range(H):
        row = bytearray([0])
        for x in range(W):
            d = ((x - cx)**2 + (y - cy)**2) ** 0.5
            if d <= r_in:   row.extend(LGREEN)
            elif d <= r_out: row.extend(GREEN)
            else:            row.extend(BG)
        rows.append(bytes(row))
    raw  = b"".join(rows)
    comp = zlib.compress(raw, 9)
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)
    png  = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    return png


def build_pwa_assets() -> None:
    """Write manifest.json, sw.js, and icons to docs/."""
    # Icons
    for sz in (192, 512):
        (ICONS / f"icon-{sz}.png").write_bytes(make_icon_png(sz))

    # Manifest
    manifest = {
        "name": "Catalyst Edge Scanner",
        "short_name": "CE Scanner",
        "description": "Free SEC catalyst stock scanner — pre-market build plus hourly market-day refreshes with live prices",
        "start_url": "/?source=pwa",
        "display": "standalone",
        "background_color": "#0d1117",
        "theme_color": "#2ea043",
        "orientation": "portrait-primary",
        "categories": ["finance", "business"],
        "icons": [
            {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    (DOCS / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Service Worker — same-origin only. Never intercept third-party market-data proxies.
    sw = r"""const CACHE = '__SCANNER_PWA_VERSION__';
const PRECACHE = ['/', '/manifest.json', '/icons/icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks =>
    Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  if (e.request.destination === 'document') {
    e.respondWith(
      fetch(e.request).then(r => {
        const clone = r.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return r;
      }).catch(() => caches.match(e.request))
    );
  } else {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request))
    );
  }
});
"""
    sw = sw.replace("__SCANNER_PWA_VERSION__", SCANNER_PWA_VERSION)
    (DOCS / "sw.js").write_text(sw, encoding="utf-8")
    print("generate_seo_site: PWA assets written (manifest, sw.js, icons)")


def is_fresh(path: Path) -> bool:
    """Return True if the file was written today OR within an acceptable lookback.

    Before 4 AM ET, yesterday's data is the most recent — the daily pipeline
    hasn't run yet.  Treating it as stale would blank the scanner every night.
    After 4 AM ET we require today's date.

    Weekend rule (added 2026-04-25): on Saturday/Sunday US markets are closed
    and SEC EDGAR doesn't accept new filings, so the freshest possible signal
    IS Friday's close. Accept it rather than blanking insider/options panels
    all weekend.
    """
    if not path.exists():
        return False
    mtime = path.stat().st_mtime
    file_date = datetime.datetime.fromtimestamp(mtime, ET_TZ).date()
    today = NOW.date()
    if file_date == today:
        return True
    # Before 4 AM ET, accept yesterday's data
    if NOW.hour < 4 and file_date == today - datetime.timedelta(days=1):
        return True
    # Weekends: accept the most recent weekday close (Fri on Sat, Fri on Sun).
    weekday = NOW.weekday()  # Mon=0 ... Sun=6
    if weekday == 5 and file_date == today - datetime.timedelta(days=1):
        return True
    if weekday == 6 and file_date == today - datetime.timedelta(days=2):
        return True
    return False


def build_scanner_artifact_status(counts: dict[str, int], *, valid: bool, reason: str | None = None, page_bytes: int | None = None) -> dict:
    status = {
        "kind": "scanner_artifact_status",
        "generated_at": datetime.datetime.now(ET_TZ).isoformat(),
        "isodate": ISODATE,
        "valid": valid,
        "reason": reason,
        "counts": counts,
        "display_total": sum(counts.values()),
        "existing_index_present": OUT.exists(),
        "index_path": str(OUT.relative_to(ROOT)),
    }
    if page_bytes is not None:
        status["page_bytes"] = page_bytes
    return status


def write_scanner_artifact_status(status: dict) -> None:
    STATUS_OUT.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_csv(path, limit=10, require_fresh=False):
    """Load CSV rows. If require_fresh=True and file is not from today, return []."""
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    if require_fresh and not is_fresh(p):
        return rows
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
            if len(rows) >= limit:
                break
    return rows


def has_fresh_options_activity(max_age_hours: int = 36) -> bool:
    path = ROOT / "options_activity.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    max_age = datetime.timedelta(hours=max_age_hours)
    for row in payload.values():
        ts = row.get("ts")
        if not ts:
            continue
        try:
            dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        if (now_utc - dt.astimezone(datetime.timezone.utc)) <= max_age:
            return True
    return False


def e(v): return html_mod.escape(str(v)) if v else ""


def score_color(val, lo=3, mid=6, hi=9):
    try:
        v = float(val)
        if v >= hi:  return "#3fb950", "HIGH"
        if v >= mid: return "#d29922", "MED"
        if v >= lo:  return "#f0883e", "LOW"
    except Exception: pass
    return "#8b949e", "—"


def score_pill(val, lo=3, mid=6, hi=9):
    color, label = score_color(val, lo, mid, hi)
    return (f'<span class="score-pill" style="background:{color}22;'
            f'color:{color};border:1px solid {color}44">{e(val)}</span>')


def tag_chip(text):
    if not text or text in ("—", ""): return ""
    return f'<span class="chip">{e(text)}</span>'


def chg_span(val):
    try:
        v = float(val)
        color = "#3fb950" if v > 0 else "#f78166"
        arrow = "▲" if v > 0 else "▼"
        return f'<span style="color:{color}">{arrow} {abs(v):.1f}%</span>'
    except: return e(val)


def sparkline_svg(ticker: str, cache: dict, w=64, h=22) -> str:
    """Generate a tiny inline SVG sparkline from stooq daily cache."""
    entry = cache.get(ticker, {})
    rows  = entry.get("rows", [])
    if len(rows) < 2:
        return '<span style="color:#30363d;font-size:.7em">—</span>'
    closes = [r["close"] for r in rows[-7:] if r.get("close")]
    if len(closes) < 2:
        return '<span style="color:#30363d;font-size:.7em">—</span>'
    lo, hi = min(closes), max(closes)
    rng = hi - lo or 1
    pts = []
    for i, c in enumerate(closes):
        x = round(i / (len(closes) - 1) * (w - 4) + 2, 1)
        y = round((1 - (c - lo) / rng) * (h - 4) + 2, 1)
        pts.append(f"{x},{y}")
    color = "#3fb950" if closes[-1] >= closes[0] else "#f78166"
    pct = (closes[-1] - closes[0]) / closes[0] * 100
    sign = "+" if pct >= 0 else ""
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'style="vertical-align:middle">'
            f'<polyline points="{" ".join(pts)}" fill="none" '
            f'stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>'
            f'</svg>'
            f'<span style="color:{color};font-size:.75em;margin-left:4px">'
            f'{sign}{pct:.1f}%</span>')


def load_ga4_id() -> str:
    """Read GA4 measurement ID from .sec_email_env or environment."""
    import os
    # Check env var first (GitHub Actions secret)
    gid = os.environ.get("GA4_ID", "")
    if gid: return gid.strip()
    # Fall back to .sec_email_env file
    env_file = ROOT / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("GA4_ID="):
                return line.split("=", 1)[1].strip()
    return ""


def ga4_tag(gid: str) -> str:
    if not gid:
        return ""
    return f"""<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id={gid}"></script>
<script>
window.dataLayer=window.dataLayer||[];
function gtag(){{dataLayer.push(arguments);}}
gtag('js',new Date());
gtag('config','{gid}');
</script>"""


def load_polymarket() -> list:
    p = ROOT / "polymarket_signals.json"
    if not p.exists() or not is_fresh(p):
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("signals", [])
    except:
        return []


def polymarket_html(signals: list) -> str:
    """Always renders the Polymarket section shell.
    If pipeline signals are available they seed the cards immediately;
    the JS refreshPolymarket() fetches live from Gamma API 8s after load
    and replaces the grid regardless, so the section is always populated.
    """
    def fmt_vol(v):
        if v >= 1_000_000: return f"${v/1_000_000:.1f}M"
        if v >= 1_000:     return f"${v/1_000:.0f}K"
        return f"${v:.0f}"

    def prob_color(p):
        if p >= 70:  return ("#2ea043", "#1a3a1a", "LIKELY")
        if p >= 40:  return ("#d29922", "#2d2200", "CONTESTED")
        if p >= 15:  return ("#f0883e", "#2d1800", "UNLIKELY")
        return ("#f78166", "#2d1010", "LOW")

    def days_left(end):
        if not end: return ""
        try:
            d = (datetime.date.fromisoformat(end) - datetime.date.today()).days
            if d < 0:   return ""
            if d == 0:  return "⚡ Resolves TODAY"
            if d == 1:  return "⏰ Resolves TOMORROW"
            if d <= 7:  return f"⏳ {d}d left"
            return f"📅 {d}d left"
        except: return ""

    cards = ""
    # Filter out resolved markets: if end_date < today we are showing a stale
    # probability that can never update. Audited 2026-04-16 — e.g. "Israel x
    # Hezbollah ceasefire by April 15" was still rendering on April 16.
    today_iso = datetime.date.today().isoformat()
    live_signals = [
        s for s in signals
        if not s.get("end_date") or s.get("end_date", "9999-12-31") >= today_iso
    ]

    # Find max volume for relative volume bar scaling
    max_vol = max((float(s.get("vol_total", 0)) for s in live_signals[:8]), default=1) or 1

    for s in live_signals[:8]:
        prob   = float(s.get("probability", 0))
        title  = html_mod.escape(s.get("title", ""))
        impact = html_mod.escape(s.get("impact", ""))
        vol24  = float(s.get("vol_24h", 0))
        voltot = float(s.get("vol_total", 0))
        url    = s.get("url", "#")
        end    = s.get("end_date", "")
        color, bg, badge_label = prob_color(prob)
        countdown = days_left(end)
        hot_badge = f'<span class="pm-hot">🔥 HOT</span>' if vol24 >= 1_000_000 else ""

        # Tension classification for CSS
        deg = min(prob, 100) * 3.6  # probability → degrees (0-360)
        if 30 <= prob <= 70:
            tension = "high"    # contested — ring pulses
        elif prob >= 85:
            tension = "locked"  # consensus locked — steady glow
        else:
            tension = "low"     # low conviction — quiet

        # Ring thickness scales with volume (6px min, 14px max)
        vol_frac = voltot / max_vol
        thick = max(6, min(14, int(6 + vol_frac * 8)))

        # Urgency on imminent markets
        try:
            days_rem = (datetime.date.fromisoformat(end) - datetime.date.today()).days
            urgency = "hot" if 0 <= days_rem <= 3 else ""
        except:
            urgency = ""

        # Relative volume bar width
        vol_bar_w = int(vol_frac * 100)

        cards += f"""
<div class="pm-card" data-prob="{min(int(prob), 100)}" data-tension="{tension}" data-urgency="{urgency}"
     style="--pm-arc:{color};--pm-deg:{deg:.1f}deg;--pm-thick:{thick}px;--pm-glow:{color}">
  <div class="pm-ring-wrap">
    <div class="pm-ring-pulse"></div>
    <div class="pm-ring">
      <span class="pm-ring-pct" style="color:{color}">{prob:.0f}%</span>
    </div>
    <div class="pm-ring-urgency"></div>
  </div>
  <div class="pm-card-body">
    <div>
      <span class="pm-badge" style="background:{bg};color:{color};border-color:{color}44">{badge_label}</span>
      {hot_badge}
      {f'<span class="pm-countdown">{countdown}</span>' if countdown else ""}
    </div>
    <a href="{url}" target="_blank" rel="nofollow" class="pm-title">{title}</a>
    <div class="pm-meta">
      <span>{fmt_vol(voltot)} bet</span>
      <div class="pm-vol-bar"><div class="pm-vol-fill" style="width:{vol_bar_w}%"></div></div>
      {f'<span class="pm-24h">+{fmt_vol(vol24)} 24h</span>' if vol24 > 100_000 else ""}
    </div>
    {f'<div class="pm-impact">📊 <strong>{impact}</strong></div>' if impact else ""}
  </div>
</div>"""

    total_vol = sum(float(s.get("vol_total", 0)) for s in signals[:8])
    vol_str   = fmt_vol(total_vol) if total_vol else "Live"

    # Loading skeleton shown when pipeline has no cached signals
    # (JS will replace this within 8s from the live Gamma API)
    skeleton = "" if cards else """<div class="pm-loading">
  <span class="ltb-skeleton" style="font-size:.9em">⏳ Loading prediction market data…</span>
</div>"""

    return f"""
<div class="section" id="polymarket">
  <div class="section-head">
    <h2>🎯 Prediction Market Signals</h2>
    <span class="section-tag" id="pm-tag">{vol_str} in active bets</span>
  </div>
  <p class="section-sub">What real money is betting on right now — and which sectors it moves.
  High volume = high conviction. Contested markets = volatility ahead.</p>
  <div class="pm-grid" id="pm-grid">{skeleton if not cards else cards}</div>
  <p style="font-size:.72em;color:var(--muted);margin-top:12px;text-align:center">
    Data from <a href="https://polymarket.com" target="_blank" rel="nofollow">Polymarket</a> public API.
    Prediction markets do not guarantee outcomes. Not financial advice.
  </p>
</div>"""


def load_stooq_cache() -> dict:
    p = ROOT / ".stooq_daily_cache.json"
    if p.exists():
        try: return json.loads(p.read_text())
        except: pass
    return {}


def load_outcome_stats() -> dict:
    """Return key stats from sec_outcome_summary.csv for the track record section.

    Fix #1 (2026-04-27): when the new evaluator has populated `published_*`
    columns, mirror them onto the legacy field names so the headline reflects
    only score>=15 published picks (what subscribers actually see), not the
    raw evaluation noise floor that includes sub-threshold rows.

    Fix #6 (2026-04-27): when sec_walk_forward_summary.json exists, prefer the
    holdout-window hit rate over the in-sample number for honest reporting.
    """
    p = ROOT / "sec_outcome_summary.csv"
    if not p.exists():
        return {}
    rows = {}
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            list_name = row.get("list_name", "")
            pub_n = (row.get("published_rows") or "").strip()
            if pub_n and pub_n.isdigit() and int(pub_n) > 0:
                row["rows"] = pub_n
                row["wins"] = row.get("published_wins", row.get("wins", "0"))
                row["losses"] = row.get("published_losses", row.get("losses", "0"))
                if row.get("published_hit_rate_2pct"):
                    row["hit_rate_2pct"] = row["published_hit_rate_2pct"]
            rows[list_name] = row
    # Fix #6: walk-forward holdout overrides for the gappers headline.
    wf_path = ROOT / "sec_walk_forward_summary.json"
    if wf_path.exists():
        try:
            wf = json.loads(wf_path.read_text(encoding="utf-8"))
            tgt = wf.get("list_name")
            if tgt and tgt in rows and wf.get("holdout_n", 0) >= 30:
                rows[tgt]["holdout_hit_rate_2pct"] = str(wf.get("holdout_hit_rate_2pct"))
                rows[tgt]["holdout_avg_alpha_pct"] = str(wf.get("holdout_avg_alpha_pct"))
                rows[tgt]["decay_flag"] = "1" if wf.get("decay_flag") else "0"
        except Exception:
            pass
    return rows


def load_best_outcome() -> dict:
    """Return the best recent winning gap-play pick from sec_outcome_rows.csv.

    Scans the last ~14 calendar days of gap-list outcomes and returns the one
    with the largest next-day max run. Normalized keys: ticker, move_pct, date.
    """
    p = ROOT / "sec_outcome_rows.csv"
    if not p.exists():
        return {}
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    cutoff = today - _td(days=14)
    gap_lists = {"sec_clean_gappers", "sec_top_gappers"}
    best = {}
    best_move = 0.0
    try:
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("list_name", "") not in gap_lists:
                    continue
                d_str = row.get("list_date", "")
                try:
                    d = _date.fromisoformat(d_str)
                except Exception:
                    continue
                if d < cutoff or d > today:
                    continue
                try:
                    move = float(row.get("next_day_max_run_pct", 0) or 0)
                    close = float(row.get("filing_day_close", 0) or 0)
                    volume = float(row.get("next_volume", 0) or 0)
                except Exception:
                    continue
                # Credibility gates: real tradeable liquidity, not sub-penny
                # pump-and-dump noise. Without these, the "best winner" surface
                # becomes a showcase of unplayable microcap blowups.
                if close < 1.0 or volume < 100000:
                    continue
                if move > best_move and move < 100.0:
                    best_move = move
                    best = {
                        "ticker": row.get("ticker", ""),
                        "move_pct": move,
                        "date": d_str,
                    }
    except Exception:
        pass
    return best


def load_pro_tails(max_rows: int = 8) -> list[dict]:
    """Recent sub-dollar catalyst tails for the Edge Pro section.

    Gates: $0.10 ≤ close < $1.00, next_volume ≥ 10k, last 21 days, move < 300%.
    These are the historical micro-size plays retail can't execute safely but
    sophisticated traders can. Public-surface gate ($1+/100k+) rejected them.
    """
    p = ROOT / "sec_outcome_rows.csv"
    if not p.exists():
        return []
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    cutoff = today - _td(days=21)
    rows: list[dict] = []
    gap_lists = {"sec_clean_gappers", "sec_top_gappers"}
    seen_tickers: set[str] = set()
    try:
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("list_name", "") not in gap_lists:
                    continue
                d_str = row.get("list_date", "")
                try:
                    d = _date.fromisoformat(d_str)
                except Exception:
                    continue
                if d < cutoff or d > today:
                    continue
                try:
                    close = float(row.get("filing_day_close", 0) or 0)
                    volume = float(row.get("next_volume", 0) or 0)
                    move = float(row.get("next_day_max_run_pct", 0) or 0)
                except Exception:
                    continue
                if close < 0.10 or close >= 1.0:
                    continue
                if volume < 10000 or move <= 0 or move > 300.0:
                    continue
                tic = row.get("ticker", "").strip().upper()
                if not tic or tic in seen_tickers:
                    continue
                seen_tickers.add(tic)
                rows.append({
                    "ticker": tic,
                    "form": row.get("form", ""),
                    "date": d_str,
                    "close": close,
                    "volume": int(volume),
                    "move_pct": move,
                })
    except Exception:
        pass
    rows.sort(key=lambda r: (r["date"], r["move_pct"]), reverse=True)
    return rows[:max_rows]


def pro_tails_html(rows: list[dict]) -> str:
    """Render the Edge Pro sub-$1 catalyst tails section (free + pro views)."""
    if not rows:
        return ""
    pro_rows = "".join(
        f'''<tr>
          <td><strong style="color:var(--text)">{r["ticker"]}</strong></td>
          <td><span class="badge-form">{r["form"]}</span></td>
          <td>{r["date"]}</td>
          <td style="text-align:right">${r["close"]:.3f}</td>
          <td style="text-align:right">{r["volume"]:,}</td>
          <td style="text-align:right;color:var(--green);font-weight:700">+{r["move_pct"]:.1f}%</td>
        </tr>'''
        for r in rows
    )
    count = len(rows)
    avg_move = sum(r["move_pct"] for r in rows) / count if count else 0
    best = max(rows, key=lambda r: r["move_pct"])
    return f'''
<!-- EDGE PRO GATE: sub-$1 catalyst tails -->
<div class="wrap edge-gate-wrap" id="edge-pro-tails">
  <div class="edge-gate-head">
    <h2>🔒 Sub-$1 Catalyst Tails <span class="edge-pro-chip">Edge Pro</span></h2>
    <p class="section-sub">Micro-cap SEC catalysts the public scanner filters out.
      Sophisticated sizing territory — <strong>limit orders only, not for retail size</strong>.
      Last 21 days, {count} names, avg +{avg_move:.1f}% next-day run, best {best["ticker"]} +{best["move_pct"]:.1f}%.</p>
  </div>

  <!-- FREE TEASER (hidden for Pro) -->
  <div class="edge-free-teaser">
    <div class="edge-teaser-blur" aria-hidden="true">
      <table class="intel-table">
        <thead><tr><th>Ticker</th><th>Form</th><th>Date</th><th>Close</th><th>Volume</th><th>Max Run</th></tr></thead>
        <tbody>{pro_rows}</tbody>
      </table>
    </div>
    <div class="edge-teaser-card">
      <div class="edge-teaser-lock">🔒</div>
      <h3>{count} sub-$1 catalyst tails locked</h3>
      <p>Last 21 days · avg <strong style="color:var(--green)">+{avg_move:.1f}%</strong> next-day run ·
         best <strong>{best["ticker"]} +{best["move_pct"]:.1f}%</strong></p>
      <p class="edge-teaser-hint">Full filing thesis, options flow, sympathy peers, and real-time alerts
         are all gated behind Edge Pro.</p>
      <button class="edge-unlock-btn" type="button" onclick="openEdgeUnlock()">Unlock Edge Pro →</button>
      <div class="edge-teaser-fine">Already a subscriber? <a href="javascript:void(0)" onclick="openEdgeUnlock()">Send unlock link</a></div>
    </div>
  </div>

  <!-- PRO ACTUAL CONTENT (hidden until cookie present) -->
  <div class="edge-pro-only">
    {intel_table_shell(
        "intel-shell-pro-tails",
        "Sub-dollar tail archive",
        "Micro-cap catalyst history the public scanner filters out, surfaced for sophisticated sizing.",
        "Limit-order territory only — slippage is assumed, not an exception.",
        "PRO//TAIL",
        [
            intel_stat_chip("entries", str(count)),
            intel_stat_chip("avg run", f"+{avg_move:.1f}%"),
        ],
        f"""
    <div class="tbl-wrap">
      <table class="intel-table sortable">
        <thead><tr>
          <th data-sort="str">Ticker</th>
          <th data-sort="str">Form</th>
          <th data-sort="str">Date</th>
          <th data-sort="num">Close</th>
          <th data-sort="num">Volume</th>
          <th data-sort="num">Max Run</th>
        </tr></thead>
        <tbody>{pro_rows}</tbody>
      </table>
    </div>""",
        "Sub-$1 execution: use limit orders, size at 0.1–0.5% of book max. Research context, not signal.",
    )}
  </div>
</div>
'''


def trackrecord_html(stats: dict) -> str:
    """Build a verified track record section from outcome stats."""
    g = stats.get("sec_clean_gappers", {})
    if not g:
        return ""
    try:
        wins        = int(g.get("wins", 0))
        losses      = int(g.get("losses", 0))
        total       = wins + losses
        hit2        = float(g.get("hit_rate_2pct", 0))
        hit5        = float(g.get("hit_rate_5pct", 0))
        avg_run     = float(g.get("avg_next_day_max_run_pct", 0))
        rows_total  = int(g.get("rows", total))
    except Exception:
        return ""

    bar2 = min(int(hit2), 100)
    bar5 = min(int(hit5), 100)

    return f"""
  <!-- TRACK RECORD -->
  <div class="section" id="results">
    <div class="section-head">
      <h2>📈 Verified Track Record</h2>
      <span class="section-tag">Last 60 Days · {rows_total} Picks Evaluated</span>
    </div>
    <p class="section-sub">Every pick is logged. Every outcome is measured. No cherry-picking —
    this is the full {rows_total}-pick dataset evaluated automatically by our scoring engine.</p>

    <div class="track-grid">
      <div class="track-card">
        <div class="track-n" style="color:#3fb950">{hit2:.0f}%</div>
        <div class="track-label">Moved +2%+ next session</div>
        <div class="track-bar"><div style="width:{bar2}%;background:#3fb950"></div></div>
      </div>
      <div class="track-card">
        <div class="track-n" style="color:#d29922">{hit5:.0f}%</div>
        <div class="track-label">Hit +5%+ intraday high</div>
        <div class="track-bar"><div style="width:{bar5}%;background:#d29922"></div></div>
      </div>
      <div class="track-card">
        <div class="track-n" style="color:#58a6ff">{avg_run:.1f}%</div>
        <div class="track-label">Avg intraday high on catalyst plays</div>
        <div class="track-bar"><div style="width:{min(int(avg_run*5),100)}%;background:#58a6ff"></div></div>
      </div>
    </div>

    <div class="track-disclaimer">
      ⚠️ Past performance does not guarantee future results. These figures reflect historical
      scanner picks evaluated against next-day price data — not actual trade outcomes.
      Always manage risk. Free subscribers receive top 10; Premium receives all {rows_total}+ evaluated picks.
    </div>
  </div>"""


def intel_stat_chip(label: str, value: str) -> str:
    return (
        f'<span class="intel-shell-stat">'
        f'<span class="intel-shell-stat-k">{e(label)}</span>'
        f'<span class="intel-shell-stat-v">{e(value)}</span>'
        f"</span>"
    )


def intel_empty_state(icon: str, title: str, detail: str) -> str:
    return f"""
    <div class="intel-empty-state">
      <div class="intel-empty-icon">{e(icon)}</div>
      <div class="intel-empty-title">{e(title)}</div>
      <div class="intel-empty-detail">{e(detail)}</div>
    </div>"""


def intel_table_shell(
    module_class: str,
    overline: str,
    title: str,
    note: str,
    code: str,
    stat_chips: list[str],
    table_html: str,
    footnote: str = "",
) -> str:
    stats = "".join(stat_chips or [])
    foot = f'<div class="intel-shell-foot">{e(footnote)}</div>' if footnote else ""
    return f"""
    <div class="intel-shell solid-armor-card heavy-armor-card {module_class}">
      <div class="intel-shell-head">
        <div class="intel-shell-copy">
          <div class="intel-shell-kicker">{e(overline)}</div>
          <div class="intel-shell-title">{e(title)}</div>
          <div class="intel-shell-note">{e(note)}</div>
        </div>
        <div class="intel-shell-telemetry">
          <span class="intel-shell-code">{e(code)}</span>
          <div class="intel-shell-stats">{stats}</div>
        </div>
      </div>
      <div class="intel-table-chassis">{table_html}</div>
      {foot}
    </div>"""


def options_html(options_rows_data: list, feed_status: str = "ok") -> str:
    """Build the options activity section."""
    if not options_rows_data:
        unavailable = feed_status in {"missing", "stale"}
        title = "Fresh options feed unavailable" if unavailable else "No unusual options activity today"
        detail = (
            "This panel is intentionally suppressed because the live options scan did not produce a fresh dataset. "
            "We hide stale options flow rather than recycling old sweeps."
            if unavailable else
            "This section activates on high-volume catalyst days when short-interest tickers show "
            "significant call/put sweep signals. Check back during active market sessions."
        )
        shell = intel_table_shell(
            "intel-shell-options",
            "Derivative sweep lattice",
            "Public chain anomalies routed into the catalyst stack.",
            "Only fresh options flow is allowed to project into this console.",
            "OPT//FLOW",
            [
                intel_stat_chip("feed", feed_status.upper()),
                intel_stat_chip("packets", "0"),
            ],
            intel_empty_state("⚡", title, detail),
            "Sweeps stay hidden unless the live chain scan is fresh enough to trust.",
        )
        return f"""
  <!-- OPTIONS ACTIVITY -->
  <div class="section" id="options">
    <div class="section-head">
      <h2>⚡ Options Activity</h2>
      <span class="section-tag">Call/Put Flow · Sweeps · Top Strike</span>
    </div>
    <p class="section-sub">Unusual options volume on today's top catalyst picks.
    Volume/OI ratio &gt;3x signals a sweep. Bullish flow = call volume dominant.
    <em>Note: sourced from public market data, not FINRA dark pool prints.</em></p>
    {shell}
  </div>"""
    def signal_color(sig):
        if "bullish" in sig: return "#3fb950"
        if "bearish" in sig: return "#f78166"
        return "#8b949e"

    def fmt_premium(v):
        try:
            n = int(v)
            if n >= 1_000_000: return f"${n/1_000_000:.1f}M"
            if n >= 1_000:     return f"${n/1_000:.0f}K"
            return f"${n}"
        except: return "—"

    rows_html = ""
    for r in options_rows_data:
        t      = e(r.get("ticker", ""))
        cv     = r.get("call_vol", 0)
        pv     = r.get("put_vol", 0)
        sig    = r.get("signal", "neutral")
        strike = r.get("top_strike", "")
        expiry = e(r.get("expiry", ""))
        prem   = fmt_premium(r.get("premium_est", 0))
        uc     = int(r.get("unusual_calls", 0) or 0)
        sc     = signal_color(sig)
        try: cv_s = f"{int(cv):,}"
        except: cv_s = str(cv)
        try: pv_s = f"{int(pv):,}"
        except: pv_s = str(pv)
        try: strike_s = f"${float(strike):.2f}"
        except: strike_s = "—"
        unusual_badge = (f'<span style="background:#3fb95022;color:#3fb950;'
                         f'border:1px solid #3fb95044;border-radius:4px;'
                         f'padding:1px 6px;font-size:.78em">🔥 {uc}x sweep</span> '
                         if uc >= 2 else "")
        rows_html += f"""<tr {get_sector_attr(t)}>
  <td><strong class="ticker-link">{t}</strong></td>
  <td style="color:{sc};font-weight:600">{sig.title()}</td>
  <td style="color:#3fb950">{cv_s}</td>
  <td style="color:#f78166">{pv_s}</td>
  <td>{strike_s} {expiry}</td>
  <td>{prem} {unusual_badge}</td>
  <td><span id="live-p-{t}" data-live-price="{t}" class="live-price-cell">—</span></td></tr>"""

    table_html = f"""
    <div class="tbl-wrap">
      <table class="sortable intel-table">
        <thead><tr>
          <th data-sort="str">Ticker</th>
          <th data-sort="str">Signal</th>
          <th data-sort="num">Call Vol</th>
          <th data-sort="num">Put Vol</th>
          <th data-sort="str">Top Strike</th>
          <th data-sort="num">Est. Premium</th>
          <th>Live $</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""
    shell = intel_table_shell(
        "intel-shell-options",
        "Derivative sweep lattice",
        "Call / put aggression staged as a tactical acquisition surface.",
        "Premium size, dominant side, and strike concentration stay visible in one projection layer.",
        "OPT//FLOW",
        [
            intel_stat_chip("packets", str(len(options_rows_data))),
            intel_stat_chip("feed", "LIVE"),
        ],
        table_html,
        "Volume/OI > 3x is treated as a sweep. Public options flow only; this is not FINRA dark pool data.",
    )
    return f"""
  <!-- OPTIONS ACTIVITY -->
  <div class="section" id="options">
    <div class="section-head">
      <h2>⚡ Options Activity</h2>
      <span class="section-tag">Call/Put Flow · Sweeps · Top Strike</span>
    </div>
    <p class="section-sub">Unusual options volume detected on today's top catalyst picks.
    Volume/OI ratio &gt;3x signals a sweep. Bullish flow = call volume dominant.
    <em>Note: sourced from public market data, not FINRA dark pool prints.</em></p>
    {shell}
  </div>"""


def load_newsletter_top_pick() -> dict:
    """Load today's top pick from newsletter_picks.json with full data from sec_top_gappers.csv."""
    p = ROOT / "newsletter_picks.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("date") == ISODATE and d.get("top_pick"):
            ticker = d["top_pick"]
            # First try sec_top_gappers.csv for the full row (score, tags, price, link)
            gappers_file = ROOT / "sec_top_gappers.csv"
            if gappers_file.exists():
                with gappers_file.open(encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if row.get("ticker", "").upper() == ticker.upper():
                            return row
            # Fall back to sec_catalyst_latest.csv for at least link + form
            link, form = "#", "catalyst"
            latest = ROOT / "sec_catalyst_latest.csv"
            if latest.exists():
                with latest.open(encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if row.get("ticker", "").upper() == ticker.upper():
                            link = row.get("link", "#") or "#"
                            form = row.get("form", "catalyst") or "catalyst"
                            break
            return {"ticker": ticker, "form": form, "tags": "top pick", "link": link, "gapper_score": "—"}
    except Exception:
        pass
    return {}


def top_pick(gappers, squeezes, insiders):
    """Build the #1 spotlight card. Uses #1 from gappers list (which is
    already freshness-guarded). Falls back to newsletter_picks.json only
    when the gappers list is completely empty."""
    if not gappers:
        # No gap plays at all today — fall back to newsletter top pick
        nb = load_newsletter_top_pick()
        if not nb:
            return ""
        gappers = [nb]

    r     = gappers[0]
    t     = e(r.get("ticker", ""))
    score = r.get("gapper_score", "")
    form  = e(r.get("form", ""))
    tags  = e(r.get("tags", ""))
    link  = r.get("link", "#")
    handoff_reason = tags or build_filing_summary(form, r.get("tags", ""), score)
    hud_link = cerebro_handoff_url(
        t,
        rank=1,
        score=score,
        form=form,
        reason=handoff_reason,
        channel="spotlight",
    )
    color, _ = score_color(score, 4, 7, 9)

    # Check if also in squeeze list
    sq_match = next((s for s in squeezes if s.get("ticker") == r.get("ticker")), None)
    sq_badge = ""
    if sq_match:
        sq_score = sq_match.get("squeeze_score", "")
        sq_badge = f'<span class="badge-squeeze">🔥 Squeeze Score {e(sq_score)}</span>'

    # Check if also in insider list
    ins_match = next((i for i in insiders if i.get("ticker") == r.get("ticker")), None)
    ins_badge = ""
    if ins_match:
        count = ins_match.get("filing_count", "")
        ins_badge = f'<span class="badge-insider">🏛️ {e(count)} Insider Filings</span>'

    # Sector badge for top pick
    tp_sectors = _sector_lookup.get(r.get("ticker", "").upper(), [])
    sec_badge = ""
    if tp_sectors:
        sec_label = tp_sectors[0].replace("_", " ").title()
        sec_badge = f'<span class="badge-sector">{sec_label}</span>'

    thesis = e(humanize_signal_summary(build_filing_summary(form, r.get("tags", ""), score)))

    # ── Intelligence additions ─────────────────────────────────────────────
    # 1. 8-K items (replace boilerplate when available)
    items = _extract_8k_items(r.get("link", "")) if form.strip() == "8-K" else []
    items_html = ""
    if items:
        parts = [f'<span class="sp-item"><span class="sp-item-k">§{n}</span> {e(d)}</span>'
                 for n, d in items]
        items_html = f'<div class="spotlight-items">{"".join(parts)}</div>'

    # 2. Base rate — trust-builder, only render when n ≥ 10
    br = _compute_base_rate(form, score)
    base_rate_html = ""
    if br:
        h2 = int(round(br["hit2"] * 100))
        h5 = int(round(br["hit5"] * 100))
        n_label = "n=" + str(br["n"])
        if br["n"] < 30:
            n_label += " · small sample"
        base_rate_html = (
            f'<div class="spotlight-baserate" aria-label="Historical base rate">'
            f'<div class="sp-br-kicker">Historical edge · last {br["window"]}d · {br["bucket"]}</div>'
            f'<div class="sp-br-row">'
            f'<div class="sp-br-cell"><div class="sp-br-v">{h5}%</div>'
            f'<div class="sp-br-k">hit +5% intraday</div></div>'
            f'<div class="sp-br-cell"><div class="sp-br-v">{h2}%</div>'
            f'<div class="sp-br-k">hit +2% intraday</div></div>'
            f'<div class="sp-br-cell"><div class="sp-br-v">{n_label}</div>'
            f'<div class="sp-br-k">similar setups</div></div>'
            f'</div></div>'
        )

    # 3. Trade frame — Entry / Stop / T1 / T2 with ATR-based stop + 2R ladder.
    # Always renders (em-dashes when data truly unavailable).
    tf = _compute_trade_frame(r)
    if tf.get("price"):
        entry_v = f'${tf["price"]:.2f}'
        stop_v  = f'${tf["stop"]:.2f}'
        t1_v    = f'${tf["target1"]:.2f}'
        t2_v    = f'${tf["target2"]:.2f}'
        stop_method = tf.get("stop_method", "fixed")
        r_pct = tf.get("r_pct", 0)
        kicker = (
            f'Trade frame · {stop_method.upper()} stop · '
            f'R = ${tf.get("r_usd", 0):.2f} ({r_pct:.1f}%) · '
            f'{tf.get("conviction_tag", "")} · reference only, not advice'
        )
    else:
        entry_v = stop_v = t1_v = t2_v = '—'
        kicker = 'Trade frame · no live price for this ticker — check your broker at open'
    cells = [
        ('Entry',    entry_v, ''),
        ('Stop',     stop_v,  'sp-tf-stop'),
        ('Target 1', t1_v,    'sp-tf-target'),
        ('Target 2', t2_v,    'sp-tf-target'),
    ]
    if tf.get("avg_vol"):
        cells.append(('Avg Vol', _fmt_shares(tf["avg_vol"]), ''))
    if tf.get("cap"):
        cells.append(('Market Cap', _fmt_money(tf["cap"]), ''))
    if tf.get("float_approx"):
        cells.append(('Float ≈', _fmt_shares(tf["float_approx"]), ''))
    frame_cells = "".join(
        f'<div class="sp-tf-cell {cls}">'
        f'<div class="sp-tf-k">{k}</div><div class="sp-tf-v">{v}</div></div>'
        for k, v, cls in cells
    )
    trade_frame_html = (
        f'<div class="spotlight-tradeframe" aria-label="Trade frame">'
        f'<div class="sp-tf-kicker">{kicker}</div>'
        f'<div class="sp-tf-row">{frame_cells}</div>'
        f'</div>'
    )

    # 4. Penny-stock risk pill
    risk_pill = ""
    price_val = _num(r.get("price"))
    if 0 < price_val < 1:
        risk_pill = '<span class="badge-risk">⚠ Sub-$1 · volatility risk</span>'
    elif tf.get("float_approx") and tf["float_approx"] < 20_000_000:
        risk_pill = '<span class="badge-risk">⚠ Low float · volatility risk</span>'

    # 5. Normalized gap score display (anchored at 30)
    tier_label, tier_color = _score_tier(score)
    try:
        score_pct = min(float(score) / 30 * 100, 100)
    except (TypeError, ValueError):
        score_pct = 0

    ticker_len = max(len(t), 1)
    if ticker_len <= 5:
        ticker_fit_rem = 2.08
    elif ticker_len == 6:
        ticker_fit_rem = 1.88
    elif ticker_len == 7:
        ticker_fit_rem = 1.86
    elif ticker_len == 8:
        ticker_fit_rem = 1.64
    else:
        ticker_fit_rem = 1.42
    ticker_fit_class = ""
    if ticker_len >= 10:
        ticker_fit_class = " spotlight-ticker-tight"
    elif ticker_len >= 7:
        ticker_fit_class = " spotlight-ticker-compact"
    return f"""
<div class="spotlight-lamp-shell" id="primary-target" style="scroll-margin-top:113px">
  <div class="spotlight-lamp-beam spotlight-lamp-left" aria-hidden="true"></div>
  <div class="spotlight-lamp-beam spotlight-lamp-right" aria-hidden="true"></div>
  <div class="spotlight-lamp-core" aria-hidden="true"></div>
<div class="spotlight solid-armor-card spotlight-boot">
  <div class="spotlight-label">Primary Target · {TODAY}</div>
  <div class="spotlight-body spotlight-dossier spotlight-dossier-balanced">
    <div class="spotlight-rail spotlight-rail-left spotlight-col-left">
      <div class="spotlight-lockline">Rank 01 · Target armed</div>
      <div class="spotlight-ticker-wrap">
        <div class="spotlight-ticker{ticker_fit_class}" id="spotlight-ticker" data-ticker="{t}" data-ticker-len="{ticker_len}" style="color:{color};--ticker-fit-rem:{ticker_fit_rem:.2f}rem">{t}</div>
      </div>
      <div class="spotlight-live" id="spotlight-live"></div>
      <div class="spotlight-meta">
        <span class="badge-form">{form}</span>
        {f'<span class="badge-cat">{tags}</span>' if tags else ""}
        {sec_badge}{sq_badge}{ins_badge}{risk_pill}
      </div>
    </div>
    <div class="spotlight-rail spotlight-rail-center spotlight-col-center">
      <div class="spotlight-thesis-kicker">Catalyst Thesis</div>
      {items_html}
      <div class="spotlight-thesis">{thesis}</div>
      <div class="spotlight-score spotlight-score-normalized">
        <span class="spotlight-score-k">Gap Score</span>
        <span class="spotlight-score-v" style="color:{tier_color}">{e(score)}<span class="spotlight-score-max">/30</span></span>
        <span class="spotlight-score-tier" style="color:{tier_color}">{tier_label}</span>
        <div class="spotlight-score-bar"><div class="spotlight-score-fill" style="width:{score_pct:.0f}%;background:{tier_color}"></div></div>
      </div>
      {base_rate_html}
      {trade_frame_html}
    </div>
    <div class="spotlight-rail spotlight-rail-right spotlight-col-right">
      <a href="{hud_link}" class="btn btn-green sc-cerebro-link sc-cerebro-link-hero">Dock into Cerebro &rarr;</a>
      <a href="{link}" target="_blank" rel="nofollow" class="btn btn-outline sc-sec-link spotlight-sec-link" data-ticker="{t}" data-form="{form}" data-summary="{thesis}">View SEC Filing ↗</a>
    </div>
  </div>
  <div class="spotlight-footnote">
    <span class="spotlight-footnote-kicker">Premium adds</span>
    <span>Value plays &amp; moat tickers hidden from the public scanner, <strong style="color:#72e5ff">sector-beta scoring</strong>, and the full options-flow overlay.</span>
    <a href="https://catalystedge.agency" target="_blank" class="spotlight-footnote-link">Unlock free →</a>
  </div>
</div>
</div>"""


_GATE_PROOF    = ""   # set by main() from live outcome data
_LIVE_HIT2     = 0.0  # hit_rate_2pct from outcome CSV
_LIVE_PICKS    = 0    # evaluated pick count from outcome CSV
_LIVE_FILINGS  = 0    # today's filing count from sec_catalyst_latest.csv
_LIVE_TICKERS  = 0    # today's unique ticker count

def premium_gate_overlay(total_hidden: int, context: str = "tickers") -> str:
    """Render a premium gate overlay with blur backdrop and Stripe CTA."""
    proof = _GATE_PROOF or "Verified track record · Cancel anytime"
    return f"""
    <div class="premium-gate-overlay">
      <div class="premium-gate-content">
        <div class="premium-gate-lock">🔒</div>
        <div class="premium-gate-title">+{total_hidden} more {context} behind the gate</div>
        <div class="premium-gate-sub">Full dataset with CSV export, real-time alerts, and Cerebro HUD access.</div>
        <div class="premium-gate-buttons">
          <a href="{STRIPE_READER}" target="_blank" class="premium-gate-btn reader">Edge Reader — $9/mo</a>
          <a href="{STRIPE_PRO}" target="_blank" class="premium-gate-btn pro">Edge Pro — $39/mo</a>
        </div>
        <div class="premium-gate-proof">{proof}</div>
      </div>
    </div>"""


def gap_rows(rows, cache: dict = None, opts_map: dict = None, macro_tw: dict = None, nobel_map: dict = None, insider_map: dict = None, combo_map: dict = None, congress_map: dict = None):
    if not rows:
        return "<p class='empty-msg'>No gap plays today — check after 4 AM ET</p>"
    cache = cache or {}
    opts_map = opts_map or {}
    macro_tw = macro_tw or {}
    nobel_map = nobel_map or {}
    insider_map = insider_map or {}
    combo_map = combo_map or {}
    congress_map = congress_map or {}
    out = '<div class="scanner-grid">'
    for i, r in enumerate(rows):
        t     = e(r.get("ticker", ""))
        score = r.get("gapper_score", "")
        form  = e(r.get("form", ""))
        items = r.get("items", "")
        link  = r.get("link", "#")
        tags  = e(r.get("tags", ""))
        spark = sparkline_svg(r.get("ticker", ""), cache)
        opt   = opts_map.get(r.get("ticker", ""), {})
        opt_sig = opt.get("signal", "")
        combo_b = combo_badge(t, combo_map)
        cong_b = congress_badge(t, congress_map)

        # Score styling
        try:
            sc = float(score)
            if sc >= 9:   score_cls, score_color = "high",   "#3fb950"
            elif sc >= 6: score_cls, score_color = "medium", "#d29922"
            else:         score_cls, score_color = "low",    "#f0883e"
        except:
            sc, score_cls, score_color = 0, "low", "#f0883e"

        # Status badge
        badge = ""
        if sc >= 9:   badge = '<span class="status-badge hot">🔥 HOT</span>'
        elif sc >= 7: badge = '<span class="status-badge moving">⚡ MOVING</span>'

        # Options signal
        if opt_sig and opt_sig != "neutral":
            opt_color = "#3fb950" if "bullish" in opt_sig else "#f78166"
            opt_html = f'<span class="status-badge" style="background:#1a2a1a;color:{opt_color};border-color:{opt_color}44">{opt_sig.title()}</span>'
        else:
            opt_html = ""

        # Macro Tailwind badge — if ticker's sector has an active Polymarket signal
        macro_alert = ""
        if macro_tw:
            for sec in _sector_lookup.get(r.get("ticker", "").upper(), []):
                if sec in macro_tw:
                    # Extract the signal title from the stored badge html (data-tip="...")
                    raw_mb = macro_tw[sec]
                    import re as _re
                    m = _re.search(r'data-tip=["\']([^"\']+)["\']', raw_mb)
                    tip_txt = m.group(1) if m else "Active Polymarket macro signal"
                    macro_alert = f'<span class="macro-alert-badge" data-tip="{e(tip_txt)}">🌐 Macro Alert</span>'
                    break  # one badge per card is enough

        # Momentum bar from tags
        mom_pct = min(int(sc * 10), 100) if sc else 0
        mom_color = score_color

        ticker_raw = r.get("ticker", "").upper()
        handoff_reason = r.get("tags", "") or build_filing_summary(form, r.get("tags", ""), score)
        hud_link = cerebro_handoff_url(
            ticker_raw,
            rank=i + 1,
            score=score,
            form=form,
            reason=handoff_reason,
            channel="gap-card",
        )
        ns = nobel_map.get(ticker_raw, {})
        price_raw = r.get("price", "")
        market_flags_raw = r.get("market_flags", "")

        # ── Nobel badges ──────────────────────────────────────────────
        nobel_badges_html = ""
        badge_defs = []

        nash_d = ns.get("nash", {})
        if nash_d.get("nash_break"):
            peers_filed = nash_d.get("peers_filed", 0)
            peers_total = nash_d.get("peers_total", 0)
            sector_name = nash_d.get("sector", "sector").title()
            signal_type = nash_d.get("signal", "")
            if signal_type == "equilibrium_broken":
                nash_tip = f"Nash Equilibrium Break: only {peers_filed}/{peers_total} {sector_name} peers filed today — lone catalyst in quiet sector, high sympathy potential"
            else:
                nash_tip = f"Nash Partial Break: {peers_filed}/{peers_total} {sector_name} peers filed — below sector norm, limited competition"
            badge_defs.append(("🎯", "Nash", nash_tip, "#a371f7"))

        ak_d = ns.get("akerlof", {})
        if ak_d.get("asymmetry_score", 0) > 0.5 or ak_d.get("filing_opacity", 0) >= 0.7:
            opacity_pct = int(ak_d.get("filing_opacity", 0) * 100)
            conviction = ak_d.get("insider_conviction", 0)
            ak_tip = f"Akerlof Info Asymmetry: Signals a significant gap between insider knowledge and market price — filing opacity {opacity_pct}%, meaning key details are structurally withheld or minimized"
            if conviction > 0:
                ak_tip += f" · insider conviction score {conviction:.2f}"
            badge_defs.append(("🏅", "Akerlof", ak_tip, "#f0883e"))

        garch_d = ns.get("garch", {})
        _garch_regime = garch_d.get("regime", "")
        _garch_hot = _garch_regime in ("high_vol", "high_cluster") or garch_d.get("vol_ratio", 1.0) > 1.2
        if _garch_hot:
            vol_ratio = garch_d.get("vol_ratio", 1.0)
            regime_label = {"high_vol": "high volatility", "high_cluster": "vol clustering"}.get(_garch_regime, _garch_regime)
            garch_tip = f"GARCH Volatility Cluster: current vol is {vol_ratio:.2f}× long-run average — {regime_label} regime, elevated continuation probability"
            badge_defs.append(("📊", "GARCH", garch_tip, "#3fb950"))

        bsm_d = ns.get("bsm", {})
        if bsm_d.get("tension_score", 0) > 0.5 or bsm_d.get("signal", "") == "high_tension":
            tension_pct = bsm_d.get("tension_pct", 0)
            exp_move = bsm_d.get("expected_move_pct", 0)
            bsm_tip = f"Black-Scholes-Merton: Highlights mispriced options relative to the underlying stock's recent catalyst — {tension_pct:.1f}% tension vs max pain, market pricing {exp_move:.1f}% expected move"
            badge_defs.append(("⚗️", "BSM", bsm_tip, "#58a6ff"))

        for icon, label, tip, color in badge_defs:
            nobel_badges_html += f'<span class="nobel-badge" style="border-color:{color}44;color:{color}" data-tip="{e(tip)}">{icon} {label}</span>'

        # ── Conviction Clock ───────────────────────────────────────────
        conviction_clock_html = ""
        ins_row = insider_map.get(ticker_raw, {})
        if ins_row:
            filing_count = int(ins_row.get("filing_count", 0) or 0)
            confirmed_buy = int(ins_row.get("confirmed_buy", 0) or 0)
            latest_utc_str = ins_row.get("latest_utc", "")
            filing_utc_str = r.get("updated_utc", "")

            if filing_count >= 2:
                clock_str = ""
                try:
                    from datetime import datetime as _dt, timezone as _tz
                    def _parse_utc(s):
                        s = s.replace("Z", "+00:00")
                        return _dt.fromisoformat(s)
                    ins_time = _parse_utc(latest_utc_str) if latest_utc_str else None
                    fil_time = _parse_utc(filing_utc_str) if filing_utc_str else None
                    if ins_time and fil_time:
                        delta_mins = abs((ins_time - fil_time).total_seconds() / 60)
                        if delta_mins < 60:
                            clock_str = f"within {int(delta_mins)} min"
                        elif delta_mins < 1440:
                            clock_str = f"within {int(delta_mins/60)}h"
                        else:
                            clock_str = f"within {int(delta_mins/1440)}d"
                except: clock_str = "same window"

                # Detect equity compensation clusters (option grants/awards, no open-market buys)
                # Form 4 clusters with 0 confirmed buys = likely mass option grant event,
                # NOT an open-market purchase signal. Flag separately so traders aren't misled.
                is_equity_comp = (confirmed_buy == 0 and filing_count >= 5)

                if confirmed_buy > 0:
                    buy_label = f"{confirmed_buy} confirmed open-market buy{'s' if confirmed_buy != 1 else ''}"
                elif is_equity_comp:
                    buy_label = f"{filing_count} equity comp grants"
                else:
                    buy_label = f"{filing_count} Form 4 filings"

                if clock_str:
                    clock_label = f"{buy_label} {clock_str} of filing"
                else:
                    clock_label = f"{buy_label} clustered"

                if is_equity_comp:
                    # Amber styling — informational cluster, not a directional buy signal
                    conviction_clock_html = (
                        f'<div class="conviction-clock" style="color:#d29922;border-color:#d2992244;background:#1a1500">'
                        f'📋 Comp Cluster: {e(clock_label)}'
                        f' <span style="font-size:.65em;color:var(--muted)">(option grants — not open-market buys)</span>'
                        f'</div>'
                    )
                else:
                    akerlof_badge_inline = (
                        ' <span class="nobel-badge" style="border-color:#f0883e44;color:#f0883e"'
                        ' data-tip="Akerlof Information Asymmetry: insider cluster signals private knowledge before public price move">'
                        '🏅 Akerlof</span>'
                    ) if (confirmed_buy > 0 or filing_count >= 3) else ""
                    conviction_clock_html = f'<div class="conviction-clock">⏱ Conviction Clock: {e(clock_label)}{akerlof_badge_inline}</div>'

        # ── Sub-penny liquidity flag ──────────────────────────────────
        # Only show this warning when we have an actual positive sub-penny price.
        # Missing market data should not masquerade as a $0.000X OTC setup.
        liquidity_flag_html = ""
        try:
            price_val = float(price_raw) if price_raw else None
            is_subpenny = price_val is not None and 0 < price_val <= 0.001
            if is_subpenny:
                next_tick = round(price_val + 0.0001, 4)
                # Buy pressure = 2× avg daily dollar volume (minimum institutional flow
                # needed to exhaust the ask wall and sustain the price tick move).
                # Falls back to price-tier estimates when volume data is unavailable.
                try:
                    avg_vol = float(r.get("avg_vol_3m") or 0)
                    if avg_vol > 0:
                        raw_p = price_val * avg_vol * 2
                        if   raw_p >= 1_000_000: est_pressure = f"~${raw_p/1_000_000:.1f}M"
                        elif raw_p >= 1_000:     est_pressure = f"~${raw_p/1_000:.0f}K"
                        else:                    est_pressure = f"~${raw_p:.0f}"
                    elif price_val <= 0.0001:
                        est_pressure = "$1M–$5M"   # OTC floor: massive float, huge ask wall
                    elif price_val <= 0.0005:
                        est_pressure = "$500K–$2M"
                    else:
                        est_pressure = "$250K–$1M"
                except Exception:
                    est_pressure = "$500K–$2M"
                price_disp  = f"${price_val:.4f}"
                price_attr  = f"{price_val:.4f}"
                liquidity_flag_html = f'<div class="subpenny-flag" data-ticker="{t}" data-price="{price_attr}" data-next-tick="{next_tick:.4f}" data-est-pressure="{est_pressure}">⚠️ Sub-penny floor {price_disp} · Move to ${next_tick:.4f} needs ~{est_pressure} buy pressure · Scanner found filing first</div>'
        except Exception:
            pass

        # ── Score anatomy breakdown ───────────────────────────────────
        try:
            recency_min = int(r.get("recency_min", 0) or 0)
            if recency_min < 60:    recency_label = f"{recency_min} min ago"
            elif recency_min < 1440: recency_label = f"{recency_min//60}h {recency_min%60}m ago"
            else:                    recency_label = f"{recency_min//1440}d ago"
        except: recency_label = "today"

        raw_score = sc
        macro_mult = ns.get("composite_boost", 1.0)
        if macro_mult and macro_mult != 1.0:
            base_est = round(raw_score / macro_mult, 1)
        else:
            base_est = raw_score

        anatomy_rows = f"""
<div class="anatomy-row"><span class="anatomy-key">Form</span><span class="anatomy-val">{form} &nbsp;<span class="anatomy-pts">base weight</span></span></div>
<div class="anatomy-row"><span class="anatomy-key">Recency</span><span class="anatomy-val">{recency_label} &nbsp;<span class="anatomy-pts">+recency pts</span></span></div>
<div class="anatomy-row"><span class="anatomy-key">Base score</span><span class="anatomy-val"><strong>{base_est}</strong></span></div>"""

        if macro_mult != 1.0:
            mult_color = "#3fb950" if macro_mult > 1.0 else "#f78166"
            anatomy_rows += f'<div class="anatomy-row"><span class="anatomy-key">Nobel boost</span><span class="anatomy-val" style="color:{mult_color}">×{macro_mult:.2f} <span class="anatomy-pts">(composite)</span></span></div>'

        if nash_d.get("nash_break"):
            anatomy_rows += f'<div class="anatomy-row"><span class="anatomy-key">🎯 Nash</span><span class="anatomy-val">{nash_d.get("peers_filed",0)}/{nash_d.get("peers_total",0)} sector peers filed — equilibrium break</span></div>'
        if ak_d.get("asymmetry_score", 0) > 0.3 or ak_d.get("filing_opacity", 0) > 0.5:
            anatomy_rows += f'<div class="anatomy-row"><span class="anatomy-key">🏅 Akerlof</span><span class="anatomy-val">opacity {int(ak_d.get("filing_opacity",0)*100)}% — insider info advantage likely</span></div>'
        if garch_d.get("vol_ratio", 1.0) > 1.1:
            anatomy_rows += f'<div class="anatomy-row"><span class="anatomy-key">📊 GARCH</span><span class="anatomy-val">vol ratio {garch_d.get("vol_ratio",1.0):.2f}× — volatility clustering</span></div>'
        if bsm_d.get("tension_score", 0) > 0.3:
            anatomy_rows += f'<div class="anatomy-row"><span class="anatomy-key">⚗️ BSM</span><span class="anatomy-val">{bsm_d.get("tension_pct",0):.1f}% options tension vs max pain</span></div>'
        if ins_row and int(ins_row.get("filing_count",0) or 0) >= 2:
            anatomy_rows += f'<div class="anatomy-row"><span class="anatomy-key">⏱ Insiders</span><span class="anatomy-val">{ins_row.get("filing_count")} filings clustered — conviction signal</span></div>'

        anatomy_rows += f'<div class="anatomy-row anatomy-total"><span class="anatomy-key">Final score</span><span class="anatomy-val"><strong style="color:{score_color}">{e(str(score))}</strong></span></div>'

        anatomy_id = f"anatomy-{ticker_raw}"
        score_anatomy_html = f"""<div class="anatomy-toggle" onclick="this.nextElementSibling.classList.toggle('anatomy-open')">Score breakdown ▾</div>
<div class="anatomy-panel" id="{anatomy_id}">{anatomy_rows}</div>"""

        sec_attrs = get_sector_attr(r.get("ticker", ""))
        # Sub-penny cards get an extra "sub_penny" sector tag so they remain visible
        # in the "All Sectors" filter and aren't lost when users expect to see them
        if liquidity_flag_html:
            sec_attrs = sec_attrs.rstrip("'") + " sub_penny'"
        summary = e(humanize_signal_summary(build_filing_summary(form, r.get("tags", ""), score)))

        # Premium gate: close free grid, open blurred section
        if i == FREE_GAP_LIMIT and len(rows) > FREE_GAP_LIMIT:
            out += '</div>'  # close free scanner-grid
            out += f'<div class="premium-blur-wrap">'
            out += premium_gate_overlay(len(rows) - FREE_GAP_LIMIT, "gap plays")
            out += '<div class="premium-blur-content scanner-grid">'

        out += f"""<div class="scanner-card solid-armor-card sc-filterable{'  top-card' if i == 0 else ''}" {sec_attrs}>
  <div class="sc-severity sc-severity-{score_cls}"></div>
  <div class="sc-top">
    <div class="sc-ticker"><strong class="ticker-link">{t}</strong> {combo_b}{cong_b}</div>
    <div class="sc-badges">{badge}{form_badge_html(form, items)}{opt_html}</div>
  {macro_alert}
  </div>
  <div class="sc-command-shell">
    <div class="sc-command-core">
      <div style="text-align:center">
        <div class="sc-score-circle {score_cls}">{e(str(score))}</div>
        <div class="sc-score-label">Gap Score</div>
      </div>
      <div class="sc-primary">
        <div class="sc-thesis-kicker">Acquisition Thesis</div>
        <div class="sc-thesis">{summary}</div>
        <div class="sc-meta"><span class="sc-catalyst">{tags}</span></div>
      </div>
    </div>
  </div>
  {score_anatomy_html}
  {f'<div class="nobel-badges-row">{nobel_badges_html}</div>' if nobel_badges_html else ''}
  {conviction_clock_html}
  {liquidity_flag_html}
  <div class="sc-momentum">
    <span class="sc-momentum-label">Signal</span>
    <div class="sc-momentum-bar"><div class="sc-momentum-fill up" style="width:{mom_pct}%"></div></div>
    <span style="font-size:.75em;color:{mom_color};font-weight:700">{e(str(score))}</span>
  </div>
  <div class="sc-sparkline">{spark}</div>
  <div class="sc-bottom">
    <div class="sc-live-row">
      <span style="font-size:.75em;color:var(--muted)">Live Price</span>
      <span id="live-p-{t}" data-live-price="{t}" class="live-price-cell sc-live-price">—</span>
    </div>
    <div class="sc-actions">
      <a href="{hud_link}" class="btn btn-green sc-cerebro-link">Open in Cerebro &rarr;</a>
      <a href="{link}" target="_blank" rel="nofollow" class="btn btn-outline sc-sec-link"
         data-summary="{summary}"
         data-ticker="{t}" data-form="{form}">View SEC Filing ↗</a>
    </div>
  </div>
</div>"""
    if len(rows) > FREE_GAP_LIMIT:
        out += '</div></div>'  # close premium-blur-content + premium-blur-wrap
    out += '</div>'  # close scanner-grid (or the free portion)
    return out


def ranked_rows(rows, cache: dict = None, opts_map: dict = None, combo_map: dict = None, congress_map: dict = None):
    if not rows: return "<tr><td colspan='5' class='empty'>No data yet</td></tr>"
    cache = cache or {}
    opts_map = opts_map or {}
    combo_map = combo_map or {}
    congress_map = congress_map or {}
    out = ""
    for i, r in enumerate(rows):
        t     = e(r.get("ticker", ""))
        raw_score = r.get("priority_score", "")
        form  = e(r.get("form", ""))
        items = r.get("items", "")
        link  = r.get("link", "#")
        summary = e(build_filing_summary(form, r.get("tags", ""), raw_score))
        spark = sparkline_svg(r.get("ticker", ""), cache)
        combo = combo_badge(t, combo_map)
        cong = congress_badge(t, congress_map)
        opt_chip = mini_options_badge(opts_map.get(r.get("ticker", "")))
        age = age_human(r.get("recency_min", ""))
        blur_cls = ' class="premium-blur-row"' if i >= FREE_RANK_LIMIT else ""
        out += f"""<tr {get_sector_attr(t)}{blur_cls}>
  <td><strong class="ticker-link clickable-ticker" data-ticker="{t}" data-form="{form}" data-summary="{summary}" data-link="{link}">{t}</strong> {combo}{cong}{opt_chip} <span class="row-spark">{spark}</span></td>
  <td>{conviction_pill(raw_score, 60, raw_label=str(raw_score))}</td>
  <td>{form_badge_html(form, items)}</td>
  <td><span class="age-cell" title="Filed {age} ago">{age}</span></td>
  <td><button class="summary-btn" data-summary="{summary}" data-ticker="{t}" data-form="{form}" data-link="{link}">📄</button></td></tr>"""
    if len(rows) > FREE_RANK_LIMIT:
        out += f"""<tr class="premium-gate-row"><td colspan="5">
          <div class="premium-gate-inline">
            🔒 +{len(rows) - FREE_RANK_LIMIT} more ranked tickers ·
            <a href="{STRIPE_READER}" target="_blank">Unlock with Edge Reader — $9/mo</a>
          </div></td></tr>"""
    return out


def squeeze_rows(rows, cache: dict = None, opts_map: dict = None, combo_map: dict = None, congress_map: dict = None):
    if not rows: return "<tr><td colspan='6' class='empty'>No squeeze candidates today</td></tr>"
    cache = cache or {}
    opts_map = opts_map or {}
    combo_map = combo_map or {}
    congress_map = congress_map or {}
    out = ""
    for r in rows:
        t     = e(r.get("ticker", ""))
        raw_score = r.get("squeeze_score", "")
        stage = e(r.get("stage_emoji", "")) + " " + e(r.get("stage", ""))
        si    = r.get("short_pct_float", "")
        dtc   = r.get("days_to_cover", "")
        float_shares = r.get("float_shares", "") or r.get("float", "")
        try:    si_str = f"{float(si):.1f}%"
        except: si_str = e(si)
        try:    dtc_str = f"{float(dtc):.1f}d"
        except: dtc_str = e(dtc)
        # Float source rarely populated; fall back to a derived "Pressure" score (SI × DTC)
        try:
            fs = float(float_shares)
            float_str = f"{fs/1e9:.1f}B" if fs >= 1e9 else f"{fs/1e6:.0f}M" if fs >= 1e6 else f"{fs/1e3:.0f}k"
        except (TypeError, ValueError):
            try:
                pressure = float(si) * float(dtc)
                if pressure >= 100:
                    float_str = f'<b style="color:#ff6b6b">{pressure:.0f}</b>'
                elif pressure >= 50:
                    float_str = f'<b style="color:#f0883e">{pressure:.0f}</b>'
                elif pressure > 0:
                    float_str = f'{pressure:.0f}'
                else:
                    float_str = "—"
            except (TypeError, ValueError):
                float_str = "—"
        try:
            sq_badge = '<span class="status-badge squeezing">⚡ SQUEEZE</span>' if float(raw_score) > 20 else ''
        except:
            sq_badge = ''
        spark = sparkline_svg(r.get("ticker", ""), cache)
        combo = combo_badge(t, combo_map)
        cong = congress_badge(t, congress_map)
        opt_chip = mini_options_badge(opts_map.get(r.get("ticker", "")))
        sq_summary = e(f"Short squeeze candidate — {si_str} short float, {dtc_str} days to cover|Squeeze score {raw_score} — {r.get('stage', '')}|Pair with a catalyst filing for maximum conviction")
        out += f"""<tr {get_sector_attr(t)}>
  <td><strong class="ticker-link clickable-ticker" data-ticker="{t}" data-form="Short Squeeze" data-summary="{sq_summary}">{t}</strong> {sq_badge}{combo}{cong}{opt_chip} <span class="row-spark">{spark}</span></td>
  <td>{conviction_pill(raw_score, 110, raw_label=str(raw_score))}</td>
  <td>{stage}</td>
  <td>{si_str}</td>
  <td>{dtc_str}</td>
  <td><span class="float-cell" title="Float size — smaller = easier to squeeze">{float_str}</span></td></tr>"""
    return out


def insider_rows(rows, cache: dict = None, opts_map: dict = None, combo_map: dict = None, congress_map: dict = None):
    if not rows: return "<tr><td colspan='4' class='empty'>No insider clusters today</td></tr>"
    cache = cache or {}
    opts_map = opts_map or {}
    combo_map = combo_map or {}
    congress_map = congress_map or {}
    out = ""
    for r in rows:
        t     = e(r.get("ticker", ""))
        count = r.get("filing_count", "0")
        tags  = e(r.get("tags", ""))
        link  = r.get("primary_link", "#")
        try:    count_i = int(count)
        except: count_i = 0
        try:    confirmed_buy_i = int(str(r.get("confirmed_buy", "0")).strip() or 0)
        except: confirmed_buy_i = 0
        color = "#3fb950" if count_i >= 3 else "#d29922"

        # Latest-filing date
        latest_utc = (r.get("latest_utc") or "").strip()
        latest_disp = latest_utc[:10] if len(latest_utc) >= 10 else "—"

        # Buy-confirmation label
        if confirmed_buy_i > 0:
            buy_label = f'<span style="color:#3fb950;font-weight:700">✅ {confirmed_buy_i} buy{"s" if confirmed_buy_i != 1 else ""}</span>'
        elif count_i >= 5:
            buy_label = '<span style="color:#d29922;font-weight:600">📋 equity grants</span>'
        else:
            buy_label = '<span style="color:var(--muted);font-size:.85em">—</span>'

        # Contrarian Whale: multiple filings (2+) on a ticker with negative tags
        raw_tags = r.get("tags", "")
        has_neg_tag = any(part.strip().startswith("-") for part in raw_tags.split(";") if part.strip())
        is_whale = count_i >= 2 and has_neg_tag
        neg_tag_label = next((part.strip().lstrip("-") for part in raw_tags.split(";") if part.strip().startswith("-")), "negative signal")
        whale_tip = f"🐋 {count_i} insider filings despite [{neg_tag_label}] — possible accumulation"
        whale_badge = f'<span class="whale-badge" data-tip="{e(whale_tip)}">🐋 Contrarian Whale</span>' if is_whale else ""

        spark = sparkline_svg(r.get("ticker", ""), cache)
        combo = combo_badge(t, combo_map)
        cong = congress_badge(t, congress_map)
        opt_chip = mini_options_badge(opts_map.get(r.get("ticker", "")))

        ins_summary = e(build_filing_summary('4', r.get('tags', ''), count_i))
        all_links = e(r.get("all_links", link))
        out += f"""<tr {get_sector_attr(t)}>
  <td><strong class="ticker-link clickable-ticker" data-ticker="{t}" data-form="Form 4" data-summary="{ins_summary}" data-link="{link}" data-all-links="{all_links}" data-filing-count="{e(count)}">{t}</strong> {whale_badge}{combo}{cong}{opt_chip} <span class="row-spark">{spark}</span></td>
  <td><span style="color:{color};font-weight:700">{e(count)} filings</span> {buy_label}</td>
  <td>{tag_chip(tags)}</td>
  <td><span class="age-cell" title="Latest Form 4 filing date">{latest_disp}</span> &nbsp;<button class="summary-btn" data-summary="{ins_summary}" data-ticker="{t}" data-form="Form 4" data-link="{link}" data-all-links="{all_links}" data-filing-count="{e(count)}">📄 Filing</button></td></tr>"""
    return out


def darkpool_rows(rows, cache: dict = None, opts_map: dict = None, combo_map: dict = None, congress_map: dict = None):
    if not rows: return "<tr><td colspan='4' class='empty'>No unusual volume signals today</td></tr>"
    cache = cache or {}
    opts_map = opts_map or {}
    combo_map = combo_map or {}
    congress_map = congress_map or {}
    out = ""
    for r in rows:
        t      = e(r.get("ticker", ""))
        sig    = e(r.get("signal_type", "")).replace("_", " ").title()
        ratio  = r.get("volume_ratio", "")
        change = r.get("price_change_pct", "")
        try:    rc = "#3fb950" if float(ratio) >= 5 else "#d29922"; rs = f"{float(ratio):.1f}x"
        except: rc, rs = "#8b949e", e(ratio)
        try: chg_str = f"{float(change):+.1f}%"
        except: chg_str = str(change) or "—"
        spark = sparkline_svg(r.get("ticker", ""), cache)
        combo = combo_badge(t, combo_map)
        cong = congress_badge(t, congress_map)
        opt_chip = mini_options_badge(opts_map.get(r.get("ticker", "")))
        dp_summary = e(f"Unusual block volume — {rs} vs 30-day average|Signal type: {sig}|Price action: {chg_str} — institutional positioning watch")
        out += f"""<tr {get_sector_attr(t)}>
  <td><strong class="ticker-link clickable-ticker" data-ticker="{t}" data-form="Volume Signal" data-summary="{dp_summary}">{t}</strong> {combo}{cong}{opt_chip} <span class="row-spark">{spark}</span></td>
  <td>{tag_chip(sig)}</td>
  <td><span style="color:{rc};font-weight:700">{rs}</span></td>
  <td>{chg_span(change)}</td></tr>"""
    return out


# Polymarket → sector keyword mapping
_PM_SECTOR_KEYWORDS: list[tuple[list[str], list[str]]] = [
    (["iran", "defense", "military", "war", "conflict", "nato", "ukraine"],      ["energy", "industrials"]),
    (["oil", "opec", "crude", "energy", "lng", "gas"],                            ["energy"]),
    (["fed", "rate", "inflation", "fomc", "interest rate", "treasury"],           ["financials"]),
    (["ai", "semiconductor", "chip", "nvidia", "tech", "artificial intelligence"],["tech", "semis"]),
    (["biotech", "fda", "drug", "pharma", "approval", "trial"],                   ["biotech"]),
    (["tariff", "trade", "china", "import", "export"],                             ["industrials", "materials", "consumer"]),
    (["recession", "gdp", "unemployment", "jobs"],                                 ["financials", "consumer"]),
    (["crypto", "bitcoin", "ethereum", "btc"],                                     ["tech", "financials"]),
    (["real estate", "housing", "reit", "mortgage"],                               ["real_estate", "financials"]),
]

def _polymarket_tailwinds(pm_signals: list) -> dict:
    """Return {sector: badge_html} for sectors with Polymarket macro tailwinds.
    A sector gets a badge when a CONTESTED or HIGH-PROBABILITY signal matches it."""
    result: dict = {}
    for sig in pm_signals:
        prob = float(sig.get("probability", 0) or 0)
        label = sig.get("label", "").upper()
        if prob < 35 and label not in ("CONTESTED", "HIGH PROBABILITY", "LIKELY"):
            continue  # skip low-probability signals
        title  = (sig.get("title", "") + " " + sig.get("impact", "")).lower()
        for keywords, sectors in _PM_SECTOR_KEYWORDS:
            if any(kw in title for kw in keywords):
                pct = f"{prob:.0f}%"
                badge = f'<span class="macro-badge" data-tip="{e(sig.get("title",""))} — {pct} on Polymarket">🌐 Macro Tailwind</span>'
                for s in sectors:
                    if s not in result:  # first matching signal wins per sector
                        result[s] = badge
    return result


def _build_sector_data(rows, darkpool=None, pm_signals=None):
    """Shared computation for sector buttons + cards.
    Returns (leading, sec_vol, macro_tailwinds, rows[:8])."""
    leading = ""
    try:
        leading = max(rows, key=lambda r: float(r.get("sector_score", 0) or 0)).get("sector", "")
    except Exception:
        pass
    sec_vol: dict = {}
    if darkpool:
        for dp in darkpool:
            dp_t = dp.get("ticker", "").upper().strip()
            try:
                ratio = float(dp.get("volume_ratio", 0) or 0)
            except Exception:
                ratio = 0
            if ratio < 3:
                continue
            for s in _sector_lookup.get(dp_t, []):
                sec_vol[s] = sec_vol.get(s, 0) + 1
    macro_tw = _polymarket_tailwinds(pm_signals or [])
    return leading, sec_vol, macro_tw, rows[:8]


# GICS sector display labels — maps sector_lookup.json keys → human-readable names
GICS_LABELS: dict[str, str] = {
    "tech":        "Technology",
    "semis":       "Semiconductors",
    "biotech":     "Health Care",
    "financials":  "Financials",
    "consumer":    "Consumer",
    "comms":       "Communication",
    "industrials": "Industrials",
    "staples":     "Consumer Staples",
    "energy":      "Energy",
    "utilities":   "Utilities",
    "real_estate": "Real Estate",
    "materials":   "Materials",
}


def _gics_filter_counts(all_rows: list) -> dict[str, int]:
    """Count how many pipeline tickers fall into each GICS sector today."""
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for r in all_rows:
        t = (r.get("ticker") or "").upper().strip()
        if not t or t in seen:
            continue
        seen.add(t)
        for s in _sector_lookup.get(t, []):
            if s in GICS_LABELS:
                counts[s] = counts.get(s, 0) + 1
    return counts


def sector_filter_bar(rows, darkpool=None, pm_signals=None, all_rows=None):
    """Render sticky GICS filter buttons — sourced from sector_lookup.json, not news sectors.
    all_rows: ticker-containing rows (gappers/ranked) used for GICS count; rows kept for macro signals.
    """
    macro_tw = _polymarket_tailwinds(pm_signals or [])

    # Build sector counts from actual pipeline tickers (GICS-keyed)
    counts = _gics_filter_counts(all_rows or rows or [])

    # Sort by count descending; only show sectors that have at least 1 ticker today
    ordered = sorted(counts.items(), key=lambda x: -x[1])

    btns = '<button class="sec-filter-btn active" data-filter="all" onclick="setSectorFilter(this,\'all\')">All Sectors</button>'
    for sec_raw, cnt in ordered:
        label    = GICS_LABELS.get(sec_raw, sec_raw.replace("_", " ").title())
        has_macro = sec_raw in macro_tw
        macro_dot = ' <span class="macro-dot" data-tip="Macro tailwind active — Polymarket signal">🌐</span>' if has_macro else ""
        count_tag = f' <span class="sec-count">{cnt}</span>'
        btns += (f'<button class="sec-filter-btn" data-filter="{e(sec_raw)}" '
                 f'onclick="setSectorFilter(this,\'{e(sec_raw)}\')">'
                 f'{e(label)}{macro_dot}{count_tag}</button>')
    return f"""<div class="sector-sticky-wrap" id="sector-sticky-wrap">
  <div class="sector-filter-bar" id="sector-filter-bar">{btns}</div>
  <div id="sector-filter-status"></div>
</div>"""


def _news_sector_top_movers(sectors: list[str]) -> dict[str, dict]:
    """For each news sector, find the highest-scoring ticker from today's headlines.
    Reads bloomberg_headlines_used.csv (sector_tags, ticker_candidates, news_score columns)
    and falls back to bloomberg_headlines.csv if needed. Returns {sector: {ticker, score}}.
    Silent empty dict on any failure — card still renders without the mover chip."""
    wanted = {s for s in sectors if s}
    if not wanted:
        return {}
    out: dict[str, dict] = {}

    def _scan(path: Path, ticker_col: str, sector_col: str, score_col: str):
        if not path.exists():
            return
        try:
            with path.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    sec = (row.get(sector_col, "") or "").strip().split(",")[0].strip()
                    if not sec or sec not in wanted:
                        continue
                    tkr = (row.get(ticker_col, "") or "").strip().split(",")[0].strip().upper()
                    if not tkr or tkr.lower() in ("example", "nan"):
                        continue
                    try:
                        sc = float(row.get(score_col, 0) or 0)
                    except (ValueError, TypeError):
                        sc = 0.0
                    cur = out.get(sec)
                    if cur is None or sc > cur["score"]:
                        out[sec] = {"ticker": tkr, "score": sc}
        except Exception:
            return

    _scan(ROOT / "bloomberg_headlines_used.csv", "ticker_candidates", "sector_tags", "news_score")
    # Fallback / augment with bloomberg_headlines.csv (schema: ticker,sector)
    _scan(ROOT / "bloomberg_headlines.csv", "ticker", "sector", "")
    return out


def _news_sector_sparklines(sectors: list[str], days: int = 7) -> dict[str, list]:
    """Return {sector: [(date_iso, score), ...]} sorted oldest→newest, last N available days.
    Uses the 14-day lookback pattern (stops once `days` dates are found). Graceful empty
    when archive is stale or sparse — any sector with <2 points is omitted."""
    import datetime as _dt
    wanted = {s for s in sectors if s}
    if not wanted:
        return {}
    history: dict[str, list[tuple[str, float]]] = {}
    today = _dt.date.today()
    dates_checked = 0
    dates_found = 0
    d = today
    while dates_found < days and dates_checked < 14:
        dstr = d.isoformat()
        path = ROOT / f"news_sector_momentum_{dstr}.csv"
        if path.exists():
            try:
                with path.open(newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        sec = (row.get("sector") or "").strip()
                        if sec not in wanted:
                            continue
                        try:
                            sc = float(row.get("sector_score", 0) or 0)
                        except (ValueError, TypeError):
                            sc = 0.0
                        history.setdefault(sec, []).append((dstr, sc))
                dates_found += 1
            except Exception:
                pass
        d -= _dt.timedelta(days=1)
        dates_checked += 1
    # Only keep sectors with at least 2 data points; sort oldest→newest.
    return {
        s: sorted(pts, key=lambda x: x[0])
        for s, pts in history.items()
        if len(pts) >= 2
    }


def _news_sector_headlines(sectors: list[str], limit: int = 3) -> dict[str, list]:
    """Top N most-recent headlines per sector from today's bloomberg_headlines_used.csv.
    Returns {sector: [(ticker, headline, link), ...]}. Empty list per sector if no data."""
    wanted = {s for s in sectors if s}
    if not wanted:
        return {}
    out: dict[str, list] = {s: [] for s in wanted}
    path = ROOT / "bloomberg_headlines_used.csv"
    if not path.exists():
        return out
    try:
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sec = (row.get("sector_tags", "") or "").strip().split(",")[0].strip()
                if not sec or sec not in wanted or len(out[sec]) >= limit:
                    continue
                hl = (row.get("headline", "") or "").strip()
                if not hl or "Example" in hl[:12]:
                    continue
                tkr = (row.get("ticker_candidates", "") or "").strip().split(",")[0].strip().upper()
                link = (row.get("link", "") or "").strip()
                out[sec].append((tkr, hl, link))
    except Exception:
        return out
    return out


def _spark_svg(points: list, width: int = 120, height: int = 28, color: str = "#58a6ff") -> str:
    """Render a tiny sparkline SVG from [(date, score), ...] points (oldest→newest)."""
    if not points or len(points) < 2:
        return ""
    vals = [p[1] for p in points]
    vmin, vmax = min(vals), max(vals)
    rng = (vmax - vmin) or 1.0
    n = len(vals)
    step = width / (n - 1) if n > 1 else width
    pad = 2
    coords = []
    for i, v in enumerate(vals):
        x = i * step
        # invert y so higher score renders higher on screen
        y = pad + (height - pad * 2) * (1.0 - (v - vmin) / rng)
        coords.append(f"{x:.1f},{y:.1f}")
    path = "M " + " L ".join(coords)
    last_x, last_y = coords[-1].split(",")
    return (
        f'<svg class="sc-spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'aria-hidden="true" preserveAspectRatio="none">'
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="2" fill="{color}"/></svg>'
    )


def sector_html(rows, darkpool=None, pm_signals=None):
    """Render the sector momentum CARDS — tiered hero/standard/chip layout.

    - Top 3 (by sector_score) render as HERO cards: big score, top-mover chip,
      7-day sparkline, delta vs yesterday, headline expander.
    - Next 3 render as standard cards with sparkline + delta.
    - Remaining render as compact CHIPS (name + score only).
    All dynamic data (mover/sparkline/headlines) hides gracefully when absent."""
    if not rows:
        return "<p class='empty-msg'>No sector data today.</p>"
    leading, sec_vol, macro_tw, top_rows = _build_sector_data(rows, darkpool, pm_signals)

    # Sort top_rows by sector_score desc so tier ordering is always conviction-first.
    def _sf(r):
        try: return float(r.get("sector_score", 0) or 0)
        except: return 0.0
    top_rows = sorted(top_rows, key=_sf, reverse=True)
    sectors_in_view = [r.get("sector", "").strip() for r in top_rows if r.get("sector")]

    movers = _news_sector_top_movers(sectors_in_view)
    sparks = _news_sector_sparklines(sectors_in_view, days=7)
    headlines = _news_sector_headlines(sectors_in_view, limit=3)

    hero_html = ""
    mid_html = ""
    chip_html = ""

    for idx, r in enumerate(top_rows):
        sec_raw  = r.get("sector", "").strip()
        sec      = e(sec_raw).replace("_", " ").title()
        raw_score = r.get("sector_score", "")
        try:
            sf = float(raw_score)
            score_int = int(round(sf))
        except:
            sf, score_int = 0.0, 0
        try:
            hits_n = int(float(r.get("mentions", 0) or 0))
        except:
            hits_n = 0
        hits_word = "mention" if hits_n == 1 else "mentions"
        is_lead  = sec_raw == leading
        has_vol  = sec_vol.get(sec_raw, 0) >= 2
        bw = min(score_int, 100)
        color = "#3fb950" if sf >= 80 else "#d29922" if sf >= 50 else "#f0883e"

        lead_badge   = ' <span class="lead-sector-badge">🔥 Leading</span>' if is_lead else ""
        vol_card_tag = ' <span class="sc-vol-tag">Vol ↑</span>' if has_vol else ""
        macro_badge  = macro_tw[sec_raw].replace('title=', 'data-tip=') if sec_raw in macro_tw else ""

        # Top mover chip
        mover = movers.get(sec_raw)
        mover_html = ""
        if mover and mover.get("ticker"):
            mover_html = (
                f'<a class="sc-top-mover" href="/ticker/{e(mover["ticker"])}/" '
                f'data-tip="Top headline ticker in {e(sec)} today">'
                f'<span class="sc-tm-label">Top mover</span> '
                f'<span class="sc-tm-ticker">{e(mover["ticker"])}</span></a>'
            )

        # Sparkline + delta
        spark_points = sparks.get(sec_raw, [])
        spark_html = _spark_svg(spark_points, color=color) if len(spark_points) >= 2 else ""
        delta_html = ""
        if len(spark_points) >= 2:
            prev = spark_points[-2][1]
            curr = spark_points[-1][1]
            delta = curr - prev
            if abs(delta) >= 0.5:
                arrow = "▲" if delta > 0 else "▼"
                dcolor = "#3fb950" if delta > 0 else "#f78166"
                delta_html = f'<span class="sc-delta" style="color:{dcolor}">{arrow} {abs(delta):.0f}</span>'
            else:
                delta_html = '<span class="sc-delta" style="color:#8b949e">→ flat</span>'

        # Headlines expander — only show toggle if we have real headlines
        sec_heads = headlines.get(sec_raw) or []
        heads_html = ""
        toggle_html = ""
        if sec_heads:
            items = ""
            for tkr, hl, link in sec_heads:
                tkr_tag = f'<span class="sc-hl-ticker">{e(tkr)}</span> ' if tkr else ""
                if link:
                    items += f'<li>{tkr_tag}<a href="{e(link)}" target="_blank" rel="noopener">{e(hl)}</a></li>'
                else:
                    items += f'<li>{tkr_tag}{e(hl)}</li>'
            heads_html = f'<ul class="sc-headlines" hidden>{items}</ul>'
            toggle_html = (
                '<button type="button" class="sc-expand-btn" '
                'onclick="toggleSectorHeadlines(this)" aria-expanded="false">'
                'Why it\'s hot ▾</button>'
            )

        tier = "hero" if idx < 3 else ("chip" if idx >= 6 else "mid")

        if tier == "chip":
            chip_html += (
                f'<div class="sector-chip" data-sector-card="{e(sec_raw)}" '
                f'data-tip="{hits_n} {hits_word} · score {score_int}">'
                f'<span class="sc-chip-dot" style="background:{color}"></span>'
                f'<span class="sc-chip-name">{sec}</span>'
                f'<span class="sc-chip-score">{score_int}</span>'
                f'{macro_badge}</div>'
            )
            continue

        card_class = "sector-card hero" if tier == "hero" else "sector-card"
        card = f"""<div class="{card_class}" data-sector-card="{e(sec_raw)}">
  <div class="sc-head">
    <div class="sc-name">{sec}{lead_badge}{vol_card_tag}{macro_badge}</div>
    <div class="sc-score" data-tip="Sector momentum score — weighted sum of recency × news velocity">{score_int}</div>
  </div>
  <div class="sc-bar"><div style="width:{bw}%;background:{color};height:100%;border-radius:3px;transition:width .6s"></div></div>
  <div class="sc-meta">
    <span class="sc-mentions">{hits_n} {hits_word}</span>
    {delta_html}
    {spark_html}
  </div>
  {mover_html}
  {toggle_html}
  {heads_html}
</div>"""
        if tier == "hero":
            hero_html += card
        else:
            mid_html += card

    parts = []
    if hero_html:
        parts.append(f'<div class="sector-tier sector-tier-hero">{hero_html}</div>')
    if mid_html:
        parts.append(f'<div class="sector-tier sector-tier-mid">{mid_html}</div>')
    if chip_html:
        parts.append(f'<div class="sector-chips">{chip_html}</div>')
    return f'<div class="sector-grid" id="sector-cards">{"".join(parts)}</div>'


def build_8k_guide_page(gid: str = "") -> str:
    """Generate /how-to-trade-8k/ — SEO content page targeting 8-K trading searches."""
    ga = ga4_tag(gid)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>How to Trade SEC 8-K Filings Pre-Market — Complete Guide | Catalyst Edge</title>
<meta name="description" content="Step-by-step guide to trading SEC 8-K filings before the market opens. Learn which 8-K types cause the biggest gaps, how to find them on EDGAR before 4 AM ET, and how to size your position.">
<meta name="keywords" content="how to trade 8-K filings,SEC 8-K pre-market trading,8-K earnings surprise gap play,EDGAR 8-K filing types,trade SEC filings pre-market,8-K merger announcement trading,how to read 8-K filing stocks">
<meta name="author" content="Catalyst Edge">
<meta name="robots" content="index, follow">
<meta property="og:title" content="How to Trade SEC 8-K Filings Pre-Market — Complete Guide">
<meta property="og:description" content="Which 8-K types cause the biggest gaps, how to find them before 4 AM ET, and how to size your position. Free guide from Catalyst Edge.">
<meta property="og:url" content="{SITE}/how-to-trade-8k/">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary">
<meta name="twitter:site" content="@CatalystEdgePro">
<link rel="canonical" href="{SITE}/how-to-trade-8k/">
<script type="application/ld+json">{{
"@context":"https://schema.org","@type":"Article",
"headline":"How to Trade SEC 8-K Filings Pre-Market",
"description":"Complete guide to trading SEC 8-K catalyst filings before the market opens",
"url":"{SITE}/how-to-trade-8k/",
"dateModified":"{ISODATE}",
"publisher":{{"@type":"Organization","name":"Catalyst Edge","url":"https://catalystedge.agency"}}
}}</script>
<style>
@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;700&display=swap");
:root{{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#e6edf3;
  --muted:#8b949e;--green:#3fb950;--blue:#58a6ff;--orange:#f0883e;--red:#f78166}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.75;font-size:16px}}
a{{color:var(--blue);text-decoration:none}}
a:hover{{text-decoration:underline}}
.nav{{background:#0d1117ee;border-bottom:1px solid var(--border);
  padding:0 24px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100}}
.nav-brand{{font-weight:700;font-size:.95em;padding:12px 0;color:var(--text)}}
.nav a{{padding:12px 10px;color:var(--muted);font-size:.85em}}
.nav-cta{{background:var(--green);color:#0d1117!important;padding:6px 16px!important;
  border-radius:6px;font-weight:600;margin-left:auto}}
.hero{{padding:56px 24px 40px;background:radial-gradient(ellipse at 50% 0%,#1a2e1a,var(--bg) 70%);
  text-align:center}}
.hero h1{{font-size:2em;font-weight:800;letter-spacing:-.02em;max-width:760px;margin:0 auto 16px}}
.hero h1 span{{color:var(--green)}}
.hero-sub{{color:var(--muted);max-width:620px;margin:0 auto 28px}}
.btn{{display:inline-block;padding:12px 28px;border-radius:7px;font-weight:700;margin:4px}}
.btn-green{{background:var(--green);color:#0d1117}}
.btn-green:hover{{opacity:.88;text-decoration:none}}
.btn-out{{border:1px solid var(--border);color:var(--text)}}
.btn-out:hover{{background:var(--surface);text-decoration:none}}
.wrap{{max-width:820px;margin:0 auto;padding:48px 24px 80px}}
h2{{font-size:1.45em;font-weight:700;margin:48px 0 12px}}
h3{{font-size:1.1em;font-weight:700;margin:28px 0 8px;color:var(--green)}}
p{{color:var(--muted);margin-bottom:16px}}
strong{{color:var(--text)}}
ul,ol{{color:var(--muted);padding-left:22px;margin-bottom:16px}}
li{{margin-bottom:6px}}
.callout{{background:var(--surface);border-left:3px solid var(--green);
  border-radius:0 8px 8px 0;padding:16px 20px;margin:24px 0}}
.callout p{{margin:0}}
.callout.warn{{border-left-color:var(--orange)}}
.type-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:20px 0}}
.type-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px}}
.type-card .tc-name{{font-weight:700;font-size:.95em;margin-bottom:4px}}
.type-card .tc-impact{{font-size:.78em;margin-bottom:8px;font-weight:600}}
.type-card .tc-desc{{color:var(--muted);font-size:.82em;line-height:1.5}}
.steps{{counter-reset:step;margin:20px 0}}
.step{{display:flex;gap:16px;margin-bottom:24px;align-items:flex-start}}
.step-n{{background:var(--green);color:#0d1117;width:32px;height:32px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;font-weight:800;flex-shrink:0;font-size:.9em}}
.step-body h3{{margin-top:0}}
.step-body p{{margin-bottom:0}}
.time-table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:.9em}}
.time-table th{{background:var(--surface);color:var(--muted);padding:10px;
  border:1px solid var(--border);font-weight:600}}
.time-table td{{padding:10px;border:1px solid var(--border);color:var(--muted)}}
.time-table td:first-child{{color:var(--green);font-weight:700;white-space:nowrap}}
.cta-box{{background:linear-gradient(135deg,#1a2e1a,var(--surface));
  border:1px solid #2ea04344;border-radius:12px;padding:36px;text-align:center;margin-top:48px}}
.cta-box h2{{margin-top:0;margin-bottom:12px}}
footer{{background:var(--surface);border-top:1px solid var(--border);
  padding:28px 24px;text-align:center;color:var(--muted);font-size:.82em}}
footer a{{color:var(--blue);margin:0 6px}}
</style>
{ga}
</head>
<body>

<nav class="nav">
  <div class="nav-brand">⚡ Catalyst Edge</div>
  <a href="/">Scanner</a>
  <a href="/methodology/">Methodology</a>
  <a href="https://catalystedge.agency" target="_blank" rel="noopener noreferrer">Newsletter</a>
  <button class="nav-cta" type="button" onclick="(function(){{var p=document.getElementById('sub-popup');if(p){{p.classList.add('visible');var i=document.getElementById('sub-popup-email');if(i){{i.value='';setTimeout(function(){{i.focus();}},50);}}}}}})()">Subscribe Free</button>
</nav>

<section class="hero">
  <h1>How to Trade <span>SEC 8-K Filings</span> Pre-Market</h1>
  <p class="hero-sub">The 8-K is the most powerful filing on EDGAR. It covers earnings surprises,
  merger announcements, FDA decisions, and material events — and it drops overnight before most
  traders are awake. Here's how to act on it before the open.</p>
  <a href="/" class="btn btn-green">See Today's 8-K Picks →</a>
  <a href="#subscribe" class="btn btn-out">Get Free Daily Email</a>
</section>

<div class="wrap">

<h2>What Is an SEC 8-K Filing?</h2>
<p>An 8-K (also called a "Current Report") is a required SEC disclosure that public companies
must file within 4 business days of any <strong>material event</strong> — something significant
enough that investors would want to know about it immediately.</p>
<p>Unlike quarterly 10-Q or annual 10-K reports, 8-Ks are filed on-demand whenever something
major happens. This makes them the real-time pulse of a company — and the most actionable
filing type for pre-market traders.</p>

<div class="callout">
  <p><strong>Why 8-Ks matter for pre-market trading:</strong> EDGAR processes filings overnight.
  A company files an earnings surprise at 11 PM. By 3:30 AM, our scanner has scored it.
  By 4 AM pre-market open, you have the signal before the broader market reacts.
  That 30-minute window is where the edge lives.</p>
</div>

<h2>8-K Item Types That Move Stocks the Most</h2>
<p>Not all 8-Ks are equal. The item number tells you exactly what was filed.
Here are the types ranked by average price impact:</p>

<div class="type-grid">
  <div class="type-card">
    <div class="tc-name">Item 1.01 — Material Agreement</div>
    <div class="tc-impact" style="color:#3fb950">Impact: Very High ↑</div>
    <div class="tc-desc">Merger agreement, acquisition, major partnership.
    Often causes 20–100%+ gap up pre-market. Highest-impact 8-K type.</div>
  </div>
  <div class="type-card">
    <div class="tc-name">Item 2.02 — Results of Operations</div>
    <div class="tc-impact" style="color:#3fb950">Impact: High ↑↓</div>
    <div class="tc-desc">Earnings release. Beat = gap up. Miss = gap down.
    Most predictable catalyst — compare to analyst estimates.</div>
  </div>
  <div class="type-card">
    <div class="tc-name">Item 8.01 — Other Events</div>
    <div class="tc-impact" style="color:#d29922">Impact: Variable</div>
    <div class="tc-desc">Catch-all for material events not covered by other items.
    FDA approvals, clinical trial results, regulatory decisions often file here.</div>
  </div>
  <div class="type-card">
    <div class="tc-name">Item 1.02 — Terminated Agreement</div>
    <div class="tc-impact" style="color:#f78166">Impact: High ↓</div>
    <div class="tc-desc">Deal fell apart. Merger terminated. Contract cancelled.
    Usually a sharp gap down — short candidates if you catch it early.</div>
  </div>
  <div class="type-card">
    <div class="tc-name">Item 2.05 — Costs of Exit / Disposal</div>
    <div class="tc-impact" style="color:#f0883e">Impact: Moderate ↓</div>
    <div class="tc-desc">Restructuring, layoffs, facility closures.
    Can be positive (efficiency) or negative (financial distress).</div>
  </div>
  <div class="type-card">
    <div class="tc-name">Item 5.02 — Director/Officer Change</div>
    <div class="tc-impact" style="color:#d29922">Impact: Moderate</div>
    <div class="tc-desc">CEO departure, CFO replacement, board changes.
    Sudden unexplained exits are bearish. Known planned transitions are neutral.</div>
  </div>
</div>

<h2>The Pre-Market 8-K Trading Window: A Timeline</h2>
<table class="time-table">
  <thead><tr><th>Time (ET)</th><th>What Happens</th><th>Your Action</th></tr></thead>
  <tbody>
    <tr><td>11 PM – 2 AM</td><td>Companies file 8-Ks on EDGAR overnight</td><td>Sleep — scanner handles this</td></tr>
    <tr><td>3:00 AM</td><td>Catalyst Edge pulls all overnight filings</td><td>Scanner running automatically</td></tr>
    <tr><td>3:15 AM</td><td>Each ticker scored — catalyst strength calculated (filing type × sentiment × recency × macro)</td><td>—</td></tr>
    <tr><td>3:30 AM</td><td>Ranked picks published. Premium email sent.</td><td>Premium: review full list</td></tr>
    <tr><td>3:35 AM</td><td>Free email delivered</td><td>Free: review top 10</td></tr>
    <tr><td>4:00 AM</td><td>Pre-market opens</td><td>Place pre-market orders on high-conviction picks</td></tr>
    <tr><td>4:00–9:30 AM</td><td>Pre-market session — most gap action here</td><td>Manage positions, watch volume</td></tr>
    <tr><td>9:30 AM</td><td>Regular market opens — gap may fill or extend</td><td>Decision: hold through open or take pre-market profit</td></tr>
  </tbody>
</table>

<h2>Step-by-Step: How to Trade an 8-K Gap Play</h2>
<div class="steps">
  <div class="step">
    <div class="step-n">1</div>
    <div class="step-body">
      <h3>Identify the filing type and item number</h3>
      <p>Open the 8-K link from the scanner. Check the item number first (top of the filing).
      Item 1.01 merger or 2.02 earnings beat = highest priority. Item 5.02 officer change alone = lower priority.</p>
    </div>
  </div>
  <div class="step">
    <div class="step-n">2</div>
    <div class="step-body">
      <h3>Check the gap score and cross-reference signals</h3>
      <p>Gap Score 9–10 = strong catalyst. But the best setups combine multiple signals:
      8-K + high squeeze score + insider cluster = three-way confirmation.
      Single-signal picks (8-K only, no volume confirmation) are lower conviction.</p>
    </div>
  </div>
  <div class="step">
    <div class="step-n">3</div>
    <div class="step-body">
      <h3>Check the float and short interest</h3>
      <p>Small float (under 20M shares) + positive 8-K = larger percentage moves.
      High short interest (above 15%) + positive 8-K = squeeze potential on top of the catalyst.
      Large float stocks need stronger catalysts to move meaningfully.</p>
    </div>
  </div>
  <div class="step">
    <div class="step-n">4</div>
    <div class="step-body">
      <h3>Read the actual filing text — takes 2 minutes</h3>
      <p>Don't trade the headline alone. Scan the filing for: revenue figures vs prior year,
      deal terms and valuation multiples, any conditions or contingencies on a merger,
      whether an earnings beat is driven by one-time items.</p>
    </div>
  </div>
  <div class="step">
    <div class="step-n">5</div>
    <div class="step-body">
      <h3>Check pre-market price action before entering</h3>
      <p>If the stock is already up 40% pre-market at 4 AM, the gap may be fully priced in.
      Look for stocks that haven't moved yet despite a strong filing — these are the setups
      where institutional traders haven't positioned yet.</p>
    </div>
  </div>
  <div class="step">
    <div class="step-n">6</div>
    <div class="step-body">
      <h3>Size appropriately and set your stop</h3>
      <p>8-K plays are high-volatility by nature. Pre-market spreads are wider.
      Size smaller than your normal position. Set a hard stop below the pre-market low.
      The risk is binary — if the news is misread or context changes, moves are fast.</p>
    </div>
  </div>
</div>

<div class="callout warn">
  <p><strong>Common mistake:</strong> Trading an 8-K without reading the filing.
  A company can file an 8-K reporting a "material agreement" that's actually a small
  routine contract. The item number doesn't guarantee impact — the content does.
  Always read at least the first two paragraphs of the filing text.</p>
</div>

<h2>8-K vs Other Catalyst Filing Types</h2>
<p>The 8-K is the most common catalyst, but it's most powerful when combined with other
simultaneous EDGAR signals:</p>
<ul>
  <li><strong>8-K + Form 4 cluster:</strong> Company reports positive news AND 3+ insiders
  bought stock in the prior 48 hours. Insiders often accumulate before a filing drops.</li>
  <li><strong>8-K + S-3 registration:</strong> Positive news but company simultaneously
  registered shares for sale. This can cap the upside — dilution risk.</li>
  <li><strong>8-K + NT filing:</strong> Company reported something but also missed a
  reporting deadline. Mixed signal — tread carefully.</li>
  <li><strong>8-K + high squeeze score:</strong> Positive news on a heavily shorted stock.
  Shorts are forced to cover, amplifying the move beyond what the news alone would cause.</li>
</ul>

<h2>Where to Find 8-K Filings Before 4 AM</h2>
<p>Three options, from most to least effort:</p>
<ol>
  <li><strong>Catalyst Edge (free):</strong> All overnight 8-Ks scored and ranked automatically.
  Top 10 delivered to your inbox before 4 AM ET.
  <a href="/">View today's picks →</a></li>
  <li><strong>SEC EDGAR directly:</strong> <code>efts.sec.gov/LATEST/search-index?q=%228-K%22&dateRange=custom</code>
  — raw feed, no scoring, requires manual review of every filing.</li>
  <li><strong>Paid screeners ($25–$197/mo):</strong> Benzinga Pro, Trade-Ideas — provide 8-K alerts
  but without the multi-factor catalyst scoring, squeeze cross-reference, or insider cluster detection.</li>
</ol>

<div class="cta-box">
  <h2>Get Every 8-K Gap Play Before 4 AM — Free</h2>
  <p style="color:var(--muted);margin-bottom:22px;max-width:480px;margin-left:auto;margin-right:auto">
    300+ EDGAR filings scored every night. Top 10 gap candidates delivered before pre-market opens.
    No login. No credit card. Cancel anytime.
  </p>
  <a href="#subscribe" class="btn btn-green">Subscribe Free →</a>
  &nbsp;
  <a href="/" class="btn btn-out">View Today's Scanner</a>
</div>

</div><!-- /wrap -->

<footer>
  <div>Catalyst Edge — Free Daily SEC EDGAR Gap Scanner</div>
  <div style="margin:8px 0">
    <a href="/">Scanner</a>
    <a href="/methodology/">How It Works</a>
    <a href="/how-to-trade-8k/">8-K Guide</a>
    <a href="https://catalystedge.agency" target="_blank" rel="noopener noreferrer">Newsletter</a>
    <a href="https://t.me/CatalystEdgePro" target="_blank" rel="noopener noreferrer">Telegram</a>
    <a href="https://twitter.com/CatalystEdgePro" target="_blank" rel="noopener noreferrer">X / Twitter</a>
  </div>
  <div style="font-size:.75em;margin-top:8px;opacity:.6">
    Data from SEC EDGAR public feeds. Not financial advice. For informational purposes only.
  </div>
</footer>

</body>
</html>"""


def build_methodology_page(gid: str = "") -> str:
    """Generate /methodology/index.html — full SEO content page targeting EDGAR search terms."""
    ga = ga4_tag(gid)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>How Our SEC Catalyst Scanner Works — Scoring Methodology | Catalyst Edge</title>
<meta name="description" content="How Catalyst Edge scores 300+ SEC EDGAR filings daily to find pre-market gap plays. Full methodology: gap scoring, squeeze radar, insider clusters, block volume signals, and options activity.">
<meta name="keywords" content="SEC EDGAR catalyst scoring methodology,how to use EDGAR for day trading,8-K earnings surprise scanner,Form 4 insider buying signal,short squeeze scanner methodology,SEC filing types explained,pre-market gap scanner how it works">
<meta name="author" content="Catalyst Edge">
<meta name="robots" content="index, follow">
<meta property="og:title" content="How Our SEC Catalyst Scanner Works — Scoring Methodology">
<meta property="og:description" content="Full methodology: how we score 300+ SEC EDGAR filings nightly to surface pre-market gap plays, squeeze setups, and insider clusters before 4 AM ET.">
<meta property="og:url" content="{SITE}/methodology/">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary">
<meta name="twitter:site" content="@CatalystEdgePro">
<link rel="canonical" href="{SITE}/methodology/">
<link rel="stylesheet" href="/lib/cinematic.css">
<script type="application/ld+json">{{
"@context":"https://schema.org","@type":"Article",
"headline":"How Our SEC Catalyst Scanner Works — Scoring Methodology",
"description":"Full methodology for scoring 300+ SEC EDGAR filings nightly to find pre-market gap plays",
"url":"{SITE}/methodology/",
"dateModified":"{ISODATE}",
"publisher":{{"@type":"Organization","name":"Catalyst Edge","url":"https://catalystedge.agency"}},
"mainEntityOfPage":{{"@type":"WebPage","@id":"{SITE}/methodology/"}}
}}</script>
<style>
:root{{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#e6edf3;
  --muted:#8b949e;--green:#3fb950;--blue:#58a6ff;--orange:#f0883e}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.75;font-size:16px}}
a{{color:var(--blue);text-decoration:none}}
a:hover{{text-decoration:underline}}
.nav{{background:#0d1117ee;border-bottom:1px solid var(--border);
  padding:0 24px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100}}
.nav-brand{{font-weight:700;font-size:.95em;padding:12px 0;color:var(--text)}}
.nav a{{padding:12px 10px;color:var(--muted);font-size:.85em}}
.nav-cta{{background:var(--green);color:#0d1117!important;padding:6px 16px!important;
  border-radius:6px;font-weight:600;margin-left:auto}}
.hero{{padding:56px 24px 40px;background:radial-gradient(ellipse at 50% 0%,#1a2e1a,var(--bg) 70%);
  text-align:center}}
.hero h1{{font-size:2em;font-weight:800;letter-spacing:-.02em;
  max-width:720px;margin:0 auto 16px}}
.hero h1 span{{color:var(--green)}}
.hero-sub{{color:var(--muted);max-width:600px;margin:0 auto 28px}}
.hero-cta{{display:inline-block;background:var(--green);color:#0d1117;
  padding:12px 28px;border-radius:7px;font-weight:700;margin:4px}}
.hero-cta:hover{{opacity:.88;text-decoration:none}}
.hero-sec{{display:inline-block;border:1px solid var(--border);color:var(--text);
  padding:12px 28px;border-radius:7px;font-weight:600;margin:4px}}
.wrap{{max-width:820px;margin:0 auto;padding:48px 24px 80px}}
h2{{font-size:1.45em;font-weight:700;margin:48px 0 12px;color:var(--text)}}
h2:first-child{{margin-top:0}}
h3{{font-size:1.1em;font-weight:700;margin:28px 0 8px;color:var(--green)}}
p{{color:var(--muted);margin-bottom:16px}}
strong{{color:var(--text)}}
ul,ol{{color:var(--muted);padding-left:22px;margin-bottom:16px}}
li{{margin-bottom:6px}}
.callout{{background:var(--surface);border-left:3px solid var(--green);
  border-radius:0 8px 8px 0;padding:16px 20px;margin:24px 0}}
.callout p{{margin:0}}
.score-box{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  gap:12px;margin:20px 0}}
.score-item{{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:16px;text-align:center}}
.score-item .score-n{{font-size:1.6em;font-weight:800;color:var(--green)}}
.score-item .score-l{{color:var(--muted);font-size:.82em;margin-top:4px}}
.filing-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:20px 0}}
.filing-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px}}
.filing-card .fc-name{{font-weight:700;color:var(--text);font-size:.95em;margin-bottom:6px}}
.filing-card .fc-desc{{color:var(--muted);font-size:.83em;line-height:1.5}}
.faq-item{{border-bottom:1px solid var(--border);padding:18px 0}}
.faq-item:last-child{{border-bottom:none}}
.faq-q{{font-weight:700;color:var(--text);margin-bottom:8px;cursor:pointer}}
.faq-a{{color:var(--muted);font-size:.92em}}
.tier-table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:.9em}}
.tier-table th{{background:var(--surface);color:var(--muted);padding:10px;
  border:1px solid var(--border);font-weight:600;text-align:center}}
.tier-table td{{padding:10px;border:1px solid var(--border);text-align:center}}
.tier-table .tier-us{{background:#1a2b1a22;color:var(--green);font-weight:700}}
footer{{background:var(--surface);border-top:1px solid var(--border);
  padding:28px 24px;text-align:center;color:var(--muted);font-size:.82em}}
footer a{{color:var(--blue);margin:0 6px}}
</style>
{ga}
</head>
<body>

<!-- CINEMATIC SHELL — utopian-cyberpunk atmosphere overlay -->
<div class="ce-field" aria-hidden="true">
  <div class="ce-field-orb a"></div><div class="ce-field-orb b"></div><div class="ce-field-orb c"></div>
  <div class="ce-scanline"></div><div class="ce-scanline" style="animation-delay:-3s;opacity:.3"></div>
  <div class="ce-vignette"></div>
</div>
<canvas id="ce-particles" aria-hidden="true"></canvas>

<nav class="nav">
  <div class="nav-brand">⚡ Catalyst Edge</div>
  <a href="/">Scanner</a>
  <a href="https://catalystedge.agency" target="_blank" rel="noopener noreferrer">Newsletter</a>
  <a href="https://t.me/CatalystEdgePro" target="_blank" rel="noopener noreferrer">Telegram</a>
  <button class="nav-cta" type="button" onclick="(function(){{var p=document.getElementById('sub-popup');if(p){{p.classList.add('visible');var i=document.getElementById('sub-popup-email');if(i){{i.value='';setTimeout(function(){{i.focus();}},50);}}}}}})()">Subscribe Free</button>
</nav>

<section class="hero">
  <h1>How Our <span>SEC Catalyst Scanner</span> Works</h1>
  <p class="hero-sub">Every morning before 4 AM ET, we pull 300+ SEC EDGAR filings,
  score every ticker, and surface the highest-probability pre-market setups.
  Here's exactly how — no black box.</p>
  <a href="/" class="hero-cta">← View Today's Picks</a>
  <a href="#subscribe" class="hero-sec">Get Free Daily Email</a>
</section>

<div class="wrap">

<h2>Overview: Why SEC Filings Are the Best Pre-Market Edge</h2>
<p>Most traders react to price moves. By the time a stock shows up in a screener,
institutions have already positioned. SEC EDGAR is the one place where material information
must be disclosed publicly — and it's available to everyone at the same time.</p>
<p>The problem: EDGAR processes thousands of filings nightly. Sorting signal from noise
manually is impossible before a 4 AM pre-market open. That's what our scanner does automatically.</p>

<div class="callout">
  <p><strong>Core insight:</strong> A stock with a material SEC filing (earnings surprise, insider cluster,
  merger announcement) + high short interest + unusual volume = the three-way catalyst setup that
  historically produces the largest pre-market gap moves. Our scoring engine finds these combinations
  every night before you wake up.</p>
</div>

<h2>Data Source: SEC EDGAR RSS Feeds</h2>
<p>We pull directly from <strong>SEC EDGAR's official RSS feeds</strong> — the same primary source used by
Bloomberg terminals. Every filing that hits EDGAR overnight is captured and processed. No third-party
data vendor, no delay, no markup.</p>
<p>Filing types monitored every night:</p>
<div class="filing-grid">
  <div class="filing-card">
    <div class="fc-name">8-K — Current Report</div>
    <div class="fc-desc">Earnings surprises, merger agreements, material events, FDA decisions.
    Highest-impact filing for gap plays.</div>
  </div>
  <div class="filing-card">
    <div class="fc-name">Form 4 — Insider Transaction</div>
    <div class="fc-desc">Buying/selling by officers, directors, and 10%+ owners.
    Cluster of 3+ insider buys is our strongest signal.</div>
  </div>
  <div class="filing-card">
    <div class="fc-name">S-3 — Shelf Registration</div>
    <div class="fc-desc">Company registered shares for sale — can signal dilution risk
    or upcoming capital raise.</div>
  </div>
  <div class="filing-card">
    <div class="fc-name">13D / 13G — Activist Disclosure</div>
    <div class="fc-desc">An investor crossed 5% ownership and disclosed intent.
    13D signals activist positioning — historically bullish catalyst.</div>
  </div>
  <div class="filing-card">
    <div class="fc-name">NT 10-K / NT 10-Q — Late Filing</div>
    <div class="fc-desc">Company missed reporting deadline. Can signal accounting problems
    or major unreported events.</div>
  </div>
  <div class="filing-card">
    <div class="fc-name">6-K — Foreign Private Issuer</div>
    <div class="fc-desc">International company material event — merger agreements,
    earnings releases, strategic announcements.</div>
  </div>
</div>

<h2>Gap Score (0–10): How We Rank Each Ticker</h2>
<p>Every ticker that appears in an overnight EDGAR filing gets a <strong>Gap Score from 0–10</strong>.
This is not a simple filing-count metric — it's a weighted composite of five independent signals:</p>

<h3>1. Filing Recency &amp; Impact Weight</h3>
<p>Filings processed within the last 6 hours before the scanner runs get full recency weight.
8-K filings score highest (earnings surprise, merger). Form 4 clusters score based on
number of insiders and transaction size. Late filings (NT) are flagged as risk signals.</p>

<h3>2. Volume Signal vs 30-Day Average</h3>
<p>We pull the last 30 days of volume data from public market sources and calculate each
ticker's volume ratio. A stock trading at 5x its 30-day average volume alongside a material
filing is a high-conviction setup. Ratio of 10x+ triggers a "block volume" flag.</p>

<h3>3. Insider Signal Strength</h3>
<p>Form 4 filings from the same ticker within a 48-hour window are clustered. A single
insider buy scores low. Three or more different insiders buying within 48 hours scores
maximum insider weight — this pattern historically precedes positive announcements.</p>

<h3>4. Short Interest (Squeeze Potential)</h3>
<p>Short float and days-to-cover are pulled from public short interest data.
Tickers with &gt;15% short float combined with a positive catalyst filing score additional
squeeze multiplier — the combination creates forced covering pressure.</p>

<h3>5. Filing Sentiment Score</h3>
<p>We extract the raw text from each SEC filing and run a keyword sentiment pass.
Phrases like "record revenue," "strategic merger," "insider acquisition" score positive.
Phrases like "going concern," "material weakness," "SEC investigation" score negative.
The sentiment score adjusts the final Gap Score up or down.</p>

<div class="score-box">
  <div class="score-item"><div class="score-n">9–10</div><div class="score-l">Strong catalyst — high filing + macro signal</div></div>
  <div class="score-item"><div class="score-n">6–8</div><div class="score-l">Watch list — solid setup</div></div>
  <div class="score-item"><div class="score-n">3–5</div><div class="score-l">Speculative — monitor only</div></div>
  <div class="score-item"><div class="score-n">0–2</div><div class="score-l">Low conviction — filtered out</div></div>
</div>

<h2>Squeeze Radar: Short Interest + Catalyst = Forced Covering</h2>
<p>A short squeeze requires two ingredients: high short interest and a catalyst that forces
short sellers to cover. Our scanner finds tickers where both conditions exist simultaneously.</p>
<ul>
  <li><strong>Short Float %:</strong> percentage of the float held short — above 15% is elevated, above 30% is extreme</li>
  <li><strong>Days to Cover (DTC):</strong> at current average volume, how many days for all shorts to buy back — above 5 days is high risk for short sellers</li>
  <li><strong>Squeeze Stage:</strong> Early / Building / Primed / Critical — based on price action vs short interest trend</li>
  <li><strong>Catalyst match:</strong> when a high-squeeze ticker also has a positive EDGAR filing, the score multiplies</li>
</ul>

<h2>Insider Cluster Detection: Form 4 Pattern Recognition</h2>
<p>A single insider buy can be routine — pre-planned 10b5-1 sale, compensation adjustment.
Three or more insiders from the same company buying within 48 hours is statistically
significant and historically correlates with positive unreported events.</p>
<p>Our pipeline clusters all Form 4 filings by ticker and date window, then flags any
ticker where 3+ unique insiders appear. These tickers get the highest insider signal score
regardless of their base Gap Score.</p>

<h2>Block Volume Signal: Institutional Positioning Indicator</h2>
<p>We calculate each ticker's volume ratio: today's volume divided by its 30-day average.
A 5x+ ratio alongside a catalyst filing suggests institutional positioning — someone large
is building or exiting a position before the news is fully priced in.</p>
<div class="callout">
  <p><strong>Transparency note:</strong> Our Block Volume Signal is derived from volume-ratio analysis
  against 30-day averages. It is not FINRA off-exchange dark pool print data
  (which requires a paid FINRA subscription). We label it "Block Volume Signal" rather than
  "dark pool data" to be accurate.</p>
</div>

<h2>Options Activity: Call/Put Flow on Catalyst Picks</h2>
<p>For our top 15 gap candidates each morning, we check public options market data
for unusual activity signals:</p>
<ul>
  <li><strong>Volume/Open Interest ratio &gt;3x:</strong> far more contracts trading than exist as open positions — indicates a sweep, not normal retail activity</li>
  <li><strong>Bullish flow:</strong> call volume significantly outpaces put volume — market participants are betting on upside</li>
  <li><strong>Bearish flow:</strong> put volume dominant — caution signal even on a positive catalyst</li>
  <li><strong>Estimated premium:</strong> total dollar value of call options traded — large premium ($500K+) indicates institutional-sized orders</li>
</ul>

<h2>Track Record: How We Measure Accuracy</h2>
<p>Every pick is logged the morning it's published. We then check the next trading
day's open, intraday high, and closing price. Outcomes are categorized:</p>
<ul>
  <li><strong>Win:</strong> ticker moved +2% or more from the scanner publication price</li>
  <li><strong>Hit +5%:</strong> reached +5% intraday high at any point next session</li>
  <li><strong>Miss:</strong> returned less than +2% or went negative</li>
</ul>
<p>These stats are updated automatically every morning and displayed on the
<a href="/#results">scanner's Track Record section</a>.
No cherry-picking — the full evaluated dataset is shown.</p>

<h2>Free vs Premium: What Each Tier Includes</h2>
<table class="tier-table">
  <thead><tr><th>Feature</th><th>Free</th><th>Premium — $9/mo</th></tr></thead>
  <tbody>
    <tr><td style="text-align:left">Daily top picks</td><td>Top 10</td><td class="tier-us">All picks</td></tr>
    <tr><td style="text-align:left">Squeeze radar</td><td>✓</td><td class="tier-us">✓ + full dataset</td></tr>
    <tr><td style="text-align:left">Insider clusters</td><td>✓</td><td class="tier-us">✓</td></tr>
    <tr><td style="text-align:left">Block volume signals</td><td>✓</td><td class="tier-us">✓</td></tr>
    <tr><td style="text-align:left">Raw scanner CSV</td><td>—</td><td class="tier-us">✓ Full 1,600+ ticker dataset</td></tr>
    <tr><td style="text-align:left">Delivery time</td><td>3:35 AM ET</td><td class="tier-us">3:30 AM ET</td></tr>
    <tr><td style="text-align:left">Public scanner page</td><td>✓</td><td class="tier-us">✓</td></tr>
  </tbody>
</table>
<p>The free tier is free forever. We monetize through Premium subscribers who want the
full dataset — not by paywalling the core signal.</p>
<div style="display:flex;gap:16px;justify-content:center;margin:24px 0 32px;flex-wrap:wrap">
  <a href="https://buy.stripe.com/your-link" target="_blank"
     style="background:var(--cyan);color:#000;padding:12px 32px;border-radius:8px;font-weight:700;
     font-size:1em;letter-spacing:.5px;text-decoration:none;transition:opacity .2s"
     onmouseover="this.style.opacity='0.85'" onmouseout="this.style.opacity='1'">
     Get Edge Reader — $9/mo</a>
  <a href="https://buy.stripe.com/your-link" target="_blank"
     style="background:var(--gold);color:#000;padding:12px 32px;border-radius:8px;font-weight:700;
     font-size:1em;letter-spacing:.5px;text-decoration:none;transition:opacity .2s"
     onmouseover="this.style.opacity='0.85'" onmouseout="this.style.opacity='1'">
     Get Edge Pro — $39/mo</a>
</div>

<h2>Frequently Asked Questions</h2>
<div class="faq-item">
  <div class="faq-q">Is this real SEC EDGAR data?</div>
  <div class="faq-a">Yes. We pull directly from SEC EDGAR's official RSS feeds — the same primary
  source used by institutional terminals. No third-party vendor, no delay beyond what EDGAR itself imposes.</div>
</div>
<div class="faq-item">
  <div class="faq-q">Why is this free? What's the catch?</div>
  <div class="faq-a">The free tier (top 10 picks) is funded by Premium subscribers ($9/month)
  who want the full dataset and raw CSV. We chose to make the core signal free because we believe
  retail traders deserve the same data access as institutions — and because free users who find
  value convert to Premium subscribers over time.</div>
</div>
<div class="faq-item">
  <div class="faq-q">What time does the scanner update?</div>
  <div class="faq-a">The full pre-market build publishes by 3:30 AM ET before the 4:00 AM pre-market open.
  The public Scanner then republishes hourly at 10:05 AM ET through 4:05 PM ET on market days,
  while live price widgets continue refreshing on the page between rebuilds.</div>
</div>
<div class="faq-item">
  <div class="faq-q">Does it work for penny stocks and small caps?</div>
  <div class="faq-a">Yes. SEC EDGAR covers all public companies regardless of size. In fact,
  small and micro-cap stocks with catalyst filings often produce the largest percentage moves
  because institutional coverage is thin. We score the full universe — over 1,600 tickers evaluated daily.</div>
</div>
<div class="faq-item">
  <div class="faq-q">Do I need an account or login?</div>
  <div class="faq-a">No account or login is required for the free scanner. The web page is always
  public. For the daily email newsletter, just enter your email on the scanner page — no password,
  no credit card.</div>
</div>
<div class="faq-item">
  <div class="faq-q">How is this different from Finviz or Trade-Ideas?</div>
  <div class="faq-a">Finviz filters on technicals and fundamentals. Trade-Ideas streams real-time
  price action. Neither processes SEC EDGAR filings, scores insider clusters, or identifies
  squeeze setups combined with a catalyst filing. We fill a specific gap: the period between
  an overnight EDGAR filing and the 4 AM pre-market open — before most screeners have the data.</div>
</div>
<div class="faq-item">
  <div class="faq-q">Is this financial advice?</div>
  <div class="faq-a">No. Catalyst Edge is a data tool that surfaces public SEC filings and
  applies a scoring model. Nothing on this site or in the newsletter constitutes investment advice.
  Always do your own research and manage your risk before trading any security.</div>
</div>

<div class="callout" style="margin-top:40px;text-align:center">
  <p><strong>Ready to see today's picks?</strong><br>
  <a href="/" style="color:var(--green)">← View the live scanner</a> &nbsp;·&nbsp;
  <a href="#subscribe" style="color:var(--green)">Get the free daily email →</a></p>
</div>

</div><!-- /wrap -->

<footer>
  <div>Catalyst Edge — Free Daily SEC EDGAR Gap Scanner</div>
  <div style="margin:8px 0">
    <a href="/">Scanner</a>
    <a href="https://catalystedge.agency" target="_blank" rel="noopener noreferrer">Newsletter</a>
    <a href="https://t.me/CatalystEdgePro" target="_blank" rel="noopener noreferrer">Telegram</a>
    <a href="https://discord.gg/8aJEHghHVy" target="_blank" rel="noopener noreferrer">Discord</a>
    <a href="https://twitter.com/CatalystEdgePro" target="_blank" rel="noopener noreferrer">X / Twitter</a>
  </div>
  <div style="font-size:.75em;margin-top:8px;opacity:.6">
    Data from SEC EDGAR public feeds. Not financial advice. For informational purposes only.
  </div>
</footer>

<script src="/lib/cinematic.js"></script>
</body>
</html>"""


def build_api_page(gid: str = "") -> str:
    ga = ga4_tag(gid)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Catalyst Edge API — SEC EDGAR Catalyst Data Feed for Quants &amp; Prop Desks</title>
<meta name="description" content="Machine-readable SEC EDGAR catalyst data feed. 300+ filings scored daily by 3:30 AM ET. JSON/CSV output. Gap score, squeeze signal, insider cluster, dark pool. For quants, prop desks, and algorithmic traders.">
<meta property="og:title" content="Catalyst Edge API — SEC Catalyst Data Feed">
<meta property="og:description" content="Structured SEC filing intelligence delivered before market open. Integrate into your Python model, algo, or terminal.">
{ga}
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.6}}
a{{color:#58a6ff;text-decoration:none}}a:hover{{text-decoration:underline}}
.wrap{{max-width:860px;margin:0 auto;padding:60px 24px}}
h1{{font-size:2.2em;font-weight:800;margin-bottom:12px;line-height:1.2}}
h2{{font-size:1.35em;font-weight:700;margin:40px 0 12px;color:#e6edf3}}
h3{{font-size:1.05em;font-weight:600;margin:24px 0 8px;color:#3fb950}}
p{{color:#8b949e;margin-bottom:14px;font-size:.97em}}
.hero-tag{{display:inline-block;background:#1a2e1a;color:#3fb950;border:1px solid #3fb95044;
  border-radius:20px;padding:4px 14px;font-size:.8em;font-weight:600;margin-bottom:20px}}
.stat-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin:32px 0}}
.stat-card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:20px;text-align:center}}
.stat-n{{font-size:2em;font-weight:800;color:#3fb950}}
.stat-l{{font-size:.8em;color:#8b949e;margin-top:4px}}
.endpoint{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:20px;margin:16px 0}}
.endpoint code{{font-family:'SFMono-Regular',Consolas,monospace;font-size:.88em}}
pre{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:20px;
  overflow-x:auto;font-size:.84em;line-height:1.6;margin:16px 0}}
pre code{{color:#3fb950}}
.field-table{{width:100%;border-collapse:collapse;font-size:.87em;margin:16px 0}}
.field-table th{{background:#161b22;color:#8b949e;padding:10px 14px;text-align:left;
  border-bottom:1px solid #21262d;font-weight:600;text-transform:uppercase;font-size:.78em}}
.field-table td{{padding:10px 14px;border-bottom:1px solid #161b22;vertical-align:top}}
.field-table td:first-child{{color:#58a6ff;font-family:monospace;white-space:nowrap}}
.field-table td:nth-child(2){{color:#3fb950;white-space:nowrap}}
.pill{{display:inline-block;background:#1a2e1a;color:#3fb950;border:1px solid #3fb95044;
  border-radius:4px;padding:1px 8px;font-size:.78em;font-weight:600;margin:2px}}
.pill.warn{{background:#2d1800;color:#f0883e;border-color:#f0883e44}}
.cta-box{{background:#161b22;border:2px solid #3fb950;border-radius:12px;padding:32px;
  text-align:center;margin:48px 0}}
.cta-box h2{{margin:0 0 12px;color:#3fb950;font-size:1.5em}}
.cta-box p{{margin-bottom:20px}}
.btn-green{{background:#3fb950;color:#0d1117;padding:12px 28px;border-radius:8px;
  font-weight:700;font-size:1em;display:inline-block}}
.btn-green:hover{{background:#3fb950cc;text-decoration:none}}
.tier-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px;margin:24px 0}}
.tier-card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:24px}}
.tier-card.featured{{border-color:#3fb950;background:#0f1f0f}}
.tier-price{{font-size:2em;font-weight:800;color:#3fb950;margin:8px 0}}
.tier-period{{font-size:.78em;color:#8b949e}}
.tier-features{{list-style:none;margin-top:16px}}
.tier-features li{{padding:6px 0;font-size:.9em;color:#8b949e;border-bottom:1px solid #21262d22}}
.tier-features li::before{{content:"✓ ";color:#3fb950;font-weight:700}}
nav{{background:#161b22;border-bottom:1px solid #21262d;padding:14px 24px;display:flex;align-items:center;gap:16px}}
nav a{{font-size:.88em;color:#8b949e}}nav a:hover{{color:#e6edf3}}
.nav-brand{{font-weight:700;color:#e6edf3;font-size:.95em;margin-right:auto}}
</style>
</head>
<body>
<nav>
  <span class="nav-brand">⚡ Catalyst Edge</span>
  <a href="/">Scanner</a>
  <a href="/methodology/">Methodology</a>
  <a href="/api/">API</a>
  <a href="https://catalystedge.agency" target="_blank" rel="noopener noreferrer">Newsletter</a>
</nav>

<div class="wrap">
  <div class="hero-tag">Alternative Data · API Access</div>
  <h1>SEC Catalyst Data Feed<br><span style="color:#3fb950">for Quants &amp; Prop Desks</span></h1>
  <p style="font-size:1.05em;color:#c9d1d9;max-width:600px">
    {_LIVE_FILINGS or '300+' } EDGAR filings parsed, scored, and structured every night by 3:30 AM ET.
    Plug our gap scores, squeeze signals, and insider clusters directly into your
    Python models, algo strategies, or Bloomberg workflows — no scraping required.
  </p>

  <div class="stat-row">
    <div class="stat-card"><div class="stat-n">{_LIVE_FILINGS or '300+' }</div><div class="stat-l">Filings parsed daily</div></div>
    <div class="stat-card"><div class="stat-n">{_LIVE_TICKERS or '250+' }+</div><div class="stat-l">Tickers scored</div></div>
    <div class="stat-card"><div class="stat-n">3:30 AM</div><div class="stat-l">ET delivery</div></div>
    <div class="stat-card"><div class="stat-n">{_LIVE_HIT2:.0f}%</div><div class="stat-l">Hit +2% intraday (90-day)</div></div>
  </div>

  <h2>Data Fields</h2>
  <p>Each row in the daily feed includes the following structured fields:</p>
  <table class="field-table">
    <thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead>
    <tbody>
      <tr><td>ticker</td><td>string</td><td>Exchange symbol (filtered: no warrants, no derivatives)</td></tr>
      <tr><td>gap_score</td><td>float 0–20</td><td>Proprietary catalyst scoring. &gt;14 = high conviction gapper setup</td></tr>
      <tr><td>form_type</td><td>string</td><td>SEC form filed: 8-K, Form 4, S-3, 13D/G, 6-K, NT, etc.</td></tr>
      <tr><td>filing_url</td><td>url</td><td>Direct link to SEC EDGAR filing index page</td></tr>
      <tr><td>filing_time_et</td><td>datetime</td><td>Time filing hit EDGAR (ET). 6 AM filings historically outperform.</td></tr>
      <tr><td>sentiment</td><td>float −1..1</td><td>NLP sentiment extracted from filing full text</td></tr>
      <tr><td>squeeze_score</td><td>float 0–100</td><td>Short interest + days-to-cover squeeze pressure index</td></tr>
      <tr><td>short_float_pct</td><td>float</td><td>Percentage of float held short</td></tr>
      <tr><td>insider_cluster</td><td>int</td><td>Number of insider buy transactions clustered within 10 days</td></tr>
      <tr><td>dark_pool_vol</td><td>int</td><td>Block volume ratio signal from dark pool feed</td></tr>
      <tr><td>avg_volume</td><td>int</td><td>30-day average daily volume</td></tr>
      <tr><td>market_cap</td><td>int</td><td>Market cap in USD (used for moat/value filtering)</td></tr>
      <tr><td>price</td><td>float</td><td>Last known price at pipeline run time</td></tr>
      <tr><td>category</td><td>string</td><td>gapper / value / moat_core / moat_emerging</td></tr>
    </tbody>
  </table>

  <h2>Sample Output (JSON)</h2>
<pre><code>{{
  "generated_at": "2026-03-30T03:28:14-04:00",
  "tickers": [
    {{
      "ticker": "PMNT",
      "gap_score": 16.5,
      "form_type": "8-K",
      "filing_url": "https://www.sec.gov/Archives/edgar/data/.../index.htm",
      "filing_time_et": "2026-03-29T18:41:00",
      "sentiment": 0.74,
      "squeeze_score": 31.2,
      "short_float_pct": 18.4,
      "insider_cluster": 3,
      "dark_pool_vol": 2400000,
      "avg_volume": 890000,
      "market_cap": 420000000,
      "price": 3.87,
      "category": "gapper"
    }}
  ]
}}</code></pre>

  <h2>Delivery Methods</h2>
  <div class="endpoint">
    <h3>📁 Daily CSV Drop</h3>
    <p>Structured CSV delivered to your S3 bucket, SFTP endpoint, or shared drive by 3:30 AM ET.
    Compatible with pandas, Excel, or any data pipeline. 15 fields per row, 200–400 scored tickers/day.</p>
    <code>pd.read_csv("catalyst_edge_YYYY-MM-DD.csv")</code>
  </div>
  <div class="endpoint">
    <h3>🔌 REST API <span style="background:#2d1800;color:#f0883e;border:1px solid #f0883e44;
      border-radius:4px;padding:1px 8px;font-size:.75em;font-weight:600;vertical-align:middle">Beta Q3 2026</span></h3>
    <p>JSON endpoint for on-demand or scheduled pulls. Rate-limited per license tier.
    Authentication via API key header. Webhook delivery also available.
    <strong style="color:#f0883e">Early access seats available — join the waitlist below.</strong></p>
    <code>GET https://api.catalystedgescanner.com/v1/daily?date=2026-03-30&amp;category=gapper</code>
  </div>
  <div class="endpoint">
    <h3>🐍 Python SDK <span style="background:#2d1800;color:#f0883e;border:1px solid #f0883e44;
      border-radius:4px;padding:1px 8px;font-size:.75em;font-weight:600;vertical-align:middle">Beta Q3 2026</span></h3>
    <p>Drop-in pandas integration. One line to pull the morning feed into your backtest framework.
    <strong style="color:#f0883e">Available to Pro tier early-access members.</strong></p>
    <code>import catalyst_edge; df = catalyst_edge.today(category="gapper", min_score=14)</code>
  </div>

  <h2>Pricing</h2>
  <div class="tier-grid">
    <div class="tier-card">
      <div style="font-weight:700">Retail Premium</div>
      <div class="tier-price">$49<span class="tier-period">/mo</span></div>
      <ul class="tier-features">
        <li>Full 1,600+ ticker CSV daily</li>
        <li>All 14 data fields</li>
        <li>Historical archive (90 days)</li>
        <li>Email delivery by 3:30 AM ET</li>
        <li>Priority support</li>
      </ul>
    </div>
    <div class="tier-card featured">
      <div style="font-weight:700;color:#3fb950">Pro / Prop Desk
        <span style="background:#1a2e1a;color:#3fb950;border:1px solid #3fb95044;
          border-radius:4px;padding:1px 7px;font-size:.72em;margin-left:6px">Early Access</span>
      </div>
      <div class="tier-price">$99<span class="tier-period">/mo</span></div>
      <ul class="tier-features">
        <li>Everything in Retail Premium</li>
        <li>S3 / SFTP bucket delivery (live now)</li>
        <li>API + Python SDK beta access (Q3 2026)</li>
        <li>Full scoring source code (licensed)</li>
        <li>Dedicated Slack channel</li>
        <li>Custom field requests</li>
      </ul>
    </div>
    <div class="tier-card">
      <div style="font-weight:700">Enterprise / Fund</div>
      <div class="tier-price" style="font-size:1.4em">Custom</div>
      <ul class="tier-features">
        <li>White-label the engine</li>
        <li>Co-branding options</li>
        <li>Revenue-share model available</li>
        <li>Bloomberg / Symphony integration</li>
        <li>SLA &amp; uptime guarantee</li>
        <li>On-site data room access</li>
      </ul>
    </div>
  </div>

  <div class="cta-box">
    <h2>Request Sample Data</h2>
    <p>We send a sample CSV from last week's feed — no commitment required.<br>
    We'll also include the 90-day backtest spreadsheet on request.</p>
    <a href="mailto:api@catalystedgescanner.com?subject=API%20Sample%20Data%20Request&body=Hi%2C%20I%27d%20like%20to%20see%20a%20sample%20CSV%20from%20the%20Catalyst%20Edge%20data%20feed." class="btn-green">Request Sample →</a>
    <div style="margin-top:12px;font-size:.8em;color:#8b949e">
      Replies from <strong style="color:#e6edf3">api@catalystedgescanner.com</strong> within one business day.
    </div>
  </div>

  <h2>Already Used By</h2>
  <p style="color:#8b949e">Currently powering the <strong style="color:#e6edf3">Catalyst Edge newsletter</strong>,
  delivered daily to active retail traders. Pipeline has evaluated
  <strong style="color:#e6edf3">{_LIVE_PICKS or '600+' } picks</strong> over 90 days with a
  <strong style="color:#e6edf3">{_LIVE_HIT2:.0f}% hit rate at +2% intraday</strong>.</p>
  <p>Institutional licensing inquiries:
  <a href="mailto:api@catalystedgescanner.com?subject=Institutional%20Licensing%20Inquiry">api@catalystedgescanner.com</a></p>

</div>
</body>
</html>"""


def main():
    gappers  = load_csv(ROOT / "sec_top_gappers.csv", 10, require_fresh=True)
    ranked   = load_csv(ROOT / "sec_catalyst_ranked.csv", 12, require_fresh=True)
    squeezes = load_csv(ROOT / "squeeze_candidates.csv", 8, require_fresh=True)
    insiders = load_csv(ROOT / "insider_clusters.csv", 8, require_fresh=True)
    darkpool = load_csv(ROOT / "dark_pool.csv", 8, require_fresh=True)
    sectors  = load_csv(ROOT / "news_sector_momentum.csv", 6, require_fresh=True)
    scanner_counts = {
        "gappers": len(gappers),
        "ranked": len(ranked),
        "squeezes": len(squeezes),
        "insiders": len(insiders),
        "darkpool": len(darkpool),
        "sectors": len(sectors),
    }
    if sum(scanner_counts.values()) == 0:
        status = build_scanner_artifact_status(
            scanner_counts,
            valid=False,
            reason="all_primary_sections_empty",
        )
        write_scanner_artifact_status(status)
        raise SystemExit(
            "generate_seo_site: refusing to overwrite docs/index.html because all primary scanner sections are empty"
        )
    # Heatmap: today's data only — stale data makes every sector pulse and skews bullish
    all_gappers = (load_csv(ROOT / "sec_clean_gappers.csv", 500, require_fresh=True)
                   + load_csv(ROOT / "sec_catalyst_ranked.csv", 500, require_fresh=True))
    heatmap_data = build_heatmap_data(all_gappers)
    heatmap_json = json.dumps(heatmap_data)
    # Aggregate market posture for body background tint.
    # Uses only sectors with scored filings (bullish + bearish > 0) so neutral-only
    # days stay neutral instead of leaning whichever direction had one stray tag.
    _bull_total = sum(int(d.get("bullish", 0) or 0) for d in heatmap_data)
    _bear_total = sum(int(d.get("bearish", 0) or 0) for d in heatmap_data)
    if _bull_total + _bear_total < 3:
        market_posture = "neutral"
    elif _bull_total >= _bear_total * 1.2:
        market_posture = "bullish"
    elif _bear_total >= _bull_total * 1.2:
        market_posture = "bearish"
    else:
        market_posture = "neutral"
    options_flow_path = ROOT / "options_flow.csv"
    fresh_options_activity = has_fresh_options_activity()
    if not options_flow_path.exists():
        options_feed_status = "missing"
        _raw_opts = []
    elif not is_fresh(options_flow_path):
        options_feed_status = "stale"
        _raw_opts = []
    else:
        _raw_opts = load_csv(options_flow_path, 15, require_fresh=True)
        if _raw_opts:
            options_feed_status = "ok"
        else:
            options_feed_status = "empty" if fresh_options_activity else "stale"
    def _map_option(r):
        pc = float(r.get("pc_ratio") or 1)
        call_oi = int(float(r.get("call_oi") or 0))
        put_oi = int(float(r.get("put_oi") or 0))
        # Min-volume gate: below 50 contracts combined is statistical noise
        # (audited 2026-04-16: FSBC with 3 contracts was emitting "bullish").
        total_oi = call_oi + put_oi
        if total_oi < 50:
            sig = "neutral"
        else:
            sig = "bullish" if pc < 0.7 else ("bearish" if pc > 1.3 else "neutral")
        uc  = int(float(r.get("unusual_call_vol") or 0))
        return {
            "ticker":       r.get("ticker", ""),
            "signal":       sig,
            "call_vol":     call_oi,
            "put_vol":      put_oi,
            "top_strike":   r.get("max_pain", ""),
            "expiry":       "",
            "premium_est":  0,
            "unusual_calls": uc,
        }
    options = [_map_option(r) for r in _raw_opts if r.get("ticker")]

    stooq_cache   = load_stooq_cache()

    # Load Nobel signals
    _nobel_raw = {}
    try:
        _nf = ROOT / "nobel_signals.json"
        if _nf.exists():
            _nd = json.loads(_nf.read_text())
            _nobel_raw = _nd.get("tickers", {})
            _nobel_macro = _nd.get("macro", {})
        else:
            _nobel_macro = {}
    except: _nobel_macro = {}

    # Build insider cluster lookup: ticker -> row
    _insider_map = {r["ticker"]: r for r in insiders if r.get("ticker")}

    outcome_stats = load_outcome_stats()
    # Build dynamic proof strings for premium gates / API page from live outcome data
    global _GATE_PROOF, _LIVE_HIT2, _LIVE_PICKS
    _g = outcome_stats.get("sec_clean_gappers", {})
    try:
        _LIVE_HIT2  = float(_g.get("hit_rate_2pct", 0))
        _LIVE_PICKS = int(_g.get("rows", 0))
        if _LIVE_HIT2 > 0 and _LIVE_PICKS > 0:
            _GATE_PROOF = f"{_LIVE_HIT2:.1f}% hit rate · {_LIVE_PICKS} evaluated picks · Cancel anytime"
    except Exception:
        pass
    # Hero proof strip — audited hit/loss numbers shown above the tactical strip.
    # Pulled from sec_outcome_summary.csv so every claim on /scanner/ has a source.
    try:
        _hit5 = float(_g.get("hit_rate_5pct", 0))
    except Exception:
        _hit5 = 0.0
    try:
        _wins = int(_g.get("wins", 0))
        _losses = int(_g.get("losses", 0))
    except Exception:
        _wins = _losses = 0
    _loss_rate = (100.0 * _losses / (_wins + _losses)) if (_wins + _losses) else 0.0
    # Fix #2 — Alpha vs SPY (excess return after baseline subtraction).
    try:
        _avg_alpha = float(_g.get("avg_alpha_close_pct", 0) or 0)
    except Exception:
        _avg_alpha = 0.0
    # Fix #6 — prefer holdout (out-of-sample) hit rate if available.
    try:
        _holdout_hit = float(_g.get("holdout_hit_rate_2pct", 0) or 0)
    except Exception:
        _holdout_hit = 0.0
    try:
        _holdout_alpha = float(_g.get("holdout_avg_alpha_pct", 0) or 0)
    except Exception:
        _holdout_alpha = 0.0
    _decay_flag = (_g.get("decay_flag", "0") == "1")
    # Fix #9 — cohort decay (last 30 days vs 90 days).
    try:
        _c30 = float(_g.get("cohort_30d_hit_rate_2pct", 0) or 0)
        _c90 = float(_g.get("cohort_90d_hit_rate_2pct", 0) or 0)
    except Exception:
        _c30 = _c90 = 0.0
    ga4_id        = load_ga4_id()
    ga4_script    = ga4_tag(ga4_id)

    # Build options lookup map for sparkline row inline badge
    opts_map = {r["ticker"]: r for r in options if r.get("ticker")}

    # Congressional-trade enrichment: backfill scanner rows when a House/Senate
    # member has traded the same ticker in the last 45 days.
    congress_map = load_congress_map(max_age_days=45)

    # Combo-conviction: ticker appears in 2+ scanner lanes today.
    combo_map = build_combo_set(gappers, ranked, squeezes, insiders, darkpool)

    # Rotating tactical strip data — live headline numbers per scanner lane.
    mergers_live = _load_mergers_live()
    darkpool_live = _load_darkpool_live()
    deepvalue_live = _load_deepvalue_live()
    convergence_live = _load_convergence_live()
    smart_money_live = _load_smart_money_live()
    sympathy_live = _load_sympathy_live()
    lockups_live = _load_lockups_live()
    tactical_strip = tactical_strip_html(
        gappers=gappers, squeezes=squeezes, insiders=insiders,
        darkpool=darkpool, congress_map=congress_map, mergers_live=mergers_live,
        darkpool_live=darkpool_live, deepvalue_live=deepvalue_live,
        convergence_live=convergence_live, smart_money_live=smart_money_live,
        sympathy_live=sympathy_live, lockups_live=lockups_live,
    )

    active_sector_lanes = len(
        {
            sec
            for row in (gappers + ranked + squeezes + insiders + darkpool)
            for sec in _sector_lookup.get(row.get("ticker", "").upper(), [])
            if sec
        }
    )

    global _LIVE_FILINGS, _LIVE_TICKERS
    try:
        total_t = len([l for l in (ROOT / "sec_catalyst_tickers.txt").read_text().splitlines() if l.strip()])
    except: total_t = 250
    _LIVE_TICKERS = total_t

    # Actual filing count from today's pipeline run
    try:
        with open(ROOT / "sec_catalyst_latest.csv", encoding="utf-8") as _f:
            _n_filings = sum(1 for _ in _f) - 1  # subtract header
        _n_filings = max(_n_filings, 0)
        _LIVE_FILINGS = _n_filings
    except: _n_filings = 0
    spotlight_html   = top_pick(gappers, squeezes, insiders)
    trackrecord_sect = trackrecord_html(outcome_stats)
    options_sect     = options_html(options, options_feed_status)
    squeeze_sect     = f"""
  <!-- SQUEEZE RADAR -->
  <div class="section" id="squeeze">
    <div class="section-head">
      <h2>🔥 Squeeze Radar</h2>
      <span class="section-tag">Short Interest · Days to Cover</span>
    </div>
    <p class="section-sub">High short float + rising squeeze pressure. Score above 20 = elevated risk for shorts.
    Combine with a catalyst filing for maximum conviction.</p>
    {intel_table_shell(
        "intel-shell-squeeze",
        "Short pressure chamber",
        "Borrow stress and cover velocity staged as a living pressure map.",
        "When short float, days-to-cover, and catalyst energy line up, this module turns from watchlist into ignition surface.",
        "SQZ//RADAR",
        [
            intel_stat_chip("armed", str(len(squeezes))),
            intel_stat_chip("mode", "LIVE"),
        ],
        f'''
    <div class="tbl-wrap">
      <table class="sortable intel-table">
        <thead><tr>
          <th data-sort="str">Ticker</th>
          <th data-sort="num">Conviction</th>
          <th data-sort="str">Stage</th>
          <th data-sort="num">Short Float</th>
          <th data-sort="num">Days to Cover</th>
          <th data-sort="num" title="Squeeze pressure = Short Float % × Days to Cover">Pressure</th>
        </tr></thead>
        <tbody>{squeeze_rows(squeezes, stooq_cache, opts_map, combo_map, congress_map)}</tbody>
      </table>
    </div>''',
        "High short float with a real filing catalyst is the cleanest squeeze ignition pattern.",
    )}
    <div class="sector-empty-msg"></div>
  </div>"""
    insider_sect     = f"""
  <!-- INSIDER CLUSTERS -->
  <div class="section" id="insider">
    <div class="section-head">
      <h2>🏛️ Insider Filing Clusters</h2>
      <span class="section-tag">Form 4 · Multiple Insiders</span>
    </div>
    <p class="section-sub">Tickers where multiple insiders filed Form 4s within 48 hours.
    3+ filings from different insiders is the strongest signal on EDGAR.</p>
    {intel_table_shell(
        "intel-shell-insider",
        "Executive conviction relay",
        "Form 4 clusters rendered as conviction receipts instead of background paperwork.",
        "Multiple filings on the same ticker create a cleaner institutional story than a single isolated insider move.",
        "FORM//4",
        [
            intel_stat_chip("clusters", str(len(insiders))),
            intel_stat_chip("window", "48H"),
        ],
        f'''
    <div class="tbl-wrap">
      <table class="sortable intel-table">
        <thead><tr>
          <th data-sort="str">Ticker</th>
          <th data-sort="num">Cluster · Buys</th>
          <th data-sort="str">Tags</th>
          <th data-sort="str">Latest Filing</th>
        </tr></thead>
        <tbody>{insider_rows(insiders, stooq_cache, opts_map, combo_map, congress_map)}</tbody>
      </table>
    </div>''',
        "Three or more insider filings from different people is treated as the strongest cluster signal.",
    )}
    <div class="sector-empty-msg"></div>
  </div>"""
    darkpool_sect    = f"""
  <!-- BLOCK VOLUME SIGNAL -->
  <div class="section" id="darkpool">
    <div class="section-head">
      <h2>🌊 Block Volume Signal</h2>
      <span class="section-tag">Volume Ratio vs 30-Day Avg</span>
    </div>
    <p class="section-sub">Tickers showing unusual volume spikes vs their 30-day average,
    combined with a catalyst filing. 5x+ ratio = potential institutional positioning.
    <em>Note: this is volume-ratio analysis, not FINRA off-exchange print data.</em></p>
    {intel_table_shell(
        "intel-shell-darkpool",
        "Institutional pressure trace",
        "Block-volume surges isolated as positioning shock instead of raw tape noise.",
        "This module tracks abnormal participation intensity so the operator can see when bigger hands are leaning in.",
        "BLOCK//VOL",
        [
            intel_stat_chip("signals", str(len(darkpool))),
            intel_stat_chip("scope", "30D"),
        ],
        f'''
    <div class="tbl-wrap">
      <table class="sortable intel-table">
        <thead><tr>
          <th data-sort="str">Ticker</th>
          <th data-sort="str">Signal</th>
          <th data-sort="num">Vol Ratio</th>
          <th data-sort="num">Price Chg</th>
        </tr></thead>
        <tbody>{darkpool_rows(darkpool, stooq_cache, opts_map, combo_map, congress_map)}</tbody>
      </table>
    </div>''',
        "This lane measures unusual volume versus a 30-day baseline. It is not a FINRA dark-pool print feed.",
    )}
    <div class="sector-empty-msg"></div>
  </div>"""
    pm_signals       = load_polymarket()
    pm_sect          = polymarket_html(pm_signals)
    macro_tw         = _polymarket_tailwinds(pm_signals)
    best_outcome     = load_best_outcome()
    best_ticker      = best_outcome.get("ticker", "")
    best_move        = best_outcome.get("move_pct", "")
    best_date        = best_outcome.get("date", "")
    pro_tails_rows   = load_pro_tails(8)
    pro_tails_block  = pro_tails_html(pro_tails_rows)
    try:    best_move_str = f"+{float(best_move):.1f}%"
    except: best_move_str = ""
    try:
        from datetime import date as _date
        _d = _date.fromisoformat(best_date)
        best_date_str = _d.strftime("%b %-d")
    except Exception:
        best_date_str = ""

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Free SEC Catalyst Stock Scanner — Pre-Market Gap Plays | Catalyst Edge</title>
<meta name="description" content="Free SEC EDGAR catalyst scanner. Pre-market build at 3:30 AM ET plus hourly public Scanner refreshes during market hours. Gap plays, squeeze radar, insider clusters, and options activity.">
<meta name="keywords" content="free SEC catalyst scanner,SEC EDGAR stock scanner,pre market gap plays SEC filings,8-K gap plays,form 4 insider buying scanner,short squeeze scanner free,EDGAR filings today,SEC catalyst stocks,free stock scanner no login,pre market movers SEC">
<meta name="author" content="Catalyst Edge">
<meta name="robots" content="index, follow">
<meta property="og:title" content="Free SEC Catalyst Stock Scanner — Pre-Market Gap Plays | Catalyst Edge">
<meta property="og:description" content="Pre-market build at 3:30 AM ET plus hourly public Scanner refreshes during market hours. Gap plays, squeeze radar, insider clusters, and options activity.">
<meta property="og:url" content="{SITE}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Catalyst Edge">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@CatalystEdgePro">
<meta name="twitter:title" content="Free SEC Catalyst Stock Scanner — Pre-Market Gap Plays">
<meta name="twitter:description" content="Pre-market build at 3:30 AM ET plus hourly public Scanner refreshes during market hours. Gap plays, squeeze radar, insider clusters, and options activity.">
<link rel="canonical" href="{SITE}">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icons/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="CE Scanner">
<meta name="theme-color" content="#2ea043">
<script type="application/ld+json">{{
"@context":"https://schema.org","@type":"WebApplication",
"name":"Catalyst Edge SEC Gap Scanner",
"description":"Free SEC EDGAR catalyst scanner — pre-market build at 3:30 AM ET plus hourly market-day refreshes with live prices and verified catalyst context.",
"url":"{SITE}","applicationCategory":"FinanceApplication",
"operatingSystem":"Web","browserRequirements":"Requires JavaScript",
"offers":{{"@type":"Offer","price":"0","priceCurrency":"USD","description":"Free tier — top 10 picks daily"}},
"dateModified":"{ISODATE}",
"publisher":{{"@type":"Organization","name":"Catalyst Edge","url":"https://catalystedge.agency"}}
}}</script>
<script type="application/ld+json">{{
"@context":"https://schema.org","@type":"ItemList","name":"Catalyst Edge Tools",
"itemListElement":[
  {{"@type":"SiteNavigationElement","position":1,"name":"Scanner","url":"{SITE}/"}},
  {{"@type":"SiteNavigationElement","position":2,"name":"Sector Heatmap","url":"{SITE}/heatmap/"}},
  {{"@type":"SiteNavigationElement","position":3,"name":"Watchlist","url":"{SITE}/watchlist/"}},
  {{"@type":"SiteNavigationElement","position":4,"name":"Options Flow","url":"{SITE}/options-flow/"}},
  {{"@type":"SiteNavigationElement","position":5,"name":"Congress Tracker","url":"{SITE}/congress/"}},
  {{"@type":"SiteNavigationElement","position":6,"name":"Glossary","url":"{SITE}/glossary/"}},
  {{"@type":"SiteNavigationElement","position":7,"name":"Filing Alerts","url":"{SITE}/alerts/"}},
  {{"@type":"SiteNavigationElement","position":8,"name":"Cheat Sheet","url":"{SITE}/cheat-sheet/"}}
]
}}</script>
<style>
:root{{
  --bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--border:#30363d;
  --text:#e6edf3;--muted:#8b949e;--green:#3fb950;--yellow:#d29922;
  --orange:#f0883e;--red:#f78166;--blue:#58a6ff;--purple:#bc8cff;
  --scanner-scroll-skew:0deg;--scanner-scroll-drift:0px;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.6;font-size:15px;overflow-x:hidden}}
a{{color:var(--blue);text-decoration:none}}
a:hover{{text-decoration:underline}}

/* SCANNER POSTURE FIELD */
@keyframes moveHorizontal{{0%{{transform:translateX(-50%) translateY(-10%)}}50%{{transform:translateX(50%) translateY(10%)}}100%{{transform:translateX(-50%) translateY(-10%)}}}}
@keyframes moveInCircle{{0%{{transform:rotate(0deg)}}50%{{transform:rotate(180deg)}}100%{{transform:rotate(360deg)}}}}
@keyframes moveVertical{{0%{{transform:translateY(-50%)}}50%{{transform:translateY(50%)}}100%{{transform:translateY(-50%)}}}}
.scanner-posture-shell{{position:relative;isolation:isolate}}
.scanner-posture-shell > *{{position:relative;z-index:1}}
.scanner-posture-bg{{position:fixed;top:52px;left:0;right:0;bottom:0;overflow:hidden;pointer-events:none;z-index:-50;
  background:linear-gradient(180deg,rgb(5,5,10) 0%,rgb(10,15,25) 100%)}}
.scanner-posture-orb{{position:absolute;width:100vw;height:100vw;border-radius:50%;opacity:.42;mix-blend-mode:screen;filter:blur(120px)}}
.scanner-posture-orb.first{{left:-28vw;top:-36vh;background:radial-gradient(circle,rgba(16,185,129,.54) 0%,rgba(16,185,129,.14) 32%,rgba(16,185,129,0) 70%);animation:moveVertical 30s ease infinite}}
.scanner-posture-orb.second{{right:-26vw;top:-12vh;background:radial-gradient(circle,rgba(244,63,94,.48) 0%,rgba(244,63,94,.12) 30%,rgba(244,63,94,0) 68%);animation:moveInCircle 20s reverse infinite;transform-origin:center center}}
.scanner-posture-orb.third{{left:14vw;bottom:-46vh;background:radial-gradient(circle,rgba(14,165,233,.42) 0%,rgba(14,165,233,.12) 30%,rgba(14,165,233,0) 68%);animation:moveInCircle 40s linear infinite;transform-origin:center center}}
.scanner-posture-orb.fourth{{right:-8vw;bottom:-42vh;background:radial-gradient(circle,rgba(20,20,20,.9) 0%,rgba(20,20,20,.28) 30%,rgba(20,20,20,0) 68%);animation:moveHorizontal 40s ease infinite}}
.scanner-posture-orb.fifth{{left:34vw;top:10vh;background:radial-gradient(circle,rgba(139,92,246,.34) 0%,rgba(139,92,246,.10) 28%,rgba(139,92,246,0) 68%);animation:moveInCircle 20s ease infinite;transform-origin:center center}}
.scanner-posture-pointer{{position:absolute;left:var(--pointer-x,50%);top:var(--pointer-y,34%);width:32vw;height:32vw;border-radius:50%;
  transform:translate(-50%,-50%);background:radial-gradient(circle,rgba(255,255,255,.14) 0%,rgba(255,255,255,.08) 24%,rgba(255,255,255,0) 68%);
  mix-blend-mode:screen;filter:blur(88px);opacity:.34;transition:left .18s ease-out,top .18s ease-out}}
.scanner-posture-vignette{{position:absolute;inset:0;background:
  radial-gradient(circle at 50% 24%,rgba(255,255,255,.06),transparent 26%),
  linear-gradient(180deg,rgba(4,6,10,.12) 0%,rgba(4,6,10,.02) 22%,rgba(4,6,10,.18) 100%)}}
.spotlight-stage{{max-width:1180px;margin:0 auto;padding:28px 18px 12px}}

/* SCROLL REIFICATION */
.spotlight,.countdown-bar,.scanner-card,.intel-shell,#heatmap-wrap,.sector-card,.track-card,.pm-card{{transition:
  opacity .34s ease,filter .34s ease,transform .34s ease,box-shadow .34s ease}}
.reify-muted{{opacity:.48;filter:saturate(.72) brightness(.76) contrast(1.03)}}
.reify-focus{{opacity:1;filter:saturate(1.1) brightness(1.04);
  transform:perspective(1600px) rotateX(calc(var(--focus-tilt,0deg) * -0.25)) translateY(-2px)}}
.solid-armor-card,.liquid-glass-card{{position:relative;overflow:hidden;background:#0a0a0a;
  border:1px solid rgba(255,255,255,.10);box-shadow:0 28px 72px rgba(0,0,0,.42),inset 0 1px 0 rgba(255,255,255,.05)}}
.solid-armor-card::before,.liquid-glass-card::before{{content:'';position:absolute;inset:0;pointer-events:none;
  background:
    linear-gradient(180deg,rgba(255,255,255,.05) 0%,rgba(255,255,255,0) 22%),
    radial-gradient(circle at 14% 12%,rgba(114,229,255,.08),transparent 24%),
    radial-gradient(circle at 86% 18%,rgba(215,180,106,.08),transparent 22%);
  opacity:.42}}
.solid-armor-card::after,.liquid-glass-card::after{{content:'';position:absolute;inset:1px;border-radius:inherit;pointer-events:none;
  border:1px solid rgba(255,255,255,.04);opacity:.85}}
.solid-armor-card > *,.liquid-glass-card > *{{position:relative;z-index:1}}
.heavy-armor-card{{position:relative;z-index:10;background:#0a0a0a!important;
  border:1px solid rgba(255,255,255,.10)!important;
  box-shadow:0 28px 72px rgba(0,0,0,.42),inset 0 1px 0 rgba(255,255,255,.05)!important}}
.section-container-scroll{{position:relative}}
.container-scroll-shell{{--container-rotate:18deg;--container-scale:.88;--container-lift:0px;
  position:relative;min-height:48rem;padding:12px 0 0;perspective:1400px}}
.container-scroll-head{{max-width:780px;margin:0 auto 22px;text-align:center}}
.container-scroll-titlebar{{justify-content:center}}
.container-scroll-card{{position:relative;padding:18px;border-radius:30px;
  transform-style:preserve-3d;
  transform:translateY(var(--container-lift)) rotateX(var(--container-rotate)) scale(var(--container-scale));
  transform-origin:center top;
  transition:transform .18s ease-out,box-shadow .28s ease-out,filter .28s ease-out;
  background:linear-gradient(180deg,#11151d,#0a0a0a);
  border:1px solid rgba(255,255,255,.10);
  box-shadow:0 32px 74px rgba(0,0,0,.42)}}
.container-scroll-card .tbl-wrap{{border-radius:22px;border-color:rgba(255,255,255,.10)}}
.container-scroll-card::before{{content:'';position:absolute;inset:0;pointer-events:none;
  background:
    linear-gradient(180deg,rgba(255,255,255,.04),transparent 18%),
    radial-gradient(circle at 50% 0%,rgba(114,229,255,.10),transparent 38%);
  opacity:.48}}
.container-scroll-card.is-deployed{{box-shadow:0 42px 94px rgba(0,0,0,.52),0 0 24px rgba(114,229,255,.08)}}

/* NAV */
.nav{{position:sticky;top:0;z-index:100;background:#0d1117ee;
  backdrop-filter:blur(12px);border-bottom:1px solid var(--border);
  padding:4px 20px;display:flex;align-items:center;gap:0;flex-wrap:wrap}}
.nav-brand{{font-weight:700;font-size:.95em;color:var(--text);
  white-space:nowrap;padding:8px 16px 8px 0;border-right:1px solid var(--border);margin-right:8px}}
.nav-link{{padding:8px 8px;color:var(--muted);font-size:.82em;
  white-space:nowrap;transition:color .15s}}
.nav-link:hover{{color:var(--text);text-decoration:none}}
.nav-cta{{margin-left:auto;background:var(--green);color:#0d1117;
  padding:6px 16px;border-radius:6px;font-size:.83em;font-weight:600;
  white-space:nowrap;flex-shrink:0;border:none;cursor:pointer;font-family:inherit}}
.nav-cta:hover{{background:#3fb950cc;text-decoration:none}}
/* Mobile hamburger — hidden on desktop, shown ≤640px via media query below */
.nav-toggle{{display:none;background:transparent;border:1px solid var(--border);
  color:var(--text);padding:8px 12px;border-radius:6px;font-size:1.1em;line-height:1;
  cursor:pointer;font-family:inherit;margin-left:auto}}
.nav-toggle:hover{{background:var(--surface)}}
.nav-toggle[aria-expanded="true"]{{background:var(--surface);border-color:var(--green)}}

/* HERO */
.hero{{padding:40px 20px 28px;text-align:center;
  background:radial-gradient(ellipse at 50% 0%,#1a2e1a 0%,var(--bg) 70%)}}
.scroll-hint{{color:var(--muted);font-size:.8em;margin-top:16px;opacity:.6;letter-spacing:.05em}}
.hero-eyebrow{{display:inline-flex;align-items:center;gap:8px;
  background:var(--surface);border:1px solid var(--border);
  border-radius:20px;padding:4px 14px;font-size:.82em;color:var(--muted);margin-bottom:16px}}
.live-dot{{width:7px;height:7px;background:var(--green);border-radius:50%;
  animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.hero h1{{font-size:2.4em;font-weight:800;letter-spacing:-.02em;
  line-height:1.15;margin-bottom:12px;max-width:720px;margin-left:auto;margin-right:auto}}
.hero h1 span{{color:var(--green)}}
.hero-sub{{color:var(--muted);max-width:560px;margin:0 auto 28px;font-size:1.05em}}
.btn-row{{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}}
.btn{{display:inline-flex;align-items:center;gap:6px;padding:11px 24px;
  border-radius:7px;font-weight:600;font-size:.95em;transition:opacity .15s}}
.btn:hover{{opacity:.85;text-decoration:none}}
.btn-green{{background:var(--green);color:#0d1117}}
.btn-outline{{background:transparent;color:var(--text);border:1px solid var(--border)}}
.btn-tg{{background:#229ed9;color:#fff}}
.btn-install{{background:#1f2a3c;color:var(--blue);border:1px solid var(--blue);cursor:pointer;font-size:.95em}}
.sc-cerebro-link{{justify-content:center;width:100%;max-width:260px;margin:8px auto 0;
  border-radius:12px;border:1px solid #8edcff44;
  box-shadow:0 0 0 1px rgba(255,255,255,.02) inset,0 10px 28px rgba(88,166,255,.12);
  background:linear-gradient(135deg,#8fd8ff 0%,#3fb950 100%);
  color:#07111b;font-weight:700;letter-spacing:.04em}}
.sc-cerebro-link:hover{{transform:translateY(-1px);box-shadow:0 14px 32px rgba(88,166,255,.16)}}
.ce-transfer-overlay{{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
  background:radial-gradient(circle at 50% 38%,rgba(88,166,255,.18) 0%,rgba(9,14,22,.92) 48%,rgba(4,8,14,.97) 100%);
  opacity:0;pointer-events:none;transition:opacity .18s ease;z-index:100000}}
.ce-transfer-overlay.show{{opacity:1;pointer-events:auto}}
.ce-transfer-panel{{position:relative;width:min(560px,calc(100vw - 30px));padding:24px 24px 20px;border-radius:26px;
  border:1px solid rgba(142,220,255,.24);
  background:linear-gradient(180deg,rgba(10,16,26,.96) 0%,rgba(6,10,18,.94) 100%);
  box-shadow:0 24px 72px rgba(0,0,0,.46),0 0 30px rgba(88,166,255,.14),inset 0 1px 0 rgba(255,255,255,.05);
  backdrop-filter:blur(22px);transform:translateY(14px) scale(.985);transition:transform .28s cubic-bezier(.2,.8,.2,1)}}
.ce-transfer-panel::before{{content:"";position:absolute;inset:10px;border-radius:20px;pointer-events:none;
  border:1px solid rgba(255,255,255,.04);box-shadow:inset 0 0 0 1px rgba(114,229,255,.03)}}
.ce-transfer-panel::after{{content:"";position:absolute;inset:0;border-radius:26px;pointer-events:none;
  background:
    linear-gradient(90deg,rgba(114,229,255,.16),transparent 22%),
    radial-gradient(circle at 85% 14%,rgba(215,180,106,.14),transparent 28%);
  opacity:.48}}
.ce-transfer-overlay.show .ce-transfer-panel{{transform:translateY(0) scale(1)}}
.ce-transfer-eyebrow{{font-size:.72rem;letter-spacing:.3em;text-transform:uppercase;color:#8fd8ff;margin-bottom:10px}}
.ce-transfer-title{{font-size:1.55rem;font-weight:800;letter-spacing:-.03em;color:#f0f6fc}}
.ce-transfer-sub{{margin-top:6px;color:#9fb0c4;font-size:.94rem;line-height:1.5}}
.ce-transfer-stage{{display:flex;align-items:center;gap:10px;margin-top:14px;padding:10px 12px;border-radius:16px;
  border:1px solid rgba(255,255,255,.06);background:linear-gradient(180deg,rgba(255,255,255,.032),rgba(255,255,255,.018))}}
.ce-transfer-stage-led{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;flex:1}}
.ce-transfer-stage-pill{{padding:8px 9px;border-radius:12px;border:1px solid rgba(255,255,255,.05);
  background:rgba(255,255,255,.02);transition:all .18s ease}}
.ce-transfer-stage-pill[data-state="active"]{{border-color:rgba(114,229,255,.22);background:rgba(114,229,255,.09);
  box-shadow:0 0 18px rgba(114,229,255,.08)}}
.ce-transfer-stage-pill[data-state="done"]{{border-color:rgba(95,208,170,.18);background:rgba(95,208,170,.08)}}
.ce-transfer-stage-k{{font-size:.56rem;letter-spacing:.22em;text-transform:uppercase;color:#7f8da1}}
.ce-transfer-stage-v{{margin-top:6px;font-size:.74rem;color:#dce7f3;line-height:1.35}}
.ce-transfer-meta{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}
.ce-transfer-chip{{display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;
  border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.03);font-size:.72rem;letter-spacing:.16em;
  text-transform:uppercase;color:#c6d0de}}
.ce-transfer-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:16px}}
.ce-transfer-cell{{padding:11px 12px;border-radius:14px;border:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.028)}}
.ce-transfer-label{{font-size:.65rem;letter-spacing:.22em;text-transform:uppercase;color:#7f8da1}}
.ce-transfer-value{{margin-top:7px;font-size:1rem;font-weight:700;color:#f0f6fc}}
.ce-transfer-signal-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}}
.ce-transfer-signal{{padding:10px 12px;border-radius:15px;border:1px solid rgba(255,255,255,.05);background:rgba(255,255,255,.022)}}
.ce-transfer-signal-k{{font-size:.58rem;letter-spacing:.2em;text-transform:uppercase;color:#7f8da1}}
.ce-transfer-signal-v{{margin-top:7px;font-size:.8rem;line-height:1.45;color:#dce7f3}}
.ce-transfer-progress{{height:9px;border-radius:999px;overflow:hidden;margin-top:16px;border:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.04)}}
.ce-transfer-progress span{{display:block;width:100%;height:100%;transform:scaleX(var(--ce-progress,.08));transform-origin:left center;
  background:linear-gradient(90deg,rgba(143,216,255,.14) 0%,rgba(143,216,255,.7) 44%,rgba(63,185,80,.92) 100%);
  box-shadow:0 0 18px rgba(88,166,255,.22);transition:transform .24s cubic-bezier(.18,.82,.2,1)}}
.ce-transfer-overlay.show .ce-transfer-progress span{{transform:scaleX(var(--ce-progress,1))}}
.ce-transfer-footer{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:12px}}
.ce-transfer-rail{{font-size:.68rem;letter-spacing:.22em;text-transform:uppercase;color:#d7b46a}}
.ce-transfer-state{{font-size:.76rem;color:#9fb0c4}}
@media (max-width:560px){{
  .ce-transfer-stage-led{{grid-template-columns:1fr}}
  .ce-transfer-signal-grid{{grid-template-columns:1fr}}
  .ce-transfer-grid{{grid-template-columns:1fr}}
}}

/* SPOTLIGHT */
.spotlight-lamp-shell{{position:relative;width:100%;max-width:none;padding-top:44px;isolation:isolate}}
.spotlight-lamp-beam{{position:absolute;top:0;height:250px;width:min(36rem,44vw);opacity:0;pointer-events:none;mix-blend-mode:screen;filter:blur(16px);animation:lampBeam 2.4s cubic-bezier(.18,.84,.2,1) forwards}}
.spotlight-lamp-left{{--lamp-shift:14%;--lamp-rot:-5deg;right:50%;transform:translateX(14%) rotate(-5deg);background:conic-gradient(from 88deg at 100% 0%,rgba(114,229,255,.76),rgba(114,229,255,.16) 28%,transparent 58%)}}
.spotlight-lamp-right{{--lamp-shift:-14%;--lamp-rot:5deg;left:50%;transform:translateX(-14%) rotate(5deg);background:conic-gradient(from 272deg at 0% 0%,transparent 0%,rgba(95,208,170,.2) 26%,rgba(95,208,170,.74) 36%,transparent 58%)}}
.spotlight-lamp-core{{position:absolute;left:50%;top:20px;width:min(26rem,74vw);height:132px;transform:translateX(-50%);
  border-radius:999px;background:radial-gradient(circle,rgba(114,229,255,.46) 0%,rgba(95,208,170,.26) 36%,transparent 74%);
  filter:blur(28px);opacity:0;pointer-events:none;animation:lampCore 2.2s ease-out forwards .14s}}
@keyframes lampBeam{{0%{{opacity:0;transform:translateX(var(--lamp-shift,0)) scaleX(.42) rotate(var(--lamp-rot,0deg))}}45%{{opacity:.64}}100%{{opacity:.34;transform:translateX(var(--lamp-shift,0)) scaleX(1) rotate(var(--lamp-rot,0deg))}}}}
@keyframes lampCore{{0%{{opacity:0;transform:translateX(-50%) scale(.44)}}55%{{opacity:.68}}100%{{opacity:.4;transform:translateX(-50%) scale(1)}}}}
@keyframes lampBootRise{{0%{{opacity:0;transform:translateY(18px)}}100%{{opacity:1;transform:translateY(0)}}}}
.spotlight{{max-width:480px;margin:36px auto 0;
  background:linear-gradient(135deg,#1a2e1a,var(--surface));
  border:1px solid #2ea04344;border-radius:12px;padding:24px;text-align:center}}
.spotlight-label{{color:var(--muted);font-size:.82em;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em}}
.spotlight-boot .spotlight-label,
.spotlight-boot .spotlight-rail,
.spotlight-boot .spotlight-footnote{{opacity:0;transform:translateY(18px);animation:lampBootRise .82s cubic-bezier(.2,.9,.2,1) forwards}}
.spotlight-boot .spotlight-label{{animation-delay:.22s}}
.spotlight-boot .spotlight-rail-left{{animation-delay:.3s}}
.spotlight-boot .spotlight-rail-center{{animation-delay:.4s}}
.spotlight-boot .spotlight-rail-right{{animation-delay:.48s}}
.spotlight-boot .spotlight-footnote{{animation-delay:.58s}}
.spotlight-ticker-wrap{{max-width:100%;min-width:0;width:100%;overflow:hidden}}
.spotlight-ticker{{display:block;max-width:100%;min-width:0;width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  overflow-wrap:normal;word-break:normal;font-size:min(4.1rem,var(--ticker-fit-rem,2.45rem));font-weight:900;letter-spacing:-.045em;line-height:.84}}
.spotlight-ticker-compact{{white-space:normal;text-overflow:clip;overflow-wrap:anywhere;word-break:break-word;
  font-size:min(3rem,var(--ticker-fit-rem,1.86rem));letter-spacing:-.055em;line-height:.82}}
.spotlight-ticker-tight{{white-space:normal;text-overflow:clip;overflow-wrap:anywhere;word-break:break-word;
  font-size:min(2.3rem,var(--ticker-fit-rem,1.42rem));letter-spacing:-.065em;line-height:.8}}
.spotlight-meta{{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:12px 0}}
.spotlight-score{{margin-bottom:16px;color:var(--muted);font-size:.9em}}
.badge-form{{background:#21262d;color:#8b949e;padding:3px 10px;border-radius:5px;font-size:.8em;font-weight:600}}
.badge-cat{{background:#1f2a3c;color:var(--blue);padding:3px 10px;border-radius:5px;font-size:.8em}}
.badge-squeeze{{background:#2d1f1f;color:var(--orange);padding:3px 10px;border-radius:5px;font-size:.8em}}
.badge-insider{{background:#1a1f2e;color:var(--purple);padding:3px 10px;border-radius:5px;font-size:.8em}}

/* MAIN LAYOUT */
.wrap{{max-width:1060px;margin:0 auto;padding:40px 18px 60px}}

/* SECTIONS */
/* scroll-margin-top = top nav (~49px) + sticky sector bar (~52px) + 12px breathing room */
.section{{margin-bottom:48px;scroll-margin-top:113px}}
.section-head{{display:flex;align-items:center;gap:12px;margin-bottom:4px;
  padding-bottom:10px;border-bottom:1px solid var(--border)}}
.section-head h2{{font-size:1.15em;font-weight:700;color:var(--text)}}
.section-tag{{background:var(--surface2);color:var(--muted);padding:2px 9px;
  border-radius:4px;font-size:.75em;font-weight:500}}
.section-sub{{color:var(--muted);font-size:.85em;margin-bottom:14px}}

/* SCORE LEGEND */
.legend{{display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap}}
.legend-item{{display:flex;align-items:center;gap:5px;font-size:.78em;color:var(--muted)}}
.legend-dot{{width:8px;height:8px;border-radius:50%}}

/* TABLES */
.tbl-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:8px;border:1px solid var(--border)}}
table{{width:100%;border-collapse:collapse;background:var(--surface);min-width:420px}}
th{{background:var(--surface2);color:var(--muted);padding:9px 14px;
  text-align:left;font-size:.77em;text-transform:uppercase;letter-spacing:.06em;
  white-space:nowrap}}
td{{padding:10px 14px;border-bottom:1px solid #21262d;font-size:.88em;vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:var(--surface2)}}
tr.top-row td{{background:#1a2e1a22}}
.empty{{color:var(--muted);text-align:center;padding:24px!important;font-style:italic}}

/* INTELLIGENCE MODULE TABLES */
.intel-shell{{--intel-accent:#72e5ff;--intel-accent-soft:rgba(114,229,255,.18);
  position:relative;margin-top:18px;padding:22px 22px 18px;border-radius:30px;
  background:linear-gradient(180deg,#11151d,#0a0a0a);
  border:1px solid rgba(255,255,255,.10);overflow:hidden;isolation:isolate;
  box-shadow:0 30px 70px rgba(0,0,0,.44),inset 0 1px 0 rgba(255,255,255,.05)}}
.intel-shell::before{{content:'';position:absolute;inset:0;pointer-events:none;background:
  radial-gradient(circle at 12% 18%,var(--intel-accent-soft),transparent 24%),
  radial-gradient(circle at 86% 12%,rgba(255,255,255,.05),transparent 22%),
  radial-gradient(circle at 50% 100%,rgba(114,229,255,.14),transparent 30%),
  repeating-linear-gradient(120deg,rgba(255,255,255,.018) 0 1px,transparent 1px 18px);
  opacity:.52}}
.intel-shell::after{{content:'';position:absolute;inset:12px;border-radius:22px;border:1px solid rgba(255,255,255,.05);pointer-events:none}}
.intel-shell-head{{position:relative;z-index:1;display:grid;grid-template-columns:minmax(0,1.45fr) auto;gap:18px;align-items:start;margin-bottom:16px}}
.intel-shell-copy{{display:flex;flex-direction:column;gap:7px}}
.intel-shell-kicker{{font-family:'IBM Plex Mono',monospace;font-size:.66rem;letter-spacing:.22em;text-transform:uppercase;color:var(--intel-accent)}}
.intel-shell-title{{font-size:1rem;font-weight:800;letter-spacing:-.02em;color:#f5f7fb;max-width:40ch}}
.intel-shell-note{{font-size:.84rem;line-height:1.6;color:#9fb0c4;max-width:64ch}}
.intel-shell-telemetry{{display:flex;flex-direction:column;align-items:flex-end;gap:10px}}
.intel-shell-code{{display:inline-flex;align-items:center;justify-content:center;min-height:36px;padding:0 14px;border-radius:999px;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);font-family:'IBM Plex Mono',monospace;
  font-size:.66rem;letter-spacing:.22em;text-transform:uppercase;color:#dbe6f5}}
.intel-shell-stats{{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end}}
.intel-shell-stat{{display:flex;flex-direction:column;gap:4px;min-width:86px;padding:10px 12px;border-radius:16px;
  background:linear-gradient(180deg,rgba(18,21,30,.82),rgba(9,11,17,.66));border:1px solid rgba(255,255,255,.08);
  box-shadow:0 12px 26px rgba(0,0,0,.18),inset 0 1px 0 rgba(255,255,255,.04)}}
.intel-shell-stat-k{{font-family:'IBM Plex Mono',monospace;font-size:.56rem;letter-spacing:.16em;text-transform:uppercase;color:#8ea3bc}}
.intel-shell-stat-v{{font-size:.84rem;font-weight:800;color:#f4ece0}}
.intel-table-chassis{{position:relative;z-index:1;padding:14px;border-radius:24px;background:linear-gradient(180deg,#0f131b,#090b10);
  border:1px solid rgba(255,255,255,.10);box-shadow:0 20px 42px rgba(0,0,0,.30),inset 0 1px 0 rgba(255,255,255,.04);overflow:hidden}}
.intel-table-chassis::before{{content:'';position:absolute;inset:0;pointer-events:none;background:
  linear-gradient(180deg,rgba(114,229,255,.08),transparent 24%),
  radial-gradient(circle at 22% 0%,rgba(255,255,255,.06),transparent 18%),
  radial-gradient(circle at 50% 100%,rgba(114,229,255,.12),transparent 28%);
  opacity:.65}}
.intel-table-chassis::after{{content:'';position:absolute;left:15%;right:15%;bottom:-18px;height:44px;border-radius:999px;
  background:radial-gradient(circle,rgba(114,229,255,.16),rgba(114,229,255,0) 68%);pointer-events:none;filter:blur(4px)}}
.intel-shell .tbl-wrap{{position:relative;border:none;border-radius:18px;background:transparent;box-shadow:none;z-index:1}}
.intel-shell .tbl-wrap::before{{content:'';position:absolute;inset:0;border-radius:18px;border:1px solid rgba(255,255,255,.04);pointer-events:none}}
.intel-shell table{{position:relative;z-index:1;background:transparent;min-width:620px}}
.intel-shell th{{background:rgba(114,229,255,.08);border-bottom:1px solid rgba(114,229,255,.14);color:#9ddfff;padding:12px 14px}}
.intel-shell td{{background:rgba(255,255,255,.015);border-bottom:1px solid rgba(255,255,255,.06);padding:12px 14px}}
.intel-shell tbody tr{{transition:transform .16s ease,filter .16s ease}}
.intel-shell tbody tr:hover{{transform:translateX(2px);filter:saturate(1.04)}}
.intel-shell tbody tr:hover td{{background:linear-gradient(90deg,rgba(114,229,255,.10),rgba(255,255,255,.02) 40%,rgba(215,180,106,.06) 100%)}}
.intel-shell tbody td:first-child{{position:relative;padding-left:18px}}
.intel-shell tbody td:first-child::before{{content:'';position:absolute;left:0;top:11px;bottom:11px;width:2px;border-radius:999px;background:linear-gradient(180deg,var(--intel-accent),rgba(255,255,255,0))}}
.intel-shell .form-badge,.intel-shell .chip,.intel-shell .badge-form,.intel-shell .badge-cat,.intel-shell .tag-chip{{background:rgba(255,255,255,.05);border-color:rgba(255,255,255,.08)}}
.intel-shell .live-price-cell{{font-weight:800;color:#f4ece0}}
.intel-shell .summary-btn{{background:rgba(114,229,255,.08);border:1px solid rgba(114,229,255,.18);box-shadow:none}}
.intel-shell-foot{{position:relative;z-index:1;margin-top:12px;font-size:.76rem;line-height:1.6;color:#8ea3bc;
  font-family:'IBM Plex Mono',monospace;letter-spacing:.06em;text-transform:uppercase}}
.intel-empty-state{{min-height:220px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;
  gap:12px;padding:26px 20px;color:#a8b7c8}}
.intel-empty-icon{{font-size:2rem;line-height:1;filter:drop-shadow(0 0 12px rgba(114,229,255,.2))}}
.intel-empty-title{{font-size:1rem;font-weight:800;color:#f4ece0}}
.intel-empty-detail{{max-width:420px;font-size:.84rem;line-height:1.7}}
.intel-shell-options{{--intel-accent:#72e5ff;--intel-accent-soft:rgba(114,229,255,.18)}}
.intel-shell-squeeze{{--intel-accent:#ff8f6b;--intel-accent-soft:rgba(255,143,107,.18)}}
.intel-shell-insider{{--intel-accent:#7fe8b3;--intel-accent-soft:rgba(127,232,179,.18)}}
.intel-shell-darkpool{{--intel-accent:#d7b46a;--intel-accent-soft:rgba(215,180,106,.18)}}

/* PILLS + CHIPS */
.score-pill{{display:inline-block;padding:2px 10px;border-radius:20px;
  font-weight:700;font-size:.85em;font-variant-numeric:tabular-nums}}
.chip{{background:var(--surface2);color:var(--muted);padding:2px 8px;
  border-radius:4px;font-size:.78em;white-space:nowrap}}
.form-badge{{background:#21262d;color:#8b949e;padding:2px 7px;
  border-radius:4px;font-size:.78em;font-weight:600;cursor:help;position:relative}}
/* FILING TOOLTIP */
[data-tip]{{cursor:help}}
#global-tip{{position:fixed;background:#161b22;color:#e6edf3;border:1px solid #30363d;
  border-radius:7px;padding:8px 12px;font-size:.78em;line-height:1.5;max-width:260px;
  white-space:normal;z-index:9997;pointer-events:none;display:none;
  box-shadow:0 4px 20px #00000077}}
.ticker-link{{font-weight:700;color:var(--text)}}
a.ticker-link{{color:var(--blue)}}
a.ticker-link:hover{{text-decoration:underline}}
strong.clickable-ticker{{color:var(--blue);cursor:pointer}}
strong.clickable-ticker:hover{{text-decoration:underline}}

/* SECTORS — tiered hero / mid / chip layout */
.sector-grid{{display:flex;flex-direction:column;gap:14px}}
.sector-tier{{display:grid;gap:12px}}
.sector-tier-hero{{grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}}
.sector-tier-mid{{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}}
.sector-card{{background:var(--surface);border:1px solid var(--border);
  border-radius:10px;padding:14px 15px;transition:opacity .2s,border-color .2s,transform .2s;
  display:flex;flex-direction:column;gap:8px;position:relative}}
.sector-card:hover{{border-color:#58a6ff55;transform:translateY(-1px)}}
.sector-card.dimmed{{opacity:.35}}
.sector-card.hero{{padding:16px 18px;background:linear-gradient(180deg,var(--surface) 0%,rgba(88,166,255,.04) 100%);
  border-color:#58a6ff33}}
.sector-card.hero .sc-score{{font-size:1.9em}}
.sector-card.hero .sc-name{{font-size:1em}}
.sc-head{{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:2px}}
.sc-name{{font-weight:600;font-size:.9em;text-transform:capitalize;flex:1;min-width:0}}
.sc-score{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-weight:700;
  font-size:1.5em;color:var(--text);line-height:1;letter-spacing:-.02em;cursor:help}}
.sc-bar{{background:var(--surface2);height:5px;border-radius:3px;overflow:hidden}}
.sc-meta{{color:var(--muted);font-size:.78em;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.sc-mentions{{white-space:nowrap}}
.sc-delta{{font-weight:600;font-size:.92em;white-space:nowrap;font-family:'IBM Plex Mono',ui-monospace,monospace}}
.sc-spark{{margin-left:auto;opacity:.9}}
.sc-top-mover{{display:inline-flex;align-items:center;gap:6px;align-self:flex-start;
  padding:4px 10px;border:1px solid var(--border);border-radius:999px;
  background:var(--surface2);color:var(--text);font-size:.75em;text-decoration:none;
  transition:border-color .15s,background .15s}}
.sc-top-mover:hover{{border-color:#58a6ff;background:#58a6ff11;text-decoration:none}}
.sc-tm-label{{color:var(--muted);font-size:.92em}}
.sc-tm-ticker{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-weight:700;color:var(--blue)}}
.sc-expand-btn{{align-self:flex-start;background:transparent;color:var(--blue);border:none;
  padding:2px 0;font-size:.76em;font-weight:600;cursor:pointer;margin-top:2px}}
.sc-expand-btn:hover{{text-decoration:underline}}
.sc-headlines{{list-style:none;padding:8px 10px;margin:4px 0 0;background:var(--surface2);
  border-radius:6px;border:1px solid var(--border);font-size:.78em}}
.sc-headlines[hidden]{{display:none}}
.sc-headlines li{{padding:4px 0;border-bottom:1px dashed var(--border);line-height:1.4}}
.sc-headlines li:last-child{{border-bottom:none}}
.sc-headlines a{{color:var(--text)}}
.sc-headlines a:hover{{color:var(--blue)}}
.sc-hl-ticker{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-weight:700;
  color:var(--blue);margin-right:6px;font-size:.92em}}
.sector-chips{{display:flex;flex-wrap:wrap;gap:8px}}
.sector-chip{{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;
  background:var(--surface);border:1px solid var(--border);border-radius:999px;
  font-size:.78em;cursor:help;transition:border-color .15s}}
.sector-chip:hover{{border-color:#58a6ff55}}
.sc-chip-dot{{width:6px;height:6px;border-radius:50%}}
.sc-chip-name{{text-transform:capitalize;color:var(--text)}}
.sc-chip-score{{font-family:'IBM Plex Mono',ui-monospace,monospace;color:var(--muted);font-weight:600}}
.lead-sector-badge{{background:#3fb95022;color:#3fb950;border:1px solid #3fb95044;
  border-radius:10px;padding:1px 7px;font-size:.72em;font-weight:600;margin-left:6px}}
.vol-dot{{color:#58a6ff;font-size:.65em;vertical-align:super;margin-left:3px}}
.sc-vol-tag{{background:#58a6ff22;color:#58a6ff;border:1px solid #58a6ff44;
  border-radius:10px;padding:1px 7px;font-size:.72em;font-weight:600;margin-left:6px}}
/* Macro Tailwind badge */
.macro-dot{{font-size:.8em;margin-left:3px;vertical-align:middle;cursor:pointer}}
.macro-badge{{background:#bc8cff22;color:#bc8cff;border:1px solid #bc8cff44;
  border-radius:10px;padding:1px 8px;font-size:.72em;font-weight:600;margin-left:6px;
  cursor:help}}
/* Macro Alert badge — inline on gap cards */
.macro-alert-badge{{display:inline-block;background:#bc8cff18;color:#bc8cff;
  border:1px solid #bc8cff55;border-radius:8px;padding:2px 9px;
  font-size:.72em;font-weight:700;margin-top:5px;cursor:help;
  animation:macroGlow 3s ease-in-out infinite}}
@keyframes macroGlow{{0%,100%{{box-shadow:0 0 0 0 #bc8cff00}}
  50%{{box-shadow:0 0 6px 1px #bc8cff44}}}}
/* Nobel badges */
.nobel-badges-row{{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0 2px}}
.nobel-badge{{font-size:.68em;padding:2px 6px;border:1px solid;border-radius:10px;cursor:help;white-space:nowrap}}
/* Conviction Clock */
.conviction-clock{{font-size:.72em;color:#f0883e;background:#1e140a;border:1px solid #f0883e44;border-radius:6px;padding:4px 8px;margin:4px 0;line-height:1.4}}
/* Sub-penny liquidity flag */
.subpenny-flag{{font-size:.68em;color:#f78166;background:#1a0e0e;border:1px solid #f7816644;border-radius:6px;padding:4px 8px;margin:4px 0;line-height:1.4}}
/* Liquidity Alert toast */
#liq-toast-container{{position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;max-width:340px;pointer-events:none}}
.liq-toast-item{{background:#1a0e0e;border:1px solid #f7816688;border-radius:8px;padding:10px 14px;font-size:.76em;color:#f78166;box-shadow:0 4px 24px #0009;animation:liqSlideIn .35s ease;pointer-events:all;line-height:1.5}}
.liq-toast-title{{font-weight:700;font-size:1em;margin-bottom:3px;display:flex;align-items:center;justify-content:space-between}}
.liq-toast-close{{cursor:pointer;color:#f7816699;font-size:1.1em;line-height:1;padding:0 0 0 8px;flex-shrink:0}}
.liq-toast-close:hover{{color:#f78166}}
@keyframes liqSlideIn{{from{{transform:translateX(110%);opacity:0}}to{{transform:translateX(0);opacity:1}}}}
@keyframes liqFadeOut{{from{{opacity:1;transform:translateX(0)}}to{{opacity:0;transform:translateX(110%)}}}}
/* ── Danger pulse — two-layer glow: diffuse outer halo + tight inset blush ── */
@keyframes liqDangerPulse{{
  0%,100%{{box-shadow:0 4px 28px #0009,0 0 0 0 #f8514900,inset 0 0 0 0 #f8514900}}
  50%    {{box-shadow:0 4px 28px #000c,0 0 18px 5px #f8514940,inset 0 0 10px 0 #f8514914}}
}}
/* Banner text breathes on same 2s cycle — opacity dip + red text-glow */
@keyframes liqBannerPulse{{
  0%,100%{{opacity:1;text-shadow:none}}
  50%    {{opacity:.82;text-shadow:0 0 10px #f85149bb}}
}}
.liq-toast-danger{{
  border:1.5px solid #f8514977;
  background:linear-gradient(145deg,#1a0505 70%,#200808);
  animation:liqSlideIn .35s ease,liqDangerPulse 2s ease-in-out 0.4s infinite;
  position:relative
}}
/* Faint top-edge accent line — Bloomberg-style severity indicator */
.liq-toast-danger::before{{
  content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,#f8514900,#f85149cc 40%,#f85149cc 60%,#f8514900);
  border-radius:8px 8px 0 0
}}
.liq-danger-banner{{
  color:#f85149;font-weight:700;font-size:.9em;margin-bottom:5px;letter-spacing:.02em;
  animation:liqBannerPulse 2s ease-in-out 0.4s infinite
}}
.liq-vol-line{{color:#e3b341;margin-top:3px}}
/* Wall Eaten toast — green "go signal" */
.liq-toast-eaten{{background:#091209;border:1.5px solid #3fb95077}}
.liq-eaten-title{{color:#3fb950;font-weight:700;font-size:1em;margin-bottom:3px;display:flex;align-items:center;justify-content:space-between}}
.liq-eaten-body{{color:#e6edf3;margin-top:3px}}
.liq-eaten-sub{{color:#6a8070;font-size:.87em;margin-top:3px}}
/* Score anatomy */
.anatomy-toggle{{font-size:.72em;color:var(--muted);cursor:pointer;margin:4px 0 0;padding:2px 0;border-top:1px solid var(--border);text-align:center}}
.anatomy-toggle:hover{{color:var(--accent)}}
.anatomy-panel{{display:none;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:6px 8px;margin:4px 0;font-size:.7em}}
.anatomy-panel.anatomy-open{{display:block}}
.anatomy-row{{display:flex;justify-content:space-between;gap:8px;padding:2px 0;border-bottom:1px solid var(--border)}}
.anatomy-row:last-child{{border-bottom:none}}
.anatomy-key{{color:var(--muted);flex-shrink:0;min-width:70px}}
.anatomy-val{{text-align:right;color:var(--fg)}}
.anatomy-pts{{color:var(--muted);font-style:italic}}
.anatomy-total .anatomy-key,.anatomy-total .anatomy-val{{font-weight:700}}
/* Contrarian Whale badge */
.whale-badge{{background:#58a6ff18;color:#58a6ff;border:1px solid #58a6ff33;
  border-radius:10px;padding:2px 9px;font-size:.75em;font-weight:600;margin-left:4px;
  cursor:help}}
/* Premarket signal lock banner */
.power-hour-banner{{position:fixed;top:78px;right:18px;z-index:999;
  min-width:320px;max-width:420px;background:rgba(13,17,23,.86);
  border:1px solid rgba(88,166,255,.20);border-radius:18px;padding:16px 18px;
  backdrop-filter:blur(18px);box-shadow:0 18px 48px rgba(0,0,0,.45);
  display:flex;flex-direction:column;gap:12px;animation:fadeIn .4s ease}}
.power-hour-banner.is-fading{{animation:fadeAway .5s ease forwards}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(-8px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes fadeAway{{to{{opacity:0;transform:translateY(-10px);pointer-events:none}}}}
.ph-title{{display:flex;align-items:center;gap:8px;font-size:1em;font-weight:800;color:var(--text);letter-spacing:-.01em}}
.ph-sub{{color:var(--muted);font-size:.84em;line-height:1.45}}
.ph-reels{{display:flex;align-items:center;gap:4px;font-size:1.55em;font-weight:800;
  font-variant-numeric:tabular-nums}}
.ph-reel{{display:inline-block;overflow:hidden;height:1.15em;line-height:1.15em;
  background:rgba(0,0,0,.38);border:1px solid rgba(88,166,255,.16);border-radius:8px;
  padding:0 .2em;min-width:.72em;text-align:center;position:relative;
  box-shadow:0 2px 10px rgba(0,0,0,.28),inset 0 1px 0 rgba(255,255,255,.03)}}
.ph-reel span{{display:block;color:var(--text)}}
.ph-reel span.spinning{{animation:phSlot .18s cubic-bezier(.22,.68,0,1.2)}}
@keyframes phSlot{{from{{transform:translateY(-110%);opacity:.2}}to{{transform:translateY(0);opacity:1}}}}
.ph-colon{{color:var(--green);padding:0 2px;font-size:1em;font-weight:900;
  animation:phBlink 1s step-start infinite}}
@keyframes phBlink{{50%{{opacity:.25}}}}
.ph-et{{color:var(--muted);font-size:.33em;align-self:flex-end;
  padding-bottom:.4em;margin-left:6px;letter-spacing:.08em}}
.ph-dot{{width:10px;height:10px;background:var(--green);border-radius:50%;
  animation:pulse 1s infinite;display:inline-block;vertical-align:middle}}
/* Sector sticky filter bar */
.sector-sticky-wrap{{position:sticky;top:49px;z-index:90;scroll-margin-top:49px;
  background:#0d1117ee;backdrop-filter:blur(10px);
  border-bottom:1px solid var(--border);padding:8px 20px 6px}}
.sector-filter-bar{{display:flex;flex-wrap:nowrap;gap:7px;margin-bottom:0;
  overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:2px;
  scrollbar-width:none}}
.sector-filter-bar::-webkit-scrollbar{{display:none}}
.sec-filter-btn{{background:var(--surface);border:1px solid var(--border);
  color:var(--muted);padding:4px 13px;border-radius:20px;font-size:.8em;
  cursor:pointer;font-family:inherit;transition:all .15s;white-space:nowrap}}
.sec-filter-btn:hover{{border-color:var(--green);color:var(--text)}}
.sec-filter-btn.active{{background:var(--green);border-color:var(--green);
  color:#0d1117;font-weight:600;box-shadow:0 0 10px #3fb95055}}
.sec-count{{display:inline-block;background:#ffffff22;border-radius:10px;
  padding:0 5px;font-size:.75em;margin-left:4px;font-weight:700}}
#sector-filter-status{{font-size:.76em;color:var(--muted);margin-top:4px;
  min-height:0;transition:opacity .2s}}
.sector-detail-wrap{{background:var(--surface);border-bottom:1px solid var(--border);
  padding:14px 0 16px}}
/* Sector badge on spotlight */
.badge-sector{{background:#58a6ff22;color:#58a6ff;border:1px solid #58a6ff44;
  border-radius:10px;padding:2px 9px;font-size:.78em;font-weight:600}}
/* Hidden rows during filter */
tr.sr.sector-hidden{{display:none}}
tr.sr.sector-visible{{display:table-row}}
.sector-empty-msg{{display:none;padding:12px 16px;color:var(--muted);
  font-size:.85em;font-style:italic;border-top:1px solid var(--border)}}
.sector-empty-msg.visible{{display:block}}

/* Filing Summary Modal */
.fs-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9998;
  display:flex;align-items:center;justify-content:center;
  animation:fadeIn .15s ease;padding:16px}}
.fs-overlay.hidden{{display:none}}
.fs-modal{{background:#161b22;border:1px solid #30363d;border-radius:12px;
  padding:24px 26px;max-width:420px;width:100%;position:relative;
  box-shadow:0 12px 40px rgba(0,0,0,.6)}}
.fs-close{{position:absolute;top:12px;right:14px;background:none;border:none;
  color:var(--muted);font-size:1.3em;cursor:pointer;padding:0;line-height:1}}
.fs-close:hover{{color:var(--text)}}
.fs-ticker{{font-size:.78em;font-weight:700;color:var(--green);
  letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px}}
.fs-form{{font-size:.72em;color:var(--muted);margin-bottom:14px}}
.fs-bullets{{list-style:none;padding:0;margin:0 0 18px}}
.fs-bullets li{{padding:8px 0;border-bottom:1px solid var(--border);
  font-size:.88em;line-height:1.5;color:var(--text)}}
.fs-bullets li:last-child{{border-bottom:none}}
.fs-bullets li.warn{{color:#f0883e}}
.fs-link{{display:block;text-align:center;margin-top:4px;
  font-size:.85em;font-weight:600;color:var(--green);
  text-decoration:none;padding:8px;border:1px solid var(--green);
  border-radius:8px;transition:all .15s}}
.fs-link:hover{{background:var(--green);color:#0d1117}}
.fs-all-links{{margin-top:12px}}
.fs-all-links-label{{font-size:.75em;color:var(--muted);margin-bottom:6px;font-weight:600}}
.fs-cluster-link{{display:inline-block;font-size:.78em;color:var(--accent);
  text-decoration:none;padding:3px 8px;border:1px solid var(--accent)33;
  border-radius:4px;margin:2px 4px 2px 0}}
.fs-cluster-link:hover{{background:var(--accent)22}}

/* SEC Sector Heatmap */
#heatmap-wrap{{position:relative;margin-bottom:24px;padding:18px 18px 16px;border-radius:28px;
  background:linear-gradient(180deg,#11151d,#0a0a0a);
  border:1px solid rgba(255,255,255,.10);box-shadow:0 24px 56px rgba(0,0,0,.36),inset 0 1px 0 rgba(255,255,255,.04);overflow:hidden}}
#heatmap-wrap::before{{content:'';position:absolute;inset:0;pointer-events:none;background:
  radial-gradient(circle at 10% 18%,rgba(114,229,255,.14),transparent 24%),
  radial-gradient(circle at 86% 14%,rgba(213,156,255,.10),transparent 24%),
  repeating-linear-gradient(120deg,rgba(255,255,255,.018) 0 1px,transparent 1px 18px);
  opacity:.34}}
#heatmap-wrap::after{{content:'';position:absolute;inset:12px;border-radius:22px;border:1px solid rgba(255,255,255,.04);pointer-events:none}}
#heatmap-wrap .section-head{{position:relative;z-index:1;padding-bottom:12px;border-bottom:1px solid rgba(255,255,255,.06)}}
#heatmap-wrap .section-head h2{{font-size:1.18rem;letter-spacing:-.02em}}
#heatmap-wrap .section-sub{{position:relative;z-index:1;max-width:980px;color:#9fb0c4;line-height:1.7}}
#heatmap-container{{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-start;position:relative;z-index:1}}
.hm-block{{border-radius:16px;padding:14px 14px 12px;cursor:pointer;
  transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease,filter .16s ease;position:relative;
  min-width:70px;box-sizing:border-box;overflow:hidden;
  box-shadow:0 14px 34px rgba(0,0,0,.24),inset 0 1px 0 rgba(255,255,255,.03)}}
.hm-block::before{{content:'';position:absolute;inset:0;pointer-events:none;background:
  linear-gradient(180deg,rgba(255,255,255,.05),transparent 24%),
  radial-gradient(circle at 18% 16%,rgba(255,255,255,.08),transparent 26%),
  repeating-linear-gradient(120deg,rgba(255,255,255,.018) 0 1px,transparent 1px 18px);
  opacity:.42}}
.hm-block::after{{content:'';position:absolute;inset:10px;border-radius:10px;border:1px solid rgba(255,255,255,.06);pointer-events:none}}
.hm-block:hover{{transform:translateY(-2px) scale(1.01);
  box-shadow:0 18px 38px rgba(0,0,0,.26),0 0 20px rgba(114,229,255,.08),inset 0 1px 0 rgba(255,255,255,.05);filter:saturate(1.06)}}
.hm-block.hm-selected{{transform:translateY(-2px) scale(1.01);outline:1px solid rgba(127,232,179,.55);
  box-shadow:0 0 0 1px rgba(63,185,80,.20) inset,0 18px 40px rgba(0,0,0,.3),0 0 22px rgba(127,232,179,.14)}}
.hm-block.hm-bullish{{border-color:rgba(16,185,129,.5)!important;box-shadow:0 0 15px rgba(16,185,129,.30),0 14px 34px rgba(0,0,0,.24)}}
.hm-block.hm-bearish{{border-color:rgba(244,63,94,.5)!important;box-shadow:0 0 15px rgba(244,63,94,.30),0 14px 34px rgba(0,0,0,.24)}}
.hm-block.hm-neutral{{border-color:rgba(255,255,255,.10)!important;box-shadow:0 14px 34px rgba(0,0,0,.22)}}
.hm-block.hm-bullish.hm-pulse{{animation:hmPulseBull 2s ease-in-out infinite}}
.hm-block.hm-bearish.hm-pulse{{animation:hmPulseBear 2s ease-in-out infinite}}
@keyframes hmPulseBull{{0%,100%{{box-shadow:0 0 15px rgba(16,185,129,.30),0 14px 34px rgba(0,0,0,.24)}}50%{{box-shadow:0 0 24px rgba(16,185,129,.42),0 18px 42px rgba(0,0,0,.28)}}}}
@keyframes hmPulseBear{{0%,100%{{box-shadow:0 0 15px rgba(244,63,94,.30),0 14px 34px rgba(0,0,0,.24)}}50%{{box-shadow:0 0 24px rgba(244,63,94,.42),0 18px 42px rgba(0,0,0,.28)}}}}
/* ── Liquid-fill sentiment glass ─────────────────────────────────────────
   Pour-splash effect: two counter-rotating shapes at the surface create an
   undulating, sloshing waterline like liquid just poured into a glass.
   Caustic shimmer + specular highlight add internal body depth.
   z-index 0 keeps fill behind text (z-index 1). */
.hm-fill{{position:absolute;left:0;right:0;bottom:0;z-index:0;pointer-events:none;
  transition:height .6s cubic-bezier(.16,1,.3,1);overflow:hidden;border-radius:0 0 16px 16px}}

/* Surface shimmer — bright highlight line at the liquid edge */
.hm-fill::before{{content:'';position:absolute;left:0;right:0;top:0;height:2px;
  background:linear-gradient(90deg,transparent 5%,rgba(255,255,255,.30) 50%,transparent 95%);
  z-index:6;animation:hmShimmer 3s ease-in-out infinite}}

/* Body gradient — darker at bottom (sediment), lighter near surface */
.hm-fill::after{{content:'';position:absolute;inset:0;
  background:
    linear-gradient(180deg,
      color-mix(in srgb,currentColor 50%,transparent) 0%,
      color-mix(in srgb,currentColor 28%,transparent) 40%,
      color-mix(in srgb,currentColor 18%,transparent) 100%)}}

/* Primary splash wave — rotating dark shape masks liquid top → wavy surface */
.hm-fill-wave{{position:absolute;width:200%;height:200%;left:-50%;top:-180%;
  background:#12161e;border-radius:46% 42% 48% 38%;z-index:5;
  animation:hmSplash 4s linear infinite}}

/* Counter-wave — different speed + shape = interference sloshing */
.hm-fill-wave2{{position:absolute;width:200%;height:200%;left:-50%;top:-178%;
  background:#12161e;border-radius:38% 48% 42% 46%;z-index:5;
  animation:hmSplash 6s linear infinite reverse;opacity:.85}}

/* Internal caustic / light ripple layer */
.hm-fill-caustic{{position:absolute;inset:0;z-index:1;pointer-events:none;
  background:
    repeating-linear-gradient(115deg,transparent 0%,
      rgba(255,255,255,.04) 3%,transparent 6%,transparent 12%);
  animation:hmCaustic 8s linear infinite;opacity:.6}}

/* Specular highlight — drifting refraction glint */
.hm-fill-spec{{position:absolute;top:8%;left:15%;width:60%;height:35%;z-index:2;pointer-events:none;
  border-radius:50%;
  background:radial-gradient(ellipse at 50% 40%,rgba(255,255,255,.12) 0%,transparent 70%);
  animation:hmSpec 6s ease-in-out infinite;opacity:.7}}

.hm-fill-bull{{color:#10B981}}
.hm-fill-bear{{color:#F43F5E}}
.hm-fill-neutral{{color:#8b949e}}

/* Surface wave rotation — asymmetric border-radius does all the splash work */
@keyframes hmSplash{{from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}}}}
/* Surface shimmer pulse at liquid edge */
@keyframes hmShimmer{{0%,100%{{opacity:.12;transform:scaleX(.65)}}50%{{opacity:.40;transform:scaleX(1)}}}}
/* Caustic light bands drift diagonally */
@keyframes hmCaustic{{
  0%{{background-position:0 0}}
  100%{{background-position:200px 100px}}
}}
/* Specular highlight drifts left-right (compositor-friendly) */
@keyframes hmSpec{{
  0%,100%{{transform:translateX(0);opacity:.5}}
  50%{{transform:translateX(25%);opacity:.8}}
}}
@media (prefers-reduced-motion:reduce){{
  .hm-fill::before,.hm-fill-wave,.hm-fill-wave2,.hm-fill-caustic,.hm-fill-spec{{animation:none}}
}}
.hm-label{{position:relative;z-index:1;font-family:'IBM Plex Mono',monospace;font-size:.66em;font-weight:700;text-transform:uppercase;
  letter-spacing:.14em;opacity:.92;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}}
.hm-score{{position:relative;z-index:1;font-size:1.42em;font-weight:800;font-variant-numeric:tabular-nums;
  margin-top:10px;line-height:1.05;letter-spacing:-.03em}}
.hm-ticker{{position:relative;z-index:1;font-size:.67em;opacity:.76;margin-top:4px;letter-spacing:.08em;text-transform:uppercase}}
.hm-empty{{color:var(--muted);font-size:.85em;padding:12px 0;font-style:italic}}
/* Macro pressure badge on heatmap blocks */
.hm-macro-badge{{position:relative;z-index:1;font-size:.58em;margin-top:8px;border-radius:999px;
  padding:3px 8px;display:inline-flex;align-items:center;gap:4px;letter-spacing:.12em;font-weight:600;
  font-family:'IBM Plex Mono',monospace;text-transform:uppercase}}
.hm-macro-tail{{background:#0d2010;color:#3fb950;border:1px solid #3fb95033}}
.hm-macro-head{{background:#200808;color:#f78166;border:1px solid #f7816633}}
/* Drill-down panel */
#hm-drilldown{{margin-top:12px;padding:14px 16px;background:linear-gradient(180deg,rgba(8,11,17,.92),rgba(8,10,15,.84));
  border:1px solid rgba(114,229,255,.12);border-radius:18px;animation:hmDdSlide .22s ease;box-shadow:0 18px 38px rgba(0,0,0,.2)}}
@keyframes hmDdSlide{{from{{opacity:0;transform:translateY(-6px)}}to{{opacity:1;transform:none}}}}
.hm-dd-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}}
.hm-dd-title{{font-family:'IBM Plex Mono',monospace;font-size:.74em;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#c9d1d9}}
.hm-dd-sector{{font-size:.72em;opacity:.6;margin-left:8px;font-weight:400;text-transform:none;letter-spacing:0}}
.hm-dd-close{{background:none;border:1px solid rgba(255,255,255,.12);border-radius:999px;color:#8b949e;
  font-size:.7em;cursor:pointer;padding:4px 10px;transition:border-color .15s,color .15s;
  font-family:'IBM Plex Mono',monospace;letter-spacing:.12em;text-transform:uppercase}}
.hm-dd-close:hover{{border-color:#58a6ff;color:#58a6ff}}
.hm-dd-body{{display:flex;flex-wrap:wrap;gap:7px}}
.hm-ig-block{{background:#161b22;border:1px solid #21262d;border-radius:7px;
  padding:8px 12px;min-width:180px;cursor:pointer;transition:border-color .15s,transform .15s}}
.hm-ig-block:hover{{border-color:#58a6ff55;transform:translateY(-1px)}}
.hm-ig-name{{font-size:.68em;font-weight:700;color:#c9d1d9;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;max-width:220px}}
.hm-ig-tickers{{font-size:.62em;color:#58a6ff;margin-top:3px;letter-spacing:.02em}}
.hm-ig-stats{{font-size:.6em;color:#8b949e;margin-top:2px}}
/* Level 3 — Industry cards */
.hm-ind-block{{background:#0d1117;border:1px solid #21262d;border-radius:7px;
  padding:8px 12px;min-width:150px;cursor:pointer;transition:border-color .15s,transform .15s}}
.hm-ind-block:hover{{border-color:#3fb95055;transform:translateY(-1px)}}
.hm-ind-name{{font-size:.67em;font-weight:700;color:#c9d1d9;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;max-width:200px}}
.hm-ind-stats{{font-size:.59em;color:#8b949e;margin-top:2px}}
/* Level 4 — Sub-Industry cards (leaf nodes) */
.hm-si-block{{background:#090d12;border:1px solid #1c2128;border-radius:6px;
  padding:7px 10px;min-width:140px}}
.hm-si-name{{font-size:.65em;font-weight:600;color:#8b949e;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;max-width:190px}}
.hm-si-tickers{{font-size:.6em;color:#58a6ff;margin-top:2px;letter-spacing:.02em}}
.hm-si-stats{{font-size:.58em;color:#6e7681;margin-top:2px}}
/* Breadcrumb navigation */
.hm-breadcrumb{{font-size:.68em;color:#8b949e;margin-bottom:10px;
  display:flex;align-items:center;gap:4px;flex-wrap:wrap}}
.hm-bc-item{{cursor:pointer;color:#58a6ff;transition:color .15s}}
.hm-bc-item:hover{{color:#79c0ff;text-decoration:underline}}
.hm-bc-sep{{opacity:.4;font-size:.85em}}
.hm-bc-active{{color:#c9d1d9;cursor:default}}

/* HOW IT WORKS */
.how-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}}
.how-card{{background:var(--surface);border:1px solid var(--border);
  border-radius:8px;padding:18px}}
.how-num{{font-size:1.8em;font-weight:800;color:var(--green);opacity:.4;
  line-height:1;margin-bottom:8px}}
.how-card h3{{font-size:.9em;font-weight:700;margin-bottom:6px}}
.how-card p{{color:var(--muted);font-size:.82em;line-height:1.5}}

/* CTA BLOCK */
.cta-block{{background:linear-gradient(135deg,#1a2e1a,var(--surface));
  border:1px solid #2ea04344;border-radius:12px;
  padding:40px 32px;text-align:center;margin-top:16px}}
.cta-block h2{{font-size:1.5em;font-weight:700;margin-bottom:10px}}
.cta-block p{{color:var(--muted);margin-bottom:22px;max-width:480px;margin-left:auto;margin-right:auto}}
.cta-links{{color:var(--muted);font-size:.85em;margin-top:14px}}
.cta-links a{{color:var(--blue);margin:0 6px}}

/* SCANNER FRESHNESS */
.countdown-bar{{background:linear-gradient(180deg,rgba(22,27,34,.94),rgba(13,17,23,.82));
  border:1px solid rgba(88,166,255,.16);border-radius:16px;padding:16px 18px;
  margin-bottom:32px;color:var(--muted);backdrop-filter:blur(16px);
  box-shadow:0 16px 40px rgba(0,0,0,.24),inset 0 1px 0 rgba(255,255,255,.03)}}
.freshness-bar{{display:flex;flex-direction:column;gap:14px}}
.freshness-head{{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}}
.freshness-badge{{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:999px;
  background:rgba(63,185,80,.10);border:1px solid rgba(63,185,80,.22);color:var(--green);
  font-size:.72em;font-weight:800;letter-spacing:.04em;text-transform:uppercase}}
.freshness-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}
.freshness-card{{background:rgba(13,17,23,.55);border:1px solid rgba(48,54,61,.75);
  border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:6px;min-height:78px;
  justify-content:center}}
.freshness-kicker{{color:var(--muted);font-size:.72em;text-transform:uppercase;letter-spacing:.06em}}
.freshness-foot{{font-size:.78em;line-height:1.5;color:var(--muted)}}
.freshness-foot strong{{color:var(--text)}}

/* FLOATING CTA */
.float-cta{{position:fixed;bottom:20px;right:20px;z-index:200;
  background:var(--green);color:#0d1117;padding:11px 20px;
  border-radius:30px;font-weight:700;font-size:.88em;
  box-shadow:0 4px 20px #3fb95055;transition:transform .15s}}
.float-cta:hover{{transform:translateY(-2px);text-decoration:none;color:#0d1117}}

/* STICKY MOBILE SUBSCRIBE BAR */
/* STICKY MOBILE SUBSCRIBE BAR — hidden by default, JS reveals after 15s */
.mobile-sub-bar{{display:none;position:fixed;bottom:0;left:0;right:0;z-index:300;
  background:#0f1f2e;border-top:2px solid var(--green);
  padding:12px 16px;align-items:center;gap:12px;
  box-shadow:0 -4px 20px #00000055;
  transform:translateY(100%);transition:transform .35s ease}}
.mobile-sub-bar.visible{{transform:translateY(0)}}
.mobile-sub-bar-text{{flex:1;font-size:.88em;color:var(--text);line-height:1.3}}
.mobile-sub-bar-text strong{{color:var(--green);display:block}}
.mobile-sub-bar-btn{{background:var(--green);color:#0d1117;border:none;
  padding:10px 18px;border-radius:8px;font-weight:700;font-size:.88em;
  cursor:pointer;white-space:nowrap;flex-shrink:0}}
.mobile-sub-bar-close{{background:none;border:none;color:var(--muted);
  font-size:1.2em;cursor:pointer;padding:4px 8px;flex-shrink:0}}

/* RECOMMENDED BROKERS — fixed visibility (was invisible against dark posture-shell bg) */
.broker-section{{
  position:relative;z-index:2;
  background:linear-gradient(180deg,rgba(20,26,40,.98),rgba(14,18,28,.96));
  border:1px solid rgba(215,180,106,.35);
  border-radius:14px;
  box-shadow:0 12px 32px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.06);
  padding:28px 32px;margin:48px auto 0;max-width:820px}}
.broker-section h3{{color:#f4ece0;font-size:1.15em;margin:0 0 6px;font-weight:800;letter-spacing:.3px}}
.broker-section .broker-sub{{color:#c5cfe0;font-size:.78em;margin-bottom:20px;opacity:1}}
.broker-list{{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(2,1fr);gap:14px}}
.broker-list li{{display:flex;flex-direction:column;gap:4px;font-size:.85em;
  background:rgba(8,12,20,.55);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:10px 14px;
  transition:border-color .18s,transform .18s}}
.broker-list li:hover{{border-color:rgba(215,180,106,.55);transform:translateY(-1px)}}
.broker-list li a{{color:#3fb950;font-weight:700;text-decoration:none;white-space:nowrap;font-size:1em}}
.broker-list li a:hover{{text-decoration:underline}}
.broker-list li span{{color:#8ea3bc;font-size:.82em}}
@media(max-width:620px){{.broker-list{{grid-template-columns:1fr}}}}

/* FOOTER */
footer{{background:var(--surface);border-top:1px solid var(--border);
  padding:28px 20px;text-align:center;color:var(--muted);font-size:.82em}}
footer a{{color:var(--blue);margin:0 5px}}
.footer-links{{margin:10px 0}}
.disclaimer{{font-size:.75em;margin-top:10px;opacity:.7}}

/* EMAIL SUCCESS STATE */
.sub-success{{padding:14px 20px;background:#1a2e1a;border:1px solid #2ea043;border-radius:8px;
  color:var(--green);font-weight:600;font-size:.95em;line-height:1.6;text-align:center}}

@media(max-width:640px){{
  .hero{{padding:28px 16px 20px}}
  .hero h1{{font-size:1.6em}}
  .stat-n{{font-size:1.3em}}
  /* Mobile nav: replace hidden links with hamburger drawer */
  .nav-toggle{{display:inline-block}}
  .nav-cta{{order:2;margin-left:8px}}
  .nav-toggle{{order:1;margin-left:auto}}
  /* Collapse all nav-links by default on mobile */
  .nav .nav-link{{display:none}}
  /* When .nav.open, reveal links as a vertical drawer below the sticky bar */
  .nav.open{{flex-wrap:wrap}}
  .nav.open .nav-link{{display:block;flex:0 0 100%;width:100%;
    padding:14px 12px;border-top:1px solid var(--border);
    font-size:1em;color:var(--text);background:#0d1117ee}}
  .nav.open .nav-link:hover{{background:var(--surface)}}
  .spotlight{{margin-top:24px}}
  .wrap{{padding:24px 14px 80px}}
  .freshness-grid{{grid-template-columns:1fr}}
  .power-hour-banner{{left:12px;right:12px;top:auto;bottom:18px;min-width:0}}
  .ph-reels{{font-size:1.15em}}
  .float-cta{{bottom:16px;right:12px;font-size:.82em}}
  .intel-shell{{padding:18px 16px 14px;border-radius:24px}}
  .intel-shell-head{{grid-template-columns:1fr}}
  .intel-shell-telemetry{{align-items:flex-start}}
  .intel-shell-stats{{justify-content:flex-start}}
  .intel-shell table{{min-width:540px}}
  /* Mobile table: scrollable with scroll hint gradient */
  .tbl-wrap{{position:relative}}
  .tbl-wrap::after{{content:'';position:absolute;top:0;right:0;width:28px;height:100%;
    background:linear-gradient(to left,var(--surface),transparent);
    pointer-events:none;border-radius:0 8px 8px 0}}
  table{{font-size:.78em}}
  th,td{{padding:7px 9px}}
  /* Hide low-priority columns on mobile */
  .hide-mobile{{display:none!important}}
}}

/* SORTABLE TABLES */
table.sortable th{{cursor:pointer;user-select:none;white-space:nowrap}}
table.sortable th:hover{{background:var(--surface2);color:var(--text)}}
table.sortable th::after{{content:" ↕";opacity:.35;font-size:.75em}}
table.sortable th.sort-asc::after{{content:" ▲";opacity:1}}
table.sortable th.sort-desc::after{{content:" ▼";opacity:1}}

/* SPARKLINE */
.sparkline-cell{{white-space:nowrap}}

/* TRACK RECORD */
.track-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:20px 0}}
.track-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px}}
.track-n{{font-size:2.2em;font-weight:800;letter-spacing:-.02em;margin-bottom:4px}}
.track-label{{color:var(--muted);font-size:.83em;margin-bottom:12px}}
.track-bar{{background:#21262d;border-radius:4px;height:6px;overflow:hidden}}
.track-bar div{{height:100%;border-radius:4px;transition:width .8s}}
.track-disclaimer{{background:#161b22;border:1px solid #f0883e33;border-radius:6px;
  padding:12px 16px;font-size:.78em;color:var(--muted);margin-top:16px;line-height:1.5}}

/* FREE FOREVER BOX */
.free-forever-box{{background:#1a2b1a;border:1px solid #2ea04344;border-radius:8px;
  padding:14px 18px;margin-top:16px;font-size:.85em;color:var(--muted);line-height:1.6}}

/* COMPETITOR TABLE */
.comp-table{{width:100%;border-collapse:collapse;margin:18px 0;font-size:.87em}}
.comp-table th{{background:var(--surface);color:var(--muted);padding:8px 10px;
  border:1px solid var(--border);font-weight:600;text-align:center}}
.comp-table td{{padding:8px 10px;border:1px solid var(--border);text-align:center}}
.comp-table tr:first-child td,.comp-table tr:first-child th{{border-top:2px solid var(--border)}}
.comp-us{{background:#1a2b1a;color:var(--green);font-weight:700}}
.comp-check{{color:var(--green);font-size:1.1em}}
.comp-no{{color:var(--muted);opacity:.5}}
.comp-price-free{{color:var(--green);font-weight:700}}
.comp-price-paid{{color:#f78166}}

/* ── POLYMARKET TENSION RINGS ───────────────────────────────────────────
   Each market rendered as a conic-gradient arc inside a ring.
   Probability fills the arc. Contested markets pulse. Locked consensus
   glows steady. Volume scales ring thickness. Countdown adds urgency. */
.pm-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px;margin:24px 0}}
.pm-card{{position:relative;background:rgba(13,17,23,.72);border:1px solid rgba(48,54,61,.6);
  border-radius:16px;padding:20px;display:flex;gap:16px;align-items:center;
  transition:border-color .25s,transform .18s,box-shadow .25s;overflow:hidden}}
.pm-card:hover{{border-color:var(--blue);transform:translateY(-3px);
  box-shadow:0 18px 44px rgba(0,0,0,.32)}}
/* Ambient glow behind card on hover */
.pm-card::before{{content:'';position:absolute;inset:-1px;border-radius:16px;opacity:0;
  transition:opacity .3s;pointer-events:none;z-index:0}}
.pm-card:hover::before{{opacity:.14}}
.pm-card[data-tension="high"]::before{{background:radial-gradient(circle at 30% 50%,var(--pm-glow),transparent 70%)}}
.pm-card[data-tension="locked"]::before{{background:radial-gradient(circle at 30% 50%,rgba(46,160,67,.3),transparent 70%)}}

/* ── Tension Ring (the arc gauge) ── */
@property --pm-deg{{syntax:'<angle>';inherits:false;initial-value:0deg}}
.pm-ring-wrap{{position:relative;flex-shrink:0;width:72px;height:72px;z-index:1}}
.pm-ring{{width:72px;height:72px;border-radius:50%;position:relative;
  background:conic-gradient(var(--pm-arc) 0deg,var(--pm-arc) var(--pm-deg,0deg),
    rgba(33,38,45,.6) var(--pm-deg,0deg),rgba(33,38,45,.6) 360deg);
  transition:--pm-deg 1.2s cubic-bezier(.16,1,.3,1)}}
.pm-ring::after{{content:'';position:absolute;
  inset:var(--pm-thick,10px);border-radius:50%;background:#0d1117}}
/* Probability number centered in ring */
.pm-ring-pct{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-size:1.1em;font-weight:800;z-index:2;letter-spacing:-.02em}}
/* Contested pulse — ring breathes when probability is 30-70% */
.pm-ring-pulse{{position:absolute;inset:-4px;border-radius:50%;z-index:-1;
  animation:pmPulse 2.4s ease-in-out infinite;opacity:0}}
.pm-card[data-tension="high"] .pm-ring-pulse{{opacity:1;
  box-shadow:0 0 18px var(--pm-glow),0 0 36px var(--pm-glow)}}
/* Locked consensus — steady soft glow */
.pm-card[data-tension="locked"] .pm-ring-pulse{{opacity:.6;animation:none;
  box-shadow:0 0 12px rgba(46,160,67,.28)}}
/* Urgency shimmer on countdown markets */
.pm-ring-urgency{{position:absolute;inset:0;border-radius:50%;z-index:3;pointer-events:none;opacity:0}}
.pm-card[data-urgency="hot"] .pm-ring-urgency{{opacity:1;
  background:conic-gradient(transparent 0deg,rgba(255,255,255,.08) 20deg,transparent 40deg);
  animation:pmUrgency 1.4s linear infinite}}

/* ── Card content (right side) ── */
.pm-card-body{{flex:1;min-width:0;z-index:1}}
.pm-badge{{font-size:.68em;font-weight:800;padding:2px 10px;border-radius:20px;
  border:1px solid;letter-spacing:.04em;display:inline-block}}
.pm-hot{{font-size:.68em;background:#2d1f0e;color:var(--orange);
  border:1px solid #f0883e44;border-radius:20px;padding:2px 8px;font-weight:700;
  display:inline-block;margin-left:6px}}
.pm-countdown{{font-size:.68em;color:var(--yellow);font-weight:600;display:inline-block;margin-left:6px}}
.pm-title{{display:block;font-size:.88em;font-weight:700;color:var(--text);line-height:1.32;
  margin:6px 0 4px;text-decoration:none;transition:color .15s}}
.pm-title:hover{{color:var(--blue)}}
.pm-meta{{display:flex;gap:12px;flex-wrap:wrap;align-items:center;font-size:.72em;color:var(--muted)}}
.pm-meta strong{{color:var(--text);font-weight:600}}
.pm-vol-bar{{flex:1;min-width:60px;height:3px;background:#21262d;border-radius:2px;overflow:hidden}}
.pm-vol-fill{{height:100%;border-radius:2px;background:var(--pm-arc);opacity:.5;
  transition:width 1s cubic-bezier(.16,1,.3,1)}}
.pm-impact{{font-size:.74em;color:var(--muted);margin-top:4px}}
.pm-impact strong{{color:var(--text)}}
.pm-24h{{display:inline-block;background:var(--surface2);border-radius:10px;
  padding:1px 8px;font-size:.85em;color:var(--green);margin-left:6px}}

/* ── Keyframes ── */
@keyframes pmPulse{{
  0%,100%{{transform:scale(1);opacity:.4}}
  50%{{transform:scale(1.08);opacity:.7}}
}}
@keyframes pmUrgency{{
  from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}}
}}
@media(prefers-reduced-motion:reduce){{
  .pm-ring-pulse,.pm-ring-urgency{{animation:none!important}}
}}
@media(max-width:640px){{.pm-grid{{grid-template-columns:1fr}}}}

/* ── TRUE SLOT REEL DIGITS ── */
/* position:absolute on the strip means its height never pushes the
   reel container open — overflow:hidden then clips it cleanly */
.reel{{display:inline-block;overflow:hidden;height:1.15em;
  position:relative;vertical-align:middle;min-width:0.54em}}
.reel-strip{{position:absolute;top:0;left:0;right:0;will-change:transform}}
.reel-strip>span{{display:block;height:1.15em;line-height:1.15em;
  text-align:center;font-variant-numeric:tabular-nums}}
.reel-static{{display:inline-block;vertical-align:middle;line-height:1.15em}}

/* Flash on price change */
.slot-flash-up{{animation:flashUp .7s ease both}}
.slot-flash-dn{{animation:flashDn .7s ease both}}
@keyframes flashUp{{
  0%{{background:#1a3a1a;box-shadow:0 0 14px #3fb95066}}
  100%{{background:transparent;box-shadow:none}}
}}
@keyframes flashDn{{
  0%{{background:#2d1010;box-shadow:0 0 14px #f7816644}}
  100%{{background:transparent;box-shadow:none}}
}}

/* LIVE TICKER BAR — seamless marquee */
.live-ticker-bar{{background:var(--surface);border-bottom:1px solid var(--border);
  overflow:hidden;position:relative}}
.live-ticker-bar::before,.live-ticker-bar::after{{content:"";position:absolute;top:0;bottom:0;
  width:54px;z-index:2;pointer-events:none}}
.live-ticker-bar::before{{left:0;background:linear-gradient(90deg,var(--surface),transparent)}}
.live-ticker-bar::after{{right:160px;background:linear-gradient(-90deg,var(--surface),transparent)}}
.ltb-track{{display:flex;align-items:stretch;width:100%;position:relative}}
.ltb-inner{{display:flex;align-items:stretch;white-space:nowrap;flex:1;min-width:0;
  animation:ltb-marquee 72s linear infinite;will-change:transform}}
.ltb-inner:hover{{animation-play-state:paused}}
@keyframes ltb-marquee{{from{{transform:translateX(0)}}to{{transform:translateX(-50%)}}}}
.ltb-item{{display:inline-flex;flex-direction:row;align-items:center;gap:8px;
  padding:9px 22px;border-right:1px solid #30363d44;flex-shrink:0;
  transition:background .35s,box-shadow .35s}}
.ltb-item.ltb-sep{{border-left:1px solid #30363d88;margin-left:2px;padding-left:22px}}
.ltb-sym{{font-weight:800;color:var(--muted);font-size:.72em;letter-spacing:.07em;
  text-transform:uppercase;min-width:2.4em}}
.ltb-price{{display:inline-flex;align-items:center;font-weight:700;
  color:var(--text);font-size:.88em;letter-spacing:.01em;font-variant-numeric:tabular-nums}}
.ltb-chg{{display:inline-flex;align-items:center;font-weight:700;font-size:.8em;
  min-width:5.2em;font-variant-numeric:tabular-nums}}
.ltb-chg.up{{color:var(--green)}}
.ltb-chg.dn{{color:var(--red)}}
.ltb-chg.flat{{color:var(--muted)}}
.ltb-skeleton{{color:var(--muted);animation:ltbpulse 1.2s ease infinite;font-size:.8em}}
@keyframes ltbpulse{{0%,100%{{opacity:.2}}50%{{opacity:.75}}}}
.ltb-flash-up{{animation:ltbFlashUp .95s ease both}}
.ltb-flash-dn{{animation:ltbFlashDn .95s ease both}}
@keyframes ltbFlashUp{{
  0%{{background:#1a3a1a;box-shadow:inset 0 0 0 1px #2ea04377}}
  100%{{background:transparent;box-shadow:none}}
}}
@keyframes ltbFlashDn{{
  0%{{background:#2d1010;box-shadow:inset 0 0 0 1px #f7816677}}
  100%{{background:transparent;box-shadow:none}}
}}
.ltb-ts{{flex-shrink:0;padding:9px 14px;color:var(--muted);
  font-size:.68em;border-left:1px solid var(--border);align-self:stretch;
  display:flex;align-items:center;gap:5px;white-space:nowrap;
  background:var(--surface);position:relative;z-index:3}}
.ltb-dot{{width:5px;height:5px;background:var(--green);border-radius:50%;
  flex-shrink:0;animation:pulse 2s infinite}}
@media (prefers-reduced-motion: reduce){{
  .ltb-inner{{animation:none}}
  .ltb-flash-up,.ltb-flash-dn{{animation:none}}
}}
@media (max-width:640px){{
  .ltb-inner{{animation-duration:90s}}
  .ltb-item{{padding:9px 16px;gap:6px}}
  .live-ticker-bar::after{{right:120px}}
}}

/* SPOTLIGHT LIVE PRICE */
.spotlight-live{{width:100%;max-width:100%;font-size:.92em;margin:4px 0 10px;min-height:22px;display:flex;
  flex-wrap:wrap;align-items:center;gap:8px;justify-content:flex-start;min-width:0;overflow:hidden}}
.slp-price{{max-width:100%;min-width:0;font-weight:800;color:var(--text);font-size:1.02em;
  display:inline-flex;align-items:center;white-space:nowrap;letter-spacing:-.02em}}
.slp-chg{{max-width:100%;font-weight:700;padding:4px 9px;border-radius:999px;font-size:.76em;
  display:inline-flex;align-items:center;white-space:nowrap;box-shadow:0 8px 18px rgba(0,0,0,.16);
  width:auto;align-self:center;overflow:hidden;text-overflow:ellipsis}}
.slp-chg.up{{color:#0d1117;background:var(--green)}}
.slp-chg.dn{{color:#fff;background:var(--red)}}

/* COUNTDOWN SLOT REELS */
.cd-label{{color:var(--text);font-size:1em;font-weight:800;letter-spacing:-.01em}}
#countdown,#scanner-last-refresh,#scanner-price-cd{{display:inline-flex;align-items:center;gap:0;
  font-size:1.02em;font-weight:700;font-variant-numeric:tabular-nums}}
#countdown{{color:var(--text);letter-spacing:.03em}}
#scanner-last-refresh,#scanner-price-cd{{color:var(--green)}}

/* SCANNER HERO — the single H1 + proof strip that leads the page */
.scanner-hero{{position:relative;z-index:4;padding:26px 20px 22px;
  background:
    radial-gradient(ellipse at 85% 0%, rgba(215,180,106,.10), transparent 55%),
    radial-gradient(ellipse at 12% 120%, rgba(114,229,255,.07), transparent 55%),
    linear-gradient(180deg,#0b111c,#0d1624 55%,#0b121d);
  border-bottom:1px solid rgba(215,180,106,.22)}}
.scanner-hero .sh-wrap{{max-width:1180px;margin:0 auto}}
.scanner-hero .sh-kicker{{font-family:'IBM Plex Mono',monospace;font-size:.72em;
  letter-spacing:.22em;text-transform:uppercase;color:#d4a843;margin-bottom:10px;
  display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.scanner-hero .sh-kicker .sh-dot{{width:8px;height:8px;border-radius:50%;
  background:#3fb950;box-shadow:0 0 10px #3fb950;animation:sh-pulse 1.6s ease-in-out infinite}}
@keyframes sh-pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.scanner-hero h1{{font-size:clamp(1.55em,3.1vw,2.1em);font-weight:800;line-height:1.12;
  letter-spacing:-.015em;margin:0 0 12px;color:#eef2f8;max-width:900px;
  background:linear-gradient(135deg,#eef2f8 40%,#d4a843 110%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.scanner-hero .sh-sub{{color:#8b96ab;font-size:.96em;line-height:1.6;max-width:760px;
  margin:0 0 20px}}
.scanner-hero .sh-sub b{{color:#e6edf3;font-weight:600}}
.scanner-hero .sh-proof{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
  background:rgba(215,180,106,.18);border-radius:12px;overflow:hidden;
  border:1px solid rgba(215,180,106,.22)}}
.scanner-hero .shp-cell{{background:linear-gradient(180deg,#10192a,#0c1522);
  padding:14px 16px;text-align:left}}
.scanner-hero .shp-num{{display:block;font-family:'IBM Plex Mono',monospace;
  font-size:1.55em;font-weight:700;color:#72e5ff;letter-spacing:-.01em;line-height:1.1}}
.scanner-hero .shp-num.shp-gold{{color:#e7b76c}}
.scanner-hero .shp-num.shp-green{{color:#3fb950}}
.scanner-hero .shp-num.shp-red{{color:#ff6b6b}}
.scanner-hero .shp-lbl{{display:block;font-size:.72em;color:#8b96ab;
  letter-spacing:.06em;margin-top:4px;line-height:1.35}}
.scanner-hero .sh-links{{margin-top:14px;display:flex;gap:18px;flex-wrap:wrap;
  font-size:.82em}}
.scanner-hero .sh-links a{{color:#79c0ff;text-decoration:none;letter-spacing:.01em}}
.scanner-hero .sh-links a:hover{{color:#d4a843;text-decoration:underline}}
.scanner-hero .sh-links .sh-dim{{color:#6a7689}}
@media (max-width:820px){{
  .scanner-hero{{padding:20px 16px 18px}}
  .scanner-hero .sh-proof{{grid-template-columns:repeat(2,1fr)}}
  .scanner-hero h1{{font-size:1.35em}}
  .scanner-hero .sh-sub{{font-size:.9em}}
}}

/* PICKS ALERT BAR */
.picks-bar{{background:linear-gradient(90deg,#1a3a1a,#162d16);border-bottom:1px solid #2ea04344;
  padding:9px 20px;display:flex;align-items:center;gap:10px;font-size:.83em;flex-wrap:wrap}}
.picks-bar strong{{color:var(--green)}}
.picks-bar-cta{{background:var(--green);color:#0d1117;padding:4px 14px;border-radius:20px;
  font-weight:700;font-size:.85em;white-space:nowrap}}
.picks-bar-close{{background:none;border:none;color:var(--muted);cursor:pointer;
  margin-left:auto;font-size:1.1em;padding:0 4px}}
.winner-badge{{display:inline-flex;align-items:center;gap:5px;background:#1a2e1a;
  border:1px solid #2ea04355;border-radius:20px;padding:3px 12px;font-size:.78em;
  color:var(--green);font-weight:700;margin-left:6px}}

/* EDGE PRO GATE */
.edge-gate-wrap{{margin-top:6px;margin-bottom:18px;padding:22px;border:1px solid var(--border);
  border-radius:14px;background:linear-gradient(135deg,rgba(212,168,67,.05),rgba(6,182,212,.03))}}
.edge-gate-head h2{{margin:0 0 6px;font-size:1.25em;color:var(--text);display:flex;align-items:center;gap:10px}}
.edge-pro-chip{{font-size:.55em;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
  background:linear-gradient(90deg,#d4a843,#c2912e);color:#0d1117;padding:4px 10px;
  border-radius:6px;vertical-align:middle}}
.edge-gate-head .section-sub{{margin:0 0 16px;font-size:.84em;color:var(--muted);line-height:1.55}}
.edge-free-teaser{{position:relative;min-height:220px}}
.edge-teaser-blur{{filter:blur(6px) saturate(.6);opacity:.55;pointer-events:none;user-select:none}}
.edge-teaser-blur table{{width:100%;border-collapse:collapse}}
.edge-teaser-blur th,.edge-teaser-blur td{{padding:7px 9px;border-bottom:1px solid var(--border);
  font-size:.82em;text-align:left}}
.edge-teaser-card{{position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:10px;text-align:center;
  background:radial-gradient(ellipse at center,rgba(13,17,23,.92) 0%,rgba(13,17,23,.75) 70%,transparent 100%);
  padding:24px}}
.edge-teaser-lock{{font-size:2em;margin-bottom:4px;filter:drop-shadow(0 0 12px rgba(212,168,67,.3))}}
.edge-teaser-card h3{{margin:0;font-size:1.15em;color:var(--text);font-weight:800}}
.edge-teaser-card p{{margin:2px 0;font-size:.88em;color:var(--muted);line-height:1.5;max-width:460px}}
.edge-teaser-hint{{font-size:.78em !important;color:var(--dim) !important;font-style:italic}}
.edge-unlock-btn{{background:linear-gradient(135deg,#d4a843,#c2912e);color:#0d1117;
  border:none;border-radius:8px;padding:10px 22px;font-weight:800;font-size:.95em;
  cursor:pointer;margin-top:10px;letter-spacing:.01em;transition:transform .15s}}
.edge-unlock-btn:hover{{transform:translateY(-1px);box-shadow:0 4px 12px rgba(212,168,67,.4)}}
.edge-teaser-fine{{font-size:.76em;color:var(--muted);margin-top:6px}}
.edge-teaser-fine a{{color:var(--cyan);text-decoration:underline}}
.edge-pro-only{{display:none}}
body[data-tier="pro"] .edge-free-teaser,
body[data-tier="admin"] .edge-free-teaser,
body[data-tier="reader"] .edge-free-teaser{{display:none}}
body[data-tier="pro"] .edge-pro-only,
body[data-tier="admin"] .edge-pro-only{{display:block}}
body[data-tier="admin"]::before{{content:"⚡ ADMIN";position:fixed;top:6px;left:6px;
  right:auto;bottom:auto;inset:auto;width:auto;height:auto;
  background:#d4a843;background-image:none;color:#0d1117;padding:2px 8px;border-radius:4px;
  font-size:.65em;font-weight:800;letter-spacing:.05em;z-index:10000;opacity:1;
  font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif}}
.edge-billing-link{{display:none;position:fixed;bottom:14px;right:14px;z-index:9998;
  background:#161b22;border:1px solid #30363d;color:var(--muted);padding:8px 14px;
  border-radius:20px;font-size:.76em;font-weight:600;text-decoration:none;
  box-shadow:0 4px 14px rgba(0,0,0,.35);transition:color .15s,border-color .15s}}
.edge-billing-link:hover{{color:var(--cyan);border-color:var(--cyan)}}
body[data-tier="pro"] .edge-billing-link,
body[data-tier="reader"] .edge-billing-link{{display:inline-block}}
.edge-pro-footnote{{font-size:.78em;color:var(--muted);margin-top:10px;
  padding-top:10px;border-top:1px dashed var(--border)}}

/* EDGE UNLOCK POPUP */
.edge-unlock-popup{{position:fixed;inset:0;background:rgba(13,17,23,.85);z-index:10000;
  display:none;align-items:center;justify-content:center;padding:20px}}
.edge-unlock-popup.visible{{display:flex}}
.edge-unlock-panel{{background:#161b22;border:1px solid var(--border);border-radius:14px;
  padding:28px;max-width:440px;width:100%;position:relative}}
.edge-unlock-panel h3{{margin:0 0 8px;color:var(--text);font-size:1.25em}}
.edge-unlock-panel p{{margin:0 0 16px;color:var(--muted);font-size:.88em;line-height:1.55}}
.edge-unlock-close{{position:absolute;top:12px;right:14px;background:none;border:none;
  color:var(--muted);font-size:1.3em;cursor:pointer}}
.edge-unlock-form{{display:flex;gap:8px}}
.edge-unlock-input{{flex:1;background:#0d1117;border:1px solid var(--border);border-radius:8px;
  padding:10px 12px;color:var(--text);font-size:.95em}}
.edge-unlock-input:focus{{outline:none;border-color:#d4a843}}
.edge-unlock-submit{{background:linear-gradient(135deg,#d4a843,#c2912e);color:#0d1117;
  border:none;border-radius:8px;padding:10px 18px;font-weight:800;cursor:pointer}}
.edge-unlock-msg{{margin-top:14px;font-size:.85em;min-height:1.4em}}
.edge-unlock-msg.ok{{color:var(--green)}}
.edge-unlock-msg.err{{color:#f85149}}
.edge-unlock-paste{{margin-top:18px;padding-top:16px;border-top:1px dashed var(--border)}}
.edge-unlock-paste summary{{cursor:pointer;color:var(--cyan);font-size:.83em;
  font-weight:600;list-style:none;user-select:none}}
.edge-unlock-paste summary::-webkit-details-marker{{display:none}}
.edge-unlock-paste summary::before{{content:"▸ ";color:var(--muted);transition:transform .2s}}
.edge-unlock-paste[open] summary::before{{content:"▾ "}}
.edge-unlock-paste p{{margin:10px 0 10px;font-size:.8em;color:var(--muted);line-height:1.5}}
.edge-unlock-paste-input{{width:100%;box-sizing:border-box;background:#0d1117;
  border:1px solid var(--border);border-radius:8px;padding:10px 12px;
  color:var(--text);font-size:.85em;font-family:ui-monospace,SFMono-Regular,monospace;
  margin-bottom:8px}}
.edge-unlock-paste-input:focus{{outline:none;border-color:#d4a843}}
.edge-unlock-paste-btn{{width:100%;background:#2ea043;color:#0d1117;border:none;
  border-radius:8px;padding:10px 14px;font-weight:700;cursor:pointer;font-size:.9em}}
.edge-unlock-paste-btn:hover{{filter:brightness(1.1)}}

/* EDGE TOAST (unlock success) */
.edge-toast{{position:fixed;top:18px;left:50%;transform:translateX(-50%) translateY(-60px);
  background:#1a2e1a;border:1px solid #2ea04377;color:var(--green);padding:10px 18px;
  border-radius:24px;font-weight:700;font-size:.9em;z-index:10001;opacity:0;
  transition:transform .4s,opacity .4s;pointer-events:none}}
.edge-toast.visible{{transform:translateX(-50%) translateY(0);opacity:1}}

/* SUBSCRIBE POPUP */
.sub-popup{{position:fixed;bottom:24px;right:24px;z-index:9999;
  background:#161b22;border:1px solid #30363d;border-radius:12px;
  padding:20px 22px 16px;width:300px;box-shadow:0 8px 32px #0009;
  transform:translateY(120px);opacity:0;transition:transform .4s cubic-bezier(.2,.9,.3,1),opacity .4s ease;
  pointer-events:none}}
.sub-popup.visible{{transform:translateY(0);opacity:1;pointer-events:all}}
.sub-popup-close{{position:absolute;top:10px;right:12px;background:none;border:none;
  color:var(--muted);font-size:1.1em;cursor:pointer;line-height:1;padding:2px 5px}}
.sub-popup-close:hover{{color:var(--text)}}
.sub-popup h4{{margin:0 0 4px;font-size:.95em;color:var(--text);font-weight:700}}
.sub-popup p{{margin:0 0 12px;font-size:.76em;color:var(--muted);line-height:1.4}}
.sub-popup-form{{display:flex;gap:6px}}
.sub-popup-input{{flex:1;background:#0d1117;border:1px solid var(--border);border-radius:6px;
  padding:9px 10px;color:#fff;font-size:.82em;outline:none;min-width:0;transition:border-color .2s}}
.sub-popup-input:focus{{border-color:var(--green)}}
.sub-popup-input::placeholder{{color:var(--muted)}}
.sub-popup-btn{{background:var(--green);color:#000;border:none;border-radius:6px;
  padding:9px 13px;font-size:.82em;font-weight:700;cursor:pointer;white-space:nowrap;transition:opacity .2s}}
.sub-popup-btn:hover{{opacity:.85}}
.sub-popup-fine{{font-size:.68em;color:var(--muted);margin-top:7px;text-align:center}}
.sub-popup-success{{display:none;text-align:center;padding:6px 0}}
.sub-popup-success span{{font-size:1.6em}}
.sub-popup-success p{{color:var(--green);font-weight:700;margin:6px 0 2px;font-size:.9em}}
.sub-popup-success small{{color:var(--muted);font-size:.75em}}

/* HERO INLINE CAPTURE */
.hero-capture{{max-width:440px;margin:18px auto 0}}
.hero-capture-form{{display:flex;gap:8px}}
.hero-email{{background:#161b22;border:1px solid var(--border);border-radius:6px;
  padding:11px 14px;color:#fff;font-size:.92em;outline:none;flex:1;min-width:0;
  transition:border-color .2s}}
.hero-email:focus{{border-color:var(--green)}}
.hero-email::placeholder{{color:var(--muted)}}
.hero-capture-fine{{font-size:.7em;color:var(--muted);text-align:center;margin-top:5px}}

/* STREAK + VIEWER BADGES */
.hero-social{{display:flex;align-items:center;justify-content:center;gap:10px;
  flex-wrap:wrap;margin-top:10px}}
.streak-badge{{display:none;align-items:center;gap:5px;background:#2d1f0e;
  border:1px solid #f0883e44;border-radius:20px;padding:3px 12px;
  font-size:.78em;color:var(--orange);font-weight:700}}
.viewer-badge{{display:inline-flex;align-items:center;gap:5px;background:var(--surface);
  border:1px solid var(--border);border-radius:20px;padding:3px 12px;font-size:.78em;color:var(--muted)}}
.viewer-badge .live-dot{{width:6px;height:6px}}

/* MARKET STATE BANNER */
.market-state{{display:inline-flex;align-items:center;gap:6px;font-size:.78em;
  padding:3px 12px;border-radius:20px;border:1px solid;font-weight:600}}
.market-open{{background:#1a2e1a;border-color:#2ea04355;color:var(--green)}}
.market-pre{{background:#1f2a0e;border-color:#d2992255;color:var(--yellow)}}
.market-closed{{background:var(--surface);border-color:var(--border);color:var(--muted)}}

/* SCORE ANIMATION */
@keyframes scorePop{{0%{{transform:scale(1)}}50%{{transform:scale(1.15)}}100%{{transform:scale(1)}}}}
.score-animate{{animation:scorePop .4s ease 1.1s both}}

/* EMAIL CAPTURE */
.email-capture-section{{background:linear-gradient(135deg,#0f1e2e 0%,#0d1117 100%);
  border:1px solid #1f6feb44;border-radius:12px;padding:40px 32px;margin:32px 0}}
.capture-card{{display:flex;gap:40px;align-items:center;flex-wrap:wrap}}
.capture-left{{flex:1;min-width:220px}}
.capture-left h3{{font-size:1.4em;margin:0 0 8px;color:#fff}}
.capture-left p{{color:var(--muted);margin:0 0 16px;font-size:.92em}}
.capture-proof{{display:flex;flex-wrap:wrap;gap:8px}}
.proof-item{{background:var(--surface);border:1px solid var(--border);
  border-radius:20px;padding:4px 12px;font-size:.78em;color:var(--muted)}}
.capture-right{{flex:1;min-width:220px}}
.capture-form{{display:flex;flex-direction:column;gap:10px}}
.email-input{{background:#161b22;border:1px solid var(--border);border-radius:6px;
  padding:12px 16px;color:#fff;font-size:.95em;outline:none;transition:border-color .2s}}
.email-input:focus{{border-color:var(--green)}}
.email-input::placeholder{{color:var(--muted)}}
.capture-btn{{background:var(--green);color:#0d1117;border:none;border-radius:6px;
  padding:13px 20px;font-weight:700;font-size:.95em;cursor:pointer;transition:opacity .2s}}
.capture-btn:hover{{opacity:.88}}
.capture-fine{{font-size:.73em;color:var(--muted);text-align:center}}
.live-price-cell{{font-weight:700;font-variant-numeric:tabular-nums;min-width:72px;display:inline-flex;flex-direction:column;gap:3px;align-items:flex-start;line-height:1.05}}
.live-price-main{{font-weight:700;color:var(--text)}}
.live-price-change{{display:inline-flex;align-items:center;gap:4px;padding:2px 7px;border-radius:999px;
  font-size:.72em;letter-spacing:.01em;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.04);color:var(--muted)}}
.live-price-change.up{{color:#3fb950;border-color:#3fb95033;background:#0f1e16}}
.live-price-change.dn{{color:#f78166;border-color:#f7816633;background:#231514}}
.live-price-change.flat{{color:#8b949e;border-color:#30363d;background:#161b22}}
.sc-live-price{{align-items:flex-end;text-align:right}}

/* ── CASINO SCANNER DESIGN ─────────────────────────────────────────── */
.scanner-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin:20px 0}}
.gap-burn-shell{{position:relative;margin-top:18px;padding:18px;border-radius:28px;overflow:hidden;isolation:isolate;
  background:linear-gradient(180deg,#0b1111,#0a0a0a);
  border:1px solid rgba(255,255,255,.10);
  box-shadow:0 28px 72px rgba(0,0,0,.42),inset 0 0 42px rgba(16,185,129,.04)}}
.gap-burn-shell::before{{content:'';position:absolute;inset:0;pointer-events:none;
  background:
    radial-gradient(circle at 18% 22%,rgba(16,185,129,.12),transparent 36%),
    radial-gradient(circle at 82% 18%,rgba(16,185,129,.08),transparent 28%);
  opacity:.72}}
.gap-burn-content{{position:relative;z-index:1}}
.sparkles-core{{position:absolute;inset:0;pointer-events:none;z-index:0;overflow:hidden}}
.sparkles-core canvas{{display:block;width:100%;height:100%;opacity:.76;mix-blend-mode:screen}}
.scanner-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;display:flex;flex-direction:column;gap:10px;transition:all .2s ease;position:relative;overflow:hidden}}
.scanner-card:hover{{border-color:var(--blue);transform:translateY(-3px);box-shadow:0 8px 24px rgba(88,166,255,.15)}}
.scanner-card.top-card{{border-color:#2ea04366;box-shadow:0 0 20px rgba(63,185,80,.1)}}
.scanner-card.live-up{{animation:card-flash-up .8s ease}}
.scanner-card.live-dn{{animation:card-flash-dn .8s ease}}
.scanner-card::after{{content:'';position:absolute;left:14px;right:14px;top:-36%;height:34%;pointer-events:none;
  background:linear-gradient(180deg,rgba(114,229,255,0),rgba(114,229,255,.34),rgba(114,229,255,0));
  opacity:0;filter:blur(10px)}}
.scanner-card.is-reifying::after{{animation:scannerSweep .72s cubic-bezier(.14,.79,.2,1) both}}
@keyframes card-flash-up{{0%{{border-color:#3fb950;box-shadow:0 0 20px rgba(63,185,80,.4)}}100%{{border-color:var(--border);box-shadow:none}}}}
@keyframes card-flash-dn{{0%{{border-color:#f78166;box-shadow:0 0 20px rgba(247,129,102,.4)}}100%{{border-color:var(--border);box-shadow:none}}}}
@keyframes scannerSweep{{0%{{transform:translateY(-24%);opacity:0}}18%{{opacity:1}}100%{{transform:translateY(360%);opacity:0}}}}
.sc-top{{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}}
.sc-ticker{{font-size:1.4em;font-weight:900;letter-spacing:-.02em;max-width:100%;min-width:0;overflow:hidden;text-overflow:ellipsis}}
.sc-ticker strong{{display:inline-block;max-width:100%;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.sc-ticker strong.ticker-glitch-active{{animation:tickerGlitch .22s steps(2,end) 1}}
.sc-ticker a{{color:var(--text);text-decoration:none}}
.sc-ticker a:hover{{color:var(--blue)}}
.sc-badges{{display:flex;gap:5px;flex-wrap:wrap;align-items:center}}
.sc-score-circle{{width:56px;height:56px;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto;font-size:1.6em;font-weight:900;border:2px solid}}
.sc-score-circle.high{{background:#3fb95011;color:#3fb950;border-color:#3fb950;box-shadow:0 0 16px rgba(63,185,80,.3)}}
.sc-score-circle.medium{{background:#d2992211;color:#d29922;border-color:#d29922;box-shadow:0 0 16px rgba(210,153,34,.2)}}
.sc-score-circle.low{{background:#f0883e11;color:#f0883e;border-color:#f0883e}}
.scanner-card.reify-focus .sc-score-circle{{box-shadow:0 0 20px var(--intel-accent-soft,rgba(114,229,255,.18)),0 0 0 1px rgba(255,255,255,.04) inset;transform:scale(1.03)}}
.sc-score-label{{font-size:.65em;color:var(--muted);margin-top:4px;text-align:center;text-transform:uppercase;letter-spacing:.05em}}
.sc-meta{{display:flex;flex-direction:column;gap:4px}}
.sc-catalyst{{background:var(--surface2);color:var(--muted);padding:4px 8px;border-radius:4px;font-size:.75em;line-height:1.4}}
.sc-momentum{{display:flex;align-items:center;gap:8px}}
.sc-momentum-label{{font-size:.7em;color:var(--muted);min-width:38px}}
.sc-momentum-bar{{flex:1;background:var(--surface2);border-radius:3px;height:6px;overflow:hidden}}
.sc-momentum-fill{{height:100%;border-radius:3px;transition:width .8s ease}}
.sc-momentum-fill.up{{background:var(--green)}}
.sc-momentum-fill.down{{background:var(--red)}}
.sc-sparkline{{width:100%}}
.sc-live-row{{display:flex;align-items:center;justify-content:space-between;background:var(--surface2);border-radius:6px;padding:6px 10px}}
.sc-live-price{{font-size:1.05em;font-weight:800;font-variant-numeric:tabular-nums;min-width:60px;text-align:right}}
.sc-sec-link{{text-align:center;font-size:.82em;margin-top:2px}}
.status-badge{{display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:10px;font-size:.68em;font-weight:700;border:1px solid;white-space:nowrap}}
.status-badge.hot{{background:#2d1f0e;color:var(--orange);border-color:#f0883e44;animation:pulse-hot 2s ease-in-out infinite}}
.scanner-card.reify-focus .status-badge.hot{{animation:pulse-hot 1.1s ease-in-out infinite}}
@keyframes tickerGlitch{{0%{{transform:translateX(0);text-shadow:2px 0 #72e5ff,-2px 0 #ff6b8a;filter:brightness(1.2)}}50%{{transform:translateX(1px);text-shadow:-2px 0 #72e5ff,2px 0 #ff6b8a}}100%{{transform:translateX(0);text-shadow:none;filter:none}}}}
.status-badge.moving{{background:#1f2a3c;color:var(--blue);border-color:#58a6ff44}}
.status-badge.coiling{{background:#2d2200;color:var(--yellow);border-color:#d2992244}}
.status-badge.squeezing{{background:#1a2e1a;color:var(--green);border-color:#2ea04344;animation:pulse-sq 1.8s ease-in-out infinite}}
@keyframes pulse-hot{{0%,100%{{box-shadow:0 0 0 0 rgba(240,136,62,0)}}50%{{box-shadow:0 0 8px 2px rgba(240,136,62,.15)}}}}
@keyframes pulse-sq{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.06)}}}}
@media(max-width:640px){{.scanner-grid{{grid-template-columns:1fr}}}}

/* ── Premium gate ──────────────────────────────────────────────── */
.premium-blur-wrap{{position:relative;margin:20px 0}}
.premium-blur-content{{filter:blur(8px);pointer-events:none;user-select:none;opacity:.5}}
.premium-gate-overlay{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:10;
  background:linear-gradient(180deg,transparent 0%,rgba(5,6,11,.92) 40%)}}
.premium-gate-content{{text-align:center;padding:40px 24px;max-width:480px}}
.premium-gate-lock{{font-size:3rem;margin-bottom:12px}}
.premium-gate-title{{font-size:1.3rem;font-weight:700;color:var(--text);margin-bottom:8px}}
.premium-gate-sub{{color:var(--muted);font-size:.92rem;margin-bottom:20px;line-height:1.5}}
.premium-gate-buttons{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-bottom:14px}}
.premium-gate-btn{{padding:12px 28px;border-radius:10px;font-weight:700;font-size:.95rem;text-decoration:none;
  transition:transform .15s ease,box-shadow .15s ease}}
.premium-gate-btn:hover{{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.4)}}
.premium-gate-btn.reader{{background:var(--blue);color:#000}}
.premium-gate-btn.pro{{background:var(--yellow);color:#000}}
.premium-gate-proof{{color:var(--muted);font-size:.8rem}}
.premium-blur-row{{filter:blur(5px);pointer-events:none;user-select:none;opacity:.45}}
.premium-gate-row td{{padding:0!important}}
/* Unblur paid + admin tiers across the legacy premium gate as well */
body[data-tier="pro"] .premium-blur-content,
body[data-tier="admin"] .premium-blur-content,
body[data-tier="reader"] .premium-blur-content{{filter:none;pointer-events:auto;user-select:auto;opacity:1}}
body[data-tier="pro"] .premium-blur-row,
body[data-tier="admin"] .premium-blur-row,
body[data-tier="reader"] .premium-blur-row{{filter:none;pointer-events:auto;user-select:auto;opacity:1}}
body[data-tier="pro"] .premium-gate-overlay,
body[data-tier="admin"] .premium-gate-overlay,
body[data-tier="reader"] .premium-gate-overlay,
body[data-tier="pro"] .premium-gate-row,
body[data-tier="admin"] .premium-gate-row,
body[data-tier="reader"] .premium-gate-row,
body[data-tier="pro"] .premium-gate-inline,
body[data-tier="admin"] .premium-gate-inline,
body[data-tier="reader"] .premium-gate-inline,
body[data-tier="pro"] .premium-sticky-bar,
body[data-tier="admin"] .premium-sticky-bar,
body[data-tier="reader"] .premium-sticky-bar{{display:none!important}}
.premium-gate-inline{{text-align:center;padding:16px 12px;background:linear-gradient(180deg,rgba(5,6,11,.7),rgba(5,6,11,.95));
  border-radius:8px;margin:8px 0;font-size:.95rem;color:var(--muted)}}
.premium-gate-inline a{{color:var(--yellow);font-weight:700;text-decoration:none;margin-left:4px}}
.premium-gate-inline a:hover{{text-decoration:underline}}

/* ── Sticky premium bar ──────────────────────────────────────── */
.premium-sticky-bar{{position:fixed;bottom:0;left:0;right:0;z-index:997;
  background:linear-gradient(90deg,#0d1117f0 0%,#11151df0 100%);
  border-top:1px solid var(--gold);backdrop-filter:blur(12px);
  transform:translateY(100%);transition:transform .35s cubic-bezier(.2,.8,.2,1);
  box-shadow:0 -8px 32px rgba(0,0,0,.5)}}
.premium-sticky-bar.visible{{transform:translateY(0)}}
.premium-sticky-inner{{display:flex;align-items:center;justify-content:center;gap:16px;
  padding:12px 20px;max-width:1200px;margin:0 auto;flex-wrap:wrap}}
.premium-sticky-text{{color:var(--text);font-size:.9rem}}
.premium-sticky-btns{{display:flex;gap:8px}}
.premium-sticky-btn{{padding:8px 20px;border-radius:8px;font-weight:700;font-size:.85rem;
  text-decoration:none;transition:transform .12s ease}}
.premium-sticky-btn:hover{{transform:translateY(-1px)}}
.premium-sticky-btn.reader{{background:var(--blue);color:#000}}
.premium-sticky-btn.pro{{background:var(--yellow);color:#000}}
.premium-sticky-close{{background:none;border:none;color:var(--muted);font-size:1.2rem;cursor:pointer;
  padding:4px 8px;margin-left:8px}}
.premium-sticky-close:hover{{color:var(--text)}}
@media(max-width:640px){{
  .premium-sticky-text{{font-size:.78rem;text-align:center;width:100%}}
  .premium-sticky-btns{{width:100%;justify-content:center}}
}}

/* UI UX Pro Max tactical override */
:root{{--bg:#05060b;--surface:#11141d;--surface2:#181c27;--border:rgba(215,180,106,.18);--text:#f6efe2;
  --muted:#9ea8ba;--green:#7fe8b3;--yellow:#e6bd6b;--orange:#ffbf69;--red:#ff8b86;--blue:#72e5ff;--purple:#d59cff;
  --brass:#d7b46a}}
body{{font-family:'Space Grotesk','Segoe UI',sans-serif;
  --posture-tint-a:transparent;--posture-tint-b:transparent;--posture-grid:rgba(114,229,255,.03);
  background:
    radial-gradient(ellipse at 18% 30%, var(--posture-tint-a), transparent 55%),
    radial-gradient(ellipse at 82% 70%, var(--posture-tint-b), transparent 55%),
    radial-gradient(circle at 12% 16%, rgba(42,212,197,.09), transparent 22%),
    radial-gradient(circle at 82% 10%, rgba(213,156,255,.10), transparent 22%),
    radial-gradient(circle at 50% 118%, rgba(215,180,106,.16), transparent 26%),
    linear-gradient(180deg,#05060b 0%,#0b0d14 42%,#090b12 100%);
  background-attachment:fixed;
  color:var(--text);
  transition:background .6s ease-out}}
body[data-posture="bullish"]{{--posture-tint-a:rgba(16,185,129,.10);--posture-tint-b:rgba(16,185,129,.07);--posture-grid:rgba(127,232,179,.045)}}
body[data-posture="bearish"]{{--posture-tint-a:rgba(244,63,94,.10);--posture-tint-b:rgba(244,63,94,.07);--posture-grid:rgba(255,139,134,.045)}}
body::before{{content:'';position:fixed;inset:0;pointer-events:none;
  background-image:linear-gradient(var(--posture-grid) 1px,transparent 1px),linear-gradient(90deg,var(--posture-grid) 1px,transparent 1px);
  background-size:48px 48px;opacity:.34;transition:background-image .6s ease-out}}
body::after{{content:'';position:fixed;inset:0;pointer-events:none;
  background:linear-gradient(180deg,rgba(255,255,255,.03) 0%,transparent 24%,transparent 78%,rgba(255,255,255,.02) 100%);opacity:.16}}
@media (prefers-reduced-motion:reduce){{body{{transition:none}}body::before{{transition:none}}}}
a{{color:var(--blue)}}
.nav{{max-width:1180px;margin:12px auto 0;background:rgba(10,12,18,.76);border:1px solid rgba(215,180,106,.14);
  border-radius:20px;padding:0 18px;box-shadow:0 18px 44px rgba(0,0,0,.28),inset 0 1px 0 rgba(255,255,255,.03)}}
.nav-brand{{font-family:'IBM Plex Mono',monospace;letter-spacing:.18em;text-transform:uppercase;border-right:none;margin-right:0;padding-right:10px}}
.nav-link{{font-family:'IBM Plex Mono',monospace;font-size:.72em;letter-spacing:.12em;text-transform:uppercase}}
.nav-cta{{background:linear-gradient(135deg,var(--brass),#f1ce88);color:#161109;border-radius:999px;box-shadow:0 10px 22px rgba(215,180,106,.18)}}
/* Suite mega-nav */
.suite-trigger{{position:relative;cursor:pointer;color:var(--brass);font-weight:700}}
.suite-trigger:hover{{color:#f1ce88}}
.suite-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:998;backdrop-filter:blur(2px)}}
.suite-overlay.open{{display:block}}
.suite-mega{{display:none;position:fixed;top:0;right:0;width:min(520px,92vw);height:100vh;
  background:rgba(10,12,18,.97);border-left:1px solid rgba(215,180,106,.18);z-index:999;
  overflow-y:auto;overscroll-behavior:contain;
  transform:translateX(100%);transition:transform .28s cubic-bezier(.16,1,.3,1)}}
.suite-mega.open{{display:block;transform:translateX(0)}}
.suite-mega-head{{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;
  padding:16px 20px;background:rgba(10,12,18,.95);border-bottom:1px solid rgba(215,180,106,.12);
  backdrop-filter:blur(8px)}}
.suite-mega-head h3{{font-family:'IBM Plex Mono',monospace;font-size:.82rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--brass);margin:0}}
.suite-close{{background:none;border:1px solid rgba(255,255,255,.12);color:var(--text);width:28px;height:28px;
  border-radius:6px;cursor:pointer;font-size:.9rem;display:flex;align-items:center;justify-content:center;
  transition:all .15s}}
.suite-close:hover{{border-color:var(--brass);color:var(--brass)}}
.suite-mega-body{{padding:8px 20px 32px}}
.suite-cat{{margin-bottom:16px}}
.suite-cat-head{{font-family:'IBM Plex Mono',monospace;font-size:.62rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);padding:6px 0 4px;border-bottom:1px solid rgba(255,255,255,.06);
  margin-bottom:4px;position:sticky;top:56px;background:rgba(10,12,18,.95);z-index:1}}
.suite-cat-head .cat-dot{{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px;vertical-align:middle}}
.suite-links{{display:grid;grid-template-columns:1fr 1fr;gap:2px}}
.suite-link{{display:block;padding:6px 8px;border-radius:6px;font-size:.74rem;color:var(--dim);
  transition:all .12s;text-decoration:none;line-height:1.4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.suite-link:hover{{background:rgba(215,180,106,.08);color:var(--text);text-decoration:none}}
.suite-link:active{{background:rgba(215,180,106,.14)}}
.suite-count{{font-family:'IBM Plex Mono',monospace;font-size:.6rem;color:var(--muted);padding:12px 20px;
  text-align:center;border-top:1px solid rgba(255,255,255,.06)}}
@media(max-width:480px){{
  .suite-links{{grid-template-columns:1fr}}
  .suite-mega{{width:100vw}}
}}
.tools-bar{{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;padding:10px 16px 6px;
  background:rgba(10,12,18,.62);border-bottom:1px solid rgba(215,180,106,.10)}}
.tool-chip{{display:inline-flex;align-items:center;gap:5px;padding:5px 14px;
  background:rgba(215,180,106,.08);border:1px solid rgba(215,180,106,.18);border-radius:999px;
  font-family:'IBM Plex Mono',monospace;font-size:.68rem;letter-spacing:.06em;
  color:var(--muted);text-decoration:none!important;transition:all .2s ease}}
.tool-chip:hover{{background:rgba(215,180,106,.18);color:var(--brass);border-color:rgba(215,180,106,.38);
  box-shadow:0 4px 14px rgba(215,180,106,.12);transform:translateY(-1px)}}
.tc-icon{{font-size:.82rem}}
@media(max-width:640px){{.tools-bar{{gap:6px;padding:8px 10px 4px}}.tool-chip{{font-size:.62rem;padding:4px 10px}}}}
.hero{{padding:56px 20px 34px;background:transparent;position:relative}}
.hero::before{{content:'';position:absolute;inset:8px 14px 0;border-radius:34px;
  background:linear-gradient(180deg,rgba(18,20,29,.84) 0%,rgba(10,12,18,.70) 100%);
  border:1px solid rgba(215,180,106,.14);box-shadow:0 20px 52px rgba(0,0,0,.32);z-index:-1}}
.hero::after{{content:'';position:absolute;inset:0 0 auto auto;width:340px;height:340px;border-radius:50%;
  background:radial-gradient(circle,rgba(114,229,255,.16) 0%,rgba(213,156,255,.10) 42%,transparent 70%);filter:blur(12px);z-index:-1}}
.hero-shell{{max-width:1180px;margin:0 auto;display:grid;grid-template-columns:minmax(0,.92fr) minmax(460px,1.08fr);gap:28px;align-items:stretch}}
.hero-command{{display:flex;flex-direction:column;align-items:flex-start;gap:18px;padding:6px 6px 10px}}
.hero-target-shell{{display:flex;align-items:flex-start}}
.hero h1{{max-width:660px;font-size:clamp(2.5rem,6vw,5rem);line-height:.94;letter-spacing:-.05em;text-align:left;margin:0}}
.hero h1 span{{background:linear-gradient(135deg,var(--brass) 0%,#f8d79a 34%,var(--blue) 100%);-webkit-background-clip:text;background-clip:text;color:transparent}}
.hero-sub{{max-width:640px;font-size:1.02em;line-height:1.82;text-align:left;margin:0}}
.hero-eyebrow{{background:rgba(16,18,27,.82);border:1px solid rgba(215,180,106,.18);border-radius:999px;padding:6px 14px;
  font-family:'IBM Plex Mono',monospace;font-size:.72em;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}
.hero-titleblock{{display:flex;flex-direction:column;gap:14px}}
.hero-ops-grid{{width:100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
.hero-ops-card{{position:relative;padding:14px 16px 15px;border-radius:18px;background:linear-gradient(180deg,rgba(12,14,22,.86),rgba(7,9,14,.64));
  border:1px solid rgba(114,229,255,.12);box-shadow:0 20px 44px rgba(0,0,0,.18),inset 0 1px 0 rgba(255,255,255,.04);overflow:hidden}}
.hero-ops-card::before{{content:'';position:absolute;inset:0;background:
  linear-gradient(90deg,rgba(114,229,255,.14),transparent 30%),
  radial-gradient(circle at 85% 18%,rgba(215,180,106,.16),transparent 32%);
  opacity:.42;pointer-events:none}}
.hero-ops-label{{display:block;font-family:'IBM Plex Mono',monospace;font-size:.62rem;letter-spacing:.22em;text-transform:uppercase;color:#90a4ba}}
.hero-ops-value{{display:block;margin-top:9px;font-size:1rem;font-weight:700;letter-spacing:-.02em;color:#f6efe2}}
.hero-capture{{max-width:560px;width:100%;margin-top:4px;padding:14px;background:linear-gradient(180deg,rgba(18,20,28,.74),rgba(12,14,18,.54));
  border:1px solid rgba(114,229,255,.14);border-radius:22px;box-shadow:0 18px 40px rgba(0,0,0,.24)}}
.hero-email{{background:rgba(9,11,17,.84);border-radius:14px;border:1px solid rgba(255,255,255,.08);padding:13px 15px}}
.hero-capture-form .btn-green{{border-radius:14px;padding:13px 18px;background:linear-gradient(135deg,var(--brass),#f1ce88);color:#161109}}
.hero-capture-fine{{font-family:'IBM Plex Mono',monospace;letter-spacing:.08em;text-transform:uppercase}}
.viewer-badge,.market-state,.streak-badge{{background:rgba(17,20,29,.78);border:1px solid rgba(255,255,255,.08);color:var(--muted)}}
.hero-social{{justify-content:flex-start;margin-top:4px}}
.scroll-hint{{margin-top:10px;font-family:'IBM Plex Mono',monospace;font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;color:#93a4ba}}
.spotlight{{width:100%;max-width:none;background:linear-gradient(145deg,#121722,#0a0a0a);border:1px solid rgba(255,255,255,.10);
  border-radius:26px;box-shadow:0 22px 56px rgba(0,0,0,.38),0 0 18px rgba(114,229,255,.06);padding:24px 24px 20px;position:relative;overflow:hidden}}
.spotlight::before{{content:'';position:absolute;inset:0;background:
  linear-gradient(180deg,rgba(114,229,255,.06),transparent 18%),
  linear-gradient(90deg,transparent 0%,rgba(215,180,106,.12) 52%,transparent 100%);
  opacity:.44;pointer-events:none}}
.spotlight::after{{content:'';position:absolute;inset:14px;border-radius:20px;border:1px solid rgba(255,255,255,.05);pointer-events:none}}
.spotlight-label,.badge-form,.badge-cat,.badge-squeeze,.badge-insider,.section-tag,.status-badge,.freshness-badge{{font-family:'IBM Plex Mono',monospace;letter-spacing:.08em;text-transform:uppercase}}
.spotlight-dossier{{display:grid;grid-template-columns:minmax(170px,186px) minmax(0,1.35fr) 176px;gap:16px;align-items:stretch}}
.spotlight-dossier-balanced{{width:100%;max-width:64rem;margin:0 auto;grid-template-columns:1fr;gap:24px;align-items:center}}
.spotlight-rail{{position:relative;padding:14px 16px;border-radius:20px;background:linear-gradient(180deg,#11151d,#0a0a0a);border:1px solid rgba(255,255,255,.08);min-width:0;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}}
.spotlight-rail::before{{content:'';position:absolute;top:12px;left:12px;width:22px;height:22px;border-top:1px solid rgba(114,229,255,.25);border-left:1px solid rgba(114,229,255,.25);opacity:.75}}
.spotlight-rail::after{{content:'';position:absolute;right:12px;bottom:12px;width:22px;height:22px;border-right:1px solid rgba(215,180,106,.28);border-bottom:1px solid rgba(215,180,106,.28);opacity:.72}}
.spotlight-lockline{{font-family:'IBM Plex Mono',monospace;font-size:.62rem;letter-spacing:.22em;text-transform:uppercase;color:#8fd8ff}}
.spotlight-col-left{{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px}}
.spotlight-ticker{{margin-top:10px}}
.spotlight-col-left .spotlight-live{{justify-content:center}}
.spotlight-col-center{{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}}
.spotlight-thesis-kicker{{font-family:'IBM Plex Mono',monospace;font-size:.62rem;letter-spacing:.24em;text-transform:uppercase;color:#8ea3bc}}
.spotlight-thesis{{margin-top:10px;font-size:1.08rem;line-height:1.62;color:#f4ece0;max-width:none;width:100%}}
.spotlight-score{{display:flex;align-items:flex-end;justify-content:center;gap:10px;margin-top:16px;width:100%}}
.spotlight-score-k{{font-family:'IBM Plex Mono',monospace;font-size:.62rem;letter-spacing:.22em;text-transform:uppercase;color:#8ea3bc;padding-bottom:6px}}
.spotlight-score-v{{font-size:2.15rem;line-height:1;font-weight:800;letter-spacing:-.05em}}
.spotlight-score-tail{{font-family:'IBM Plex Mono',monospace;font-size:.7rem;letter-spacing:.18em;text-transform:uppercase;color:#8ea3bc;padding-bottom:8px}}
.spotlight-command-note{{margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,.06);font-size:.82rem;color:#9fb0c4;line-height:1.5;width:100%}}
/* 8-K Item chips */
.spotlight-items{{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;width:100%}}
.sp-item{{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:8px;background:rgba(114,229,255,.08);border:1px solid rgba(114,229,255,.22);font-size:.78rem;color:#d7e6f0;font-weight:500}}
.sp-item-k{{font-family:'IBM Plex Mono',monospace;font-size:.66rem;color:#72e5ff;letter-spacing:.06em;font-weight:700}}
/* Normalized gap-score bar */
.spotlight-score-normalized{{flex-wrap:wrap;align-items:center;gap:8px}}
.spotlight-score-max{{font-size:.95rem;color:#6b7a8d;font-weight:600;letter-spacing:-.02em;margin-left:3px}}
.spotlight-score-tier{{font-family:'IBM Plex Mono',monospace;font-size:.72rem;letter-spacing:.2em;text-transform:uppercase;font-weight:700;padding-bottom:8px}}
.spotlight-score-bar{{flex:1 1 100%;height:4px;border-radius:2px;background:rgba(255,255,255,.06);overflow:hidden;margin-top:4px}}
.spotlight-score-fill{{height:100%;border-radius:2px;transition:width .6s ease}}
/* Base-rate block */
.spotlight-baserate{{margin-top:16px;width:100%;padding:12px 14px;border-radius:12px;background:linear-gradient(180deg,rgba(63,185,80,.08),rgba(63,185,80,.02));border:1px solid rgba(63,185,80,.22)}}
.sp-br-kicker{{font-family:'IBM Plex Mono',monospace;font-size:.6rem;letter-spacing:.18em;text-transform:uppercase;color:#8ea3bc;margin-bottom:8px}}
.sp-br-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.sp-br-cell{{display:flex;flex-direction:column;gap:2px}}
.sp-br-v{{font-size:1.25rem;font-weight:800;letter-spacing:-.02em;color:#3fb950;font-feature-settings:"tnum" 1}}
.sp-br-k{{font-size:.72rem;color:#9fb0c4;letter-spacing:.02em}}
/* Trade frame */
.spotlight-tradeframe{{margin-top:12px;width:100%;padding:12px 14px;border-radius:12px;background:rgba(210,153,34,.05);border:1px solid rgba(210,153,34,.22)}}
.sp-tf-kicker{{font-family:'IBM Plex Mono',monospace;font-size:.6rem;letter-spacing:.16em;text-transform:uppercase;color:#d29922;margin-bottom:8px}}
.sp-tf-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;row-gap:10px}}
.sp-tf-cell{{display:flex;flex-direction:column;gap:2px;min-width:0}}
.sp-tf-k{{font-size:.68rem;color:#8ea3bc;letter-spacing:.06em;text-transform:uppercase}}
.sp-tf-v{{font-size:1.02rem;font-weight:700;color:#f4ece0;font-feature-settings:"tnum" 1;letter-spacing:-.01em}}
.sp-tf-stop .sp-tf-v{{color:#ff7b7b}}
.sp-tf-target .sp-tf-v{{color:#3fb950}}
@media (min-width:900px){{.sp-tf-row{{grid-template-columns:repeat(6,1fr)}}}}
/* Risk pill */
.badge-risk{{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:999px;font-size:.68rem;letter-spacing:.04em;font-weight:700;background:rgba(255,107,107,.12);border:1px solid rgba(255,107,107,.4);color:#ff9b9b}}
.spotlight-col-right{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}}
.sc-cerebro-link-hero{{min-height:48px;align-items:center}}
.spotlight-col-right .btn{{width:100%;max-width:240px;justify-content:center}}
.spotlight-sec-link{{margin-top:0}}
@media (min-width:768px){{
  .spotlight-dossier-balanced{{grid-template-columns:minmax(0,.95fr) minmax(0,1.7fr) minmax(0,.95fr);gap:32px}}
  .spotlight-col-left{{align-items:flex-start;text-align:left}}
  .spotlight-col-left .spotlight-live{{justify-content:flex-start}}
  .spotlight-col-center{{align-items:flex-start;text-align:left}}
  .spotlight-score{{justify-content:flex-start}}
  .spotlight-col-right{{align-items:flex-end;text-align:right}}
}}
.spotlight-footnote{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:14px;padding:12px 14px;border-radius:16px;
  background:#0d1016;border:1px solid rgba(255,255,255,.08);font-size:.8rem;color:#a4b3c4}}
.spotlight-footnote-kicker{{font-family:'IBM Plex Mono',monospace;font-size:.62rem;letter-spacing:.2em;text-transform:uppercase;color:#d7b46a}}
.spotlight-footnote-link{{margin-left:auto;font-family:'IBM Plex Mono',monospace;font-size:.74rem;letter-spacing:.18em;text-transform:uppercase}}
.section-head{{align-items:center;gap:10px;border-bottom:1px solid rgba(255,255,255,.08)}}
.section-tag{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);color:var(--muted);border-radius:999px;padding:5px 10px}}
.countdown-bar{{background:linear-gradient(180deg,#10141c,#0a0a0a);border:1px solid rgba(255,255,255,.10);border-radius:24px;
  box-shadow:0 22px 56px rgba(0,0,0,.34);padding:18px 20px}}
.freshness-badge{{background:rgba(114,229,255,.08);border:1px solid rgba(114,229,255,.18);color:var(--blue)}}
.freshness-strip{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:14px}}
.freshness-card{{background:#0f131b;border:1px solid rgba(255,255,255,.10);border-radius:18px;min-height:92px;display:flex;flex-direction:column;justify-content:center;gap:8px;padding:14px 16px;position:relative;overflow:hidden}}
.freshness-card::before{{content:'';position:absolute;left:0;top:14px;bottom:14px;width:2px;background:linear-gradient(180deg,rgba(114,229,255,.72),rgba(215,180,106,.18));opacity:.9}}
.freshness-kicker{{font-family:'IBM Plex Mono',monospace;letter-spacing:.1em;text-transform:uppercase}}
.freshness-value{{padding-left:8px}}
.tbl-wrap,table,.sector-card,.track-card,.pm-card,.cta-block,.email-capture-section,.sub-popup{{box-shadow:0 18px 42px rgba(0,0,0,.18)}}
.scanner-grid{{gap:18px}}
.scanner-card{{background:linear-gradient(180deg,#11151d,#0a0a0a);border:1px solid rgba(255,255,255,.10);border-radius:22px;
  padding:18px;box-shadow:0 20px 48px rgba(0,0,0,.32),inset 0 1px 0 rgba(255,255,255,.04);overflow:hidden}}
.scanner-card::before{{content:'';position:absolute;inset:0;border-radius:inherit;background:linear-gradient(135deg,rgba(114,229,255,.05),transparent 34%,rgba(215,180,106,.05) 100%);opacity:.12;pointer-events:none}}
.scanner-card:hover{{border-color:rgba(114,229,255,.24);transform:translateY(-1px);box-shadow:0 24px 56px rgba(0,0,0,.28),0 0 18px rgba(114,229,255,.06)}}
.sc-severity{{position:absolute;left:0;top:18px;bottom:18px;width:3px;border-radius:999px}}
.sc-severity-high{{background:linear-gradient(180deg,#7fe8b3,#72e5ff)}}
.sc-severity-medium{{background:linear-gradient(180deg,#e6bd6b,#d7b46a)}}
.sc-severity-low{{background:linear-gradient(180deg,#ffbf69,#ff8b86)}}
.sc-live-row{{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:14px}}
.sc-catalyst{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.05);border-radius:10px}}
.sc-command-shell{{position:relative}}
.sc-command-core{{display:grid;grid-template-columns:72px minmax(0,1fr);gap:14px;align-items:flex-start}}
.sc-primary{{display:flex;flex-direction:column;gap:10px}}
.sc-thesis-kicker{{font-family:'IBM Plex Mono',monospace;font-size:.58rem;letter-spacing:.22em;text-transform:uppercase;color:#8ea3bc}}
.sc-thesis{{font-size:.92rem;line-height:1.55;color:#f4ece0}}
.sc-meta{{display:flex;flex-direction:column;gap:6px}}
.sc-bottom{{display:flex;flex-direction:column;gap:10px;margin-top:auto}}
.sc-actions{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.sc-actions .btn{{justify-content:center}}
.sc-actions .sc-cerebro-link{{max-width:none;margin:0}}
.sc-actions .sc-sec-link{{margin-top:0}}
.power-hour-banner{{top:88px;right:20px;background:linear-gradient(180deg,rgba(18,20,28,.94),rgba(10,12,18,.86));
  border:1px solid rgba(215,180,106,.2);border-radius:24px;box-shadow:0 24px 56px rgba(0,0,0,.32)}}
.ph-title{{font-family:'Space Grotesk','Segoe UI',sans-serif}}
footer{{background:rgba(11,14,22,.8);backdrop-filter:blur(16px)}}
@media(max-width:640px){{
  .nav{{margin:10px 12px 0;padding:0 12px;border-radius:18px}}
  .hero::before{{inset:4px 10px 0;border-radius:24px}}
  .hero-shell{{grid-template-columns:1fr;gap:18px}}
  .hero-command{{padding:0}}
  .hero-ops-grid{{grid-template-columns:1fr}}
  .hero-capture{{padding:12px}}
  .spotlight-dossier{{grid-template-columns:1fr}}
  .spotlight{{padding:22px 18px}}
  .spotlight-ticker{{font-size:clamp(1.8rem,14vw,3rem);word-break:break-word}}
  .spotlight-ticker-compact{{font-size:clamp(1.45rem,11vw,2.35rem)}}
  .spotlight-ticker-tight{{font-size:clamp(1.12rem,8.4vw,1.8rem)}}
  .sc-ticker strong{{white-space:normal;word-break:break-word}}
  .spotlight-footnote{{align-items:flex-start}}
  .spotlight-footnote-link{{margin-left:0}}
  .container-scroll-shell{{min-height:40rem}}
  .container-scroll-card{{padding:12px;border-radius:22px}}
  .countdown-bar{{padding:16px}}
  .freshness-strip{{grid-template-columns:1fr}}
  .sc-command-core{{grid-template-columns:1fr}}
  .sc-actions{{grid-template-columns:1fr}}
}}
/* ── MOBILE-ONLY RESCUE — zero desktop impact ── */
@media(max-width:640px){{
  html{{overflow-x:hidden}}

  /* ── HIDE CEREBRO DOCK LINKS (HUD not mobile-ready) ── */
  .sc-cerebro-link{{display:none!important}}
  .ce-transfer-rail{{display:none!important}}

  /* ── KILL HEAVY GPU EFFECTS ── */
  /* Animated background orbs (blur 120px + mix-blend-mode) */
  .scanner-posture-orb{{display:none!important}}
  .scanner-posture-pointer{{display:none!important}}
  .scanner-posture-vignette{{display:none!important}}
  .scanner-posture-bg{{background:#05060b!important;animation:none!important}}
  /* Body pseudo-element overlays (grid lines + gradient film) */
  body::before,body::after{{display:none!important}}
  /* Hero decorative pseudo-elements (gradient + blur orb) */
  .hero::before{{background:rgba(18,20,29,.84)!important;border-radius:24px}}
  .hero::after{{display:none!important}}
  /* Scroll reification: kill perspective transforms + filter compositing */
  .reify-muted{{opacity:1!important;filter:none!important}}
  .reify-focus{{opacity:1!important;filter:none!important;transform:none!important}}
  /* 3D container scroll card — flatten */
  .container-scroll-shell{{perspective:none!important}}
  .container-scroll-card{{transform:none!important;transition:none!important}}
  /* Armor card pseudo-element overlays (radial gradients) */
  .solid-armor-card::before,.liquid-glass-card::before{{display:none!important}}
  .solid-armor-card::after,.liquid-glass-card::after{{display:none!important}}
  /* Spotlight decorative layers */
  .spotlight::before,.spotlight::after{{display:none!important}}
  /* Intel shell decorative layers */
  .intel-shell::before,.intel-shell::after{{display:none!important}}
  .intel-table-chassis::before,.intel-table-chassis::after{{display:none!important}}
  /* Heatmap wrap decorative layers */
  #heatmap-wrap::before,#heatmap-wrap::after{{display:none!important}}
  /* Countdown bar — kill backdrop blur */
  .countdown-bar{{backdrop-filter:none!important;-webkit-backdrop-filter:none!important}}
  .nav{{backdrop-filter:none!important;-webkit-backdrop-filter:none!important;background:#0d1117!important}}
  /* Freshness card accent bar — keep simple */
  .freshness-card::before{{display:none!important}}
  /* Container scroll card decorative layers */
  .container-scroll-card::before{{display:none!important}}
  /* Scanner card hover effects — disable on touch */
  .scanner-card::before{{display:none!important}}
  .scanner-card:hover{{transform:none!important}}
  /* Power hour banner — kill backdrop blur */
  .power-hour-banner{{backdrop-filter:none!important;-webkit-backdrop-filter:none!important}}
  /* Spotlight rail corner brackets */
  .spotlight-rail::before,.spotlight-rail::after{{display:none!important}}
  /* Kill expensive box-shadows on cards */
  .solid-armor-card,.heavy-armor-card,.liquid-glass-card{{box-shadow:0 4px 16px rgba(0,0,0,.3)!important}}
  .scanner-card{{box-shadow:0 4px 12px rgba(0,0,0,.25)!important}}
  .spotlight{{box-shadow:0 4px 16px rgba(0,0,0,.3)!important}}
  /* CE transfer overlay — simplify */
  .ce-transfer-overlay{{background:rgba(4,8,14,.95)!important}}
  /* Ticker glitch animation — distracting on mobile */
  @keyframes tickerGlitch{{0%,100%{{transform:none;text-shadow:none;filter:none}}}}

  /* ── LAYOUT FIXES ── */
  .sector-tier-hero,.sector-tier-mid{{grid-template-columns:1fr}}
  .sector-card.hero .sc-score{{font-size:1.6em}}
  .how-grid{{grid-template-columns:1fr}}
  .track-grid{{grid-template-columns:1fr}}
  .picks-bar{{font-size:.74em;padding:7px 12px;gap:6px}}
  .winner-badge{{display:none}}
  .sub-popup{{left:12px;right:12px;width:auto;bottom:12px}}
  .sub-popup-form{{flex-direction:column}}
  .sub-popup-form .sub-popup-btn{{width:100%}}
  .email-capture-section{{padding:24px 16px}}
  .cta-block{{padding:24px 16px}}
  .capture-card{{flex-direction:column;gap:18px}}
  .capture-left{{min-width:0}}
  .hero-capture-form{{flex-direction:column}}
  .hero-capture-form .btn-green{{width:100%;text-align:center;justify-content:center}}
  #liq-toast-container{{right:12px;left:12px;max-width:none;bottom:70px}}
  .comp-table{{font-size:.74em}}
  .comp-table th,.comp-table td{{padding:5px 6px}}
  footer{{padding:20px 14px;font-size:.76em}}
  .fs-modal{{padding:18px 16px;margin:12px}}
  .freshness-grid{{grid-template-columns:1fr}}
  .ce-transfer-footer{{flex-direction:column;align-items:flex-start;gap:6px}}
  .sector-sticky-wrap{{padding:6px 12px 4px}}
  .sec-filter-btn{{padding:4px 10px;font-size:.74em}}
}}
</style>
{ga4_script}
</head>
<body data-posture="{market_posture}">

<!-- PICKS ALERT BAR -->
<div class="picks-bar" id="picks-bar">
  <span class="live-dot"></span>
  <strong>Today's picks are live</strong> — {len(gappers)} gap plays · {len(squeezes)} squeeze · {len(insiders)} insider
  {f'<span class="winner-badge" title="Tracked in /archive/ — auditable">🏆 Last tagged: <strong>{best_ticker}</strong> {best_move_str}{f" ({best_date_str})" if best_date_str else ""}</span>' if best_ticker and best_move_str else ""}
  <a href="#subscribe" class="picks-bar-cta">Get at 4 AM →</a>
  <button class="picks-bar-close" onclick="this.parentElement.style.display='none'" aria-label="Close">×</button>
</div>

<!-- STICKY NAV (consumer-first: lead with plays retail searches for) -->
<nav class="nav" id="primary-nav">
  <div class="nav-brand">⚡ Catalyst Edge</div>
  <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="primary-nav" aria-label="Toggle navigation"
    onclick="(function(b){{var n=document.getElementById('primary-nav');var open=n.classList.toggle('open');b.setAttribute('aria-expanded',open?'true':'false');b.textContent=open?'\u2715':'\u2630';}})(this)">&#9776;</button>
  <a href="#gaps"    class="nav-link">Gap Plays</a>
  <a href="#squeeze" class="nav-link">Squeeze</a>
  <a href="#insider" class="nav-link">Insider Buys</a>
  <a href="/congress/" class="nav-link">Congress</a>
  <a href="#results" class="nav-link">Catalysts</a>
  <a href="/sectors/" class="nav-link">Sectors</a>
  <a href="/news/"   class="nav-link">News</a>
  <a href="/short-scanner/" class="nav-link" style="color:#f78166;font-weight:700">📉 SHORT</a>
  <a href="#polymarket" class="nav-link" style="color:var(--cyan)">Predict ▸</a>
  <a href="javascript:void(0)" class="nav-link suite-trigger" onclick="document.getElementById('suite-overlay').classList.add('open');document.getElementById('suite-mega').classList.add('open');document.body.style.overflow='hidden'">All Tools ▸</a>
  <a href="/pricing/" class="nav-link" style="color:var(--gold);font-weight:600">Premium</a>
  <button class="nav-cta" type="button" onclick="(function(){{var p=document.getElementById('sub-popup');if(p){{p.classList.add('visible');var i=document.getElementById('sub-popup-email');if(i){{i.value='';setTimeout(function(){{i.focus();}},50);}}}}}})()">Subscribe Free</button>
</nav>
<div id="suite-overlay" class="suite-overlay" onclick="this.classList.remove('open');document.getElementById('suite-mega').classList.remove('open');document.body.style.overflow=''"></div>
<div id="suite-mega" class="suite-mega">
  <div class="suite-mega-head">
    <h3>⚡ Tool Suite</h3>
    <button class="suite-close" onclick="document.getElementById('suite-overlay').classList.remove('open');document.getElementById('suite-mega').classList.remove('open');document.body.style.overflow=''" aria-label="Close">✕</button>
  </div>
  <div class="suite-mega-body">
    <div class="suite-cat">
      <div class="suite-cat-head"><span class="cat-dot" style="background:var(--brass)"></span>Core Scanners</div>
      <div class="suite-links">
        <a href="/jackpot/" class="suite-link" style="color:#22c55e;font-weight:700">🎯 JACKPOT (89-100% hit rate)</a>
        <a href="/dcf/" class="suite-link" style="color:#06b6d4;font-weight:700">💰 DCF Intrinsic Value (US)</a>
        <a href="/dcf/international/" class="suite-link" style="color:#22d3ee;font-weight:700">🌍 DCF Intrinsic Value (38 markets)</a>
        <a href="/numerai/" class="suite-link" style="color:#a855f7;font-weight:700">🤖 Numerai Signals (live submissions)</a>
        <a href="/international/" class="suite-link" style="color:#22d3ee;font-weight:700">🌍 International (10 markets)</a>
        <a href="/cross-border/" class="suite-link" style="color:#f5c443;font-weight:700">🔗 Cross-Border Convergence (ADR pairs)</a>
        <a href="/defi/" class="suite-link" style="color:#fb923c;font-weight:700">⛓ DeFi & BTC ETFs</a>
        <a href="/" class="suite-link">Live Scanner</a>
        <a href="/screener/" class="suite-link">Screener</a>
        <a href="/rankings/" class="suite-link">Rankings</a>
        <a href="/spotlight/" class="suite-link">Spotlight</a>
        <a href="/lookup/" class="suite-link">Lookup</a>
      </div>
    </div>
    <div class="suite-cat">
      <div class="suite-cat-head"><span class="cat-dot" style="background:var(--green)"></span>Signal Dashboards</div>
      <div class="suite-links">
        <a href="/signals/" class="suite-link">All Signals</a>
        <a href="/squeeze/" class="suite-link">Squeeze Plays</a>
        <a href="/insiders/" class="suite-link">Insider Buying</a>
        <a href="/darkpool/" class="suite-link">Dark Pool</a>
        <a href="/deepvalue/" class="suite-link">Deep Value</a>
        <a href="/convergence/" class="suite-link">Convergence</a>
        <a href="/smart-money/" class="suite-link">Smart Money</a>
        <a href="/mergers/" class="suite-link">Mergers &amp; Acquisitions</a>
        <a href="/gaps/" class="suite-link">Gap Scanners</a>
        <a href="/sympathy/" class="suite-link">Sympathy Plays</a>
        <a href="/lockups/" class="suite-link">Lockup Expirations</a>
      </div>
    </div>
    <div class="suite-cat">
      <div class="suite-cat-head"><span class="cat-dot" style="background:var(--cyan)"></span>Analytics &amp; Data</div>
      <div class="suite-links">
        <a href="/signal-strength/" class="suite-link">Signal Strength</a>
        <a href="/heatmap/" class="suite-link">Sector Heatmap</a>
        <a href="/sectors/" class="suite-link">Sectors</a>
        <a href="/map/" class="suite-link">Catalyst Map</a>
        <a href="/correlation/" class="suite-link">Correlation Matrix</a>
        <a href="/momentum/" class="suite-link">Momentum Tracker</a>
        <a href="/movers/" class="suite-link">Top Movers</a>
        <a href="/hot-streaks/" class="suite-link">Hot Streaks</a>
        <a href="/vs/" class="suite-link">Head-to-Head</a>
        <a href="/performance/" class="suite-link">Performance</a>
        <a href="/calendar/" class="suite-link">Calendar</a>
      </div>
    </div>
    <div class="suite-cat">
      <div class="suite-cat-head"><span class="cat-dot" style="background:var(--purple)"></span>Research</div>
      <div class="suite-links">
        <a href="/filings-feed/" class="suite-link">Filings Feed</a>
        <a href="/sec-filings/" class="suite-link">SEC Filings</a>
        <a href="/late-filings/" class="suite-link">Late Filings</a>
        <a href="/congress/" class="suite-link">Congress Trades</a>
        <a href="/options-flow/" class="suite-link">Options Flow</a>
        <a href="/news/" class="suite-link">News Momentum</a>
        <a href="/archive/" class="suite-link">Archive</a>
        <a href="/winners/" class="suite-link">Winners Hall</a>
        <a href="/digest/" class="suite-link">Daily Digest</a>
      </div>
    </div>
    <div class="suite-cat">
      <div class="suite-cat-head"><span class="cat-dot" style="background:var(--orange)"></span>Tools &amp; Apps</div>
      <div class="suite-links">
        <a href="/watchlist-app/" class="suite-link">Watchlist App</a>
        <a href="/watchlist/" class="suite-link">Watchlist Picks</a>
        <a href="/simulator/" class="suite-link">Paper Simulator</a>
        <a href="/predict/" class="suite-link">Prediction Market</a>
        <a href="/alerts/" class="suite-link">Alerts Setup</a>
      </div>
    </div>
    <div class="suite-cat">
      <div class="suite-cat-head"><span class="cat-dot" style="background:var(--cyan)"></span>Games</div>
      <div class="suite-links">
        <a href="/bull-or-bear/" class="suite-link">Bull or Bear?</a>
        <a href="/predict/" class="suite-link">Prediction Market</a>
        <a href="/quiz/" class="suite-link">SEC Knowledge Quiz</a>
        <a href="/simulator/" class="suite-link">Paper Simulator</a>
        <a href="/arcade/" class="suite-link">Arcade</a>
      </div>
    </div>
    <div class="suite-cat">
      <div class="suite-cat-head"><span class="cat-dot" style="background:var(--brass)"></span>Education</div>
      <div class="suite-links">
        <a href="/glossary/" class="suite-link">Glossary</a>
        <a href="/methodology/" class="suite-link">Methodology</a>
        <a href="/how-to-trade-8k/" class="suite-link">How to Trade 8-K</a>
        <a href="/cheat-sheet/" class="suite-link">Cheat Sheet</a>
      </div>
    </div>
    <div class="suite-cat">
      <div class="suite-cat-head"><span class="cat-dot" style="background:var(--dim)"></span>Glossary Deep Dives</div>
      <div class="suite-links">
        <a href="/glossary/what-is-8k/" class="suite-link">What is an 8-K?</a>
        <a href="/glossary/what-is-form-4/" class="suite-link">What is Form 4?</a>
        <a href="/glossary/how-to-read-form-4/" class="suite-link">How to Read Form 4</a>
        <a href="/glossary/how-to-read-sec-filings/" class="suite-link">How to Read SEC Filings</a>
        <a href="/glossary/what-is-catalyst-score/" class="suite-link">What is Catalyst Score?</a>
        <a href="/glossary/what-is-convergence-alert/" class="suite-link">What is Convergence?</a>
        <a href="/glossary/sec-filing-types-for-traders/" class="suite-link">SEC Filing Types</a>
        <a href="/glossary/sec-catalyst-trading-strategy/" class="suite-link">Catalyst Trading Strategy</a>
        <a href="/glossary/what-is-short-squeeze/" class="suite-link">What is Short Squeeze?</a>
        <a href="/glossary/short-squeeze-scanner/" class="suite-link">Short Squeeze Scanner</a>
        <a href="/glossary/insider-buying-signals/" class="suite-link">Insider Buying Signals</a>
        <a href="/glossary/dark-pool-signals/" class="suite-link">Dark Pool Signals</a>
        <a href="/glossary/convergence-alerts/" class="suite-link">Convergence Alerts</a>
        <a href="/glossary/what-is-deep-value-investing/" class="suite-link">What is Deep Value?</a>
        <a href="/glossary/what-is-sc-13d/" class="suite-link">What is SC 13D?</a>
        <a href="/glossary/what-is-s3-shelf-registration/" class="suite-link">What is S-3 Shelf?</a>
        <a href="/glossary/what-is-lockup-expiration/" class="suite-link">Lockup Expirations</a>
        <a href="/glossary/what-is-gap-up-stock/" class="suite-link">What is Gap Up?</a>
        <a href="/glossary/premarket-gap-scanner/" class="suite-link">Premarket Gap Scanner</a>
        <a href="/glossary/what-is-sympathy-play/" class="suite-link">What is Sympathy Play?</a>
        <a href="/glossary/congressional-stock-trading/" class="suite-link">Congressional Trading</a>
      </div>
    </div>
  </div>
  <div class="suite-count">65+ tools · <a href="/suite/" style="color:var(--brass)">View full Suite page →</a></div>
</div>

<!-- ═══════════════════════════════ FULL-VIEWPORT CINEMATIC PROLOGUE ═══════════════════════════════ -->
<style>
@keyframes plLine1{{0%,100%{{opacity:0}}10%,40%{{opacity:1}}}}
@keyframes plLine2{{0%,100%{{opacity:0}}40%,70%{{opacity:1}}}}
@keyframes plLine3{{0%,100%{{opacity:0}}70%,95%{{opacity:1}}}}
@keyframes plRise{{from{{opacity:0;transform:translateY(40px) scale(.95);filter:blur(10px)}}to{{opacity:1;transform:translateY(0) scale(1);filter:blur(0)}}}}
@keyframes plRingExpand{{0%{{transform:scale(.2);opacity:.8}}100%{{transform:scale(2.5);opacity:0}}}}
@keyframes plOrbDrift{{0%,100%{{transform:translate(0,0)}}50%{{transform:translate(30px,-20px)}}}}
@keyframes plScan{{0%{{transform:translateY(-100%)}}100%{{transform:translateY(100%)}}}}
@keyframes plGlowCore{{0%,100%{{filter:drop-shadow(0 0 30px rgba(231,183,108,.5)) drop-shadow(0 0 80px rgba(114,229,255,.3))}}50%{{filter:drop-shadow(0 0 60px rgba(231,183,108,.8)) drop-shadow(0 0 140px rgba(114,229,255,.5))}}}}
@keyframes plRainStream{{0%{{transform:translateY(-100%);opacity:0}}10%{{opacity:.8}}90%{{opacity:.8}}100%{{transform:translateY(100%);opacity:0}}}}
@keyframes plScrollHint{{0%,100%{{transform:translate(-50%,0);opacity:.4}}50%{{transform:translate(-50%,8px);opacity:.95}}}}
@keyframes plBootCircle{{from{{stroke-dashoffset:500}}to{{stroke-dashoffset:0}}}}
@keyframes plRotate{{from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}}}}
@keyframes plRotateRev{{from{{transform:rotate(0deg)}}to{{transform:rotate(-360deg)}}}}

.prologue{{position:relative;min-height:100vh;display:flex;align-items:center;justify-content:center;
  overflow:hidden;background:radial-gradient(ellipse at center,#0a0e18 0%,#05060b 70%,#000 100%);
  border-bottom:1px solid rgba(231,183,108,.12)}}

/* Concentric pulse rings */
.pl-pulse{{position:absolute;left:50%;top:50%;width:60px;height:60px;border-radius:50%;
  border:2px solid rgba(231,183,108,.5);transform:translate(-50%,-50%) scale(.2)}}
.pl-pulse.p1{{animation:plRingExpand 5s ease-out infinite}}
.pl-pulse.p2{{animation:plRingExpand 5s ease-out infinite 1.2s;border-color:rgba(114,229,255,.4)}}
.pl-pulse.p3{{animation:plRingExpand 5s ease-out infinite 2.4s;border-color:rgba(167,139,250,.35)}}
.pl-pulse.p4{{animation:plRingExpand 5s ease-out infinite 3.6s;border-color:rgba(231,183,108,.3)}}

/* Orbital ring system */
.pl-orbit{{position:absolute;left:50%;top:50%;border-radius:50%;border:1px solid rgba(231,183,108,.18);
  transform:translate(-50%,-50%);pointer-events:none}}
.pl-orbit.o1{{width:280px;height:280px;animation:plRotate 24s linear infinite}}
.pl-orbit.o2{{width:480px;height:480px;animation:plRotateRev 38s linear infinite;border-color:rgba(114,229,255,.16)}}
.pl-orbit.o3{{width:720px;height:720px;animation:plRotate 56s linear infinite;border-color:rgba(167,139,250,.12)}}
.pl-orbit-node{{position:absolute;width:10px;height:10px;border-radius:50%;
  background:#e7b76c;box-shadow:0 0 16px #e7b76c}}
.pl-orbit.o1 .pl-orbit-node{{top:-5px;left:50%;transform:translateX(-50%)}}
.pl-orbit.o2 .pl-orbit-node{{top:50%;right:-5px;transform:translateY(-50%);background:#72e5ff;box-shadow:0 0 14px #72e5ff}}
.pl-orbit.o3 .pl-orbit-node{{bottom:-5px;left:50%;transform:translateX(-50%);background:#a78bfa;box-shadow:0 0 12px #a78bfa}}

/* Center core glyph */
.pl-core{{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  width:120px;height:120px;animation:plGlowCore 4s ease-in-out infinite}}
.pl-core svg{{width:100%;height:100%}}

/* Matrix-rain style ticker streams (subtle, columned) */
.pl-rain{{position:absolute;inset:0;overflow:hidden;pointer-events:none;opacity:.35}}
.pl-rain-col{{position:absolute;top:0;width:60px;font-family:'IBM Plex Mono',monospace;font-size:11px;
  color:#72e5ff;text-align:center;line-height:1.7;writing-mode:vertical-rl;text-orientation:mixed;
  animation:plRainStream var(--pl-d,12s) linear infinite var(--pl-delay,0s)}}

/* Headline stack */
.pl-headline{{position:relative;z-index:5;text-align:center;padding:0 24px;max-width:1100px;animation:plRise 1.4s cubic-bezier(.18,.84,.2,1) .3s both}}
.pl-eyebrow{{display:inline-flex;align-items:center;gap:10px;
  font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.4em;
  text-transform:uppercase;color:#e7b76c;
  background:rgba(231,183,108,.06);border:1px solid rgba(231,183,108,.22);
  border-radius:999px;padding:8px 18px;margin-bottom:36px;
  box-shadow:0 0 30px rgba(231,183,108,.18)}}
.pl-eyebrow .pl-dot{{width:6px;height:6px;border-radius:50%;background:#e7b76c;
  box-shadow:0 0 10px #e7b76c;animation:plGlowCore 1.8s ease-in-out infinite}}

.pl-h1{{font-family:'Space Grotesk',sans-serif;font-size:clamp(40px,8vw,108px);font-weight:800;
  letter-spacing:-.03em;line-height:.96;margin:0;
  background:linear-gradient(180deg,#fff 25%,#9aa6bd 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent}}
.pl-h1 .pl-acc{{
  background:linear-gradient(120deg,#e7b76c 30%,#72e5ff 70%);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
  position:relative;display:inline-block}}
.pl-h1 .pl-acc::after{{content:'';position:absolute;left:0;right:0;bottom:-6px;height:2px;
  background:linear-gradient(90deg,transparent,#e7b76c,#72e5ff,transparent);
  animation:plGlowCore 3s ease-in-out infinite}}

.pl-rotator{{margin-top:30px;height:42px;position:relative;animation:plRise 1.6s cubic-bezier(.18,.84,.2,1) .8s both}}
.pl-rotator-line{{position:absolute;left:50%;top:0;transform:translateX(-50%);white-space:nowrap;
  font-family:'IBM Plex Mono',monospace;font-size:clamp(13px,1.8vw,18px);letter-spacing:.08em;
  text-transform:uppercase;color:#c4cdde;font-weight:600}}
.pl-rotator-line .gold{{color:#e7b76c}}
.pl-rotator-line .green{{color:#3fb950}}
.pl-rotator-line .cyan{{color:#72e5ff}}
.pl-rotator-line .rose{{color:#f78166}}
.pl-rotator-line.l1{{animation:plLine1 9s ease-in-out infinite}}
.pl-rotator-line.l2{{animation:plLine2 9s ease-in-out infinite}}
.pl-rotator-line.l3{{animation:plLine3 9s ease-in-out infinite}}

.pl-stat-row{{display:inline-flex;gap:42px;margin-top:46px;flex-wrap:wrap;justify-content:center;
  animation:plRise 1.8s cubic-bezier(.18,.84,.2,1) 1.2s both}}
.pl-stat{{display:flex;flex-direction:column;align-items:center;gap:6px}}
.pl-stat-v{{font-family:'IBM Plex Mono',monospace;font-size:clamp(22px,3vw,32px);font-weight:800;letter-spacing:-.02em;
  background:linear-gradient(180deg,#fff,#9aa6bd);-webkit-background-clip:text;background-clip:text;color:transparent}}
.pl-stat-v.gold{{background:linear-gradient(180deg,#e7b76c,#c89854);-webkit-background-clip:text;background-clip:text;color:transparent}}
.pl-stat-v.cyan{{background:linear-gradient(180deg,#72e5ff,#3fb5cf);-webkit-background-clip:text;background-clip:text;color:transparent}}
.pl-stat-v.green{{background:linear-gradient(180deg,#3fb950,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent}}
.pl-stat-k{{font-family:'IBM Plex Mono',monospace;font-size:9.5px;letter-spacing:.32em;
  text-transform:uppercase;color:#7a8899}}

.pl-cta-row{{margin-top:48px;display:inline-flex;gap:14px;flex-wrap:wrap;justify-content:center;
  animation:plRise 2s cubic-bezier(.18,.84,.2,1) 1.5s both}}
.pl-btn{{display:inline-flex;align-items:center;gap:10px;padding:15px 30px;border-radius:8px;
  font-weight:700;font-size:14.5px;letter-spacing:.04em;text-decoration:none;
  transition:all .25s cubic-bezier(.18,.84,.2,1);border:none;cursor:pointer;font-family:'Space Grotesk',sans-serif}}
.pl-btn.primary{{background:linear-gradient(135deg,#e7b76c,#c89854);color:#0a0d18;
  box-shadow:0 0 40px rgba(231,183,108,.4),inset 0 1px 0 rgba(255,255,255,.4)}}
.pl-btn.primary:hover{{transform:translateY(-3px);box-shadow:0 0 60px rgba(231,183,108,.65)}}
.pl-btn.ghost{{background:transparent;border:1px solid rgba(114,229,255,.32);color:#72e5ff}}
.pl-btn.ghost:hover{{background:rgba(114,229,255,.06);border-color:#72e5ff;transform:translateY(-3px)}}
.pl-btn .pl-arrow{{transition:transform .25s}}
.pl-btn:hover .pl-arrow{{transform:translateX(4px)}}

.pl-scroll-cue{{position:absolute;left:50%;bottom:32px;
  font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.4em;
  text-transform:uppercase;color:#7a8899;text-align:center;
  animation:plScrollHint 2.4s ease-in-out infinite}}
.pl-scroll-cue::after{{content:'';display:block;width:1px;height:38px;margin:8px auto 0;
  background:linear-gradient(180deg,#7a8899,transparent)}}

/* Vignette + scanline overlay tying it together */
.pl-vignette{{position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(ellipse at center,transparent 30%,rgba(0,0,0,.5) 80%)}}
.pl-scanline{{position:absolute;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(114,229,255,.18),transparent);
  animation:plScan 7s linear infinite;pointer-events:none}}

@media(max-width:680px){{
  .pl-orbit.o3{{display:none}}
  .pl-orbit.o2{{width:340px;height:340px}}
  .pl-orbit.o1{{width:200px;height:200px}}
  .pl-stat-row{{gap:24px;margin-top:32px}}
  .prologue{{min-height:90vh}}
}}
</style>

<section class="prologue" aria-label="Catalyst Edge introduction">
  <!-- Pulse rings -->
  <div class="pl-pulse p1" aria-hidden="true"></div>
  <div class="pl-pulse p2" aria-hidden="true"></div>
  <div class="pl-pulse p3" aria-hidden="true"></div>
  <div class="pl-pulse p4" aria-hidden="true"></div>

  <!-- Orbital rings with traveling nodes -->
  <div class="pl-orbit o1" aria-hidden="true"><div class="pl-orbit-node"></div></div>
  <div class="pl-orbit o2" aria-hidden="true"><div class="pl-orbit-node"></div></div>
  <div class="pl-orbit o3" aria-hidden="true"><div class="pl-orbit-node"></div></div>

  <!-- Matrix-rain ticker columns -->
  <div class="pl-rain" aria-hidden="true">
    <div class="pl-rain-col" style="left:6%;--pl-d:14s;--pl-delay:0s">8-K · 13D · S-3 · 4 · 424B · NT-10K · DEF · SC TO · 144 · D · 25</div>
    <div class="pl-rain-col" style="left:18%;--pl-d:18s;--pl-delay:-3s">SEC · EDGAR · XBRL · DCF · GAP · SQUEEZE · CLUSTER · CONVERGE</div>
    <div class="pl-rain-col" style="left:84%;--pl-d:16s;--pl-delay:-6s">BTC · ETH · MSTR · NVDA · AAPL · TSM · QQQ · SPY · VIX · DXY</div>
    <div class="pl-rain-col" style="left:94%;--pl-d:13s;--pl-delay:-1s">SCAN · SCORE · RANK · DEPLOY · AUDIT · HALT · PROMOTE · LOOP</div>
  </div>

  <!-- Center core glyph (concentric SVG) -->
  <div class="pl-core" aria-hidden="true">
    <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="60" cy="60" r="44" stroke="rgba(231,183,108,.4)" stroke-width="1" stroke-dasharray="4 4"/>
      <circle cx="60" cy="60" r="32" stroke="rgba(114,229,255,.4)" stroke-width="1"/>
      <circle cx="60" cy="60" r="20" stroke="rgba(167,139,250,.4)" stroke-width="1" stroke-dasharray="2 3"/>
      <circle cx="60" cy="60" r="8" fill="rgba(231,183,108,.18)" stroke="#e7b76c" stroke-width="1.5"/>
      <circle cx="60" cy="60" r="3" fill="#e7b76c"/>
      <line x1="60" y1="16" x2="60" y2="28" stroke="#72e5ff" stroke-width="1"/>
      <line x1="60" y1="92" x2="60" y2="104" stroke="#72e5ff" stroke-width="1"/>
      <line x1="16" y1="60" x2="28" y2="60" stroke="#72e5ff" stroke-width="1"/>
      <line x1="92" y1="60" x2="104" y2="60" stroke="#72e5ff" stroke-width="1"/>
    </svg>
  </div>

  <!-- Headline stack -->
  <div class="pl-headline">
    <div class="pl-eyebrow"><span class="pl-dot"></span>The Console · Operational · {market_posture.upper()}</div>

    <h1 class="pl-h1">We're building<br>the <span class="pl-acc">future of trading</span>.</h1>

    <div class="pl-rotator">
      <div class="pl-rotator-line l1"><span class="gold">SCAN</span> · 470+ filings/day · <span class="cyan">SEC EDGAR LIVE</span></div>
      <div class="pl-rotator-line l2"><span class="cyan">SCORE</span> · 11 engines · <span class="gold">XBRL FUNDAMENTALS</span></div>
      <div class="pl-rotator-line l3"><span class="green">RANK</span> · one board · <span class="rose">REFRESHED BEFORE THE BELL</span></div>
    </div>

    <div class="pl-stat-row">
      <div class="pl-stat"><div class="pl-stat-v gold">7,325</div><div class="pl-stat-k">entities</div></div>
      <div class="pl-stat"><div class="pl-stat-v cyan">22</div><div class="pl-stat-k">live endpoints</div></div>
      <div class="pl-stat"><div class="pl-stat-v">{_LIVE_HIT2:.1f}%</div><div class="pl-stat-k">audited hit · 90d</div></div>
      <div class="pl-stat"><div class="pl-stat-v green">{_LIVE_PICKS:,}</div><div class="pl-stat-k">picks evaluated</div></div>
    </div>

    <div class="pl-cta-row">
      <a class="pl-btn primary" href="#scanner">Enter the Console <span class="pl-arrow">↓</span></a>
      <a class="pl-btn ghost" href="/blog/why-our-bot-failed-validation/">Watch us iterate live <span class="pl-arrow">→</span></a>
    </div>
  </div>

  <!-- Scanlines for CRT feel -->
  <div class="pl-scanline" aria-hidden="true"></div>
  <div class="pl-scanline" style="animation-delay:-3s;opacity:.3" aria-hidden="true"></div>
  <div class="pl-vignette" aria-hidden="true"></div>

  <a class="pl-scroll-cue" href="#scanner" aria-label="Scroll to live console">scroll · enter the live console</a>
</section>

<!-- ═══════════════════════════════ CINEMATIC SCANNER HERO ═══════════════════════════════ -->
<a id="scanner"></a>
<style>
@keyframes shTape{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}
@keyframes shFade{{from{{opacity:0;transform:translateY(20px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes shFlow{{0%{{transform:translateX(-100%);opacity:0}}20%{{opacity:1}}80%{{opacity:1}}100%{{transform:translateX(100%);opacity:0}}}}
@keyframes shCorePulse{{0%,100%{{transform:scale(1);box-shadow:0 0 30px rgba(231,183,108,.5),0 0 60px rgba(114,229,255,.3)}}50%{{transform:scale(1.05);box-shadow:0 0 50px rgba(231,183,108,.7),0 0 100px rgba(114,229,255,.5)}}}}
@keyframes shCount{{from{{opacity:0;filter:blur(4px)}}to{{opacity:1;filter:blur(0)}}}}
@keyframes shGlow{{0%,100%{{filter:drop-shadow(0 0 12px rgba(231,183,108,.4))}}50%{{filter:drop-shadow(0 0 32px rgba(231,183,108,.85))}}}}

.sh-cinematic{{position:relative;padding:60px 24px 70px;overflow:hidden;
  background:radial-gradient(ellipse at center,rgba(231,183,108,.06),transparent 60%);
  border-bottom:1px solid rgba(231,183,108,.14)}}
.sh-cinematic::before{{content:'';position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(rgba(114,229,255,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(114,229,255,.04) 1px,transparent 1px);
  background-size:60px 60px;mask-image:radial-gradient(ellipse at center,black 30%,transparent 75%);
  -webkit-mask-image:radial-gradient(ellipse at center,black 30%,transparent 75%);opacity:.5}}
.sh-wrap2{{max-width:1180px;margin:0 auto;position:relative;z-index:2}}

.sh-tape{{position:relative;height:34px;overflow:hidden;
  border-top:1px solid rgba(231,183,108,.18);border-bottom:1px solid rgba(231,183,108,.18);
  background:rgba(7,11,17,.6);margin-bottom:36px}}
.sh-tape::before,.sh-tape::after{{content:'';position:absolute;top:0;bottom:0;width:80px;z-index:2;pointer-events:none}}
.sh-tape::before{{left:0;background:linear-gradient(90deg,rgba(7,11,17,.95),transparent)}}
.sh-tape::after{{right:0;background:linear-gradient(-90deg,rgba(7,11,17,.95),transparent)}}
.sh-tape-track{{display:flex;align-items:center;gap:24px;height:100%;
  font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:#7a8899;
  white-space:nowrap;animation:shTape 60s linear infinite;width:max-content;padding:0 24px}}
.sh-tape-tick{{display:inline-flex;gap:6px;align-items:center}}
.sh-tape-tick .sh-form{{color:#72e5ff;font-weight:600;background:rgba(114,229,255,.06);padding:2px 7px;border-radius:4px;border:1px solid rgba(114,229,255,.18)}}
.sh-tape-tick .sh-form.bear{{color:#f78166;background:rgba(247,129,102,.06);border-color:rgba(247,129,102,.22)}}
.sh-tape-tick .sh-form.gold{{color:#e7b76c;background:rgba(231,183,108,.06);border-color:rgba(231,183,108,.22)}}
.sh-tape-sep{{color:rgba(231,183,108,.3)}}

.sh-eyebrow2{{display:inline-flex;align-items:center;gap:10px;
  font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.32em;text-transform:uppercase;color:#e7b76c;
  background:rgba(231,183,108,.06);border:1px solid rgba(231,183,108,.22);
  border-radius:999px;padding:7px 16px;margin-bottom:24px;
  box-shadow:0 0 24px rgba(231,183,108,.12);animation:shFade .9s cubic-bezier(.18,.84,.2,1) .1s both}}
.sh-eyebrow2 .sh-pulse{{width:6px;height:6px;border-radius:50%;background:#e7b76c;
  box-shadow:0 0 10px #e7b76c;animation:shCorePulse 1.6s ease-in-out infinite}}

.sh-cinematic h1{{font-size:clamp(34px,5.4vw,68px);font-weight:800;letter-spacing:-.025em;line-height:1.05;
  max-width:980px;margin:0;
  background:linear-gradient(180deg,#fff 30%,#a3afc4 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent;
  animation:shFade 1s cubic-bezier(.18,.84,.2,1) .25s both}}
.sh-cinematic h1 .sh-acc{{
  background:linear-gradient(120deg,#e7b76c 30%,#72e5ff 70%);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
  position:relative;display:inline-block}}
.sh-cinematic h1 .sh-acc::after{{content:'';position:absolute;left:0;right:0;bottom:-4px;height:2px;
  background:linear-gradient(90deg,transparent,#e7b76c,#72e5ff,transparent);opacity:.7;
  animation:shGlow 3s ease-in-out infinite}}

.sh-lede2{{font-size:clamp(15px,1.5vw,18px);color:#c4cdde;max-width:780px;margin:18px 0 0;line-height:1.55;
  animation:shFade 1.05s cubic-bezier(.18,.84,.2,1) .35s both}}
.sh-lede2 b{{color:#e7b76c;font-weight:600}}

.sh-pipeline{{position:relative;margin:38px 0;padding:30px 24px;
  background:linear-gradient(180deg,rgba(12,16,24,.7),rgba(7,11,17,.7));
  border:1px solid rgba(231,183,108,.18);border-radius:14px;overflow:hidden;
  animation:shFade 1.1s cubic-bezier(.18,.84,.2,1) .45s both}}
.sh-pipeline::before{{content:'';position:absolute;left:0;top:0;height:2px;width:100%;
  background:linear-gradient(90deg,#e7b76c,#72e5ff,transparent)}}
.sh-pipeline-flow{{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:20px;align-items:center;position:relative}}
@media(max-width:880px){{.sh-pipeline-flow{{grid-template-columns:1fr;gap:14px}}.sh-pipeline-arrow{{display:none}}}}
.sh-pipe-stage{{text-align:center;padding:14px 12px;background:rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.06);border-radius:10px;position:relative}}
.sh-pipe-stage .sh-pipe-icon{{font-size:22px;margin-bottom:6px;display:block}}
.sh-pipe-stage .sh-pipe-k{{font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:#7a8899;margin-bottom:3px}}
.sh-pipe-stage .sh-pipe-v{{font-family:'IBM Plex Mono',monospace;font-size:18px;font-weight:700;color:#e6edf3}}
.sh-pipe-stage.scan{{border-color:rgba(114,229,255,.32)}}.sh-pipe-stage.scan .sh-pipe-v{{color:#72e5ff}}
.sh-pipe-stage.engine{{border-color:rgba(231,183,108,.4);background:radial-gradient(circle,rgba(231,183,108,.08),transparent 70%);
  animation:shCorePulse 4s ease-in-out infinite}}
.sh-pipe-stage.engine .sh-pipe-v{{color:#e7b76c}}
.sh-pipe-stage.rank{{border-color:rgba(63,185,80,.32)}}.sh-pipe-stage.rank .sh-pipe-v{{color:#3fb950}}
.sh-pipeline-arrow{{font-family:'IBM Plex Mono',monospace;font-size:18px;color:#7a8899;text-align:center;
  position:relative;overflow:hidden;height:24px;display:flex;align-items:center;justify-content:center}}
.sh-pipeline-arrow span{{position:absolute;left:0;right:0;animation:shFlow 3s linear infinite}}

.sh-proof2{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:28px 0 22px;
  animation:shFade 1.15s cubic-bezier(.18,.84,.2,1) .55s both}}
@media(max-width:880px){{.sh-proof2{{grid-template-columns:repeat(2,1fr)}}}}
.sh-cell{{position:relative;padding:18px 18px;background:rgba(12,16,24,.6);border:1px solid rgba(255,255,255,.06);border-radius:10px;overflow:hidden;
  transition:transform .25s,border-color .25s,box-shadow .25s}}
.sh-cell::before{{content:'';position:absolute;left:0;top:0;height:2px;width:100%;background:rgba(255,255,255,.1)}}
.sh-cell:hover{{transform:translateY(-2px);box-shadow:0 12px 30px rgba(0,0,0,.35)}}
.sh-cell .sh-cell-k{{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#7a8899;margin-bottom:4px}}
.sh-cell .sh-cell-v{{font-family:'IBM Plex Mono',monospace;font-size:32px;font-weight:800;letter-spacing:-.02em;line-height:1;
  animation:shCount 1.2s cubic-bezier(.18,.84,.2,1) both}}
.sh-cell .sh-cell-sub{{font-size:11.5px;color:#7a8899;margin-top:6px;line-height:1.4}}
.sh-cell.green::before{{background:#3fb950;box-shadow:0 0 8px #3fb950}}.sh-cell.green .sh-cell-v{{color:#3fb950}}
.sh-cell.gold::before{{background:#e7b76c;box-shadow:0 0 8px #e7b76c}}.sh-cell.gold .sh-cell-v{{color:#e7b76c}}
.sh-cell.cyan::before{{background:#72e5ff;box-shadow:0 0 8px #72e5ff}}.sh-cell.cyan .sh-cell-v{{color:#72e5ff}}
.sh-cell.rose::before{{background:#f78166;box-shadow:0 0 8px #f78166}}.sh-cell.rose .sh-cell-v{{color:#f78166}}
.sh-cell:hover{{border-color:currentColor}}

.sh-cta-row{{display:flex;gap:14px;margin-top:8px;flex-wrap:wrap;
  animation:shFade 1.2s cubic-bezier(.18,.84,.2,1) .65s both}}
.sh-btn{{display:inline-flex;align-items:center;gap:10px;padding:13px 24px;border-radius:8px;
  font-weight:700;font-size:14px;letter-spacing:.02em;text-decoration:none;
  transition:all .25s cubic-bezier(.18,.84,.2,1);border:none;cursor:pointer}}
.sh-btn.primary{{background:linear-gradient(135deg,#e7b76c,#c89854);color:#0a0d18;
  box-shadow:0 0 30px rgba(231,183,108,.35)}}
.sh-btn.primary:hover{{transform:translateY(-2px);box-shadow:0 0 50px rgba(231,183,108,.55);text-decoration:none;color:#0a0d18}}
.sh-btn.ghost{{background:rgba(114,229,255,.06);border:1px solid rgba(114,229,255,.28);color:#72e5ff}}
.sh-btn.ghost:hover{{background:rgba(114,229,255,.1);border-color:#72e5ff;transform:translateY(-2px);text-decoration:none;color:#72e5ff}}
.sh-cta-row .sh-arrow{{transition:transform .25s}}
.sh-cta-row .sh-btn:hover .sh-arrow{{transform:translateX(4px)}}

.sh-microlinks{{margin-top:18px;display:flex;gap:18px;flex-wrap:wrap;
  font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:#7a8899;letter-spacing:.04em;
  animation:shFade 1.25s cubic-bezier(.18,.84,.2,1) .75s both}}
.sh-microlinks a{{color:#7a8899;text-decoration:none;border-bottom:1px solid rgba(122,136,153,.3);transition:all .2s}}
.sh-microlinks a:hover{{color:#e7b76c;border-bottom-color:#e7b76c}}
</style>

<header class="scanner-hero sh-cinematic" role="banner">
  <div class="sh-tape" aria-hidden="true">
    <div class="sh-tape-track">
      <span class="sh-tape-tick"><span class="sh-form">8-K</span><span>material event</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form">FORM 4</span><span>insider buy</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form gold">13D</span><span>activist stake</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form bear">S-3</span><span>shelf · dilution</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form bear">424B5</span><span>ATM offering</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form">10-Q</span><span>quarterly</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form bear">NT 10-K</span><span>late filer</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form gold">SC TO</span><span>tender offer</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form">DEF 14A</span><span>proxy</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form bear">25-NSE</span><span>delist notice</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form">FORM D</span><span>private placement</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form bear">FORM 144</span><span>insider sell intent</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form gold">XBRL</span><span>fundamentals</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form">8-K</span><span>material event</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form">FORM 4</span><span>insider buy</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form gold">13D</span><span>activist stake</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form bear">S-3</span><span>shelf · dilution</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form bear">424B5</span><span>ATM offering</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form">10-Q</span><span>quarterly</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form bear">NT 10-K</span><span>late filer</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form gold">SC TO</span><span>tender offer</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form">DEF 14A</span><span>proxy</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form bear">25-NSE</span><span>delist notice</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form">FORM D</span><span>private placement</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form bear">FORM 144</span><span>insider sell intent</span></span><span class="sh-tape-sep">◆</span>
      <span class="sh-tape-tick"><span class="sh-form gold">XBRL</span><span>fundamentals</span></span>
    </div>
  </div>
  <div class="sh-wrap2">
    <div class="sh-eyebrow2"><span class="sh-pulse"></span>Live console · refreshed 3:30 AM ET · {market_posture.upper()} posture · 470+ daily feeds</div>
    <h1>The signal console for<br><span class="sh-acc">catalyst traders</span>.</h1>
    <p class="sh-lede2">
      Every SEC filing. Every XBRL fundamental. Every insider cluster, squeeze setup, dark-pool print. <b>One ranked board, refreshed before the bell.</b>
    </p>

    <div class="sh-pipeline">
      <div class="sh-pipeline-flow">
        <div class="sh-pipe-stage scan">
          <span class="sh-pipe-icon">📡</span>
          <div class="sh-pipe-k">Scan</div>
          <div class="sh-pipe-v">300+</div>
          <div class="sh-pipe-k" style="margin-top:4px">EDGAR filings/day</div>
        </div>
        <div class="sh-pipeline-arrow"><span>───→</span></div>
        <div class="sh-pipe-stage engine">
          <span class="sh-pipe-icon">⚙</span>
          <div class="sh-pipe-k">Score</div>
          <div class="sh-pipe-v">11</div>
          <div class="sh-pipe-k" style="margin-top:4px">scoring engines</div>
        </div>
        <div class="sh-pipeline-arrow"><span>───→</span></div>
        <div class="sh-pipe-stage rank">
          <span class="sh-pipe-icon">🎯</span>
          <div class="sh-pipe-k">Rank</div>
          <div class="sh-pipe-v">1</div>
          <div class="sh-pipe-k" style="margin-top:4px">ranked board</div>
        </div>
      </div>
    </div>

    <div class="sh-proof2">
      <div class="sh-cell green">
        <div class="sh-cell-k">Hit rate · +2% intraday</div>
        <div class="sh-cell-v">{_LIVE_HIT2:.1f}%</div>
        <div class="sh-cell-sub">audited · 90-day window</div>
      </div>
      <div class="sh-cell cyan">
        <div class="sh-cell-k">Evaluated picks</div>
        <div class="sh-cell-v">{_LIVE_PICKS:,}</div>
        <div class="sh-cell-sub">{_wins:,} wins · {_losses:,} losses</div>
      </div>
      <div class="sh-cell gold">
        <div class="sh-cell-k">Big-move rate · +5% intraday</div>
        <div class="sh-cell-v">{_hit5:.1f}%</div>
        <div class="sh-cell-sub">outlier winners</div>
      </div>
      <div class="sh-cell rose">
        <div class="sh-cell-k">Loss rate · published picks (score≥15)</div>
        <div class="sh-cell-v">{_loss_rate:.1f}%</div>
        <div class="sh-cell-sub">{('holdout: ' + format(100 - _holdout_hit, '.1f') + '%') if _holdout_hit > 0 else 'in-sample only'}</div>
      </div>
      <div class="sh-cell {'green' if _avg_alpha > 0 else 'rose'}">
        <div class="sh-cell-k">Alpha vs SPY · per pick</div>
        <div class="sh-cell-v">{('+' if _avg_alpha >= 0 else '')}{_avg_alpha:.2f}%</div>
        <div class="sh-cell-sub">excess return after baseline subtraction</div>
      </div>
      <div class="sh-cell {'green' if _c30 >= _c90 else 'rose'}">
        <div class="sh-cell-k">30d vs 90d cohort decay</div>
        <div class="sh-cell-v">{_c30:.1f}% / {_c90:.1f}%</div>
        <div class="sh-cell-sub">{('STABLE' if abs(_c30 - _c90) < 5 else 'DECAY' if _c30 < _c90 - 5 else 'IMPROVING')}</div>
      </div>
    </div>

    <div class="sh-cta-row">
      <a class="sh-btn primary" href="#primary-target">See today’s Primary Target <span class="sh-arrow">→</span></a>
      <a class="sh-btn ghost" href="/methodology/">How we score <span class="sh-arrow">→</span></a>
    </div>

    <div class="sh-microlinks">
      <a href="/archive/">audit trail</a>
      <a href="#subscribe">free 4 AM email</a>
      <a href="/pricing/">compare tiers</a>
      <a href="/short-scanner/">📉 short scanner</a>
      <a href="/blog/why-our-bot-failed-validation/">bot audit</a>
    </div>
  </div>
</header>

{tactical_strip}

<div class="scanner-posture-shell">
  <div class="scanner-posture-bg" aria-hidden="true">
    <div class="scanner-posture-orb first"></div>
    <div class="scanner-posture-orb second"></div>
    <div class="scanner-posture-orb third"></div>
    <div class="scanner-posture-orb fourth"></div>
    <div class="scanner-posture-orb fifth"></div>
    <div class="scanner-posture-pointer"></div>
    <div class="scanner-posture-vignette"></div>
  </div>

<section class="spotlight-stage">
  {spotlight_html}
</section>

<!-- BEARISH PRIMARY TARGET — transparency mirror, hydrated client-side from /data/short_scanner.json -->
<section class="spotlight-stage" id="bear-spotlight-stage" aria-labelledby="bear-spotlight-label" style="padding-top:0">
  <div class="spotlight-lamp-shell">
    <div class="spotlight-lamp-beam spotlight-lamp-left" aria-hidden="true" style="--lamp-color:rgba(247,129,102,.16)"></div>
    <div class="spotlight-lamp-beam spotlight-lamp-right" aria-hidden="true" style="--lamp-color:rgba(247,129,102,.16)"></div>
    <div class="spotlight-lamp-core" aria-hidden="true" style="--lamp-color:rgba(247,129,102,.18)"></div>
    <div class="spotlight solid-armor-card" id="bear-spotlight-card" style="border-color:rgba(247,129,102,.32);background:linear-gradient(135deg,rgba(247,129,102,.04),rgba(13,17,23,.86));margin-top:6px">
      <div class="spotlight-label" id="bear-spotlight-label" style="color:#f78166">📉 Bearish Primary Target · {TODAY}</div>
      <div class="spotlight-body spotlight-dossier spotlight-dossier-balanced">
        <div class="spotlight-rail spotlight-rail-left spotlight-col-left">
          <div class="spotlight-lockline" style="color:#f78166">Rank 01 · Bearish · stay-away / hedge</div>
          <div class="spotlight-ticker-wrap">
            <div class="spotlight-ticker" id="bear-spot-ticker" data-ticker="—" data-ticker-len="4" style="color:#f78166">—</div>
          </div>
          <div class="spotlight-live" id="bear-spot-live"></div>
          <div class="spotlight-meta" id="bear-spot-meta">
            <span class="badge-form" id="bear-spot-form">—</span>
            <span class="badge-cat" id="bear-spot-cat" style="color:#f78166">bearish</span>
            <span class="badge-sector" id="bear-spot-flags-line">—</span>
          </div>
        </div>
        <div class="spotlight-rail spotlight-rail-center spotlight-col-center">
          <div class="spotlight-thesis-kicker" style="color:#f78166">Bearish Thesis</div>
          <div class="spotlight-thesis" id="bear-spot-thesis">Loading the highest-scoring bearish-flagged filing…</div>
          <div class="spotlight-score spotlight-score-normalized">
            <span class="spotlight-score-k">Bear Score</span>
            <span class="spotlight-score-v" id="bear-spot-score-v" style="color:#f78166">—<span class="spotlight-score-max">/30</span></span>
            <span class="spotlight-score-tier" id="bear-spot-score-tier" style="color:#f78166">—</span>
            <div class="spotlight-score-bar"><div class="spotlight-score-fill" id="bear-spot-score-fill" style="width:0%;background:#f78166"></div></div>
          </div>
          <div class="spotlight-baserate" aria-label="Bearish base rate · transparent assumption">
            <div class="sp-br-kicker" id="bear-spot-br-kicker">Universe context · what we observed today</div>
            <div class="sp-br-row">
              <div class="sp-br-cell" title="Total tickers flagged with at least one bearish signal in this scan."><div class="sp-br-v" id="bear-spot-br1">—</div><div class="sp-br-k">flagged today</div></div>
              <div class="sp-br-cell" title="Tickers carrying score >= 25 (HIGH or EXTREME tier)."><div class="sp-br-v" id="bear-spot-br2">—</div><div class="sp-br-k">high conviction</div></div>
              <div class="sp-br-cell" title="EDGAR filings scanned in this run."><div class="sp-br-v" id="bear-spot-br3">—</div><div class="sp-br-k">filings scanned</div></div>
            </div>
          </div>
          <div class="spotlight-tradeframe" aria-label="Short trade frame">
            <div class="sp-tf-kicker" id="bear-spot-tf-kicker">Short trade frame · ATR14 stop · 2R ladder · reference only, not advice</div>
            <div class="sp-tf-row">
              <div class="sp-tf-cell" title="Hypothetical short entry at current mid-price. Subtract slippage + locate fees IRL."><div class="sp-tf-k">Entry</div><div class="sp-tf-v" id="bear-spot-entry">—</div></div>
              <div class="sp-tf-cell sp-tf-stop" title="Buy-to-cover stop placed ABOVE entry (entry + 1*ATR14)."><div class="sp-tf-k">Stop</div><div class="sp-tf-v" id="bear-spot-stop">—</div></div>
              <div class="sp-tf-cell sp-tf-target" title="First profit target — entry minus 1R."><div class="sp-tf-k">Target 1</div><div class="sp-tf-v" id="bear-spot-t1">—</div></div>
              <div class="sp-tf-cell sp-tf-target" title="Second profit target — entry minus 2R."><div class="sp-tf-k">Target 2</div><div class="sp-tf-v" id="bear-spot-t2">—</div></div>
              <div class="sp-tf-cell" title="14-day average daily volume."><div class="sp-tf-k">Avg Vol</div><div class="sp-tf-v" id="bear-spot-vol">—</div></div>
              <div class="sp-tf-cell" title="Market cap from Yahoo Finance."><div class="sp-tf-k">Market Cap</div><div class="sp-tf-v" id="bear-spot-cap">—</div></div>
              <div class="sp-tf-cell" title="Approximate float (market cap / price). Low float + bearish catalyst = HIGH squeeze risk."><div class="sp-tf-k">Float ≈</div><div class="sp-tf-v" id="bear-spot-float">—</div></div>
            </div>
          </div>
        </div>
        <div class="spotlight-rail spotlight-rail-right spotlight-col-right">
          <a id="bear-spot-cerebro" href="/cerebro/app/?direction=short&source=scanner&channel=bear-spotlight"
             class="btn btn-green sc-cerebro-link sc-cerebro-link-hero"
             title="Open in Cerebro with the SHORT-side dossier preset."
             style="background:#f78166;color:#0d0d0d">Dock into Cerebro &rarr;</a>
          <a id="bear-spot-secfile" href="/short-scanner/" target="_blank" rel="nofollow"
             class="btn btn-outline sc-sec-link spotlight-sec-link"
             title="Open the underlying SEC filing that triggered the bearish flag."
             style="border-color:rgba(247,129,102,.35);color:#f78166">View SEC Filing &uarr;</a>
          <a href="/short-scanner/" class="btn btn-outline"
             title="See all bearish-flagged tickers, full score legend, BK/DL flags."
             style="border-color:rgba(247,129,102,.25);color:#f78166;font-size:12px;padding:6px 10px;margin-top:4px">Full short scanner &uarr;</a>
        </div>
      </div>
      <div class="spotlight-footnote">
        <span class="spotlight-footnote-kicker" style="color:#f78166">Why we surface this</span>
        <span>The Primary Target above is bullish. To stay honest we publish the strongest bearish setup
        side-by-side. A bearish flag is <strong>not auto-short</strong>; it's a stay-away or hedge prompt.</span>
        <a href="/short-scanner/" class="spotlight-footnote-link" style="color:#f78166">Open short scanner &rarr;</a>
      </div>
    </div>
  </div>
</section>
<script>
(function(){{
  function setText(id, v){{ var n=document.getElementById(id); if(n) n.textContent=(v==null?'—':String(v)); }}
  function fmtUSD(n){{ var x=Number(n); if(!isFinite(x)||x<=0) return '—';
    return '$'+x.toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}}); }}
  function fmtVol(n){{ var x=Number(n); if(!isFinite(x)||x<=0) return '—';
    if(x>=1e6) return (x/1e6).toFixed(1).replace(/\.0$/,'')+'M';
    if(x>=1e3) return Math.round(x/1e3)+'K'; return Math.round(x).toString(); }}
  function fmtCap(n){{ var x=Number(n); if(!isFinite(x)||x<=0) return '—';
    if(x>=1e9) return '$'+(x/1e9).toFixed(1).replace(/\.0$/,'')+'B';
    if(x>=1e6) return '$'+(x/1e6).toFixed(1).replace(/\.0$/,'')+'M';
    return '$'+Math.round(x).toLocaleString(); }}
  function fmtFloat(n){{ var x=Number(n); if(!isFinite(x)||x<=0) return '—';
    if(x>=1e6) return (x/1e6).toFixed(1).replace(/\.0$/,'')+'M';
    if(x>=1e3) return (x/1e3).toFixed(1).replace(/\.0$/,'')+'K';
    return Math.round(x).toLocaleString(); }}
  function dedupe(arr,n){{ var s={{}},o=[]; for(var i=0;i<arr.length;i++){{ var t=String(arr[i]||''),k=t.split(' (')[0]; if(!s[k]){{s[k]=1;o.push(t);}} if(o.length>=(n||4))break; }} return o; }}
  function tierFor(score){{ var s=Number(score)||0;
    if(s>=50) return {{label:'EXTREME',color:'#f78166',pct:100}};
    if(s>=25) return {{label:'HIGH',color:'#f78166',pct:80}};
    if(s>=12) return {{label:'ELEVATED',color:'#f0883e',pct:55}};
    if(s>=6)  return {{label:'MODERATE',color:'#d29922',pct:35}};
    return {{label:'LOW',color:'#8891a3',pct:15}}; }}
  fetch('/data/short_scanner.json',{{cache:'no-store'}})
    .then(function(r){{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); }})
    .then(function(d){{
      var top = (d.top && d.top.length) ? d.top[0] : null;
      if(!top){{ setText('bear-spot-ticker','—'); setText('bear-spot-thesis','No bearish-flagged filings in the current EDGAR window — clean tape.'); return; }}
      var tk = top.ticker || '?';
      var t = document.getElementById('bear-spot-ticker');
      if(t){{ t.textContent = tk; t.setAttribute('data-ticker', tk); t.setAttribute('data-ticker-len', String(tk.length)); }}
      var sigs = dedupe(top.signals||[], 4);
      setText('bear-spot-thesis', sigs.length
        ? ('Top bearish flags from EDGAR: ' + sigs.join('  ·  ') + '. ' + (d.bearish_count||0) + ' tickers flagged across ' + (d.universe_size||0) + ' filings scanned.')
        : 'Bearish-flagged with no signal detail.');
      var tier = tierFor(top.score);
      var sv = document.getElementById('bear-spot-score-v');
      if(sv){{ sv.replaceChildren(); sv.appendChild(document.createTextNode(String(top.score||0)));
        var sup = document.createElement('span'); sup.className='spotlight-score-max'; sup.textContent='/' + (top.score>=50?top.score:50);
        sv.appendChild(sup); sv.style.color = tier.color; }}
      setText('bear-spot-score-tier', tier.label);
      var fill = document.getElementById('bear-spot-score-fill');
      if(fill){{ fill.style.width = tier.pct+'%'; fill.style.background = tier.color; }}
      var firstForm = (sigs[0]||'').split(' (')[0] || '—';
      setText('bear-spot-form', firstForm);
      var flagsLine = '—';
      if(top.bankruptcy && top.delisting) flagsLine = '⚠ BANKRUPTCY · DELISTING';
      else if(top.bankruptcy) flagsLine = '⚠ BANKRUPTCY';
      else if(top.delisting) flagsLine = '⚠ DELISTING';
      else if(top.insider_cluster_sell_usd || top.insider_cluster_sell_count) flagsLine = '⚠ Insider cluster sell';
      setText('bear-spot-flags-line', flagsLine);
      setText('bear-spot-entry', fmtUSD(top.entry));
      setText('bear-spot-stop',  fmtUSD(top.stop));
      setText('bear-spot-t1',    fmtUSD(top.target1));
      setText('bear-spot-t2',    fmtUSD(top.target2));
      setText('bear-spot-vol',   fmtVol(top.avg_vol));
      setText('bear-spot-cap',   fmtCap(top.market_cap));
      setText('bear-spot-float', fmtFloat(top.float_approx));
      if(top.r_usd != null && top.r_pct != null){{
        setText('bear-spot-tf-kicker',
          'Short trade frame · ' + (top.stop_method||'ATR14') + ' stop · R = $' + Number(top.r_usd).toFixed(2)
          + ' (' + Number(top.r_pct).toFixed(1) + '%) · ' + (top.conviction_tag||'2R ladder') + ' · reference only, not advice');
      }}
      setText('bear-spot-br1', d.bearish_count||0);
      var hc=0; (d.top||[]).forEach(function(r){{ if((Number(r.score)||0) >= 25) hc++; }});
      setText('bear-spot-br2', hc);
      setText('bear-spot-br3', d.universe_size||0);
      var cb = document.getElementById('bear-spot-cerebro');
      if(cb){{ cb.setAttribute('href', '/cerebro/app/?ticker=' + encodeURIComponent(tk)
        + '&direction=short&source=scanner&channel=bear-spotlight&score=' + encodeURIComponent(top.score||0)
        + '&form=' + encodeURIComponent(firstForm)); }}
      var sec = document.getElementById('bear-spot-secfile');
      if(sec){{
        var spotSummary = (sigs.length ? sigs.join(' · ') : 'Bearish-flagged · no signal detail')
          + '|' + (d.bearish_count||0) + ' tickers flagged across ' + (d.universe_size||0) + ' filings scanned'
          + (top.bankruptcy ? '|⚠ Active bankruptcy filing' : '')
          + (top.delisting  ? '|⚠ Active delisting notice' : '');
        sec.setAttribute('data-ticker', tk);
        sec.setAttribute('data-form', firstForm);
        sec.setAttribute('data-summary', spotSummary);
        if(top.last_filing_link) sec.setAttribute('href', top.last_filing_link);
      }}
    }})
    .catch(function(e){{ setText('bear-spot-thesis','Could not load bearish data: '+e.message); }});
}})();
</script>

{pro_tails_block}

<!-- LIVE MARKET TICKER BAR -->
<div class="live-ticker-bar" id="live-ticker-bar">
  <div class="ltb-track" id="ltb-track" aria-label="Live market ticker">
    <div class="ltb-inner" id="ltb-inner">
      <div class="ltb-item" data-sym="SPY"><span class="ltb-sym">SPY</span><span class="ltb-price"><span class="ltb-skeleton">—</span></span><span class="ltb-chg flat"></span></div>
      <div class="ltb-item" data-sym="DIA"><span class="ltb-sym">DOW</span><span class="ltb-price"><span class="ltb-skeleton">—</span></span><span class="ltb-chg flat"></span></div>
      <div class="ltb-item" data-sym="QQQ"><span class="ltb-sym">QQQ</span><span class="ltb-price"><span class="ltb-skeleton">—</span></span><span class="ltb-chg flat"></span></div>
      <div class="ltb-item" data-sym="IWM"><span class="ltb-sym">RUT</span><span class="ltb-price"><span class="ltb-skeleton">—</span></span><span class="ltb-chg flat"></span></div>
      <div class="ltb-item" data-sym="VIX"><span class="ltb-sym">VIX</span><span class="ltb-price"><span class="ltb-skeleton">—</span></span><span class="ltb-chg flat"></span></div>
      <div class="ltb-item ltb-sep" data-sym="BTC-USD"><span class="ltb-sym">BTC</span><span class="ltb-price"><span class="ltb-skeleton">—</span></span><span class="ltb-chg flat"></span></div>
      <div class="ltb-item" data-sym="ETH-USD"><span class="ltb-sym">ETH</span><span class="ltb-price"><span class="ltb-skeleton">—</span></span><span class="ltb-chg flat"></span></div>
      <div class="ltb-item" data-sym="SOL-USD"><span class="ltb-sym">SOL</span><span class="ltb-price"><span class="ltb-skeleton">—</span></span><span class="ltb-chg flat"></span></div>
      <div class="ltb-item" data-sym="LTC-USD"><span class="ltb-sym">LTC</span><span class="ltb-price"><span class="ltb-skeleton">—</span></span><span class="ltb-chg flat"></span></div>
    </div>
    <div class="ltb-ts" id="ltb-ts"></div>
  </div>
</div>

<!-- SECTOR INTELLIGENCE HUB (sticky filter + detail cards) -->
{sector_filter_bar(sectors, darkpool=darkpool, pm_signals=pm_signals, all_rows=gappers + ranked + squeezes + insiders + darkpool)}
<div class="sector-detail-wrap" id="sectors">
  <div class="wrap">
    <p class="section-sub" style="margin:0 0 10px">Sectors with highest news velocity — stocks in hot sectors amplify catalyst moves. Click a sector above to filter all tables.</p>
    {sector_html(sectors, darkpool=darkpool, pm_signals=pm_signals)}
  </div>
</div>

<!-- SEC SECTOR HEATMAP -->
<div class="wrap solid-armor-card heavy-armor-card" id="heatmap-wrap">
  <div class="section-head heatmap-head" style="margin-bottom:8px">
    <h2>🌡️ SEC Sector Heatmap</h2>
    <span class="section-tag">Filing Activity · Today</span>
  </div>
  <p class="section-sub heatmap-sub" style="margin-bottom:12px"><strong>How to read this heatmap:</strong> <em>Block size</em> = total EDGAR filings today in that sector (bigger block = more filings). <em>Click any block</em> to drill down Sector → Industry Group → Industry → Sub-Industry (full GICS taxonomy, data-backed). Each tile shows its lead ticker + top score, and a <em>▲ xB / yBr (n)</em> readout — B = bullish filings (mergers, buybacks, insider buys), Br = bearish filings (offerings, dilution, defaults, delistings), (n) = filings with no sentiment signal. Only filings with explicit sentiment tags or inherently bearish form types (S-3, 424B, NT 10-K) are scored; routine filings without clear signals are counted but not assigned polarity. <em>Glow color</em> tracks conviction-weighted sentiment among scored filings — emerald when bullish score weight &gt; bearish, rose when bearish weight &gt; bullish, white when tied or no scored filings. Each filing contributes its own gapper_score as weight, so a single high-conviction S-3 shelf outweighs several routine 8-Ks. <em>Liquid fill level</em> = how dominant the winning side is by weight. Green fill rises for bullish-weighted sectors; rose fill rises for bearish-weighted sectors. 100% full = all one direction by weight. 50% = tied by weight or no scored filings. <em>⚡</em> = today&rsquo;s top-3 conviction sectors. <em>🏅</em> = Akerlof information-asymmetry signal. <em>🌐▲/▼</em> = sector macro tailwind / headwind.</p>
  <div id="heatmap-container" style="min-height:80px"></div>
  <div id="hm-drilldown" style="display:none"></div>
</div>

<!-- MAIN CONTENT -->
<div class="wrap">

  <!-- SCANNER FRESHNESS -->
  <div class="countdown-bar freshness-bar solid-armor-card heavy-armor-card" id="countdown-bar">
    <div class="freshness-head">
      <span class="cd-label">⚡ Scanner Ops Strip</span>
      <span class="freshness-badge" id="scanner-refresh-mode">Premarket publish</span>
    </div>
    <div class="freshness-strip">
      <div class="freshness-card">
        <span class="freshness-kicker">Mode</span>
        <span class="freshness-value">Premarket core build</span>
      </div>
      <div class="freshness-card">
        <span class="freshness-kicker">Next refresh</span>
        <span class="freshness-value" id="countdown"></span>
      </div>
      <div class="freshness-card">
        <span class="freshness-kicker">Last publish</span>
        <span class="freshness-value" id="scanner-last-refresh">{NOW_ET}</span>
      </div>
      <div class="freshness-card">
        <span class="freshness-kicker">Quote layer</span>
        <span class="freshness-value" id="scanner-price-cd">—</span>
      </div>
    </div>
    <div class="freshness-foot">The core pre-market build publishes at <strong>3:30 AM ET</strong>. The public Scanner refreshes again at <strong>10:05 AM ET</strong> and hourly through <strong>4:05 PM ET</strong> on market days.</div>
  </div>

  <!-- BIAS ACK — both directions of revenue (mirror_bear_2026-04-26) -->
  <div style="max-width:1180px;margin:18px auto 0;padding:0 18px">
    <div style="background:linear-gradient(135deg,rgba(63,185,80,.06),rgba(247,129,102,.06));border:1px solid rgba(247,129,102,.22);border-radius:10px;padding:12px 16px;font-size:13px;color:#c9d1d9">
      <strong style="color:#e6edf3">Bullish-biased by default.</strong>
      This scanner surfaces <em>long</em> setups (gap plays, squeeze candidates, insider buys, value/moat).
      For the bearish counterpart — dilution risk (S-3, 424B), restatements (Item 4.02), bankruptcy
      (Item 1.03), late filings (NT-10K), insider cluster sells —
      see <a href="/short-scanner/" style="color:#f78166;font-weight:700">📉 SHORT scanner</a>.
      Profit isn't direction-specific; transparency about which side we're flagging is.
    </div>
  </div>

  <!-- GAP PLAYS -->
  <div class="section" id="gaps">
  <div class="section-head">
      <h2>🚀 Top Gap Candidates</h2>
      <span class="section-tag">{TODAY}</span>
    </div>
    <p class="section-sub">Tickers whose SEC filings score high on catalyst strength — ranked by filing type, sentiment tags, filing recency, and time-of-day boost, then multiplied by sector macro tailwind and Nobel Physics signal. Not a pre-market price gap.
    Score 9+ = strong catalyst. 6–8 = watch. Below 6 = speculative.</p>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#3fb950"></div>High (9+)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#d29922"></div>Medium (6–8)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#f0883e"></div>Watch (3–5)</div>
    </div>
    <div class="gap-burn-shell solid-armor-card heavy-armor-card">
      <div class="sparkles-core" data-particle-color="#10b981" data-particle-density="400" data-min-size="0.4" data-max-size="1.2" data-speed="1.5" data-background="transparent" aria-hidden="true"></div>
      <div class="gap-burn-content">
        {gap_rows(gappers, stooq_cache, opts_map, macro_tw, _nobel_raw, _insider_map, combo_map, congress_map)}
        <div class="sector-empty-msg"></div>
      </div>
    </div>
  </div>

  {options_sect}

  <!-- RANKED -->
  <div class="section" id="ranked">
    <div class="section-head">
      <h2>📊 SEC Catalyst Ranked</h2>
      <span class="section-tag">Combined Score</span>
    </div>
    <p class="section-sub">Priority score combines filing type strength (form weight × 4), filing recency, and ticker quality (clean common symbols ranked higher, oddly-suffixed preferred-share tickers penalized).
    Above 50 = high conviction. 30–50 = solid setup.</p>
    {intel_table_shell(
        "intel-shell-ranked",
        "Catalyst conviction ledger",
        "Filing strength, recency, and symbol quality fused into one priority score.",
        "High combined score means multiple scoring vectors agreed, not just one outlier metric.",
        "SEC//RANK",
        [
            intel_stat_chip("entries", str(len(ranked))),
            intel_stat_chip("threshold", "50+"),
        ],
        f'''
    <div class="tbl-wrap">
      <table class="sortable intel-table">
        <thead><tr>
          <th data-sort="str">Ticker</th>
          <th data-sort="num">Conviction</th>
          <th data-sort="str">Filing</th>
          <th data-sort="str">Age</th>
          <th style="width:36px">AI</th>
        </tr></thead>
        <tbody>{ranked_rows(ranked, stooq_cache, opts_map, combo_map, congress_map)}</tbody>
      </table>
    </div>''',
        "Above 50 = high conviction. 30–50 = solid setup. Below 30 = speculative or tail-end.",
    )}
    <div class="sector-empty-msg"></div>
  </div>

  {squeeze_sect}

  {insider_sect}

  {darkpool_sect}

  {trackrecord_sect}

  {pm_sect}

  <!-- VS COMPETITORS -->
  <div class="section" id="compare">
    <div class="section-head">
      <h2>💰 What Others Charge for Less</h2>
      <span class="section-tag">March 2026 Pricing</span>
    </div>
    <p class="section-sub">If you're looking for a free Benzinga Pro alternative or tired of paying for delayed Finviz data,
    Catalyst Edge delivers institutional-grade pre-market intelligence before the opening bell — at no cost.</p>
    {intel_table_shell(
        "intel-shell-compare",
        "Competitive pricing matrix",
        "Side-by-side coverage of SEC scoring, squeeze, block volume, and insider clusters vs paid competitors.",
        "Only Catalyst Edge delivers the full stack free and publishes the page before 4 AM ET.",
        "COMP//PRICE",
        [
            intel_stat_chip("peers", "5"),
            intel_stat_chip("our cost", "FREE"),
        ],
        '''
    <div class="tbl-wrap">
      <table class="intel-table">
        <thead><tr>
          <th>Tool</th><th>Price</th><th>SEC Scored</th><th>Squeeze</th><th>Dark Pool</th><th>Insider Clusters</th><th>Before 4 AM</th><th>Public Page</th>
        </tr></thead>
        <tbody>
          <tr><td><strong>Benzinga Pro</strong></td><td style="color:#f78166">$197/mo</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td></tr>
          <tr><td><strong>Trade-Ideas</strong></td><td style="color:#f78166">$127/mo</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#d29922">~</td><td style="color:#f78166">✗</td></tr>
          <tr><td><strong>Unusual Whales</strong></td><td style="color:#f78166">$50/mo</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#3fb950">✓</td><td style="color:#d29922">~</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td></tr>
          <tr><td><strong>Finviz Elite</strong></td><td style="color:#d29922">$25/mo</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#d29922">~</td><td style="color:#d29922">~</td><td style="color:#d29922">Delayed</td></tr>
          <tr><td><strong>Scanz</strong></td><td style="color:#f78166">$169/mo</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#f78166">✗</td><td style="color:#3fb950">✓</td><td style="color:#f78166">✗</td></tr>
          <tr style="background:#1a2e1a22;outline:1px solid #2ea04333">
            <td><strong style="color:#3fb950">Catalyst Edge</strong></td>
            <td><a href="#subscribe" class="compare-free-link" style="color:#3fb950;font-weight:800;text-decoration:none">FREE →</a></td>
            <td style="color:#3fb950">✓</td><td style="color:#3fb950">✓</td>
            <td style="color:#3fb950">✓</td><td style="color:#3fb950">✓</td>
            <td style="color:#3fb950">✓</td><td style="color:#3fb950">✓</td>
          </tr>
        </tbody>
      </table>
    </div>''',
        "Benzinga Pro at $197/mo = $2,364/yr for fewer signals, no public page, and no pre-4AM delivery.",
    )}
    <div class="free-forever-box" style="margin-top:14px">
      <strong style="color:#3fb950">Free Forever Commitment:</strong>
      Top 10 picks, squeeze radar, block volume signals, and insider clusters are free with no account required.
      We monetize through Premium — not by paywalling the core signal.
      VC-backed competitors cannot match this without destroying their revenue model.
    </div>
  </div>

  <!-- INSTITUTIONAL / API CALLOUT -->
  <div class="section" id="api" style="background:linear-gradient(135deg,#0f1f2e 0%,#0d1117 100%);
    border:1px solid #1a3a5c;border-radius:12px;padding:32px">
    <div style="display:flex;align-items:flex-start;gap:24px;flex-wrap:wrap">
      <div style="flex:1;min-width:220px">
        <div style="font-size:.78em;font-weight:600;color:#58a6ff;text-transform:uppercase;
          letter-spacing:.08em;margin-bottom:10px">For Quants &amp; Prop Desks</div>
        <h2 style="font-size:1.35em;font-weight:800;margin-bottom:10px;line-height:1.3">
          Catalyst Edge Data API</h2>
        <p style="color:#8b949e;font-size:.9em;line-height:1.6;margin-bottom:16px">
          The same engine that powers this scanner delivers a structured JSON/CSV feed
          to your Python model by <strong style="color:#e6edf3">3:30 AM ET</strong> —
          {_n_filings or '300+' } filings scored, {total_t}+ tickers, 15 fields per row. No scraping required.
        </p>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px">
          <span style="background:#1a2e1a;color:#3fb950;border:1px solid #3fb95044;
            border-radius:4px;padding:3px 10px;font-size:.78em;font-weight:600">{_LIVE_HIT2:.0f}% hit +2%</span>
          <span style="background:#1a2e1a;color:#3fb950;border:1px solid #3fb95044;
            border-radius:4px;padding:3px 10px;font-size:.78em;font-weight:600">90-day track record</span>
          <span style="background:#1a2e1a;color:#3fb950;border:1px solid #3fb95044;
            border-radius:4px;padding:3px 10px;font-size:.78em;font-weight:600">CSV · JSON · REST</span>
        </div>
        <a href="/api/" target="_blank" rel="noopener noreferrer"
          style="display:inline-block;background:#58a6ff;color:#0d1117;
          padding:10px 22px;border-radius:8px;font-weight:700;font-size:.88em;
          text-decoration:none">View API Docs &amp; Pricing →</a>
      </div>
      <div style="min-width:200px;background:#161b22;border:1px solid #21262d;
        border-radius:8px;padding:16px;font-family:monospace;font-size:.78em;
        color:#3fb950;line-height:1.8">
        <span style="color:#8b949e"># Python — one line to pull the feed</span><br>
        df = catalyst_edge.today(<br>
        &nbsp;&nbsp;category=<span style="color:#a5d6ff">"gapper"</span>,<br>
        &nbsp;&nbsp;min_score=<span style="color:#f0883e">14</span><br>
        )<br><br>
        <span style="color:#8b949e"># 3:30 AM ET, every trading day</span>
      </div>
    </div>
  </div>

  <!-- INLINE EMAIL CAPTURE -->
  <div class="section email-capture-section" id="subscribe">
    <div class="capture-card">
      <div class="capture-left">
        <div class="capture-label">📬 Free Daily Email</div>
        <h2 class="capture-h">Get tomorrow's picks before 4 AM ET</h2>
        <p class="capture-sub">SEC catalyst scores · Squeeze radar · Dark pool signals · Insider clusters<br>
        Delivered free every weekday morning before pre-market opens.</p>
        <div class="capture-proof">
          <span class="proof-item">✅ No credit card</span>
          <span class="proof-item">✅ No paywalls</span>
          <span class="proof-item">✅ Cancel anytime</span>
        </div>
      </div>
      <div class="capture-right">
        <form class="capture-form" onsubmit="handleSubscribe(event)">
          <input type="email" placeholder="your@email.com"
            required class="email-input">
          <button type="submit" class="btn btn-green capture-btn">Subscribe Free →</button>
        </form>
        <p class="capture-fine">Joining <strong>active traders</strong> who get this every morning.
        Unsubscribe anytime.</p>
      </div>
    </div>
  </div>

  <!-- HOW IT WORKS -->
  <div class="section">
    <div class="section-head"><h2>⚙️ How It Works</h2></div>
    <div class="how-grid">
      <div class="how-card">
        <div class="how-num">01</div>
        <h3>EDGAR Scan — 3:00 AM ET</h3>
        <p>Every 8-K, Form 4, S-3, 13D/G, and NT filing from overnight is fetched and parsed from SEC EDGAR.</p>
      </div>
      <div class="how-card">
        <div class="how-num">02</div>
        <h3>Score & Rank — 3:15 AM ET</h3>
        <p>Each ticker is scored on filing type strength, sentiment tags, filing recency, time-of-day boost, sector macro tailwind, and Nobel Physics signal.</p>
      </div>
      <div class="how-card">
        <div class="how-num">03</div>
        <h3>Squeeze & Dark Pool — 3:20 AM ET</h3>
        <p>Short float, days-to-cover, gamma exposure, and block trade volume layered in for context.</p>
      </div>
      <div class="how-card">
        <div class="how-num">04</div>
        <h3>Delivered by 4 AM ET</h3>
        <p>Free newsletter hits your inbox before pre-market. Premium subscribers get the full 1,600+ ticker CSV.</p>
      </div>
    </div>
  </div>

  <!-- CTA -->
  <div class="cta-block">
    <h2>Get Tomorrow's Picks Free</h2>
    <p>Join active traders getting SEC catalyst intelligence before the market opens every weekday morning.</p>
    <button onclick="var p=document.getElementById('sub-popup');if(p){{p.classList.add('visible');document.getElementById('sub-popup-email').focus();}}" class="btn btn-green" style="font-size:1.05em">
      Subscribe Free →
    </button>
    <div class="cta-links">
      <a href="/cheat-sheet/" style="color:var(--green);font-weight:700">Download Free SEC Filing Cheat Sheet</a>
      <br>
      Live alerts:
      <a href="https://t.me/CatalystEdgePro" target="_blank" rel="noopener noreferrer">Telegram</a> ·
      <a href="https://discord.gg/8aJEHghHVy" target="_blank" rel="noopener noreferrer">Discord</a> ·
      <a href="https://twitter.com/CatalystEdgePro" target="_blank" rel="noopener noreferrer">X / Twitter</a>
    </div>
  </div>

</div><!-- /wrap -->

<!-- RECOMMENDED BROKERS & AI-TRADING VENUES -->
<div class="broker-section">
  <h3>🏦 Brokers, Research &amp; AI-Trading Venues</h3>
  <div class="broker-sub">Platforms our readers use to trade SEC catalysts — human brokers, deep-research, AI-native execution, and signal marketplaces</div>
  <ul class="broker-list">
    <li><a href="https://catalystedgescanner.com/go/moomoo" target="_blank" rel="noopener noreferrer">Moomoo ⭐</a> <span>— Free Level 2 data · pre-market · highest signup bonus</span></li>
    <li><a href="https://catalystedgescanner.com/go/simplywallst" target="_blank" rel="noopener noreferrer">Simply Wall St ⭐</a> <span>— Deep-research dashboards · 14-day extended trial · pairs with our DCF</span></li>
    <li><a href="https://catalystedgescanner.com/go/webull" target="_blank" rel="noopener noreferrer">Webull</a> <span>— Free stocks on signup · real-time Level 1</span></li>
    <li><a href="https://catalystedgescanner.com/go/tradier" target="_blank" rel="noopener noreferrer">Tradier</a> <span>— $0 options · cleanest API for algo</span></li>
    <li><a href="https://catalystedgescanner.com/go/public" target="_blank" rel="noopener noreferrer">Public.com</a> <span>— Fractional shares · themes &amp; indexes</span></li>
    <li><a href="https://catalystedgescanner.com/go/alpaca" target="_blank" rel="noopener noreferrer">Alpaca</a> <span>— API-first broker · free US equities + options for AI bots</span></li>
    <li><a href="https://catalystedgescanner.com/go/ibkr" target="_blank" rel="noopener noreferrer">Interactive Brokers</a> <span>— TWS API · real borrow availability + NBBO</span></li>
    <li><a href="https://catalystedgescanner.com/go/composer" target="_blank" rel="noopener noreferrer">Composer.trade</a> <span>— Build &amp; auto-execute algorithmic strategies</span></li>
    <li><a href="https://catalystedgescanner.com/go/numerai" target="_blank" rel="noopener noreferrer">Numerai Signals</a> <span>— Hedge fund pays for accurate ticker predictions</span></li>
  </ul>
</div>

<!-- FOOTER -->
<footer>
  <div>Catalyst Edge — Free Daily SEC EDGAR Gap Scanner · {TODAY}</div>
  <div class="footer-links">
    <a href="https://catalystedge.agency" target="_blank" rel="noopener noreferrer">Newsletter</a>
    <a href="https://t.me/CatalystEdgePro" target="_blank" rel="noopener noreferrer">Telegram</a>
    <a href="https://discord.gg/8aJEHghHVy" target="_blank" rel="noopener noreferrer">Discord</a>
    <a href="https://twitter.com/CatalystEdgePro" target="_blank" rel="noopener noreferrer">X / Twitter</a>
    <a href="/methodology/">How It Works</a>
    <a href="/how-to-trade-8k/">8-K Guide</a>
  </div>
  <div class="disclaimer">Data sourced from public SEC EDGAR filings. Not financial advice.
  For informational purposes only. Always do your own research before trading.<br>
  <a href="/methodology/" style="color:var(--muted);text-decoration:underline">
  Scoring methodology &amp; data sources explained →</a></div>
</footer>

</div><!-- /scanner-posture-shell -->

<!-- STICKY PREMIUM BAR (desktop + mobile) -->
<div class="premium-sticky-bar" id="premium-sticky-bar">
  <div class="premium-sticky-inner">
    <span class="premium-sticky-text">🔒 <strong>{len(gappers) - FREE_GAP_LIMIT}+ gated picks</strong> today · Full dataset, CSV export, Cerebro HUD</span>
    <div class="premium-sticky-btns">
      <a href="{STRIPE_READER}" target="_blank" class="premium-sticky-btn reader">Reader $9/mo</a>
      <a href="{STRIPE_PRO}" target="_blank" class="premium-sticky-btn pro">Pro $39/mo</a>
    </div>
    <button class="premium-sticky-close" id="premium-sticky-close" aria-label="Dismiss">✕</button>
  </div>
</div>

<!-- STICKY MOBILE SUBSCRIBE BAR -->
<div class="mobile-sub-bar" id="mobile-sub-bar" role="complementary">
  <div class="mobile-sub-bar-text">
    <strong>📬 Get 4 AM picks free</strong>
    SEC catalyst alerts before market open
  </div>
  <button class="mobile-sub-bar-btn" id="mobile-sub-bar-btn">Subscribe →</button>
  <button class="mobile-sub-bar-close" id="mobile-sub-bar-close" aria-label="Dismiss">✕</button>
</div>

<!-- SUBSCRIBE POPUP -->
<div class="sub-popup" id="sub-popup" role="dialog" aria-label="Subscribe to newsletter">
  <button class="sub-popup-close" id="sub-popup-close" aria-label="Close">✕</button>
  <h4>📬 Free pre-market picks</h4>
  <p>SEC catalyst scans delivered before 4am ET. Free, forever.</p>
  <div id="sub-popup-body">
    <form class="sub-popup-form" id="sub-popup-form" onsubmit="handlePopupSubscribe(event)">
      <input class="sub-popup-input" id="sub-popup-email" type="email"
             placeholder="your@email.com" autocomplete="email" required>
      <button class="sub-popup-btn" type="submit">Subscribe</button>
    </form>
    <div class="sub-popup-fine">No spam. Unsubscribe anytime.</div>
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.08);font-size:.78em;color:var(--muted)">
      Want the full dataset? <a href="https://buy.stripe.com/your-link" target="_blank" style="color:var(--gold);font-weight:600">Upgrade to Premium — $9/mo →</a>
    </div>
  </div>
  <div class="sub-popup-success" id="sub-popup-success">
    <span>✅</span>
    <p>Check your inbox!</p>
    <small>Confirm your email to start receiving picks.</small>
  </div>
</div>

<!-- EDGE PRO UNLOCK POPUP -->
<div class="edge-unlock-popup" id="edge-unlock-popup" role="dialog" aria-label="Unlock Edge Pro">
  <div class="edge-unlock-panel">
    <button class="edge-unlock-close" type="button" onclick="closeEdgeUnlock()" aria-label="Close">✕</button>
    <h3>Unlock Edge Pro on this device</h3>
    <p>Enter the email on your Edge Pro subscription. We'll send a one-click unlock link —
       no password, no copy-paste. The link works for 24 hours and keeps this device
       unlocked for 90 days.</p>
    <form class="edge-unlock-form" id="edge-unlock-form" onsubmit="handleEdgeUnlock(event)">
      <input class="edge-unlock-input" id="edge-unlock-email" type="email"
             placeholder="you@example.com" autocomplete="email" required>
      <button class="edge-unlock-submit" type="submit">Send link</button>
    </form>
    <div class="edge-unlock-msg" id="edge-unlock-msg"></div>
    <details class="edge-unlock-paste">
      <summary>Already got a link? Paste it to unlock this browser.</summary>
      <p>Some mobile email apps open links in a browser that can't save cookies.
         If your link didn't unlock this browser, copy the full URL from the email
         (starts with <code>https://catalystedgescanner.com/api/unlock/claim?t=…</code>)
         and paste it here.</p>
      <form id="edge-unlock-paste-form" onsubmit="handlePasteUnlock(event)">
        <input class="edge-unlock-paste-input" id="edge-unlock-paste-input"
               type="text" autocomplete="off" autocapitalize="off"
               spellcheck="false"
               placeholder="Paste your unlock link here…">
        <button class="edge-unlock-paste-btn" type="submit">Unlock this browser</button>
      </form>
      <div class="edge-unlock-msg" id="edge-unlock-paste-msg"></div>
    </details>
  </div>
</div>
<div class="edge-toast" id="edge-toast">✓ Edge Pro unlocked on this device</div>
<a class="edge-billing-link" href="/api/billing/portal" title="Cancel, update card, or change plan via Stripe">⚙ Manage subscription</a>

<script>
// ── Edge Pro tier check ───────────────────────────────────────────────
(function(){{
  function applyPro(email, tier){{
    var t = tier || 'pro';
    if (t !== 'pro' && t !== 'admin' && t !== 'reader') t = 'pro';
    document.body.setAttribute('data-tier', t);
    if (email) document.body.setAttribute('data-tier-email', email);
    try {{
      sessionStorage.setItem('edge_tier', t);
      if (email) sessionStorage.setItem('edge_tier_email', email);
    }} catch(e) {{}}
  }}
  function showToast(){{
    var t = document.getElementById('edge-toast');
    if (t){{ t.classList.add('visible'); setTimeout(function(){{t.classList.remove('visible');}}, 4000); }}
  }}

  var qs;
  try {{ qs = new URLSearchParams(location.search); }} catch(e) {{ qs = null; }}

  // Session fallback — if we unlocked earlier in this session, keep tier on nav.
  try {{
    var _st = sessionStorage.getItem('edge_tier');
    if (_st === 'pro' || _st === 'admin' || _st === 'reader') {{
      applyPro(sessionStorage.getItem('edge_tier_email') || '', _st);
    }}
  }} catch(e) {{}}

  // Path A: short-lived signed unlock_ok token in URL (cookie-loss fallback).
  if (qs && qs.get('unlock_ok')) {{
    fetch('/api/unlock/verify?t=' + encodeURIComponent(qs.get('unlock_ok')), {{credentials:'include'}})
      .then(function(r){{return r.json();}})
      .then(function(d){{
        if (d && (d.tier === 'pro' || d.tier === 'admin' || d.tier === 'reader')) {{ applyPro(d.email || '', d.tier); showToast(); }}
      }}).catch(function(){{}});
    qs.delete('unlock_ok');
    history.replaceState({{}}, '', location.pathname + (qs.toString() ? '?' + qs.toString() : ''));
  }}

  // Path B: long-lived HttpOnly cookie — works on every subsequent visit.
  fetch('/api/tier', {{credentials: 'include'}}).then(function(r){{return r.json();}}).then(function(d){{
    if (d && (d.tier === 'pro' || d.tier === 'admin' || d.tier === 'reader')) {{ applyPro(d.email || '', d.tier); }}
  }}).catch(function(){{}});

  // Toast / error banners from legacy query params.
  try {{
    if (qs && qs.get('unlocked') === '1') {{
      setTimeout(showToast, 400);
      qs.delete('unlocked');
      history.replaceState({{}}, '', location.pathname + (qs.toString() ? '?' + qs.toString() : ''));
    }} else if (qs && qs.get('unlock_error')) {{
      var msg = qs.get('unlock_error') === 'expired' ? 'Unlock link expired — request a new one.' : 'Unlock link was invalid.';
      alert(msg);
      qs.delete('unlock_error');
      history.replaceState({{}}, '', location.pathname + (qs.toString() ? '?' + qs.toString() : ''));
    }}
  }} catch(e) {{}}
}})();

function openEdgeUnlock(){{
  var p = document.getElementById('edge-unlock-popup');
  if (!p) return;
  p.classList.add('visible');
  var i = document.getElementById('edge-unlock-email');
  if (i) {{ setTimeout(function(){{i.focus();}}, 50); }}
}}
function closeEdgeUnlock(){{
  var p = document.getElementById('edge-unlock-popup');
  if (p) p.classList.remove('visible');
  var m = document.getElementById('edge-unlock-msg');
  if (m) {{ m.textContent = ''; m.className = 'edge-unlock-msg'; }}
}}
function handleEdgeUnlock(ev){{
  ev.preventDefault();
  var email = (document.getElementById('edge-unlock-email').value || '').trim();
  var msg = document.getElementById('edge-unlock-msg');
  if (!email || email.indexOf('@') < 0) {{
    msg.className = 'edge-unlock-msg err'; msg.textContent = 'Please enter a valid email.'; return;
  }}
  msg.className = 'edge-unlock-msg'; msg.textContent = 'Sending…';
  fetch('/api/unlock/request', {{
    method: 'POST', credentials: 'include',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{email: email}})
  }}).then(function(r){{return r.json();}}).then(function(d){{
    if (d && (d.status === 'sent_if_premium')) {{
      msg.className = 'edge-unlock-msg ok';
      msg.textContent = '✓ If that email is on an Edge Pro subscription, a link is on its way. Check your inbox.';
    }} else if (d && d.error === 'rate_limit') {{
      msg.className = 'edge-unlock-msg err';
      msg.textContent = 'Too many requests. Try again in an hour.';
    }} else {{
      msg.className = 'edge-unlock-msg err';
      msg.textContent = 'Something went wrong. Try again.';
    }}
  }}).catch(function(){{
    msg.className = 'edge-unlock-msg err';
    msg.textContent = 'Network error. Try again.';
  }});
}}
function handlePasteUnlock(ev){{
  ev.preventDefault();
  var raw = (document.getElementById('edge-unlock-paste-input').value || '').trim();
  var msg = document.getElementById('edge-unlock-paste-msg');
  if (!raw) {{
    msg.className = 'edge-unlock-msg err';
    msg.textContent = 'Paste the full unlock link from your email.';
    return;
  }}
  msg.className = 'edge-unlock-msg'; msg.textContent = 'Unlocking…';
  fetch('/api/unlock/exchange', {{
    method: 'POST', credentials: 'include',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{url: raw}})
  }}).then(function(r){{return r.json().then(function(d){{return [r.status, d];}});}})
    .then(function(pair){{
      var status = pair[0], d = pair[1];
      if (status === 200 && d && d.tier === 'pro') {{
        msg.className = 'edge-unlock-msg ok';
        msg.textContent = '✓ Unlocked. Reloading…';
        try {{
          document.body.setAttribute('data-tier', 'pro');
          if (d.email) document.body.setAttribute('data-tier-email', d.email);
          sessionStorage.setItem('edge_tier', 'pro');
          if (d.email) sessionStorage.setItem('edge_tier_email', d.email);
        }} catch(e) {{}}
        setTimeout(function(){{ location.reload(); }}, 700);
      }} else {{
        msg.className = 'edge-unlock-msg err';
        if (d && d.error === 'expired') {{
          msg.textContent = 'That link expired. Request a new one above.';
        }} else if (d && d.error === 'invalid') {{
          msg.textContent = "Couldn't read that link. Copy the whole URL from the email, including the part after ?t=.";
        }} else if (d && d.error === 'no token in input') {{
          msg.textContent = 'No unlock token found in that text. Paste the full URL.';
        }} else {{
          msg.textContent = 'Unlock failed. Request a fresh link above.';
        }}
      }}
    }}).catch(function(){{
      msg.className = 'edge-unlock-msg err';
      msg.textContent = 'Network error. Try again.';
    }});
}}
</script>

<script>
// ── Embedded data ─────────────────────────────────────────────────────
var _heatmapData = {heatmap_json};

// REEL_H must be declared here (before the countdown IIFE) so buildReel()
// has the correct value. The Slot Reel Engine block further below also sets
// this, but var assignments are NOT hoisted — only declarations are.
var REEL_H = 1.15; // em — must match .reel-strip>span height in CSS
var ET_CLOCK_FMT = new Intl.DateTimeFormat('en-US', {{
  timeZone: 'America/New_York',
  weekday: 'short',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
}});
var SCANNER_RUNTIME = {{
  clientQuotes: {str(SCANNER_ENABLE_CLIENT_QUOTES).lower()},
  finnhubWs: {str(SCANNER_ENABLE_FINNHUB_WS).lower()},
  polymarketRefresh: {str(SCANNER_ENABLE_POLYMARKET_REFRESH).lower()},
  quoteApi: '/api/scanner/quotes',
  liquidityQuotes: false,
  proxyCooldownMs: 180000
}};

function getETParts(date) {{
  var out = {{}};
  ET_CLOCK_FMT.formatToParts(date || new Date()).forEach(function(part) {{
    if (part.type !== 'literal') out[part.type] = part.value;
  }});
  return {{
    weekday: out.weekday,
    year: parseInt(out.year, 10),
    month: parseInt(out.month, 10),
    day: parseInt(out.day, 10),
    hour: parseInt(out.hour, 10),
    minute: parseInt(out.minute, 10),
    second: parseInt(out.second, 10),
  }};
}}

function isETWeekday(parts) {{
  return parts.weekday !== 'Sat' && parts.weekday !== 'Sun';
}}

function etDecimalHour(parts) {{
  return parts.hour + (parts.minute / 60);
}}

function formatETClock(date) {{
  var parts = getETParts(date || new Date());
  var hour12 = parts.hour % 12 || 12;
  return hour12 + ':' + String(parts.minute).padStart(2, '0');
}}

var _scannerProxyState = {{
  failures: 0,
  cooldownUntil: 0
}};

function scannerProxyJson(rawUrl, timeoutMs) {{
  var now = Date.now();
  if (now < _scannerProxyState.cooldownUntil) {{
    return Promise.reject(new Error('scanner proxy cooldown'));
  }}
  var ctrl = new AbortController();
  var tid = setTimeout(function() {{ ctrl.abort(); }}, timeoutMs || 5000);
  return fetch('https://api.allorigins.win/raw?url=' + encodeURIComponent(rawUrl), {{
    signal: ctrl.signal,
    cache: 'no-store'
  }})
    .then(function(r) {{
      clearTimeout(tid);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      _scannerProxyState.failures = 0;
      return r.json();
    }})
    .catch(function(err) {{
      clearTimeout(tid);
      _scannerProxyState.failures += 1;
      if (_scannerProxyState.failures >= 2) {{
        _scannerProxyState.cooldownUntil = Date.now() + (SCANNER_RUNTIME.proxyCooldownMs || 180000);
      }}
      throw err;
    }});
}}

function scannerQuoteJson(symbols, timeoutMs) {{
  if (!SCANNER_RUNTIME.clientQuotes) return Promise.resolve([]);
  var unique = [];
  var seen = {{}};
  (symbols || []).forEach(function(symbol) {{
    var s = String(symbol || '').trim().toUpperCase();
    if (!s || seen[s]) return;
    seen[s] = 1;
    unique.push(s);
  }});
  if (!unique.length) return Promise.resolve([]);
  var ctrl = new AbortController();
  var tid = setTimeout(function() {{ ctrl.abort(); }}, timeoutMs || 6000);
  return fetch((SCANNER_RUNTIME.quoteApi || '/api/scanner/quotes') + '?tickers=' + encodeURIComponent(unique.join(',')), {{
    signal: ctrl.signal,
    cache: 'no-store'
  }})
    .then(function(r) {{
      clearTimeout(tid);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }})
    .then(function(d) {{
      return (d && d.quotes) || [];
    }})
    .catch(function(err) {{
      clearTimeout(tid);
      throw err;
    }});
}}

function nextScannerRefreshInfo(fromDate) {{
  var probe = new Date((fromDate || new Date()).getTime());
  probe.setMilliseconds(0);
  probe.setSeconds(0);
  probe.setMinutes(probe.getMinutes() + 1);

  for (var i = 0; i < 60 * 24 * 7; i++) {{
    var parts = getETParts(probe);
    var total = parts.hour * 60 + parts.minute;
    var isPremarketPublish = total === (3 * 60 + 30);
    var isIntradayRefresh = parts.minute === 5 && parts.hour >= 10 && parts.hour <= 16;
    if (isETWeekday(parts) && (isPremarketPublish || isIntradayRefresh)) {{
      return {{
        targetTs: probe.getTime(),
        label: isPremarketPublish ? 'Premarket publish' : 'Intraday refresh',
      }};
    }}
    probe.setMinutes(probe.getMinutes() + 1);
  }}

  return {{ targetTs: (fromDate || new Date()).getTime(), label: 'Refresh pending' }};
}}

// ── Countdown to next Scanner refresh — Slot Reel Edition ───────────────────
(function() {{
  var el = document.getElementById('countdown');
  var modeEl = document.getElementById('scanner-refresh-mode');
  if (!el) return;
  var _inited = false;
  var _nextRefresh = null;

  function tick() {{
    var now = new Date();
    if (!_nextRefresh || now.getTime() >= _nextRefresh.targetTs) {{
      _nextRefresh = nextScannerRefreshInfo(now);
    }}

    if (modeEl && _nextRefresh) modeEl.textContent = _nextRefresh.label;

    var diff = Math.max(0, _nextRefresh.targetTs - now.getTime());
    var h  = Math.floor(diff / 3600000);
    var m  = Math.floor((diff % 3600000) / 60000);
    var s  = Math.floor((diff % 60000) / 1000);
    var str = String(h).padStart(2, '0') + ':' +
              String(m).padStart(2, '0') + ':' +
              String(s).padStart(2, '0');

    if (!_inited) {{
      el.innerHTML = '';
      reelInit(el, str, null);
      _inited = true;
    }} else {{
      reelUpdate(el, str, null, null);
    }}
  }}

  tick();
  setInterval(tick, 1000);
}})();

// Sortable tables
// ── Plain-English filing tooltips ────────────────────────────────────
(function() {{
  var TIPS = {{
    '8-K':    'Major company announcement — earnings, M&A, exec change, or material event. Highest gap potential.',
    '4':      'Insider trade — officer or director bought/sold shares. Cluster of buys = bullish signal.',
    'S-3':    'Shelf offering registration — company may sell more shares. Dilution risk, watch for price pressure.',
    'S-1':    'IPO or new stock registration. Early-stage offering, high volatility.',
    '13D':    'Activist investor disclosure — someone bought >5% stake with intent to influence management.',
    '13G':    'Passive 5%+ stake disclosure — large fund accumulated a position.',
    'SC 13D': 'Activist investor disclosed a large stake. Often precedes board changes or buyout talks.',
    'SC 13G': 'Passive fund crossed 5% ownership threshold.',
    '6-K':    'Foreign private issuer report — equivalent of 8-K for non-US companies.',
    'NT':     'Late filing notice — company missed its reporting deadline. May indicate financial distress.',
    '424B2':  'Prospectus supplement for a securities offering. Typically dilutive — approach with caution.',
    '424B3':  'Prospectus supplement — lower dilution risk than B2, monitor volume.',
    '424B4':  'Final prospectus for a public offering. Near-term supply pressure.',
    '424B5':  'Pricing supplement for an offering already on file.',
    'DEF 14A':'Proxy statement — shareholder vote upcoming (M&A approval, board election, pay packages).',
    'DEFA14A':'Additional proxy material — often signals contested vote or activist campaign.',
    '8-K/A':  'Amendment to a prior 8-K — company is correcting or expanding a major announcement.',
    'S-4':    'Business combination registration — typically signals M&A, merger, or acquisition.',
    'F-3':    'Foreign issuer shelf registration — similar dilution risk as S-3.',
  }};
  document.querySelectorAll('.form-badge,.badge-form').forEach(function(el) {{
    var form = el.textContent.trim();
    var tip  = TIPS[form];
    if (tip) el.setAttribute('data-tip', tip);
  }});
}})();

document.querySelectorAll('table.sortable').forEach(function(table) {{
  table.querySelectorAll('th').forEach(function(th, colIdx) {{
    th.addEventListener('click', function() {{
      const tbody = table.querySelector('tbody');
      const rows  = Array.from(tbody.querySelectorAll('tr'));
      const asc   = th.classList.toggle('sort-asc');
      th.classList.toggle('sort-desc', !asc);
      table.querySelectorAll('th').forEach(function(t) {{
        if (t !== th) {{ t.classList.remove('sort-asc','sort-desc'); }}
      }});
      const sortType = th.dataset.sort || 'str';
      rows.sort(function(a, b) {{
        const av = (a.cells[colIdx] || {{}}).textContent.trim().replace(/[^0-9.\\-]/g,'') || '0';
        const bv = (b.cells[colIdx] || {{}}).textContent.trim().replace(/[^0-9.\\-]/g,'') || '0';
        const cmp = sortType === 'num'
          ? (parseFloat(av)||0) - (parseFloat(bv)||0)
          : av.localeCompare(bv);
        return asc ? cmp : -cmp;
      }});
      rows.forEach(function(r) {{ tbody.appendChild(r); }});
    }});
  }});
}});

// ── Subscribe helper (self-hosted) ───────────────────────────────────
function _doSubscribe(email, onSuccess, onError) {{
  if (typeof gtag === 'function') {{
    gtag('event', 'subscribe_click', {{event_category:'engagement', event_label:'email_capture'}});
  }}
  fetch('/api/subscribe', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{email: email}})
  }}).then(function(resp) {{
    if (resp.ok) {{
      localStorage.setItem('ce_subscribed', '1');
      if (onSuccess) onSuccess();
    }} else {{
      if (onError) onError();
    }}
  }}).catch(function() {{
    if (onError) onError();
  }});
}}

// Email capture form (hero / inline forms)
function handleSubscribe(event) {{
  event.preventDefault();
  var input = event.target.querySelector('.email-input,.hero-email');
  var email = (input ? input.value : '').trim();
  if (!email || !email.includes('@')) {{
    if (input) {{ input.style.borderColor = '#f78166'; input.focus(); }}
    return;
  }}
  var btn = event.target.querySelector('button[type=submit]');
  if (btn) btn.disabled = true;
  _doSubscribe(email, function() {{
    // Clear the input and replace the form with a success message
    if (input) {{ input.value = ''; }}
    var form = event.target;
    form.innerHTML = '<div class="sub-success">\u2705 Subscribed! Check your inbox.<br><span style="font-size:.82em;color:var(--muted)">Your first alert arrives at 3:55 AM ET.</span></div>';
    // Also hide popup since they just subscribed
    var popup = document.getElementById('sub-popup');
    if (popup) popup.classList.remove('visible');
  }}, function() {{
    // Fallback: show error
    alert('Subscribe failed — please try again or visit catalystedge.agency');
  }});
}}

// Popup subscribe handler
function handlePopupSubscribe(event) {{
  event.preventDefault();
  var input = document.getElementById('sub-popup-email');
  var email = (input ? input.value : '').trim();
  if (!email || !email.includes('@')) {{
    if (input) {{ input.style.borderColor = '#f78166'; input.focus(); }}
    return;
  }}
  var btn = event.target.querySelector('.sub-popup-btn');
  if (btn) {{ btn.disabled = true; btn.textContent = '...'; }}
  _doSubscribe(email, function() {{
    document.getElementById('sub-popup-body').style.display = 'none';
    document.getElementById('sub-popup-success').style.display = 'block';
    setTimeout(function() {{
      var popup = document.getElementById('sub-popup');
      if (popup) popup.classList.remove('visible');
    }}, 3000);
  }}, function() {{
    window.open('https://catalystedge.agency?email=' + encodeURIComponent(email), '_blank');
  }});
}}

// ── Mobile sticky subscribe bar ───────────────────────────────────────
(function() {{
  var bar  = document.getElementById('mobile-sub-bar');
  var btn  = document.getElementById('mobile-sub-bar-btn');
  var cls  = document.getElementById('mobile-sub-bar-close');
  if (!bar || window.innerWidth > 640) return;
  if (localStorage.getItem('ce_subscribed') || localStorage.getItem('ce_bar_dismissed')) return;

  // Show on mobile after 15 seconds
  setTimeout(function() {{
    bar.style.display = 'flex';
    // Two-frame delay so transition fires after display:flex is painted
    requestAnimationFrame(function() {{
      requestAnimationFrame(function() {{ bar.classList.add('visible'); }});
    }});
  }}, 15000);

  if (btn) btn.addEventListener('click', function() {{
    bar.classList.remove('visible');
    // Open the subscribe popup
    var popup = document.getElementById('sub-popup');
    if (popup) {{
      popup.classList.add('visible');
      var inp = document.getElementById('sub-popup-email');
      if (inp) inp.focus();
    }}
  }});

  if (cls) cls.addEventListener('click', function() {{
    bar.classList.remove('visible');
    localStorage.setItem('ce_bar_dismissed', '1');
    setTimeout(function() {{ bar.style.display = 'none'; }}, 400);
  }});
}})();

// ── Premium sticky bar — shows after scrolling past the gate ──────────
(function() {{
  var bar = document.getElementById('premium-sticky-bar');
  var cls = document.getElementById('premium-sticky-close');
  if (!bar) return;
  if (localStorage.getItem('ce_premium_dismissed')) return;

  var gate = document.querySelector('.premium-blur-wrap');
  if (gate) {{
    var obs = new IntersectionObserver(function(entries) {{
      entries.forEach(function(e) {{
        if (!e.isIntersecting && e.boundingClientRect.top < 0) {{
          bar.classList.add('visible');
        }}
      }});
    }}, {{ threshold: 0 }});
    obs.observe(gate);
  }} else {{
    // No gate (all free?) — show after 20s scroll
    setTimeout(function() {{ bar.classList.add('visible'); }}, 20000);
  }}

  if (cls) cls.addEventListener('click', function() {{
    bar.classList.remove('visible');
    localStorage.setItem('ce_premium_dismissed', '1');
  }});
}})();

// ── Subscribe popup logic ─────────────────────────────────────────────
(function() {{
  var popup   = document.getElementById('sub-popup');
  var closeBtn = document.getElementById('sub-popup-close');
  if (!popup) return;

  function dismissPopup() {{
    popup.classList.remove('visible');
    localStorage.setItem('ce_popup_dismissed', '1');
  }}

  // Don't show if already subscribed or dismissed
  if (localStorage.getItem('ce_subscribed') || localStorage.getItem('ce_popup_dismissed')) return;

  // Show after 30 seconds
  setTimeout(function() {{
    // Don't show if subscribe section is in viewport
    var sect = document.getElementById('subscribe');
    if (sect) {{
      var r = sect.getBoundingClientRect();
      if (r.top >= 0 && r.bottom <= window.innerHeight) return;
    }}
    popup.classList.add('visible');
  }}, 30000);

  if (closeBtn) closeBtn.addEventListener('click', dismissPopup);

  // Hide popup when subscribe section scrolls into view
  var observer = new IntersectionObserver(function(entries) {{
    entries.forEach(function(e) {{
      if (e.isIntersecting) popup.classList.remove('visible');
    }});
  }}, {{threshold: 0.4}});
  var sect = document.getElementById('subscribe');
  if (sect) observer.observe(sect);
}})();

// ── Polymarket bar + reel animation on scroll ─────────────────────────
(function() {{
  function animateCard(card, delay) {{
    var pctEl = card.querySelector('.pm-pct');
    if (pctEl) {{
      // Always read from data-prob-txt (set at render time) so re-animation
      // on scroll-back never reads the reel strip text by accident.
      var finalTxt = pctEl.dataset.probTxt || pctEl.textContent.trim();
      var color    = pctEl.style.color;
      // Guard: if already animated, just ensure correct value is displayed
      if (card.dataset.pmAnimated) {{
        reelUpdate(pctEl, finalTxt, null, null);
        return;
      }}
      card.dataset.pmAnimated = '1';
      setTimeout(function() {{
        // 1. Init all digit reels to "0" so we start from zero
        var zeroTxt = finalTxt.replace(/[0-9]/g, '0');
        reelInit(pctEl, zeroTxt, null);
        pctEl.style.color = color;
        // 2. 120ms later spin each reel to the real value — this IS the slot effect
        setTimeout(function() {{
          reelUpdate(pctEl, finalTxt, null, null);
          pctEl.style.color = color;
        }}, 120);
      }}, delay);
    }}
    // Bar sweeps from 0 → target width
    var bar = card.querySelector('.pm-bar-fill');
    if (bar) {{
      bar.style.width = '0%';
      setTimeout(function() {{ bar.style.width = bar.dataset.width || '0%'; }}, delay + 240);
    }}
  }}

  function runAnimations() {{
    document.querySelectorAll('.pm-card').forEach(function(c, i) {{
      animateCard(c, 120 + i * 110);
    }});
  }}

  if (!('IntersectionObserver' in window)) {{
    runAnimations(); return;
  }}
  var fired = false;
  var obs = new IntersectionObserver(function(entries) {{
    entries.forEach(function(e) {{
      if (e.isIntersecting && !fired) {{
        fired = true;
        runAnimations();
        obs.disconnect();
      }}
    }});
  }}, {{threshold: 0.05, rootMargin: '0px 0px -40px 0px'}});
  var grid = document.querySelector('.pm-grid');
  if (grid) obs.observe(grid);
}})();

// ── Streak tracker (localStorage) ────────────────────────────────────
(function() {{
  try {{
    var today = new Date().toDateString();
    var last  = localStorage.getItem('ce_last') || '';
    var streak = parseInt(localStorage.getItem('ce_streak') || '0');
    var yest  = new Date(Date.now() - 86400000).toDateString();
    if (last === yest)      streak++;
    else if (last !== today) streak = 1;
    if (last !== today) {{
      localStorage.setItem('ce_last', today);
      localStorage.setItem('ce_streak', streak);
    }}
    var el = document.getElementById('streak-badge');
    if (el && streak >= 2) {{
      el.textContent = '🔥 Day ' + streak + ' streak';
      el.style.display = 'inline-flex';
    }}
  }} catch(e) {{}}
}})();

// ── Live viewer count (realistic, time-seeded) ────────────────────────
(function() {{
  function viewers() {{
    var seed = Math.floor(Date.now() / 300000);
    var h = new Date().getHours();
    var base = (h >= 4 && h <= 10) ? 34 : (h >= 11 && h <= 16) ? 22 : 9;
    return base + ((seed * 9301 + 49297) % 233280) % 18;
  }}
  var el = document.getElementById('viewer-count');
  if (el) {{
    el.textContent = viewers();
    setInterval(function() {{ el.textContent = viewers(); }}, 30000);
  }}
}})();

// ── Market state badge ────────────────────────────────────────────────
(function() {{
  var el = document.getElementById('market-state-badge');
  if (!el) return;
  var parts = getETParts(new Date());
  var h = etDecimalHour(parts);
  var state, cls;
  if (!isETWeekday(parts)) {{ state = '⚫ After Hours'; cls = 'market-closed'; }}
  else if (h >= 4 && h < 9.5)  {{ state = '🟡 Pre-Market Open'; cls = 'market-pre'; }}
  else if (h >= 9.5 && h < 16) {{ state = '🟢 Market Open'; cls = 'market-open'; }}
  else                         {{ state = '⚫ After Hours'; cls = 'market-closed'; }}
  el.className = 'market-state ' + cls;
  el.textContent = state;
}})();

// ── Score animation on spotlight ─────────────────────────────────────
(function() {{
  var el = document.querySelector('.spotlight-score span[style]');
  if (!el) return;
  var target = parseFloat(el.textContent) || 0;
  if (!target) return;
  el.classList.add('score-animate');
  var t0 = performance.now(), dur = 900;
  function tick(t) {{
    var p = Math.min((t - t0) / dur, 1);
    var ease = 1 - Math.pow(1 - p, 3);
    el.textContent = (target * ease).toFixed(1);
    if (p < 1) requestAnimationFrame(tick);
    else el.textContent = target;
  }}
  requestAnimationFrame(tick);
}})();

// Register service worker (PWA)
if ('serviceWorker' in navigator) {{
  window.addEventListener('load', function() {{
    navigator.serviceWorker.register('/sw.js?v={SCANNER_PWA_VERSION}').catch(function() {{}});
  }});
}}

// PWA install prompt
var _pwaPrompt = null;
window.addEventListener('beforeinstallprompt', function(e) {{
  e.preventDefault();
  _pwaPrompt = e;
  var btn = document.getElementById('pwa-install-btn');
  if (btn) btn.style.display = 'inline-flex';
}});
function installPWA() {{
  if (!_pwaPrompt) return;
  _pwaPrompt.prompt();
  _pwaPrompt.userChoice.then(function(r) {{
    if (typeof gtag === 'function') gtag('event', 'pwa_install', {{event_label: r.outcome}});
    _pwaPrompt = null;
    var btn = document.getElementById('pwa-install-btn');
    if (btn) btn.style.display = 'none';
  }});
}}

// ── GA4 Engagement Tracking ──────────────────────────────────────────
(function() {{
  if (typeof gtag !== 'function') return;

  // 1. Section visibility — fires once per section per page load
  var sections = [
    ['gaps',         '#gaps'],
    ['squeeze',      '#squeeze'],
    ['insider',      '#insider'],
    ['darkpool',     '#darkpool'],
    ['options',      '#options'],
    ['track_record', '#track-record'],
    ['email_capture','.cta-block'],
    ['competitor',   '#competitor'],
    ['polymarket',   '#polymarket'],
    ['value',        '#value'],
    ['moat',         '#moat'],
  ];
  if ('IntersectionObserver' in window) {{
    var seen = {{}};
    var sectionObs = new IntersectionObserver(function(entries) {{
      entries.forEach(function(entry) {{
        if (entry.isIntersecting && !seen[entry.target.id || entry.target.className]) {{
          seen[entry.target.id || entry.target.className] = true;
          gtag('event', 'section_view', {{
            event_category: 'scroll',
            event_label: entry.target.dataset.trackId || entry.target.id || 'unknown'
          }});
        }}
      }});
    }}, {{ threshold: 0.2 }});
    sections.forEach(function(s) {{
      var el = document.querySelector(s[1]);
      if (el) {{ el.dataset.trackId = s[0]; sectionObs.observe(el); }}
    }});
  }}

  // 2. Button / CTA clicks
  var btns = [
    ['.btn-green',   'cta_subscribe_hero'],
    ['.btn-tg',      'cta_telegram'],
    ['.nav-cta',     'cta_nav_subscribe'],
    ['.float-cta',   'cta_float_subscribe'],
    ['.capture-btn', 'cta_capture_form_btn'],
    ['.spotlight a', 'cta_top_pick_filing'],
  ];
  btns.forEach(function(b) {{
    document.querySelectorAll(b[0]).forEach(function(el) {{
      el.addEventListener('click', function() {{
        gtag('event', 'button_click', {{
          event_category: 'engagement',
          event_label: b[1]
        }});
      }});
    }});
  }});

  // 3. Table sort tracking
  document.querySelectorAll('table.sortable th').forEach(function(th) {{
    th.addEventListener('click', function() {{
      gtag('event', 'table_sort', {{
        event_category: 'engagement',
        event_label: th.textContent.trim()
      }});
    }});
  }});

  // 4. Time-on-page milestones
  var milestones = [30, 60, 120, 300];
  milestones.forEach(function(sec) {{
    setTimeout(function() {{
      gtag('event', 'time_on_page', {{
        event_category: 'engagement',
        event_label: sec + 's'
      }});
    }}, sec * 1000);
  }});

  // 5. SEC filing link clicks (external)
  document.querySelectorAll('a[href*="sec.gov"]').forEach(function(a) {{
    a.addEventListener('click', function() {{
      gtag('event', 'filing_click', {{
        event_category: 'engagement',
        event_label: a.href
      }});
    }});
  }});

}})();

// ══════════════════════════════════════════════════════════════════════
// TRUE SLOT REEL ENGINE
// 30-row circular strip (0-9 × 3). Always lives in the middle set
// (rows 10-19). Spins forward 1-9 rows then invisibly snaps back.
// The snap is invisible because row 10+N and row 20+N show the same
// digit, so the user sees no jump.
// ══════════════════════════════════════════════════════════════════════

var REEL_H = 1.15; // em — must match .reel-strip>span height in CSS

function buildReel(digit, color) {{
  var wrap = document.createElement('span');
  wrap.className = 'reel';
  wrap.dataset.d = digit;

  var strip = document.createElement('span');
  strip.className = 'reel-strip';
  if (color) strip.style.color = color;

  // 30 rows: 0-9 × 3 (middle set = rows 10-19, animation lands in rows 10-28)
  for (var i = 0; i < 30; i++) {{
    var s = document.createElement('span');
    s.textContent = i % 10;
    strip.appendChild(s);
  }}

  var d = parseInt(digit);
  strip.style.transition = 'none';
  strip.style.transform  = 'translateY(-' + ((10 + d) * REEL_H) + 'em)';
  wrap.appendChild(strip);
  return wrap;
}}

function buildStatic(ch, color) {{
  var s = document.createElement('span');
  s.className = 'reel-static';
  s.textContent = ch;
  if (color) s.style.color = color;
  return s;
}}

function reelInit(container, text, colorFn) {{
  container.innerHTML = '';
  text.split('').forEach(function(ch) {{
    var color = colorFn ? colorFn(ch) : null;
    if (/[0-9]/.test(ch)) container.appendChild(buildReel(ch, color));
    else                   container.appendChild(buildStatic(ch, color));
  }});
}}

function reelUpdate(container, newText, flashEl, flashDir) {{
  var reels   = Array.from(container.querySelectorAll('.reel'));
  var statics = Array.from(container.querySelectorAll('.reel-static'));
  var newDigits  = newText.split('').filter(function(c) {{ return /[0-9]/.test(c); }});
  var newStatics = newText.split('').filter(function(c) {{ return !/[0-9]/.test(c); }});

  if (newDigits.length !== reels.length) {{
    reelInit(container, newText, null);
    return;
  }}

  newStatics.forEach(function(ch, i) {{
    if (statics[i]) statics[i].textContent = ch;
  }});

  newDigits.forEach(function(ch, i) {{
    var reel  = reels[i];
    var strip = reel.querySelector('.reel-strip');
    var oldD  = parseInt(reel.dataset.d);
    var newD  = parseInt(ch);
    if (oldD === newD) return;

    // Forward steps: always 1-9 (slot spins forward only, like a real reel)
    var fwd = (newD - oldD + 10) % 10;

    // From middle set (10+oldD), spin forward fwd rows → lands in rows 10-28 ✓
    var startRow  = 10 + oldD;
    var targetRow = startRow + fwd;

    // Single smooth animation — starts fast, decelerates to a crisp stop
    strip.style.transition = 'transform 0.38s cubic-bezier(0.12, 0.9, 0.22, 1)';
    strip.style.transform  = 'translateY(-' + (targetRow * REEL_H) + 'em)';

    // After animation completes, snap invisibly back to middle set
    // (row 10+newD shows same digit as row targetRow — no visible jump)
    var reelRef = reel;
    setTimeout(function() {{
      strip.style.transition = 'none';
      strip.style.transform  = 'translateY(-' + ((10 + newD) * REEL_H) + 'em)';
      reelRef.dataset.d = ch;
    }}, 420);

    reel.dataset.d = ch; // mark immediately so rapid calls see new value
  }});

  if (flashEl && flashDir) {{
    flashEl.classList.remove('slot-flash-up', 'slot-flash-dn');
    void flashEl.offsetWidth;
    flashEl.classList.add('slot-flash-' + flashDir);
  }}
}}

// ── Helper: is market open right now? ────────────────────────────────
function isMarketHours() {{
  var parts = getETParts(new Date());
  if (!isETWeekday(parts)) return false;
  var h = etDecimalHour(parts);
  return (h >= 9.5 && h < 16); // 9:30 AM – 4:00 PM ET
}}
function isPreMarket() {{
  var parts = getETParts(new Date());
  if (!isETWeekday(parts)) return false;
  var h = etDecimalHour(parts);
  return (h >= 4 && h < 9.5);
}}

// ── Live Market Ticker Bar (marquee) ──────────────────────────────────
(function() {{
  if (!SCANNER_RUNTIME.clientQuotes) {{
    var bar = document.getElementById('live-ticker-bar');
    if (bar) bar.style.display = 'none';
    return;
  }}
  var SYMBOLS = ['SPY','DIA','QQQ','IWM','VIX','BTC-USD','ETH-USD','SOL-USD','LTC-USD'];
  var _data = {{}};

  function fmtPrice(p, sym) {{
    if (p == null || !isFinite(p)) return '—';
    if (sym === 'VIX') return p.toFixed(2);
    if (sym.indexOf('-USD') > 0) {{
      if (p >= 100)  return '$' + Math.round(p).toLocaleString('en-US');
      if (p >= 10)   return '$' + p.toFixed(2);
      return '$' + p.toFixed(3);
    }}
    return '$' + p.toFixed(2);
  }}

  function cloneItems() {{
    var inner = document.getElementById('ltb-inner');
    if (!inner || inner.dataset.cloned) return;
    var originals = Array.prototype.slice.call(inner.querySelectorAll('.ltb-item'));
    originals.forEach(function(node) {{
      var c = node.cloneNode(true);
      c.setAttribute('aria-hidden', 'true');
      c.classList.add('ltb-clone');
      inner.appendChild(c);
    }});
    inner.dataset.cloned = '1';
  }}

  function paintPill(item, d) {{
    var priceEl = item.querySelector('.ltb-price');
    var chgEl   = item.querySelector('.ltb-chg');
    if (!priceEl || !chgEl) return;
    priceEl.textContent = d.priceStr;
    chgEl.textContent   = (d.up ? '▲' : '▼') + ' ' + d.pctStr;
    chgEl.className = 'ltb-chg ' + (d.up ? 'up' : 'dn');
  }}

  function renderItem(sym, d) {{
    if (!d) return;
    var items = document.querySelectorAll('.ltb-item[data-sym="' + sym + '"]');
    var old = _data[sym];
    items.forEach(function(it) {{ paintPill(it, d); }});
    if (old && old.price !== d.price && isFinite(old.price) && isFinite(d.price)) {{
      var dir = d.price > old.price ? 'up' : 'dn';
      items.forEach(function(it) {{
        it.classList.remove('ltb-flash-up','ltb-flash-dn');
        void it.offsetWidth;
        it.classList.add('ltb-flash-' + dir);
      }});
    }}
    _data[sym] = d;
  }}

  function fetchAll() {{
    return scannerQuoteJson(SYMBOLS, 5000)
      .then(function(rows) {{
        var byTicker = {{}};
        (rows || []).forEach(function(row) {{
          if (!row || !row.ticker || row.price == null) return;
          byTicker[String(row.ticker).toUpperCase()] = row;
        }});
        return SYMBOLS.map(function(sym) {{
          var row = byTicker[String(sym).toUpperCase()];
          if (!row) return null;
          var price = Number(row.price);
          var prev = Number(row.prev_close || 0);
          var pct = prev > 0 ? ((price - prev) / prev) * 100 : 0;
          var up = pct >= 0;
          return {{
            sym: sym,
            price: price,
            priceStr: fmtPrice(price, sym),
            pctStr: Math.abs(pct).toFixed(2) + '%',
            up: up
          }};
        }});
      }})
      .catch(function() {{ return SYMBOLS.map(function() {{ return null; }}); }});
  }}

  function updateTimestamp() {{
    var ts = document.getElementById('ltb-ts');
    if (!ts) return;
    ts.replaceChildren();
    var dot = document.createElement('span');
    dot.className = 'ltb-dot';
    ts.appendChild(dot);
    ts.appendChild(document.createTextNode(' ' + formatETClock(new Date()) + ' ET'));
  }}

  function updateAll() {{
    fetchAll().then(function(results) {{
      SYMBOLS.forEach(function(sym, i) {{ renderItem(sym, results[i]); }});
      cloneItems();
      updateTimestamp();
    }});
  }}

  updateAll();
  setInterval(function() {{ updateAll(); }},
    isMarketHours() ? 10000 : isPreMarket() ? 20000 : 60000);
}})();

// ── Spotlight Top Pick Live Price ─────────────────────────────────────
(function() {{
  var tickerEl = document.getElementById('spotlight-ticker');
  if (!tickerEl) return;
  var sym = tickerEl.dataset.ticker || '';
  if (!sym || sym.length < 1 || sym.length > 6) return;

  var liveEl  = document.getElementById('spotlight-live');
  if (!liveEl) return;
  if (!SCANNER_RUNTIME.clientQuotes) {{
    liveEl.innerHTML = '<span class="slp-chg" style="background:rgba(255,255,255,.05);color:var(--muted)">Snapshot mode</span>';
    return;
  }}
  var _lastPrice = null;
  var _inited    = false;

  function fetchAndRender() {{
    scannerQuoteJson([sym], 5000)
      .then(function(rows) {{
        var row = rows && rows[0];
        if (!row || row.price == null) return;
        var price = Number(row.price);
        var prev = Number(row.prev_close || 0);
        var chg = price - prev, pct = prev > 0 ? (chg/prev)*100 : 0, up = chg >= 0;
        var priceStr = '$' + price.toFixed(2);
        var chgStr   = (up?'▲ +':'▼ ') + Math.abs(pct).toFixed(2) + '%';
        var cls = up ? 'up' : 'dn';

        if (!_inited) {{
          liveEl.innerHTML = '';
          var pw = document.createElement('span');
          pw.className = 'slp-price';
          pw.textContent = priceStr;
          liveEl.appendChild(pw);

          var cb = document.createElement('span');
          cb.className = 'slp-chg ' + cls;
          cb.textContent = chgStr;
          liveEl.appendChild(cb);
          _inited = true;
        }} else {{
          var flashDir = (_lastPrice != null && price !== _lastPrice)
            ? (price > _lastPrice ? 'up' : 'dn') : null;
          var pw2 = liveEl.querySelector('.slp-price');
          var cb2 = liveEl.querySelector('.slp-chg');
          if (pw2) pw2.textContent = priceStr;
          if (cb2) {{
            cb2.textContent = chgStr;
            cb2.className = 'slp-chg ' + cls;
          }}
          if (flashDir) {{
            var shell = tickerEl.closest('.spotlight');
            if (shell) {{
              shell.classList.remove('slot-flash-up', 'slot-flash-dn');
              void shell.offsetWidth;
              shell.classList.add(flashDir === 'up' ? 'slot-flash-up' : 'slot-flash-dn');
            }}
          }}
        }}
        _lastPrice = price;
      }}).catch(function() {{}});
  }}

  // Stagger 1.5s after ticker bar loads
  setTimeout(function() {{
    fetchAndRender();
    var interval = isMarketHours() ? 10000 : isPreMarket() ? 20000 : 60000;
    setInterval(fetchAndRender, interval);
  }}, 1500);
}})();

// ── Sub-penny Liquidity Alert (live bid/ask wall fetch) ──────────────
(function() {{
  var flags = Array.from(document.querySelectorAll('.subpenny-flag[data-ticker]'));
  if (!flags.length) return;
  if (!SCANNER_RUNTIME.liquidityQuotes) return;

  var YF_QS         = 'https://query2.finance.yahoo.com/v10/finance/quoteSummary/';
  var toastCtr      = document.getElementById('liq-toast-container');
  var DANGER_SHARES = 1e9;   // ≥1B shares at ask = extreme liquidity trap → sticky toast
  var _prevShares   = {{}};   // sym → last known shares at ask (for tape direction)
  var _prevWallUSD  = {{}};   // sym → last known wall $ amount (for Wall Eaten detection)

  function fmtWall(d) {{
    if (d >= 1e9) return '$' + (d/1e9).toFixed(2) + 'B';
    if (d >= 1e6) return '$' + (d/1e6).toFixed(2) + 'M';
    if (d >= 1e3) return '$' + (d/1e3).toFixed(0) + 'K';
    return '$' + d.toFixed(0);
  }}
  function fmtShares(n) {{
    if (n >= 1e12) return (n/1e12).toFixed(1) + 'T';
    if (n >= 1e9)  return (n/1e9).toFixed(1)  + 'B';
    if (n >= 1e6)  return (n/1e6).toFixed(1)  + 'M';
    if (n >= 1e3)  return (n/1e3).toFixed(0)  + 'K';
    return n.toLocaleString('en-US');
  }}

  // Returns color + label based on whether ask wall is growing (danger) or shrinking (being eaten)
  function wallDirection(sym, shares) {{
    var prev = _prevShares[sym];
    _prevShares[sym] = shares;
    if (prev === undefined)   return {{ color: '#e3b341', label: '● LIVE' }};   // first read — amber
    if (shares < prev)        return {{ color: '#3fb950', label: '▼ LIVE' }};   // wall shrinking — green (being eaten)
    if (shares > prev)        return {{ color: '#f85149', label: '▲ LIVE' }};   // wall growing  — red (accumulating)
    return                           {{ color: '#e3b341', label: '● LIVE' }};   // unchanged     — amber
  }}

  function showToast(sym, wallStr, nextTick, dir, volMultStr, isDanger) {{
    if (!toastCtr) return;
    // Replace existing toast for this sym on refresh (direction update)
    var existing = toastCtr.querySelector('[data-liq-sym="' + sym + '"]');
    if (existing) existing.parentNode.removeChild(existing);

    var item = document.createElement('div');
    item.className = 'liq-toast-item' + (isDanger ? ' liq-toast-danger' : '');
    item.dataset.liqSym = sym;

    var liveTag = dir
      ? '<span style="color:' + dir.color + ';font-size:.85em"> ' + dir.label + '</span>'
      : '<span style="color:var(--muted);font-size:.85em"> est.</span>';
    var dangerBanner = isDanger
      ? '<div class="liq-danger-banner">🚨 EXTREME WALL — Liquidity Trap</div>'
      : '';
    var volLine = volMultStr
      ? '<div class="liq-vol-line">📊 Requires ' + volMultStr + ' · Wall: ' + wallStr + '</div>'
      : '<div style="margin-top:3px">Sell Wall: ' + wallStr + '</div>';

    /* Safe DOM build — no innerHTML even though sym/wallStr are internal data. */
    var titleEl = document.createElement('div');
    titleEl.className = 'liq-toast-title';
    titleEl.appendChild(document.createTextNode('⚠️ Liquidity Alert: ' + sym));
    if (liveTag) {{
      var liveSpan = document.createElement('span');
      liveSpan.style.cssText = 'background:rgba(63,185,80,.18);color:#3fb950;font-size:.7em;padding:1px 6px;border-radius:3px;margin-left:6px;font-weight:700;letter-spacing:.04em';
      liveSpan.textContent = 'LIVE';
      titleEl.appendChild(liveSpan);
    }}
    var closeBtn = document.createElement('span');
    closeBtn.className = 'liq-toast-close';
    closeBtn.title = 'Dismiss';
    closeBtn.textContent = '✕';
    titleEl.appendChild(closeBtn);
    item.appendChild(titleEl);
    if (isDanger) {{
      var dangerEl = document.createElement('div');
      dangerEl.className = 'liq-danger-banner';
      dangerEl.textContent = '🚨 EXTREME WALL — Liquidity Trap';
      item.appendChild(dangerEl);
    }}
    item.appendChild(document.createTextNode(
      'Move to $' + parseFloat(nextTick).toFixed(4) + ' requires clearing the ask'));
    var volEl = document.createElement('div');
    if (volMultStr) {{
      volEl.className = 'liq-vol-line';
      volEl.textContent = '📊 Requires ' + volMultStr + ' · Wall: ' + wallStr;
    }} else {{
      volEl.style.cssText = 'margin-top:3px';
      volEl.textContent = 'Sell Wall: ' + wallStr;
    }}
    item.appendChild(volEl);

    closeBtn.addEventListener('click', function(e) {{
      e.stopPropagation();  // prevent click bleeding through to card/page beneath the toast
      e.preventDefault();
      item.style.animation = 'liqFadeOut .3s ease forwards';
      setTimeout(function() {{ if (item.parentNode) item.parentNode.removeChild(item); }}, 320);
    }});
    toastCtr.appendChild(item);

    // Danger toasts (≥1B shares at ask) are STICKY — trader must manually dismiss
    if (!isDanger) {{
      setTimeout(function() {{
        if (item.parentNode) {{
          item.style.animation = 'liqFadeOut .3s ease forwards';
          setTimeout(function() {{ if (item.parentNode) item.parentNode.removeChild(item); }}, 320);
        }}
      }}, 14000);
    }}
  }}

  // Green "Wall Eaten" toast — fires only when wallUSD drops ≥10% in a single 30s poll
  function showWallEatenToast(sym, pctDrop, newWallStr) {{
    if (!toastCtr) return;
    // Replace any existing wall-eaten toast for this sym
    var key = sym + '-eaten';
    var existing = toastCtr.querySelector('[data-liq-sym="' + key + '"]');
    if (existing) existing.parentNode.removeChild(existing);

    var item = document.createElement('div');
    item.className = 'liq-toast-item liq-toast-eaten';
    item.dataset.liqSym = key;
    /* Safe DOM build — no innerHTML. */
    var eatenTitle = document.createElement('div');
    eatenTitle.className = 'liq-toast-title liq-eaten-title';
    eatenTitle.appendChild(document.createTextNode('🔥 Wall Being Eaten: ' + sym));
    var eatenClose = document.createElement('span');
    eatenClose.className = 'liq-toast-close';
    eatenClose.title = 'Dismiss';
    eatenClose.textContent = '✕';
    eatenTitle.appendChild(eatenClose);
    item.appendChild(eatenTitle);
    var eatenBody = document.createElement('div');
    eatenBody.className = 'liq-eaten-body';
    eatenBody.appendChild(document.createTextNode('Sell pressure dropped '));
    var pctStrong = document.createElement('strong');
    pctStrong.textContent = pctDrop.toFixed(1) + '%';
    eatenBody.appendChild(pctStrong);
    eatenBody.appendChild(document.createTextNode(' in the last 30s'));
    item.appendChild(eatenBody);
    var eatenSub = document.createElement('div');
    eatenSub.className = 'liq-eaten-sub';
    eatenSub.textContent = 'Remaining wall: ' + newWallStr + ' · Watch for continuation ▲';
    item.appendChild(eatenSub);

    eatenClose.addEventListener('click', function(e) {{
      e.stopPropagation();
      e.preventDefault();
      item.style.animation = 'liqFadeOut .3s ease forwards';
      setTimeout(function() {{ if (item.parentNode) item.parentNode.removeChild(item); }}, 320);
    }});
    toastCtr.appendChild(item);
    // Wall Eaten is time-sensitive intel — auto-dismiss after 10s
    setTimeout(function() {{
      if (item.parentNode) {{
        item.style.animation = 'liqFadeOut .3s ease forwards';
        setTimeout(function() {{ if (item.parentNode) item.parentNode.removeChild(item); }}, 320);
      }}
    }}, 10000);
  }}

  function fetchAskWall(flag, isRefresh) {{
    var sym      = flag.dataset.ticker;
    var nextTick = flag.dataset.nextTick    || '0.0002';
    var estPress = flag.dataset.estPressure || '';
    var staticPrice = parseFloat(flag.dataset.price || '');
    if (!isFinite(staticPrice) || staticPrice <= 0 || staticPrice > 0.001) {{
      flag.remove();
      return;
    }}

    // quoteSummary summaryDetail: ask, askSize (round lots ×100), averageDailyVolume10Day
    var yfUrl = YF_QS + encodeURIComponent(sym) + '?modules=summaryDetail';
    scannerProxyJson(yfUrl, 5000)
      .then(function(d) {{
        // ── Parse Yahoo Finance quoteSummary envelope ──────────────────
        var result = d && d.quoteSummary && d.quoteSummary.result;
        if (!result || !result.length) throw new Error('empty result');
        var sd = result[0].summaryDetail;
        if (!sd) throw new Error('no summaryDetail');

        // ask.raw = price per share; askSize.raw = round lots (1 lot = 100 shares)
        // askSize.raw === 0 means ticker is in "Ask Only" or "Bid Only" state → no wall data
        var ask     = (sd.ask     && typeof sd.ask.raw     === 'number') ? sd.ask.raw     : null;
        var askLots = (sd.askSize && typeof sd.askSize.raw === 'number' && sd.askSize.raw > 0)
                    ? sd.askSize.raw : null;
        if (!ask || !askLots || ask <= 0) throw new Error('no ask data');
        if (ask > 0.001) {{
          flag.remove();
          return;
        }}
        var shares  = askLots * 100;     // convert lots → shares
        var wallUSD = ask * shares;
        var wallStr = fmtWall(wallUSD);

        // ── Wall Eaten detection (30s poll only) ───────────────────────
        // Fires when wallUSD drops ≥10% vs previous poll — "pressure cracking"
        if (isRefresh) {{
          var prevWall = _prevWallUSD[sym];
          if (prevWall !== undefined && prevWall > 0 && wallUSD < prevWall) {{
            var pctDrop = (prevWall - wallUSD) / prevWall * 100;
            if (pctDrop >= 10) showWallEatenToast(sym, pctDrop, wallStr);
          }}
        }}
        _prevWallUSD[sym] = wallUSD;

        // Volume multiplier: how many avg daily volumes does this wall represent?
        var avgVol = (sd.averageDailyVolume10Day  && sd.averageDailyVolume10Day.raw)
                  || (sd.averageDailyVolume3Month && sd.averageDailyVolume3Month.raw)
                  || 0;
        var volMultStr = '';
        if (avgVol > 0) {{
          var mult = shares / avgVol;
          volMultStr = (mult >= 10 ? mult.toFixed(0) : mult.toFixed(1)) + '× avg daily volume';
        }}

        // Tape direction: green=wall shrinking, red=wall growing, amber=new/unchanged
        var dir      = wallDirection(sym, shares);
        var isDanger = shares >= DANGER_SHARES;

        // ── Update the card flag div (safe DOM, no innerHTML) ─────────
        flag.replaceChildren();
        flag.appendChild(document.createTextNode(
          '⚠️ Sub-penny floor $' + parseFloat(flag.dataset.price).toFixed(4) +
          ' · Move to $' + parseFloat(nextTick).toFixed(4) +
          ' requires clearing a '));
        var wallStrong = document.createElement('strong');
        wallStrong.textContent = wallStr + ' sell wall';
        flag.appendChild(wallStrong);
        flag.appendChild(document.createTextNode(
          ' (' + fmtShares(shares) + ' shares @ $' + ask.toFixed(4) + ')'));
        if (volMultStr) {{
          flag.appendChild(document.createTextNode(' · '));
          var volSpan = document.createElement('span');
          volSpan.style.color = '#e3b341';
          volSpan.textContent = volMultStr;
          flag.appendChild(volSpan);
        }}
        var dirSpan = document.createElement('span');
        dirSpan.style.cssText = 'color:' + dir.color + ';font-size:.85em';
        dirSpan.textContent = ' ' + dir.label;
        flag.appendChild(dirSpan);
        flag.style.borderColor = isDanger ? '#f8514999' : '#f7816699';

        // Show toast: always on first load; on refresh only if direction changed or danger
        var prevShares = _prevShares[sym];  // already updated by wallDirection()
        var changed    = prevShares !== undefined && shares !== prevShares;
        if (!isRefresh || changed || isDanger) {{
          showToast(sym, wallStr, nextTick, dir, volMultStr, isDanger);
        }}
      }})
      .catch(function() {{
        // Yahoo returned no data — keep static estimate, fire single est. toast on first load
        if (!isRefresh && estPress) showToast(sym, estPress, nextTick, null, '', false);
      }});
  }}

  // Initial fetch — stagger 800ms apart to avoid proxy rate-limit
  flags.forEach(function(flag, i) {{
    setTimeout(function() {{ fetchAskWall(flag, false); }}, 2000 + i * 800);
  }});

  // Poll every 30s for tape direction updates (▼ wall shrinking / ▲ wall growing)
  setInterval(function() {{
    flags.forEach(function(flag, i) {{
      setTimeout(function() {{ fetchAskWall(flag, true); }}, i * 800);
    }});
  }}, 30000);
}})();

// ── Polymarket Live Odds Refresh (every 5 min) ────────────────────────
(function() {{
  if (!SCANNER_RUNTIME.polymarketRefresh) {{
    // Live refresh disabled — clear any loading skeleton so it doesn't hang forever
    var _pmGrid = document.getElementById('pm-grid');
    if (_pmGrid && _pmGrid.querySelector('.pm-loading')) {{
      _pmGrid.innerHTML = '<div style="padding:16px;border:1px solid rgba(255,255,255,.10);border-radius:8px;background:rgba(0,0,0,.5);text-align:center"><span style="color:var(--muted);font-size:.875rem">Prediction market data loads at next pipeline cycle.</span></div>';
    }}
    return;
  }}
  // Gamma API has no CORS headers — must route through a proxy.
  // Try three proxies in sequence; first success wins.
  var GAMMA_RAW   = 'https://gamma-api.polymarket.com/markets?limit=200&active=true&closed=false&order=volume24hr&ascending=false';
  var GAMMA_PROXIES = [
    'https://corsproxy.io/?' + encodeURIComponent(GAMMA_RAW),
    'https://api.allorigins.win/raw?url=' + encodeURIComponent(GAMMA_RAW),
    'https://api.codetabs.com/v1/proxy?quest=' + encodeURIComponent(GAMMA_RAW)
  ];
  var FINANCE_KW = [
    'fed ','federal reserve','interest rate','rate cut','rate hike',
    'inflation','recession','gdp','tariff','trade war','trade deal',
    'china trade','china ','iran','oil price','energy price','crude',
    'bitcoin','crypto','gold price','nasdaq','s&p 500','s&p500',
    'stock market','earnings','acquisition','merger','ipo','layoffs',
    'unemployment','treasury','us dollar','debt ceiling',
    'sanctions','opec','bank collapse','financial crisis','economic',
    'market crash','bear market','default','powell','ceasefire',
    'russia','ukraine','north korea','taiwan',
    'kharg island','strait of hormuz',
    'trump tariff','trump tax','trump trade','trump executive',
    'us china','us-china','trade policy','import duty',
    'jobs report','nonfarm','cpi report','fed meeting','fomc',
    'oil barrel','brent','wti','energy sector','defense spending'
  ];
  var SPORTS_EX = [
    // Traditional sports
    'nba','nfl','nhl','mlb','soccer','football','basketball',
    'hockey','baseball','tennis','golf','mma','ufc','f1',
    'super bowl','world cup','champions league','premier league',
    'warriors','lakers','celtics','jets','eagles','cowboys',
    'shockers','hornets','knicks','cavaliers','nuggets',
    'wichita','tulsa','vs.','o/u','spread:','moneyline',
    'lebron','mahomes',
    // Esports / gaming
    'dota','counter-strike','cs:go','csgo','cs2',
    'esport','e-sport','esports',
    'league of legends','valorant','overwatch','fortnite',
    'pubg','apex legends','rocket league','starcraft',
    'hearthstone','call of duty','warzone','halo',
    'gaming tournament','pro league','esl ','blast ','faceit',
    'major championship',
    // Entertainment / pop culture
    'oscar','emmy','grammy','golden globe','bafta',
    'survivor','bachelor','big brother','american idol',
    'box office','album','song of the year','best actor',
    'best picture','celebrity','kardashian','taylor swift'
  ];

  function isRelevant(title) {{
    var t = title.toLowerCase();
    if (SPORTS_EX.some(function(ex) {{ return t.includes(ex); }})) return false;
    return FINANCE_KW.some(function(kw) {{ return t.includes(kw); }});
  }}

  function parseProb(prices) {{
    try {{
      var p = typeof prices === 'string' ? JSON.parse(prices) : prices;
      return Math.round(parseFloat(p[0]) * 1000) / 10;
    }} catch(e) {{ return null; }}
  }}

  function probColor(p) {{
    if (p >= 70) return '#2ea043';
    if (p >= 40) return '#d29922';
    if (p >= 15) return '#f0883e';
    return '#f78166';
  }}

  function fmtVol(v) {{
    if (v >= 1e6) return '$' + (v/1e6).toFixed(1) + 'M';
    if (v >= 1e3) return '$' + Math.round(v/1e3) + 'K';
    return '$' + Math.round(v);
  }}

  // maxVol set by processMarkets before calling buildCardHtml
  var _pmMaxVol = 1;

  function buildCardHtml(s) {{
    var prob   = s.prob;
    var title  = s.title.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    var impact = (s.impact || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    var vol24  = s.vol24;
    var voltot = s.voltot;
    var url    = (s.url && /^https?:\/\//.test(s.url)) ? s.url.replace(/"/g,'%22') : '#';
    var end    = s.end;
    var color  = probColor(prob);
    var deg    = Math.min(prob, 100) * 3.6;
    var badge  = prob >= 70 ? 'LIKELY' : prob >= 40 ? 'CONTESTED' : prob >= 15 ? 'UNLIKELY' : 'LOW';
    var bg     = prob >= 70 ? '#1a3a1a' : prob >= 40 ? '#2d2200' : prob >= 15 ? '#2d1800' : '#2d1010';
    var hotBadge = vol24 >= 1e6 ? '<span class="pm-hot">🔥 HOT</span>' : '';
    var tension = (prob >= 30 && prob <= 70) ? 'high' : prob >= 85 ? 'locked' : 'low';
    var volFrac = voltot / (_pmMaxVol || 1);
    var thick = Math.max(6, Math.min(14, Math.round(6 + volFrac * 8)));
    var volBarW = Math.round(volFrac * 100);

    var countdown = '';
    var urgency = '';
    if (end) {{
      var d = Math.round((new Date(end) - new Date()) / 86400000);
      if (d === 0) {{ countdown = '⚡ Resolves TODAY'; urgency = 'hot'; }}
      else if (d === 1) {{ countdown = '⏰ Resolves TOMORROW'; urgency = 'hot'; }}
      else if (d > 0 && d <= 3) {{ countdown = '⏳ ' + d + 'd left'; urgency = 'hot'; }}
      else if (d > 3 && d <= 7) countdown = '⏳ ' + d + 'd left';
      else if (d > 7) countdown = '📅 ' + d + 'd left';
    }}

    var vol24Badge = vol24 > 1e5
      ? '<span class="pm-24h">+' + fmtVol(vol24) + ' 24h</span>'
      : '';

    return '<div class="pm-card" data-prob="' + Math.min(Math.round(prob),100) + '" data-tension="' + tension + '" data-urgency="' + urgency + '"' +
      ' style="--pm-arc:' + color + ';--pm-deg:' + deg.toFixed(1) + 'deg;--pm-thick:' + thick + 'px;--pm-glow:' + color + '">' +
      '<div class="pm-ring-wrap">' +
        '<div class="pm-ring-pulse"></div>' +
        '<div class="pm-ring"><span class="pm-ring-pct" style="color:' + color + '">' + prob.toFixed(0) + '%</span></div>' +
        '<div class="pm-ring-urgency"></div>' +
      '</div>' +
      '<div class="pm-card-body">' +
        '<div>' +
          '<span class="pm-badge" style="background:' + bg + ';color:' + color + ';border-color:' + color + '44">' + badge + '</span>' +
          hotBadge +
          (countdown ? '<span class="pm-countdown">' + countdown + '</span>' : '') +
        '</div>' +
        '<a href="' + url + '" target="_blank" rel="nofollow" class="pm-title">' + title + '</a>' +
        '<div class="pm-meta"><span>' + fmtVol(voltot) + ' bet</span>' +
          '<div class="pm-vol-bar"><div class="pm-vol-fill" style="width:' + volBarW + '%"></div></div>' +
          vol24Badge +
        '</div>' +
        (impact ? '<div class="pm-impact">📊 <strong>' + impact + '</strong></div>' : '') +
      '</div>' +
    '</div>';
  }}

  function marketImpact(title) {{
    var t = title.toLowerCase();
    if (t.includes('iran') || t.includes('israel') || t.includes('ceasefire'))
      return 'Energy stocks, defense, oil prices';
    if (t.includes('fed') || t.includes('rate') || t.includes('interest'))
      return 'Rate-sensitive: banks, REITs, growth stocks';
    if (t.includes('tariff') || t.includes('trade war') || t.includes('china'))
      return 'Manufacturing, supply chain, semiconductors';
    if (t.includes('bitcoin') || t.includes('crypto'))
      return 'Risk sentiment, crypto-adjacent equities';
    if (t.includes('recession') || t.includes('gdp'))
      return 'Broad market, defensives vs cyclicals';
    if (t.includes('oil') || t.includes('opec') || t.includes('energy'))
      return 'Energy sector, transportation, materials';
    if (t.includes('russia') || t.includes('ukraine'))
      return 'Commodities, defense, European equities';
    if (t.includes('default') || t.includes('debt'))
      return 'Treasuries, credit markets, financials';
    return 'Macro / risk-off sentiment';
  }}

  function tryProxy(idx) {{
    if (idx >= GAMMA_PROXIES.length) {{
      // All proxies failed — show graceful error; only replace if still showing the skeleton
      var grid = document.getElementById('pm-grid');
      if (grid && grid.querySelector('.pm-loading')) {{
        grid.innerHTML = '<div style="padding:16px;border:1px solid rgba(255,255,255,.10);border-radius:8px;background:rgba(0,0,0,.5);text-align:center"><span style="color:var(--muted);font-size:.875rem">Prediction market API temporarily unavailable. Retrying next cycle.</span> <a href="https://polymarket.com" target="_blank" rel="nofollow" style="color:var(--blue);font-size:.875rem;margin-left:8px">View directly →</a></div>';
      }}
      console.warn('[polymarket] All proxies exhausted — will retry on next interval');
      return;
    }}
    var ctrl = new AbortController();
    var tid  = setTimeout(function() {{ ctrl.abort(); }}, 10000);
    fetch(GAMMA_PROXIES[idx], {{signal: ctrl.signal}})
      .then(function(r) {{
        clearTimeout(tid);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }})
      .then(function(markets) {{ processMarkets(markets); }})
      .catch(function() {{ tryProxy(idx + 1); }});
  }}

  function refreshPolymarket() {{ tryProxy(0); }}

  function processMarkets(markets) {{
    var signals = [];
    var todayIso = new Date().toISOString().slice(0,10);
    markets.forEach(function(m) {{
      var title = (m.question || m.groupItemTitle || '').trim();
      if (!title || !isRelevant(title)) return;
      var prob = parseProb(m.outcomePrices);
      if (prob == null) return;
      var vol24 = parseFloat(m.volume24hr || 0);
      if ((prob === 0 || prob === 100) && vol24 < 5e6) return;
      var events = m.events || [{{}}];
      var slug = (events[0] && events[0].slug) || m.slug || '';
      var endIso = (m.endDate || '').slice(0,10);
      // Skip resolved / expired markets — probability can no longer update
      if (endIso && endIso < todayIso) return;
      signals.push({{
        title: title,
        prob:  prob,
        impact: marketImpact(title),
        vol24:  vol24,
        voltot: parseFloat(m.volume || 0),
        end:    endIso,
        url:    'https://polymarket.com/event/' + slug
      }});
    }});
    signals.sort(function(a,b) {{ return b.vol24 - a.vol24; }});
    signals = signals.slice(0, 8);

    var grid = document.getElementById('pm-grid');
    if (!grid) return;

    if (!signals.length) {{
      grid.innerHTML = '<p style="color:var(--muted);text-align:center;padding:24px 0">No active finance markets right now.</p>';
      return;
    }}
    _pmMaxVol = Math.max.apply(null, signals.map(function(s) {{ return s.voltot; }})) || 1;
    grid.innerHTML = signals.map(buildCardHtml).join('');

    grid.querySelectorAll('.pm-card').forEach(function(card, idx) {{
      var ring  = card.querySelector('.pm-ring');
      var pctEl = card.querySelector('.pm-ring-pct');
      var base  = 80 + idx * 110;
      var finalDeg = card.style.getPropertyValue('--pm-deg') || '0deg';
      // Animate ring arc from 0 → final
      if (ring) {{
        card.style.setProperty('--pm-deg', '0deg');
        setTimeout(function() {{
          card.style.setProperty('--pm-deg', finalDeg);
        }}, base);
      }}
      // Animate probability number with reel if available
      if (pctEl && typeof reelInit === 'function') {{
        var finalTxt = pctEl.textContent.trim();
        var color    = pctEl.style.color;
        setTimeout(function() {{
          var zeroTxt = finalTxt.replace(/[0-9]/g, '0');
          reelInit(pctEl, zeroTxt, null);
          pctEl.style.color = color;
          setTimeout(function() {{
            reelUpdate(pctEl, finalTxt, null, null);
            pctEl.style.color = color;
          }}, 120);
        }}, base + 60);
      }}
    }});

    var totalVol = signals.reduce(function(s,m) {{ return s + m.voltot; }}, 0);
    var tag = document.getElementById('pm-tag');
    if (tag) tag.textContent = fmtVol(totalVol) + ' in active bets';

    if (typeof gtag === 'function') {{
      gtag('event', 'polymarket_refresh', {{
        event_category: 'live_data',
        event_label: signals.length + '_markets'
      }});
    }}
  }}

  // First live refresh 8s after page load (so user sees the spin),
  // then every 5 minutes to keep odds current
  setTimeout(function() {{
    refreshPolymarket();
    setInterval(refreshPolymarket, 300000);
  }}, 8000);
}})();

// ── Finnhub WebSocket — Real-Time Scanner Prices ──────────────────────
(function() {{
  var TOKEN   = SCANNER_RUNTIME.finnhubWs ? 'd753ohpr01qg1eo7gta0d753ohpr01qg1eo7gtag' : '';
  var _prev   = {{}};
  var _prevClose = {{}};
  var _socket = null;
  var _subbed = {{}};
  var _cdSec  = isMarketHours() ? 10 : isPreMarket() ? 15 : 60;

  // Track which tickers are visible in the viewport (saves battery / main-thread on mobile)
  var _visible = {{}};
  if ('IntersectionObserver' in window) {{
    var _priceObs = new IntersectionObserver(function(entries) {{
      entries.forEach(function(e) {{
        var t = e.target.getAttribute('data-live-price') || '';
        if (t) _visible[t] = e.isIntersecting;
      }});
    }}, {{rootMargin: '300px'}}); // 300px buffer so price loads just before scrolling into view
    document.querySelectorAll('[data-live-price]').forEach(function(el) {{
      _priceObs.observe(el);
    }});
  }}

  function getTickers() {{
    var seen = {{}}, out = [];
    document.querySelectorAll('[data-live-price]').forEach(function(el) {{
      var t = el.getAttribute('data-live-price') || '';
      if (t && !seen[t]) {{ seen[t] = 1; out.push(t); }}
    }});
    return out;
  }}

  function getVisibleTickers() {{
    var all = getTickers();
    // If IntersectionObserver hasn't fired yet, return all (safe fallback)
    if (Object.keys(_visible).length === 0) return all;
    return all.filter(function(t) {{ return _visible[t] !== false; }});
  }}

  function getLivePriceCells(ticker) {{
    return Array.prototype.slice.call(document.querySelectorAll('[data-live-price=\"' + ticker + '\"]'));
  }}

  function ensureLivePriceCell(cell) {{
    var priceEl = cell.querySelector('.live-price-main');
    var changeEl = cell.querySelector('.live-price-change');
    if (priceEl && changeEl) return {{ priceEl: priceEl, changeEl: changeEl }};
    cell.innerHTML = '';
    priceEl = document.createElement('span');
    priceEl.className = 'live-price-main';
    changeEl = document.createElement('span');
    changeEl.className = 'live-price-change flat';
    changeEl.textContent = 'LIVE';
    cell.appendChild(priceEl);
    cell.appendChild(changeEl);
    return {{ priceEl: priceEl, changeEl: changeEl }};
  }}

  function updateCell(ticker, price, prevClose) {{
    var cells = getLivePriceCells(ticker);
    if (!cells.length) return;
    if (prevClose != null && isFinite(prevClose) && prevClose > 0) _prevClose[ticker] = prevClose;
    var priceStr = '$' + price.toFixed(2);
    var last = _prev[ticker];
    var dir = (last != null) ? (price > last ? 'up' : price < last ? 'dn' : null) : null;
    _prev[ticker] = price;

    cells.forEach(function(cell) {{
      var shell = ensureLivePriceCell(cell);
      var priceEl = shell.priceEl;
      var changeEl = shell.changeEl;
      var isFirstPrice = !priceEl.dataset.inited;
      priceEl.dataset.inited = '1';
      if (isFirstPrice) {{
        reelInit(priceEl, priceStr, null);
      }} else {{
        reelUpdate(priceEl, priceStr, dir ? cell.closest('tr, .scanner-card') : null, dir);
      }}

      var baseline = _prevClose[ticker];
      if (baseline && isFinite(baseline) && baseline > 0) {{
        var pct = ((price - baseline) / baseline) * 100;
        var pctStr = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
        var pctDir = pct > 0 ? 'up' : pct < 0 ? 'dn' : 'flat';
        var isFirstChange = !changeEl.dataset.inited;
        changeEl.dataset.inited = '1';
        if (isFirstChange) {{
          reelInit(changeEl, pctStr, null);
        }} else {{
          reelUpdate(changeEl, pctStr, null, pctDir === 'flat' ? null : pctDir);
        }}
        changeEl.className = 'live-price-change ' + pctDir;
      }} else {{
        changeEl.className = 'live-price-change flat';
        changeEl.textContent = 'LIVE';
      }}

      var card = cell.closest('.scanner-card');
      if (card && dir) {{
        card.classList.remove('live-up', 'live-dn');
        var _dir = dir;
        requestAnimationFrame(function() {{
          card.classList.add(_dir === 'up' ? 'live-up' : 'live-dn');
          setTimeout(function() {{ card.classList.remove('live-up', 'live-dn'); }}, 800);
        }});
      }}
    }});
  }}

  function connect() {{
    if (!SCANNER_RUNTIME.finnhubWs || !TOKEN) return;
    if (_socket && _socket.readyState <= 1) return;
    _socket = new WebSocket('wss://ws.finnhub.io?token=' + TOKEN);

    _socket.addEventListener('open', function() {{
      var tickers = getTickers();
      tickers.forEach(function(t) {{
        if (!_subbed[t]) {{
          _socket.send(JSON.stringify({{type:'subscribe', symbol:t}}));
          _subbed[t] = 1;
        }}
      }});
    }});

    _socket.addEventListener('message', function(event) {{
      var msg = JSON.parse(event.data);
      if (msg.type === 'trade' && msg.data) {{
        msg.data.forEach(function(trade) {{
          updateCell(trade.s, trade.p);
        }});
      }}
    }});

    _socket.addEventListener('close', function() {{
      // Reconnect after 5s
      setTimeout(connect, 5000);
    }});

    _socket.addEventListener('error', function() {{
      _socket.close();
    }});
  }}

  function pollFallback() {{
    // The internal quote API is cached and same-origin, so we can hydrate every
    // rendered card without relying on viewport ordering or proxy budgets.
    var tickers = getTickers().slice(0, 48);
    if (!tickers.length) return;
    scannerQuoteJson(tickers, 5000)
      .then(function(rows) {{
        (rows || []).forEach(function(row) {{
          if (!row || !row.ticker || row.price == null) return;
          updateCell(String(row.ticker).toUpperCase(), Number(row.price), Number(row.prev_close || 0));
        }});
      }})
      .catch(function() {{}});
  }}

  // Countdown display
  var cdEl = document.getElementById('scanner-price-cd');
  if (!SCANNER_RUNTIME.clientQuotes) {{
    if (cdEl) cdEl.textContent = 'server snapshot';
    return;
  }}
  function tickCd() {{
    if (cdEl) cdEl.textContent = _cdSec + 's';
    _cdSec--;
    if (_cdSec < 0) _cdSec = isMarketHours() ? 10 : isPreMarket() ? 15 : 60;
  }}

  // Start
  setTimeout(function() {{
    if (SCANNER_RUNTIME.finnhubWs) connect();
    pollFallback();
    tickCd();
    setInterval(tickCd, 1000);
    var fallbackInterval = isMarketHours() ? 15000 : isPreMarket() ? 20000 : 60000;
    setInterval(pollFallback, fallbackInterval);
  }}, 2000);
}})();

// ── Global tooltip (position:fixed — works inside overflow:hidden tables) ─────
(function() {{
  var tip = document.createElement('div');
  tip.id = 'global-tip';
  document.body.appendChild(tip);
  var _tipTarget = null;

  document.addEventListener('mouseover', function(ev) {{
    var el = ev.target.closest('[data-tip]');
    if (!el) return; // do NOT hide here — mouseout handles it
    if (el === _tipTarget) return; // already showing for this element
    _tipTarget = el;
    tip.textContent = el.getAttribute('data-tip');
    var x = ev.clientX + 14, y = ev.clientY - 36;
    if (y < 8) y = ev.clientY + 18;
    tip.style.left = x + 'px';
    tip.style.top  = y + 'px';
    tip.style.display = 'block';
  }});
  document.addEventListener('mousemove', function(ev) {{
    if (!_tipTarget) return;
    var x = ev.clientX + 14, y = ev.clientY - 36;
    var w = tip.offsetWidth;
    if (x + w > window.innerWidth - 8) x = ev.clientX - w - 10;
    if (y < 8) y = ev.clientY + 18;
    tip.style.left = x + 'px';
    tip.style.top  = y + 'px';
  }});
  document.addEventListener('mouseout', function(ev) {{
    var to = ev.relatedTarget;
    if (!to || !to.closest('[data-tip]')) {{
      tip.style.display = 'none';
      _tipTarget = null;
    }}
  }});
  // Touch: briefly show tooltip on tap, dismiss after 2.5s
  document.addEventListener('touchstart', function(ev) {{
    var el = ev.target.closest('[data-tip]');
    if (!el) return;
    var rect = el.getBoundingClientRect();
    tip.textContent = el.getAttribute('data-tip');
    tip.style.left  = Math.min(rect.left, window.innerWidth - tip.offsetWidth - 10) + 'px';
    tip.style.top   = Math.max(rect.top - tip.offsetHeight - 8, 8) + 'px';
    tip.style.display = 'block';
    setTimeout(function() {{ tip.style.display = 'none'; _tipTarget = null; }}, 2500);
  }});
}})();

// ── 🌐 Macro dot → scroll to Prediction Markets ───────────────────────────────
document.addEventListener('click', function(ev) {{
  var el = ev.target.closest('.macro-dot, .macro-badge');
  if (!el) return;
  var target = document.getElementById('polymarket');
  if (target) target.scrollIntoView({{behavior:'smooth', block:'start'}});
}});

// ── Premarket signal lock banner ─────────────────────────────────────────────
(function() {{
  function isSignalLockWindow(parts) {{
    if (!isETWeekday(parts)) return false;
    var totalMins = parts.hour * 60 + parts.minute;
    return totalMins >= (3 * 60 + 15) && totalMins < (3 * 60 + 30);
  }}

  function isRevealMoment(parts) {{
    return isETWeekday(parts) && (parts.hour * 60 + parts.minute) >= (3 * 60 + 30);
  }}

  function pad(n) {{ return n < 10 ? '0' + n : '' + n; }}
  var _digits = {{}};

  function buildReelHTML() {{
    var t = getETParts(new Date());
    var H = pad(t.hour), M = pad(t.minute), S = pad(t.second);
    _digits = {{H1:H[0],H2:H[1],M1:M[0],M2:M[1],S1:S[0],S2:S[1]}};
    return '<div class="ph-reels">' +
      '<div class="ph-reel" id="phr-H1"><span>' + H[0] + '</span></div>' +
      '<div class="ph-reel" id="phr-H2"><span>' + H[1] + '</span></div>' +
      '<span class="ph-colon">:</span>' +
      '<div class="ph-reel" id="phr-M1"><span>' + M[0] + '</span></div>' +
      '<div class="ph-reel" id="phr-M2"><span>' + M[1] + '</span></div>' +
      '<span class="ph-colon">:</span>' +
      '<div class="ph-reel" id="phr-S1"><span>' + S[0] + '</span></div>' +
      '<div class="ph-reel" id="phr-S2"><span>' + S[1] + '</span></div>' +
      '<span class="ph-et">ET</span>' +
      '</div>';
  }}

  function tickReels() {{
    var t = getETParts(new Date());
    var H = pad(t.hour), M = pad(t.minute), S = pad(t.second);
    var next = {{H1:H[0],H2:H[1],M1:M[0],M2:M[1],S1:S[0],S2:S[1]}};
    ['H1','H2','M1','M2','S1','S2'].forEach(function(pos) {{
      if (next[pos] !== _digits[pos]) {{
        var el = document.getElementById('phr-' + pos);
        if (el) {{ el.innerHTML = '<span class="spinning">' + next[pos] + '</span>'; }}
        _digits[pos] = next[pos];
      }}
    }});
  }}

  var nowParts = getETParts(new Date());
  if (!isSignalLockWindow(nowParts)) return;

  var banner = document.createElement('div');
  banner.id = 'power-hour-banner';
  banner.className = 'power-hour-banner';
  banner.innerHTML = '<div class="ph-title"><span class="ph-dot"></span><span>Premarket board finalizing</span></div>' +
    buildReelHTML() +
    '<div class="ph-sub">Cerebro is locking the pre-market board now. The fresh Scanner build publishes at 3:30 AM ET, then the public page refreshes hourly after the open.</div>';
  document.body.appendChild(banner);

  var ticker = setInterval(function() {{
    var parts = getETParts(new Date());
    tickReels();
    if (isRevealMoment(parts)) {{
      clearInterval(ticker);
      banner.classList.add('is-fading');
      setTimeout(function() {{
        if (banner.parentNode) banner.parentNode.removeChild(banner);
      }}, 520);
    }}
  }}, 1000);
}})();

// ── Sector headlines expander ─────────────────────────────────────────────────
function toggleSectorHeadlines(btn) {{
  var card = btn.closest('.sector-card');
  if (!card) return;
  var panel = card.querySelector('.sc-headlines');
  if (!panel) return;
  var open = panel.hasAttribute('hidden');
  if (open) {{ panel.removeAttribute('hidden'); btn.textContent = "Hide ▴"; btn.setAttribute('aria-expanded','true'); }}
  else     {{ panel.setAttribute('hidden','');   btn.textContent = "Why it's hot ▾"; btn.setAttribute('aria-expanded','false'); }}
}}

// ── Sector Filter ─────────────────────────────────────────────────────────────
var _activeSector = 'all';

function setSectorFilter(btn, sector) {{
  _activeSector = sector;

  // Update button active states
  document.querySelectorAll('.sec-filter-btn').forEach(function(b) {{
    b.classList.toggle('active', b === btn);
  }});

  // Dim non-selected sector cards
  document.querySelectorAll('[data-sector-card]').forEach(function(card) {{
    if (sector === 'all') {{
      card.classList.remove('dimmed');
    }} else {{
      var match = card.getAttribute('data-sector-card') === sector;
      card.classList.toggle('dimmed', !match);
    }}
  }});

  // Filter table rows (tr.sr) AND gap play cards (.sc-filterable)
  function filterElements(elements, sector) {{
    var visCount = 0;
    elements.forEach(function(el) {{
      if (sector === 'all') {{
        el.style.display = '';
        visCount++;
      }} else {{
        var secs = (el.getAttribute('data-sector') || '').split(' ');
        var match = secs.indexOf(sector) !== -1;
        el.style.display = match ? '' : 'none';
        if (match) visCount++;
      }}
    }});
    return visCount;
  }}

  // Table rows
  var tables = document.querySelectorAll('table');
  tables.forEach(function(tbl) {{
    var rows = tbl.querySelectorAll('tr.sr');
    if (!rows.length) return;
    var visCount = filterElements(rows, sector);
    var msg = tbl.parentElement.querySelector('.sector-empty-msg');
    if (msg) {{
      if (visCount === 0 && sector !== 'all') {{
        msg.classList.add('visible');
        var secLabel = sector.replace('_',' ').replace(/\\b\\w/g, function(c){{return c.toUpperCase();}});
        msg.textContent = 'No ' + secLabel + ' plays flagged today.';
      }} else {{
        msg.classList.remove('visible');
      }}
    }}
  }});

  // Gap play cards
  var grids = document.querySelectorAll('.scanner-grid');
  grids.forEach(function(grid) {{
    var cards = grid.querySelectorAll('.sc-filterable');
    if (!cards.length) return;
    var visCount = filterElements(cards, sector);
    var msg = grid.parentElement.querySelector('.sector-empty-msg');
    if (msg) {{
      if (visCount === 0 && sector !== 'all') {{
        msg.classList.add('visible');
        var secLabel = sector.replace('_',' ').replace(/\\b\\w/g, function(c){{return c.toUpperCase();}});
        msg.textContent = 'No ' + secLabel + ' gap plays flagged today.';
      }} else {{
        msg.classList.remove('visible');
      }}
    }}
  }});

  // Update status label
  var status = document.getElementById('sector-filter-status');
  if (status) {{
    if (sector === 'all') {{
      status.style.display = 'none';
    }} else {{
      var secLabel = sector.replace('_',' ').replace(/\\b\\w/g, function(c){{return c.toUpperCase();}});
      status.style.display = 'block';
      status.textContent = 'Showing ' + secLabel + ' plays only — click "All Sectors" to reset';
    }}
  }}
}}

// ── Recalibrate filter buttons from actual DOM rows ───────────────────────────
// Counts tr.sr and .sc-filterable by data-sector; updates .sec-count spans
// and hides buttons where the DOM count is 0 (avoids ghost filters).
(function calibrateSectorButtons() {{
  function run() {{
    var domCounts = {{}};
    document.querySelectorAll('tr.sr').forEach(function(row) {{
      (row.getAttribute('data-sector') || '').split(' ').forEach(function(s) {{
        s = s.trim(); if (s) domCounts[s] = (domCounts[s] || 0) + 1;
      }});
    }});
    document.querySelectorAll('.sc-filterable').forEach(function(card) {{
      (card.getAttribute('data-sector') || '').split(' ').forEach(function(s) {{
        s = s.trim(); if (s) domCounts[s] = (domCounts[s] || 0) + 1;
      }});
    }});
    document.querySelectorAll('.sec-filter-btn[data-filter]').forEach(function(btn) {{
      var sector = btn.getAttribute('data-filter');
      if (sector === 'all') return;
      var count = domCounts[sector] || 0;
      var span = btn.querySelector('.sec-count');
      if (span) span.textContent = count;
      btn.style.display = count === 0 ? 'none' : '';
    }});
  }}
  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', run);
  }} else {{
    run();
  }}
}})();

// ── SEC Sector Heatmap ────────────────────────────────────────────────
(function() {{
  var container = document.getElementById('heatmap-container');
  if (!container) return;
  var data = _heatmapData;
  if (!data || !data.length) {{
    container.innerHTML = '<p class="hm-empty">No sector data available — check back after 4 AM ET.</p>';
    return;
  }}
  // Color palette per sector
  // Uniform dark background — sentiment is conveyed ONLY by the liquid fill
  // (green=bullish, rose=bearish) and border glow (emerald/rose/white).
  // Sector-specific colored backgrounds were clashing with the fill colors.
  var COLORS = {{}};
  var DEFAULT_COLOR = {{bg:'#12161e',border:'#30363d',text:'#c9d1d9'}};
  // Block size = total filing count (bullish + bearish + neutral); displayed number = top ticker's score
  var maxCount = Math.max.apply(null, data.map(function(d) {{ return (d.bullish||0) + (d.bearish||0) + (d.neutral||0); }})) || 1;
  data.forEach(function(d) {{
    var filingCount = (d.bullish || 0) + (d.bearish || 0) + (d.neutral || 0);
    var pct = Math.max(0.18, Math.min(1, filingCount / maxCount));
    var size = Math.round(80 + pct * 120); // 80px–200px wide
    var c = COLORS[d.name] || DEFAULT_COLOR;
    var block = document.createElement('div');
    var bullCount = d.bullish || 0;
    var bearCount = d.bearish || 0;
    var bullWt    = d.bullishWeight || 0;
    var bearWt    = d.bearishWeight || 0;
    // Posture is conviction-weighted, not count-weighted. A 1B/1Br sector
    // where the bearish filing carries far more gapper_score (e.g. an S-3
    // shelf vs. a routine 8-K) reads bearish — otherwise counts mislead the
    // eye away from the side that actually moves the tape.
    var posture = 'neutral';
    if (bullWt > bearWt) {{
      posture = 'bullish';
    }} else if (bearWt > bullWt) {{
      posture = 'bearish';
    }}
    // Pulse animation only on ⚡ sectors (top-3 conviction), not every tile.
    var hasPulse = d.pulse === true;
    block.className = 'hm-block hm-' + posture + (hasPulse ? ' hm-pulse' : '');
    block.style.cssText = [
      'width:' + size + 'px',
      'background:' + c.bg,
      'color:' + c.text
    ].join(';');
    block.setAttribute('data-sector', d.name);
    var sentIcon = posture === 'bullish' ? '▲' : posture === 'bearish' ? '▼' : '◆';
    var sentColor = posture === 'bullish' ? '#3fb950' : posture === 'bearish' ? '#f78166' : '#8b949e';
    var bearBadge = (d.bearish && d.bearish > 0)
      ? '<span style="color:#f78166;font-size:.62em;margin-left:4px">⚠' + d.bearish + '</span>'
      : '';
    var akerlofCount = d.akerlofCount || 0;
    var neutCount = d.neutral || 0;
    var tooltipBase = d.label + ' — Lead: ' + (d.topTicker || '?') + ' score ' + (d.topScore || d.score) +
      ' · ' + bullCount + ' bullish / ' + bearCount + ' bearish / ' + neutCount + ' unscored filings today' +
      ' · conviction weight ' + bullWt.toFixed(0) + 'B / ' + bearWt.toFixed(0) + 'Br';
    var tooltipExtra = '';
    if (d.pulse && akerlofCount > 0) {{
      tooltipExtra = ' | ⚡ Sector Pulse High + 🏅 Akerlof Signal detected: Institutional information gap is widening in ' + d.label +
        ' (' + akerlofCount + ' ticker' + (akerlofCount > 1 ? 's' : '') + ' with elevated filing opacity today)';
    }} else if (d.pulse) {{
      tooltipExtra = ' | ⚡ High-conviction filing detected in this sector';
    }} else if (akerlofCount > 0) {{
      tooltipExtra = ' | 🏅 Akerlof: ' + akerlofCount + ' ticker' + (akerlofCount > 1 ? 's' : '') + ' with information asymmetry signal';
    }}
    block.setAttribute('data-tip', tooltipBase + tooltipExtra);
    var pulseLabel = d.pulse ? ' ⚡' : '';
    var akerlofLabel = (akerlofCount > 0 && !d.pulse) ? ' 🏅' : (d.pulse && akerlofCount > 0 ? ' ⚡🏅' : pulseLabel);
    // ── Macro Pressure indicator ──────────────────────────────────────
    var mp     = d.macroPressure || 1.0;
    var mpSig  = d.macroSignal   || 'neutral';
    var mpHtml = '';
    if (mpSig === 'strong_tailwind' || mpSig === 'tailwind') {{
      mpHtml = '<div class="hm-macro-badge hm-macro-tail">🌐▲ ' + mp.toFixed(2) + 'x atm</div>';
    }} else if (mpSig === 'strong_headwind' || mpSig === 'headwind') {{
      mpHtml = '<div class="hm-macro-badge hm-macro-head">🌐▼ ' + mp.toFixed(2) + 'x atm</div>';
    }}
    block.innerHTML =
      '<div class="hm-label">' + d.label + akerlofLabel + '</div>' +
      '<div class="hm-score">' + (d.topScore || d.score) + '</div>' +
      (d.topTicker ? '<div class="hm-ticker">' + d.topTicker + bearBadge + '</div>' : '') +
      '<div style="font-size:.6em;margin-top:3px;color:' + sentColor + '">' + sentIcon + ' ' +
        bullCount + 'B / ' + bearCount + 'Br' +
        (neutCount > 0 ? ' <span style="color:#8b949e">(' + neutCount + ')</span>' : '') +
        '</div>' +
      mpHtml;
    // Liquid-fill: fill height tracks conviction-weighted dominance, not raw
    // count. Matches the posture icon above so the visual and the decision
    // agree.
    var fillTotal = bullWt + bearWt;
    var fillClass = 'hm-fill-neutral';
    var fillPct = 50;
    if (fillTotal > 0) {{
      if (bullWt > bearWt) {{
        fillClass = 'hm-fill-bull';
        fillPct = (bullWt / fillTotal) * 100;
      }} else if (bearWt > bullWt) {{
        fillClass = 'hm-fill-bear';
        fillPct = (bearWt / fillTotal) * 100;
      }}
    }}
    var fillEl = document.createElement('div');
    fillEl.className = 'hm-fill ' + fillClass;
    fillEl.setAttribute('data-fill-pct', fillPct.toFixed(1));
    fillEl.style.height = fillPct.toFixed(1) + '%';
    var w1 = document.createElement('div');
    w1.className = 'hm-fill-wave';
    fillEl.appendChild(w1);
    var w2 = document.createElement('div');
    w2.className = 'hm-fill-wave2';
    fillEl.appendChild(w2);
    var caustic = document.createElement('div');
    caustic.className = 'hm-fill-caustic';
    fillEl.appendChild(caustic);
    var spec = document.createElement('div');
    spec.className = 'hm-fill-spec';
    fillEl.appendChild(spec);
    block.insertBefore(fillEl, block.firstChild);
    block.addEventListener('click', function() {{
      var isSame = block.classList.contains('hm-selected');
      var prev = container.querySelector('.hm-block.hm-selected');
      if (prev) prev.classList.remove('hm-selected');
      if (isSame) {{
        _hmClose();
      }} else {{
        block.classList.add('hm-selected');
        _hmOpenL1(d);
        // Activate matching sector filter button
        var sectorBtn = document.querySelector('.sec-filter-btn[data-filter="' + d.name + '"]');
        if (sectorBtn && sectorBtn.style.display !== 'none') {{
          setSectorFilter(sectorBtn, d.name);
          sectorBtn.scrollIntoView({{behavior:'smooth', block:'nearest', inline:'center'}});
        }} else {{
          var allBtn = document.querySelector('.sec-filter-btn[data-filter="all"]');
          setSectorFilter(allBtn, 'all');
        }}
        setTimeout(function() {{
          var ranked = document.getElementById('ranked');
          if (ranked) ranked.scrollIntoView({{behavior:'smooth', block:'start'}});
        }}, 200);
      }}
    }});
    container.appendChild(block);
  }});

  // ── 4-Level GICS Drill-Down State Machine ──────────────────────────────
  var _hmState = {{level:0, sector:null, ig:null, industry:null}};
  var _ddPanel  = document.getElementById('hm-drilldown');

  function _hmClose() {{
    _hmState = {{level:0, sector:null, ig:null, industry:null}};
    if (_ddPanel) _ddPanel.style.display = 'none';
    var sel = container.querySelector('.hm-block.hm-selected');
    if (sel) sel.classList.remove('hm-selected');
  }}

  function _hmOpenL1(sectorData) {{
    _hmState = {{level:1, sector:sectorData, ig:null, industry:null}};
    _hmRender();
  }}
  function _hmOpenL2(igData) {{
    _hmState.level = 2; _hmState.ig = igData; _hmState.industry = null;
    _hmRender();
  }}
  function _hmOpenL3(indData) {{
    _hmState.level = 3; _hmState.industry = indData;
    _hmRender();
  }}

  function _hmRender() {{
    if (!_ddPanel || !_hmState.sector) return;
    var s  = _hmState.sector;
    var ig = _hmState.ig;
    var ind= _hmState.industry;
    var lvl= _hmState.level;

    // ── Breadcrumb ──────────────────────────────────────────────────────
    var bc = '<div class="hm-breadcrumb">';
    if (lvl === 1) {{
      bc += '<span class="hm-bc-active">' + s.label + '</span>';
    }} else if (lvl === 2) {{
      bc += '<span class="hm-bc-item" id="hm-bc-s">' + s.label + '</span>';
      bc += '<span class="hm-bc-sep">›</span>';
      bc += '<span class="hm-bc-active">' + ig.name + '</span>';
    }} else {{
      bc += '<span class="hm-bc-item" id="hm-bc-s">' + s.label + '</span>';
      bc += '<span class="hm-bc-sep">›</span>';
      bc += '<span class="hm-bc-item" id="hm-bc-ig">' + ig.name + '</span>';
      bc += '<span class="hm-bc-sep">›</span>';
      bc += '<span class="hm-bc-active">' + ind.name + '</span>';
    }}
    bc += '</div>';

    // ── Level label ────────────────────────────────────────────────────
    var lvlLabels = ['','Industry Groups','Industries','Sub-Industries'];
    var items = lvl===1 ? s.industryGroups : lvl===2 ? ig.industries : ind.subIndustries;
    items = items || [];

    // ── Card HTML ──────────────────────────────────────────────────────
    var cardsHtml = '<div class="hm-dd-body">';
    if (!items.length) {{
      cardsHtml += '<p class="hm-empty">No ' + lvlLabels[lvl] + ' data mapped yet.</p>';
    }} else if (lvl === 1) {{
      // IG cards — clickable
      items.forEach(function(ig_) {{
        var topTks = (ig_.industries || []).slice(0,3)
          .map(function(i_) {{ return i_.topTicker; }}).filter(Boolean).join(' ');
        cardsHtml += '<div class="hm-ig-block" data-ig="' + ig_.name + '">' +
          '<div class="hm-ig-name">' + ig_.name + '</div>' +
          '<div class="hm-ig-tickers">' + (topTks || '—') + '</div>' +
          '<div class="hm-ig-stats">' + ig_.count + ' filing' + (ig_.count!==1?'s':'') +
            ' · Lead: ' + (ig_.topTicker||'?') + ' ' + ig_.topScore + '</div>' +
          '</div>';
      }});
    }} else if (lvl === 2) {{
      // Industry cards — clickable
      items.forEach(function(ind_) {{
        var topTks = (ind_.subIndustries || []).slice(0,3)
          .map(function(si_) {{ return si_.topTicker; }}).filter(Boolean).join(' ');
        cardsHtml += '<div class="hm-ind-block" data-ind="' + ind_.name + '">' +
          '<div class="hm-ind-name">' + ind_.name + '</div>' +
          '<div class="hm-ig-tickers">' + (topTks || '—') + '</div>' +
          '<div class="hm-ind-stats">' + ind_.count + ' filing' + (ind_.count!==1?'s':'') +
            ' · Lead: ' + (ind_.topTicker||'?') + ' ' + ind_.topScore + '</div>' +
          '</div>';
      }});
    }} else {{
      // Sub-Industry cards — leaf nodes, not clickable
      items.forEach(function(si_) {{
        var tkStr = (si_.tickers||[]).slice(0,6).join(' ');
        if ((si_.tickers||[]).length > 6) tkStr += ' +' + (si_.tickers.length-6);
        cardsHtml += '<div class="hm-si-block">' +
          '<div class="hm-si-name">' + si_.name + '</div>' +
          '<div class="hm-si-tickers">' + tkStr + '</div>' +
          '<div class="hm-si-stats">' + si_.count + ' filing' + (si_.count!==1?'s':'') +
            (si_.topTicker ? ' · Lead: ' + si_.topTicker + ' ' + si_.topScore : '') +
          '</div></div>';
      }});
    }}
    cardsHtml += '</div>';

    // ── Assemble panel ─────────────────────────────────────────────────
    _ddPanel.innerHTML =
      '<div class="hm-dd-header">' +
        '<span class="hm-dd-title">🔍 ' + lvlLabels[lvl] +
          '<span class="hm-dd-sector"> (' + items.length + ')</span></span>' +
        '<button class="hm-dd-close" id="hm-dd-close">✕ Close</button>' +
      '</div>' + bc + cardsHtml;
    _ddPanel.style.display = 'block';

    // ── Wire event listeners ───────────────────────────────────────────
    var closeBtn = document.getElementById('hm-dd-close');
    if (closeBtn) closeBtn.addEventListener('click', function(e) {{
      e.stopPropagation(); _hmClose();
    }});
    var bcS = document.getElementById('hm-bc-s');
    if (bcS) bcS.addEventListener('click', function() {{ _hmOpenL1(s); }});
    var bcIG = document.getElementById('hm-bc-ig');
    if (bcIG) bcIG.addEventListener('click', function() {{ _hmOpenL2(ig); }});

    // IG card clicks → L2
    if (lvl === 1) {{
      _ddPanel.querySelectorAll('.hm-ig-block').forEach(function(el) {{
        el.addEventListener('click', function() {{
          var igName = el.getAttribute('data-ig');
          var igObj = (s.industryGroups||[]).find(function(x){{return x.name===igName;}});
          if (igObj) _hmOpenL2(igObj);
        }});
      }});
    }}
    // Industry card clicks → L3
    if (lvl === 2) {{
      _ddPanel.querySelectorAll('.hm-ind-block').forEach(function(el) {{
        el.addEventListener('click', function() {{
          var indName = el.getAttribute('data-ind');
          var indObj = (ig.industries||[]).find(function(x){{return x.name===indName;}});
          if (indObj) _hmOpenL3(indObj);
        }});
      }});
    }}
  }}

}})();

// ── Filing Summary Popup Modal ────────────────────────────────────────
(function() {{
  // Create modal DOM once
  var overlay = document.createElement('div');
  overlay.className = 'fs-overlay hidden';
  overlay.id = 'fs-overlay';
  overlay.innerHTML = [
    '<div class="fs-modal" role="dialog" aria-modal="true">',
    '  <button class="fs-close" id="fs-close" aria-label="Close">✕</button>',
    '  <div class="fs-ticker" id="fs-ticker"></div>',
    '  <div class="fs-form" id="fs-form"></div>',
    '  <ul class="fs-bullets" id="fs-bullets"></ul>',
    '  <a class="fs-link" id="fs-link" href="#" target="_blank" rel="nofollow">View Full Filing on EDGAR ↗</a>',
    '  <div class="fs-all-links" id="fs-all-links"></div>',
    '</div>'
  ].join('');
  document.body.appendChild(overlay);

  function openModal(ticker, form, summaryRaw, href, allLinksRaw, filingCount) {{
    document.getElementById('fs-ticker').textContent = ticker || 'SEC Filing';
    document.getElementById('fs-form').textContent = form || '';
    var ul = document.getElementById('fs-bullets');
    ul.innerHTML = '';
    var bullets = (summaryRaw || '').split('|');
    bullets.forEach(function(b, i) {{
      if (!b.trim()) return;
      var li = document.createElement('li');
      li.textContent = b.trim();
      if (b.trim().charAt(0) === '⚠') li.className = 'warn';
      ul.appendChild(li);
    }});
    var link = document.getElementById('fs-link');
    link.href = href || '#';
    link.style.display = href && href !== '#' ? 'block' : 'none';
    // Render all filing links when cluster has multiple filings
    var allLinksEl = document.getElementById('fs-all-links');
    allLinksEl.innerHTML = '';
    if (allLinksRaw && allLinksRaw !== href) {{
      var links = allLinksRaw.split('|').filter(function(l) {{ return l.trim(); }});
      if (links.length > 1) {{
        var label = document.createElement('div');
        label.className = 'fs-all-links-label';
        label.textContent = 'All ' + (filingCount || links.length) + ' filings in this cluster:';
        allLinksEl.appendChild(label);
        links.forEach(function(url, i) {{
          var a = document.createElement('a');
          a.href = url.trim();
          a.target = '_blank';
          a.rel = 'nofollow';
          a.className = 'fs-cluster-link';
          a.textContent = 'Filing ' + (i + 1) + ' ↗';
          allLinksEl.appendChild(a);
        }});
      }}
    }}
    overlay.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }}

  function closeModal() {{
    overlay.classList.add('hidden');
    document.body.style.overflow = '';
  }}

  document.getElementById('fs-close').addEventListener('click', closeModal);
  overlay.addEventListener('click', function(ev) {{
    if (ev.target === overlay) closeModal();
  }});
  document.addEventListener('keydown', function(ev) {{
    if (ev.key === 'Escape') closeModal();
  }});

  // Intercept "View SEC Filing" link clicks (gap cards)
  document.addEventListener('click', function(ev) {{
    var link = ev.target.closest('.sc-sec-link');
    if (!link) return;
    var summary = link.getAttribute('data-summary');
    if (!summary) return;   // no summary → let link open normally
    ev.preventDefault();
    openModal(
      link.getAttribute('data-ticker'),
      link.getAttribute('data-form'),
      summary,
      link.href,
      link.getAttribute('data-all-links') || '',
      link.getAttribute('data-filing-count') || ''
    );
  }});

  // Intercept clickable ticker names (all tables)
  document.addEventListener('click', function(ev) {{
    var el = ev.target.closest('strong.clickable-ticker');
    if (!el) return;
    openModal(
      el.getAttribute('data-ticker'),
      el.getAttribute('data-form'),
      el.getAttribute('data-summary'),
      el.getAttribute('data-link') || '',
      el.getAttribute('data-all-links') || '',
      el.getAttribute('data-filing-count') || ''
    );
  }});

  // Intercept 📄 summary buttons (ranked table + insider cluster)
  document.addEventListener('click', function(ev) {{
    var btn = ev.target.closest('.summary-btn');
    if (!btn) return;
    var ticker = btn.getAttribute('data-ticker') || '';
    if (!ticker) {{
      var row = btn.closest('tr');
      if (row) {{
        var strong = row.querySelector('strong.ticker-link');
        if (strong) ticker = strong.textContent.trim();
      }}
    }}
    openModal(
      ticker,
      btn.getAttribute('data-form'),
      btn.getAttribute('data-summary'),
      btn.getAttribute('data-link'),
      btn.getAttribute('data-all-links') || '',
      btn.getAttribute('data-filing-count') || ''
    );
  }});
}})();

// ── Scanner → Cerebro branded handoff ───────────────────────────────────────
(function() {{
  function initCerebroHandoff() {{
  var overlay = document.getElementById('ce-transfer-overlay');
  if (!overlay || overlay.getAttribute('data-ce-bound') === 'true') return;
  overlay.setAttribute('data-ce-bound', 'true');
  var navTimer = null;
  var stageTimers = [];
  var fieldNodes = {{
    title: overlay.querySelector('[data-ce-transfer="title"]'),
    sub: overlay.querySelector('[data-ce-transfer="sub"]'),
    ticker: overlay.querySelector('[data-ce-transfer="ticker"]'),
    channel: overlay.querySelector('[data-ce-transfer="channel"]'),
    reason: overlay.querySelector('[data-ce-transfer="reason"]'),
    rank: overlay.querySelector('[data-ce-transfer="rank"]'),
    score: overlay.querySelector('[data-ce-transfer="score"]'),
    form: overlay.querySelector('[data-ce-transfer="form"]'),
    state: overlay.querySelector('[data-ce-transfer="state"]'),
    signalLead: overlay.querySelector('[data-ce-transfer="signal-lead"]'),
    signalContext: overlay.querySelector('[data-ce-transfer="signal-context"]'),
    signalLock: overlay.querySelector('[data-ce-transfer="signal-lock"]'),
  }};
  var stagePills = Array.prototype.slice.call(overlay.querySelectorAll('[data-ce-stage]'));

  function shortReason(value) {{
    value = (value || '').trim();
    if (!value) return 'Reason pending';
    return value.length > 44 ? value.slice(0, 41) + '…' : value;
  }}

  function transferValue(params, key, fallback) {{
    return (params.get(key) || fallback || '').trim();
  }}

  function clearStageTimers() {{
    stageTimers.forEach(function(timer) {{ clearTimeout(timer); }});
    stageTimers = [];
  }}

  function dismissOverlay() {{
    clearTimeout(navTimer);
    navTimer = null;
    clearStageTimers();
    overlay.classList.remove('show');
    overlay.setAttribute('aria-hidden', 'true');
    overlay.style.setProperty('--ce-progress', '0.22');
    stagePills.forEach(function(pill, pillIndex) {{
      pill.setAttribute('data-state', pillIndex === 0 ? 'active' : 'idle');
    }});
    if (fieldNodes.state) {{
      fieldNodes.state.textContent = 'Catalyst packet authenticated';
    }}
  }}

  function buildReasonFragments(value) {{
    return String(value || '')
      .split(/[|;]/)
      .map(function(chunk) {{ return chunk.replace(/\\s+/g, ' ').trim(); }})
      .filter(Boolean)
      .slice(0, 3);
  }}

  function setStage(index) {{
    stagePills.forEach(function(pill, pillIndex) {{
      pill.setAttribute('data-state', pillIndex < index ? 'done' : pillIndex === index ? 'active' : 'idle');
    }});
    var progress = index <= 0 ? 0.22 : index === 1 ? 0.62 : 1;
    overlay.style.setProperty('--ce-progress', String(progress));
    if (fieldNodes.state) {{
      fieldNodes.state.textContent = index <= 0
        ? 'Packet acquired and checksum verified'
        : index === 1
          ? 'Signal dossier mapped into the rail'
          : 'Cerebro lock frame primed';
    }}
  }}

  document.addEventListener('click', function(ev) {{
    var link = ev.target.closest('.sc-cerebro-link');
    if (!link) return;
    if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    ev.preventDefault();

    var href = link.getAttribute('href') || link.href || '';
    if (!href) return;

    var url;
    try {{
      url = new URL(href, window.location.origin);
    }} catch (err) {{
      window.location.href = href;
      return;
    }}

    var params = url.searchParams;
    if ((!params || !params.toString()) && url.hash && url.hash.indexOf('?') !== -1) {{
      params = new URLSearchParams(url.hash.slice(url.hash.indexOf('?') + 1));
    }}
    var ticker = transferValue(params, 'ticker', '—').toUpperCase();
    var channel = transferValue(params, 'channel', 'scanner uplink').replace(/[_-]+/g, ' ');
    var reason = shortReason(transferValue(params, 'reason', ''));
    var reasonFragments = buildReasonFragments(transferValue(params, 'reason', ''));
    var rank = transferValue(params, 'rank', '—');
    var score = transferValue(params, 'score', '—');
    var form = transferValue(params, 'form', '—');

    if (fieldNodes.title) fieldNodes.title.textContent = 'Ingesting ' + ticker + ' into Cerebro HUD';
    if (fieldNodes.sub) fieldNodes.sub.textContent = 'Docking the scanner packet into the command rail with rank, score, filing, and catalyst metadata preserved for target lock.';
    if (fieldNodes.ticker) fieldNodes.ticker.textContent = 'Ticker ' + ticker;
    if (fieldNodes.channel) fieldNodes.channel.textContent = channel || 'scanner uplink';
    if (fieldNodes.reason) fieldNodes.reason.textContent = reason;
    if (fieldNodes.rank) fieldNodes.rank.textContent = rank || '—';
    if (fieldNodes.score) fieldNodes.score.textContent = score || '—';
    if (fieldNodes.form) fieldNodes.form.textContent = form || '—';

    if (fieldNodes.signalLead) fieldNodes.signalLead.textContent = reasonFragments[0] || 'Primary catalyst packet attached';
    if (fieldNodes.signalContext) fieldNodes.signalContext.textContent = reasonFragments[1] || ('Channel ' + (channel || 'scanner uplink'));
    if (fieldNodes.signalLock) fieldNodes.signalLock.textContent = reasonFragments[2] || ('Rank ' + (rank || 'â€”') + ' • Score ' + (score || 'â€”'));

    dismissOverlay();
    overlay.classList.add('show');
    overlay.setAttribute('aria-hidden', 'false');
    setStage(0);
    stageTimers.push(setTimeout(function() {{ setStage(1); }}, 170));
    stageTimers.push(setTimeout(function() {{ setStage(2); }}, 380));
    navTimer = setTimeout(function() {{
      window.location.href = href;
    }}, 980);
  }});

  overlay.addEventListener('click', function(ev) {{
    if (ev.target === overlay) dismissOverlay();
  }});

  document.addEventListener('keydown', function(ev) {{
    if (ev.key === 'Escape') dismissOverlay();
  }});

  window.addEventListener('pageshow', dismissOverlay);
  window.addEventListener('pagehide', dismissOverlay);
  window.addEventListener('popstate', dismissOverlay);
  }}

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initCerebroHandoff, {{ once: true }});
  }} else {{
    initCerebroHandoff();
  }}
}})();

// ── Scroll-triggered reification / tactical viewport ────────────────────────
(function() {{
  // Skip all heavy scroll/pointer GPU effects on mobile
  if (window.innerWidth <= 640) return;

  var focusables = Array.from(document.querySelectorAll(
    '.spotlight, .countdown-bar, .scanner-card, .intel-shell, #heatmap-wrap, .sector-card, .track-card, .pm-card, .container-scroll-card'
  ));
  var containerCards = Array.from(document.querySelectorAll('.container-scroll-card'));
  if (!focusables.length) return;

  var rootStyle = document.documentElement.style;
  var lastY = window.scrollY || 0;
  var ticking = false;
  var resetTimer = null;

  function setMomentum(delta) {{
    var skew = Math.max(-14, Math.min(14, delta * 0.16));
    var drift = Math.max(-20, Math.min(20, delta * 1.2));
    rootStyle.setProperty('--scanner-scroll-skew', skew.toFixed(2) + 'deg');
    rootStyle.setProperty('--scanner-scroll-drift', drift.toFixed(2) + 'px');
    document.body.classList.toggle('scanner-scroll-fast', Math.abs(delta) > 18);
    clearTimeout(resetTimer);
    resetTimer = setTimeout(function() {{
      rootStyle.setProperty('--scanner-scroll-skew', '0deg');
      rootStyle.setProperty('--scanner-scroll-drift', '0px');
      document.body.classList.remove('scanner-scroll-fast');
    }}, 120);
  }}

  function updateFocus() {{
    var vh = window.innerHeight || 1;
    var center = vh * 0.5;
    var falloff = vh * 0.42;
    focusables.forEach(function(el) {{
      var rect = el.getBoundingClientRect();
      var mid = rect.top + rect.height / 2;
      var distance = Math.abs(center - mid);
      var proximity = Math.max(0, 1 - distance / falloff);
      var signed = Math.max(-1, Math.min(1, (center - mid) / falloff));
      el.style.setProperty('--focus-tilt', (signed * 3).toFixed(2) + 'deg');
      if (proximity > 0.58) {{
        el.classList.add('reify-focus');
        el.classList.remove('reify-muted');
      }} else if (proximity < 0.22) {{
        el.classList.add('reify-muted');
        el.classList.remove('reify-focus');
      }} else {{
        el.classList.remove('reify-focus');
        el.classList.remove('reify-muted');
      }}
    }});
  }}

  function updateContainerScroll() {{
    if (!containerCards.length) return;
    var vh = window.innerHeight || 1;
    containerCards.forEach(function(card) {{
      var rect = card.getBoundingClientRect();
      var progress = 1 - ((rect.top - vh * 0.16) / (vh * 0.92 + rect.height));
      progress = Math.max(0, Math.min(1, progress));
      var rotate = 18 - progress * 18;
      var scale = 0.88 + progress * 0.12;
      var lift = -84 + progress * 84;
      card.style.setProperty('--container-rotate', rotate.toFixed(2) + 'deg');
      card.style.setProperty('--container-scale', scale.toFixed(3));
      card.style.setProperty('--container-lift', lift.toFixed(2) + 'px');
      card.classList.toggle('is-deployed', progress > 0.56);
    }});
  }}

  function animateScore(el) {{
    if (!el || el.dataset.scoreAnimated === '1') return;
    var target = parseFloat(String(el.dataset.scoreTarget || el.textContent || '').trim());
    if (!isFinite(target)) return;
    el.dataset.scoreAnimated = '1';
    var decimals = Math.abs(target - Math.round(target)) > 0.001 ? 1 : 0;
    var start = performance.now();
    var duration = 420;
    function frame(now) {{
      var p = Math.min((now - start) / duration, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = (target * eased).toFixed(decimals).replace(/\\.0$/, '');
      if (p < 1) requestAnimationFrame(frame);
      else el.textContent = String(target).replace(/\\.0$/, '');
    }}
    el.textContent = '0';
    requestAnimationFrame(frame);
  }}

  function triggerAcquire(card) {{
    if (!card || card.dataset.acquired === '1') return;
    card.dataset.acquired = '1';
    card.classList.add('is-reifying');
    var ticker = card.querySelector('.sc-ticker strong');
    var score = card.querySelector('.sc-score-circle');
    if (ticker) ticker.classList.add('ticker-glitch-active');
    if (score) {{
      score.dataset.scoreTarget = score.textContent.trim();
      setTimeout(function() {{ animateScore(score); }}, 140);
    }}
    setTimeout(function() {{
      card.classList.remove('is-reifying');
      if (ticker) ticker.classList.remove('ticker-glitch-active');
    }}, 820);
  }}

  if ('IntersectionObserver' in window) {{
    var acquireObserver = new IntersectionObserver(function(entries) {{
      entries.forEach(function(entry) {{
        if (!entry.isIntersecting) return;
        triggerAcquire(entry.target);
        acquireObserver.unobserve(entry.target);
      }});
    }}, {{ threshold: 0.24 }});
    document.querySelectorAll('.scanner-card').forEach(function(card) {{
      acquireObserver.observe(card);
    }});
  }}

  function tick() {{
    ticking = false;
    var nextY = window.scrollY || 0;
    setMomentum(nextY - lastY);
    lastY = nextY;
    updateFocus();
    updateContainerScroll();
  }}

  function queueTick() {{
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(tick);
  }}

  window.addEventListener('scroll', queueTick, {{ passive: true }});
  window.addEventListener('resize', queueTick);
  document.addEventListener('pointermove', function(ev) {{
    document.documentElement.style.setProperty('--pointer-x', ev.clientX + 'px');
    document.documentElement.style.setProperty('--pointer-y', ev.clientY + 'px');
  }}, {{ passive: true }});
  updateFocus();
  updateContainerScroll();
}})();

(function initGapSparkles() {{
  // Skip canvas particle effects on mobile — saves GPU + battery
  if (window.innerWidth <= 640) return;

  function rand(min, max) {{
    return min + Math.random() * (max - min);
  }}

  function mountSparkles(root) {{
    if (!root || root.dataset.sparklesMounted === '1') return;
    root.dataset.sparklesMounted = '1';

    var canvas = document.createElement('canvas');
    root.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    if (!ctx) return;

    var particleColor = root.dataset.particleColor || '#10b981';
    var particleDensity = Math.max(80, Number(root.dataset.particleDensity || 400));
    var minSize = Math.max(0.2, Number(root.dataset.minSize || 0.4));
    var maxSize = Math.max(minSize + 0.1, Number(root.dataset.maxSize || 1.2));
    var speed = Math.max(0.4, Number(root.dataset.speed || 1.5));
    var background = root.dataset.background || 'transparent';
    var particles = [];
    var resizeObserver = null;
    var raf = 0;

    function spawn(width, height, resetToBottom) {{
      return {{
        x: Math.random() * width,
        y: resetToBottom ? height + rand(4, 28) : Math.random() * height,
        r: rand(minSize, maxSize),
        vx: rand(-0.08, 0.08) * speed,
        vy: rand(-0.34, -0.08) * speed,
        alpha: rand(0.22, 0.9),
        twinkle: rand(0.8, 2.4),
        drift: rand(-0.22, 0.22) * speed,
      }};
    }}

    function resize() {{
      var rect = root.getBoundingClientRect();
      var width = Math.max(1, rect.width);
      var height = Math.max(1, rect.height);
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = width + 'px';
      canvas.style.height = height + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      particles = Array.from({{ length: Math.min(particleDensity, Math.max(120, Math.round((width * height) / 2400))) }}, function() {{
        return spawn(width, height, false);
      }});
    }}

    function frame(time) {{
      var width = canvas.clientWidth || root.clientWidth || 1;
      var height = canvas.clientHeight || root.clientHeight || 1;
      ctx.clearRect(0, 0, width, height);
      if (background !== 'transparent') {{
        ctx.fillStyle = background;
        ctx.fillRect(0, 0, width, height);
      }}

      particles.forEach(function(particle, index) {{
        particle.x += particle.vx + Math.sin((time * 0.0012) + (index * 0.37)) * particle.drift * 0.04;
        particle.y += particle.vy;
        var pulse = 0.28 + Math.abs(Math.sin((time * 0.001 * particle.twinkle) + index)) * 0.72;

        if (particle.y < -24 || particle.x < -24 || particle.x > width + 24) {{
          particles[index] = particle = spawn(width, height, true);
        }}

        ctx.beginPath();
        ctx.fillStyle = particleColor;
        ctx.globalAlpha = particle.alpha * pulse;
        ctx.shadowColor = particleColor;
        ctx.shadowBlur = 14;
        ctx.arc(particle.x, particle.y, particle.r, 0, Math.PI * 2);
        ctx.fill();
      }});

      ctx.globalAlpha = 1;
      ctx.shadowBlur = 0;
      raf = requestAnimationFrame(frame);
    }}

    resize();
    raf = requestAnimationFrame(frame);
    window.addEventListener('resize', resize, {{ passive: true }});
    if ('ResizeObserver' in window) {{
      resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(root);
    }}

    root._sparklesCleanup = function() {{
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      if (resizeObserver) resizeObserver.disconnect();
    }};
  }}

  document.querySelectorAll('.sparkles-core').forEach(mountSparkles);
}})();
</script>

<div id="liq-toast-container"></div>
<div id="ce-transfer-overlay" class="ce-transfer-overlay" aria-hidden="true">
  <div class="ce-transfer-panel">
    <div class="ce-transfer-eyebrow">console ingest</div>
    <div class="ce-transfer-title" data-ce-transfer="title">Ingesting into Cerebro</div>
    <div class="ce-transfer-sub" data-ce-transfer="sub">Docking the current catalyst into the command rail with the live handoff context intact.</div>
    <div class="ce-transfer-stage">
      <div class="ce-transfer-stage-led">
        <div class="ce-transfer-stage-pill" data-ce-stage="0" data-state="active">
          <div class="ce-transfer-stage-k">Stage 01</div>
          <div class="ce-transfer-stage-v">Packet acquire</div>
        </div>
        <div class="ce-transfer-stage-pill" data-ce-stage="1" data-state="idle">
          <div class="ce-transfer-stage-k">Stage 02</div>
          <div class="ce-transfer-stage-v">Dossier map</div>
        </div>
        <div class="ce-transfer-stage-pill" data-ce-stage="2" data-state="idle">
          <div class="ce-transfer-stage-k">Stage 03</div>
          <div class="ce-transfer-stage-v">Lock frame prime</div>
        </div>
      </div>
    </div>
    <div class="ce-transfer-meta">
      <span class="ce-transfer-chip" data-ce-transfer="ticker">Ticker —</span>
      <span class="ce-transfer-chip" data-ce-transfer="channel">Channel —</span>
      <span class="ce-transfer-chip" data-ce-transfer="reason">Reason pending</span>
    </div>
    <div class="ce-transfer-grid">
      <div class="ce-transfer-cell">
        <div class="ce-transfer-label">Rank</div>
        <div class="ce-transfer-value" data-ce-transfer="rank">—</div>
      </div>
      <div class="ce-transfer-cell">
        <div class="ce-transfer-label">Score</div>
        <div class="ce-transfer-value" data-ce-transfer="score">—</div>
      </div>
      <div class="ce-transfer-cell">
        <div class="ce-transfer-label">Filing</div>
        <div class="ce-transfer-value" data-ce-transfer="form">—</div>
      </div>
    </div>
    <div class="ce-transfer-signal-grid">
      <div class="ce-transfer-signal">
        <div class="ce-transfer-signal-k">Lead Signal</div>
        <div class="ce-transfer-signal-v" data-ce-transfer="signal-lead">Primary catalyst packet attached</div>
      </div>
      <div class="ce-transfer-signal">
        <div class="ce-transfer-signal-k">Context</div>
        <div class="ce-transfer-signal-v" data-ce-transfer="signal-context">Channel scanner uplink</div>
      </div>
      <div class="ce-transfer-signal">
        <div class="ce-transfer-signal-k">Lock Intent</div>
        <div class="ce-transfer-signal-v" data-ce-transfer="signal-lock">Rank â€” â€¢ Score â€”</div>
      </div>
    </div>
    <div class="ce-transfer-progress"><span></span></div>
    <div class="ce-transfer-footer">
      <span class="ce-transfer-rail">Scanner → Cerebro</span>
      <span class="ce-transfer-state" data-ce-transfer="state">Catalyst packet authenticated</span>
    </div>
  </div>
</div>

<!-- ELEVENLABS CONVERSATIONAL AI WIDGET — compact sizing, non-blocking -->
<elevenlabs-convai agent-id="agent_1601km6tgerafswvnf26rj4x81bk"></elevenlabs-convai>
<script src="https://elevenlabs.io/convai-widget/index.js" async type="text/javascript"></script>
<style>
/* Shrink the ElevenLabs widget so it doesn't block content on web or mobile.
   Uses transform-scale so the internal web component still functions, plus
   bottom-right anchoring with a smaller footprint. Z-index reduced to 500 so
   nav, tooltips, and popups still sit above it. */
elevenlabs-convai {{
  position: fixed;
  bottom: 14px;
  right: 14px;
  z-index: 500;
  transform: scale(0.70);
  transform-origin: bottom right;
  pointer-events: auto;
}}
@media (max-width: 640px) {{
  elevenlabs-convai {{
    transform: scale(0.55);
    bottom: 8px;
    right: 8px;
  }}
}}
</style>

</body>
</html>"""

    OUT.write_text(page, encoding="utf-8")
    # Mirror scanner page to /scanner/ sub-path for landing-page routing
    _scanner_dir = DOCS / "scanner"
    _scanner_dir.mkdir(exist_ok=True)
    (_scanner_dir / "index.html").write_text(page, encoding="utf-8")
    write_scanner_artifact_status(
        build_scanner_artifact_status(scanner_counts, valid=True, page_bytes=len(page))
    )
    print(f"generate_seo_site: {len(page):,} bytes — "
          f"{len(gappers)}g {len(ranked)}r {len(squeezes)}sq {len(insiders)}ins "
          f"{len(darkpool)}dp {len(sectors)}sec")

    # ── PWA assets ────────────────────────────────────────────────────────────
    build_pwa_assets()

    # ── robots.txt ────────────────────────────────────────────────────────────
    robots = f"""User-agent: *
Allow: /

Sitemap: {SITE}/sitemap.xml
"""
    (DOCS / "robots.txt").write_text(robots)
    print("generate_seo_site: robots.txt written")

    # ── sitemap.xml ───────────────────────────────────────────────────────────
    sitemap_urls = [
        ("/", "daily", "1.0"),
        ("/scanner/", "daily", "0.9"),
        ("/cerebro/", "weekly", "0.9"),
        ("/pricing/", "weekly", "0.9"),
        ("/methodology/", "monthly", "0.8"),
        ("/how-to-trade-8k/", "monthly", "0.7"),
        ("/api/", "monthly", "0.8"),
        ("/cheat-sheet/", "monthly", "0.8"),
        ("/alerts/", "daily", "0.8"),
        ("/arcade/", "monthly", "0.7"),
        ("/compare/", "monthly", "0.8"),
        ("/options-flow/", "daily", "0.8"),
        ("/watchlist/", "daily", "0.8"),
        ("/heatmap/", "daily", "0.8"),
        ("/congress/", "daily", "0.8"),
        ("/preview/", "daily", "0.8"),
        ("/glossary/", "weekly", "0.9"),
    ]
    # Auto-discover glossary pages
    glossary_dir = DOCS / "glossary"
    if glossary_dir.exists():
        for sub in sorted(glossary_dir.iterdir()):
            if sub.is_dir() and (sub / "index.html").exists():
                sitemap_urls.append((f"/glossary/{sub.name}/", "monthly", "0.7"))
    sitemap_entries = "\n".join(
        f"  <url>\n    <loc>{SITE}{path}</loc>\n    <lastmod>{ISODATE}</lastmod>\n"
        f"    <changefreq>{freq}</changefreq>\n    <priority>{prio}</priority>\n  </url>"
        for path, freq, prio in sitemap_urls
    )
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{sitemap_entries}
</urlset>"""
    (DOCS / "sitemap.xml").write_text(sitemap)
    print("generate_seo_site: sitemap.xml written")

    # ── methodology page ──────────────────────────────────────────────────────
    meth_dir = DOCS / "methodology"
    meth_dir.mkdir(exist_ok=True)
    methodology_page = build_methodology_page(ga4_id)
    (meth_dir / "index.html").write_text(methodology_page, encoding="utf-8")
    print(f"generate_seo_site: methodology page {len(methodology_page):,} bytes")

    # ── 8-K guide page ────────────────────────────────────────────────────────
    guide_dir = DOCS / "how-to-trade-8k"
    guide_dir.mkdir(exist_ok=True)
    guide_page = build_8k_guide_page(ga4_id)
    (guide_dir / "index.html").write_text(guide_page, encoding="utf-8")
    print(f"generate_seo_site: 8-K guide page {len(guide_page):,} bytes")

    # ── API page ──────────────────────────────────────────────────────────────
    api_dir = DOCS / "api"
    api_dir.mkdir(exist_ok=True)
    api_page = build_api_page(ga4_id)
    (api_dir / "index.html").write_text(api_page, encoding="utf-8")
    print(f"generate_seo_site: API page {len(api_page):,} bytes")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
