#!/usr/bin/env python3
"""Rank SEC catalyst tickers for first-look priority."""

from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).parent
INPUT = ROOT / "sec_catalyst_latest.csv"
OUT_CSV = ROOT / "sec_catalyst_ranked.csv"
OUT_TXT = ROOT / "sec_catalyst_priority_tickers.txt"
OUT_MOMO_CSV = ROOT / "sec_catalyst_ranked_momentum.csv"
OUT_MOMO_TXT = ROOT / "sec_catalyst_priority_momentum.txt"
OUT_QUAL_CSV = ROOT / "sec_catalyst_ranked_quality.csv"
OUT_QUAL_TXT = ROOT / "sec_catalyst_priority_quality.txt"


def form_score(form: str) -> int:
    f = form.upper()
    # Going-private & issuer-tender — highest explosive signal (~+40% moves).
    if f.startswith("SC 13E3"):
        return 10
    if f.startswith("SC TO-I"):
        return 10
    if f.startswith("8-K/A"):
        return 10  # amendments often carry restatement / new material disclosures
    if f.startswith("8-K") or f.startswith("6-K"):
        return 10
    # Tender offers: direct buyout mechanics, highest-signal catalyst.
    if f.startswith("SC TO-T"):
        return 9
    # Delisting / deregistration — terminal events, score high for tracking.
    if f.startswith("25-NSE") or f.startswith("25 "):
        return 9
    if f == "25":
        return 9
    if f.startswith("15-12"):
        return 8
    if f.startswith("SC 14D9"):
        return 8
    # M&A registration — definitive merger docs.
    if f.startswith("S-4") or f.startswith("F-4"):
        return 8
    if f.startswith("S-3") or f.startswith("F-3"):
        return 8
    # Activist campaigns.
    if f.startswith("DEFA14A") or f.startswith("DFAN14A"):
        return 8
    if f.startswith("SC 13D/A"):
        return 8
    if f.startswith("SC 13D") or f.startswith("SC 13G"):
        return 7
    # Definitive proxy (includes M&A votes).
    if f.startswith("DEF 14A"):
        return 6
    if f.startswith("424B"):
        return 6
    # IPO registration. Amendments are weaker than initial.
    if f.startswith("S-1/A") or f.startswith("F-1"):
        return 5
    if f.startswith("S-1"):
        return 5
    if f.startswith("PREC14A"):
        return 6  # contested preliminary proxy — activist
    if f.startswith("PRE 14A"):
        return 5
    if f.startswith("NT 10-Q") or f.startswith("NT 10-K"):
        return 5
    # Periodic reports: scheduled filings; most are not catalysts, but
    # going-concern / material-weakness language in a 10-K moves small caps.
    # Weighted below 8-K (10) and below shelf/offering (6–8).
    if f.startswith("10-K"):
        return 3
    if f.startswith("10-Q"):
        return 2
    if f.startswith("RW"):
        return 4
    return 1


def recency_score(recency_min: int) -> int:
    if recency_min <= 60:
        return 20
    if recency_min <= 180:
        return 15
    if recency_min <= 360:
        return 10
    if recency_min <= 720:
        return 6
    return 3


def ticker_quality_penalty(ticker: str) -> int:
    t = ticker.upper()
    penalty = 0
    # Heuristic de-prioritization for less tradable suffix patterns.
    if "-" in t:
        penalty += 3
    if len(t) >= 5 and re.search(r"[WURP]$", t):
        penalty += 4
    if len(t) > 5:
        penalty += 2
    return penalty


