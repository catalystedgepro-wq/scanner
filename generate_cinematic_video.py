#!/usr/bin/env python3
"""generate_cinematic_video.py — Cinematic daily briefing for Catalyst Edge.

100% free tools: Pillow hero frames + FFmpeg Ken Burns motion + crossfade
transitions + timed data overlays + karaoke captions + voice + music bed.

No paid APIs (no fal.ai, no D-ID, no Replicate).

Output:  social/anchor_YYYY-MM-DD.mp4
         anchor_video.mp4

Setup:
  pip install --break-system-packages Pillow edge-tts
  Run: python3 generate_cinematic_video.py
"""

from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from generate_anchor_video import (
    HAS_PIL, W, H, FPS, TODAY, TODAY_DISPLAY, DOW,
    ROOT, WIN_OUT,
    DARK_BG, CARD_BG, BLUE, PURPLE, RED, GREEN, WHITE, GRAY, LIGHT_GRAY,
    CAT_COLOR, CAT_BG, CAT_LABEL,
    load_pick, get_category, clean_tags, load_top5_scores, build_script,
    gen_audio as _gen_audio_orig, audio_duration, gen_music, load_fonts,
    draw_rr, tsize, shadow, centered, hbar_rgba, lerp, lerp_a,
)


def gen_audio(script: str, mp3, ass, el_api_key: str = ""):
    """Wrapper that falls back to edge-tts if ElevenLabs quota is exhausted."""
    try:
        return _gen_audio_orig(script, mp3, ass, el_api_key)
    except Exception as e:
        if "quota" in str(e).lower() or "401" in str(e):
            print(f"    ElevenLabs quota exhausted — falling back to edge-tts")
            return _gen_audio_orig(script, mp3, ass, "")
        raise

if HAS_PIL:
    from PIL import Image, ImageDraw, ImageFilter


# ═══════════════════════════════════════════════════════════════════════════
#  HERO FRAME RENDERERS
# ═══════════════════════════════════════════════════════════════════════════

def _vignette(draw: ImageDraw.Draw, step: int = 4, intensity: int = 30,
              tint: tuple = (0, 0, 8)):
    """Dark-corner radial vignette."""
    for y in range(0, H, step):
        for x in range(0, W, step):
            dx = (x - W / 2) / (W / 2)
            dy = (y - H / 2) / (H / 2)
            dist = min(1.0, (dx * dx + dy * dy) ** 0.5)
            b = int(intensity * (1 - dist * 0.75))
            c = tuple(max(0, DARK_BG[i] + b + tint[i]) for i in range(3))
            draw.rectangle([x, y, x + step - 1, y + step - 1], fill=(*c, 255))


def _grid(draw: ImageDraw.Draw, spacing: int = 90, alpha: int = 14):
    """Faint blue grid overlay."""
    for x in range(0, W, spacing):
        draw.line([(x, 0), (x, H)], fill=(*BLUE, alpha))
    for y in range(0, H, spacing):
        draw.line([(0, y), (W, y)], fill=(*BLUE, alpha))


def _scanlines(draw: ImageDraw.Draw, step: int = 4, alpha: int = 10):
    """CRT-style horizontal scan lines."""
    for y in range(0, H, step):
        draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))


def _bokeh(draw: ImageDraw.Draw, count: int = 60, seed: int = 42,
           colors: list | None = None):
    """Scattered bokeh particles."""
    random.seed(seed)
    palette = colors or [BLUE, (*lerp(BLUE, WHITE, 0.5),), GREEN, (100, 200, 255)]
    for _ in range(count):
        px, py = random.randint(0, W), random.randint(0, H)
        pr = random.randint(3, 18)
        pa = random.randint(12, 55)
        pc = random.choice(palette)
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(*pc[:3], pa))


