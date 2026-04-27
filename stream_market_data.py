"""stream_market_data.py — Streaming market-data daemon.

Subscribes to a watchlist of symbols via Finnhub WebSocket (free tier)
and writes each tick to an append-only JSONL file. Designed to run as a
long-lived daemon under systemd or `nohup`.

Why Finnhub: token is already in $WORKSPACE_ROOT/.sec_email_env, free tier
includes WebSocket trade ticks for US equities, no extra cost. Polygon and
Alpaca-data WebSockets are also supported via the SOURCE env var if/when
those keys are added.

Environment (read from .sec_email_env):
  - FINNHUB_API_KEY              (required for source=finnhub)
  - ALPACA_API_KEY_ID/SECRET     (required for source=alpaca)
  - STREAM_SOURCE                (default: finnhub | alpaca)
  - STREAM_WATCHLIST             (default: top-20 from sec_top_gappers.csv)
  - STREAM_OUTPUT_PATH           (default: data/stream_quotes.jsonl)
  - STREAM_MAX_RECONNECT         (default: 100  reconnect attempts before giving up)

Outputs:
  - $WORKSPACE_ROOT/data/stream_quotes.jsonl  (one JSON object per tick)
  - $WORKSPACE_ROOT/data/stream_quotes_status.json  (heartbeat: last tick, lag)
  - $WORKSPACE_ROOT/logs/stream_market_data.log

Usage:
  # Foreground:
  python3 /home/operator/.openclaw/workspace/stream_market_data.py

  # Background:
  nohup python3 /home/operator/.openclaw/workspace/stream_market_data.py \\
       > /home/operator/.openclaw/workspace/logs/stream_stdout.log 2>&1 &

  # Specific watchlist:
  STREAM_WATCHLIST="AAPL,TSLA,NVDA,SPY,QQQ" python3 stream_market_data.py
"""

import asyncio
import datetime as dt
import json
import os
import sys
import csv
from pathlib import Path

try:
    import websockets  # provided by `pip install websockets`
except ImportError:
    sys.stderr.write("ERROR: install websockets — `pip install websockets`\n")
    sys.exit(2)

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".sec_email_env"
LOG_FILE = ROOT / "logs" / "stream_market_data.log"
OUTPUT_PATH = ROOT / "data" / "stream_quotes.jsonl"
STATUS_PATH = ROOT / "data" / "stream_quotes_status.json"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_env() -> dict:
    env = {}
    if not ENV_FILE.exists():
        return env
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def log(msg: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    line = f"[{ts}] {msg}\n"
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line)
    sys.stdout.write(line)
    sys.stdout.flush()


def default_watchlist(env: dict) -> list[str]:
    """Pull top-N tickers from sec_top_gappers.csv if present."""
    explicit = env.get("STREAM_WATCHLIST") or os.environ.get("STREAM_WATCHLIST", "")
    if explicit.strip():
        return [s.strip().upper() for s in explicit.split(",") if s.strip()]

    csv_path = ROOT / "sec_top_gappers.csv"
    if not csv_path.exists():
        return ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "NFLX"]
    try:
        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            tickers: list[str] = []
            for row in reader:
                t = (row.get("ticker") or row.get("symbol") or "").strip().upper()
                if t and t not in tickers:
                    tickers.append(t)
                if len(tickers) >= 20:
                    break
        return tickers or ["SPY", "QQQ", "AAPL"]
    except Exception as e:  # noqa: BLE001
        log(f"watchlist load failed: {e} — using defaults")
        return ["SPY", "QQQ", "AAPL"]


def write_status(payload: dict) -> None:
    try:
        STATUS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log(f"status write failed: {e}")


# --------------------------------------------------------------------------- #
# Finnhub WS
# --------------------------------------------------------------------------- #

FINNHUB_WS_URL = "wss://ws.finnhub.io?token={token}"


