#!/usr/bin/env python3
"""spoke_memory.py — Cerebro Long-Term Memory Bank (Phase 5 foundation).

Subscribes to the 'cerebro:updates' Redis pub/sub channel and permanently
logs every velocity spark into a local SQLite time-series database.

Why SQLite instead of InfluxDB:
  - Zero RAM overhead (InfluxDB 2.0 needs >1GB RAM minimum)
  - No Docker required — runs anywhere Python runs
  - pandas reads it directly in July: pd.read_sql("SELECT ...", conn)
  - WAL mode allows concurrent reads while this writer is active
  - 90-day rolling window keeps the file under ~50MB

When July arrives, the ML Sympathy Engine just runs:
    import pandas as pd, sqlite3
    conn = sqlite3.connect('.cerebro_memory.db')
    df = pd.read_sql("SELECT * FROM velocity_sparks WHERE ts_unix > ?",
                     conn, params=[time.time() - 90*86400])
    # Then cross-correlate with df.corr() and lagged CCF

Run:
  python3 spoke_memory.py            — runs forever (use systemd or screen)
  python3 spoke_memory.py --once     — process backlog then exit (for testing)

Managed by: cerebro-memory.service (systemd)
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path

from everos_memory_client import EverOSRequestError, load_config, save_note
import redis

ROOT   = Path(__file__).parent
DB     = ROOT / ".cerebro_memory.db"
CHAN   = "cerebro:updates"

REDIS_HOST    = "127.0.0.1"
REDIS_PORT    = 6379
RETENTION_SEC = 90 * 86400   # 90 days
PRUNE_EVERY   = 500          # prune old rows every N inserts
EVEROS_CFG    = load_config()
EVEROS_BACKOFF_UNTIL = [0.0]


# ── Database init ──────────────────────────────────────────────────────────────
def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS velocity_sparks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id    TEXT    UNIQUE,       -- dedup: sha1(ticker+type+hour)
            ts_unix     REAL    NOT NULL,
            ts_iso      TEXT    NOT NULL,
            ticker      TEXT    NOT NULL,
            sector      TEXT    DEFAULT '',
            event_type  TEXT    DEFAULT '',
            velocity    REAL    DEFAULT 0.0,
            patent      REAL    DEFAULT 0.0,
            legal       REAL    DEFAULT 0.0,
            digital     REAL    DEFAULT 0.0,
            options     REAL    DEFAULT 0.0,
            weather     REAL    DEFAULT 0.0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_ts ON velocity_sparks(ticker, ts_unix)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts       ON velocity_sparks(ts_unix)")
    conn.execute("PRAGMA journal_mode=WAL")   # concurrent reads during write
    conn.execute("PRAGMA synchronous=NORMAL") # fast enough, safe enough
    conn.commit()


def _prune(conn: sqlite3.Connection) -> int:
    """Delete rows older than RETENTION_SEC. Returns number of rows removed."""
    cutoff = time.time() - RETENTION_SEC
    cur = conn.execute("DELETE FROM velocity_sparks WHERE ts_unix < ?", (cutoff,))
    conn.commit()
    return cur.rowcount


def _event_id(ticker: str, event_type: str, ts: float) -> str:
    """Idempotency key: same ticker + event type within the same hour → same ID."""
    hour_bucket = int(ts // 3600) * 3600
    raw = f"{ticker}:{event_type}:{hour_bucket}"
    return sha1(raw.encode()).hexdigest()[:16]


# ── Spark handler ──────────────────────────────────────────────────────────────
def _mirror_to_everos(payload: dict, event_id: str, velocity: float) -> None:
    if not EVEROS_CFG.enabled or time.time() < EVEROS_BACKOFF_UNTIL[0]:
        return

    ticker = (payload.get("ticker") or "").upper()
    if not ticker:
        return

    event_type = payload.get("event", "")
    velocity_event = payload.get("velocity_event") or {}
    spark = velocity_event.get("spark") or payload.get("spark") or {}
    metadata = {
        "event_id": event_id,
        "event": event_type,
        "ticker": ticker,
        "velocity": round(float(velocity or 0.0), 4),
        "schema_version": payload.get("schema_version"),
        "ts": payload.get("ts"),
    }
    title = f"{ticker} {event_type} event"
    body = "Mirrored from the live Cerebro event stream."

    if isinstance(velocity_event, dict) and velocity_event:
        title = velocity_event.get("headline") or title
        body_lines = [
            velocity_event.get("detail") or "",
            f"severity: {velocity_event.get('severity', 'unknown')}",
            f"source: {velocity_event.get('source', 'unknown')}",
            f"polarity: {velocity_event.get('polarity', 'neutral')}",
        ]
        body = "\n".join(line for line in body_lines if line)
        metadata.update(
            {
                "severity": velocity_event.get("severity"),
                "source": velocity_event.get("source"),
                "polarity": velocity_event.get("polarity"),
                "score": spark.get("score"),
                "magnitude": spark.get("magnitude"),
            }
        )
    else:
        for key in ("patent", "legal", "digital", "options", "weather"):
            if key in spark:
                metadata[key] = spark.get(key)

    try:
        save_note(
            title,
            body=body,
            metadata=metadata,
            cfg=EVEROS_CFG,
            flush=True,
            id_seed=f"{event_id}:{ticker}",
            scene="cerebro_velocity",
            raw_data_type="CerebroVelocityEvent",
        )
    except EverOSRequestError as exc:
        EVEROS_BACKOFF_UNTIL[0] = time.time() + 300
        print(f"  [memory] everos_skip: {exc}", file=sys.stderr, flush=True)


def _store(conn: sqlite3.Connection, raw: bytes, counter: list) -> None:
    try:
        payload    = json.loads(raw)
        event_type = payload.get("event", "")
        ticker     = (payload.get("ticker") or "").upper()
        ts         = float(payload.get("ts") or time.time())

        # Heartbeats and non-ticker events carry no spark — skip
        if event_type == "heartbeat" or not ticker:
            return

        spark   = payload.get("spark") or {}
        patent  = float(spark.get("patent",  0) or 0)
        legal   = float(spark.get("legal",   0) or 0)
        digital = float(spark.get("digital", 0) or 0)
        options = float(spark.get("options", 0) or 0)
        weather = float(spark.get("weather", 0) or 0)
        velocity = patent + legal + digital + options + weather

        # Zero-velocity macro events (pipeline_complete etc.) are logged but not critical
        eid = _event_id(ticker, event_type, ts)
        ts_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        conn.execute("""
            INSERT OR IGNORE INTO velocity_sparks
              (event_id, ts_unix, ts_iso, ticker, event_type,
               velocity, patent, legal, digital, options, weather)
            VALUES (?,?,?,?,?, ?,?,?,?,?,?)
        """, (eid, ts, ts_iso, ticker, event_type,
              velocity, patent, legal, digital, options, weather))
        conn.commit()
        _mirror_to_everos(payload, eid, velocity)

        counter[0] += 1

        # Periodic pruning + progress log
        if counter[0] % PRUNE_EVERY == 0:
            pruned = _prune(conn)
            cur = conn.execute("SELECT COUNT(*) FROM velocity_sparks")
            total = cur.fetchone()[0]
            print(f"  [memory] {counter[0]} logged | {total} rows active | {pruned} pruned", flush=True)

    except Exception as e:
        # Never crash the listener on a malformed message
        print(f"  WARN store: {e}", file=sys.stderr, flush=True)


# ── Main loop ──────────────────────────────────────────────────────────────────
def run(once: bool = False) -> None:
    print(f"[spoke_memory] {datetime.now(timezone.utc).isoformat()}")
    print(f"  DB: {DB}")
    print(f"  Channel: {CHAN}  |  Retention: 90 days")
    print(f"  EverOS: {'enabled' if EVEROS_CFG.enabled else 'disabled'}")

    conn = sqlite3.connect(DB, check_same_thread=False)
    _init_db(conn)

    cur = conn.execute("SELECT COUNT(*) FROM velocity_sparks")
    print(f"  Existing rows: {cur.fetchone()[0]}")

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    ps = r.pubsub()
    ps.subscribe(CHAN)
    print(f"  Subscribed to {CHAN}. Listening...\n", flush=True)

    counter = [0]

    try:
        for msg in ps.listen():
            if msg["type"] != "message":
                continue
            _store(conn, msg["data"], counter)
            if once and counter[0] >= 1:
                break
    except KeyboardInterrupt:
        print(f"\n  [memory] Shutting down. {counter[0]} sparks logged this session.")
    finally:
        conn.close()


if __name__ == "__main__":
    run(once="--once" in sys.argv)
