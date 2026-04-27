#!/usr/bin/env python3
"""Public Pick Scoreboard — what Catalyst Edge actually called and how it played out.

Reads sec_outcome_rows.csv + causal_lift_per_ticker.csv. Renders
docs/scoreboard/index.html showing aggregate hit rate and per-pick outcomes
across rolling windows: 7d, 30d, 90d.

This is the trust play SeekingAlpha never built — every call's outcome
is public, audited, with Wilson lower bounds.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
ROWS_CSV = ROOT / "sec_outcome_rows.csv"
CAUSAL_CSV = ROOT / "causal_lift_per_ticker.csv"
OUT_DIR = ROOT / "docs" / "scoreboard"
OUT_HTML = OUT_DIR / "index.html"

Z = 1.96


def to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def wilson_lower(p: float, n: int) -> float:
    if n == 0:
        return 0.0
    denom = 1 + Z * Z / n
    center = p + Z * Z / (2 * n)
    margin = Z * math.sqrt((p * (1 - p) + Z * Z / (4 * n)) / n)
    return max(0.0, (center - margin) / denom)


def load_outcome_rows() -> list[dict[str, str]]:
    if not ROWS_CSV.exists():
        return []
    out: list[dict[str, str]] = []
    with ROWS_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append(r)
    return out


def window_summary(rows: list[dict[str, str]], days: int) -> dict[str, Any]:
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=days)
    sub = []
    for r in rows:
        try:
            d = dt.date.fromisoformat(r.get("list_date", ""))
        except ValueError:
            continue
        if d < cutoff:
            continue
        # Limit to published cohort (score >= 15) so the public scoreboard
        # mirrors what /scanner/ actually surfaces, not the eval noise floor.
        if to_float(r.get("base_score", 0)) < 15:
            continue
        sub.append(r)
    if not sub:
        return {"n": 0, "hit_rate_2pct": 0.0, "wilson_lower": 0.0,
                "avg_alpha_pct": 0.0, "avg_realistic_pnl_pct": 0.0,
                "best_call": None, "worst_call": None}
    hits = sum(1 for r in sub if r.get("hit_2pct") == "1")
    p = hits / len(sub)
    alphas = [to_float(r.get("alpha_close_pct", 0)) for r in sub]
    real_pnl = [to_float(r.get("realistic_pnl_pct", 0)) for r in sub]
    sub_sorted = sorted(sub, key=lambda x: to_float(x.get("alpha_close_pct", 0)), reverse=True)
    best = sub_sorted[0]
    worst = sub_sorted[-1]
    return {
        "n": len(sub),
        "hit_rate_2pct": round(p * 100, 2),
        "wilson_lower": round(wilson_lower(p, len(sub)) * 100, 2),
        "avg_alpha_pct": round(sum(alphas) / len(alphas), 3),
        "avg_realistic_pnl_pct": round(sum(real_pnl) / len(real_pnl), 3),
        "best_call": {
            "ticker": best.get("ticker", ""),
            "date": best.get("list_date", ""),
            "alpha_pct": round(to_float(best.get("alpha_close_pct", 0)), 2),
            "form": best.get("form", ""),
        },
        "worst_call": {
            "ticker": worst.get("ticker", ""),
            "date": worst.get("list_date", ""),
            "alpha_pct": round(to_float(worst.get("alpha_close_pct", 0)), 2),
            "form": worst.get("form", ""),
        },
    }


def render_window_card(label: str, w: dict[str, Any]) -> str:
    h = html.escape
    if w["n"] == 0:
        return f'<div class="window-card"><h3>{label}</h3><p>No picks in window.</p></div>'
    badge_color = "#3fb950" if w["hit_rate_2pct"] >= 50 else "#f78166"
    alpha_color = "#3fb950" if w["avg_alpha_pct"] >= 0 else "#f78166"
    bc, wc = w["best_call"], w["worst_call"]
    return f'''
<div class="window-card">
  <h3>{h(label)} window</h3>
  <div class="kpi-row">
    <div class="kpi"><div class="kpi-n" style="color:{badge_color}">{w["hit_rate_2pct"]}%</div><div class="kpi-l">hit rate (+2% intraday)</div></div>
    <div class="kpi"><div class="kpi-n">{w["wilson_lower"]}%</div><div class="kpi-l">Wilson lower bound (95%)</div></div>
    <div class="kpi"><div class="kpi-n">{w["n"]}</div><div class="kpi-l">picks evaluated</div></div>
    <div class="kpi"><div class="kpi-n" style="color:{alpha_color}">{('+' if w["avg_alpha_pct"]>=0 else '')}{w["avg_alpha_pct"]}%</div><div class="kpi-l">avg alpha vs SPY</div></div>
  </div>
  <div class="bestworst">
    <div class="best">✅ Best call: <strong>{h(bc["ticker"])}</strong> ({h(bc["form"])}) on {h(bc["date"])} → <strong style="color:#3fb950">+{bc["alpha_pct"]}%</strong> alpha</div>
    <div class="worst">⚠️ Worst call: <strong>{h(wc["ticker"])}</strong> ({h(wc["form"])}) on {h(wc["date"])} → <strong style="color:#f78166">{wc["alpha_pct"]}%</strong> alpha</div>
  </div>
</div>'''


def render_per_ticker_table(rows: list[dict[str, str]], limit: int = 30) -> str:
    h = html.escape
    rows = rows[:limit]
    body = ""
    for r in rows:
        wl = to_float(r.get("wilson_lower_pct", 0))
        wl_color = "#3fb950" if wl >= 50 else ("#e7b76c" if wl >= 35 else "#f78166")
        body += f'''
<tr>
  <td><strong>{h(r.get("ticker",""))}</strong></td>
  <td>{r.get("n_picks","")}</td>
  <td>{r.get("hit_rate_2pct","")}%</td>
  <td style="color:{wl_color}">{r.get("wilson_lower_pct","")}%</td>
  <td>{r.get("avg_causal_lift_pct","")}%</td>
  <td>{r.get("avg_spy_alpha_pct","")}%</td>
  <td>{h(r.get("last_date",""))}</td>
</tr>'''
    return body


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_outcome_rows()
    if not rows:
        OUT_HTML.write_text("<html><body>No outcome data available.</body></html>")
        print("scoreboard: no data")
        return 0

    w7 = window_summary(rows, 7)
    w30 = window_summary(rows, 30)
    w90 = window_summary(rows, 90)

    # Per-ticker causal table (sorted by Wilson lower bound).
    per_ticker: list[dict[str, str]] = []
    if CAUSAL_CSV.exists():
        with CAUSAL_CSV.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if int(float(r.get("n_picks", "0") or 0)) < 2:
                    continue
                per_ticker.append(r)

    today_str = dt.date.today().isoformat()
    out_html = f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Public Pick Scoreboard · Catalyst Edge</title>
<meta name="description" content="Every Catalyst Edge call, audited. Hit rate, Wilson lower bound, alpha vs SPY across 7-day / 30-day / 90-day rolling windows. Per-ticker causal lift table.">
<link rel="canonical" href="https://catalystedgescanner.com/scoreboard/">
<meta name="robots" content="index,follow">
<style>
body{{margin:0;font:14.5px/1.6 ui-sans-serif,system-ui,sans-serif;background:#07090f;color:#e5e9f0;padding:40px 18px}}
.wrap{{max-width:980px;margin:0 auto}}
.kicker{{color:#e7b76c;font:11px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;margin-bottom:6px}}
h1{{font-size:34px;font-weight:800;letter-spacing:-.01em;margin:0 0 12px;line-height:1.1}}
.lede{{color:#8b96ab;margin:0 0 32px;max-width:680px;font-size:15px}}
h2{{color:#e7b76c;font-size:18px;margin:36px 0 12px}}
h3{{color:#72e5ff;font-size:15px;margin:0 0 10px}}
.disclaimer{{background:rgba(231,183,108,.05);border-left:3px solid #e7b76c;padding:14px 18px;margin:20px 0;font-size:13px;color:#c9d1d9;border-radius:0 6px 6px 0}}
.window-card{{background:rgba(15,21,33,.6);border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:18px 20px;margin:14px 0}}
.kpi-row{{display:flex;flex-wrap:wrap;gap:24px;margin:10px 0 14px}}
.kpi{{min-width:120px}}
.kpi-n{{font-size:24px;font-weight:800;font-family:ui-monospace,monospace;color:#e5e9f0}}
.kpi-l{{font-size:11px;color:#8b96ab;text-transform:uppercase;letter-spacing:.06em;margin-top:2px}}
.bestworst{{display:flex;flex-direction:column;gap:6px;font-size:13px;color:#c9d1d9}}
table{{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}}
th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid rgba(255,255,255,.06)}}
th{{color:#8b96ab;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.06em;background:rgba(15,21,33,.4)}}
.foot{{margin-top:48px;padding-top:18px;border-top:1px solid rgba(255,255,255,.06);color:#6b7280;font-size:12px}}
.foot a{{color:#72e5ff;text-decoration:none}}
</style></head>
<body><div class="wrap">

<div class="kicker">PUBLIC SCOREBOARD · {today_str}</div>
<h1>Pick Scoreboard</h1>
<p class="lede">Every Catalyst Edge call from the score≥15 published cohort, audited against next-day price action. Wilson lower bounds (95% confidence) shown alongside raw hit rates so small-sample claims can't dominate. Causal lift = excess return attributable to the catalyst itself, after subtracting same-day peer cohort baseline.</p>

<div class="disclaimer">
This is not financial advice. Numbers update each pipeline cycle. Methodology details at <a href="/methodology/" style="color:#e7b76c;font-weight:600">/methodology/</a>. Walk-forward holdout numbers (out-of-sample only) at <a href="/trust/" style="color:#e7b76c;font-weight:600">/trust/</a>.
</div>

<h2>Rolling-window performance</h2>
{render_window_card("7-day", w7)}
{render_window_card("30-day", w30)}
{render_window_card("90-day", w90)}

<h2>Top tickers by Wilson lower bound (causal-lift)</h2>
<p class="lede" style="font-size:13px">Tickers we've called multiple times, ranked by the most conservative win-rate estimate. Causal lift is excess move beyond the same-day peer cohort baseline.</p>
<table>
<tr><th>Ticker</th><th>Picks</th><th>Hit %</th><th>Wilson lo</th><th>Causal lift</th><th>SPY alpha</th><th>Last</th></tr>
{render_per_ticker_table(per_ticker, 30)}
</table>

<div class="foot">
<strong>Live:</strong>
<a href="/scoops/">scoops</a> ·
<a href="/protocol/">protocol</a> ·
<a href="/trust/">trust ledger</a> ·
<a href="/methodology/">methodology</a> ·
<a href="/scanner/">scanner</a><br>
Auto-published from /opt/catalyst/build_scoreboard.py · last regen {today_str} UTC.
Wilson lower bounds use z=1.96 (95% CI). Score≥15 = published cohort floor.
</div>

</div></body></html>
'''
    OUT_HTML.write_text(out_html, encoding="utf-8")
    print(
        f"scoreboard: 7d={w7['n']}/{w7['hit_rate_2pct']}% "
        f"30d={w30['n']}/{w30['hit_rate_2pct']}% "
        f"90d={w90['n']}/{w90['hit_rate_2pct']}% "
        f"per_ticker_rows={len(per_ticker)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
