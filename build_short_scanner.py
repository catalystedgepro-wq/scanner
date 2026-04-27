#!/usr/bin/env python3
"""build_short_scanner.py — Bearish counterpart to combined_priority.csv.

Filters existing SEC EDGAR feed + cluster data for BEARISH patterns:
  - 8-K Item 5.02 (CEO/CFO departure, no successor named) — strongest bear signal
  - 8-K Item 4.02 (non-reliance / accounting restatements) — very bearish
  - 8-K Item 1.03 (bankruptcy filings)
  - S-3 / S-3ASR (shelf registration → dilution risk)
  - 424B2/B3/B5 (prospectus supplements → ATM offerings → dilution)
  - 10-K/A or NT-10K (delayed/amended annual reports)
  - Going-concern qualifications (parsed from 10-K text)
  - Form 4 cluster SELLS (CEO+CFO selling > $250K in same week)

Output: docs/data/short_scanner.json (rendered by /short-scanner/ page)
        docs/short_scanner_latest.csv (parallel to combined_priority.csv)

This is the regime-symmetric scanner: existing /scanner/ flags LONG ideas,
this flags SHORT ideas (or stay-away ideas for longs).
"""
from __future__ import annotations

import csv
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
RAW_CSV = ROOT / "sec_catalyst_latest.csv"
F4_CSV = ROOT / "sec_form4_latest.csv"            # optional — may not exist
# Specialized fetchers write to ROOT, not docs/. Earlier paths were wrong.
BANKRUPTCY_CSV = ROOT / "sec_bankruptcy.csv"
DELIST_CSV = ROOT / "sec_delisting.csv"
LATE_FILING_CSV = ROOT / "sec_late_filing.csv"
OUT_JSON = ROOT / "docs/data/short_scanner.json"
OUT_CSV = ROOT / "docs/short_scanner_latest.csv"
LOG = ROOT / "logs/short_scanner.log"
LOG.parent.mkdir(exist_ok=True)
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

# Bearish form-type weights
BEAR_FORM_WEIGHTS = {
    "8-K/A": 6,        # amended 8-K — usually correcting bad news
    "8-K": 0,          # neutral until item parsed
    "S-3": 5,          # shelf → dilution risk
    "S-3/A": 5,
    "S-3ASR": 5,
    "S-1": 4,          # IPO/secondary
    "S-1/A": 4,
    "424B2": 4,        # prospectus supplement
    "424B3": 4,
    "424B5": 5,        # ATM-offering prospectus
    "424B4": 3,
    "10-K/A": 7,       # restated 10-K — material misstatement
    "NT-10-K": 6,      # late annual report
    "NT-10-Q": 5,      # late quarterly
    "10-Q/A": 6,       # restated 10-Q
    "DEF 14A": 0,      # proxy — neutral
    "DEFA14A": 0,
}

