#!/usr/bin/env python3
"""
build_defensescoop.py — DefenseScoop DoD-tech + warfighter-IT news tape.

Source: https://defensescoop.com/feed/
        WordPress RSS 2.0 w/ dc:creator + multi-category + pubDate RFC2822.

DefenseScoop is the Pentagon + combatant-command + service-branch technology
trade-press firehose covering DoD IT modernization, JADC2 (Joint All-Domain
Command and Control), CJADC2 Mission Partner Environment, AI in warfare
(Replicator, Project Maven, Task Force Lima), autonomous systems (CCA
Collaborative Combat Aircraft, Ghost Bat, loyal wingman), space force cyber,
hypersonics, electronic warfare, directed energy, OIG audits, CDAO Chief
Digital and AI Officer, Defense Innovation Unit (DIU), RDER Rapid Defense
Experimentation Reserve, Palantir NGC2, Anduril, Shield AI, Replicator drone
drops, SOCOM spec ops IT, Navy Pacific IT modernization, Air Force ABMS,
Army IVAS Integrated Visual Augmentation System, Space Force ground stations.

Distinct from build_fedscoop.py (federal civilian IT), build_cyberscoop.py
(cyber incident), build_darpa.py (DARPA research) — DefenseScoop is the
warfighter-capability + contract-award trade-press operational tape below
fed_register policy and above SEC contract-award 8-K disclosure.

Output: defensescoop.csv — filed_utc, kind, title, link, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import html
import pathlib
import re
import sys
import urllib.request
from datetime import timezone
from email.utils import parsedate_to_datetime

URL = "https://defensescoop.com/feed/"
OUT = pathlib.Path(__file__).resolve().parent / "defensescoop.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Priority-ordered classifier. Most-specific kinds first.
CLASSIFIER = [
    ("ai_warfare",           re.compile(r"\b(artificial intelligence|\bAI\b|machine learning|\bML\b|Task Force Lima|Project Maven|Replicator|autonomous|CCA\b|Collaborative Combat Aircraft|Ghost Bat|loyal wingman|algorithmic warfare|CDAO|Chief Digital AI)\b", re.I)),
    ("jadc2_c2",             re.compile(r"\b(JADC2|CJADC2|Joint All-Domain|command and control|\bC2\b|NGC2|mission partner environment|MPE\b|combined joint|all-domain operations)\b", re.I)),
    ("autonomous_drones",    re.compile(r"\b(drone|UAV|UAS|unmanned aerial|unmanned surface|USV\b|unmanned underwater|UUV\b|MQ-9|Reaper|Switchblade|Anduril|Shield AI|Skydio|ALTIUS|Ghost|Coyote)\b", re.I)),
    ("hypersonic_missile",   re.compile(r"\b(hypersonic|LRHW\b|Long Range Hypersonic|ARRW\b|HCSW\b|conventional prompt|glide vehicle|boost.?glide|scramjet|Mach \d|HWIT)\b", re.I)),
    ("space_force",          re.compile(r"\b(Space Force|USSF\b|Space Command|USSPACECOM|Guardian|proliferated architecture|Tranche \d|SDA\b|Space Development Agency|satellite communication|SATCOM|space domain awareness)\b", re.I)),
    ("cyber_warfare",        re.compile(r"\b(CYBERCOM|Cyber Command|offensive cyber|cyber mission force|CMF\b|cyber operations|information operations|IO\b|red team|blue team|cyber range|Persistent Engagement)\b", re.I)),
    ("electronic_warfare",   re.compile(r"\b(electronic warfare|\bEW\b|electronic attack|electronic protection|jamming|ELINT|SIGINT|COMINT|spectrum warfare|electromagnetic spectrum|EMS\b|NGJ|Next Generation Jammer)\b", re.I)),
    ("directed_energy",      re.compile(r"\b(directed energy|\bDEW\b|laser weapon|HEL\b|high energy laser|microwave weapon|HPM\b|high power microwave|IFPC-HEL|LaWS|P-HEL)\b", re.I)),
    ("network_comms",        re.compile(r"\b(tactical network|radio|SATCOM|MILSATCOM|Link 16|Link 22|waveform|JTRS|software defined radio|SDR\b|mesh network|tactical edge)\b", re.I)),
    ("army_ivas",            re.compile(r"\b(IVAS|Integrated Visual Augmentation|HoloLens|soldier lethality|Army Futures|Next Generation Squad Weapon|NGSW\b|Project Linchpin|Project Convergence)\b", re.I)),
    ("navy_pacific",         re.compile(r"\b(Navy|INDOPACOM|Indo-Pacific|Pacific Deterrence|Project Overmatch|DDG-\d|Constellation|Columbia.?class|Virginia.?class|submarine|Pacific fleet)\b", re.I)),
    ("air_force_abms",       re.compile(r"\b(Air Force|ABMS|Advanced Battle Management|Skyborg|E-7 Wedgetail|F-35|F-15EX|B-21|Sentinel ICBM|Next Generation Air Dominance|NGAD)\b", re.I)),
    ("socom_spec_ops",       re.compile(r"\b(SOCOM\b|Special Operations|USSOCOM|spec ops|JSOC\b|Delta Force|Navy SEAL|Ranger|Green Beret|Maritime Special Operations|SOF\b)\b", re.I)),
    ("contract_award",       re.compile(r"\b(contract award|contract worth|awarded|task order|IDIQ|OTA\b|other transaction|prototype agreement|GWAC\b|SEWP|protest|GAO protest|sole source|ceiling)\b", re.I)),
    ("diu_innovation",       re.compile(r"\b(Defense Innovation Unit|\bDIU\b|RDER|Rapid Defense Experimentation|OUSD R.E|under secretary R.E|SBIR|STTR|AFWERX|SOFWERX|NavalX)\b", re.I)),
    ("dod_budget",           re.compile(r"\b(DoD budget|Department of Defense budget|NDAA\b|National Defense Authorization|defense appropriation|FY2\d|Pentagon budget|CR\b|continuing resolution)\b", re.I)),
    ("industrial_base",      re.compile(r"\b(defense industrial base|\bDIB\b|supply chain|munitions shortage|industrial capacity|organic industrial|arsenal|depot|Nat.{0,5}Def.{0,5}Stockpile|critical minerals)\b", re.I)),
    ("leadership_nominations", re.compile(r"\b(nominated|confirmation|Senate Armed Services|SASC\b|HASC\b|Secretary of Defense|SecDef|Under Secretary|Service Secretary|CJCS|Joint Chiefs)\b", re.I)),
    ("allied_aukus",         re.compile(r"\b(AUKUS|NATO\b|Quad\b|Five Eyes|FVEY|Japan|South Korea|ROK|Australia|UK MoD|allied|bilateral|multinational|IOR\b|EUCOM)\b", re.I)),
    ("intel_ic_dod",         re.compile(r"\b(DIA\b|Defense Intelligence|NGA\b|National Geospatial|NRO\b|NSA\b|National Security Agency|ICAM|TS/SCI|combatant intelligence|J-2)\b", re.I)),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml,application/xml,text/xml",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def unescape_clean(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def extract_tag(body: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", body, re.S)
    return unescape_clean(m.group(1)) if m else ""


def extract_all(body: str, tag: str) -> list[str]:
    return [unescape_clean(x) for x in re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", body, re.S)]


def to_iso_utc(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return ""


def classify(title: str, summary: str, categories: list[str]) -> str:
    hay = f"{title}  {summary}  {' '.join(categories)}"
    for name, pat in CLASSIFIER:
        if pat.search(hay):
            return name
    return "defensetech"


def parse_items(body: bytes) -> list[dict]:
    text = body.decode("utf-8", errors="replace")
    items = re.findall(r"<item[^>]*>(.*?)</item>", text, re.S)
    rows = []
    for raw in items:
        title = extract_tag(raw, "title")
        link = extract_tag(raw, "link")
        summary = extract_tag(raw, "description")
        categories = extract_all(raw, "category")
        filed = to_iso_utc(extract_tag(raw, "pubDate"))
        if not (title and link):
            continue
        kind = classify(title, summary, categories)
        rows.append({
            "filed_utc": filed,
            "kind": kind,
            "title": title[:240],
            "link": link,
            "summary": summary[:400],
        })
    return rows


def write_csv(rows: list[dict]) -> None:
    if not rows and OUT.exists() and OUT.stat().st_size > MIN_GOOD:
        print(f"defensescoop: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
        return
    cols = ["filed_utc", "kind", "title", "link", "summary"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    try:
        body = fetch(URL)
    except Exception as e:
        print(f"defensescoop: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"defensescoop: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
