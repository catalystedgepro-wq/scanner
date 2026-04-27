#!/usr/bin/env python3
"""agent_defi_shadow.py — DeFi shadow trader (no venue, signal tracking only).

Reads docs/defi_liquidations.csv (top-protocol TVL snapshot with stress_label),
fires bullish/bearish "shadow trades" against the top 10 protocols by TVL, and
maintains a 5-day-horizon outcome ledger so the audit pipeline can grade
DeFi signal accuracy alongside equities, crypto, and options.

Output:
  - docs/data/defi_shadow.json     live snapshot for /trades/ + /status/
  - agent_defi_shadow_ledger.csv   persistent ledger for outcome scoring

Signal logic per protocol:
  BULLISH: stress_label == "drift" AND -1.0 <= change_1d_pct <= 3.0
           AND change_7d_pct > -10.0
  BEARISH: stress_label != "drift" OR change_1d_pct <= -3.0
           OR change_7d_pct <= -15.0
  NEUTRAL: anything else (no shadow trade)

Idempotency: client_order_id = ce_defi_<YYYY-MM-DD>_<protocol_slug>_shadow
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
DEFI_CSV = ROOT / "docs/defi_liquidations.csv"
OUT = ROOT / "docs/data/defi_shadow.json"
LEDGER_CSV = ROOT / "agent_defi_shadow_ledger.csv"
LOG = ROOT / "logs/defi_shadow.log"
OUT.parent.mkdir(parents=True, exist_ok=True)
LOG.parent.mkdir(exist_ok=True)

UNIVERSE_SIZE = 10
HORIZON_DAYS = 5
TP_PCT = 0.05
SL_PCT = -0.03
NOTIONAL_USD = 100.0

LEDGER_FIELDS = [
    "client_order_id", "captured_at", "protocol", "signal",
    "entry_tvl", "change_1d_pct", "change_7d_pct",
    "horizon_5d_change_pct", "horizon_5d_evaluated_at",
    "hit_5pct", "lost_3pct",
]


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def write_status(payload: dict) -> None:
    payload.setdefault("last_attempt_utc",
                       datetime.now(timezone.utc).isoformat(timespec="seconds"))
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True))


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name or "").strip("_").lower()
    return s or "unknown"


def to_float(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# CSV I/O

def latest_protocol_snapshot() -> dict[str, dict]:
    """Return {protocol_name: most-recent row}, parsed from defi_liquidations.csv.

    File is overwritten each cron cycle, so it carries today's snapshot only.
    Multiple historical runs may have been appended; take the last row per protocol.
    """
    if not DEFI_CSV.exists():
        return {}
    by_protocol: dict[str, dict] = {}
    with DEFI_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("protocol") or "").strip()
            if not name:
                continue
            by_protocol[name] = r  # later rows overwrite earlier
    return by_protocol


def top_n(snapshots: dict[str, dict], n: int) -> list[dict]:
    rows = list(snapshots.values())
    rows.sort(key=lambda r: to_float(r.get("tvl_usd")) or 0, reverse=True)
    return rows[:n]


def load_ledger() -> list[dict]:
    if not LEDGER_CSV.exists():
        return []
    rows = []
    with LEDGER_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
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


# ---------------------------------------------------------------------------
# Signal classification

def classify(row: dict) -> str:
    """Returns 'defi_shadow_bull', 'defi_shadow_bear', or 'neutral'."""
    stress = (row.get("stress_label") or "").lower()
    c1 = to_float(row.get("change_1d_pct"))
    c7 = to_float(row.get("change_7d_pct"))

    # Bearish first (loss-of-stress dominates)
    if stress != "drift":
        return "defi_shadow_bear"
    if c1 is not None and c1 <= -3.0:
        return "defi_shadow_bear"
    if c7 is not None and c7 <= -15.0:
        return "defi_shadow_bear"

    # Bullish
    if (stress == "drift"
            and c1 is not None and -1.0 <= c1 <= 3.0
            and (c7 is None or c7 > -10.0)):
        return "defi_shadow_bull"

    return "neutral"


# ---------------------------------------------------------------------------
# Ingest + horizon evaluation

def ingest(top_rows: list[dict], ledger: list[dict]) -> tuple[int, int, int, list[dict]]:
    """Return (bullish, bearish, neutral, new_signals)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing_ids = {r.get("client_order_id") for r in ledger}
    bullish = bearish = neutral = 0
    new_signals: list[dict] = []
    for row in top_rows:
        sig = classify(row)
        proto = (row.get("protocol") or "").strip()
        if sig == "defi_shadow_bull":
            bullish += 1
        elif sig == "defi_shadow_bear":
            bearish += 1
        else:
            neutral += 1
            continue
        coid = f"ce_defi_{today}_{slugify(proto)}_shadow"
        if coid in existing_ids:
            continue
        new_row = {
            "client_order_id": coid,
            "captured_at": row.get("captured_at"),
            "protocol": proto,
            "signal": sig,
            "entry_tvl": to_float(row.get("tvl_usd")),
            "change_1d_pct": to_float(row.get("change_1d_pct")),
            "change_7d_pct": to_float(row.get("change_7d_pct")),
            "horizon_5d_change_pct": None,
            "horizon_5d_evaluated_at": None,
            "hit_5pct": None,
            "lost_3pct": None,
        }
        ledger.append(new_row)
        new_signals.append(new_row)
    return bullish, bearish, neutral, new_signals


