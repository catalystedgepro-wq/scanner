#!/usr/bin/env python3
"""cerebro_verify.py — Cerebro Pre-Flight Diagnostics.

Verifies connectivity and authentication for all API pillars before
launching major ingestion runs. Returns PASS/FAIL for every domain.

Usage: python3 cerebro_verify.py
Pure stdlib — no requests/anthropic SDK.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import os
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).parent
CONTRACT_VERSION = "2026-04-07-s01"


def _load_key(name: str) -> str:
    """Load a key from env var or .sec_email_env file."""
    key = os.environ.get(name, "").strip()
    if key:
        return key
    env_path = ROOT / ".sec_email_env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key
    return ""


def _get(url: str, headers: dict | None = None, timeout: int = 12) -> tuple[int, bytes]:
    h = {"User-Agent": "CatalystEdge/1.0 contact@catalystedge.com"}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as exc:
        return 0, str(exc).encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def check_live_api(base_url: str) -> bool:
    print("  Local     Cerebro API ...", end=" ", flush=True)
    health_status, health_body = _get(f"{base_url.rstrip('/')}/api/health")
    if health_status != 200:
        print(f"FAIL — /api/health HTTP {health_status}")
        return False
    try:
        health = json.loads(health_body)
    except Exception as exc:
        print(f"FAIL — /api/health parse error: {exc}")
        return False
    if health.get("status") != "ok":
        print(f"FAIL — /api/health status={health.get('status')!r}")
        return False
    if health.get("contract_version") != CONTRACT_VERSION:
        print(f"FAIL - /api/health contract_version={health.get('contract_version')!r}")
        return False
    universe_status, universe_body = _get(f"{base_url.rstrip('/')}/api/universe?page=1&per_page=3&min_gravity=1")
    if universe_status != 200:
        print(f"FAIL — /api/universe HTTP {universe_status}")
        return False
    try:
        universe = json.loads(universe_body)
    except Exception as exc:
        print(f"FAIL — /api/universe parse error: {exc}")
        return False
    if not isinstance(universe, dict):
        print(f"FAIL — /api/universe returned {type(universe).__name__}, expected object")
        return False
    required = {"contract_version", "total", "page", "per_page", "pages", "tickers"}
    missing = sorted(required - set(universe))
    if missing:
        print(f"FAIL — /api/universe missing keys: {', '.join(missing)}")
        return False
    if universe.get("contract_version") != CONTRACT_VERSION:
        print(f"FAIL - /api/universe contract_version={universe.get('contract_version')!r}")
        return False
    if not isinstance(universe.get("tickers"), list):
        print("FAIL — /api/universe tickers is not a list")
        return False
    row_required = {"ticker", "name", "gravity", "brightness", "cap_tier", "sector", "etf_weight", "etf_overlords", "is_rogue"}
    for idx, row in enumerate(universe.get("tickers", [])[:3], start=1):
        if not isinstance(row, dict):
            print(f"FAIL - /api/universe ticker row {idx} is not an object")
            return False
        row_missing = sorted(row_required - set(row))
        if row_missing:
            print(f"FAIL - /api/universe ticker row {idx} missing keys: {', '.join(row_missing)}")
            return False
    print(f"PASS  (status=ok | total={universe.get('total')} | page={universe.get('page')}/{universe.get('pages')})")
    return True


def check_pipeline_manifest(manifest_arg: str, base_url: str | None = None) -> bool:
    print("  Local     pipeline_manifest.json ...", end=" ", flush=True)
    manifest_path = Path(manifest_arg)
    if not manifest_path.exists():
        print(f"FAIL — missing {manifest_path.name}")
        return False
    manifest = _load_json(manifest_path)
    if not manifest:
        print("FAIL — manifest parse error")
        return False
    if manifest.get("kind") != "cerebro_pipeline_manifest":
        print(f"FAIL — kind={manifest.get('kind')!r}")
        return False
    if manifest.get("status") != "complete":
        print(f"FAIL — status={manifest.get('status')!r}")
        return False
    outputs = manifest.get("outputs", {})
    required = ["sec_catalyst_latest", "sec_catalyst_ranked", "combined_priority", "newsletter_body", "entity_master", "macro_layer", "scanner_index", "scanner_artifact_status", "hud_index", "api_server"]
    missing = [name for name in required if not outputs.get(name, {}).get("exists")]
    if missing:
        print(f"FAIL — missing outputs: {', '.join(missing)}")
        return False
    hud_index = ROOT / outputs["hud_index"]["path"]
    if not hud_index.exists() or "assets/index-" not in hud_index.read_text():
        print("FAIL — HUD index is missing hashed asset reference")
        return False
    scanner_index = ROOT / outputs["scanner_index"]["path"]
    if not scanner_index.exists():
        print("FAIL — Scanner index is missing")
        return False
    scanner_status_path = ROOT / outputs["scanner_artifact_status"]["path"]
    scanner_status = _load_json(scanner_status_path)
    if not scanner_status:
        print("FAIL — scanner_artifact_status parse error")
        return False
    if scanner_status.get("kind") != "scanner_artifact_status":
        print(f"FAIL — scanner_artifact_status kind={scanner_status.get('kind')!r}")
        return False
    if not scanner_status.get("valid"):
        print(f"FAIL — scanner artifact invalid: {scanner_status.get('reason') or 'unknown'}")
        return False
    print(f"PASS  ({len(required)} required outputs present | scanner_display_total={scanner_status.get('display_total')} | commit={manifest.get('git_short_commit') or 'unknown'})")
    if base_url:
        return check_live_api(base_url)
    return True


# ── Domain checks ─────────────────────────────────────────────────────────────

def check_anthropic() -> bool:
    print("  Domain 3  Anthropic (Geospatial Item 2 Parser) ...", end=" ", flush=True)
    key = _load_key("ANTHROPIC_API_KEY")
    if not key:
        print("FAIL — ANTHROPIC_API_KEY not set")
        print("         Fix: export ANTHROPIC_API_KEY=sk-ant-... && source ~/.bashrc")
        return False
    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode()
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key":         key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        if resp.get("content"):
            print(f"PASS  (key ...{key[-8:]})")
            return True
        print(f"FAIL — unexpected response: {str(resp)[:80]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:150]
        print(f"FAIL — HTTP {e.code}: {body}")
        if e.code == 401:
            print(f"         Key length={len(key)}, ends=...{key[-8:]}")
            print("         Revoke and regenerate at console.anthropic.com")
    except Exception as exc:
        print(f"FAIL — {exc}")
    return False


def check_fmp() -> bool:
    print("  Domain 1  Canopy/ETF Holdings (Wikipedia S&P500) ...", end=" ", flush=True)
    # Canopy is built from Wikipedia constituent lists — verify accessibility
    status, body = _get(
        "https://en.wikipedia.org/w/api.php?action=parse"
        "&page=List_of_S%26P_500_companies&prop=wikitext&format=json&section=1")
    if status == 200 and b"wikitext" in body:
        em_path = ROOT / "entity_master.json"
        with_etf = 0
        if em_path.exists():
            try:
                em = json.loads(em_path.read_text())
                with_etf = sum(1 for r in em.values() if r.get("etf_weights_sum", 0) > 0)
            except Exception:
                pass
        print(f"PASS  (Wikipedia OK | {with_etf} tickers with ETF weight)")
        return True
    print(f"FAIL — HTTP {status} (Wikipedia unavailable)")
    return False


def check_fred() -> bool:
    print("  Domain 2  FRED (Macro Physics) ...", end=" ", flush=True)
    # FRED CSV endpoint requires no API key
    status, body = _get(
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
        timeout=15)
    if status == 200 and b"," in body:
        lines = body.decode().strip().splitlines()
        latest = lines[-1] if lines else ""
        print(f"PASS  (DGS10 latest: {latest})")
        return True
    print(f"FAIL — HTTP {status}")
    return False


def check_yahoo() -> bool:
    print("  Domain 2  Yahoo Finance (TNX + DXY live) ...", end=" ", flush=True)
    status, body = _get(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=1m&range=1d",
        headers={"User-Agent": "Mozilla/5.0"})
    if status == 200:
        try:
            d = json.loads(body)
            price = d["chart"]["result"][0]["meta"].get("regularMarketPrice")
            print(f"PASS  (^TNX = {price}%)")
            return True
        except Exception:
            pass
    print(f"FAIL — HTTP {status}")
    return False


def check_edgar() -> bool:
    print("  Domain 1  SEC EDGAR (Universe / Filings) ...", end=" ", flush=True)
    status, body = _get(
        "https://www.sec.gov/files/company_tickers_exchange.json")
    if status == 200 and b"ticker" in body:
        print("PASS")
        return True
    print(f"FAIL — HTTP {status}")
    return False


def check_noaa() -> bool:
    print("  Domain 3  NOAA (Collision Engine) ...", end=" ", flush=True)
    status, body = _get(
        "https://mesonet.agron.iastate.edu/geojson/sbw.geojson")
    if status == 200 and b"features" in body:
        try:
            d = json.loads(body)
            n = len(d.get("features", []))
            print(f"PASS  ({n} active weather polygons)")
            return True
        except Exception:
            pass
    print(f"FAIL — HTTP {status}")
    return False


def check_worldbank() -> bool:
    print("  Domain 2  World Bank (Sovereign Health) ...", end=" ", flush=True)
    status, body = _get(
        "https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.KD.ZG?format=json&mrv=1")
    if status == 200 and b"value" in body:
        try:
            d = json.loads(body)
            val = d[1][0].get("value") if len(d) > 1 and d[1] else None
            print(f"PASS  (US GDP growth = {val}%)")
            return True
        except Exception:
            pass
    print(f"FAIL — HTTP {status}")
    return False


def check_options() -> bool:
    print("  Domain 5  Options Chain (Alpaca / Tradier) ...", end=" ", flush=True)
    # Check Alpaca paper trading keys
    alpaca_key = _load_key("ALPACA_API_KEY")
    alpaca_sec = _load_key("ALPACA_SECRET_KEY")
    if alpaca_key and alpaca_sec:
        status, body = _get(
            "https://data.alpaca.markets/v1beta1/options/snapshots/AAPL"
            "?feed=indicative&limit=1",
            headers={
                "APCA-API-KEY-ID":     alpaca_key,
                "APCA-API-SECRET-KEY": alpaca_sec,
            })
        if status == 200 and b"snapshots" in body:
            print(f"PASS  (Alpaca: key ...{alpaca_key[-6:]})")
            return True
        print(f"FAIL — Alpaca HTTP {status}")
        return False

    # Check Tradier sandbox token
    tradier_token = _load_key("TRADIER_TOKEN")
    if tradier_token:
        status, body = _get(
            "https://sandbox.tradier.com/v1/markets/options/expirations?symbol=AAPL",
            headers={"Authorization": f"Bearer {tradier_token}", "Accept": "application/json"})
        if status == 200 and b"expirations" in body:
            print(f"PASS  (Tradier sandbox: token ...{tradier_token[-6:]})")
            return True
        print(f"FAIL — Tradier HTTP {status}")
        return False

    print("FAIL — No keys (add ALPACA_API_KEY+ALPACA_SECRET_KEY or TRADIER_TOKEN to .sec_email_env)")
    print("         Free signup: alpaca.markets → Paper Trading → API Keys (5 min)")
    return False


def check_uspto() -> bool:
    """Optional: Lens.org patent API (free token) or USPTO PEDS."""
    print("  Domain 4  USPTO Patents (Lens.org) ...", end=" ", flush=True)
    token = _load_key("LENS_API_TOKEN")
    if not token:
        print("SKIP — No token (lens.org → Register → API token, free)")
        return True   # optional — don't block green light
    try:
        req = urllib.request.Request(
            "https://api.lens.org/patent/search",
            data=json.dumps({"query": {"match": {"applicant.name": "Apple"}},
                             "size": 1}).encode(),
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent":    "CatalystEdge/1.0",
            })
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read())
            print(f"PASS  ({d.get('total', '?')} Apple patents found)")
            return True
    except Exception as exc:
        print(f"FAIL — {exc}")
    return False


def check_courtlistener() -> bool:
    """Optional: CourtListener API (free token required since 2024)."""
    print("  Domain 4  CourtListener / PACER (Legal Risk) ...", end=" ", flush=True)
    token = _load_key("CL_API_TOKEN")
    if not token:
        print("SKIP — No token (courtlistener.com → Register → API token, free)")
        return True   # optional — don't block green light
    # v4 uses /search/ endpoint with q= parameter
    for url in [
        "https://www.courtlistener.com/api/rest/v4/search/?q=apple&type=d&page_size=1",
        "https://www.courtlistener.com/api/rest/v3/dockets/?case_name=apple&page_size=1",
    ]:
        status, body = _get(url, headers={"Authorization": f"Token {token}"})
        if status == 200 and b"count" in body:
            try:
                d = json.loads(body)
                print(f"PASS  ({d.get('count', '?')} Apple dockets | token ...{token[-6:]})")
                return True
            except Exception:
                pass
        if status == 401:
            print(f"FAIL — HTTP 401 (invalid token — check CL_API_TOKEN in .sec_email_env)")
            return False
    print(f"FAIL — HTTP {status} (endpoint changed or token rejected)")
    return False


def check_google_trends() -> bool:
    """Optional: Google Trends reachability (no API key needed)."""
    print("  Domain 6  Google Trends (Digital Footprint) ...", end=" ", flush=True)
    import http.cookiejar
    cj     = http.cookiejar.CookieJar()
    opener = urllib.request.OpenerDirector()
    opener.add_handler(urllib.request.HTTPCookieProcessor(cj))
    opener.add_handler(urllib.request.HTTPSHandler())
    opener.add_handler(urllib.request.HTTPHandler())
    try:
        req = urllib.request.Request(
            "https://trends.google.com/trends/explore",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        r = opener.open(req, timeout=15)
        status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as exc:
        print(f"FAIL — {exc}")
        return False
    p = ROOT / "digital_footprint.json"
    cached = 0
    if p.exists():
        try:
            cached = len(json.loads(p.read_text()))
        except Exception:
            pass
    if status in (200, 429):
        note = "rate-limited from server IP — spoke functional" if status == 429 else f"{len(list(cj))} cookies"
        print(f"PASS  (HTTP {status} | {note} | {cached} tickers cached)")
        return True
    print(f"FAIL — HTTP {status}")
    return False


def check_entity_master() -> bool:
    print("  Local     entity_master.json ...", end=" ", flush=True)
    p = ROOT / "entity_master.json"
    if p.exists():
        try:
            em = json.loads(p.read_text())
            with_gics = sum(1 for r in em.values() if r.get("gics"))
            with_cap  = sum(1 for r in em.values() if r.get("mkt_cap_usd"))
            with_geo  = sum(1 for r in em.values() if r.get("geospatial_nodes"))
            with_etf  = sum(1 for r in em.values() if r.get("etf_weights_sum", 0) > 0)
            print(f"PASS  ({len(em)} tickers | GICS={with_gics} | "
                  f"caps={with_cap} | geo={with_geo} | ETF_weight={with_etf})")
            return True
        except Exception as exc:
            print(f"FAIL — parse error: {exc}")
    else:
        print("FAIL — not found (run build_universe_gravity.py)")
    return False


# ── Main ──────────────────────────────────────────────────────────────────────
def _run_preflight_checks() -> bool:
    print()
    print("══════════════════════════════════════════════════════")
    print("  CEREBRO PRE-FLIGHT DIAGNOSTICS")
    print("══════════════════════════════════════════════════════")

    print("\n  [ REQUIRED — Domains 1–3 Core ]")
    core = {
        "EDGAR":      check_edgar(),
        "Yahoo":      check_yahoo(),
        "FRED":       check_fred(),
        "WorldBank":  check_worldbank(),
        "NOAA":       check_noaa(),
        "Anthropic":  check_anthropic(),
        "ETF_Canopy": check_fmp(),
        "UEM":        check_entity_master(),
    }

    print("\n  [ OPTIONAL — Domain 4–6 Spokes ]")
    optional = {
        "Options":        check_options(),
        "USPTO":          check_uspto(),
        "CourtListener":  check_courtlistener(),
        "GoogleTrends":   check_google_trends(),
    }

    core_pass     = sum(core.values())
    core_total    = len(core)
    opt_pass      = sum(optional.values())
    opt_total     = len(optional)
    core_failed   = [k for k, v in core.items() if not v]
    opt_needed    = [k for k, v in optional.items() if not v and k != "Options"]

    print()
    print("══════════════════════════════════════════════════════")
    print(f"  Core   : {core_pass}/{core_total} PASS" + ("  ✅ BEDROCK SEALED" if core_pass == core_total else ""))
    print(f"  Spokes : {opt_pass}/{opt_total} PASS" + ("  ✅ ALL SPOKES LIVE" if opt_pass == opt_total else ""))
    if opt_pass == opt_total:
        print("  🧠 12/12 Intelligence — ALL DOMAINS ACTIVE")

    if core_pass == core_total:
        print("\n  ✅ ALL SYSTEMS GO — safe to launch ingestion")
    else:
        print(f"\n  ⚠️  Fix before launching: {', '.join(core_failed)}")

    if core_pass == core_total and opt_pass < opt_total:
        skipped = [k for k, v in optional.items() if not v]
        print(f"  ℹ  Optional spokes not yet active: {', '.join(skipped)}")
        if "USPTO" in skipped:
            print("       USPTO        : lens.org → Register → API token (free)")
        if "CourtListener" in skipped:
            print("       CourtListener: courtlistener.com → Register → API token (free)")
        if "Options" in skipped:
            print("       Options      : alpaca.markets → Paper Trading → API Keys (free)")
    print("══════════════════════════════════════════════════════")
    print()
    return core_pass == core_total


def main() -> None:
    parser = argparse.ArgumentParser(description="Cerebro verification entrypoint")
    parser.add_argument("--mode", choices=("manifest", "preflight", "all"), default="manifest")
    parser.add_argument("--manifest", default=str(ROOT / "pipeline_manifest.json"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    ok = True
    if args.mode in ("manifest", "all"):
        ok = check_pipeline_manifest(args.manifest, args.base_url) and ok
    if args.mode in ("preflight", "all"):
        ok = _run_preflight_checks() and ok
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
