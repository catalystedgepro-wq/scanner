#!/usr/bin/env python3
"""cerebro_publisher.py — Redis Pub/Sub bridge for the Cerebro pipeline.

Called by run_daily_sec_catalyst.sh (and individual spokes) to push
real-time Spark, Macro, and Options events to the 'cerebro:updates' channel.

The FastAPI /ws/live endpoint relays these payloads to connected HUD clients.

Usage:
    python3 cerebro_publisher.py --event=pipeline_complete
    python3 cerebro_publisher.py --event=spark_update --ticker=NVDA
    python3 cerebro_publisher.py --event=macro_update
    python3 cerebro_publisher.py --event=options_sweep --ticker=AAPL

Pure stdlib — uses socket directly to avoid redis-py dependency in pipeline.
Falls back silently if Redis is unavailable (pipeline never blocks on this).
"""
from __future__ import annotations

import json
import socket
import sys
import time
from hashlib import sha1
from pathlib import Path

from velocity_deck_schema import VELOCITY_DECK_SCHEMA_VERSION, build_velocity_event

ROOT   = Path(__file__).parent
HOST   = "127.0.0.1"
PORT   = 6379
CHAN   = "cerebro:updates"

# ── Debounce / idempotency cache ──────────────────────────────────────────────
# Flat JSON file: {event_key: unix_timestamp_of_last_publish}
# Same ticker + event_type within DEBOUNCE_SEC → silently dropped
DEBOUNCE_FILE = ROOT / ".publisher_dedup.json"
DEBOUNCE_SEC  = 300   # 5 minutes — prevents NOAA firing 14×/hour for same event


def _dedup_key(event: str, ticker: str | None) -> str:
    raw = f"{event}:{(ticker or '').upper()}"
    return sha1(raw.encode()).hexdigest()[:12]


def _is_duplicate(event: str, ticker: str | None) -> bool:
    """Return True if this exact event was published within DEBOUNCE_SEC."""
    key = _dedup_key(event, ticker)
    now = time.time()
    cache: dict = {}
    try:
        if DEBOUNCE_FILE.exists():
            cache = json.loads(DEBOUNCE_FILE.read_text())
    except Exception:
        pass

    last = cache.get(key, 0)
    if now - last < DEBOUNCE_SEC:
        return True

    # Update cache — prune entries older than 2× window to keep file tiny
    cache[key] = now
    cache = {k: v for k, v in cache.items() if now - v < DEBOUNCE_SEC * 2}
    try:
        DEBOUNCE_FILE.write_text(json.dumps(cache))
    except Exception:
        pass
    return False


def _redis_publish(channel: str, message: str) -> bool:
    """
    Send a PUBLISH command to Redis via raw socket (no redis-py needed in pipeline).
    Protocol: RESP inline PUBLISH <channel> <message>
    """
    try:
        cmd = f"*3\r\n$7\r\nPUBLISH\r\n${len(channel)}\r\n{channel}\r\n${len(message)}\r\n{message}\r\n"
        with socket.create_connection((HOST, PORT), timeout=2) as s:
            s.sendall(cmd.encode("utf-8"))
            resp = s.recv(64).decode("utf-8", errors="replace")
            return resp.startswith(":")   # Redis returns :N\r\n (subscriber count)
    except Exception:
        return False   # silent — never block the pipeline


def _build_payload(event: str, ticker: str | None) -> dict:
    """Build a structured event payload for the HUD."""
    payload: dict = {"event": event, "ts": time.time()}

    if ticker:
        ticker = ticker.upper()
        payload["ticker"] = ticker
        payload["kind"] = "velocity_event"
        payload["schema_version"] = VELOCITY_DECK_SCHEMA_VERSION

        spark_entry: dict = {}
        entity_name = ""
        em_path = ROOT / "entity_master.json"
        if em_path.exists():
            try:
                em = json.loads(em_path.read_text())
                entity_name = (em.get(ticker) or {}).get("name", "")
            except Exception:
                pass

        sv_path = ROOT / "spark_velocities.json"
        if sv_path.exists():
            try:
                sv = json.loads(sv_path.read_text())
                spark_entry = sv.get(ticker, {}) or {}
            except Exception:
                spark_entry = {}

        if spark_entry:
            velocity_event = build_velocity_event(
                ticker,
                spark_entry,
                name=entity_name,
                wire_event=event,
                ts=payload["ts"],
            )
            payload["spark"] = velocity_event["spark"]
            payload["velocity_event"] = velocity_event

    if event == "macro_update":
        mp_path = ROOT / "macro_pressure.json"
        if mp_path.exists():
            try:
                mp = json.loads(mp_path.read_text())
                payload["macro_summary"] = {
                    "global_multiplier": mp.get("global_multiplier", 1.0),
                    "recession_warning": mp.get("recession_warning", False),
                    "updated":           mp.get("updated", ""),
                }
            except Exception:
                pass

    if event == "pipeline_complete":
        # Attach quick stats
        em_path = ROOT / "entity_master.json"
        if em_path.exists():
            try:
                em = json.loads(em_path.read_text())
                payload["universe_size"] = len(em)
            except Exception:
                pass

    if event == "options_sweep" and ticker:
        oa_path = ROOT / "options_activity.json"
        if oa_path.exists():
            try:
                oa = json.loads(oa_path.read_text())
                entry = oa.get(ticker.upper(), {})
                if entry:
                    payload["options"] = {
                        "sweep_count": entry.get("sweep_count", 0),
                        "sentiment":   entry.get("flow", {}).get("sentiment", ""),
                        "gamma_magnet":entry.get("gamma_magnet"),
                    }
            except Exception:
                pass

    return payload


def publish(event: str, ticker: str | None = None) -> None:
    # Debounce: identical event+ticker within 5 min → drop (flood control)
    # Pipeline_complete and macro_update are always allowed through
    if event not in ("pipeline_complete", "macro_update") and _is_duplicate(event, ticker):
        print(f"  cerebro_publisher: {event} [{ticker or '—'}] DEBOUNCED (duplicate within {DEBOUNCE_SEC}s)")
        return

    payload = _build_payload(event, ticker)
    msg     = json.dumps(payload)
    ok      = _redis_publish(CHAN, msg)
    status  = "published" if ok else "redis_unavailable"
    print(f"  cerebro_publisher: {event} → {CHAN}  [{status}]")


if __name__ == "__main__":
    event  = next((a.split("=")[1] for a in sys.argv if a.startswith("--event=")),  "pipeline_complete")
    ticker = next((a.split("=")[1] for a in sys.argv if a.startswith("--ticker=")), None)
    publish(event, ticker)
