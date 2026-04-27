#!/usr/bin/env python3
"""indexnow_ping.py — Submit URLs to IndexNow + sitemap pings.

IndexNow API fans out to Bing, Yandex, Naver, Seznam (and per their docs Google
is in experimental support). Free, no API key registration — you just self-host
a key file at https://<host>/<key>.txt and search engines verify it.

Usage:
    python3 indexnow_ping.py --urls https://catalystedgescanner.com/blog/<slug>/
    python3 indexnow_ping.py --slug <slug>
    python3 indexnow_ping.py --sitemap   # also ping Bing/Google/Yandex sitemap endpoints
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
DOCS = WORKSPACE / "docs"
LOG_PATH = WORKSPACE / "logs" / "distribution_loop.log"

HOST = "catalystedgescanner.com"
KEY = "cesa-indexnow-7f3a2b9c1d4e6f8a"
KEY_FILE_URL = f"https://{HOST}/{KEY}.txt"
SITEMAP_URL = f"https://{HOST}/sitemap.xml"


def _now_iso() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    line = f"[{_now_iso()}] indexnow_ping: {msg}"
    print(line)
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def submit_indexnow(urls: list[str]) -> bool:
    """Fan out to api.indexnow.org. Bing/Yandex/Seznam pick it up automatically."""
    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_FILE_URL,
        "urlList": urls,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.indexnow.org/indexnow",
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.getcode()
            _log(f"indexnow.org HTTP {code} for {len(urls)} url(s)")
            return 200 <= code < 300
    except Exception as e:
        _log(f"indexnow.org ERROR: {e}")
        return False


def submit_indexnow_sitemap() -> bool:
    """IndexNow accepts the sitemap URL itself as a list — fans out to all
    URLs in the sitemap. Replaces the now-410/404 Bing/Google ping endpoints.
    """
    return submit_indexnow([SITEMAP_URL])


def ensure_key_file() -> Path:
    """Make sure /docs/<KEY>.txt exists locally so deploys carry it to the droplet."""
    p = DOCS / f"{KEY}.txt"
    if not p.exists():
        p.write_text(KEY + "\n", encoding="utf-8")
        _log(f"wrote key file {p}")
    return p


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", nargs="+", help="explicit URLs to submit")
    parser.add_argument("--slug", help="submit https://<host>/blog/<slug>/")
    parser.add_argument("--sitemap", action="store_true",
                        help="also ping Bing/Google sitemap endpoints")
    args = parser.parse_args(argv)

    ensure_key_file()

    urls: list[str] = []
    if args.urls:
        urls.extend(args.urls)
    if args.slug:
        urls.append(f"https://{HOST}/blog/{args.slug}/")

    ok_inow = True
    if urls:
        ok_inow = submit_indexnow(urls)

    if args.sitemap:
        submit_indexnow_sitemap()

    return 0 if ok_inow else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
