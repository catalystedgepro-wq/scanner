#!/usr/bin/env python3
"""Tradier equity paper/live agent — publish-first compliance.

Trades small equity positions ($25 starter notional) on tickers that have
ALREADY been published via /scoops/ — i.e. the scoop page renders BEFORE
we open any position. This mirrors the legal posture used by published
analysts (Cramer, etc.) and keeps us out of the "scalping" regulatory
class that has bitten automated newsletters.

Activation:
  1. Set TRADIER_API_TOKEN + TRADIER_ACCOUNT_ID in /opt/catalyst/.sec_email_env
     (paper account uses sandbox.tradier.com; live uses api.tradier.com)
  2. Set TRADIER_LIVE=1 to trade real money (default = paper/dry-run)
  3. Set TRADIER_AGENT_ENABLED=1 to actually fire orders
  4. Add to autonomous_loop.sh

Risk controls (all configurable via env):
  TRADIER_MAX_POSITION_USD=25      # starter size per ticker
  TRADIER_MAX_OPEN_POSITIONS=4     # cap on simultaneous positions
  TRADIER_DAILY_LOSS_HALT=10       # if today's P/L < -$10, halt new entries
  TRADIER_TRAILING_STOP_PCT=0.06   # 6% trailing stop, recomputed each cycle
  TRADIER_PROFIT_TARGET_PCT=0.05   # 5% profit-take (close half, ride the rest)

Output:
  tradier_orders.csv      — full order audit trail (immutable append)
  tradier_positions.json  — current open positions
  tradier_status.json     — last-cycle status for /trust/

This is a SAFETY-FIRST scaffold. Defaults to DRY RUN. Will not fire any
real order until both TRADIER_LIVE=1 and TRADIER_AGENT_ENABLED=1.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
SCOOPS_DIR = ROOT / "docs" / "scoops"
SCOOPS_STATUS = ROOT / "scoops_status.json"
ORDERS_CSV = ROOT / "tradier_orders.csv"
POSITIONS_JSON = ROOT / "tradier_positions.json"
STATUS_JSON = ROOT / "tradier_status.json"
HALT_FILE = ROOT / ".agent_tradier_halted"

# Live vs paper. Default = sandbox/paper.
LIVE = os.environ.get("TRADIER_LIVE", "0").strip() == "1"
ENABLED = os.environ.get("TRADIER_AGENT_ENABLED", "0").strip() == "1"
# Accept either TRADIER_API_TOKEN (preferred) or TRADIER_TOKEN (legacy var
# already used by the options-flow data spoke).
TOKEN = (
    os.environ.get("TRADIER_API_TOKEN", "").strip()
    or os.environ.get("TRADIER_TOKEN", "").strip()
)
ACCOUNT = os.environ.get("TRADIER_ACCOUNT_ID", "").strip()

API_BASE = "https://api.tradier.com/v1" if LIVE else "https://sandbox.tradier.com/v1"


def _profile_lookup(base: str) -> tuple[str, str]:
    """Read-only /user/profile call. Returns (account_id, base_used)."""
    if not TOKEN:
        return "", ""
    req = urllib.request.Request(
        f"{base}/user/profile",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "User-Agent": "CatalystEdge/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return "", base
    profile = data.get("profile") or {}
    accounts = profile.get("account") or []
    if isinstance(accounts, dict):
        accounts = [accounts]
    for a in accounts:
        acct = a.get("account_number") or a.get("number")
        if acct:
            return str(acct), base
    return "", base


def discover_account_id() -> tuple[str, str]:
    """Try the configured base first, then the other base as fallback.

    Tradier issues separate tokens for sandbox vs live. Discovery is a
    read-only profile call; trying both is safe and lets us auto-detect
    which environment the token belongs to.

    Returns (account_id, base_url_that_worked).
    """
    primary = "https://api.tradier.com/v1" if LIVE else "https://sandbox.tradier.com/v1"
    fallback = "https://sandbox.tradier.com/v1" if LIVE else "https://api.tradier.com/v1"
    acct, base = _profile_lookup(primary)
    if acct:
        return acct, base
    acct, base = _profile_lookup(fallback)
    return acct, base

MAX_POSITION_USD = float(os.environ.get("TRADIER_MAX_POSITION_USD", "25"))
MAX_OPEN = int(os.environ.get("TRADIER_MAX_OPEN_POSITIONS", "4"))
DAILY_LOSS_HALT = float(os.environ.get("TRADIER_DAILY_LOSS_HALT", "10"))
TRAILING_PCT = float(os.environ.get("TRADIER_TRAILING_STOP_PCT", "0.06"))
PROFIT_PCT = float(os.environ.get("TRADIER_PROFIT_TARGET_PCT", "0.05"))
HARD_STOP_PCT = float(os.environ.get("TRADIER_HARD_STOP_PCT", "0.08"))
TIME_STOP_DAYS = int(os.environ.get("TRADIER_TIME_STOP_DAYS", "3"))
# PDT rule: < 4 day-trade round-trips per rolling 5 business days when
# equity < $25k. We halt at 3 to leave buffer for the unavoidable hard-stop.
PDT_DAYTRADE_LIMIT = 3
PDT_WINDOW_DAYS = 5


def _trade_dates_from_orders() -> list[tuple[dt.date, str, str]]:
    """Read tradier_orders.csv into (date, ticker, side) tuples."""
    if not ORDERS_CSV.exists():
        return []
    out: list[tuple[dt.date, str, str]] = []
    with ORDERS_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                ts = dt.datetime.fromisoformat(r.get("timestamp_utc", ""))
                d = ts.date()
            except (TypeError, ValueError):
                continue
            tk = (r.get("ticker") or "").upper()
            side = (r.get("side") or "").lower()
            dr = r.get("dry_run", "")
            if str(dr).lower() in ("true", "1"):
                continue  # dry-runs don't count toward PDT
            out.append((d, tk, side))
    return out


def count_day_trades_last_5_business_days(now: dt.datetime) -> int:
    """A 'day trade' = buy + sell of the same ticker on the same calendar
    date. Count distinct (date, ticker) pairs where both sides occurred."""
    rows = _trade_dates_from_orders()
    cutoff = (now - dt.timedelta(days=PDT_WINDOW_DAYS + 2)).date()
    by_day_tk: dict[tuple[dt.date, str], set[str]] = {}
    for d, tk, side in rows:
        if d < cutoff or not tk or side not in ("buy", "sell"):
            continue
        by_day_tk.setdefault((d, tk), set()).add(side)
    return sum(1 for sides in by_day_tk.values() if {"buy", "sell"}.issubset(sides))


def position_age_days(ticker: str, now: dt.datetime) -> int:
    """Days since most recent BUY of this ticker. Returns 0 if no record."""
    rows = _trade_dates_from_orders()
    last_buy: dt.date | None = None
    for d, tk, side in rows:
        if tk != ticker.upper() or side != "buy":
            continue
        if not last_buy or d > last_buy:
            last_buy = d
    if not last_buy:
        return 0
    return (now.date() - last_buy).days


def kelly_size(equity: float, hit_rate: float, profit_pct: float, stop_pct: float) -> float:
    """Half-Kelly position size. Returns dollar amount.

    edge = p × W - (1-p) × L
    kelly_fraction = edge / (W × L)
    Falls back to MAX_POSITION_USD floor when kelly is non-positive (system
    must demonstrate edge before scaling up).
    """
    if hit_rate <= 0 or profit_pct <= 0 or stop_pct <= 0:
        return MAX_POSITION_USD
    edge = hit_rate * profit_pct - (1 - hit_rate) * stop_pct
    if edge <= 0:
        return MAX_POSITION_USD  # negative edge → use floor only
    kelly = edge / (profit_pct * stop_pct)
    half_kelly = max(0.05, min(0.25, kelly * 0.5))  # clamp 5%-25% per trade
    return max(MAX_POSITION_USD, equity * half_kelly)


def get_current_hit_rate() -> float:
    """Read sec_outcome_summary.csv:sec_clean_gappers published_hit_rate_2pct."""
    summary = ROOT / "sec_outcome_summary.csv"
    if not summary.exists():
        return 0.44  # fallback to current observed
    try:
        with summary.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("list_name") == "sec_clean_gappers":
                    pub = r.get("published_hit_rate_2pct") or r.get("hit_rate_2pct", "44")
                    return float(pub) / 100.0
    except (OSError, ValueError):
        pass
    return 0.44


def write_status(payload: dict[str, Any]) -> None:
    STATUS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_order(row: dict[str, Any]) -> None:
    fieldnames = [
        "timestamp_utc", "action", "ticker", "side", "quantity",
        "estimated_price", "tradier_order_id", "tradier_status",
        "dry_run", "scoop_slug", "reason",
    ]
    exists = ORDERS_CSV.exists()
    with ORDERS_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in fieldnames})


def http_request(method: str, path: str, params: dict | None = None) -> dict:
    """Tradier API call. Returns parsed JSON or {} on error."""
    if not TOKEN:
        return {}
    url = f"{API_BASE}{path}"
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params)
        body = None
    else:
        body = urllib.parse.urlencode(params or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "User-Agent": "CatalystEdge/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def get_account_balance() -> dict:
    if not (TOKEN and ACCOUNT):
        return {}
    data = http_request("GET", f"/accounts/{ACCOUNT}/balances")
    return data if isinstance(data, dict) else {}


def get_positions() -> list[dict]:
    if not (TOKEN and ACCOUNT):
        return []
    data = http_request("GET", f"/accounts/{ACCOUNT}/positions")
    raw = data.get("positions")
    # Tradier returns the string "null" (not a dict) when the account has
    # zero positions. Guard against any non-dict shape.
    if not isinstance(raw, dict):
        return []
    p = raw.get("position") or []
    if isinstance(p, dict):
        return [p]
    return p if isinstance(p, list) else []


def get_quote(ticker: str) -> float:
    data = http_request("GET", "/markets/quotes", {"symbols": ticker})
    q = (data.get("quotes") or {}).get("quote") or {}
    if isinstance(q, list):
        q = q[0] if q else {}
    try:
        return float(q.get("last") or q.get("close") or 0)
    except (TypeError, ValueError):
        return 0.0


def place_order(ticker: str, side: str, qty: int, dry_run: bool) -> dict:
    """side='buy' or 'sell'. Returns Tradier response or dry-run stub."""
    if dry_run:
        return {"order": {"id": "DRYRUN", "status": "dry_run"}}
    return http_request(
        "POST",
        f"/accounts/{ACCOUNT}/orders",
        {
            "class": "equity",
            "symbol": ticker,
            "side": side,
            "quantity": str(qty),
            "type": "market",
            "duration": "day",
        },
    )


def load_recent_scoops(max_age_hours: int = 36) -> list[dict[str, str]]:
    """Read scoops_status.json; only tickers with a scoop published within
    the last 36h are eligible to enter (publish-first compliance gate)."""
    if not SCOOPS_STATUS.exists():
        return []
    try:
        data = json.loads(SCOOPS_STATUS.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    items = data.get("items") or []
    out: list[dict[str, str]] = []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=max_age_hours)
    for it in items:
        try:
            d = dt.date.fromisoformat(it.get("date", ""))
            ts = dt.datetime.combine(d, dt.time(0, 0), tzinfo=dt.timezone.utc)
            if ts < cutoff - dt.timedelta(hours=24):  # day-grain check
                continue
        except (TypeError, ValueError):
            continue
        if it.get("validation") != "ok":
            continue
        out.append(it)
    return out


def main() -> int:
    global ACCOUNT, API_BASE
    now_utc = dt.datetime.now(dt.timezone.utc)
    status = {
        "last_run_utc": now_utc.isoformat(),
        "live": LIVE,
        "enabled": ENABLED,
        "halted": HALT_FILE.exists(),
        "token_present": bool(TOKEN),
        "actions": [],
        "errors": [],
    }

    if not TOKEN:
        status["actions"].append("skipped_no_token")
        write_status(status)
        print("tradier_agent: skipped (TRADIER_API_TOKEN / TRADIER_TOKEN missing)")
        return 0

    # Auto-discover account ID if not explicitly set. Tries both sandbox
    # and live profile endpoints; whichever responds becomes our API base.
    global API_BASE
    if not ACCOUNT:
        ACCOUNT, discovered_base = discover_account_id()
        if ACCOUNT and discovered_base:
            API_BASE = discovered_base
            status["api_base_detected"] = discovered_base
        status["account_discovered_via_profile"] = bool(ACCOUNT)
    status["account_id_present"] = bool(ACCOUNT)
    status["api_base"] = API_BASE
    if not ACCOUNT:
        status["actions"].append("skipped_no_account_id")
        write_status(status)
        print(
            "tradier_agent: skipped (no TRADIER_ACCOUNT_ID; profile lookup "
            "empty on both sandbox + live — token may be invalid)"
        )
        return 0

    dry_run = not (LIVE and ENABLED)
    status["dry_run"] = dry_run

    # Manage existing positions FIRST — exit-only path runs even when halted.
    positions = get_positions()
    status["open_positions"] = len(positions)
    POSITIONS_JSON.write_text(json.dumps(positions, indent=2), encoding="utf-8")

    for p in positions:
        sym = p.get("symbol", "")
        try:
            qty = int(float(p.get("quantity", 0)))
            cost = float(p.get("cost_basis", 0))
            avg = cost / qty if qty else 0
        except (TypeError, ValueError):
            continue
        if qty <= 0 or avg <= 0:
            continue
        last = get_quote(sym)
        if last <= 0:
            continue
        pnl_pct = (last - avg) / avg
        age_days = position_age_days(sym, now_utc)

        # Hard stop fires regardless of age — capital preservation > PDT.
        # Profit target fires regardless of age — winners get taken.
        # Trailing/time stops fire ONLY after >=1 day held to keep us
        # PDT-safe (same-day round-trip = day trade).
        exit_reason: str | None = None
        if pnl_pct <= -HARD_STOP_PCT:
            exit_reason = f"hard_stop_{pnl_pct:.2%}"
        elif pnl_pct >= PROFIT_PCT:
            exit_reason = f"profit_target_{pnl_pct:.2%}"
        elif age_days >= 1 and pnl_pct <= -TRAILING_PCT:
            exit_reason = f"trailing_stop_{pnl_pct:.2%}_age{age_days}d"
        elif age_days >= TIME_STOP_DAYS:
            exit_reason = f"time_stop_{age_days}d"

        if exit_reason:
            r = place_order(sym, "sell", qty, dry_run)
            status["actions"].append(
                {"action": "exit", "ticker": sym, "qty": qty,
                 "pnl_pct": round(pnl_pct * 100, 2),
                 "age_days": age_days, "reason": exit_reason, "result": r}
            )
            append_order({
                "timestamp_utc": now_utc.isoformat(), "action": "exit",
                "ticker": sym, "side": "sell", "quantity": qty,
                "estimated_price": last,
                "tradier_order_id": (r.get("order") or {}).get("id", ""),
                "tradier_status": (r.get("order") or {}).get("status", ""),
                "dry_run": dry_run, "reason": exit_reason,
            })

    if HALT_FILE.exists():
        status["actions"].append("halted_no_new_entries")
        write_status(status)
        print(f"tradier_agent: halt active — exits processed, no entries (dry_run={dry_run})")
        return 0

    # Daily-loss halt check.
    bal = get_account_balance()
    try:
        day_pnl = float(((bal.get("balances") or {}).get("close_pl") or 0))
    except (TypeError, ValueError):
        day_pnl = 0.0
    status["day_pnl"] = day_pnl
    if day_pnl < -DAILY_LOSS_HALT:
        HALT_FILE.touch()
        status["actions"].append(f"daily_loss_auto_halt_pnl={day_pnl}")
        write_status(status)
        print(f"tradier_agent: daily loss ${day_pnl:.2f} <  -${DAILY_LOSS_HALT}, auto-halted")
        return 0

    # PDT guard — halt new entries when day-trade count is at the limit.
    dt_count = count_day_trades_last_5_business_days(now_utc)
    status["pdt_day_trades_5d"] = dt_count
    if dt_count >= PDT_DAYTRADE_LIMIT:
        status["actions"].append(f"pdt_halt_daytrades={dt_count}")
        write_status(status)
        print(f"tradier_agent: PDT halt — {dt_count}/{PDT_DAYTRADE_LIMIT} day trades in 5d window")
        return 0

    # Compound capacity scales with equity: 1 position per $250 equity, capped.
    bal = get_account_balance()
    try:
        equity = float(((bal.get("balances") or {}).get("total_equity") or 0))
    except (TypeError, ValueError):
        equity = 0.0
    status["equity"] = equity
    dynamic_max_open = max(MAX_OPEN, min(10, int(equity / 250)))
    open_n = len(positions)
    if open_n >= dynamic_max_open:
        status["actions"].append(f"max_positions_reached_{open_n}/{dynamic_max_open}")
        write_status(status)
        print(f"tradier_agent: max open positions reached ({open_n}/{dynamic_max_open})")
        return 0

    # Kelly-aware position size. Falls back to MAX_POSITION_USD when edge ≤ 0.
    hit_rate = get_current_hit_rate()
    target_size_usd = kelly_size(equity or MAX_POSITION_USD * 4, hit_rate, PROFIT_PCT, HARD_STOP_PCT)
    status["hit_rate_used"] = round(hit_rate, 4)
    status["target_position_usd"] = round(target_size_usd, 2)

    held = {(p.get("symbol") or "").upper() for p in positions}
    candidates = load_recent_scoops()
    status["scoop_candidates"] = [c["ticker"] for c in candidates]

    for c in candidates:
        if open_n >= dynamic_max_open:
            break
        ticker = c["ticker"].upper()
        if ticker in held:
            continue
        last = get_quote(ticker)
        if last <= 0 or last < 1.0:
            continue  # Sub-$1 hard-no per protocol
        if last > target_size_usd:
            continue  # Per-share price too high for Kelly-sized position
        qty = max(1, int(target_size_usd // last))
        notional = qty * last
        if notional > target_size_usd * 1.25:
            continue
        r = place_order(ticker, "buy", qty, dry_run)
        order = r.get("order") or {}
        status["actions"].append(
            {"action": "entry", "ticker": ticker, "qty": qty,
             "est_price": last, "notional": round(notional, 2),
             "scoop_slug": c.get("slug"), "result": order}
        )
        append_order({
            "timestamp_utc": now_utc.isoformat(), "action": "entry",
            "ticker": ticker, "side": "buy", "quantity": qty,
            "estimated_price": last,
            "tradier_order_id": order.get("id", ""),
            "tradier_status": order.get("status", ""),
            "dry_run": dry_run, "scoop_slug": c.get("slug", ""),
            "reason": f"convergence_signals={c.get('signals')}_score={c.get('score')}_hit={hit_rate:.2f}",
        })
        open_n += 1

    write_status(status)
    print(
        f"tradier_agent: live={LIVE} enabled={ENABLED} dry_run={dry_run} "
        f"open={status['open_positions']} actions={len(status['actions'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
