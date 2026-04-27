#!/usr/bin/env python3
"""build_kalshi_macro.py — Kalshi macroeconomic prediction markets.

Kalshi is the CFTC-regulated real-money event-futures exchange. Because
contracts clear in USD, the yes/no prices are *calibrated probability*
(unlike Polymarket, which is crypto-collateralized). Real-money macro
consensus = the cleanest prior for binary macro catalysts.

Signal:
- FED rate-decision markets → rate-cut beta for KRE, IYR, XLU, QQQ
- CPI/Inflation markets → TIPS vs nominals, XLE crude sensitivity
- Recession / GDP / NFP / unemployment markets → cyclical vs defensive
- Tech-layoff markets → AI capex sentiment (read-through to META/AMZN)
- Powell leaving / Fed chair markets → front-end volatility regime
- Debt-ceiling / government-shutdown markets → short-T-bill / TGA impact

Source: api.elections.kalshi.com/trade-api/v2/markets (no auth)
Output: kalshi_macro.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "kalshi_macro.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Map macro-series ticker → category for summary routing.
SERIES_CATEGORIES = {
    "FED": "fed_policy",
    "KXFEDDECISION": "fed_policy",
    "LEAVEPOWELL": "fed_policy",
    "CPI": "inflation",
    "KXHICP": "inflation",
    "KXLCPIMAX": "inflation",
    "KXLCPIMAXYOY": "inflation",
    "ACPI": "inflation",
    "KXGDPYEAR": "growth",
    "KXGDPSHAREMANU": "growth",
    "RECESSION": "growth",
    "KXUSPSPEND": "growth",
    "KXISMSERVICES": "growth",
    "KXEHSALES": "housing",
    "KXTECHLAYOFF": "labor",
    "KXLAYOFFSYINFO": "labor",
    "KXLAYOFFSYPBS": "labor",
    "KXUSDEBT": "fiscal",
    "KXUSDEBTMON": "fiscal",
    "KXNGASW": "commodity",
    "DIESELM": "commodity",
    "KXRUCRUDEX": "commodity",
}


def _get(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"kalshi_macro: {url[:100]}: {e}")
        return None


def _fetch_series(series: str) -> list[dict]:
    all_markets: list[dict] = []
    cursor = ""
    for _ in range(3):  # up to 300 markets per series
        url = (f"{BASE}/markets?status=open&series_ticker={series}"
               f"&limit=100")
        if cursor:
            url += f"&cursor={cursor}"
        payload = _get(url)
        if not payload:
            break
        mk = payload.get("markets", [])
        if not mk:
            break
        all_markets.extend(mk)
        cursor = payload.get("cursor") or ""
        if not cursor:
            break
    return all_markets


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")

    for series, cat in SERIES_CATEGORIES.items():
        markets = _fetch_series(series)
        for m in markets:
            try:
                yes_ask = float(m.get("yes_ask_dollars") or 0)
                yes_bid = float(m.get("yes_bid_dollars") or 0)
                last = float(m.get("last_price_dollars") or 0)
                liq = float(m.get("liquidity_dollars") or 0)
            except Exception:
                continue
            # yes_ask ≈ $1 implies ~100% probability; $0.50 ≈ 50%.
            prob = (yes_ask + yes_bid) / 2 if (yes_bid or yes_ask) else last
            # volume_fp is an integer (fixed-point).
            try:
                vol = int(m.get("volume_fp") or 0)
                vol24h = int(m.get("volume_24h_fp") or 0)
                oi = int(m.get("open_interest_fp") or 0)
            except Exception:
                vol = vol24h = oi = 0
            rows.append({
                "ticker": m.get("ticker", ""),
                "series": series,
                "category": cat,
                "title": (m.get("title") or "")[:200],
                "yes_sub_title": (m.get("yes_sub_title") or "")[:80],
                "prob_yes": f"{prob:.4f}",
                "last_price": f"{last:.4f}",
                "liquidity_usd": f"{liq:.2f}",
                "volume_fp": str(vol),
                "volume_24h_fp": str(vol24h),
                "open_interest_fp": str(oi),
                "close_time": m.get("close_time", "") or "",
                "captured_at": now_iso,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"kalshi_macro: empty, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["category"], -int(r["volume_fp"] or 0)))

    fieldnames = ["ticker", "series", "category", "title", "yes_sub_title",
                  "prob_yes", "last_price", "liquidity_usd",
                  "volume_fp", "volume_24h_fp", "open_interest_fp",
                  "close_time", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: top markets per category by volume.
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    bits: list[str] = []
    for cat in ("fed_policy", "inflation", "growth", "labor"):
        recs = by_cat.get(cat, [])
        if not recs:
            continue
        top = max(recs, key=lambda r: int(r["volume_fp"] or 0))
        bits.append(f"{cat}:{top['series']}={float(top['prob_yes']):.0%}"
                    f"(vol={top['volume_fp']})")
    print(f"kalshi_macro: {len(rows)} markets | {' | '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
