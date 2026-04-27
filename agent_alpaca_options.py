#!/usr/bin/env python3
"""agent_alpaca_options.py — Alpaca options paper trader (long-call first cut).

Reads unusual-flow option legs from /data/options_flow.json, picks top 5 calls
by volume, places single-leg market BUY orders on Alpaca paper.

Long-only on calls (bullish setups) for the first cut. No bracket — Alpaca paper
options doesn't support brackets natively. Outcomes tracker handles exit accounting.

SAFETY GUARDRAILS (env-overridable):
  ALPACA_AGENT_OPTIONS_LIVE         must be exactly "1" (default = dry-run)
  ALPACA_OPTIONS_MAX_POSITION_USD   default 200 (per-contract premium cap)
  ALPACA_OPTIONS_MAX_DAILY_LOSS_USD default 300
  ALPACA_OPTIONS_MAX_OPEN_POSITIONS default 3
  .agent_alpaca_halted file         shared halt switch

IDEMPOTENCY:
  client_order_id = ce_opt_<YYYY-MM-DD>_<OCC_SYMBOL>_entry

Reference: https://docs.alpaca.markets/reference/postorder
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
HALT_FILE = ROOT / ".agent_alpaca_halted"
OPTIONS_FLOW_JSON = ROOT / "docs/data/options_flow.json"
OUT = ROOT / "docs/data/alpaca_options.json"
LOG = ROOT / "logs/alpaca_options.log"
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


def to_float(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def load_call_candidates() -> list[dict]:
    """Return top-5 long-call candidates from the options flow JSON."""
    if not OPTIONS_FLOW_JSON.exists():
        return []
    try:
        d = json.loads(OPTIONS_FLOW_JSON.read_text())
    except Exception:
        return []
    legs = d.get("unusual_legs") or []
    calls = [l for l in legs if (l.get("side") or "").lower() == "call"]
    calls.sort(key=lambda l: l.get("volume") or 0, reverse=True)
    return calls[:5]


def main() -> int:
    load_env()

    # Circuit-breaker check
    kill_lock = ROOT / ".kill_switch_tripped"
    if kill_lock.exists():
        log(f"ABORT: kill switch lockfile present at {kill_lock} — no new options orders.")
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
    live = os.environ.get("ALPACA_AGENT_OPTIONS_LIVE", "").strip() == "1"

    max_pos_usd = env_float("ALPACA_OPTIONS_MAX_POSITION_USD", 200.0)
    max_daily_loss = env_float("ALPACA_OPTIONS_MAX_DAILY_LOSS_USD", 300.0)
    max_open = env_int("ALPACA_OPTIONS_MAX_OPEN_POSITIONS", 3)

    halted = False
    halt_reason = None
    if HALT_FILE.exists():
        halted = True
        halt_reason = f"halt_file_present: {HALT_FILE.name}"

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

    # Existing option positions (asset_class = us_option)
    code_p, positions, _ = alpaca_call("GET", base, "/v2/positions", key, secret)
    if code_p != 200 or not isinstance(positions, list):
        positions = []
    open_option_symbols = {
        (p.get("symbol") or "").upper()
        for p in positions
        if (p.get("asset_class") or "") == "us_option"
    }

    candidates = load_call_candidates()
    log(f"context | mode={'paper' if is_paper else 'LIVE'} live={live} "
        f"equity=${equity:,.2f} pl_today=${pl_today} "
        f"option_positions={len(open_option_symbols)} halted={halted} "
        f"call_candidates={len(candidates)}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    decisions: list[dict] = []
    placed = skipped = rejected = 0

    for leg in candidates:
        occ = (leg.get("symbol") or "").upper()
        if not occ:
            continue
        client_order_id = f"ce_opt_{today}_{occ}_entry"
        decision = {
            "occ_symbol": occ,
            "underlying": leg.get("underlying"),
            "expiry": leg.get("expiry"),
            "strike": leg.get("strike"),
            "side": "call",
            "signal": "options_unusual_flow",
            "client_order_id": client_order_id,
            "details": {
                "volume": leg.get("volume"),
                "open_interest": leg.get("open_interest"),
                "bid": leg.get("bid"),
                "ask": leg.get("ask"),
                "last_trade_price": leg.get("last_trade_price"),
                "implied_volatility": leg.get("implied_volatility"),
                "delta": leg.get("delta"),
            },
        }

        if halted:
            decision["status"] = "skipped"
            decision["reason"] = halt_reason
            decisions.append(decision); skipped += 1; continue

        if occ in open_option_symbols:
            decision["status"] = "skipped"
            decision["reason"] = "already_in_open_position"
            decisions.append(decision); skipped += 1; continue

        if len(open_option_symbols) + placed >= max_open:
            decision["status"] = "skipped"
            decision["reason"] = f"max_open_positions_{max_open}_reached"
            decisions.append(decision); skipped += 1; continue

        ask = to_float(leg.get("ask"))
        if not ask or ask <= 0:
            decision["status"] = "skipped"
            decision["reason"] = "no_ask_quote"
            decisions.append(decision); skipped += 1; continue

        per_contract = ask * 100.0
        decision["est_per_contract_usd"] = round(per_contract, 2)
        if per_contract > max_pos_usd:
            decision["status"] = "skipped"
            decision["reason"] = f"premium_${per_contract:.2f}_exceeds_max_pos_${max_pos_usd}"
            decisions.append(decision); skipped += 1; continue

        qty = int(math.floor(max_pos_usd / per_contract))
        if qty < 1:
            decision["status"] = "skipped"
            decision["reason"] = "qty_floor_zero"
            decisions.append(decision); skipped += 1; continue

        decision["qty"] = qty
        decision["est_total_cost_usd"] = round(per_contract * qty, 2)

        order_body = {
            "symbol": occ,
            "qty": str(qty),
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "client_order_id": client_order_id,
        }

        if not live:
            decision["status"] = "dry_run"
            decision["reason"] = "ALPACA_AGENT_OPTIONS_LIVE!=1 (default safe mode)"
            decisions.append(decision); placed += 1; continue

        c2, body, req_id_o = alpaca_call("POST", base, "/v2/orders", key, secret, order_body)
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
        },
        "account": {
            "equity": equity,
            "last_equity": last_equity,
            "pl_today_usd": pl_today,
            "open_option_positions": len(open_option_symbols),
        },
        "summary": summary,
        "decisions": decisions,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
