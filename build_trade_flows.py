#!/usr/bin/env python3
"""build_trade_flows.py — US monthly imports/exports by partner (Census).

Monthly US trade with the 10 largest partners. Leading signal for
supply-chain-exposed stocks:
- China imports -> AAPL/TSLA/NKE/WMT/TGT input costs + tariff
  pass-through margin risk.
- Mexico imports surging -> auto OEMs (F, GM, STLA) and near-shoring
  beneficiaries (EXP, TXN fabs).
- Vietnam/India imports up, China down -> diversification thesis
  (NKE, LULU, ICL logistics).
- Total imports shrinking fast -> recession signal (port volume drops,
  EXPD/FDX/UPS earnings pressure, CHRW freight fade).
- Export surge to Europe -> dollar weakens or industrial demand (CAT,
  DE, OTIS) rally.

Source: api.census.gov/data/timeseries/intltrade/imports/hs +
api.census.gov/data/timeseries/intltrade/exports/hs. Public, no key
needed for low-volume queries, monthly 45-day lag.

Output: trade_flows.csv
Columns: month, country, imports_usd, exports_usd, trade_balance,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "trade_flows.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# Census country codes for top-10 US trading partners + near-shoring
# and supply-chain diversification watch list.
COUNTRIES = {
    "5700": "CHINA",
    "2010": "MEXICO",
    "1220": "CANADA",
    "5880": "JAPAN",
    "5820": "SOUTH KOREA",
    "4280": "GERMANY",
    "5830": "TAIWAN",
    "5520": "VIETNAM",
    "5330": "INDIA",
    "4120": "UNITED KINGDOM",
    "4759": "NETHERLANDS",
    "4279": "FRANCE",
    "4210": "IRELAND",
    "5570": "SINGAPORE",
}


def months_window(n: int = 12) -> tuple[str, str]:
    """Return (from, to) YYYY-MM strings spanning last n months."""
    today = dt.date.today().replace(day=1)
    # Census has ~45-day lag, so shift end back 2 months.
    end = today - dt.timedelta(days=45)
    end = end.replace(day=1)
    start = end
    for _ in range(n - 1):
        prev = start - dt.timedelta(days=1)
        start = prev.replace(day=1)
    return start.strftime("%Y-%m"), end.strftime("%Y-%m")


def census_fetch(direction: str, code: str,
                 t_from: str, t_to: str) -> list[tuple[str, int]]:
    """direction: 'imports' or 'exports'. Returns [(YYYY-MM, usd)]."""
    val_col = "GEN_VAL_MO" if direction == "imports" else "ALL_VAL_MO"
    params = {
        "get": f"{val_col},CTY_NAME",
        "time": f"from {t_from} to {t_to}",
        "CTY_CODE": code,
    }
    url = (
        f"https://api.census.gov/data/timeseries/intltrade/{direction}/hs?"
        + urllib.parse.urlencode(params)
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    payload = None
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                payload = json.loads(r.read().decode("utf-8", errors="ignore"))
            break
        except Exception as e:
            last_err = e
    if payload is None:
        print(f"trade_flows {direction} {code}: {last_err}")
        return []
    if not isinstance(payload, list) or len(payload) < 2:
        return []
    header = payload[0]
    try:
        val_i = header.index(val_col)
        time_i = header.index("time")
    except ValueError:
        return []
    out: list[tuple[str, int]] = []
    for row in payload[1:]:
        try:
            out.append((row[time_i], int(row[val_i])))
        except (ValueError, IndexError):
            continue
    return out


def main() -> None:
    t_from, t_to = months_window(12)
    merged: dict[tuple[str, str], dict[str, int]] = {}
    for code, name in COUNTRIES.items():
        imp = dict(census_fetch("imports", code, t_from, t_to))
        exp = dict(census_fetch("exports", code, t_from, t_to))
        months = sorted(set(imp.keys()) | set(exp.keys()))
        for m in months:
            merged[(m, name)] = {
                "imports": imp.get(m, 0),
                "exports": exp.get(m, 0),
            }
    # Preserve existing data when this run is obviously degraded: empty, or
    # sparse enough that zeros would poison downstream consumers. Trigger on
    # >20% of country-months having both imports and exports == 0 (a good
    # run has near-zero such rows — exports always populate).
    zero_rows = sum(
        1 for v in merged.values() if not v["imports"] and not v["exports"]
    )
    degraded = (
        not merged
        or (len(merged) and zero_rows / len(merged) > 0.20)
    )
    if degraded and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"trade_flows: fetch degraded ({zero_rows}/{len(merged)} "
              f"empty rows), keeping existing {OUT_CSV.name} "
              f"({OUT_CSV.stat().st_size} bytes)")
        return
    rows: list[dict] = []
    for (m, name), v in sorted(merged.items()):
        imp, exp = v["imports"], v["exports"]
        rows.append({
            "month": m,
            "country": name,
            "imports_usd": imp,
            "exports_usd": exp,
            "trade_balance": exp - imp,
        })
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["month", "country", "imports_usd",
                        "exports_usd", "trade_balance", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    # Find latest China line for the status print.
    china = [r for r in rows if r["country"] == "CHINA"]
    latest = china[-1] if china else (rows[-1] if rows else {})
    print(f"trade_flows: {len(rows)} rows "
          f"({len({r['month'] for r in rows})} months × "
          f"{len({r['country'] for r in rows})} partners) | "
          f"latest CHINA {latest.get('month','?')} "
          f"imports=${int(latest.get('imports_usd',0))/1e9:.1f}B "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
