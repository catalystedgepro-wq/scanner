#!/usr/bin/env python3
"""build_usa_spending.py — USASpending.gov large contract awards (30d).

Federal contract awards are a direct, mechanical revenue signal:
- Defense primes (LMT, RTX, NOC, GD, BA, LDOS, LHX) book contracts
  that hit reported backlog next quarter — often moves the stock
  before analysts update models.
- Civil contracts (CAT, DE, PWR, KBR, FLR) hit industrials earnings.
- IT services (ACN, IBM, CACI, SAIC, BAH, PLTR) book multi-year
  task orders — retail never sees these until earnings calls.
- BARDA/HHS pharma awards (PFE, JNJ, LLY, MRNA, NVAX) — pandemic
  preparedness, shows pre-election risk allocation.

Signal: Rising 30d award aggregate to a ticker = backlog accretion.
Cross-check: If award total > 10% of ticker's quarterly revenue, expect
next-quarter beat.

Source: api.usaspending.gov/api/v2/search/spending_by_award (POST, no
key required). Award type codes A/B/C/D = definitive contracts.

Output: usa_spending.csv
Columns: recipient, ticker, agency, awards_count, total_usd,
         largest_usd, largest_award_id, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "usa_spending.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

# Uppercase recipient-name substrings → ticker. Match by "in" on upper name.
RECIPIENT_TICKER: list[tuple[str, str]] = [
    ("LOCKHEED MARTIN", "LMT"),
    ("RAYTHEON", "RTX"),
    ("RTX CORP", "RTX"),
    ("NORTHROP GRUMMAN", "NOC"),
    ("GENERAL DYNAMICS", "GD"),
    ("BOEING", "BA"),
    ("L3HARRIS", "LHX"),
    ("LEIDOS", "LDOS"),
    ("SAIC", "SAIC"),
    ("BOOZ ALLEN", "BAH"),
    ("CACI", "CACI"),
    ("HUNTINGTON INGALLS", "HII"),
    ("TEXTRON", "TXT"),
    ("TRANSDIGM", "TDG"),
    ("HEICO", "HEI"),
    ("HOWMET", "HWM"),
    ("PALANTIR", "PLTR"),
    ("MICROSOFT", "MSFT"),
    ("AMAZON WEB SERVICES", "AMZN"),
    ("AMAZON.COM", "AMZN"),
    ("ALPHABET", "GOOGL"),
    ("GOOGLE LLC", "GOOGL"),
    ("ORACLE", "ORCL"),
    ("IBM", "IBM"),
    ("ACCENTURE", "ACN"),
    ("CISCO SYSTEMS", "CSCO"),
    ("DELL TECHNOLOGIES", "DELL"),
    ("HEWLETT PACKARD ENTERPRISE", "HPE"),
    ("HP INC", "HPQ"),
    ("CATERPILLAR", "CAT"),
    ("DEERE", "DE"),
    ("FLUOR", "FLR"),
    ("QUANTA SERVICES", "PWR"),
    ("KBR INC", "KBR"),
    ("AECOM", "ACM"),
    ("JACOBS SOLUTIONS", "J"),
    ("JACOBS ENGINEERING", "J"),
    ("PARSONS", "PSN"),
    ("PFIZER", "PFE"),
    ("MODERNA", "MRNA"),
    ("JOHNSON & JOHNSON", "JNJ"),
    ("JANSSEN", "JNJ"),
    ("ELI LILLY", "LLY"),
    ("MERCK SHARP", "MRK"),
    ("GILEAD", "GILD"),
    ("REGENERON", "REGN"),
    ("NOVAVAX", "NVAX"),
    ("EMERGENT BIOSOLUTIONS", "EBS"),
    ("HONEYWELL", "HON"),
    ("GENERAL ELECTRIC", "GE"),
    ("3M ", "MMM"),
    ("FEDEX", "FDX"),
    ("UNITED PARCEL", "UPS"),
    ("DELTA AIR LINES", "DAL"),
    ("UNITED AIRLINES", "UAL"),
    ("AMERICAN AIRLINES", "AAL"),
    ("CSX", "CSX"),
    ("UNION PACIFIC", "UNP"),
    ("NORFOLK SOUTHERN", "NSC"),
    ("PFIZER", "PFE"),
    ("AT&T", "T"),
    ("VERIZON", "VZ"),
    ("T-MOBILE", "TMUS"),
    ("EXXON", "XOM"),
    ("CHEVRON", "CVX"),
    ("BP AMERICA", "BP"),
    ("SPACEX", "SPACEX_PRIVATE"),
    ("TESLA, INC", "TSLA"),
    ("NVIDIA", "NVDA"),
    ("AMD", "AMD"),
    ("INTEL CORP", "INTC"),
    ("MICRON", "MU"),
    ("CROWDSTRIKE", "CRWD"),
    ("PALO ALTO NETWORKS", "PANW"),
    ("FORTINET", "FTNT"),
    ("ZSCALER", "ZS"),
    ("SNOWFLAKE", "SNOW"),
    ("SERVICENOW", "NOW"),
    ("SALESFORCE", "CRM"),
    ("CARDINAL HEALTH", "CAH"),
    ("MCKESSON", "MCK"),
    ("AMERISOURCEBERGEN", "COR"),
    ("CENCORA", "COR"),
    ("HCA HEALTHCARE", "HCA"),
]


def map_ticker(recipient_name: str) -> str:
    up = (recipient_name or "").upper()
    for sub, tk in RECIPIENT_TICKER:
        if sub in up:
            return tk
    return ""


def fetch_page(start: str, end: str, page: int,
               limit: int = 100) -> list[dict]:
    payload = {
        "filters": {
            "time_period": [{"start_date": start, "end_date": end}],
            "award_type_codes": ["A", "B", "C", "D"],
        },
        "fields": ["Award ID", "Recipient Name", "Award Amount",
                   "Awarding Agency", "Description"],
        "page": page,
        "limit": limit,
        "sort": "Award Amount",
        "order": "desc",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API, data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"usa_spending: page {page} -> {e}")
        return []
    return body.get("results", []) or []


def main() -> None:
    today = dt.date.today()
    start = (today - dt.timedelta(days=30)).isoformat()
    end = today.isoformat()

    awards: list[dict] = []
    for page in range(1, 6):  # up to 500 top awards
        page_rows = fetch_page(start, end, page, limit=100)
        if not page_rows:
            break
        awards.extend(page_rows)

    if not awards:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"usa_spending: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    agg: dict[str, dict] = {}
    for a in awards:
        name = a.get("Recipient Name") or ""
        amt = float(a.get("Award Amount") or 0)
        agency = a.get("Awarding Agency") or ""
        aid = a.get("Award ID") or ""
        tk = map_ticker(name)
        if not tk or tk.endswith("_PRIVATE"):
            continue
        bucket = agg.setdefault(name, {
            "recipient": name,
            "ticker": tk,
            "agency": agency,
            "awards_count": 0,
            "total_usd": 0.0,
            "largest_usd": 0.0,
            "largest_award_id": "",
        })
        bucket["awards_count"] += 1
        bucket["total_usd"] += amt
        if amt > bucket["largest_usd"]:
            bucket["largest_usd"] = amt
            bucket["largest_award_id"] = aid
            bucket["agency"] = agency

    rows = list(agg.values())
    rows.sort(key=lambda r: r["total_usd"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["total_usd"] = f"{r['total_usd']:.0f}"
        r["largest_usd"] = f"{r['largest_usd']:.0f}"
        r["captured_at"] = now

    fieldnames = ["recipient", "ticker", "agency", "awards_count",
                  "total_usd", "largest_usd", "largest_award_id",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    top = rows[:3]
    top_s = " | ".join(
        f"{r['ticker']}=${int(float(r['total_usd']))/1e6:.0f}M"
        for r in top)
    print(f"usa_spending: {len(awards)} awards scanned | "
          f"{len(rows)} ticker matches | top: {top_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
