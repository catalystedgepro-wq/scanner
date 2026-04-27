#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime
import json
import time
import urllib.request
from pathlib import Path

from everos_memory_client import EverOSRequestError, backend_available, load_config, render_note, save_messages

ROOT = Path(__file__).parent
OUT = ROOT / "sympathy_events.csv"
STATUS = ROOT / "sympathy_burst_status.json"
STOOQ_CACHE_PATH = ROOT / ".stooq_daily_cache.json"

FIELDNAMES = [
    "date", "trigger_ticker", "sector", "gap_score", "form",
    "price_t0", "peers", "peer_prices_t0",
    "price_t1day", "move_pct_t1day", "peer_avg_move_pct_t1day",
]

STOOQ_URL = "https://stooq.com/q/d/l/?s={sym}.us&i=d"
SCORE_THRESHOLD = 13
BURST_LOOKBACK_DAYS = 5
BURST_GROUP_THRESHOLD = 4
BURST_HIDE_THRESHOLD = 8

_stooq_cache: dict | None = None


def _load_stooq_cache() -> dict:
    """Load shared Stooq cache (refreshed daily by classify_sec_catalysts.py).

    Droplet cannot reach stooq.com:443 directly (audited 2026-04-16: curl times
    out), so direct fetch here silently returned None and left price_t0 empty
    for all 715 events. Using the cache keeps sympathy math in sync with the
    classifier's price layer.
    """
    global _stooq_cache
    if _stooq_cache is not None:
        return _stooq_cache
    try:
        _stooq_cache = json.loads(STOOQ_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        _stooq_cache = {}
    return _stooq_cache


def _fetch_price(ticker: str) -> float | None:
    sym = ticker.upper()
    cache = _load_stooq_cache()
    entry = cache.get(sym)
    if isinstance(entry, dict):
        rows = entry.get("rows") or []
        if rows:
            last = rows[-1]
            if isinstance(last, dict):
                close = last.get("Close") or last.get("close")
                try:
                    if close is not None:
                        return float(close)
                except (TypeError, ValueError):
                    pass
            elif isinstance(last, (list, tuple)) and len(last) >= 5:
                try:
                    return float(last[4])
                except (TypeError, ValueError):
                    pass
    url = STOOQ_URL.format(sym=ticker.lower())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CatalystEdge/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            lines = response.read().decode("utf-8").strip().splitlines()
        if len(lines) < 2:
            return None
        last = lines[-1].split(",")
        return float(last[4]) if len(last) >= 5 else None
    except Exception:
        return None


def load_sector_lookup() -> dict[str, list[str]]:
    path = ROOT / "sector_lookup.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_existing() -> list[dict[str, str]]:
    if not OUT.exists():
        return []
    with OUT.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def save_all(rows: list[dict[str, str]]) -> None:
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _coerce_float(raw: str | float | int | None) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _coerce_date(raw: str | None) -> datetime.date | None:
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(str(raw).strip())
    except ValueError:
        return None


def _density_mode_for_count(count: int) -> str:
    if count >= BURST_HIDE_THRESHOLD:
        return "suppressed"
    if count >= BURST_GROUP_THRESHOLD:
        return "grouped"
    return "full"


def fill_t1day(rows: list[dict[str, str]]) -> tuple[int, list[dict[str, str]]]:
    today = datetime.date.today().isoformat()
    filled = 0
    resolved_rows: list[dict[str, str]] = []

    for row in rows:
        if row.get("price_t1day") or not row.get("date") or row["date"] >= today:
            continue

        t0 = _coerce_float(row.get("price_t0"))
        ticker = (row.get("trigger_ticker") or "").upper()
        if not ticker:
            continue

        price = _fetch_price(ticker)
        if not price:
            continue

        row["price_t1day"] = f"{price:.4f}"
        if t0 and t0 > 0:
            row["move_pct_t1day"] = f"{((price - t0) / t0 * 100):.2f}"
        time.sleep(0.15)

        peers = [peer.strip() for peer in (row.get("peers") or "").split(",") if peer.strip()]
        peer_t0s: dict[str, float] = {}
        for pair in (row.get("peer_prices_t0") or "").split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue
            symbol, value = pair.split(":", 1)
            parsed = _coerce_float(value)
            if parsed is not None:
                peer_t0s[symbol.strip().upper()] = parsed

        peer_moves = []
        for peer in peers[:5]:
            peer_price = _fetch_price(peer)
            if peer_price and peer in peer_t0s and peer_t0s[peer] > 0:
                peer_moves.append((peer_price - peer_t0s[peer]) / peer_t0s[peer] * 100)
            time.sleep(0.12)
        if peer_moves:
            row["peer_avg_move_pct_t1day"] = f"{(sum(peer_moves) / len(peer_moves)):.2f}"

        resolved_rows.append(dict(row))
        filled += 1

    return filled, resolved_rows


def _mirror_to_everos(new_rows: list[dict[str, str]], resolved_rows: list[dict[str, str]]) -> None:
    cfg = load_config()
    if not cfg.enabled:
        print("build_sympathy_logger: EverOS disabled")
        return
    if not backend_available(cfg):
        print("build_sympathy_logger: EverOS backend unavailable")
        return

    messages: list[dict[str, str]] = []

    for row in new_rows:
        trigger = (row.get("trigger_ticker") or "").upper()
        peers = [peer.strip() for peer in (row.get("peers") or "").split(",") if peer.strip()]
        messages.append(
            {
                "role": "assistant",
                "content": render_note(
                    f"Sympathy setup {trigger}",
                    body=(
                        f"Leader {trigger} opened a new sympathy setup in {row.get('sector', 'unknown')} "
                        f"with gap score {row.get('gap_score', '')} and form {row.get('form', '')}."
                    ),
                    metadata={
                        "kind": "sympathy_setup",
                        "date": row.get("date", ""),
                        "trigger_ticker": trigger,
                        "sector": row.get("sector", "unknown"),
                        "gap_score": _coerce_float(row.get("gap_score")),
                        "form": row.get("form", ""),
                        "price_t0": _coerce_float(row.get("price_t0")),
                        "peers": peers[:5],
                        "peer_prices_t0": row.get("peer_prices_t0", ""),
                    },
                ),
            }
        )

    for row in resolved_rows:
        trigger = (row.get("trigger_ticker") or "").upper()
        messages.append(
            {
                "role": "assistant",
                "content": render_note(
                    f"Sympathy outcome {trigger}",
                    body=(
                        f"The T+1 outcome for {trigger} is now resolved with move {row.get('move_pct_t1day', '')}% "
                        f"versus peer average {row.get('peer_avg_move_pct_t1day', '')}%."
                    ),
                    metadata={
                        "kind": "sympathy_outcome",
                        "date": row.get("date", ""),
                        "trigger_ticker": trigger,
                        "sector": row.get("sector", "unknown"),
                        "gap_score": _coerce_float(row.get("gap_score")),
                        "price_t0": _coerce_float(row.get("price_t0")),
                        "price_t1day": _coerce_float(row.get("price_t1day")),
                        "move_pct_t1day": _coerce_float(row.get("move_pct_t1day")),
                        "peer_avg_move_pct_t1day": _coerce_float(row.get("peer_avg_move_pct_t1day")),
                    },
                ),
            }
        )

    if not messages:
        return

    today = datetime.date.today().isoformat()
    try:
        saved = save_messages(
            messages,
            cfg=cfg,
            flush=True,
            id_seed=f"sympathy:{today}",
            scene="cerebro_sympathy",
            raw_data_type="CerebroSympathyEvent",
        )
        print(f"build_sympathy_logger: mirrored {saved} sympathy memory event(s) into EverOS")
    except EverOSRequestError as exc:
        print(f"build_sympathy_logger: EverOS mirror failed ({exc})")


def _write_burst_status(
    all_rows: list[dict[str, str]],
    new_rows: list[dict[str, str]],
    resolved_rows: list[dict[str, str]],
) -> dict[str, object]:
    today = datetime.date.today()
    lookback_floor = today - datetime.timedelta(days=BURST_LOOKBACK_DAYS)
    recent_open_rows: list[dict[str, str]] = []

    for row in all_rows:
        row_date = _coerce_date(row.get("date"))
        if row_date is None or row_date < lookback_floor:
            continue
        if row.get("price_t1day"):
            continue
        recent_open_rows.append(row)

    sector_summary: dict[str, dict[str, object]] = {}
    for row in recent_open_rows:
        sector = (row.get("sector") or "unknown").strip().lower() or "unknown"
        item = sector_summary.setdefault(
            sector,
            {
                "sector": sector,
                "count": 0,
                "new_today": 0,
                "avg_gap_score": 0.0,
                "leaders": [],
                "forms": [],
            },
        )
        item["count"] = int(item["count"]) + 1
        if _coerce_date(row.get("date")) == today:
            item["new_today"] = int(item["new_today"]) + 1
        score = _coerce_float(row.get("gap_score")) or 0.0
        item["avg_gap_score"] = float(item["avg_gap_score"]) + score
        ticker = (row.get("trigger_ticker") or "").upper().strip()
        if ticker and ticker not in item["leaders"]:
            item["leaders"].append(ticker)
        form = (row.get("form") or "").strip().upper()
        if form and form not in item["forms"]:
            item["forms"].append(form)

    sectors: list[dict[str, object]] = []
    for item in sector_summary.values():
        count = int(item["count"])
        avg_gap_score = float(item["avg_gap_score"]) / count if count else 0.0
        density_mode = _density_mode_for_count(count)
        level = "active" if count >= 2 else "watch"
        sectors.append(
            {
                "sector": item["sector"],
                "count": count,
                "new_today": int(item["new_today"]),
                "avg_gap_score": round(avg_gap_score, 2),
                "leaders": item["leaders"][:5],
                "forms": item["forms"][:4],
                "density_mode": density_mode,
                "level": level,
            }
        )

    sectors.sort(key=lambda item: (item["count"], item["new_today"], item["avg_gap_score"]), reverse=True)
    top_sector = sectors[0] if sectors else None
    top_count = int(top_sector["count"]) if top_sector else 0
    ui_density_mode = _density_mode_for_count(top_count) if top_sector else "full"

    payload: dict[str, object] = {
        "generated_at": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "today": today.isoformat(),
        "lookback_days": BURST_LOOKBACK_DAYS,
        "source_file": OUT.name,
        "active_burst": bool(top_sector and top_count >= 2),
        "ui_density_mode": ui_density_mode,
        "thresholds": {
            "grouped_labels": BURST_GROUP_THRESHOLD,
            "suppressed_labels": BURST_HIDE_THRESHOLD,
            "active_burst_min_sector_count": 2,
        },
        "totals": {
            "rows": len(all_rows),
            "new_entries": len(new_rows),
            "resolved_entries": len(resolved_rows),
            "open_recent_setups": len(recent_open_rows),
            "watch_sectors": len(sectors),
        },
        "top_sector": top_sector,
        "sectors": sectors[:8],
    }

    STATUS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if top_sector:
        print(
            "build_sympathy_logger: burst_status "
            f"active={payload['active_burst']} sector={top_sector['sector']} "
            f"count={top_sector['count']} ui_density={ui_density_mode}"
        )
    else:
        print("build_sympathy_logger: burst_status active=False sector=none ui_density=full")
    return payload


def _load_gapper_rows() -> list[dict[str, str]]:
    gappers_file = ROOT / "sec_clean_gappers.csv"
    if not gappers_file.exists():
        gappers_file = ROOT / "sec_top_gappers.csv"
    if not gappers_file.exists():
        return []
    with gappers_file.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    today = datetime.date.today().isoformat()
    sector_lookup = load_sector_lookup()
    existing = load_existing()

    filled, resolved_rows = fill_t1day(existing)
    if filled:
        print(f"build_sympathy_logger: filled {filled} T+1day price(s)")

    gapper_rows = _load_gapper_rows()
    if not gapper_rows:
        print("build_sympathy_logger: no gappers file found - skipping today's log")
        save_all(existing)
        _mirror_to_everos([], resolved_rows)
        _write_burst_status(existing, [], resolved_rows)
        return

    logged_today = {row.get("trigger_ticker") for row in existing if row.get("date") == today}
    new_rows: list[dict[str, str]] = []

    for row in gapper_rows:
        ticker = (row.get("ticker") or "").strip().upper()
        if not ticker or ticker in logged_today:
            continue

        # Exclude non-common-stock tickers: preferred shares (C-PR, NXDT-PA),
        # warrants (-WT), units (-U), and any ticker over 5 chars that isn't pure
        # alpha (SLNHP, DMII pass len test but are OTC noise — cut those with
        # TRU/RU suffix letters that preferred shares use).
        if "-" in ticker or "/" in ticker or "." in ticker:
            continue
        if len(ticker) > 5 or not ticker.isalpha():
            continue

        score = _coerce_float(row.get("gapper_score") or row.get("priority_score")) or 0.0
        if score < SCORE_THRESHOLD:
            continue

        form = row.get("form", "")
        sectors = sector_lookup.get(ticker, [])
        sector = sectors[0] if sectors else "unknown"

        peers: list[str] = []
        if sector != "unknown":
            for other in gapper_rows:
                other_ticker = (other.get("ticker") or "").strip().upper()
                if not other_ticker or other_ticker == ticker:
                    continue
                if sector in sector_lookup.get(other_ticker, []):
                    peers.append(other_ticker)
                if len(peers) >= 5:
                    break

        price_t0 = _fetch_price(ticker)
        time.sleep(0.12)

        peer_prices: list[str] = []
        for peer in peers[:5]:
            peer_price = _fetch_price(peer)
            if peer_price:
                peer_prices.append(f"{peer}:{peer_price:.4f}")
            time.sleep(0.12)

        new_rows.append(
            {
                "date": today,
                "trigger_ticker": ticker,
                "sector": sector,
                "gap_score": f"{score:.2f}",
                "form": form,
                "price_t0": f"{price_t0:.4f}" if price_t0 else "",
                "peers": ",".join(peers),
                "peer_prices_t0": ",".join(peer_prices),
                "price_t1day": "",
                "move_pct_t1day": "",
                "peer_avg_move_pct_t1day": "",
            }
        )
        print(f"  logged: {ticker} sector={sector} score={score} price_t0={price_t0} peers={peers}")

    all_rows = existing + new_rows
    save_all(all_rows)
    _mirror_to_everos(new_rows, resolved_rows)
    _write_burst_status(all_rows, new_rows, resolved_rows)
    print(f"build_sympathy_logger: +{len(new_rows)} new entries -> {len(all_rows)} total in sympathy_events.csv")


if __name__ == "__main__":
    main()
