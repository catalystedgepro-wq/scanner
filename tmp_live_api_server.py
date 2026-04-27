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
import time
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis
from velocity_deck_schema import (
    VELOCITY_DECK_SCHEMA_VERSION,
    build_velocity_event,
    canonical_spark_snapshot,
    spark_total,
)
from everos_memory_client import (
    EverOSRequestError as _EverOSRequestError,
    load_config as _load_everos_config,
    search_memories as _everos_search_memories,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path("/opt/catalyst")

_PATHS = {
    "entity_master":   ROOT / "entity_master.json",
    "macro_layer":     ROOT / "macro_layer.json",
    "macro_pressure":  ROOT / "macro_pressure.json",
    "spark_velocities":ROOT / "spark_velocities.json",
    "options_activity":ROOT / "options_activity.json",
    "collision_alerts":ROOT / "collision_alerts.json",
    "gap_scanner":     ROOT / "gap_scanner.json",
}

REDIS_URL   = "redis://localhost:6379"
REDIS_CHAN   = "cerebro:updates"
CONTRACT_VERSION = "2026-04-07-s01"
_EVEROS_CFG = _load_everos_config()
_SYMPATHY_PATH = ROOT / "sympathy_events.csv"

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Cerebro Core Intelligence API",
    description="Physics Engine live feed — Gravity × Velocity × Atmospheric Pressure",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # lock to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
async def _read_json(key: str) -> dict | list:
    path = _PATHS.get(key)
    if not path or not path.exists():
        return {}
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        raw = await f.read()
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _brightness(rec: dict, sparks: dict, ticker: str) -> float:
    """Compute live brightness for a single ticker record."""
    gravity = rec.get("gravity", 0.0) or 0.0
    spark_e = canonical_spark_snapshot(sparks.get(ticker.upper(), {}))
    velocity = (
        spark_e.get("patent",  0.0) +
        spark_e.get("legal",   0.0) +
        spark_e.get("digital", 0.0) +
        spark_e.get("options", 0.0)
    )
    return round(gravity * (1.0 + velocity), 2)


def _universe_row(rec: dict, sparks: dict, ticker: str) -> dict:
    """Return a normalized universe row with the required API contract keys."""
    g = rec.get("gravity", 0.0) or 0.0
    gics = rec.get("gics") or {}
    sector = gics.get("s", "") if isinstance(gics, dict) else rec.get("sector", "")
    return {
        "ticker":        ticker,
        "name":          rec.get("name", ""),
        "gravity":       round(g, 4),
        "brightness":    _brightness(rec, sparks, ticker),
        "cap_tier":      rec.get("mkt_cap_tier", "") or rec.get("cap_tier", ""),
        "sector":        sector,
        "etf_weight":    round(rec.get("etf_weights_sum", 0.0) or 0.0, 6),
        "etf_overlords": rec.get("etf_overlords", []),
        "is_rogue":      rec.get("is_rogue", False),
    }


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
    return {
        "status":     "ok",
        "contract_version": CONTRACT_VERSION,
        "redis":      redis_ok,
        "entity_master_exists": em_path.exists(),
        "entity_master_size":   em_path.stat().st_size if em_path.exists() else 0,
        "ts":         time.time(),
    }


# ── REST: Universe (paginated) ────────────────────────────────────────────────
@app.get("/api/universe")
async def get_universe(
    page:     int = Query(1,   ge=1),
    per_page: int = Query(500, ge=1, le=2000),
    sector:   Optional[str] = Query(None),
    min_gravity: float = Query(0.0),
):
    """Paginated entity_master. Filter by sector short code or min gravity."""
    em: dict = await _read_json("entity_master")
    sparks: dict = await _read_json("spark_velocities")

    rows = []
    for ticker, rec in em.items():
        if rec.get("etf"):
            continue
        g = rec.get("gravity", 0.0) or 0.0
        if g < min_gravity:
            continue
        if sector:
            gics = rec.get("gics") or {}
            if isinstance(gics, dict) and gics.get("s") != sector:
                continue
        rows.append(_universe_row(rec, sparks, ticker))

    rows.sort(key=lambda r: -r["brightness"])
    total = len(rows)
    start = (page - 1) * per_page
    return {
        "contract_version": CONTRACT_VERSION,
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    (total + per_page - 1) // per_page,
        "tickers":  rows[start : start + per_page],
    }


# ── REST: Single ticker ───────────────────────────────────────────────────────
@app.get("/api/ticker/{symbol}")
async def get_ticker(symbol: str):
    em: dict     = await _read_json("entity_master")
    sparks: dict = await _read_json("spark_velocities")

    ticker = symbol.upper()
    rec = em.get(ticker)
    if not rec:
        raise HTTPException(status_code=404, detail=f"{ticker} not in entity_master")

    loop = asyncio.get_running_loop()
    sympathy_future = loop.run_in_executor(None, _sympathy_history_for_ticker, ticker, 5)
    memory_future = _everos_context(f"{ticker} velocity sympathy catalyst", limit=3)
    sympathy_history, memory_context = await asyncio.gather(sympathy_future, memory_future)

    spark_e = canonical_spark_snapshot(sparks.get(ticker, {}))
    velocity_event = build_velocity_event(
        ticker,
        spark_e,
        name=rec.get("name", ""),
        wire_event="velocity_snapshot",
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "velocity_deck_schema_version": VELOCITY_DECK_SCHEMA_VERSION,
        "ticker":         ticker,
        "name":           rec.get("name", ""),
        "gravity":        rec.get("gravity", 0.0),
        "brightness":     _brightness(rec, sparks, ticker),
        "mkt_cap_usd":    rec.get("mkt_cap_usd"),
        "cap_tier":       rec.get("mkt_cap_tier", ""),
        "gics":           rec.get("gics", {}),
        "etf_weights_sum":rec.get("etf_weights_sum", 0.0),
        "sparks":         spark_e,
        "velocity_event": velocity_event,
        "geospatial_nodes": rec.get("geospatial_nodes", []),
        "cik":            rec.get("cik", ""),
        "sympathy_history": sympathy_history,
        "memory_context": memory_context,
    }


# ── REST: Sectors ─────────────────────────────────────────────────────────────
@app.get("/api/sectors")
async def get_sectors():
    """Aggregate brightness and gravity by GICS sector."""
    em: dict     = await _read_json("entity_master")
    sparks: dict = await _read_json("spark_velocities")
    macro: dict  = await _read_json("macro_pressure")
    pressures    = macro.get("pressures", {})

    buckets: dict[str, dict] = {}
    for ticker, rec in em.items():
        if rec.get("etf"):
            continue
        gics = rec.get("gics")
        sector = gics.get("s", "unknown") if isinstance(gics, dict) else "unknown"
        b = _brightness(rec, sparks, ticker)
        g = rec.get("gravity", 0.0) or 0.0
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
    return {"sectors": result}


# ── REST: Macro ───────────────────────────────────────────────────────────────
@app.get("/api/macro")
async def get_macro():
    layer:    dict = await _read_json("macro_layer")
    pressure: dict = await _read_json("macro_pressure")
    return {"macro_layer": layer, "macro_pressure": pressure}


# ── REST: Options ─────────────────────────────────────────────────────────────
@app.get("/api/options")
async def get_options(limit: int = Query(50, ge=1, le=500)):
    activity: dict = await _read_json("options_activity")
    rows = []
    for ticker, data in activity.items():
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
        })
    rows.sort(key=lambda r: -r["sweep_count"])
    return {"options": rows[:limit], "total": len(rows)}


