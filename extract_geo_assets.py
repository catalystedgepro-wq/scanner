#!/usr/bin/env python3
"""extract_geo_assets.py — Domain 3: Geospatial Asset Ingestion.

Parses SEC 10-K "Item 2: Properties" text via Claude API to extract physical
coordinates, then geocodes via OpenStreetMap Nominatim.

Architecture:
    CIK → EDGAR latest 10-K accession
        → 10-K document text
        → Item 2 section extraction (regex)
        → Claude haiku → structured JSON [{type, address, status, description}]
        → Nominatim geocoding → {lat, lon}
        → entity_master.json["geospatial_nodes"]

Relational Key: CIK ↔ Lat/Long (the UEM "GPS" anchor)

Static Gravity data — update once per year per 10-K cycle.
Results are cached in .geo_assets_cache.json to save API costs.

Run:
    python3 extract_geo_assets.py [--limit=100] [--dry-run] [--force]

Requires: ANTHROPIC_API_KEY in .sec_email_env
Pure stdlib — no numpy/pandas/shapely.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
UA   = os.environ.get("SEC_USER_AGENT", "CatalystEdge/1.0 contact@catalystedge.com")

GEO_CACHE_PATH  = ROOT / ".geo_assets_cache.json"
ENTITY_MASTER   = ROOT / "entity_master.json"


# ── API key loader ────────────────────────────────────────────────────────────
def _load_api_key() -> str | None:
    # Environment variable takes priority (set via export on droplet)
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key and key.startswith("sk-ant"):
        return key
    # Fall back to .sec_email_env file
    env_path = ROOT / ".sec_email_env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key and key.startswith("sk-ant"):
                    return key
    return None


def _preflight_check(api_key: str) -> bool:
    """Test the API key with a minimal call before starting the crawl."""
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "hi"}],
    }
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            if resp.get("content"):
                print(f"  Pre-flight: Anthropic API OK (key ...{api_key[-6:]})")
                return True
    except urllib.error.HTTPError as e:
        code = e.code
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"  Pre-flight FAIL: HTTP {code} — {body}")
        if code == 401:
            print(f"  Key used: ...{api_key[-12:]} (length={len(api_key)})")
            print("  Fix: export ANTHROPIC_API_KEY=sk-ant-... on the droplet")
    except Exception as exc:
        print(f"  Pre-flight FAIL: {exc}")
    return False


# ── HTTP helper ───────────────────────────────────────────────────────────────
def _get(url: str, headers: dict | None = None, timeout: int = 20) -> bytes | None:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as exc:
        print(f"  WARN: fetch failed {url[:80]}: {exc}")
        return None


# ── EDGAR: get latest 10-K filing ─────────────────────────────────────────────
def get_latest_10k_url(cik: str) -> str | None:
    """Return the URL of the primary HTML document in the latest 10-K filing."""
    subs_url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    raw = _get(subs_url)
    if not raw:
        return None
    try:
        subs = json.loads(raw)
        filings = subs.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        accns   = filings.get("accessionNumber", [])
        docs    = filings.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form.strip().upper() in ("10-K", "10-K/A"):
                accn = accns[i].replace("-", "")
                doc  = docs[i]
                return (f"https://www.sec.gov/Archives/edgar/data/"
                        f"{int(cik)}/{accn}/{doc}")
    except Exception:
        pass
    return None


# ── Extract Item 2 text from 10-K ─────────────────────────────────────────────
_ITEM2_PATTERN = re.compile(
    r"item\s+2[\.\s:]+properties?\b(.{200,15000}?)(?=item\s+3[\.\s:]+|$)",
    re.IGNORECASE | re.DOTALL,
)
_TAG_STRIP = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s{2,}")


def extract_item2_text(filing_url: str) -> str | None:
    """Fetch 10-K and extract Item 2 Properties section."""
    raw = _get(filing_url, timeout=30)
    if not raw:
        return None
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return None

    # Strip HTML tags
    text = _TAG_STRIP.sub(" ", text)
    text = _WHITESPACE.sub(" ", text)

    m = _ITEM2_PATTERN.search(text)
    if m:
        return m.group(1).strip()[:8000]  # cap at 8k chars for LLM cost
    return None


# ── Claude API: extract locations from Item 2 text ───────────────────────────
_GEO_PROMPT_SYSTEM = (
    "You are the Cerebro Geospatial Architect. Perform high-precision entity "
    "extraction from SEC 10-K 'Item 2: Properties' text to populate a global "
    "graph database. Extract only specific, verifiable physical locations. "
    "Do NOT hallucinate addresses for vague descriptions."
)


def _build_geo_prompt(ticker: str, cik: str, item2_text: str) -> str:
    return f"""Analyze this SEC 10-K "Item 2: Properties" excerpt for {ticker} (CIK: {cik}).

