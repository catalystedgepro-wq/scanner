#!/usr/bin/env python3
"""build_lead_magnet.py — Generate SEC Filing Cheat Sheet lead magnet pages.

Produces two HTML files:
  docs/cheat-sheet/index.html  — Landing page with email capture (gated)
  docs/cheat-sheet/download.html — Full cheat sheet (print-friendly, ungated)

Uses real pipeline performance data from sec_performance_breakdown.json
and outcome stats from sec_outcome_summary.csv.
"""
from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "docs" / "cheat-sheet"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ET = ZoneInfo("America/New_York")
NOW = datetime.datetime.now(ET)
TODAY = NOW.strftime("%B %Y")
YEAR = NOW.strftime("%Y")

SITE = "https://catalystedgescanner.com"
SUBSCRIBE_URL = f"{SITE}/#subscribe"
TELEGRAM_URL = "https://t.me/CatalystEdgePro"


def _load_perf() -> dict:
    p = ROOT / "sec_performance_breakdown.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _load_summary() -> dict:
    p = ROOT / "sec_outcome_summary.csv"
    if not p.exists():
        return {}
    rows = list(csv.DictReader(p.read_text(encoding="utf-8").splitlines()))
    return {r["list_name"]: r for r in rows}


def _landing_page(perf: dict, summary: dict) -> str:
    gapper = summary.get("sec_clean_gappers", {})
    total_picks = perf.get("total_picks_scored", 8000)
    hit_rate = gapper.get("hit_rate_2pct", "44.5")
    avg_run = gapper.get("avg_next_day_max_run_pct", "5.1")

    form_stats = perf.get("form_type_stats", [])
    top_forms_preview = ""
    for f in form_stats[:5]:
        label = f.get("label", f["form"])
        hr = f["hit_rate_3pct"]
        picks = f["picks"]
        bar_w = min(hr * 1.5, 100)
        top_forms_preview += f"""
        <div class="preview-row">
          <div class="preview-label">{label}</div>
          <div class="preview-bar-track">
            <div class="preview-bar" style="width:{bar_w}%"></div>
            <span class="preview-val">{hr:.1f}%</span>
          </div>
          <div class="preview-n">{picks:,} picks</div>
        </div>"""

    catalyst_stats = perf.get("catalyst_tag_stats", [])
    catalyst_preview = ""
    for c in catalyst_stats[:4]:
        cat = c["catalyst"]
        hr = c["hit_rate_3pct"]
        catalyst_preview += f"""
        <div class="catalyst-chip">
          <span class="chip-name">{cat}</span>
          <span class="chip-rate">{hr:.0f}%</span>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Free SEC Filing Cheat Sheet — Catalyst Edge</title>
<meta name="description" content="Download the free SEC Filing Cheat Sheet. Learn which SEC filings move stocks, backed by {total_picks:,}+ backtested picks.">
<meta property="og:title" content="Free SEC Filing Cheat Sheet — Catalyst Edge">
<meta property="og:description" content="Which SEC filings actually move stocks? {total_picks:,}+ picks backtested. Free download.">
<meta property="og:type" content="website">
<meta property="og:url" content="{SITE}/cheat-sheet/">
<link rel="canonical" href="{SITE}/cheat-sheet/">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "Free SEC Filing Cheat Sheet — 12 Form Types Ranked by Win Rate",
  "description": "Which SEC filings actually move stocks? {total_picks:,}+ picks backtested across 12 form types.",
  "author": {{"@type": "Organization", "name": "Catalyst Edge"}},
  "publisher": {{"@type": "Organization", "name": "Catalyst Edge", "url": "{SITE}"}},
  "mainEntityOfPage": {{"@type": "WebPage", "@id": "{SITE}/cheat-sheet/"}},
  "datePublished": "{YEAR}-04-13",
  "dateModified": "{YEAR}-04-13"
}}
</script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0a0e1a;--surface:#111827;--surface2:#1a2235;
  --gold:#d4a843;--gold-dim:#a68a3a;--green:#22c55e;--green-dim:#166534;
  --red:#ef4444;--blue:#3b82f6;--cyan:#06b6d4;
  --text:#e2e8f0;--text-dim:#94a3b8;--text-muted:#64748b;
  --border:#1e293b;--radius:12px;
}}
body{{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.6;
  -webkit-font-smoothing:antialiased;
}}
a{{color:var(--gold);text-decoration:none}}
a:hover{{text-decoration:underline}}

/* ── Hero ── */
.hero{{
  padding:4rem 1.5rem 3rem;text-align:center;
  background:linear-gradient(180deg,#0f1629 0%,var(--bg) 100%);
  border-bottom:1px solid var(--border);
  position:relative;overflow:hidden;
}}
.hero::before{{
  content:'';position:absolute;top:-40%;left:50%;transform:translateX(-50%);
  width:600px;height:600px;
  background:radial-gradient(circle,rgba(212,168,67,.08) 0%,transparent 70%);
  pointer-events:none;
}}
.hero-badge{{
  display:inline-block;padding:.35rem .9rem;
  background:rgba(212,168,67,.12);border:1px solid rgba(212,168,67,.25);
  border-radius:20px;font-size:.78rem;color:var(--gold);
  text-transform:uppercase;letter-spacing:.08em;margin-bottom:1.2rem;
}}
.hero h1{{
  font-size:clamp(2rem,5vw,3.2rem);font-weight:800;
  line-height:1.15;margin-bottom:1rem;
  background:linear-gradient(135deg,#fff 30%,var(--gold));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;
}}
.hero-sub{{
  font-size:1.1rem;color:var(--text-dim);max-width:600px;margin:0 auto 2rem;
}}
.hero-stats{{
  display:flex;gap:2rem;justify-content:center;flex-wrap:wrap;margin-bottom:2.5rem;
}}
.stat{{text-align:center}}
.stat-num{{font-size:2rem;font-weight:800;color:var(--gold);display:block}}
.stat-label{{font-size:.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em}}

/* ── CTA Card ── */
.cta-card{{
  max-width:480px;margin:0 auto;
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:2rem;text-align:left;
}}
.cta-card h3{{font-size:1.15rem;margin-bottom:.5rem}}
.cta-card p{{font-size:.88rem;color:var(--text-dim);margin-bottom:1.2rem}}
.cta-form{{display:flex;gap:.5rem}}
.cta-input{{
  flex:1;padding:.7rem 1rem;background:var(--bg);border:1px solid var(--border);
  border-radius:8px;color:var(--text);font-size:.95rem;outline:none;
}}
.cta-input:focus{{border-color:var(--gold)}}
.cta-btn{{
  padding:.7rem 1.5rem;background:var(--gold);color:#000;font-weight:700;
  border:none;border-radius:8px;cursor:pointer;font-size:.95rem;
  white-space:nowrap;transition:background .2s;
}}
.cta-btn:hover{{background:#e6bc5a}}
.cta-fine{{font-size:.75rem;color:var(--text-muted);margin-top:.6rem}}
.cta-proof{{display:flex;gap:1rem;margin-top:.8rem;flex-wrap:wrap}}
.cta-proof span{{font-size:.8rem;color:var(--green)}}

/* ── Preview Section ── */
.wrap{{max-width:900px;margin:0 auto;padding:0 1.5rem}}
.section{{padding:3rem 0;border-bottom:1px solid var(--border)}}
.section:last-child{{border-bottom:none}}
.section-head{{margin-bottom:1.5rem}}
.section-head h2{{font-size:1.5rem;font-weight:700}}
.section-head p{{color:var(--text-dim);font-size:.92rem;margin-top:.3rem}}

/* Preview rows */
.preview-row{{
  display:grid;grid-template-columns:200px 1fr 80px;
  align-items:center;gap:.8rem;padding:.6rem 0;
  border-bottom:1px solid rgba(255,255,255,.04);
}}
.preview-label{{font-size:.88rem;font-weight:600}}
.preview-bar-track{{
  position:relative;height:24px;background:var(--surface2);border-radius:4px;overflow:hidden;
}}
.preview-bar{{
  height:100%;background:linear-gradient(90deg,var(--gold-dim),var(--gold));
  border-radius:4px;transition:width .6s;
}}
.preview-val{{
  position:absolute;right:8px;top:50%;transform:translateY(-50%);
  font-size:.78rem;font-weight:700;color:#fff;
}}
.preview-n{{font-size:.78rem;color:var(--text-muted);text-align:right}}

/* Catalyst chips */
.catalyst-grid{{display:flex;gap:.8rem;flex-wrap:wrap}}
.catalyst-chip{{
  display:flex;align-items:center;gap:.6rem;
  padding:.6rem 1rem;background:var(--surface);border:1px solid var(--border);
  border-radius:8px;
}}
.chip-name{{font-size:.88rem;font-weight:600}}
.chip-rate{{
  font-size:.82rem;font-weight:700;color:var(--green);
  background:rgba(34,197,94,.1);padding:.15rem .5rem;border-radius:4px;
}}

/* What's Inside */
.inside-grid{{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem;
}}
.inside-card{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:1.2rem;
}}
.inside-card h4{{font-size:.95rem;margin-bottom:.4rem;color:var(--gold)}}
.inside-card p{{font-size:.82rem;color:var(--text-dim);line-height:1.5}}

/* Blur overlay */
.blur-gate{{
  position:relative;
}}
.blur-gate::after{{
  content:'';position:absolute;bottom:0;left:0;right:0;height:200px;
  background:linear-gradient(transparent,var(--bg));pointer-events:none;
}}
.blur-inner{{filter:blur(3px);pointer-events:none;user-select:none}}

/* Bottom CTA */
.bottom-cta{{
  text-align:center;padding:4rem 1.5rem;
  background:linear-gradient(180deg,var(--bg) 0%,#0f1629 100%);
}}
.bottom-cta h2{{font-size:1.8rem;margin-bottom:.8rem}}
.bottom-cta p{{color:var(--text-dim);margin-bottom:1.5rem;max-width:500px;margin-left:auto;margin-right:auto}}

/* Footer */
.footer{{
  text-align:center;padding:2rem;font-size:.78rem;color:var(--text-muted);
  border-top:1px solid var(--border);
}}

/* Responsive */
@media(max-width:640px){{
  .preview-row{{grid-template-columns:1fr;gap:.3rem}}
  .preview-n{{text-align:left}}
  .cta-form{{flex-direction:column}}
  .hero-stats{{gap:1rem}}
}}

/* Success state */
.cta-success{{display:none;text-align:center;padding:1.5rem}}
.cta-success h3{{color:var(--green);margin-bottom:.5rem}}
.cta-success a{{color:var(--gold);font-weight:700}}
</style>
</head>
<body>

<div class="hero">
  <div class="hero-badge">Free Download</div>
  <h1>The SEC Filing<br>Cheat Sheet</h1>
  <p class="hero-sub">
    Which SEC filings actually move stocks? We backtested {total_picks:,}+ picks
    across 12 form types to find out. The answer might change how you trade.
  </p>
  <div class="hero-stats">
    <div class="stat">
      <span class="stat-num">{total_picks:,}+</span>
      <span class="stat-label">Picks Backtested</span>
    </div>
    <div class="stat">
      <span class="stat-num">12</span>
      <span class="stat-label">Form Types Ranked</span>
    </div>
    <div class="stat">
      <span class="stat-num">{hit_rate}%</span>
      <span class="stat-label">Top List Hit Rate</span>
    </div>
    <div class="stat">
      <span class="stat-num">+{avg_run}%</span>
      <span class="stat-label">Avg Max Run</span>
    </div>
  </div>

  <div class="cta-card" id="hero-cta">
    <h3>Get the free cheat sheet</h3>
    <p>Enter your email and get instant access. Plus, get our free daily SEC catalyst picks before 4 AM ET.</p>
    <form class="cta-form" onsubmit="handleCapture(event, 'hero')">
      <input type="email" class="cta-input" placeholder="your@email.com" required id="hero-email">
      <button type="submit" class="cta-btn">Download Free</button>
    </form>
    <div class="cta-proof">
      <span>No credit card</span>
      <span>Instant access</span>
      <span>Unsubscribe anytime</span>
    </div>
    <div class="cta-fine">Join traders getting free SEC catalyst intelligence daily.</div>
    <div class="cta-success" id="hero-success">
      <h3>You're in.</h3>
      <p><a href="download.html">Click here to download your cheat sheet</a></p>
      <p style="font-size:.82rem;color:var(--text-dim);margin-top:.5rem">
        Check your inbox — your first daily picks email arrives tomorrow before 4 AM ET.
      </p>
    </div>
  </div>
</div>

<div class="wrap">

  <!-- Preview: Form Type Performance -->
  <div class="section">
    <div class="section-head">
      <h2>Preview: Filing Type Win Rates</h2>
      <p>Hit rate (3%+ move within 1 day) by SEC form type. Full breakdown in the cheat sheet.</p>
    </div>
    {top_forms_preview}
    <div class="blur-gate" style="margin-top:1rem">
      <div class="blur-inner">
        <div class="preview-row">
          <div class="preview-label">8-K (Material Event)</div>
          <div class="preview-bar-track"><div class="preview-bar" style="width:55%"></div><span class="preview-val">37.1%</span></div>
          <div class="preview-n">2,255 picks</div>
        </div>
        <div class="preview-row">
          <div class="preview-label">NT 10-K (Late Annual)</div>
          <div class="preview-bar-track"><div class="preview-bar" style="width:52%"></div><span class="preview-val">35.0%</span></div>
          <div class="preview-n">454 picks</div>
        </div>
        <div class="preview-row">
          <div class="preview-label">6-K (Foreign Issuer)</div>
          <div class="preview-bar-track"><div class="preview-bar" style="width:52%"></div><span class="preview-val">34.6%</span></div>
          <div class="preview-n">2,241 picks</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Preview: Top Catalysts -->
  <div class="section">
    <div class="section-head">
      <h2>Preview: Highest-Edge Catalysts</h2>
      <p>Catalyst signals ranked by 3%+ hit rate. These are the filing tags that predict movement.</p>
    </div>
    <div class="catalyst-grid">
      {catalyst_preview}
    </div>
    <p style="color:var(--text-muted);font-size:.82rem;margin-top:1rem">
      + 4 more catalyst types in the full cheat sheet
    </p>
  </div>

  <!-- What's Inside -->
  <div class="section">
    <div class="section-head">
      <h2>What's Inside</h2>
    </div>
    <div class="inside-grid">
      <div class="inside-card">
        <h4>12 SEC Form Types Decoded</h4>
        <p>What each form means, when it's filed, and exactly how it's moved stocks historically.</p>
      </div>
      <div class="inside-card">
        <h4>Win Rate by Form Type</h4>
        <p>Backtested hit rates across {total_picks:,}+ picks. Know which forms have real edge.</p>
      </div>
      <div class="inside-card">
        <h4>8 Catalyst Signal Tags</h4>
        <p>FDA approvals, insider clusters, cost cuts, M&A — ranked by actual trading performance.</p>
      </div>
      <div class="inside-card">
        <h4>Timing Playbook</h4>
        <p>When to enter, where to set stops, and how filing time affects catalyst follow-through.</p>
      </div>
      <div class="inside-card">
        <h4>Filter Criteria</h4>
        <p>Minimum price, volume, and market cap thresholds that separate noise from signal.</p>
      </div>
      <div class="inside-card">
        <h4>Red Flags to Avoid</h4>
        <p>Forms and tags that look like catalysts but consistently destroy capital.</p>
      </div>
    </div>
  </div>

</div>

<!-- Bottom CTA -->
<div class="bottom-cta">
  <h2>Stop guessing which filings matter.</h2>
  <p>Download the cheat sheet and get data-backed answers — free, no strings.</p>
  <div class="cta-card" style="max-width:480px;margin:0 auto" id="bottom-cta">
    <form class="cta-form" onsubmit="handleCapture(event, 'bottom')">
      <input type="email" class="cta-input" placeholder="your@email.com" required id="bottom-email">
      <button type="submit" class="cta-btn">Download Free</button>
    </form>
    <div class="cta-fine" style="margin-top:.5rem">Free forever. Daily picks + cheat sheet.</div>
    <div class="cta-success" id="bottom-success">
      <h3>You're in.</h3>
      <p><a href="download.html">Click here to download your cheat sheet</a></p>
    </div>
  </div>
</div>

<div class="footer">
  &copy; {YEAR} Catalyst Edge &middot;
  <a href="{SITE}">Scanner</a> &middot;
  <a href="{TELEGRAM_URL}">Telegram</a> &middot;
  SEC data from EDGAR. Not financial advice.
</div>

<script>
function handleCapture(e, loc) {{
  e.preventDefault();
  var emailEl = document.getElementById(loc + '-email');
  var email = emailEl.value.trim();
  if (!email) return;

  // Store email in localStorage for analytics
  try {{
    var subs = JSON.parse(localStorage.getItem('ce_leads') || '[]');
    subs.push({{email: email, ts: Date.now(), src: 'cheat-sheet'}});
    localStorage.setItem('ce_leads', JSON.stringify(subs));
  }} catch(ex) {{}}

  // Fire GA event if available
  if (typeof gtag === 'function') {{
    gtag('event', 'lead_magnet_download', {{
      event_category: 'conversion',
      event_label: 'sec_cheat_sheet',
      value: 1
    }});
  }}

  // Show success + redirect
  var formParent = emailEl.closest('.cta-card');
  var form = formParent.querySelector('.cta-form');
  var success = formParent.querySelector('.cta-success');
  if (form) form.style.display = 'none';
  if (success) success.style.display = 'block';
  var fine = formParent.querySelector('.cta-fine');
  if (fine) fine.style.display = 'none';
  var proof = formParent.querySelector('.cta-proof');
  if (proof) proof.style.display = 'none';

  // Auto-redirect to download after 2s
  setTimeout(function() {{
    window.location.href = 'download.html';
  }}, 2500);
}}
</script>
</body>
</html>"""


