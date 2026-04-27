#!/usr/bin/env python3
"""build_xasset_macro.py — cross-asset macro regime detector.

Pulls live cross-asset signals via yfinance and tags each with a regime
classification + trade readthrough. This is the macro context layer that
sits above the equity scanners — when the curve inverts, USD strengthens,
or oil/gold collapses, equity flow rotates predictably.

Output: docs/data/xasset_macro.json
"""
from __future__ import annotations

import datetime as dt
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import yfinance as yf  # noqa: E402


def _find_root() -> Path:
    for cand in (Path("/opt/catalyst"),
                 Path("/home/operator/.openclaw/workspace"),
                 Path(__file__).resolve().parent):
        if (cand / "build_xasset_macro.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT = ROOT / "docs/data/xasset_macro.json"
OUT.parent.mkdir(parents=True, exist_ok=True)


def last_close(ticker: str) -> float | None:
    try:
        h = yf.Ticker(ticker).history(period="5d")
        if h.empty:
            return None
        return float(h["Close"].iloc[-1])
    except Exception:
        return None


def yield_curve_regime(spread: float | None) -> tuple[str, str]:
    if spread is None:
        return "unknown", "data unavailable"
    if spread < 0:
        return "inverted", ("10Y < 3M — recession indicator. "
                            "Historically: defensive sectors (utilities, staples, gold) outperform; "
                            "cyclicals (industrials, banks ex-large-cap) underperform.")
    if spread < 0.5:
        return "flat", "curve flat — late-cycle. Tilt toward quality, low-debt, high-FCF."
    return "steep", "curve steep — risk-on. Cyclicals + small-caps tend to lead."


def dxy_regime(dxy: float | None) -> tuple[str, str]:
    if dxy is None:
        return "unknown", "data unavailable"
    if dxy >= 106:
        return "very_strong", ("DXY >= 106 — emerging-market FX stress, "
                               "commodity headwind. Avoid EM equities, oil cyclicals.")
    if dxy >= 102:
        return "strong", "DXY >= 102 — moderate USD strength. Watch EM weakness."
    if dxy <= 98:
        return "weak", ("DXY <= 98 — commodity tailwind, EM tailwind. "
                        "Favor materials, gold miners, EM equities.")
    return "neutral", "DXY 98-102 — neutral. No strong FX-driven readthrough."


def oil_gold_regime(ratio: float | None) -> tuple[str, str]:
    if ratio is None:
        return "unknown", "data unavailable"
    if ratio < 12:
        return "recession_signal", ("Oil/Gold < 12 — historical recession marker. "
                                    "Risk-off rotation: utilities, healthcare, gold miners.")
    if ratio > 25:
        return "commodity_surge", ("Oil/Gold > 25 — commodity-driven inflation regime. "
                                   "Favor energy, materials; avoid duration-sensitive growth.")
    return "balanced", "Oil/Gold 12-25 — balanced macro. Standard equity factor exposure."


def vix_regime(vix: float | None) -> tuple[str, str]:
    if vix is None:
        return "unknown", "data unavailable"
    if vix >= 30:
        return "panic", ("VIX >= 30 — outright panic. Volatility crush trades, oversold "
                         "bounces, mean reversion windows.")
    if vix >= 25:
        return "elevated", "VIX 25-30 — elevated. Trim risk, raise stops."
    if vix <= 14:
        return "complacent", ("VIX <= 14 — complacency. Vol selling crowded; "
                              "risk of mean-reversion higher than implied.")
    return "normal", "VIX 14-25 — normal regime."


def crude_natgas_regime(ratio: float | None) -> tuple[str, str]:
    if ratio is None:
        return "unknown", "data unavailable"
    if ratio < 8:
        return "natgas_surge", "Crude/NatGas < 8 — natural gas relative strength."
    if ratio > 25:
        return "crude_surge", "Crude/NatGas > 25 — crude relative strength."
    return "balanced", "Crude/NatGas balanced."


def main() -> int:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    # Treasury yields are quoted x10 by yfinance (^TNX = 10Y, ^IRX = 3M, ^FVX = 5Y)
    tnx = last_close("^TNX")  # 10Y
    irx = last_close("^IRX")  # 3M
    fvx = last_close("^FVX")  # 5Y
    dxy = last_close("DX-Y.NYB")
    crude = last_close("CL=F")
    gold = last_close("GC=F")
    natgas = last_close("NG=F")
    vix = last_close("^VIX")
    sp500 = last_close("^GSPC")
    btc = last_close("BTC-USD")

    yc_spread = (tnx - irx) if (tnx is not None and irx is not None) else None
    oil_gold = (crude / gold) * 100 if (crude is not None and gold is not None and gold > 0) else None
    crude_ng = (crude / natgas) if (crude is not None and natgas is not None and natgas > 0) else None

    yc_label, yc_note = yield_curve_regime(yc_spread)
    dxy_label, dxy_note = dxy_regime(dxy)
    og_label, og_note = oil_gold_regime(oil_gold)
    vix_label, vix_note = vix_regime(vix)
    cng_label, cng_note = crude_natgas_regime(crude_ng)

    payload = {
        "generated_at": captured,
        "signals": [
            {
                "id": "yield_curve", "label": "10Y/3M Yield Curve",
                "value": round(yc_spread, 2) if yc_spread is not None else None,
                "value_unit": "bps spread",
                "components": {"tnx_10y": tnx, "irx_3m": irx, "fvx_5y": fvx},
                "regime": yc_label,
                "readthrough": yc_note,
            },
            {
                "id": "dxy", "label": "USD Strength (DXY)",
                "value": round(dxy, 2) if dxy is not None else None,
                "value_unit": "index",
                "regime": dxy_label,
                "readthrough": dxy_note,
            },
            {
                "id": "oil_gold", "label": "Oil/Gold Ratio",
                "value": round(oil_gold, 2) if oil_gold is not None else None,
                "value_unit": "ratio × 100",
                "components": {"crude_wti": crude, "gold": gold},
                "regime": og_label,
                "readthrough": og_note,
            },
            {
                "id": "vix", "label": "VIX (Implied Vol)",
                "value": round(vix, 2) if vix is not None else None,
                "value_unit": "%",
                "regime": vix_label,
                "readthrough": vix_note,
            },
            {
                "id": "crude_natgas", "label": "Crude/NatGas",
                "value": round(crude_ng, 2) if crude_ng is not None else None,
                "value_unit": "ratio",
                "components": {"crude": crude, "natgas": natgas},
                "regime": cng_label,
                "readthrough": cng_note,
            },
            {
                "id": "sp500", "label": "S&P 500",
                "value": round(sp500, 2) if sp500 is not None else None,
                "value_unit": "index",
                "regime": "—", "readthrough": "context anchor",
            },
            {
                "id": "btc", "label": "Bitcoin",
                "value": round(btc, 0) if btc is not None else None,
                "value_unit": "USD",
                "regime": "—", "readthrough": "risk-asset proxy",
            },
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2))

    # Concise console summary
    print(f"xasset_macro: yc={yc_spread} ({yc_label}) "
          f"| dxy={dxy} ({dxy_label}) "
          f"| oil_gold={oil_gold and round(oil_gold,2)} ({og_label}) "
          f"| vix={vix} ({vix_label}) "
          f"| crude/ng={crude_ng and round(crude_ng,2)} ({cng_label})")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