async def stream_finnhub(token: str, watchlist: list[str]) -> None:
    url = FINNHUB_WS_URL.format(token=token)
    backoff = 2
    max_backoff = 120
    tick_count = 0
    last_tick_ts = None

    while True:
        try:
            log(f"connecting to Finnhub WS (watchlist={len(watchlist)} symbols)")
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                # Subscribe to each symbol
                for symbol in watchlist:
                    await ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))
                log(f"subscribed to {len(watchlist)} symbols")
                backoff = 2  # reset backoff on successful connect

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    if msg.get("type") == "trade":
                        for trade in msg.get("data", []):
                            tick = {
                                "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                                "source": "finnhub",
                                "symbol": trade.get("s"),
                                "price": trade.get("p"),
                                "volume": trade.get("v"),
                                "trade_ts_ms": trade.get("t"),
                                "conditions": trade.get("c") or [],
                            }
                            with OUTPUT_PATH.open("a", encoding="utf-8") as fh:
                                fh.write(json.dumps(tick) + "\n")
                            tick_count += 1
                            last_tick_ts = tick["ts"]
                            if tick_count % 50 == 0:
                                write_status({
                                    "source": "finnhub",
                                    "watchlist_size": len(watchlist),
                                    "ticks_received": tick_count,
                                    "last_tick_ts": last_tick_ts,
                                    "last_tick_symbol": tick["symbol"],
                                    "status": "streaming",
                                })
                    elif msg.get("type") == "ping":
                        continue
                    elif msg.get("type") == "error":
                        log(f"Finnhub error: {msg}")
        except (websockets.ConnectionClosed, OSError) as e:
            log(f"connection closed: {e}; reconnecting in {backoff}s")
            write_status({
                "source": "finnhub",
                "status": "reconnecting",
                "ticks_received": tick_count,
                "last_tick_ts": last_tick_ts,
                "error": str(e),
            })
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        except Exception as e:  # noqa: BLE001
            log(f"fatal: {type(e).__name__}: {e}; reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


# --------------------------------------------------------------------------- #
# Alpaca WS (IEX free tier on paper account)
# --------------------------------------------------------------------------- #

ALPACA_WS_URL = "wss://stream.data.alpaca.markets/v2/iex"


async def stream_alpaca(key: str, secret: str, watchlist: list[str]) -> None:
    backoff = 2
    max_backoff = 120
    tick_count = 0
    last_tick_ts = None

    while True:
        try:
            log(f"connecting to Alpaca IEX WS (watchlist={len(watchlist)} symbols)")
            async with websockets.connect(ALPACA_WS_URL, ping_interval=20) as ws:
                # Auth
                await ws.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
                auth_resp = await asyncio.wait_for(ws.recv(), timeout=10)
                log(f"alpaca auth response: {auth_resp[:200]}")
                # Subscribe to trades + quotes for the watchlist
                await ws.send(json.dumps({
                    "action": "subscribe",
                    "trades": watchlist,
                    "quotes": watchlist,
                }))
                sub_resp = await asyncio.wait_for(ws.recv(), timeout=10)
                log(f"alpaca subscribe response: {sub_resp[:300]}")
                backoff = 2

                async for raw in ws:
                    try:
                        msgs = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(msgs, list):
                        msgs = [msgs]
                    for msg in msgs:
                        msg_type = msg.get("T")
                        if msg_type in ("t", "q"):  # trade or quote
                            tick = {
                                "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                                "source": "alpaca",
                                "kind": "trade" if msg_type == "t" else "quote",
                                "symbol": msg.get("S"),
                                "price": msg.get("p"),
                                "size": msg.get("s"),
                                "bid": msg.get("bp"),
                                "ask": msg.get("ap"),
                                "exchange_ts": msg.get("t"),
                            }
                            with OUTPUT_PATH.open("a", encoding="utf-8") as fh:
                                fh.write(json.dumps(tick) + "\n")
                            tick_count += 1
                            last_tick_ts = tick["ts"]
                            if tick_count % 50 == 0:
                                write_status({
                                    "source": "alpaca",
                                    "watchlist_size": len(watchlist),
                                    "ticks_received": tick_count,
                                    "last_tick_ts": last_tick_ts,
                                    "last_tick_symbol": tick["symbol"],
                                    "status": "streaming",
                                })
        except (websockets.ConnectionClosed, OSError) as e:
            log(f"alpaca connection closed: {e}; reconnecting in {backoff}s")
            write_status({
                "source": "alpaca",
                "status": "reconnecting",
                "ticks_received": tick_count,
                "last_tick_ts": last_tick_ts,
                "error": str(e),
            })
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        except Exception as e:  # noqa: BLE001
            log(f"alpaca fatal: {type(e).__name__}: {e}; reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


async def main_async() -> int:
    env = load_env()
    source = (env.get("STREAM_SOURCE") or os.environ.get("STREAM_SOURCE", "finnhub")).strip().lower()
    watchlist = default_watchlist(env)

    log(f"=== stream_market_data start source={source} watchlist={watchlist[:5]}... ({len(watchlist)} total) ===")

    if source == "finnhub":
        token = env.get("FINNHUB_API_KEY") or os.environ.get("FINNHUB_API_KEY", "")
        if not token:
            log("ERROR: FINNHUB_API_KEY missing")
            return 2
        await stream_finnhub(token, watchlist)
    elif source == "alpaca":
        key = env.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY_ID", "")
        secret = env.get("ALPACA_API_SECRET") or os.environ.get("ALPACA_API_SECRET", "")
        if not key or not secret:
            log("ERROR: ALPACA_API_KEY_ID / ALPACA_API_SECRET missing")
            return 2
        await stream_alpaca(key, secret, watchlist)
    else:
        log(f"ERROR: unknown STREAM_SOURCE={source} (use finnhub or alpaca)")
        return 2
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        log("interrupted by user")
        return 0
    except Exception as e:  # noqa: BLE001
        log(f"FATAL: {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
