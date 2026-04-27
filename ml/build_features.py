#!/usr/bin/env python3
"""
build_features.py — Construct feature matrix from SEC outcome rows + enrichment CSVs.

Consumes:
- /home/operator/.openclaw/workspace/sec_outcome_rows.csv
- /home/operator/.openclaw/workspace/combined_priority.csv (news momentum)
- /home/operator/.openclaw/workspace/entity_master.csv (sector, cap_tier)
- /home/operator/.openclaw/workspace/bloomberg_headlines.csv (headline count / polarity)

Emits: ml/features.parquet with one row per (ticker, list_date).

Targets:
- hit_2pct, hit_5pct (binary)
- next_day_max_run_pct (regression head, future v2)
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

LOG = logging.getLogger("build_features")
ROOT = Path("/home/operator/.openclaw/workspace")
OUT = ROOT / "ml" / "features.parquet"

OUTCOME_FILE = ROOT / "sec_outcome_rows.csv"
COMBINED_FILE = ROOT / "combined_priority.csv"
ENTITY_FILE = ROOT / "entity_master.csv"
NEWS_FILE = ROOT / "bloomberg_headlines.csv"

SEVERE_RISK_TERMS = (
    "offering",
    "private placement",
    "default",
    "bankruptcy",
    "delist",
    "going concern",
    "dilution",
)


def load_outcomes() -> pd.DataFrame:
    df = pd.read_csv(OUTCOME_FILE, parse_dates=["list_date"])
    df["filing_day_close"] = pd.to_numeric(df["filing_day_close"], errors="coerce")
    for col in ("hit_2pct", "hit_3pct", "hit_5pct"):
        df[col] = df[col].astype(int)
    return df


def load_entities() -> pd.DataFrame:
    if not ENTITY_FILE.exists():
        return pd.DataFrame(columns=["ticker", "sector", "cap_tier"])
    df = pd.read_csv(ENTITY_FILE)
    keep = [c for c in ("ticker", "sector", "cap_tier", "industry") if c in df.columns]
    return df[keep].drop_duplicates("ticker")


def load_news_features() -> pd.DataFrame:
    if not NEWS_FILE.exists():
        return pd.DataFrame(columns=["ticker", "news_count_24h", "news_neg_density"])
    df = pd.read_csv(NEWS_FILE)
    if "ticker" not in df.columns or "headline" not in df.columns:
        return pd.DataFrame(columns=["ticker", "news_count_24h", "news_neg_density"])
    df["headline"] = df["headline"].fillna("").str.lower()
    df["is_negative"] = df["headline"].apply(
        lambda h: any(term in h for term in SEVERE_RISK_TERMS)
    )
    agg = df.groupby("ticker").agg(
        news_count_24h=("headline", "count"),
        news_neg_density=("is_negative", "mean"),
    ).reset_index()
    return agg


def add_form_features(df: pd.DataFrame) -> pd.DataFrame:
    top_forms = df["form"].value_counts().head(12).index.tolist()
    for form in top_forms:
        col = f"form_{form.replace('/', '_').replace('-', '_')}"
        df[col] = (df["form"] == form).astype(int)
    return df


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    df["list_date"] = pd.to_datetime(df["list_date"])
    df["weekday"] = df["list_date"].dt.weekday.astype(int)
    df["month"] = df["list_date"].dt.month.astype(int)
    df["is_monday"] = (df["weekday"] == 0).astype(int)
    df["is_friday"] = (df["weekday"] == 4).astype(int)
    return df


def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    df["log_close"] = np.log(df["filing_day_close"].clip(lower=0.5))
    df["penny_flag"] = (df["filing_day_close"] < 5.0).astype(int)
    df["midcap_flag"] = ((df["filing_day_close"] >= 5.0) & (df["filing_day_close"] < 50.0)).astype(int)
    df["largecap_flag"] = (df["filing_day_close"] >= 50.0).astype(int)
    return df


def build(save: bool = True) -> pd.DataFrame:
    df = load_outcomes()
    entities = load_entities()
    news = load_news_features()

    df = df.merge(entities, on="ticker", how="left")
    df = df.merge(news, on="ticker", how="left")
    df["news_count_24h"] = df["news_count_24h"].fillna(0)
    df["news_neg_density"] = df["news_neg_density"].fillna(0)

    df = add_form_features(df)
    df = add_temporal_features(df)
    df = add_price_features(df)

    if "sector" in df.columns:
        df["sector"] = df["sector"].fillna("unknown")
        sector_dummies = pd.get_dummies(df["sector"], prefix="sector", dtype=int)
        df = pd.concat([df, sector_dummies], axis=1)

    if "cap_tier" in df.columns:
        df["cap_tier"] = df["cap_tier"].fillna("unknown")
        cap_dummies = pd.get_dummies(df["cap_tier"], prefix="cap", dtype=int)
        df = pd.concat([df, cap_dummies], axis=1)

    df = df.sort_values(["list_date", "ticker"]).reset_index(drop=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if save:
        df.to_parquet(OUT, index=False)
        LOG.info("wrote %d rows, %d cols -> %s", len(df), df.shape[1], OUT)
    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    df = build(save=not args.dry_run)
    print(f"Features built: {len(df)} rows × {df.shape[1]} cols")
    print(f"Target balance: hit_2pct={df['hit_2pct'].mean():.3f} hit_5pct={df['hit_5pct'].mean():.3f}")


if __name__ == "__main__":
    main()
