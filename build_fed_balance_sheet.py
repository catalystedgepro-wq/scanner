#!/usr/bin/env python3
"""build_fed_balance_sheet.py — Fed balance sheet H.4.1 weekly (QT/QE pace).

Fed balance sheet = primary liquidity tap. QE expansion → risk-on (SPY,
QQQ, BTC). QT runoff → risk-off, especially long-duration tech. Movers:
TLT, IEF (rates), HYG/JNK (credit), BTC proxy.

Source: FRED WALCL (total assets), TREAST (Treasuries), WSHOMCB (MBS),
RESPPLLOPNWW (reverse repo).

Output: fed_balance_sheet.csv
Columns: week_end, total_assets_b, treasuries_b, mbs_b, reverse_repo_b,
         wow_change_b, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fed_balance_sheet.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("total_assets_b", "WALCL"),
    ("treasuries_b", "TREAST"),
    ("mbs_b", "WSHOMCB"),
    ("reverse_repo_b", "RRPONTSYD"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"fedbs {sid}: {e}")
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
    return out[-104:]


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    tot_sorted = sorted(data["total_assets_b"].keys())
    idx = {d: i for i, d in enumerate(tot_sorted)}
    dates = sorted(data["total_assets_b"].keys(), reverse=True)[:104]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = data["total_assets_b"].get(d, 0)
        i = idx.get(d, -1)
        prev = data["total_assets_b"].get(tot_sorted[i - 1], 0) if i >= 1 else 0
        wow = f"{(cur - prev) / 1e3:.1f}" if prev else ""
        rows.append({
            "week_end": d,
            "total_assets_b": f"{cur / 1e3:.0f}",
            "treasuries_b": f"{data['treasuries_b'].get(d, 0) / 1e3:.0f}",
            "mbs_b": f"{data['mbs_b'].get(d, 0) / 1e3:.0f}",
            "reverse_repo_b": f"{data['reverse_repo_b'].get(d, 0):.0f}",
            "wow_change_b": wow,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "week_end", "total_assets_b", "treasuries_b",
                "mbs_b", "reverse_repo_b", "wow_change_b", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"fed_balance_sheet: {len(rows)} weeks | latest {latest.get('week_end','?')} "
          f"total=${latest.get('total_assets_b','?')}B wow={latest.get('wow_change_b','?')}B "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
