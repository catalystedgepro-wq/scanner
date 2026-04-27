#!/usr/bin/env python3
"""silent_logger.py — Phase 4 (Lite): Historical Data Lake Builder.

Permanently subscribes to Redis 'cerebro:updates' channel and appends
every spark event to daily JSONL log files under the resolved Cerebro root's
`history/` directory.

Each line is a complete JSON payload: {event, ticker, spark, ts, timestamp}
Files rotate daily: sparks_2026-04-04.jsonl, sparks_2026-04-05.jsonl, ...

This silently builds the backtesting dataset while the live HUD runs.
Zero impact on the API server or pipeline.

Deploy: systemctl start cerebro-logger
Pure stdlib redis RESP subscriber — uses redis-py from venv.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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
        if (resolved / "silent_logger.py").exists():
            return resolved
    return Path(__file__).resolve().parent


LOG_DIR  = _resolve_root() / "history"
REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
CHAN     = "cerebro:updates"


def _subscribe_loop() -> None:
    """
    Pure blocking RESP subscriber using socket (no redis-py needed).
    Falls back to redis-py if available.
    """
    # Try redis-py first (installed in venv)
    try:
        import redis
        client = redis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
        pubsub = client.pubsub()
        pubsub.subscribe(CHAN)
        print(f"  cerebro-logger: redis-py connected → {CHAN}", flush=True)

        for message in pubsub.listen():
            if message["type"] != "message":
                continue
            raw = message["data"]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            yield raw

    except ImportError:
        # Fallback: raw RESP socket subscriber
        import socket
        print(f"  cerebro-logger: raw socket → {REDIS_HOST}:{REDIS_PORT}", flush=True)
        s = socket.create_connection((REDIS_HOST, REDIS_PORT), timeout=30)
        cmd = f"*2\r\n$9\r\nSUBSCRIBE\r\n${len(CHAN)}\r\n{CHAN}\r\n"
        s.sendall(cmd.encode())
        buf = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                raise ConnectionError("Redis disconnected")
            buf += chunk
            # Parse complete RESP messages
            while b"\r\n" in buf:
                if buf.startswith(b"*3"):
                    parts = buf.split(b"\r\n")
                    if len(parts) >= 8:
                        msg_type = parts[2].lstrip(b"$0123456789")
                        if parts[4] == b"message":
                            data = parts[8].decode("utf-8", errors="replace")
                            buf  = b"\r\n".join(parts[9:])
                            yield data
                            break
                        buf = b"\r\n".join(parts[1:])
                    else:
                        break
                else:
                    buf = buf[buf.find(b"\r\n") + 2:]


def _log_path() -> Path:
    """Return today's log file path, creating directory if needed."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return LOG_DIR / f"sparks_{date_str}.jsonl"


def run_logger() -> None:
    print(f"  cerebro-logger: starting — writing to {LOG_DIR}/sparks_YYYY-MM-DD.jsonl",
          flush=True)

    logged   = 0
    errors   = 0
    last_log = time.time()

    while True:
        try:
            for raw in _subscribe_loop():
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    errors += 1
                    continue

                # Skip heartbeats — they're noise
                if payload.get("event") == "heartbeat":
                    continue

                # Enrich with wall-clock timestamp
                payload["logged_at"] = datetime.now(timezone.utc).isoformat()

                try:
                    log_path = _log_path()
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(payload) + "\n")
                    logged += 1
                except Exception as exc:
                    print(f"  cerebro-logger: write error — {exc}", flush=True)
                    errors += 1

                # Status heartbeat every 5 minutes
                now = time.time()
                if now - last_log >= 300:
                    print(f"  cerebro-logger: {logged} events logged | "
                          f"{errors} errors | {_log_path().name}", flush=True)
                    last_log = now

        except Exception as exc:
            print(f"  cerebro-logger: connection lost ({exc}) — retry in 10s", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    run_logger()