# ── REST: Velocity Deck events ────────────────────────────────────────────────
@app.get("/api/spark")
async def get_sparks(limit: int = Query(50, ge=1, le=500)):
    sparks: dict = await _read_json("spark_velocities")
    em: dict     = await _read_json("entity_master")

    rows = []
    for ticker, entry in sparks.items():
        name = em.get(ticker, {}).get("name", "") if em else ""
        velocity_event = build_velocity_event(
            ticker,
            entry,
            name=name,
            wire_event="velocity_snapshot",
        )
        if velocity_event["total_velocity"] == 0.0:
            continue
        rows.append(velocity_event)

    rows.sort(key=lambda r: (-r["severity_rank"], -abs(r["total_velocity"]), r["ticker"]))
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
            gics = rec.get("gics") or {}
            if isinstance(gics, dict) and gics.get("s") != sector:
                continue
        b = _brightness(rec, sparks, ticker)
        if b <= 0:
            continue
        rows.append({"ticker": ticker, "name": rec.get("name", ""),
                     "brightness": b, "gravity": rec.get("gravity", 0.0),
                     "sector": (rec.get("gics") or {}).get("s", "")
                                if isinstance(rec.get("gics"), dict) else ""})

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
_DEFAULT_FAST_MODEL = "claude-haiku-4-5-20251001"


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


