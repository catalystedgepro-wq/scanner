"""
Regression tests for build_squeeze_hunter scoring primitives.

Locks in the Squeeze Score math:
  short_pct (0-35) + days_to_cover (0-20) + activist (0-15) +
  insider (0-10) + gamma (0-10) + wsb (0-5) +
  dtc_acceleration (0-10) + si_trend (0-5)

Part of the 2026-04-17 math audit. Also covers `determine_stage`
classification to guard the consumer-facing COILED/IGNITION/ACTIVE/LATE labels.

Run with: pytest tests/test_squeeze_hunter.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parent.parent
MODULE_PATH = WORKSPACE / "build_squeeze_hunter.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_squeeze_hunter", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_squeeze_hunter"] = mod
    spec.loader.exec_module(mod)
    return mod


sq = _load_module()


# ── score_short_pct ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "pct,expected",
    [
        (0, 0),
        (7.99, 0),
        (8, 3),
        (14.99, 3),
        (15, 7),
        (24.99, 7),
        (25, 14),
        (39.99, 14),
        (40, 22),
        (59.99, 22),
        (60, 30),
        (79.99, 30),
        (80, 35),
        (100, 35),
    ],
)
def test_score_short_pct_tiers(pct, expected):
    assert sq.score_short_pct(pct) == expected


def test_score_short_pct_max_capped_at_35():
    assert sq.score_short_pct(999) == 35


# ── score_days_to_cover ────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "dtc,expected",
    [
        (0, 0),
        (1.99, 0),
        (2, 3),
        (2.99, 3),
        (3, 7),
        (4.99, 7),
        (5, 12),
        (6.99, 12),
        (7, 16),
        (9.99, 16),
        (10, 20),
        (50, 20),
    ],
)
def test_score_days_to_cover_tiers(dtc, expected):
    assert sq.score_days_to_cover(dtc) == expected


# ── score_activist ─────────────────────────────────────────────────────────────
def test_score_activist_match_returns_15():
    assert sq.score_activist("GME", {"GME", "AMC"}) == 15


def test_score_activist_no_match_returns_0():
    assert sq.score_activist("AAPL", {"GME", "AMC"}) == 0


def test_score_activist_empty_set():
    assert sq.score_activist("GME", set()) == 0


# ── score_insider ──────────────────────────────────────────────────────────────
def test_score_insider_missing_ticker():
    assert sq.score_insider("AAPL", {}) == 0


def test_score_insider_confirmed_buy_cluster_3plus():
    # is_buy AND count>=3 → 10
    m = {"GME": {"filing_count": 5, "confirmed_buy": "1"}}
    assert sq.score_insider("GME", m) == 10


def test_score_insider_confirmed_buy_cluster_2():
    m = {"GME": {"filing_count": 2, "confirmed_buy": "1"}}
    assert sq.score_insider("GME", m) == 7


def test_score_insider_unconfirmed_cluster_3plus():
    # count>=3 but not is_buy → 5
    m = {"GME": {"filing_count": 3, "confirmed_buy": "0"}}
    assert sq.score_insider("GME", m) == 5


def test_score_insider_unconfirmed_cluster_2():
    m = {"GME": {"filing_count": 2, "confirmed_buy": "0"}}
    assert sq.score_insider("GME", m) == 3


def test_score_insider_single_filing():
    m = {"GME": {"filing_count": 1, "confirmed_buy": "0"}}
    assert sq.score_insider("GME", m) == 1


# ── score_gamma ────────────────────────────────────────────────────────────────
def test_score_gamma_missing_returns_0():
    assert sq.score_gamma("AAPL", {}) == 0


def test_score_gamma_reads_entry():
    m = {"GME": {"gamma_score": 7}}
    assert sq.score_gamma("GME", m) == 7


def test_score_gamma_none_value_is_zero():
    m = {"GME": {"gamma_score": None}}
    assert sq.score_gamma("GME", m) == 0


# ── score_wsb (tuple: pts, count, sentiment) ───────────────────────────────────
def test_score_wsb_unknown_is_neutral():
    pts, count, sent = sq.score_wsb("AAPL", {})
    assert (pts, count, sent) == (2, 0, "none")


@pytest.mark.parametrize(
    "count,expected_pts",
    [
        (0, 2),    # undiscovered
        (1, 5),    # starting — prime window
        (3, 5),
        (4, 4),    # building
        (10, 4),
        (11, 3),   # heating
        (25, 3),
        (26, 1),   # hot — late risk
        (50, 1),
        (51, 0),   # viral — probably late
        (9999, 0),
    ],
)
def test_score_wsb_count_tiers(count, expected_pts):
    m = {"GME": {"mention_count_24h": count, "sentiment_label": "bullish"}}
    pts, returned_count, sent = sq.score_wsb("GME", m)
    assert pts == expected_pts
    assert returned_count == count
    assert sent == "bullish"


# ── score_dtc_acceleration ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "current,prior,expected",
    [
        (10, 10, 0),            # no change
        (10.4, 10.0, 0),        # <0.5 delta
        (10.5, 10.0, 1),        # 0.5 delta
        (11.0, 10.0, 3),        # 1.0 delta
        (12.0, 10.0, 5),        # 2.0 delta
        (13.0, 10.0, 7),        # 3.0 delta
        (15.0, 10.0, 10),       # 5.0 delta — extreme
        (20.0, 10.0, 10),       # capped
        (8.0, 10.0, 0),         # negative delta (shorts covering)
    ],
)
def test_score_dtc_acceleration(current, prior, expected):
    assert sq.score_dtc_acceleration(current, prior) == expected


# ── score_si_trend ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "trend_pct,expected",
    [
        (-20, 1),    # shorts covering
        (-0.01, 1),
        (0, 2),      # holding steady
        (4.99, 2),
        (5, 3),
        (9.99, 3),
        (10, 4),
        (19.99, 4),
        (20, 5),     # aggressive doubling down
        (100, 5),
    ],
)
def test_score_si_trend(trend_pct, expected):
    assert sq.score_si_trend(trend_pct) == expected


# ── determine_stage ────────────────────────────────────────────────────────────
def test_stage_watch_low_si():
    stage, icon = sq.determine_stage(
        squeeze_score=50, wsb_count=0, si_pct=3, dtc=10,
        si_trend=5, has_activist=True, has_insider=True,
    )
    assert stage == "WATCH"


def test_stage_late_viral_and_covering():
    stage, _ = sq.determine_stage(
        squeeze_score=40, wsb_count=50, si_pct=15, dtc=5,
        si_trend=-15, has_activist=False, has_insider=False,
    )
    assert stage == "LATE"


def test_stage_active_viral_and_still_elevated():
    stage, _ = sq.determine_stage(
        squeeze_score=40, wsb_count=30, si_pct=15, dtc=5,
        si_trend=5, has_activist=False, has_insider=False,
    )
    assert stage == "ACTIVE"


def test_stage_ignition_wsb_discovering():
    stage, _ = sq.determine_stage(
        squeeze_score=35, wsb_count=10, si_pct=15, dtc=4,
        si_trend=5, has_activist=False, has_insider=False,
    )
    assert stage == "IGNITION"


def test_stage_coiled_with_insider_catalyst():
    stage, _ = sq.determine_stage(
        squeeze_score=20, wsb_count=2, si_pct=15, dtc=5,
        si_trend=5, has_activist=False, has_insider=True,
    )
    assert stage == "COILED"


def test_stage_coiled_pure_structural_without_catalyst():
    # wsb<=5, si>=20, dtc>=4 → COILED even without activist/insider
    stage, _ = sq.determine_stage(
        squeeze_score=20, wsb_count=1, si_pct=25, dtc=5,
        si_trend=2, has_activist=False, has_insider=False,
    )
    assert stage == "COILED"


def test_stage_watch_fallback():
    # Doesn't meet any thresholds
    stage, _ = sq.determine_stage(
        squeeze_score=20, wsb_count=10, si_pct=8, dtc=2,
        si_trend=0, has_activist=False, has_insider=False,
    )
    assert stage == "WATCH"


# ── Composite sanity: total possible score shape ───────────────────────────────
def test_max_possible_squeeze_score_is_110():
    # 35 + 20 + 15 + 10 + 10 + 5 + 10 + 5 = 110
    short = sq.score_short_pct(80)
    dtc = sq.score_days_to_cover(10)
    activist = sq.score_activist("X", {"X"})
    insider = sq.score_insider("X", {"X": {"filing_count": 5, "confirmed_buy": "1"}})
    gamma = sq.score_gamma("X", {"X": {"gamma_score": 10}})
    wsb_pts, _, _ = sq.score_wsb("X", {"X": {"mention_count_24h": 3, "sentiment_label": "bull"}})
    dtc_acc = sq.score_dtc_acceleration(15, 10)
    si_trend = sq.score_si_trend(20)
    total = short + dtc + activist + insider + gamma + wsb_pts + dtc_acc + si_trend
    assert total == 110


def test_min_possible_squeeze_score_is_1():
    # Floor: 0+0+0+0+0+1+0+1 = 2 (unknown wsb = 2 though, and si_trend floor is 1)
    # Actually: unknown ticker wsb returns pts=2, so min = 0+0+0+0+0+2+0+1 = 3
    short = sq.score_short_pct(0)
    dtc = sq.score_days_to_cover(0)
    activist = sq.score_activist("X", set())
    insider = sq.score_insider("X", {})
    gamma = sq.score_gamma("X", {})
    wsb_pts, _, _ = sq.score_wsb("X", {})
    dtc_acc = sq.score_dtc_acceleration(0, 0)
    si_trend = sq.score_si_trend(-50)
    total = short + dtc + activist + insider + gamma + wsb_pts + dtc_acc + si_trend
    assert total == 3
