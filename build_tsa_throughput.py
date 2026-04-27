#!/usr/bin/env python3
"""build_tsa_throughput.py — TSA daily passenger checkpoint volume.

Daily airport screenings vs 2019/2023 baseline = real-time travel
demand. AAL, DAL, UAL, LUV, ALK, JBLU, SAVE, HA, BA, ABNB, MAR, HLT,
H, CAR, HTZ all react. Also proxies consumer discretionary spending
health. Spikes around holidays confirm/deny seasonal strength.

Source: tsa.gov/travel/passenger-volumes (HTML table).
Output: tsa_throughput.csv
Columns: date, volume_2026, volume_2025, volume_2019, yoy_pct,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "tsa_throughput.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

URL = "https://www.tsa.gov/travel/passenger-volumes"


def fetch() -> list[dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"tsa: {e}")
        return []
    # Table row pattern: <td>date</td><td>num</td><td>num</td>...
    rows: list[dict] = []
    body_match = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not body_match:
        return []
    for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", body_match.group(1), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr.group(1), re.S)
        if len(cells) < 2:
            continue
        clean = [re.sub(r"<[^>]+>", "", c).strip().replace(",", "")
                 for c in cells]
        date_txt = clean[0]
        nums = []
        for c in clean[1:]:
            try:
                nums.append(int(c))
            except Exception:
                nums.append(0)
        # Parse date (varied formats: "4/17/2026" or "April 17, 2026")
        d_iso = ""
        try:
            if "/" in date_txt:
                m, d, y = date_txt.split("/")
                d_iso = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            else:
                d_iso = dt.datetime.strptime(date_txt, "%B %d, %Y").date().isoformat()
        except Exception:
            continue
        rows.append({
            "date": d_iso,
            "volume_2026": nums[0] if len(nums) > 0 else 0,
            "volume_2025": nums[1] if len(nums) > 1 else 0,
            "volume_2019": nums[-1] if len(nums) >= 3 else 0,
        })
    return rows


def main() -> None:
    rows = fetch()
    rows.sort(key=lambda r: r["date"], reverse=True)
    rows = rows[:60]
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        v_cur = r["volume_2026"]
        v_py = r["volume_2025"]
        r["yoy_pct"] = f"{(v_cur - v_py) / v_py * 100:+.2f}" if v_py else ""
        r["captured_at"] = now
        r["volume_2026"] = str(v_cur)
        r["volume_2025"] = str(v_py)
        r["volume_2019"] = str(r["volume_2019"])
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "volume_2026", "volume_2025",
                        "volume_2019", "yoy_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"tsa: {len(rows)} days | latest "
          f"{latest.get('date','?')} vol={latest.get('volume_2026','?')} "
          f"yoy={latest.get('yoy_pct','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
