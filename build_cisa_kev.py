#!/usr/bin/env python3
"""build_cisa_kev.py — CISA Known Exploited Vulnerabilities catalog.

CVEs actively exploited in the wild. When a vendor appears, shareholders
of the affected company take a hit (MSFT, CRWD, PANW, FTNT, CSCO, NET,
ZS, S, OKTA, VMW). When a CVE is patched by CRWD/PANW/FTNT first, they
tend to outperform 2–5% near-term.

Source: cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
        (free, no key)

Output: cisa_kev.csv
Columns: cve_id, vendor, product, vulnerability, date_added, due_date,
         known_ransomware, tickers_affected, short_desc, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cisa_kev.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

FEED = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

VENDOR_TICKERS = {
    "microsoft":  "MSFT",
    "cisco":      "CSCO",
    "fortinet":   "FTNT",
    "palo alto":  "PANW",
    "crowdstrike":"CRWD",
    "okta":       "OKTA",
    "cloudflare": "NET",
    "zscaler":    "ZS",
    "sentinelone":"S",
    "oracle":     "ORCL",
    "sap":        "SAP",
    "adobe":      "ADBE",
    "vmware":     "VMW",
    "citrix":     "CTXS",
    "ibm":        "IBM",
    "google":     "GOOGL",
    "apple":      "AAPL",
    "atlassian":  "TEAM",
    "mongodb":    "MDB",
    "elastic":    "ESTC",
    "progress":   "PRGS",
    "ivanti":     "",  # private
    "sonicwall":  "",  # private
    "fortra":     "",  # private
    "veeam":      "",  # private
    "barracuda":  "",  # private
    "trend micro":"TMICY",
    "juniper":    "JNPR",
    "f5 networks":"FFIV",
}


def tag_ticker(vendor: str) -> str:
    v = vendor.lower()
    for k, t in VENDOR_TICKERS.items():
        if k in v:
            return t
    return ""


def fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"cisa_kev: {e}")
        return None


def main() -> None:
    data = fetch(FEED) or {}
    vulns = data.get("vulnerabilities") or []
    rows: list[dict] = []
    for v in vulns:
        vendor = v.get("vendorProject") or ""
        rows.append({
            "cve_id": v.get("cveID", ""),
            "vendor": vendor,
            "product": v.get("product", ""),
            "vulnerability": (v.get("vulnerabilityName") or "")[:120],
            "date_added": v.get("dateAdded", ""),
            "due_date": v.get("dueDate", ""),
            "known_ransomware": v.get("knownRansomwareCampaignUse", "Unknown"),
            "tickers_affected": tag_ticker(vendor),
            "short_desc": (v.get("shortDescription") or "")[:200].replace("\n", " "),
        })
    rows.sort(key=lambda r: r["date_added"], reverse=True)
    rows = rows[:200]  # latest 200 — ~6 months of additions
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "cve_id", "vendor", "product", "vulnerability",
                "date_added", "due_date", "known_ransomware",
                "tickers_affected", "short_desc", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"cisa_kev: {len(rows)} CVEs | latest {latest.get('cve_id','?')} "
          f"{latest.get('vendor','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
