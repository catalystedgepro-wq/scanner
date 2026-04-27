"""
Regression tests for rank_sec_catalysts scoring primitives.

Locks in the current math so a future edit to a weight or threshold trips
these tests. Part of the 2026-04-17 math audit requested by the user:
"For all our tables. we are sure that our math is correct?"

Run with: pytest tests/test_rank_sec_catalysts.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parent.parent
MODULE_PATH = WORKSPACE / "rank_sec_catalysts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("rank_sec_catalysts", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rank_sec_catalysts"] = mod
    spec.loader.exec_module(mod)
    return mod


rank = _load_module()


# ── form_score ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "form,expected",
    [
        ("8-K", 10),
        ("8-K/A", 10),
        ("6-K", 10),
        ("S-3", 8),
        ("S-3/A", 8),
        ("S-3ASR", 8),
        ("424B2", 6),
        ("424B5", 6),
        ("SC 13D", 7),
        ("SC 13G", 7),
        ("SC 13D/A", 7),
        ("NT 10-Q", 5),
        ("NT 10-K", 5),
        ("RW", 4),
        ("10-K", 1),
        ("10-Q", 1),
        # 2026-04-17 expansion.
        ("DEF 14A", 6),
        ("PRE 14A", 5),
        ("SC TO-T", 9),
        ("SC 14D9", 8),
        ("S-1", 5),
        ("S-1/A", 4),
        ("S-4", 8),
        ("", 1),
    ],
)
def test_form_score(form, expected):
    assert rank.form_score(form) == expected


def test_form_score_is_case_insensitive():
    assert rank.form_score("8-k") == rank.form_score("8-K") == 10
    assert rank.form_score("sc 13d") == 7


# ── recency_score ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "minutes,expected",
    [
        (0, 20),
        (60, 20),
        (61, 15),
        (180, 15),
        (181, 10),
        (360, 10),
        (361, 6),
        (720, 6),
        (721, 3),
        (10_000, 3),
    ],
)
def test_recency_score_tiers(minutes, expected):
    assert rank.recency_score(minutes) == expected


def test_recency_score_monotonic_non_increasing():
    xs = [0, 30, 60, 120, 180, 300, 360, 600, 720, 1440, 10_000]
    scores = [rank.recency_score(x) for x in xs]
    assert scores == sorted(scores, reverse=True), scores


# ── ticker_quality_penalty ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "ticker,expected",
    [
        ("AAPL", 0),
        ("SPY", 0),
        ("T", 0),
        ("BRK-A", 3),            # dash
        ("ABCDE", 0),             # 5 chars not ending WURP
        ("ABCDW", 4),             # 5 chars ending W (warrant)
        ("ABCDR", 4),             # rights
        ("ABCDP", 4),             # preferred
        ("ABCDU", 4),             # units
        ("ABCDEF", 2),            # len>5 (+2), ends F (no WURP match)
        ("ABCDEW", 6),            # len>5 (+2) + ends W (+4)
        ("BRK-AW", 9),            # dash +3, ends W +4, len>5 +2
    ],
)
def test_ticker_quality_penalty(ticker, expected):
    assert rank.ticker_quality_penalty(ticker) == expected


def test_ticker_quality_penalty_case_insensitive():
    assert rank.ticker_quality_penalty("abcdw") == rank.ticker_quality_penalty("ABCDW") == 4


# ── score_momentum ─────────────────────────────────────────────────────────────
def test_score_momentum_8k_fresh_clean_ticker():
    # 8-K catalyst boost 16 + recency 20 (<=60) - penalty 0 = 36
    assert rank.score_momentum("8-K", 30, "AAPL") == 36


def test_score_momentum_s3_old_warrant():
    # S-3 boost 12 + recency 3 (>720) - (penalty 4 // 2 = 2) = 13
    assert rank.score_momentum("S-3", 1500, "ABCDW") == 13


def test_score_momentum_unknown_form_penalty_halved():
    # Generic boost 2 + recency 20 - (penalty 2 // 2 = 1) = 21
    assert rank.score_momentum("10-Q", 15, "ABCDEF") == 21


def test_score_momentum_424b_midrange():
    # 424B boost 8 + recency 15 (<=180) - 0 = 23
    assert rank.score_momentum("424B5", 120, "MSFT") == 23


# ── score_quality ──────────────────────────────────────────────────────────────
def test_score_quality_8k_fresh_clean_ticker():
    # form_score(8-K)*4 = 40 + recency 20 + quality_bonus (clean len<=4: +6, 8-K: +4) - penalty 0 = 70
    assert rank.score_quality("8-K", 30, "AAPL") == 70


def test_score_quality_424b_penalized():
    # form_score(424B)*4 = 24 + recency 20 + bonus (len<=4 no dash: +6, 424B: -4) - penalty 0 = 46
    assert rank.score_quality("424B5", 30, "MSFT") == 46


def test_score_quality_dashed_ticker_loses_clean_bonus():
    # form_score(SC 13D)*4 = 28 + recency 20 + bonus (dash disqualifies +6, no 8-K bonus) - penalty 3 = 45
    assert rank.score_quality("SC 13D", 30, "BRK-A") == 45


def test_score_quality_warrant_far_past():
    # form_score(S-3)*4 = 32 + recency 3 + bonus 0 (len 5, not <=4) - penalty 4 = 31
    assert rank.score_quality("S-3", 10_000, "ABCDW") == 31


# ── Relative ordering: the property we actually care about ─────────────────────
def test_fresh_8k_beats_stale_8k_on_quality():
    fresh = rank.score_quality("8-K", 30, "AAPL")
    stale = rank.score_quality("8-K", 5000, "AAPL")
    assert fresh > stale


def test_clean_ticker_beats_warrant_on_quality_same_form():
    clean = rank.score_quality("8-K", 60, "AAPL")
    warrant = rank.score_quality("8-K", 60, "AAPLW")
    assert clean > warrant


def test_8k_beats_10q_on_quality_same_ticker():
    catalyst = rank.score_quality("8-K", 60, "AAPL")
    boilerplate = rank.score_quality("10-Q", 60, "AAPL")
    assert catalyst > boilerplate
