#!/usr/bin/env python3
"""build_manifold_macro.py — Manifold prediction markets for macro.

Manifold is a play-money prediction market with broad coverage of
macro/political/corporate questions. Probabilities are battle-
tested by micro-traders (the market self-calibrates via LMSR), and
for macro topics the skew from random often leads consensus Wall
Street forecasts by weeks.

Terms searched (per sweep, each grabs top ~10 open markets):
- recession       macro-regime switch odds
- Fed rate cut    FOMC path expectations
- Fed rate hike   hawkish scenarios
- SPX             S&P 500 target levels
- bitcoin         crypto directional
- inflation       CPI reversion bets
- Trump           policy / legal / admin odds
- election        political shock
- OpenAI          AI industry shakeout
- China           geopolitical / trade

Signal for trading:
- Recession prob > 40% sustained + VIX < 20 = complacency hedge
  setup; bid VXX/SVIX options, fade IWM.
- SPX "above X by EOY" prob rising through 70% = consensus late
  bull; fade SPXL on 3d pullback.
- Fed rate-cut prob > 85% for next FOMC + DXY rising = market
  pricing cuts that won't come; bid TLT, fade USO.

Source: api.manifold.markets/v0/search-markets (no key).

Output: manifold_macro.csv
Columns: topic, question, probability_pct, volume_usd, close_time,
         market_id, url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "manifold_macro.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.manifold.markets/v0/search-markets"

TOPICS = [
    ("recession", "recession"),
    ("rate_cut", "Fed rate cut"),
    ("rate_hike", "Fed rate hike"),
    ("spx", "SPX"),
    ("bitcoin", "bitcoin"),
    ("inflation", "inflation"),
    ("trump", "Trump"),
    ("election", "election"),
    ("openai", "OpenAI"),
    ("china", "China Taiwan"),
    ("nvidia", "Nvidia"),
    ("tesla", "Tesla"),
    ("fed", "FOMC"),
    ("gold", "gold"),
    ("war", "war"),
]


def _fetch(term: str) -> list[dict]:
    qs = urllib.parse.urlencode({
        "term": term, "limit": "15", "filter": "open",
        "sort": "24-hour-vol",
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"manifold_macro {term}: {e}")
        return []
    return data if isinstance(data, list) else []


def main() -> None:
    rows: list[dict] = []
    seen_ids: set[str] = set()
    for topic_key, term in TOPICS:
        for m in _fetch(term):
            mid = m.get("id") or ""
            if not mid or mid in seen_ids:
                continue
            prob = m.get("probability")
            if prob is None:
                # Multi-outcome markets don't have a single probability.
                continue
            vol_all = m.get("volume") or 0
            # Only keep markets with *some* play-money liquidity.
            if vol_all < 50:
                continue
            seen_ids.add(mid)
            close_ts = m.get("closeTime") or 0
            close_iso = ""
            if isinstance(close_ts, (int, float)) and close_ts > 0:
                close_iso = (dt.datetime.fromtimestamp(
                    close_ts / 1000, tz=dt.timezone.utc)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z"))
            rows.append({
                "topic": topic_key,
                "question": (m.get("question") or "")[:180],
                "probability_pct": f"{float(prob) * 100:.1f}",
                "volume_usd": f"{float(vol_all):.0f}",
                "close_time": close_iso,
                "market_id": mid,
                "url": m.get("url") or "",
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"manifold_macro: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["topic"], -float(r["volume_usd"])))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["topic", "question", "probability_pct",
                  "volume_usd", "close_time", "market_id",
                  "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Top-volume market per macro topic.
    by_topic: dict[str, dict] = {}
    for r in rows:
        cur = by_topic.get(r["topic"])
        if cur is None or float(r["volume_usd"]) > float(cur["volume_usd"]):
            by_topic[r["topic"]] = r
    rec = by_topic.get("recession")
    rc = by_topic.get("rate_cut")
    rec_s = (f"recession: {rec['probability_pct']}% "
             f"(${rec['volume_usd']})" if rec else "")
    rc_s = (f"rate_cut: {rc['probability_pct']}% "
            f"(${rc['volume_usd']})" if rc else "")
    print(f"manifold_macro: {len(rows)} markets {len(by_topic)} topics "
          f"| {rec_s} | {rc_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