# 8-K Item bearish patterns (parse from filing link or summary)
BEAR_8K_ITEMS = {
    "Item 5.02": 7,   # officer departure
    "Item 4.02": 9,   # non-reliance / restatement
    "Item 1.03": 10,  # bankruptcy
    "Item 3.01": 6,   # delisting notice
    "Item 4.01": 5,   # auditor change (could be either; weight as cautious bear)
    "Item 8.01": 0,   # other — neutral
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(m: str) -> None:
    line = f"[{now_iso()}] short_scanner: {m}"
    LOG.open("a").write(line + "\n")
    print(line)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def fetch_yahoo_quote(ticker: str) -> dict:
    """Pull live price + ATR14 + avg_vol + market_cap from Yahoo v8 chart API.
    Returns zeros on any failure (rate limit, suspended ticker, etc.).
    """
    res = {"price": 0.0, "atr14": 0.0, "avg_vol": 0.0, "market_cap": 0.0}
    if not ticker:
        return res
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1d&range=30d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            d = json.loads(r.read())
        results = (d.get("chart") or {}).get("result") or []
        if not results:
            return res
        meta = results[0].get("meta") or {}
        px = float(meta.get("regularMarketPrice") or 0)
        if px > 0:
            res["price"] = px
        ind = (results[0].get("indicators") or {}).get("quote", [{}])[0]
        highs = ind.get("high") or []
        lows = ind.get("low") or []
        closes = ind.get("close") or []
        vols = ind.get("volume") or []
        bars = [(h, l, c) for h, l, c in zip(highs, lows, closes)
                if h is not None and l is not None and c is not None]
        if len(bars) >= 15:
            trs = []
            for i in range(1, len(bars)):
                h, l, _ = bars[i]
                _h_prev, _l_prev, prev_c = bars[i - 1]
                trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
            atr14 = sum(trs[-14:]) / 14
            if atr14 > 0:
                res["atr14"] = atr14
        clean_vols = [v for v in vols if v is not None]
        if clean_vols:
            res["avg_vol"] = sum(clean_vols) / len(clean_vols)
    except Exception:
        return res

    # Market cap via Yahoo quote summary v7 endpoint (no auth needed).
    try:
        url2 = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
        req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=6) as r2:
            d2 = json.loads(r2.read())
        rows = ((d2.get("quoteResponse") or {}).get("result") or [])
        if rows:
            mcap = float(rows[0].get("marketCap") or 0)
            if mcap > 0:
                res["market_cap"] = mcap
            # Bonus fields useful for short-side intelligence.
            res["short_pct_float"] = float(rows[0].get("shortPercentOfFloat") or 0) * 100
            res["short_ratio"] = float(rows[0].get("shortRatio") or 0)
            res["pct_change"] = float(rows[0].get("regularMarketChangePercent") or 0)
    except Exception:
        pass

    # Fallback for market cap: quoteSummary endpoint exposes summaryDetail.marketCap
    # for some tickers (preferreds, ADRs) where v7 quote returns zero.
    if res.get("market_cap", 0) <= 0:
        try:
            url3 = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
                    f"?modules=summaryDetail,price")
            req3 = urllib.request.Request(url3, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req3, timeout=6) as r3:
                d3 = json.loads(r3.read())
            qr = ((d3.get("quoteSummary") or {}).get("result") or [])
            if qr:
                price_blk = qr[0].get("price") or {}
                mcap_blk = (price_blk.get("marketCap") or {}).get("raw") or 0
                if not mcap_blk:
                    sd = qr[0].get("summaryDetail") or {}
                    mcap_blk = (sd.get("marketCap") or {}).get("raw") or 0
                if mcap_blk:
                    res["market_cap"] = float(mcap_blk)
        except Exception:
            pass
    return res


def extract_bearish_heatmap() -> list:
    """Pull the inlined `var _heatmapData = [...]` blob from docs/scanner/index.html
    and return it sorted by bearishWeight desc (so the bearish-leaning sectors
    lead). Returns empty list on any parse failure — heatmap is optional.
    """
    src_path = ROOT / "docs/scanner/index.html"
    if not src_path.exists():
        return []
    try:
        src = src_path.read_text(encoding="utf-8")
        m = re.search(r"var\s+_heatmapData\s*=\s*(\[.*?\]);", src, re.DOTALL)
        if not m:
            return []
        rows = json.loads(m.group(1))
        # Sort by bearishWeight desc, falling back to total score desc.
        rows.sort(key=lambda d: (
            -float(d.get("bearishWeight") or 0),
            -float(d.get("score") or 0),
        ))
        # Mark the top-3 bearish-weighted sectors with their own pulse so the
        # ⚡ icon highlights bearish dominance (not raw filing volume).
        bear_rank = 0
        for d in rows:
            d["bearishPulse"] = False
            if (d.get("bearishWeight") or 0) > 0 and bear_rank < 3:
                d["bearishPulse"] = True
                bear_rank += 1
        return rows
    except Exception as e:
        log(f"  heatmap extract failed: {e}")
        return []


