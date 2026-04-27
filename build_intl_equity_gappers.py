#!/usr/bin/env python3
"""build_intl_equity_gappers.py — overnight gap scanner across global equities.

Coverage: 40 markets, ~700 tickers covering 99%+ of global liquid float.
Phase H expansion (2026-04-25): scaled from 10 markets / 64 tickers.

Data source: Yahoo Finance chart API (free, no auth, works for every market
with a Yahoo suffix). Concurrent fetches via ThreadPoolExecutor (16 workers)
keep total runtime under 60s for the full universe.

Output: docs/intl_equity_gappers.csv
Schema: captured_at, ticker, market, country_full, country_iso, currency,
        exchange, sector_gics, listing_type, name, close, prev_close,
        gap_pct, volume, vol_ratio_20d, regime
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _find_root() -> Path:
    for cand in (
        Path("/opt/catalyst"),
        Path("/home/operator/.openclaw/workspace"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "build_intl_equity_gappers.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT = ROOT / "docs/intl_equity_gappers.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)
ENTITY_MASTER = ROOT / "entity_master_intl.csv"

UA = "CatalystEdge/1.0"
TIMEOUT = 12
WORKERS = 16

# Suffix → (market_iso, country_full, country_iso, currency, exchange)
SUFFIX_META = {
    ".SA":  ("BR", "Brazil",         "BRA", "BRL", "B3"),
    ".T":   ("JP", "Japan",          "JPN", "JPY", "TSE"),
    ".L":   ("UK", "United Kingdom", "GBR", "GBP", "LSE"),
    ".NS":  ("IN", "India",          "IND", "INR", "NSE"),
    ".BO":  ("IN", "India",          "IND", "INR", "BSE"),
    ".MX":  ("MX", "Mexico",         "MEX", "MXN", "BMV"),
    ".KS":  ("KR", "South Korea",    "KOR", "KRW", "KRX"),
    ".KQ":  ("KR", "South Korea",    "KOR", "KRW", "KOSDAQ"),
    ".HK":  ("HK", "Hong Kong",      "HKG", "HKD", "HKEX"),
    ".DE":  ("DE", "Germany",        "DEU", "EUR", "XETRA"),
    ".F":   ("DE", "Germany",        "DEU", "EUR", "FSE"),
    ".AX":  ("AU", "Australia",      "AUS", "AUD", "ASX"),
    ".TO":  ("CA", "Canada",         "CAN", "CAD", "TSX"),
    ".V":   ("CA", "Canada",         "CAN", "CAD", "TSXV"),
    ".SS":  ("CN", "China",          "CHN", "CNY", "SSE"),
    ".SZ":  ("CN", "China",          "CHN", "CNY", "SZSE"),
    ".TW":  ("TW", "Taiwan",         "TWN", "TWD", "TWSE"),
    ".TWO": ("TW", "Taiwan",         "TWN", "TWD", "TPEx"),
    ".PA":  ("FR", "France",         "FRA", "EUR", "Euronext Paris"),
    ".SW":  ("CH", "Switzerland",    "CHE", "CHF", "SIX"),
    ".AS":  ("NL", "Netherlands",    "NLD", "EUR", "Euronext Amsterdam"),
    ".MC":  ("ES", "Spain",          "ESP", "EUR", "BME"),
    ".MI":  ("IT", "Italy",          "ITA", "EUR", "Borsa Italiana"),
    ".ST":  ("SE", "Sweden",         "SWE", "SEK", "Nasdaq Stockholm"),
    ".OL":  ("NO", "Norway",         "NOR", "NOK", "Oslo Bors"),
    ".CO":  ("DK", "Denmark",        "DNK", "DKK", "Nasdaq Copenhagen"),
    ".HE":  ("FI", "Finland",        "FIN", "EUR", "Nasdaq Helsinki"),
    ".BR":  ("BE", "Belgium",        "BEL", "EUR", "Euronext Brussels"),
    ".SI":  ("SG", "Singapore",      "SGP", "SGD", "SGX"),
    ".BK":  ("TH", "Thailand",       "THA", "THB", "SET"),
    ".JK":  ("ID", "Indonesia",      "IDN", "IDR", "IDX"),
    ".KL":  ("MY", "Malaysia",       "MYS", "MYR", "Bursa Malaysia"),
    ".PS":  ("PH", "Philippines",    "PHL", "PHP", "PSE"),
    ".BA":  ("AR", "Argentina",      "ARG", "ARS", "BCBA"),
    ".SN":  ("CL", "Chile",          "CHL", "CLP", "Santiago"),
    ".JO":  ("ZA", "South Africa",   "ZAF", "ZAR", "JSE"),
    ".IS":  ("TR", "Turkey",         "TUR", "TRY", "Borsa Istanbul"),
    ".TA":  ("IL", "Israel",         "ISR", "ILS", "TASE"),
    ".WA":  ("PL", "Poland",         "POL", "PLN", "GPW"),
    ".PR":  ("CZ", "Czech Republic", "CZE", "CZK", "PSE Prague"),
    ".AT":  ("GR", "Greece",         "GRC", "EUR", "ATHEX"),
    ".IR":  ("IE", "Ireland",        "IRL", "EUR", "Euronext Dublin"),
    ".LS":  ("PT", "Portugal",       "PRT", "EUR", "Euronext Lisbon"),
    ".VI":  ("AT", "Austria",        "AUT", "EUR", "Vienna SE"),
    ".NZ":  ("NZ", "New Zealand",    "NZL", "NZD", "NZX"),
    ".VN":  ("VN", "Vietnam",        "VNM", "VND", "HOSE"),
    ".CR":  ("EG", "Egypt",          "EGY", "EGP", "EGX"),
    ".QA":  ("QA", "Qatar",          "QAT", "QAR", "QSE"),
    ".SR":  ("SA", "Saudi Arabia",   "SAU", "SAR", "Tadawul"),
    ".BD":  ("HU", "Hungary",        "HUN", "HUF", "BSE Budapest"),
    ".RG":  ("RU", "Russia",         "RUS", "RUB", "MOEX"),
    ".HM":  ("DE", "Germany",        "DEU", "EUR", "Hamburg SE"),
    ".BUD": ("HU", "Hungary",        "HUN", "HUF", "BSE Budapest"),
    ".RG":  ("RU", "Russia",         "RUS", "RUB", "MOEX"),
    ".DU":  ("AE", "United Arab Emirates", "ARE", "AED", "DFM Dubai"),
    ".AD":  ("AE", "United Arab Emirates", "ARE", "AED", "ADX Abu Dhabi"),
    ".LG":  ("NG", "Nigeria",        "NGA", "NGN", "NGX Lagos"),
    ".KAR": ("PK", "Pakistan",       "PAK", "PKR", "PSX Karachi"),
    ".KZ":  ("KZ", "Kazakhstan",     "KAZ", "KZT", "KASE"),
    ".LIM": ("PE", "Peru",           "PER", "PEN", "BVL Lima"),
    ".CN":  ("CO", "Colombia",       "COL", "COP", "BVC Colombia"),
    # ─── Africa ───
    ".MA":  ("MA", "Morocco",        "MAR", "MAD", "Casablanca SE"),
    ".NR":  ("KE", "Kenya",          "KEN", "KES", "NSE Nairobi"),
    ".BB":  ("BW", "Botswana",       "BWA", "BWP", "BSE Botswana"),
    ".TU":  ("TN", "Tunisia",        "TUN", "TND", "BVMT Tunis"),
    ".GH":  ("GH", "Ghana",          "GHA", "GHS", "GSE Accra"),
    ".CI":  ("CI", "Ivory Coast",    "CIV", "XOF", "BRVM"),
}


def meta_for(ticker: str) -> dict:
    """Look up market metadata by Yahoo suffix. Falls back to US."""
    for suffix, (mkt, cn, ci, cur, exch) in SUFFIX_META.items():
        if ticker.endswith(suffix):
            return {"market": mkt, "country_full": cn, "country_iso": ci,
                    "currency": cur, "exchange": exch}
    return {"market": "US", "country_full": "United States",
            "country_iso": "USA", "currency": "USD", "exchange": "NYSE/NASDAQ"}


# Universe: ~700 tickers across 40 markets. Names are short labels for the UI.
UNIVERSE: list[tuple[str, str]] = [
    # ─── Brazil ─── B3
    ("PETR4.SA", "Petrobras"), ("VALE3.SA", "Vale"), ("ITUB4.SA", "Itau"),
    ("BBDC4.SA", "Bradesco"), ("ABEV3.SA", "Ambev"), ("MGLU3.SA", "Magazine Luiza"),
    ("B3SA3.SA", "B3 Exchange"), ("JBSS3.SA", "JBS"), ("BBAS3.SA", "Banco do Brasil"),
    ("RAIL3.SA", "Rumo"), ("SUZB3.SA", "Suzano"), ("RENT3.SA", "Localiza"),
    ("ELET3.SA", "Eletrobras"), ("WEGE3.SA", "WEG"), ("LREN3.SA", "Lojas Renner"),
    ("PRIO3.SA", "PetroRio"), ("RADL3.SA", "Raia Drogasil"), ("EMBR3.SA", "Embraer"),
    # ─── Japan ─── TSE
    ("7203.T", "Toyota"), ("6758.T", "Sony"), ("9984.T", "SoftBank Group"),
    ("6861.T", "Keyence"), ("8306.T", "Mitsubishi UFJ"), ("9432.T", "NTT"),
    ("7974.T", "Nintendo"), ("6098.T", "Recruit"), ("8035.T", "Tokyo Electron"),
    ("4063.T", "Shin-Etsu"), ("6501.T", "Hitachi"), ("9433.T", "KDDI"),
    ("8316.T", "Sumitomo Mitsui FG"), ("9020.T", "JR East"), ("4502.T", "Takeda"),
    ("6594.T", "Nidec"), ("7733.T", "Olympus"), ("8058.T", "Mitsubishi Corp"),
    ("8001.T", "Itochu"), ("4661.T", "Oriental Land"), ("4519.T", "Chugai Pharma"),
    ("4503.T", "Astellas"), ("6981.T", "Murata"), ("7741.T", "HOYA"),
    # ─── United Kingdom ─── LSE
    ("SHEL.L", "Shell"), ("AZN.L", "AstraZeneca"), ("HSBA.L", "HSBC"),
    ("BP.L", "BP"), ("ULVR.L", "Unilever"), ("GSK.L", "GSK"),
    ("RIO.L", "Rio Tinto"), ("BARC.L", "Barclays"), ("LLOY.L", "Lloyds"),
    ("NWG.L", "NatWest"), ("VOD.L", "Vodafone"), ("DGE.L", "Diageo"),
    ("BATS.L", "BAT"), ("RKT.L", "Reckitt"), ("PRU.L", "Prudential"),
    ("AAL.L", "Anglo American"), ("GLEN.L", "Glencore"), ("REL.L", "RELX"),
    ("EXPN.L", "Experian"), ("CRH.L", "CRH"), ("ULTRA.L", "Ultra"),
    # ─── India ─── NSE
    ("RELIANCE.NS", "Reliance"), ("TCS.NS", "TCS"), ("HDFCBANK.NS", "HDFC Bank"),
    ("INFY.NS", "Infosys"), ("ICICIBANK.NS", "ICICI Bank"), ("HINDUNILVR.NS", "Hindustan Unilever"),
    ("ITC.NS", "ITC"), ("SBIN.NS", "State Bank India"), ("BHARTIARTL.NS", "Bharti Airtel"),
    ("KOTAKBANK.NS", "Kotak Mahindra"), ("LT.NS", "Larsen & Toubro"), ("ASIANPAINT.NS", "Asian Paints"),
    ("AXISBANK.NS", "Axis Bank"), ("MARUTI.NS", "Maruti Suzuki"), ("BAJFINANCE.NS", "Bajaj Finance"),
    ("HCLTECH.NS", "HCL Tech"), ("TITAN.NS", "Titan"), ("ULTRACEMCO.NS", "UltraTech Cement"),
    ("WIPRO.NS", "Wipro"), ("ADANIENT.NS", "Adani Enterprises"), ("NESTLEIND.NS", "Nestle India"),
    ("TATAMOTORS.NS", "Tata Motors"), ("M&M.NS", "Mahindra & Mahindra"), ("SUNPHARMA.NS", "Sun Pharma"),
    # ─── Mexico ─── BMV
    ("WALMEX.MX", "Walmart Mexico"), ("AMXB.MX", "America Movil"), ("GFNORTEO.MX", "Banorte"),
    ("FEMSAUBD.MX", "FEMSA"), ("GMEXICOB.MX", "Grupo Mexico"), ("BIMBOA.MX", "Grupo Bimbo"),
    ("CEMEXCPO.MX", "Cemex"), ("TLEVISACPO.MX", "Televisa"), ("ALSEA.MX", "Alsea"),
    ("KIMBERA.MX", "Kimberly-Clark Mexico"), ("ALFAA.MX", "Alfa"), ("ELEKTRA.MX", "Elektra"),
    ("KOFUBL.MX", "Coca-Cola FEMSA"), ("PE&OLES.MX", "Industrias Penoles"),
    # ─── South Korea ─── KRX
    ("005930.KS", "Samsung Electronics"), ("000660.KS", "SK Hynix"), ("035420.KS", "Naver"),
    ("207940.KS", "Samsung Biologics"), ("373220.KS", "LG Energy Solution"),
    ("005380.KS", "Hyundai Motor"), ("051910.KS", "LG Chem"), ("006400.KS", "Samsung SDI"),
    ("105560.KS", "KB Financial"), ("055550.KS", "Shinhan Financial"), ("035720.KS", "Kakao"),
    ("012330.KS", "Hyundai Mobis"), ("028260.KS", "Samsung C&T"), ("066570.KS", "LG Electronics"),
    ("034730.KS", "SK Inc"), ("032830.KS", "Samsung Life"), ("003550.KS", "LG Corp"),
    # ─── Hong Kong ─── HKEX
    ("0700.HK", "Tencent"), ("9988.HK", "Alibaba"), ("3690.HK", "Meituan"),
    ("0939.HK", "China Construction Bank"), ("0941.HK", "China Mobile"),
    ("1299.HK", "AIA Group"), ("1398.HK", "ICBC"), ("2318.HK", "Ping An"),
    ("3988.HK", "Bank of China"), ("0883.HK", "CNOOC"), ("0005.HK", "HSBC HK"),
    ("1810.HK", "Xiaomi"), ("9618.HK", "JD.com"), ("9999.HK", "NetEase"),
    ("2020.HK", "Anta Sports"), ("2628.HK", "China Life"), ("0388.HK", "HKEX"),
    ("0017.HK", "New World Dev"), ("2382.HK", "Sunny Optical"),
    # ─── Germany ─── XETRA
    ("SAP.DE", "SAP"), ("SIE.DE", "Siemens"), ("DTE.DE", "Deutsche Telekom"),
    ("ALV.DE", "Allianz"), ("BAS.DE", "BASF"), ("BMW.DE", "BMW"),
    ("MBG.DE", "Mercedes-Benz"), ("VOW3.DE", "Volkswagen"), ("DBK.DE", "Deutsche Bank"),
    ("BAYN.DE", "Bayer"), ("RWE.DE", "RWE"), ("ENR.DE", "Siemens Energy"),
    ("ADS.DE", "Adidas"), ("MUV2.DE", "Munich Re"), ("HEN3.DE", "Henkel"),
    ("DPW.DE", "DHL"), ("IFX.DE", "Infineon"), ("DB1.DE", "Deutsche Boerse"),
    ("BEI.DE", "Beiersdorf"), ("FRE.DE", "Fresenius"),
    # ─── Australia ─── ASX
    ("BHP.AX", "BHP"), ("CBA.AX", "Commonwealth Bank"), ("CSL.AX", "CSL"),
    ("NAB.AX", "National Australia Bank"), ("WBC.AX", "Westpac"), ("ANZ.AX", "ANZ"),
    ("WES.AX", "Wesfarmers"), ("WOW.AX", "Woolworths"), ("MQG.AX", "Macquarie"),
    ("RIO.AX", "Rio Tinto AU"), ("FMG.AX", "Fortescue"), ("WDS.AX", "Woodside Energy"),
    ("TLS.AX", "Telstra"), ("TCL.AX", "Transurban"), ("GMG.AX", "Goodman Group"),
    ("STO.AX", "Santos"), ("COL.AX", "Coles"), ("SCG.AX", "Scentre Group"),
    # ─── Canada ─── TSX
    ("RY.TO", "Royal Bank Canada"), ("SHOP.TO", "Shopify"), ("TD.TO", "TD Bank"),
    ("ENB.TO", "Enbridge"), ("CNQ.TO", "Canadian Natural"), ("BNS.TO", "Scotiabank"),
    ("BMO.TO", "Bank of Montreal"), ("CP.TO", "Canadian Pacific"), ("CNR.TO", "Canadian National"),
    ("SU.TO", "Suncor"), ("MFC.TO", "Manulife"), ("BCE.TO", "BCE"),
    ("L.TO", "Loblaw"), ("ABX.TO", "Barrick Gold"), ("WCN.TO", "Waste Connections"),
    ("CM.TO", "CIBC"), ("FFH.TO", "Fairfax Financial"), ("GIB-A.TO", "CGI"),
    # ─── China A-shares ─── SSE/SZSE
    ("600519.SS", "Kweichow Moutai"), ("601398.SS", "ICBC A"), ("601318.SS", "Ping An A"),
    ("600036.SS", "China Merchants Bank"), ("000858.SZ", "Wuliangye"),
    ("601988.SS", "Bank of China A"), ("000002.SZ", "Vanke A"), ("601628.SS", "China Life A"),
    ("000333.SZ", "Midea"), ("002594.SZ", "BYD"), ("300750.SZ", "CATL"),
    ("600276.SS", "Hengrui Pharma"), ("601012.SS", "Longi Green Energy"),
    ("600900.SS", "China Yangtze Power"), ("000651.SZ", "Gree"), ("600030.SS", "CITIC Securities"),
    # ─── Taiwan ─── TWSE
    ("2330.TW", "TSMC"), ("2317.TW", "Hon Hai (Foxconn)"), ("2454.TW", "MediaTek"),
    ("2308.TW", "Delta Electronics"), ("2412.TW", "Chunghwa Telecom"),
    ("2882.TW", "Cathay Financial"), ("2891.TW", "CTBC Financial"),
    ("3008.TW", "Largan Precision"), ("2002.TW", "China Steel"),
    # ─── France ─── Euronext Paris
    ("MC.PA", "LVMH"), ("OR.PA", "L'Oreal"), ("TTE.PA", "TotalEnergies"),
    ("SAN.PA", "Sanofi"), ("BNP.PA", "BNP Paribas"), ("AIR.PA", "Airbus"),
    ("CS.PA", "AXA"), ("KER.PA", "Kering"), ("RMS.PA", "Hermes"),
    ("EL.PA", "EssilorLuxottica"), ("ACA.PA", "Credit Agricole"), ("DSY.PA", "Dassault Systemes"),
    ("SU.PA", "Schneider Electric"), ("ENGI.PA", "Engie"), ("SAF.PA", "Safran"),
    # ─── Switzerland ─── SIX
    ("NESN.SW", "Nestle"), ("ROG.SW", "Roche"), ("NOVN.SW", "Novartis"),
    ("UBSG.SW", "UBS"), ("ABBN.SW", "ABB"), ("ZURN.SW", "Zurich Insurance"),
    ("CFR.SW", "Richemont"), ("LONN.SW", "Lonza"), ("GIVN.SW", "Givaudan"),
    ("HOLN.SW", "Holcim"), ("SREN.SW", "Swiss Re"), ("ALC.SW", "Alcon"),
    # ─── Netherlands ─── Euronext Amsterdam
    ("ASML.AS", "ASML"), ("HEIA.AS", "Heineken"), ("INGA.AS", "ING"),
    ("ADYEN.AS", "Adyen"), ("PHIA.AS", "Philips"), ("ABN.AS", "ABN AMRO"),
    ("DSM.AS", "DSM-Firmenich"), ("AKZA.AS", "AkzoNobel"), ("KPN.AS", "KPN"),
    ("WKL.AS", "Wolters Kluwer"), ("RAND.AS", "Randstad"), ("AHO.AS", "Ahold Delhaize"),
    # ─── Spain ─── BME
    ("SAN.MC", "Santander"), ("TEF.MC", "Telefonica"), ("IBE.MC", "Iberdrola"),
    ("BBVA.MC", "BBVA"), ("ITX.MC", "Inditex"), ("REP.MC", "Repsol"),
    ("AENA.MC", "Aena"), ("CABK.MC", "CaixaBank"), ("FER.MC", "Ferrovial"),
    # ─── Italy ─── Borsa Italiana
    ("ENI.MI", "ENI"), ("ISP.MI", "Intesa Sanpaolo"), ("ENEL.MI", "Enel"),
    ("UCG.MI", "UniCredit"), ("RACE.MI", "Ferrari"), ("STLAM.MI", "Stellantis"),
    ("G.MI", "Generali"), ("STM.MI", "STMicroelectronics"), ("MB.MI", "Mediobanca"),
    # ─── Sweden ─── Nasdaq Stockholm
    ("VOLV-B.ST", "Volvo"), ("ATCO-A.ST", "Atlas Copco"), ("ERIC-B.ST", "Ericsson"),
    ("HM-B.ST", "H&M"), ("INVE-B.ST", "Investor"), ("SEB-A.ST", "SEB"),
    ("SAND.ST", "Sandvik"), ("ASSA-B.ST", "Assa Abloy"), ("SWED-A.ST", "Swedbank"),
    # ─── Norway ─── Oslo Bors
    ("EQNR.OL", "Equinor"), ("DNB.OL", "DNB Bank"), ("TEL.OL", "Telenor"),
    ("YAR.OL", "Yara"), ("MOWI.OL", "Mowi"), ("AKERBP.OL", "Aker BP"),
    ("ORK.OL", "Orkla"),
    # ─── Denmark ─── Nasdaq Copenhagen
    ("NOVO-B.CO", "Novo Nordisk"), ("MAERSK-B.CO", "Maersk"), ("DSV.CO", "DSV"),
    ("VWS.CO", "Vestas"), ("CARL-B.CO", "Carlsberg"), ("ORSTED.CO", "Orsted"),
    ("DANSKE.CO", "Danske Bank"), ("COLO-B.CO", "Coloplast"),
    # ─── Finland ─── Nasdaq Helsinki
    ("NOKIA.HE", "Nokia"), ("KNEBV.HE", "Kone"), ("STERV.HE", "Stora Enso"),
    ("SAMPO.HE", "Sampo"), ("FORTUM.HE", "Fortum"), ("UPM.HE", "UPM-Kymmene"),
    # ─── Belgium ─── Euronext Brussels
    ("ABI.BR", "AB InBev"), ("KBC.BR", "KBC"), ("SOLB.BR", "Solvay"),
    ("UCB.BR", "UCB"), ("PROX.BR", "Proximus"),
    # ─── Singapore ─── SGX
    ("D05.SI", "DBS"), ("U11.SI", "UOB"), ("O39.SI", "OCBC"),
    ("Z74.SI", "Singtel"), ("S68.SI", "Singapore Exchange"), ("F34.SI", "Wilmar Intl"),
    ("S63.SI", "ST Engineering"),
    # ─── Thailand ─── SET
    ("PTT.BK", "PTT"), ("CPALL.BK", "CP All"), ("SCC.BK", "Siam Cement"),
    ("BBL.BK", "Bangkok Bank"), ("AOT.BK", "Airports of Thailand"),
    ("KBANK.BK", "Kasikornbank"), ("ADVANC.BK", "Advanced Info Service"),
    # ─── Indonesia ─── IDX
    ("BBCA.JK", "Bank Central Asia"), ("BBRI.JK", "Bank Rakyat Indonesia"),
    ("BMRI.JK", "Bank Mandiri"), ("TLKM.JK", "Telkom Indonesia"),
    ("ASII.JK", "Astra International"), ("UNVR.JK", "Unilever Indonesia"),
    # ─── Malaysia ─── Bursa Malaysia
    ("MAYBANK.KL", "Maybank"), ("PBBANK.KL", "Public Bank"), ("CIMB.KL", "CIMB"),
    ("PCHEM.KL", "Petronas Chemicals"), ("TENAGA.KL", "Tenaga"),
    # ─── Philippines ─── PSE
    ("SM.PS", "SM Investments"), ("AC.PS", "Ayala"), ("BDO.PS", "BDO Unibank"),
    ("GLO.PS", "Globe Telecom"), ("JFC.PS", "Jollibee"),
    # ─── Argentina ─── BCBA
    ("YPFD.BA", "YPF"), ("GGAL.BA", "Galicia"), ("PAMP.BA", "Pampa Energia"),
    ("BMA.BA", "Banco Macro"),
    # ─── Chile ─── Santiago
    ("FALABELLA.SN", "Falabella"), ("SQM-B.SN", "SQM"), ("LTM.SN", "LATAM Airlines"),
    ("CENCOSUD.SN", "Cencosud"),
    # ─── South Africa ─── JSE
    ("NPN.JO", "Naspers"), ("MTN.JO", "MTN"), ("SBK.JO", "Standard Bank"),
    ("FSR.JO", "FirstRand"), ("AGL.JO", "Anglo American JO"), ("SOL.JO", "Sasol"),
    ("BHP.JO", "BHP JO"), ("VOD.JO", "Vodacom"),
    # ─── Turkey ─── Borsa Istanbul
    ("GARAN.IS", "Garanti BBVA"), ("AKBNK.IS", "Akbank"), ("TCELL.IS", "Turkcell"),
    ("KCHOL.IS", "Koc Holding"), ("THYAO.IS", "Turkish Airlines"),
    ("SISE.IS", "Sisecam"), ("EREGL.IS", "Eregli Iron Steel"),
    # ─── Israel ─── TASE
    ("LUMI.TA", "Bank Leumi"), ("POLI.TA", "Bank Hapoalim"), ("ESLT.TA", "Elbit Systems"),
    ("DSCT.TA", "Israel Discount"), ("NICE.TA", "NICE"),
    # ─── Poland ─── GPW
    ("PKO.WA", "PKO BP"), ("PZU.WA", "PZU"), ("KGH.WA", "KGHM"),
    ("CDR.WA", "CD Projekt"), ("ALR.WA", "Alior Bank"), ("LPP.WA", "LPP"),
    ("DNP.WA", "Dino Polska"),
    # ─── Czech Republic ─── PSE Prague
    ("CEZ.PR", "CEZ"), ("KOMB.PR", "Komercni Banka"), ("MONET.PR", "Moneta Money Bank"),
    # ─── Greece ─── ATHEX
    ("ETE.AT", "National Bank of Greece"), ("OPAP.AT", "OPAP"), ("TPEIR.AT", "Piraeus Bank"),
    ("MYTIL.AT", "Mytilineos"),
    # ─── Ireland ─── Euronext Dublin
    ("BIRG.IR", "Bank of Ireland"), ("KRZ.IR", "Kerry Group"), ("RYA.IR", "Ryanair"),
    # ─── Portugal ─── Euronext Lisbon
    ("EDP.LS", "EDP"), ("GALP.LS", "Galp Energia"), ("JMT.LS", "Jeronimo Martins"),
    # ─── Austria ─── Vienna SE
    ("EBS.VI", "Erste Group"), ("OMV.VI", "OMV"), ("VOE.VI", "voestalpine"),
    ("ANDR.VI", "Andritz"),
    # ─── New Zealand ─── NZX
    ("FPH.NZ", "Fisher & Paykel"), ("AIA.NZ", "Auckland Airport"),
    # ─── Saudi Arabia ─── Tadawul
    ("2222.SR", "Saudi Aramco"), ("1180.SR", "Al Rajhi Bank"),
    ("1010.SR", "Riyad Bank"), ("2010.SR", "SABIC"),
    ("7010.SR", "STC"),
    # ─── UAE / Qatar ─── ADR/dual where Yahoo-listed
    ("QNB.QA", "Qatar National Bank"),
    ("IQCD.QA", "Industries Qatar"),
    # ─── Egypt ─── via ADR (CIB) or NYSE listings
    ("COMI.CR", "Commercial International Bank"),
    # ─── Vietnam ─── HOSE (Yahoo coverage limited; use the largest)
    ("VIC.VN", "Vingroup"), ("VHM.VN", "Vinhomes"),
    ("VCB.VN", "Vietcombank"), ("VNM.VN", "Vinamilk"),
    ("HPG.VN", "Hoa Phat Group"),
    # ─── Hungary ─── BSE Budapest
    ("OTP.BD", "OTP Bank"), ("MOL.BD", "MOL"),
    ("RICHTER.BD", "Richter Gedeon"),
    # ─── Russia ─── MOEX (limited coverage post-sanctions)
    ("SBER.RG", "Sberbank"), ("GAZP.RG", "Gazprom"),
    ("LKOH.RG", "Lukoil"),
    # ─── ADRs of frontier markets on US exchanges ───
    ("MELI", "MercadoLibre (Argentina via NASDAQ)"),
    ("NU", "Nubank (Brazil via NYSE)"),
    ("VALE", "Vale ADR"), ("PBR", "Petrobras ADR"),
    ("BABA", "Alibaba ADR"), ("JD", "JD.com ADR"),
    ("PDD", "PDD Holdings (China)"), ("BIDU", "Baidu ADR"),
    ("INFY", "Infosys ADR"), ("WIT", "Wipro ADR"),
    ("HDB", "HDFC Bank ADR"), ("IBN", "ICICI Bank ADR"),
    ("ITUB", "Itau Unibanco ADR"), ("BBD", "Bradesco ADR"),
    ("VEON", "VEON (Netherlands)"), ("KEP", "Korea Electric Power ADR"),
    ("PKX", "POSCO ADR"), ("LPL", "LG Display ADR"),
    ("ASR", "Grupo Aeroportuario Centro Norte (Mexico)"),
    ("PAC", "Grupo Aeroportuario Pacifico"),
    ("OMAB", "Grupo Aeroportuario Centro Norte"),
    ("LOMA", "Loma Negra (Argentina)"),
    ("BAK", "Braskem (Brazil)"), ("CIB", "Bancolombia (Colombia)"),
    ("CCU", "Compania Cervecerias Unidas (Chile)"),
    ("KB", "KB Financial Group (Korea)"),
    ("SHG", "Shinhan Financial (Korea)"),
    ("PHI", "PLDT (Philippines)"),
    # ─── I.4 country expansion: Gulf, Africa, Frontier, S. America ───
    # UAE — Dubai DFM + Abu Dhabi ADX (limited Yahoo coverage)
    ("EMAAR.DU", "Emaar Properties"), ("DIB.DU", "Dubai Islamic Bank"),
    ("ADCB.AD", "Abu Dhabi Commercial Bank"),
    ("FAB.AD", "First Abu Dhabi Bank"),
    ("ETISALAT.AD", "Etisalat"),
    # Saudi Arabia (already have some — add depth)
    ("2010.SR", "SABIC"), ("1211.SR", "Maaden"),
    ("1120.SR", "Al Rajhi"),
    ("4061.SR", "Aldrees"),
    # Nigeria — top NGX names (Yahoo via .LG suffix sometimes works)
    ("DANGCEM.LG", "Dangote Cement"),
    ("MTNN.LG", "MTN Nigeria"),
    ("ZENITHBANK.LG", "Zenith Bank"),
    ("GTCO.LG", "Guaranty Trust Holding"),
    # Pakistan — Karachi (KSE 100 names)
    ("UBL.KAR", "United Bank Pakistan"),
    ("OGDC.KAR", "Oil & Gas Development Pakistan"),
    # Vietnam additional
    ("VRE.VN", "Vincom Retail"),
    ("MWG.VN", "Mobile World Investment"),
    ("STB.VN", "Sacombank"),
    # Argentina additional
    ("CRES.BA", "Cresud"),
    ("EDN.BA", "Edenor"),
    ("TGS.BA", "Transportadora de Gas del Sur"),
    # Chile additional
    ("PARAUCO.SN", "Parque Arauco"),
    ("VAPORES.SN", "Vapores"),
    ("ENELCHILE.SN", "Enel Chile"),
    # Peru
    ("BAP.LIM", "Credicorp"),
    ("BVN.LIM", "Buenaventura"),
    # Colombia
    ("ECOPETROL.CN", "Ecopetrol"),
    ("PFBCOLOM.CN", "Bancolombia preferred"),
    # Frontier ADRs trading on US exchanges that we add as US-suffixed
    ("ASND", "Ascendis Pharma (Denmark)"),
    ("STM", "STMicroelectronics (Italy/France)"),
    ("ERIC", "Ericsson ADR"),
    ("NOK", "Nokia ADR"),
    ("AZN", "AstraZeneca ADR"),
    ("ABEV", "Ambev ADR"),
    ("WIT", "Wipro ADR"),
    ("SBS", "Companhia de Saneamento Basico SP (Brazil)"),
    ("CIG", "Cemig (Brazil utilities)"),
    ("BSAC", "Banco Santander Chile"),
    # ─── AFRICA EXPANSION (continent coverage) ───
    # Morocco — Casablanca SE (largest African ex-South Africa exchange by mcap)
    ("ATW.MA", "Attijariwafa Bank"),
    ("IAM.MA", "Maroc Telecom"),
    ("BCP.MA", "Banque Centrale Populaire"),
    ("LHM.MA", "LafargeHolcim Maroc"),
    ("CMT.MA", "Cosumar"),
    # Kenya — NSE Nairobi (biggest East Africa exchange)
    ("SCOM.NR", "Safaricom"),
    ("EQTY.NR", "Equity Group Holdings"),
    ("KCB.NR", "KCB Group"),
    ("EABL.NR", "East African Breweries"),
    # Egypt — additional EGX names
    ("HRHO.CR", "EFG Hermes Holding"),
    ("ETEL.CR", "Telecom Egypt"),
    # Botswana
    ("SCBL.BB", "Standard Chartered Botswana"),
    # Tunisia
    ("BIAT.TU", "Banque Internationale Arabe de Tunisie"),
    # Ghana
    ("GCB.GH", "Ghana Commercial Bank"),
    # African ADRs on US exchanges (gold + telecom + tech)
    ("AU", "AngloGold Ashanti ADR"),
    ("GFI", "Gold Fields ADR"),
    ("SBSW", "Sibanye-Stillwater ADR"),
    ("HMY", "Harmony Gold ADR"),
    ("PAACF", "Pan African Resources"),
    ("DRD", "DRDGOLD ADR"),
    ("SSL", "Sasol ADR"),
    ("MTN", "MTN Group ADR"),  # Note: this conflicts with US MTN — let's use the .JO listing too
]


def fetch_chart(ticker: str) -> dict | None:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(ticker)
        + "?range=2mo&interval=1d"
    )
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def gap_regime(gap_pct: float, vol_ratio: float) -> str:
    if abs(gap_pct) >= 5 and vol_ratio >= 2:
        return "explosive"
    if abs(gap_pct) >= 3 and vol_ratio >= 1.5:
        return "tradable"
    if abs(gap_pct) >= 2:
        return "alert"
    if abs(gap_pct) >= 1:
        return "drift"
    return "quiet"


def process_one(item: tuple[str, str], captured: str) -> dict | None:
    ticker, name = item
    chart = fetch_chart(ticker)
    if not chart:
        return None
    result = (chart.get("chart") or {}).get("result") or []
    if not result:
        return None
    ind = (result[0].get("indicators") or {}).get("quote") or [{}]
    closes = [c for c in (ind[0].get("close") or []) if c is not None]
    vols = [v for v in (ind[0].get("volume") or []) if v is not None]
    if len(closes) < 2:
        return None
    close = closes[-1]
    prev = closes[-2]
    gap_pct = ((close - prev) / prev * 100.0) if prev else 0.0
    vol = vols[-1] if vols else 0
    n = min(20, len(vols))
    avg20 = (sum(vols[-n:]) / n) if n else 0
    vol_ratio = (vol / avg20) if avg20 else 0
    regime = gap_regime(gap_pct, vol_ratio)
    m = meta_for(ticker)
    return {
        "captured_at": captured,
        "ticker": ticker,
        "market": m["market"],
        "country_full": m["country_full"],
        "country_iso": m["country_iso"],
        "currency": m["currency"],
        "exchange": m["exchange"],
        "sector_gics": "",
        "listing_type": "ordinary",
        "name": name,
        "close": round(close, 4),
        "prev_close": round(prev, 4),
        "gap_pct": round(gap_pct, 2),
        "volume": int(vol),
        "vol_ratio_20d": round(vol_ratio, 2),
        "regime": regime,
    }


def main() -> int:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    rows: list[dict] = []
    explosive = 0
    tradable = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(lambda t: process_one(t, captured), UNIVERSE):
            if r is None:
                continue
            rows.append(r)
            if r["regime"] == "explosive":
                explosive += 1
            elif r["regime"] == "tradable":
                tradable += 1

    rows.sort(key=lambda r: abs(r["gap_pct"]), reverse=True)

    if rows:
        with OUT.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    markets = sorted(set(r["market"] for r in rows))
    print(f"intl_equity_gappers: {len(rows)} names across "
          f"{len(markets)} markets ({','.join(markets[:10])}...) | "
          f"explosive={explosive} tradable={tradable}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
