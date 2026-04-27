#!/usr/bin/env python3
"""Welcome journey email automation for Catalyst Edge newsletter.

Fetches all active Beehiiv subscribers and sends timed onboarding emails
at Day 0, 3, 7, and 14 after subscription.

Required env vars (loaded from .sec_email_env or shell):
  BEEHIIV_API_KEY  — Beehiiv v2 API key
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS  — Gmail SMTP credentials

Optional:
  EMAIL_FROM  — sender address (defaults to SMTP_USER)
  SMTP_USE_TLS — default true
"""

from __future__ import annotations

import datetime as dt
import json
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path


BEEHIIV_PUB_ID = "pub_9949283d-4561-4be2-be68-fd442b268d15"
JOURNEY_FILE = Path(__file__).parent / "subscriber_journey.json"
JOURNEY_DAYS = [0, 3, 7, 14]

BRAND_NAVY = "#0a0f1e"
BRAND_BLUE = "#3b82f6"
BRAND_WHITE = "#ffffff"
BRAND_LIGHT = "#f1f5f9"
BRAND_MUTED = "#94a3b8"


# ---------------------------------------------------------------------------
# Beehiiv helpers
# ---------------------------------------------------------------------------

def fetch_beehiiv_subscribers(api_key: str, pub_id: str) -> list[dict]:
    """Return list of active subscriber dicts with at least email + created_at."""
    subscribers: list[dict] = []
    page = 1
    api_base = "https://api.beehiiv.com/v2"

    while True:
        url = (
            f"{api_base}/publications/{pub_id}/subscriptions"
            f"?limit=100&status=active&page={page}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"WARNING: Beehiiv fetch failed {e.code}: {e.read().decode()[:200]}")
            break

        page_subs = body.get("data", [])
        for sub in page_subs:
            email = (sub.get("email") or "").strip()
            if email:
                subscribers.append(sub)

        # Beehiiv v2 pagination: check has_more + next page
        if body.get("has_more") or len(page_subs) == 100:
            page += 1
        else:
            break

    return subscribers


# ---------------------------------------------------------------------------
# Journey state helpers
# ---------------------------------------------------------------------------

def load_journey() -> dict[str, dict]:
    if not JOURNEY_FILE.exists():
        return {}
    try:
        return json.loads(JOURNEY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_journey(journey: dict[str, dict]) -> None:
    JOURNEY_FILE.write_text(json.dumps(journey, indent=2), encoding="utf-8")


def subscribed_date_from_sub(sub: dict) -> str:
    """Extract YYYY-MM-DD subscription date from Beehiiv subscriber dict."""
    # created_at is a Unix timestamp in Beehiiv v2
    created_at = sub.get("created_at")
    if created_at:
        try:
            ts = int(created_at)
            return dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    # Fallback: try status_updated field
    status_updated = sub.get("status_updated")
    if status_updated:
        try:
            ts = int(status_updated)
            return dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    return dt.date.today().isoformat()


# ---------------------------------------------------------------------------
# HTML email templates
# ---------------------------------------------------------------------------

def _base_html(title: str, content_html: str, preheader: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
{f'<div style="display:none;max-height:0;overflow:hidden;font-size:1px;color:#f1f5f9;">{preheader}</div>' if preheader else ''}
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f1f5f9;">
  <tr>
    <td align="center" style="padding:20px 10px;">
      <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

        <!-- HEADER -->
        <tr>
          <td style="background-color:{BRAND_NAVY};padding:28px 32px;text-align:center;">
            <p style="margin:0;font-size:22px;font-weight:700;color:{BRAND_WHITE};letter-spacing:0.5px;">
              ⚡ Catalyst Edge
            </p>
            <p style="margin:6px 0 0;font-size:12px;color:{BRAND_MUTED};letter-spacing:1px;text-transform:uppercase;">
              SEC Catalyst Intelligence
            </p>
          </td>
        </tr>

        <!-- BODY -->
        <tr>
          <td style="padding:32px 32px 24px;">
            {content_html}
          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td style="background-color:{BRAND_LIGHT};padding:20px 32px;border-top:1px solid #e2e8f0;">
            <p style="margin:0;font-size:11px;color:{BRAND_MUTED};line-height:1.6;text-align:center;">
              You're receiving this because you subscribed to Catalyst Edge.<br>
              <strong>Disclaimer:</strong> This newsletter is for informational and educational purposes only.
              Nothing here constitutes financial advice or a recommendation to buy or sell any security.
              Always do your own due diligence and consult a licensed financial advisor before making
              investment decisions. Past catalyst performance does not guarantee future results.<br><br>
              &copy; {dt.date.today().year} Catalyst Edge &nbsp;|&nbsp;
              <a href="https://catalystedge.agency" style="color:{BRAND_BLUE};text-decoration:none;">catalystedge.agency</a>
            </p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def _cta_button(text: str, url: str) -> str:
    return (
        f'<a href="{url}" style="display:inline-block;background-color:{BRAND_BLUE};'
        f'color:{BRAND_WHITE};padding:14px 28px;border-radius:6px;font-weight:700;'
        f'font-size:15px;text-decoration:none;letter-spacing:0.3px;">{text}</a>'
    )


def _h2(text: str) -> str:
    return f'<h2 style="margin:0 0 16px;font-size:22px;font-weight:700;color:{BRAND_NAVY};line-height:1.3;">{text}</h2>'


def _p(text: str) -> str:
    return f'<p style="margin:0 0 14px;font-size:15px;color:#334155;line-height:1.7;">{text}</p>'


def _li(text: str) -> str:
    return f'<li style="margin:0 0 8px;font-size:15px;color:#334155;line-height:1.6;">{text}</li>'


def _tag_pill(text: str, color: str = BRAND_NAVY) -> str:
    return (
        f'<span style="display:inline-block;background-color:{color};color:{BRAND_WHITE};'
        f'font-size:11px;font-weight:600;padding:3px 9px;border-radius:4px;'
        f'margin:2px 3px 2px 0;letter-spacing:0.3px;">{text}</span>'
    )


def build_day0_html() -> str:
    content = f"""
{_h2("Welcome to Catalyst Edge ⚡")}
{_p("You're in. Every weekday at <strong>4 AM ET</strong>, you get tickers with real, filed SEC catalysts — scored from 300+ EDGAR filings overnight. Not rumors. Not Twitter. Real filings.")}

<!-- ── MOVE TO PRIMARY BANNER ── -->
<div style="background-color:#fef9c3;border:1px solid #fde047;border-radius:8px;padding:14px 18px;margin:0 0 24px;">
  <p style="margin:0;font-size:14px;color:#713f12;line-height:1.6;">
    <strong>⚠️ Do this right now:</strong> Drag this email to your <strong>Primary</strong> tab (Gmail) or tap <strong>"Move to Primary"</strong>. On mobile, add us to VIP contacts. If our 4 AM alert lands in Promotions, you lose the edge before the market opens.
  </p>
</div>

<!-- ── SCANNER LINK ── -->
<div style="text-align:center;padding:4px 0 20px;">
  {_cta_button("Open the Live Scanner →", "https://catalystedgescanner.com")}
  <p style="margin:8px 0 0;font-size:12px;color:{BRAND_MUTED};">Updated every night. Check it at 4:15 AM ET — after the newsletter arrives.</p>
</div>

<!-- ── QUICK START CHECKLIST ── -->
<p style="margin:0 0 12px;font-size:16px;font-weight:700;color:{BRAND_NAVY};">🚀 Your 3-Step Quick Start</p>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 24px;">
  <tr>
    <td style="padding:12px 16px;background-color:#f8fafc;border-radius:8px 8px 0 0;border-bottom:1px solid #e2e8f0;vertical-align:top;">
      <p style="margin:0;font-size:14px;color:{BRAND_NAVY};line-height:1.6;">
        <strong>1. Bookmark the Scanner</strong><br>
        <a href="https://catalystedgescanner.com" style="color:{BRAND_BLUE};text-decoration:none;">catalystedgescanner.com</a> — check it at <strong>4:15 AM ET</strong> after your newsletter arrives. The heatmap shows which sectors have the hottest filings in seconds.
      </p>
    </td>
  </tr>
  <tr>
    <td style="padding:12px 16px;background-color:#f8fafc;border-bottom:1px solid #e2e8f0;vertical-align:top;">
      <p style="margin:0;font-size:14px;color:{BRAND_NAVY};line-height:1.6;">
        <strong>2. Whitelist us</strong><br>
        Move this email to <strong>Primary</strong> (or add <a href="mailto:opensource@example.com" style="color:{BRAND_BLUE};text-decoration:none;">opensource@example.com</a> to your contacts). One missed 4 AM alert = one missed setup.
      </p>
    </td>
  </tr>
  <tr>
    <td style="padding:12px 16px;background-color:#f8fafc;border-radius:0 0 8px 8px;vertical-align:top;">
      <p style="margin:0;font-size:14px;color:{BRAND_NAVY};line-height:1.6;">
        <strong>3. Watch the 2-minute demo</strong><br>
        <a href="https://www.youtube.com/@CatalystEdgePro" style="color:{BRAND_BLUE};text-decoration:none;">YouTube: @CatalystEdgePro</a> — see how to spot a <strong>🐋 Contrarian Whale</strong> filing in under 10 seconds, and how the SEC Sector Heatmap filters 300+ filings instantly.
      </p>
    </td>
  </tr>
</table>

<!-- ── PROOF BLOCK ── -->
<div style="background-color:#0a0f1e;border-radius:8px;padding:20px 22px;margin:0 0 24px;">
  <p style="margin:0 0 10px;font-size:13px;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;">Scanner Performance — Last 60 Days</p>
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td style="text-align:center;padding:8px;">
        <p style="margin:0;font-size:28px;font-weight:800;color:#3fb950;">41%</p>
        <p style="margin:4px 0 0;font-size:11px;color:#94a3b8;">Picks hit +2%</p>
      </td>
      <td style="text-align:center;padding:8px;border-left:1px solid #30363d;">
        <p style="margin:0;font-size:28px;font-weight:800;color:#58a6ff;">5.0%</p>
        <p style="margin:4px 0 0;font-size:11px;color:#94a3b8;">Avg intraday high</p>
      </td>
      <td style="text-align:center;padding:8px;border-left:1px solid #30363d;">
        <p style="margin:0;font-size:28px;font-weight:800;color:#bc8cff;">485</p>
        <p style="margin:4px 0 0;font-size:11px;color:#94a3b8;">Picks tracked</p>
      </td>
    </tr>
  </table>
  <p style="margin:12px 0 0;font-size:11px;color:#8b949e;text-align:center;">Backtested against next-day open · 8-K catalyst plays only · updated daily</p>
</div>

<!-- ── WHAT YOU GET ── -->
<p style="margin:0 0 12px;font-size:15px;font-weight:600;color:{BRAND_NAVY};">What lands in your inbox every morning:</p>
<ul style="margin:0 0 20px;padding-left:22px;">
  {_li('<strong>⚡ Gapper Plays</strong> — High-conviction next-day gap setups from fresh 8-K filings')}
  {_li('<strong>💎 Value Plays</strong> — Insider buying, buybacks, activist 13D/13G positions')}
  {_li('<strong>🏰 Moat Picks</strong> — Large-cap durable companies with catalyst events')}
  {_li('<strong>🌡️ Sector Heatmap</strong> — Which sectors have the hottest EDGAR filings right now')}
  {_li('<strong>🐋 Contrarian Whale alerts</strong> — Insiders buying into bad news (highest-conviction signal)')}
</ul>

<!-- ── PS UPSELL ── -->
<div style="border-top:1px solid #e2e8f0;margin-top:8px;padding-top:20px;">
  <p style="margin:0;font-size:14px;color:#334155;line-height:1.7;">
    <strong>P.S.</strong> You're currently on the free plan. The <strong>Founding Member rate is $9/mo</strong> — locked in forever once you upgrade. There are a limited number of spots before the price moves to $19/mo. If you want the full list (all gappers, all value plays, moat core, Polymarket macro signals, and real-time alerts), <a href="https://catalystedge.agency" style="color:{BRAND_BLUE};font-weight:600;text-decoration:none;">lock in your rate here →</a>
  </p>
</div>
"""
    return _base_html(
        "Welcome to Catalyst Edge ⚡",
        content,
        preheader="3 things to do right now — bookmark the scanner, whitelist us, watch the demo."
    )


def build_day3_html() -> str:
    content = f"""
{_h2("How to read your Catalyst Edge picks")}
{_p("You've had a few issues now. Here's a quick decoder so you can get maximum value from every pick.")}

<p style="margin:0 0 12px;font-size:16px;font-weight:600;color:{BRAND_NAVY};">The three scores explained:</p>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 20px;border-collapse:collapse;">
  <tr>
    <td style="padding:10px 14px;background-color:#eff6ff;border-radius:6px 6px 0 0;border-bottom:1px solid #bfdbfe;">
      <strong style="color:#1e40af;">⚡ Gapper Score</strong>
      <p style="margin:4px 0 0;font-size:13px;color:#334155;line-height:1.5;">How likely the stock is to gap up significantly the next trading day. High scores come from fresh 8-K filings with positive keywords like FDA approval, record revenue, contract awards, or definitive agreements — filed within 4 hours of market close.</p>
    </td>
  </tr>
  <tr>
    <td style="padding:10px 14px;background-color:#f0fdf4;border-bottom:1px solid #bbf7d0;">
      <strong style="color:#065f46;">💎 Value Score</strong>
      <p style="margin:4px 0 0;font-size:13px;color:#334155;line-height:1.5;">Fundamental quality signals — insider purchases (Form 4 "Transaction Code P"), share buyback announcements, activist 13D/13G filings, dividend increases. Filtered for price > $5 and avg volume > 500K.</p>
    </td>
  </tr>
  <tr>
    <td style="padding:10px 14px;background-color:#fff7ed;border-radius:0 0 6px 6px;">
      <strong style="color:#7c2d12;">🏰 Moat Score</strong>
      <p style="margin:4px 0 0;font-size:13px;color:#334155;line-height:1.5;">Competitive durability — patents, exclusive agreements, multi-year contracts, recurring revenue, pricing power. Best for longer-term watch candidates.</p>
    </td>
  </tr>
</table>

<p style="margin:0 0 12px;font-size:16px;font-weight:600;color:{BRAND_NAVY};">What the tags mean:</p>
<div style="margin:0 0 20px;">
  {_tag_pill("+fda approval", "#1e40af")}
  {_tag_pill("+definitive agreement", "#1e40af")}
  {_tag_pill("+contract award", "#1e40af")}
  {_tag_pill("+record revenue", "#065f46")}
  {_tag_pill("+insider_buy_p", "#065f46")}
  {_tag_pill("+buyback", "#065f46")}
  {_tag_pill("+patent", "#7c2d12")}
  {_tag_pill("+recurring revenue", "#7c2d12")}
</div>
{_p("Tags starting with <strong>+</strong> are positive catalysts. Tags starting with <strong>-</strong> are risk flags (dilution, going concern, etc.) — avoid those for gap plays.")}

<div style="background-color:#fff7ed;border-left:4px solid #f59e0b;padding:16px 20px;border-radius:0 6px 6px 0;margin:0 0 24px;">
  <p style="margin:0;font-size:14px;color:#334155;line-height:1.6;">
    <strong>Pro tip for gap plays:</strong> Focus on Gapper Score ≥ 9, recency ≤ 180 minutes, and no <strong>-offering</strong> or <strong>-dilution</strong> tags. These are your highest-conviction next-day setups.
  </p>
</div>

<div style="background-color:#fef2f2;border-radius:6px;padding:14px 18px;margin:0 0 20px;">
  <p style="margin:0;font-size:13px;color:#991b1b;line-height:1.6;">
    <strong>Risk Disclaimer:</strong> Catalyst Edge picks are sourced from public SEC filings and scored algorithmically. They are not financial advice. SEC filings can be complex; always read the original filing. Past catalyst patterns do not guarantee future price action. Never risk money you cannot afford to lose.
  </p>
</div>

<div style="text-align:center;padding:8px 0 8px;">
  {_cta_button("Read Today's Issue →", "https://catalystedge.agency")}
</div>
"""
    return _base_html(
        "How to read your Catalyst Edge picks",
        content,
        preheader="Gapper score, value score, moat score — here's exactly what each one means."
    )


def build_day7_html() -> str:
    content = f"""
{_h2("7 days in — here's how our picks performed")}
{_p("You've been with Catalyst Edge for a week. Let's talk about how we measure performance — and why we built a backtesting system into the pipeline.")}

<p style="margin:0 0 12px;font-size:16px;font-weight:600;color:{BRAND_NAVY};">How our backtesting works:</p>
{_p("Every ticker we publish gets logged automatically. Each day, our pipeline looks back at past picks and records the next-day price move using historical EDGAR data cross-referenced against price history.")}

<div style="background-color:#f8fafc;border-radius:6px;padding:16px 20px;margin:0 0 20px;border:1px solid #e2e8f0;">
  <p style="margin:0 0 10px;font-size:14px;font-weight:600;color:{BRAND_NAVY};">What counts as a "hit":</p>
  <ul style="margin:0;padding-left:20px;">
    {_li('Next-day open-to-close move of <strong>≥ 3%</strong> in the direction of the catalyst')}
    {_li('Scored within 12 hours of market open following the filing')}
    {_li('No disqualifying risk flags (-offering, -going concern, etc.)')}
  </ul>
</div>

{_p("As our dataset grows, you'll start seeing a <strong>hit rate</strong> in each issue — the percentage of past picks that hit the ≥3% threshold. Early data is sparse, but it builds every trading day.")}

<div style="background-color:#eff6ff;border-left:4px solid {BRAND_BLUE};padding:16px 20px;border-radius:0 6px 6px 0;margin:0 0 24px;">
  {_p('<strong>Stay tuned:</strong> Track record data builds over time. By 30 days, you\'ll have a meaningful sample. By 60 days, you\'ll be able to see which catalyst types and sectors perform best.')}
</div>

<p style="margin:0 0 12px;font-size:16px;font-weight:600;color:{BRAND_NAVY};">Coming soon for premium subscribers:</p>
<ul style="margin:0 0 20px;padding-left:22px;">
  {_li('Full sector-by-catalyst hit rate breakdown')}
  {_li('Historical win rate by form type (8-K, Form 4, 13D)')}
  {_li('Deeper moat analysis with revenue/margin trend data')}
  {_li('Priority alerts when a high-conviction catalyst drops')}
</ul>

<div style="text-align:center;padding:8px 0 16px;">
  {_cta_button("Read Today's Issue →", "https://catalystedge.agency")}
</div>
"""
    return _base_html(
        "7 days in — track record & backtesting",
        content,
        preheader="How we track performance — and what a ≥3% hit rate actually means."
    )


def build_day14_html() -> str:
    content = f"""
{_h2("Upgrade to Catalyst Edge Premium ⚡")}
{_p("Two weeks in. You've seen how the picks are structured and sourced. Now it's time to go deeper.")}

<p style="margin:0 0 12px;font-size:16px;font-weight:600;color:{BRAND_NAVY};">What Premium includes:</p>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 24px;border-collapse:collapse;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0;">
  <tr style="background-color:{BRAND_NAVY};">
    <td style="padding:10px 16px;font-size:13px;font-weight:600;color:{BRAND_WHITE};">Feature</td>
    <td style="padding:10px 16px;font-size:13px;font-weight:600;color:{BRAND_WHITE};text-align:center;">Free</td>
    <td style="padding:10px 16px;font-size:13px;font-weight:600;color:#fbbf24;text-align:center;">Premium ⚡</td>
  </tr>
  <tr style="background-color:#f8fafc;">
    <td style="padding:10px 16px;font-size:13px;color:#334155;">Daily Gapper Picks (8-K catalyst)</td>
    <td style="padding:10px 16px;font-size:13px;color:#334155;text-align:center;">✓ Top 5</td>
    <td style="padding:10px 16px;font-size:13px;color:#065f46;font-weight:600;text-align:center;">✓ Full list</td>
  </tr>
  <tr>
    <td style="padding:10px 16px;font-size:13px;color:#334155;">Value Picks (Form 4 / 13D / buybacks)</td>
    <td style="padding:10px 16px;font-size:13px;color:#334155;text-align:center;">✓ Top 3</td>
    <td style="padding:10px 16px;font-size:13px;color:#065f46;font-weight:600;text-align:center;">✓ Full list</td>
  </tr>
  <tr style="background-color:#f8fafc;">
    <td style="padding:10px 16px;font-size:13px;color:#334155;">Moat Core Picks (large cap, durable)</td>
    <td style="padding:10px 16px;font-size:13px;color:#64748b;text-align:center;">—</td>
    <td style="padding:10px 16px;font-size:13px;color:#065f46;font-weight:600;text-align:center;">✓ Included</td>
  </tr>
  <tr>
    <td style="padding:10px 16px;font-size:13px;color:#334155;">Earlier delivery (3:30 AM ET)</td>
    <td style="padding:10px 16px;font-size:13px;color:#64748b;text-align:center;">—</td>
    <td style="padding:10px 16px;font-size:13px;color:#065f46;font-weight:600;text-align:center;">✓ Priority</td>
  </tr>
  <tr style="background-color:#f8fafc;">
    <td style="padding:10px 16px;font-size:13px;color:#334155;">Hit rate track record data</td>
    <td style="padding:10px 16px;font-size:13px;color:#64748b;text-align:center;">Summary only</td>
    <td style="padding:10px 16px;font-size:13px;color:#065f46;font-weight:600;text-align:center;">✓ Full breakdown</td>
  </tr>
  <tr>
    <td style="padding:10px 16px;font-size:13px;color:#334155;">Priority catalyst alerts</td>
    <td style="padding:10px 16px;font-size:13px;color:#64748b;text-align:center;">—</td>
    <td style="padding:10px 16px;font-size:13px;color:#065f46;font-weight:600;text-align:center;">✓ Real-time</td>
  </tr>
</table>

<div style="background-color:#fefce8;border:2px solid #fbbf24;border-radius:8px;padding:20px 24px;margin:0 0 24px;text-align:center;">
  <p style="margin:0 0 6px;font-size:24px;font-weight:700;color:{BRAND_NAVY};">$9 / month</p>
  <p style="margin:0 0 16px;font-size:14px;color:#64748b;">Founding member rate — <strong>locked in forever</strong>. Price goes up for future subscribers.</p>
  {_cta_button("Upgrade to Premium → $9/month", "https://catalystedgescanner.com/pricing/")}
  <p style="margin:12px 0 0;font-size:12px;color:{BRAND_MUTED};">Cancel anytime. No contracts.</p>
</div>

{_p("You joined early. The founding member rate is your reward — it never goes up as long as you stay subscribed.")}

<div style="text-align:center;padding:4px 0 8px;">
  <a href="https://catalystedge.agency" style="color:{BRAND_MUTED};font-size:13px;text-decoration:none;">
    Stay on the free plan →
  </a>
</div>
"""
    return _base_html(
        "Upgrade to Catalyst Edge Premium",
        content,
        preheader="Founding member rate: $9/month — locked in forever. Upgrade today."
    )


EMAIL_TEMPLATES = {
    0: {
        "subject": "Welcome to Catalyst Edge ⚡ — Here's what to expect",
        "builder": build_day0_html,
    },
    3: {
        "subject": "How to read your Catalyst Edge picks",
        "builder": build_day3_html,
    },
    7: {
        "subject": "7 days in — here's how our picks performed",
        "builder": build_day7_html,
    },
    14: {
        "subject": "Upgrade to Catalyst Edge Premium ⚡",
        "builder": build_day14_html,
    },
}


# ---------------------------------------------------------------------------
# SMTP helpers
# ---------------------------------------------------------------------------

def send_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    email_from: str,
    use_tls: bool,
    to_email: str,
    subject: str,
    html_body: str,
) -> None:
    plain = f"{subject}\n\nView this email in an HTML-capable email client.\nhttps://catalystedge.agency"
    msg = EmailMessage()
    msg["From"] = email_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(plain)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        smtp.send_message(msg)


# ---------------------------------------------------------------------------
# Main journey logic
# ---------------------------------------------------------------------------

def main() -> int:
    beehiiv_api_key = os.getenv("BEEHIIV_API_KEY", "").strip()
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port_raw = os.getenv("SMTP_PORT", "587").strip()
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip().replace(" ", "")
    email_from = os.getenv("EMAIL_FROM", smtp_user).strip()
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}

    if not beehiiv_api_key:
        print("ERROR: BEEHIIV_API_KEY not set")
        return 1
    if not all([smtp_host, smtp_port_raw, smtp_user, smtp_pass]):
        print("ERROR: SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS not fully set")
        return 1

    smtp_port = int(smtp_port_raw)
    today = dt.date.today()
    today_str = today.isoformat()

    print(f"journey_start date={today_str}")

    # Load subscribers
    print("Fetching Beehiiv subscribers...")
    try:
        subscribers = fetch_beehiiv_subscribers(beehiiv_api_key, BEEHIIV_PUB_ID)
    except Exception as e:
        print(f"ERROR: Could not fetch subscribers: {e}")
        return 1
    print(f"Found {len(subscribers)} active subscribers")

    # Load existing journey state
    journey = load_journey()

    counts = {"new": 0, "day3": 0, "day7": 0, "day14": 0, "skipped": 0}

    for sub in subscribers:
        email = (sub.get("email") or "").strip().lower()
        if not email:
            continue

        # Determine subscription date
        if email in journey:
            subscribed_date_str = journey[email]["subscribed_date"]
        else:
            subscribed_date_str = subscribed_date_from_sub(sub)

        try:
            subscribed_date = dt.date.fromisoformat(subscribed_date_str)
        except ValueError:
            subscribed_date = today

        # Figure out what to send today
        days_since = (today - subscribed_date).days

        if email not in journey:
            # New subscriber — add to journey and send Day 0
            journey[email] = {
                "subscribed_date": subscribed_date_str,
                "steps_sent": [],
            }
            step = 0
        else:
            steps_sent = journey[email].get("steps_sent", [])
            # Check each remaining journey day
            step = None
            for d in JOURNEY_DAYS[1:]:  # skip 0, already handled above
                if days_since == d and d not in steps_sent:
                    step = d
                    break

            if step is None:
                counts["skipped"] += 1
                continue

        template = EMAIL_TEMPLATES[step]
        subject = template["subject"]
        html_body = template["builder"]()

        try:
            send_email(
                smtp_host, smtp_port, smtp_user, smtp_pass,
                email_from, use_tls, email, subject, html_body
            )
            journey[email]["steps_sent"].append(step)
            if step == 0:
                counts["new"] += 1
                print(f"  [day0] sent to {email}")
            elif step == 3:
                counts["day3"] += 1
                print(f"  [day3] sent to {email}")
            elif step == 7:
                counts["day7"] += 1
                print(f"  [day7] sent to {email}")
            elif step == 14:
                counts["day14"] += 1
                print(f"  [day14] sent to {email}")
        except Exception as e:
            print(f"  WARNING: Failed to send to {email} (day {step}): {e}")

    save_journey(journey)
    total = len(subscribers)
    print(
        f"journey_processed subscribers={total} "
        f"new={counts['new']} day3={counts['day3']} "
        f"day7={counts['day7']} day14={counts['day14']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
