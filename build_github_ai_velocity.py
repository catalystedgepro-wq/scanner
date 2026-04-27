#!/usr/bin/env python3
"""build_github_ai_velocity.py — AI/ML repo creation + star velocity.

Developer-sentiment leading indicator: GitHub repo creation velocity
across LLM / agents / RAG / inference / GPU topics. When AI repo
creation spikes, hyperscaler capex and GPU demand follow 60-90 days
later.

Signal:
- `created:>=N-days` counts rising fast = bull AI cycle intact
- Star velocity on top repos = dev mindshare (ollama, vllm, trtllm)
- Topic rotation: LLM → agents → inference → robotics = maturity
  curve

Drives:
- GPU (NVDA, AMD, AVGO, MRVL)
- AI infra (SMCI, ANET, VRT, PWR)
- AI platforms (PLTR, MSFT, GOOGL, META, ORCL)
- Edge/dev tooling (GTLB, DDOG, ESTC)
- AI ETFs (BOTZ, AIQ, ROBO, IGV)

Source: api.github.com/search/repositories (free, 30 req/min unauth).
Output: github_ai_velocity.csv
Columns: topic, window_days, repo_count, top_repo, top_stars,
         top_pushed, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "github_ai_velocity.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = "https://api.github.com/search/repositories"

TOPICS = [
    "llm",
    "agents",
    "rag",
    "llamaindex",
    "langchain",
    "fine-tuning",
    "inference",
    "diffusion-models",
    "computer-vision",
    "reinforcement-learning",
    "robotics",
    "mlops",
    "vector-database",
    "transformer",
    "mcp",
]

WINDOW_DAYS = 30


def _search(query: str) -> dict | None:
    params = urllib.parse.urlencode({
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": 1,
    })
    url = f"{API}?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"github_ai_velocity: {query}: {e}")
        return None


def main() -> None:
    today = dt.datetime.now(dt.timezone.utc).date()
    since = (today - dt.timedelta(days=WINDOW_DAYS)).isoformat()

    rows: list[dict] = []

    for topic in TOPICS:
        q = f"topic:{topic} created:>={since}"
        data = _search(q)
        if not data:
            time.sleep(3)
            continue
        total = int(data.get("total_count") or 0)
        items = data.get("items") or []
        top = items[0] if items else None
        rows.append({
            "topic": topic,
            "window_days": str(WINDOW_DAYS),
            "repo_count": str(total),
            "top_repo": (top.get("full_name") or "")[:60] if top else "",
            "top_stars": str(top.get("stargazers_count") or 0) if top else "0",
            "top_pushed": (top.get("pushed_at") or "")[:10] if top else "",
        })
        time.sleep(3)  # stay under 30 req/min unauth cap

    # Aggregate top-5 AI repos by recent push velocity (trending now).
    q = (f"topic:llm pushed:>={since} stars:>100")
    trending = _search(q)
    if trending:
        items = trending.get("items") or []
        for i, repo in enumerate(items[:5]):
            rows.append({
                "topic": f"trending_{i+1}",
                "window_days": str(WINDOW_DAYS),
                "repo_count": "1",
                "top_repo": (repo.get("full_name") or "")[:60],
                "top_stars": str(repo.get("stargazers_count") or 0),
                "top_pushed": (repo.get("pushed_at") or "")[:10],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"github_ai_velocity: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["topic", "window_days", "repo_count", "top_repo",
                  "top_stars", "top_pushed", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    llm = next((r for r in rows if r["topic"] == "llm"), None)
    agents = next((r for r in rows if r["topic"] == "agents"), None)
    rag = next((r for r in rows if r["topic"] == "rag"), None)
    bits = []
    if llm:
        bits.append(f"llm_new={llm['repo_count']}")
    if agents:
        bits.append(f"agents_new={agents['repo_count']}")
    if rag:
        bits.append(f"rag_new={rag['repo_count']}")
    print(f"github_ai_velocity: {len(rows)} rows | {WINDOW_DAYS}d window | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