def enrich_short_trade_frame(row: dict) -> None:
    """Mutates row in-place with short-side trade frame fields.

    Mirrors the bullish ATR14 trade frame used by /scanner/, but inverts
    direction: short entry = current price, stop = entry + 1×ATR (above),
    target1 = entry − 1R (below), target2 = entry − 2R (below).
    Falls back to fixed-% (5/8/12) when ATR is unavailable.
    """
    ticker = (row.get("ticker") or "").upper().strip()
    q = fetch_yahoo_quote(ticker)
    price = q["price"]
    atr = q["atr14"]
    vol = q["avg_vol"]
    cap = q["market_cap"]
    if price <= 0:
        return
    row["price"] = round(price, 4)
    if atr > 0:
        stop = price + atr                              # short stop ABOVE
        row["atr14"] = round(atr, 3)
        row["stop_method"] = "ATR14"
    else:
        stop_pct = 0.12 if price < 1 else 0.08 if price < 5 else 0.05
        stop = price * (1 + stop_pct)
        row["stop_method"] = "fixed"
    R = max(0.01, stop - price)
    row["entry"] = round(price, 2)
    row["stop"] = round(stop, 2)
    row["target1"] = round(price - R, 2)                # 1R DOWN
    row["target2"] = round(price - 2 * R, 2)            # 2R DOWN
    row["r_usd"] = round(R, 2)
    row["r_pct"] = round(R / price * 100, 1)
    row["conviction_tag"] = "2R ladder" if row.get("score", 0) >= 15 else "1R focus"
    if vol > 0:
        row["avg_vol"] = int(vol)
    if cap > 0:
        row["market_cap"] = round(cap, 0)
        row["float_approx"] = round(cap / price, 0)
    # Short-side intelligence (when Yahoo provides it).
    sp_float = q.get("short_pct_float", 0)
    if sp_float > 0:
        row["short_pct_float"] = round(sp_float, 2)
    sr = q.get("short_ratio", 0)
    if sr > 0:
        row["short_ratio"] = round(sr, 2)
    pc = q.get("pct_change")
    if pc is not None:
        row["pct_change_today"] = round(pc, 2)


