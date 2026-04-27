"""
build_convergence_score.py — THE MASTER SIGNAL. Combines all pipeline layers.
Output: convergence_alerts.csv
"""

import csv
import datetime
from pathlib import Path

ROOT = Path(__file__).parent
OUTPUT_FILE = ROOT / "convergence_alerts.csv"

CONVICTION_ORDER = {"MAXIMUM": 0, "HIGH": 1, "ELEVATED": 2, "WATCH": 3, "AVOID": 4}

def load_csv_as_dict(filename, key_col="ticker"):
    """Load a CSV file as dict keyed by key_col. Returns {} on missing file."""
    path = ROOT / filename
    result = {}
    if not path.exists():
        print(f"  [SKIP] {filename} not found")
        return result
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                k = row.get(key_col, "").strip()
                if k:
                    result[k] = row
        print(f"  Loaded {filename}: {len(result)} rows")
    except Exception as e:
        print(f"  [WARN] Could not load {filename}: {e}")
    return result

def load_csv_multi(filename, key_col="ticker"):
    """Load CSV as dict of lists (multiple rows per key)."""
    path = ROOT / filename
    result = {}
    if not path.exists():
        print(f"  [SKIP] {filename} not found")
        return result
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                k = row.get(key_col, "").strip()
                if k:
                    result.setdefault(k, []).append(row)
        print(f"  Loaded {filename}: {len(result)} unique tickers")
    except Exception as e:
        print(f"  [WARN] Could not load {filename}: {e}")
    return result

def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

