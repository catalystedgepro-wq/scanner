#!/usr/bin/env python3
"""Classify SEC catalyst filings into gappers, value, and moat candidates."""

from __future__ import annotations

import csv
import gzip
import json
import os
import re
import time
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
INPUT = ROOT / "sec_catalyst_latest.csv"
CONFIG_PATH = ROOT / "scoring_config.json"

OUT_GAPPERS_CSV = ROOT / "sec_top_gappers.csv"
OUT_GAPPERS_TXT = ROOT / "sec_top_gappers_tickers.txt"
OUT_VALUE_CSV = ROOT / "sec_top_value.csv"
OUT_VALUE_TXT = ROOT / "sec_top_value_tickers.txt"
OUT_MOAT_CSV = ROOT / "sec_top_moat.csv"
OUT_MOAT_TXT = ROOT / "sec_top_moat_tickers.txt"
OUT_MOAT_CORE_CSV = ROOT / "sec_top_moat_core.csv"
OUT_MOAT_CORE_TXT = ROOT / "sec_top_moat_core_tickers.txt"
OUT_MOAT_EMERG_CSV = ROOT / "sec_top_moat_emerging.csv"
OUT_MOAT_EMERG_TXT = ROOT / "sec_top_moat_emerging_tickers.txt"
OUT_CLEAN_GAPPERS_CSV = ROOT / "sec_clean_gappers.csv"
OUT_CLEAN_GAPPERS_TXT = ROOT / "sec_clean_gappers_tickers.txt"
OUT_CLEAN_VALUE_CSV = ROOT / "sec_clean_value.csv"
OUT_CLEAN_VALUE_TXT = ROOT / "sec_clean_value_tickers.txt"
OUT_CLEAN_MOAT_CORE_CSV = ROOT / "sec_clean_moat_core.csv"
OUT_CLEAN_MOAT_CORE_TXT = ROOT / "sec_clean_moat_core_tickers.txt"

CACHE_FILE = ROOT / ".sec_filing_text_cache.json"
CACHE_QUOTE_FILE = ROOT / ".sec_quote_cache.json"
CACHE_SHARES_FILE = ROOT / ".sec_shares_cache.json"
CACHE_TTL_SEC = 48 * 3600
QUOTE_CACHE_TTL_SEC = 20 * 60
SHARES_CACHE_TTL_SEC = 7 * 24 * 3600

# 8-K Item map. Keys are canonical Item codes, values are short human labels.
# Only the items that actually move stocks are listed; others pass through.
EIGHTK_ITEM_LABELS: dict[str, str] = {
    "1.01": "Material Agreement",
    "1.02": "Terminated Agreement",
    "1.03": "Bankruptcy",
    "2.01": "Acquisition / Disposition",
    "2.02": "Earnings",
    "2.03": "Debt / Off-Balance Obligation",
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

_ITEM_RE = re.compile(r"Item\s+(\d\.\d{2})\b", re.IGNORECASE)


def extract_8k_items(text: str) -> list[str]:
    """Return ordered-unique list of Item codes found in 8-K text (e.g. ['2.02', '9.01'])."""
    if not text:
        return []
    seen: dict[str, None] = {}
    for m in _ITEM_RE.finditer(text[:12000]):
        code = m.group(1)
        if code not in seen:
            seen[code] = None
    return list(seen.keys())

POS_GAPPER = [
    "raises guidance",
    "guidance increased",
    "preliminary results",
    "record revenue",
    "earnings beat",
    "contract award",
    "awarded contract",
    "fda approval",
    "fda clearance",
    "definitive agreement",
    "merger agreement",
    "business combination agreement",
    "share repurchase program",
]
NEG_GAPPER = [
    "offering",
    "registered direct",
    "private placement",
    "atm program",
    "at-the-market",
    "dilution",
    "going concern",
    "bankruptcy",
    "chapter 11",
    "delist",
    "non-compliance",
]

POS_VALUE = [
    "share repurchase",
    "buyback",
    "dividend increase",
    "special dividend",
    "debt reduction",
    "deleveraging",
    "cost reduction",
    "restructuring plan",
    "cash flow",
    "free cash flow",
    "asset sale",
    "schedule 13d",
    "form 4",
]
NEG_VALUE = [
    "offering",
    "dilution",
    "convertible note",
    "warrant",
    "default",
    "going concern",
]

POS_MOAT = [
    "patent",
    "intellectual property",
    "exclusive",
    "sole supplier",
    "multi-year",
    "long-term agreement",
    "renewal",
    "backlog",
    "recurring revenue",
    "subscription",
    "market share gains",
    "pricing power",
    "gross margin expansion",
]
NEG_MOAT = [
    "customer concentration",
    "contract termination",
    "impairment",
    "material weakness",
    "non-compliance",
]

RISK_FLAGS = [
    "offering",
    "private placement",
    "atm program",
    "going concern",
    "bankruptcy",
    "delist",
    "non-compliance",
    "material weakness",
    "default",
]

YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols}"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=60d&interval=1d"
YAHOO_SPARK_URL = "https://query1.finance.yahoo.com/v8/finance/spark?symbols={symbols}&range=60d&interval=1d"
STOOQ_DAILY_URL = "https://stooq.com/q/d/l/?s={symbol}.us&i=d"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Investable quality thresholds used in value/moat ranking.
DEFAULT_CONFIG = {
    "investability": {"min_price": 3.0, "min_avg_vol": 250000, "min_mcap": 300000000},
    "moat_core": {"min_price": 5.0, "min_avg_vol": 500000, "min_mcap": 2000000000},
    "clean_presets": {
        "max_rows": 40,
        "severe_risks": ["offering", "private placement", "default", "bankruptcy", "delist", "going concern"],
        "gappers": {"min_score": 8, "max_recency_min": 240},
        "value": {"min_score": 12, "min_price": 5.0, "min_avg_vol": 500000},
        "moat_core": {"min_score": 14},
    },
}
CFG: dict[str, Any] = DEFAULT_CONFIG


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_CONFIG
    if not isinstance(raw, dict):
        return DEFAULT_CONFIG
    return _deep_merge(DEFAULT_CONFIG, raw)


