#!/usr/bin/env python3
"""Squeeze Hunter — Roaring Kitty-style short squeeze detector.

Combines 7 signal layers into a Squeeze Score (0-100) and
assigns each candidate a Stage (COILED / IGNITION / ACTIVE / LATE).

Signal layers:
  1. Short % of float       (0-35 pts) — the fuel
  2. Days to cover          (0-20 pts) — the trap tightness
  3. Activist 13-D/13-G     (0-15 pts) — institutional match
  4. Insider buy cluster    (0-10 pts) — insider conviction
  5. Options gamma setup    (0-10 pts) — amplifier
  6. WSB mention velocity   (0-5 pts)  — crowd awareness
  7. SI trend (MoM)         (0-5 pts)  — shorts doubling down
  8. DTC acceleration       (0-10 pts) — Desai et al. (2002, JF): rapid DTC increase
                                         signals crowding that precedes squeeze

Outputs: squeeze_candidates.csv
"""
from __future__ import annotations

import csv
import datetime
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent

# Input files
SHORT_CSV    = ROOT / "short_data.csv"
OPTIONS_CSV  = ROOT / "options_flow.csv"
WSB_CSV      = ROOT / "wsb_mentions.csv"
CLUSTERS_CSV = ROOT / "insider_clusters.csv"
CATALYST_CSV = ROOT / "sec_catalyst_latest.csv"
QUOTE_CACHE  = ROOT / ".sec_quote_cache.json"

OUT_CSV      = ROOT / "squeeze_candidates.csv"

FIELDNAMES = [
    "ticker", "squeeze_score", "stage", "stage_emoji",
    "short_pct_float", "days_to_cover", "si_trend_pct",
    "activist_signal", "insider_cluster", "gamma_score",
    "wsb_mentions", "wsb_sentiment",
    "score_breakdown", "price", "market_cap",
    "si_score", "dtc_score", "activist_score", "insider_score",
    "gamma_pts", "wsb_score", "trend_score", "dtc_accel_score",
]

