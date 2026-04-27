#!/usr/bin/env python3
"""build_github_velocity.py — GitHub commit velocity on tech-stock orgs.

Commit velocity on a public engineering org is a direct signal of product
momentum. Covers AI labs, databases, infra, and crypto orgs whose parent
tickers are tradable.

Source: GitHub REST API /orgs/{org}/events — 300 events, no auth (60/hr).
Output: github_velocity.csv
Columns: org, ticker, events_7d, commits_7d, prs_7d, stars_added, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "github_velocity.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

ORGS = {
    "microsoft": "MSFT", "google": "GOOGL", "GoogleCloudPlatform": "GOOGL",
    "facebook": "META", "apple": "AAPL",
    "Netflix": "NFLX", "NVIDIA": "NVDA",
    "IBM": "IBM", "openai": "",  # private
    "anthropics": "",  # private
    "huggingface": "",  # private
    "databricks": "",  # private
    "palantir": "PLTR", "snowflakedb": "SNOW", "cloudflare": "NET",
    "DataDog": "DDOG", "mongodb": "MDB", "elastic": "ESTC",
    "hashicorp": "IBM",  # acquired by IBM
    "CrowdStrike": "CRWD", "okta": "OKTA",
    "intel": "INTC",
    "coinbase": "COIN", "binance": "",
    "Shopify": "SHOP", "stripe": "",
    "salesforce": "CRM", "adobe": "ADBE", "oracle": "ORCL",
    "airbnb": "ABNB", "uber": "UBER",
    "pinterest": "PINS",
}


def fetch(url: str, timeout: int = 20) -> list | None:
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"github: {url[-40:]} -> {e}")
        return None


def main():
    today = dt.datetime.utcnow()
    cutoff = today - dt.timedelta(days=7)
    rows: list[dict] = []
    for org, ticker in ORGS.items():
        data = fetch(f"https://api.github.com/orgs/{org}/events?per_page=100")
        if not isinstance(data, list):
            continue
        bucket = {"events": 0, "commits": 0, "prs": 0, "stars": 0}
        for e in data:
            try:
                ts = dt.datetime.strptime((e.get("created_at") or "")[:19], "%Y-%m-%dT%H:%M:%S")
            except Exception:
                continue
            if ts < cutoff:
                continue
            bucket["events"] += 1
            t = e.get("type") or ""
            if t == "PushEvent":
                bucket["commits"] += len((e.get("payload") or {}).get("commits") or [])
            elif t == "PullRequestEvent":
                bucket["prs"] += 1
            elif t == "WatchEvent":
                bucket["stars"] += 1
        rows.append({
            "org": org,
            "ticker": ticker,
            "events_7d": bucket["events"],
            "commits_7d": bucket["commits"],
            "prs_7d": bucket["prs"],
            "stars_added": bucket["stars"],
            "captured_at": today.isoformat(timespec="seconds") + "Z",
        })
    rows.sort(key=lambda r: r["commits_7d"], reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "org", "ticker", "events_7d", "commits_7d",
                "prs_7d", "stars_added", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"github_velocity: {len(rows)} orgs -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
