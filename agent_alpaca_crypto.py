#!/usr/bin/env python3
"""agent_alpaca_crypto.py — Catalyst Edge → Alpaca crypto paper trader.

Parallels agent_alpaca_orders.py but for crypto (BTC, ETH, SOL, LTC, AVAX).

Signal sources (CSVs produced by existing spoke builders, droplet-served at /):
  - btc_etf_flows.csv         (BTC ETF dollar volume + regime)
  - defi_liquidations.csv     (crypto-stress label across top TVL protocols)
  - eth_gas.csv               (base_fee_gwei + congestion_label)

Score per symbol (0-3):
  +1 if BTC heavy-interest (sum ETF dollar_volume_usd > $2B)
  +1 if broad-crypto calm  (defi majority stress_label=drift, |avg 1d| <= 2%)
  +1 if ETH gas relief     (only counts for ETH/USD)
Threshold for placing an order: score >= 2.

SAFETY GUARDRAILS (env-overridable):
  ALPACA_AGENT_CRYPTO_LIVE        must be exactly "1" to place real orders
  ALPACA_CRYPTO_MAX_POSITION_USD  default 25
  ALPACA_CRYPTO_MAX_DAILY_LOSS_USD default 100
  ALPACA_CRYPTO_MAX_OPEN_POSITIONS default 3
  ALPACA_CRYPTO_TP_PCT            default 0.03
  ALPACA_CRYPTO_SL_PCT            default 0.02
  .agent_alpaca_halted            shared halt switch (halts crypto + equity)

Crypto on Alpaca:
  - Notional ordering: {notional: "25", side: buy, type: market, time_in_force: gtc}
  - No native bracket orders → place entry, then a separate limit-sell + stop-sell
    using paired client_order_ids (ce_crypto_<date>_<sym>_entry/_tp/_sl).

Output: /home/operator/.openclaw/workspace/docs/data/alpaca_crypto.json
"""
from __future__ import annotations

import csv
import json
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
ETF_CSV = ROOT / "docs/btc_etf_flows.csv"
DEFI_CSV = ROOT / "docs/defi_liquidations.csv"
GAS_CSV = ROOT / "eth_gas.csv"
OUT = ROOT / "docs/data/alpaca_crypto.json"
LOG = ROOT / "logs/alpaca_crypto.log"
OUT.parent.mkdir(parents=True, exist_ok=True)
LOG.parent.mkdir(exist_ok=True)

UNIVERSE = ["BTC/USD", "ETH/USD", "SOL/USD", "LTC/USD", "AVAX/USD"]


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


def alpaca_call(method: str, base: str, path: str, key: str, secret: str,
                body: dict | None = None) -> tuple[int, dict | list, str]:
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


def crypto_latest_price(symbol: str, key: str, secret: str) -> float | None:
    """GET /v1beta3/crypto/us/latest/trades?symbols=BTC%2FUSD"""
    data_base = (os.environ.get("ALPACA_DATA_URL")
                 or "https://data.alpaca.markets").rstrip("/")
    url = (f"{data_base}/v1beta3/crypto/us/latest/trades"
           f"?symbols={urllib.parse.quote(symbol)}")
    code, body, _ = alpaca_call("GET", "", url, key, secret) if False else (None, None, None)
    # alpaca_call expects (method, base, path); pass empty base + full URL doesn't work cleanly.
    # Use a direct fetch:
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            trades = data.get("trades") or {}
            t = trades.get(symbol) or {}
            p = t.get("p") or t.get("price")
            return float(p) if p is not None else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Signal scoring

def score_btc_etf() -> tuple[bool, dict]:
    """Returns (signal_fires, details)."""
    if not ETF_CSV.exists():
        return False, {"reason": "btc_etf_flows.csv missing"}
    total_dollar_vol = 0.0
    rows = 0
    pos_changes = 0
    with ETF_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                dv = float(r.get("dollar_volume_usd") or 0)
                pc = float(r.get("pct_change") or 0)
            except ValueError:
                continue
            total_dollar_vol += dv
            rows += 1
            if pc > 0:
                pos_changes += 1
    fires = total_dollar_vol > 2_000_000_000
    return fires, {
        "total_dollar_volume_usd": round(total_dollar_vol, 0),
        "rows": rows,
        "positive_change_count": pos_changes,
        "threshold_usd": 2_000_000_000,
    }


