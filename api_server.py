#!/usr/bin/env python3
"""api_server.py — Cerebro Phase 2: FastAPI Central Nervous System.

Serves the Physics Engine state to the WebGL HUD via REST + WebSocket.
Redis Pub/Sub channel "cerebro:updates" carries live Spark/Macro deltas.

Endpoints:
    GET  /api/health          — liveness probe
    GET  /api/universe        — full entity_master (paginated)
    GET  /api/ticker/{symbol} — single node: gravity + velocity + brightness
    GET  /api/sectors         — sector brightness aggregates
    GET  /api/macro           — macro pressure snapshot (FRED/yields/sovereign)
    GET  /api/options         — options flow (top sweeps + gamma magnets)
    GET  /api/spark           — top velocity deck events
    GET  /api/brightness/top  — top N brightest nodes (live scoring)
    WS   /ws/live             — real-time push: Redis cerebro:updates → HUD

Run:
    uvicorn api_server:app --host 0.0.0.0 --port 8000

Production (via systemd):
    systemctl start cerebro
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import re
from importlib.util import find_spec
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote as urlquote
from urllib.request import Request as UrllibRequest, urlopen

import aiofiles
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import redis.asyncio as aioredis
from velocity_deck_schema import (
    VELOCITY_DECK_SCHEMA_VERSION,
    build_velocity_event,
    canonical_spark_snapshot,
    spark_total,
)
from market_data_contract import (
    openbb_pilot_settings as _openbb_pilot_settings,
    provider_contract as _provider_contract,
    provider_summary as _provider_summary,
)
from openbb_bridge import fetch_openbb_pilot_snapshot as _fetch_openbb_pilot_snapshot
from everos_memory_client import (
    EverOSRequestError as _EverOSRequestError,
    backend_available as _everos_backend_available,
    load_config as _load_everos_config,
    search_memories as _everos_search_memories,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
def _resolve_root() -> Path:
    candidates: list[Path] = []
    if os.getenv("CEREBRO_ROOT"):
        candidates.append(Path(os.environ["CEREBRO_ROOT"]).expanduser())
    candidates.extend(
        [
            Path.cwd(),
            Path(__file__).resolve().parent,
            Path("/home/operator/.openclaw/workspace"),
            Path("/opt/catalyst"),
        ]
    )
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "api_server.py").exists() and (resolved / "docs").exists():
            return resolved
    return Path(__file__).resolve().parent


ROOT = _resolve_root()


def _load_lookup_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

_PATHS = {
    "entity_master":   ROOT / "entity_master.json",
    "macro_layer":     ROOT / "macro_layer.json",
    "macro_pressure":  ROOT / "macro_pressure.json",
    "spark_velocities":ROOT / "spark_velocities.json",
    "options_activity":ROOT / "options_activity.json",
    "collision_alerts":ROOT / "collision_alerts.json",
    "gap_scanner":     ROOT / "gap_scanner.json",
    "sympathy_matrix": ROOT / "sympathy_matrix.json",
}

_SCANNER_OVERLAY_FILES = {
    "gappers":   ROOT / "sec_top_gappers.csv",
    "ranked":    ROOT / "sec_catalyst_ranked.csv",
    "squeezes":  ROOT / "squeeze_candidates.csv",
    "insiders":  ROOT / "insider_clusters.csv",
    "darkpool":  ROOT / "dark_pool.csv",
}

_INDUSTRY_HIERARCHY_LOOKUP = _load_lookup_json(ROOT / "industry_hierarchy_lookup.json")
_SECTOR_LOOKUP = _load_lookup_json(ROOT / "sector_lookup.json")
_SECTOR_ETF_TO_SECTOR = {
    "XLK": "tech",
    "SMH": "semis",
    "XLF": "financials",
    "XLV": "biotech",
    "XLE": "energy",
    "XLB": "materials",
    "XLI": "industrials",
    "XLU": "utilities",
    "XLRE": "real_estate",
    "XLY": "consumer",
    "XLP": "staples",
    "XLC": "comms",
}
_SECTOR_LABELS = {
    "real_estate": "Real Estate",
    "tech": "Technology",
    "utilities": "Utilities",
    "biotech": "Biotech",
    "semis": "Semiconductors",
    "comms": "Communications",
    "consumer": "Consumer",
    "industrials": "Industrials",
    "materials": "Materials",
    "energy": "Energy",
    "staples": "Consumer Staples",
    "financials": "Financials",
}

REDIS_URL   = "redis://localhost:6379"
REDIS_CHAN   = "cerebro:updates"
CONTRACT_VERSION = "2026-04-07-s01"
_EVEROS_CFG = _load_everos_config()
_SYMPATHY_PATH = ROOT / "sympathy_events.csv"
_OPTIONS_MAX_AGE = timedelta(hours=36)
_DECK_FRESHNESS_ORDER = {"live": 2, "cooling": 1, "stale": 0}
_COMMON_STOCK_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
_SCANNER_QUOTE_CACHE_TTL = max(4.0, float(os.getenv("SCANNER_QUOTE_CACHE_TTL_SEC", "8") or 8.0))
_SCANNER_QUOTE_TIMEOUT = max(1.5, float(os.getenv("SCANNER_QUOTE_TIMEOUT_SEC", "4.5") or 4.5))
_SCANNER_QUOTE_LIMIT = max(1, min(64, int(os.getenv("SCANNER_QUOTE_LIMIT", "64") or 64)))
_FINNHUB_TOKEN = str(os.getenv("FINNHUB_API_KEY", "") or "").strip()
_SCANNER_QUOTE_CACHE: dict[str, dict] = {}
_YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}
_QUOTE_SYMBOL_ALIASES = {
    "VIX": "^VIX",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "ADA": "ADA-USD",
    "AVAX": "AVAX-USD",
}
_STRONG_QUOTE_ALIASES = {
    symbol
    for symbol, alias in _QUOTE_SYMBOL_ALIASES.items()
    if alias.startswith("^") or alias.endswith("-USD")
}
_QUOTE_REQUEST_SYMBOL_RE = re.compile(r"^[A-Z0-9^./-]{1,24}$")
_QUOTE_COMPLEX_SYMBOL_RE = re.compile(
    r"(?:[./-](?:PR?[A-Z]{0,2}|P[A-Z]{0,2}|WS[A-Z]?|WT|W|UN|U|RT|R))$|^[A-Z]{2,6}(?:RP|P)[A-Z]{0,2}$",
    re.I,
)
_QUOTE_DELIMITED_SUFFIX_RE = re.compile(
    r"^(?P<base>[A-Z0-9^]{1,16})[./-](?P<suffix>[A-Z0-9]{1,6})$",
    re.I,
)
_QUOTE_COMPACT_EXPLICIT_SUFFIX_RE = re.compile(
    r"^(?P<base>[A-Z0-9^]{1,16}?)(?:(?:PR(?P<preferred_series>[A-Z0-9]{1,2}))|(?:P(?P<preferred_short>[A-Z0-9]{1,2}))|(?P<warrant>WS[A-Z]?|WT|W)|(?P<unit>UN|U)|(?P<right>RT|R))$",
    re.I,
)
_QUOTE_COMPACT_CLASS_SUFFIX_RE = re.compile(r"^(?P<base>[A-Z0-9^]{2,5})(?P<suffix>[AB])$", re.I)
_QUOTE_PREFERRED_SUFFIX_RE = re.compile(r"^P(?:R(?P<series>[A-Z0-9]{0,2})|(?P<series_short>[A-Z0-9]{1,2}))$", re.I)
_QUOTE_CLASS_SUFFIX_RE = re.compile(r"^[A-Z]$", re.I)
_ETF_VEHICLE_NAME_RE = re.compile(
    r"\b(etf|exchange[- ]traded fund|fund|trust|portfolio|index|spdr|ishares|vanguard|invesco|proshares|direxion)\b",
    re.I,
)
_NAME_SECTOR_RULES: list[tuple[str, str, tuple[re.Pattern[str], ...]]] = [
    (
        "real_estate",
        "property_reit",
        (
            re.compile(r"\breit\b", re.I),
            re.compile(r"\b(realty|properties|property|mortgage|apartment|residential|self-storage|land trust)\b", re.I),
        ),
    ),
    (
        "financials",
        "financial_services",
        (
            re.compile(r"\b(bank|banc|bancorp|bancshares|financial|finance|insurance|reinsurance|asset management|securities|brokerage|capital markets|specialty finance|credit|lending)\b", re.I),
            re.compile(r"\b(acquisition corp\.?|spac|capital corp\.?|investment trust|shell compan(?:y|ies)|blank check)\b", re.I),
        ),
    ),
    (
        "financials",
        "financial_vehicles",
        (
            re.compile(r"\b((closed[- ]end|income|bond|credit|municipal|tax[- ]free|floating rate|dividend|opportunistic)\s+(fund|trust)|business development company)\b", re.I),
        ),
    ),
    (
        "biotech",
        "health_sciences",
        (
            re.compile(r"\blabs?\b", re.I),
            re.compile(r"\b(pharma|pharmaceutical|therapeutic|therapeutics|therapies|biotech|biopharma|biosciences|biomedical|biomed|genomic|genomics|oncology|medical|health|life sciences?|diagnostic|laborator|clinic|surgical)\b", re.I),
        ),
    ),
    (
        "semis",
        "semiconductor",
        (
            re.compile(r"\b(semiconductor|semiconductors|chip|microelectronics)\b", re.I),
        ),
    ),
    (
        "tech",
        "software_systems",
        (
            re.compile(r"\b(software|systems|technology|technologies|tech|data|digital|cloud|cyber|cybersecurity|networks?|internet|ai|artificial intelligence|information|platforms?|identity|access|security)\b", re.I),
        ),
    ),
    (
        "energy",
        "energy_resources",
        (
            re.compile(r"\b(energy|petroleum|oil|gas|lng|uranium|drilling|exploration|pipeline|midstream|solar|wind|renewable)\b", re.I),
        ),
    ),
    (
        "materials",
        "materials_metals",
        (
            re.compile(r"\b(mining|minerals|metals|steel|copper|lithium|gold|silver|chemical|chemicals|fertilizer|forest products)\b", re.I),
        ),
    ),
    (
        "utilities",
        "power_water",
        (
            re.compile(r"\b(utility|utilities|electric|power|water|wastewater|gas distribution)\b", re.I),
        ),
    ),
    (
        "industrials",
        "industrial_logistics",
        (
            re.compile(r"\b(aerospace|aviation|defense|industrial|logistics|transport|shipping|freight|railroad|railway|railways|airlines?|machinery|automation|robotics|engineering|manufactur|equipment|marine|vessel|tankers?|cargo)\b", re.I),
        ),
    ),
    (
        "staples",
        "consumer_staples",
        (
            re.compile(r"\b(food|foods|beverage|beverages|household|grocery|tobacco|packaged goods)\b", re.I),
        ),
    ),
    (
        "consumer",
        "consumer_discretionary",
        (
            re.compile(r"\b(retail|restaurant|restaurants|apparel|footwear|gaming|entertainment|travel|hotel|leisure|automotive|beauty|wax|salon|casino)\b", re.I),
        ),
    ),
    (
        "comms",
        "media_telecom",
        (
            re.compile(r"\b(media|telecom|wireless|communications|broadcast|streaming|advertising)\b", re.I),
        ),
    ),
]
_MODEL_RUNTIME_LAST_ERROR: dict[str, str] = {"groq": "", "gemini": "", "anthropic": "", "openai": "", "ollama": ""}
_MODEL_RUNTIME_LAST_SWITCH: dict[str, str] = {"fast": "", "smart": ""}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Cerebro Core Intelligence API",
    description="Physics Engine live feed — Gravity × Velocity × Atmospheric Pressure",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://catalystedgescanner.com",
        "https://www.catalystedgescanner.com",
        "https://catalystedge.agency",
        "https://www.catalystedge.agency",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://67.205.148.181",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Key Auth Middleware ───────────────────────────────────────────────────
try:
    from api_auth import is_public_path, is_free_path, validate_key, check_rate_limit
    _AUTH_AVAILABLE = True
except ImportError:
    _AUTH_AVAILABLE = False

@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Gate paid endpoints behind API key auth."""
    if not _AUTH_AVAILABLE:
        return await call_next(request)

    path = request.url.path
    if is_public_path(path):
        return await call_next(request)

    # HUD and scanner serve HTML — don't gate those
    if not path.startswith("/api/"):
        return await call_next(request)

    api_key = request.headers.get("x-api-key", "").strip()

    # No key → allow but with anon rate limit (acts like free tier)
    if not api_key:
        return await call_next(request)

    key_info = validate_key(api_key)
    if not key_info:
        return JSONResponse(status_code=401, content={"error": "Invalid API key"})

    tier = key_info.get("tier", "free")
    if tier == "free" and not is_free_path(path):
        return JSONResponse(
            status_code=403,
            content={"error": "This endpoint requires a paid API key", "upgrade": "https://catalystedgescanner.com/pricing/"},
        )

    if not check_rate_limit(key_info["hash"], tier):
        return JSONResponse(status_code=429, content={"error": "Rate limit exceeded"})

    return await call_next(request)


# ── Startup: Redis pool ───────────────────────────────────────────────────────
_redis_pool: aioredis.Redis | None = None

@app.on_event("startup")
async def _startup():
    global _redis_pool
    try:
        _redis_pool = aioredis.from_url(REDIS_URL, decode_responses=True)
        await _redis_pool.ping()
        print("  Redis: connected")
    except Exception as exc:
        print(f"  Redis: unavailable ({exc}) — WebSocket push disabled")
        _redis_pool = None


@app.on_event("shutdown")
async def _shutdown():
    if not _redis_pool:
        return
    aclose = getattr(_redis_pool, "aclose", None)
    if callable(aclose):
        await aclose()
        return
    close = getattr(_redis_pool, "close", None)
    if callable(close):
        maybe_awaitable = close()
        if hasattr(maybe_awaitable, "__await__"):
            await maybe_awaitable


# ── Helpers ───────────────────────────────────────────────────────────────────
_ENTITY_JUNK_KEYS = {
    "CIK", "SEC", "INC", "LLC", "ETF", "USD", "CEO", "CFO", "COB",
    "NAN", "NA", "NONE", "NULL", "N/A", "UNKNOWN", "CORP", "LTD",
}


async def _read_json(key: str) -> dict | list:
    path = _PATHS.get(key)
    if not path or not path.exists():
        return {}
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        raw = await f.read()
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    # Regression guard (2026-04-16): entity_master ingestion has historically
    # emitted literal non-ticker strings ("CIK", "NAN", "USD", …) as keys,
    # which downstream spoke_legal and spark-event code mistakenly surface as
    # real tickers. Filter at the read boundary so every consumer sees clean
    # data even if upstream repopulates.
    if key in ("entity_master", "spark_velocities") and isinstance(data, dict):
        data = {k: v for k, v in data.items() if str(k).upper() not in _ENTITY_JUNK_KEYS}
    return data


def _parse_options_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _options_activity_is_fresh(data: dict) -> bool:
    ts = _parse_options_ts(data.get("ts"))
    if not ts:
        return False
    return (datetime.now(timezone.utc) - ts) <= _OPTIONS_MAX_AGE


def _should_surface_velocity_event(event: dict) -> bool:
    if (event.get("total_velocity") or 0.0) == 0.0:
        return False
    if event.get("is_stale"):
        return False
    active_sources = event.get("active_sources") or []
    if not active_sources:
        return False
    # Weather-only state-level shocks are still a coarse signal; only let the most
    # severe ones dominate the main deck until geospatial precision is promoted.
    if active_sources == ["weather"] and event.get("severity_rank", 0) < 3:
        return False
    return True


def _velocity_deck_sort_key(event: dict) -> tuple:
    active_sources = event.get("active_sources") or []
    primary_source = event.get("primary_source") or ""
    weather_only_penalty = 0 if active_sources == ["weather"] else 1
    return (
        -_DECK_FRESHNESS_ORDER.get(str(event.get("freshness") or ""), 0),
        -min(len(active_sources), 4),
        -weather_only_penalty,
        -int(event.get("severity_rank") or 0),
        -float(event.get("latest_event_ts") or event.get("ts") or 0.0),
        -abs(float(event.get("total_velocity") or 0.0)),
        primary_source == "weather",
        str(event.get("ticker") or ""),
    )


