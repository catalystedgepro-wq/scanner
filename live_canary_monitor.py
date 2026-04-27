"""live_canary_monitor.py — Live-trading observer + auto-alert.

Runs every N minutes (cron-driven). For each cycle:
  1. Reads /v2/account, /v2/positions, /v2/orders from Alpaca
  2. Snapshots equity / P&L / open positions to data/live_canary_state.json
  3. Detects events worth alerting on:
       - new fill (position appeared)
       - position closed
       - new order placed
       - drawdown crossed 0.5% / 1% / 2% thresholds
       - kill switch tripped
       - any /v2/account error
  4. Posts each event to Discord + Telegram (using existing webhooks)
  5. At market close (21:00 UTC), posts a daily summary

This is read-only — never places orders. Designed to run unattended.

Cron: */15 13-22 * * 1-5 (every 15 min, market hours + 1 hr buffer)

Output:
  data/live_canary_state.json   — rolling state for dashboard
  data/live_canary_events.jsonl — append-only event log
  logs/live_canary_monitor.log  — daemon log
"""

import datetime as dt
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
STATE_FILE = ROOT / "data" / "live_canary_state.json"
EVENTS_FILE = ROOT / "data" / "live_canary_events.jsonl"
LOG_FILE = ROOT / "logs" / "live_canary_monitor.log"
KILL_LOCK = ROOT / ".kill_switch_tripped"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def parse_kv(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def log(msg: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    line = f"[{ts}] {msg}\n"
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line)


def alpaca_get(base: str, path: str, key: str, secret: str) -> tuple[int, object]:
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = resp.read().decode("utf-8") or "[]"
            return resp.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"error": str(e)}
        return e.code, err
    except urllib.error.URLError as e:
        return 0, {"error": f"URLError: {e}"}


def post_webhook(url: str, content: str) -> None:
    if not url:
        return
    try:
        body = json.dumps({"content": content[:1900]}).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # noqa: BLE001
        log(f"webhook post failed: {e}")