def score_defi_calm() -> tuple[bool, dict]:
    if not DEFI_CSV.exists():
        return False, {"reason": "defi_liquidations.csv missing"}
    drift = total = 0
    abs_changes: list[float] = []
    with DEFI_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            total += 1
            if (r.get("stress_label") or "").lower() == "drift":
                drift += 1
            try:
                abs_changes.append(abs(float(r.get("change_1d_pct") or 0)))
            except ValueError:
                pass
    if not total:
        return False, {"reason": "no defi rows"}
    drift_share = drift / total
    avg_abs_1d = sum(abs_changes) / len(abs_changes) if abs_changes else 0.0
    fires = drift_share >= 0.5 and avg_abs_1d <= 2.0
    return fires, {
        "drift_share": round(drift_share, 3),
        "avg_abs_1d_pct": round(avg_abs_1d, 3),
        "rows": total,
        "thresholds": {"drift_share_min": 0.5, "avg_abs_1d_max": 2.0},
    }


def score_eth_gas() -> tuple[bool, dict]:
    if not GAS_CSV.exists():
        return False, {"reason": "eth_gas.csv missing"}
    last = None
    with GAS_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            last = r
    if not last:
        return False, {"reason": "no gas rows"}
    try:
        base_fee = float(last.get("base_fee_gwei") or 0)
    except ValueError:
        base_fee = 0
    congestion = (last.get("congestion_label") or "").lower()
    fires = base_fee < 1.0 and congestion in ("low", "medium")
    return fires, {
        "base_fee_gwei": base_fee,
        "congestion_label": congestion,
        "captured_at": last.get("captured_at"),
        "thresholds": {"base_fee_gwei_max": 1.0, "congestion_allowed": ["low", "medium"]},
    }


def score_symbol(symbol: str, btc_fire: bool, defi_fire: bool, gas_fire: bool) -> int:
    """Return 0-3 score for the symbol."""
    score = 0
    # Broad-crypto calm gives all majors +1
    if defi_fire:
        score += 1
    # BTC ETF heavy-interest gives BTC, SOL, LTC, AVAX +1 (correlated majors); ETH only via gas
    if btc_fire and symbol != "ETH/USD":
        score += 1
    # ETH gas relief gives ETH +1
    if gas_fire and symbol == "ETH/USD":
        score += 1
    # ETH also benefits from BTC heavy-interest as a major
    if btc_fire and symbol == "ETH/USD":
        score += 1
    return score


# ---------------------------------------------------------------------------
# Order placement

def submit_market_buy_notional(base: str, key: str, secret: str, symbol: str,
                               notional_usd: float, client_order_id: str) -> tuple[int, dict, str]:
    body = {
        "symbol": symbol,
        "notional": str(notional_usd),
        "side": "buy",
        "type": "market",
        "time_in_force": "gtc",
        "client_order_id": client_order_id,
    }
    return alpaca_call("POST", base, "/v2/orders", key, secret, body)


def submit_limit_sell(base: str, key: str, secret: str, symbol: str, qty: float,
                      limit_price: float, client_order_id: str) -> tuple[int, dict, str]:
    body = {
        "symbol": symbol,
        "qty": str(qty),
        "side": "sell",
        "type": "limit",
        "limit_price": str(round(limit_price, 2)),
        "time_in_force": "gtc",
        "client_order_id": client_order_id,
    }
    return alpaca_call("POST", base, "/v2/orders", key, secret, body)


