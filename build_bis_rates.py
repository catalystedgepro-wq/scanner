#!/usr/bin/env python3
"""build_bis_rates.py — central bank policy rates + US debt service.

Two BIS-curated stats on one sheet:
- Central bank policy rates (daily, end-of-period) for G10+EM:
  US, EA, GB, JP, CA, AU, CH, CN, IN, BR, MX, KR
- US household debt service ratio (quarterly) — solvency-side
  companion to policy-rate cost-side

Signal: G10 divergence matters — if Fed holds while BoC/ECB cut, USD
strengthens against those currencies → FX-exposed multinational
earnings drag. DSR spike → consumer balance-sheet stress → retail
defaults → credit-card issuer pressure.

Drives:
- Rate-sensitive financials (JPM, BAC, WFC, MS)
- Consumer lenders (COF, DFS, SOFI, UPST, ALLY)
- Int'l FX-exposed (AAPL, MSFT, KO, PG, JNJ)
- EM / China proxies (BABA, FXI, MCHI, EEM)
- Credit card issuers (V, MA, AXP)

Source: stats.bis.org/api/v1/data/WS_CBPOL + WS_DSR (free, no key).
Output: bis_rates.csv
Columns: series, region, period, value, unit, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bis_rates.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# Focus list of major rate-setters.
REGIONS = {
    "US": "Federal Reserve",
    "XM": "ECB",
    "GB": "Bank of England",
    "JP": "Bank of Japan",
    "CA": "Bank of Canada",
    "AU": "Reserve Bank of Australia",
    "CH": "Swiss National Bank",
    "CN": "People's Bank of China",
    "IN": "Reserve Bank of India",
    "BR": "Banco Central do Brasil",
    "MX": "Banxico",
    "KR": "Bank of Korea",
}

CBPOL_URL_TPL = ("https://stats.bis.org/api/v1/data/WS_CBPOL/D.{area}"
                 "/all?format=csv")
DSR_URL = "https://stats.bis.org/api/v1/data/WS_DSR/Q.US.H.A/all?format=csv"


def _fetch(url: str) -> list[list[str]] | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"bis_rates: {url}: {e}")
        return None
    return list(csv.reader(text.splitlines()))


def _latest_by_region(rows: list[list[str]]) -> dict[str, tuple[str, float]]:
    if not rows or len(rows) < 2:
        return {}
    header = rows[0]
    try:
        area_idx = header.index("REF_AREA")
        period_idx = header.index("TIME_PERIOD")
        value_idx = header.index("OBS_VALUE")
    except ValueError:
        return {}
    latest: dict[str, tuple[str, float]] = {}
    for row in rows[1:]:
        if len(row) <= max(area_idx, period_idx, value_idx):
            continue
        area = row[area_idx]
        if area not in REGIONS:
            continue
        period = row[period_idx]
        raw = row[value_idx].strip()
        if not raw:
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if area not in latest or period > latest[area][0]:
            latest[area] = (period, val)
    return latest


def _parse_dsr(rows: list[list[str]]) -> list[dict]:
    if not rows or len(rows) < 2:
        return []
    header = rows[0]
    try:
        period_idx = header.index("TIME_PERIOD")
        value_idx = header.index("OBS_VALUE")
    except ValueError:
        return []
    out: list[dict] = []
    for row in rows[1:]:
        if len(row) <= max(period_idx, value_idx):
            continue
        try:
            val = float(row[value_idx])
        except (TypeError, ValueError):
            continue
        out.append({"period": row[period_idx], "value": val})
    # Keep 40 most recent quarters (10 years).
    out.sort(key=lambda r: r["period"])
    return out[-40:]


def main() -> None:
    import time
    result_rows: list[dict] = []

    # Per-region CBPOL fetch (global 'all' endpoint returns empty).
    for area, label in REGIONS.items():
        rows = _fetch(CBPOL_URL_TPL.format(area=area))
        if not rows:
            time.sleep(1)
            continue
        latest = _latest_by_region(rows)
        if area in latest:
            period, val = latest[area]
            result_rows.append({
                "series": "policy_rate",
                "region": label,
                "period": period,
                "value": f"{val:.3f}",
                "unit": "percent",
            })
        time.sleep(1)

    dsr = _fetch(DSR_URL)

    if dsr:
        for r in _parse_dsr(dsr):
            result_rows.append({
                "series": "us_household_dsr",
                "region": "US",
                "period": r["period"],
                "value": f"{r['value']:.2f}",
                "unit": "percent",
            })

    if not result_rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"bis_rates: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in result_rows:
        r["captured_at"] = now

    fieldnames = ["series", "region", "period", "value", "unit",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(result_rows)

    pol = [r for r in result_rows if r["series"] == "policy_rate"]
    us_pol = next((r for r in pol if r["region"] == "Federal Reserve"), None)
    ecb_pol = next((r for r in pol if r["region"] == "ECB"), None)
    dsr_rows = [r for r in result_rows if r["series"] == "us_household_dsr"]
    dsr_latest = dsr_rows[-1] if dsr_rows else None
    bits = []
    if us_pol:
        bits.append(f"Fed={us_pol['value']}%")
    if ecb_pol:
        bits.append(f"ECB={ecb_pol['value']}%")
    if dsr_latest:
        bits.append(f"US_DSR_{dsr_latest['period']}={dsr_latest['value']}%")
    print(f"bis_rates: {len(result_rows)} rows | {len(pol)} policy rates | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
