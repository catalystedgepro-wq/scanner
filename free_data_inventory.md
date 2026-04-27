# Free Data Inventory — Catalyst Edge Scanner

**Wired:** 2026-04-18. Stdlib-only Python (no pip). All scripts write CSV to
`/home/operator/.openclaw/workspace/` and are invoked by
`run_daily_sec_catalyst.sh` prior to `generate_seo_site.py`.

## By Category

### Government Releases

| Spoke | CSV | Source | Cadence | Status |
|-------|-----|--------|---------|--------|
| `build_dod_contracts.py` | `dod_contracts.csv` | USASpending.gov REST | Daily | ✅ live |
| `build_cftc_cot.py` | `cftc_cot.csv` | CFTC Socrata `6dca-aqww` | Weekly (Fri) | ✅ live |
| `build_eia_petroleum.py` | `eia_petroleum.csv` | EIA v2 API | Weekly (Wed) | ⚠️ needs `EIA_API_KEY` |
| `build_fed_h41.py`-equivalent via `build_fred_macro.py` | `fred_macro.csv` | FRED / fredgraph.csv | Daily | ✅ live |
| `build_bls_calendar.py` | `bls_calendar.csv` | Computed (BLS Akamai-blocks bots) | Monthly | ✅ computed |
| `build_ism_adp.py` | `ism_adp.csv` | Computed (ISM/Conference Board schedule) | Monthly | ✅ computed |
| `build_fomc_calendar.py` | `fomc_calendar.csv` + `fomc_statement_latest.txt` | federalreserve.gov | 8×/yr | ✅ live |
| `build_treasury_ofac.py` | `treasury_ofac.csv` | TreasuryDirect + OFAC SDN | Daily | ✅ live |
| `build_usda_wasde.py` | `usda_wasde.csv` | Computed (WASDE monthly schedule) | Monthly | ✅ computed |
| `build_fda_pdufa.py` | `fda_pdufa.csv` | FDA advisory calendar | Weekly | ✅ live |
| `build_tsa_volume.py` | `tsa_volume.csv` | TSA (Akamai-blocked) | Daily | ⚠️ stub only |
| `build_opensecrets.py` | `opensecrets.csv` | FEC Schedule B API | Daily | ✅ live (DEMO_KEY) |
| `build_uspto_feed.py` | `uspto_feed.csv` | PatentsView API | Daily | ⚠️ needs `PATENTSVIEW_API_KEY` |
| `build_clinical_trials.py` | `clinical_trials.csv` | ClinicalTrials.gov v2 API | Daily | ✅ live |

### Exchange / Filings Data

| Spoke | CSV | Source | Cadence | Status |
|-------|-----|--------|---------|--------|
| `build_earnings_calendar.py` | `earnings_calendar.csv` | api.nasdaq.com | Daily | ✅ live |
| `build_13f_whales.py` | `13f_whales.csv` | EDGAR 13F-HR atom | Quarterly | ✅ live |
| `build_form_144.py` | `form_144.csv` | EDGAR Form 144 atom | Daily | ✅ live |
| `build_edgar_fulltext.py` | `edgar_fulltext_hits.csv` | efts.sec.gov | Daily | ✅ live |
| `build_regsho_threshold.py` | `regsho_threshold.csv` | FINRA Reg SHO list | Daily | ✅ live |
| `build_sedar_canada.py` | `sedar_canada.csv` | sedarplus.ca public filings | Daily | ✅ live |
| `build_courtlistener_recap.py` | `courtlistener_recap.csv` | CourtListener v4 API | Daily | ✅ live |

### Social / Wire Signal

| Spoke | CSV | Source | Cadence | Status |
|-------|-----|--------|---------|--------|
| `build_press_wires.py` | `press_wires.csv` | 4 wire RSS feeds | Intraday | ✅ live |
| `build_stocktwits_trending.py` | `stocktwits_trending.csv` | StockTwits /trending | Intraday | ✅ live |
| `build_reddit_velocity.py` | `reddit_velocity.csv` | apewisdom.io (reddit agg) | Intraday | ✅ live |
| `build_google_trends.py` | `google_trends.csv` | Wikipedia pageviews proxy | Daily | ✅ live |
| `build_arxiv_cashtag.py` | `arxiv_cashtag.csv` | arxiv.org API | Daily | ✅ live |
| `build_github_velocity.py` | `github_velocity.csv` | GitHub events API | Daily | ✅ live (60/hr unauth) |

### Alternative Data

| Spoke | CSV | Source | Cadence | Status |
|-------|-----|--------|---------|--------|
| `build_adsb_jets.py` | `adsb_jets.csv` | OpenSky Network | Intraday | ⚠️ stub (timeout-prone) |
| `build_crypto_correlation.py` | `crypto_correlation.csv` | CoinGecko /coins/markets | Intraday | ✅ live |

## Optional API Keys (all degrade gracefully)

| Env var | Enables | Fallback behavior |
|---------|---------|-------------------|
| `EIA_API_KEY` | Weekly petroleum all 9 series | DEMO_KEY: 3/9 series (rate-limited) |
| `FRED_API_KEY` | FRED JSON API | fredgraph.csv CSV (same data) |
| `PATENTSVIEW_API_KEY` | USPTO patent filings | Emits empty CSV |
| `GITHUB_TOKEN` | 5k req/hr | 60/hr unauth (32 orgs fit) |
| `COURTLISTENER_TOKEN` | Auth'd search | Works unauth (20 results) |
| `FEC_API_KEY` | Full FEC data | DEMO_KEY (60 filings) |

## Blockers / Known Gaps

- **TSA passenger volume** — Akamai blocks both direct and Wayback fetches from
  datacenter IPs. Needs residential proxy or alternative source.
- **BusinessWire RSS** — 403 for datacenter IPs; other 3 wires (PRNewswire,
  GlobeNewswire, Accesswire) work.
- **USPTO PatentsView** — API now requires X-Api-Key header as of 2025.
- **BLS schedule page** — Akamai-blocked; computed schedule is authoritative
  fallback (cadence rules are published BLS policy).

## Integration Points

All spokes run **before** `generate_seo_site.py` in the pipeline so their CSVs
are live artifacts when the static site renders. Scanner display and
convergence scoring both read from these CSVs.

Pipeline line references (run_daily_sec_catalyst.sh):
- New block: lines 444–474 (Free-Data Wiring Sprint)
- `generate_seo_site.py` call: line 477
