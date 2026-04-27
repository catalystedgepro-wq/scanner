#!/usr/bin/env python3
"""build_npm_velocity.py — npm registry weekly downloads for JS ecosystem.

npm download counts are the purest developer-adoption signal for the
JavaScript/TypeScript ecosystem — and JS/TS dev activity cascades into
hyperscaler revenue, frontend framework dominance, AI-JS stack
rotation, and cloud-fn runtimes.

Signal:
- react/next accel = Vercel/Netlify revenue run-rate signal
- @anthropic-ai/sdk + openai + ai accel = JS-side LLM build activity
- langchain/js accel = JS agent/RAG adoption
- typescript YoY accel = TS-displacing-JS secular shift
- vite vs webpack ratio = build-tool regime
- ethers/viem/web3.js ratio = web3 stack dominance

Source: api.npmjs.org/downloads/point/{window}/{pkg1,pkg2,...} (bulk
for unscoped; per-pkg for scoped @org/name — npm requires this split).

Output: npm_velocity.csv
Columns: package, category, downloads_7d, downloads_30d,
         ratio_7d_to_baseline, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "npm_velocity.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.npmjs.org/downloads/point"

PACKAGES = [
    ("react", "frontend"),
    ("vue", "frontend"),
    ("svelte", "frontend"),
    ("solid-js", "frontend"),
    ("@angular/core", "frontend"),
    ("next", "meta_framework"),
    ("nuxt", "meta_framework"),
    ("astro", "meta_framework"),
    ("remix", "meta_framework"),
    ("gatsby", "meta_framework"),
    ("vite", "build_tool"),
    ("webpack", "build_tool"),
    ("esbuild", "build_tool"),
    ("rollup", "build_tool"),
    ("typescript", "runtime"),
    ("tsx", "runtime"),
    ("ts-node", "runtime"),
    ("@anthropic-ai/sdk", "ai_model"),
    ("openai", "ai_model"),
    ("@google/generative-ai", "ai_model"),
    ("langchain", "ai_framework"),
    ("@langchain/core", "ai_framework"),
    ("ai", "ai_framework"),
    ("llamaindex", "ai_framework"),
    ("pnpm", "pkg_manager"),
    ("yarn", "pkg_manager"),
    ("prisma", "database"),
    ("drizzle-orm", "database"),
    ("mongoose", "database"),
    ("@supabase/supabase-js", "database"),
    ("ethers", "crypto_dev"),
    ("viem", "crypto_dev"),
    ("web3", "crypto_dev"),
    ("@solana/web3.js", "crypto_dev"),
    ("@sentry/node", "observability"),
    ("dd-trace", "observability"),
    ("vitest", "tooling"),
    ("playwright", "tooling"),
    ("eslint", "tooling"),
]


def _fetch(path: str, retry: int = 0) -> dict | None:
    url = f"{BASE}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        if e.code == 429 and retry < 3:
            time.sleep(3.0 * (retry + 1))
            return _fetch(path, retry + 1)
        if e.code == 404:
            return None
        print(f"npm_velocity: {path}: {e}")
        return None
    except Exception as e:
        print(f"npm_velocity: {path}: {e}")
        return None


def _bulk(pkgs: list[str], window: str) -> dict[str, int]:
    # Unscoped bulk — comma-separated, up to ~128 packages.
    joined = ",".join(pkgs)
    payload = _fetch(f"{window}/{joined}")
    if not payload:
        return {}
    out: dict[str, int] = {}
    # Bulk returns dict keyed by pkg. Single returns a flat record.
    if "downloads" in payload and "package" in payload:
        # Single-pkg shape (when len(pkgs)==1)
        d = payload.get("downloads")
        if isinstance(d, int):
            out[payload["package"]] = d
        return out
    for pkg, rec in payload.items():
        if isinstance(rec, dict) and isinstance(rec.get("downloads"), int):
            out[pkg] = rec["downloads"]
    return out


def _single_scoped(pkg: str, window: str) -> int | None:
    enc = urllib.parse.quote(pkg, safe="")
    payload = _fetch(f"{window}/{enc}")
    if not payload:
        return None
    d = payload.get("downloads")
    return d if isinstance(d, int) else None


def main() -> None:
    unscoped = [p for p, _ in PACKAGES if not p.startswith("@")]
    scoped = [p for p, _ in PACKAGES if p.startswith("@")]

    d7_bulk = _bulk(unscoped, "last-week")
    time.sleep(0.5)
    d30_bulk = _bulk(unscoped, "last-month")

    d7: dict[str, int] = dict(d7_bulk)
    d30: dict[str, int] = dict(d30_bulk)

    for pkg in scoped:
        time.sleep(0.4)
        v7 = _single_scoped(pkg, "last-week")
        time.sleep(0.4)
        v30 = _single_scoped(pkg, "last-month")
        if v7 is not None:
            d7[pkg] = v7
        if v30 is not None:
            d30[pkg] = v30

    rows: list[dict] = []
    for pkg, cat in PACKAGES:
        v7 = d7.get(pkg)
        v30 = d30.get(pkg)
        if v7 is None and v30 is None:
            continue
        v7 = v7 or 0
        v30 = v30 or 0
        ratio = ""
        if v30 > 0:
            projected = (v7 / 7) * 30
            ratio = f"{projected / v30:.3f}"
        rows.append({
            "package": pkg,
            "category": cat,
            "downloads_7d": str(v7),
            "downloads_30d": str(v30),
            "ratio_7d_to_baseline": ratio,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"npm_velocity: empty, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["category"], -int(r["downloads_7d"])))
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["package", "category", "downloads_7d", "downloads_30d",
                  "ratio_7d_to_baseline", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    fe_rows = [r for r in rows if r["category"] == "frontend"]
    top_fe = sorted(fe_rows, key=lambda r: -int(r["downloads_7d"]))[:3]
    bits = [f"{r['package']}={int(r['downloads_7d'])/1e6:.1f}M"
            for r in top_fe]
    accel = [r for r in rows if r["ratio_7d_to_baseline"]]
    accel.sort(key=lambda r: -float(r["ratio_7d_to_baseline"]))
    if accel:
        ar = accel[0]
        bits.append(f"top_accel={ar['package']}×{ar['ratio_7d_to_baseline']}")
    print(f"npm_velocity: {len(rows)} pkgs | 7d: {' '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
