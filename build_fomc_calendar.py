#!/usr/bin/env python3
"""build_fomc_calendar.py — FOMC meeting calendar + recent statement diff.

Eight scheduled FOMC meetings per year — each moves entire curve. Fed
publishes meeting schedule + post-meeting statement HTML.

Output: fomc_calendar.csv + fomc_statement.txt
Columns: meeting_date, has_press_conf, statement_url
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fomc_calendar.csv"
STMT_TXT = ROOT / "fomc_statement_latest.txt"

UA = "CatalystEdge/1.0 (opensource@example.com)"
CAL_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"


def fetch(url: str, timeout: int = 25) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"fomc: {e}")
        return None


def main():
    html = fetch(CAL_URL) or ""
    rows: list[dict] = []
    # 2025+ FOMC page uses: <a id="NNNNN">YEAR FOMC Meetings</a>, then
    # repeating <div class="row fomc-meeting"> blocks with fomc-meeting__month
    # and fomc-meeting__date div children.
    year_re = re.compile(r'<a\s+id="\d+">(\d{4}) FOMC Meetings</a>', re.I)
    panels = re.split(year_re, html)
    for i in range(1, len(panels), 2):
        year_s = panels[i]
        block = panels[i + 1] if i + 1 < len(panels) else ""
        try:
            year = int(year_s)
        except Exception:
            continue
        # Each meeting is a <div class="row fomc-meeting"> ... </div> block.
        meeting_rx = re.compile(
            r'<div[^>]*class="row fomc-meeting[^"]*"[^>]*>(.*?)(?=<div[^>]*class="row fomc-meeting|<div[^>]*class="panel panel-default"|$)',
            re.DOTALL | re.I,
        )
        for mblock in meeting_rx.findall(block):
            mo_m = re.search(
                r'fomc-meeting__month[^>]*>\s*(?:<strong>)?([^<]+?)(?:</strong>)?\s*</div>',
                mblock, re.I,
            )
            dt_m = re.search(
                r'fomc-meeting__date[^>]*>\s*([^<]+?)\s*</div>',
                mblock, re.I,
            )
            if not mo_m or not dt_m:
                continue
            month_txt = mo_m.group(1).strip()
            day_range = dt_m.group(1).strip()
            nums = re.findall(r"\d+", day_range)
            if not nums:
                continue
            try:
                # month may be like "January" or "January/February" for month-splits
                first_mon = re.match(r"([A-Za-z]+)", month_txt).group(1)[:3]
                mnum = dt.datetime.strptime(first_mon, "%b").month
                day = int(nums[-1])
                # If month-split like "January/February" + day 3, ending day belongs to 2nd month
                if "/" in month_txt:
                    parts = month_txt.split("/")
                    second = parts[1].strip()[:3]
                    try:
                        mnum = dt.datetime.strptime(second, "%b").month
                    except Exception:
                        pass
                meeting = dt.date(year, mnum, day)
            except Exception:
                continue
            has_pc = "1" if re.search(r"press\s*conference", mblock, re.I) else ""
            rows.append({
                "meeting_date": meeting.strftime("%Y-%m-%d"),
                "has_press_conf": has_pc,
                "notes": "Press Conference" if has_pc else "",
                "statement_url": f"https://www.federalreserve.gov/newsevents/pressreleases/monetary{meeting.strftime('%Y%m%d')}a.htm",
            })
    # Save statement text for most recent past meeting
    today = dt.date.today()
    past = [r for r in rows if r["meeting_date"] < today.strftime("%Y-%m-%d")]
    if past:
        past.sort(key=lambda r: r["meeting_date"], reverse=True)
        stmt_html = fetch(past[0]["statement_url"])
        if stmt_html:
            text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", stmt_html, flags=re.DOTALL | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            STMT_TXT.write_text(text[:20000])
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["meeting_date", "has_press_conf", "notes", "statement_url"],
        )
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["meeting_date"]))
    print(f"fomc_calendar: {len(rows)} meetings -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
