#!/usr/bin/env python3
"""build_lei_enrichment.py — Pre-populate LEI + ISIN + FIGI for top tickers.

Architecture Directive: LEI is the "GPS Coordinate" for corporate entities.
Once mapped, it is PERMANENT — the live pipeline must NEVER do a fresh GLEIF
lookup during the 4 AM rush. This warm-up script runs overnight.

Data flow:
    entity_master[ticker]["cik"]
        ↓ EDGAR submissions API → legal_name
    legal_name
        ↓ GLEIF API → lei
    lei
        ↓ OpenFIGI API → isin, figi

APIs:
    GLEIF:    https://api.gleif.org/api/v1/lei-records (free, no auth)
    OpenFIGI: https://api.openfigi.com/v3/mapping       (free, registration optional)

Writes updates back to entity_master.json.
Run: python3 build_lei_enrichment.py [--limit 2000]
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent
UA   = os.environ.get("SEC_USER_AGENT",
                      "CatalystEdge/1.0 contact@catalystedge.com")


# ── HTTP helpers ──────────────────────────────────────────────────────────────
def _get_json(url: str, retries: int = 3, sleep: float = 0.5) -> dict | list | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json"
            })
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(sleep * (attempt + 1))
            else:
                print(f"  WARN: GET {url[:80]}: {exc}")
    return None


def _post_json(url: str, payload: list | dict,
               headers: dict | None = None) -> dict | list | None:
    try:
        body = json.dumps(payload).encode("utf-8")
        hdrs = {"Content-Type": "application/json", "User-Agent": UA}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        print(f"  WARN: POST {url[:60]}: {exc}")
        return None


# ── Step 1: CIK → Legal Name (EDGAR) ─────────────────────────────────────────
def fetch_legal_name(cik: str) -> str | None:
    """Return legal entity name from EDGAR submissions API."""
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    d = _get_json(url)
    if d:
        return d.get("name") or None
    return None


# ── Step 2: Legal Name → LEI (GLEIF) ──────────────────────────────────────────
def fetch_lei(legal_name: str) -> str | None:
    """Query GLEIF for LEI by exact legal name. Returns LEI string or None."""
    encoded = urllib.parse.quote(legal_name)
    url = (f"https://api.gleif.org/api/v1/lei-records"
           f"?filter[entity.legalName]={encoded}&page[size]=1")
    d = _get_json(url, sleep=0.3)
    if not d:
        return None
    data = d.get("data", [])
    if data:
        return data[0].get("attributes", {}).get("lei") or None
    # Fuzzy fallback: try first few words of name
    words = legal_name.split()[:3]
    if len(words) < 2:
        return None
    short = urllib.parse.quote(" ".join(words))
    url2  = (f"https://api.gleif.org/api/v1/lei-records"
             f"?filter[entity.legalName]={short}&page[size]=3")
    d2 = _get_json(url2, sleep=0.3)
    if d2:
        for item in d2.get("data", []):
            name_found = (item.get("attributes", {})
                              .get("entity", {})
                              .get("legalName", {})
                              .get("name", "")).upper()
            if legal_name.upper()[:20] in name_found:
                return item["attributes"].get("lei")
    return None


# ── Step 3: LEI → ISIN + FIGI (OpenFIGI) ─────────────────────────────────────
def fetch_figi_isin_batch(tickers: list[str],
                          openfigi_key: str | None = None) -> dict[str, dict]:
    """
    Batch-lookup FIGI + ISIN for a list of tickers via OpenFIGI.
    Returns {ticker: {"figi": ..., "isin": ...}}.
    OpenFIGI allows 25 per request without API key.
    """
    url  = "https://api.openfigi.com/v3/mapping"
    hdrs = {}
    if openfigi_key:
        hdrs["X-OPENFIGI-APIKEY"] = openfigi_key

    result: dict[str, dict] = {}
    # Process in batches of 25 (API limit per request)
    for i in range(0, len(tickers), 25):
        batch = tickers[i:i + 25]
        payload = [{"idType": "TICKER", "idValue": t,
                    "exchCode": "US"} for t in batch]
        resp = _post_json(url, payload, headers=hdrs)
        if not resp:
            continue
        for j, item in enumerate(resp):
            t = batch[j]
            data = item.get("data", [])
            if data:
                first = data[0]
                result[t] = {
                    "figi": first.get("figi"),
                    "isin": None,  # OpenFIGI basic tier doesn't return ISIN
                }
        time.sleep(0.5)  # OpenFIGI rate limit

    return result


# ── Main ──────────────────────────────────────────────────────────────────────
def main(limit: int = 2000) -> None:
    em_path = ROOT / "entity_master.json"
    if not em_path.exists():
        print("build_lei_enrichment: entity_master.json not found — "
              "run build_universe_gravity.py first")
        return

    entity_master = json.loads(em_path.read_text(encoding="utf-8"))

    # Load env for optional OpenFIGI key
    figi_key = None
    env_path = ROOT / ".sec_email_env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("OPENFIGI_API_KEY="):
                figi_key = line.split("=", 1)[1].strip()

    # ── Phase A: Fetch LEI for tickers missing it ─────────────────────────────
    # Priority: tickers with GICS classification (most useful for HUD)
    needs_lei = [
        t for t, r in entity_master.items()
        if r.get("lei") is None
        and r.get("cik")
        and not r.get("etf")
        and r.get("gics")
    ][:limit]

    print(f"build_lei_enrichment: {len(needs_lei)} tickers need LEI lookup")

    lei_found  = 0
    lei_failed = 0
    for i, ticker in enumerate(needs_lei):
        rec = entity_master[ticker]
        cik = rec.get("cik", "")

        # Fetch legal name from EDGAR if not cached
        legal_name = rec.get("name") or ""
        if not legal_name and cik:
            legal_name = fetch_legal_name(cik) or ""
            if legal_name:
                rec["name"] = legal_name
            time.sleep(0.12)

        if not legal_name:
            lei_failed += 1
            continue

        lei = fetch_lei(legal_name)
        if lei:
            rec["lei"] = lei
            lei_found += 1
        else:
            rec["lei"] = None   # explicit null — don't retry until refreshed
            lei_failed += 1

        # Progress
        if (i + 1) % 100 == 0:
            print(f"  LEI progress: {i+1}/{len(needs_lei)} — "
                  f"found={lei_found}, failed={lei_failed}")
            # Save incrementally
            em_path.write_text(json.dumps(entity_master, indent=2),
                               encoding="utf-8")

        time.sleep(0.25)  # GLEIF asks for ~4 req/sec max

    print(f"build_lei_enrichment: LEI — found={lei_found}, failed={lei_failed}")

    # ── Phase B: Batch FIGI/ISIN lookup for tickers without FIGI ─────────────
    needs_figi = [
        t for t, r in entity_master.items()
        if r.get("figi") is None and not r.get("etf") and r.get("gics")
    ][:limit]

    if needs_figi:
        print(f"build_lei_enrichment: fetching FIGI for "
              f"{len(needs_figi)} tickers ...")
        figi_map = fetch_figi_isin_batch(needs_figi, openfigi_key=figi_key)
        for ticker, figi_data in figi_map.items():
            if ticker in entity_master:
                entity_master[ticker].update(figi_data)
        print(f"build_lei_enrichment: FIGI — {len(figi_map)} resolved")

    # ── Save ──────────────────────────────────────────────────────────────────
    em_path.write_text(json.dumps(entity_master, indent=2), encoding="utf-8")

    # Stats
    with_lei  = sum(1 for r in entity_master.values() if r.get("lei"))
    with_figi = sum(1 for r in entity_master.values() if r.get("figi"))
    print(f"build_lei_enrichment: complete → "
          f"{with_lei} LEIs, {with_figi} FIGIs in entity_master.json")


if __name__ == "__main__":
    import sys
    lim = int(next((a.split("=")[1] for a in sys.argv
                    if a.startswith("--limit=")), "2000"))
    main(limit=lim)
