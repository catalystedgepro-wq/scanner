#!/usr/bin/env python3
"""spoke_digital.py — Domain 6: Digital Footprint (Search Interest Velocity).

Tracks Google Trends "Search Interest Velocity" for top tickers — the
Consumer Buzz signal that precedes revenue beats and gap-ups by 3–7 days.

Physics:
    Search velocity = recent_24h_avg / weekly_avg
    velocity > 1.20 (+20% surge)  → +12 velocity  (DIGITAL_BUZZ)
    velocity > 1.50 (+50% surge)  → +18 velocity  (DIGITAL_SPIKE)
    velocity < 0.60 (-40% decline)→ -6  velocity  (DIGITAL_FADE)
    Decay: k = log(2)/48 (half-life = 48h — buzz is short-lived)

Architecture:
    Pure stdlib Google Trends session (no pytrends):
      1. GET trends.google.com → session cookies
      2. POST /trends/api/explore → widget token
      3. GET /trends/api/widgetdata/multiline → 7-day hourly interest data
    Results cached in digital_footprint.json
    Velocities written to spark_velocities.json["digital"]

Run: python3 spoke_digital.py [--limit=100] [--dry-run] [--ticker=NVDA]
Schedule: Every 4 hours during market hours
Pure stdlib — no pytrends/requests/pandas.
"""
from __future__ import annotations

import http.cookiejar
import json
import math
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent

ENTITY_MASTER    = ROOT / "entity_master.json"
DIGITAL_CACHE    = ROOT / "digital_footprint.json"
SPARK_VELOCITIES = ROOT / "spark_velocities.json"

# Physics constants
BUZZ_VELOCITY_MILD   = 12.0    # >20% surge
BUZZ_VELOCITY_STRONG = 18.0    # >50% surge
FADE_VELOCITY        = -6.0    # >40% decline
DIGITAL_HALF_LIFE    = 48      # hours
_DECAY_K = math.log(2) / DIGITAL_HALF_LIFE

# Detection thresholds
SURGE_MILD_THRESHOLD   = 1.20
SURGE_STRONG_THRESHOLD = 1.50
FADE_THRESHOLD         = 0.60
MIN_INTEREST_VALUE     = 5     # ignore near-zero interest (no data)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
       "AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/124.0.0.0 Safari/537.36")


# ── Google Trends session ─────────────────────────────────────────────────────
_gt_opener: urllib.request.OpenerDirector | None = None

def _get_gt_session() -> urllib.request.OpenerDirector | None:
    """Establish a Google Trends session (cookie-based). Cached per process."""
    global _gt_opener
    if _gt_opener:
        return _gt_opener
    cj     = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [
        ("User-Agent",      _UA),
        ("Accept-Language", "en-US,en;q=0.9"),
        ("Accept",          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    ]
    try:
        opener.open("https://trends.google.com/trends/explore", timeout=15)
        _gt_opener = opener
        return opener
    except Exception as exc:
        print(f"  WARN: Google Trends session init failed: {exc}")
    return None


def _gt_explore(opener, keyword: str, timeframe: str = "now 7-d") -> dict | None:
    """
    POST to Google Trends explore API to get widget tokens.
    Returns the parsed widget list or None.
    """
    payload = urllib.parse.urlencode({
        "hl":  "en-US",
        "tz":  "360",
        "req": json.dumps({
            "comparisonItem": [{"keyword": keyword, "geo": "", "time": timeframe}],
            "category":       0,
            "property":       "",
        }),
    }).encode("utf-8")
    url = "https://trends.google.com/trends/api/explore"
    try:
        req  = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/x-www-form-urlencoded",
        })
        resp = opener.open(req, timeout=15)
        raw  = resp.read().decode("utf-8")
        # Strip Google's ")]}',\n" XSSI prefix
        raw = re.sub(r"^\)\]\}',?\n?", "", raw.strip())
        return json.loads(raw)
    except Exception as exc:
        print(f"  WARN: explore API failed for '{keyword}': {exc}")
    return None


def _gt_timeseries(opener, token: str, req_json: str) -> list[int] | None:
    """
    Fetch the TIMESERIES widget data using the token from explore.
    Returns list of interest values (0–100) over the timeframe.
    """
    params = urllib.parse.urlencode({
        "hl":    "en-US",
        "tz":    "360",
        "req":   req_json,
        "token": token,
        "tz":    "360",
    })
    url = f"https://trends.google.com/trends/api/widgetdata/multiline?{params}"
    try:
        resp = opener.open(url, timeout=15)
        raw  = resp.read().decode("utf-8")
        raw  = re.sub(r"^\)\]\}',?\n?", "", raw.strip())
        d    = json.loads(raw)
        rows = (d.get("default", {})
                 .get("timelineData", []))
        values = []
        for row in rows:
            vs = row.get("value", [])
            values.append(int(vs[0]) if vs else 0)
        return values if values else None
    except Exception as exc:
        print(f"  WARN: timeseries API failed: {exc}")
    return None


