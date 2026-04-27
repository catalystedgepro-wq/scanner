#!/usr/bin/env python3
"""build_huggingface_trending.py — HuggingFace trending AI models.

Direct AI-sector catalyst signal. HuggingFace is the de-facto model
registry; a sudden top-spot move correlates with AI-compute demand
downstream (NVDA, AMD, AVGO, MU, ANET, SMCI, DELL, VRT) and AI-app
layer (MSFT, GOOGL, META, AMZN, PLTR, U).

Specific tells:
- Chinese lab model tops ranks (DeepSeek, Qwen, Zhipu) = China-AI
  competitive threat narrative, NVDA overhang, SMCI AI-bubble fear.
- Meta Llama model surges = open-source AI momentum, bad for closed-
  model bets (MSFT/OpenAI indirect).
- New mixture-of-experts model: infra redesign burst for AI compute
  (AVGO/ANET networking demand).
- Diffusion-image model trending (FLUX/SD3): NVIDIA consumer RTX
  demand, creator-economy plays (ADBE, PINS).

Fetches top-30 models sorted by likes (weekly trending proxy) and
top-30 sorted by downloads (usage proxy).

Output: huggingface_trending.csv
Columns: model_id, author, likes, downloads, last_modified, pipeline,
license, library, rank_type, captured_at

Source: huggingface.co/api/models (no key, live, JSON).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "huggingface_trending.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

RANKINGS = [
    ("likes", "https://huggingface.co/api/models"
              "?sort=likes&direction=-1&limit=30"),
    ("downloads", "https://huggingface.co/api/models"
                  "?sort=downloads&direction=-1&limit=30"),
    ("trending", "https://huggingface.co/api/models"
                 "?sort=trendingScore&direction=-1&limit=30"),
]


def _fetch(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
        return d if isinstance(d, list) else []
    except Exception as e:
        print(f"huggingface_trending {url[:60]}: {e}")
        return []


def main() -> None:
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rank_type, url in RANKINGS:
        models = _fetch(url)
        for idx, m in enumerate(models, start=1):
            mid = m.get("id") or m.get("modelId") or ""
            if not mid:
                continue
            key = (rank_type, mid)
            if key in seen:
                continue
            seen.add(key)
            author = mid.split("/")[0] if "/" in mid else ""
            rows.append({
                "model_id": mid[:100],
                "author": author[:40],
                "rank_in_type": str(idx),
                "likes": str(m.get("likes") or 0),
                "downloads": str(m.get("downloads") or 0),
                "last_modified": (m.get("lastModified") or "")[:19],
                "pipeline": (m.get("pipeline_tag") or "")[:40],
                "library": (m.get("library_name") or "")[:40],
                "tags": ",".join((m.get("tags") or [])[:6])[:120],
                "rank_type": rank_type,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"huggingface_trending: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["rank_type", "rank_in_type", "model_id", "author",
                  "likes", "downloads", "last_modified", "pipeline",
                  "library", "tags", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: top-5 by trending (or likes if no trending).
    def key(r: dict) -> tuple:
        return (r["rank_type"] != "trending", int(r["rank_in_type"]))

    rows.sort(key=key)
    top = [r for r in rows if r["rank_type"] == "trending"][:5]
    if not top:
        top = [r for r in rows if r["rank_type"] == "likes"][:5]
    bits = " | ".join(f"{r['model_id']} ({r['likes']}L)" for r in top[:3])
    print(f"huggingface_trending: {len(rows)} rows | {bits} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
