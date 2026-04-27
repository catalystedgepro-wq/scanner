#!/usr/bin/env python3
"""Canonical market-data provider contract for Cerebro.

This module centralizes:
  * Which providers Cerebro knows about
  * Which env vars authenticate each provider
  * How OpenBB should inherit provider credentials/default priorities

The goal is to keep provider logic out of scattered feature files.
"""
from __future__ import annotations

import os
from pathlib import Path


def _clean_env(name: str) -> str:
    return str(os.environ.get(name, "") or "").strip()


def _first_env(*names: str) -> str:
    for name in names:
        value = _clean_env(name)
        if value:
            return value
    return ""


def _env_flag(name: str, default: bool = False) -> bool:
    value = _clean_env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = _clean_env(name)
    if not value:
        return default
    try:
        return max(0.1, float(value))
    except (TypeError, ValueError):
        return default


def _priority_list(name: str, default: list[str]) -> list[str]:
    raw = _clean_env(name)
    if not raw:
        return list(default)
    items = [item.strip().lower() for item in raw.split(",")]
    unique: list[str] = []
    for item in items:
        if item and item not in unique:
            unique.append(item)
    return unique or list(default)


_PROVIDER_SPECS: list[dict] = [
    {
        "id": "openbb",
        "label": "OpenBB",
        "category": "unification",
        "keyless": True,
        "env_vars": ("OPENBB_ENABLED",),
        "auth_method": "feature_flag",
        "openbb_credentials": (),
    },
    {
        "id": "yfinance",
        "label": "Yahoo Finance / yfinance",
        "category": "keyless_fallback",
        "keyless": True,
        "env_vars": (),
        "auth_method": "none",
        "openbb_credentials": (),
    },
    {
        "id": "fred",
        "label": "FRED",
        "category": "macro",
        "keyless": True,
        "env_vars": ("FRED_API_KEY",),
        "auth_method": "optional_api_key",
        "openbb_credentials": (("fred_api_key", ("FRED_API_KEY",)),),
    },
    {
        "id": "fmp",
        "label": "Financial Modeling Prep",
        "category": "keyed",
        "keyless": False,
        "env_vars": ("FMP_API_KEY",),
        "auth_method": "api_key",
        "openbb_credentials": (("fmp_api_key", ("FMP_API_KEY",)),),
    },
    {
        "id": "polygon",
        "label": "Polygon",
        "category": "keyed",
        "keyless": False,
        "env_vars": ("POLYGON_API_KEY",),
        "auth_method": "api_key",
        "openbb_credentials": (("polygon_api_key", ("POLYGON_API_KEY",)),),
    },
    {
        "id": "finnhub",
        "label": "Finnhub",
        "category": "keyed",
        "keyless": False,
        "env_vars": ("FINNHUB_API_KEY",),
        "auth_method": "api_key",
        "openbb_credentials": (("finnhub_api_key", ("FINNHUB_API_KEY",)),),
    },
    {
        "id": "alpaca",
        "label": "Alpaca",
        "category": "keyed",
        "keyless": False,
        "env_vars": ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
        "auth_method": "key_and_secret",
        "openbb_credentials": (
            ("alpaca_api_key", ("ALPACA_API_KEY",)),
            ("alpaca_secret_key", ("ALPACA_SECRET_KEY",)),
        ),
    },
    {
        "id": "tradier",
        "label": "Tradier",
        "category": "keyed",
        "keyless": False,
        "env_vars": ("TRADIER_TOKEN",),
        "auth_method": "token",
        "openbb_credentials": (
            ("tradier_api_key", ("TRADIER_TOKEN", "TRADIER_API_KEY")),
            ("tradier_account_type", ("TRADIER_ACCOUNT_TYPE",)),
        ),
    },
    {
        "id": "tradingeconomics",
        "label": "Trading Economics",
        "category": "macro",
        "keyless": False,
        "env_vars": ("TRADINGECONOMICS_API_KEY",),
        "auth_method": "api_key",
        "openbb_credentials": (
            ("tradingeconomics_api_key", ("TRADINGECONOMICS_API_KEY", "TRADING_ECONOMICS_API_KEY")),
        ),
    },
    {
        "id": "nasdaq",
        "label": "Nasdaq Data Link",
        "category": "keyed",
        "keyless": False,
        "env_vars": ("NASDAQ_DATA_LINK_API_KEY",),
        "auth_method": "api_key",
        "openbb_credentials": (("nasdaq_api_key", ("NASDAQ_DATA_LINK_API_KEY", "NASDAQ_API_KEY")),),
    },
    {
        "id": "alpha_vantage",
        "label": "Alpha Vantage",
        "category": "keyed",
        "keyless": False,
        "env_vars": ("ALPHA_VANTAGE_API_KEY",),
        "auth_method": "api_key",
        "openbb_credentials": (("alpha_vantage_api_key", ("ALPHA_VANTAGE_API_KEY",)),),
    },
    {
        "id": "coinpaprika",
        "label": "CoinPaprika",
        "category": "crypto_keyless",
        "keyless": True,
        "env_vars": (),
        "auth_method": "none",
        "openbb_credentials": (),
    },
    {
        "id": "dexpaprika",
        "label": "DexPaprika",
        "category": "crypto_keyless",
        "keyless": True,
        "env_vars": (),
        "auth_method": "none",
        "openbb_credentials": (),
    },
    {
        "id": "binance",
        "label": "Binance Public",
        "category": "crypto_keyless",
        "keyless": True,
        "env_vars": (),
        "auth_method": "none",
        "openbb_credentials": (),
    },
    {
        "id": "coinbase",
        "label": "Coinbase Public",
        "category": "crypto_keyless",
        "keyless": True,
        "env_vars": (),
        "auth_method": "none",
        "openbb_credentials": (),
    },
]


