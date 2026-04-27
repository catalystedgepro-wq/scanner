#!/usr/bin/env python3
"""track_agent_outcomes.py — outcomes tracker for the live paper-trading agent.

Maintains a persistent ledger of every paper order placed by agent_alpaca_orders.py,
captures fills + exits via Alpaca, and computes +1d/+5d/+30d horizon outcomes
(absolute and vs SPY) so tune_scoring_config.py can re-tune signal weights nightly.

Output:
  - agent_outcomes_ledger.csv     persistent canonical row store
  - docs/data/agent_outcomes.json live snapshot for /trades/ and /trust/
  - agent_outcomes_summary.csv    mirrors sec_outcome_summary.csv schema

Read-only with respect to orders. Never places, modifies, or cancels anything.

Reference:
  - https://docs.alpaca.markets/reference/getanorderbyclientorderid
  - https://docs.alpaca.markets/reference/historicalbarsforsymbol
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
ORDERS_JSON = ROOT / "docs/data/alpaca_orders.json"
CRYPTO_JSON = ROOT / "docs/data/alpaca_crypto.json"
OPTIONS_JSON = ROOT / "docs/data/alpaca_options.json"
LEDGER_CSV = ROOT / "agent_outcomes_ledger.csv"
SUMMARY_CSV = ROOT / "agent_outcomes_summary.csv"
OUT = ROOT / "docs/data/agent_outcomes.json"
LOG = ROOT / "logs/agent_outcomes.log"
OUT.parent.mkdir(parents=True, exist_ok=True)
LOG.parent.mkdir(exist_ok=True)

LEDGER_FIELDS = [
    "client_order_id", "order_id", "ticker", "signal", "side", "qty",
    "asset_class", "underlying",
    "entry_price", "entry_ts_utc", "fill_ts_utc",
    "exit_price", "exit_ts_utc", "exit_reason",
    "pl_usd", "pl_pct", "hold_days",
    "p1d_pct", "p5d_pct", "p30d_pct",
    "vs_spy_5d_pct", "vs_spy_30d_pct",
    "hit_2pct", "big_move_5pct", "lost_3pct",
]

SPY_BARS_CACHE: dict[str, list[dict]] = {}


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


def write_status(payload: dict) -> None:
    payload.setdefault("last_attempt_utc",
                       datetime.now(timezone.utc).isoformat(timespec="seconds"))
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True))


def to_float(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def to_int(v) -> int | None:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Alpaca HTTP

def alpaca_get(url: str, key: str, secret: str) -> tuple[int, dict | list, str]:
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"raw": raw[:300]}
            return resp.status, parsed, resp.headers.get("X-Request-ID", "")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"raw": raw[:300]}
        except Exception:
            parsed = {"raw": raw[:300]}
        return e.code, parsed, e.headers.get("X-Request-ID", "") if e.headers else ""


# ---------------------------------------------------------------------------
# Ledger I/O

def load_ledger() -> list[dict]:
    if not LEDGER_CSV.exists():
        return []
    rows = []
    with LEDGER_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # normalize empty strings to None for clean updates
            for k in LEDGER_FIELDS:
                if r.get(k) == "":
                    r[k] = None
            rows.append(r)
    return rows


def save_ledger(rows: list[dict]) -> None:
    with LEDGER_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in LEDGER_FIELDS})


def find_row(rows: list[dict], client_order_id: str) -> dict | None:
    for r in rows:
        if r.get("client_order_id") == client_order_id:
            return r
    return None


# ---------------------------------------------------------------------------
# Decision ingest

def _make_row(coid: str, dec: dict, source_ts: str | None,
              asset_class: str, signal_prefix: str | None = None,
              ticker_field: str = "ticker", underlying_field: str | None = None,
              order_id_field: str = "alpaca_order_id",
              entry_price_field: str = "est_price") -> dict:
    sig = dec.get("signal") or ""
    if signal_prefix and not sig.startswith(signal_prefix):
        sig = f"{signal_prefix}{sig}"
    return {
        "client_order_id": coid,
        "order_id": dec.get(order_id_field),
        "ticker": dec.get(ticker_field),
        "signal": sig,
        "side": dec.get("side") or "buy",
        "qty": dec.get("qty") or dec.get("est_qty"),
        "asset_class": asset_class,
        "underlying": dec.get(underlying_field) if underlying_field else None,
        "entry_price": dec.get(entry_price_field),
        "entry_ts_utc": source_ts,
        "fill_ts_utc": None,
        "exit_price": None, "exit_ts_utc": None, "exit_reason": None,
        "pl_usd": None, "pl_pct": None, "hold_days": None,
        "p1d_pct": None, "p5d_pct": None, "p30d_pct": None,
        "vs_spy_5d_pct": None, "vs_spy_30d_pct": None,
        "hit_2pct": None, "big_move_5pct": None, "lost_3pct": None,
    }


def ingest_orders_json(rows: list[dict]) -> int:
    """Pull placed orders from all three trader JSONs into the unified ledger.

    Sources:
      - /data/alpaca_orders.json   (equity)
      - /data/alpaca_crypto.json   (crypto, signal prefixed "crypto_")
      - /data/alpaca_options.json  (options, signal prefixed "options_", ticker = OCC symbol)
    DeFi shadow signals are tracked separately in agent_defi_shadow_ledger.csv.
    """
    added = 0

    # 1) Equity
    if ORDERS_JSON.exists():
        try:
            d = json.loads(ORDERS_JSON.read_text())
            for dec in (d.get("decisions") or []):
                if dec.get("status") != "placed":
                    continue
                coid = dec.get("client_order_id")
                if not coid or find_row(rows, coid):
                    continue
                row = _make_row(coid, dec, d.get("last_attempt_utc"),
                                asset_class="equity")
                rows.append(row); added += 1
        except Exception:
            pass

    # 2) Crypto
    if CRYPTO_JSON.exists():
        try:
            d = json.loads(CRYPTO_JSON.read_text())
            for dec in (d.get("decisions") or []):
                if dec.get("status") != "placed":
                    continue
                coid = (dec.get("client_order_id") or "").replace("_entry", "")
                # Crypto agent uses ce_crypto_* IDs already
                if not coid or find_row(rows, coid):
                    continue
                row = _make_row(coid, dec, d.get("last_attempt_utc"),
                                asset_class="crypto",
                                signal_prefix="crypto_",
                                order_id_field="alpaca_order_id_entry",
                                entry_price_field="est_price")
                # qty falls back to est_qty for crypto (notional orders)
                if row.get("qty") is None:
                    row["qty"] = dec.get("est_qty")
                rows.append(row); added += 1
        except Exception:
            pass

    # 3) Options (OCC symbol; underlying tracked separately; no SPY benchmark for options)
    if OPTIONS_JSON.exists():
        try:
            d = json.loads(OPTIONS_JSON.read_text())
            for dec in (d.get("decisions") or []):
                if dec.get("status") != "placed":
                    continue
                coid = dec.get("client_order_id")
                if not coid or find_row(rows, coid):
                    continue
                row = _make_row(coid, dec, d.get("last_attempt_utc"),
                                asset_class="option",
                                signal_prefix="options_",
                                ticker_field="occ_symbol",
                                underlying_field="underlying",
                                entry_price_field="est_per_contract_usd")
                rows.append(row); added += 1
        except Exception:
            pass

    return added


# ---------------------------------------------------------------------------
# Fill + exit capture

def capture_fills(rows: list[dict], base: str, key: str, secret: str) -> int:
    """For each row without fill_ts, look up the order on Alpaca."""
    captured = 0
    for r in rows:
        if r.get("fill_ts_utc"):
            continue
        oid = r.get("order_id")
        if not oid:
            continue
        code, body, _ = alpaca_get(f"{base.rstrip('/')}/v2/orders/{oid}", key, secret)
        if code != 200 or not isinstance(body, dict):
            continue
        filled_at = body.get("filled_at")
        filled_avg = body.get("filled_avg_price")
        if filled_at and filled_avg:
            r["fill_ts_utc"] = filled_at
            r["entry_price"] = to_float(filled_avg) or r.get("entry_price")
            captured += 1
        time.sleep(0.1)
    return captured


def capture_exits(rows: list[dict], base: str, key: str, secret: str,
                  open_symbols: set[str]) -> int:
    """For each filled row not yet exited, check if position is still held."""
    captured = 0
    for r in rows:
        if r.get("exit_ts_utc"):
            continue
        if not r.get("fill_ts_utc"):
            continue
        sym = (r.get("ticker") or "").upper()
        if not sym:
            continue
        if sym in open_symbols:
            continue
        # Position closed → find the exit fill via /v2/orders?status=closed
        params = {"status": "closed", "symbols": sym, "limit": 50}
        url = f"{base.rstrip('/')}/v2/orders?{urllib.parse.urlencode(params)}"
        code, body, _ = alpaca_get(url, key, secret)
        if code != 200 or not isinstance(body, list):
            continue
        # Pick most-recent SELL after the entry fill
        entry_ts = r.get("fill_ts_utc")
        candidates = [
            o for o in body
            if (o.get("side") == "sell" and o.get("filled_at") and o.get("filled_avg_price")
                and (entry_ts is None or o.get("filled_at") > entry_ts))
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda o: o.get("filled_at"), reverse=True)
        exit_o = candidates[0]
        r["exit_price"] = to_float(exit_o.get("filled_avg_price"))
        r["exit_ts_utc"] = exit_o.get("filled_at")
        # Bracket TP/SL legs have order_class/parent_id; "client_order_id" suffix may differ
        coid = exit_o.get("client_order_id") or ""
        if "tp" in coid.lower() or exit_o.get("type") == "limit":
            r["exit_reason"] = "take_profit"
        elif "sl" in coid.lower() or exit_o.get("type") == "stop":
            r["exit_reason"] = "stop_loss"
        else:
            r["exit_reason"] = "manual_or_other"
        # P/L
        try:
            entry = float(r.get("entry_price") or 0)
            qty = float(r.get("qty") or 0)
            ex = r["exit_price"] or 0
            r["pl_usd"] = round((ex - entry) * qty, 2)
            r["pl_pct"] = round((ex / entry - 1) * 100, 4) if entry else None
            t1 = datetime.fromisoformat(r["fill_ts_utc"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(r["exit_ts_utc"].replace("Z", "+00:00"))
            r["hold_days"] = round((t2 - t1).total_seconds() / 86400, 2)
        except Exception:
            pass
        captured += 1
        time.sleep(0.1)
    return captured


# ---------------------------------------------------------------------------
# Horizon outcomes (+1d/+5d/+30d, vs SPY)

def fetch_bars(symbol: str, start_iso: str, key: str, secret: str,
               limit: int = 35) -> list[dict]:
    """Pull daily bars starting from start (ISO) for `limit` days."""
    data_base = (os.environ.get("ALPACA_DATA_URL")
                 or "https://data.alpaca.markets").rstrip("/")
    params = {"timeframe": "1Day", "start": start_iso, "limit": str(limit), "feed": "iex"}
    url = f"{data_base}/v2/stocks/{urllib.parse.quote(symbol)}/bars?{urllib.parse.urlencode(params)}"
    code, body, _ = alpaca_get(url, key, secret)
    if code != 200 or not isinstance(body, dict):
        return []
    return body.get("bars") or []


def get_spy_bars(start_iso: str, key: str, secret: str) -> list[dict]:
    cache_key = start_iso[:10]
    if cache_key in SPY_BARS_CACHE:
        return SPY_BARS_CACHE[cache_key]
    bars = fetch_bars("SPY", start_iso, key, secret, limit=35)
    SPY_BARS_CACHE[cache_key] = bars
    return bars


def horizon_pct(bars: list[dict], n: int) -> float | None:
    """Return % move from bar[0].open to bar[n].close (n trading days forward)."""
    if not bars or n >= len(bars):
        return None
    start = bars[0].get("o") or bars[0].get("c")
    end = bars[n].get("c")
    if not start or not end:
        return None
    try:
        return round((float(end) / float(start) - 1) * 100, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def compute_horizons(rows: list[dict], key: str, secret: str) -> int:
    """For rows with a fill_ts but missing horizon stats, fill them in."""
    today = datetime.now(timezone.utc)
    updated = 0
    for r in rows:
        ft = r.get("fill_ts_utc")
        if not ft:
            continue
        # Skip if already fully populated
        if r.get("p30d_pct") is not None and r.get("vs_spy_30d_pct") is not None:
            continue
        # Options rows don't have bar data for OCC symbols on /v2/stocks/.../bars
        # — outcome accounting is fill→exit only for those; skip horizon math.
        if (r.get("asset_class") or "equity") == "option":
            continue
        try:
            fill_dt = datetime.fromisoformat(ft.replace("Z", "+00:00"))
        except Exception:
            continue
        days_since = (today - fill_dt).days
        if days_since < 1:
            continue
        bars = fetch_bars(r["ticker"], ft, key, secret, limit=35)
        spy_bars = get_spy_bars(ft, key, secret)
        if not bars:
            continue
        # bars[0] = the day OF the fill (or next trading day depending on Alpaca)
        if r.get("p1d_pct") is None and len(bars) > 1:
            r["p1d_pct"] = horizon_pct(bars, 1)
        if r.get("p5d_pct") is None and len(bars) > 5 and days_since >= 5:
            r["p5d_pct"] = horizon_pct(bars, 5)
            spy5 = horizon_pct(spy_bars, 5)
            if r["p5d_pct"] is not None and spy5 is not None:
                r["vs_spy_5d_pct"] = round(r["p5d_pct"] - spy5, 4)
        if r.get("p30d_pct") is None and len(bars) > 30 and days_since >= 30:
            r["p30d_pct"] = horizon_pct(bars, 30)
            spy30 = horizon_pct(spy_bars, 30)
            if r["p30d_pct"] is not None and spy30 is not None:
                r["vs_spy_30d_pct"] = round(r["p30d_pct"] - spy30, 4)
        # Audit flags use the longest available horizon
        ref = r.get("p5d_pct")
        if ref is None:
            ref = r.get("p1d_pct")
        if ref is not None:
            r["hit_2pct"] = 1 if ref >= 2.0 else 0
            r["big_move_5pct"] = 1 if ref >= 5.0 else 0
            r["lost_3pct"] = 1 if ref <= -3.0 else 0
        updated += 1
        time.sleep(0.1)
    return updated


# ---------------------------------------------------------------------------
# Stats

def compute_stats(rows: list[dict]) -> tuple[dict, dict]:
    """Returns (overall_stats, by_signal_stats)."""
    def calc(subset: list[dict]) -> dict:
        scored = [r for r in subset if r.get("p5d_pct") is not None or r.get("p1d_pct") is not None]
        n5 = sum(1 for r in subset if r.get("p5d_pct") is not None)
        n30 = sum(1 for r in subset if r.get("p30d_pct") is not None)
        if not scored:
            return {"n": len(subset), "n_5d": n5, "n_30d": n30,
                    "hit_rate_2pct": None, "big_move_rate_5pct": None,
                    "loss_rate_3pct": None, "avg_pl_pct": None,
                    "avg_vs_spy_5d_pct": None, "avg_vs_spy_30d_pct": None}
        hits = sum(1 for r in scored if r.get("hit_2pct") == 1)
        bigs = sum(1 for r in scored if r.get("big_move_5pct") == 1)
        loss = sum(1 for r in scored if r.get("lost_3pct") == 1)

        def avg(field: str) -> float | None:
            vals = [to_float(r.get(field)) for r in scored]
            vals = [v for v in vals if v is not None]
            return round(sum(vals) / len(vals), 4) if vals else None

        return {
            "n": len(subset),
            "n_5d": n5,
            "n_30d": n30,
            "hit_rate_2pct": round(hits / len(scored), 4),
            "big_move_rate_5pct": round(bigs / len(scored), 4),
            "loss_rate_3pct": round(loss / len(scored), 4),
            "avg_pl_pct": avg("p5d_pct"),
            "avg_vs_spy_5d_pct": avg("vs_spy_5d_pct"),
            "avg_vs_spy_30d_pct": avg("vs_spy_30d_pct"),
        }

    overall = calc(rows)
    by_signal: dict[str, dict] = {}
    sigs = sorted({r.get("signal") or "unknown" for r in rows})
    for s in sigs:
        by_signal[s] = calc([r for r in rows if (r.get("signal") or "unknown") == s])
    return overall, by_signal


def write_summary_csv(by_signal: dict[str, dict]) -> None:
    """Mirror sec_outcome_summary.csv shape so tune_scoring_config.py can consume it."""
    # sec_outcome_summary.csv columns:
    # list_name,rows,wins,losses,avg_gap_next_open_pct,avg_next_day_max_run_pct,
    # avg_next_day_close_pct,hit_rate_2pct,hit_rate_3pct,hit_rate_5pct
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "list_name", "rows", "wins", "losses",
            "avg_gap_next_open_pct", "avg_next_day_max_run_pct",
            "avg_next_day_close_pct", "hit_rate_2pct",
            "hit_rate_3pct", "hit_rate_5pct",
        ])
        for sig, s in by_signal.items():
            n = s.get("n") or 0
            hr = s.get("hit_rate_2pct")
            wins = int(round((hr or 0) * (s.get("n_5d") or 0))) if hr is not None else 0
            losses = (s.get("n_5d") or 0) - wins
            w.writerow([
                f"agent_{sig}",
                n, wins, losses,
                "", "",                                   # gap fields not tracked yet
                s.get("avg_pl_pct") or "",
                round((hr or 0) * 100, 2) if hr is not None else "",
                "",                                        # hit_rate_3pct (not tracked)
                round((s.get("big_move_rate_5pct") or 0) * 100, 2)
                  if s.get("big_move_rate_5pct") is not None else "",
            ])


# ---------------------------------------------------------------------------
# Main

def main() -> int:
    load_env()
    key = os.environ.get("ALPACA_API_KEY_ID", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET", "").strip()
    base = (os.environ.get("ALPACA_BASE_URL")
            or "https://paper-api.alpaca.markets").strip()

    if not key or not secret:
        log("ABORT: Alpaca keys missing")
        write_status({"ok": False, "reason": "alpaca_keys_missing"})
        return 0

    rows = load_ledger()
    initial = len(rows)
    added = ingest_orders_json(rows)
    log(f"ledger | initial={initial} new_from_orders_json={added}")

    # Refresh open positions for exit detection
    code_p, positions, req_id = alpaca_get(f"{base.rstrip('/')}/v2/positions", key, secret)
    if code_p != 200 or not isinstance(positions, list):
        positions = []
    open_symbols = {(p.get("symbol") or "").upper() for p in positions}

    fills = capture_fills(rows, base, key, secret)
    exits = capture_exits(rows, base, key, secret, open_symbols)
    horizons_updated = compute_horizons(rows, key, secret)

    save_ledger(rows)

    overall, by_signal = compute_stats(rows)
    write_summary_csv(by_signal)

    fills_total = sum(1 for r in rows if r.get("fill_ts_utc"))
    exits_total = sum(1 for r in rows if r.get("exit_ts_utc"))
    n5 = sum(1 for r in rows if r.get("p5d_pct") is not None)
    n30 = sum(1 for r in rows if r.get("p30d_pct") is not None)

    rows_sorted = sorted(rows, key=lambda r: r.get("entry_ts_utc") or "", reverse=True)
    recent = []
    for r in rows_sorted[:25]:
        recent.append({k: r.get(k) for k in LEDGER_FIELDS})

    payload = {
        "ok": True,
        "x_request_id": req_id,
        "ledger_rows": len(rows),
        "fills_captured": fills_total,
        "exits_captured": exits_total,
        "horizon_complete_5d": n5,
        "horizon_complete_30d": n30,
        "stats": overall,
        "by_signal": by_signal,
        "recent_outcomes": recent,
    }
    write_status(payload)
    log(
        f"summary | rows={len(rows)} new={added} fills={fills_total} exits={exits_total} "
        f"n5={n5} n30={n30} hit_2pct={overall.get('hit_rate_2pct')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
