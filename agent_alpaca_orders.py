#!/usr/bin/env python3
"""agent_alpaca_orders.py — Catalyst Edge → Alpaca paper trader.

Reads top signals from combined_priority.csv + cross_border_convergence.json,
sizes a small position per signal, and either logs the decision (dry-run, default)
or places a bracket order on Alpaca paper.

SAFETY GUARDRAILS (all hardcoded, env-overridable):
  - ALPACA_AGENT_LIVE_ORDERS  must be exactly "1" to place real orders.
                              Default behavior = dry-run, no orders submitted.
  - ALPACA_MAX_POSITION_USD   max $/trade (default 50)
  - ALPACA_MAX_DAILY_LOSS_USD halt new orders if equity − last_equity < -X (default 200)
  - ALPACA_MAX_OPEN_POSITIONS skip new entries if already at limit (default 5)
  - ALPACA_TAKE_PROFIT_PCT    bracket take-profit % (default 0.05 = +5%)
  - ALPACA_STOP_LOSS_PCT      bracket stop-loss % (default 0.03 = -3%)
  - .agent_alpaca_halted file present in workspace → halt all orders

IDEMPOTENCY:
  client_order_id = "ce_<YYYY-MM-DD>_<TICKER>_<signal>"  Alpaca rejects duplicates,
  so re-running the script the same day is a no-op for already-placed orders.

OUTPUT:
  /home/operator/.openclaw/workspace/docs/data/alpaca_orders.json
  with full decision log: each candidate, why it was placed/skipped/rejected.

Reference: https://docs.alpaca.markets/reference/postorder
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
HALT_FILE = ROOT / ".agent_alpaca_halted"
ACCOUNT_JSON = ROOT / "docs/data/alpaca_account.json"
COMBINED_CSV = ROOT / "combined_priority.csv"
CB_JSON = ROOT / "docs/data/cross_border_convergence.json"
OUT = ROOT / "docs/data/alpaca_orders.json"
LOG = ROOT / "logs/alpaca_orders.log"
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
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def write_status(payload: dict) -> None:
    payload.setdefault("last_attempt_utc",
                       datetime.now(timezone.utc).isoformat(timespec="seconds"))
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Alpaca HTTP

def alpaca_call(method: str, base: str, path: str, key: str, secret: str,
                body: dict | None = None) -> tuple[int, dict | list, str]:
    """Returns (status, parsed_body, x_request_id)."""
    url = base.rstrip("/") + path
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"raw": raw[:500]}
            return resp.status, parsed, resp.headers.get("X-Request-ID", "")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"raw": raw}
        except Exception:
            parsed = {"raw": raw[:500]}
        return e.code, parsed, e.headers.get("X-Request-ID", "") if e.headers else ""


def get_latest_trade_price(base: str, key: str, secret: str, symbol: str) -> float | None:
    """Use the data API (broker base URL has /v2/stocks/{sym}/trades/latest as a passthrough)."""
    data_base = (os.environ.get("ALPACA_DATA_URL")
                 or "https://data.alpaca.markets").rstrip("/")
    code, body, _ = alpaca_call("GET", data_base, f"/v2/stocks/{symbol}/trades/latest",
                                key, secret)
    if code == 200 and isinstance(body, dict):
        trade = body.get("trade") or {}
        p = trade.get("p") or trade.get("price")
        try:
            return float(p) if p is not None else None
        except (TypeError, ValueError):
            return None
    return None


# ---------------------------------------------------------------------------
# Signal loading

def top_combined(n: int) -> list[dict]:
    if not COMBINED_CSV.exists():
        return []
    rows: list[dict] = []
    with COMBINED_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                r["_score"] = float(r.get("total_score") or 0)
            except ValueError:
                r["_score"] = 0.0
            rows.append(r)
    rows.sort(key=lambda r: r["_score"], reverse=True)
    out = []
    for r in rows:
        ticker = (r.get("ticker") or "").strip().upper()
        if not ticker or "." in ticker or len(ticker) > 5:
            continue
        out.append({
            "ticker": ticker,
            "score": r["_score"],
            "signal": "combined_priority",
            "side": "buy",  # combined_priority is bullish-only by construction
            "details": {
                "sec_score": r.get("sec_score"),
                "news_score": r.get("news_score"),
                "gapper_score": r.get("gapper_score"),
                "value_score": r.get("value_score"),
                "moat_score": r.get("moat_score"),
            },
        })
        if len(out) >= n:
            break
    return out


def top_crossborder(n: int) -> list[dict]:
    if not CB_JSON.exists():
        return []
    try:
        d = json.loads(CB_JSON.read_text())
    except Exception:
        return []
    setups = d.get("top_setups") or []
    out = []
    for s in setups:
        ticker = (s.get("us_ticker") or "").strip().upper()
        gap = s.get("us_gap_pct") or 0
        conv = (s.get("conviction") or "").upper()
        if not ticker or "." in ticker or len(ticker) > 5:
            continue
        if conv not in ("STRONG", "TRADE"):
            continue
        if gap is None:
            continue
        # Long-only on the agent first cut: skip negative-gap (bearish) setups.
        if float(gap) < 1.5:
            continue
        out.append({
            "ticker": ticker,
            "score": (4 if conv == "STRONG" else 3) + 0.01 * float(gap),
            "signal": f"crossborder_{conv.lower()}",
            "side": "buy",
            "details": {
                "us_gap_pct": gap,
                "foreign_gap_pct": s.get("foreign_gap_pct"),
                "conviction": conv,
                "score_4pt": s.get("score"),
            },
        })
        if len(out) >= n:
            break
    return out


def merge_signals(combined: list[dict], cb: list[dict]) -> list[dict]:
    """Dedup by ticker; combined_priority wins on score."""
    seen: dict[str, dict] = {}
    for sig in combined + cb:
        t = sig["ticker"]
        if t not in seen or sig["score"] > seen[t]["score"]:
            seen[t] = sig
    return sorted(seen.values(), key=lambda s: s["score"], reverse=True)


# ---------------------------------------------------------------------------
# Order construction

def build_bracket(symbol: str, qty: int, ref_price: float,
                  tp_pct: float, sl_pct: float, client_order_id: str) -> dict:
    tp = round(ref_price * (1.0 + tp_pct), 2)
    sl = round(ref_price * (1.0 - sl_pct), 2)
    return {
        "symbol": symbol,
        "qty": str(qty),
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
        "order_class": "bracket",
        "take_profit": {"limit_price": str(tp)},
        "stop_loss": {"stop_price": str(sl)},
        "client_order_id": client_order_id,
    }


# ---------------------------------------------------------------------------
# Main

def main() -> int:
    load_env()

    # Circuit-breaker check — if agent_kill_switch.py tripped earlier today,
    # skip everything until the operator removes the lockfile manually.
    kill_lock = ROOT / ".kill_switch_tripped"
    if kill_lock.exists():
        log(f"ABORT: kill switch lockfile present at {kill_lock} — "
            "no new orders. Remove the lockfile to resume.")
        write_status({
            "ok": False,
            "reason": "kill_switch_tripped",
            "lockfile": str(kill_lock),
        })
        return 0

    key = os.environ.get("ALPACA_API_KEY_ID", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET", "").strip()
    base = (os.environ.get("ALPACA_BASE_URL")
            or "https://paper-api.alpaca.markets").strip()

    if not key or not secret:
        log("ABORT: Alpaca keys missing")
        write_status({"ok": False, "reason": "alpaca_keys_missing"})
        return 0

    is_paper = "paper" in base.lower()
    live = os.environ.get("ALPACA_AGENT_LIVE_ORDERS", "").strip() == "1"

    # Hard guardrails
    max_pos_usd = env_float("ALPACA_MAX_POSITION_USD", 50.0)
    max_daily_loss = env_float("ALPACA_MAX_DAILY_LOSS_USD", 200.0)
    max_open_positions = env_int("ALPACA_MAX_OPEN_POSITIONS", 5)
    tp_pct = env_float("ALPACA_TAKE_PROFIT_PCT", 0.05)
    sl_pct = env_float("ALPACA_STOP_LOSS_PCT", 0.03)
    n_signals = env_int("ALPACA_MAX_SIGNALS_PER_RUN", 5)

    # Halt checks
    halted = False
    halt_reason = None

    if HALT_FILE.exists():
        halted = True
        halt_reason = f"halt_file_present: {HALT_FILE.name}"

    # Account snapshot to enforce daily-loss kill switch + position cap
    code, account, req_id = alpaca_call("GET", base, "/v2/account", key, secret)
    if code != 200 or not isinstance(account, dict):
        log(f"ABORT account: HTTP {code} req_id={req_id}")
        write_status({
            "ok": False,
            "reason": f"account_fetch_failed_{code}",
            "x_request_id": req_id,
        })
        return 0

    try:
        equity = float(account.get("equity") or 0)
        last_equity = float(account.get("last_equity") or equity)
    except (TypeError, ValueError):
        equity = last_equity = 0.0
    pl_today = round(equity - last_equity, 2)

    if not halted and pl_today <= -abs(max_daily_loss):
        halted = True
        halt_reason = f"daily_loss_kill_switch: pl_today=${pl_today} <= -${max_daily_loss}"

    if not halted and account.get("trading_blocked"):
        halted = True
        halt_reason = "trading_blocked_on_account"

    # Existing positions + open orders
    code_p, positions, _ = alpaca_call("GET", base, "/v2/positions", key, secret)
    if code_p != 200 or not isinstance(positions, list):
        positions = []
    open_symbols = {(p.get("symbol") or "").upper() for p in positions}

    code_o, open_orders, _ = alpaca_call(
        "GET", base, "/v2/orders?status=open&limit=200", key, secret)
    if code_o != 200 or not isinstance(open_orders, list):
        open_orders = []
    pending_symbols = {(o.get("symbol") or "").upper() for o in open_orders}

    log(f"context | mode={'paper' if is_paper else 'LIVE'} live_orders={live} "
        f"equity=${equity:,.2f} pl_today=${pl_today} positions={len(positions)} "
        f"halted={halted}")

    # Build the candidate list
    combined = top_combined(n_signals)
    cb = top_crossborder(n_signals)
    candidates = merge_signals(combined, cb)[:n_signals]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    decisions: list[dict] = []
    placed = skipped = rejected = 0

    for sig in candidates:
        ticker = sig["ticker"]
        client_order_id = f"ce_{today}_{ticker}_{sig['signal']}"

        decision = {
            "ticker": ticker,
            "signal": sig["signal"],
            "score": round(sig["score"], 2),
            "side": sig["side"],
            "client_order_id": client_order_id,
            "details": sig.get("details", {}),
        }

        if halted:
            decision["status"] = "skipped"
            decision["reason"] = halt_reason
            decisions.append(decision); skipped += 1; continue

        if ticker in open_symbols:
            decision["status"] = "skipped"
            decision["reason"] = "already_in_open_position"
            decisions.append(decision); skipped += 1; continue

        if ticker in pending_symbols:
            decision["status"] = "skipped"
            decision["reason"] = "already_has_open_order"
            decisions.append(decision); skipped += 1; continue

        if len(open_symbols) + placed >= max_open_positions:
            decision["status"] = "skipped"
            decision["reason"] = f"max_open_positions_{max_open_positions}_reached"
            decisions.append(decision); skipped += 1; continue

        # Get current price
        price = get_latest_trade_price(base, key, secret, ticker)
        if not price or price <= 0:
            decision["status"] = "skipped"
            decision["reason"] = "no_quote_available"
            decisions.append(decision); skipped += 1; continue

        decision["est_price"] = round(price, 2)
        qty = int(math.floor(max_pos_usd / price))
        if qty < 1:
            decision["status"] = "skipped"
            decision["reason"] = f"price_${price:.2f}_exceeds_max_pos_${max_pos_usd}"
            decisions.append(decision); skipped += 1; continue

        decision["qty"] = qty
        decision["est_position_usd"] = round(qty * price, 2)
        decision["take_profit_price"] = round(price * (1.0 + tp_pct), 2)
        decision["stop_loss_price"] = round(price * (1.0 - sl_pct), 2)

        order = build_bracket(ticker, qty, price, tp_pct, sl_pct, client_order_id)

        if not live:
            decision["status"] = "dry_run"
            decision["reason"] = "ALPACA_AGENT_LIVE_ORDERS!=1 (default safe mode)"
            decisions.append(decision); placed += 1; continue

        # LIVE path: actually POST the order
        c2, body, req_id_o = alpaca_call("POST", base, "/v2/orders", key, secret, order)
        decision["x_request_id"] = req_id_o
        if c2 in (200, 201) and isinstance(body, dict):
            decision["status"] = "placed"
            decision["alpaca_order_id"] = body.get("id")
            decision["alpaca_status"] = body.get("status")
            placed += 1
        else:
            err_msg = (body.get("message") if isinstance(body, dict) else None) or str(body)[:200]
            decision["status"] = "rejected"
            decision["reason"] = f"http_{c2}: {err_msg}"
            rejected += 1
        decisions.append(decision)

    summary = {
        "candidates": len(candidates),
        "placed_or_dry_run": placed,
        "skipped": skipped,
        "rejected": rejected,
    }
    log(f"summary | candidates={summary['candidates']} placed={placed} "
        f"skipped={skipped} rejected={rejected} live_orders={live}")

    write_status({
        "ok": True,
        "is_paper": is_paper,
        "live_orders_enabled": live,
        "halted": halted,
        "halt_reason": halt_reason,
        "guardrails": {
            "max_position_usd": max_pos_usd,
            "max_daily_loss_usd": max_daily_loss,
            "max_open_positions": max_open_positions,
            "take_profit_pct": tp_pct,
            "stop_loss_pct": sl_pct,
        },
        "account": {
            "equity": equity,
            "last_equity": last_equity,
            "pl_today_usd": pl_today,
            "open_positions": len(positions),
        },
        "summary": summary,
        "decisions": decisions,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
