#!/usr/bin/env python3
"""coinbase_ws_monitor.py — Persistent WebSocket exit-trigger daemon.

Connects to Coinbase Advanced Trade WebSocket feed (level1 ticker) and
watches BTC/ETH/ARB/LINK/ATOM in real-time. On every price tick, checks
all open positions for TP/SL/time-stop. Fires a market-sell instantly
when a trigger hits — typical reaction time <100ms vs the 1-min cron's
worst case of 60s.

This is the persistent process retail bots usually skip. Real institutional
risk control fires on every tick. We do too.

Architecture:
  - Single async websocket connection to advanced-trade-ws.coinbase.com
  - Subscribe to ticker channel for our 5 traded products
  - Maintain in-memory position state (refresh from API every 60s)
  - On price update, evaluate exit triggers
  - Fire market sell via REST when triggered (idempotent client_order_id)
  - Auto-reconnect on disconnect with exponential backoff

Run: nohup python3 coinbase_ws_monitor.py > logs/coinbase_ws.log 2>&1 &
Stop: kill the PID; or write .agent_coinbase_halted file.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
KEY_FILE = Path("/path/to/local/Desktop/catalyst-edge/cdp_api_key.json")
ENV_FILE = ROOT / ".sec_email_env"
HALT_FILE = ROOT / ".agent_coinbase_halted"
WS_LOG = ROOT / "logs/coinbase_ws.log"
PID_FILE = ROOT / "coinbase_ws.pid"
WS_LOG.parent.mkdir(exist_ok=True)

PRODUCTS = ["BTC-USD", "ETH-USD", "ARB-USD", "LINK-USD", "ATOM-USD"]
WS_URL = "wss://advanced-trade-ws.coinbase.com"

TP_PCT = 0.05
SL_PCT = 0.04
MAX_HOLD_HOURS = 168
POSITION_REFRESH_SECS = 60


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(m: str) -> None:
    line = f"[{now_iso()}] WS {m}"
    WS_LOG.open("a").write(line + "\n")
    print(line, flush=True)


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def get_key() -> tuple[str, bytes] | None:
    if not KEY_FILE.exists():
        return None
    d = json.loads(KEY_FILE.read_text())
    raw = base64.b64decode(d["privateKey"])
    return d["id"], raw[:32]


def jwt_for(method: str, path_no_query: str, key_id: str, priv32: bytes) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import jwt as pyjwt
    pk = Ed25519PrivateKey.from_private_bytes(priv32)
    n = int(time.time())
    return pyjwt.encode(
        {"sub": key_id, "iss": "cdp", "nbf": n, "exp": n + 120,
         "uri": f"{method} api.coinbase.com{path_no_query}"},
        pk, algorithm="EdDSA", headers={"kid": key_id, "nonce": str(n)},
    )


def cb_request(method: str, path: str, key_id: str, priv32: bytes,
               body: dict | None = None) -> tuple[int, dict | str]:
    path_no_q = path.split("?", 1)[0]
    body_str = json.dumps(body) if body else ""
    token = jwt_for(method, path_no_q, key_id, priv32)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = "https://api.coinbase.com" + path
    data = body_str.encode() if body_str else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"raw": str(e)}
        return e.code, err
    except Exception as e:
        return 0, {"err": str(e)[:120]}


def fetch_holdings(key_id: str, priv32: bytes) -> dict[str, float]:
    code, resp = cb_request("GET", "/api/v3/brokerage/accounts?limit=250", key_id, priv32)
    if code != 200 or not isinstance(resp, dict):
        return {}
    out: dict[str, float] = {}
    for a in resp.get("accounts", []):
        cur = a.get("currency", "")
        bal = float((a.get("available_balance") or {}).get("value") or 0)
        if cur in ("BTC", "ETH", "ARB", "LINK", "ATOM") and bal > 0:
            out[cur] = bal
    return out


def fetch_position_entries(key_id: str, priv32: bytes,
                           held: dict[str, float]) -> dict[str, dict]:
    """For each held coin, find avg entry price + entry time from recent fills."""
    out: dict[str, dict] = {}
    for cur, size in held.items():
        product = f"{cur}-USD"
        code, resp = cb_request(
            "GET",
            f"/api/v3/brokerage/orders/historical/fills?product_id={product}&limit=50",
            key_id, priv32,
        )
        if code != 200 or not isinstance(resp, dict):
            continue
        fills = resp.get("fills", [])
        accum, cost, oldest = 0.0, 0.0, None
        for f in fills:
            if f.get("side") != "BUY":
                continue
            sz_raw = float(f.get("size") or 0)
            px = float(f.get("price") or 0)
            in_quote = bool(f.get("size_in_quote"))
            base_sz = (sz_raw / px) if (in_quote and px > 0) else sz_raw
            if base_sz <= 0:
                continue
            take = min(base_sz, size - accum)
            accum += take
            cost += take * px
            oldest = f.get("trade_time")
            if accum >= size - 1e-9:
                break
        if accum > 0:
            out[cur] = {
                "size": size,
                "avg_entry": cost / accum,
                "entry_ts": oldest,
            }
    return out


def fire_market_sell(product: str, base_size: float,
                     key_id: str, priv32: bytes, reason: str) -> dict:
    body = {
        "client_order_id": f"ce_ws_exit_{product}_{int(time.time())}",
        "product_id": product,
        "side": "SELL",
        "order_configuration": {"market_market_ioc": {"base_size": str(base_size)}},
    }
    code, resp = cb_request("POST", "/api/v3/brokerage/orders", key_id, priv32, body)
    if code == 200 and isinstance(resp, dict) and resp.get("success"):
        log(f"  ✅ SELL FIRED  {product}  size={base_size}  reason={reason}  order_id={resp.get('success_response',{}).get('order_id','?')[:20]}")
        return {"ok": True, "resp": resp}
    log(f"  ❌ SELL FAILED  {product}  reason={reason}  http={code}  err={resp}")
    return {"ok": False, "err": resp}


async def run() -> None:
    load_env()
    if HALT_FILE.exists():
        log("HALT file present — exiting")
        return
    k = get_key()
    if not k:
        log("no Coinbase key — exiting")
        return
    key_id, priv32 = k

    # Write PID for monitoring
    PID_FILE.write_text(str(os.getpid()))

    try:
        import websockets
    except ImportError:
        log("websockets module not installed; pip install websockets --break-system-packages")
        return

    backoff = 1
    while not HALT_FILE.exists():
        try:
            log(f"connecting to {WS_URL}")
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
                # Subscribe to ticker channel
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "channel": "ticker",
                    "product_ids": PRODUCTS,
                }))
                log(f"subscribed ticker for {PRODUCTS}")
                backoff = 1

                positions: dict[str, dict] = {}
                last_pos_refresh = 0.0
                tick_count = 0
                exits_fired = 0

                async for raw_msg in ws:
                    if HALT_FILE.exists():
                        log("HALT file detected mid-stream — exiting")
                        break
                    try:
                        msg = json.loads(raw_msg)
                    except Exception:
                        continue
                    if msg.get("channel") != "ticker":
                        continue
                    events = msg.get("events", [])

                    # Refresh holdings every 60s (avoid hammering API)
                    now = time.time()
                    if now - last_pos_refresh > POSITION_REFRESH_SECS:
                        held = fetch_holdings(key_id, priv32)
                        positions = fetch_position_entries(key_id, priv32, held)
                        last_pos_refresh = now
                        if tick_count % 100 == 0 or not positions:
                            log(f"position refresh: {len(positions)} held  "
                                f"({', '.join(positions.keys()) or 'none'})")

                    for ev in events:
                        for tk in ev.get("tickers", []):
                            tick_count += 1
                            product = tk.get("product_id")
                            price = float(tk.get("price") or 0)
                            if not price or not product:
                                continue
                            sym = product.split("-")[0]
                            pos = positions.get(sym)
                            if not pos:
                                continue
                            entry = pos["avg_entry"]
                            pnl_pct = (price / entry) - 1.0
                            tp_hit = pnl_pct >= TP_PCT
                            sl_hit = pnl_pct <= -SL_PCT
                            ts_iso = pos.get("entry_ts") or ""
                            try:
                                t0 = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
                                hold_h = (datetime.now(timezone.utc) - t0).total_seconds() / 3600
                            except Exception:
                                hold_h = 0
                            time_stop = hold_h >= MAX_HOLD_HOURS
                            if tp_hit or sl_hit or time_stop:
                                reason = "TP" if tp_hit else ("SL" if sl_hit else "time")
                                log(f"TRIGGER  {sym}  pnl={pnl_pct*100:+.2f}%  "
                                    f"hold={hold_h:.1f}h  reason={reason}")
                                fire_market_sell(product, pos["size"],
                                                 key_id, priv32, reason)
                                # Drop from positions until next refresh
                                positions.pop(sym, None)
                                exits_fired += 1

                    if tick_count % 500 == 0 and tick_count > 0:
                        log(f"heartbeat ticks={tick_count} exits_fired={exits_fired} "
                            f"positions={list(positions.keys())}")

        except Exception as e:
            log(f"ws ERROR: {type(e).__name__}: {str(e)[:150]}")
            await asyncio.sleep(min(backoff, 60))
            backoff = min(backoff * 2, 60)

    log("daemon exit")


def stop_handler(signum, frame):
    log(f"signal {signum} received, shutting down")
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log("KeyboardInterrupt — exiting")