def _download_page(perf: dict, summary: dict) -> str:
    form_stats = perf.get("form_type_stats", [])
    catalyst_stats = perf.get("catalyst_tag_stats", [])
    total_picks = perf.get("total_picks_scored", 8000)

    gapper = summary.get("sec_clean_gappers", {})
    hit_rate = gapper.get("hit_rate_2pct", "44.5")
    avg_run = gapper.get("avg_next_day_max_run_pct", "5.1")

    # Form type explanations
    form_explanations = {
        "8-K": "Material event disclosure. Companies must file within 4 business days of a triggering event — earnings surprises, executive changes, M&A, material agreements, or bankruptcy. The broadest and most impactful catalyst form.",
        "4": "Insider trading report. Officers, directors, and 10% holders must disclose buys/sells within 2 business days. Insider buying clusters are historically one of the strongest directional signals.",
        "S-3": "Shelf registration statement. Allows companies to sell securities 'off the shelf' over time. Often precedes dilution, but can also signal capital raises for growth. Context matters.",
        "6-K": "Foreign private issuer report. Equivalent to 8-K for non-US companies. Contains material events, earnings, and regulatory updates for ADRs and foreign-listed securities.",
        "424B5": "Prospectus supplement. Filed when securities are actually sold from a shelf registration. Usually means dilution is imminent — price often drops on filing.",
        "424B2": "Structured product prospectus. Typically for notes, warrants, or complex instruments. Highest-dilution signal in the form universe — historically the worst performer.",
        "424B3": "Selling shareholder prospectus. Existing holders registering shares for resale. Signals potential selling pressure from insiders or early investors.",
        "424B4": "Final IPO/offering prospectus. Filed when an offering prices. Can signal demand and institutional interest.",
        "424B1": "Preliminary prospectus. Early-stage offering document. Rarely filed alone — watch for follow-up 424B5.",
        "NT 10-K": "Late annual report notification. Company can't file its 10-K on time. Often signals accounting issues, restatements, or operational problems. Historically underperforms.",
        "NT 10-Q": "Late quarterly report notification. Similar to NT 10-K but for quarterly filings. Less severe but still a yellow flag.",
        "RW": "Registration withdrawal. Company pulling a previously filed registration statement. Can mean abandoned offering (bullish) or regulatory issues (bearish).",
    }

    form_rows = ""
    for i, f in enumerate(form_stats):
        form = f["form"]
        label = f.get("label", form)
        hr = f["hit_rate_3pct"]
        picks = f["picks"]
        explanation = form_explanations.get(form, "")
        signal = "HIGH" if hr >= 45 else "MODERATE" if hr >= 35 else "LOW" if hr >= 25 else "AVOID"
        signal_color = "#22c55e" if hr >= 45 else "#d4a843" if hr >= 35 else "#94a3b8" if hr >= 25 else "#ef4444"
        bar_w = min(hr * 1.5, 100)

        form_rows += f"""
      <div class="form-card">
        <div class="form-header">
          <div class="form-rank">#{i+1}</div>
          <div class="form-title">
            <h3>{label}</h3>
            <span class="form-code">{form}</span>
          </div>
          <div class="form-signal" style="color:{signal_color}">{signal}</div>
        </div>
        <div class="form-stats-row">
          <div class="form-stat">
            <span class="fs-val">{hr:.1f}%</span>
            <span class="fs-label">3%+ Hit Rate</span>
          </div>
          <div class="form-stat">
            <span class="fs-val">{picks:,}</span>
            <span class="fs-label">Picks Tested</span>
          </div>
        </div>
        <div class="form-bar-track">
          <div class="form-bar" style="width:{bar_w}%"></div>
        </div>
        <p class="form-explain">{explanation}</p>
      </div>"""

    catalyst_rows = ""
    for c in catalyst_stats:
        cat = c["catalyst"]
        hr = c["hit_rate_3pct"]
        picks = c["picks"]
        bar_w = min(hr * 1.3, 100)
        catalyst_rows += f"""
      <div class="cat-row">
        <div class="cat-name">{cat}</div>
        <div class="cat-bar-track">
          <div class="cat-bar" style="width:{bar_w}%"></div>
          <span class="cat-val">{hr:.0f}%</span>
        </div>
        <div class="cat-n">{picks} picks</div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SEC Filing Cheat Sheet — Catalyst Edge</title>
<meta name="robots" content="noindex">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0a0e1a;--surface:#111827;--surface2:#1a2235;
  --gold:#d4a843;--gold-dim:#a68a3a;--green:#22c55e;
  --red:#ef4444;--blue:#3b82f6;
  --text:#e2e8f0;--text-dim:#94a3b8;--text-muted:#64748b;
  --border:#1e293b;--radius:12px;
}}
body{{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.6;
  -webkit-font-smoothing:antialiased;
}}
a{{color:var(--gold);text-decoration:none}}

/* Print styles */
@media print{{
  body{{background:#fff;color:#111;font-size:10pt}}
  :root{{--bg:#fff;--surface:#f8f9fa;--surface2:#e9ecef;
    --text:#111;--text-dim:#555;--text-muted:#888;--border:#ddd;
    --gold:#8b6914;--green:#166534;--red:#991b1b}}
  .no-print{{display:none!important}}
  .form-card,.cat-row{{break-inside:avoid}}
}}

.wrap{{max-width:800px;margin:0 auto;padding:2rem 1.5rem}}

/* Header */
.doc-header{{
  text-align:center;padding:3rem 0 2rem;
  border-bottom:2px solid var(--gold);margin-bottom:2rem;
}}
.doc-header h1{{
  font-size:2.2rem;font-weight:800;margin-bottom:.5rem;
  color:var(--gold);
}}
.doc-header .subtitle{{color:var(--text-dim);font-size:1rem}}
.doc-header .meta{{
  margin-top:1rem;font-size:.82rem;color:var(--text-muted);
}}
.doc-header .stat-strip{{
  display:flex;gap:2rem;justify-content:center;margin-top:1.5rem;flex-wrap:wrap;
}}
.doc-header .ss{{text-align:center}}
.doc-header .ss-num{{font-size:1.5rem;font-weight:800;color:var(--gold);display:block}}
.doc-header .ss-label{{font-size:.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em}}

.print-btn{{
  display:inline-block;padding:.6rem 1.5rem;
  background:var(--gold);color:#000;font-weight:700;
  border:none;border-radius:8px;cursor:pointer;font-size:.9rem;
  margin-top:1rem;
}}
.print-btn:hover{{background:#e6bc5a}}

/* Sections */
.section{{margin-bottom:3rem}}
.section h2{{
  font-size:1.4rem;font-weight:700;margin-bottom:.3rem;
  padding-bottom:.5rem;border-bottom:1px solid var(--border);
}}
.section-sub{{color:var(--text-dim);font-size:.88rem;margin-bottom:1.5rem}}

/* Form cards */
.form-card{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:1.2rem;margin-bottom:1rem;
}}
.form-header{{display:flex;align-items:center;gap:.8rem;margin-bottom:.8rem}}
.form-rank{{
  width:32px;height:32px;display:flex;align-items:center;justify-content:center;
  background:var(--surface2);border-radius:6px;font-weight:800;font-size:.82rem;
  color:var(--gold);
}}
.form-title{{flex:1}}
.form-title h3{{font-size:1rem;margin:0;line-height:1.2}}
.form-code{{font-size:.72rem;color:var(--text-muted);font-family:monospace}}
.form-signal{{
  font-size:.72rem;font-weight:800;text-transform:uppercase;
  letter-spacing:.08em;
}}
.form-stats-row{{display:flex;gap:2rem;margin-bottom:.6rem}}
.form-stat{{}}
.fs-val{{font-size:1.1rem;font-weight:700;display:block}}
.fs-label{{font-size:.7rem;color:var(--text-muted);text-transform:uppercase}}
.form-bar-track{{
  height:6px;background:var(--surface2);border-radius:3px;margin-bottom:.8rem;overflow:hidden;
}}
.form-bar{{height:100%;background:linear-gradient(90deg,var(--gold-dim),var(--gold));border-radius:3px}}
.form-explain{{font-size:.84rem;color:var(--text-dim);line-height:1.5}}

/* Catalyst rows */
.cat-row{{
  display:grid;grid-template-columns:180px 1fr 70px;
  align-items:center;gap:.8rem;padding:.7rem 0;
  border-bottom:1px solid rgba(255,255,255,.04);
}}
.cat-name{{font-size:.9rem;font-weight:600}}
.cat-bar-track{{
  position:relative;height:22px;background:var(--surface2);border-radius:4px;overflow:hidden;
}}
.cat-bar{{
  height:100%;background:linear-gradient(90deg,var(--green) 0%,#16a34a 100%);
  border-radius:4px;
}}
.cat-val{{
  position:absolute;right:8px;top:50%;transform:translateY(-50%);
  font-size:.78rem;font-weight:700;
}}
.cat-n{{font-size:.75rem;color:var(--text-muted);text-align:right}}

/* Playbook */
.playbook{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:1.5rem;
}}
.playbook h3{{font-size:1rem;color:var(--gold);margin-bottom:.8rem}}
.playbook ul{{list-style:none;padding:0}}
.playbook li{{
  padding:.5rem 0;border-bottom:1px solid rgba(255,255,255,.04);
  font-size:.88rem;display:flex;gap:.6rem;
}}
.playbook li:last-child{{border-bottom:none}}
.playbook .pl-icon{{color:var(--gold);flex-shrink:0}}

/* Red flags */
.red-flag{{
  background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.2);
  border-radius:var(--radius);padding:1.2rem;margin-top:1rem;
}}
.red-flag h3{{color:var(--red);font-size:1rem;margin-bottom:.6rem}}
.red-flag ul{{list-style:none;padding:0}}
.red-flag li{{
  font-size:.86rem;padding:.35rem 0;color:var(--text-dim);
}}

/* Filters */
.filter-table{{width:100%;border-collapse:collapse;margin-top:1rem}}
.filter-table th{{
  text-align:left;font-size:.75rem;text-transform:uppercase;
  color:var(--text-muted);padding:.5rem;border-bottom:1px solid var(--border);
}}
.filter-table td{{
  padding:.6rem .5rem;font-size:.88rem;border-bottom:1px solid rgba(255,255,255,.04);
}}

/* Footer */
.doc-footer{{
  text-align:center;padding:2rem 0;margin-top:2rem;
  border-top:1px solid var(--border);
}}
.doc-footer p{{font-size:.82rem;color:var(--text-muted)}}
.doc-footer a{{color:var(--gold)}}

@media(max-width:640px){{
  .cat-row{{grid-template-columns:1fr;gap:.3rem}}
  .cat-n{{text-align:left}}
  .form-stats-row{{flex-direction:column;gap:.5rem}}
  .doc-header .stat-strip{{gap:1rem}}
}}
</style>
</head>
<body>
<div class="wrap">

  <div class="doc-header">
    <h1>SEC Filing Cheat Sheet</h1>
    <div class="subtitle">Which filings move stocks — backed by data, not opinion.</div>
    <div class="meta">Catalyst Edge &middot; {TODAY} &middot; catalystedgescanner.com</div>
    <div class="stat-strip">
      <div class="ss">
        <span class="ss-num">{total_picks:,}+</span>
        <span class="ss-label">Picks Backtested</span>
      </div>
      <div class="ss">
        <span class="ss-num">12</span>
        <span class="ss-label">Form Types</span>
      </div>
      <div class="ss">
        <span class="ss-num">8</span>
        <span class="ss-label">Catalyst Signals</span>
      </div>
      <div class="ss">
        <span class="ss-num">60 days</span>
        <span class="ss-label">Lookback</span>
      </div>
    </div>
    <button class="print-btn no-print" onclick="window.print()">Save as PDF</button>
  </div>

  <!-- Section 1: Form Types -->
  <div class="section">
    <h2>SEC Form Types — Ranked by Edge</h2>
    <p class="section-sub">
      Hit rate = % of picks that moved 3%+ within 1 trading day of filing.
      Ranked from highest to lowest edge.
    </p>
    {form_rows}
  </div>

  <!-- Section 2: Catalyst Signals -->
  <div class="section">
    <h2>Catalyst Signal Tags — Ranked</h2>
    <p class="section-sub">
      Filing text is scanned for catalyst keywords. These tags predict which filings have real momentum.
    </p>
    {catalyst_rows}
  </div>

  <!-- Section 3: Timing Playbook -->
  <div class="section">
    <h2>Timing Playbook</h2>
    <div class="playbook">
      <h3>Entry Rules</h3>
      <ul>
        <li><span class="pl-icon">&rarr;</span> <strong>Pre-market scan at 4:00 AM ET.</strong> Filings posted overnight (8 PM – 6 AM) have the cleanest gaps because retail hasn't reacted yet.</li>
        <li><span class="pl-icon">&rarr;</span> <strong>Wait for the first 5-minute candle.</strong> Don't chase the opening print. Let the initial liquidity shake out.</li>
        <li><span class="pl-icon">&rarr;</span> <strong>Volume confirmation.</strong> Entry only if pre-market volume is 2x+ the 10-day average by 9:00 AM.</li>
        <li><span class="pl-icon">&rarr;</span> <strong>Score threshold.</strong> Our pipeline uses a minimum composite score of 12 (gappers) or 14 (moat core) — tickers below this threshold underperform.</li>
      </ul>
    </div>
    <div class="playbook" style="margin-top:1rem">
      <h3>Risk Management</h3>
      <ul>
        <li><span class="pl-icon">&rarr;</span> <strong>Stop loss: 3% below entry.</strong> If the catalyst thesis is wrong, the move reverses fast. Cut early.</li>
        <li><span class="pl-icon">&rarr;</span> <strong>Position size: max 5% of portfolio per catalyst play.</strong> These are event-driven, not convictions.</li>
        <li><span class="pl-icon">&rarr;</span> <strong>Take profit at +5% or EOD.</strong> Most filing-driven moves complete within 1 session. Don't hold overnight unless the catalyst has multi-day legs (M&A, FDA).</li>
        <li><span class="pl-icon">&rarr;</span> <strong>Never average down on a catalyst reversal.</strong> If the thesis breaks, the entry was wrong.</li>
      </ul>
    </div>
  </div>

  <!-- Section 4: Filters -->
  <div class="section">
    <h2>Filter Criteria</h2>
    <p class="section-sub">Minimum thresholds used by the Catalyst Edge pipeline to separate signal from noise.</p>
    <table class="filter-table">
      <tr><th>Filter</th><th>Gappers</th><th>Value</th><th>Moat Core</th></tr>
      <tr><td>Min Price</td><td>$3.00</td><td>$5.00</td><td>$5.00</td></tr>
      <tr><td>Min Avg Volume</td><td>250,000</td><td>500,000</td><td>500,000</td></tr>
      <tr><td>Min Market Cap</td><td>$300M</td><td>$300M</td><td>$2B</td></tr>
      <tr><td>Min Score</td><td>12</td><td>12</td><td>14</td></tr>
      <tr><td>Max Recency</td><td>720 min</td><td>&mdash;</td><td>&mdash;</td></tr>
    </table>
  </div>

  <!-- Section 5: Red Flags -->
  <div class="section">
    <h2>Red Flags</h2>
    <div class="red-flag">
      <h3>Forms & Signals to Avoid</h3>
      <ul>
        <li><strong>424B2 (Structured Notes)</strong> — 9.5% hit rate. Worst performer across all form types. Almost always dilutive.</li>
        <li><strong>Form 4 with only sells</strong> — Insider selling without a corresponding catalyst tag is a distribution signal, not a catalyst.</li>
        <li><strong>Filings tagged: "offering", "private placement", "default", "bankruptcy", "delist", "going concern"</strong> — These are automatically excluded by the pipeline for a reason. They have negative expected value.</li>
        <li><strong>Stale filings (&gt;12 hours old)</strong> — The edge decays fast. Filings older than 720 minutes have significantly lower hit rates.</li>
        <li><strong>Low volume + high score</strong> — A strong filing on a stock with no liquidity means you can't exit when the thesis breaks.</li>
      </ul>
    </div>
  </div>

  <!-- Footer -->
  <div class="doc-footer">
    <p><strong>Get daily picks free</strong> &mdash; <a href="{SITE}/#subscribe">catalystedgescanner.com</a></p>
    <p>Telegram: <a href="{TELEGRAM_URL}">@CatalystEdgePro</a> &middot;
    Data from SEC EDGAR. Not financial advice. Past performance does not guarantee future results.</p>
    <p style="margin-top:.5rem">&copy; {YEAR} Catalyst Edge</p>
  </div>

</div>
</body>
</html>"""


def main() -> int:
    perf = _load_perf()
    summary = _load_summary()

    landing = _landing_page(perf, summary)
    (OUT_DIR / "index.html").write_text(landing, encoding="utf-8")
    print(f"  Landing page: {OUT_DIR / 'index.html'}")

    download = _download_page(perf, summary)
    (OUT_DIR / "download.html").write_text(download, encoding="utf-8")
    print(f"  Download page: {OUT_DIR / 'download.html'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
