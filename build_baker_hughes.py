#!/usr/bin/env python3
"""build_baker_hughes.py — Weekly North America rig count (Friday 1pm ET).

Rig count is a leading indicator of drilling activity → revenue for
oilfield services (SLB, HAL, BKR, LBRT, NEX, PTEN, RPC, HP) and proppant/
frac-sand (CVIA, SLCA). Trump-era lean inventories + capital discipline
means rig-count surprises move these ~5–10% on the day of release.

Source: bakerhughesrigcount.com (public HTML table).
Output: baker_hughes_rigs.csv
Columns: date, us_rigs, us_delta_wk, us_delta_yr, canada_rigs, intl_rigs, oil_rigs, gas_rigs, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "baker_hughes_rigs.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
URLS = [
    "https://bakerhughesrigcount.gcs-web.com/na-rig-count",
    "https://rigcount.bakerhughes.com/na-rig-count",
]


def fetch(url: str, timeout: int = 25) -> str | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"baker_hughes: {e}")
        return None


def _int(s: str) -> int:
    try:
        return int(re.sub(r"[^\d-]", "", s) or 0)
    except Exception:
        return 0


def parse(html: str) -> list[dict]:
    rows: list[dict] = []
    # Current rig count table: look for rows with date + 3-5 numeric cells
    tr_rx = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.I)
    cell_rx = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.I)
    date_rx = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})")
    seen: set[str] = set()
    for tr in tr_rx.findall(html):
        cells = [re.sub(r"<[^>]+>", " ", c).strip() for c in cell_rx.findall(tr)]
        if len(cells) < 3:
            continue
        dm = date_rx.search(cells[0])
        if not dm:
            continue
        m, d, y = dm.groups()
        y = int(y) if len(y) == 4 else 2000 + int(y)
        try:
            date = f"{y}-{int(m):02d}-{int(d):02d}"
        except Exception:
            continue
        if date in seen:
            continue
        seen.add(date)
        nums = [_int(c) for c in cells[1:7]]
        nums += [0] * max(0, 6 - len(nums))
        rows.append({
            "date": date,
            "us_rigs": nums[0],
            "us_delta_wk": nums[1],
            "us_delta_yr": nums[2],
            "canada_rigs": nums[3],
            "intl_rigs": nums[4],
            "oil_rigs": nums[5],
            "gas_rigs": 0,
        })
    return rows


def main() -> None:
    html = ""
    for u in URLS:
        html = fetch(u) or ""
        if html and "rig" in html.lower():
            break
    rows = parse(html) if html else []
    rows.sort(key=lambda r: r["date"], reverse=True)
    rows = rows[:52]
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "us_rigs", "us_delta_wk", "us_delta_yr",
                "canada_rigs", "intl_rigs", "oil_rigs", "gas_rigs",
                "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"baker_hughes: {len(rows)} weeks | latest {latest.get('date','?')} "
          f"US={latest.get('us_rigs','?')} delta={latest.get('us_delta_wk','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
