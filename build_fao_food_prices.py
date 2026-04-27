#!/usr/bin/env python3
"""build_fao_food_prices.py — FAO Food Price Index monthly.

UN-FAO global food price index (1990=100 baseline) with five
sub-indices: Cereals, Meat, Dairy, Vegetable Oils, Sugar. Released
on the first Thursday of each month.

Signal: FFPI > 140 (2022 levels) = global food inflation crisis,
EM social unrest risk, import-dependent sovereign stress. Vegetable
oils spiking = palm/soy/canola rally (ADM, BG). Meat rising = cattle
deficit (TSN, HRL). Sugar spike = ethanol demand (BG, ADM again).
Dairy drop = Oceania milk glut (DA, FDP).

Drives:
- Agri processors (ADM, BG, TSN, HRL, DAR)
- Grain handlers (AGCO, DE)
- Fertilizer (NTR, MOS, CF, SOIL, MOSU)
- Food retailers (KR, SFM, COST, WMT)
- Food manufacturers (GIS, K, CPB, POST)
- Sugar/ethanol (ANDE, REX)
- EM food-stressed economies (EMXC, VWO — inverse)

Source: fao.org/worldfoodsituation/foodpricesindex (free, HTML).
Output: fao_food_prices.csv
Columns: release_date, index_name, value, mom_change_pct,
         yoy_change_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fao_food_prices.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.fao.org/worldfoodsituation/foodpricesindex/en/"

INDEX_LABELS = [
    ("ffpi", r"FAO Food Price Index"),
    ("cereal", r"FAO Cereal Price Index"),
    ("vegoil", r"FAO Vegetable Oil Price Index"),
    ("meat", r"FAO Meat Price Index"),
    ("dairy", r"FAO Dairy Price Index"),
    ("sugar", r"FAO Sugar Price Index"),
]

RELEASE_RE = re.compile(
    r"Release date:\s*(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)
VALUE_RE_TPL = (
    r"{label}\**\s*(?:\([A-Z]+\)\s+)?(?:[A-Z]+\s+)?averaged\s+"
    r"(\d+(?:\.\d+)?)\s*points"
)
MOM_RE = re.compile(
    r"up\s+(\d+(?:\.\d+)?)\s*points?\s*\((\d+(?:\.\d+)?)\s*percent\)"
    r"|down\s+(\d+(?:\.\d+)?)\s*points?\s*\((\d+(?:\.\d+)?)\s*percent\)",
    re.IGNORECASE)
YOY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*points?\s*\((\d+(?:\.\d+)?)\s*percent\)\s*"
    r"(above|below)\s+its\s*(?:value|level)\s*a\s*year\s*ago?",
    re.IGNORECASE)


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&#8209;", "-", s)
    s = re.sub(r"[\u2010-\u2015]", "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_paragraph(body: str, label: str) -> str:
    # Find the sentence starting with `label averaged`.
    pattern = re.compile(
        rf"{re.escape(label)}\**\s*(?:\([A-Z]+\)\s+)?(?:[A-Z]+\s+)?"
        rf"averaged\s+(.*?)(?=»|\Z)",
        re.IGNORECASE | re.DOTALL)
    m = pattern.search(body)
    return m.group(1) if m else ""


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"fao_food_prices: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fao_food_prices: keeping existing {OUT_CSV.name}")
        return

    body = _strip_html(html)

    release = ""
    m = RELEASE_RE.search(body)
    if m:
        # dd/mm/yyyy → yyyy-mm-dd
        parts = m.group(1).split("/")
        if len(parts) == 3:
            release = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"

    rows: list[dict] = []
    for key, label in INDEX_LABELS:
        value_re = re.compile(
            VALUE_RE_TPL.format(label=re.escape(label)),
            re.IGNORECASE)
        vm = value_re.search(body)
        if not vm:
            continue
        try:
            val = float(vm.group(1))
        except (TypeError, ValueError):
            continue

        para = _extract_paragraph(body, label)
        mom_pct = ""
        yoy_pct = ""

        mom_m = MOM_RE.search(para)
        if mom_m:
            if mom_m.group(1):  # "up"
                try:
                    mom_pct = f"+{float(mom_m.group(2)):.1f}"
                except (TypeError, ValueError):
                    pass
            elif mom_m.group(3):  # "down"
                try:
                    mom_pct = f"-{float(mom_m.group(4)):.1f}"
                except (TypeError, ValueError):
                    pass

        yoy_m = YOY_RE.search(para)
        if yoy_m:
            try:
                pct = float(yoy_m.group(2))
                direction = yoy_m.group(3).lower()
                yoy_pct = f"{'+' if direction == 'above' else '-'}{pct:.1f}"
            except (TypeError, ValueError):
                pass

        rows.append({
            "release_date": release,
            "index_name": key,
            "value": f"{val:.2f}",
            "mom_change_pct": mom_pct,
            "yoy_change_pct": yoy_pct,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fao_food_prices: parsed 0, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["release_date", "index_name", "value",
                  "mom_change_pct", "yoy_change_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    ffpi = next((r for r in rows if r["index_name"] == "ffpi"), None)
    bits = []
    if ffpi:
        bits.append(f"FFPI={ffpi['value']} ({ffpi['mom_change_pct']}%MoM, "
                    f"{ffpi['yoy_change_pct']}%YoY)")
    for key in ("vegoil", "sugar", "meat"):
        r = next((x for x in rows if x["index_name"] == key), None)
        if r:
            bits.append(f"{key}={r['value']}")
    print(f"fao_food_prices: {len(rows)} indices | release {release} | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