def provider_contract() -> list[dict]:
    rows: list[dict] = []
    for spec in _PROVIDER_SPECS:
        env_vars = list(spec.get("env_vars", ()))
        present = [name for name in env_vars if _clean_env(name)]
        missing = [name for name in env_vars if not _clean_env(name)]
        if spec.get("auth_method") == "feature_flag":
            configured = _env_flag(env_vars[0], False) if env_vars else False
            live_enabled = configured
        else:
            configured = bool(spec.get("keyless")) or not missing
            live_enabled = configured
        rows.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "category": spec["category"],
                "auth_method": spec["auth_method"],
                "keyless": bool(spec.get("keyless")),
                "configured": configured,
                "live_enabled": live_enabled,
                "env_vars": env_vars,
                "present_env_vars": present,
                "missing_env_vars": missing,
            }
        )
    return rows


def provider_summary() -> dict:
    rows = provider_contract()
    configured = [row["id"] for row in rows if row["configured"]]
    live_enabled = [row["id"] for row in rows if row.get("live_enabled")]
    keyless = [row["id"] for row in rows if row["keyless"]]
    gated = [
        row["id"]
        for row in rows
        if row["auth_method"] == "feature_flag" and not row.get("live_enabled")
    ]
    return {
        "total": len(rows),
        "configured": len(configured),
        "configured_ids": configured,
        "live_enabled": len(live_enabled),
        "live_enabled_ids": live_enabled,
        "keyless_ids": keyless,
        "gated_ids": gated,
        "openbb_enabled": openbb_pilot_settings()["enabled"],
    }


def build_openbb_credentials() -> dict:
    credentials: dict[str, str] = {}
    for spec in _PROVIDER_SPECS:
        for target_key, aliases in spec.get("openbb_credentials", ()):
            value = _first_env(*aliases)
            if value:
                credentials[target_key] = value
    return credentials


def openbb_pilot_settings() -> dict:
    macro_priority = _priority_list(
        "OPENBB_MACRO_PROVIDER_PRIORITY",
        ["fred", "tradingeconomics", "fmp"],
    )
    crypto_priority = _priority_list(
        "OPENBB_CRYPTO_PROVIDER_PRIORITY",
        ["yfinance", "fmp", "polygon", "coinpaprika"],
    )
    settings_dir = Path(_first_env("OPENBB_SETTINGS_DIR") or "~/.openbb_platform").expanduser()
    return {
        "enabled": _env_flag("OPENBB_ENABLED", False),
        "settings_dir": str(settings_dir),
        "timeout_seconds": _env_float("OPENBB_TIMEOUT_SECONDS", 12.0),
        "macro_provider_priority": macro_priority,
        "crypto_provider_priority": crypto_priority,
        "crypto_symbols": _priority_list(
            "OPENBB_CRYPTO_SYMBOLS",
            ["BTC-USD", "ETH-USD", "SOL-USD"],
        ),
    }


def build_openbb_user_settings() -> dict:
    settings = openbb_pilot_settings()
    credentials = build_openbb_credentials()
    macro_priority = settings["macro_provider_priority"]
    crypto_priority = settings["crypto_provider_priority"]

    command_defaults = {
        "economy.fred_series": {"provider": macro_priority},
        "/economy/fred_series": {"provider": macro_priority},
        "economy.calendar": {"provider": macro_priority},
        "/economy/calendar": {"provider": macro_priority},
        "crypto.price.historical": {"provider": crypto_priority},
        "/crypto/price/historical": {"provider": crypto_priority},
        "crypto.price.quote": {"provider": crypto_priority},
        "/crypto/price/quote": {"provider": crypto_priority},
    }

    return {
        "credentials": credentials,
        "preferences": {
            "output_type": "OBBject",
            "metadata": True,
        },
        "defaults": {
            "commands": command_defaults,
        },
    }