def main():
    print("Loading all signal layers...")

    # Load all layers
    combined    = load_csv_as_dict("combined_priority.csv")
    deepvalue   = load_csv_as_dict("deepvalue_screen.csv")
    smart_money = load_csv_as_dict("smart_money.csv")
    nt_radar    = load_csv_as_dict("nt_radar.csv")
    dark_pool   = load_csv_as_dict("dark_pool.csv")
    mergers     = load_csv_as_dict("merger_signals.csv")
    lockup      = load_csv_as_dict("lockup_calendar.csv")
    inflection  = load_csv_as_dict("revenue_inflection.csv")
    squeeze     = load_csv_as_dict("squeeze_candidates.csv")
    insider     = load_csv_as_dict("insider_clusters.csv")
    options     = load_csv_as_dict("options_flow.csv")
    keyword_multi = load_csv_multi("keyword_hits.csv")
    sec_multi     = load_csv_multi("sec_catalyst_latest.csv")
    alpha_factors = load_csv_as_dict("alpha_factors.csv")
    cve_multi     = load_csv_multi("cve_velocity.csv")
    earnings_cal  = load_csv_as_dict("earnings_calendar.csv")
    going_concern = load_csv_as_dict("going_concern.csv")
    regsho        = load_csv_as_dict("regsho_threshold.csv")
    reddit_vel    = load_csv_as_dict("reddit_velocity.csv")
    wiki_attn     = load_csv_as_dict("wiki_attention.csv")
    finra_short   = load_csv_multi("finra_short_volume.csv")
    form144       = load_csv_multi("form144_filings.csv")
    nhtsa         = load_csv_multi("nhtsa_recalls.csv")
    cfpb          = load_csv_as_dict("cfpb_complaints.csv")
    crypto_tr     = load_csv_as_dict("crypto_treasury.csv")
    openfda       = load_csv_as_dict("openfda_adverse.csv")
    gtrends       = load_csv_as_dict("google_trends.csv")
    edgar_ft      = load_csv_multi("edgar_fulltext_hits.csv")
    stocktwits    = load_csv_as_dict("stocktwits_trending.csv")
    wsb           = load_csv_as_dict("wsb_mentions.csv")
    av_movers     = load_csv_as_dict("av_movers.csv")
    gap_scan      = load_csv_as_dict("gap_scanner.csv")
    short_data    = load_csv_as_dict("short_data.csv")
    usa_spend     = load_csv_as_dict("usa_spending.csv")
    github_vel    = load_csv_as_dict("github_velocity.csv")
    finra_regsho  = load_csv_as_dict("finra_reg_sho.csv", key_col="symbol")
    arxiv         = load_csv_multi("arxiv_cashtag.csv", key_col="ticker_guess")
    asx           = load_csv_multi("asx_announcements.csv")
    halts         = load_csv_multi("nasdaq_halts.csv", key_col="symbol")
    hn_attn       = load_csv_multi("hnews_attention.csv", key_col="tickers")
    # New SEC-derived ticker-column spokes
    sec_buybacks  = load_csv_as_dict("sec_buybacks.csv")
    sec_contracts = load_csv_multi("sec_contracts.csv")
    sec_tender    = load_csv_as_dict("sec_tender.csv", key_col="target_ticker")
    sec_m_proxy   = load_csv_as_dict("sec_merger_proxy.csv")
    sec_splits    = load_csv_multi("sec_splits.csv")
    sec_distress  = load_csv_multi("sec_distress.csv")
    sec_biotech   = load_csv_multi("sec_biotech.csv")
    sec_fda_cat   = load_csv_multi("sec_fda.csv")
    sec_ftd       = load_csv_multi("sec_ftd.csv", key_col="symbol")
    sec_uplist    = load_csv_as_dict("sec_uplist.csv")
    sec_pill      = load_csv_multi("sec_poison_pill.csv")
    sec_crypto_cat= load_csv_multi("sec_crypto.csv")
    sec_13d_rows  = load_csv_multi("sec_13d_filings.csv")
    sec_bankruptcy= load_csv_multi("sec_bankruptcy.csv")
    sec_delisting = load_csv_multi("sec_delisting.csv", key_col="cik")
    sec_xbrl_dcf  = load_csv_as_dict("sec_xbrl_dcf.csv")

    # Macro signal ingestion → sector lean dict
    def load_list(filename):
        path = ROOT / filename
        if not path.exists():
            return []
        try:
            with open(path, newline="") as f:
                return list(csv.DictReader(f))
        except Exception:
            return []

    kalshi_rows  = load_list("kalshi_macro.csv")
    fed_test     = load_list("fed_testimony.csv")
    fed_enforce  = load_list("fed_enforcement.csv")
    occ_rows     = load_list("occ.csv")
    fred_rows    = load_list("fred_macro.csv")
    gdacs_rows   = load_list("gdacs_disasters.csv")
    paho_rows    = load_list("paho.csv")
    ustr_rows    = load_list("ustr.csv")
    usitc_rows   = load_list("usitc.csv")
    ftc_rows     = load_list("ftc.csv")
    doj_rows     = load_list("doj.csv")
    ferc_rows    = load_list("ferc.csv")
    cftc_rows    = load_list("cftc.csv")
    osha_rows    = load_list("osha.csv")
    fcc_rows     = load_list("fcc.csv")
    cfpb_rule_rows = load_list("cfpb_rules.csv")
    cfpb_enf_rows  = load_list("cfpb_enforcement.csv")

    # Sector tickers
    SECTOR_TICKERS = {
        "energy_crude":  ["XLE", "USO", "XOM", "CVX", "COP", "OXY", "PSX", "VLO", "MPC"],
        "energy_natgas": ["UNG", "BOIL", "EQT", "AR", "CHK", "CTRA", "RRC"],
        "gold":          ["GLD", "IAU", "NEM", "GOLD", "AEM", "FNV", "WPM"],
        "crypto":        ["IBIT", "MSTR", "COIN", "MARA", "RIOT", "HUT", "CLSK"],
        "banks":         ["XLF", "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC", "SCHW", "KBE", "KRE"],
        "semis":         ["SMH", "NVDA", "AMD", "INTC", "MU", "AVGO", "TSM", "QCOM", "AMAT", "LRCX", "KLAC"],
        "defense":       ["LMT", "BA", "RTX", "GD", "NOC", "LHX", "LDOS", "HII"],
        "insurance":     ["ALL", "AIG", "PGR", "TRV", "CINF", "HIG", "MET", "PRU", "RNR"],
        "pharma":        ["PFE", "MRK", "JNJ", "LLY", "ABBV", "AMGN", "GILD", "BMY", "XBI", "IBB"],
        "utilities":     ["XLU", "NEE", "DUK", "SO", "AEP", "D", "EXC", "SRE", "PEG", "XEL"],
        "reits":         ["VNQ", "AMT", "PLD", "EQIX", "CCI", "PSA", "WELL", "O", "SPG", "DLR"],
        "tech_mega":     ["XLK", "QQQ", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NFLX", "TSLA", "CRM"],
        "industrials":   ["XLI", "CAT", "DE", "HON", "UPS", "GE", "MMM", "UNP", "LMT", "BA"],
        "retail":        ["XRT", "WMT", "COST", "HD", "LOW", "TGT", "AMZN", "TJX", "DG", "DLTR"],
        "china":         ["FXI", "KWEB", "BABA", "JD", "PDD", "NIO", "LI", "XPEV", "BIDU"],
        "clean_energy":  ["ICLN", "TAN", "ENPH", "SEDG", "FSLR", "RUN", "NEE", "PLUG"],
        "biotech":       ["XBI", "IBB", "LABU", "MRNA", "BIIB", "REGN", "VRTX", "GILD", "AMGN"],
    }

    def macro_sector_lean():
        """Compute sector-level lean points from all macro sources."""
        lean = {s: 0 for s in SECTOR_TICKERS.keys()}
        # Kalshi commodity contracts
        for r in kalshi_rows:
            cat = r.get("category", "").lower()
            title = r.get("title", "").lower()
            prob = safe_float(r.get("prob_yes", 0))
            # "Will crude exports be below X" YES prob → bearish supply = bullish oil
            if cat == "commodity":
                if "crude" in title or "oil" in title:
                    if "below" in title and prob >= 0.6:
                        lean["energy_crude"] += 1
                    elif "above" in title and prob >= 0.6:
                        lean["energy_crude"] -= 1
                elif "gold" in title and "above" in title and prob >= 0.6:
                    lean["gold"] += 1
                elif "gas" in title or "natural gas" in title:
                    if "below" in title and prob >= 0.6:
                        lean["energy_natgas"] += 1
            elif cat == "crypto":
                if "above" in title and prob >= 0.6:
                    lean["crypto"] += 1
                elif "below" in title and prob >= 0.6:
                    lean["crypto"] -= 1
        # Fed testimony + enforcement → banks sentiment
        banks_pressure = 0
        for r in fed_test + fed_enforce + occ_rows:
            kind = r.get("kind", "").lower()
            title = (r.get("title", "") + " " + r.get("entity", "")).lower()
            if "enforcement" in kind or "bulletin" in kind or "capital" in kind:
                banks_pressure += 1
            if "digital_assets" in kind or "crypto" in title or "digital asset" in title:
                lean["crypto"] += 1
        if banks_pressure >= 3:
            lean["banks"] -= 1  # regulatory overhang
        # Fed balance sheet — WALCL rising = liquidity tailwind
        for r in fred_rows:
            if r.get("series") == "WALCL":
                chg = safe_float(r.get("change_pct", 0))
                if chg >= 0.2:  # rising
                    lean["crypto"] += 1
                    lean["semis"] += 1
                elif chg <= -0.2:
                    lean["crypto"] -= 1
                    lean["semis"] -= 1
                break
        # GDACS disasters → insurance pressure, energy storms
        red_alerts = sum(1 for r in gdacs_rows if r.get("alert_level", "").lower() == "red")
        if red_alerts >= 3:
            lean["insurance"] -= 2
            lean["energy_crude"] += 1  # supply disruption premium
        elif red_alerts >= 1:
            lean["insurance"] -= 1
        # PAHO Americas public health → pharma / biotech demand
        pharma_pressure = 0
        for r in paho_rows:
            kind = r.get("kind", "").lower()
            if kind in ("vaccine_immunization", "outbreak_epidemic", "mpox_orthopox",
                        "hiv_aids_sti", "tuberculosis_tb", "antimicrobial_resistance"):
                pharma_pressure += 1
            elif kind == "noncommunicable_disease":
                pharma_pressure += 1  # GLP-1 / oncology demand
        if pharma_pressure >= 3:
            lean["pharma"] += 2
            lean["biotech"] += 1
        elif pharma_pressure >= 1:
            lean["pharma"] += 1
        # USTR trade policy → sector-specific tariff lean
        for r in ustr_rows:
            kind = r.get("kind", "").lower()
            if kind in ("section_301_china", "china_bilateral"):
                lean["china"] -= 1
                lean["semis"] -= 1  # export-control overhang
            elif kind == "section_232_steel":
                lean["industrials"] += 1  # domestic steel primes
            elif kind == "section_201_solar":
                lean["clean_energy"] += 1  # domestic solar premium
            elif kind == "uflpa_forced_labor":
                lean["china"] -= 1
                lean["clean_energy"] += 1  # polysilicon reshoring
            elif kind == "critical_minerals":
                lean["clean_energy"] += 1  # US miners / EV supply chain
            elif kind == "ag_retaliation":
                lean["retail"] -= 1  # consumer-goods ag pass-through
            elif kind == "digital_trade":
                lean["tech_mega"] += 1  # US big-tech cross-border position
        # USITC quasi-judicial trade rulings → sector lean
        for r in usitc_rows:
            kind = r.get("kind", "").lower()
            if kind in ("ad_china", "cvd_china"):
                lean["china"] -= 1
                lean["industrials"] += 1  # domestic producers benefit
            elif kind in ("ad_other", "cvd_other"):
                lean["industrials"] += 1
            elif kind == "section_337_ip":
                lean["tech_mega"] += 1  # IP moat win for complainant
            elif kind == "section_201_safeguard":
                lean["clean_energy"] += 1  # typical solar safeguard
            elif kind == "critical_mineral":
                lean["clean_energy"] += 1
            elif kind == "steel_aluminum":
                lean["industrials"] += 1
            elif kind == "determination_affirmative":
                lean["industrials"] += 1
            elif kind == "determination_negative":
                lean["industrials"] -= 1  # revocation bearish for protected US firms
        # FTC antitrust / consumer-protection actions
        for r in ftc_rows:
            kind = r.get("kind", "").lower()
            if kind in ("merger_challenge", "merger_consent", "merger_abandoned"):
                lean["tech_mega"] -= 1  # mega-deal blocked overhang
            elif kind == "monopoly_case":
                lean["tech_mega"] -= 1
            elif kind == "crypto_enforcement":
                lean["crypto"] -= 1
            elif kind == "price_fixing":
                lean["industrials"] -= 1
        # DOJ Antitrust Division + criminal enforcement
        for r in doj_rows:
            kind = r.get("kind", "").lower()
            if kind in ("merger_enforcement", "antitrust_final_judgment",
                        "antitrust_consent"):
                lean["tech_mega"] -= 1  # deal overhang resolved (often clears)
                lean["industrials"] -= 1
            elif kind in ("fcpa_settlement", "false_claims_act", "dpa_nap"):
                lean["industrials"] -= 1  # corporate penalty drag
            elif kind == "healthcare_fraud":
                lean["pharma"] -= 1
            elif kind == "drug_scheduling":
                lean["pharma"] += 1  # often opens pharmacotherapy market
            elif kind == "financial_fraud":
                lean["banks"] -= 1
            elif kind == "sanctions_designation":
                lean["china"] -= 1
                lean["energy_crude"] += 1  # supply-side premium
        # FERC energy regulatory actions
        for r in ferc_rows:
            kind = r.get("kind", "").lower()
            if kind == "lng_export_auth":
                lean["energy_natgas"] += 1  # midstream LNG tailwind
            elif kind == "pipeline_certificate":
                lean["energy_natgas"] += 1
                lean["energy_crude"] += 1  # midstream unlock
            elif kind == "pipeline_abandon":
                lean["energy_natgas"] -= 1
            elif kind == "hydro_license":
                lean["utilities"] += 1
            elif kind == "der_order_2222":
                lean["clean_energy"] += 1  # DER aggregator unlock
            elif kind == "offshore_wind":
                lean["clean_energy"] += 1
            elif kind == "enforcement_action":
                lean["utilities"] -= 1
            elif kind == "capacity_market":
                lean["utilities"] += 1
        # CFTC derivatives & enforcement
        for r in cftc_rows:
            kind = r.get("kind", "").lower()
            if kind == "crypto_derivatives":
                lean["crypto"] += 1  # ETF/futures approval typically bullish
            elif kind in ("spoofing_enforcement", "market_manipulation",
                          "enforcement_penalty"):
                lean["banks"] -= 1  # prop-desk drag
            elif kind == "position_limits":
                lean["energy_crude"] -= 1  # tighter = reduced speculative flow
            elif kind == "swap_dealer":
                lean["banks"] -= 1  # capital burden
        # OSHA safety enforcement
        for r in osha_rows:
            kind = r.get("kind", "").lower()
            if kind in ("severe_injury", "willful_violation", "citation_penalty"):
                lean["industrials"] -= 1
            elif kind == "heat_standard":
                lean["industrials"] -= 1  # labor cost pass-through
            elif kind in ("process_safety_mgmt", "toxic_substance"):
                lean["energy_crude"] -= 1  # refiner compliance drag
            elif kind == "national_emphasis":
                lean["industrials"] -= 1  # inspection surge industry-wide
        # FCC telecom & media
        for r in fcc_rows:
            kind = r.get("kind", "").lower()
            if kind == "spectrum_auction":
                lean["tech_mega"] += 1  # carrier capex + 5G enabler
            elif kind == "net_neutrality":
                lean["tech_mega"] -= 1  # ISP reclassification drag
            elif kind == "huawei_zte_security":
                lean["china"] -= 1
                lean["semis"] += 1  # domestic semi tailwind
            elif kind == "section_230":
                lean["tech_mega"] -= 1  # platform liability
            elif kind in ("rural_digital_rdof", "universal_service"):
                lean["tech_mega"] += 1
            elif kind == "license_transfer" or kind == "merger_review":
                lean["tech_mega"] += 1  # deal-unlock
            elif kind == "satellite_license":
                lean["defense"] += 1  # satellite primes
        # CFPB rules → consumer-finance sector lean
        # Regulatory tightening is bearish for retail banks, card issuers, BNPL.
        for r in cfpb_rule_rows:
            kind = r.get("kind", "").lower()
            if kind in ("udaap_enforcement", "consent_order", "cid_investigation"):
                lean["banks"] -= 1  # firm-specific consent overhang bleeds to peers
            elif kind in ("late_fee_cap", "overdraft_rule", "nsf_fee"):
                lean["banks"] -= 1  # fee-income hit
            elif kind in ("mortgage_reg_z", "reg_z_amendment"):
                lean["banks"] -= 1
                lean["reits"] -= 1  # housing-credit drag
            elif kind in ("bnpl_rule", "credit_card_rule"):
                lean["banks"] -= 1  # COF/SYF/DFS/AXP
            elif kind in ("fair_lending", "ecoa_rule", "disparate_impact"):
                lean["banks"] -= 1
            elif kind == "open_banking_1033":
                lean["tech_mega"] += 1  # fintech data portability tailwind
            elif kind == "crypto_consumer_protection":
                lean["crypto"] -= 1
        # Normalize lean to [-3, +3] range
        for k in lean:
            if lean[k] > 3:
                lean[k] = 3
            elif lean[k] < -3:
                lean[k] = -3
        return lean

    SECTOR_LEAN = macro_sector_lean()
    # F-13 fix (2026-04-24): build a sector LIST per ticker instead of a single
    # mapping. Prior version overwrote earlier sectors (AMZN tech_mega → retail,
    # GILD pharma → biotech, LMT defense → industrials, NEE utilities → clean),
    # losing cross-exposure. Now lean sums across all matched sectors.
    TICKER_SECTORS = {}
    for sector, tickers in SECTOR_TICKERS.items():
        for t in tickers:
            TICKER_SECTORS.setdefault(t, []).append(sector)
    # Keep legacy name for the "primary sector" label in output CSV.
    TICKER_TO_SECTOR = {t: secs[0] for t, secs in TICKER_SECTORS.items()}
    print(f"  Macro sector lean computed: {dict((k, v) for k, v in SECTOR_LEAN.items() if v != 0)}")

    # Sponsor → ticker map (pharma + defense)
    SPONSOR_TICKER_MAP = {
        "pfizer": "PFE", "merck": "MRK", "johnson & johnson": "JNJ", "janssen": "JNJ",
        "novartis": "NVS", "roche": "RHHBY", "genentech": "RHHBY", "astrazeneca": "AZN",
        "bristol-myers squibb": "BMY", "bristol myers": "BMY", "eli lilly": "LLY",
        "glaxosmithkline": "GSK", "gsk": "GSK", "sanofi": "SNY", "abbvie": "ABBV",
        "amgen": "AMGN", "gilead": "GILD", "vertex": "VRTX", "biogen": "BIIB",
        "regeneron": "REGN", "moderna": "MRNA", "biontech": "BNTX", "novo nordisk": "NVO",
        "bayer": "BAYRY", "takeda": "TAK", "mylan": "VTRS", "viatris": "VTRS", "teva": "TEVA",
        "haleon": "HLN", "corcept": "CORT", "jazz": "JAZZ", "novavax": "NVAX",
        "insmed": "INSM", "biomarin": "BMRN", "hologic": "HOLX", "abbott": "ABT",
        "alnylam": "ALNY", "incyte": "INCY", "bio-rad": "BIO", "seagen": "SGEN",
        "horizon": "HZNP", "exelixis": "EXEL", "sarepta": "SRPT", "blueprint": "BPMC",
        "ionis": "IONS", "alkermes": "ALKS", "halozyme": "HALO", "zoetis": "ZTS",
        "lockheed martin": "LMT", "boeing": "BA", "raytheon": "RTX", "rtx": "RTX",
        "general dynamics": "GD", "northrop grumman": "NOC", "l3harris": "LHX",
        "leidos": "LDOS", "huntington ingalls": "HII", "bae systems": "BAESY",
        "booz allen": "BAH", "saic": "SAIC", "caci": "CACI", "kratos": "KTOS",
        "mercury systems": "MRCY", "palantir": "PLTR", "textron": "TXT",
    }

    def map_sponsor(name):
        """Return ticker if name matches a known sponsor, else None."""
        if not name:
            return None
        lower = name.lower()
        for key, tkr in SPONSOR_TICKER_MAP.items():
            if key in lower:
                return tkr
        return None

    # Build clinicaltrials signal: ticker → count of recent P2/P3 trials
    clinical_pts_by_ticker = {}
    if (ROOT / "clinicaltrials.csv").exists():
        try:
            with open(ROOT / "clinicaltrials.csv", newline="") as f:
                for row in csv.DictReader(f):
                    t = map_sponsor(row.get("sponsor", ""))
                    if not t:
                        continue
                    phase = row.get("phase", "")
                    if "P3" in phase:
                        clinical_pts_by_ticker[t] = clinical_pts_by_ticker.get(t, 0) + 2
                    elif "P2" in phase:
                        clinical_pts_by_ticker[t] = clinical_pts_by_ticker.get(t, 0) + 1
            print(f"  clinical sponsor map: {len(clinical_pts_by_ticker)} tickers scored")
        except Exception as e:
            print(f"  [WARN] clinicaltrials sponsor map: {e}")

    # Build FDA approvals signal: ticker → approval count
    fda_approvals_by_ticker = {}
    if (ROOT / "fda_approvals.csv").exists():
        try:
            with open(ROOT / "fda_approvals.csv", newline="") as f:
                for row in csv.DictReader(f):
                    t = map_sponsor(row.get("sponsor_name", ""))
                    if not t:
                        continue
                    status = row.get("submission_status", "")
                    if status == "AP":  # Approved
                        fda_approvals_by_ticker[t] = fda_approvals_by_ticker.get(t, 0) + 1
            print(f"  FDA sponsor map: {len(fda_approvals_by_ticker)} tickers scored")
        except Exception as e:
            print(f"  [WARN] fda_approvals sponsor map: {e}")

    # CFPB enforcement defendant → ticker map (consumer-finance + big banks + cards)
    CFPB_DEFENDANT_MAP = {
        "wells fargo": "WFC", "bank of america": "BAC", "citibank": "C", "citigroup": "C",
        "jpmorgan": "JPM", "jp morgan": "JPM", "td bank": "TD", "pnc": "PNC",
        "u.s. bank": "USB", "us bank": "USB", "truist": "TFC", "goldman sachs": "GS",
        "morgan stanley": "MS", "capital one": "COF", "discover": "DFS", "synchrony": "SYF",
        "ally": "ALLY", "american express": "AXP", "amex": "AXP", "paypal": "PYPL",
        "affirm": "AFRM", "block": "SQ", "square": "SQ", "apple inc": "AAPL",
        "coinbase": "COIN", "robinhood": "HOOD", "sofi": "SOFI", "lendingclub": "LC",
        "upstart": "UPST", "rocket mortgage": "RKT", "quicken loans": "RKT",
        "new day financial": "NEWT", "equifax": "EFX", "experian": "EXPGY",
        "transunion": "TRU", "intuit": "INTU", "credit karma": "INTU",
        "nordstrom": "JWN", "macys": "M", "target": "TGT", "walmart": "WMT",
    }

    def map_cfpb_defendant(name):
        if not name:
            return None
        lower = name.lower()
        for key, tkr in CFPB_DEFENDANT_MAP.items():
            if key in lower:
                return tkr
        return None

    # Build CFPB enforcement signal: ticker → count of recent actions (bearish)
    cfpb_enf_by_ticker = {}
    for row in cfpb_enf_rows:
        t = map_cfpb_defendant(row.get("defendant", ""))
        if not t:
            continue
        cfpb_enf_by_ticker[t] = cfpb_enf_by_ticker.get(t, 0) + 1
    if cfpb_enf_by_ticker:
        print(f"  CFPB enforcement map: {len(cfpb_enf_by_ticker)} tickers flagged")

    # Build DoD contracts signal: ticker → total $ awarded
    dod_by_ticker = {}
    if (ROOT / "dod_contracts.csv").exists():
        try:
            with open(ROOT / "dod_contracts.csv", newline="") as f:
                for row in csv.DictReader(f):
                    t = row.get("ticker_guess", "").strip() or map_sponsor(row.get("firm", ""))
                    if not t:
                        continue
                    amt = safe_float(row.get("amount_usd", 0))
                    dod_by_ticker[t] = dod_by_ticker.get(t, 0) + amt
            print(f"  DoD contracts map: {len(dod_by_ticker)} tickers scored")
        except Exception as e:
            print(f"  [WARN] dod_contracts sponsor map: {e}")

    # Positive keywords for bonus scoring
    POSITIVE_KEYWORDS = {
        "record revenue", "raises guidance", "earnings beat", "positive results",
        "fda approval", "fda clearance", "breakthrough therapy", "contract award",
        "clinical trial results"
    }

    # Expand universe: combined_priority + high-signal tickers from other sources
    universe_set = set(combined.keys())
    for src_name, src_data in [
        ("gap_scanner", gap_scan),
        ("regsho", regsho),
        ("av_movers", av_movers),
        ("form144", form144),
        ("going_concern", going_concern),
        ("squeeze", squeeze),
        ("insider", insider),
        ("deepvalue", deepvalue),
        ("smart_money", smart_money),
        ("dark_pool", dark_pool),
        ("merger", mergers),
        ("nt_radar", nt_radar),
        ("sec_buybacks", sec_buybacks),
        ("sec_contracts", sec_contracts),
        ("sec_tender", sec_tender),
        ("sec_m_proxy", sec_m_proxy),
        ("sec_splits", sec_splits),
        ("sec_distress", sec_distress),
        ("sec_biotech", sec_biotech),
        ("sec_fda_cat", sec_fda_cat),
        ("sec_ftd", sec_ftd),
        ("sec_uplist", sec_uplist),
        ("sec_pill", sec_pill),
        ("sec_crypto_cat", sec_crypto_cat),
        ("sec_13d", sec_13d_rows),
    ]:
        for t in src_data.keys():
            if t and t.isalpha() and 1 <= len(t) <= 5:
                universe_set.add(t)
    # Top-N retail-attention tickers
    def top_by(d, key, n):
        scored = []
        for t, row in d.items():
            try:
                v = float(row.get(key, 0))
                scored.append((v, t))
            except (ValueError, TypeError):
                pass
        scored.sort(reverse=True)
        return [t for _, t in scored[:n] if t.isalpha() and 1 <= len(t) <= 5]
    for t in top_by(reddit_vel, "mentions", 60):
        universe_set.add(t)
    for t in top_by(wsb, "mention_count_24h", 30):
        universe_set.add(t)
    # Pull sponsor-mapped tickers into universe
    universe_set.update(clinical_pts_by_ticker.keys())
    universe_set.update(fda_approvals_by_ticker.keys())
    universe_set.update(dod_by_ticker.keys())
    for t in halts.keys():
        if t and t.isalpha() and 1 <= len(t) <= 5:
            universe_set.add(t)
    # Add all sector-ETF tickers so macro lean propagates
    for tickers in SECTOR_TICKERS.values():
        universe_set.update(tickers)
    universe = sorted(universe_set)
    print(f"\nScoring {len(universe)} tickers (expanded from {len(combined)} in combined_priority)")

    results = []
    for ticker in universe:
        cp = combined.get(ticker, {})

        # --- SEC Catalyst layer ---
        sec_pts = 0
        sec_rows = sec_multi.get(ticker, [])
        if sec_rows:
            # Check recency
            for row in sec_rows:
                recency = safe_float(row.get("recency_min", 9999))
                g = safe_float(row.get("gapper_score", 0))
                v = safe_float(row.get("value_score", 0))
                m = safe_float(row.get("moat_score", 0))
                if recency < 480 and (g + v + m) > 10:
                    sec_pts = 15
                    break

        # --- Insider layer ---
        ins_pts = 0
        ins_row = insider.get(ticker, {})
        if ins_row:
            confirmed = ins_row.get("confirmed_buy", "0").strip()
            filing_count = safe_int(ins_row.get("filing_count", 0))
            if confirmed == "1" and filing_count >= 2:
                ins_pts = 15
            elif filing_count >= 2:
                ins_pts = 5

        # --- Deep Value layer ---
        dv_pts = 0
        dv_row = deepvalue.get(ticker, {})
        if dv_row:
            grade = dv_row.get("grade", "")
            dv_score = safe_float(dv_row.get("deepvalue_score", 0))
            if grade in ("A", "B"):
                dv_pts = 15
            elif dv_score >= 30:
                dv_pts = 8

        # --- Squeeze layer ---
        sq_pts = 0
        sq_row = squeeze.get(ticker, {})
        if sq_row:
            stage = sq_row.get("stage", "")
            sq_score = safe_float(sq_row.get("squeeze_score", 0))
            if stage in ("COILED", "IGNITION"):
                sq_pts = 15
            elif sq_score >= 20:
                sq_pts = 8

        # --- Smart Money layer ---
        sm_pts = 0
        sm_row = smart_money.get(ticker, {})
        if sm_row:
            fund_count = safe_int(sm_row.get("fund_count", 0))
            if fund_count >= 2:
                sm_pts = 10
            elif fund_count == 1:
                sm_pts = 5

        # --- Revenue Inflection layer ---
        inf_pts = 0
        inf_row = inflection.get(ticker, {})
        if inf_row:
            strength = inf_row.get("signal_strength", "")
            if strength == "STRONG":
                inf_pts = 10
            elif strength == "MODERATE":
                inf_pts = 5

        # --- Dark Pool layer ---
        dp_pts = 0
        dp_row = dark_pool.get(ticker, {})
        if dp_row:
            dp_flag = dp_row.get("dark_pool_flag", "False")
            dp_signal = dp_row.get("signal_type", "")
            if dp_flag == "True" and dp_signal == "ACCUMULATION":
                dp_pts = 10
            elif dp_flag == "True":
                dp_pts = 5

        # --- NT Radar layer ---
        nt_pts = 0
        nt_row = nt_radar.get(ticker, {})
        if nt_row:
            if nt_row.get("signal_type") == "POSITIVE_NT":
                nt_pts = 5

        # --- Merger layer ---
        mg_pts = 0
        mg_row = mergers.get(ticker, {})
        if mg_row:
            mg_pts = 5

        # --- A-4: Put/Call Ratio — Pan & Poteshman (2006, RFS) ---
        # Contrarian signal: high PCR = fear = mean-reversion bullish;
        # low PCR = euphoria = reversal bearish. Sign conventions are additive.
        pcr_pts = 0
        opt_row = options.get(ticker, {})
        if opt_row:
            pcr = safe_float(opt_row.get("pc_ratio", 0))
            if pcr >= 1.5:
                pcr_pts = 5    # strong contrarian bullish
            elif pcr >= 1.0:
                pcr_pts = 2    # mild contrarian bullish
            elif pcr <= 0.3:
                pcr_pts = -3   # euphoria warning
            elif pcr <= 0.5:
                pcr_pts = -1   # mild crowd optimism

        # --- Alpha factors (A-2, A-3, A-12) ---
        af_pts = 0
        af_row = alpha_factors.get(ticker, {})
        if af_row:
            af_pts += safe_int(af_row.get("gapper_vol_bonus", 0))
            af_pts += safe_int(af_row.get("gapper_volz_bonus", 0))
            af_pts += safe_int(af_row.get("illiq_penalty", 0))

        # --- Keyword bonus ---
        kw_pts = 0
        kw_rows = keyword_multi.get(ticker, [])
        for kw_row in kw_rows:
            kw = kw_row.get("keyword", "").strip().lower()
            for pos_kw in POSITIVE_KEYWORDS:
                if pos_kw in kw or kw in pos_kw:
                    kw_pts = 5
                    break
            if kw_pts:
                break

        # --- CVE Security Risk layer (negative penalty for ops risk) ---
        cve_pts = 0
        cve_rows = cve_multi.get(ticker, [])
        if cve_rows:
            critical = sum(1 for r in cve_rows if r.get("severity", "").upper() == "CRITICAL")
            high = sum(1 for r in cve_rows if r.get("severity", "").upper() == "HIGH")
            kev = sum(1 for r in cve_rows if r.get("is_kev", "").strip().lower() in ("true", "1", "yes"))
            if kev >= 1:
                cve_pts = -10
            elif critical >= 3:
                cve_pts = -6
            elif critical >= 1:
                cve_pts = -3
            elif high >= 5:
                cve_pts = -2

        # --- Earnings calendar layer (imminent earnings = catalyst window) ---
        ern_pts = 0
        ern_row = earnings_cal.get(ticker, {})
        if ern_row:
            rpt = ern_row.get("report_date", "").strip()
            if rpt:
                try:
                    rpt_dt = datetime.datetime.strptime(rpt, "%Y-%m-%d").date()
                    today = datetime.date.today()
                    days = (rpt_dt - today).days
                    if 0 <= days <= 2:
                        ern_pts = 8
                    elif 3 <= days <= 7:
                        ern_pts = 5
                    elif 8 <= days <= 14:
                        ern_pts = 2
                except ValueError:
                    pass

        # --- Going concern penalty (auditor flagged business continuity risk) ---
        gc_pts = 0
        if going_concern.get(ticker, {}):
            gc_pts = -15

        # --- RegSHO threshold list (FTD persistence = short squeeze fuel) ---
        rs_pts = 0
        if regsho.get(ticker, {}):
            rs_pts = 5

        # --- Reddit velocity (retail attention surge) ---
        rdt_pts = 0
        rdt_row = reddit_vel.get(ticker, {})
        if rdt_row:
            vel = safe_float(rdt_row.get("velocity_pct", 0))
            mentions = safe_int(rdt_row.get("mentions", 0))
            if vel >= 200 and mentions >= 50:
                rdt_pts = 8
            elif vel >= 100 and mentions >= 25:
                rdt_pts = 5
            elif vel >= 50 and mentions >= 10:
                rdt_pts = 2

        # --- Wikipedia attention spike (z-score of pageviews) ---
        wk_pts = 0
        wk_row = wiki_attn.get(ticker, {})
        if wk_row:
            z = safe_float(wk_row.get("z_score", 0))
            if z >= 4:
                wk_pts = 5
            elif z >= 3:
                wk_pts = 3
            elif z >= 2:
                wk_pts = 1

        # --- FINRA short volume (short ratio = squeeze fuel) ---
        fs_pts = 0
        fs_rows = finra_short.get(ticker, [])
        if fs_rows:
            # Take most recent by date
            latest = max(fs_rows, key=lambda r: r.get("date", ""))
            sr = safe_float(latest.get("short_ratio", 0))
            if sr >= 0.6:
                fs_pts = 5
            elif sr >= 0.5:
                fs_pts = 3
            elif sr >= 0.4:
                fs_pts = 1

        # --- Form 144 (insider restricted stock sale intent = bearish) ---
        f144_pts = 0
        f144_rows = form144.get(ticker, [])
        if f144_rows:
            # Multiple filings = stronger sell intent
            if len(f144_rows) >= 3:
                f144_pts = -5
            elif len(f144_rows) >= 1:
                f144_pts = -3

        # --- NHTSA recalls (ops liability / legal exposure) ---
        nr_pts = 0
        if nhtsa.get(ticker, []):
            nr_pts = -3

        # --- CFPB complaint surge (bearish for consumer finance) ---
        cf_pts = 0
        cf_row = cfpb.get(ticker, {})
        if cf_row:
            delta = safe_float(cf_row.get("delta_pct", 0))
            if delta >= 20:
                cf_pts = -5
            elif delta >= 10:
                cf_pts = -3

        # --- CFPB enforcement actions (direct consent-order liability) ---
        cfpb_enf_pts = 0
        enf_cnt = cfpb_enf_by_ticker.get(ticker, 0)
        if enf_cnt >= 2:
            cfpb_enf_pts = -5
        elif enf_cnt >= 1:
            cfpb_enf_pts = -3

        # --- SEC 8-K Item 1.03 bankruptcy filing (catastrophic) ---
        bkr_pts = 0
        if sec_bankruptcy.get(ticker, []):
            bkr_pts = -10   # Chapter 7/11 — equity likely wiped

        # --- XBRL DCF intrinsic-value grade ---
        # Two-stage Damodaran model: A-grade = >50% upside vs current price.
        # Weights tuned to favor durable mispricings, not deep-distressed F's
        # (which overlap with bankruptcy_pts and distress flags).
        dcf_pts = 0
        dcf_row = sec_xbrl_dcf.get(ticker, {})
        if dcf_row:
            grade = (dcf_row.get("dcf_grade") or "").strip().upper()
            if grade == "A":   dcf_pts = 5
            elif grade == "B": dcf_pts = 3
            elif grade == "C": dcf_pts = 1
            elif grade == "D": dcf_pts = -1
            elif grade == "F": dcf_pts = -3

        # --- SC 13D/13G activist & >5% passive stake filings ---
        sc13d_pts = 0
        sc13_hits = sec_13d_rows.get(ticker, [])
        if sc13_hits:
            has_activist = any(h.get("form", "").startswith("SC 13D") for h in sc13_hits)
            has_passive  = any(h.get("form", "").startswith("SC 13G") for h in sc13_hits)
            if has_activist:
                sc13d_pts = 3   # 13D = intent-to-influence (takeover/breakup premium)
            elif has_passive:
                sc13d_pts = 1   # 13G = institutional discovery
            if len(sc13_hits) >= 3:
                sc13d_pts = min(5, sc13d_pts + 2)  # multiple filings = heightened interest

        # --- Crypto treasury exposure (BTC beta) ---
        ct_pts = 0
        ct_row = crypto_tr.get(ticker, {})
        if ct_row:
            pnl = safe_float(ct_row.get("unrealized_pnl_usd", 0))
            if pnl > 100000000:  # +$100M unrealized gain
                ct_pts = 3
            elif pnl < -100000000:  # -$100M unrealized loss
                ct_pts = -3

        # --- OpenFDA adverse events (bearish for pharma) ---
        fda_pts = 0
        fda_row = openfda.get(ticker, {})
        if fda_row:
            yoy = fda_row.get("yoy_delta_pct", "0")
            if yoy == "inf":
                fda_pts = -5
            else:
                yoyf = safe_float(yoy)
                if yoyf >= 50:
                    fda_pts = -5
                elif yoyf >= 25:
                    fda_pts = -3

        # --- Google Trends attention spike ---
        gt_pts = 0
        gt_row = gtrends.get(ticker, {})
        if gt_row:
            z = safe_float(gt_row.get("z_score", 0))
            if z >= 3:
                gt_pts = 3
            elif z >= 2:
                gt_pts = 2

        # --- EDGAR full-text hits (bankruptcy / going concern language) ---
        eft_pts = 0
        eft_rows = edgar_ft.get(ticker, [])
        if eft_rows:
            for r in eft_rows:
                phrase = r.get("phrase", "").lower()
                if "going concern" in phrase or "bankruptcy" in phrase or "chapter 11" in phrase:
                    eft_pts = -5
                    break
                elif "material weakness" in phrase or "restatement" in phrase:
                    eft_pts = -3
                    break

        # --- Stocktwits trending (social attention) ---
        st_pts = 0
        st_row = stocktwits.get(ticker, {})
        if st_row:
            watchers = safe_int(st_row.get("watchers", 0))
            bull = safe_float(st_row.get("bullish_pct", 0))
            bear = safe_float(st_row.get("bearish_pct", 0))
            if watchers >= 50000:
                st_pts = 3
            elif watchers >= 10000:
                st_pts = 1
            if bear >= 70:
                st_pts -= 2
            elif bull >= 70:
                st_pts += 1

        # --- WSB mentions (retail attention on wallstreetbets) ---
        wsb_pts = 0
        wsb_row = wsb.get(ticker, {})
        if wsb_row:
            mentions_24h = safe_int(wsb_row.get("mention_count_24h", 0))
            sent = wsb_row.get("sentiment_label", "").lower()
            if mentions_24h >= 100:
                wsb_pts = 5
            elif mentions_24h >= 50:
                wsb_pts = 3
            elif mentions_24h >= 25:
                wsb_pts = 1
            if sent == "bullish":
                wsb_pts += 1
            elif sent == "bearish":
                wsb_pts -= 1

        # --- AV movers (top gainer/loser of the day) ---
        av_pts = 0
        av_row = av_movers.get(ticker, {})
        if av_row:
            cat = av_row.get("category", "")
            chg = safe_float(av_row.get("change_pct", 0))
            if cat == "gainers" and chg >= 20:
                av_pts = 3
            elif cat == "losers" and chg <= -20:
                av_pts = -3

        # --- Gap scanner (overnight/intraday gap with volume) ---
        # Empirical backtest: score>=15 + gap_score>=80 = 100% hit on +2% intraday.
        # Boosting gap layer to surface these to MAXIMUM/HIGH conviction.
        gap_pts = 0
        gap_row = gap_scan.get(ticker, {})
        if gap_row:
            gs = safe_float(gap_row.get("gap_score", 0))
            overnight = safe_float(gap_row.get("overnight_gap_pct", 0))
            if gs >= 80:
                gap_pts = 10  # was 5 — this is the jackpot filter
            elif gs >= 60:
                gap_pts = 6   # was 3
            elif gs >= 40:
                gap_pts = 3   # was 1
            # Extra boost for real pre-market follow-through (>=2% overnight)
            if overnight >= 2:
                gap_pts += 3

        # --- Short interest data (squeeze setup fuel) ---
        sd_pts = 0
        sd_row = short_data.get(ticker, {})
        if sd_row:
            spf = safe_float(sd_row.get("short_pct_float", 0))
            dtc = safe_float(sd_row.get("days_to_cover", 0))
            if spf >= 20 and dtc >= 5:
                sd_pts = 8
            elif spf >= 15:
                sd_pts = 5
            elif spf >= 10:
                sd_pts = 2

        # --- USA Spending (federal contracts = revenue) ---
        us_pts = 0
        us_row = usa_spend.get(ticker, {})
        if us_row:
            total = safe_float(us_row.get("total_usd", 0))
            if total >= 1_000_000_000:
                us_pts = 5
            elif total >= 100_000_000:
                us_pts = 3
            elif total >= 10_000_000:
                us_pts = 1

        # --- GitHub velocity (dev activity for tech cos) ---
        gh_pts = 0
        gh_row = github_vel.get(ticker, {})
        if gh_row:
            events = safe_int(gh_row.get("events_7d", 0))
            if events >= 100:
                gh_pts = 3
            elif events >= 50:
                gh_pts = 2
            elif events >= 20:
                gh_pts = 1

        # --- FINRA RegSHO daily short ratio ---
        fr_pts = 0
        fr_row = finra_regsho.get(ticker, {})
        if fr_row:
            sr = safe_float(fr_row.get("short_ratio", 0))
            if sr >= 0.6:
                fr_pts = 3
            elif sr >= 0.5:
                fr_pts = 2

        # --- arXiv cashtag (research mentions for academic-tied tickers) ---
        ax_pts = 0
        ax_rows = arxiv.get(ticker, [])
        if ax_rows and len(ax_rows) >= 3:
            ax_pts = 2
        elif ax_rows:
            ax_pts = 1

        # --- ASX price-sensitive announcements (Australian tickers) ---
        asx_pts = 0
        asx_rows = asx.get(ticker, [])
        if asx_rows:
            ps_hits = sum(1 for r in asx_rows if r.get("price_sensitive", "0") == "1")
            if ps_hits >= 2:
                asx_pts = 3
            elif ps_hits >= 1:
                asx_pts = 1

        # --- Clinical trials (P2/P3 pipeline via sponsor map) ---
        clin_pts = 0
        cp = clinical_pts_by_ticker.get(ticker, 0)
        if cp >= 6:
            clin_pts = 5
        elif cp >= 3:
            clin_pts = 3
        elif cp >= 1:
            clin_pts = 1

        # --- FDA approvals (sponsor map) ---
        fda_app_pts = 0
        fa = fda_approvals_by_ticker.get(ticker, 0)
        if fa >= 3:
            fda_app_pts = 5
        elif fa >= 2:
            fda_app_pts = 3
        elif fa >= 1:
            fda_app_pts = 1

        # --- DoD contracts ($ awarded) ---
        dod_pts = 0
        dod_amt = dod_by_ticker.get(ticker, 0)
        if dod_amt >= 1_000_000_000:
            dod_pts = 5
        elif dod_amt >= 100_000_000:
            dod_pts = 3
        elif dod_amt >= 10_000_000:
            dod_pts = 1

        # --- NASDAQ halts (T1 news pending = catalyst, T12 bad = bearish) ---
        halt_pts = 0
        halt_rows = halts.get(ticker, [])
        if halt_rows:
            for r in halt_rows:
                code = r.get("reason_code", "").upper()
                if code == "T1":
                    halt_pts = 3  # news pending — bullish catalyst window
                    break
                elif code in ("T12", "H10", "H4"):
                    halt_pts = -5  # regulatory / additional info
                    break
                elif code in ("LUDP", "T2"):
                    halt_pts = 1  # volatility halt / related news
                    break

        # --- Hacker News attention (tech ticker buzz) ---
        hn_pts = 0
        # hn_attn key can be pipe-separated list — check all rows
        for key, rows in hn_attn.items():
            if ticker in key.split("|") or key == ticker:
                hn_pts = min(3, len(rows))
                break

        # --- SEC buybacks (bullish shareholder return) ---
        bb_pts = 0
        if sec_buybacks.get(ticker, {}):
            bb_pts = 4

        # --- SEC contracts (govt contract award = revenue) ---
        contract_pts = 0
        c_rows = sec_contracts.get(ticker, [])
        if c_rows:
            gov_count = sum(1 for r in c_rows if "government" in r.get("kind", "").lower())
            if gov_count >= 2:
                contract_pts = 4
            elif gov_count >= 1:
                contract_pts = 2
            elif c_rows:
                contract_pts = 1

        # --- SEC tender offer target (bullish takeout premium) ---
        tender_pts = 0
        if sec_tender.get(ticker, {}):
            tender_pts = 6

        # --- SEC merger proxy (M&A target on proxy filing) ---
        m_proxy_pts = 0
        if sec_m_proxy.get(ticker, {}):
            m_proxy_pts = 4

        # --- SEC splits (reverse=distress/bearish, forward=bullish) ---
        split_pts = 0
        sp_rows = sec_splits.get(ticker, [])
        if sp_rows:
            for r in sp_rows:
                k = r.get("kind", "").lower()
                if "reverse" in k:
                    split_pts = -3
                    break
                elif "forward" in k or k == "split":
                    split_pts = 2
                    break

        # --- SEC distress (going concern / bankruptcy filings) ---
        distress_pts = 0
        d_rows = sec_distress.get(ticker, [])
        if d_rows:
            for r in d_rows:
                k = r.get("kind", "").lower()
                if "going_concern" in k or "bankruptcy" in k or "chapter" in k:
                    distress_pts = -10
                    break
                elif "delist" in k or "nt_10" in k:
                    distress_pts = -5
                    break

        # --- SEC biotech catalyst (approval, BLA, PDUFA) ---
        biotech_pts = 0
        b_rows = sec_biotech.get(ticker, [])
        if b_rows:
            for r in b_rows:
                k = r.get("kind", "").lower()
                if "approval" in k or "bla" in k:
                    biotech_pts = 5
                    break
                elif "pdufa" in k or "trial" in k or "regulatory" in k:
                    biotech_pts = 3
                    break
                else:
                    biotech_pts = 1

        # --- SEC FDA catalyst (NDA, 510k, orphan drug) ---
        sec_fda_pts = 0
        fd_rows = sec_fda_cat.get(ticker, [])
        if fd_rows:
            for r in fd_rows:
                k = r.get("kind", "").lower()
                if "approval" in k or "nda" in k:
                    sec_fda_pts = 4
                    break
                elif "510k" in k or "orphan" in k or "fast_track" in k:
                    sec_fda_pts = 3
                    break
                elif fd_rows:
                    sec_fda_pts = 1
                    break

        # --- SEC FTD (fails-to-deliver persistence = squeeze fuel) ---
        ftd_pts = 0
        ftd_rows = sec_ftd.get(ticker, [])
        if ftd_rows:
            max_qty = 0
            for r in ftd_rows:
                try:
                    q = float(r.get("quantity_failed", 0) or 0)
                    if q > max_qty:
                        max_qty = q
                except (ValueError, TypeError):
                    pass
            if max_qty >= 1_000_000:
                ftd_pts = 5
            elif max_qty >= 100_000:
                ftd_pts = 3
            elif max_qty >= 10_000:
                ftd_pts = 1

        # --- SEC uplist (exchange uplist = bullish liquidity/credibility) ---
        uplist_pts = 0
        if sec_uplist.get(ticker, {}):
            uplist_pts = 3

        # --- SEC poison pill (rights plan = takeover defense, signals interest) ---
        pill_pts = 0
        pill_rows = sec_pill.get(ticker, [])
        if pill_rows:
            for r in pill_rows:
                k = r.get("kind", "").lower()
                if "rights_plan" in k or "poison_pill" in k:
                    pill_pts = 3
                    break

        # --- SEC crypto pivot filing (exposure signal) ---
        sec_crypto_pts = 0
        cc_rows = sec_crypto_cat.get(ticker, [])
        if cc_rows:
            sec_crypto_pts = 2

        # --- Macro → sector lean (cross-asset regime) ---
        # Sum across ALL sector memberships (a ticker can be in tech_mega
        # AND retail), then clamp to [-5, +5] to avoid runaway lean stacks.
        macro_pts = 0
        sector = TICKER_TO_SECTOR.get(ticker)  # primary sector label
        secs = TICKER_SECTORS.get(ticker, [])
        for s in secs:
            macro_pts += SECTOR_LEAN.get(s, 0)
        if macro_pts > 5:
            macro_pts = 5
        elif macro_pts < -5:
            macro_pts = -5

        # --- Compute totals ---
        # F-10 fix: weight layers by empirical predictive power.
        # Lakonishok & Lee (2001, RFS): insider buying predicts 5-8% excess returns.
        # Cohen, Malloy & Pomorski (2012): opportunistic insider trades 3x more predictive.
        # Insider and squeeze get 2.5x multiplier, smart money 1.5x.
        ins_pts = int(ins_pts * 2.5)
        sq_pts = int(sq_pts * 2.0)
        sm_pts = int(sm_pts * 1.5)
        layer_scores = {
            "sec":      sec_pts,
            "insider":  ins_pts,
            "deepvalue": dv_pts,
            "squeeze":  sq_pts,
            "smart":    sm_pts,
            "inflection": inf_pts,
            "darkpool": dp_pts,
            "nt":       nt_pts,
            "merger":   mg_pts,
            # F-11 fix (2026-04-24): let negative alpha (illiq penalty) and
            # negative PCR (euphoria warning) actually reduce the score. The
            # previous `max(0, x)` clipping silently dropped these penalties.
            "alpha":    af_pts,
            "pcr":      pcr_pts,
            "cve":      cve_pts,
            "earnings": ern_pts,
            "going_concern": gc_pts,
            "regsho":   rs_pts,
            "reddit":   rdt_pts,
            "wiki":     wk_pts,
            "finra_short": fs_pts,
            "form144":  f144_pts,
            "nhtsa":    nr_pts,
            "cfpb":     cf_pts,
            "cfpb_enf": cfpb_enf_pts,
            "sc13d":    sc13d_pts,
            "bankruptcy": bkr_pts,
            "dcf":      dcf_pts,
            "crypto_tr": ct_pts,
            "openfda":  fda_pts,
            "gtrends":  gt_pts,
            "edgar_ft": eft_pts,
            "stocktwits": st_pts,
            "wsb":      wsb_pts,
            "av":       av_pts,
            "gap":      gap_pts,
            "short":    sd_pts,
            "usa_spend": us_pts,
            "github":   gh_pts,
            "finra_regsho": fr_pts,
            "arxiv":    ax_pts,
            "asx":      asx_pts,
            "clinical": clin_pts,
            "fda_app":  fda_app_pts,
            "dod":      dod_pts,
            "halt":     halt_pts,
            "hn":       hn_pts,
            "macro":    macro_pts,
            "buyback":  bb_pts,
            "contract": contract_pts,
            "tender":   tender_pts,
            "m_proxy":  m_proxy_pts,
            "split":    split_pts,
            "distress": distress_pts,
            "biotech":  biotech_pts,
            "sec_fda":  sec_fda_pts,
            "ftd":      ftd_pts,
            "uplist":   uplist_pts,
            "pill":     pill_pts,
            "sec_crypto": sec_crypto_pts,
        }
        raw_total = sum(layer_scores.values()) + kw_pts
        # F-12 fix (2026-04-24): lower-bound the score so distressed names
        # (gc_pts=-15 stacked with distress=-10) show up as AVOID, not
        # absorbed as ordinary WATCH. Upper bound unchanged.
        convergence_score = max(-50, min(100, raw_total))

        # signal_count = layers that scored > 0 (excluding keyword bonus)
        signal_count = sum(1 for v in layer_scores.values() if v > 0)

        # signals_fired — list positive signals only; negative layers surface
        # via conviction=AVOID below.
        signals_fired = ";".join(k for k, v in layer_scores.items() if v > 0)

        # conviction_level
        if convergence_score <= -10:
            conviction = "AVOID"
        elif signal_count >= 4 and convergence_score >= 50:
            conviction = "MAXIMUM"
        elif signal_count >= 3 and convergence_score >= 35:
            conviction = "HIGH"
        elif signal_count >= 2 and convergence_score >= 20:
            conviction = "ELEVATED"
        elif signal_count >= 1:
            conviction = "WATCH"
        else:
            conviction = "WATCH"

        # Get price and market_cap
        price = ""
        market_cap = ""
        if sec_rows:
            price = sec_rows[0].get("price", "")
            market_cap = sec_rows[0].get("market_cap", "")
        if not price:
            ins_row2 = insider.get(ticker, {})
            price = ins_row2.get("price", "")
            market_cap = ins_row2.get("market_cap", "")

        results.append({
            "ticker":           ticker,
            "convergence_score": convergence_score,
            "conviction_level": conviction,
            "signal_count":     signal_count,
            "signals_fired":    signals_fired,
            "sec_pts":          sec_pts,
            "insider_pts":      ins_pts,
            "deepvalue_pts":    dv_pts,
            "squeeze_pts":      sq_pts,
            "smart_pts":        sm_pts,
            "inflection_pts":   inf_pts,
            "darkpool_pts":     dp_pts,
            "nt_pts":           nt_pts,
            "merger_pts":       mg_pts,
            "keyword_pts":      kw_pts,
            "alpha_pts":        af_pts,
            "pcr_pts":          pcr_pts,
            "cve_pts":          cve_pts,
            "earnings_pts":     ern_pts,
            "going_concern_pts": gc_pts,
            "regsho_pts":       rs_pts,
            "reddit_pts":       rdt_pts,
            "wiki_pts":         wk_pts,
            "finra_short_pts":  fs_pts,
            "form144_pts":      f144_pts,
            "nhtsa_pts":        nr_pts,
            "cfpb_pts":         cf_pts,
            "cfpb_enf_pts":     cfpb_enf_pts,
            "sc13d_pts":        sc13d_pts,
            "bankruptcy_pts":   bkr_pts,
            "dcf_pts":          dcf_pts,
            "crypto_tr_pts":    ct_pts,
            "openfda_pts":      fda_pts,
            "gtrends_pts":      gt_pts,
            "edgar_ft_pts":     eft_pts,
            "stocktwits_pts":   st_pts,
            "wsb_pts":          wsb_pts,
            "av_pts":           av_pts,
            "gap_pts":          gap_pts,
            "short_pts":        sd_pts,
            "usa_spend_pts":    us_pts,
            "github_pts":       gh_pts,
            "finra_regsho_pts": fr_pts,
            "arxiv_pts":        ax_pts,
            "asx_pts":          asx_pts,
            "clinical_pts":     clin_pts,
            "fda_app_pts":      fda_app_pts,
            "dod_pts":          dod_pts,
            "halt_pts":         halt_pts,
            "hn_pts":           hn_pts,
            "macro_pts":        macro_pts,
            "buyback_pts":      bb_pts,
            "contract_pts":     contract_pts,
            "tender_pts":       tender_pts,
            "m_proxy_pts":      m_proxy_pts,
            "split_pts":        split_pts,
            "distress_pts":     distress_pts,
            "biotech_pts":      biotech_pts,
            "sec_fda_pts":      sec_fda_pts,
            "ftd_pts":          ftd_pts,
            "uplist_pts":       uplist_pts,
            "pill_pts":         pill_pts,
            "sec_crypto_pts":   sec_crypto_pts,
            "sector":           sector or "",
            "price":            price,
            "market_cap":       market_cap,
        })

    # Sort: conviction level order, then convergence_score desc
    results.sort(key=lambda x: (CONVICTION_ORDER.get(x["conviction_level"], 9), -x["convergence_score"]))

    fieldnames = [
        "ticker", "convergence_score", "conviction_level", "signal_count",
        "signals_fired", "sec_pts", "insider_pts", "deepvalue_pts", "squeeze_pts",
        "smart_pts", "inflection_pts", "darkpool_pts", "nt_pts", "merger_pts",
        "keyword_pts", "alpha_pts", "pcr_pts", "cve_pts",
        "earnings_pts", "going_concern_pts", "regsho_pts", "reddit_pts", "wiki_pts",
        "finra_short_pts", "form144_pts", "nhtsa_pts", "cfpb_pts", "cfpb_enf_pts", "sc13d_pts", "bankruptcy_pts", "dcf_pts",
        "crypto_tr_pts", "openfda_pts", "gtrends_pts",
        "edgar_ft_pts", "stocktwits_pts", "wsb_pts", "av_pts",
        "gap_pts", "short_pts", "usa_spend_pts",
        "github_pts", "finra_regsho_pts", "arxiv_pts", "asx_pts",
        "clinical_pts", "fda_app_pts", "dod_pts", "halt_pts", "hn_pts",
        "macro_pts",
        "buyback_pts", "contract_pts", "tender_pts", "m_proxy_pts", "split_pts",
        "distress_pts", "biotech_pts", "sec_fda_pts", "ftd_pts", "uplist_pts",
        "pill_pts", "sec_crypto_pts",
        "sector",
        "price", "market_cap"
    ]
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote {len(results)} rows to {OUTPUT_FILE}")

    for level in ["MAXIMUM", "HIGH", "ELEVATED", "WATCH"]:
        count = sum(1 for r in results if r["conviction_level"] == level)
        print(f"  {level}: {count}")

    print("\nTop 10 Convergence Alerts:")
    for r in results[:10]:
        print(f"  {r['ticker']:6s} score={r['convergence_score']:3d} {r['conviction_level']:8s} "
              f"signals={r['signal_count']} [{r['signals_fired']}]")

if __name__ == "__main__":
    main()
