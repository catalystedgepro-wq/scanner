"""
Regression test for build_heatmap_data polarity classification.

Locked after the 2026-04-16 audit that found: ZCAR tagged '-warrant' was being
counted as BULLISH because the old classifier ran a substring match over a
fixed NEG keyword list and ignored the explicit -/+ polarity prefix. The fix
trusts the sign prefix first, keyword list as fallback.

Run with: pytest /home/operator/.openclaw/workspace/tests/test_heatmap_classifier.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
GENERATOR = WORKSPACE / "generate_seo_site.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_seo_site", GENERATOR)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["generate_seo_site"] = mod
    spec.loader.exec_module(mod)
    return mod


def _row(ticker: str, tags: str, score: float = 10.0, form: str = "8-K") -> dict:
    return {
        "ticker": ticker,
        "form": form,
        "gapper_score": str(score),
        "tags": tags,
    }


def test_neg_prefix_is_bearish_even_when_keyword_not_in_neg_list():
    """ZCAR case: '-warrant' must be bearish. 'warrant' is not in NEG keyword list."""
    mod = _load_module()
    mod._sector_lookup["ZCAR"] = ["consumer"]
    result = mod.build_heatmap_data([_row("ZCAR", "-warrant", score=12)])
    consumer = next((s for s in result if s["name"] == "consumer"), None)
    assert consumer is not None, "consumer sector missing"
    assert consumer["bearish"] == 1, f"expected 1 bearish, got {consumer['bearish']}"
    assert consumer["bullish"] == 0


def test_pos_prefix_with_neg_body_keyword_is_neutral_tie():
    """Post-2026-04-17 audit: '+share repurchase amid offering window' has pos=1
    prefix AND a NEG keyword ('offering') in the body, which adds 1 to neg_count.
    Tied 1/1 → neutral, not bullish. This locks in the audited behavior."""
    mod = _load_module()
    mod._sector_lookup["TESTA"] = ["tech"]
    result = mod.build_heatmap_data([_row("TESTA", "+share repurchase amid offering window")])
    tech = next((s for s in result if s["name"] == "tech"), None)
    assert tech is not None
    assert tech["bullish"] == 0
    assert tech["bearish"] == 0
    assert tech["neutral"] == 1


def test_pos_prefix_with_clean_body_is_bullish():
    """'+share repurchase' with no NEG body keyword must stay bullish."""
    mod = _load_module()
    mod._sector_lookup["TESTA2"] = ["tech"]
    result = mod.build_heatmap_data([_row("TESTA2", "+share repurchase")])
    tech = next((s for s in result if s["name"] == "tech"), None)
    assert tech is not None
    assert tech["bullish"] == 1
    assert tech["bearish"] == 0


def test_keyword_fallback_when_no_polarity_prefix():
    """No +/- prefix → fall back to NEG keyword substring match."""
    mod = _load_module()
    mod._sector_lookup["TESTB"] = ["tech"]
    result = mod.build_heatmap_data([_row("TESTB", "going concern disclosed")])
    tech = next((s for s in result if s["name"] == "tech"), None)
    assert tech is not None
    assert tech["bearish"] == 1


def test_empty_tags_non_bearish_form_is_neutral():
    """Post-2026-04-17 audit: no tags + non-bearish form → neutral, NOT bullish.
    This was the fix for the 'every sector 0 bearish' artifact."""
    mod = _load_module()
    mod._sector_lookup["TESTC"] = ["tech"]
    result = mod.build_heatmap_data([_row("TESTC", "", form="8-K")])
    tech = next((s for s in result if s["name"] == "tech"), None)
    assert tech is not None
    assert tech["bullish"] == 0
    assert tech["bearish"] == 0
    assert tech["neutral"] == 1


def test_empty_tags_bearish_form_is_bearish():
    """No tags + bearish form type (S-3 offering) → bearish fallback."""
    mod = _load_module()
    mod._sector_lookup["TESTC2"] = ["tech"]
    result = mod.build_heatmap_data([_row("TESTC2", "", form="S-3")])
    tech = next((s for s in result if s["name"] == "tech"), None)
    assert tech is not None
    assert tech["bearish"] == 1


def test_sentiment_formula_matches_fill_pct():
    """sentiment = bullish_weight / (bullish_weight + bearish_weight).
    When all scores are equal this collapses to the count ratio, so 3 bullish +
    1 bearish at score 10 each still yields 0.75 — but the formula is now
    conviction-weighted under the hood."""
    mod = _load_module()
    mod._sector_lookup["T1"] = ["tech"]
    mod._sector_lookup["T2"] = ["tech"]
    mod._sector_lookup["T3"] = ["tech"]
    mod._sector_lookup["T4"] = ["tech"]
    # 3 bullish, 1 bearish, all score 10 → weight ratio = count ratio = 0.75
    result = mod.build_heatmap_data([
        _row("T1", "+merger"),
        _row("T2", "+results"),
        _row("T3", "+repurchase"),
        _row("T4", "-offering"),
    ])
    tech = next((s for s in result if s["name"] == "tech"), None)
    assert tech is not None
    assert tech["bullish"] == 3
    assert tech["bearish"] == 1
    assert tech["sentiment"] == 0.75
    assert tech["bullishWeight"] == 30.0
    assert tech["bearishWeight"] == 10.0


def test_score_weighted_polarity_flips_tied_counts():
    """1 bullish (score 2) vs 1 bearish (score 20) → counts tied but conviction
    clearly bearish. This is the case the 2026-04-17 audit was built to catch."""
    mod = _load_module()
    mod._sector_lookup["LOWB"] = ["industrials"]
    mod._sector_lookup["HIGHX"] = ["industrials"]
    result = mod.build_heatmap_data([
        _row("LOWB",  "+results",   score=2.0),
        _row("HIGHX", "-offering",  score=20.0),
    ])
    ind = next((s for s in result if s["name"] == "industrials"), None)
    assert ind is not None
    # Counts are tied 1:1 — preserved for display.
    assert ind["bullish"] == 1
    assert ind["bearish"] == 1
    # But conviction weight is 2 vs 20 → sentiment clearly bearish.
    assert ind["bullishWeight"] == 2.0
    assert ind["bearishWeight"] == 20.0
    # sentiment = 2 / (2 + 20) = 0.09 (rounded to 2 decimals)
    assert ind["sentiment"] == 0.09


def test_score_floor_keeps_zero_scored_filings_visible():
    """A zero-scored polar filing should still register on its side with weight
    1.0 so it doesn't silently vanish from the conviction calculation. Paired
    with a higher-scored companion so the sector clears the score<1 filter."""
    mod = _load_module()
    mod._sector_lookup["ZERO"]  = ["materials"]
    mod._sector_lookup["ANCHOR"] = ["materials"]
    result = mod.build_heatmap_data([
        _row("ZERO",   "-offering", score=0.0),   # floor kicks in → bearishWeight += 1.0
        _row("ANCHOR", "+merger",   score=5.0),   # ensures the sector survives the filter
    ])
    mat = next((s for s in result if s["name"] == "materials"), None)
    assert mat is not None
    assert mat["bearish"] == 1
    assert mat["bullish"] == 1
    assert mat["bearishWeight"] == 1.0  # floored from 0.0
    assert mat["bullishWeight"] == 5.0
