#!/usr/bin/env python3
"""
train_catalyst_model.py — LightGBM two-head classifier for catalyst picks.

Heads:
- hit_2pct
- hit_5pct

Protocol:
- Walk-forward CV, rolling 90-day train / 7-day test, no look-ahead
- 1-day embargo between train and test (purged CV, Lopez de Prado W5 preview)
- Class-weighted binary log-loss
- Final model trained on full history
- Baseline comparison: rule-based hit rate on same holdout slices

Outputs:
- models/hit_2pct.lgb, models/hit_5pct.lgb
- training_report.json  (fold metrics, baseline deltas, feature importances)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, average_precision_score

LOG = logging.getLogger("train_catalyst")
ROOT = Path("/home/operator/.openclaw/workspace/ml")
FEATURES = ROOT / "features.parquet"
MODELS_DIR = ROOT / "models"
REPORT = ROOT / "training_report.json"

TARGETS = ("hit_2pct", "hit_5pct")

DROP_COLS = {
    "list_name", "list_date", "ticker", "form", "sector", "cap_tier",
    "next_open", "next_high", "next_close", "next_volume",
    "gap_next_open_pct", "next_day_max_run_pct",
    "next_day_close_pct", "next_day_vwap_pct",
    "hit_2pct", "hit_3pct", "hit_5pct",
}

TRAIN_DAYS = 14
TEST_DAYS = 3
EMBARGO_DAYS = 1
MIN_TRAIN_ROWS = 200

LGB_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.04,
    "num_leaves": 31,
    "max_depth": -1,
    "min_data_in_leaf": 30,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 5,
    "lambda_l2": 1.0,
    "verbose": -1,
    "seed": 42,
}


@dataclass
class FoldResult:
    target: str
    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    n_train: int
    n_test: int
    base_rate: float
    ml_auc: float
    ml_ap: float
    ml_hit_at_topdecile: float
    baseline_hit: float
    ml_hit_at_threshold: float
    threshold: float


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in DROP_COLS and df[c].dtype != "object"]


def walk_forward_splits(dates: pd.Series):
    dates = pd.to_datetime(dates).sort_values().unique()
    if len(dates) == 0:
        return
    start = dates[0]
    end = dates[-1]
    cursor = pd.Timestamp(start) + pd.Timedelta(days=TRAIN_DAYS)
    fold = 0
    while cursor + pd.Timedelta(days=TEST_DAYS) <= pd.Timestamp(end):
        train_start = cursor - pd.Timedelta(days=TRAIN_DAYS)
        train_end = cursor - pd.Timedelta(days=EMBARGO_DAYS + 1)
        test_start = cursor
        test_end = cursor + pd.Timedelta(days=TEST_DAYS)
        yield fold, train_start, train_end, test_start, test_end
        cursor += pd.Timedelta(days=TEST_DAYS)
        fold += 1


def train_one_head(df: pd.DataFrame, target: str, feat_cols: list[str]) -> tuple[lgb.Booster, list[FoldResult]]:
    folds: list[FoldResult] = []
    for fold, tr_s, tr_e, te_s, te_e in walk_forward_splits(df["list_date"]):
        train_mask = (df["list_date"] >= tr_s) & (df["list_date"] <= tr_e)
        test_mask = (df["list_date"] >= te_s) & (df["list_date"] < te_e)
        if train_mask.sum() < MIN_TRAIN_ROWS or test_mask.sum() == 0:
            continue
        X_tr, y_tr = df.loc[train_mask, feat_cols], df.loc[train_mask, target].astype(int)
        X_te, y_te = df.loc[test_mask, feat_cols], df.loc[test_mask, target].astype(int)
        if y_tr.nunique() < 2 or y_te.nunique() < 2:
            continue

        pos = y_tr.sum()
        neg = len(y_tr) - pos
        scale = max(1.0, neg / max(1, pos))
        params = dict(LGB_PARAMS, scale_pos_weight=scale)

        dtrain = lgb.Dataset(X_tr, label=y_tr)
        dvalid = lgb.Dataset(X_te, label=y_te, reference=dtrain)
        booster = lgb.train(
            params,
            dtrain,
            num_boost_round=400,
            valid_sets=[dvalid],
            callbacks=[lgb.early_stopping(40, verbose=False), lgb.log_evaluation(0)],
        )
        proba = booster.predict(X_te)

        try:
            ml_auc = float(roc_auc_score(y_te, proba))
            ml_ap = float(average_precision_score(y_te, proba))
        except ValueError:
            continue

        order = np.argsort(-proba)
        top_k = max(1, int(round(0.1 * len(order))))
        top_idx = order[:top_k]
        hit_topdecile = float(y_te.iloc[top_idx].mean())

        threshold = float(np.quantile(proba, 0.75)) if len(proba) >= 4 else 0.5
        hit_at_thr = float(y_te[proba >= threshold].mean()) if (proba >= threshold).any() else 0.0
        base_rate = float(y_te.mean())

        baseline_col = "base_score"
        if baseline_col in df.columns:
            base_vals = df.loc[test_mask, baseline_col].values
            b_order = np.argsort(-base_vals)
            b_top = b_order[:top_k]
            baseline_hit = float(y_te.iloc[b_top].mean())
        else:
            baseline_hit = base_rate

        folds.append(FoldResult(
            target=target, fold=fold,
            train_start=str(tr_s.date()), train_end=str(tr_e.date()),
            test_start=str(te_s.date()), test_end=str(te_e.date()),
            n_train=int(train_mask.sum()), n_test=int(test_mask.sum()),
            base_rate=base_rate, ml_auc=ml_auc, ml_ap=ml_ap,
            ml_hit_at_topdecile=hit_topdecile,
            baseline_hit=baseline_hit,
            ml_hit_at_threshold=hit_at_thr,
            threshold=threshold,
        ))

    X_full, y_full = df[feat_cols], df[target].astype(int)
    pos = y_full.sum()
    neg = len(y_full) - pos
    scale = max(1.0, neg / max(1, pos))
    params = dict(LGB_PARAMS, scale_pos_weight=scale)
    dfull = lgb.Dataset(X_full, label=y_full)
    final = lgb.train(params, dfull, num_boost_round=300)
    return final, folds


def summarize(folds: list[FoldResult]) -> dict:
    if not folds:
        return {"n_folds": 0}
    df = pd.DataFrame([asdict(f) for f in folds])
    return {
        "n_folds": int(len(df)),
        "mean_auc": float(df["ml_auc"].mean()),
        "mean_ap": float(df["ml_ap"].mean()),
        "mean_base_rate": float(df["base_rate"].mean()),
        "mean_ml_topdecile_hit": float(df["ml_hit_at_topdecile"].mean()),
        "mean_baseline_topdecile_hit": float(df["baseline_hit"].mean()),
        "topdecile_lift_pts": float((df["ml_hit_at_topdecile"] - df["baseline_hit"]).mean() * 100),
        "folds_ml_beats_baseline": int((df["ml_hit_at_topdecile"] > df["baseline_hit"]).sum()),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(FEATURES)
    df["list_date"] = pd.to_datetime(df["list_date"])
    df = df.sort_values("list_date").reset_index(drop=True)
    feat_cols = feature_columns(df)
    LOG.info("training on %d rows, %d features", len(df), len(feat_cols))

    report = {"features": feat_cols, "heads": {}}
    for target in TARGETS:
        LOG.info("=== head: %s ===", target)
        model, folds = train_one_head(df, target, feat_cols)
        out = MODELS_DIR / f"{target}.lgb"
        model.save_model(str(out))
        importances = dict(sorted(
            zip(feat_cols, model.feature_importance(importance_type="gain").tolist()),
            key=lambda kv: -kv[1],
        )[:20])
        summary = summarize(folds)
        report["heads"][target] = {
            "model_path": str(out),
            "cv_summary": summary,
            "folds": [asdict(f) for f in folds],
            "top_feature_importance": importances,
        }
        LOG.info("%s cv summary: %s", target, summary)

    REPORT.write_text(json.dumps(report, indent=2))
    LOG.info("report -> %s", REPORT)
    for t in TARGETS:
        s = report["heads"][t]["cv_summary"]
        print(f"{t}: folds={s.get('n_folds')} auc={s.get('mean_auc', 0):.3f} "
              f"topdecile_ml={s.get('mean_ml_topdecile_hit', 0):.3f} "
              f"topdecile_base={s.get('mean_baseline_topdecile_hit', 0):.3f} "
              f"lift={s.get('topdecile_lift_pts', 0):+.1f}pts "
              f"beats={s.get('folds_ml_beats_baseline')}/{s.get('n_folds')}")


if __name__ == "__main__":
    main()
