#!/usr/bin/env python3
"""build_aaii_sentiment.py — AAII weekly individual-investor sentiment.

Retail sentiment survey (bulls / bears / neutral). Historically
contrarian at extremes (>55% bulls = frothy top, >55% bears = capitulation
bottom). Drives retail-heavy names (HOOD, COIN, GME, AMC, BB, NVDA).

Source: AAII publishes via FRED aliases (some mirrored) or their CSV at
aaii.com/download-historical. Simpler: use AAII JSON via
aaii.com/investor-sentiment.

Output: aaii_sentiment.csv
Columns: week_end, bull, bear, neutral, spread, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "aaii_sentiment.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = "https://www.aaii.com/sentimentsurvey/sent_results"


def fetch() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"aaii: {e}")
        return ""


def pct(s: str) -> float:
    s = s.replace("%", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def main() -> None:
    html = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    # Parse the results table. Look for rows with date + three percent cells.
    # Pattern: MM/DD/YYYY ... XX.X% XX.X% XX.X%
    pattern = re.compile(
        r"(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}\.\d)%\s*(\d{1,2}\.\d)%\s*(\d{1,2}\.\d)%",
        re.S,
    )
    for m in pattern.finditer(html)[:20] if False else list(pattern.finditer(html))[:20]:
        date = m.group(1)
        try:
            mo, day, yr = date.split("/")
            iso = f"{yr}-{int(mo):02d}-{int(day):02d}"
        except Exception:
            iso = date
        bull = pct(m.group(2))
        neutral = pct(m.group(3))
        bear = pct(m.group(4))
        rows.append({
            "week_end": iso,
            "bull": bull,
            "bear": bear,
            "neutral": neutral,
            "spread": round(bull - bear, 1),
            "captured_at": now,
        })
    rows.sort(key=lambda r: r["week_end"], reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["week_end", "bull", "bear", "neutral", "spread", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"aaii_sentiment: {len(rows)} weeks | latest {latest.get('week_end','?')} "
          f"bull={latest.get('bull','?')} bear={latest.get('bear','?')} "
          f"spread={latest.get('spread','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