def score_momentum(form: str, recency_min: int, ticker: str) -> int:
    # Momentum prefers fast catalysts and tolerates odd tickers more.
    f = form.upper()
    catalyst_boost = 0
    if f.startswith("8-K") or f.startswith("6-K"):
        catalyst_boost = 16
    elif f.startswith("SC TO-T"):
        catalyst_boost = 14
    elif f.startswith("SC 14D9") or f.startswith("S-4"):
        catalyst_boost = 12
    elif f.startswith("S-3"):
        catalyst_boost = 12
    elif f.startswith("SC 13D") or f.startswith("SC 13G"):
        catalyst_boost = 10
    elif f.startswith("DEF 14A"):
        catalyst_boost = 9
    elif f.startswith("424B"):
        catalyst_boost = 8
    elif f.startswith("S-1/A"):
        catalyst_boost = 6
    elif f.startswith("S-1") or f.startswith("PRE 14A"):
        catalyst_boost = 7
    elif f.startswith("NT 10-Q") or f.startswith("NT 10-K"):
        catalyst_boost = 6
    else:
        catalyst_boost = 2
    return catalyst_boost + recency_score(recency_min) - (ticker_quality_penalty(ticker) // 2)


def score_quality(form: str, recency_min: int, ticker: str) -> int:
    # Quality prefers cleaner/common symbols and stronger governance/event forms.
    f = form.upper()
    form_pts = form_score(f) * 4
    quality_bonus = 0
    if len(ticker) <= 4 and "-" not in ticker:
        quality_bonus += 6
    if f.startswith("8-K") or f.startswith("6-K"):
        quality_bonus += 4
    if f.startswith("424B"):
        quality_bonus -= 4
    return form_pts + recency_score(recency_min) + quality_bonus - ticker_quality_penalty(ticker)


def main() -> int:
    rows = []
    with INPUT.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            form = (row.get("form") or "").strip()
            recency_raw = (row.get("recency_min") or "").strip()
            if not ticker:
                continue
            recency = int(recency_raw) if recency_raw.isdigit() else 999999
            rows.append(
                {
                    "ticker": ticker,
                    "form": form,
                    "updated_utc": row.get("updated_utc", ""),
                    "recency_min": recency,
                    "priority_score": score_quality(form, recency, ticker),
                    "momentum_score": score_momentum(form, recency, ticker),
                    "quality_score": score_quality(form, recency, ticker),
                    "link": row.get("link", ""),
                }
            )

    # Keep best row per ticker
    best = {}
    for r in rows:
        cur = best.get(r["ticker"])
        if cur is None or r["priority_score"] > cur["priority_score"] or (
            r["priority_score"] == cur["priority_score"] and r["recency_min"] < cur["recency_min"]
        ):
            best[r["ticker"]] = r

    ranked = sorted(
        best.values(),
        key=lambda r: (-r["priority_score"], r["recency_min"], r["ticker"]),
    )

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticker",
                "priority_score",
                "momentum_score",
                "quality_score",
                "form",
                "updated_utc",
                "recency_min",
                "link",
            ],
        )
        writer.writeheader()
        writer.writerows(ranked)

    with OUT_TXT.open("w", encoding="utf-8") as f:
        for r in ranked:
            f.write(r["ticker"] + "\n")

    ranked_momo = sorted(
        ranked,
        key=lambda r: (-r["momentum_score"], r["recency_min"], r["ticker"]),
    )
    ranked_quality = sorted(
        ranked,
        key=lambda r: (-r["quality_score"], r["recency_min"], r["ticker"]),
    )

    with OUT_MOMO_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticker",
                "momentum_score",
                "form",
                "updated_utc",
                "recency_min",
                "link",
            ],
        )
        writer.writeheader()
        for r in ranked_momo:
            writer.writerow(
                {
                    "ticker": r["ticker"],
                    "momentum_score": r["momentum_score"],
                    "form": r["form"],
                    "updated_utc": r["updated_utc"],
                    "recency_min": r["recency_min"],
                    "link": r["link"],
                }
            )

    with OUT_QUAL_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticker",
                "quality_score",
                "form",
                "updated_utc",
                "recency_min",
                "link",
            ],
        )
        writer.writeheader()
        for r in ranked_quality:
            writer.writerow(
                {
                    "ticker": r["ticker"],
                    "quality_score": r["quality_score"],
                    "form": r["form"],
                    "updated_utc": r["updated_utc"],
                    "recency_min": r["recency_min"],
                    "link": r["link"],
                }
            )

    with OUT_MOMO_TXT.open("w", encoding="utf-8") as f:
        for r in ranked_momo:
            f.write(r["ticker"] + "\n")

    with OUT_QUAL_TXT.open("w", encoding="utf-8") as f:
        for r in ranked_quality:
            f.write(r["ticker"] + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