def fetch_trends(keyword: str) -> list[int] | None:
    """
    Fetch 7-day hourly Google Trends interest for a keyword.
    Returns list of ~168 interest values (0–100) or None on failure.
    """
    opener = _get_gt_session()
    if not opener:
        return None

    explore_data = _gt_explore(opener, keyword)
    if not explore_data:
        return None

    try:
        widgets = explore_data.get("widgets", [])
        for widget in widgets:
            if widget.get("id") == "TIMESERIES":
                token   = widget.get("token", "")
                req_obj = widget.get("request", {})
                if token and req_obj:
                    return _gt_timeseries(opener, token, json.dumps(req_obj))
    except Exception as exc:
        print(f"  WARN: widget parse error for '{keyword}': {exc}")
    return None


def compute_digital_velocity(values: list[int]) -> tuple[float, str]:
    """
    Compute search interest velocity: recent_24h_avg / weekly_avg.
    Returns (velocity_ratio, signal_label).
    """
    if not values:
        return 1.0, "no_data"

    # Filter out zero-fill at start
    nonzero = [v for v in values if v >= MIN_INTEREST_VALUE]
    if not nonzero:
        return 1.0, "no_interest"

    weekly_avg = sum(nonzero) / len(nonzero)
    if weekly_avg <= 0:
        return 1.0, "no_interest"

    # Recent 24 data points (hourly: last 24h; daily: last day)
    recent = values[-min(24, len(values)):]
    recent_avg = sum(recent) / len(recent) if recent else weekly_avg

    ratio = round(recent_avg / weekly_avg, 3)

    if ratio >= SURGE_STRONG_THRESHOLD:
        return ratio, "spike"
    elif ratio >= SURGE_MILD_THRESHOLD:
        return ratio, "surge"
    elif ratio <= FADE_THRESHOLD:
        return ratio, "fade"
    else:
        return ratio, "normal"


def compute_velocity_injection(ratio: float, signal: str) -> float:
    """Map velocity ratio to scoring_engine velocity injection."""
    if signal == "spike":
        return BUZZ_VELOCITY_STRONG
    elif signal == "surge":
        return BUZZ_VELOCITY_MILD
    elif signal == "fade":
        return FADE_VELOCITY
    return 0.0


def load_spark_velocities() -> dict:
    if SPARK_VELOCITIES.exists():
        try:
            return json.loads(SPARK_VELOCITIES.read_text())
        except Exception:
            pass
    return {}


# ── Scan target selection ─────────────────────────────────────────────────────
def load_scan_targets(limit: int) -> list[tuple[str, str]]:
    """
    Return (ticker, search_term) pairs for top tickers.
    Search term = company name (better signal than ticker symbol for Google).
    Priority: active catalyst tickers → GICS classified → outer universe.
    """
    if not ENTITY_MASTER.exists():
        return []

    entity_master: dict = json.loads(ENTITY_MASTER.read_text(encoding="utf-8"))

    active: set[str] = set()
    for fname in ("sec_catalyst_tickers.txt", "combined_priority_tickers.txt",
                  "sec_top_gappers_tickers.txt"):
        p = ROOT / fname
        if p.exists():
            active.update(l.strip().upper() for l in p.read_text().splitlines() if l.strip())

    def _priority(t: str) -> int:
        if t in active:
            return 0
        if entity_master.get(t, {}).get("gics"):
            return 1
        return 2

    # Filter: non-ETF, has a name, prefer consumer/tech (more Google-searchable)
    consumer_sectors = {"tech", "consumer", "comms", "biotech"}
    targets = []
    for ticker, rec in entity_master.items():
        if rec.get("etf"):
            continue
        name = (rec.get("name") or "").strip()
        if not name:
            continue
        # Use first 2 words of company name — e.g. "Apple Inc" not "Apple Inc."
        search_term = " ".join(name.split()[:2]).rstrip(".,;")
        targets.append((ticker, search_term))

    targets.sort(key=lambda x: _priority(x[0]))
    return targets[:limit]


