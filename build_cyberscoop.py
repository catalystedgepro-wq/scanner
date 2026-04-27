#!/usr/bin/env python3
"""
build_cyberscoop.py — CyberScoop cybersecurity trade-press tape.

Source: https://cyberscoop.com/feed/
        WordPress RSS 2.0 w/ dc:creator + multi-category + pubDate RFC2822.

CyberScoop is the operational cyber-incident + enterprise-security trade-press
firehose covering breach disclosures, ransomware campaigns, nation-state APT
ops (Salt Typhoon/Volt Typhoon/APT29/Lazarus), CVE exploitation waves, zero-day
vendor advisories, M&A in cyber, VC funding rounds, CISO leadership moves,
privacy/GDPR/state-law enforcement, supply-chain attacks (SolarWinds/Kaseya/
MOVEit/3CX/XZ-backdoor lineage).

Distinct from build_fedscoop.py (federal-IT operational tape), build_cve_velocity.py
(NVD CVSS numerics), build_tech_status.py (Statuspage.io infra-outage), and
sector cyber-reg feeds fed_register (NIST/CISA rulemaking) + doj_news (DOJ
prosecutions) — CyberScoop covers the vendor + incident + industry trade-press
operational layer that moves CRWD/PANW/OKTA/ZS/FTNT/S/TENB/RPD/MIME equity in
24-72h windows on breach disclosures + vendor advisory dumps.

Output: cyberscoop.csv — filed_utc, kind, title, link, summary.

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

URL = "https://cyberscoop.com/feed/"
OUT = pathlib.Path(__file__).resolve().parent / "cyberscoop.csv"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MIN_GOOD = 200


# Priority-ordered classifier. Most-specific kinds first.
CLASSIFIER = [
    ("ransomware_attack",    re.compile(r"\b(ransomware|LockBit|BlackCat|ALPHV|Cl0p|Clop|BlackBasta|Black Basta|Conti|Rhysida|Akira|Scattered Spider|ShinyHunters|encrypted|ransom demand|double extortion)\b", re.I)),
    ("nation_state_apt",     re.compile(r"\b(Salt Typhoon|Volt Typhoon|Flax Typhoon|APT\d+|Lazarus|Kimsuky|Sandworm|Fancy Bear|Cozy Bear|nation-state|state-sponsored|Chinese hackers|Russian hackers|North Korean hackers|Iranian hackers|Unit 61398|Unit 8200)\b", re.I)),
    ("supply_chain_breach",  re.compile(r"\b(supply chain|supply-chain|SolarWinds|Kaseya|MOVEit|3CX|XZ|xz-utils|npm package|PyPI package|package malicious|open source compromise|software bill of materials|SBOM|build compromise)\b", re.I)),
    ("zero_day_exploit",     re.compile(r"\b(zero.?day|0-day|unpatched|active.?exploitation|exploited in the wild|ITW|in-the-wild|CVE-20\d\d-\d{4,6}|emergency patch|out-of-band patch|CISA KEV|known exploited)\b", re.I)),
    ("data_breach",          re.compile(r"\b(data breach|data leak|exposed database|leaked credentials|stolen data|PII exposed|customer records|breach notification|breach disclosure|records compromised|sensitive information leaked)\b", re.I)),
    ("cyber_ma_funding",     re.compile(r"\b(acquisition|acquires|to acquire|merger|funding round|Series [A-E]|raises \$|IPO filing|venture|VC funding|private equity|PE firm|valuation|acquired by)\b", re.I)),
    ("vendor_advisory",      re.compile(r"\b(Microsoft advisory|Patch Tuesday|Cisco advisory|Fortinet|Palo Alto advisory|Ivanti|Citrix|F5 advisory|VMware advisory|vulnerability disclosure|security bulletin|vendor patch|critical vulnerability)\b", re.I)),
    ("ai_security",          re.compile(r"\b(AI security|prompt injection|LLM attack|jailbreak|deepfake|AI-powered attack|machine learning|adversarial|MCP|model poisoning|AI governance|responsible AI)\b", re.I)),
    ("cisa_guidance",        re.compile(r"\b(CISA|Cybersecurity and Infrastructure Security Agency|BOD \d+|binding operational directive|emergency directive|CISA alert|Secure by Design|JCDC|Joint Cyber Defense)\b", re.I)),
    ("nsa_cybercom",         re.compile(r"\b(NSA\b|Cyber Command|CYBERCOM|National Security Agency|Office of the National Cyber Director|ONCD|offensive cyber|national cyber strategy)\b", re.I)),
    ("critical_infra",       re.compile(r"\b(critical infrastructure|water utility|electric grid|power grid|pipeline attack|Colonial Pipeline|OT security|operational technology|ICS|industrial control|SCADA|healthcare attack|hospital breach|rail attack)\b", re.I)),
    ("privacy_regulation",   re.compile(r"\b(GDPR|CCPA|privacy act|data protection|FTC enforcement|state privacy law|California privacy|Texas privacy|Colorado privacy|biometric|BIPA|COPPA|child privacy)\b", re.I)),
    ("identity_auth",        re.compile(r"\b(identity|MFA|multi-factor|phishing-resistant|FIDO|passkey|OAuth|SSO|single sign-on|credential stuff|password|token theft|session hijack)\b", re.I)),
    ("cloud_security",       re.compile(r"\b(AWS security|Azure security|GCP security|cloud misconfiguration|S3 bucket|cloud breach|Kubernetes|container security|CNAPP|CSPM|cloud posture)\b", re.I)),
    ("phishing_bec",         re.compile(r"\b(phishing|spear phishing|business email compromise|BEC\b|vishing|smishing|credential phishing|email security|SEG|secure email gateway)\b", re.I)),
    ("crypto_theft",         re.compile(r"\b(cryptocurrency theft|crypto hack|DeFi exploit|bridge attack|wallet drain|North Korea crypto|Lazarus crypto|Bybit|Ronin|Wormhole|Nomad|stablecoin attack)\b", re.I)),
    ("law_enforcement",      re.compile(r"\b(FBI\b|DOJ\b|indictment|takedown|seized|sanctioned by Treasury|OFAC sanctions|Europol|Interpol|arrest|extradition|botnet takedown)\b", re.I)),
    ("congress_cyber",       re.compile(r"\b(Congress|Senate\b|House\b|hearing|testimony|cyber legislation|Cybersecurity Information Sharing|CIRCIA|Cyber Incident Reporting|federal cyber)\b", re.I)),
    ("enterprise_tooling",   re.compile(r"\b(SIEM|SOAR|EDR|XDR|MDR|NDR|firewall|SASE|SSE|ZTNA|zero trust|threat intelligence|DLP|data loss prevention|vulnerability management)\b", re.I)),
    ("disinformation_ops",   re.compile(r"\b(disinformation|influence operation|election security|deepfake political|foreign interference|propaganda|misinformation campaign)\b", re.I)),
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
    return "cybernews"


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
        print(f"cyberscoop: fetch produced 0 rows; preserving last-good {OUT}", file=sys.stderr)
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
        print(f"cyberscoop: fetch failed: {e}", file=sys.stderr)
        return 0
    rows = parse_items(body)
    rows.sort(key=lambda r: r.get("filed_utc", ""), reverse=True)
    write_csv(rows)
    print(f"cyberscoop: {len(rows)} rows → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