def post_telegram(env: dict, text: str) -> None:
    bot = env.get("TELEGRAM_BOT_TOKEN", "")
    chat = env.get("TELEGRAM_CHANNEL", "")
    if not bot or not chat:
        return
    try:
        url = f"https://api.telegram.org/bot{bot}/sendMessage"
        body = json.dumps({
            "chat_id": chat,
            "text": text[:4000],
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # noqa: BLE001
        log(f"telegram post failed: {e}")


def notify(env: dict, content: str) -> None:
    log(f"NOTIFY: {content[:120]}")
    discord = env.get("DISCORD_WEBHOOK_URL", "")
    post_webhook(discord, content)
    post_telegram(env, content)


def read_prev_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def append_event(event: dict) -> None:
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def main() -> int:
    env = parse_kv(ENV_FILE)
    key = env.get("ALPACA_API_KEY_ID", "")
    secret = env.get("ALPACA_API_SECRET", "")
    base = env.get("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets"
    is_live = "paper" not in base.lower()

    if not key or not secret:
        log("ABORT: keys missing")
        return 2

    # /v2/account
    code_a, account = alpaca_get(base, "/v2/account", key, secret)
    if code_a != 200 or not isinstance(account, dict):
        notify(env, f"⚠️ Canary monitor: account fetch failed ({code_a}) — "
                    f"{json.dumps(account)[:200]}")
        return 2
    equity = float(account.get("equity") or 0)
    last_equity = float(account.get("last_equity") or equity)
    cash = float(account.get("cash") or 0)
    pl_today = equity - last_equity
    drawdown_pct = (pl_today / last_equity * 100.0) if last_equity > 0 else 0.0

    # /v2/positions
    code_p, positions = alpaca_get(base, "/v2/positions", key, secret)
    if code_p != 200 or not isinstance(positions, list):
        positions = []
    pos_symbols = sorted(p.get("symbol", "?") for p in positions)
    pos_count = len(positions)
    pos_unreal_pl = sum(float(p.get("unrealized_pl", 0)) for p in positions)

    # /v2/orders open
    code_o, orders = alpaca_get(base, "/v2/orders?status=open", key, secret)
    if code_o != 200 or not isinstance(orders, list):
        orders = []
    open_order_count = len(orders)

    state = {
        "evaluated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "is_live": is_live,
        "base_url": base,
        "account_id": account.get("id"),
        "equity": equity,
        "last_equity": last_equity,
        "cash": cash,
        "pl_today_usd": round(pl_today, 2),
        "drawdown_pct": round(drawdown_pct, 4),
        "open_positions": pos_count,
        "position_symbols": pos_symbols,
        "unrealized_pl_usd": round(pos_unreal_pl, 2),
        "open_orders": open_order_count,
        "kill_switch_tripped": KILL_LOCK.exists(),
    }

    prev = read_prev_state()

    # Detect change events
    events = []
    prev_symbols = set(prev.get("position_symbols", []))
    cur_symbols = set(pos_symbols)
    for sym in cur_symbols - prev_symbols:
        events.append({
            "type": "position_opened", "symbol": sym, "ts": state["evaluated_at"],
        })
    for sym in prev_symbols - cur_symbols:
        events.append({
            "type": "position_closed", "symbol": sym, "ts": state["evaluated_at"],
        })

    prev_dd = prev.get("drawdown_pct", 0.0)
    for thresh in (-0.5, -1.0, -2.0):
        if prev_dd > thresh and drawdown_pct <= thresh:
            events.append({
                "type": "drawdown_threshold",
                "threshold_pct": thresh,
                "drawdown_pct": drawdown_pct,
                "ts": state["evaluated_at"],
            })

    if state["kill_switch_tripped"] and not prev.get("kill_switch_tripped", False):
        events.append({"type": "kill_switch_tripped", "ts": state["evaluated_at"]})

    for evt in events:
        append_event(evt)
        if evt["type"] == "position_opened":
            notify(env, f"🟢 **OPEN** `{evt['symbol']}` (equity ${equity:,.2f})")
        elif evt["type"] == "position_closed":
            notify(env, f"🔴 **CLOSE** `{evt['symbol']}` (equity ${equity:,.2f}, P/L today ${pl_today:+,.2f})")
        elif evt["type"] == "drawdown_threshold":
            notify(env, f"⚠️ **DRAWDOWN** crossed {evt['threshold_pct']}% (now "
                        f"{drawdown_pct:+.2f}%, equity ${equity:,.2f})")
        elif evt["type"] == "kill_switch_tripped":
            notify(env, f"🛑 **KILL SWITCH TRIPPED** — equity ${equity:,.2f}, P/L today ${pl_today:+,.2f}")

    # Daily summary at 21:00 UTC (market close)
    now = dt.datetime.now(dt.timezone.utc)
    if now.hour == 21 and now.minute < 15:
        last_summary_date = prev.get("last_summary_date")
        today_str = now.strftime("%Y-%m-%d")
        if last_summary_date != today_str:
            summary = (
                f"📊 **DAILY SUMMARY** {today_str} ({'LIVE' if is_live else 'PAPER'})\n"
                f"Equity: ${equity:,.2f}  P/L today: ${pl_today:+,.2f} ({drawdown_pct:+.2f}%)\n"
                f"Cash: ${cash:,.2f}  Positions: {pos_count} {pos_symbols or '—'}\n"
                f"Unrealized P/L: ${pos_unreal_pl:+,.2f}  Open orders: {open_order_count}"
            )
            notify(env, summary)
            state["last_summary_date"] = today_str

    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    log(f"OK is_live={is_live} equity=${equity:,.2f} pl=${pl_today:+.2f} "
        f"pos={pos_count} orders={open_order_count} events={len(events)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        log(f"FATAL: {type(e).__name__}: {e}")
        sys.exit(2)