# ── Frame 1: Market Pulse (intro) ───────────────────────────────────────
def render_market_pulse(fonts: dict) -> Image.Image:
    """Dark trading floor with glowing candlestick chart and particles."""
    img = Image.new("RGBA", (W, H), (*DARK_BG, 255))
    draw = ImageDraw.Draw(img)

    _vignette(draw, tint=(0, 0, 12))

    # Volumetric light cone from top centre
    cx = W // 2
    for r in range(500, 0, -3):
        a = int(22 * (1 - r / 500))
        draw.ellipse([cx - r, -int(r * 0.4), cx + r, int(r * 1.6)],
                     fill=(*lerp(BLUE, (100, 200, 255), 0.3), a))

    _grid(draw)

    # ── Candlestick chart ────────────────────────────────────────────────
    chart_cx, chart_cy = W // 2, H // 2 - 80
    n_candles = 14
    cw, gap = 38, 14
    total_w = n_candles * (cw + gap)
    sx = chart_cx - total_w // 2
    chart_h = 650
    chart_top = chart_cy - chart_h // 2

    random.seed(42)
    prices = [100.0]
    for _ in range(n_candles):
        prices.append(prices[-1] + random.uniform(-7, 7))
    pmin, pmax = min(prices) - 10, max(prices) + 10

    def p2y(p: float) -> int:
        return int(chart_top + chart_h * (1 - (p - pmin) / (pmax - pmin)))

    for i in range(n_candles):
        x = sx + i * (cw + gap)
        o, c = prices[i], prices[i + 1]
        high = max(o, c) + random.uniform(2, 6)
        low = min(o, c) - random.uniform(2, 6)
        bull = c >= o
        col = GREEN if bull else RED

        # Wick
        draw.line([(x + cw // 2, p2y(high)), (x + cw // 2, p2y(low))],
                  fill=(*col, 170), width=2)

        # Body glow
        by1, by2 = p2y(max(o, c)), p2y(min(o, c))
        bh = max(4, by2 - by1)
        for g in range(3, 0, -1):
            draw.rectangle([x - g * 3, by1 - g * 3, x + cw + g * 3, by1 + bh + g * 3],
                           fill=(*col, 6 * g))

        # Body
        fill_col = (*col, 220) if bull else (*DARK_BG, 255)
        draw.rectangle([x, by1, x + cw, by1 + bh], fill=fill_col,
                       outline=(*col, 255), width=2)

    # Price level lines
    for i in range(5):
        y = chart_top + int(chart_h * i / 4)
        for g in range(3):
            draw.line([(sx - 30, y + g), (sx + total_w + 30, y + g)],
                      fill=(*GRAY, 20 - g * 6))
        p = pmin + (pmax - pmin) * (1 - i / 4)
        draw.text((sx + total_w + 40, y - 12), f"{p:.0f}",
                  font=fonts["small"], fill=(*GRAY, 100))

    # Volume bars (subtle, below chart)
    vol_y = chart_top + chart_h + 30
    vol_h = 80
    for i in range(n_candles):
        x = sx + i * (cw + gap)
        vh = random.randint(15, vol_h)
        col = GREEN if prices[i + 1] >= prices[i] else RED
        draw.rectangle([x, vol_y + vol_h - vh, x + cw, vol_y + vol_h],
                       fill=(*col, 50))

    _bokeh(draw, 90, seed=42)

    # Timestamp + market label
    draw.text((60, H - 140), "PRE-MARKET  04:00 AM ET", font=fonts["body"],
              fill=(*GRAY, 140))
    draw.text((60, H - 90), "S&P FUTURES  ·  NASDAQ  ·  DOW",
              font=fonts["small"], fill=(*GRAY, 80))

    _scanlines(draw)
    return img


# ── Frame 2: Ticker Hero Reveal ─────────────────────────────────────────
def render_ticker_hero(ticker: str, category: str, score: float,
                       form: str, fonts: dict) -> Image.Image:
    """Dramatic ticker with radial glow, score gauge, and energy lines."""
    cat_col = CAT_COLOR[category]
    img = Image.new("RGBA", (W, H), (*DARK_BG, 255))
    draw = ImageDraw.Draw(img)

    cx, cy = W // 2, H // 2 - 100

    # Radial burst
    for r in range(620, 0, -4):
        a = int(35 * (1 - r / 620) ** 1.4)
        c = lerp(cat_col, WHITE, 0.15)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*c, a))

    # Energy lines
    random.seed(hash(ticker) % 10000)
    for _ in range(28):
        angle = random.uniform(0, 2 * math.pi)
        r1, r2 = random.randint(180, 340), random.randint(400, 720)
        x1, y1 = cx + int(r1 * math.cos(angle)), cy + int(r1 * math.sin(angle))
        x2, y2 = cx + int(r2 * math.cos(angle)), cy + int(r2 * math.sin(angle))
        draw.line([(x1, y1), (x2, y2)], fill=(*cat_col, random.randint(25, 70)), width=2)

    _grid(draw, 120, 10)

    # ── Giant ticker with multi-layer glow ───────────────────────────────
    tk_text = f"${ticker}"
    tw, th = tsize(draw, tk_text, fonts["giant"])
    tx, ty = (W - tw) // 2, cy - th // 2

    for g in [22, 16, 10, 5]:
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.text((tx, ty), tk_text, font=fonts["giant"],
                fill=(*cat_col, 12 + g * 3))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=g * 2))
        img = Image.alpha_composite(img, glow)
        draw = ImageDraw.Draw(img)

    shadow(draw, (tx, ty), tk_text, fonts["giant"], (*WHITE, 255), 5)

    # ── Score gauge arc ──────────────────────────────────────────────────
    gauge_cy = cy + th // 2 + 110
    gauge_r = 170

    # Background arc
    for a_deg in range(-140, 140):
        a = math.radians(a_deg)
        for dr in range(-4, 5):
            px = cx + int((gauge_r + dr) * math.cos(a))
            py = gauge_cy + int((gauge_r + dr) * math.sin(a))
            if 0 <= px < W and 0 <= py < H:
                draw.point((px, py), fill=(*GRAY, 35))

    # Filled arc
    fill_deg = int(280 * min(1.0, score / 16.0))
    for a_deg in range(-140, -140 + fill_deg):
        a = math.radians(a_deg)
        t = (a_deg + 140) / 280
        gc = lerp(cat_col, WHITE, t * 0.4)
        for dr in range(-3, 4):
            px = cx + int((gauge_r + dr) * math.cos(a))
            py = gauge_cy + int((gauge_r + dr) * math.sin(a))
            if 0 <= px < W and 0 <= py < H:
                draw.point((px, py), fill=(*gc, 220))

    # Score number
    sc = f"{score:.0f}"
    sw, sh = tsize(draw, sc, fonts["score"])
    draw.text((cx - sw // 2, gauge_cy - sh // 2 - 8), sc,
              font=fonts["score"], fill=(*WHITE, 255))
    lbl = "/ 16"
    lw, _ = tsize(draw, lbl, fonts["small"])
    draw.text((cx - lw // 2, gauge_cy + sh // 2 - 18), lbl,
              font=fonts["small"], fill=(*GRAY, 180))

    # Category pill
    cat_text = CAT_LABEL[category]
    cw2, ch2 = tsize(draw, cat_text, fonts["tag"])
    pill_x = (W - cw2 - 48) // 2
    pill_y = gauge_cy + gauge_r + 50
    draw_rr(draw, pill_x, pill_y, pill_x + cw2 + 48, pill_y + ch2 + 20, 20,
            (*CAT_BG[category], 200), (*cat_col, 255), 2)
    centered(draw, pill_y + 10, cat_text, fonts["tag"], (*cat_col, 255))

    # Form badge
    form_y = pill_y + ch2 + 50
    fw2, fh2 = tsize(draw, form, fonts["body"])
    fx = (W - fw2 - 40) // 2
    draw_rr(draw, fx, form_y, fx + fw2 + 40, form_y + fh2 + 16, 10,
            (*CARD_BG, 200), (*BLUE, 120), 1)
    centered(draw, form_y + 8, form, fonts["body"], (*BLUE, 255))

    _bokeh(draw, 45, seed=hash(ticker) % 999 + 1,
           colors=[cat_col, (*lerp(cat_col, WHITE, 0.4),)])
    _scanlines(draw)
    return img


# ── Frame 3: Analysis Dashboard ─────────────────────────────────────────
def render_analysis(ticker: str, category: str, score: float,
                    form: str, tags: list, gs: float, vs: float, ms: float,
                    fonts: dict) -> Image.Image:
    """Detailed score breakdown with sub-scores and signals."""
    cat_col = CAT_COLOR[category]
    img = Image.new("RGBA", (W, H), (*DARK_BG, 255))
    draw = ImageDraw.Draw(img)

    _vignette(draw, 6, 20)
    _grid(draw, 120, 8)

    PAD = 60
    y = 280

    # Section title
    centered(draw, y, "CATALYST ANALYSIS", fonts["h2"], (*WHITE, 255))
    y += 80
    draw.line([(PAD, y), (W - PAD, y)], fill=(*BLUE, 100), width=2)
    y += 30

    # Ticker + category
    tk_label = f"${ticker}"
    tw2, th2 = tsize(draw, tk_label, fonts["h1"])
    draw.text((PAD, y), tk_label, font=fonts["h1"], fill=(*cat_col, 255))
    cat_text = CAT_LABEL[category]
    cw2, ch2 = tsize(draw, cat_text, fonts["tag"])
    cx2 = W - PAD - cw2 - 32
    draw_rr(draw, cx2, y + 12, cx2 + cw2 + 32, y + 12 + ch2 + 16, 14,
            (*CAT_BG[category], 200), (*cat_col, 200), 1)
    draw.text((cx2 + 16, y + 20), cat_text, font=fonts["tag"], fill=(*cat_col, 255))
    y += th2 + 30

    # Score summary card
    card_h = 160
    draw_rr(draw, PAD, y, W - PAD, y + card_h, 16, (*CARD_BG, 200), (*BLUE, 40), 1)

    # Total score (large)
    sc_text = f"{score:.0f}"
    sw2, sh2 = tsize(draw, sc_text, fonts["score"])
    draw.text((PAD + 40, y + (card_h - sh2) // 2 - 5), sc_text,
              font=fonts["score"], fill=(*WHITE, 255))
    draw.text((PAD + 40 + sw2 + 8, y + card_h // 2 - 10), "/ 16",
              font=fonts["body"], fill=(*GRAY, 180))

    # Sub-score bars
    sub_scores = [
        ("GAPPER", gs, RED),
        ("VALUE", vs, GREEN),
        ("MOAT", ms, PURPLE),
    ]
    bar_x = PAD + 260
    bar_w = W - PAD - bar_x - 40
    bar_h = 28
    for idx, (name, val, col) in enumerate(sub_scores):
        by = y + 20 + idx * (bar_h + 14)
        draw.text((bar_x, by), name, font=fonts["small"], fill=(*col, 220))
        bx = bar_x + 120
        draw_rr(draw, bx, by, bx + bar_w, by + bar_h, bar_h // 2,
                (18, 22, 54, 180))
        fw = int(bar_w * min(1.0, val / 6.0))
        if fw > bar_h:
            hbar_rgba(img, bx, by, bx + fw, by + bar_h,
                      (*col, 200), (*lerp(col, WHITE, 0.4), 200))
            draw = ImageDraw.Draw(img)
        vt = f"{val:.1f}"
        vtw, _ = tsize(draw, vt, fonts["small"])
        draw.text((bx + fw + 8, by), vt, font=fonts["small"], fill=(*WHITE, 180))

    y += card_h + 30

    # Filing info card
    filing_h = 120
    draw_rr(draw, PAD, y, W - PAD, y + filing_h, 16, (*CARD_BG, 160))
    draw.text((PAD + 24, y + 16), "SEC FILING", font=fonts["tag"], fill=(*BLUE, 255))
    draw.text((PAD + 24, y + 60), f"Form {form}  ·  Filed {TODAY_DISPLAY}",
              font=fonts["body"], fill=(*WHITE, 200))
    y += filing_h + 24

    # Signal tags
    tag_x = PAD
    used_tags = tags[:4] if tags else ["SEC Catalyst", "Event-Driven", "Top Score"]
    for tag in used_tags:
        tw3, th3 = tsize(draw, tag, fonts["small"])
        draw_rr(draw, tag_x, y, tag_x + tw3 + 28, y + th3 + 14, 8,
                (18, 26, 58, 180))
        draw.text((tag_x + 14, y + 7), tag, font=fonts["small"], fill=(*WHITE, 200))
        tag_x += tw3 + 36
        if tag_x > W - 120:
            break

    _scanlines(draw)
    return img


# ── Frame 4: Top 5 Leaderboard ──────────────────────────────────────────
def render_leaderboard(top5: list, category: str, fonts: dict) -> Image.Image:
    """Top 5 horizontal bar chart with rankings."""
    cat_col = CAT_COLOR[category]
    img = Image.new("RGBA", (W, H), (*DARK_BG, 255))
    draw = ImageDraw.Draw(img)

    _vignette(draw, 6, 18)
    _grid(draw, 120, 8)

    PAD = 70

    centered(draw, 300, "TODAY'S TOP SEC CATALYSTS", fonts["h2"], (*WHITE, 255))
    draw.line([(PAD, 380), (W - PAD, 380)], fill=(*BLUE, 100), width=2)

    BAR_H, GAP = 82, 28
    MAX_W = W - PAD * 2 - 170
    start_y = 430

    for idx, (t, s) in enumerate(top5[:5]):
        ry = start_y + idx * (BAR_H + GAP)
        is_top = idx == 0

        # Rank
        rank = str(idx + 1)
        rf = fonts["h2"] if is_top else fonts["h3"]
        rc = (*cat_col, 255) if is_top else (*GRAY, 160)
        draw.text((PAD, ry + (BAR_H - tsize(draw, rank, rf)[1]) // 2),
                  rank, font=rf, fill=rc)

        # Ticker
        lbl = f"${t}"
        lf = fonts["h3"] if is_top else fonts["body"]
        lc = (*WHITE, 255) if is_top else (*LIGHT_GRAY, 200)
        draw.text((PAD + 55, ry + (BAR_H - tsize(draw, lbl, lf)[1]) // 2),
                  lbl, font=lf, fill=lc)

        # Bar
        bx = PAD + 210
        draw_rr(draw, bx, ry, bx + MAX_W, ry + BAR_H, BAR_H // 2,
                (18, 22, 54, 180))
        fw = int(MAX_W * min(1.0, s / 16.0))
        if fw > BAR_H:
            c1 = (*lerp(cat_col, DARK_BG, 0.15 if is_top else 0.4), 210)
            c2 = (*lerp(cat_col, WHITE, 0.4 if is_top else 0.12), 210)
            hbar_rgba(img, bx, ry, bx + fw, ry + BAR_H, c1, c2)
            draw = ImageDraw.Draw(img)

        # Score
        sv = f"{s:.0f}"
        svw, svh = tsize(draw, sv, fonts["h3"] if is_top else fonts["body"])
        svx = (bx + fw + 14) if fw < MAX_W - 50 else (bx + fw - svw - 14)
        draw.text((svx, ry + (BAR_H - svh) // 2), sv,
                  font=fonts["h3"] if is_top else fonts["body"],
                  fill=(*WHITE, 220))

    fy = start_y + 5 * (BAR_H + GAP) + 30
    draw.line([(PAD, fy), (W - PAD, fy)], fill=(*BLUE, 60))
    centered(draw, fy + 16, f"Scored from {TODAY_DISPLAY} SEC filings",
             fonts["small"], (*GRAY, 140))

    _scanlines(draw)
    return img


# ── Frame 5: Call-to-Action Closing ──────────────────────────────────────
def render_cta(fonts: dict) -> Image.Image:
    """Product suite, pricing tiers, subscribe CTA."""
    img = Image.new("RGBA", (W, H), (*DARK_BG, 255))
    draw = ImageDraw.Draw(img)

    _vignette(draw, 6, 22, (0, 0, 10))
    _grid(draw, 120, 8)

    cx = W // 2

    # Central glow
    for r in range(420, 0, -4):
        a = int(18 * (1 - r / 420))
        draw.ellipse([cx - r, H // 2 - 280 - r, cx + r, H // 2 - 280 + r],
                     fill=(*BLUE, a))

    centered(draw, 300, "CATALYST EDGE", fonts["h1"], (*WHITE, 255))
    centered(draw, 400, "SEC Intelligence Before the Bell", fonts["body"],
             (*lerp(BLUE, WHITE, 0.5), 220))

    # Product cards (2×2)
    products = [
        ("SCANNER", "Live market scanner", "7,325 entities"),
        ("NEWSLETTER", "Daily SEC picks", "Free tier"),
        ("CEREBRO", "3D market HUD", "15K+ tickers"),
        ("AI AGENT", "Ask about filings", "Voice + chat"),
    ]
    card_w, card_h, gap = 430, 155, 26
    sy = 510
    for i, (name, desc, stat) in enumerate(products):
        col_idx, row_idx = i % 2, i // 2
        x1 = (W - 2 * card_w - gap) // 2 + col_idx * (card_w + gap)
        y1 = sy + row_idx * (card_h + gap)
        draw_rr(draw, x1, y1, x1 + card_w, y1 + card_h, 14,
                (*CARD_BG, 210), (*BLUE, 50), 1)
        draw.text((x1 + 22, y1 + 18), name, font=fonts["tag"], fill=(*BLUE, 255))
        draw.text((x1 + 22, y1 + 62), desc, font=fonts["small"], fill=(*WHITE, 200))
        draw.text((x1 + 22, y1 + 100), stat, font=fonts["small"], fill=(*GRAY, 150))

    # Pricing pills
    py = sy + 2 * (card_h + gap) + 36
    tiers = [("FREE", "$0/mo", BLUE), ("READER", "$12/mo", GREEN),
             ("PRO", "$39/mo", PURPLE)]
    pill_w = 260
    total_pw = len(tiers) * pill_w + (len(tiers) - 1) * 20
    px = (W - total_pw) // 2
    for name, price, col in tiers:
        draw_rr(draw, px, py, px + pill_w, py + 68, 34,
                (*col, 25), (*col, 200), 2)
        nw, _ = tsize(draw, name, fonts["tag"])
        pw, _ = tsize(draw, price, fonts["small"])
        tot = nw + 12 + pw
        tx = px + (pill_w - tot) // 2
        draw.text((tx, py + 16), name, font=fonts["tag"], fill=(*col, 255))
        draw.text((tx + nw + 12, py + 20), price, font=fonts["small"],
                  fill=(*WHITE, 200))
        px += pill_w + 20

    # URLs
    uy = py + 110
    centered(draw, uy, "catalystedge.agency", fonts["h3"],
             (*lerp(BLUE, WHITE, 0.5), 255))
    centered(draw, uy + 50, "catalystedgescanner.com", fonts["body"],
             (*GRAY, 180))

    # Social
    centered(draw, uy + 110, "YouTube  ·  TikTok  ·  X  ·  Instagram  ·  Telegram",
             fonts["small"], (*GRAY, 150))

    # Disclaimer
    centered(draw, H - 110, "Not financial advice. For informational purposes only.",
             fonts["small"], (100, 100, 120, 170))

    _scanlines(draw)
    return img


# ═══════════════════════════════════════════════════════════════════════════
#  OVERLAY RENDERERS
# ═══════════════════════════════════════════════════════════════════════════

def render_branding_bar(fonts: dict) -> Image.Image:
    """1080×100 RGBA — top bar with BREAKING stripe + brand."""
    img = Image.new("RGBA", (W, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for y in range(100):
        a = int(215 * (1 - y / 100))
        draw.line([(0, y), (W - 1, y)], fill=(*DARK_BG, a))

    draw.rectangle([0, 0, W, 44], fill=(185, 18, 18, 215))
    centered(draw, 8, "BREAKING — SEC CATALYST ALERT", fonts["small"], WHITE)
    draw.text((40, 52), "CATALYST EDGE", font=fonts["brand"],
              fill=(*lerp(BLUE, WHITE, 0.5), 255))
    dw, _ = tsize(draw, TODAY_DISPLAY.upper(), fonts["small"])
    draw.text((W - dw - 40, 58), TODAY_DISPLAY.upper(),
              font=fonts["small"], fill=(*GRAY, 200))
    return img


def render_lower_third(ticker: str, category: str, form: str,
                       score: float, tags: list, fonts: dict) -> Image.Image:
    """1080×300 RGBA lower-third with ticker data."""
    LH = 300
    cat_col = CAT_COLOR[category]
    img = Image.new("RGBA", (W, LH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Semi-transparent gradient band
    for y in range(LH):
        a = int(205 * (y / LH) ** 0.55)
        draw.line([(0, y), (W - 1, y)], fill=(*DARK_BG, a))

    PAD = 50

    # Category pill
    ct = CAT_LABEL[category]
    cw2, ch2 = tsize(draw, ct, fonts["small"])
    draw_rr(draw, PAD, 16, PAD + cw2 + 28, 16 + ch2 + 14, 10,
            (*CAT_BG[category], 200), (*cat_col, 200), 1)
    draw.text((PAD + 14, 23), ct, font=fonts["small"], fill=(*cat_col, 255))

    # Ticker + score
    draw.text((PAD, 60), f"${ticker}", font=fonts["h2"], fill=(*WHITE, 255))
    tw2, _ = tsize(draw, f"${ticker}", fonts["h2"])
    draw.text((PAD + tw2 + 20, 74), f"Score {score:.0f}/16",
              font=fonts["body"], fill=(*GRAY, 200))

    # Form badge
    fmw, fmh = tsize(draw, form, fonts["body"])
    fx = W - PAD - fmw - 36
    draw_rr(draw, fx, 62, fx + fmw + 36, 62 + fmh + 14, 10,
            (*CARD_BG, 200), (*BLUE, 100), 1)
    draw.text((fx + 18, 69), form, font=fonts["body"], fill=(*BLUE, 255))

    # Tags
    tx = PAD
    ty = 132
    for tag in (tags[:3] if tags else ["SEC Catalyst", "Event-Driven"]):
        tw3, th3 = tsize(draw, tag, fonts["small"])
        draw_rr(draw, tx, ty, tx + tw3 + 24, ty + th3 + 12, 8,
                (18, 26, 58, 160))
        draw.text((tx + 12, ty + 6), tag, font=fonts["small"], fill=(*WHITE, 190))
        tx += tw3 + 32

    # Score bar
    by = 195
    BW = W - PAD * 2
    BH = 22
    draw_rr(draw, PAD, by, PAD + BW, by + BH, BH // 2, (18, 22, 54, 180))
    fw = int(BW * min(1.0, score / 16.0))
    if fw > BH:
        hbar_rgba(img, PAD, by, PAD + fw, by + BH,
                  (*cat_col, 210), (*lerp(cat_col, WHITE, 0.45), 210))

    draw = ImageDraw.Draw(img)
    centered(draw, 240, "CATALYSTEDGE.AGENCY  |  FREE NEWSLETTER  |  SCANNER",
             fonts["small"], (*lerp(BLUE, WHITE, 0.35), 170), W)

    return img


# ═══════════════════════════════════════════════════════════════════════════
#  FFmpeg PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def _get_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 5.0


def make_ken_burns(image_path: Path, duration: float, out_path: Path,
                   style: str = "zoom_in") -> bool:
    """Generate a Ken Burns (slow zoom/pan) clip from a static frame."""
    n = int(duration * FPS)

    styles = {
        "zoom_in":
            f"z='min(zoom+0.0007,1.22)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        "zoom_out":
            f"z='if(eq(on,1),1.22,max(zoom-0.0007,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        "pan_up":
            f"z='1.12':x='iw/2-(iw/zoom/2)':y='max(ih/2-(ih/zoom/2)-on*0.7,0)'",
        "pan_down":
            f"z='1.12':x='iw/2-(iw/zoom/2)':y='min(on*0.7,ih-ih/zoom)'",
        "drift_right":
            f"z='1.12':x='min(on*0.5,iw-iw/zoom)':y='ih/2-(ih/zoom/2)'",
    }
    zf = styles.get(style, styles["zoom_in"])

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-vf", f"zoompan={zf}:d={n}:s={W}x{H}:fps={FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-t", f"{duration:.2f}", str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  Ken Burns ({style}) error: {r.stderr[-400:]}")
        return False
    return True


def composite_final(clips: list[Path], brand_png: Path, lt_png: Path,
                    ass_path: Path, mp3: Path, music: Path | None,
                    dur: float, out_path: Path):
    """
    2-pass composite:
      Pass 1: concat clips + overlay branding bar + lower third + ASS captions
      Pass 2: add voice + music
    """
    TMP = mp3.parent

    # ── Pass 1: concat → overlays → silent video ────────────────────────
    # Write concat list
    concat_txt = TMP / "concat.txt"
    concat_txt.write_text(
        "\n".join(f"file '{c}'" for c in clips), encoding="utf-8")

    concat_mp4 = TMP / "concat_raw.mp4"
    r = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        str(concat_mp4),
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  Concat error: {r.stderr[-500:]}")
        raise SystemExit(1)

    # Overlay branding bar + lower third + subtitles
    silent = TMP / "silent.mp4"
    ass_esc = str(ass_path).replace("\\", "/").replace(":", "\\:")
    lt_y = H - 300  # lower third height

    # Lower third appears after intro segment (~5s in)
    vf = (
        f"[0:v][1:v]overlay=0:0[v1];"
        f"[v1][2:v]overlay=0:{lt_y}:enable='gte(t,4)'[v2];"
        f"[v2]subtitles={ass_esc}:force_style='MarginV=580'[vout]"
    )

    r = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(concat_mp4),
        "-loop", "1", "-i", str(brand_png),
        "-loop", "1", "-i", str(lt_png),
        "-filter_complex", vf,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-t", f"{dur:.2f}",
        str(silent),
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  Overlay error: {r.stderr[-600:]}")
        # Fallback: use concat without overlays
        shutil.copy(str(concat_mp4), str(silent))

    # ── Pass 2: add voice + music bed ────────────────────────────────────
    if music and music.exists():
        af = ("[0:a]volume=1.0[voice];"
              "[1:a]volume=0.12[bed];"
              "[voice][bed]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(mp3), "-i", str(music), "-i", str(silent),
            "-filter_complex", af,
            "-map", "2:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(mp3), "-i", str(silent),
            "-map", "1:v", "-map", "0:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out_path),
        ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  Final mix error: {r.stderr[-500:]}")
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print(f"generate_cinematic_video date={TODAY} dow={DOW}")

    if not HAS_PIL:
        print("ERROR: pip install --break-system-packages Pillow")
        raise SystemExit(1)

    def _load_env_key(name: str) -> str:
        val = os.environ.get(name, "").strip()
        if not val:
            env_file = ROOT / ".sec_email_env"
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith(f"{name}="):
                        val = line.split("=", 1)[1].strip()
                        break
        return val

    # ElevenLabs quota exhausted — use edge-tts (free, unlimited)
    el_api_key = ""

    # ── Load data ────────────────────────────────────────────────────────
    ticker, row, picks_data = load_pick()
    if not ticker:
        print("  No pick data — skipping")
        return

    category = get_category(row)
    form = row.get("form", "8-K")
    tags = clean_tags(row.get("tags", ""))
    gs = float(row.get("gapper_score", 0) or 0)
    vs = float(row.get("value_score", 0) or 0)
    ms = float(row.get("moat_score", 0) or 0)
    total_score = gs + vs + ms
    top5 = load_top5_scores(picks_data.get("top5_tickers", [ticker]))

    print(f"  Pick: ${ticker}  category={category}  score={total_score:.0f}")

    fonts = load_fonts()
    script = build_script(ticker, row, category, picks_data)
    print(f"  Script ({len(script.split())} words)")

    TMP = Path(tempfile.mkdtemp(prefix="cine_vid_"))
    mp3 = TMP / "voice.mp3"
    ass = TMP / "captions.ass"
    music = TMP / "music.wav"

    # ── 1. Voice-over ────────────────────────────────────────────────────
    print("  Generating voiceover...")
    gen_audio(script, mp3, ass, el_api_key)
    dur = audio_duration(mp3)
    print(f"  Audio: {dur:.1f}s")

    # ── 2. Music bed ─────────────────────────────────────────────────────
    print("  Generating music bed...")
    has_music = gen_music(dur, music)

    # ── 3. Render hero frames ────────────────────────────────────────────
    print("  Rendering cinematic frames...")
    f_intro = TMP / "frame_intro.png"
    f_ticker = TMP / "frame_ticker.png"
    f_analysis = TMP / "frame_analysis.png"
    f_board = TMP / "frame_board.png"
    f_cta = TMP / "frame_cta.png"

    render_market_pulse(fonts).convert("RGB").save(str(f_intro))
    render_ticker_hero(ticker, category, total_score, form, fonts) \
        .convert("RGB").save(str(f_ticker))
    render_analysis(ticker, category, total_score, form, tags,
                    gs, vs, ms, fonts).convert("RGB").save(str(f_analysis))
    render_leaderboard(top5, category, fonts).convert("RGB").save(str(f_board))
    render_cta(fonts).convert("RGB").save(str(f_cta))
    print("  5 frames rendered.")

    # ── 4. Ken Burns clips ───────────────────────────────────────────────
    # Segment timing: 5 segments across total voiceover duration
    #   intro 12% | ticker 16% | analysis 28% | leaderboard 24% | cta 20%
    ratios = [0.12, 0.16, 0.28, 0.24, 0.20]
    seg_dur = [max(4.0, dur * r) for r in ratios]
    # Normalise to exact voiceover length
    total_seg = sum(seg_dur)
    seg_dur = [s * dur / total_seg for s in seg_dur]

    frames = [f_intro, f_ticker, f_analysis, f_board, f_cta]
    kb_styles = ["zoom_in", "zoom_in", "pan_down", "pan_up", "zoom_out"]

    clips: list[Path] = []
    for i, (frame, style, sdur) in enumerate(zip(frames, kb_styles, seg_dur)):
        clip = TMP / f"clip_{i}.mp4"
        print(f"  Ken Burns #{i} ({style}, {sdur:.1f}s)...")
        ok = make_ken_burns(frame, sdur, clip, style)
        if not ok:
            # Fallback: static image as video
            subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-i", str(frame),
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-r", str(FPS),
                "-t", f"{sdur:.2f}", str(clip),
            ], capture_output=True, text=True)
        clips.append(clip)

    # ── 5. Overlays ──────────────────────────────────────────────────────
    print("  Rendering overlays...")
    brand_png = TMP / "brand_bar.png"
    lt_png = TMP / "lower_third.png"
    render_branding_bar(fonts).save(str(brand_png))
    render_lower_third(ticker, category, form, total_score,
                       tags if tags else ["SEC Catalyst", "Event-Driven"],
                       fonts).save(str(lt_png))

    # ── 6. Final composite ───────────────────────────────────────────────
    print("  Compositing final video...")
    WIN_OUT.mkdir(parents=True, exist_ok=True)
    out_win = WIN_OUT / f"anchor_{TODAY}.mp4"
    out_local = ROOT / "anchor_video.mp4"

    composite_final(clips, brand_png, lt_png, ass, mp3,
                    music if has_music else None, dur, out_win)

    shutil.copy(str(out_win), str(out_local))

    # Copy to Windows Desktop (cp instead of shutil to avoid WSL chmod errors)
    win_desk = Path("/path/to/local/Desktop/catalyst-edge/social")
    if win_desk.exists():
        dest = win_desk / f"anchor_{TODAY}.mp4"
        subprocess.run(["cp", str(out_win), str(dest)], capture_output=True)
        print(f"  Copied to Desktop: {dest.name}")
        (win_desk / f"UPLOAD_TODAY_anchor_{TODAY}.txt").write_text(
            f"YouTube Shorts / TikTok anchor upload — {TODAY_DISPLAY}\n"
            f"File: anchor_{TODAY}.mp4\n"
            f"Title: {TODAY_DISPLAY} Top SEC Catalyst Pick\n"
            f"Description: Free daily stock picks from 300+ SEC filings.\n"
            f"Newsletter: https://catalystedge.agency\n"
            f"Live Scanner: https://catalystedgescanner.com\n"
            f"#stocks #investing #SEC #fintwit #YouTubeShorts\n",
            encoding="utf-8",
        )

    shutil.rmtree(TMP, ignore_errors=True)

    mb = out_win.stat().st_size / 1e6
    print(f"\n  Done! {mb:.1f} MB → {out_win}")
    print(f"  Also at: {out_local}")


if __name__ == "__main__":
    main()
