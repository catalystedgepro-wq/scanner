#!/usr/bin/env python3
"""
build_bis_cb_speeches.py — BIS Central Bank Speeches tape.

Source: https://www.bis.org/doclist/cbspeeches.rss  (RDF RSS 1.0, cb:speech namespace)

Aggregated archive of global central bank speeches — Federal Reserve, ECB,
BoE, BoJ, DNB, RBA, RBI, SNB, Norges Bank, Riksbank, etc. — with speaker,
venue, occurrenceDate. Institution is not in institutionAbbrev (always "BIS")
so it is inferred from description text.

Output: bis_cb_speeches.csv — filed_utc, institution, kind, speaker, title,
link, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import html
import pathlib
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

URL = "https://www.bis.org/doclist/cbspeeches.rss"
OUT = pathlib.Path(__file__).resolve().parent / "bis_cb_speeches.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Institution inference from description text. First-match-wins ordering
# places narrower matches before broader ones.
INSTITUTION_RULES = [
    ("fed",           re.compile(r"Federal Reserve System|Federal Reserve Board|Board of Governors|Federal Reserve Bank of", re.I)),
    ("ecb",           re.compile(r"European Central Bank|\bECB\b", re.I)),
    ("boe",           re.compile(r"Bank of England|\bBoE\b|Prudential Regulation Authority", re.I)),
    ("boj",           re.compile(r"Bank of Japan|\bBoJ\b", re.I)),
    ("pboc",          re.compile(r"People.s Bank of China|\bPBoC\b|\bPBC\b", re.I)),
    ("snb",           re.compile(r"Swiss National Bank|\bSNB\b", re.I)),
    ("rba",           re.compile(r"Reserve Bank of Australia|\bRBA\b", re.I)),
    ("rbnz",          re.compile(r"Reserve Bank of New Zealand|\bRBNZ\b", re.I)),
    ("rbi",           re.compile(r"Reserve Bank of India|\bRBI\b", re.I)),
    ("boc",           re.compile(r"Bank of Canada|Banque du Canada", re.I)),
    ("dnb",           re.compile(r"De Nederlandsche Bank|\bDNB\b", re.I)),
    ("bundesbank",    re.compile(r"Deutsche Bundesbank|\bBundesbank\b", re.I)),
    ("banque_france", re.compile(r"Banque de France|Bank of France", re.I)),
    ("banca_italia",  re.compile(r"Banca d.Italia|Bank of Italy", re.I)),
    ("banco_espana",  re.compile(r"Banco de Espa.a|Bank of Spain", re.I)),
    ("oenb",          re.compile(r"Oesterreichische Nationalbank|\bOeNB\b|Austrian National Bank", re.I)),
    ("nbb",           re.compile(r"National Bank of Belgium|Nationale Bank van Belgi", re.I)),
    ("bcl",           re.compile(r"Banque centrale du Luxembourg", re.I)),
    ("cbi",           re.compile(r"Central Bank of Ireland", re.I)),
    ("bog_greece",    re.compile(r"Bank of Greece", re.I)),
    ("bop_portugal",  re.compile(r"Banco de Portugal", re.I)),
    ("bof_finland",   re.compile(r"Bank of Finland|Suomen Pankki", re.I)),
    ("norges_bank",   re.compile(r"Norges Bank", re.I)),
    ("riksbank",      re.compile(r"Sveriges Riksbank|Riksbank", re.I)),
    ("danmarks",      re.compile(r"Danmarks Nationalbank", re.I)),
    ("sedlabanki",    re.compile(r"Central Bank of Iceland|Sedlabanki", re.I)),
    ("boi",           re.compile(r"Bank of Israel", re.I)),
    ("sarb",          re.compile(r"South African Reserve Bank|\bSARB\b", re.I)),
    ("cbrt",          re.compile(r"Central Bank of the Republic of T.rkiye|Turkish Central|\bCBRT\b", re.I)),
    ("cbr",           re.compile(r"Bank of Russia|Central Bank of the Russian Federation", re.I)),
    ("nbp",           re.compile(r"Narodowy Bank Polski|National Bank of Poland", re.I)),
    ("mnb",           re.compile(r"Magyar Nemzeti Bank|\bMNB\b", re.I)),
    ("cnb",           re.compile(r"Czech National Bank|.esk. n.rodn. banka", re.I)),
    ("hkma",          re.compile(r"Hong Kong Monetary Authority|\bHKMA\b", re.I)),
    ("mas",           re.compile(r"Monetary Authority of Singapore|\bMAS\b", re.I)),
    ("bok",           re.compile(r"Bank of Korea|\bBoK\b", re.I)),
    ("bnm",           re.compile(r"Bank Negara Malaysia|\bBNM\b", re.I)),
    ("bot",           re.compile(r"Bank of Thailand|\bBoT\b", re.I)),
    ("bsp",           re.compile(r"Bangko Sentral ng Pilipinas|\bBSP\b", re.I)),
    ("bi_indonesia",  re.compile(r"Bank Indonesia", re.I)),
    ("sbv",           re.compile(r"State Bank of Vietnam", re.I)),
    ("banxico",       re.compile(r"Bank of Mexico|Banco de M.xico", re.I)),
    ("bcb",           re.compile(r"Banco Central do Brasil|Central Bank of Brazil", re.I)),
    ("bcra",          re.compile(r"Banco Central de la Rep.blica Argentina", re.I)),
    ("bccl",          re.compile(r"Banco Central de Chile", re.I)),
    ("banrep",        re.compile(r"Banco de la Rep.blica|Bank of the Republic", re.I)),
    ("bcrp",          re.compile(r"Banco Central de Reserva del Per.", re.I)),
    ("cbuae",         re.compile(r"Central Bank of the United Arab Emirates|\bCBUAE\b", re.I)),
    ("sama",          re.compile(r"Saudi Central Bank|\bSAMA\b", re.I)),
    ("cbe",           re.compile(r"Central Bank of Egypt", re.I)),
    ("cbk",           re.compile(r"Central Bank of Kenya", re.I)),
    ("cbn",           re.compile(r"Central Bank of Nigeria|\bCBN\b", re.I)),
    ("bis",           re.compile(r"Bank for International Settlements|\bBIS\b", re.I)),
    ("imf",           re.compile(r"International Monetary Fund|\bIMF\b", re.I)),
    ("fsb",           re.compile(r"Financial Stability Board|\bFSB\b", re.I)),
    ("boj_jamaica",   re.compile(r"Bank of Jamaica", re.I)),
    ("bnb_bulgaria",  re.compile(r"Bulgarian National Bank|\bBNB\b", re.I)),
    ("boa_albania",   re.compile(r"Bank of Albania", re.I)),
    ("cbsl",          re.compile(r"Central Bank of Sri Lanka", re.I)),
    ("nbr_romania",   re.compile(r"National Bank of Romania", re.I)),
    ("nbs_serbia",    re.compile(r"National Bank of Serbia", re.I)),
    ("cnb_croatia",   re.compile(r"Croatian National Bank", re.I)),
    ("nbu_ukraine",   re.compile(r"National Bank of Ukraine", re.I)),
    ("cbm_malta",     re.compile(r"Central Bank of Malta", re.I)),
    ("cbc_cyprus",    re.compile(r"Central Bank of Cyprus", re.I)),
    ("bol_lithuania", re.compile(r"Bank of Lithuania", re.I)),
    ("bol_latvia",    re.compile(r"Bank of Latvia|Latvijas Banka", re.I)),
    ("ee_estonia",    re.compile(r"Eesti Pank|Bank of Estonia", re.I)),
    ("nbs_slovakia",  re.compile(r"National Bank of Slovakia", re.I)),
    ("bs_slovenia",   re.compile(r"Bank of Slovenia|Banka Slovenije", re.I)),
    ("bot_tanzania",  re.compile(r"Bank of Tanzania", re.I)),
    ("bog_ghana",     re.compile(r"Bank of Ghana", re.I)),
    ("bou_uganda",    re.compile(r"Bank of Uganda", re.I)),
    ("cb_namibia",    re.compile(r"Bank of Namibia", re.I)),
    ("bm_mauritius",  re.compile(r"Bank of Mauritius", re.I)),
    ("bcc",           re.compile(r"Banco de Cabo Verde", re.I)),
    ("cbb_bahrain",   re.compile(r"Central Bank of Bahrain", re.I)),
    ("cbj_jordan",    re.compile(r"Central Bank of Jordan", re.I)),
    ("cbl_lebanon",   re.compile(r"Banque du Liban", re.I)),
    ("cbq_qatar",     re.compile(r"Qatar Central Bank", re.I)),
    ("cbk_kuwait",    re.compile(r"Central Bank of Kuwait", re.I)),
    ("bot_thailand2", re.compile(r"Bank of Thailand", re.I)),
]

# Topic classification. Priority-ordered; first match wins.
TOPIC_RULES = [
    ("crypto_digital",     re.compile(r"\b(crypto|stablecoin|cbdc|digital (currenc|euro|dollar|pound|yuan)|tokeni[sz]ation|bitcoin|digital asset)\b", re.I)),
    ("payments",           re.compile(r"\bpayment|retail payments|cross-border|instant payment|fast payment|fedwire|target2\b", re.I)),
    ("climate",            re.compile(r"\b(climate|green financ|sustainab|transition risk|ngfs|net.?zero|esg)\b", re.I)),
    ("ai_tech",            re.compile(r"\b(artificial intelligence|\bai\b|machine learning|fintech|tech(nolog)?y|innovation hub)\b", re.I)),
    ("cyber",              re.compile(r"\bcyber|operational resilience|resilient operation\b", re.I)),
    ("financial_stability",re.compile(r"\b(financial stability|macroprudential|systemic risk|shadow bank|non-?bank|ccyb|countercyclical buffer)\b", re.I)),
    ("supervision",        re.compile(r"\b(supervis|basel|capital requirement|prudential|stress test|bank regulation|bank capital)\b", re.I)),
    ("monetary_policy",    re.compile(r"\b(monetary polic|interest rate|inflation|disinflation|rate (cut|hike|decision)|policy rate|rate path|forward guidance|qt\b|quantitative (easing|tightening)|balance sheet)\b", re.I)),
    ("markets",            re.compile(r"\b(bond market|treasury market|market liquidity|repo|money market|fx market|foreign exchange|market structure|capital market)\b", re.I)),
    ("economic_outlook",   re.compile(r"\b(outlook|economy|economic (conditions|activity|growth)|labour market|labor market|productivity|gdp)\b", re.I)),
    ("international",      re.compile(r"\b(international monetary|global financial|imf|g7|g20|multilateral|capital flow|spillover)\b", re.I)),
    ("communication",      re.compile(r"\b(communication|transparency|accountability|central bank independence|governance)\b", re.I)),
    ("rural_community",    re.compile(r"\b(rural|community reinvest|underserved|financial inclusion|community bank)\b", re.I)),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,application/xml,text/xml"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def unescape_clean(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def extract_tag(body: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", body, re.S)
    return unescape_clean(m.group(1)) if m else ""


def to_iso_utc(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    # cb:occurrenceDate / dc:date are usually already ISO-8601 with Z.
    if re.match(r"^\d{4}-\d{2}-\d{2}T", raw):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    try:
        dt = parsedate_to_datetime(raw)
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return ""


def classify_institution(description: str, speaker: str) -> str:
    hay = f"{description} {speaker}"
    for name, pat in INSTITUTION_RULES:
        if pat.search(hay):
            return name
    return "other"


def classify_topic(title: str, description: str) -> str:
    hay = f"{title} {description}"
    for name, pat in TOPIC_RULES:
        if pat.search(hay):
            return name
    return "press"


def parse_items(body: bytes) -> list[dict]:
    text = body.decode("utf-8", errors="replace")
    # RDF RSS 1.0 items are <item rdf:about="url"> ... </item>
    items = re.findall(r"<item\s+rdf:about=[^>]*>(.*?)</item>", text, re.S)
    rows = []
    for raw in items:
        title = extract_tag(raw, "title") or extract_tag(raw, "dc:title")
        link = extract_tag(raw, "link")
        description = extract_tag(raw, "description")
        speaker = (
            extract_tag(raw, "cb:nameAsWritten")
            or extract_tag(raw, "dc:creator")
            or extract_tag(raw, "cb:byline")
        )
        filed_raw = (
            extract_tag(raw, "cb:occurrenceDate")
            or extract_tag(raw, "dc:date")
        )
        filed = to_iso_utc(filed_raw)
        if not (title and link):
            continue
        institution = classify_institution(description, speaker)
        kind = classify_topic(title, description)
        rows.append({
            "filed_utc": filed,
            "institution": institution,
            "kind": kind,
            "speaker": speaker,
            "title": title[:240],
            "link": link,
            "summary": description[:400],
        })
    return rows


def write_csv(rows: list[dict]) -> None:
    if not rows and OUT.exists() and OUT.stat().st_size > MIN_GOOD:
        print(f"bis_cb_speeches: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
        return
    cols = ["filed_utc", "institution", "kind", "speaker", "title", "link", "summary"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    try:
        body = fetch(URL)
    except Exception as e:
        print(f"bis_cb_speeches: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"bis_cb_speeches: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
