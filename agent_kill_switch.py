"""agent_kill_switch.py — Portfolio circuit breaker for the autonomous loop.

Run this BEFORE every agent_alpaca_*.py invocation in the autonomous loop.
If equity drawdown exceeds the configured threshold for the trading day, this
script CANCELS all open orders, LIQUIDATES all positions, and writes a
lockfile that prevents agent_alpaca_*.py from opening new positions until
the operator clears the lockfile manually.

Environment (read from $WORKSPACE_ROOT/.sec_email_env):
  - ALPACA_API_KEY_ID         (required)
  - ALPACA_API_SECRET         (required)
  - ALPACA_BASE_URL           (default: paper-api.alpaca.markets)
  - KILL_SWITCH_DRAWDOWN_PCT  (default: 3.0  — flatten if today's loss ≥ 3% of equity)
  - KILL_SWITCH_MAX_LOSS_USD  (default: 500  — flatten if today's loss ≥ $500)
  - KILL_SWITCH_DISCORD_WEBHOOK  (optional — POST a notification on trip)
  - KILL_SWITCH_DRY_RUN       (default: 0   — set to 1 to log without flattening)

Outputs:
  - $WORKSPACE_ROOT/data/kill_switch_state.json  (last evaluation)
  - $WORKSPACE_ROOT/.kill_switch_tripped         (lockfile — presence = tripped)
  - $WORKSPACE_ROOT/logs/kill_switch.log         (append-only audit trail)

Manual reset:
  rm /home/operator/.openclaw/workspace/.kill_switch_tripped

Exit codes:
  0  — equity within bounds, no action taken
  1  — circuit breaker tripped (positions flattened or already flat)
  2  — error (missing keys / network / lockfile already present)
  3  — already tripped earlier today (lockfile exists, no-op)
"""

import json
import os
import sys
import time
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".sec_email_env"
LOCKFILE = ROOT / ".kill_switch_tripped"
STATE_FILE = ROOT / "data" / "kill_switch_state.json"
LOG_FILE = ROOT / "logs" / "kill_switch.log"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_env() -> dict:
    """Load .sec_email_env into a dict (keys=values, ignoring comments)."""
    env = {}
    if not ENV_FILE.exists():
        return env
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def env_float(env: dict, key: str, default: float) -> float:
    try:
        return float(env.get(key, os.environ.get(key, default)))
    except (TypeError, ValueError):
        return default


def env_int(env: dict, key: str, default: int) -> int:
    try:
        return int(env.get(key, os.environ.get(key, default)))
    except (TypeError, ValueError):
        return default


def log(msg: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    line = f"[{ts}] {msg}\n"
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line)
    sys.stdout.write(line)


def alpaca_request(method: str, base: str, path: str, key: str, secret: str,
                   body: dict | None = None, timeout: int = 15) -> tuple[int, object]:
    url = base.rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
            err_payload = json.loads(err_body) if err_body else {"error": str(e)}
        except Exception:
            err_payload = {"error": str(e)}
        return e.code, err_payload
    except urllib.error.URLError as e:
        return 0, {"error": f"URLError: {e}"}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": f"{type(e).__name__}: {e}"}


