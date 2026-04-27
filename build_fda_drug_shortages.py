#!/usr/bin/env python3
"""build_fda_drug_shortages.py — Current FDA drug shortages.

Drug shortages move generic makers (TEVA, VTRS, AMPH, PRGO, LNTH), CMOs
(CTLT, LH, CMO-specific), and sometimes benefit specialty pharma with
unique supply (RHHBY, PFE). Shortage additions/resolutions are 2–5% moves.

Source: fda.gov/drugs/drug-shortages (scrape, free). FDA also provides
an app backend JSON.

Output: fda_drug_shortages.csv
Columns: drug, status, reason, therapeutic_class, update_date, url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_drug_shortages.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

URL = "https://www.accessdata.fda.gov/scripts/drugshortages/default.cfm"


def fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"fda_shortage: {e}")
        return None


def parse(html: str) -> list[dict]:
    rows: list[dict] = []
    tr_rx = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.I)
    cell_rx = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.I)
    link_rx = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.I)
    for tr in tr_rx.findall(html):
        cells = [re.sub(r"<[^>]+>", " ", c).strip() for c in cell_rx.findall(tr)]
        if len(cells) < 2:
            continue
        drug = cells[0]
        if not drug or drug.lower() in {"drug", "generic name"}:
            continue
        status = cells[1] if len(cells) > 1 else ""
        urlm = link_rx.search(tr)
        href = urlm.group(1) if urlm else ""
        if href and not href.startswith("http"):
            href = "https://www.accessdata.fda.gov/scripts/drugshortages/" + href.lstrip("/")
        rows.append({
            "drug": drug[:120],
            "status": status,
            "reason": "",
            "therapeutic_class": "",
            "update_date": "",
            "url": href,
        })
    return rows[:200]


def main() -> None:
    html = fetch(URL) or ""
    rows = parse(html)
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "drug", "status", "reason", "therapeutic_class",
                "update_date", "url", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"fda_drug_shortages: {len(rows)} drugs -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
