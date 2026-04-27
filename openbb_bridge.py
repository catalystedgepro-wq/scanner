#!/usr/bin/env python3
"""Optional OpenBB-backed macro + crypto pilot surface for Cerebro."""
from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from importlib.util import find_spec
from io import StringIO
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from market_data_contract import openbb_pilot_settings, provider_contract, provider_summary


_DEFAULT_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}


def _provider_map() -> dict[str, dict]:
    return {row["id"]: row for row in provider_contract()}


def _first_configured_provider(priority: list[str]) -> str:
    providers = _provider_map()
    for provider_id in priority:
        if providers.get(provider_id, {}).get("configured"):
            return provider_id
    return priority[0] if priority else ""


def _openbb_import_ready() -> bool:
    return bool(find_spec("openbb"))


def _import_obb():
    if not _openbb_import_ready():
        raise RuntimeError("openbb_not_installed")
    from openbb import obb  # type: ignore

    return obb


def _normalize_rows(raw: Any) -> list[dict]:
    if raw is None:
        return []
    if hasattr(raw, "results"):
        return _normalize_rows(getattr(raw, "results"))
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        rows: list[dict] = []
        for item in raw:
            if isinstance(item, dict):
                rows.append(item)
            elif hasattr(item, "model_dump"):
                rows.append(item.model_dump())
            elif hasattr(item, "dict"):
                rows.append(item.dict())
            elif hasattr(item, "__dict__"):
                rows.append({k: v for k, v in vars(item).items() if not k.startswith("_")})
        return rows
    if hasattr(raw, "to_dict"):
        try:
            return list(raw.to_dict("records"))
        except Exception:
            try:
                data = raw.to_dict()
                if isinstance(data, list):
                    return [row for row in data if isinstance(row, dict)]
            except Exception:
                return []
    return []


def _row_symbol(row: dict) -> str:
    for key in ("symbol", "series", "series_id", "id", "ticker"):
        value = row.get(key)
        if value:
            return str(value).upper()
    return ""