def _canonical_quote_symbol(symbol: str) -> str:
    normalized = (
        str(symbol or "")
        .strip()
        .upper()
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace(" ", "")
    )
    if ":" in normalized:
        prefix, _, remainder = normalized.partition(":")
        if prefix and remainder and re.fullmatch(r"[A-Z0-9_]{2,16}", prefix):
            normalized = remainder
    normalized = normalized.lstrip("$")
    normalized = re.sub(r"([./-])PR([./-])([A-Z0-9]{1,2})$", r"-PR\3", normalized)
    normalized = re.sub(r"([./-])P([./-])([A-Z0-9]{1,2})$", r"-P\3", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip()


def _provider_quote_symbol(symbol: str) -> str:
    canonical = _canonical_quote_symbol(symbol)
    return _QUOTE_SYMBOL_ALIASES.get(canonical, canonical)


def _quote_prefers_alias(symbol: str) -> bool:
    canonical = _canonical_quote_symbol(symbol)
    return canonical in _STRONG_QUOTE_ALIASES


def _quote_suffix_family(suffix: str) -> tuple[str, str]:
    normalized = str(suffix or "").strip().upper()
    if not normalized:
        return "", ""
    preferred = _QUOTE_PREFERRED_SUFFIX_RE.fullmatch(normalized)
    if preferred:
        series = preferred.group("series") or preferred.group("series_short") or ""
        return "preferred", series
    if normalized in {"WT", "WS", "W"} or re.fullmatch(r"WS[A-Z]{1,2}", normalized):
        return "warrant", normalized
    if normalized in {"RT", "R"}:
        return "right", normalized
    if normalized in {"UN", "U"}:
        return "unit", normalized
    if _QUOTE_CLASS_SUFFIX_RE.fullmatch(normalized):
        return "class_share", normalized
    return "", normalized


def _quote_delimited_symbol_detail(symbol: str) -> tuple[str, str, str] | None:
    match = _QUOTE_DELIMITED_SUFFIX_RE.fullmatch(_canonical_quote_symbol(symbol))
    if not match:
        return None
    base = match.group("base")
    suffix = match.group("suffix")
    family, normalized_suffix = _quote_suffix_family(suffix)
    if not family:
        return None
    return base, family, normalized_suffix


def _quote_compact_symbol_detail(symbol: str) -> tuple[str, str, str] | None:
    canonical = _canonical_quote_symbol(symbol)
    if not canonical or any(sep in canonical for sep in "./-"):
        return None
    match = _QUOTE_COMPACT_EXPLICIT_SUFFIX_RE.fullmatch(canonical)
    if not match:
        return None
    base = match.group("base")
    if not base:
        return None
    if match.group("preferred_series") or match.group("preferred_short"):
        series = (match.group("preferred_series") or match.group("preferred_short") or "").upper()
        return base, "preferred", series
    if match.group("warrant"):
        return base, "warrant", str(match.group("warrant") or "").upper()
    if match.group("unit"):
        return base, "unit", "UN"
    if match.group("right"):
        return base, "right", "RT"
    return None


def _quote_compact_class_detail(symbol: str) -> tuple[str, str] | None:
    canonical = _canonical_quote_symbol(symbol)
    if not canonical or any(sep in canonical for sep in "./-"):
        return None
    match = _QUOTE_COMPACT_CLASS_SUFFIX_RE.fullmatch(canonical)
    if not match:
        return None
    return match.group("base"), match.group("suffix")


def _append_quote_variant_family(
    out: list[str],
    seen: set[str],
    *,
    base: str,
    family: str,
    suffix: str,
) -> None:
    if family == "class_share":
        for separator in ("-", ".", "/"):
            _append_quote_candidate(out, seen, f"{base}{separator}{suffix}")
        _append_quote_candidate(out, seen, f"{base}{suffix}")
        return

    if family == "preferred":
        series = suffix
        for separator in ("-", ".", "/"):
            _append_quote_candidate(out, seen, f"{base}{separator}PR{series}")
            if series:
                _append_quote_candidate(out, seen, f"{base}{separator}P{series}")
            else:
                _append_quote_candidate(out, seen, f"{base}{separator}P")
        _append_quote_candidate(out, seen, f"{base}PR{series}")
        _append_quote_candidate(out, seen, f"{base}P{series}" if series else f"{base}P")
        return

    if family == "unit":
        for separator in ("-", ".", "/"):
            _append_quote_candidate(out, seen, f"{base}{separator}UN")
            _append_quote_candidate(out, seen, f"{base}{separator}U")
        _append_quote_candidate(out, seen, f"{base}UN")
        _append_quote_candidate(out, seen, f"{base}U")
        return

    if family == "warrant":
        warrant_suffixes = [suffix] if suffix.startswith("WS") and suffix != "WS" else ["WT", "WS", "W"]
        for separator in ("-", ".", "/"):
            for warrant_suffix in warrant_suffixes:
                _append_quote_candidate(out, seen, f"{base}{separator}{warrant_suffix}")
        for warrant_suffix in warrant_suffixes:
            _append_quote_candidate(out, seen, f"{base}{warrant_suffix}")
        return

    if family == "right":
        for separator in ("-", ".", "/"):
            _append_quote_candidate(out, seen, f"{base}{separator}RT")
            _append_quote_candidate(out, seen, f"{base}{separator}R")
        _append_quote_candidate(out, seen, f"{base}RT")
        _append_quote_candidate(out, seen, f"{base}R")


def _quote_identity_tokens(symbol: str) -> set[str]:
    canonical = _canonical_quote_symbol(symbol)
    if not canonical:
        return set()

    identities = {canonical}
    alias = _QUOTE_SYMBOL_ALIASES.get(canonical)
    if alias:
        alias_canonical = _canonical_quote_symbol(alias)
        if alias_canonical:
            identities.add(alias_canonical)
            identities.add(alias_canonical.replace("-", ""))
    detail = _quote_delimited_symbol_detail(canonical) or _quote_compact_symbol_detail(canonical)
    compact_class_detail = _quote_compact_class_detail(canonical)
    if compact_class_detail:
        base, suffix = compact_class_detail
        identities.add(f"{base}{suffix}")
        for separator in ("-", ".", "/"):
            identities.add(f"{base}{separator}{suffix}")
    if not detail:
        return identities

    base, family, suffix = detail
    if family == "class_share":
        identities.add(f"{base}{suffix}")
        return identities

    if family == "preferred":
        identities.add(f"{base}PR{suffix}")
        identities.add(f"{base}P{suffix}" if suffix else f"{base}P")
        return identities

    if family == "unit":
        identities.add(f"{base}UN")
        identities.add(f"{base}U")
        return identities

    if family == "warrant":
        if suffix.startswith("WS") and suffix != "WS":
            identities.add(f"{base}{suffix}")
        else:
            identities.update({f"{base}WT", f"{base}WS", f"{base}W"})
        return identities

    if family == "right":
        identities.add(f"{base}RT")
        identities.add(f"{base}R")
        return identities

    return identities


def _quote_symbols_equivalent(left_symbol: str, right_symbol: str) -> bool:
    left = _quote_identity_tokens(left_symbol)
    right = _quote_identity_tokens(right_symbol)
    return bool(left and right and left.intersection(right))


def _quote_response_matches_request(requested_symbol: str, returned_symbol: str | None) -> bool:
    normalized_returned = _canonical_quote_symbol(returned_symbol or "")
    if not normalized_returned:
        return True
    if _quote_symbols_equivalent(requested_symbol, normalized_returned):
        return True
    accepted = set(_quote_symbol_candidates(requested_symbol, provider="lookup"))
    accepted.add(_canonical_quote_symbol(requested_symbol))
    return normalized_returned in accepted


def _quote_search_candidate_allowed(requested_symbol: str, candidate_symbol: str) -> bool:
    requested = _canonical_quote_symbol(requested_symbol)
    candidate = _canonical_quote_symbol(candidate_symbol)
    if not requested or not candidate:
        return False
    if candidate == requested:
        return True
    if _quote_symbols_equivalent(requested, candidate):
        return True
    accepted = set(_quote_symbol_candidates(requested, provider="lookup"))
    accepted.add(requested)
    if candidate in accepted:
        return True
    if candidate.startswith(requested):
        suffix = candidate[len(requested):]
        if suffix in {"W", "WS", "WT", "UN", "U", "RT", "R"}:
            return True
    return False


def _append_quote_candidate(out: list[str], seen: set[str], candidate: str) -> None:
    normalized = _canonical_quote_symbol(candidate)
    if not normalized or normalized in seen:
        return
    if not _QUOTE_REQUEST_SYMBOL_RE.fullmatch(normalized):
        return
    seen.add(normalized)
    out.append(normalized)


def _finnhub_supported_quote_symbol(symbol: str) -> bool:
    if not symbol or symbol.startswith("^") or symbol.endswith("-USD"):
        return False
    canonical = _canonical_quote_symbol(symbol)
    if _quote_prefers_alias(canonical):
        return False
    if "/" in symbol:
        return False
    return not bool(_QUOTE_COMPLEX_SYMBOL_RE.search(symbol))


def _quote_symbol_candidates(symbol: str, provider: str = "") -> list[str]:
    canonical = _canonical_quote_symbol(symbol)
    if not canonical:
        return []

    provider = str(provider or "").strip().lower()
    out: list[str] = []
    seen: set[str] = set()
    detail = _quote_delimited_symbol_detail(canonical) or _quote_compact_symbol_detail(canonical)
    compact_class_detail = _quote_compact_class_detail(canonical) if provider in {"yahoo", "finnhub"} else None

    alias = _QUOTE_SYMBOL_ALIASES.get(canonical)
    if alias and _quote_prefers_alias(canonical):
        _append_quote_candidate(out, seen, alias)
    _append_quote_candidate(out, seen, canonical)
    if alias and not _quote_prefers_alias(canonical):
        _append_quote_candidate(out, seen, alias)

    if detail:
        base, family, suffix = detail
        _append_quote_variant_family(out, seen, base=base, family=family, suffix=suffix)
    else:
        if "." in canonical:
            _append_quote_candidate(out, seen, canonical.replace(".", "-"))
            _append_quote_candidate(out, seen, canonical.replace(".", ""))
        if "/" in canonical:
            _append_quote_candidate(out, seen, canonical.replace("/", "-"))
            _append_quote_candidate(out, seen, canonical.replace("/", "."))
            _append_quote_candidate(out, seen, canonical.replace("/", ""))
        if "-" in canonical:
            _append_quote_candidate(out, seen, canonical.replace("-", "."))
            _append_quote_candidate(out, seen, canonical.replace("-", "/"))
            _append_quote_candidate(out, seen, canonical.replace("-", ""))
        if compact_class_detail:
            base, suffix = compact_class_detail
            for separator in ("-", ".", "/"):
                _append_quote_candidate(out, seen, f"{base}{separator}{suffix}")

    if provider == "finnhub":
        if detail and detail[1] in {"preferred", "warrant", "unit", "right"}:
            return []
        return [candidate for candidate in out if _finnhub_supported_quote_symbol(candidate)]
    return out


def _http_json(url: str, *, timeout: float = _SCANNER_QUOTE_TIMEOUT) -> dict:
    req = UrllibRequest(url, headers=_YAHOO_HEADERS)
    with urlopen(req, timeout=timeout) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


def _quote_cache_get(symbol: str) -> dict | None:
    cached = _SCANNER_QUOTE_CACHE.get(symbol)
    if not cached:
        return None
    if (time.time() - float(cached.get("_cached_at") or 0.0)) > _SCANNER_QUOTE_CACHE_TTL:
        _SCANNER_QUOTE_CACHE.pop(symbol, None)
        return None
    return {key: value for key, value in cached.items() if key != "_cached_at"}


def _quote_cache_put(symbol: str, payload: dict) -> dict:
    stamped = dict(payload)
    stamped["_cached_at"] = time.time()
    _SCANNER_QUOTE_CACHE[symbol] = stamped
    return {key: value for key, value in stamped.items() if key != "_cached_at"}


def _finnhub_quote(symbol: str) -> dict | None:
    if not _FINNHUB_TOKEN:
        return None
    for provider_symbol in _quote_symbol_candidates(symbol, provider="finnhub"):
        try:
            payload = _http_json(
                f"https://finnhub.io/api/v1/quote?symbol={urlquote(provider_symbol)}&token={urlquote(_FINNHUB_TOKEN)}"
            )
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
            continue
        price = float(payload.get("c") or 0.0)
        prev = float(payload.get("pc") or 0.0)
        if price <= 0:
            continue
        pct = ((price - prev) / prev * 100.0) if prev > 0 else None
        return {
            "ticker": _canonical_quote_symbol(symbol),
            "provider_symbol": provider_symbol,
            "price": round(price, 6),
            "prev_close": round(prev, 6) if prev > 0 else None,
            "pct_change": round(pct, 4) if pct is not None else None,
            "market_state": "",
            "source": "finnhub",
            "ts": time.time(),
        }
    return None


def _yahoo_search_quote_candidates(symbol: str) -> list[str]:
    url = (
        "https://query1.finance.yahoo.com/v1/finance/search"
        f"?q={urlquote(symbol)}&quotesCount=8&newsCount=0"
    )
    try:
        payload = _http_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for row in (payload or {}).get("quotes") or []:
        candidate = _canonical_quote_symbol(row.get("symbol") or "")
        if not candidate:
            continue
        if not _quote_search_candidate_allowed(symbol, candidate):
            continue
        _append_quote_candidate(out, seen, candidate)
    return out


def _yahoo_chart_quote_for_symbol(symbol: str, provider_symbol: str) -> dict | None:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urlquote(provider_symbol)}?interval=1m&range=1d&includePrePost=true"
    )
    try:
        payload = _http_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    result = (((payload or {}).get("chart") or {}).get("result") or [None])[0]
    if not result:
        return None
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice") or meta.get("postMarketPrice") or meta.get("preMarketPrice") or meta.get("price")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    try:
        price_f = float(price or 0.0)
    except (TypeError, ValueError):
        return None
    if price_f <= 0:
        return None
    try:
        prev_f = float(prev or 0.0)
    except (TypeError, ValueError):
        prev_f = 0.0
    returned_symbol = str(meta.get("symbol") or provider_symbol or "")
    if not _quote_response_matches_request(symbol, returned_symbol) and not _quote_search_candidate_allowed(symbol, returned_symbol):
        return None
    pct = ((price_f - prev_f) / prev_f * 100.0) if prev_f > 0 else None
    return {
        "ticker": _canonical_quote_symbol(symbol),
        "provider_symbol": _canonical_quote_symbol(returned_symbol),
        "price": round(price_f, 6),
        "prev_close": round(prev_f, 6) if prev_f > 0 else None,
        "pct_change": round(pct, 4) if pct is not None else None,
        "market_state": str(meta.get("marketState") or ""),
        "source": "yahoo_chart",
        "ts": time.time(),
    }


def _yahoo_chart_quote(symbol: str) -> dict | None:
    tried: set[str] = set()
    for provider_symbol in _quote_symbol_candidates(symbol, provider="yahoo"):
        tried.add(provider_symbol)
        quote = _yahoo_chart_quote_for_symbol(symbol, provider_symbol)
        if quote:
            return quote

    for provider_symbol in _yahoo_search_quote_candidates(symbol):
        if provider_symbol in tried:
            continue
        quote = _yahoo_chart_quote_for_symbol(symbol, provider_symbol)
        if quote:
            quote["source"] = "yahoo_search_chart"
            return quote
    return None


def _fetch_scanner_quote(symbol: str) -> dict:
    canonical = _canonical_quote_symbol(symbol)
    cached = _quote_cache_get(canonical)
    if cached:
        cached.setdefault("requested_symbol", canonical)
        return cached

    quote = _finnhub_quote(canonical) or _yahoo_chart_quote(canonical)
    if quote:
        quote.setdefault("requested_symbol", canonical)
        return _quote_cache_put(canonical, quote)
    return {
        "requested_symbol": canonical,
        "ticker": canonical,
        "provider_symbol": None,
        "price": None,
        "prev_close": None,
        "pct_change": None,
        "market_state": "",
        "source": "unavailable",
        "ts": time.time(),
    }


def _parse_scanner_quote_request(raw: str) -> list[str]:
    seen: set[str] = set()
    tickers: list[str] = []
    for chunk in re.split(r"[\s,;|]+", str(raw or "").strip()):
        symbol = _canonical_quote_symbol(chunk)
        if not symbol or symbol in seen or not _QUOTE_REQUEST_SYMBOL_RE.fullmatch(symbol):
            continue
        seen.add(symbol)
        tickers.append(symbol)
        if len(tickers) >= _SCANNER_QUOTE_LIMIT:
            break
    return tickers


def _sector_lookup_gics(ticker: str) -> tuple[dict, str]:
    ticker = str(ticker or "").upper().strip()
    if not ticker:
        return {}, ""
    gics = _INDUSTRY_HIERARCHY_LOOKUP.get(ticker)
    if isinstance(gics, dict):
        sector = str(gics.get("s") or "").strip().lower()
        if sector:
            normalized = {key: value for key, value in gics.items() if value}
            normalized["s"] = sector
            return normalized, "industry_lookup"
    sector_list = _SECTOR_LOOKUP.get(ticker) or []
    if sector_list:
        sector = str(sector_list[0] or "").strip().lower()
        if sector:
            return {"s": sector}, "sector_lookup"
    return {}, ""


def _extract_etf_symbols(raw: list | tuple | str | dict | None) -> list[str]:
    if not raw:
        return []
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    symbols: list[str] = []
    for item in items:
        if isinstance(item, str):
            symbol = item
        elif isinstance(item, dict):
            symbol = item.get("etf") or item.get("ticker") or item.get("symbol") or ""
        else:
            symbol = ""
        symbol = str(symbol or "").strip().upper()
        if symbol:
            symbols.append(symbol)
    return symbols


def _infer_sector_from_etf(rec: dict, ticker: str = "") -> tuple[dict, str, str]:
    if rec.get("etf"):
        sector = _SECTOR_ETF_TO_SECTOR.get(str(ticker or "").upper().strip())
        if sector:
            return {"s": sector}, "etf_self", str(ticker or "").upper().strip()
    for symbol in _extract_etf_symbols(rec.get("etf_overlords")) + _extract_etf_symbols(rec.get("canopy_etfs")):
        sector = _SECTOR_ETF_TO_SECTOR.get(symbol)
        if sector:
            return {"s": sector}, "inferred_etf", symbol
    return {}, "", ""


def _build_gics_runtime(sector_key: str, industry_text: str = "") -> dict:
    title = _SECTOR_LABELS.get(sector_key, sector_key.replace("_", " ").title())
    leaf = industry_text.strip() if industry_text else title
    return {"s": sector_key, "ig": title, "i": leaf, "si": leaf}


def _sector_from_name_runtime(rec: dict, ticker: str = "") -> tuple[dict, str, bool, str]:
    name = str(rec.get("name") or "").strip()
    if not name:
        return {}, "", False, ""
    if rec.get("etf") and _ETF_VEHICLE_NAME_RE.search(name):
        return _build_gics_runtime("financials", name), "etf_vehicle", True, "name:etf_vehicle"
    for sector, label, patterns in _NAME_SECTOR_RULES:
        if rec.get("etf") and label == "financial_vehicles":
            continue
        for pattern in patterns:
            if pattern.search(name):
                return _build_gics_runtime(sector, name), "name_heuristic", True, f"{label}:{pattern.pattern}"
    return {}, "", False, ""


# ── Live-fire derivative sector resolution ────────────────────────────────────
# Recognises compact derivative suffixes so warrants/units/rights (e.g. DJTW)
# inherit their parent's sector in real time — before the batch EM cron runs.

_COMPACT_WARRANT_RE = re.compile(
    r"^([A-Z0-9]{2,12}?)(WSA|WSB|WS|WT|RT|UN|U|W|R|RI)$", re.I
)
_HYPHEN_DOT_WARRANT_RE = re.compile(
    r"[-.](WSA|WSB|WS|WT|W|UN|U|RT|R|RI)$", re.I
)
_INVALID_LIVE_SECTORS = frozenset({"", "unknown", "none", "null", "other"})

# Lazy entity_master sector cache (5-min TTL) — avoids loading 15K records per request.
_EM_SECTOR_CACHE: dict[str, str] = {}
_EM_SECTOR_CACHE_TS: float = 0.0
_EM_SECTOR_CACHE_TTL = 300.0


def _em_sector_for_parent(parent: str) -> str | None:
    """Synchronous sector lookup from entity_master with 5-min cache."""
    global _EM_SECTOR_CACHE, _EM_SECTOR_CACHE_TS
    now = time.time()
    if now - _EM_SECTOR_CACHE_TS > _EM_SECTOR_CACHE_TTL:
        try:
            em_raw: dict = json.loads(
                (ROOT / "entity_master.json").read_text(encoding="utf-8")
            )
            _EM_SECTOR_CACHE = {
                t: str(
                    (rec.get("gics") or {}).get("s") or rec.get("sector") or ""
                ).strip().lower()
                for t, rec in em_raw.items()
            }
        except Exception:
            pass
        _EM_SECTOR_CACHE_TS = now
    val = _EM_SECTOR_CACHE.get(parent.upper())
    return val if val and val not in _INVALID_LIVE_SECTORS else None


def _parent_candidates(ticker: str) -> list[str]:
    """Return ordered list of candidate parent tickers for a derivative symbol."""
    t = ticker.upper().strip()
    candidates: list[str] = []
    # Dollar-sign preferred: JPM$L → JPM
    if "$" in t:
        candidates.append(t.split("$", 1)[0])
    # Compact warrant/unit/rights: DJTW → DJT, SXTPW → SXTP, BNCWW → BNCW
    m = _COMPACT_WARRANT_RE.fullmatch(t)
    if m:
        candidates.append(m.group(1))
    # Hyphenated/dot: TICK-WT → TICK, TICK.WS → TICK
    cleaned = _HYPHEN_DOT_WARRANT_RE.sub("", t).strip("-./$")
    if cleaned and cleaned != t:
        candidates.append(cleaned)
    # ADR-hedged suffix (4-char ending H): ARMH → ARM
    if len(t) == 4 and t.endswith("H"):
        candidates.append(t[:-1])
    # Dedup while preserving order, excluding self
    seen: set[str] = {t}
    return [c for c in candidates if c not in seen and (seen.add(c) or True)]  # type: ignore[func-returns-value]


def _resolve_live_derivative_sector(ticker: str) -> tuple[str, str] | None:
    """Inherit parent's sector for a derivative ticker (live, no batch required).

    Returns (sector_key, evidence_string) or None if not a derivative / parent unknown.
    Checks sector_lookup → industry_hierarchy → entity_master (5-min cache).
    Walks one grandparent level to handle double-derivative tickers like BNCWW.
    """
    t = str(ticker or "").upper().strip()
    parents = _parent_candidates(t)
    if not parents:
        return None

    def _sector_from_parent(p: str) -> str | None:
        # 1. sector_lookup.json (hot, loaded at startup)
        sl = _SECTOR_LOOKUP.get(p)
        if sl:
            v = str(sl[0] if isinstance(sl, list) else sl).strip().lower()
            if v and v not in _INVALID_LIVE_SECTORS:
                return v
        # 2. industry_hierarchy_lookup.json
        ihl = _INDUSTRY_HIERARCHY_LOOKUP.get(p)
        if isinstance(ihl, dict):
            v = str(ihl.get("s") or "").strip().lower()
            if v and v not in _INVALID_LIVE_SECTORS:
                return v
        # 3. entity_master (lazy 5-min cache)
        return _em_sector_for_parent(p)

    for parent in parents:
        sector = _sector_from_parent(parent)
        if sector:
            return sector, f"derivative_parent:{parent}"
        # One grandparent hop — handles BNCWW → BNCW (other) → BNC (staples)
        for gp in _parent_candidates(parent):
            sector = _sector_from_parent(gp)
            if sector:
                return sector, f"derivative_parent:{gp}:via:{parent}"

    return None


def _normalized_sector_detail(rec: dict, ticker: str = "") -> tuple[str, str, bool, str, dict]:
    gics = rec.get("gics") if isinstance(rec.get("gics"), dict) else {}
    sector = str((gics.get("s") if gics else "") or rec.get("sector") or "").strip().lower()
    # "other" is not a resolved sector — fall through the resolution chain to find something better.
    if sector and sector != "other":
        normalized = {key: value for key, value in gics.items() if value} if gics else {"s": sector}
        normalized["s"] = sector
        source = str(rec.get("sector_source") or ("gics" if gics.get("s") else "sector_field")).strip() or (
            "gics" if gics.get("s") else "sector_field"
        )
        inferred = bool(rec.get("sector_inferred"))
        evidence = str(rec.get("sector_evidence") or "")
        return sector, source, inferred, evidence, normalized

    lookup_gics, lookup_source = _sector_lookup_gics(ticker)
    if lookup_gics.get("s") and lookup_gics["s"].lower() != "other":
        return str(lookup_gics["s"]).strip().lower(), lookup_source, False, "", lookup_gics

    inferred_gics, inferred_source, evidence = _infer_sector_from_etf(rec, ticker)
    if inferred_gics.get("s") and inferred_gics["s"].lower() != "other":
        return str(inferred_gics["s"]).strip().lower(), inferred_source, True, evidence, inferred_gics

    name_gics, name_source, name_inferred, name_evidence = _sector_from_name_runtime(rec, ticker)
    if name_gics.get("s") and name_gics["s"].lower() != "other":
        return str(name_gics["s"]).strip().lower(), name_source, name_inferred, name_evidence, name_gics

    # Live-fire derivative resolution: warrants/units/rights inherit parent sector
    # without waiting for the batch entity_master cron (e.g. DJTW → DJT → tech).
    deriv = _resolve_live_derivative_sector(ticker)
    if deriv:
        deriv_sector, deriv_evidence = deriv
        return deriv_sector, "derivative_parent", True, deriv_evidence, {"s": deriv_sector}

    # Nothing better found — preserve stored "other" rather than degrading to "unknown"
    if sector == "other":
        normalized = {key: value for key, value in gics.items() if value} if gics else {"s": sector}
        normalized["s"] = sector
        source = str(rec.get("sector_source") or "sector_field").strip()
        inferred = bool(rec.get("sector_inferred"))
        evidence = str(rec.get("sector_evidence") or "")
        return sector, source, inferred, evidence, normalized

    return "unknown", "unknown", False, "", {}


def _normalized_sector(rec: dict, ticker: str = "") -> str:
    return _normalized_sector_detail(rec, ticker)[0]


def _normalized_gravity_detail(rec: dict, ticker: str, overlay_item: dict | None = None) -> tuple[float, str]:
    raw = rec.get("gravity", 0.0)
    try:
        gravity = float(raw or 0.0)
    except (TypeError, ValueError):
        gravity = 0.0
    if gravity > 0:
        return round(gravity, 4), "entity_master"

    best = 0.0
    source = "unscored"
    ticker = (ticker or "").upper().strip()
    sector, _, _, _, _ = _normalized_sector_detail(rec, ticker)
    etf_anchor = float(rec.get("etf_weights_sum") or 0.0)

    if overlay_item:
        overlay_gravity = _scanner_overlay_universe_row(ticker, overlay_item)["gravity"]
        if overlay_gravity > best:
            best = overlay_gravity
            source = "scanner_overlay"

    if sector != "unknown" and best < 1.15:
        best = 1.15
        source = "gics_sector"

    if etf_anchor > 0:
        canopy_gravity = round(max(1.05, min(3.25, 1.0 + etf_anchor * 24.0)), 4)
        if canopy_gravity > best:
            best = canopy_gravity
            source = "canopy_anchor"

    if rec.get("cik") and _COMMON_STOCK_TICKER_RE.fullmatch(ticker) and best < 1.0:
        best = 1.0
        source = "cik_common"

    return round(best, 4), source


def _normalized_gravity(rec: dict, ticker: str, overlay_item: dict | None = None) -> float:
    return _normalized_gravity_detail(rec, ticker, overlay_item)[0]


def _brightness(rec: dict, sparks: dict, ticker: str, overlay_item: dict | None = None) -> float:
    """Compute live brightness for a single ticker record."""
    gravity = _normalized_gravity(rec, ticker, overlay_item)
    spark_e = canonical_spark_snapshot(sparks.get(ticker.upper(), {}))
    velocity = (
        spark_e.get("patent",       0.0) +
        spark_e.get("legal",        0.0) +
        spark_e.get("digital",      0.0) +
        spark_e.get("options",      0.0) +
        spark_e.get("supply_chain", 0.0) +
        spark_e.get("weather",      0.0)
    )
    return round(gravity * (1.0 + velocity), 2)


def _normalize_etf_overlords(raw: list, weights_sum: float) -> list[dict]:
    """Convert etf_overlords to [{etf, weight}] objects.

    entity_master may store strings (["XLF"]) or dicts ([{etf, weight}]).
    Normalise to dicts so the HUD always receives a consistent shape.
    """
    if not raw:
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({"etf": item, "weight": round(weights_sum / max(len(raw), 1), 4)})
    return out


