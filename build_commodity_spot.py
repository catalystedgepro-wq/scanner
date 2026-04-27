#!/usr/bin/env python3
"""build_commodity_spot.py — Major commodity spot/futures prices (daily).

Causal chain fuel: coffee spike -> SBUX/MDLZ margin squeeze, cotton ->
HBI/GPS, lumber -> DHI/LEN/PHM input costs, wheat -> GIS/K/CPB, corn ->
TSN/PPC/HRL feed costs, gold -> GOLD/NEM miners, silver -> PAAS/WPM,
copper -> FCX/SCCO/BHP, nat gas -> EQT/AR/SWN, platinum/palladium ->
SBSW/IMPUY (auto catalytic converters), DXY -> export-heavy multinats.

Sources:
- Stooq `q/l/?s={sym}.f&f=sd2t2c` single-symbol CSV quote. Reliable,
  no auth, no rate limit. Primary source.
- Yahoo Finance v8 chart endpoint. Backup only, heavily rate-limited
  (WSL and droplet both get 429'd after modest bursts).
- FRED via curl (HTTP/1.1) for WTI/Brent/natgas as third-tier backup.

Output: commodity_spot.csv
Columns: symbol, name, unit, price, captured_at, source
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "commodity_spot.csv"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Stooq symbol -> (display_name, unit, Yahoo backup symbol)
CONTRACTS = [
    ("gc.f",  "gold",        "oz",     "GC=F"),
    ("si.f",  "silver",      "oz",     "SI=F"),
    ("hg.f",  "copper",      "lb",     "HG=F"),
    ("pl.f",  "platinum",    "oz",     "PL=F"),
    ("pa.f",  "palladium",   "oz",     "PA=F"),
    ("cl.f",  "wti",         "bbl",    "CL=F"),
    ("bz.f",  "brent",       "bbl",    "BZ=F"),
    ("ng.f",  "natgas",      "mmbtu",  "NG=F"),
    ("rb.f",  "gasoline",    "gal",    "RB=F"),
    ("ho.f",  "heating_oil", "gal",    "HO=F"),
    ("zc.f",  "corn",        "bushel", "ZC=F"),
    ("zs.f",  "soybeans",    "bushel", "ZS=F"),
    ("zw.f",  "wheat",       "bushel", "ZW=F"),
    ("kc.f",  "coffee",      "lb",     "KC=F"),
    ("ct.f",  "cotton",      "lb",     "CT=F"),
    ("sb.f",  "sugar",       "lb",     "SB=F"),
    ("cc.f",  "cocoa",       "mt",     "CC=F"),
    ("lb.f",  "lumber",      "mbf",    "LBR=F"),
    ("dx.f",  "dxy",         "index",  "DX-Y.NYB"),
]

FRED_BACKUP = {
    "wti_fred":    "DCOILWTICO",
    "brent_fred":  "DCOILBRENTEU",
    "natgas_fred": "DHHNGSP",
}


def stooq_fetch(sym: str) -> float | None:
    """Fetch last close from Stooq. Returns None on N/D or error."""
    url = f"https://stooq.com/q/l/?s={sym}&f=sd2t2c&h&e=csv"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"stooq {sym}: {e}")
        return None
    lines = [l for l in body.splitlines() if l.strip()]
    if len(lines) < 2:
        return None
    parts = lines[1].split(",")
    if len(parts) < 4:
        return None
    close = parts[-1].strip()
    if close in {"", "N/D", "NaN"}:
        return None
    try:
        return float(close)
    except ValueError:
        return None


def yahoo_fetch(sym: str, retries: int = 2) -> float | None:
    enc = urllib.parse.quote(sym, safe="")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}"
           f"?range=5d&interval=1d")
    headers = {
        "User-Agent": UA,
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://finance.yahoo.com/",
    }
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read().decode("utf-8", errors="ignore"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(15)
                continue
            return None
        except Exception:
            return None
    else:
        return None
    try:
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        for c in reversed(closes):
            if c is not None:
                return float(c)
    except (KeyError, IndexError, TypeError):
        pass
    return None


def fred_latest(sid: str) -> float | None:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    for attempt in range(3):
        try:
            body = subprocess.check_output(
                ["curl", "-sSL", "--http1.1", "--max-time", "20",
                 "-A", UA, url],
                stderr=subprocess.DEVNULL,
                timeout=25,
            ).decode("utf-8", errors="ignore")
            if body.strip():
                break
        except (subprocess.CalledProcessError,
                subprocess.TimeoutExpired):
            if attempt == 2:
                return None
    else:
        return None
    for line in reversed(body.splitlines()):
        if "," not in line:
            continue
        _, val = line.split(",", 1)
        val = val.strip()
        if val in (".", "", "NaN"):
            continue
        try:
            return float(val)
        except ValueError:
            continue
    return None


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    rows: list[dict] = []
    for stooq_sym, name, unit, yahoo_sym in CONTRACTS:
        price = stooq_fetch(stooq_sym)
        source = "stooq"
        if price is None:
            price = yahoo_fetch(yahoo_sym)
            source = "yahoo_v8" if price is not None else None
        if price is None:
            continue
        rows.append({
            "symbol": stooq_sym,
            "name": name,
            "unit": unit,
            "price": f"{price:.4f}",
            "captured_at": now,
            "source": source,
        })
        time.sleep(0.3)
    for name, sid in FRED_BACKUP.items():
        price = fred_latest(sid)
        if price is None:
            continue
        rows.append({
            "symbol": sid,
            "name": name,
            "unit": "",
            "price": f"{price:.4f}",
            "captured_at": now,
            "source": "fred",
        })
    # Preserve existing CSV if today's fetch totally failed
    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"commodity_spot: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["symbol", "name", "unit", "price",
                        "captured_at", "source"],
        )
        w.writeheader()
        w.writerows(rows)
    gold = next((r for r in rows if r["name"] == "gold"), {})
    wti = next((r for r in rows if r["name"] == "wti"), {})
    print(f"commodity_spot: {len(rows)} contracts | gold="
          f"{gold.get('price','?')} wti={wti.get('price','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