Extract all physical locations where the company owns or leases significant assets.
Only extract specific, named locations — skip vague references like "various facilities."

Output ONLY valid JSON in this exact format:
{{
  "ticker": "{ticker}",
  "cik": "{cik}",
  "geospatial_nodes": [
    {{
      "type": "HQ|Manufacturing|Distribution|R&D|Retail",
      "address": "full address, city, state, country",
      "status": "Owned|Leased",
      "description": "brief description"
    }}
  ]
}}

If no specific locations are found, return: {{"ticker":"{ticker}","cik":"{cik}","geospatial_nodes":[]}}

Item 2 text:
{item2_text[:6000]}"""


def call_claude_geo(ticker: str, cik: str, item2_text: str,
                    api_key: str) -> list[dict]:
    """Call Claude to extract geospatial nodes from Item 2 text."""
    payload = {
        "model":      "claude-haiku-4-5-20251001",
        "max_tokens": 800,
        "system":     _GEO_PROMPT_SYSTEM,
        "messages":   [{"role": "user",
                        "content": _build_geo_prompt(ticker, cik, item2_text)}],
    }
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            resp = json.loads(r.read().decode("utf-8"))
            text = resp["content"][0]["text"].strip()
        # Extract JSON block
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            return data.get("geospatial_nodes", [])
    except Exception as exc:
        print(f"  WARN: Claude geo API error for {ticker}: {exc}")
    return []


# ── Nominatim geocoding (OpenStreetMap, free, 1 req/sec) ─────────────────────
def geocode_address(address: str) -> tuple[float, float] | None:
    """Geocode an address string via Nominatim. Returns (lat, lon) or None."""
    params = urllib.parse.urlencode({
        "q":      address,
        "format": "json",
        "limit":  1,
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    raw = _get(url, headers={
        "User-Agent": "CatalystEdge/1.0 contact@catalystedge.com",
        "Accept-Language": "en",
    }, timeout=10)
    if not raw:
        return None
    try:
        results = json.loads(raw)
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        pass
    return None


# ── Main ──────────────────────────────────────────────────────────────────────
def main(limit: int = 100, dry_run: bool = False, force: bool = False) -> None:
    api_key = _load_api_key()
    if not api_key:
        print("extract_geo_assets: ANTHROPIC_API_KEY not found")
        print("  Fix: export ANTHROPIC_API_KEY=sk-ant-... && source ~/.bashrc")
        return
    if not _preflight_check(api_key):
        print("extract_geo_assets: pre-flight failed — aborting crawl")
        return

    # Load entity master
    if not ENTITY_MASTER.exists():
        print("extract_geo_assets: entity_master.json not found — run build_universe_gravity.py first")
        return
    entity_master: dict = json.loads(ENTITY_MASTER.read_text(encoding="utf-8"))

    # Load geo cache
    geo_cache: dict = {}
    if GEO_CACHE_PATH.exists():
        try:
            geo_cache = json.loads(GEO_CACHE_PATH.read_text())
        except Exception:
            pass

    # Priority targets: active catalyst tickers first, then GICS-classified
    active: set[str] = set()
    for fname in ("sec_catalyst_tickers.txt", "sec_top_gappers_tickers.txt",
                  "combined_priority_tickers.txt"):
        p = ROOT / fname
        if p.exists():
            active.update(l.strip().upper() for l in p.read_text().splitlines() if l.strip())

    def _priority(ticker: str) -> int:
        if ticker in active:
            return 0
        if entity_master.get(ticker, {}).get("gics"):
            return 1
        return 2

    # Select targets that have a CIK, are not ETFs, and haven't been geocoded
    targets = [
        t for t, r in entity_master.items()
        if r.get("cik")
        and not r.get("etf")
        and (force or not r.get("geospatial_nodes"))
        and t not in geo_cache
    ]
    targets.sort(key=_priority)
    targets = targets[:limit]

    already_cached = sum(1 for t in entity_master if entity_master[t].get("geospatial_nodes"))
    print(f"extract_geo_assets: {len(targets)} targets | {already_cached} already geocoded")

    if dry_run:
        print("  [DRY RUN] Would process:")
        for t in targets[:10]:
            print(f"    {t}  CIK={entity_master[t].get('cik')}")
        return

    extracted = 0
    geocoded  = 0
    api_cost  = 0

    for i, ticker in enumerate(targets):
        rec = entity_master[ticker]
        cik = rec.get("cik", "")

        # Step 1: Get latest 10-K URL
        filing_url = get_latest_10k_url(cik)
        time.sleep(0.12)
        if not filing_url:
            geo_cache[ticker] = {"status": "no_10k"}
            continue

        # Step 2: Extract Item 2 text
        item2 = extract_item2_text(filing_url)
        time.sleep(0.12)
        if not item2:
            geo_cache[ticker] = {"status": "no_item2"}
            continue

        # Step 3: Claude extraction
        nodes = call_claude_geo(ticker, cik, item2, api_key)
        api_cost += 1
        time.sleep(0.5)

        # Step 4: Nominatim geocoding
        geocoded_nodes = []
        for node in nodes:
            addr = node.get("address", "")
            if not addr:
                continue
            coords = geocode_address(addr)
            time.sleep(1.1)  # Nominatim rate limit: 1 req/sec
            if coords:
                node["lat"] = coords[0]
                node["lon"] = coords[1]
                geocoded_nodes.append(node)
                geocoded += 1
            else:
                # Store without coords — still useful for address text
                node["lat"] = None
                node["lon"] = None
                geocoded_nodes.append(node)

        # Step 5: Persist to entity_master
        if geocoded_nodes:
            entity_master[ticker]["geospatial_nodes"] = geocoded_nodes
            extracted += 1

        geo_cache[ticker] = {"status": "done", "node_count": len(geocoded_nodes)}

        if (i + 1) % 20 == 0:
            ENTITY_MASTER.write_text(
                json.dumps(entity_master, indent=2, ensure_ascii=False),
                encoding="utf-8")
            GEO_CACHE_PATH.write_text(json.dumps(geo_cache, indent=2))
            print(f"  [{i+1}/{len(targets)}] extracted={extracted}, "
                  f"geocoded_nodes={geocoded}, "
                  f"~cost=${api_cost * 0.001:.2f}")

    # Final save
    ENTITY_MASTER.write_text(
        json.dumps(entity_master, indent=2, ensure_ascii=False),
        encoding="utf-8")
    GEO_CACHE_PATH.write_text(json.dumps(geo_cache, indent=2))

    total_nodes = sum(
        len(r.get("geospatial_nodes", []))
        for r in entity_master.values()
    )
    print(f"\nextract_geo_assets: complete")
    print(f"  Tickers processed : {len(targets)}")
    print(f"  With geo nodes    : {extracted}")
    print(f"  Total nodes (UEM) : {total_nodes}")
    print(f"  Geocoded w/ coords: {geocoded}")
    print(f"  Estimated cost    : ~${api_cost * 0.001:.3f}")


if __name__ == "__main__":
    import sys
    lim     = int(next((a.split("=")[1] for a in sys.argv
                        if a.startswith("--limit=")), "100"))
    dry_run = "--dry-run" in sys.argv
    force   = "--force"   in sys.argv
    main(limit=lim, dry_run=dry_run, force=force)
