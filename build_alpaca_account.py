#!/usr/bin/env python3
"""build_alpaca_account.py — read-only Alpaca paper-account snapshot.

Reads ALPACA_API_KEY_ID, ALPACA_API_SECRET, ALPACA_BASE_URL from .sec_email_env.
If keys missing → writes {"ok":false,"reason":"alpaca_keys_missing"} and exits 0.
If present → GETs /v2/account, /v2/positions, /v2/orders → single normalized JSON.

Output: /home/operator/.openclaw/workspace/docs/data/alpaca_account.json

Reference: https://docs.alpaca.markets/reference/getaccount-1
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
OUT = ROOT / "docs/data/alpaca_account.json"
LOG = ROOT / "logs/alpaca_account.log"
OUT.parent.mkdir(parents=True, exist_ok=True)
LOG.parent.mkdir(exist_ok=True)


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()  # tolerate leading/trailing whitespace
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def write_status(payload: dict) -> None:
    payload.setdefault("last_attempt_utc", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True))


def alpaca_get(base: str, path: str, key: str, secret: str) -> tuple[int, dict | list, str]:
    """Returns (status_code, parsed_json, x_request_id)."""
    req = urllib.request.Request(
        base.rstrip("/") + path,
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, data, resp.headers.get("X-Request-ID", "")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body[:500]}
        return e.code, data, e.headers.get("X-Request-ID", "")


def to_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    load_env()
    key = os.environ.get("ALPACA_API_KEY_ID", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET", "").strip()
    base = (os.environ.get("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets").strip()

    if not key or not secret:
        log("ABORT: ALPACA_API_KEY_ID or ALPACA_API_SECRET missing")
        write_status({"ok": False, "reason": "alpaca_keys_missing"})
        return 0

    is_paper = "paper" in base.lower()

    # 1. Account snapshot
    code, account, req_id = alpaca_get(base, "/v2/account", key, secret)
    if code != 200 or not isinstance(account, dict):
        log(f"ABORT account: HTTP {code} req_id={req_id} body={str(account)[:200]}")
        write_status({
            "ok": False,
            "reason": f"account_fetch_failed_{code}",
            "x_request_id": req_id,
            "is_paper": is_paper,
        })
        return 0

    # 2. Positions
    code_p, positions, req_id_p = alpaca_get(base, "/v2/positions", key, secret)
    if code_p != 200 or not isinstance(positions, list):
        positions = []
        log(f"WARN positions: HTTP {code_p} req_id={req_id_p}")

    # 3. Recent orders (open + 50 most recent regardless of status)
    code_o, open_orders, req_id_o = alpaca_get(base, "/v2/orders?status=open&limit=50", key, secret)
    if code_o != 200 or not isinstance(open_orders, list):
        open_orders = []
        log(f"WARN orders: HTTP {code_o} req_id={req_id_o}")

    # Normalize positions
    norm_positions = []
    for p in positions:
        norm_positions.append({
            "symbol": p.get("symbol"),
            "qty": to_float(p.get("qty")),
            "side": p.get("side"),
            "avg_entry_price": to_float(p.get("avg_entry_price")),
            "current_price": to_float(p.get("current_price")),
            "market_value": to_float(p.get("market_value")),
            "unrealized_pl": to_float(p.get("unrealized_pl")),
            "unrealized_plpc": to_float(p.get("unrealized_plpc")),
            "asset_class": p.get("asset_class"),
        })

    # Normalize open orders
    norm_orders = []
    for o in open_orders:
        norm_orders.append({
            "id": o.get("id"),
            "symbol": o.get("symbol"),
            "side": o.get("side"),
            "qty": to_float(o.get("qty")),
            "type": o.get("type"),
            "limit_price": to_float(o.get("limit_price")),
            "stop_price": to_float(o.get("stop_price")),
            "submitted_at": o.get("submitted_at"),
            "status": o.get("status"),
        })

    payload = {
        "ok": True,
        "is_paper": is_paper,
        "x_request_id": req_id,
        "account": {
            "account_number": account.get("account_number"),
            "status": account.get("status"),
            "currency": account.get("currency"),
            "equity": to_float(account.get("equity")),
            "last_equity": to_float(account.get("last_equity")),
            "cash": to_float(account.get("cash")),
            "buying_power": to_float(account.get("buying_power")),
            "long_market_value": to_float(account.get("long_market_value")),
            "short_market_value": to_float(account.get("short_market_value")),
            "daytrade_count": account.get("daytrade_count"),
            "pattern_day_trader": account.get("pattern_day_trader"),
            "trading_blocked": account.get("trading_blocked"),
            "account_blocked": account.get("account_blocked"),
            "created_at": account.get("created_at"),
        },
        "positions_count": len(norm_positions),
        "positions": norm_positions[:100],
        "open_orders_count": len(norm_orders),
        "open_orders": norm_orders[:100],
    }

    # P/L since open
    eq = payload["account"]["equity"] or 0.0
    last_eq = payload["account"]["last_equity"] or eq
    payload["pl_today_usd"] = round(eq - last_eq, 2)
    payload["pl_today_pct"] = round(100.0 * (eq - last_eq) / last_eq, 4) if last_eq else 0.0

    log(
        f"snapshot ok | mode={'paper' if is_paper else 'LIVE'} "
        f"equity=${eq:,.2f} bp=${payload['account']['buying_power']:,.2f} "
        f"positions={len(norm_positions)} open_orders={len(norm_orders)} "
        f"pl_today=${payload['pl_today_usd']} req_id={req_id}"
    )
    write_status(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