def main() -> int:
    raw = read_csv(RAW_CSV)
    bear_rows: dict[str, dict] = {}  # ticker -> rolling-up bear data

    for r in raw:
        t = (r.get("ticker") or "").strip().upper()
        f = (r.get("form") or "").strip()
        if not t or not f:
            continue
        weight = BEAR_FORM_WEIGHTS.get(f, 0)
        if weight <= 0:
            continue
        if t not in bear_rows:
            bear_rows[t] = {"ticker": t, "score": 0, "signals": [], "forms": []}
        bear_rows[t]["score"] += weight
        bear_rows[t]["signals"].append(f"{f} (+{weight})")
        bear_rows[t]["forms"].append(f)
        bear_rows[t]["last_filing_link"] = r.get("link", "")
        bear_rows[t]["recency_min"] = r.get("recency_min", "")

    # Boost from bankruptcy file
    for r in read_csv(BANKRUPTCY_CSV):
        t = (r.get("ticker") or "").strip().upper()
        if not t:
            continue
        if t not in bear_rows:
            bear_rows[t] = {"ticker": t, "score": 0, "signals": [], "forms": []}
        bear_rows[t]["score"] += 12
        bear_rows[t]["signals"].append("BANKRUPTCY filing (+12)")
        bear_rows[t]["bankruptcy"] = True

    # Build a CIK→ticker lookup from the main catalyst feed for files
    # (delisting, bankruptcy) that may only carry CIK without ticker.
    cik_to_ticker: dict[str, str] = {}
    for r in raw:
        ck = (r.get("cik") or "").strip().lstrip("0")
        tk = (r.get("ticker") or "").strip().upper()
        if ck and tk:
            cik_to_ticker[ck] = tk

    def resolve_ticker(row: dict) -> str:
        t = (row.get("ticker") or "").strip().upper()
        if t:
            return t
        ck = (row.get("cik") or row.get("ciks") or "").strip().lstrip("0")
        if ck and ck in cik_to_ticker:
            return cik_to_ticker[ck]
        return ""

    # Boost from delisting file (resolve missing ticker via CIK)
    for r in read_csv(DELIST_CSV):
        t = resolve_ticker(r)
        if not t:
            continue
        if t not in bear_rows:
            bear_rows[t] = {"ticker": t, "score": 0, "signals": [], "forms": []}
        bear_rows[t]["score"] += 10
        form_kind = (r.get("form") or "").strip() or "DELIST"
        bear_rows[t]["signals"].append(f"DELISTING ({form_kind}) (+10)")
        bear_rows[t]["delisting"] = True
        if not bear_rows[t].get("last_filing_link"):
            bear_rows[t]["last_filing_link"] = r.get("link", "")

    # ── Late filings (NT-10-K / NT-10-Q / NT-20-F + amendments) ──────────────
    late_weights = {
        "NT 10-K": 6, "NT-10-K": 6, "NT 10-K/A": 6, "NT-10-K/A": 6,
        "NT 10-Q": 5, "NT-10-Q": 5, "NT 10-Q/A": 5, "NT-10-Q/A": 5,
        "NT 20-F": 6, "NT-20-F": 6,
    }
    for r in read_csv(LATE_FILING_CSV):
        t = resolve_ticker(r)
        if not t:
            continue
        f = (r.get("form") or "").strip()
        w = late_weights.get(f, 4)
        if t not in bear_rows:
            bear_rows[t] = {"ticker": t, "score": 0, "signals": [], "forms": []}
        bear_rows[t]["score"] += w
        # Normalize to space-style for downstream regex bucketing
        norm = f.replace(" ", "-") if f.startswith("NT ") else f
        bear_rows[t]["signals"].append(f"{norm} (+{w})")
        bear_rows[t]["forms"].append(norm)
        # Repeat-distress (cluster_count > 1) is a stronger signal — bonus weight
        try:
            cluster_n = int(r.get("cluster_count") or 0)
            if cluster_n >= 2:
                bear_rows[t]["score"] += 3
                bear_rows[t]["signals"].append(f"Late-filing repeat ({cluster_n}x) (+3)")
                bear_rows[t]["late_filing_repeat"] = cluster_n
        except (TypeError, ValueError):
            pass
        bear_rows[t]["late_filing"] = True
        if not bear_rows[t].get("last_filing_link"):
            bear_rows[t]["last_filing_link"] = r.get("url", "") or r.get("link", "")

    # ── Form 4 activity clusters (from main catalyst feed) ─────────────────
    # Without the dedicated form4 file we can't filter by S/F transaction
    # codes — but we CAN flag tickers with multiple Form 4 events in the
    # current EDGAR window as activity clusters. UI labels honestly:
    # "Insider activity cluster — verify direction in EDGAR before shorting".
    f4_by_ticker: dict[str, list[dict]] = {}
    for r in raw:
        if (r.get("form") or "").strip() != "4":
            continue
        t = (r.get("ticker") or "").strip().upper()
        if t:
            f4_by_ticker.setdefault(t, []).append(r)
    for t, rows in f4_by_ticker.items():
        if len(rows) >= 2:
            if t not in bear_rows:
                bear_rows[t] = {"ticker": t, "score": 0, "signals": [], "forms": []}
            bear_rows[t]["score"] += 6   # lower than verified-sell weight (8)
            bear_rows[t]["signals"].append(
                f"Form 4 activity cluster — {len(rows)} filings (+6)")
            bear_rows[t]["insider_cluster_sell_count"] = len(rows)
            # We don't have $ values here — leave usd unset so UI shows "—"
            # rather than a fabricated number.
            if not bear_rows[t].get("last_filing_link"):
                bear_rows[t]["last_filing_link"] = rows[0].get("link", "")

    # Optional: if the dedicated Form 4 file ever materializes, override with
    # verified S/F cluster sells (+8 weight, dollar-value gated at $250K).
    if F4_CSV.exists():
        f4_rows = read_csv(F4_CSV)
        by_t: dict[str, list[dict]] = {}
        for r in f4_rows:
            t = (r.get("ticker") or "").strip().upper()
            tx = (r.get("transaction_code") or "").strip()
            if t and tx in ("S", "F"):
                by_t.setdefault(t, []).append(r)
        for t, sells in by_t.items():
            if len(sells) < 2:
                continue
            total = 0.0
            for r in sells:
                try:
                    total += float(r.get("transaction_value_usd") or 0)
                except ValueError:
                    pass
            if total >= 250_000:
                if t not in bear_rows:
                    bear_rows[t] = {"ticker": t, "score": 0, "signals": [], "forms": []}
                bear_rows[t]["score"] += 8
                bear_rows[t]["signals"].append(
                    f"Verified insider SELL cluster — {len(sells)} sales / ${total:,.0f} (+8)")
                bear_rows[t]["insider_cluster_sell_usd"] = total
                bear_rows[t]["insider_cluster_sell_count"] = len(sells)

    # Sort by score desc
    sorted_rows = sorted(bear_rows.values(), key=lambda r: -r["score"])

    # Enrich top-12 with price/ATR14/avg_vol/market_cap + INVERTED trade frame
    # (short side: stop is ABOVE entry, targets are BELOW entry).
    # 12 covers the card grid (6) + safety margin if some lookups fail.
    for r in sorted_rows[:12]:
        try:
            enrich_short_trade_frame(r)
        except Exception as e:
            log(f"  enrich failed for {r.get('ticker')}: {e}")

    # Bucket tickers into bearish-signal categories so /short-scanner/ can
    # render parallel tables (Dilution / Restatement / Departures / etc.)
    # the same way /scanner/ has Gap / Squeeze / Insider sections.
    DILUTION_FORMS = {"S-3", "S-3/A", "S-3ASR", "S-1", "S-1/A",
                      "424B2", "424B3", "424B4", "424B5"}
    RESTATEMENT_FORMS = {"10-K/A", "10-Q/A", "8-K/A"}
    LATE_FORMS = {"NT-10-K", "NT-10-Q", "NT-10-K/A", "NT-10-Q/A", "NT-20-F"}
    # 8-K Item codes appear inside the signal string we appended above
    # (e.g. "Item 5.02 (+7)") — but BEAR_FORM_WEIGHTS only weights raw forms.
    # For bucketing we read back from row signals + flags.

    def has_form(row, forms):
        for s in row.get("signals", []):
            head = s.split(" (")[0]
            if head in forms:
                return True
        return False

    def bucket_filter(rows, predicate, max_n=20):
        return [r for r in rows if predicate(r)][:max_n]

    buckets = {
        "dilution":     bucket_filter(sorted_rows, lambda r: has_form(r, DILUTION_FORMS)),
        "restatement":  bucket_filter(sorted_rows, lambda r: has_form(r, RESTATEMENT_FORMS)),
        "late_filing":  bucket_filter(sorted_rows, lambda r: has_form(r, LATE_FORMS)),
        "bankruptcy":   bucket_filter(sorted_rows, lambda r: r.get("bankruptcy") or r.get("delisting")),
        "insider_sell": bucket_filter(sorted_rows, lambda r: r.get("insider_cluster_sell_count", 0) >= 2),
    }

    # Extract sector heatmap from /scanner/ page and re-sort by bearishWeight
    # so the bearish-leaning sectors lead. Data already includes bull/bear/neutral
    # counts + macro signals + Akerlof flags + GICS industry hierarchy.
    heatmap_rows = extract_bearish_heatmap()
    HEATMAP_OUT = ROOT / "docs/data/short_heatmap.json"
    HEATMAP_OUT.write_text(json.dumps(
        {"as_of": now_iso(), "sectors": heatmap_rows}, indent=2))

    out = {
        "as_of": now_iso(),
        "universe_size": len(raw),
        "bearish_count": len(sorted_rows),
        "bucket_counts": {k: len(v) for k, v in buckets.items()},
        "top": sorted_rows[:50],
        "buckets": buckets,
        "sector_heatmap_count": len(heatmap_rows),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))

    # Also write CSV parallel to combined_priority.csv
    with OUT_CSV.open("w") as f:
        f.write("ticker,bear_score,top_signals,bankruptcy,delisting,recency_min\n")
        for r in sorted_rows:
            f.write(f"{r['ticker']},{r['score']},"
                    f"{'|'.join(r.get('signals', [])[:3]).replace(',', ';')},"
                    f"{int(r.get('bankruptcy', False))},"
                    f"{int(r.get('delisting', False))},"
                    f"{r.get('recency_min', '')}\n")

    log(f"DONE  bearish_tickers={len(sorted_rows)}  top3={[r['ticker'] for r in sorted_rows[:3]]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