def _universe_row(rec: dict, sparks: dict, ticker: str, overlay_item: dict | None = None) -> dict:
    """Return a normalized universe row with the required API contract keys."""
    g, gravity_source = _normalized_gravity_detail(rec, ticker, overlay_item)
    sector, sector_source, sector_inferred, sector_evidence, _ = _normalized_sector_detail(rec, ticker)
    weights_sum = rec.get("etf_weights_sum", 0.0) or 0.0
    spark_entry = sparks.get(ticker.upper(), {})
    gamma_size = float(spark_entry.get("gamma_size", 0) or 0)
    return {
        "ticker":        ticker,
        "name":          rec.get("name", ""),
        "gravity":       round(g, 4),
        "brightness":    _brightness(rec, sparks, ticker, overlay_item),
        "cap_tier":      rec.get("mkt_cap_tier", "") or rec.get("cap_tier", ""),
        "sector":        sector,
        "sector_source": sector_source,
        "sector_inferred": sector_inferred,
        "sector_evidence": sector_evidence,
        "etf_weight":    round(weights_sum, 6),
        "etf_overlords": _normalize_etf_overlords(rec.get("etf_overlords", []), weights_sum),
        "is_rogue":      rec.get("is_rogue", False),
        "gravity_source": gravity_source,
        "gammaSize":     round(gamma_size, 4),
    }


def _scanner_float(raw: str | float | int | None) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _scanner_overlay_score(row: dict) -> float:
    candidates = [
        _scanner_float(row.get("gapper_score")),
        _scanner_float(row.get("priority_score")),
        _scanner_float(row.get("momentum_score")),
        _scanner_float(row.get("quality_score")),
        _scanner_float(row.get("squeeze_score")),
        _scanner_float(row.get("filing_count")),
        _scanner_float(row.get("volume_ratio")),
    ]
    return max((value for value in candidates if value is not None), default=0.0)


def _read_scanner_overlay() -> dict[str, dict]:
    overlay: dict[str, dict] = {}

    for source, path in _SCANNER_OVERLAY_FILES.items():
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                for rank, row in enumerate(csv.DictReader(handle), start=1):
                    ticker = (row.get("ticker") or "").upper().strip()
                    if not ticker:
                        continue

                    item = overlay.setdefault(
                        ticker,
                        {
                            "ticker": ticker,
                            "name": row.get("name", "") or "",
                            "sources": [],
                            "best_rank": rank,
                            "scanner_score": 0.0,
                            "form": "",
                            "tags": "",
                            "stage": "",
                            "signal_type": "",
                            "link": "",
                            "price": None,
                            "market_cap": None,
                        },
                    )

                    if source not in item["sources"]:
                        item["sources"].append(source)

                    item["best_rank"] = min(item["best_rank"], rank)
                    item["scanner_score"] = max(item["scanner_score"], _scanner_overlay_score(row))
                    item["form"] = item["form"] or (row.get("form") or "")
                    item["tags"] = item["tags"] or (row.get("tags") or row.get("score_breakdown") or "")
                    item["stage"] = item["stage"] or (row.get("stage") or "")
                    item["signal_type"] = item["signal_type"] or (row.get("signal_type") or "")
                    item["link"] = item["link"] or (row.get("link") or row.get("primary_link") or "")

                    price = _scanner_float(row.get("price"))
                    if item["price"] is None and price is not None:
                        item["price"] = price

                    market_cap = _scanner_float(row.get("market_cap"))
                    if item["market_cap"] is None and market_cap is not None:
                        item["market_cap"] = market_cap
        except Exception:
            continue

    return overlay


def _scanner_overlay_universe_row(ticker: str, item: dict) -> dict:
    score = item.get("scanner_score") or 0.0
    gravity = round(max(1.0, min(20.0, score / 2.5 if score else 3.0)), 4)
    brightness = round(max(gravity * 1.45, score or gravity), 2)
    label = item.get("tags") or item.get("stage") or item.get("signal_type") or "scanner_overlay"
    sector, sector_source, sector_inferred, sector_evidence, _ = _normalized_sector_detail({}, ticker)
    return {
        "ticker": ticker,
        "name": item.get("name") or f"{ticker} scanner overlay",
        "gravity": gravity,
        "brightness": brightness,
        "cap_tier": "",
        "sector": sector,
        "sector_source": sector_source,
        "sector_inferred": sector_inferred,
        "sector_evidence": sector_evidence,
        "etf_weight": 0.0,
        "etf_overlords": [],
        "is_rogue": False,
        "gravity_source": "scanner_overlay",
        "scanner_only": True,
        "scanner_sources": item.get("sources", []),
        "scanner_rank": item.get("best_rank"),
        "scanner_score": round(score, 4),
        "scanner_form": item.get("form", ""),
        "scanner_tags": item.get("tags") or label,
        "scanner_link": item.get("link", ""),
    }


def _merge_scanner_overlay(row: dict, item: dict | None) -> dict:
    merged = dict(row)
    if not item:
        merged.setdefault("scanner_only", False)
        merged.setdefault("scanner_sources", [])
        merged.setdefault("scanner_rank", None)
        merged.setdefault("scanner_score", None)
        merged.setdefault("scanner_form", "")
        merged.setdefault("scanner_tags", "")
        merged.setdefault("scanner_link", "")
        return merged

    merged.update(
        {
            "scanner_only": False,
            "scanner_sources": item.get("sources", []),
            "scanner_rank": item.get("best_rank"),
            "scanner_score": round(item.get("scanner_score") or 0.0, 4),
            "scanner_form": item.get("form", ""),
            "scanner_tags": item.get("tags") or item.get("stage") or item.get("signal_type") or "",
            "scanner_link": item.get("link", ""),
        }
    )
    return merged


def _sympathy_rows() -> list[dict[str, str]]:
    if not _SYMPATHY_PATH.exists():
        return []
    try:
        with _SYMPATHY_PATH.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def _sympathy_float(raw: str | float | int | None) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _sympathy_history_for_ticker(ticker: str, limit: int = 5) -> list[dict]:
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return []

    rows: list[dict] = []
    for row in _sympathy_rows():
        trigger = (row.get("trigger_ticker") or "").upper().strip()
        peers = [peer.strip().upper() for peer in (row.get("peers") or "").split(",") if peer.strip()]
        relation = ""
        if trigger == ticker:
            relation = "trigger"
        elif ticker in peers:
            relation = "peer"
        if not relation:
            continue
        rows.append(
            {
                "date": row.get("date", ""),
                "trigger_ticker": trigger,
                "relation": relation,
                "sector": row.get("sector", ""),
                "gap_score": _sympathy_float(row.get("gap_score")),
                "form": row.get("form", ""),
                "price_t0": _sympathy_float(row.get("price_t0")),
                "price_t1day": _sympathy_float(row.get("price_t1day")),
                "move_pct_t1day": _sympathy_float(row.get("move_pct_t1day")),
                "peer_avg_move_pct_t1day": _sympathy_float(row.get("peer_avg_move_pct_t1day")),
                "peers": peers[:5],
                "resolved": _sympathy_float(row.get("price_t1day")) is not None,
            }
        )

    rows.sort(
        key=lambda item: (
            item.get("date", ""),
            abs(item.get("move_pct_t1day") or 0.0),
            item.get("gap_score") or 0.0,
        ),
        reverse=True,
    )
    return rows[:limit]


def _recent_sympathy_highlights(limit: int = 3) -> list[dict]:
    rows: list[dict] = []
    for row in _sympathy_rows():
        move = _sympathy_float(row.get("move_pct_t1day"))
        trigger = (row.get("trigger_ticker") or "").upper().strip()
        if not trigger or move is None:
            continue
        rows.append(
            {
                "date": row.get("date", ""),
                "trigger_ticker": trigger,
                "sector": row.get("sector", ""),
                "form": row.get("form", ""),
                "gap_score": _sympathy_float(row.get("gap_score")),
                "move_pct_t1day": move,
                "peer_avg_move_pct_t1day": _sympathy_float(row.get("peer_avg_move_pct_t1day")),
            }
        )

    rows.sort(
        key=lambda item: (
            item.get("date", ""),
            abs(item.get("move_pct_t1day") or 0.0),
            item.get("gap_score") or 0.0,
        ),
        reverse=True,
    )
    return rows[:limit]


