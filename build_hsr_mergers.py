#!/usr/bin/env python3
"""build_hsr_mergers.py — Hart-Scott-Rodino pre-merger filings (FTC/DOJ).

HSR Act mandates pre-notification of deals >$111.4M (2026 threshold). FTC
publishes monthly transaction reports. Second requests = regulatory
pushback (deal risk spikes). Movers: target-side + acquirer-side, risk-arb
funds (Merger Fund MERFX, IQ Merger Arb MNA).

Source: FTC Early Termination Notices JSON + monthly transaction reports
(ftc.gov/enforcement/premerger-notification-program).

Output: hsr_mergers.csv
Columns: date, acquirer, target, transaction_id, early_termination, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "hsr_mergers.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# FTC Early Termination Notices data set
URL = (
    "https://www.ftc.gov/sites/default/files/attachments/"
    "premerger-notification-program/early-termination-notices.json"
)

FALLBACK_URL = "https://www.ftc.gov/enforcement/premerger-notification-program/early-termination-notices"


def fetch_json() -> list:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"hsr json: {e}")
        return []


def fetch_html() -> str:
    req = urllib.request.Request(FALLBACK_URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"hsr html: {e}")
        return ""


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    data = fetch_json()
    if data:
        for rec in data[:200]:
            rows.append({
                "date": rec.get("date", "") or rec.get("date_granted", ""),
                "acquirer": (rec.get("acquiring_person", "") or rec.get("acquirer", ""))[:100],
                "target": (rec.get("acquired_entity", "") or rec.get("target", ""))[:100],
                "transaction_id": rec.get("pdf_transaction_number", "") or rec.get("id", ""),
                "early_termination": "yes",
                "captured_at": now,
            })
    else:
        html = fetch_html()
        # scrape table rows
        for row_html in re.findall(r"<tr[^>]*>(.+?)</tr>", html, re.S)[:100]:
            cells = re.findall(r"<t[dh][^>]*>(.+?)</t[dh]>", row_html, re.S)
            if len(cells) < 3:
                continue
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if not re.match(r"\d", clean[0]):
                continue
            rows.append({
                "date": clean[0][:10],
                "acquirer": clean[1][:100] if len(clean) > 1 else "",
                "target": clean[2][:100] if len(clean) > 2 else "",
                "transaction_id": clean[3] if len(clean) > 3 else "",
                "early_termination": "yes",
                "captured_at": now,
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "acquirer", "target", "transaction_id",
                "early_termination", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"hsr_mergers: {len(rows)} notices -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
