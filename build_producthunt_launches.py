#!/usr/bin/env python3
"""build_producthunt_launches.py — Product Hunt daily launches tape.

Product Hunt launches are a high-signal leading indicator for:
- AI/SaaS category momentum (indie dev tools = downstream spend on
  MSFT Azure / AWS / MDB / DDOG / SNOW)
- Consumer-app thesis shifts (meditation → mental-health pipeline)
- Developer-tool launch velocity (GitLab, JFrog, HashiCorp readthrough)
- Crypto / fintech launches (COIN, HOOD, SOFI category)

Signal:
- Daily launch counts trending up → ecosystem expansion
- Category share (AI-laden titles vs infra vs consumer)
- Keyword frequency → thematic drift

Source: producthunt.com/feed (Atom, no auth)
Output: producthunt_launches.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import html
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "producthunt_launches.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
FEED = "https://www.producthunt.com/feed"

CATEGORY_KEYWORDS = {
    "ai": ["ai ", "llm", "gpt", "chatbot", "agent", "copilot",
           "prompt", "rag", "neural", "vector"],
    "devtool": ["api", "sdk", "cli", "ide", "dev ", "github",
                "terminal", "compiler", "framework", "plugin",
                "markdown"],
    "saas_prod": ["productivity", "workspace", "notes",
                  "meeting", "calendar", "task", "crm", "pm"],
    "design": ["design", "figma", "canvas", "creative", "image",
               "video", "editor"],
    "analytics": ["analytics", "dashboard", "report", "metric",
                  "telemetry"],
    "marketing": ["seo", "ads", "marketing", "campaign", "growth"],
    "crypto": ["crypto", "bitcoin", "ethereum", "web3", "nft",
               "blockchain", "wallet"],
    "security": ["security", "password", "vpn", "privacy",
                 "encryption", "2fa"],
    "fintech": ["fintech", "banking", "invoice", "payment",
                "stripe", "wallet"],
    "health": ["health", "meditation", "sleep", "fitness",
               "mental", "wellness"],
}


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"producthunt_launches: {url[:80]}: {e}")
        return ""


def _field(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
    return (m.group(1) if m else "").strip()


def _classify(text: str) -> str:
    t = text.lower()
    hits: list[str] = []
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(k in t for k in kws):
            hits.append(cat)
    return ",".join(hits)


def main() -> None:
    atom = _get(FEED)
    if not atom:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"producthunt_launches: no fetch, keeping {OUT_CSV.name}")
        return
    entries = re.findall(r"<entry>(.*?)</entry>", atom, re.S)
    if not entries:
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for e in entries:
        title = _field(e, "title")
        pub = _field(e, "published")
        content = _field(e, "content")
        # Extract first <p>...</p> from decoded html as tagline.
        dec = html.unescape(content)
        tag_m = re.search(r"<p>\s*([^<]+?)\s*</p>", dec, re.S)
        tagline = tag_m.group(1).strip() if tag_m else ""
        link_m = re.search(
            r'<link[^>]+rel="alternate"[^>]+href="([^"]+)"', e)
        link = link_m.group(1) if link_m else ""
        author_m = re.search(r"<name>([^<]+)</name>", e)
        author = author_m.group(1).strip() if author_m else ""
        category = _classify(f"{title} {tagline}")
        rows.append({
            "published": pub,
            "title": title[:160],
            "tagline": tagline[:240],
            "category": category,
            "author": author[:80],
            "link": link,
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"producthunt_launches: empty, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["published"], reverse=True)
    fieldnames = ["published", "title", "tagline", "category",
                  "author", "link", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    cat_counts: dict[str, int] = {}
    for r in rows:
        for c in r["category"].split(","):
            if c:
                cat_counts[c] = cat_counts.get(c, 0) + 1
    top = " ".join(f"{k}={v}" for k, v in
                   sorted(cat_counts.items(), key=lambda x: -x[1])[:5])
    print(f"producthunt_launches: {len(rows)} launches | {top} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
