"""
Regression test for build_sympathy_logger._fetch_price.

Locked after the 2026-04-16 audit that found: all 715 rows of sympathy_events.csv
had empty price_t0 because the logger's _fetch_price hit stooq.com directly, but
the droplet cannot reach stooq.com:443 (times out). The fix reads the shared
.stooq_daily_cache.json that the classifier already refreshes daily.

Run with: pytest /home/operator/.openclaw/workspace/tests/test_sympathy_price_fetch.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
LOGGER = WORKSPACE / "build_sympathy_logger.py"


def _load_module(tmp_cache_path: Path):
    spec = importlib.util.spec_from_file_location("build_sympathy_logger", LOGGER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_sympathy_logger"] = mod
    spec.loader.exec_module(mod)
    mod.STOOQ_CACHE_PATH = tmp_cache_path
    mod._stooq_cache = None
    return mod


def test_fetch_price_reads_dict_rows(tmp_path):
    cache = tmp_path / ".stooq_daily_cache.json"
    cache.write_text(json.dumps({
        "AAPL": {"ts": 1.0, "rows": [
            {"date": "2026-04-14", "close": 180.0},
            {"date": "2026-04-15", "close": 185.5},
        ]}
    }))
    mod = _load_module(cache)
    assert mod._fetch_price("AAPL") == 185.5
    # case insensitive
    assert mod._fetch_price("aapl") == 185.5


def test_fetch_price_reads_list_rows(tmp_path):
    cache = tmp_path / ".stooq_daily_cache.json"
    cache.write_text(json.dumps({
        "MSFT": {"ts": 1.0, "rows": [
            ["2026-04-14", 300, 305, 298, 302, 1_000_000],
            ["2026-04-15", 302, 307, 301, 306.25, 1_200_000],
        ]}
    }))
    mod = _load_module(cache)
    assert mod._fetch_price("MSFT") == 306.25


def test_fetch_price_missing_ticker_falls_back_or_returns_none(tmp_path, monkeypatch):
    cache = tmp_path / ".stooq_daily_cache.json"
    cache.write_text(json.dumps({"AAPL": {"ts": 1.0, "rows": []}}))
    mod = _load_module(cache)
    # Block network fallback so we see the None path.
    def _blocked(*a, **kw):
        raise RuntimeError("network blocked in test")
    monkeypatch.setattr(mod.urllib.request, "urlopen", _blocked)
    assert mod._fetch_price("NOTHERE") is None


def test_fetch_price_empty_cache_returns_none(tmp_path, monkeypatch):
    cache = tmp_path / ".stooq_daily_cache.json"
    cache.write_text("{}")
    mod = _load_module(cache)
    def _blocked(*a, **kw):
        raise RuntimeError("network blocked")
    monkeypatch.setattr(mod.urllib.request, "urlopen", _blocked)
    assert mod._fetch_price("X") is None