_ANTHROPIC_MODEL_FAST = ((_os.environ.get("ANTHROPIC_MODEL_FAST", "") or "").strip() or _DEFAULT_FAST_MODEL)
_ANTHROPIC_MODEL_SMART = ((_os.environ.get("ANTHROPIC_MODEL_SMART", "") or "").strip() or _ANTHROPIC_MODEL_FAST)
_ANTHROPIC_FAST_TIMEOUT_SECONDS = _env_float("ANTHROPIC_FAST_TIMEOUT_SECONDS", 8.0)
_ANTHROPIC_SMART_TIMEOUT_SECONDS = _env_float("ANTHROPIC_SMART_TIMEOUT_SECONDS", 16.0)
_ANTHROPIC_SMART_RETRIES = _env_int("ANTHROPIC_SMART_RETRIES", 1)


def _model_display_name(model_name: str) -> str:
    slug = (model_name or "").strip().replace("_", "-")
    if not slug:
        return "Fallback path"
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
    model_name: str,
    tier: str,
    *,
    is_fallback: bool,
    fallback_reason: str = "",
    timeout_seconds: float | None = None,
    attempts: int = 0,
) -> dict:
    return {
        "model": model_name or "",
        "display_name": _model_display_name(model_name),
        "tier": tier,
        "is_fallback": is_fallback,
        "fallback_reason": fallback_reason or "",
        "timeout_seconds": timeout_seconds,
        "attempts": attempts,
    }

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


async def _generate_model_text(
    *,
    model_name: str,
    tier: str,
    system: str,
    user: str,
    max_tokens: int,
    timeout_seconds: float,
    retries: int = 0,
) -> tuple[str, dict]:
    if not _ANTHROPIC_AVAILABLE or not _ANTHROPIC_API_KEY or not model_name:
        fallback_reason = (
            "anthropic_package_unavailable"
            if not _ANTHROPIC_AVAILABLE
            else "anthropic_api_key_missing"
            if not _ANTHROPIC_API_KEY
            else "model_unconfigured"
        )
        return "", _build_model_metadata(
            model_name,
            tier,
            is_fallback=True,
            fallback_reason=fallback_reason,
            timeout_seconds=timeout_seconds,
            attempts=0,
        )

    loop = asyncio.get_running_loop()
    attempts = 0
    last_error = ""

    for attempt_index in range(retries + 1):
        attempts = attempt_index + 1
        try:
            response_future = loop.run_in_executor(
                None,
                _call_anthropic_model,
                model_name,
                system,
                user,
                max_tokens,
            )
            text = await asyncio.wait_for(response_future, timeout=timeout_seconds)
            if text:
                return text, _build_model_metadata(
                    model_name,
                    tier,
                    is_fallback=False,
                    timeout_seconds=timeout_seconds,
                    attempts=attempts,
                )
            last_error = "empty_response"
            print(f"  WARN {tier} model ({model_name}): empty response", flush=True)
        except asyncio.TimeoutError:
            last_error = "timeout"
            print(f"  WARN {tier} model ({model_name}): timed out after {timeout_seconds:.1f}s", flush=True)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"  WARN {tier} model ({model_name}): {exc}", flush=True)

    return "", _build_model_metadata(
        model_name,
        tier,
        is_fallback=True,
        fallback_reason=last_error or "unknown_failure",
        timeout_seconds=timeout_seconds,
        attempts=attempts,
    )


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

    model_metadata = _build_model_metadata(
        _ANTHROPIC_MODEL_FAST,
        "fast",
        is_fallback=True,
        fallback_reason="anthropic_api_key_missing" if not _ANTHROPIC_API_KEY else "model_unavailable",
        timeout_seconds=_ANTHROPIC_FAST_TIMEOUT_SECONDS,
        attempts=0,
    )
    summary, model_metadata = await _generate_model_text(
        model_name=_ANTHROPIC_MODEL_FAST,
        tier="fast",
        system=_SYSTEM_INTELLIGENCE_CARD,
        user=user_prompt,
        max_tokens=160,
        timeout_seconds=_ANTHROPIC_FAST_TIMEOUT_SECONDS,
        retries=0,
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

    model_metadata = _build_model_metadata(
        _ANTHROPIC_MODEL_SMART,
        "smart",
        is_fallback=True,
        fallback_reason="anthropic_api_key_missing" if not _ANTHROPIC_API_KEY else "model_unavailable",
        timeout_seconds=_ANTHROPIC_SMART_TIMEOUT_SECONDS,
        attempts=0,
    )
    script, model_metadata = await _generate_model_text(
        model_name=_ANTHROPIC_MODEL_SMART,
        tier="smart",
        system=_SYSTEM_BRIEFING,
        user=f"Overnight data:\n{context}",
        max_tokens=220,
        timeout_seconds=_ANTHROPIC_SMART_TIMEOUT_SECONDS,
        retries=_ANTHROPIC_SMART_RETRIES,
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
