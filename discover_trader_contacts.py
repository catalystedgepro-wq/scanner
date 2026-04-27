#!/usr/bin/env python3
"""discover_trader_contacts.py — Find individual trader YouTube channels and extract contact emails.

Strategy:
1. Search YouTube for trading keywords (no API key — parses ytInitialData JSON)
2. Visit each channel's /about page to extract contact email
3. Save discovered emails to trader_contacts.csv for outreach

Run daily — skips already-discovered channels.
"""
from __future__ import annotations

import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT        = Path(__file__).parent
OUTPUT_CSV  = ROOT / "trader_contacts.csv"
SEEN_FILE   = ROOT / ".discovered_channels.json"

SEARCH_QUERIES = [
    "penny stock trading channel",
    "day trading SEC filings",
    "pre market gap scanner",
    "small cap stock picks daily",
    "stock market morning watchlist",
    "SEC catalyst stocks",
    "short squeeze stocks daily",
    "penny stocks gapping up",
    "day trading live scanner",
    "OTC stock picks",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

MAX_CHANNELS_PER_QUERY = 8
MAX_TOTAL              = 20   # per run — pipeline calls this daily


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(json.dumps(list(seen)))


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  fetch error {url[:60]}: {e}")
        return ""


def search_youtube_channels(query: str) -> list[str]:
    """Return channel URLs from a YouTube search."""
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}&sp=EgIQAg%3D%3D"
    html = fetch_url(url)
    if not html:
        return []

    # Extract ytInitialData JSON
    match = re.search(r"var ytInitialData = ({.*?});</script>", html, re.DOTALL)
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
    except Exception:
        return []

    channels = []
    raw = json.dumps(data)

    # Find channelRenderer entries
    for m in re.finditer(r'"channelId"\s*:\s*"(UC[^"]{20,})"', raw):
        cid = m.group(1)
        url = f"https://www.youtube.com/channel/{cid}"
        if url not in channels:
            channels.append(url)
        if len(channels) >= MAX_CHANNELS_PER_QUERY:
            break

    # Also find vanity URLs
    for m in re.finditer(r'"canonicalBaseUrl"\s*:\s*"(/@[^"]+)"', raw):
        url = f"https://www.youtube.com{m.group(1)}"
        if url not in channels:
            channels.append(url)
        if len(channels) >= MAX_CHANNELS_PER_QUERY:
            break

    return channels[:MAX_CHANNELS_PER_QUERY]


def get_channel_email(channel_url: str) -> dict | None:
    """Visit channel /about page and extract contact email if present."""
    about_url = channel_url.rstrip("/") + "/about"
    html = fetch_url(about_url)
    if not html:
        return None

    # Extract channel name — try og:title first (most reliable), then channelMetadataRenderer
    og_match = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]{2,80})"', html)
    if og_match:
        name = og_match.group(1).replace(" - YouTube", "").strip()
    else:
        meta_match = re.search(r'"channelMetadataRenderer".*?"title"\s*:\s*"([^"]{2,80})"', html, re.DOTALL)
        name = meta_match.group(1) if meta_match else "Trader"

    # Extract subscriber count (approximate)
    subs_match = re.search(r'"subscriberCountText"[^}]*?"simpleText"\s*:\s*"([^"]+)"', html)
    subs = subs_match.group(1) if subs_match else ""

    # Look for email in page — YouTube encodes emails via a "View email address" button
    # The encoded email is in channelAboutFullMetadata
    # Try encoded email field first
    email_match = re.search(r'"email"\s*:\s*"([^"@]+@[^"]+\.[^"]{2,})"', html)
    if email_match:
        email = email_match.group(1)
    else:
        # Try plain email pattern in page
        plain = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html)
        if plain:
            email = plain.group(0)
        else:
            # Try channel's linked website
            site_match = re.search(r'"url"\s*:\s*"(https?://(?!youtube|google|youtu)[^"]{5,80})"', html)
            if site_match:
                site_html = fetch_url(site_match.group(1))
                site_email = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', site_html)
                email = site_email.group(0) if site_email else None
            else:
                email = None

    if not email:
        return None

    # Filter out YouTube's own domains and common false positives
    skip_domains = ["youtube.com", "google.com", "goo.gl", "youtu.be",
                    "example.com", "domain.com", "email.com"]
    if any(d in email for d in skip_domains):
        return None
    if len(email) > 80:
        return None

    return {
        "name":    name,
        "email":   email,
        "channel": channel_url,
        "subs":    subs,
        "source":  "youtube",
    }


def load_existing_emails() -> set:
    if not OUTPUT_CSV.exists():
        return set()
    emails = set()
    with OUTPUT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            emails.add(row.get("email", "").lower())
    return emails


def append_contact(contact: dict) -> None:
    exists = OUTPUT_CSV.exists()
    with OUTPUT_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name","email","channel","subs","source"])
        if not exists:
            w.writeheader()
        w.writerow(contact)


def main() -> int:
    seen_channels  = load_seen()
    existing_emails = load_existing_emails()
    found = 0

    print(f"discover_trader_contacts: starting — {len(seen_channels)} channels already seen")

    for query in SEARCH_QUERIES:
        if found >= MAX_TOTAL:
            break
        print(f"\nSearching: '{query}'")
        channels = search_youtube_channels(query)
        print(f"  Found {len(channels)} channels")

        for ch_url in channels:
            if found >= MAX_TOTAL:
                break
            if ch_url in seen_channels:
                continue

            seen_channels.add(ch_url)
            time.sleep(1)

            contact = get_channel_email(ch_url)
            if not contact:
                print(f"  no email: {ch_url[-40:]}")
                continue

            email = contact["email"].lower()
            if email in existing_emails:
                print(f"  duplicate: {email}")
                continue

            existing_emails.add(email)
            append_contact(contact)
            found += 1
            print(f"  ✅ {contact['name']} <{email}> ({contact['subs']})")

        time.sleep(1)

    save_seen(seen_channels)
    print(f"\ndiscover_trader_contacts: {found} new contacts found → {OUTPUT_CSV.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
