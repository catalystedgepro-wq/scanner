#!/usr/bin/env python3
"""build_pypi_velocity.py — PyPI download velocity for AI/crypto/biotech libs.

Python package downloads are a forward indicator of developer adoption,
which in turn foreshadows revenue flowing to the hyperscaler/model
providers. Openai/anthropic weekly downloads track API volume.
Langchain + llamaindex + chromadb track retrieval/agent building.

Signal:
- openai weekly downloads accel = MSFT/OAI revenue tailwind (Azure)
- anthropic weekly downloads accel = AMZN bedrock revenue tailwind
- diffusers accel = NVDA / CRWV GPU demand
- huggingface_hub accel = compute-demand proxy (CRWV, SMCI, DELL)
- pandas/numpy YoY accel = data-science adoption baseline health
- torch vs tensorflow ratio = PyTorch share of AI compute stack
- crypto libs (web3, solana) velocity = onchain dev activity
  (COIN revenue proxy)

Drives:
- MSFT (OAI revenue share), AMZN (Bedrock), GOOG (Vertex)
- NVDA, AMD, AVGO (GPU demand via diffusers/torch)
- CRWV, SMCI, DELL (AI infrastructure)
- PLTR (Python data-platform cohort)
- HUBS (DB chains via pandas)

Source: pypistats.org/api/packages/{pkg}/recent (free, JSON).
Output: pypi_velocity.csv
Columns: package, category, downloads_1d, downloads_7d, downloads_30d,
         ratio_7d_to_baseline, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "pypi_velocity.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://pypistats.org/api/packages"

PACKAGES = [
    # AI model providers
    ("openai", "ai_model"),
    ("anthropic", "ai_model"),
    ("google-generativeai", "ai_model"),
    ("cohere", "ai_model"),
    ("mistralai", "ai_model"),
    # AI frameworks / agents
    ("langchain", "ai_framework"),
    ("langgraph", "ai_framework"),
    ("llama-index", "ai_framework"),
    ("crewai", "ai_framework"),
    ("autogen-agentchat", "ai_framework"),
    # Vector DB / retrieval
    ("chromadb", "ai_vector"),
    ("pinecone-client", "ai_vector"),
    ("qdrant-client", "ai_vector"),
    ("weaviate-client", "ai_vector"),
    # Compute / ML
    ("torch", "ai_compute"),
    ("tensorflow", "ai_compute"),
    ("transformers", "ai_compute"),
    ("diffusers", "ai_compute"),
    ("huggingface-hub", "ai_compute"),
    ("accelerate", "ai_compute"),
    ("vllm", "ai_compute"),
    # Data science baseline
    ("pandas", "data_baseline"),
    ("numpy", "data_baseline"),
    ("scikit-learn", "data_baseline"),
    ("polars", "data_baseline"),
    # Crypto
    ("web3", "crypto_dev"),
    ("solana", "crypto_dev"),
    ("ccxt", "crypto_dev"),
    # Bio
    ("biopython", "bio"),
    ("scanpy", "bio"),
    # Web serving (infra signal)
    ("fastapi", "infra"),
    ("pydantic", "infra"),
    ("uvicorn", "infra"),
]


def _get(pkg: str, attempt: int = 0) -> dict | None:
    url = f"{BASE}/{pkg}/recent"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        if e.code == 429 and attempt < 2:
            time.sleep(2.0 * (attempt + 1))
            return _get(pkg, attempt + 1)
        print(f"pypi_velocity: {pkg}: {e}")
        return None
    except Exception as e:
        print(f"pypi_velocity: {pkg}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []
    for pkg, cat in PACKAGES:
        payload = _get(pkg)
        if not payload or not isinstance(payload.get("data"), dict):
            continue
        d = payload["data"]
        d1 = d.get("last_day") or 0
        d7 = d.get("last_week") or 0
        d30 = d.get("last_month") or 0
        # ratio of 7d × 4.3 vs 30d (reveals acceleration)
        ratio = ""
        if d30 > 0:
            projected = (d7 / 7) * 30
            ratio = f"{projected / d30:.3f}"
        rows.append({
            "package": pkg,
            "category": cat,
            "downloads_1d": str(d1),
            "downloads_7d": str(d7),
            "downloads_30d": str(d30),
            "ratio_7d_to_baseline": ratio,
        })
        time.sleep(0.5)  # polite rate limit

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"pypi_velocity: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    # Sort inside each category by 7d desc.
    rows.sort(key=lambda r: (r["category"], -int(r["downloads_7d"])))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["package", "category", "downloads_1d", "downloads_7d",
                  "downloads_30d", "ratio_7d_to_baseline", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: top 3 AI model providers 7d, plus top accel.
    ai_rows = [r for r in rows if r["category"] == "ai_model"]
    top_ai = sorted(ai_rows, key=lambda r: -int(r["downloads_7d"]))[:3]
    bits = [f"{r['package']}={int(r['downloads_7d'])/1e6:.1f}M"
            for r in top_ai]
    # Biggest accel.
    accel = [r for r in rows if r["ratio_7d_to_baseline"]]
    accel.sort(key=lambda r: -float(r["ratio_7d_to_baseline"]))
    if accel:
        ar = accel[0]
        bits.append(f"top_accel={ar['package']}×{ar['ratio_7d_to_baseline']}")
    print(f"pypi_velocity: {len(rows)} pkgs | 7d: {' '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