YAHOO_SUMMARY = (
    "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
    "?modules=price,defaultKeyStatistics"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


# ── Scoring functions ──────────────────────────────────────────────────────────
def score_short_pct(pct: float) -> int:
    """0-35 pts. The fuel — how trapped are the shorts?"""
    if pct >= 80: return 35
    if pct >= 60: return 30
    if pct >= 40: return 22
    if pct >= 25: return 14
    if pct >= 15: return 7
    if pct >= 8:  return 3
    return 0


def score_days_to_cover(dtc: float) -> int:
    """0-20 pts. How long to exit without moving price?"""
    if dtc >= 10: return 20
    if dtc >= 7:  return 16
    if dtc >= 5:  return 12
    if dtc >= 3:  return 7
    if dtc >= 2:  return 3
    return 0


def score_activist(ticker: str, activist_tickers: set[str]) -> int:
    """0-15 pts. 13-D or 13-G activist position filed recently."""
    return 15 if ticker in activist_tickers else 0


def score_insider(ticker: str, cluster_map: dict) -> int:
    """0-10 pts. Insider buy cluster from Form 4 filings."""
    entry = cluster_map.get(ticker)
    if not entry:
        return 0
    count   = int(entry.get("filing_count", 0) or 0)
    is_buy  = str(entry.get("confirmed_buy", "0")) == "1"
    if is_buy and count >= 3: return 10
    if is_buy and count >= 2: return 7
    if count >= 3:            return 5
    if count >= 2:            return 3
    return 1


def score_gamma(ticker: str, options_map: dict) -> int:
    """0-10 pts. Options gamma squeeze potential."""
    entry = options_map.get(ticker)
    if not entry:
        return 0
    return int(entry.get("gamma_score", 0) or 0)


def score_wsb(ticker: str, wsb_map: dict) -> tuple[int, int, str]:
    """0-5 pts. WSB awareness level (low = better for entry score)."""
    entry = wsb_map.get(ticker)
    if not entry:
        return 2, 0, "none"   # unknown = neutral
    count     = int(entry.get("mention_count_24h", 0) or 0)
    sentiment = entry.get("sentiment_label", "none")

    # Low awareness = good entry signal (still coiled)
    # Peak awareness = exhaustion risk
    if count == 0:    pts = 2   # undiscovered
    elif count <= 3:  pts = 5   # starting to get noticed — prime window
    elif count <= 10: pts = 4   # building
    elif count <= 25: pts = 3   # heating up
    elif count <= 50: pts = 1   # hot — late stage risk
    else:             pts = 0   # viral — probably late

    return pts, count, sentiment


def score_dtc_acceleration(dtc_current: float, dtc_prior: float) -> int:
    """0-10 pts. Desai et al. (2002, JF): rapid DTC increase = crowding signal.
    delta_DTC = DTC_now - DTC_30d_ago. Fast rise = shorts getting trapped."""
    delta = dtc_current - dtc_prior
    if delta >= 5:   return 10  # extreme crowding acceleration
    if delta >= 3:   return 7
    if delta >= 2:   return 5
    if delta >= 1:   return 3
    if delta >= 0.5: return 1
    return 0


def score_si_trend(trend_pct: float) -> int:
    """0-5 pts. Shorts increasing while stock is under pressure = trapped."""
    if trend_pct >= 20:  return 5   # shorts doubling down aggressively
    if trend_pct >= 10:  return 4
    if trend_pct >= 5:   return 3
    if trend_pct >= 0:   return 2   # shorts holding steady
    return 1                         # shorts covering (squeeze may have started)


def determine_stage(
    squeeze_score: int,
    wsb_count: int,
    si_pct: float,
    dtc: float,
    si_trend: float,
    has_activist: bool,
    has_insider: bool,
) -> tuple[str, str]:
    """
    Stage classification calibrated for small/mid-cap pipeline stocks.
      COILED    — SI elevated, low retail awareness, catalysts present → best entry
      IGNITION  — SI still high, WSB discovering, price starting to move
      ACTIVE    — Squeeze underway, high volume
      LATE      — Peak hype, exhaustion risk
      WATCH     — Setup building but not yet prime
    """
    if si_pct < 5:
        return "WATCH", "👀"

    # LATE: viral + SI declining
    if wsb_count > 30 and si_trend < -10:
        return "LATE", "⚠️"

    # ACTIVE: viral + still elevated SI
    if wsb_count > 20 and si_pct >= 10:
        return "ACTIVE", "⚡"

    # IGNITION: WSB discovering, SI still high, score decent
    if 5 < wsb_count <= 20 and si_pct >= 10 and squeeze_score >= 30:
        return "IGNITION", "🔥"

    # COILED: undiscovered + meaningful SI + institutional/insider catalyst
    if wsb_count <= 5 and si_pct >= 10 and dtc >= 3 and (has_activist or has_insider or squeeze_score >= 28):
        return "COILED", "🔒"

    # COILED: high SI even without explicit catalyst (pure structural setup)
    if wsb_count <= 5 and si_pct >= 20 and dtc >= 4:
        return "COILED", "🔒"

    return "WATCH", "👀"


# ── Data loaders ───────────────────────────────────────────────────────────────
def load_short_map() -> dict[str, dict]:
    m: dict[str, dict] = {}
    if SHORT_CSV.exists():
        with SHORT_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                m[row["ticker"]] = row
    return m


def load_quote_map() -> dict[str, dict]:
    """Price + market cap from .sec_quote_cache.json (~3k tickers)."""
    if not QUOTE_CACHE.exists():
        return {}
    try:
        import json as _j
        raw = _j.loads(QUOTE_CACHE.read_text(encoding="utf-8"))
        return {k: (v.get("data") or {}) for k, v in raw.items() if isinstance(v, dict)}
    except Exception:
        return {}


def load_options_map() -> dict[str, dict]:
    m: dict[str, dict] = {}
    if OPTIONS_CSV.exists():
        with OPTIONS_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                m[row["ticker"]] = row
    return m


def load_wsb_map() -> dict[str, dict]:
    m: dict[str, dict] = {}
    if WSB_CSV.exists():
        with WSB_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                m[row["ticker"]] = row
    return m


def load_cluster_map() -> dict[str, dict]:
    m: dict[str, dict] = {}
    if CLUSTERS_CSV.exists():
        with CLUSTERS_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                m[row["ticker"]] = row
    return m


def load_activist_tickers() -> set[str]:
    """13-D and 13-G filings = activist / institutional stake building."""
    activist: set[str] = set()
    if not CATALYST_CSV.exists():
        return activist
    with CATALYST_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            form = (row.get("form") or "").strip().upper()
            if form in ("SC 13D", "13D", "SC 13G", "13G", "SC 13D/A", "SC 13G/A"):
                t = (row.get("ticker") or "").strip().upper()
                if t:
                    activist.add(t)
    return activist


def load_all_tickers() -> list[str]:
    """All tickers with short data >= 8% — these are our candidates."""
    short_map = load_short_map()
    if short_map:
        return [t for t, r in short_map.items()
                if float(r.get("short_pct_float", 0) or 0) >= 8.0]
    # Fallback — use combined priority
    cp = ROOT / "combined_priority.csv"
    if not cp.exists():
        return []
    tickers = []
    with cp.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = (row.get("ticker") or "").strip().upper()
            if t:
                tickers.append(t)
    return tickers


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> int:
    print("build_squeeze_hunter: scoring candidates")

    short_map    = load_short_map()
    options_map  = load_options_map()
    wsb_map      = load_wsb_map()
    cluster_map  = load_cluster_map()
    activist_set = load_activist_tickers()
    tickers      = load_all_tickers()
    quote_map    = load_quote_map()

    print(f"  Inputs: {len(short_map)} short, {len(options_map)} options, "
          f"{len(wsb_map)} wsb, {len(cluster_map)} clusters, "
          f"{len(activist_set)} activist filings")
    print(f"  Scoring {len(tickers)} candidates...")

    results: list[dict] = []

    for ticker in tickers:
        s_row = short_map.get(ticker, {})
        si_pct   = float(s_row.get("short_pct_float", 0) or 0)
        dtc      = float(s_row.get("days_to_cover",   0) or 0)
        si_trend = float(s_row.get("si_trend_pct",    0) or 0)
        dtc_prior = float(s_row.get("days_to_cover_prior", 0) or 0)
        price    = s_row.get("price", "")
        mkt_cap  = s_row.get("market_cap", "")
        # Enrich from quote cache if short_data.csv has no price (it typically doesn't)
        if not price or not mkt_cap:
            q = quote_map.get(ticker, {}) or quote_map.get(ticker.upper(), {})
            if q:
                if not price and q.get("price") is not None:
                    price = str(round(float(q["price"]), 2))
                if not mkt_cap and q.get("market_cap") is not None:
                    mkt_cap = str(q["market_cap"])
        # Last-resort price fetch via stooq (only if still missing — small N per run)
        if not price:
            try:
                url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"
                req = urllib.request.Request(url, headers={"User-Agent": "CatalystEdge/1.0"})
                with urllib.request.urlopen(req, timeout=6) as r:
                    lines = r.read().decode("utf-8", errors="replace").strip().splitlines()
                if len(lines) >= 2:
                    last = lines[-1].split(",")
                    if len(last) >= 5:
                        price = str(round(float(last[4]), 2))
            except Exception:
                pass

        # Score each layer
        si_score       = score_short_pct(si_pct)
        dtc_score      = score_days_to_cover(dtc)
        dtc_accel      = score_dtc_acceleration(dtc, dtc_prior)
        activist_score = score_activist(ticker, activist_set)
        insider_score  = score_insider(ticker, cluster_map)
        gamma_pts      = score_gamma(ticker, options_map)
        wsb_pts, wsb_count, wsb_sent = score_wsb(ticker, wsb_map)
        trend_score    = score_si_trend(si_trend)

        total = (si_score + dtc_score + dtc_accel + activist_score + insider_score
                 + gamma_pts + wsb_pts + trend_score)

        stage, stage_emoji = determine_stage(
            total, wsb_count, si_pct, dtc, si_trend,
            has_activist=activist_score > 0,
            has_insider=insider_score > 0,
        )

        breakdown = (
            f"SI:{si_score} DTC:{dtc_score} ACT:{activist_score} "
            f"INS:{insider_score} GAMMA:{gamma_pts} WSB:{wsb_pts} TREND:{trend_score} "
            f"DTCA:{dtc_accel}"
        )

        results.append({
            "ticker":          ticker,
            "squeeze_score":   total,
            "stage":           stage,
            "stage_emoji":     stage_emoji,
            "short_pct_float": si_pct,
            "days_to_cover":   dtc,
            "si_trend_pct":    si_trend,
            "activist_signal": "YES" if activist_score > 0 else "no",
            "insider_cluster": "YES" if insider_score > 0 else "no",
            "gamma_score":     gamma_pts,
            "wsb_mentions":    wsb_count,
            "wsb_sentiment":   wsb_sent,
            "score_breakdown": breakdown,
            "price":           price,
            "market_cap":      mkt_cap,
            "si_score":        si_score,
            "dtc_score":       dtc_score,
            "activist_score":  activist_score,
            "insider_score":   insider_score,
            "gamma_pts":       gamma_pts,
            "wsb_score":       wsb_pts,
            "trend_score":     trend_score,
            "dtc_accel_score": dtc_accel,
        })

    # Sort: COILED first, then by score
    stage_order = {"COILED": 0, "IGNITION": 1, "ACTIVE": 2, "WATCH": 3, "LATE": 4}
    results.sort(key=lambda r: (
        stage_order.get(r["stage"], 9),
        -int(r["squeeze_score"])
    ))

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    coiled   = [r for r in results if r["stage"] == "COILED"]
    ignition = [r for r in results if r["stage"] == "IGNITION"]
    print(f"\n  Results: {len(results)} candidates scored")
    print(f"  COILED    (best entry): {len(coiled)}")
    print(f"  IGNITION  (momentum):   {len(ignition)}")
    print(f"  Top picks:")
    for r in results[:5]:
        print(f"    {r['stage_emoji']} {r['ticker']:8s} score={r['squeeze_score']:3d} "
              f"SI={r['short_pct_float']:.1f}% DTC={r['days_to_cover']:.1f}d "
              f"WSB={r['wsb_mentions']} | {r['score_breakdown']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