def _row_timestamp(row: dict) -> str:
    for key in ("date", "timestamp", "datetime", "last_updated", "time"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _row_value(row: dict) -> float | None:
    for key in ("value", "close", "last", "price", "close_price"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _fetch_macro_pilot(obb: Any, provider: str) -> dict:
    symbols = ["DGS10", "DGS2", "FEDFUNDS", "UNRATE", "CPIAUCSL"]
    result = obb.economy.fred_series(symbol=symbols, provider=provider)
    rows = _normalize_rows(result)
    latest_by_symbol: dict[str, dict] = {}
    for row in rows:
        symbol = _row_symbol(row)
        if not symbol:
            continue
        latest_by_symbol[symbol] = row
    return {
        "provider": provider,
        "series": {
            symbol: {
                "value": _row_value(row),
                "timestamp": _row_timestamp(row),
            }
            for symbol, row in latest_by_symbol.items()
        },
    }


def _fred_graph_latest(series_id: str) -> dict:
    params = urlencode({"id": series_id})
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?{params}"
    with urlopen(Request(url, headers=_DEFAULT_HTTP_HEADERS), timeout=6) as response:
        rows = list(csv.DictReader(StringIO(response.read().decode("utf-8", "replace"))))
    for row in reversed(rows):
        value = str(row.get(series_id) or "").strip()
        if not value or value == ".":
            continue
        try:
            return {
                "value": float(value),
                "timestamp": str(row.get("DATE") or ""),
            }
        except (TypeError, ValueError):
            continue
    return {"value": None, "timestamp": ""}


def _fetch_macro_direct(provider: str) -> dict:
    series_ids = ("DGS10", "DGS2", "FEDFUNDS", "UNRATE", "CPIAUCSL")
    series = {}
    with ThreadPoolExecutor(max_workers=len(series_ids)) as executor:
        futures = {executor.submit(_fred_graph_latest, series_id): series_id for series_id in series_ids}
        for future in as_completed(futures):
            series_id = futures[future]
            try:
                row = future.result()
            except Exception:
                continue
            if row.get("value") is None and not row.get("timestamp"):
                continue
            series[series_id] = row
    return {
        "provider": "fred_graph_csv" if provider == "fred" else f"{provider}_direct",
        "series": series,
    }


def _yahoo_chart_quote(symbol: str) -> dict:
    params = urlencode(
        {
            "interval": "1d",
            "range": "7d",
            "includePrePost": "false",
            "events": "div,splits,capitalGains",
        }
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}"
    with urlopen(Request(url, headers=_DEFAULT_HTTP_HEADERS), timeout=10) as response:
        payload = response.read().decode("utf-8", "replace")
    data = json.loads(payload)
    result = ((data.get("chart") or {}).get("result") or [None])[0] or {}
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote_rows = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}
    closes = quote_rows.get("close") or []
    cleaned = [
        (ts, value)
        for ts, value in zip(timestamps, closes)
        if value not in (None, "")
    ]
    latest_ts = timestamps[-1] if timestamps else None
    latest_price = meta.get("regularMarketPrice")
    if latest_price in (None, "") and cleaned:
        latest_ts, latest_price = cleaned[-1]
    prev_close = meta.get("chartPreviousClose")
    if prev_close in (None, "", 0) and len(cleaned) >= 2:
        prev_close = cleaned[-2][1]
    change_pct = None
    if latest_price not in (None, "") and prev_close not in (None, "", 0):
        try:
            change_pct = ((float(latest_price) - float(prev_close)) / float(prev_close)) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            change_pct = None
    return {
        "symbol": symbol.upper(),
        "price": float(latest_price) if latest_price not in (None, "") else None,
        "change_pct": round(change_pct, 3) if change_pct is not None else None,
        "timestamp": str(latest_ts or ""),
    }


def _binance_symbol(symbol: str) -> str:
    base = str(symbol or "").upper().replace("-USD", "").replace("/", "").replace("-", "")
    return f"{base}USDT"


def _binance_quote(symbol: str) -> dict:
    trading_pair = _binance_symbol(symbol)
    params = urlencode({"symbol": trading_pair})
    url = f"https://api.binance.com/api/v3/ticker/24hr?{params}"
    with urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    last_price = payload.get("lastPrice")
    change_pct = payload.get("priceChangePercent")
    return {
        "symbol": symbol.upper(),
        "price": float(last_price) if last_price not in (None, "") else None,
        "change_pct": round(float(change_pct), 3) if change_pct not in (None, "") else None,
        "timestamp": str(payload.get("closeTime") or ""),
    }


def _coinbase_quote(symbol: str) -> dict:
    product = str(symbol or "").upper()
    url = f"https://api.exchange.coinbase.com/products/{product}/stats"
    with urlopen(Request(url, headers=_DEFAULT_HTTP_HEADERS), timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    last_price = payload.get("last")
    open_price = payload.get("open")
    change_pct = None
    if last_price not in (None, "") and open_price not in (None, "", "0", 0):
        change_pct = ((float(last_price) - float(open_price)) / float(open_price)) * 100.0
    return {
        "symbol": product,
        "price": float(last_price) if last_price not in (None, "") else None,
        "change_pct": round(change_pct, 3) if change_pct is not None else None,
        "timestamp": "",
    }


def _fetch_crypto_direct(provider: str, symbols: list[str]) -> dict:
    quotes: list[dict] = []
    source = "coinbase_stats"
    for symbol in symbols:
        try:
            quotes.append(_coinbase_quote(symbol))
            continue
        except Exception:
            pass
        try:
            quotes.append(_yahoo_chart_quote(symbol))
            source = "yahoo_chart"
        except Exception:
            continue
    quotes.sort(key=lambda row: row["symbol"])
    return {
        "provider": source if quotes else ("coinbase_stats" if provider == "yfinance" else f"{provider}_direct"),
        "quotes": quotes,
    }


def _fetch_crypto_pilot(obb: Any, provider: str, symbols: list[str]) -> dict:
    start_date = (date.today() - timedelta(days=7)).isoformat()
    result = obb.crypto.price.historical(symbol=symbols, provider=provider, start_date=start_date, interval="1d")
    rows = _normalize_rows(result)
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        symbol = _row_symbol(row)
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(row)

    snapshots: list[dict] = []
    for symbol, symbol_rows in grouped.items():
        latest = symbol_rows[-1]
        previous = symbol_rows[-2] if len(symbol_rows) > 1 else None
        latest_value = _row_value(latest)
        previous_value = _row_value(previous or {})
        change_pct = None
        if latest_value is not None and previous_value not in (None, 0):
            change_pct = ((latest_value - previous_value) / previous_value) * 100.0
        snapshots.append(
            {
                "symbol": symbol,
                "price": latest_value,
                "change_pct": round(change_pct, 3) if change_pct is not None else None,
                "timestamp": _row_timestamp(latest),
            }
        )

    snapshots.sort(key=lambda row: row["symbol"])
    return {"provider": provider, "quotes": snapshots}


def fetch_openbb_pilot_snapshot() -> dict:
    settings = openbb_pilot_settings()
    summary = provider_summary()
    selected_macro_provider = _first_configured_provider(settings["macro_provider_priority"])
    selected_crypto_provider = _first_configured_provider(settings["crypto_provider_priority"])

    payload = {
        "status": "disabled",
        "reason": "",
        "settings": settings,
        "provider_summary": summary,
        "selected_providers": {
            "macro": selected_macro_provider,
            "crypto": selected_crypto_provider,
        },
        "sources": {
            "macro": "",
            "crypto": "",
        },
        "macro": {},
        "crypto": {},
        "errors": [],
    }

    if not settings["enabled"]:
        payload["reason"] = "openbb_disabled"
        return payload

    obb = None
    payload["status"] = "ok"
    payload["reason"] = ""
    if not _openbb_import_ready():
        payload["status"] = "degraded"
        payload["reason"] = "openbb_not_installed"
        payload["errors"].append(
            {
                "surface": "openbb_import",
                "provider": "openbb",
                "message": "RuntimeError: openbb_not_installed",
            }
        )
    else:
        try:
            obb = _import_obb()
        except Exception as exc:
            payload["status"] = "degraded"
            payload["reason"] = "openbb_import_failed"
            payload["errors"].append(
                {
                    "surface": "openbb_import",
                    "provider": "openbb",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )

    try:
        if obb is None:
            raise RuntimeError(payload["reason"] or "openbb_import_failed")
        payload["macro"] = _fetch_macro_pilot(obb, selected_macro_provider)
        payload["sources"]["macro"] = f"openbb:{selected_macro_provider}"
    except Exception as exc:
        macro_fallback = {}
        try:
            macro_fallback = _fetch_macro_direct(selected_macro_provider)
        except Exception as fallback_exc:
            payload["errors"].append(
                {
                    "surface": "macro_fallback",
                    "provider": selected_macro_provider,
                    "message": f"{type(fallback_exc).__name__}: {fallback_exc}",
                }
            )
        if (macro_fallback.get("series") or {}):
            payload["macro"] = macro_fallback
            payload["sources"]["macro"] = f"direct:{macro_fallback.get('provider', selected_macro_provider)}"
            payload["status"] = "fallback_live"
        else:
            payload["status"] = "degraded"
        payload["errors"].append(
            {
                "surface": "macro",
                "provider": selected_macro_provider,
                "message": f"{type(exc).__name__}: {exc}",
            }
        )

    try:
        if obb is None:
            raise RuntimeError(payload["reason"] or "openbb_import_failed")
        payload["crypto"] = _fetch_crypto_pilot(
            obb,
            selected_crypto_provider,
            settings["crypto_symbols"],
        )
        payload["sources"]["crypto"] = f"openbb:{selected_crypto_provider}"
    except Exception as exc:
        crypto_fallback = {}
        try:
            crypto_fallback = _fetch_crypto_direct(selected_crypto_provider, settings["crypto_symbols"])
        except Exception as fallback_exc:
            payload["errors"].append(
                {
                    "surface": "crypto_fallback",
                    "provider": selected_crypto_provider,
                    "message": f"{type(fallback_exc).__name__}: {fallback_exc}",
                }
            )
        if crypto_fallback.get("quotes"):
            payload["crypto"] = crypto_fallback
            payload["sources"]["crypto"] = f"direct:{crypto_fallback.get('provider', selected_crypto_provider)}"
            if payload["status"] == "ok":
                payload["status"] = "fallback_live"
        else:
            payload["status"] = "degraded"
        payload["errors"].append(
            {
                "surface": "crypto",
                "provider": selected_crypto_provider,
                "message": f"{type(exc).__name__}: {exc}",
            }
        )

    has_live_payload = bool((payload.get("macro") or {}).get("series")) or bool((payload.get("crypto") or {}).get("quotes"))
    if payload["errors"]:
        payload["status"] = "fallback_live" if has_live_payload else "degraded"

    return payload
