# Catalyst Edge ML Module

Supervised-learning layer for catalyst pick selection. Lifts the track record from rule-based (44.5% +2%, 23.75% +5%, 5.1% avg run) toward target (65% +2%, 45% +5%, 10% avg run).

## Install

```bash
cd /home/operator/.openclaw/workspace/ml
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-ml.txt
```

## Pipeline

1. `python build_features.py` — produces `features.parquet` from outcome rows + joins.
2. `python train_catalyst_model.py` — walk-forward LightGBM, writes `models/hit_2pct.lgb`, `models/hit_5pct.lgb`, `training_report.json`.
3. `python calibrate_model.py` — isotonic calibration on last 60 days holdout.
4. `python predict_today.py` — scores today's picks, writes `sec_ml_ranked.csv`.
5. `python evaluate_ml.py` — nightly benchmark vs baseline → `ml_benchmark_log.csv`.

## Integration

Add to `run_daily_sec_catalyst.sh` after `classify_sec_catalysts.py`:

```bash
source /home/operator/.openclaw/workspace/ml/.venv/bin/activate
python /home/operator/.openclaw/workspace/ml/predict_today.py
deactivate
```

Newsletter builder reads `sec_ml_ranked.csv` when present; falls back to `combined_priority.csv` if ML absent.

## Gate

Every model version blocked by `BASELINE.md` targets. Walk-forward AUC must beat random. If worse than baseline on holdout, deploy aborts.