def evaluate_horizons(ledger: list[dict], snapshots: dict[str, dict]) -> int:
    """For ledger rows with no horizon outcome and entry >= HORIZON_DAYS old, compute."""
    now = datetime.now(timezone.utc)
    updated = 0
    for r in ledger:
        if r.get("horizon_5d_change_pct") is not None:
            continue
        captured = r.get("captured_at")
        if not captured:
            continue
        try:
            cap_dt = datetime.fromisoformat(str(captured).replace("Z", "+00:00"))
        except Exception:
            continue
        if (now - cap_dt) < timedelta(days=HORIZON_DAYS):
            continue
        proto = r.get("protocol")
        cur = snapshots.get(proto) if proto else None
        if not cur:
            continue
        cur_tvl = to_float(cur.get("tvl_usd"))
        entry = to_float(r.get("entry_tvl"))
        if not cur_tvl or not entry:
            continue
        pct = round((cur_tvl / entry - 1) * 100, 4)
        # For bear signals we want negative moves to "hit"; flip sign for evaluation
        sig = r.get("signal") or ""
        ref = pct if sig == "defi_shadow_bull" else -pct
        r["horizon_5d_change_pct"] = pct
        r["horizon_5d_evaluated_at"] = now.isoformat(timespec="seconds")
        r["hit_5pct"] = 1 if ref >= TP_PCT * 100 else 0
        r["lost_3pct"] = 1 if ref <= SL_PCT * 100 else 0
        updated += 1
    return updated


# ---------------------------------------------------------------------------
# Main

def main() -> int:
    if not DEFI_CSV.exists():
        log(f"ABORT: {DEFI_CSV} missing")
        write_status({"ok": False, "reason": "defi_liquidations_csv_missing"})
        return 0

    snapshots = latest_protocol_snapshot()
    if not snapshots:
        log("ABORT: no protocol rows parsed")
        write_status({"ok": False, "reason": "no_defi_rows"})
        return 0

    top_rows = top_n(snapshots, UNIVERSE_SIZE)
    ledger = load_ledger()
    bullish, bearish, neutral, new_signals = ingest(top_rows, ledger)
    updated = evaluate_horizons(ledger, snapshots)
    save_ledger(ledger)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    todays = [r for r in ledger if (r.get("client_order_id") or "").startswith(f"ce_defi_{today}_")]
    todays_signals = []
    for r in todays:
        proto = r.get("protocol") or ""
        todays_signals.append({
            "protocol": proto,
            "tvl_usd": r.get("entry_tvl"),
            "change_1d_pct": r.get("change_1d_pct"),
            "change_7d_pct": r.get("change_7d_pct"),
            "stress_label": (snapshots.get(proto) or {}).get("stress_label"),
            "signal": r.get("signal"),
            "client_order_id": r.get("client_order_id"),
            "entry_proxy": "tvl_usd_change",
            "horizon_days": HORIZON_DAYS,
            "tp_pct": TP_PCT,
            "sl_pct": SL_PCT,
        })

    # Stats from completed-horizon ledger rows
    completed = [r for r in ledger if r.get("horizon_5d_change_pct") is not None]
    hits = sum(1 for r in completed if r.get("hit_5pct") == 1)
    losses = sum(1 for r in completed if r.get("lost_3pct") == 1)
    avg_pct = (sum(to_float(r.get("horizon_5d_change_pct")) or 0 for r in completed) / len(completed)) if completed else None

    log(f"summary | top={len(top_rows)} bull={bullish} bear={bearish} neutral={neutral} "
        f"new={len(new_signals)} horizons_updated={updated} ledger_rows={len(ledger)} "
        f"completed={len(completed)}")

    write_status({
        "ok": True,
        "is_shadow_only": True,
        "rows_evaluated": len(top_rows),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "ledger_rows": len(ledger),
        "horizons_completed": len(completed),
        "stats": {
            "n": len(completed),
            "hit_rate_5pct": round(hits / len(completed), 4) if completed else None,
            "loss_rate_3pct": round(losses / len(completed), 4) if completed else None,
            "avg_horizon_5d_change_pct": round(avg_pct, 4) if avg_pct is not None else None,
        },
        "thresholds": {
            "horizon_days": HORIZON_DAYS,
            "tp_pct": TP_PCT,
            "sl_pct": SL_PCT,
            "notional_usd": NOTIONAL_USD,
        },
        "signals": todays_signals,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
