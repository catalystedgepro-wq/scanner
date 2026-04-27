#!/usr/bin/env python3
"""build_fed_funds_futures.py — Fed funds futures-implied path (daily).

CME FedWatch-equivalent expectations. Change in next-3-meeting implied
cuts = single biggest overnight driver of SPX, QQQ, IWM, XLRE, XLF.
Bank of America, regional banks (KRE) rip on 50bp+ cuts priced in.

Source: FRED DFEDTAR (upper target), DFEDTARU (upper limit),
DFEDTARL (lower limit), EFFR (effective rate).
Output: fed_funds_futures.csv
Columns: date, fed_upper, fed_lower, effective, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fed_funds_futures.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("fed_upper", "DFEDTARU"),
    ("fed_lower", "DFEDTARL"),
    ("effective", "EFFR"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"fed {sid}: {e}")
        return []
    out = []
    for line in txt.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if v in {".", ""}:
            continue
        try:
            out.append((d, float(v)))
        except Exception:
            pass
    return out[-120:]


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    dates = sorted(data["fed_upper"].keys(), reverse=True)[:90]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        rows.append({
            "date": d,
            "fed_upper": f"{data['fed_upper'].get(d, 0):.2f}",
            "fed_lower": f"{data['fed_lower'].get(d, 0):.2f}",
            "effective": f"{data['effective'].get(d, 0):.2f}",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "fed_upper", "fed_lower", "effective", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"fed_funds: {len(rows)} days | latest {latest.get('date','?')} "
          f"upper={latest.get('fed_upper','?')} eff={latest.get('effective','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
