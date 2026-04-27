#!/usr/bin/env python3
"""build_alpaca_options_chain.py — Alpaca options chain probe.

Reads top 20 tickers from combined_priority.csv (total_score >= 5),
fetches each ticker's options chain via /v1beta1/options/snapshots/{SYMBOL},
filters to nearest expiry, flags unusual volume/OI activity.

Output: /home/operator/.openclaw/workspace/docs/data/options_flow.json

Reference: https://docs.alpaca.markets/reference/optionchain
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
COMBINED_CSV = ROOT / "combined_priority.csv"
OUT = ROOT / "docs/data/options_flow.json"
LOG = ROOT / "logs/options_flow.log"
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


def write_status(payload: dict) -> None:
    payload.setdefault("last_attempt_utc",
                       datetime.now(timezone.utc).isoformat(timespec="seconds"))
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True))


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


def to_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def to_int(v) -> int | None:
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_occ(occ: str) -> tuple[str, str, str, float] | None:
    """Parse OCC option symbol like 'AAPL250620C00210000' → (underlying, expiry, side, strike)."""
    # OCC format: ROOT YYMMDD C/P 8-digit-strike (strike * 1000)
    if not occ or len(occ) < 16:
        return None
    # Find the date+side+strike suffix at the end
    # Side char is at position -9 (C or P)
    if len(occ) < 15:
        return None
    side_pos = len(occ) - 9
    side_char = occ[side_pos]
    if side_char not in ("C", "P"):
        return None
    underlying = occ[:side_pos - 6]
    yymmdd = occ[side_pos - 6:side_pos]
    strike_raw = occ[side_pos + 1:]
    try:
        strike = float(strike_raw) / 1000.0
        yy, mm, dd = yymmdd[0:2], yymmdd[2:4], yymmdd[4:6]
        expiry = f"20{yy}-{mm}-{dd}"
        return underlying, expiry, "call" if side_char == "C" else "put", strike
    except ValueError:
        return None


def top_tickers(n: int, min_score: float) -> list[str]:
    if not COMBINED_CSV.exists():
        return []
    rows: list[tuple[str, float]] = []
    with COMBINED_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").strip().upper()
            if not t or "." in t or len(t) > 5:
                continue
            try:
                s = float(r.get("total_score") or 0)
            except ValueError:
                s = 0.0
            if s >= min_score:
                rows.append((t, s))
    rows.sort(key=lambda x: x[1], reverse=True)
    out: list[str] = []
    seen = set()
    for t, _ in rows:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= n:
            break
    return out


def extract_legs_from_snapshot(payload: dict, underlying: str) -> list[dict]:
    """Walk an Alpaca options snapshot response.

    Shape per docs is roughly: {"snapshots": {"<OCC_SYMBOL>": {"latestQuote": {...}, "latestTrade": {...},
                                                              "greeks": {...}, "impliedVolatility": ..., "openInterest": ...}, ...}}
    """
    snaps = payload.get("snapshots") or payload.get("data") or {}
    if not isinstance(snaps, dict):
        return []
    legs = []
    for occ, snap in snaps.items():
        if not isinstance(snap, dict):
            continue
        parsed = parse_occ(occ)
        if not parsed:
            continue
        und, expiry, side, strike = parsed
        und_use = und or underlying

        latest_quote = snap.get("latestQuote") or {}
        latest_trade = snap.get("latestTrade") or {}
        greeks = snap.get("greeks") or {}
        # Volume + open_interest sometimes nested in dailyBar or top-level
        daily = snap.get("dailyBar") or {}

        legs.append({
            "symbol": occ,
            "underlying": und_use,
            "expiry": expiry,
            "strike": strike,
            "side": side,
            "bid": to_float(latest_quote.get("bp") or latest_quote.get("bid")),
            "ask": to_float(latest_quote.get("ap") or latest_quote.get("ask")),
            "last_trade_price": to_float(latest_trade.get("p") or latest_trade.get("price")),
            "volume": to_int(daily.get("v") or snap.get("volume")),
            "open_interest": to_int(snap.get("openInterest") or snap.get("open_interest")),
            "implied_volatility": to_float(snap.get("impliedVolatility") or snap.get("implied_volatility")),
            "delta": to_float(greeks.get("delta")),
            "gamma": to_float(greeks.get("gamma")),
            "theta": to_float(greeks.get("theta")),
            "vega":  to_float(greeks.get("vega")),
        })
    return legs


def main() -> int:
    load_env()
    key = os.environ.get("ALPACA_API_KEY_ID", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET", "").strip()
    base = (os.environ.get("ALPACA_BASE_URL")
            or "https://paper-api.alpaca.markets").strip()
    data_base = (os.environ.get("ALPACA_DATA_URL")
                 or "https://data.alpaca.markets").rstrip("/")

    if not key or not secret:
        log("ABORT: Alpaca keys missing")
        write_status({"ok": False, "reason": "alpaca_keys_missing"})
        return 0

    is_paper = "paper" in base.lower()
    tickers = top_tickers(20, min_score=5.0)
    log(f"scanning {len(tickers)} tickers: {tickers[:8]}...")

    first_req_id = ""
    tickers_scanned: list[str] = []
    tickers_with_options: list[str] = []
    all_legs: list[dict] = []

    for i, t in enumerate(tickers):
        url = f"{data_base}/v1beta1/options/snapshots/{urllib.parse.quote(t)}?feed=indicative"
        code, body, req_id = alpaca_get(url, key, secret)
        if not first_req_id:
            first_req_id = req_id
        tickers_scanned.append(t)
        if code != 200 or not isinstance(body, dict):
            log(f"  {t}: HTTP {code} req_id={req_id}")
            time.sleep(0.1)
            continue
        legs = extract_legs_from_snapshot(body, t)
        if not legs:
            time.sleep(0.1)
            continue
        # Filter to nearest expiry only
        expiries = sorted({l["expiry"] for l in legs if l.get("expiry")})
        if not expiries:
            time.sleep(0.1)
            continue
        nearest = expiries[0]
        legs_near = [l for l in legs if l.get("expiry") == nearest]
        if legs_near:
            tickers_with_options.append(t)
            all_legs.extend(legs_near)
            log(f"  {t}: {len(legs_near)} legs at expiry {nearest}")
        time.sleep(0.1)

    # Compute unusual flags + sort
    unusual_legs: list[dict] = []
    for leg in all_legs:
        vol = leg.get("volume") or 0
        oi = leg.get("open_interest") or 0
        leg["unusual"] = bool(vol >= 100 and oi >= 100 and vol > 2 * oi)
        if leg["unusual"]:
            unusual_legs.append(leg)
    unusual_legs.sort(key=lambda l: l.get("volume") or 0, reverse=True)

    payload = {
        "ok": True,
        "is_paper": is_paper,
        "x_request_id": first_req_id,
        "tickers_scanned": tickers_scanned,
        "tickers_with_options": tickers_with_options,
        "unusual_count": len(unusual_legs),
        "unusual_legs": unusual_legs[:25],
        "all_legs_count": len(all_legs),
    }
    log(f"summary: scanned={len(tickers_scanned)} with_options={len(tickers_with_options)} "
        f"all_legs={len(all_legs)} unusual={len(unusual_legs)}")
    write_status(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
