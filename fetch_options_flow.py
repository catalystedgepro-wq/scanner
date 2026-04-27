#!/usr/bin/env python3
"""Fetch options chain data for high short-interest tickers.

Primary source: Tradier API (free brokerage account — api.tradier.com)
Fallback:       Yahoo Finance v7 options endpoint

Detects gamma squeeze setups: call-heavy OI near the money,
unusual call volume, and max-pain levels.

Outputs: options_flow.csv
Columns: ticker, current_price, call_oi, put_oi, pc_ratio,
         gamma_score, max_pain, atm_call_iv, unusual_call_vol

Setup: add TRADIER_TOKEN=your_token to .sec_email_env
       Get a free token at tradier.com (free brokerage account, no deposit)
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT       = Path(__file__).parent
SHORT_CSV  = ROOT / "short_data.csv"
OUT_CSV    = ROOT / "options_flow.csv"
CACHE_FILE = ROOT / ".options_flow_cache.json"
CACHE_TTL  = 6 * 3600  # 6 hours — covers full trading day

FIELDNAMES = [
    "ticker", "current_price", "call_oi", "put_oi", "pc_ratio",
    "gamma_score", "max_pain", "atm_call_iv", "unusual_call_vol",
]

# ── Load env ──────────────────────────────────────────────────────────────────

def _load_env() -> dict:
    env: dict = {}
    env_file = ROOT / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update(os.environ)
    return env

_ENV = _load_env()
TRADIER_TOKEN = _ENV.get("TRADIER_TOKEN", "")
TRADIER_BASE  = "https://api.tradier.com/v1"

YAHOO_OPT  = "https://query1.finance.yahoo.com/v7/finance/options/{symbol}"
YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# ── Cache ─────────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_cache(c: dict) -> None:
    CACHE_FILE.write_text(json.dumps(c))


# ── Tradier ───────────────────────────────────────────────────────────────────

def _tradier_request(path: str, params: dict | None = None) -> dict:
    url = f"{TRADIER_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode())


def _get_nearest_expiry_tradier(symbol: str) -> str | None:
    try:
        data = _tradier_request("/markets/options/expirations", {"symbol": symbol})
        dates = data.get("expirations", {})
        if not dates:
            return None
        date_list = dates.get("date", [])
        if isinstance(date_list, str):
            date_list = [date_list]
        today = datetime.date.today().isoformat()
        future = [d for d in date_list if d >= today]
        return future[0] if future else None
    except Exception:
        return None


def fetch_options_tradier(symbol: str) -> dict:
    expiry = _get_nearest_expiry_tradier(symbol)
    if not expiry:
        return {}
    try:
        data = _tradier_request("/markets/options/chains", {
            "symbol": symbol, "expiration": expiry, "greeks": "false"
        })
        options = data.get("options") or {}
        if not options:
            return {}
        chain = options.get("option") or []
        if isinstance(chain, dict):
            chain = [chain]

        calls = [o for o in chain if o.get("option_type") == "call"]
        puts  = [o for o in chain if o.get("option_type") == "put"]

        # Get current price from mid of ATM call
        price = 0.0
        for o in chain:
            if o.get("option_type") == "call":
                bid = float(o.get("bid") or 0)
                ask = float(o.get("ask") or 0)
                if bid > 0 and ask > 0:
                    # Use strike as proxy for current price (rough)
                    price = float(o.get("underlying_price") or o.get("strike") or 0)
                    break

        return _compute_metrics(symbol, price, calls, puts, source="tradier")
    except Exception:
        return {}


# ── Yahoo Finance fallback ────────────────────────────────────────────────────

def fetch_options_yahoo(symbol: str) -> dict:
    url = YAHOO_OPT.format(symbol=symbol.upper())
    req = urllib.request.Request(url, headers=YF_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())

        result  = data["optionChain"]["result"][0]
        meta    = result.get("quote", {})
        price   = float(meta.get("regularMarketPrice") or meta.get("ask") or 0)
        opts    = result.get("options", [{}])[0]
        calls   = opts.get("calls", [])
        puts    = opts.get("puts",  [])

        # Normalise Yahoo fields to match Tradier naming
        def _norm_yf(contracts: list, ctype: str) -> list:
            out = []
            for c in contracts:
                out.append({
                    "option_type":    ctype,
                    "strike":         float(c.get("strike", 0)),
                    "open_interest":  int(c.get("openInterest", 0) or 0),
                    "volume":         int(c.get("volume", 0) or 0),
                    "implied_volatility": float(c.get("impliedVolatility", 0) or 0),
                })
            return out

        return _compute_metrics(symbol, price,
                                _norm_yf(calls, "call"),
                                _norm_yf(puts, "put"),
                                source="yahoo")
    except Exception:
        return {}


# ── Shared metrics ────────────────────────────────────────────────────────────

def _compute_metrics(symbol: str, price: float,
                     calls: list, puts: list, source: str) -> dict:
    if not calls and not puts:
        return {}

    call_oi = sum(int(c.get("open_interest", 0) or 0) for c in calls)
    put_oi  = sum(int(p.get("open_interest", 0) or 0) for p in puts)
    pc_ratio = round(put_oi / max(1, call_oi), 3)

    # Near-the-money (within 30% of price)
    lo, hi = (price * 0.7, price * 1.3) if price > 0 else (0, float("inf"))
    ntm_calls = [c for c in calls if lo <= float(c.get("strike", 0) or 0) <= hi]
    ntm_puts  = [p for p in puts  if lo <= float(p.get("strike", 0) or 0) <= hi]
    ntm_call_oi = sum(int(c.get("open_interest", 0) or 0) for c in ntm_calls)
    ntm_put_oi  = sum(int(p.get("open_interest", 0) or 0) for p in ntm_puts)

    # ATM IV
    atm_iv = 0.0
    for c in calls:
        if price > 0 and price * 0.95 <= float(c.get("strike", 0) or 0) <= price * 1.05:
            atm_iv = round(float(c.get("implied_volatility", 0) or 0) * 100, 1)
            break

    # Unusual call volume
    unusual = 0
    for c in ntm_calls:
        oi  = int(c.get("open_interest", 0) or 0)
        vol = int(c.get("volume", 0) or 0)
        if oi > 100 and vol > oi * 0.5:
            unusual += vol

    # Gamma score 0-10
    gamma_score = 0
    if call_oi > 0 and put_oi > 0:
        if pc_ratio < 0.5:   gamma_score = 8
        elif pc_ratio < 0.8: gamma_score = 6
        elif pc_ratio < 1.0: gamma_score = 4
        elif pc_ratio < 1.3: gamma_score = 2
    if ntm_call_oi > ntm_put_oi * 1.5:
        gamma_score = min(10, gamma_score + 2)
    if unusual > 1000:
        gamma_score = min(10, gamma_score + 1)

    # Max pain
    strikes = sorted(set(
        [float(c.get("strike", 0)) for c in calls] +
        [float(p.get("strike", 0)) for p in puts]
    ))
    max_pain = price
    if strikes:
        min_loss = float("inf")
        for s in strikes:
            loss = (
                sum(max(0, s - float(c.get("strike", 0))) * int(c.get("open_interest", 0) or 0)
                    for c in calls) +
                sum(max(0, float(p.get("strike", 0)) - s) * int(p.get("open_interest", 0) or 0)
                    for p in puts)
            )
            if loss < min_loss:
                min_loss = loss
                max_pain = s

    return {
        "ticker":          symbol.upper(),
        "current_price":   round(price, 2),
        "call_oi":         call_oi,
        "put_oi":          put_oi,
        "pc_ratio":        pc_ratio,
        "gamma_score":     gamma_score,
        "max_pain":        round(max_pain, 2),
        "atm_call_iv":     atm_iv,
        "unusual_call_vol": unusual,
        "_source":         source,
    }


# ── Ticker loader ─────────────────────────────────────────────────────────────

def load_candidates() -> list[str]:
    if not SHORT_CSV.exists():
        return []
    out = []
    with SHORT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            si = float(row.get("short_pct_float", 0) or 0)
            if si >= 8.0:
                out.append(row["ticker"])
    return out[:40]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    now_ts  = int(datetime.datetime.now().timestamp())
    cache   = load_cache()
    tickers = load_candidates()

    use_tradier = bool(TRADIER_TOKEN)
    source_name = "Tradier" if use_tradier else "Yahoo Finance"
    print(f"fetch_options_flow: {len(tickers)} high-SI tickers via {source_name}")

    rows: list[dict] = []
    for i, ticker in enumerate(tickers):
        entry = cache.get(ticker)
        if entry and now_ts - int(entry.get("ts", 0)) < CACHE_TTL:
            data = entry.get("data", {})
        else:
            if use_tradier:
                data = fetch_options_tradier(ticker)
                if not data:  # Tradier missed it — try Yahoo fallback
                    data = fetch_options_yahoo(ticker)
            else:
                data = fetch_options_yahoo(ticker)

            cache[ticker] = {"ts": now_ts, "data": data}
            if i % 5 == 4:
                time.sleep(0.5)

        if data:
            rows.append(data)

    save_cache(cache)
    rows.sort(key=lambda r: int(r.get("gamma_score", 0) or 0), reverse=True)

    # Write CSV (strip internal _source field)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Archive dated copy
    dated = ROOT / f"options_flow_{datetime.date.today().isoformat()}.csv"
    dated.write_text(OUT_CSV.read_text(encoding="utf-8"), encoding="utf-8")

    gamma_hits = [r for r in rows if int(r.get("gamma_score", 0) or 0) >= 4]
    print(f"  Wrote {len(rows)} rows | {len(gamma_hits)} with gamma score >= 4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
