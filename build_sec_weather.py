#!/usr/bin/env python3
"""build_sec_weather.py — SEC physical-climate-event tape.

7 weather/disaster 8-K kinds (physical-risk disclosures vs
transition-risk already covered in sec_energy_tx):

- hurricane — Atlantic/Gulf storm damage, insured-losses Q&A.
  Names: CB/TRV/AIG/ALL (insurers), UNP/NSC (rail), AAL/DAL (air).
- wildfire — CA/NW/SW fire-season exposure. Canonical: PCG
  2018-2024 fire-liability overhang; SCE/SPWR/EDE downstream.
- drought — agriculture sector feed. Irrigation / Yield impact
  (CF, MOS, ADM, BG cluster).
- tornado — midwestern damage; feeds CB/TRV/ALL plus broker
  (MMC/AON).
- winter_storm — natural-gas/power demand spike; feeds LNG/CEG/
  VST power-producer bullish.
- extreme_weather — umbrella term, often in SEC-required TCFD-
  aligned language.
- natural_disaster — broad umbrella; declared-disaster FEMA-
  referenced filings trigger SBA-loan and insurance language.

Economic readthrough:
- Hurricane/wildfire/tornado cluster -> insurer book-value
  pressure (CB/TRV/AIG/ALL) + reinsurance basket (RE/RNR).
- Drought cluster -> fertilizer bull (CF/MOS/NTR).
- Winter_storm cluster -> gas-utility (NJR/SRE/ATO) bull + natgas
  spot momentum.

Source: efts.sec.gov/LATEST/search-index
Output: sec_weather.csv

Lookback: 60 days.
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_weather.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES: dict[str, str] = {
    "hurricane": '"hurricane"',
    "wildfire": '"wildfire"',
    "drought": '"drought"',
    "tornado": '"tornado"',
    "winter_storm": '"winter storm"',
    "extreme_weather": '"extreme weather"',
    "natural_disaster": '"natural disaster"',
}

LIMITS = {
    "hurricane": 80,
    "wildfire": 50,
    "drought": 60,
    "tornado": 40,
    "winter_storm": 40,
    "extreme_weather": 80,
    "natural_disaster": 100,
}

TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")


def _fetch(kind: str, query: str, limit: int) -> list[dict]:
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=60)).isoformat()
    d_to = today.isoformat()
    qq = urllib.parse.quote(query)
    forms = urllib.parse.quote("8-K")
    url = (f"https://efts.sec.gov/LATEST/search-index?q={qq}"
           f"&dateRange=custom&startdt={d_from}&enddt={d_to}"
           f"&forms={forms}&from=0&size={min(limit, 100)}")
    out: list[dict] = []
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"sec_weather: {kind} fetch failed: {e}")
        return out
    for h in d.get("hits", {}).get("hits", []):
        src = h.get("_source") or {}
        names_list = src.get("display_names") or []
        names_str = " ".join(names_list)
        m = TICKER_RE.search(names_str)
        out.append({
            "kind": kind,
            "ticker": m.group(1) if m else "",
            "name": (names_list[0] if names_list else "")[:80],
            "form": src.get("form", ""),
            "filed": src.get("file_date", ""),
            "accession": h.get("_id", ""),
        })
    return out


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    rows: list[dict] = []
    counts: dict[str, int] = {}
    for kind, q in QUERIES.items():
        batch = _fetch(kind, q, LIMITS.get(kind, 100))
        counts[kind] = len(batch)
        rows.extend(batch)
        time.sleep(0.4)

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_weather: no fetch, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: (r["filed"], r["kind"]), reverse=True)
    fieldnames = ["kind", "ticker", "name", "form", "filed",
                  "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    cutoff = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    recent = [r for r in rows if r["filed"] >= cutoff and r["ticker"]]
    tkrs = [f"{r['kind'][:4]}:{r['ticker']}" for r in recent[:15]]
    cb = " ".join(f"{k[:4]}={v}" for k, v in counts.items())
    print(f"sec_weather: {len(rows)} rows | {cb} | "
          f"last14d={len(recent)} [{' '.join(tkrs)}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
