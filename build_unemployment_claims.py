#!/usr/bin/env python3
"""build_unemployment_claims.py — DOL weekly initial unemployment claims.

Weekly jobless claims is the earliest, highest-frequency labor market
signal. Thursday 8:30am ET release moves bonds + equity futures within
seconds. Pre-recession averaging 220k → 280k+ sustained = Sahm/recession
rule nearing trigger.

Trade uses:
- Initial claims > 300k sustained 4 wks: recession odds jump, bond
  rally (TLT +2-4%), defensives (XLU/XLP) lift, staffing (MAN/RHI/ASGN)
  fade 10-15%.
- Sharp drop to < 200k: overheated labor → Fed hawkish repricing,
  growth (QQQ) wobbles, financials (KRE) catch bid from higher-for-longer.
- Continuing claims (C3) rising while initial claims flat: rehire
  window closing — cyclicals (XLI, XLB) under-perform into softening.
- State concentration (CA, NY, IL spike): regional-bank deposit outflow
  risk, airline (SAVE, JBLU) travel-demand proxy weakens.

Source: oui.doleta.gov/unemploy/csv/ar539.csv (DOL ETA 539 weekly claims
by state). Public, no key. ~15 MB file, filter to last 52 weeks.

Output: unemployment_claims.csv
Columns: report_date, initial_claims, continuing_claims,
         covered_employment, insured_unemp_rate, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import io
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "unemployment_claims.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://oui.doleta.gov/unemploy/csv/ar539.csv"


def parse_mdy(s: str) -> dt.date | None:
    """Parse 'M/D/YYYY' → date."""
    try:
        m, d, y = s.split("/")
        return dt.date(int(y), int(m), int(d))
    except Exception:
        return None


def main() -> None:
    cutoff = dt.date.today() - dt.timedelta(days=400)
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    # Aggregate by report date.
    agg: dict[dt.date, dict[str, int]] = {}
    covered_total: dict[dt.date, int] = {}
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("latin-1")
    except Exception as e:
        print(f"unemployment_claims: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 120:
            print(f"  keeping existing {OUT_CSV.name}")
            return
        body = ""
    reader = csv.DictReader(io.StringIO(body))
    state_count: dict[dt.date, int] = {}
    for row in reader:
        d = parse_mdy(row.get("rptdate", ""))
        if not d or d < cutoff:
            continue
        # DOL ETA 539 schema: c3=initial claims, c8=continuing claims (Reg
        # UI), c18=covered employment. c1 is reflecting-week sequence,
        # c19 is pre-computed IUR (%).
        try:
            ic = int(row.get("c3", "0") or 0)
            cc = int(row.get("c8", "0") or 0)
            cov = int(row.get("c18", "0") or 0)
        except ValueError:
            continue
        slot = agg.setdefault(d, {"initial": 0, "continuing": 0})
        slot["initial"] += ic
        slot["continuing"] += cc
        covered_total[d] = covered_total.get(d, 0) + cov
        state_count[d] = state_count.get(d, 0) + 1

    if not agg:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 120:
            print(f"unemployment_claims: no rows, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
            return
    rows: list[dict] = []
    for d in sorted(agg.keys()):
        # Only keep weeks with full national coverage (53 reporting
        # jurisdictions: 50 states + DC + PR + VI). Drop partial-report
        # weeks where some states haven't submitted yet.
        if state_count.get(d, 0) < 50:
            continue
        ic = agg[d]["initial"]
        cc = agg[d]["continuing"]
        cov = covered_total.get(d, 0)
        # Insured unemployment rate = continuing_claims / covered_emp (as %).
        iur = (cc / cov * 100.0) if cov > 0 else 0.0
        rows.append({
            "report_date": d.isoformat(),
            "initial_claims": ic,
            "continuing_claims": cc,
            "covered_employment": cov,
            "insured_unemp_rate": f"{iur:.2f}" if cov else "",
        })
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["report_date", "initial_claims", "continuing_claims",
                        "covered_employment", "insured_unemp_rate",
                        "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[-1] if rows else {}
    print(f"unemployment_claims: {len(rows)} weeks | latest "
          f"{latest.get('report_date','?')} "
          f"initial={latest.get('initial_claims','?'):,} "
          f"continuing={latest.get('continuing_claims','?'):,} "
          f"iur={latest.get('insured_unemp_rate','?')}% -> {OUT_CSV.name}"
          if latest else
          f"unemployment_claims: no rows written -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
