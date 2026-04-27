#!/usr/bin/env python3
"""data_integrity_watchdog.py — Atomic layer integrity checks for Catalyst Edge.

Runs after each pipeline cycle (or on demand) and validates the 5 Godly Factors:

  1. FILING COUNT INTEGRITY   — UI data-filing-count matches insider_clusters.csv
  2. LIQUIDITY DEPTH ACCURACY — Live Yahoo askSize × 100 vs est. in generated HTML
  3. TEMPORAL EDGE            — Latest filing discovered within MAX_DISCOVERY_LAG minutes
  4. QUALITATIVE TAG SYNC     — Nobel badge count in HTML matches nobel_signals.json
  5. SECTOR GRAVITY SYNC      — Heatmap filing counts match live CSV tally

Fires a Telegram alert for each failed assertion.
Writes watchdog_log.csv for trend tracking.

Usage:
    python3 data_integrity_watchdog.py            # run all checks
    python3 data_integrity_watchdog.py --check filing liquidity   # selective
    python3 data_integrity_watchdog.py --quiet    # only alert on failures

Env vars (same as rest of pipeline):
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL

Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

ROOT         = Path(__file__).parent
HTML_FILE    = ROOT / "docs" / "index.html"
INSIDER_CSV  = ROOT / "insider_clusters.csv"
CATALYST_CSV = ROOT / "sec_catalyst_latest.csv"
NOBEL_JSON   = ROOT / "nobel_signals.json"
HEATMAP_JSON = ROOT / "heatmap_data.json"      # written by generate_seo_site if exists
GICS_CSV     = ROOT / "gics_map.csv"
WATCHDOG_LOG = ROOT / "watchdog_log.csv"

MAX_DISCOVERY_LAG = 20      # minutes — beyond this the "found first" claim weakens
LIQUIDITY_DRIFT   = 0.15    # 15% — alert if live wall differs from HTML estimate by this much
DANGER_SHARES     = 1_000_000_000   # same threshold as the JS toast

UA = "Mozilla/5.0 (compatible; CatalystEdge-Watchdog/1.0)"

LOG_FIELDS = [
    "ts", "check", "status", "detail", "ticker",
]

# ── Telegram (mirrors alert_pipeline_failure.py) ──────────────────────────────

def _send_telegram(text: str) -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    channel = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    if not token or not channel:
        return False
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id":    channel,
        "text":       text,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"  [telegram] send failed: {e}")
        return False


# ── Log helper ────────────────────────────────────────────────────────────────

def _log(check: str, status: str, detail: str, ticker: str = "") -> dict:
    row = {
        "ts":     dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "check":  check,
        "status": status,
        "detail": detail[:200],
        "ticker": ticker,
    }
    append = WATCHDOG_LOG.exists()
    with WATCHDOG_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if not append:
            w.writeheader()
        w.writerow(row)
    return row


def _alert(check: str, detail: str, ticker: str = "") -> None:
    _log(check, "FAIL", detail, ticker)
    emoji = {"filing": "📋", "liquidity": "💧", "temporal": "⏱",
             "badges": "🏅", "sector": "🗺"}.get(check, "⚠️")
    msg = (
        f"{emoji} <b>Watchdog FAIL — {check.upper()}</b>\n"
        f"{'Ticker: ' + ticker + chr(10) if ticker else ''}"
        f"{detail}"
    )
    print(f"  ❌ {check}: {detail}")
    _send_telegram(msg)


def _ok(check: str, detail: str, ticker: str = "") -> None:
    _log(check, "OK", detail, ticker)
    print(f"  ✅ {check}: {detail}")


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _read_html() -> str:
    if not HTML_FILE.exists():
        return ""
    return HTML_FILE.read_text(encoding="utf-8", errors="ignore")


def _extract_filing_counts(html: str) -> dict[str, int]:
    """Extract data-filing-count values for every ticker in the insider table."""
    # Matches: data-ticker="HII" ... data-filing-count="10"
    pattern = re.compile(
        r'data-ticker="([A-Z0-9.\-]+)"[^>]*data-filing-count="(\d+)"'
    )
    result: dict[str, int] = {}
    for m in pattern.finditer(html):
        ticker, count = m.group(1), int(m.group(2))
        if ticker not in result or count > result[ticker]:
            result[ticker] = count   # keep max when multiple elements per ticker
    return result


def _extract_subpenny_flags(html: str) -> dict[str, dict]:
    """Extract data-ticker, data-est-pressure from subpenny-flag divs."""
    pattern = re.compile(
        r'class="subpenny-flag"[^>]*'
        r'data-ticker="([^"]+)"[^>]*'
        r'data-price="([^"]*)"[^>]*'
        r'data-next-tick="([^"]*)"[^>]*'
        r'data-est-pressure="([^"]*)"'
    )
    result = {}
    for m in pattern.finditer(html):
        result[m.group(1)] = {
            "price":        m.group(2),
            "next_tick":    m.group(3),
            "est_pressure": m.group(4),
        }
    return result


def _count_nobel_badges_in_html(html: str) -> dict[str, int]:
    """Count Nobel badge occurrences per type in the generated HTML."""
    return {
        "Nash":   len(re.findall(r'🎯 Nash',   html)),
        "Akerlof": len(re.findall(r'🏅 Akerlof', html)),
        "GARCH":  len(re.findall(r'📊 GARCH',  html)),
        "BSM":    len(re.findall(r'⚗️ BSM',    html)),
    }


# ── Yahoo Finance fetch ───────────────────────────────────────────────────────

def _fetch_ask_wall(symbol: str) -> dict | None:
    """Fetch live ask + askSize from Yahoo quoteSummary."""
    url = (
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
        f"{urllib.request.quote(symbol)}?modules=summaryDetail"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        result = d and d.get("quoteSummary", {}).get("result")
        if not result:
            return None
        sd = result[0].get("summaryDetail", {})
        ask     = sd.get("ask",     {}).get("raw")
        askLots = sd.get("askSize", {}).get("raw")
        if not ask or not askLots or ask <= 0 or askLots <= 0:
            return None
        shares  = askLots * 100        # round lots → shares
        wall    = ask * shares
        avg10   = sd.get("averageDailyVolume10Day",  {}).get("raw", 0)
        avg3m   = sd.get("averageDailyVolume3Month", {}).get("raw", 0)
        avg_vol = avg10 or avg3m or 0
        return {
            "ask":     ask,
            "askLots": askLots,
            "shares":  shares,
            "wallUSD": wall,
            "avgVol":  avg_vol,
            "volMult": round(shares / avg_vol, 1) if avg_vol > 0 else None,
        }
    except Exception as e:
        print(f"    [{symbol}] yahoo fetch error: {e}")
        return None


def _parse_pressure_usd(est_str: str) -> float | None:
    """Convert '$20M' / '$500K' / '$1M–$5M' to a float USD mid-point."""
    if not est_str:
        return None
    # Range: take mid-point
    parts = est_str.replace("$", "").replace(",", "").split("–")
    vals = []
    for p in parts:
        p = p.strip()
        try:
            if p.endswith("B"):
                vals.append(float(p[:-1]) * 1e9)
            elif p.endswith("M"):
                vals.append(float(p[:-1]) * 1e6)
            elif p.endswith("K"):
                vals.append(float(p[:-1]) * 1e3)
            else:
                vals.append(float(p))
        except ValueError:
            continue
    return sum(vals) / len(vals) if vals else None


# ── Check 1: Filing Count Integrity ──────────────────────────────────────────

def check_filing_counts(html: str, quiet: bool) -> list[dict]:
    """HTML data-filing-count must match all_links pipe count in insider_clusters.csv."""
    results = []
    if not INSIDER_CSV.exists():
        _ok("filing", "insider_clusters.csv not found — skipping")
        return results

    # Ground truth: count actual links in all_links column
    db_counts: dict[str, int] = {}
    for row in csv.DictReader(INSIDER_CSV.open(newline="", encoding="utf-8")):
        t = row.get("ticker", "").strip().upper()
        if not t:
            continue
        all_links = row.get("all_links", "") or ""
        # pipe-separated; count non-empty parts
        count = len([l for l in all_links.split("|") if l.strip()])
        count = max(count, int(row.get("filing_count", 0) or 0))
        db_counts[t] = count

    html_counts = _extract_filing_counts(html)

    # Only check tickers that appear in BOTH
    for ticker, html_count in html_counts.items():
        db_count = db_counts.get(ticker)
        if db_count is None:
            continue   # ticker in HTML not in insider table — normal for non-cluster cards
        if html_count != db_count:
            detail = (
                f"UI shows {html_count} filings but DB has {db_count} "
                f"({abs(html_count - db_count)} off) — regeneration needed"
            )
            _alert("filing", detail, ticker)
            results.append({"ticker": ticker, "status": "FAIL", "detail": detail})
        elif not quiet:
            _ok("filing", f"{ticker} filing count {html_count} ✓", ticker)

    if not html_counts and not quiet:
        _ok("filing", "no data-filing-count attributes found in HTML — insider section may be empty")
    return results


# ── Check 2: Liquidity Depth Accuracy ────────────────────────────────────────

def check_liquidity(html: str, quiet: bool) -> list[dict]:
    """Live askSize × 100 vs HTML est-pressure for every subpenny-flag card."""
    results = []
    flags = _extract_subpenny_flags(html)
    if not flags:
        if not quiet:
            _ok("liquidity", "no subpenny-flag cards in HTML — nothing to verify")
        return results

    for ticker, meta in flags.items():
        live = _fetch_ask_wall(ticker)
        if live is None:
            detail = f"{ticker} — Yahoo returned no ask data (Ask-Only / OTC gap / delayed)"
            _log("liquidity", "WARN", detail, ticker)
            print(f"  ⚠️  liquidity: {detail}")
            continue

        wall_live = live["wallUSD"]
        wall_est  = _parse_pressure_usd(meta["est_pressure"])

        # Danger flag: ≥1B shares = extreme wall
        is_danger = live["shares"] >= DANGER_SHARES
        danger_tag = " [🚨 EXTREME WALL]" if is_danger else ""

        if wall_est is None:
            # Can't compare — just report live data
            vol_str = f" | {live['volMult']}× avg vol" if live["volMult"] else ""
            detail = (
                f"{ticker} live wall: ${wall_live/1e6:.2f}M "
                f"({live['shares']/1e9:.1f}B shares @ ${live['ask']:.4f})"
                f"{vol_str}{danger_tag} — no HTML est to compare"
            )
            _log("liquidity", "INFO", detail, ticker)
            print(f"  ℹ️  liquidity: {detail}")
            continue

        drift = abs(wall_live - wall_est) / wall_est if wall_est > 0 else 1.0

        # Build a rich status line regardless of pass/fail
        vol_str = f" | {live['volMult']}× avg vol" if live["volMult"] else ""
        live_str = (
            f"live ${wall_live/1e6:.2f}M ({live['shares']/1e9:.1f}B shares "
            f"@ ${live['ask']:.4f}){vol_str}{danger_tag}"
        )
        est_str = f"HTML est ~${wall_est/1e6:.2f}M"

        if drift > LIQUIDITY_DRIFT:
            detail = f"{ticker} wall DRIFTED {drift*100:.0f}% — {live_str} vs {est_str}"
            _alert("liquidity", detail, ticker)
            results.append({"ticker": ticker, "status": "FAIL", "detail": detail})
        elif not quiet:
            _ok("liquidity", f"{ticker} {live_str} vs {est_str} — drift {drift*100:.1f}% ✓", ticker)
    return results


# ── Check 3: Temporal Edge ────────────────────────────────────────────────────

def check_temporal(quiet: bool) -> list[dict]:
    """Most recent filing in sec_catalyst_latest.csv must be ≤ MAX_DISCOVERY_LAG minutes old."""
    results = []
    if not CATALYST_CSV.exists():
        _log("temporal", "WARN", "sec_catalyst_latest.csv not found")
        return results

    now_utc = dt.datetime.now(dt.timezone.utc)
    newest_filing_dt: dt.datetime | None = None
    newest_ticker = ""

    for row in csv.DictReader(CATALYST_CSV.open(newline="", encoding="utf-8")):
        raw = (row.get("updated_utc") or "").strip()
        if not raw:
            continue
        try:
            # Handle offset-aware timestamps like 2026-04-03T06:13:20-04:00
            filing_dt = dt.datetime.fromisoformat(raw)
            if filing_dt.tzinfo is None:
                filing_dt = filing_dt.replace(tzinfo=dt.timezone.utc)
            if newest_filing_dt is None or filing_dt > newest_filing_dt:
                newest_filing_dt = filing_dt
                newest_ticker = row.get("ticker", "")
        except ValueError:
            continue

    if newest_filing_dt is None:
        _log("temporal", "WARN", "no parseable timestamps in catalyst CSV")
        return results

    lag_min = (now_utc - newest_filing_dt).total_seconds() / 60

    # Temporal check is only meaningful during market hours (4 AM – 8 PM ET)
    et_hour = (now_utc - dt.timedelta(hours=4)).hour
    if et_hour < 4 or et_hour >= 20:
        if not quiet:
            _ok("temporal",
                f"outside market window — newest filing {newest_ticker} "
                f"is {lag_min:.0f} min old (pipeline ran at 4:05 AM ET)",
                newest_ticker)
        return results

    if lag_min > MAX_DISCOVERY_LAG:
        detail = (
            f"Newest filing ({newest_ticker}) is {lag_min:.0f} min old — "
            f"exceeds {MAX_DISCOVERY_LAG} min threshold. "
            f"Akerlof edge may be stale. Consider intraday EDGAR poll."
        )
        _alert("temporal", detail, newest_ticker)
        results.append({"ticker": newest_ticker, "status": "FAIL", "detail": detail})
    elif not quiet:
        _ok("temporal",
            f"newest filing {newest_ticker} is {lag_min:.0f} min old — within {MAX_DISCOVERY_LAG} min ✓",
            newest_ticker)
    return results


# ── Check 4: Nobel Badge Sync ─────────────────────────────────────────────────

def check_badges(html: str, quiet: bool) -> list[dict]:
    """Nobel badge count in HTML should approximately match scorer output in nobel_signals.json."""
    results = []
    if not NOBEL_JSON.exists():
        _log("badges", "WARN", "nobel_signals.json not found — skipping")
        return results

    nd = json.loads(NOBEL_JSON.read_text(encoding="utf-8"))
    tickers = nd.get("tickers", {})

    # Count expected badges from JSON
    expected: dict[str, int] = {"Nash": 0, "Akerlof": 0, "GARCH": 0, "BSM": 0}
    for t, sig in tickers.items():
        if sig.get("nash", {}).get("nash_break"):
            expected["Nash"] += 1
        ak = sig.get("akerlof", {})
        if ak.get("asymmetry_score", 0) > 0.5 or ak.get("filing_opacity", 0) >= 0.7:
            expected["Akerlof"] += 1
        garch = sig.get("garch", {})
        if garch.get("regime") in ("high_vol", "high_cluster") or garch.get("vol_ratio", 1) > 1.2:
            expected["GARCH"] += 1
        bsm = sig.get("bsm", {})
        if bsm.get("tension_score", 0) > 0.5 or bsm.get("signal") == "high_tension":
            expected["BSM"] += 1

    html_counts = _count_nobel_badges_in_html(html)

    # The HTML shows top-10 cards only — we check that html_counts ≤ expected
    # A count in HTML > expected is a genuine drift
    any_fail = False
    for badge, html_n in html_counts.items():
        exp_n = expected.get(badge, 0)
        if html_n > exp_n:
            detail = (
                f"{badge} badge appears {html_n}× in HTML but "
                f"only {exp_n} tickers qualify in nobel_signals.json — "
                f"regeneration may be stale"
            )
            _alert("badges", detail)
            results.append({"ticker": "", "status": "FAIL", "detail": detail})
            any_fail = True
        elif not quiet:
            _ok("badges", f"{badge}: HTML={html_n} / qualified={exp_n} ✓")

    if not any_fail and not quiet and not html_counts:
        _ok("badges", "no Nobel badges in HTML (all-low-signal day)")
    return results


# ── Check 5: Sector Gravity Sync ─────────────────────────────────────────────

def check_sector_gravity(quiet: bool) -> list[dict]:
    """Sector filing counts from live CSVs should match what the heatmap renders."""
    results = []

    # Build live sector counts from gapper CSVs + gics mapper
    gics_map: dict[str, str] = {}
    if (ROOT / "gics_map.csv").exists():
        for row in csv.DictReader((ROOT / "gics_map.csv").open(newline="", encoding="utf-8")):
            t   = row.get("ticker", "").strip().upper()
            sec = (row.get("sector") or row.get("gics_sector") or "").strip().lower()
            if t and sec:
                gics_map[t] = sec

    live_counts: dict[str, int] = {}
    for fname in ["sec_clean_gappers.csv", "sec_catalyst_ranked.csv"]:
        p = ROOT / fname
        if not p.exists():
            continue
        for row in csv.DictReader(p.open(newline="", encoding="utf-8")):
            t = row.get("ticker", "").strip().upper()
            if not t:
                continue
            sector = gics_map.get(t, "other")
            live_counts[sector] = live_counts.get(sector, 0) + 1

    # Load last heatmap JSON if available (written by generate_seo_site.py)
    if not HEATMAP_JSON.exists():
        if not quiet:
            _ok("sector", "heatmap_data.json not found — skipping cross-check")
        return results

    heatmap = json.loads(HEATMAP_JSON.read_text(encoding="utf-8"))
    max_drift_sectors = []

    for block in heatmap:
        sector = (block.get("id") or block.get("label") or "").lower()
        hm_count = block.get("count", 0)
        live_count = live_counts.get(sector, 0)
        if live_count == 0:
            continue   # sector not in live data — heatmap may use cached data
        drift = abs(hm_count - live_count)
        drift_pct = drift / live_count if live_count else 1
        if drift_pct > 0.20 and drift > 5:   # >20% and >5 filings off
            max_drift_sectors.append(
                f"{sector}: heatmap={hm_count} live={live_count} (Δ{drift:+d})"
            )

    if max_drift_sectors:
        detail = "Sector gravity drift detected: " + " | ".join(max_drift_sectors)
        _alert("sector", detail)
        results.append({"status": "FAIL", "detail": detail})
    elif not quiet:
        _ok("sector", f"sector counts within tolerance across {len(heatmap)} blocks ✓")
    return results


# ── Summary report ────────────────────────────────────────────────────────────

def _summary_alert(all_results: list[dict], elapsed_s: float) -> None:
    fails = [r for r in all_results if r.get("status") == "FAIL"]
    if not fails:
        return   # no alert needed — only ping on failures

    lines = [f"🛡 <b>Watchdog Summary — {len(fails)} issue(s)</b>"]
    for r in fails:
        ticker = r.get("ticker", "")
        detail = r.get("detail", "")[:120]
        lines.append(f"• {'[' + ticker + '] ' if ticker else ''}{detail}")
    lines.append(f"\n<i>Scan completed in {elapsed_s:.1f}s</i>")
    _send_telegram("\n".join(lines))


# ── Main ──────────────────────────────────────────────────────────────────────

CHECKS = ["filing", "liquidity", "temporal", "badges", "sector"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Data integrity watchdog for Catalyst Edge")
    ap.add_argument("--check", nargs="+", choices=CHECKS, default=CHECKS,
                    help="Which checks to run (default: all)")
    ap.add_argument("--quiet", action="store_true",
                    help="Only print/alert on failures")
    args = ap.parse_args()

    start = dt.datetime.now(dt.timezone.utc)
    print(f"data_integrity_watchdog: {start.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Checks: {', '.join(args.check)}")

    html = _read_html() if any(c in args.check for c in ("filing", "liquidity", "badges")) else ""
    if html:
        print(f"  HTML: {len(html):,} bytes")

    all_results: list[dict] = []

    if "filing" in args.check:
        print("\n[1/5] Filing Count Integrity")
        all_results += check_filing_counts(html, args.quiet)

    if "liquidity" in args.check:
        print("\n[2/5] Liquidity Depth Accuracy")
        all_results += check_liquidity(html, args.quiet)

    if "temporal" in args.check:
        print("\n[3/5] Temporal Edge")
        all_results += check_temporal(args.quiet)

    if "badges" in args.check:
        print("\n[4/5] Nobel Badge Sync")
        all_results += check_badges(html, args.quiet)

    if "sector" in args.check:
        print("\n[5/5] Sector Gravity Sync")
        all_results += check_sector_gravity(args.quiet)

    elapsed = (dt.datetime.now(dt.timezone.utc) - start).total_seconds()
    fails = [r for r in all_results if r.get("status") == "FAIL"]

    print(f"\n{'─'*50}")
    print(f"  {len(all_results)} assertions · {len(fails)} failed · {elapsed:.1f}s")

    if fails:
        print(f"  🔴 {len(fails)} integrity issue(s) — Telegram alert sent")
        _summary_alert(all_results, elapsed)
        return 1
    else:
        print("  🟢 All checks passed — atomic layer is clean")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
