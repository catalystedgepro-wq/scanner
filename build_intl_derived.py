#!/usr/bin/env python3
"""build_intl_derived.py — derive sector heatmap, sympathy chains, regional
movers, and country leaderboard from intl_equity_gappers.csv.

Produces docs/data/intl_panels.json — single payload the /international/ page
hydrates from. Re-runs each autonomous_loop cycle, so panels stay live.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path


def _find_root() -> Path:
    for cand in (
        Path("/opt/catalyst"),
        Path("/home/operator/.openclaw/workspace"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "build_intl_derived.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
GAPPERS = ROOT / "docs/intl_equity_gappers.csv"
CROSSBORDER = ROOT / "docs/data/cross_border_convergence.json"
OUT = ROOT / "docs/data/intl_panels.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

# Region grouping for the Regional Movers panel.
REGION_BY_ISO = {
    "USA": "Americas", "BRA": "Americas", "CAN": "Americas",
    "MEX": "Americas", "ARG": "Americas", "CHL": "Americas",
    "JPN": "APAC", "CHN": "APAC", "HKG": "APAC", "TWN": "APAC",
    "KOR": "APAC", "IND": "APAC", "AUS": "APAC", "NZL": "APAC",
    "SGP": "APAC", "THA": "APAC", "IDN": "APAC", "MYS": "APAC",
    "PHL": "APAC", "VNM": "APAC",
    "GBR": "EMEA", "DEU": "EMEA", "FRA": "EMEA", "CHE": "EMEA",
    "NLD": "EMEA", "ESP": "EMEA", "ITA": "EMEA", "SWE": "EMEA",
    "NOR": "EMEA", "DNK": "EMEA", "FIN": "EMEA", "BEL": "EMEA",
    "AUT": "EMEA", "IRL": "EMEA", "PRT": "EMEA", "GRC": "EMEA",
    "POL": "EMEA", "CZE": "EMEA", "TUR": "EMEA", "ISR": "EMEA",
    "ZAF": "EMEA",
}

# Lightweight sector lookup for the major intl tickers that matter most for
# heatmap signal. Empty sector means "Other" bucket.
SECTOR_BY_TICKER = {
    # Brazil
    "PETR4.SA": "Energy", "VALE3.SA": "Materials", "ITUB4.SA": "Financials",
    "BBDC4.SA": "Financials", "ABEV3.SA": "Consumer Staples",
    "MGLU3.SA": "Consumer Discretionary", "JBSS3.SA": "Consumer Staples",
    "BBAS3.SA": "Financials", "B3SA3.SA": "Financials", "WEGE3.SA": "Industrials",
    "SUZB3.SA": "Materials", "RENT3.SA": "Industrials", "EMBR3.SA": "Industrials",
    "ELET3.SA": "Utilities", "PRIO3.SA": "Energy", "RADL3.SA": "Consumer Staples",
    "RAIL3.SA": "Industrials", "LREN3.SA": "Consumer Discretionary",
    # Japan
    "7203.T": "Consumer Discretionary", "6758.T": "Information Technology",
    "9984.T": "Communication Services", "6861.T": "Information Technology",
    "8306.T": "Financials", "9432.T": "Communication Services",
    "7974.T": "Communication Services", "6098.T": "Industrials",
    "8035.T": "Information Technology", "4063.T": "Materials",
    "6501.T": "Industrials", "9433.T": "Communication Services",
    "8316.T": "Financials", "9020.T": "Industrials", "4502.T": "Health Care",
    "6594.T": "Industrials", "8058.T": "Industrials", "8001.T": "Industrials",
    "4661.T": "Consumer Discretionary", "4519.T": "Health Care",
    "4503.T": "Health Care", "6981.T": "Information Technology",
    "7741.T": "Health Care",
    # UK
    "SHEL.L": "Energy", "AZN.L": "Health Care", "HSBA.L": "Financials",
    "BP.L": "Energy", "ULVR.L": "Consumer Staples", "GSK.L": "Health Care",
    "RIO.L": "Materials", "BARC.L": "Financials", "LLOY.L": "Financials",
    "NWG.L": "Financials", "VOD.L": "Communication Services",
    "DGE.L": "Consumer Staples", "BATS.L": "Consumer Staples",
    "RKT.L": "Consumer Staples", "PRU.L": "Financials", "AAL.L": "Materials",
    "GLEN.L": "Materials", "REL.L": "Industrials", "EXPN.L": "Industrials",
    "CRH.L": "Materials",
    # India
    "RELIANCE.NS": "Energy", "TCS.NS": "Information Technology",
    "HDFCBANK.NS": "Financials", "INFY.NS": "Information Technology",
    "ICICIBANK.NS": "Financials", "HINDUNILVR.NS": "Consumer Staples",
    "ITC.NS": "Consumer Staples", "SBIN.NS": "Financials",
    "BHARTIARTL.NS": "Communication Services", "KOTAKBANK.NS": "Financials",
    "LT.NS": "Industrials", "ASIANPAINT.NS": "Materials",
    "AXISBANK.NS": "Financials", "MARUTI.NS": "Consumer Discretionary",
    "BAJFINANCE.NS": "Financials", "HCLTECH.NS": "Information Technology",
    "TITAN.NS": "Consumer Discretionary", "ULTRACEMCO.NS": "Materials",
    "WIPRO.NS": "Information Technology", "ADANIENT.NS": "Industrials",
    "NESTLEIND.NS": "Consumer Staples", "TATAMOTORS.NS": "Consumer Discretionary",
    "SUNPHARMA.NS": "Health Care",
    # Mexico
    "WALMEX.MX": "Consumer Staples", "AMXB.MX": "Communication Services",
    "GFNORTEO.MX": "Financials", "FEMSAUBD.MX": "Consumer Staples",
    "GMEXICOB.MX": "Materials", "BIMBOA.MX": "Consumer Staples",
    "CEMEXCPO.MX": "Materials",
    # Korea
    "005930.KS": "Information Technology", "000660.KS": "Information Technology",
    "035420.KS": "Communication Services", "207940.KS": "Health Care",
    "373220.KS": "Industrials", "005380.KS": "Consumer Discretionary",
    "051910.KS": "Materials", "006400.KS": "Information Technology",
    "105560.KS": "Financials", "055550.KS": "Financials",
    "035720.KS": "Communication Services",
    # Hong Kong / China
    "0700.HK": "Communication Services", "9988.HK": "Consumer Discretionary",
    "3690.HK": "Consumer Discretionary", "0939.HK": "Financials",
    "0941.HK": "Communication Services", "1299.HK": "Financials",
    "1398.HK": "Financials", "2318.HK": "Financials",
    "0883.HK": "Energy", "1810.HK": "Information Technology",
    "9618.HK": "Consumer Discretionary", "9999.HK": "Communication Services",
    "0388.HK": "Financials",
    "600519.SS": "Consumer Staples", "601398.SS": "Financials",
    "601318.SS": "Financials", "600036.SS": "Financials",
    "000858.SZ": "Consumer Staples", "002594.SZ": "Consumer Discretionary",
    "300750.SZ": "Industrials",
    # Taiwan
    "2330.TW": "Information Technology", "2317.TW": "Information Technology",
    "2454.TW": "Information Technology", "2412.TW": "Communication Services",
    "2882.TW": "Financials",
    # Germany
    "SAP.DE": "Information Technology", "SIE.DE": "Industrials",
    "DTE.DE": "Communication Services", "ALV.DE": "Financials",
    "BAS.DE": "Materials", "BMW.DE": "Consumer Discretionary",
    "MBG.DE": "Consumer Discretionary", "VOW3.DE": "Consumer Discretionary",
    "DBK.DE": "Financials", "BAYN.DE": "Health Care", "RWE.DE": "Utilities",
    "ADS.DE": "Consumer Discretionary", "MUV2.DE": "Financials",
    "DPW.DE": "Industrials", "IFX.DE": "Information Technology",
    # France
    "MC.PA": "Consumer Discretionary", "OR.PA": "Consumer Staples",
    "TTE.PA": "Energy", "SAN.PA": "Health Care", "BNP.PA": "Financials",
    "AIR.PA": "Industrials", "CS.PA": "Financials",
    "KER.PA": "Consumer Discretionary", "RMS.PA": "Consumer Discretionary",
    "EL.PA": "Health Care",
    # Switzerland
    "NESN.SW": "Consumer Staples", "ROG.SW": "Health Care",
    "NOVN.SW": "Health Care", "UBSG.SW": "Financials",
    "ABBN.SW": "Industrials",
    # Netherlands
    "ASML.AS": "Information Technology", "HEIA.AS": "Consumer Staples",
    "INGA.AS": "Financials", "ADYEN.AS": "Information Technology",
    "PHIA.AS": "Health Care",
    # Spain
    "SAN.MC": "Financials", "TEF.MC": "Communication Services",
    "IBE.MC": "Utilities", "BBVA.MC": "Financials",
    "ITX.MC": "Consumer Discretionary",
    # Italy
    "ENI.MI": "Energy", "ISP.MI": "Financials", "ENEL.MI": "Utilities",
    "UCG.MI": "Financials", "RACE.MI": "Consumer Discretionary",
    # Australia
    "BHP.AX": "Materials", "CBA.AX": "Financials", "CSL.AX": "Health Care",
    "NAB.AX": "Financials", "WBC.AX": "Financials", "ANZ.AX": "Financials",
    "WES.AX": "Consumer Discretionary", "WOW.AX": "Consumer Staples",
    "MQG.AX": "Financials", "FMG.AX": "Materials", "WDS.AX": "Energy",
    # Canada
    "RY.TO": "Financials", "SHOP.TO": "Information Technology",
    "TD.TO": "Financials", "ENB.TO": "Energy", "CNQ.TO": "Energy",
    "BNS.TO": "Financials", "BMO.TO": "Financials",
    # Singapore
    "D05.SI": "Financials", "U11.SI": "Financials", "O39.SI": "Financials",
    # Sweden
    "VOLV-B.ST": "Industrials", "ATCO-A.ST": "Industrials",
    "ERIC-B.ST": "Information Technology", "HM-B.ST": "Consumer Discretionary",
    # Norway
    "EQNR.OL": "Energy", "DNB.OL": "Financials",
    # Denmark
    "NOVO-B.CO": "Health Care", "MAERSK-B.CO": "Industrials",
    "VWS.CO": "Industrials",
    # Finland
    "NOKIA.HE": "Information Technology",
}


def main() -> int:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    if not GAPPERS.exists():
        print(f"missing {GAPPERS}")
        return 1

    rows: list[dict] = []
    with GAPPERS.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                r["gap_pct_f"] = float(r.get("gap_pct") or 0)
                r["vol_ratio_f"] = float(r.get("vol_ratio_20d") or 0)
                r["close_f"] = float(r.get("close") or 0)
            except ValueError:
                continue
            r["sector"] = SECTOR_BY_TICKER.get(r["ticker"], "Other")
            r["region"] = REGION_BY_ISO.get(r.get("country_iso", ""), "Other")
            rows.append(r)

    # Top gappers (signed by direction). Bump depth + guarantee at least
    # one row per country so every covered market is visible in the feed.
    sorted_up = sorted(rows, key=lambda r: -r["gap_pct_f"])
    sorted_down = sorted(rows, key=lambda r: r["gap_pct_f"])
    top_up = list(sorted_up[:60])
    top_down = list(sorted_down[:60])

    def _ensure_country_coverage(target: list, sorted_pool: list) -> list:
        seen = {r.get("country_iso") for r in target}
        for r in sorted_pool:
            iso = r.get("country_iso")
            if iso and iso not in seen and r.get("gap_pct_f") is not None:
                target.append(r)
                seen.add(iso)
        return target
    top_up = _ensure_country_coverage(top_up, sorted_up)
    top_down = _ensure_country_coverage(top_down, sorted_down)

    # Sector heatmap: avg gap by sector × region
    sector_by_region: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        sector_by_region[r["region"]][r["sector"]].append(r["gap_pct_f"])
    sector_heatmap = []
    for region, sectors in sector_by_region.items():
        for sector, gaps in sectors.items():
            if not gaps or sector == "Other":
                continue
            sector_heatmap.append({
                "region": region,
                "sector": sector,
                "avg_gap_pct": round(sum(gaps) / len(gaps), 2),
                "count": len(gaps),
                "movers_up": sum(1 for g in gaps if g >= 1),
                "movers_down": sum(1 for g in gaps if g <= -1),
            })
    sector_heatmap.sort(key=lambda x: abs(x["avg_gap_pct"]), reverse=True)

    # Sympathy chains: same country + same sector + same direction (≥1.5% same way, 2+ names)
    chains: dict = defaultdict(list)
    for r in rows:
        if abs(r["gap_pct_f"]) < 1.5 or r["sector"] == "Other":
            continue
        key = (r["country_iso"], r["sector"], "up" if r["gap_pct_f"] > 0 else "down")
        chains[key].append(r)
    sympathy = []
    for (iso, sector, direction), names in chains.items():
        if len(names) < 2:
            continue
        names.sort(key=lambda r: -abs(r["gap_pct_f"]))
        sympathy.append({
            "country_iso": iso,
            "country_full": names[0].get("country_full", ""),
            "sector": sector,
            "direction": direction,
            "count": len(names),
            "avg_gap_pct": round(
                sum(r["gap_pct_f"] for r in names) / len(names), 2),
            "tickers": [{
                "ticker": r["ticker"], "name": r.get("name", ""),
                "gap_pct": r["gap_pct_f"],
            } for r in names[:6]],
        })
    sympathy.sort(key=lambda x: (x["count"], abs(x["avg_gap_pct"])), reverse=True)

    # Country leaderboard: avg |gap| and explosive count
    by_country: dict = defaultdict(list)
    for r in rows:
        by_country[(r.get("country_iso", ""), r.get("country_full", ""))].append(r)
    country_board = []
    for (iso, name), names in by_country.items():
        gaps = [n["gap_pct_f"] for n in names]
        country_board.append({
            "country_iso": iso, "country_full": name,
            "tickers": len(names),
            "avg_abs_gap": round(sum(abs(g) for g in gaps) / max(1, len(gaps)), 2),
            "explosive": sum(1 for n in names if n.get("regime") == "explosive"),
            "tradable": sum(1 for n in names if n.get("regime") == "tradable"),
            "top_mover": (max(names, key=lambda n: abs(n["gap_pct_f"]))["ticker"]
                          if names else ""),
        })
    country_board.sort(
        key=lambda c: (c["explosive"], c["avg_abs_gap"]), reverse=True)

    # Cross-border: load if available
    cross_border_top = []
    if CROSSBORDER.exists():
        try:
            cb = json.loads(CROSSBORDER.read_text(encoding="utf-8"))
            cross_border_top = [
                s for s in (cb.get("top_setups") or [])
                if s.get("conviction") in ("STRONG", "TRADE")
            ][:10]
        except Exception:
            pass

    payload = {
        "generated_at": captured,
        "total_tickers": len(rows),
        "total_countries": len(by_country),
        "explosive_count": sum(1 for r in rows if r.get("regime") == "explosive"),
        "tradable_count": sum(1 for r in rows if r.get("regime") == "tradable"),
        "top_up": [{
            "ticker": r["ticker"], "name": r.get("name", ""),
            "country_full": r.get("country_full", ""),
            "country_iso": r.get("country_iso", ""),
            "currency": r.get("currency", ""),
            "close": r["close_f"], "gap_pct": r["gap_pct_f"],
            "vol_ratio": r["vol_ratio_f"], "regime": r.get("regime", ""),
            "sector": r["sector"], "region": r["region"],
        } for r in top_up],
        "top_down": [{
            "ticker": r["ticker"], "name": r.get("name", ""),
            "country_full": r.get("country_full", ""),
            "country_iso": r.get("country_iso", ""),
            "currency": r.get("currency", ""),
            "close": r["close_f"], "gap_pct": r["gap_pct_f"],
            "vol_ratio": r["vol_ratio_f"], "regime": r.get("regime", ""),
            "sector": r["sector"], "region": r["region"],
        } for r in top_down],
        "sector_heatmap": sector_heatmap[:24],
        "sympathy_chains": sympathy[:20],
        "country_board": country_board,
        "cross_border_top": cross_border_top,
    }
    OUT.write_text(json.dumps(payload, indent=2))

    print(f"intl_derived: {payload['total_tickers']} tickers / "
          f"{payload['total_countries']} countries | "
          f"sympathy={len(sympathy)} | sector_cells={len(sector_heatmap)} | "
          f"explosive={payload['explosive_count']} | "
          f"crossborder={len(cross_border_top)}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