def submit_stop_sell(base: str, key: str, secret: str, symbol: str, qty: float,
                     stop_price: float, client_order_id: str) -> tuple[int, dict, str]:
    body = {
        "symbol": symbol,
        "qty": str(qty),
        "side": "sell",
        "type": "stop",
        "stop_price": str(round(stop_price, 2)),
        "time_in_force": "gtc",
        "client_order_id": client_order_id,
    }
    return alpaca_call("POST", base, "/v2/orders", key, secret, body)


# ---------------------------------------------------------------------------
# Main

def main() -> int:
    load_env()

    # Circuit-breaker check
    kill_lock = ROOT / ".kill_switch_tripped"
    if kill_lock.exists():
        log(f"ABORT: kill switch lockfile present at {kill_lock} — no new crypto orders.")
        write_status({"ok": False, "reason": "kill_switch_tripped"})
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
    live = os.environ.get("ALPACA_AGENT_CRYPTO_LIVE", "").strip() == "1"

    max_pos_usd = env_float("ALPACA_CRYPTO_MAX_POSITION_USD", 25.0)
    max_daily_loss = env_float("ALPACA_CRYPTO_MAX_DAILY_LOSS_USD", 100.0)
    max_open = env_int("ALPACA_CRYPTO_MAX_OPEN_POSITIONS", 3)
    tp_pct = env_float("ALPACA_CRYPTO_TP_PCT", 0.03)
    sl_pct = env_float("ALPACA_CRYPTO_SL_PCT", 0.02)

    halted = False
    halt_reason = None
    if HALT_FILE.exists():
        halted = True
        halt_reason = f"halt_file_present: {HALT_FILE.name}"

    # Account check
    code, account, req_id = alpaca_call("GET", base, "/v2/account", key, secret)
    if code != 200 or not isinstance(account, dict):
        log(f"ABORT account: HTTP {code}")
        write_status({"ok": False, "reason": f"account_fetch_failed_{code}",
                      "x_request_id": req_id})
        return 0

    try:
        equity = float(account.get("equity") or 0)
        last_equity = float(account.get("last_equity") or equity)
    except (TypeError, ValueError):
        equity = last_equity = 0.0
    pl_today = round(equity - last_equity, 2)

    if not halted and pl_today <= -abs(max_daily_loss):
        halted = True
        halt_reason = f"daily_loss_kill: pl_today=${pl_today} <= -${max_daily_loss}"

    # Existing crypto positions
    code_p, positions, _ = alpaca_call("GET", base, "/v2/positions", key, secret)
    if code_p != 200 or not isinstance(positions, list):
        positions = []
    open_crypto_symbols = {
        (p.get("symbol") or "")
        for p in positions
        if (p.get("asset_class") == "crypto"
            or "/" in (p.get("symbol") or ""))
    }

    # Score signals
    btc_fire, btc_details = score_btc_etf()
    defi_fire, defi_details = score_defi_calm()
    gas_fire, gas_details = score_eth_gas()

    log(f"signals | btc_etf_fires={btc_fire} defi_calm_fires={defi_fire} eth_gas_fires={gas_fire}")
    log(f"context | mode={'paper' if is_paper else 'LIVE'} live={live} "
        f"equity=${equity:,.2f} pl_today=${pl_today} crypto_positions={len(open_crypto_symbols)} "
        f"halted={halted}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    decisions: list[dict] = []
    placed = skipped = rejected = 0

    for sym in UNIVERSE:
        score = score_symbol(sym, btc_fire, defi_fire, gas_fire)
        client_id_base = f"ce_crypto_{today}_{sym.replace('/', '_')}"
        decision = {
            "ticker": sym,
            "signal": "crypto_multifactor",
            "score": score,
            "side": "buy",
            "client_order_id": f"{client_id_base}_entry",
            "details": {
                "btc_etf_fires": btc_fire,
                "defi_calm_fires": defi_fire,
                "eth_gas_fires": gas_fire,
            },
        }

        if score < 2:
            decision["status"] = "skipped"
            decision["reason"] = f"score_{score}_below_threshold_2"
            decisions.append(decision); skipped += 1; continue

        if halted:
            decision["status"] = "skipped"
            decision["reason"] = halt_reason
            decisions.append(decision); skipped += 1; continue

        if sym in open_crypto_symbols:
            decision["status"] = "skipped"
            decision["reason"] = "already_in_open_position"
            decisions.append(decision); skipped += 1; continue

        if len(open_crypto_symbols) + placed >= max_open:
            decision["status"] = "skipped"
            decision["reason"] = f"max_open_positions_{max_open}_reached"
            decisions.append(decision); skipped += 1; continue

        price = crypto_latest_price(sym, key, secret)
        if not price or price <= 0:
            decision["status"] = "skipped"
            decision["reason"] = "no_quote_available"
            decisions.append(decision); skipped += 1; continue

        decision["est_price"] = round(price, 2)
        decision["est_position_usd"] = round(max_pos_usd, 2)
        decision["est_qty"] = round(max_pos_usd / price, 8)
        decision["take_profit_price"] = round(price * (1.0 + tp_pct), 2)
        decision["stop_loss_price"] = round(price * (1.0 - sl_pct), 2)

        if not live:
            decision["status"] = "dry_run"
            decision["reason"] = "ALPACA_AGENT_CRYPTO_LIVE!=1 (default safe mode)"
            decisions.append(decision); placed += 1; continue

        # LIVE path: submit market entry, then TP + SL legs
        c1, body1, req_id1 = submit_market_buy_notional(
            base, key, secret, sym, max_pos_usd, decision["client_order_id"])
        decision["x_request_id_entry"] = req_id1
        if c1 not in (200, 201) or not isinstance(body1, dict):
            err = (body1.get("message") if isinstance(body1, dict) else None) or str(body1)[:200]
            decision["status"] = "rejected"
            decision["reason"] = f"entry_http_{c1}: {err}"
            decisions.append(decision); rejected += 1; continue

        decision["alpaca_order_id_entry"] = body1.get("id")
        decision["alpaca_status_entry"] = body1.get("status")

        # Estimate qty for TP/SL legs (Alpaca will fill the buy first; legs may be rejected
        # if qty is wrong — we use the estimate). For paper this is fine.
        qty_est = decision["est_qty"]

        c2, body2, _ = submit_limit_sell(
            base, key, secret, sym, qty_est,
            decision["take_profit_price"], f"{client_id_base}_tp")
        if c2 in (200, 201) and isinstance(body2, dict):
            decision["alpaca_order_id_tp"] = body2.get("id")
        else:
            decision["tp_warning"] = f"http_{c2}"

        c3, body3, _ = submit_stop_sell(
            base, key, secret, sym, qty_est,
            decision["stop_loss_price"], f"{client_id_base}_sl")
        if c3 in (200, 201) and isinstance(body3, dict):
            decision["alpaca_order_id_sl"] = body3.get("id")
        else:
            decision["sl_warning"] = f"http_{c3}"

        decision["status"] = "placed"
        placed += 1
        decisions.append(decision)

    summary = {
        "candidates": len(UNIVERSE),
        "placed_or_dry_run": placed,
        "skipped": skipped,
        "rejected": rejected,
    }
    log(f"summary | candidates={summary['candidates']} placed={placed} "
        f"skipped={skipped} rejected={rejected} live={live}")

    write_status({
        "ok": True,
        "is_paper": is_paper,
        "live_orders_enabled": live,
        "halted": halted,
        "halt_reason": halt_reason,
        "guardrails": {
            "max_position_usd": max_pos_usd,
            "max_daily_loss_usd": max_daily_loss,
            "max_open_positions": max_open,
            "take_profit_pct": tp_pct,
            "stop_loss_pct": sl_pct,
        },
        "signals": {
            "btc_etf": {"fires": btc_fire, **btc_details},
            "defi_calm": {"fires": defi_fire, **defi_details},
            "eth_gas": {"fires": gas_fire, **gas_details},
        },
        "account": {
            "equity": equity,
            "last_equity": last_equity,
            "pl_today_usd": pl_today,
            "open_crypto_positions": len(open_crypto_symbols),
        },
        "summary": summary,
        "decisions": decisions,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