def notify_discord(webhook_url: str, content: str) -> None:
    if not webhook_url:
        return
    try:
        body = json.dumps({"content": content[:1900]}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # noqa: BLE001
        log(f"discord notify failed: {e}")


def evaluate_and_act() -> int:
    env = load_env()
    key = env.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY_ID", "")
    secret = env.get("ALPACA_API_SECRET") or os.environ.get("ALPACA_API_SECRET", "")
    base = (env.get("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets").rstrip("/")
    drawdown_pct = env_float(env, "KILL_SWITCH_DRAWDOWN_PCT", 3.0)
    max_loss_usd = env_float(env, "KILL_SWITCH_MAX_LOSS_USD", 500.0)
    discord_webhook = env.get("KILL_SWITCH_DISCORD_WEBHOOK") or env.get("DISCORD_WEBHOOK_URL", "")
    dry_run = env_int(env, "KILL_SWITCH_DRY_RUN", 0) == 1

    if not key or not secret:
        log("ERROR: Alpaca keys missing — cannot evaluate kill switch")
        return 2

    if LOCKFILE.exists():
        log(f"already tripped earlier today (lockfile present at {LOCKFILE}) — no-op")
        return 3

    code, account = alpaca_request("GET", base, "/v2/account", key, secret)
    if code != 200 or not isinstance(account, dict):
        log(f"ERROR: account fetch failed code={code} body={account}")
        return 2

    try:
        equity = float(account.get("equity") or 0)
        last_equity = float(account.get("last_equity") or equity)
        cash = float(account.get("cash") or 0)
        long_market_value = float(account.get("long_market_value") or 0)
        short_market_value = float(account.get("short_market_value") or 0)
    except (TypeError, ValueError) as e:
        log(f"ERROR: parsing account numbers: {e} body={account}")
        return 2

    pl_today = equity - last_equity
    drawdown_pct_today = (pl_today / last_equity * 100.0) if last_equity > 0 else 0.0

    state = {
        "evaluated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "equity": equity,
        "last_equity": last_equity,
        "pl_today_usd": round(pl_today, 2),
        "drawdown_pct_today": round(drawdown_pct_today, 4),
        "drawdown_threshold_pct": -drawdown_pct,
        "max_loss_threshold_usd": -max_loss_usd,
        "long_market_value": long_market_value,
        "short_market_value": short_market_value,
        "cash": cash,
        "account_id": account.get("id"),
        "trading_blocked_by_alpaca": bool(account.get("trading_blocked")),
        "tripped": False,
        "dry_run": dry_run,
    }

    # Trip conditions: today's loss is large in % terms OR absolute terms
    tripped_pct = drawdown_pct_today <= -drawdown_pct
    tripped_usd = pl_today <= -max_loss_usd

    if not (tripped_pct or tripped_usd):
        log(f"OK equity=${equity:,.2f} pl_today=${pl_today:+.2f} "
            f"drawdown={drawdown_pct_today:+.2f}% (limits: -{drawdown_pct}%, -${max_loss_usd:,.0f})")
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return 0

    # TRIPPED — take action
    state["tripped"] = True
    state["trip_reason"] = []
    if tripped_pct:
        state["trip_reason"].append(f"drawdown {drawdown_pct_today:+.2f}% breached -{drawdown_pct}%")
    if tripped_usd:
        state["trip_reason"].append(f"P/L today ${pl_today:+.2f} breached -${max_loss_usd:,.0f}")

    log(f"TRIPPED: {' AND '.join(state['trip_reason'])}")

    if dry_run:
        log("DRY_RUN=1 — would have flattened, skipping cancel/close")
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return 1

    # Step 1: cancel all open orders
    cancel_code, cancel_body = alpaca_request("DELETE", base, "/v2/orders", key, secret)
    state["cancel_orders_code"] = cancel_code
    state["cancel_orders_count"] = (
        len(cancel_body) if isinstance(cancel_body, list) else None
    )
    log(f"DELETE /v2/orders → {cancel_code} (cancelled "
        f"{state['cancel_orders_count']} orders)")

    # Step 2: close all positions
    close_code, close_body = alpaca_request("DELETE", base, "/v2/positions",
                                            key, secret)
    state["close_positions_code"] = close_code
    state["close_positions_count"] = (
        len(close_body) if isinstance(close_body, list) else None
    )
    log(f"DELETE /v2/positions → {close_code} (closed "
        f"{state['close_positions_count']} positions)")

    # Step 3: write lockfile so subsequent agent runs skip
    LOCKFILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    log(f"lockfile written at {LOCKFILE} — agent_alpaca_*.py will skip until removed")

    # Step 4: notify
    msg_lines = [
        "🛑 **KILL SWITCH TRIPPED**",
        f"Account `{account.get('id', '?')[:8]}…`",
        f"Equity: ${equity:,.2f} (last_equity ${last_equity:,.2f})",
        f"P/L today: ${pl_today:+,.2f} ({drawdown_pct_today:+.2f}%)",
        f"Reason: {'; '.join(state['trip_reason'])}",
        f"Cancelled {state['cancel_orders_count']} orders, closed "
        f"{state['close_positions_count']} positions.",
        f"Reset: `rm {LOCKFILE}`",
    ]
    notify_discord(discord_webhook, "\n".join(msg_lines))

    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return 1


def main() -> int:
    try:
        return evaluate_and_act()
    except Exception as e:  # noqa: BLE001
        log(f"FATAL: {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
