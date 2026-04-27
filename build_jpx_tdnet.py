#!/usr/bin/env python3
"""build_jpx_tdnet.py — JPX TDnet Japan corporate announcements.

TDnet ("Timely Disclosure network") is the mandatory same-day filing
channel for all TSE/JPX-listed companies. Signal: material corporate
actions from 4,000+ Japanese issuers that lead ADR (MUFG 8306, SMFG
8316, SNE 6758, HMC 7267, TM 7203) and nikkei-correlation trades by
hours.

Economic readthrough:
- 買収/合併 (acquisition/merger) -> cross-border deal spread.
- 業績予想修正 (guidance revision) -> nikkei-sector shock.
- 自己株式取得 (buyback) -> Japan-tilt quant signal.
- 配当予想修正 (dividend revision) -> high-dividend ETF (DXJ/HEDJ)
  rebalance.
- 株式分割 (stock split) -> retail flow signal.

Source: https://www.release.tdnet.info/inbs/I_list_001_{YYYYMMDD}.html
Output: jpx_tdnet.csv — last 5 weekdays.
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "jpx_tdnet.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://www.release.tdnet.info/inbs/I_list_001_{d}.html"

TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)

KIND_MAP: list[tuple[str, str]] = [
    ("m_and_a", "合併"),
    ("m_and_a", "買収"),
    ("m_and_a", "株式取得"),
    ("tender_offer", "公開買付"),
    ("guidance_revision", "業績予想"),
    ("guidance_revision", "予想修正"),
    ("guidance_revision", "修正"),
    ("earnings", "決算短信"),
    ("earnings", "四半期"),
    ("buyback", "自己株式"),
    ("buyback", "自社株"),
    ("dividend", "配当"),
    ("split", "株式分割"),
    ("split", "分割"),
    ("private_placement", "第三者割当"),
    ("offering", "新株"),
    ("listing", "上場"),
    ("delisting", "上場廃止"),
    ("delisting", "廃止"),
    ("restructure", "組織再編"),
    ("restructure", "事業譲渡"),
]


def _classify(title: str) -> str:
    for kind, kw in KIND_MAP:
        if kw in title:
            return kind
    return "other"


def _fetch_day(day: dt.date) -> list[dict] | None:
    url = BASE.format(d=day.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            txt = r.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    out: list[dict] = []
    for tr in TR_RE.findall(txt):
        cells = [re.sub(r"<[^>]+>", " ", c).strip()
                 for c in TD_RE.findall(tr)]
        if len(cells) < 5:
            continue
        if cells[0] == "時刻":
            continue
        time_s, code, name, title = cells[0], cells[1], cells[2], cells[3]
        exchange = cells[5] if len(cells) >= 6 else ""
        if not code:
            continue
        out.append({
            "date": day.isoformat(),
            "time": time_s[:5],
            "code": code[:10],
            "name": name[:60],
            "kind": _classify(title),
            "title": title[:160],
            "exchange": exchange[:10],
        })
    return out


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    rows: list[dict] = []
    days_fetched = 0
    d = dt.date.today() + dt.timedelta(days=1)
    tries = 0
    while days_fetched < 5 and tries < 12:
        tries += 1
        d = d - dt.timedelta(days=1)
        if d.weekday() >= 5:
            continue
        batch = _fetch_day(d)
        if batch is None:
            continue
        rows.extend(batch)
        days_fetched += 1

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"jpx_tdnet: no fetch, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: (r["date"], r["time"]), reverse=True)
    fieldnames = ["date", "time", "code", "name", "kind",
                  "title", "exchange", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v in sorted(kinds.items(),
                                                 key=lambda x: -x[1])[:6])
    latest = max(r["date"] for r in rows)
    recent_ma = [r for r in rows if r["kind"] == "m_and_a"][:5]
    ma_s = " ".join(f"{r['code']}" for r in recent_ma)
    print(f"jpx_tdnet: {len(rows)} rows {days_fetched}d latest={latest} | "
          f"{kb} | m&a={ma_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