def _extract_memory_content(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("content", "text", "memory", "page_content", "note"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("message", "raw"):
        nested = _extract_memory_content(item.get(key))
        if nested:
            return nested
    return ""


def _extract_memory_snippets(payload: dict | None, limit: int = 3) -> list[str]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result", {})
    if not isinstance(result, dict):
        return []

    snippets: list[str] = []
    for key in ("profiles", "memories", "pending_messages"):
        for item in result.get(key, []) or []:
            content = _extract_memory_content(item)
            if not content or content in snippets:
                continue
            snippets.append(content)
            if len(snippets) >= limit:
                return snippets[:limit]
    return snippets[:limit]


def _everos_context_sync(query: str, limit: int = 3) -> list[str]:
    if not _EVEROS_CFG.enabled:
        return []
    try:
        payload = _everos_search_memories(query, cfg=_EVEROS_CFG, top_k=limit)
    except _EverOSRequestError:
        return []
    return _extract_memory_snippets(payload, limit=limit)


async def _everos_context(query: str, limit: int = 3) -> list[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _everos_context_sync, query, limit)


def _format_sympathy_prompt(rows: list[dict]) -> str:
    lines: list[str] = []
    for row in rows:
        relation = "leader" if row.get("relation") == "trigger" else f"peer off {row.get('trigger_ticker') or 'another leader'}"
        segment = f"{row.get('date') or 'undated'}: {relation} in {row.get('sector') or 'unknown'}"
        move = row.get("move_pct_t1day")
        if move is not None:
            segment += f", T+1 {move:+.2f}%"
        elif row.get("gap_score") is not None:
            segment += f", gap score {row['gap_score']:.1f}"
        lines.append(segment)
    return "\n".join(lines)


def _format_memory_prompt(snippets: list[str]) -> str:
    rendered = []
    for snippet in snippets:
        first_line = snippet.splitlines()[0].strip()
        if first_line:
            rendered.append(f"- {first_line[:220]}")
    return "\n".join(rendered)


def _summarize_sympathy_history(ticker: str, rows: list[dict]) -> str:
    if not rows:
        return ""
    latest = rows[0]
    date = latest.get("date") or "a recent session"
    sector = latest.get("sector") or "unknown"
    move = latest.get("move_pct_t1day")
    if latest.get("relation") == "trigger":
        sentence = f"Recent sympathy history shows {ticker} last acted as a sector leader on {date} in {sector}"
    else:
        leader = latest.get("trigger_ticker") or "another catalyst leader"
        sentence = f"Recent sympathy history shows {ticker} last moved as a sympathy peer off {leader} on {date} in {sector}"
    if move is not None:
        sentence += f", with a recorded T+1 move of {move:+.2f}%."
    else:
        sentence += "."
    return sentence


def _summarize_briefing_sympathy(highlights: list[dict]) -> str:
    if not highlights:
        return ""
    lead = highlights[0]
    sector = lead.get("sector") or "the active cohort"
    move = lead.get("move_pct_t1day")
    if move is None:
        return f"Recent sympathy follow-through is clustering around {lead['trigger_ticker']} in {sector}."
    direction = "up" if move >= 0 else "down"
    return (
        f"Recent sympathy follow-through is strongest around {lead['trigger_ticker']} in {sector}, "
        f"where the last measured next-day move was {direction} {abs(move):.1f} percent."
    )


# ── REST: Health ──────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    redis_ok = False
    if _redis_pool:
        try:
            await _redis_pool.ping()
            redis_ok = True
        except Exception:
            pass
    em_path = _PATHS["entity_master"]
    openbb_settings = _openbb_pilot_settings()
    everos_backend_ok = _everos_backend_available(_EVEROS_CFG) if _EVEROS_CFG.enabled else False
    fast_model_spec = _resolve_model_spec("fast")
    smart_model_spec = _resolve_model_spec("smart")
    return {
        "status":     "ok",
        "contract_version": CONTRACT_VERSION,
        "redis":      redis_ok,
        "entity_master_exists": em_path.exists(),
        "entity_master_size":   em_path.stat().st_size if em_path.exists() else 0,
        "provider_summary": _provider_summary(),
        "openbb": {
            **openbb_settings,
            "package_available": bool(find_spec("openbb")),
        },
        "everos": {
            "enabled": _EVEROS_CFG.enabled,
            "configured": bool(_EVEROS_CFG.server_url and _EVEROS_CFG.user_id and _EVEROS_CFG.group_id),
            "backend_available": everos_backend_ok,
            "retrieve_method": _EVEROS_CFG.retrieve_method,
            "top_k": _EVEROS_CFG.top_k,
        },
        "groq": {
            "enabled": _GROQ_ENABLED,
            "configured": _provider_available("groq"),
            "base_url": _GROQ_BASE_URL,
            "fast_model": _GROQ_MODEL_FAST,
            "smart_model": _GROQ_MODEL_SMART,
            "last_error": _MODEL_RUNTIME_LAST_ERROR.get("groq", ""),
        },
        "gemini": {
            "enabled": _GEMINI_ENABLED,
            "configured": _provider_available("gemini"),
            "base_url": _GEMINI_BASE_URL,
            "fast_model": _GEMINI_MODEL_FAST,
            "smart_model": _GEMINI_MODEL_SMART,
            "last_error": _MODEL_RUNTIME_LAST_ERROR.get("gemini", ""),
        },
        "anthropic": {
            "package_available": _ANTHROPIC_AVAILABLE,
            "configured": bool(_ANTHROPIC_API_KEY),
            "fast_model": _ANTHROPIC_MODEL_FAST,
            "smart_model": _ANTHROPIC_MODEL_SMART,
            "models_distinct": _ANTHROPIC_MODEL_SMART != _ANTHROPIC_MODEL_FAST,
        },
        "openai": {
            "configured": bool(_OPENAI_API_KEY),
            "fast_model": _OPENAI_MODEL_FAST,
            "smart_model": _OPENAI_MODEL_SMART,
            "models_distinct": _OPENAI_MODEL_SMART != _OPENAI_MODEL_FAST,
            "last_error": _MODEL_RUNTIME_LAST_ERROR.get("openai", ""),
        },
        "ollama": {
            "enabled": _OLLAMA_ENABLED,
            "configured": _provider_available("ollama"),
            "base_url": _OLLAMA_BASE_URL,
            "fast_model": _OLLAMA_MODEL_FAST,
            "smart_model": _OLLAMA_MODEL_SMART,
            "models_distinct": _OLLAMA_MODEL_SMART != _OLLAMA_MODEL_FAST,
            "last_error": _MODEL_RUNTIME_LAST_ERROR.get("ollama", ""),
        },
        "model_runtime": {
            "provider_priority": _provider_iteration_order(),
            "fast_provider": fast_model_spec.get("provider", ""),
            "fast_model": fast_model_spec.get("model", ""),
            "smart_provider": smart_model_spec.get("provider", ""),
            "smart_model": smart_model_spec.get("model", ""),
            "live_configured": any(_provider_available(provider) for provider in _provider_iteration_order()),
            "last_errors": dict(_MODEL_RUNTIME_LAST_ERROR),
            "last_provider_switch": dict(_MODEL_RUNTIME_LAST_SWITCH),
        },
        "ts":         time.time(),
    }


# ── REST: Subscribe ───────────────────────────────────────────────────────────
_subscribe_rl: dict[str, list[float]] = {}   # IP → list of timestamps

@app.post("/api/subscribe")
async def subscribe(request: Request):
    """Add an email to subscribers.json."""
    # Rate limit: 5 subscribes per IP per hour
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = _subscribe_rl.get(client_ip, [])
    hits = [t for t in hits if now - t < 3600]
    if len(hits) >= 5:
        return JSONResponse({"error": "rate limit exceeded"}, status_code=429)
    hits.append(now)
    _subscribe_rl[client_ip] = hits

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return JSONResponse({"error": "invalid email"}, status_code=400)
    subs_path = Path(__file__).parent / "subscribers.json"
    subs: list = []
    if subs_path.exists():
        try:
            subs = json.loads(subs_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            subs = []
    existing = {s.get("email", "").lower() for s in subs}
    if email in existing:
        return {"status": "already_subscribed", "email": email}
    subs.append({"email": email, "active": True, "joined": time.strftime("%Y-%m-%d"), "source": "scanner"})
    subs_path.write_text(json.dumps(subs, indent=2), encoding="utf-8")
    return {"status": "subscribed", "email": email}


# ── REST: Edge Pro unlock (magic-link cookie flow) ────────────────────────────
try:
    import edge_unlock as _edge_unlock
    _EDGE_UNLOCK_AVAILABLE = True
except ImportError:
    _EDGE_UNLOCK_AVAILABLE = False

_unlock_rl: dict[str, list[float]] = {}  # IP → request timestamps


@app.post("/api/unlock/request")
async def unlock_request(request: Request):
    """Send an Edge Pro magic-link email if the address is on the premium list.

    Always returns 200 regardless of whether the email is premium to prevent
    enumeration of the subscriber list.
    """
    if not _EDGE_UNLOCK_AVAILABLE:
        return JSONResponse({"error": "unlock_unavailable"}, status_code=503)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = [t for t in _unlock_rl.get(client_ip, []) if now - t < 3600]
    if len(hits) >= 10:
        return JSONResponse({"error": "rate_limit"}, status_code=429)
    hits.append(now)
    _unlock_rl[client_ip] = hits

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email or len(email) > 254:
        return JSONResponse({"error": "invalid email"}, status_code=400)

    if _edge_unlock.is_premium(email):
        _edge_unlock.send_magic_link_email(email)
    # Generic response shape either way.
    return {"status": "sent_if_premium"}


@app.get("/api/unlock/claim")
async def unlock_claim(t: str = ""):
    """Validate magic-link, set 90-day cookie, AND render a confirmation page
    whose Continue button carries a short-TTL signed `unlock_ok` param.

    The URL param is a cookie-loss fallback: some mobile email clients open
    links in isolated in-app browsers that don't persist cookies to the user's
    default browser. The short-lived signed param lets this one session still
    unlock even if the cookie is dropped on the redirect.
    """
    if not _EDGE_UNLOCK_AVAILABLE:
        return JSONResponse({"error": "unlock_unavailable"}, status_code=503)
    from fastapi.responses import HTMLResponse, RedirectResponse
    info = _edge_unlock.verify_token(t)
    if not info.get("valid"):
        reason = "expired" if info.get("expired") else "invalid"
        return RedirectResponse(url=f"/scanner/?unlock_error={reason}", status_code=302)
    email = info["email"]
    cookie_token = _edge_unlock.issue_token(email, _edge_unlock.COOKIE_TTL_SECONDS)
    short_token = _edge_unlock.issue_token(email, _edge_unlock.SHORT_UNLOCK_TTL_SECONDS)
    continue_url = f"/scanner/?unlock_ok={short_token}"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Pro unlocked</title>
<meta http-equiv="refresh" content="3;url={continue_url}">
<style>
  html,body{{margin:0;background:#0d1117;color:#c9d1d9;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif}}
  .wrap{{max-width:520px;margin:80px auto;padding:32px;background:#161b22;border:1px solid #30363d;border-radius:14px;text-align:center}}
  .ok{{font-size:44px;line-height:1}} h1{{color:#fff;margin:16px 0 8px;font-size:22px}}
  p{{color:#8b949e;line-height:1.6;margin:8px 0}} code{{color:#58a6ff;font-size:12px;word-break:break-all}}
  a.btn{{display:inline-block;margin-top:18px;padding:12px 22px;background:#2ea043;color:#0d1117;
    border-radius:8px;font-weight:700;text-decoration:none}}
  .small{{font-size:12px;color:#6e7681;margin-top:20px;border-top:1px solid #30363d;padding-top:12px}}
</style></head><body>
<div class="wrap">
  <div class="ok">✅</div>
  <h1>Edge Pro unlocked</h1>
  <p>Welcome back, <strong>{email}</strong>.</p>
  <p>Cookie set for 90 days on this device. Redirecting to the scanner…</p>
  <a class="btn" href="{continue_url}">Continue to Scanner →</a>
  <div class="small">If this device blocks cookies (some in-app browsers do),
    the Continue link still unlocks your session via a short-lived signed token.</div>
</div>
<script>
  // As soon as JS is live, go straight through — no 3s wait.
  setTimeout(function(){{ location.href = {continue_url!r}; }}, 400);
</script>
</body></html>"""
    resp = HTMLResponse(page, status_code=200)
    resp.set_cookie(
        key=_edge_unlock.COOKIE_NAME,
        value=cookie_token,
        max_age=_edge_unlock.COOKIE_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return resp


@app.get("/api/unlock/verify")
async def unlock_verify(t: str = ""):
    """Validate a short-TTL unlock_ok token (URL fallback when cookie drops)."""
    if not _EDGE_UNLOCK_AVAILABLE:
        return {"tier": "free", "email": None}
    info = _edge_unlock.verify_token(t)
    if info.get("valid"):
        return {"tier": "pro", "email": info.get("email")}
    return {"tier": "free", "email": None, "expired": info.get("expired", False)}


@app.post("/api/unlock/exchange")
async def unlock_exchange(request: Request):
    """Exchange a magic-link token (or full magic-link URL) for a fresh 90-day
    cookie on the CALLING browser.

    This is the paste-unlock path: the user copies the magic link from their
    email client (which opened the link in an isolated in-app webview that
    can't share cookies with their default browser) and pastes it here from
    their real browser. We re-issue a full cookie bound to this browser.
    """
    if not _EDGE_UNLOCK_AVAILABLE:
        return JSONResponse({"error": "unlock_unavailable"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    raw = (body.get("token") or body.get("url") or "").strip()
    if not raw:
        return JSONResponse({"error": "missing token"}, status_code=400)
    if "?" in raw or raw.startswith("http"):
        from urllib.parse import urlparse, parse_qs
        try:
            parsed = urlparse(raw)
            token = (parse_qs(parsed.query).get("t", [""]) or [""])[0]
        except Exception:
            token = ""
    else:
        token = raw
    if not token:
        return JSONResponse({"error": "no token in input"}, status_code=400)
    info = _edge_unlock.verify_token(token)
    if not info.get("valid"):
        reason = "expired" if info.get("expired") else "invalid"
        return JSONResponse({"error": reason}, status_code=400)
    email = info["email"]
    cookie_token = _edge_unlock.issue_token(email, _edge_unlock.COOKIE_TTL_SECONDS)
    resp = JSONResponse({"status": "ok", "tier": "pro", "email": email})
    resp.set_cookie(
        key=_edge_unlock.COOKIE_NAME,
        value=cookie_token,
        max_age=_edge_unlock.COOKIE_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return resp


@app.get("/api/tier")
async def tier_status(request: Request):
    """Report whether the caller has a valid Edge Pro cookie."""
    if not _EDGE_UNLOCK_AVAILABLE:
        return {"tier": "free", "email": None}
    cookie = request.cookies.get(_edge_unlock.COOKIE_NAME, "")
    return _edge_unlock.tier_for_cookie(cookie)


@app.get("/api/unlock/logout")
async def unlock_logout():
    """Clear the edge_tier cookie."""
    from fastapi.responses import RedirectResponse
    resp = RedirectResponse(url="/scanner/?logged_out=1", status_code=302)
    resp.delete_cookie(
        key="edge_tier", path="/", samesite="lax"
    )
    return resp


@app.post("/api/stripe-webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe checkout.session.completed events to register paid subscribers."""
    import hashlib
    import hmac

    body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # Load webhook secret from env
    env_file = Path(__file__).parent / ".sec_email_env"
    webhook_secret = ""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("STRIPE_WEBHOOK_SECRET="):
                webhook_secret = line.split("=", 1)[1].strip()
                break

    # Verify Stripe signature — reject if secret missing or signature invalid
    if not webhook_secret:
        return JSONResponse({"error": "webhook not configured"}, status_code=500)
    if not sig_header:
        return JSONResponse({"error": "missing signature"}, status_code=400)
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    timestamp = parts.get("t", "")
    v1_sig = parts.get("v1", "")
    signed_payload = f"{timestamp}.{body.decode('utf-8')}"
    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, v1_sig):
        return JSONResponse({"error": "invalid signature"}, status_code=400)

    try:
        event = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {}) or {}

    try:
        from subscriber_store import upsert_subscriber, mark_status
    except Exception as exc:
        return JSONResponse({"error": f"subscriber_store unavailable: {exc}"}, status_code=500)

    def _extract_email(o: dict) -> str:
        return (
            o.get("customer_email")
            or (o.get("customer_details") or {}).get("email", "")
            or ""
        ).strip().lower()

    if event_type == "checkout.session.completed":
        email = _extract_email(obj)
        if not email:
            return {"status": "ok", "note": "no email in session"}
        amount = obj.get("amount_total", 0) or 0
        tier = "pro" if amount >= 3500 else "reader"
        upsert_subscriber(
            email,
            status="active",
            active=True,
            tier=tier,
            stripe_customer_id=obj.get("customer", ""),
            stripe_subscription_id=obj.get("subscription", ""),
            source="stripe",
        )
        if _AUTH_AVAILABLE:
            from api_auth import generate_api_key
            generate_api_key(email, "paid")
        print(f"stripe_webhook: checkout_completed {email} tier={tier}")

    elif event_type == "invoice.payment_succeeded":
        email = _extract_email(obj)
        if not email:
            return {"status": "ok", "note": "no email"}
        lines = ((obj.get("lines") or {}).get("data") or [])
        period_end = None
        for line in lines:
            period_end = (line.get("period") or {}).get("end") or period_end
        amount_paid = obj.get("amount_paid", 0) or 0
        tier = "pro" if amount_paid >= 3500 else "reader"
        mark_status(email, "active", period_end=period_end)
        upsert_subscriber(email, tier=tier, last_payment_at=int(time.time()))
        print(f"stripe_webhook: payment_succeeded {email} period_end={period_end}")

    elif event_type == "invoice.payment_failed":
        email = _extract_email(obj)
        if email:
            mark_status(email, "past_due")
            print(f"stripe_webhook: payment_failed {email} → past_due")

    elif event_type == "customer.subscription.updated":
        email = _extract_email(obj)
        if not email:
            customer_id = obj.get("customer", "")
            from subscriber_store import _get_all as _all
            for e, rec in _all().items():
                if rec.get("stripe_customer_id") == customer_id:
                    email = e
                    break
        if email:
            status = obj.get("status", "active")
            period_end = obj.get("current_period_end")
            mark_status(email, status, period_end=period_end)
            print(f"stripe_webhook: subscription_updated {email} status={status}")

    elif event_type == "customer.subscription.deleted":
        email = _extract_email(obj)
        if not email:
            customer_id = obj.get("customer", "")
            from subscriber_store import _get_all as _all
            for e, rec in _all().items():
                if rec.get("stripe_customer_id") == customer_id:
                    email = e
                    break
        if email:
            mark_status(email, "canceled")
            print(f"stripe_webhook: subscription_deleted {email} → canceled")

    return {"status": "ok", "event_type": event_type}


@app.get("/api/billing/portal")
async def billing_portal(request: Request):
    """Return a Stripe Customer Portal URL for the currently-signed-in subscriber.

    Auth is via the edge_tier cookie. Admins and free users get 400 — admin has
    no subscription to manage, free has no portal identity. Paying customers
    get a 302 straight to Stripe's hosted portal where they can cancel,
    update their card, or swap plans. Stripe bounces them back to /scanner/.
    """
    if not _EDGE_UNLOCK_AVAILABLE:
        return JSONResponse({"error": "unlock_unavailable"}, status_code=503)
    cookie = request.cookies.get(_edge_unlock.COOKIE_NAME, "")
    info = _edge_unlock.verify_token(cookie) if cookie else {"valid": False}
    if not info.get("valid"):
        return JSONResponse({"error": "not_authenticated"}, status_code=401)
    email = (info.get("email") or "").strip().lower()
    if _edge_unlock.is_admin(email):
        return JSONResponse(
            {"error": "admin_has_no_subscription",
             "note": "Admins are flagged via ADMIN_EMAILS, not Stripe."},
            status_code=400,
        )
    from subscriber_store import get_subscriber
    sub = get_subscriber(email) or {}
    customer_id = sub.get("stripe_customer_id", "")
    if not customer_id:
        return JSONResponse(
            {"error": "no_stripe_customer",
             "note": "Sign up via Stripe Checkout first."},
            status_code=404,
        )

    env_file = Path(__file__).parent / ".sec_email_env"
    stripe_key = ""
    return_url = "https://catalystedgescanner.com/scanner/"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("STRIPE_SECRET_KEY="):
                stripe_key = line.split("=", 1)[1].strip()
            elif line.startswith("STRIPE_PORTAL_RETURN_URL="):
                return_url = line.split("=", 1)[1].strip() or return_url
    if not stripe_key:
        return JSONResponse(
            {"error": "stripe_not_configured",
             "note": "Set STRIPE_SECRET_KEY in .sec_email_env"},
            status_code=503,
        )

    import urllib.parse
    import urllib.request
    import urllib.error
    body = urllib.parse.urlencode({
        "customer": customer_id,
        "return_url": return_url,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.stripe.com/v1/billing_portal/sessions",
        data=body,
        headers={
            "Authorization": f"Bearer {stripe_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8")
        except Exception:
            err_body = str(exc)
        return JSONResponse(
            {"error": "stripe_api_error", "status": exc.code, "detail": err_body[:400]},
            status_code=502,
        )
    except Exception as exc:
        return JSONResponse(
            {"error": "stripe_unreachable", "detail": str(exc)[:200]},
            status_code=502,
        )
    portal_url = data.get("url")
    if not portal_url:
        return JSONResponse({"error": "stripe_no_url", "detail": data}, status_code=502)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=portal_url, status_code=302)


@app.get("/api/admin/bootstrap")
async def admin_bootstrap(key: str = ""):
    """One-click admin cookie installer. Bookmark this on each device.

    Only emails in ADMIN_EMAILS can receive this cookie, and only with the
    shared ADMIN_BOOTSTRAP_KEY. Use case: founder needs Pro access on a
    fresh browser without waiting for a magic link.
    """
    if not _EDGE_UNLOCK_AVAILABLE:
        return JSONResponse({"error": "unlock_unavailable"}, status_code=503)
    env_file = Path(__file__).parent / ".sec_email_env"
    bootstrap_key = ""
    admin_emails_raw = ""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ADMIN_BOOTSTRAP_KEY="):
                bootstrap_key = line.split("=", 1)[1].strip()
            elif line.startswith("ADMIN_EMAILS="):
                admin_emails_raw = line.split("=", 1)[1].strip()
    if not bootstrap_key:
        return JSONResponse({"error": "admin_bootstrap_not_configured"}, status_code=503)
    import hmac as _hmac
    if not _hmac.compare_digest(key.encode(), bootstrap_key.encode()):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    admins = [e.strip().lower() for e in admin_emails_raw.split(",") if e.strip()]
    if not admins:
        return JSONResponse({"error": "no_admin_emails"}, status_code=503)
    email = admins[0]
    cookie_token = _edge_unlock.issue_token(email, _edge_unlock.COOKIE_TTL_SECONDS)
    from fastapi.responses import HTMLResponse
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="1;url=/scanner/">
<title>Admin session installed</title>
<style>body{{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
background:#0d1117;color:#c9d1d9;padding:48px;text-align:center}}
h1{{color:#d4a843}}</style></head><body>
<h1>✓ Admin session installed</h1>
<p>{email} — redirecting to scanner…</p>
</body></html>"""
    resp = HTMLResponse(page, status_code=200)
    resp.set_cookie(
        key=_edge_unlock.COOKIE_NAME,
        value=cookie_token,
        max_age=_edge_unlock.COOKIE_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return resp


@app.post("/api/keys/generate")
async def generate_api_key_endpoint(request: Request):
    """Generate a new API key. Requires admin secret in X-Admin-Key header."""
    admin_secret = os.getenv("API_ADMIN_SECRET", "").strip()
    if not admin_secret:
        env_file = Path(__file__).parent / ".sec_email_env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("API_ADMIN_SECRET="):
                    admin_secret = line.split("=", 1)[1].strip()
                    break
    if not admin_secret:
        raise HTTPException(status_code=503, detail="API key generation not configured")

    provided = request.headers.get("x-admin-key", "").strip()
    if not hmac.compare_digest(provided.encode(), admin_secret.encode()):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    email = (body.get("email") or "").strip().lower()
    tier = body.get("tier", "free")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    if tier not in ("free", "paid"):
        raise HTTPException(status_code=400, detail="Tier must be 'free' or 'paid'")

    if _AUTH_AVAILABLE:
        from api_auth import generate_api_key
        key = generate_api_key(email, tier)
        return {"api_key": key, "email": email, "tier": tier, "note": "Store this key — it cannot be retrieved later."}
    raise HTTPException(status_code=503, detail="Auth module not available")


@app.get("/api/newsletter/archive")
async def newsletter_archive():
    """Return list of available newsletter editions (newest first)."""
    archive_dir = Path(__file__).parent / "archive"
    editions = []
    if archive_dir.exists():
        for f in sorted(archive_dir.glob("newsletter_*.html"), reverse=True):
            date_str = f.stem.replace("newsletter_", "")
            editions.append({"date": date_str, "file": f.name})
    return {"editions": editions[:20]}


@app.get("/api/newsletter/latest")
async def newsletter_latest():
    """Return the latest newsletter HTML content."""
    latest = Path(__file__).parent / "newsletter" / "latest.html"
    if not latest.exists():
        return JSONResponse({"error": "no newsletter available"}, status_code=404)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(latest.read_text(encoding="utf-8"))


@app.get("/api/newsletter/{date}")
async def newsletter_by_date(date: str):
    """Return a specific newsletter edition by date."""
    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return JSONResponse({"error": "invalid date format"}, status_code=400)
    archive = Path(__file__).parent / "archive" / f"newsletter_{date}.html"
    if not archive.exists():
        return JSONResponse({"error": "edition not found"}, status_code=404)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(archive.read_text(encoding="utf-8"))


@app.get("/api/providers")
async def get_providers():
    return {
        "providers": _provider_contract(),
        "summary": _provider_summary(),
        "openbb": _openbb_pilot_settings(),
    }


@app.get("/api/scanner/quotes")
async def get_scanner_quotes(tickers: str = Query(..., min_length=1)):
    requested = _parse_scanner_quote_request(tickers)
    if not requested:
        raise HTTPException(status_code=400, detail="No valid tickers provided")
    quotes = await asyncio.gather(*(asyncio.to_thread(_fetch_scanner_quote, ticker) for ticker in requested))
    return {
        "contract_version": CONTRACT_VERSION,
        "requested": requested,
        "quotes": quotes,
        "provider_summary": {
            "finnhub_configured": bool(_FINNHUB_TOKEN),
            "cache_ttl_sec": _SCANNER_QUOTE_CACHE_TTL,
        },
    }


@app.get("/api/openbb/pilot")
async def get_openbb_pilot():
    try:
        snapshot = await asyncio.wait_for(
            asyncio.to_thread(_fetch_openbb_pilot_snapshot),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        snapshot = {"status": "degraded", "reason": "openbb_fetch_timeout_5s"}
    return {
        "contract_version": CONTRACT_VERSION,
        "pilot": snapshot,
    }


# ── REST: Universe (paginated) ────────────────────────────────────────────────
_UNIVERSE_ROWS_CACHE: list | None = None
_UNIVERSE_ROWS_CACHE_TS: float = 0.0
_UNIVERSE_ROWS_CACHE_TTL = 300.0  # 5 min; full em+scanner_overlay scan is ~20-30s


async def _build_universe_rows() -> list:
    """Assemble the full, unfiltered, brightness-sorted universe row set.
    Called once per TTL window — callers filter + paginate from this cache."""
    em: dict = await _read_json("entity_master")
    sparks: dict = await _read_json("spark_velocities")
    scanner_overlay = await asyncio.get_running_loop().run_in_executor(None, _read_scanner_overlay)

    rows = []
    for ticker, rec in em.items():
        if rec.get("etf"):
            continue
        overlay_item = scanner_overlay.get(ticker)
        rows.append(_merge_scanner_overlay(
            _universe_row(rec, sparks, ticker, overlay_item), overlay_item))

    for ticker, item in scanner_overlay.items():
        if ticker in em:
            continue
        rows.append(_scanner_overlay_universe_row(ticker, item))

    rows.sort(key=lambda r: -r["brightness"])
    return rows


@app.get("/api/universe")
async def get_universe(
    page:     int = Query(1,   ge=1),
    per_page: int = Query(500, ge=1, le=15000),
    sector:   Optional[str] = Query(None),
    min_gravity: float = Query(0.0),
):
    """Paginated entity_master plus scanner-overlay parity rows.
    5-min TTL cache on the full row set (HUD polls this with 7,325+ nodes;
    uncached rebuild is ~20-30s and was tripping verify-script timeouts)."""
    global _UNIVERSE_ROWS_CACHE, _UNIVERSE_ROWS_CACHE_TS
    now = time.time()
    if (_UNIVERSE_ROWS_CACHE is None or
            (now - _UNIVERSE_ROWS_CACHE_TS) >= _UNIVERSE_ROWS_CACHE_TTL):
        _UNIVERSE_ROWS_CACHE = await _build_universe_rows()
        _UNIVERSE_ROWS_CACHE_TS = now

    all_rows = _UNIVERSE_ROWS_CACHE
    if sector or min_gravity > 0:
        filtered = [
            r for r in all_rows
            if r["gravity"] >= min_gravity
            and (not sector or r.get("sector") == sector)
        ]
    else:
        filtered = all_rows

    total = len(filtered)
    start = (page - 1) * per_page
    return {
        "contract_version": CONTRACT_VERSION,
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    (total + per_page - 1) // per_page,
        "tickers":  filtered[start : start + per_page],
    }


# ── REST: Single ticker ───────────────────────────────────────────────────────
@app.get("/api/ticker/{symbol}")
async def get_ticker(symbol: str):
    em: dict     = await _read_json("entity_master")
    sparks: dict = await _read_json("spark_velocities")
    scanner_overlay = await asyncio.get_running_loop().run_in_executor(None, _read_scanner_overlay)

    requested_ticker = _canonical_quote_symbol(symbol)
    ticker = requested_ticker
    rec = None
    overlay_item = None
    for candidate in _quote_symbol_candidates(requested_ticker, provider="lookup"):
        rec = em.get(candidate)
        overlay_item = scanner_overlay.get(candidate)
        if rec or overlay_item:
            ticker = candidate
            break
    if not rec and not overlay_item:
        raise HTTPException(status_code=404, detail=f"{ticker} not in entity_master or scanner overlay")

    loop = asyncio.get_running_loop()
    sympathy_future = loop.run_in_executor(None, _sympathy_history_for_ticker, ticker, 5)
    memory_future = _everos_context(f"{ticker} velocity sympathy catalyst", limit=3)
    sympathy_history, memory_context = await asyncio.gather(sympathy_future, memory_future)

    spark_e = canonical_spark_snapshot(sparks.get(ticker, {}))
    if rec:
        name = rec.get("name", "")
        gravity = _normalized_gravity(rec, ticker, overlay_item)
        brightness = _brightness(rec, sparks, ticker, overlay_item)
        mkt_cap_usd = rec.get("mkt_cap_usd")
        cap_tier = rec.get("mkt_cap_tier", "")
        sector, sector_source, sector_inferred, sector_evidence, gics = _normalized_sector_detail(rec, ticker)
        etf_weights_sum = rec.get("etf_weights_sum", 0.0) or 0.0
        etf_overlords = _normalize_etf_overlords(rec.get("etf_overlords", []), etf_weights_sum)
        is_rogue = rec.get("is_rogue", False)
        geospatial_nodes = rec.get("geospatial_nodes", [])
        cik = rec.get("cik", "")
        scanner_payload = _merge_scanner_overlay({}, overlay_item)
    else:
        overlay_row = _scanner_overlay_universe_row(ticker, overlay_item or {})
        name = overlay_row["name"]
        gravity = overlay_row["gravity"]
        brightness = overlay_row["brightness"]
        mkt_cap_usd = overlay_item.get("market_cap") if overlay_item else None
        cap_tier = ""
        sector, sector_source, sector_inferred, sector_evidence, gics = _normalized_sector_detail({}, ticker)
        sector = overlay_row.get("sector", sector)
        etf_weights_sum = 0.0
        etf_overlords = []
        is_rogue = False
        geospatial_nodes = []
        cik = ""
        scanner_payload = overlay_row

    velocity_event = build_velocity_event(
        ticker,
        spark_e,
        name=name,
        wire_event="velocity_snapshot",
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "velocity_deck_schema_version": VELOCITY_DECK_SCHEMA_VERSION,
        "ticker":         ticker,
        "requested_ticker": requested_ticker,
        "name":           name,
        "gravity":        gravity,
        "brightness":     brightness,
        "mkt_cap_usd":    mkt_cap_usd,
        "cap_tier":       cap_tier,
        "sector":         sector,
        "sector_source":  sector_source,
        "sector_inferred": sector_inferred,
        "sector_evidence": sector_evidence,
        "gics":           gics,
        "etf_weights_sum":etf_weights_sum,
        "etf_overlords":  etf_overlords,
        "is_rogue":       is_rogue,
        "sparks":         spark_e,
        "velocity_event": velocity_event,
        "geospatial_nodes": geospatial_nodes,
        "cik":            cik,
        "sympathy_history": sympathy_history,
        "memory_context": memory_context,
        "scanner_only":   scanner_payload.get("scanner_only", False),
        "scanner_sources": scanner_payload.get("scanner_sources", []),
        "scanner_rank":   scanner_payload.get("scanner_rank"),
        "scanner_score":  scanner_payload.get("scanner_score"),
        "scanner_form":   scanner_payload.get("scanner_form", ""),
        "scanner_tags":   scanner_payload.get("scanner_tags", ""),
        "scanner_link":   scanner_payload.get("scanner_link", ""),
    }


# ── REST: Sectors ─────────────────────────────────────────────────────────────
_SECTORS_AGG_CACHE: dict | None = None
_SECTORS_AGG_CACHE_TS: float = 0.0
_SECTORS_AGG_CACHE_TTL = 300.0  # 5 min; heatmap called frequently


@app.get("/api/sectors")
async def get_sectors():
    """Aggregate brightness and gravity by GICS sector. 5-min cached — full
    scan of ~16k entity_master entries is expensive and heatmap polls it."""
    global _SECTORS_AGG_CACHE, _SECTORS_AGG_CACHE_TS
    now = time.time()
    if _SECTORS_AGG_CACHE is not None and (now - _SECTORS_AGG_CACHE_TS) < _SECTORS_AGG_CACHE_TTL:
        return _SECTORS_AGG_CACHE

    em: dict     = await _read_json("entity_master")
    sparks: dict = await _read_json("spark_velocities")
    macro: dict  = await _read_json("macro_pressure")
    pressures    = macro.get("pressures", {})

    buckets: dict[str, dict] = {}
    for ticker, rec in em.items():
        if rec.get("etf"):
            continue
        sector = _normalized_sector(rec, ticker)
        b = _brightness(rec, sparks, ticker)
        g = _normalized_gravity(rec, ticker)
        if sector not in buckets:
            buckets[sector] = {"brightness_sum": 0.0, "gravity_sum": 0.0,
                               "ticker_count": 0, "top_tickers": []}
        buckets[sector]["brightness_sum"] += b
        buckets[sector]["gravity_sum"]    += g
        buckets[sector]["ticker_count"]   += 1
        buckets[sector]["top_tickers"].append((ticker, b))

    result = []
    for sector, d in buckets.items():
        n = d["ticker_count"]
        tops = sorted(d["top_tickers"], key=lambda x: -x[1])[:5]
        p = pressures.get(sector, {})
        result.append({
            "sector":          sector,
            "ticker_count":    n,
            "avg_brightness":  round(d["brightness_sum"] / n, 2) if n else 0,
            "avg_gravity":     round(d["gravity_sum"]    / n, 4) if n else 0,
            "multiplier":      p.get("multiplier", 1.0),
            "macro_signals":   p.get("signals", []),
            "top_tickers":     [{"ticker": t, "brightness": b} for t, b in tops],
        })

    result.sort(key=lambda r: -r["avg_brightness"])
    payload = {"sectors": result}
    _SECTORS_AGG_CACHE = payload
    _SECTORS_AGG_CACHE_TS = now
    return payload


# ── REST: Macro ───────────────────────────────────────────────────────────────
@app.get("/api/macro")
async def get_macro():
    layer:    dict = await _read_json("macro_layer")
    pressure: dict = await _read_json("macro_pressure")
    openbb_snapshot = None
    openbb_source = "artifact"

    try:
        if _openbb_pilot_settings().get("enabled"):
            openbb_snapshot = await asyncio.wait_for(
                asyncio.to_thread(_fetch_openbb_pilot_snapshot),
                timeout=5.0,
            )
            macro_series = (openbb_snapshot.get("macro") or {}).get("series") or {}
            if macro_series:
                openbb_source = (openbb_snapshot.get("sources") or {}).get("macro") or "openbb_pilot"
                layer = {
                    **(layer or {}),
                    "openbb_macro": {
                        "provider": (openbb_snapshot.get("macro") or {}).get("provider", ""),
                        "series": macro_series,
                    },
                }
    except asyncio.TimeoutError:
        openbb_snapshot = {
            "status": "degraded",
            "reason": "openbb_fetch_timeout_5s",
        }
    except Exception as exc:
        openbb_snapshot = {
            "status": "error",
            "reason": f"{type(exc).__name__}: {exc}",
        }

    return {
        "macro_layer": layer,
        "macro_pressure": pressure,
        "source": openbb_source,
        "openbb": openbb_snapshot,
    }


@app.get("/api/crypto")
async def get_crypto_snapshot():
    try:
        snapshot = await asyncio.wait_for(
            asyncio.to_thread(_fetch_openbb_pilot_snapshot),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        snapshot = {"status": "degraded", "reason": "openbb_fetch_timeout_5s"}
    crypto = snapshot.get("crypto") or {}
    quotes = crypto.get("quotes") or []
    source = (
        (snapshot.get("sources") or {}).get("crypto")
        if quotes
        else snapshot.get("reason") or snapshot.get("status") or "disabled"
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "source": source,
        "status": snapshot.get("status", "disabled"),
        "provider": crypto.get("provider", snapshot.get("selected_providers", {}).get("crypto", "")),
        "quotes": quotes,
        "errors": snapshot.get("errors", []),
    }


# ── REST: AlphaInsider Positions ──────────────────────────────────────────────
@app.get("/api/positions")
async def get_alphainsider_positions():
    pos_path = ROOT / "alphainsider_positions.json"
    if pos_path.exists():
        try:
            data = json.loads(pos_path.read_text(encoding="utf-8"))
            return data
        except Exception:
            pass
    return {"strategy": "", "position_count": 0, "positions": []}


@app.get("/api/trades")
async def get_trade_log(limit: int = Query(50, ge=1, le=500)):
    log_path = ROOT / "alphainsider_trade_log.csv"
    if not log_path.exists():
        return {"trades": [], "count": 0}
    rows = []
    with open(log_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    rows.reverse()
    return {"trades": rows[:limit], "count": len(rows)}


# ── REST: Congress ────────────────────────────────────────────────────────────
@app.get("/api/congress")
async def get_congress(limit: int = Query(100, ge=1, le=1000)):
    csv_path = ROOT / "congressional_trades.csv"
    if not csv_path.exists():
        return {"trades": [], "count": 0, "pending_parse": 0}
    trades: list[dict] = []
    pending_parse = 0
    import re as _re
    _cusip_re = _re.compile(r"^\d{3}[A-Z0-9]{5}\d$")
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or "").strip()
            # House clerk XML stubs (ticker/txn_type/amount empty) are filings
            # the scanner knows exist but hasn't parsed the PDF for yet.
            # Don't show "— — —" rows on the public page; expose the count.
            if not ticker:
                pending_parse += 1
                continue
            # Drop CUSIPs (9-char bond identifiers) that Quiver sometimes
            # returns for corporate/municipal bond disclosures — they aren't
            # tradable stock tickers.
            if len(ticker) == 9 and _cusip_re.match(ticker):
                continue
            if len(ticker) > 6:
                continue
            trades.append(row)

    # Guard against typos in source PDFs that put transactions 9+ months in
    # the future — those rows would otherwise dominate the date-sorted slice.
    import datetime as _dt
    _future_cutoff = (_dt.date.today() + _dt.timedelta(days=7)).isoformat()
    def _sort_key(t: dict) -> str:
        d = t.get("transaction_date") or t.get("disclosure_date") or ""
        if d and d > _future_cutoff:
            return t.get("disclosure_date", "") or ""
        return d

    # Sort newest-first so the top-N always surfaces the freshest trades
    # across BOTH chambers — otherwise Quiver's older Senate tail dominates
    # the default 100-row slice and the House filter renders empty.
    trades.sort(key=_sort_key, reverse=True)

    return {
        "trades": trades[:limit],
        "count": len(trades),
        "pending_parse": pending_parse,
    }


# ── REST: Squeeze Tracker ─────────────────────────────────────────────────────
@app.get("/api/squeeze")
async def get_squeeze(limit: int = Query(50, ge=1, le=100)):
    csv_path = ROOT / "squeeze_candidates.csv"
    if not csv_path.exists():
        return {"candidates": [], "count": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "squeeze_score": row.get("squeeze_score", ""),
                "stage": row.get("stage", ""),
                "short_pct_float": row.get("short_pct_float", ""),
                "days_to_cover": row.get("days_to_cover", ""),
                "si_trend_pct": row.get("si_trend_pct", ""),
                "gamma_score": row.get("gamma_score", ""),
                "price": row.get("price", ""),
                "score_breakdown": row.get("score_breakdown", ""),
            })
    return {"candidates": rows[:limit], "count": len(rows)}


# ── REST: Insider Clusters ────────────────────────────────────────────────────
@app.get("/api/insiders")
async def get_insiders(limit: int = Query(50, ge=1, le=100)):
    csv_path = ROOT / "insider_clusters.csv"
    if not csv_path.exists():
        return {"clusters": [], "count": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "filing_count": row.get("filing_count", ""),
                "confirmed_buy": row.get("confirmed_buy", ""),
                "latest_utc": row.get("latest_utc", ""),
                "price": row.get("price", ""),
                "market_cap": row.get("market_cap", ""),
                "tags": row.get("tags", ""),
                "primary_link": row.get("primary_link", ""),
            })
    return {"clusters": rows[:limit], "count": len(rows)}


# ── REST: Lockup Calendar ─────────────────────────────────────────────────────
@app.get("/api/lockups")
async def get_lockups(limit: int = Query(200, ge=1, le=500)):
    csv_path = ROOT / "lockup_calendar.csv"
    if not csv_path.exists():
        return {"lockups": [], "count": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "company_name": row.get("company_name", ""),
                "lockup_expiry_date": row.get("lockup_expiry_date", ""),
                "days_until_expiry": row.get("days_until_expiry", ""),
                "status": row.get("status", ""),
                "insider_bought_after": row.get("insider_bought_after", ""),
                "link": row.get("link", ""),
            })
    return {"lockups": rows[:limit], "count": len(rows)}


# ── REST: Scanner (top picks) ─────────────────────────────────────────────────
@app.get("/api/scanner")
async def get_scanner_picks(limit: int = Query(10, ge=1, le=50)):
    csv_path = ROOT / "sec_catalyst_ranked.csv"
    if not csv_path.exists():
        return {"picks": [], "total_filings": 0, "total_catalysts": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    picks = []
    for row in rows[:limit]:
        picks.append({
            "ticker": row.get("ticker", ""),
            "score": row.get("priority_score", row.get("score", row.get("total_score", ""))),
            "form_type": row.get("form", row.get("form_type", row.get("formType", ""))),
            "category": row.get("category", row.get("tier", "")),
            "quality_score": row.get("quality_score", ""),
        })
    return {"picks": picks, "total_filings": len(rows), "total_catalysts": len(rows)}


# ── REST: Options ─────────────────────────────────────────────────────────────
@app.get("/api/options")
async def get_options(limit: int = Query(50, ge=1, le=500)):
    activity: dict = await _read_json("options_activity")
    rows = []
    for ticker, data in activity.items():
        if not _options_activity_is_fresh(data):
            continue
        flow        = data.get("flow", {})
        sweep_count = data.get("sweep_count", 0) or 0
        if sweep_count == 0 and flow.get("sentiment", "neutral").upper() == "NEUTRAL":
            continue
        call_vol = flow.get("call_volume", 0) or 0
        put_vol  = flow.get("put_volume",  0) or 0
        rows.append({
            "ticker":      ticker,
            "sweep_count": sweep_count,
            "call_sweeps": data.get("call_sweeps", 0),
            "sentiment":   flow.get("sentiment", "neutral"),
            "pc_ratio":    round(put_vol / call_vol, 3) if call_vol > 0 else 1.0,
            "gamma_magnet":data.get("gamma_magnet"),
            "price":       data.get("price", 0.0),
            "top_sweeps":  (data.get("top_sweeps") or [])[:3],
            "source":      data.get("source", ""),
            "ts":          data.get("ts"),
        })
    rows.sort(key=lambda r: -r["sweep_count"])
    return {"options": rows[:limit], "total": len(rows)}


@app.get("/api/options-flow")
async def get_options_flow(limit: int = Query(50, ge=1, le=200)):
    csv_path = ROOT / "options_flow.csv"
    if not csv_path.exists():
        return {"flows": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "price": row.get("current_price", ""),
                "call_oi": row.get("call_oi", ""),
                "put_oi": row.get("put_oi", ""),
                "pc_ratio": row.get("pc_ratio", ""),
                "gamma_score": row.get("gamma_score", ""),
                "max_pain": row.get("max_pain", ""),
                "atm_call_iv": row.get("atm_call_iv", ""),
                "unusual_call_vol": row.get("unusual_call_vol", ""),
                "source": row.get("source", ""),
                "activity_ts": row.get("activity_ts", ""),
            })
    return {"flows": rows[:limit], "total": len(rows)}


@app.get("/api/gaps")
async def get_gap_scanner(limit: int = Query(50, ge=1, le=200)):
    csv_path = ROOT / "gap_scanner.csv"
    if not csv_path.exists():
        return {"gaps": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "price": row.get("price", ""),
                "prev_close": row.get("prev_close", ""),
                "gap_pct": row.get("overnight_gap_pct", row.get("effective_gap_pct", "")),
                "volume": row.get("volume", ""),
                "avg_volume": row.get("avg_volume", ""),
                "vol_ratio": row.get("vol_ratio", ""),
                "accum_label": row.get("accum_label", ""),
                "gap_score": row.get("gap_score", ""),
                "date": row.get("date", ""),
            })
    rows.sort(key=lambda r: -float(r.get("gap_score") or 0))
    return {"gaps": rows[:limit], "total": len(rows)}


@app.get("/api/convergence")
async def get_convergence(limit: int = Query(50, ge=1, le=300)):
    csv_path = ROOT / "convergence_alerts.csv"
    if not csv_path.exists():
        return {"alerts": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "score": row.get("convergence_score", ""),
                "conviction": row.get("conviction_level", ""),
                "signal_count": row.get("signal_count", ""),
                "signals": row.get("signals_fired", ""),
                "price": row.get("price", ""),
                "market_cap": row.get("market_cap", ""),
            })
    rows.sort(key=lambda r: -int(r.get("score") or 0))
    return {"alerts": rows[:limit], "total": len(rows)}


@app.get("/api/darkpool")
async def get_darkpool(limit: int = Query(50, ge=1, le=200)):
    csv_path = ROOT / "dark_pool.csv"
    if not csv_path.exists():
        return {"signals": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "signal_type": row.get("signal_type", ""),
                "volume": row.get("today_volume", ""),
                "avg_volume": row.get("avg_volume_30d", ""),
                "vol_ratio": row.get("volume_ratio", ""),
                "price_change": row.get("price_change_pct", ""),
                "dark_pool_flag": row.get("dark_pool_flag", ""),
            })
    rows.sort(key=lambda r: -float(r.get("vol_ratio") or 0))
    return {"signals": rows[:limit], "total": len(rows)}


@app.get("/api/deepvalue")
async def get_deepvalue(limit: int = Query(100, ge=1, le=200)):
    csv_path = ROOT / "deepvalue_screen.csv"
    if not csv_path.exists():
        return {"stocks": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "deepvalue_score": row.get("deepvalue_score", ""),
                "score": row.get("deepvalue_score", ""),
                "grade": row.get("grade", ""),
                "pb_ratio": row.get("pb_ratio", ""),
                "pfcf_ratio": row.get("pfcf_ratio", ""),
                "debt_eq": row.get("debt_eq", ""),
                "insider_own_pct": row.get("insider_own_pct", ""),
                "roe_pct": row.get("roe_pct", ""),
                "short_float_pct": row.get("short_float_pct", ""),
            })
    rows.sort(key=lambda r: -int(r.get("score") or 0))
    return {"stocks": rows[:limit], "total": len(rows)}


# ── REST: Merger / Tender Offer signals ──────────────────────────────────────
@app.get("/api/mergers")
async def get_mergers(limit: int = Query(50, ge=1, le=200)):
    csv_path = ROOT / "merger_signals.csv"
    if not csv_path.exists():
        return {"signals": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "signal_type": row.get("signal_type", ""),
                "form": row.get("form", ""),
                "signal_count": row.get("signal_count", ""),
                "latest_date": row.get("latest_date", ""),
                "description": row.get("description", ""),
                "link": row.get("link", ""),
            })
    return {"signals": rows[:limit], "total": len(rows)}


# ── REST: Late filing (NT) radar ─────────────────────────────────────────────
@app.get("/api/late-filings")
async def get_late_filings(limit: int = Query(100, ge=1, le=300)):
    csv_path = ROOT / "nt_radar.csv"
    if not csv_path.exists():
        return {"filings": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "signal_type": row.get("signal_type", ""),
                "nt_form": row.get("nt_form", ""),
                "filed_date": row.get("filed_date", ""),
                "filer_name": row.get("filer_name", ""),
                "has_insider_buy": row.get("has_insider_buy", ""),
                "insider_count": row.get("insider_count", ""),
                "link": row.get("link", ""),
            })
    return {"filings": rows[:limit], "total": len(rows)}


# ── REST: Smart money (13F institutional) ────────────────────────────────────
@app.get("/api/smart-money")
async def get_smart_money(limit: int = Query(50, ge=1, le=200)):
    csv_path = ROOT / "smart_money.csv"
    if not csv_path.exists():
        return {"stocks": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "fund_count": row.get("fund_count", ""),
                "latest_fund_name": row.get("latest_fund_name", ""),
                "latest_filed_date": row.get("latest_filed_date", ""),
                "total_mentions": row.get("total_mentions", ""),
                "signal": row.get("signal", ""),
                "primary_link": row.get("primary_link", ""),
            })
    rows.sort(key=lambda r: -int(r.get("fund_count") or 0))
    return {"stocks": rows[:limit], "total": len(rows)}


# ── REST: Sympathy chain events ──────────────────────────────────────────────
@app.get("/api/sympathy")
async def get_sympathy(limit: int = Query(500, ge=1, le=1000)):
    csv_path = ROOT / "sympathy_events.csv"
    if not csv_path.exists():
        return {"events": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "date": row.get("date", ""),
                "trigger_ticker": row.get("trigger_ticker", ""),
                "sector": row.get("sector", ""),
                "gap_score": row.get("gap_score", ""),
                "form": row.get("form", ""),
                "price_t0": row.get("price_t0", ""),
                "peers": row.get("peers", ""),
                "move_pct_t1day": row.get("move_pct_t1day", ""),
                "peer_avg_move_pct_t1day": row.get("peer_avg_move_pct_t1day", ""),
            })
    rows.sort(key=lambda r: -float(r.get("gap_score") or 0))
    return {"events": rows[:limit], "total": len(rows)}


# ── REST: News momentum signals ─────────────────────────────────────────────
@app.get("/api/news")
async def get_news(limit: int = Query(100, ge=1, le=500)):
    csv_path = ROOT / "news_signals.csv"
    if not csv_path.exists():
        return {"signals": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "source": row.get("source", ""),
                "tier": row.get("tier", ""),
                "ticker_explicit": row.get("ticker_explicit", ""),
                "published_utc": row.get("published_utc", ""),
                "recency_min": row.get("recency_min", ""),
                "news_score": row.get("news_score", ""),
                "sector_tags": row.get("sector_tags", ""),
                "event_tags": row.get("event_tags", ""),
                "ticker_candidates": row.get("ticker_candidates", ""),
                "headline": row.get("headline", ""),
                "link": row.get("link", ""),
            })
    rows.sort(key=lambda r: -float(r.get("news_score") or 0))
    return {"signals": rows[:limit], "total": len(rows)}


# ── REST: Daily ranked picks ────────────────────────────────────────────────
@app.get("/api/rankings")
async def get_rankings(limit: int = Query(100, ge=1, le=300)):
    csv_path = ROOT / "combined_priority.csv"
    if not csv_path.exists():
        return {"picks": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "ticker": row.get("ticker", ""),
                "total_score": row.get("total_score", ""),
                "sec_score": row.get("sec_score", ""),
                "news_score": row.get("news_score", ""),
                "gapper_score": row.get("gapper_score", ""),
                "value_score": row.get("value_score", ""),
                "moat_score": row.get("moat_score", ""),
                "news_hits": row.get("news_hits", ""),
                "sector_tags": row.get("sector_tags", ""),
                "event_tags": row.get("event_tags", ""),
            })
    rows.sort(key=lambda r: -float(r.get("total_score") or 0))
    return {"picks": rows[:limit], "total": len(rows)}


# ── REST: Historical performance log ────────────────────────────────────────
@app.get("/api/performance")
async def get_performance(limit: int = Query(200, ge=1, le=500)):
    csv_path = ROOT / "daily_recap_log.csv"
    if not csv_path.exists():
        return {"trades": [], "total": 0}
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "session_date": row.get("session_date", ""),
                "ticker": row.get("ticker", ""),
                "rank": row.get("rank", ""),
                "total_score": row.get("total_score", ""),
                "form": row.get("form", ""),
                "prev_close": row.get("prev_close", ""),
                "day_open": row.get("day_open", ""),
                "day_high": row.get("day_high", ""),
                "day_close": row.get("day_close", ""),
                "open_gap_pct": row.get("open_gap_pct", ""),
                "max_intraday_pct": row.get("max_intraday_pct", ""),
                "close_pct": row.get("close_pct", ""),
                "hit_2pct": row.get("hit_2pct", ""),
                "hit_5pct": row.get("hit_5pct", ""),
                "hit_10pct": row.get("hit_10pct", ""),
                "outcome": row.get("outcome", ""),
            })
    return {"trades": rows[:limit], "total": len(rows)}


# ── REST: Unified multi-signal screener ──────────────────────────────────────
@app.get("/api/screener")
async def get_screener():
    """Cross-reference all signal sources into one unified ticker view."""
    signals: dict[str, dict] = {}

    def _add(ticker: str, signal_type: str, data: dict) -> None:
        if not ticker:
            return
        t = ticker.upper().strip()
        if t not in signals:
            signals[t] = {"ticker": t, "signals": [], "signal_count": 0}
        signals[t]["signals"].append(signal_type)
        signals[t]["signal_count"] += 1
        signals[t][signal_type] = data

    # Rankings (combined_priority)
    p = ROOT / "combined_priority.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _add(row.get("ticker", ""), "ranking", {
                    "total_score": row.get("total_score", ""),
                    "sec_score": row.get("sec_score", ""),
                    "gapper_score": row.get("gapper_score", ""),
                    "value_score": row.get("value_score", ""),
                })

    # Squeeze candidates
    p = ROOT / "squeeze_candidates.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _add(row.get("ticker", ""), "squeeze", {
                    "score": row.get("squeeze_score", row.get("score", "")),
                    "short_pct": row.get("short_float_pct", row.get("short_pct", "")),
                    "stage": row.get("stage", ""),
                })

    # Insider clusters
    p = ROOT / "insider_clusters.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _add(row.get("ticker", ""), "insider", {
                    "buy_count": row.get("buy_count", row.get("cluster_size", "")),
                    "total_value": row.get("total_value", ""),
                })

    # Dark pool
    p = ROOT / "dark_pool.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("dark_pool_flag") == "True":
                    _add(row.get("ticker", ""), "darkpool", {
                        "vol_ratio": row.get("vol_ratio", ""),
                    })

    # Deep value
    p = ROOT / "deepvalue_screen.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _add(row.get("ticker", ""), "deepvalue", {
                    "score": row.get("deepvalue_score", ""),
                    "grade": row.get("grade", ""),
                    "pb_ratio": row.get("pb_ratio", ""),
                })

    # Convergence alerts
    p = ROOT / "convergence_alerts.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _add(row.get("ticker", ""), "convergence", {
                    "score": row.get("score", ""),
                    "conviction": row.get("conviction", ""),
                })

    # Smart money
    p = ROOT / "smart_money.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _add(row.get("ticker", ""), "smart_money", {
                    "fund_count": row.get("fund_count", ""),
                })

    # Merger signals
    p = ROOT / "merger_signals.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _add(row.get("ticker", ""), "merger", {
                    "signal_type": row.get("signal_type", ""),
                })

    result = sorted(signals.values(), key=lambda x: -x["signal_count"])
    return {"tickers": result[:200], "total": len(result)}


# ── REST: Stock of the Day ──────────────────────────────────────────────────
@app.get("/api/stock-of-the-day")
async def get_stock_of_the_day():
    """Return the #1 ranked pick with all available signal data aggregated."""
    # Get #1 from combined_priority
    top = None
    p = ROOT / "combined_priority.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                top = row
                break
    if not top:
        return {"pick": None}

    ticker = top.get("ticker", "").upper().strip()
    pick: dict = {
        "ticker": ticker,
        "total_score": top.get("total_score", "0"),
        "sec_score": top.get("sec_score", "0"),
        "news_score": top.get("news_score", "0"),
        "gapper_score": top.get("gapper_score", "0"),
        "value_score": top.get("value_score", "0"),
        "moat_score": top.get("moat_score", "0"),
        "sector_tags": top.get("sector_tags", ""),
        "event_tags": top.get("event_tags", ""),
        "signals": [],
    }

    # Cross-reference other CSVs
    def _check_csv(filename: str, ticker_field: str, signal_name: str, extract_fields: list[str]) -> None:
        fp = ROOT / filename
        if not fp.exists():
            return
        with open(fp, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get(ticker_field, "").upper().strip() == ticker:
                    pick["signals"].append(signal_name)
                    for field in extract_fields:
                        pick[f"{signal_name}_{field}"] = row.get(field, "")
                    break

    _check_csv("squeeze_candidates.csv", "ticker", "squeeze", ["squeeze_score", "short_float_pct", "stage"])
    _check_csv("insider_clusters.csv", "ticker", "insider", ["buy_count", "total_value", "cluster_size"])
    _check_csv("dark_pool.csv", "ticker", "darkpool", ["vol_ratio", "dark_pool_flag"])
    _check_csv("deepvalue_screen.csv", "ticker", "deepvalue", ["deepvalue_score", "grade", "pb_ratio", "pe_ratio", "roe_pct"])
    _check_csv("convergence_alerts.csv", "ticker", "convergence", ["score", "conviction", "signal_count"])
    _check_csv("smart_money.csv", "ticker", "smart_money", ["fund_count"])
    _check_csv("merger_signals.csv", "ticker", "merger", ["signal_type", "deal_value"])

    # Get SEC filing info
    fp = ROOT / "sec_catalyst_ranked.csv"
    if fp.exists():
        with open(fp, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    pick["sec_form"] = row.get("form", "")
                    pick["sec_link"] = row.get("link", "")
                    pick["sec_updated"] = row.get("updated_utc", "")
                    break

    # Get runner-ups (#2-#5)
    runners = []
    p2 = ROOT / "combined_priority.csv"
    if p2.exists():
        with open(p2, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i == 0:
                    continue  # skip #1
                if i > 4:
                    break
                runners.append({
                    "rank": i + 1,
                    "ticker": row.get("ticker", ""),
                    "total_score": row.get("total_score", "0"),
                    "sector_tags": row.get("sector_tags", ""),
                })

    pick["signal_count"] = len(pick["signals"])
    return {"pick": pick, "runners_up": runners, "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")}


# ── REST: Sector Heatmap ────────────────────────────────────────────────────
_SECTOR_DISPLAY = {
    "tech": "Technology",
    "technology": "Technology",
    "semis": "Semiconductors",
    "semiconductors": "Semiconductors",
    "financials": "Financials",
    "financial": "Financials",
    "healthcare": "Healthcare",
    "health care": "Healthcare",
    "biotech": "Biotech & Pharma",
    "energy": "Energy",
    "materials": "Materials",
    "industrials": "Industrials",
    "utilities": "Utilities",
    "staples": "Consumer Staples",
    "consumer staples": "Consumer Staples",
    "consumer": "Consumer Discretionary",
    "discretionary": "Consumer Discretionary",
    "consumer discretionary": "Consumer Discretionary",
    "comms": "Communication Services",
    "communications": "Communication Services",
    "communication services": "Communication Services",
    "real estate": "Real Estate",
    "real_estate": "Real Estate",
    "reit": "Real Estate",
}


def _pretty_sector(raw: str) -> str:
    key = (raw or "").strip().lower()
    if not key or key in _INVALID_LIVE_SECTORS:
        return "Unclassified"
    return _SECTOR_DISPLAY.get(key, key.title())


def _resolve_ticker_sector(ticker: str, tags: str) -> str:
    """Resolve a sector label for a ticker, preferring in-file tags then entity_master."""
    tag = ""
    if tags:
        for candidate in tags.split(";"):
            candidate = candidate.strip()
            if candidate and candidate.lower() not in _INVALID_LIVE_SECTORS:
                tag = candidate
                break
    if tag:
        return _pretty_sector(tag)

    t = (ticker or "").upper().strip()
    if not t:
        return "Unclassified"
    em_sector = _em_sector_for_parent(t)
    if em_sector:
        return _pretty_sector(em_sector)
    deriv = _resolve_live_derivative_sector(t)
    if deriv:
        return _pretty_sector(deriv[0])
    return "Unclassified"


@app.get("/api/sector-heatmap")
async def get_sector_heatmap():
    """Aggregate picks by sector and return sector-level statistics.

    Sector resolution chain: combined_priority.sector_tags → entity_master.gics →
    derivative parent lookup → Unclassified. This ensures SEC-driven picks without
    news coverage still receive a proper GICS sector instead of being dumped into
    an opaque Unknown bucket.
    """
    sectors: dict[str, dict] = {}
    p = ROOT / "combined_priority.csv"
    if not p.exists():
        return {"sectors": [], "total_picks": 0, "classified_picks": 0}

    total = 0
    classified = 0
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            total += 1
            ticker = (row.get("ticker", "") or "").upper().strip()
            score = float(row.get("total_score", "0") or "0")
            sector = _resolve_ticker_sector(ticker, row.get("sector_tags", ""))
            if sector != "Unclassified":
                classified += 1

            bucket = sectors.setdefault(
                sector,
                {
                    "sector": sector,
                    "count": 0,
                    "total_score": 0.0,
                    "top_ticker": "",
                    "top_score": 0.0,
                    "tickers": [],
                },
            )
            bucket["count"] += 1
            bucket["total_score"] += score
            bucket["tickers"].append(ticker)
            if score > bucket["top_score"]:
                bucket["top_score"] = score
                bucket["top_ticker"] = ticker

    result = []
    max_total = max((s["total_score"] for s in sectors.values()), default=1.0) or 1.0
    for s in sectors.values():
        s["avg_score"] = round(s["total_score"] / max(s["count"], 1), 1)
        s["top_score"] = round(s["top_score"], 1)
        s["total_score"] = round(s["total_score"], 1)
        s["heat_pct"] = round(min(1.0, s["total_score"] / max_total), 3)
        s["tickers"] = s["tickers"][:8]
        result.append(s)

    result.sort(key=lambda x: -x["total_score"])
    return {
        "sectors": result,
        "total_picks": total,
        "classified_picks": classified,
    }


# ── REST: Filings Feed (recent SEC filings timeline) ────────────────────────
@app.get("/api/filings-feed")
async def get_filings_feed(limit: int = Query(100, ge=1, le=500)):
    """Return recent SEC filings from sec_catalyst_ranked.csv as a timeline feed."""
    p = ROOT / "sec_catalyst_ranked.csv"
    if not p.exists():
        return {"filings": [], "total": 0}
    filings = []
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            filings.append({
                "ticker": row.get("ticker", ""),
                "form": row.get("form", ""),
                "updated": row.get("updated_utc", ""),
                "priority_score": row.get("priority_score", ""),
                "momentum_score": row.get("momentum_score", ""),
                "quality_score": row.get("quality_score", ""),
                "recency_min": row.get("recency_min", ""),
                "link": row.get("link", ""),
            })
    # Sort by recency (lowest recency_min first = most recent)
    filings.sort(key=lambda x: float(x.get("recency_min") or "999999"))
    return {"filings": filings[:limit], "total": len(filings)}


# ── REST: Hot Streaks (repeat performers across days) ───────────────────────
@app.get("/api/hot-streaks")
async def get_hot_streaks():
    """Find tickers appearing in multiple daily scans — repeat catalyst performers."""
    import glob as _glob
    ticker_days: dict[str, list[dict]] = {}  # ticker -> [{date, score}]

    pattern = str(ROOT / "combined_priority_*.csv")
    files = sorted(_glob.glob(pattern))[-14:]  # last 14 days max

    for fp in files:
        fname = Path(fp).stem
        date_part = fname.replace("combined_priority_", "")
        if len(date_part) != 10:
            continue
        with open(fp, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("ticker", "").upper().strip()
                if not t:
                    continue
                s = float(row.get("total_score", "0") or "0")
                if t not in ticker_days:
                    ticker_days[t] = []
                ticker_days[t].append({"date": date_part, "score": round(s, 1)})

    # Also include today's live file
    live = ROOT / "combined_priority.csv"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if live.exists():
        with open(live, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("ticker", "").upper().strip()
                if not t:
                    continue
                s = float(row.get("total_score", "0") or "0")
                if t not in ticker_days:
                    ticker_days[t] = []
                if not any(d["date"] == today_str for d in ticker_days[t]):
                    ticker_days[t].append({"date": today_str, "score": round(s, 1)})

    # Filter to tickers appearing 2+ times
    streaks = []
    for ticker, appearances in ticker_days.items():
        if len(appearances) >= 2:
            appearances.sort(key=lambda x: x["date"], reverse=True)
            avg_score = round(sum(a["score"] for a in appearances) / len(appearances), 1)
            max_score = max(a["score"] for a in appearances)
            streaks.append({
                "ticker": ticker,
                "appearances": len(appearances),
                "avg_score": avg_score,
                "max_score": round(max_score, 1),
                "dates": [a["date"] for a in appearances],
                "scores": [a["score"] for a in appearances],
                "streak_score": round(len(appearances) * avg_score, 1),
            })

    streaks.sort(key=lambda x: -x["streak_score"])
    return {"streaks": streaks[:100], "total": len(streaks), "days_analyzed": len(files) + (1 if live.exists() else 0)}


# ── REST: Catalyst Calendar (historical daily snapshots) ────────────────────
@app.get("/api/calendar")
async def get_catalyst_calendar():
    """Return daily pick counts and top tickers from historical combined_priority files."""
    import glob as _glob
    days: list[dict] = []
    pattern = str(ROOT / "combined_priority_*.csv")
    for fp in sorted(_glob.glob(pattern)):
        fname = Path(fp).stem  # combined_priority_2026-04-13
        date_part = fname.replace("combined_priority_", "")
        if len(date_part) != 10:
            continue
        count = 0
        top_tickers: list[str] = []
        max_score = 0.0
        total_score = 0.0
        with open(fp, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                count += 1
                s = float(row.get("total_score", "0") or "0")
                total_score += s
                if count <= 3:
                    top_tickers.append(row.get("ticker", ""))
                if s > max_score:
                    max_score = s
        days.append({
            "date": date_part,
            "pick_count": count,
            "top_tickers": top_tickers,
            "top_score": round(max_score, 1),
            "avg_score": round(total_score / max(count, 1), 1),
        })
    # Also include today's live file
    live = ROOT / "combined_priority.csv"
    if live.exists():
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not any(d["date"] == today_str for d in days):
            count = 0
            top_tickers = []
            max_score = 0.0
            total_score = 0.0
            with open(live, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    count += 1
                    s = float(row.get("total_score", "0") or "0")
                    total_score += s
                    if count <= 3:
                        top_tickers.append(row.get("ticker", ""))
                    if s > max_score:
                        max_score = s
            days.append({
                "date": today_str,
                "pick_count": count,
                "top_tickers": top_tickers,
                "top_score": round(max_score, 1),
                "avg_score": round(total_score / max(count, 1), 1),
            })
    days.sort(key=lambda x: x["date"], reverse=True)
    return {"days": days[:30], "total_days": len(days)}


# ── REST: Signal Strength Meter ──────────────────────────────────────────────
@app.get("/api/signal-strength")
async def get_signal_strength():
    """Aggregate today's signal counts across all sources into a single meter."""
    sources = {
        "rankings": {"file": "combined_priority.csv", "label": "Ranked Picks"},
        "squeeze": {"file": "squeeze_candidates.csv", "label": "Squeeze Candidates"},
        "insider": {"file": "insider_clusters.csv", "label": "Insider Clusters"},
        "darkpool": {"file": "dark_pool.csv", "label": "Dark Pool Flags"},
        "deepvalue": {"file": "deepvalue_screen.csv", "label": "Deep Value Stocks"},
        "convergence": {"file": "convergence_alerts.csv", "label": "Convergence Alerts"},
        "smart_money": {"file": "smart_money.csv", "label": "Smart Money Signals"},
        "merger": {"file": "merger_signals.csv", "label": "Merger Signals"},
        "gappers": {"file": "sec_top_gappers.csv", "label": "Gap Plays"},
        "sec_filings": {"file": "sec_catalyst_ranked.csv", "label": "SEC Filings"},
        "news": {"file": "bloomberg_headlines.csv", "label": "News Headlines"},
    }
    result = []
    total_signals = 0
    total_tickers = set()
    for key, info in sources.items():
        fp = ROOT / info["file"]
        count = 0
        tickers: set[str] = set()
        if fp.exists():
            with open(fp, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    count += 1
                    t = row.get("ticker", "").upper().strip()
                    if t:
                        tickers.add(t)
                        total_tickers.add(t)
        result.append({
            "source": key,
            "label": info["label"],
            "count": count,
            "unique_tickers": len(tickers),
        })
        total_signals += count

    # Calculate overall "temperature"
    # 0-50 signals = COLD, 50-200 = WARM, 200-500 = HOT, 500+ = EXTREME
    if total_signals >= 500:
        temp = "EXTREME"
        temp_pct = 100
    elif total_signals >= 200:
        temp = "HOT"
        temp_pct = 75
    elif total_signals >= 50:
        temp = "WARM"
        temp_pct = 50
    else:
        temp = "COLD"
        temp_pct = 25

    return {
        "sources": result,
        "total_signals": total_signals,
        "unique_tickers": len(total_tickers),
        "temperature": temp,
        "temperature_pct": temp_pct,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


# ── REST: Winners Leaderboard ─────────────────────────────────────────────
@app.get("/api/winners")
async def get_winners():
    """All-time leaderboard across historical daily scans — most consistent high-scorers."""
    import glob as _glob
    ticker_history: dict[str, list[dict]] = {}

    pattern = str(ROOT / "combined_priority_*.csv")
    files = sorted(_glob.glob(pattern))

    for fp in files:
        fname = Path(fp).stem
        date_part = fname.replace("combined_priority_", "")
        if len(date_part) != 10:
            continue
        with open(fp, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                t = row.get("ticker", "").upper().strip()
                if not t:
                    continue
                s = float(row.get("total_score", "0") or "0")
                if t not in ticker_history:
                    ticker_history[t] = []
                ticker_history[t].append({"date": date_part, "score": round(s, 1), "rank": i + 1})

    live = ROOT / "combined_priority.csv"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if live.exists():
        with open(live, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                t = row.get("ticker", "").upper().strip()
                if not t:
                    continue
                s = float(row.get("total_score", "0") or "0")
                if t not in ticker_history:
                    ticker_history[t] = []
                if not any(d["date"] == today_str for d in ticker_history[t]):
                    ticker_history[t].append({"date": today_str, "score": round(s, 1), "rank": i + 1})

    winners = []
    for ticker, entries in ticker_history.items():
        entries.sort(key=lambda x: x["date"], reverse=True)
        scores = [e["score"] for e in entries]
        ranks = [e["rank"] for e in entries]
        best_rank = min(ranks)
        winners.append({
            "ticker": ticker,
            "appearances": len(entries),
            "avg_score": round(sum(scores) / len(scores), 1),
            "max_score": round(max(scores), 1),
            "best_rank": best_rank,
            "latest_score": entries[0]["score"],
            "latest_rank": entries[0]["rank"],
            "consistency": round(len(entries) / max(len(files) + 1, 1) * 100, 0),
            "dates": [e["date"] for e in entries[:10]],
        })

    winners.sort(key=lambda x: (-x["appearances"], -x["avg_score"]))
    return {"winners": winners[:100], "total": len(winners), "days_analyzed": len(files) + (1 if live.exists() else 0)}


# ── REST: Momentum Radar ──────────────────────────────────────────────────
@app.get("/api/momentum")
async def get_momentum():
    """Track tickers gaining or losing momentum — compare recent vs prior scores."""
    import glob as _glob
    ticker_scores: dict[str, list[dict]] = {}

    pattern = str(ROOT / "combined_priority_*.csv")
    files = sorted(_glob.glob(pattern))

    for fp in files:
        fname = Path(fp).stem
        date_part = fname.replace("combined_priority_", "")
        if len(date_part) != 10:
            continue
        with open(fp, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("ticker", "").upper().strip()
                if not t:
                    continue
                s = float(row.get("total_score", "0") or "0")
                if t not in ticker_scores:
                    ticker_scores[t] = []
                ticker_scores[t].append({"date": date_part, "score": round(s, 1)})

    live = ROOT / "combined_priority.csv"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if live.exists():
        with open(live, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("ticker", "").upper().strip()
                if not t:
                    continue
                s = float(row.get("total_score", "0") or "0")
                if t not in ticker_scores:
                    ticker_scores[t] = []
                if not any(d["date"] == today_str for d in ticker_scores[t]):
                    ticker_scores[t].append({"date": today_str, "score": round(s, 1)})

    movers = []
    for ticker, entries in ticker_scores.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda x: x["date"], reverse=True)
        recent = entries[0]["score"]
        prior_avg = round(sum(e["score"] for e in entries[1:]) / len(entries[1:]), 1)
        delta = round(recent - prior_avg, 1)
        pct_change = round((delta / max(prior_avg, 0.1)) * 100, 0)
        direction = "rising" if delta > 0 else "falling" if delta < 0 else "flat"

        movers.append({
            "ticker": ticker,
            "current_score": recent,
            "prior_avg": prior_avg,
            "delta": delta,
            "pct_change": pct_change,
            "direction": direction,
            "data_points": len(entries),
            "scores": [e["score"] for e in entries[:7]],
            "dates": [e["date"] for e in entries[:7]],
        })

    rising = sorted([m for m in movers if m["direction"] == "rising"], key=lambda x: -x["delta"])
    falling = sorted([m for m in movers if m["direction"] == "falling"], key=lambda x: x["delta"])

    return {
        "rising": rising[:30],
        "falling": falling[:30],
        "total_tracked": len(movers),
        "date": today_str,
    }


# ── REST: Daily Picks Archive ──────────────────────────────────────────────
@app.get("/api/archive")
async def get_archive():
    """Return daily top picks from each historical combined_priority file."""
    import glob as _glob
    days: list[dict] = []
    pattern = str(ROOT / "combined_priority_*.csv")

    for fp in sorted(_glob.glob(pattern), reverse=True):
        fname = Path(fp).stem
        date_part = fname.replace("combined_priority_", "")
        if len(date_part) != 10:
            continue
        picks: list[dict] = []
        with open(fp, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                if i >= 10:
                    break
                picks.append({
                    "rank": i + 1,
                    "ticker": row.get("ticker", "").upper().strip(),
                    "total_score": round(float(row.get("total_score", "0") or "0"), 1),
                    "sec_form": row.get("sec_form", ""),
                    "sector": row.get("sector_tags", row.get("sector", "")),
                })
        if picks:
            days.append({
                "date": date_part,
                "top_pick": picks[0]["ticker"] if picks else "",
                "top_score": picks[0]["total_score"] if picks else 0,
                "total_scanned": sum(1 for _ in open(fp)) - 1,
                "picks": picks,
            })

    # Include today's live file
    live = ROOT / "combined_priority.csv"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if live.exists() and not any(d["date"] == today_str for d in days):
        picks = []
        total = 0
        with open(live, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                total += 1
                if i < 10:
                    picks.append({
                        "rank": i + 1,
                        "ticker": row.get("ticker", "").upper().strip(),
                        "total_score": round(float(row.get("total_score", "0") or "0"), 1),
                        "sec_form": row.get("sec_form", ""),
                        "sector": row.get("sector_tags", row.get("sector", "")),
                    })
        if picks:
            days.insert(0, {
                "date": today_str,
                "top_pick": picks[0]["ticker"],
                "top_score": picks[0]["total_score"],
                "total_scanned": total,
                "picks": picks,
            })

    return {"days": days[:60], "total_days": len(days)}


# ── REST: Ticker Profile (public scanner) ───────────────────────────────────
@app.get("/api/profile/{symbol}")
async def get_ticker_profile(symbol: str):
    """Aggregate all CSV signal data for one ticker into a unified profile."""
    ticker = symbol.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")

    profile: dict = {"ticker": ticker, "found": False, "signals": []}

    # Combined priority (rankings)
    p = ROOT / "combined_priority.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                if row.get("ticker", "").upper().strip() == ticker:
                    profile["found"] = True
                    profile["rank"] = i + 1
                    profile["total_score"] = row.get("total_score", "")
                    profile["sec_score"] = row.get("sec_score", "")
                    profile["news_score"] = row.get("news_score", "")
                    profile["gapper_score"] = row.get("gapper_score", "")
                    profile["value_score"] = row.get("value_score", "")
                    profile["moat_score"] = row.get("moat_score", "")
                    profile["sector_tags"] = row.get("sector_tags", "")
                    profile["event_tags"] = row.get("event_tags", "")
                    profile["signals"].append("ranking")
                    break

    # SEC filings
    p = ROOT / "sec_catalyst_ranked.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    profile["found"] = True
                    profile["sec_form"] = row.get("form", "")
                    profile["sec_link"] = row.get("link", "")
                    profile["sec_updated"] = row.get("updated_utc", "")
                    profile["sec_priority"] = row.get("priority_score", "")
                    break

    # Gappers
    p = ROOT / "sec_top_gappers.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    profile["found"] = True
                    profile["gapper_detail_score"] = row.get("gapper_score", "")
                    profile["price"] = row.get("price", "")
                    profile["market_cap"] = row.get("market_cap", "")
                    profile["avg_vol"] = row.get("avg_vol_3m", "")
                    profile["tags"] = row.get("tags", "")
                    profile["risk_flags"] = row.get("risk_flags", "")
                    profile["signals"].append("gapper")
                    break

    # Squeeze
    p = ROOT / "squeeze_candidates.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    profile["found"] = True
                    profile["squeeze_score"] = row.get("squeeze_score", row.get("score", ""))
                    profile["short_float_pct"] = row.get("short_float_pct", "")
                    profile["squeeze_stage"] = row.get("stage", "")
                    profile["signals"].append("squeeze")
                    break

    # Insider clusters
    p = ROOT / "insider_clusters.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    profile["found"] = True
                    profile["insider_buy_count"] = row.get("buy_count", row.get("cluster_size", ""))
                    profile["insider_total_value"] = row.get("total_value", "")
                    profile["signals"].append("insider")
                    break

    # Deep value
    p = ROOT / "deepvalue_screen.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    profile["found"] = True
                    profile["deepvalue_score"] = row.get("deepvalue_score", "")
                    profile["deepvalue_grade"] = row.get("grade", "")
                    profile["pb_ratio"] = row.get("pb_ratio", "")
                    profile["pe_ratio"] = row.get("pe_ratio", "")
                    profile["roe_pct"] = row.get("roe_pct", "")
                    profile["signals"].append("deepvalue")
                    break

    # Dark pool
    p = ROOT / "dark_pool.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    if row.get("dark_pool_flag") == "True":
                        profile["found"] = True
                        profile["dp_vol_ratio"] = row.get("vol_ratio", "")
                        profile["signals"].append("darkpool")
                    break

    # Convergence
    p = ROOT / "convergence_alerts.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    profile["found"] = True
                    profile["convergence_score"] = row.get("convergence_score", row.get("score", ""))
                    profile["convergence_conviction"] = row.get("conviction_level", row.get("conviction", ""))
                    profile["signals"].append("convergence")
                    break

    # Smart money
    p = ROOT / "smart_money.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    profile["found"] = True
                    profile["smart_money_fund_count"] = row.get("fund_count", "")
                    profile["signals"].append("smart_money")
                    break

    # Merger
    p = ROOT / "merger_signals.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    profile["found"] = True
                    profile["merger_type"] = row.get("signal_type", "")
                    profile["merger_deal_value"] = row.get("deal_value", "")
                    profile["signals"].append("merger")
                    break

    # Performance history
    p = ROOT / "sec_outcome_rows.csv"
    if p.exists():
        perf_rows = []
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("ticker", "").upper().strip() == ticker:
                    perf_rows.append({
                        "date": row.get("session_date", ""),
                        "outcome": row.get("outcome", ""),
                        "open_gap_pct": row.get("open_gap_pct", ""),
                        "max_intraday_pct": row.get("max_intraday_pct", ""),
                    })
        if perf_rows:
            profile["found"] = True
            profile["performance_history"] = perf_rows[-5:]  # last 5

    profile["signal_count"] = len(profile["signals"])
    if not profile["found"]:
        raise HTTPException(status_code=404, detail=f"{ticker} not found in any signal source")
    return {"profile": profile}


# ── REST: Sympathy correlation matrix (F-5/A-11) ─────────────────────────────
@app.get("/api/sympathy-matrix")
async def get_sympathy_matrix():
    """Pre-computed sector-pair return correlations for HUD sympathy links."""
    data = await _read_json("sympathy_matrix")
    if not data:
        return {"correlation_matrix": {}, "sympathy_pairs": [], "method": "unavailable"}
    return data


# ── REST: Velocity Deck events ────────────────────────────────────────────────
@app.get("/api/spark")
async def get_sparks(limit: int = Query(50, ge=1, le=500)):
    sparks: dict = await _read_json("spark_velocities")
    em: dict     = await _read_json("entity_master")

    rows = []
    for ticker, entry in sparks.items():
        if str(ticker).upper() in _ENTITY_JUNK_KEYS:
            continue
        name = em.get(ticker, {}).get("name", "") if em else ""
        velocity_event = build_velocity_event(
            ticker,
            entry,
            name=name,
            wire_event="velocity_snapshot",
        )
        if not _should_surface_velocity_event(velocity_event):
            continue
        rows.append(velocity_event)

    rows.sort(key=_velocity_deck_sort_key)
    return {
        "contract_version": CONTRACT_VERSION,
        "velocity_deck_schema_version": VELOCITY_DECK_SCHEMA_VERSION,
        "events": rows[:limit],
        "sparks": rows[:limit],
        "total": len(rows),
    }


# ── REST: Top brightness ──────────────────────────────────────────────────────
@app.get("/api/brightness/top")
async def get_top_brightness(
    limit:  int = Query(100, ge=1, le=1000),
    sector: Optional[str] = Query(None),
):
    em: dict     = await _read_json("entity_master")
    sparks: dict = await _read_json("spark_velocities")

    rows = []
    for ticker, rec in em.items():
        if rec.get("etf"):
            continue
        if sector:
            if _normalized_sector(rec, ticker) != sector:
                continue
        b = _brightness(rec, sparks, ticker)
        if b <= 0:
            continue
        gravity = _normalized_gravity(rec, ticker)
        rows.append({"ticker": ticker, "name": rec.get("name", ""),
                     "brightness": b, "gravity": gravity,
                     "sector": _normalized_sector(rec, ticker)})

    rows.sort(key=lambda r: -r["brightness"])
    return {"nodes": rows[:limit], "total": len(rows)}


# ── REST: AI Intelligence Layer ───────────────────────────────────────────────
# Two endpoints:
#   GET /api/ai-summary/{ticker}  — 2-sentence tactical catalyst card (node clicks)
#   GET /api/briefing             — 4-sentence pre-market audio script (Phase 5)
#
# Both use Claude Haiku with strict military-grade system prompts.
# If ANTHROPIC_API_KEY is unset, both fall back to verified deterministic responses.

import os    as _os
import re    as _re
import datetime as _dt

try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

_ANTHROPIC_API_KEY = _os.environ.get("ANTHROPIC_API_KEY", "")
_OPENAI_API_KEY = (_os.environ.get("OPENAI_API_KEY", "") or "").strip()
_DEFAULT_FAST_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_OPENAI_FAST_MODEL = "gpt-5.4-mini"
_DEFAULT_OPENAI_SMART_MODEL = "gpt-5.4"


def _env_float(name: str, default: float) -> float:
    raw = (_os.environ.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        return max(0.1, float(raw))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = (_os.environ.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return default


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (_os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


_ANTHROPIC_MODEL_FAST = ((_os.environ.get("ANTHROPIC_MODEL_FAST", "") or "").strip() or _DEFAULT_FAST_MODEL)
_ANTHROPIC_MODEL_SMART = ((_os.environ.get("ANTHROPIC_MODEL_SMART", "") or "").strip() or _ANTHROPIC_MODEL_FAST)
_ANTHROPIC_FAST_TIMEOUT_SECONDS = _env_float("ANTHROPIC_FAST_TIMEOUT_SECONDS", 8.0)
_ANTHROPIC_SMART_TIMEOUT_SECONDS = _env_float("ANTHROPIC_SMART_TIMEOUT_SECONDS", 16.0)
_ANTHROPIC_SMART_RETRIES = _env_int("ANTHROPIC_SMART_RETRIES", 1)
_OPENAI_MODEL_FAST = ((_os.environ.get("OPENAI_MODEL_FAST", "") or "").strip() or _DEFAULT_OPENAI_FAST_MODEL)
_OPENAI_MODEL_SMART = ((_os.environ.get("OPENAI_MODEL_SMART", "") or "").strip() or _DEFAULT_OPENAI_SMART_MODEL)
_OPENAI_FAST_TIMEOUT_SECONDS = _env_float("OPENAI_FAST_TIMEOUT_SECONDS", 10.0)
_OPENAI_SMART_TIMEOUT_SECONDS = _env_float("OPENAI_SMART_TIMEOUT_SECONDS", 20.0)
_OPENAI_SMART_RETRIES = _env_int("OPENAI_SMART_RETRIES", 1)
_DEFAULT_OLLAMA_FAST_MODEL = "gemma2:2b"
_DEFAULT_OLLAMA_SMART_MODEL = "gemma2:2b"
_OLLAMA_ENABLED = _env_flag("OLLAMA_ENABLED", False)
_OLLAMA_BASE_URL = (((_os.environ.get("OLLAMA_BASE_URL", "") or "").strip().rstrip("/")) or "http://127.0.0.1:11434/v1")
_OLLAMA_API_KEY = ((_os.environ.get("OLLAMA_API_KEY", "") or "").strip() or "ollama-local")
_OLLAMA_MODEL_FAST = ((_os.environ.get("OLLAMA_MODEL_FAST", "") or "").strip() or _DEFAULT_OLLAMA_FAST_MODEL)
_OLLAMA_MODEL_SMART = ((_os.environ.get("OLLAMA_MODEL_SMART", "") or "").strip() or _DEFAULT_OLLAMA_SMART_MODEL)
_OLLAMA_FAST_TIMEOUT_SECONDS = _env_float("OLLAMA_FAST_TIMEOUT_SECONDS", 12.0)
_OLLAMA_SMART_TIMEOUT_SECONDS = _env_float("OLLAMA_SMART_TIMEOUT_SECONDS", 24.0)
_OLLAMA_SMART_RETRIES = _env_int("OLLAMA_SMART_RETRIES", 0)

# ── Gemini (Google AI Studio — free tier, OpenAI-compatible) ─────────────────
_GEMINI_API_KEY = ((_os.environ.get("GEMINI_API_KEY", "") or "").strip())
_GEMINI_ENABLED = _env_flag("GEMINI_ENABLED", bool(_GEMINI_API_KEY))
_GEMINI_BASE_URL = (
    ((_os.environ.get("GEMINI_BASE_URL", "") or "").strip().rstrip("/"))
    or "https://generativelanguage.googleapis.com/v1beta/openai"
)
_DEFAULT_GEMINI_FAST_MODEL = "gemini-2.0-flash"
_DEFAULT_GEMINI_SMART_MODEL = "gemini-2.0-flash"
_GEMINI_MODEL_FAST = ((_os.environ.get("GEMINI_MODEL_FAST", "") or "").strip() or _DEFAULT_GEMINI_FAST_MODEL)
_GEMINI_MODEL_SMART = ((_os.environ.get("GEMINI_MODEL_SMART", "") or "").strip() or _DEFAULT_GEMINI_SMART_MODEL)
_GEMINI_FAST_TIMEOUT_SECONDS = _env_float("GEMINI_FAST_TIMEOUT_SECONDS", 10.0)
_GEMINI_SMART_TIMEOUT_SECONDS = _env_float("GEMINI_SMART_TIMEOUT_SECONDS", 20.0)
_GEMINI_SMART_RETRIES = _env_int("GEMINI_SMART_RETRIES", 1)

# ── Groq (free tier, OpenAI-compatible, sub-second inference) ────────────────
_GROQ_API_KEY = ((_os.environ.get("GROQ_API_KEY", "") or "").strip())
_GROQ_ENABLED = _env_flag("GROQ_ENABLED", bool(_GROQ_API_KEY))
_GROQ_BASE_URL = (
    ((_os.environ.get("GROQ_BASE_URL", "") or "").strip().rstrip("/"))
    or "https://api.groq.com/openai/v1"
)
_DEFAULT_GROQ_FAST_MODEL = "llama-3.1-8b-instant"
_DEFAULT_GROQ_SMART_MODEL = "llama-3.1-8b-instant"
_GROQ_MODEL_FAST = ((_os.environ.get("GROQ_MODEL_FAST", "") or "").strip() or _DEFAULT_GROQ_FAST_MODEL)
_GROQ_MODEL_SMART = ((_os.environ.get("GROQ_MODEL_SMART", "") or "").strip() or _DEFAULT_GROQ_SMART_MODEL)
_GROQ_FAST_TIMEOUT_SECONDS = _env_float("GROQ_FAST_TIMEOUT_SECONDS", 8.0)
_GROQ_SMART_TIMEOUT_SECONDS = _env_float("GROQ_SMART_TIMEOUT_SECONDS", 16.0)
_GROQ_SMART_RETRIES = _env_int("GROQ_SMART_RETRIES", 1)

_MODEL_PROVIDER_PRIORITY = [
    token.strip().lower()
    for token in ((_os.environ.get("CEREBRO_AI_PROVIDER_PRIORITY", "") or "").split(",") or ["anthropic", "openai", "ollama"])
    if token.strip()
]
if not _MODEL_PROVIDER_PRIORITY:
    _MODEL_PROVIDER_PRIORITY = ["groq", "gemini", "anthropic", "openai", "ollama"]


def _provider_iteration_order() -> list[str]:
    ordered: list[str] = []
    for provider in list(_MODEL_PROVIDER_PRIORITY) + ["groq", "gemini", "anthropic", "openai", "ollama"]:
        normalized = str(provider or "").strip().lower()
        if not normalized or normalized in ordered:
            continue
        ordered.append(normalized)
    return ordered or ["groq", "gemini", "anthropic", "openai", "ollama"]


def _provider_model_spec(provider: str, tier: str) -> dict:
    provider = str(provider or "").strip().lower()
    tier = str(tier or "fast").strip().lower() or "fast"
    if provider == "anthropic":
        return {
            "provider": "anthropic",
            "model": _ANTHROPIC_MODEL_SMART if tier == "smart" else _ANTHROPIC_MODEL_FAST,
            "timeout_seconds": _ANTHROPIC_SMART_TIMEOUT_SECONDS if tier == "smart" else _ANTHROPIC_FAST_TIMEOUT_SECONDS,
            "retries": _ANTHROPIC_SMART_RETRIES if tier == "smart" else 0,
        }
    if provider == "openai":
        return {
            "provider": "openai",
            "model": _OPENAI_MODEL_SMART if tier == "smart" else _OPENAI_MODEL_FAST,
            "timeout_seconds": _OPENAI_SMART_TIMEOUT_SECONDS if tier == "smart" else _OPENAI_FAST_TIMEOUT_SECONDS,
            "retries": _OPENAI_SMART_RETRIES if tier == "smart" else 0,
        }
    if provider == "ollama":
        return {
            "provider": "ollama",
            "model": _OLLAMA_MODEL_SMART if tier == "smart" else _OLLAMA_MODEL_FAST,
            "timeout_seconds": _OLLAMA_SMART_TIMEOUT_SECONDS if tier == "smart" else _OLLAMA_FAST_TIMEOUT_SECONDS,
            "retries": _OLLAMA_SMART_RETRIES if tier == "smart" else 0,
        }
    if provider == "gemini":
        return {
            "provider": "gemini",
            "model": _GEMINI_MODEL_SMART if tier == "smart" else _GEMINI_MODEL_FAST,
            "timeout_seconds": _GEMINI_SMART_TIMEOUT_SECONDS if tier == "smart" else _GEMINI_FAST_TIMEOUT_SECONDS,
            "retries": _GEMINI_SMART_RETRIES if tier == "smart" else 0,
        }
    if provider == "groq":
        return {
            "provider": "groq",
            "model": _GROQ_MODEL_SMART if tier == "smart" else _GROQ_MODEL_FAST,
            "timeout_seconds": _GROQ_SMART_TIMEOUT_SECONDS if tier == "smart" else _GROQ_FAST_TIMEOUT_SECONDS,
            "retries": _GROQ_SMART_RETRIES if tier == "smart" else 0,
        }
    return {}


def _provider_available(provider: str) -> bool:
    provider = str(provider or "").strip().lower()
    if provider == "anthropic":
        return bool(_ANTHROPIC_AVAILABLE and _ANTHROPIC_API_KEY)
    if provider == "openai":
        return bool(_OPENAI_API_KEY)
    if provider == "ollama":
        return bool(_OLLAMA_ENABLED and _OLLAMA_BASE_URL and (_OLLAMA_MODEL_FAST or _OLLAMA_MODEL_SMART))
    if provider == "gemini":
        return bool(_GEMINI_ENABLED and _GEMINI_API_KEY)
    if provider == "groq":
        return bool(_GROQ_ENABLED and _GROQ_API_KEY)
    return False


def _resolve_model_spec(tier: str) -> dict:
    tier = str(tier or "fast").strip().lower() or "fast"
    for provider in _provider_iteration_order():
        if _provider_available(provider):
            return _provider_model_spec(provider, tier)
    fallback_provider = (_provider_iteration_order()[0] if _provider_iteration_order() else "anthropic").lower()
    return _provider_model_spec(fallback_provider, tier)


def _model_display_name(model_name: str) -> str:
    slug = (model_name or "").strip().replace("_", "-")
    if not slug:
        return "Fallback path"
    if slug.startswith("gpt-"):
        parts = [part for part in slug.split("-") if part]
        family = "GPT"
        version = ""
        if len(parts) >= 2:
            version = parts[1]
        suffix = " ".join(part.capitalize() for part in parts[2:] if part and not part.isdigit())
        label = f"{family} {version}".strip()
        if suffix:
            label = f"{label} {suffix}".strip()
        return label
    if slug.lower().startswith("gemini"):
        label = slug.replace("-", " ").replace(".", " ").strip()
        return " ".join(part.capitalize() for part in label.split())
    if slug.lower().startswith("llama"):
        label = slug.replace("-", " ").replace(".", " ").strip()
        return " ".join(part.capitalize() for part in label.split())
    for family_name in ("qwen", "gemma", "mistral"):
        if slug.lower().startswith(family_name):
            label = slug.replace(":", " ").replace("-", " ").strip()
            return " ".join(part.capitalize() for part in label.split())
    if slug.startswith("claude-"):
        slug = slug[len("claude-") :]
    parts = [part for part in slug.split("-") if part]
    if not parts:
        return model_name
    family = parts[0].capitalize()
    version_bits: list[str] = []
    for part in parts[1:]:
        if part.isdigit() and len(part) <= 2 and len(version_bits) < 2:
            version_bits.append(part)
            continue
        break
    version = ".".join(version_bits)
    return f"Claude {family}{f' {version}' if version else ''}"


def _build_model_metadata(
    provider: str,
    model_name: str,
    tier: str,
    *,
    is_fallback: bool,
    fallback_reason: str = "",
    timeout_seconds: float | None = None,
    attempts: int = 0,
    provider_switch: str = "",
    upstream_error: str = "",
) -> dict:
    return {
        "provider": provider or "",
        "model": model_name or "",
        "display_name": _model_display_name(model_name),
        "tier": tier,
        "is_fallback": is_fallback,
        "fallback_reason": fallback_reason or "",
        "timeout_seconds": timeout_seconds,
        "attempts": attempts,
        "provider_switch": provider_switch or "",
        "upstream_error": upstream_error or "",
    }


def _update_health_status(path: str, value: str) -> None:
    normalized = str(path or "").strip().lower()
    text = str(value or "")
    if normalized in {"openai.last_error", "model_runtime.last_errors.openai"}:
        _MODEL_RUNTIME_LAST_ERROR["openai"] = text
    elif normalized in {"anthropic.last_error", "model_runtime.last_errors.anthropic"}:
        _MODEL_RUNTIME_LAST_ERROR["anthropic"] = text
    elif normalized in {"ollama.last_error", "model_runtime.last_errors.ollama"}:
        _MODEL_RUNTIME_LAST_ERROR["ollama"] = text
    elif normalized in {"gemini.last_error", "model_runtime.last_errors.gemini"}:
        _MODEL_RUNTIME_LAST_ERROR["gemini"] = text
    elif normalized in {"groq.last_error", "model_runtime.last_errors.groq"}:
        _MODEL_RUNTIME_LAST_ERROR["groq"] = text
    elif normalized.startswith("model_runtime.provider_switch."):
        tier = normalized.rsplit(".", 1)[-1]
        if tier in _MODEL_RUNTIME_LAST_SWITCH:
            _MODEL_RUNTIME_LAST_SWITCH[tier] = text


def _describe_model_exception(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        detail = ""
        try:
            raw_body = exc.read().decode("utf-8", errors="ignore")
            if raw_body:
                try:
                    payload = json.loads(raw_body)
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    err = payload.get("error")
                    if isinstance(err, dict):
                        pieces = [
                            str(err.get("type") or "").strip(),
                            str(err.get("code") or "").strip(),
                            str(err.get("message") or "").strip(),
                        ]
                        detail = " | ".join(piece for piece in pieces if piece)
                    elif err:
                        detail = str(err).strip()
                if not detail:
                    detail = raw_body[:240].strip()
        except Exception:
            detail = ""
        reason = str(getattr(exc, "reason", "") or "").strip()
        base = f"HTTP {exc.code}"
        if reason:
            base = f"{base} {reason}"
        return f"{base}: {detail}" if detail else base
    if isinstance(exc, URLError):
        return f"URLError: {getattr(exc, 'reason', exc)}"
    return f"{type(exc).__name__}: {exc}"


def _should_attempt_provider_fallback(provider: str, error_text: str) -> bool:
    lower = str(error_text or "").strip().lower()
    if not lower:
        return False
    fallback_markers = (
        "api_key_missing",
        "provider_unconfigured",
        "model_unconfigured",
        "package_unavailable",
        "timeout",
        "timed out",
        "connection refused",
        "connection reset",
        "remote disconnected",
        "service unavailable",
        "too many requests",
        "rate limit",
        "insufficient_quota",
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "empty_response",
    )
    return any(marker in lower for marker in fallback_markers)


def _provider_fallback_specs(primary_provider: str, tier: str) -> list[dict]:
    primary = str(primary_provider or "").strip().lower()
    specs: list[dict] = []
    seen = {primary}
    for provider in _provider_iteration_order():
        if provider in seen:
            continue
        seen.add(provider)
        if not _provider_available(provider):
            continue
        spec = _provider_model_spec(provider, tier)
        if spec:
            specs.append(spec)
    return specs


def _compact_local_model_text(text: str, max_chars: int) -> str:
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 16].rstrip() + " [truncated]"


def _local_model_request(provider: str, tier: str, system: str, user: str, max_tokens: int) -> tuple[str, str, int]:
    if str(provider or "").strip().lower() != "ollama":
        return system, user, max_tokens
    normalized_tier = str(tier or "").strip().lower()
    compact_system = (
        "Write exactly two short factual sentences: first the catalyst, then the likely sector or market impact. No advice."
        if normalized_tier == "fast"
        else "Write exactly four short tactical sentences. Start with 'Good morning. All systems nominal.' Mention the main velocity event, one sector, and one risk."
    )
    compact_user = _compact_local_model_text(user, 700 if normalized_tier == "fast" else 2200)
    compact_tokens = min(max_tokens, 64 if normalized_tier == "fast" else 140)
    return compact_system, compact_user, compact_tokens

# ── Haiku system prompts ──────────────────────────────────────────────────────

_SYSTEM_INTELLIGENCE_CARD = (
    "You are the onboard AI for Cerebro, a real-time predictive attention engine "
    "and economic radar. The user is a professional data analyst monitoring market velocity. "
    "You will be provided with a raw financial filing, patent approval, or news event. "
    "Your absolute directive is to summarize the core catalyst in exactly two sentences. "
    "Sentence 1: Identify the exact physical, legal, or financial catalyst (What just happened). "
    "Sentence 2: Identify the structural or sector impact (Why the velocity is shifting). "
    "STRICT CONSTRAINTS: "
    "Do NOT use introductory filler (e.g., 'This document states...'). "
    "Do NOT provide financial advice. "
    "Do NOT use exclamation points. "
    "Output strictly the two sentences and nothing else."
)

_SYSTEM_BRIEFING = (
    "You are Cerebro, an autonomous economic mapping engine. "
    "You are providing a pre-market audio briefing for the system operator. "
    "You will be provided with a list of overnight market anomalies, rogue node activities, "
    "and sector shifts. Synthesize this data into a smooth, 4-sentence audio script. "
    "STRICT CONSTRAINTS: "
    "Tone: Calm, objective, tactical, and precise. Like an air traffic controller or JARVIS. "
    "Open with exactly: 'Good morning. All systems nominal.' "
    "Clearly state the most severe velocity spark from the overnight data. "
    "Identify one sector that is actively absorbing capital. "
    "Do NOT use bullet points, special characters, or complex numbers that sound unnatural "
    "when spoken out loud (e.g., say 'two point five billion' instead of '$2,543,100,000')."
)

# ── Filing cache helpers ──────────────────────────────────────────────────────

_FILING_CACHE_PATH = ROOT / ".sec_filing_text_cache.json"
_FILING_CACHE:   dict | None = None
_FILING_CACHE_TS: float      = 0.0
_CACHE_TTL = 300

_FORM_RE = _re.compile(r'\btype:\s*(8-K|10-K|10-Q|S-1|S-3|424B\d|DEF\s*14A)\b', _re.I)
_DATE_RE = _re.compile(r'filing date\s+(\d{4}-\d{2}-\d{2})', _re.I)


def _cache_entry_ts(entry: dict) -> float:
    """Return a comparable timestamp for a cached filing entry."""
    if not isinstance(entry, dict):
        return 0.0
    ts_raw = entry.get("ts")
    if isinstance(ts_raw, (int, float)):
        return float(ts_raw)
    if not ts_raw:
        return 0.0
    try:
        return _dt.datetime.fromisoformat(str(ts_raw)).timestamp()
    except Exception:
        return 0.0

# Keyword → catalyst type (used to classify Haiku's free-text response)
_CATALYST_KEYWORDS: dict[str, list[str]] = {
    "REVENUE_BEAT":   ["revenue", "beat", "earnings", "exceed", "profit", "surpass"],
    "PRODUCT_LAUNCH": ["launch", "product", "release", "unveil", "introduc", "commercializ"],
    "ACQUISITION":    ["acqui", "merger", "purchase", "takeover"],
    "LEGAL_RISK":     ["lawsuit", "litigation", "court", "settlement", "sue"],
    "DILUTION_RISK":  ["dilut", "offering", "shares", "raise capital"],
    "INSIDER_BUY":    ["insider", "director", "officer", "10b5"],
    "GUIDANCE_RAISE": ["guidance", "raise", "upgrad", "outlook"],
    "GUIDANCE_CUT":   ["guidance cut", "lower", "miss", "disappoint", "withdraw"],
    "PARTNERSHIP":    ["partner", "collaborat", "joint venture", "agreement"],
    "REGULATORY":     ["fda", "approval", "clearance", "patent", "regulatory"],
}

def _classify_catalyst(text: str) -> str:
    lower = text.lower()
    for cat, keywords in _CATALYST_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return cat
    return "UNKNOWN"


def _load_filing_cache() -> dict:
    global _FILING_CACHE, _FILING_CACHE_TS
    now = time.time()
    if _FILING_CACHE is not None and now - _FILING_CACHE_TS < _CACHE_TTL:
        return _FILING_CACHE
    try:
        _FILING_CACHE    = json.loads(_FILING_CACHE_PATH.read_text(encoding="utf-8"))
        _FILING_CACHE_TS = now
    except Exception:
        _FILING_CACHE = {}
    return _FILING_CACHE


def _latest_filing_for_ticker(ticker: str) -> tuple[str, str, str]:
    """Return (form_type, filing_date, filing_text[:6000]) for ticker's most recent cached filing."""
    try:
        em: dict = json.loads((ROOT / "entity_master.json").read_text(encoding="utf-8"))
        rec      = em.get(ticker.upper(), {})
        cik_raw  = rec.get("cik", "")
        if not cik_raw:
            return "", "", ""
        cik = str(cik_raw).lstrip("0")
        cache = _load_filing_cache()
        best_entry: dict | None = None
        best_ts = 0.0
        for url, entry in cache.items():
            if f"/edgar/data/{cik}/" not in url or not isinstance(entry, dict):
                continue
            text = entry.get("text", "")
            if not text:
                continue
            ts_val = _cache_entry_ts(entry)
            if best_entry is None or ts_val >= best_ts:
                best_entry = entry
                best_ts = ts_val
        if not best_entry:
            return "", "", ""
        text = best_entry.get("text", "")
        form_m = _FORM_RE.search(text)
        date_m = _DATE_RE.search(text)
        form = form_m.group(1).upper().replace(" ", "") if form_m else "UNKNOWN"
        date = date_m.group(1) if date_m else ""
        return form, date, text[:6000]
    except Exception:
        pass
    return "", "", ""


def _call_anthropic_model(model_name: str, system: str, user: str, max_tokens: int) -> str:
    """Call Anthropic synchronously and return plain text or raise."""
    if not _ANTHROPIC_AVAILABLE:
        raise RuntimeError("anthropic_package_unavailable")
    if not _ANTHROPIC_API_KEY:
        raise RuntimeError("anthropic_api_key_missing")
    client = _anthropic.Anthropic(api_key=_ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model_name,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    content = getattr(msg, "content", None) or []
    if not content:
        return ""
    return (getattr(content[0], "text", "") or "").strip()


def _call_openai_model(model_name: str, system: str, user: str, max_tokens: int) -> str:
    if not _OPENAI_API_KEY:
        raise RuntimeError("openai_api_key_missing")
    payload = {
        "model": model_name,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user}],
            },
        ],
        "max_output_tokens": max_tokens,
    }
    req = UrllibRequest(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=45) as response:
        body = response.read()
    raw = json.loads(body.decode("utf-8"))
    return _extract_openai_compatible_text(raw)


def _extract_openai_compatible_text(raw: dict) -> str:
    output_text = str(raw.get("output_text") or "").strip()
    if output_text:
        return output_text
    chunks: list[str] = []
    for item in raw.get("output") or []:
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = str(content.get("text") or content.get("output_text") or "").strip()
            if text:
                chunks.append(text)
    if chunks:
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    for choice in raw.get("choices") or []:
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            chunks.append(content.strip())
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = str(block.get("text") or "").strip()
                if text:
                    chunks.append(text)
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _call_groq_model(model_name: str, system: str, user: str, max_tokens: int) -> str:
    """Call Groq via its OpenAI-compatible endpoint."""
    if not _GROQ_ENABLED:
        raise RuntimeError("groq_disabled")
    if not _GROQ_API_KEY:
        raise RuntimeError("groq_api_key_missing")
    if not model_name:
        raise RuntimeError("model_unconfigured")
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    req = UrllibRequest(
        f"{_GROQ_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Cerebro/1.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=15) as response:
        body = response.read()
    raw = json.loads(body.decode("utf-8"))
    return _extract_openai_compatible_text(raw)


def _call_gemini_model(model_name: str, system: str, user: str, max_tokens: int) -> str:
    """Call Google Gemini via its OpenAI-compatible endpoint."""
    if not _GEMINI_ENABLED:
        raise RuntimeError("gemini_disabled")
    if not _GEMINI_API_KEY:
        raise RuntimeError("gemini_api_key_missing")
    if not model_name:
        raise RuntimeError("model_unconfigured")
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    req = UrllibRequest(
        f"{_GEMINI_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_GEMINI_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Cerebro/1.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=20) as response:
        body = response.read()
    raw = json.loads(body.decode("utf-8"))
    return _extract_openai_compatible_text(raw)


def _call_ollama_model(model_name: str, system: str, user: str, max_tokens: int) -> str:
    if not _OLLAMA_ENABLED:
        raise RuntimeError("ollama_disabled")
    if not _OLLAMA_BASE_URL:
        raise RuntimeError("ollama_base_url_missing")
    if not model_name:
        raise RuntimeError("model_unconfigured")
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "max_tokens": max_tokens,
    }
    req = UrllibRequest(
        f"{_OLLAMA_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_OLLAMA_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=45) as response:
        body = response.read()
    raw = json.loads(body.decode("utf-8"))
    return _extract_openai_compatible_text(raw)


async def _run_model_provider(
    *,
    provider: str,
    model_name: str,
    tier: str,
    system: str,
    user: str,
    max_tokens: int,
    timeout_seconds: float,
    retries: int = 0,
) -> tuple[str, dict, str]:
    provider = str(provider or "").strip().lower()
    if provider == "anthropic":
        provider_ready = bool(_ANTHROPIC_AVAILABLE and _ANTHROPIC_API_KEY and model_name)
        fallback_reason = (
            "anthropic_package_unavailable"
            if not _ANTHROPIC_AVAILABLE
            else "anthropic_api_key_missing"
            if not _ANTHROPIC_API_KEY
            else "model_unconfigured"
        )
        call_fn = _call_anthropic_model
    elif provider == "openai":
        provider_ready = bool(_OPENAI_API_KEY and model_name)
        fallback_reason = "openai_api_key_missing" if not _OPENAI_API_KEY else "model_unconfigured"
        call_fn = _call_openai_model
    elif provider == "groq":
        provider_ready = bool(_GROQ_ENABLED and _GROQ_API_KEY and model_name)
        fallback_reason = (
            "groq_disabled"
            if not _GROQ_ENABLED
            else "groq_api_key_missing"
            if not _GROQ_API_KEY
            else "model_unconfigured"
        )
        call_fn = _call_groq_model
    elif provider == "gemini":
        provider_ready = bool(_GEMINI_ENABLED and _GEMINI_API_KEY and model_name)
        fallback_reason = (
            "gemini_disabled"
            if not _GEMINI_ENABLED
            else "gemini_api_key_missing"
            if not _GEMINI_API_KEY
            else "model_unconfigured"
        )
        call_fn = _call_gemini_model
    elif provider == "ollama":
        provider_ready = bool(_OLLAMA_ENABLED and _OLLAMA_BASE_URL and model_name)
        fallback_reason = (
            "ollama_disabled"
            if not _OLLAMA_ENABLED
            else "ollama_base_url_missing"
            if not _OLLAMA_BASE_URL
            else "model_unconfigured"
        )
        call_fn = _call_ollama_model
    else:
        provider_ready = False
        fallback_reason = "provider_unconfigured"
        call_fn = _call_anthropic_model

    if not provider_ready:
        return "", _build_model_metadata(
            provider,
            model_name,
            tier,
            is_fallback=True,
            fallback_reason=fallback_reason,
            timeout_seconds=timeout_seconds,
            attempts=0,
        ), fallback_reason

    loop = asyncio.get_running_loop()
    attempts = 0
    last_error = ""
    request_system, request_user, request_max_tokens = _local_model_request(
        provider,
        tier,
        system,
        user,
        max_tokens,
    )

    for attempt_index in range(retries + 1):
        attempts = attempt_index + 1
        try:
            response_future = loop.run_in_executor(
                None,
                call_fn,
                model_name,
                request_system,
                request_user,
                request_max_tokens,
            )
            text = await asyncio.wait_for(response_future, timeout=timeout_seconds)
            if text:
                _update_health_status(f"model_runtime.last_errors.{provider}", "")
                return text, _build_model_metadata(
                    provider,
                    model_name,
                    tier,
                    is_fallback=False,
                    timeout_seconds=timeout_seconds,
                    attempts=attempts,
                ), ""
            last_error = "empty_response"
            print(f"  WARN {provider}/{tier} model ({model_name}): empty response", flush=True)
        except asyncio.TimeoutError:
            last_error = "timeout"
            print(f"  WARN {provider}/{tier} model ({model_name}): timed out after {timeout_seconds:.1f}s", flush=True)
        except Exception as exc:
            last_error = _describe_model_exception(exc)
            print(f"  WARN {provider}/{tier} model ({model_name}): {last_error}", flush=True)

    _update_health_status(f"model_runtime.last_errors.{provider}", last_error or "unknown_failure")
    return "", _build_model_metadata(
        provider,
        model_name,
        tier,
        is_fallback=True,
        fallback_reason=last_error or "unknown_failure",
        timeout_seconds=timeout_seconds,
        attempts=attempts,
    ), last_error or "unknown_failure"


async def _generate_model_text(
    *,
    provider: str,
    model_name: str,
    tier: str,
    system: str,
    user: str,
    max_tokens: int,
    timeout_seconds: float,
    retries: int = 0,
) -> tuple[str, dict]:
    primary_provider = str(provider or "").strip().lower()
    text, metadata, primary_error = await _run_model_provider(
        provider=primary_provider,
        model_name=model_name,
        tier=tier,
        system=system,
        user=user,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
    if text:
        _update_health_status(f"model_runtime.provider_switch.{tier}", "")
        return text, metadata
    if not _should_attempt_provider_fallback(primary_provider, primary_error):
        return "", metadata

    for fallback_spec in _provider_fallback_specs(primary_provider, tier):
        fallback_provider = str(fallback_spec.get("provider") or "").strip().lower()
        switch_label = f"{primary_provider}->{fallback_provider}"
        _update_health_status(f"model_runtime.provider_switch.{tier}", f"{switch_label}: {primary_error}")
        fallback_text, fallback_metadata, fallback_error = await _run_model_provider(
            provider=fallback_provider,
            model_name=str(fallback_spec.get("model") or ""),
            tier=tier,
            system=system,
            user=user,
            max_tokens=max_tokens,
            timeout_seconds=float(fallback_spec.get("timeout_seconds") or 0.0) or timeout_seconds,
            retries=int(fallback_spec.get("retries") or 0),
        )
        if fallback_text:
            fallback_metadata["provider_switch"] = switch_label
            fallback_metadata["upstream_error"] = primary_error
            return fallback_text, fallback_metadata
        if not _should_attempt_provider_fallback(fallback_provider, fallback_error):
            break
    return "", metadata


# ── Endpoint 1: Intelligence Card ─────────────────────────────────────────────

@app.get("/api/ai-summary/{ticker}")
async def get_ai_summary(ticker: str):
    """Tactical 2-sentence catalyst summary for the Intelligence Card."""
    ticker = ticker.upper().strip()

    loop = asyncio.get_running_loop()
    filing_future = loop.run_in_executor(None, _latest_filing_for_ticker, ticker)
    sympathy_future = loop.run_in_executor(None, _sympathy_history_for_ticker, ticker, 5)
    memory_future = _everos_context(f"{ticker} catalyst sympathy velocity filing", limit=3)
    (form_type, filing_date, filing_text), sympathy_history, memory_context = await asyncio.gather(
        filing_future,
        sympathy_future,
        memory_future,
    )

    prompt_parts = [
        f"Analyze this SEC filing for {ticker} ({form_type}) and identify the catalyst.\n\n"
        f"Filing text:\n{filing_text or '[No filing text cached - use ticker and form type only.]'}"
    ]
    if sympathy_history:
        prompt_parts.append("Historical context:\n" + _format_sympathy_prompt(sympathy_history))
    if memory_context:
        prompt_parts.append("Operator memory:\n" + _format_memory_prompt(memory_context))
    user_prompt = "\n\n".join(part for part in prompt_parts if part)

    model_spec = _resolve_model_spec("fast")
    model_metadata = _build_model_metadata(
        model_spec.get("provider", ""),
        model_spec.get("model", ""),
        "fast",
        is_fallback=True,
        fallback_reason=f"{model_spec.get('provider') or 'model'}_unavailable",
        timeout_seconds=float(model_spec.get("timeout_seconds") or 0.0) or None,
        attempts=0,
    )
    summary, model_metadata = await _generate_model_text(
        provider=model_spec.get("provider", ""),
        model_name=model_spec.get("model", ""),
        tier="fast",
        system=_SYSTEM_INTELLIGENCE_CARD,
        user=user_prompt,
        max_tokens=160,
        timeout_seconds=float(model_spec.get("timeout_seconds") or 0.0) or _ANTHROPIC_FAST_TIMEOUT_SECONDS,
        retries=int(model_spec.get("retries") or 0),
    )
    if summary:
        return {
            "summary":       summary,
            "confidence":    0.91,
            "catalyst_type": _classify_catalyst(summary),
            "filing_type":   form_type,
            "filing_date":   filing_date,
            "source":        "model_synthesis",
            "model_metadata": model_metadata,
            "sympathy_history": sympathy_history,
            "memory_context": memory_context,
        }

    sympathy_sentence = _summarize_sympathy_history(ticker, sympathy_history)
    if filing_text:
        filing_label = form_type or "SEC filing"
        if filing_date:
            sentence_one = (
                f"The latest verified cached filing for {ticker} is {filing_label} filed on {filing_date}, "
                "and model-generated catalyst synthesis is unavailable so review the filing directly for exact catalyst details."
            )
        else:
            sentence_one = (
                f"The latest verified cached filing for {ticker} is {filing_label}, "
                "and model-generated catalyst synthesis is unavailable so review the filing directly for exact catalyst details."
            )
        sentence_two = sympathy_sentence or f"No verified sympathy history is attached to {ticker} yet."
        return {
            "summary":       f"{sentence_one} {sentence_two}",
            "confidence":    0.42,
            "catalyst_type": "FILE_REVIEW_REQUIRED",
            "filing_type":   filing_label,
            "filing_date":   filing_date,
            "source":        "verified_fallback",
            "model_metadata": model_metadata,
            "sympathy_history": sympathy_history,
            "memory_context": memory_context,
        }

    sentence_one = f"Cerebro could not verify a cached SEC filing for {ticker} at the moment."
    sentence_two = sympathy_sentence or (
        "Live catalyst synthesis is unavailable right now, so treat this card as unverified until the filing cache refreshes."
    )
    return {
        "summary":       f"{sentence_one} {sentence_two}",
        "confidence":    0.0,
        "catalyst_type": "UNVERIFIED",
        "filing_type":   form_type,
        "filing_date":   filing_date,
        "source":        "unverified_fallback",
        "model_metadata": model_metadata,
        "sympathy_history": sympathy_history,
        "memory_context": memory_context,
    }


# ── Endpoint 2: Pre-Market Audio Briefing ─────────────────────────────────────

@app.get("/api/briefing")
async def get_briefing():
    """
    4-sentence pre-market audio script for Phase 5 ElevenLabs TTS.
    Synthesizes overnight velocity sparks, rogue nodes, and sector shifts.
    """
    loop = asyncio.get_running_loop()
    sympathy_future = loop.run_in_executor(None, _recent_sympathy_highlights, 3)
    memory_future = _everos_context("premarket velocity sympathy macro scanner operator context", limit=3)
    sympathy_highlights, memory_context = await asyncio.gather(sympathy_future, memory_future)

    def _build_context(sympathy_items: list[dict], memory_items: list[str]) -> str:
        lines: list[str] = []
        sv: dict = {}
        try:
            sv = json.loads((ROOT / "spark_velocities.json").read_text())
            top = sorted(
                [(t, sum(abs(v) for v in d.values() if isinstance(v, (int, float)))) for t, d in sv.items()],
                key=lambda item: -item[1],
            )[:5]
            if top:
                lines.append(
                    "Top overnight velocity sparks: "
                    + ", ".join(f"{ticker} ({round(value, 1)}v)" for ticker, value in top)
                )
        except Exception:
            pass
        try:
            mp: dict = json.loads((ROOT / "macro_pressure.json").read_text())
            mult = mp.get("global_multiplier", 1.0)
            sec = mp.get("leading_sector", "")
            lines.append(f"Macro multiplier: {round(mult, 3)}. Leading sector: {sec or 'undetermined'}.")
            if mp.get("recession_warning"):
                lines.append("RECESSION WARNING flag is active.")
        except Exception:
            pass
        try:
            em: dict = json.loads((ROOT / "entity_master.json").read_text())
            rogues = [
                ticker
                for ticker, rec in em.items()
                if rec.get("is_rogue") and spark_total(sv.get(ticker, {})) != 0.0
            ]
            if rogues:
                lines.append(f"Active rogue nodes with velocity: {', '.join(rogues[:4])}.")
        except Exception:
            pass
        if sympathy_items:
            rendered = []
            for item in sympathy_items:
                move = item.get("move_pct_t1day")
                move_text = f"{move:+.2f}% T+1" if move is not None else "T+1 unresolved"
                rendered.append(f"{item['trigger_ticker']} in {item.get('sector') or 'unknown'} ({move_text})")
            lines.append("Recent sympathy outcomes: " + "; ".join(rendered))
        if memory_items:
            compact = [snippet.splitlines()[0][:160] for snippet in memory_items[:2] if snippet]
            if compact:
                lines.append("Operator memory: " + " | ".join(compact))
        return "\n".join(lines) or "No overnight anomalies detected. All sectors nominal."

    context = await loop.run_in_executor(None, _build_context, sympathy_highlights, memory_context)

    model_spec = _resolve_model_spec("smart")
    model_metadata = _build_model_metadata(
        model_spec.get("provider", ""),
        model_spec.get("model", ""),
        "smart",
        is_fallback=True,
        fallback_reason=f"{model_spec.get('provider') or 'model'}_unavailable",
        timeout_seconds=float(model_spec.get("timeout_seconds") or 0.0) or None,
        attempts=0,
    )
    script, model_metadata = await _generate_model_text(
        provider=model_spec.get("provider", ""),
        model_name=model_spec.get("model", ""),
        tier="smart",
        system=_SYSTEM_BRIEFING,
        user=f"Overnight data:\n{context}",
        max_tokens=220,
        timeout_seconds=float(model_spec.get("timeout_seconds") or 0.0) or _ANTHROPIC_SMART_TIMEOUT_SECONDS,
        retries=int(model_spec.get("retries") or 0),
    )
    if script:
        return {
            "script": script,
            "source": "model_synthesis",
            "model_metadata": model_metadata,
            "context": context,
            "sympathy_highlights": sympathy_highlights,
            "memory_context": memory_context,
        }

    def _deterministic_briefing() -> str:
        try:
            sv: dict = json.loads((ROOT / "spark_velocities.json").read_text())
        except Exception:
            sv = {}
        try:
            em: dict = json.loads((ROOT / "entity_master.json").read_text())
        except Exception:
            em = {}
        try:
            mp: dict = json.loads((ROOT / "macro_pressure.json").read_text())
        except Exception:
            mp = {}

        events = []
        for ticker, entry in sv.items():
            event = build_velocity_event(
                ticker,
                entry,
                name=(em.get(ticker) or {}).get("name", ""),
                wire_event="briefing_snapshot",
            )
            if event["total_velocity"] != 0.0:
                events.append(event)
        events.sort(key=lambda item: (-item["severity_rank"], -abs(item["total_velocity"]), item["ticker"]))

        top_event = events[0] if events else None
        leading_sector = mp.get("leading_sector") or "the broad tape"
        global_multiplier = mp.get("global_multiplier", 1.0)
        rogues = [
            ticker
            for ticker, rec in em.items()
            if rec.get("is_rogue") and spark_total(sv.get(ticker, {})) != 0.0
        ]

        sentences = ["Good morning. All systems nominal."]
        if top_event:
            driver = (top_event.get("primary_driver") or {}).get("label", "velocity")
            severity = top_event.get("severity", "active")
            sentences.append(
                f"Highest live velocity is in {top_event['ticker']}, where {driver.lower()} is driving a {severity} {top_event['polarity']} stack."
            )
        else:
            sentences.append("No severe velocity stack is active in the current overnight window.")

        sentences.append(
            f"Capital is leaning toward {leading_sector} while macro pressure is running at {global_multiplier:.2f}x."
        )
        sympathy_sentence = _summarize_briefing_sympathy(sympathy_highlights)
        if rogues:
            sentences.append(f"Rogue node activity is live in {', '.join(rogues[:3])}.")
        elif sympathy_sentence:
            sentences.append(sympathy_sentence)
        else:
            sentences.append("No rogue node is currently breaking away from its ETF canopy.")
        return " ".join(sentences[:4])

    return {
        "script": _deterministic_briefing(),
        "source": "deterministic_fallback",
        "model_metadata": model_metadata,
        "context": context,
        "sympathy_highlights": sympathy_highlights,
        "memory_context": memory_context,
    }


# ── WebSocket: Live feed ──────────────────────────────────────────────────────
@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """
    Subscribe the WebGL HUD to Redis channel 'cerebro:updates'.
    Velocity payloads carry a canonical `velocity_event` object.
    Heartbeat every 30s to keep connection alive through load balancers.
    """
    await websocket.accept()

    if not _redis_pool:
        await websocket.send_text(json.dumps({
            "event": "error", "message": "Redis unavailable — live feed disabled"
        }))
        await websocket.close()
        return

    pubsub = _redis_pool.pubsub()
    await pubsub.subscribe(REDIS_CHAN)
    print(f"  WS connected: {websocket.client}")

    async def _heartbeat():
        while True:
            await asyncio.sleep(30)
            try:
                await websocket.send_text(json.dumps({"event": "heartbeat", "ts": time.time()}))
            except Exception:
                break

    hb_task = asyncio.create_task(_heartbeat())

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        print(f"  WS disconnected: {websocket.client}")
    except Exception as exc:
        print(f"  WS error: {exc}")
    finally:
        hb_task.cancel()
        await pubsub.unsubscribe(REDIS_CHAN)
        close = getattr(pubsub, "aclose", None)
        if callable(close):
            await close()
        else:
            pubsub.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)