def load_cache() -> dict[str, dict[str, str]]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(cache: dict[str, dict[str, str]]) -> None:
    CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")


def load_quote_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_QUOTE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_QUOTE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_quote_cache(cache: dict[str, dict[str, Any]]) -> None:
    CACHE_QUOTE_FILE.write_text(json.dumps(cache), encoding="utf-8")


def load_shares_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_SHARES_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_SHARES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_shares_cache(cache: dict[str, dict[str, Any]]) -> None:
    CACHE_SHARES_FILE.write_text(json.dumps(cache), encoding="utf-8")


def normalize_text(text: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def extract_sec_documents(raw_text: str) -> list[tuple[str, str]]:
    docs: list[tuple[str, str]] = []
    pattern = re.compile(r"(?is)<document>(.*?)</document>")
    type_pat = re.compile(r"(?is)<type>\s*([^\n<]+)")
    for m in pattern.finditer(raw_text):
        block = m.group(1)
        t = "UNKNOWN"
        tm = type_pat.search(block)
        if tm:
            t = tm.group(1).strip().upper()
        docs.append((t, block))
    return docs


def filter_relevant_text(raw_text: str, form: str) -> str:
    docs = extract_sec_documents(raw_text)
    selected: list[str] = []
    form_u = form.upper()
    wanted_types = [form_u, form_u.split()[0]]

    for doc_type, block in docs:
        if doc_type in wanted_types or doc_type.startswith("EX-99") or doc_type.startswith("EX99"):
            selected.append(block)

    if not selected:
        # Fallback: use filing body but trim aggressively.
        selected_text = raw_text[:25000]
    else:
        # Keep only a compact window from selected docs.
        selected_text = "\n".join(s[:15000] for s in selected)

    text = normalize_text(selected_text)

    # Focus on high-signal sections for 8-K/6-K style event filings.
    if form_u.startswith("8-K") or form_u.startswith("6-K"):
        section_hits = []
        for pat in [
            r"item 1\.01.{0,5000}",
            r"item 2\.02.{0,5000}",
            r"item 7\.01.{0,5000}",
            r"item 8\.01.{0,5000}",
            r"forward-looking statements.{0,3000}",
            r"press release.{0,7000}",
        ]:
            mm = re.search(pat, text, flags=re.IGNORECASE | re.DOTALL)
            if mm:
                section_hits.append(mm.group(0))
        if section_hits:
            text = " ".join(section_hits)

    return text[:30000]


def fetch_text(url: str, form: str, user_agent: str, cache: dict[str, dict[str, str]]) -> str:
    now = int(time.time())
    cache_key = url + f"|{form}|focused-v2"
    cached = cache.get(cache_key)
    if cached:
        ts = int(cached.get("ts", "0"))
        if now - ts <= CACHE_TTL_SEC:
            return cached.get("text", "")

    # Prefer full filing text when SEC index link is provided.
    fetch_url = url
    if url.endswith("-index.htm"):
        fetch_url = url[:-10] + ".txt"

    req = urllib.request.Request(fetch_url, headers={"User-Agent": user_agent, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    text = filter_relevant_text(raw, form)
    cache[cache_key] = {"ts": str(now), "text": text}
    return text


def has_phrase(text: str, phrase: str) -> bool:
    tokens = re.escape(phrase.strip())
    tokens = tokens.replace(r"\ ", r"\s+")
    return re.search(rf"\b{tokens}\b", text) is not None


def score_by_keywords(text: str, positive: list[str], negative: list[str]) -> tuple[int, list[str]]:
    score = 0
    tags: list[str] = []
    for kw in positive:
        if has_phrase(text, kw):
            score += 3
            tags.append(f"+{kw}")
    for kw in negative:
        if has_phrase(text, kw):
            score -= 3
            tags.append(f"-{kw}")
    return score, tags


def form_boost(form: str) -> tuple[int, int, int]:
    f = form.upper()
    gap = 0
    val = 0
    moat = 0
    if f.startswith("8-K"):
        gap += 8   # 8-K: best avg run (6.1%) — boosted from 6
        val += 4
        moat += 4
    elif f.startswith("6-K"):
        gap += 5   # 6-K: solid but below 8-K in avg run
        val += 3
        moat += 3
    elif f.startswith("S-3"):
        gap += 4   # S-3: 49% hit2 — underrated, boosted from 3
        val -= 1
    elif f == "424B2":
        gap -= 4   # 424B2: 17% hit2 — worst performer, penalise hard
        val -= 4
        moat -= 2
    elif f.startswith("424B"):
        gap += 3   # 424B3/4/5: 44-49% hit2 — performing well, reduced penalty
        val -= 2
        moat -= 1
    elif f.startswith("SC 13D") or f.startswith("SC 13G"):
        val += 5
        moat += 2
    elif f.startswith("NT 10-Q") or f.startswith("NT 10-K"):
        val -= 2
        moat -= 2
    elif f.startswith("4"):
        # Insider reports are more context for quality/value than immediate gap catalyst.
        gap -= 2
        val += 2
        moat += 1
    return gap, val, moat


def insider_signal_from_form4(text: str) -> tuple[int, list[str]]:
    score = 0
    tags: list[str] = []

    # Higher confidence insider buy signal
    if has_phrase(text, "transaction code p") or "<transactioncode>p</transactioncode>" in text:
        score += 5
        tags.append("+insider_buy_p")
    # Insider sell reduces value/moat conviction
    if has_phrase(text, "transaction code s") or "<transactioncode>s</transactioncode>" in text:
        score -= 3
        tags.append("-insider_sell_s")

    # Officer role confidence
    if has_phrase(text, "chief executive officer") or has_phrase(text, "ceo"):
        score += 3
        tags.append("+ceo")
    if has_phrase(text, "chief financial officer") or has_phrase(text, "cfo"):
        score += 2
        tags.append("+cfo")
    if has_phrase(text, "director"):
        score += 1
        tags.append("+director")
    if has_phrase(text, "10% owner") or has_phrase(text, "10 percent owner"):
        score += 1
        tags.append("+10pct_owner")

    # Large transaction hints
    if has_phrase(text, "shares acquired") or has_phrase(text, "acquired"):
        score += 1
        tags.append("+acquired")
    if has_phrase(text, "shares disposed") or has_phrase(text, "disposed"):
        score -= 1
        tags.append("-disposed")

    return score, tags


def recency_points(recency_min: int) -> int:
    if recency_min <= 60:
        return 8
    if recency_min <= 180:
        return 6
    if recency_min <= 360:
        return 4
    if recency_min <= 720:
        return 2
    return 0


def filing_time_boost(updated_utc: str) -> int:
    """Bonus gap points based on filing hour (ET).

    Data-driven from 2,013 matched outcome rows (sec_outcome_rows.csv):
      06h ET → 61% hit2  (+3)   pre-market surprise
      16-17h ET → 44% hit2  (+2)   after-close bulk filings
      19-20h ET → 50-54% hit2  (+2)   late evening gap setups
      07-10h ET → 17-39% hit2  (-2)   during-market = priced in fast
      12-14h ET → 24-26% hit2  (-1)   midday filings = low gap potential
    """
    if not updated_utc:
        return 0
    try:
        import datetime as _dt
        dt = _dt.datetime.fromisoformat(updated_utc)
        h = dt.hour  # hour in timezone from the ISO string (ET offset included)
        if h == 6:
            return 3   # 61% hit2 — pre-market surprise
        if h in (16, 17):
            return 2   # 44-43% hit2 — after-close filings
        if h in (19, 20):
            return 2   # 54-50% hit2 — late evening gap setups
        if h in (7, 8, 9, 10):
            return -2  # 17-33% hit2 — filed during market, algos price it in
        if h in (12, 13, 14):
            return -1  # 24-26% hit2 — midday filing, low gap potential
    except Exception:
        pass
    return 0


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_quote_batch(symbols: list[str], user_agent: str) -> dict[str, dict[str, Any]]:
    """Batch quote fetch via Yahoo Finance v7 API.

    NOTE: The v7 endpoint now returns 401 Unauthorized without valid session
    cookies/crumb.  This function is kept for compatibility but will typically
    return an empty dict.  The per-ticker chart API fallback in get_quote_data
    is the primary data source.
    """
    if not symbols:
        return {}
    url = YAHOO_QUOTE_URL.format(symbols=",".join(symbols))
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://finance.yahoo.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    out: dict[str, dict[str, Any]] = {}
    results = payload.get("quoteResponse", {}).get("result", [])
    for row in results:
        sym = str(row.get("symbol", "")).upper().strip()
        if not sym:
            continue
        out[sym] = {
            "price": row.get("regularMarketPrice"),
            "avg_vol_3m": row.get("averageDailyVolume3Month"),
            "market_cap": row.get("marketCap"),
        }
    return out


def fetch_spark_batch(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Batch price fetch via Yahoo Finance v8 spark API (no auth required, very fast).

    Returns price (last close) only — no volume data. Use fetch_yahoo_chart_quote
    for per-ticker volume when needed.
    """
    if not symbols:
        return {}
    url = YAHOO_SPARK_URL.format(symbols=",".join(symbols))
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://finance.yahoo.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        enc = resp.headers.get("Content-Encoding", "")
    if enc == "gzip":
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8", errors="ignore"))
    out: dict[str, dict[str, Any]] = {}
    for sym, info in data.items():
        if not isinstance(info, dict):
            continue
        closes = [c for c in (info.get("close") or []) if c is not None]
        if not closes:
            continue
        out[sym.upper()] = {"price": float(closes[-1]), "avg_vol_3m": None, "market_cap": None}
    return out


def fetch_yahoo_chart_quote(symbol: str) -> dict[str, Any]:
    """Fetch price and volume data via Yahoo Finance v8 chart API (no auth required).

    Returns price, 60-day average daily volume, and today's volume.
    Market cap is not available from this endpoint; the caller can estimate it
    from SEC shares-outstanding data (already handled in get_quote_data).
    """
    url = YAHOO_CHART_URL.format(symbol=symbol.upper())
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://finance.yahoo.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
        enc = resp.headers.get("Content-Encoding", "")
    if enc == "gzip":
        raw = gzip.decompress(raw)
    payload = json.loads(raw.decode("utf-8", errors="ignore"))

    result_list = payload.get("chart", {}).get("result") or []
    if not result_list:
        return {}
    result = result_list[0]
    meta = result.get("meta", {})

    price = meta.get("regularMarketPrice")
    if not price:
        return {}

    # Compute average daily volume from 60 days of historical data.
    quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
    vols: list[float] = [float(v) for v in (quotes.get("volume") or []) if v is not None and float(v) > 0]
    avg_vol = sum(vols) / len(vols) if vols else 0.0

    return {"price": float(price), "avg_vol_3m": avg_vol, "market_cap": None}


def fetch_stooq_quote(symbol: str, user_agent: str) -> dict[str, Any]:
    """Stooq CSV daily quote fetcher (used as secondary fallback).

    Note: Stooq may be unreliable or time out in certain environments.
    The Yahoo chart API (fetch_yahoo_chart_quote) is the preferred fallback.
    """
    url = STOOQ_DAILY_URL.format(symbol=symbol.lower())
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "text/csv"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) < 3 or not lines[0].lower().startswith("date,open,high,low,close,volume"):
        return {}
    data_rows = []
    for ln in lines[1:]:
        parts = ln.split(",")
        if len(parts) != 6:
            continue
        try:
            close = float(parts[4])
            vol = float(parts[5])
        except ValueError:
            continue
        data_rows.append((close, vol))
    if not data_rows:
        return {}
    last_close = data_rows[-1][0]
    vols = [v for _, v in data_rows[-60:]]
    avg_vol = sum(vols) / len(vols) if vols else 0
    return {"price": last_close, "avg_vol_3m": avg_vol, "market_cap": None}


def get_quote_data(tickers: list[str], user_agent: str, cache: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    now = int(time.time())
    needed: list[str] = []
    out: dict[str, dict[str, Any]] = {}

    for t in tickers:
        c = cache.get(t)
        cdata = c.get("data", {}) if c else {}
        has_useful = bool(cdata.get("price")) or bool(cdata.get("avg_vol_3m")) or bool(cdata.get("market_cap"))
        if c and now - int(c.get("ts", 0)) <= QUOTE_CACHE_TTL_SEC and has_useful:
            out[t] = cdata
        else:
            needed.append(t)

    # Fetch price + volume via Yahoo Finance chart API.
    # Cap at 50 tickers and 90 seconds total to avoid pipeline timeouts.
    deadline = time.time() + 90
    for t in needed[:50]:
        if time.time() > deadline:
            break
        try:
            data = fetch_yahoo_chart_quote(t)
        except Exception:
            data = {}
        out[t] = data
        cache[t] = {"ts": now, "data": data}

    # Mark remaining tickers as empty in cache so they don't retry next run.
    for t in needed[50:]:
        out[t] = {}
        cache[t] = {"ts": now, "data": {}}

    return out


def to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def extract_cik_from_link(link: str) -> str:
    m = re.search(r"/data/0*([0-9]{1,10})/", link)
    if not m:
        return ""
    return m.group(1).zfill(10)


def latest_shares_outstanding_from_facts(payload: dict[str, Any]) -> float:
    facts = payload.get("facts", {})
    dei = facts.get("dei", {})
    node = dei.get("EntityCommonStockSharesOutstanding", {})
    units = node.get("units", {})
    rows = units.get("shares", [])
    if not isinstance(rows, list):
        return 0.0

    best_val = 0.0
    best_key = ""
    for r in rows:
        val = to_float(r.get("val"))
        if val <= 0:
            continue
        filed = str(r.get("filed", ""))
        end = str(r.get("end", ""))
        key = f"{filed}|{end}"
        if key >= best_key:
            best_key = key
            best_val = val
    return best_val


def fetch_shares_outstanding(cik: str, user_agent: str) -> float:
    if not cik:
        return 0.0
    url = SEC_COMPANYFACTS_URL.format(cik=cik)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    return latest_shares_outstanding_from_facts(payload)


def get_shares_outstanding(
    cik: str, user_agent: str, cache: dict[str, dict[str, Any]]
) -> float:
    if not cik:
        return 0.0
    now = int(time.time())
    c = cache.get(cik)
    if c and now - int(c.get("ts", 0)) <= SHARES_CACHE_TTL_SEC:
        return to_float(c.get("shares"))
    shares = 0.0
    try:
        shares = fetch_shares_outstanding(cik, user_agent)
    except Exception:
        shares = 0.0
    cache[cik] = {"ts": now, "shares": shares}
    return shares


def investable_quality_points(price: float, avg_vol_3m: float, mcap: float) -> tuple[int, str]:
    if price <= 0 and avg_vol_3m <= 0 and mcap <= 0:
        return 0, "no_market_data"

    min_price = float(CFG["investability"]["min_price"])
    min_vol = float(CFG["investability"]["min_avg_vol"])
    min_mcap = float(CFG["investability"]["min_mcap"])

    score = 0
    flags = []
    if price >= min_price:
        score += 2
    else:
        score -= 3
        flags.append("low_price")

    if avg_vol_3m >= min_vol:
        score += 3
    else:
        score -= 3
        flags.append("thin_volume")

    if mcap <= 0:
        flags.append("no_mcap_data")
    elif mcap >= 10_000_000_000:
        score += 4
    elif mcap >= 2_000_000_000:
        score += 3
    elif mcap >= min_mcap:
        score += 1
    else:
        score -= 4
        flags.append("small_cap")

    return score, ";".join(flags)


def write_ranked(path_csv: Path, path_txt: Path, rows: list[dict[str, str]], score_key: str) -> None:
    # 2026-04-27 — apply the same dilution/largecap kill list to the broad
    # ranked output so historical eval and downstream consumers (email,
    # archive) all see the cleaned cohort, not just /scanner/'s clean lane.
    blocked_forms = {f.upper() for f in CFG.get("clean_presets", {}).get("blocked_forms", [])}
    blocked_largecap = {
        f.upper() for f in CFG.get("clean_presets", {}).get("blocked_when_largecap", [])
    }
    rows = [
        r
        for r in rows
        if r.get("form", "").upper() not in blocked_forms
        and not is_blocked_largecap(r, blocked_largecap)
    ]
    out_rows = sorted(rows, key=lambda r: (-int(r[score_key]), int(r["recency_min"]), r["ticker"]))
    with path_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticker",
                "form",
                "updated_utc",
                "recency_min",
                "gapper_score",
                "value_score",
                "moat_score",
                "insider_signal_score",
                "risk_flags",
                "market_flags",
                "tags",
                "items",
                "price",
                "avg_vol_3m",
                "market_cap",
                "link",
            ],
        )
        writer.writeheader()
        writer.writerows(out_rows)

    with path_txt.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(r["ticker"] + "\n")


def is_moat_core(row: dict[str, str]) -> bool:
    min_price = float(CFG["moat_core"]["min_price"])
    min_vol = float(CFG["moat_core"]["min_avg_vol"])
    min_mcap = float(CFG["moat_core"]["min_mcap"])
    price = to_float(row.get("price"))
    avg_vol = to_float(row.get("avg_vol_3m"))
    mcap = to_float(row.get("market_cap"))
    return (
        price >= min_price
        and avg_vol >= min_vol
        and mcap >= min_mcap
    )


def has_severe_risk(row: dict[str, str]) -> bool:
    severe_risks = {x.lower() for x in CFG["clean_presets"]["severe_risks"]}
    risks = {r.strip() for r in (row.get("risk_flags") or "").split(";") if r.strip()}
    return any(r in severe_risks for r in risks)


# Cluster analysis 2026-04-27 (analyze_loser_clusters.py) showed:
#   form_424_dilution|cap_large_gt10b   n=157  hit 6.4%  (worst single drag)
#   form_8K_general|cap_large_gt10b     n=95   hit 23.2% (-20.7pp vs overall)
#   form_4_insider|cap_large_gt10b      n=85   hit 23.5% (-20.3pp vs overall)
# Forms in blocked_when_largecap get dropped when market_cap >= LARGECAP_CEILING.
LARGECAP_CEILING = 10_000_000_000


def is_blocked_largecap(row: dict[str, str], blocked_set: set[str]) -> bool:
    """Drop forms in blocked_when_largecap when market_cap >= 10B.

    Wired 2026-04-27 from scoring_config.json:clean_presets.blocked_when_largecap.
    Empirical lift: pre-filter drops 337 historical picks at 22% hit rate; the
    surviving cohort hit rate rises mechanically because the worst tail is gone.
    """
    if not blocked_set:
        return False
    form = (row.get("form") or "").strip().upper()
    if form not in blocked_set:
        return False
    mcap = to_float(row.get("market_cap"))
    if mcap <= 0:
        return False  # unknown cap → don't filter, keep visibility
    return mcap >= LARGECAP_CEILING


def select_clean_gappers(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    min_score   = int(CFG["clean_presets"]["gappers"]["min_score"])
    max_recency = int(CFG["clean_presets"]["gappers"]["max_recency_min"])
    max_rows    = int(CFG["clean_presets"]["max_rows"])
    blocked_forms = {f.upper() for f in CFG["clean_presets"].get("blocked_forms", [])}
    blocked_largecap = {f.upper() for f in CFG["clean_presets"].get("blocked_when_largecap", [])}
    # v16: enforce min average volume on clean gappers (bucket analysis showed
    # n=120 score>=15 + vol>=100k hit 55.8% vs 45% without vol floor).
    min_avg_vol = float(CFG["clean_presets"].get("volume_floor", {}).get("min_vol_day", 0))
    selected = [
        r
        for r in rows
        if int(r.get("gapper_score", "0")) >= min_score
        and int(r.get("recency_min", "999999")) <= max_recency
        and not has_severe_risk(r)
        and r.get("form", "").upper() not in blocked_forms
        and not is_blocked_largecap(r, blocked_largecap)
        and (min_avg_vol == 0 or to_float(r.get("avg_vol_3m")) == 0 or to_float(r.get("avg_vol_3m")) >= min_avg_vol)
    ]
    selected.sort(key=lambda r: (-int(r["gapper_score"]), int(r["recency_min"]), r["ticker"]))
    return selected[:max_rows]


def select_clean_value(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    min_score = int(CFG["clean_presets"]["value"]["min_score"])
    min_price = float(CFG["clean_presets"]["value"]["min_price"])
    min_vol = float(CFG["clean_presets"]["value"]["min_avg_vol"])
    max_rows = int(CFG["clean_presets"]["max_rows"])
    selected = [
        r
        for r in rows
        if int(r.get("value_score", "0")) >= min_score
        and to_float(r.get("price")) >= min_price
        and to_float(r.get("avg_vol_3m")) >= min_vol
        and not has_severe_risk(r)
    ]
    selected.sort(key=lambda r: (-int(r["value_score"]), int(r["recency_min"]), r["ticker"]))
    return selected[:max_rows]


def select_clean_moat_core(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    min_score = int(CFG["clean_presets"]["moat_core"]["min_score"])
    max_rows = int(CFG["clean_presets"]["max_rows"])
    selected = [
        r
        for r in rows
        if is_moat_core(r)
        and int(r.get("moat_score", "0")) >= min_score
        and not has_severe_risk(r)
    ]
    selected.sort(key=lambda r: (-int(r["moat_score"]), int(r["recency_min"]), r["ticker"]))
    return selected[:max_rows]


def main() -> int:
    global CFG
    CFG = load_config()

    # Load macro gravity multipliers (FRED-based sector weights)
    _macro_multipliers: dict = {}
    _macro_env = "neutral"
    try:
        import json as _json
        _ml = _json.loads((ROOT / "macro_layer.json").read_text(encoding="utf-8"))
        _macro_multipliers = _ml.get("sector_multipliers", {})
        _macro_env = _ml.get("environment", "neutral")
        print(f"classify: macro_env={_macro_env} multipliers loaded for {len(_macro_multipliers)} sectors")
    except Exception as _e:
        print(f"classify: macro_layer.json unavailable ({_e}), no gravity applied")

    _sector_lookup: dict = {}
    try:
        _sector_lookup = _json.loads((ROOT / "sector_lookup.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    _nobel_boosts: dict = {}
    try:
        _ns = _json.loads((ROOT / "nobel_signals.json").read_text(encoding="utf-8"))
        for _t, _sig in _ns.get("tickers", {}).items():
            _nobel_boosts[_t] = _sig.get("composite_boost", 1.0)
        print(f"classify: nobel_signals loaded for {len(_nobel_boosts)} tickers")
    except Exception:
        pass

    user_agent = os.getenv(
        "SEC_USER_AGENT",
        "LocalScanner/1.0 (Catalyst Edge Maintainers Catalyst@gmail.com)",
    )

    cache = load_cache()
    quote_cache = load_quote_cache()
    shares_cache = load_shares_cache()
    rows: list[dict[str, str]] = []
    by_ticker: dict[str, dict[str, str]] = {}
    source_rows: list[dict[str, str]] = []

    with INPUT.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_rows.append(row)

    tickers = sorted(
        {
            (row.get("ticker") or "").strip().upper()
            for row in source_rows
            if (row.get("ticker") or "").strip()
        }
    )
    quote_data = get_quote_data(tickers, user_agent, quote_cache)

    for row in source_rows:
        ticker = (row.get("ticker") or "").strip().upper()
        form = (row.get("form") or "").strip()
        link = (row.get("link") or "").strip()
        if not ticker or not link:
            continue
        recency_raw = (row.get("recency_min") or "").strip()
        recency = int(recency_raw) if recency_raw.isdigit() else 999999

        filing_text = ""
        try:
            filing_text = fetch_text(link, form, user_agent, cache)
        except Exception:
            filing_text = ""
        seed_text = filing_text

        gap_s, gap_tags = score_by_keywords(seed_text, POS_GAPPER, NEG_GAPPER)
        val_s, val_tags = score_by_keywords(seed_text, POS_VALUE, NEG_VALUE)
        moat_s, moat_tags = score_by_keywords(seed_text, POS_MOAT, NEG_MOAT)
        gap_b, val_b, moat_b = form_boost(form)
        recency = int(recency)
        rec_pts = recency_points(recency)
        time_pts = filing_time_boost(row.get("updated_utc", ""))
        insider_signal_score = 0
        insider_tags: list[str] = []
        if form.upper().startswith("4"):
            insider_signal_score, insider_tags = insider_signal_from_form4(seed_text)

        # Extract 8-K Item codes from filing text (e.g. "2.02;9.01").
        items_list: list[str] = []
        if form.upper().startswith("8-K"):
            items_list = extract_8k_items(seed_text)

        q = quote_data.get(ticker, {})
        price = to_float(q.get("price"))
        avg_vol = to_float(q.get("avg_vol_3m"))
        mcap = to_float(q.get("market_cap"))

        market_flags_list: list[str] = []
        if mcap <= 0 and price > 0:
            cik = extract_cik_from_link(link)
            shares_out = get_shares_outstanding(cik, user_agent, shares_cache)
            if shares_out > 0:
                mcap = shares_out * price
                market_flags_list.append("est_mcap_from_sec_shares")

        invest_pts, market_flags = investable_quality_points(price, avg_vol, mcap)
        if market_flags:
            market_flags_list.extend([x for x in market_flags.split(";") if x])

        risks = [kw for kw in RISK_FLAGS if has_phrase(seed_text, kw)]

        # Apply macro gravity (FRED-based sector rotation weight)
        _ticker_sectors = _sector_lookup.get(ticker, [])
        _macro_mult = 1.0
        for _sec in _ticker_sectors:
            _m = _macro_multipliers.get(_sec, 1.0)
            if abs(_m - 1.0) > abs(_macro_mult - 1.0):
                _macro_mult = _m  # use strongest signal sector
        _nobel_boost = _nobel_boosts.get(ticker, 1.0)
        _raw_gap = gap_b + gap_s + rec_pts + time_pts
        _gap_final = round(_raw_gap * _macro_mult * _nobel_boost)

        out = {
            "ticker": ticker,
            "form": form,
            "updated_utc": row.get("updated_utc", ""),
            "recency_min": str(recency),
            "gapper_score": str(_gap_final),
            "value_score": str(val_b + val_s + rec_pts + invest_pts + insider_signal_score),
            "moat_score": str(moat_b + moat_s + rec_pts + invest_pts + max(0, insider_signal_score // 2)),
            "insider_signal_score": str(insider_signal_score),
            "risk_flags": ";".join(sorted(set(risks))),
            "market_flags": ";".join(sorted(set(market_flags_list))),
            "tags": ";".join(sorted(set(gap_tags + val_tags + moat_tags + insider_tags))[:25]),
            "items": ";".join(items_list),
            "price": f"{price:.4f}" if price else "",
            "avg_vol_3m": str(int(avg_vol)) if avg_vol else "",
            "market_cap": str(int(mcap)) if mcap else "",
            "link": link,
        }
        prev = by_ticker.get(ticker)
        if prev is None:
            by_ticker[ticker] = out
        else:
            prev_best = max(int(prev["gapper_score"]), int(prev["value_score"]), int(prev["moat_score"]))
            out_best = max(int(out["gapper_score"]), int(out["value_score"]), int(out["moat_score"]))
            if out_best > prev_best or (out_best == prev_best and recency < int(prev["recency_min"])):
                by_ticker[ticker] = out

    rows = list(by_ticker.values())
    write_ranked(OUT_GAPPERS_CSV, OUT_GAPPERS_TXT, rows, "gapper_score")
    write_ranked(OUT_VALUE_CSV, OUT_VALUE_TXT, rows, "value_score")
    write_ranked(OUT_MOAT_CSV, OUT_MOAT_TXT, rows, "moat_score")

    moat_core = [r for r in rows if is_moat_core(r)]
    moat_emerging = [r for r in rows if not is_moat_core(r)]
    write_ranked(OUT_MOAT_CORE_CSV, OUT_MOAT_CORE_TXT, moat_core, "moat_score")
    write_ranked(OUT_MOAT_EMERG_CSV, OUT_MOAT_EMERG_TXT, moat_emerging, "moat_score")

    clean_gappers = select_clean_gappers(rows)
    clean_value = select_clean_value(rows)
    clean_moat_core = select_clean_moat_core(rows)
    write_ranked(OUT_CLEAN_GAPPERS_CSV, OUT_CLEAN_GAPPERS_TXT, clean_gappers, "gapper_score")
    write_ranked(OUT_CLEAN_VALUE_CSV, OUT_CLEAN_VALUE_TXT, clean_value, "value_score")
    write_ranked(OUT_CLEAN_MOAT_CORE_CSV, OUT_CLEAN_MOAT_CORE_TXT, clean_moat_core, "moat_score")

    save_cache(cache)
    save_quote_cache(quote_cache)
    save_shares_cache(shares_cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
