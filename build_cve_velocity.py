#!/usr/bin/env python3
"""build_cve_velocity.py — CVE disclosure tape & CISA KEV exploitation.

CVE velocity = real-time cyber catalyst read-through:
- Vendor-targeted CVEs (esp. CRITICAL, CVSS ≥ 9.0) → vendor reaction
- CISA Known Exploited Vulnerabilities catalog = weaponized IoCs
- Spike in disclosures → CrowdStrike (CRWD), Palo Alto (PANW), Zscaler
  (ZS), SentinelOne (S), Fortinet (FTNT), Cloudflare (NET) inbound demand
- Identified vendor in active exploitation → ticker-specific blowup risk
  (Fortinet, Citrix, Ivanti, Cisco, Microsoft, Oracle, Atlassian, etc.)

Sources:
  NVD 2.0 API: services.nvd.nist.gov/rest/json/cves/2.0
  CISA KEV: cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json

Output: cve_velocity.csv
Columns: cve_id, severity, cvss_score, published, vendor, product,
         is_kev, kev_added, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cve_velocity.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

VENDOR_TICKERS = {
    "microsoft": "MSFT",
    "oracle": "ORCL",
    "cisco": "CSCO",
    "fortinet": "FTNT",
    "paloaltonetworks": "PANW",
    "palo_alto_networks": "PANW",
    "palo-alto-networks": "PANW",
    "ivanti": "",
    "citrix": "",  # Private/CTX acquired
    "crowdstrike": "CRWD",
    "sentinelone": "S",
    "zscaler": "ZS",
    "cloudflare": "NET",
    "datadog": "DDOG",
    "broadcom": "AVGO",
    "vmware": "AVGO",  # owned by Broadcom
    "atlassian": "TEAM",
    "gitlab": "GTLB",
    "github": "MSFT",
    "redhat": "IBM",
    "ibm": "IBM",
    "apple": "AAPL",
    "google": "GOOGL",
    "salesforce": "CRM",
    "sap": "SAP",
    "adobe": "ADBE",
    "amazon": "AMZN",
    "elastic": "ESTC",
    "mongodb": "MDB",
    "snowflake": "SNOW",
    "splunk": "CSCO",  # acquired by Cisco
    "nvidia": "NVDA",
    "amd": "AMD",
    "intel": "INTC",
    "qualcomm": "QCOM",
    "siemens": "SIEGY",
    "schneider_electric": "SBGSF",
}


def _get(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"cve_velocity: {url[:80]}: {e}")
        return None


def _ticker_for(vendor: str) -> str:
    v = vendor.lower().replace("_", "").replace("-", "").replace(" ", "")
    for key, tick in VENDOR_TICKERS.items():
        k = key.lower().replace("_", "").replace("-", "").replace(" ", "")
        if k == v:
            return tick
    return ""


def main() -> None:
    # CISA KEV.
    kev_url = ("https://www.cisa.gov/sites/default/files/feeds/"
               "known_exploited_vulnerabilities.json")
    kev = _get(kev_url) or {}
    kev_map: dict[str, str] = {}
    for rec in kev.get("vulnerabilities", []):
        cve = rec.get("cveID", "")
        added = rec.get("dateAdded", "")
        if cve:
            kev_map[cve] = added

    # NVD: last 14 days of publications.
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=14)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%S.000")
    end_s = end.strftime("%Y-%m-%dT%H:%M:%S.999")
    # NVD requires URL-encoded colons? No, plain works.
    base = ("https://services.nvd.nist.gov/rest/json/cves/2.0"
            f"?pubStartDate={start_s}&pubEndDate={end_s}"
            "&resultsPerPage=2000&cvssV3Severity=HIGH")
    # Fetch HIGH severity first.
    highs = _get(base) or {}
    crit_url = base.replace("cvssV3Severity=HIGH", "cvssV3Severity=CRITICAL")
    crits = _get(crit_url) or {}

    all_vulns = (highs.get("vulnerabilities", [])
                 + crits.get("vulnerabilities", []))

    rows: list[dict] = []
    for v in all_vulns:
        cve = v.get("cve", {})
        cve_id = cve.get("id", "")
        published = cve.get("published", "")[:10]
        descs = cve.get("descriptions", [])
        desc_en = ""
        for d in descs:
            if d.get("lang") == "en":
                desc_en = d.get("value", "")[:200]
                break
        # Severity + CVSS v3.
        metrics = cve.get("metrics", {})
        cvss_v3 = metrics.get("cvssMetricV31") or metrics.get("cvssMetricV30")
        severity = ""
        score = ""
        if cvss_v3:
            first = cvss_v3[0].get("cvssData", {})
            severity = first.get("baseSeverity", "")
            sc = first.get("baseScore")
            if sc is not None:
                score = f"{sc:.1f}"
        # CPE config — vendor + product.
        configs = cve.get("configurations", [])
        vendor = ""
        product = ""
        for cfg in configs:
            for node in cfg.get("nodes", []):
                for cpe in node.get("cpeMatch", []):
                    cpe_str = cpe.get("criteria", "")
                    # cpe:2.3:a:vendor:product:version:...
                    parts = cpe_str.split(":")
                    if len(parts) >= 5 and not vendor:
                        vendor = parts[3]
                        product = parts[4]
                if vendor:
                    break
            if vendor:
                break
        ticker = _ticker_for(vendor)
        is_kev = "yes" if cve_id in kev_map else ""
        kev_added = kev_map.get(cve_id, "")
        rows.append({
            "cve_id": cve_id,
            "severity": severity,
            "cvss_score": score,
            "published": published,
            "vendor": vendor,
            "product": product,
            "ticker": ticker,
            "is_kev": is_kev,
            "kev_added": kev_added,
            "desc": desc_en,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"cve_velocity: empty, keeping {OUT_CSV.name}")
        return

    # Sort: KEV first, then critical/high, then score.
    def _sort_key(r: dict) -> tuple:
        is_k = 0 if r["is_kev"] == "yes" else 1
        sev_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(
            r["severity"], 4)
        try:
            s = -float(r["cvss_score"])
        except Exception:
            s = 0
        return (is_k, sev_rank, s, r["cve_id"])

    rows.sort(key=_sort_key)

    now_iso = end.isoformat(timespec="seconds").replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now_iso

    fieldnames = ["cve_id", "severity", "cvss_score", "published",
                  "vendor", "product", "ticker", "is_kev", "kev_added",
                  "desc", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    kev_count = sum(1 for r in rows if r["is_kev"] == "yes")
    crit_count = sum(1 for r in rows if r["severity"] == "CRITICAL")
    tick_count = sum(1 for r in rows if r["ticker"])
    print(f"cve_velocity: {len(rows)} CVEs (14d) | "
          f"CRITICAL={crit_count} KEV_active={kev_count} "
          f"vendor_tickered={tick_count} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