# ── Main ──────────────────────────────────────────────────────────────────────
def main(limit: int = 100, dry_run: bool = False,
         single_ticker: str | None = None) -> None:

    if single_ticker:
        if ENTITY_MASTER.exists():
            em = json.loads(ENTITY_MASTER.read_text(encoding="utf-8"))
            name = em.get(single_ticker.upper(), {}).get("name", single_ticker)
            search_term = " ".join(name.split()[:2]).rstrip(".,;")
        else:
            search_term = single_ticker
        targets = [(single_ticker.upper(), search_term)]
    else:
        targets = load_scan_targets(limit)

    if not targets:
        print("spoke_digital: no targets — run build_universe_gravity.py first")
        return

    print(f"spoke_digital: scanning {len(targets)} tickers for search velocity | "
          f"{'DRY RUN' if dry_run else 'LIVE'}")

    if dry_run:
        for t, s in targets[:10]:
            print(f"  Would search Google Trends: '{s}' ({t})")
        return

    # Load caches
    digital_cache: dict = {}
    if DIGITAL_CACHE.exists():
        try:
            digital_cache = json.loads(DIGITAL_CACHE.read_text())
        except Exception:
            pass

    spark_velo = load_spark_velocities()

    buzz_count  = 0
    spike_count = 0
    fade_count  = 0
    today       = date.today().isoformat()

    for i, (ticker, search_term) in enumerate(targets):
        # Skip if checked today (Google Trends throttles heavily)
        cached = digital_cache.get(ticker, {})
        if cached.get("checked") == today and not single_ticker:
            ratio  = cached.get("ratio", 1.0)
            signal = cached.get("signal", "normal")
        else:
            values = fetch_trends(search_term)
            time.sleep(1.5)   # Google Trends rate limit — critical

            if values is None:
                digital_cache[ticker] = {"checked": today, "ratio": 1.0,
                                          "signal": "fetch_failed",
                                          "search_term": search_term}
                time.sleep(1.0)
                continue

            ratio, signal = compute_digital_velocity(values)
            digital_cache[ticker] = {
                "checked":     today,
                "ratio":       ratio,
                "signal":      signal,
                "search_term": search_term,
                "data_points": len(values),
                "peak":        max(values) if values else 0,
            }

        injection = compute_velocity_injection(ratio, signal)

        if injection != 0.0:
            spark_velo.setdefault(ticker, {})["digital"]        = injection
            spark_velo[ticker]["digital_ratio"]   = ratio
            spark_velo[ticker]["digital_signal"]  = signal
            spark_velo[ticker]["digital_ts"]      = datetime.now(timezone.utc).isoformat()

            icon = "🔥" if signal == "spike" else ("⚡" if signal == "surge" else "📉")
            print(f"  {ticker:8s}  {icon} {signal.upper():6s}  "
                  f"ratio={ratio:.2f}x  vel={injection:+.1f}  '{search_term}'")

            if signal == "spike":   spike_count += 1
            elif signal == "surge": buzz_count  += 1
            elif signal == "fade":  fade_count  += 1
        else:
            # Clear stale digital signal
            if ticker in spark_velo and "digital" in spark_velo[ticker]:
                del spark_velo[ticker]["digital"]

        # Checkpoint every 25 tickers
        if (i + 1) % 25 == 0:
            DIGITAL_CACHE.write_text(json.dumps(digital_cache, indent=2))
            SPARK_VELOCITIES.write_text(json.dumps(spark_velo, indent=2))
            print(f"  [{i+1}/{len(targets)}] buzz={buzz_count} spike={spike_count} fade={fade_count}")

    # Final save
    DIGITAL_CACHE.write_text(json.dumps(digital_cache, indent=2))
    SPARK_VELOCITIES.write_text(json.dumps(spark_velo, indent=2))

    print(f"\nspoke_digital: complete")
    print(f"  Scanned    : {len(targets)} tickers")
    print(f"  Spikes     : {spike_count}  (+18 velocity each)")
    print(f"  Surges     : {buzz_count}   (+12 velocity each)")
    print(f"  Fades      : {fade_count}   (-6 velocity each)")
    print(f"  Output     : digital_footprint.json | spark_velocities.json[digital]")


if __name__ == "__main__":
    import sys
    lim    = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--limit=")), "100"))
    ticker = next((a.split("=")[1] for a in sys.argv if a.startswith("--ticker=")), None)
    dry    = "--dry-run" in sys.argv
    main(limit=lim, dry_run=dry, single_ticker=ticker)
