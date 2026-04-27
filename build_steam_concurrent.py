#!/usr/bin/env python3
"""build_steam_concurrent.py — Steam concurrent players (top 100 games).

Concurrent players in gaming titles = direct engagement KPI. Movers:
TTWO (GTA, NBA2K), EA (FC, Apex), ATVI/MSFT (CoD, WoW), RBLX, U (Unity),
DDI, NVDA (RTX attach rates), AMD, NTDOY, SONY.

Source: steamcharts.com (no official API, but steamspy.com Public API
works free). Using steampowered.com ISteamCharts/GetMostPlayedGames/v1.

Output: steam_concurrent.csv
Columns: rank, appid, name, current_players, peak_24h, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "steam_concurrent.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"


def fetch() -> dict | None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"steam: {e}")
        return None


def appid_to_name(appid: int) -> str:
    # Resolve name via store.steampowered.com/api/appdetails (expensive)
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=en"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": UA}), timeout=8
        ) as r:
            d = json.loads(r.read().decode("utf-8"))
            return (d.get(str(appid), {}) or {}).get("data", {}).get("name") or ""
    except Exception:
        return ""


def main() -> None:
    data = fetch() or {}
    ranks = ((data.get("response") or {}).get("ranks")) or []
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in ranks[:50]:
        appid = r.get("appid", 0)
        rows.append({
            "rank": r.get("rank", 0),
            "appid": appid,
            "name": appid_to_name(appid)[:80] if len(rows) < 20 else "",
            "current_players": r.get("concurrent_in_game") or 0,
            "peak_24h": r.get("peak_in_game") or 0,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "rank", "appid", "name", "current_players", "peak_24h", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"steam_concurrent: {len(rows)} games | #1 {top.get('name','?')} "
          f"{top.get('current_players','?')} concurrent -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
