#!/usr/bin/env python3
"""generate_tiktok_video.py v2 — Pro-quality TikTok/Shorts video for Catalyst Edge.

Improvements over v1:
  • Pillow rendering — TrueType fonts (Ubuntu Bold), smooth gradients, drop shadows
  • Word-level ASS karaoke captions — current word highlighted yellow
  • Ken Burns zoom/pan on every slide (alternating push-in / pull-out / pan)
  • Ambient music bed — A-minor pad generated via FFmpeg aevalsrc, mixed at -18 dB
  • Dynamic bar chart in Setup slide comparing top-5 catalyst scores

Voice: en-US-GuyNeural (broadcast anchor)
Format: 1080×1920 (9:16 portrait)
Output:
  /path/to/local/Desktop/catalyst-edge/social/tiktok_YYYY-MM-DD.mp4
  /home/operator/.openclaw/workspace/tiktok_video.mp4
"""

from __future__ import annotations

import asyncio
import csv
import os
import datetime
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import edge_tts
    HAS_TTS = True
except ImportError:
    HAS_TTS = False

try:
    from elevenlabs.client import ElevenLabs as _ElevenLabsClient
    HAS_ELEVENLABS = True
except ImportError:
    HAS_ELEVENLABS = False

ROOT    = Path(__file__).parent
WIN_OUT = Path(__file__).parent / "social"
TODAY   = datetime.date.today().isoformat()
TODAY_DISPLAY = datetime.date.today().strftime("%B %d, %Y")

W, H  = 1080, 1920
FPS   = 30
VOICE = "en-GB-LibbyNeural"            # edge-tts fallback
ELEVENLABS_VOICE_ID = "pFZP5JQG7iQjIQuC4Bku"  # Lily — British, velvety, confident

# ── Colour palette ────────────────────────────────────────────────────────────
DARK_BG    = (6,  8, 20)
NAVY       = (10, 15, 30)
CARD_BG    = (18, 26, 58)
BLUE       = (59, 130, 246)
PURPLE     = (139, 92, 246)
RED        = (210, 35, 35)
GREEN      = (16, 185, 129)
WHITE      = (255, 255, 255)
GRAY       = (110, 130, 165)
LIGHT_GRAY = (190, 205, 225)
DARK_RED   = (38,  8,   8)
DARK_GREEN = (8,  35,  20)
DARK_PURPLE= (28, 12,  55)

CAT_COLOR = {"gapper": RED,  "value": GREEN,  "moat": PURPLE}
CAT_BG    = {"gapper": DARK_RED, "value": DARK_GREEN, "moat": DARK_PURPLE}
CAT_LABEL = {"gapper": "GAPPER PLAY", "value": "VALUE PLAY", "moat": "INSTITUTIONAL MOAT"}

# ── Font loading ──────────────────────────────────────────────────────────────
_FONT_PATHS = {
    "bold": [
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ],
}

def _pick_font(style: str) -> str | None:
    for p in _FONT_PATHS.get(style, []):
        if Path(p).exists():
            return p
    return None

def load_fonts() -> dict:
    bold = _pick_font("bold")
    reg  = _pick_font("regular")

    def f(path, size):
        if path:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    return {
        "giant":  f(bold, 130),  # Massive ticker
        "h1":     f(bold,  88),  # Main headline
        "h2":     f(bold,  62),  # Section header
        "h3":     f(bold,  46),  # Card heading / pill
        "body":   f(reg,   38),  # Body / signals
        "small":  f(reg,   30),  # Labels / footer
        "tag":    f(bold,  34),  # Pills and badges
        "score":  f(bold,  96),  # Big score number
        "brand":  f(bold,  50),  # CATALYST EDGE
        "date":   f(reg,   32),  # Date string
        "chart":  f(bold,  32),  # Bar chart labels
    }

# ── Drawing helpers ────────────────────────────────────────────────────────────
def lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] * (1-t) + c2[i] * t) for i in range(3))

def new_canvas(top=(6, 8, 20), bot=(3, 4, 12)) -> Image.Image:
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W-1, y)], fill=lerp(top, bot, t))
    return img

def draw_rr(draw, x1, y1, x2, y2, r, fill, outline=None, ow=0):
    try:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=fill,
                                outline=outline, width=ow)
    except TypeError:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=fill)

def tsize(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]

def draw_shadow(draw, xy, text, font, fill, offset=3):
    draw.text((xy[0]+offset, xy[1]+offset), text, font=font, fill=(0, 0, 0, 160))
    draw.text(xy, text, font=font, fill=fill)

def draw_centered(draw, y, text, font, fill, shadow=True):
    w, h = tsize(draw, text, font)
    x = (W - w) // 2
    if shadow:
        draw.text((x+3, y+3), text, font=font, fill=(0, 0, 0, 160))
    draw.text((x, y), text, font=font, fill=fill)
    return h

def draw_hbar(img, x1, y1, x2, y2, c1, c2):
    """Horizontal gradient bar (no numpy — row-by-row on a thin strip)."""
    draw = ImageDraw.Draw(img)
    span = max(1, x2 - x1)
    step = max(1, span // 200)  # at most 200 vertical strips
    for x in range(x1, x2, step):
        t = (x - x1) / span
        draw.rectangle([x, y1, min(x + step, x2), y2], fill=lerp(c1, c2, t))

def glow_circle(img, cx, cy, max_r, color):
    """Multi-layer concentric ellipses to simulate a soft glow."""
    draw = ImageDraw.Draw(img)
    layers = [(1.0, 0.80), (0.80, 0.55), (0.60, 0.30), (0.42, 0.12), (0.28, 0.04)]
    bg = img.getpixel((cx, min(cy + max_r + 2, H - 1)))
    for frac, alpha in layers:
        r = int(max_r * frac)
        c = lerp(bg, color, alpha)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)

# ── Shared chrome ──────────────────────────────────────────────────────────────
def draw_top_bar(img, draw, fonts, label="BREAKING — SEC CATALYST"):
    draw.rectangle([0, 0, W, 92], fill=(185, 18, 18))
    draw.rectangle([0, 88, W, 92], fill=(90, 6, 6))
    draw_centered(draw, 22, label, fonts["h3"], WHITE, shadow=False)
    draw.rectangle([0, 92, W, 158], fill=(10, 6, 28))
    draw_shadow(draw, (52, 106), "CATALYST EDGE", fonts["brand"], lerp(BLUE, WHITE, 0.5))
    dw, _ = tsize(draw, TODAY_DISPLAY.upper(), fonts["date"])
    draw.text((W - dw - 52, 113), TODAY_DISPLAY.upper(), font=fonts["date"], fill=GRAY)

DISCLAIMER = "Not financial advice. For informational purposes only."

def draw_bottom_bar(draw, fonts):
    draw.rectangle([0, H-158, W, H], fill=(8, 6, 20))
    draw.rectangle([0, H-158, W, H-154], fill=BLUE)
    draw_centered(draw, H-128, "CATALYSTEDGE.AGENCY  |  START FREE AT /PRICING/", fonts["tag"],
                  lerp(BLUE, WHITE, 0.5), shadow=False)
    draw_centered(draw, H-82, "NEWSLETTER  |  SCANNER  |  CEREBRO HUD  |  AI", fonts["small"],
                  GRAY, shadow=False)
    draw_centered(draw, H-44, DISCLAIMER, fonts["small"],
                  (120, 120, 140), shadow=False)

# ── Slide 1: Hook ─────────────────────────────────────────────────────────────
def slide_hook(ticker, category, fonts) -> Image.Image:
    img = new_canvas((8, 5, 22), (3, 3, 14))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    # Category-color edge borders
    for coords in [(0,0,W,20), (0,H-20,W,H), (0,0,20,H), (W-20,0,W,H)]:
        draw.rectangle(list(coords), fill=cat_col)

    # Glow circle (red alert ring)
    cx, cy = W // 2, H // 2 - 140
    glow_circle(img, cx, cy, 340, RED)
    draw = ImageDraw.Draw(img)

    # Solid inner circle
    draw.ellipse([cx-140, cy-140, cx+140, cy+140], fill=RED)

    # "!" in the circle
    bang_w, bang_h = tsize(draw, "!", fonts["h1"])
    draw_shadow(draw, (cx - bang_w//2, cy - bang_h//2 - 8), "!", fonts["h1"], WHITE, 4)

    # SEC ALERT label
    draw_centered(draw, cy + 175, "SEC ALERT", fonts["h1"], WHITE)

    # Ticker pill
    pill_y = cy + 305
    pill_text = f"${ticker}  ·  {CAT_LABEL[category]}"
    pw, _ = tsize(draw, pill_text, fonts["h3"])
    px1 = (W - pw - 80) // 2
    px2 = px1 + pw + 80
    draw_rr(draw, px1, pill_y, px2, pill_y + 88, 22, CAT_BG[category], cat_col, 2)
    draw_shadow(draw, (px1 + 40, pill_y + 20), pill_text, fonts["h3"], cat_col)

    draw_centered(draw, H - 230, "CATALYST EDGE  |  " + TODAY_DISPLAY.upper(),
                  fonts["small"], GRAY)
    return img

# ── Slide 2: Reveal ───────────────────────────────────────────────────────────
def slide_ticker_reveal(ticker, category, form, score, fonts) -> Image.Image:
    img = new_canvas((7, 5, 18), (14, 10, 32))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    draw_top_bar(img, draw, fonts)

    # Category pill
    ctext = CAT_LABEL[category]
    cw, _ = tsize(draw, ctext, fonts["tag"])
    cx1 = (W - cw - 64) // 2
    cx2 = cx1 + cw + 64
    draw_rr(draw, cx1, 184, cx2, 260, 38, CAT_BG[category], cat_col, 2)
    draw_shadow(draw, (cx1 + 32, 204), ctext, fonts["tag"], cat_col)

    # Giant ticker with $ prefix
    tk_w, tk_h = tsize(draw, ticker, fonts["giant"])
    ds_w, _    = tsize(draw, "$", fonts["h2"])
    total_w    = ds_w + 10 + tk_w
    sx         = (W - total_w) // 2
    tk_y       = 288

    # Glow card behind ticker
    pad = 44
    draw_rr(draw, sx - pad, tk_y - 18, sx + total_w + pad, tk_y + tk_h + 18, 22,
            (12, 12, 38))

    draw_shadow(draw, (sx, tk_y + (tk_h - tsize(draw,"$",fonts["h2"])[1])//2 + 12),
                "$", fonts["h2"], lerp(cat_col, WHITE, 0.5))
    draw_shadow(draw, (sx + ds_w + 10, tk_y), ticker, fonts["giant"], cat_col, 5)

    # Form badge
    form_y = tk_y + tk_h + 58
    ft = form.upper()
    fw, _ = tsize(draw, ft, fonts["tag"])
    fx1 = (W - fw - 60) // 2
    fx2 = fx1 + fw + 60
    draw_rr(draw, fx1, form_y, fx2, form_y + 66, 33, CARD_BG)
    draw.rectangle([fx1, form_y + 60, fx2, form_y + 66], fill=cat_col)
    draw_shadow(draw, (fx1 + 30, form_y + 15), ft, fonts["tag"], WHITE)

    # Score label + number
    sc_y = form_y + 105
    draw_centered(draw, sc_y, "CATALYST SCORE", fonts["small"], GRAY)
    sc_str = f"{score:.0f} / 16"
    sc_w, sc_h = tsize(draw, sc_str, fonts["score"])
    draw_shadow(draw, ((W - sc_w)//2, sc_y + 46), sc_str, fonts["score"], cat_col, 5)

    # Score bar
    bar_y = sc_y + 46 + sc_h + 32
    BX1, BX2, BH = 80, W - 80, 34
    draw_rr(draw, BX1, bar_y, BX2, bar_y + BH, BH//2, (18, 22, 54))
    fill_px = int((BX2 - BX1) * min(1.0, score / 16.0))
    if fill_px > BH:
        draw_hbar(img, BX1, bar_y, BX1 + fill_px, bar_y + BH, cat_col,
                  lerp(cat_col, WHITE, 0.55))
        draw = ImageDraw.Draw(img)

    draw_centered(draw, bar_y + BH + 50, "ADD TO WATCHLIST", fonts["h3"],
                  lerp(cat_col, WHITE, 0.35))
    draw_bottom_bar(draw, fonts)
    return img

# ── Slide 3: Signals ──────────────────────────────────────────────────────────
def slide_signals(ticker, category, tags, fonts) -> Image.Image:
    img = new_canvas((7, 5, 18), (14, 10, 32))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    draw_top_bar(img, draw, fonts, "WHY THIS MATTERS")

    # Small ticker
    draw_centered(draw, 185, f"${ticker}", fonts["h2"], cat_col)
    draw_centered(draw, 260, "KEY SIGNALS FROM FILING", fonts["small"], GRAY)

    signals = tags if tags else [
        "SEC Material Event Filed",
        "Watch the Opening Bell",
        "High Catalyst Score",
        "Event-Driven Setup",
    ]

    for i, sig in enumerate(signals[:4]):
        cy = 315 + i * 210
        draw_rr(draw, 56, cy, W - 56, cy + 172, 18, CARD_BG, cat_col, 1)
        draw_rr(draw, 56, cy, 82, cy + 172, 6, cat_col)

        # Number badge
        bcx, bcy = 122, cy + 86
        draw.ellipse([bcx-36, bcy-36, bcx+36, bcy+36], fill=cat_col)
        n = str(i + 1)
        nw, nh = tsize(draw, n, fonts["tag"])
        draw.text((bcx - nw//2, bcy - nh//2), n, font=fonts["tag"], fill=WHITE)

        sig_x = 176
        sig_text = sig.title()
        sw, _ = tsize(draw, sig_text, fonts["body"])
        avail = W - 56 - 56 - 176
        if sw <= avail:
            draw_shadow(draw, (sig_x, cy + 68), sig_text, fonts["body"], WHITE)
        else:
            ws = sig_text.split()
            half = max(1, len(ws) // 2)
            draw_shadow(draw, (sig_x, cy + 48), " ".join(ws[:half]), fonts["body"], WHITE)
            draw_shadow(draw, (sig_x, cy + 48 + 48), " ".join(ws[half:]), fonts["body"], WHITE)

    draw_bottom_bar(draw, fonts)
    return img

# ── Slide 4: Setup with bar chart ─────────────────────────────────────────────
def slide_setup(ticker, category, price, top5: list[tuple[str, float]],
                picks_data: dict, fonts) -> Image.Image:
    img = new_canvas((7, 5, 18), (14, 10, 32))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    draw_top_bar(img, draw, fonts, "THE SETUP")

    gcount  = picks_data.get("gapper_count", 0)
    vcount  = picks_data.get("value_count",  0)
    mcount  = picks_data.get("moat_count",   0)
    scanned = picks_data.get("total_combined", 0)
    total_picks = gcount + vcount + mcount

    draw_centered(draw, 185, "HOW WE FOUND THIS", fonts["small"], GRAY)

    # Stats row
    stats = [
        (str(scanned),      "FILINGS\nSCANNED"),
        (str(total_picks),  "CATALYST\nPICKS"),
        ("#1",              "TODAY'S\nRANKING"),
    ]
    bw, bh, bgap = 300, 205, 18
    bsx = (W - (len(stats) * bw + (len(stats)-1) * bgap)) // 2
    bsy = 232

    for i, (val, lbl) in enumerate(stats):
        bx = bsx + i * (bw + bgap)
        draw_rr(draw, bx, bsy, bx + bw, bsy + bh, 18, CARD_BG)
        vw, vh = tsize(draw, val, fonts["h1"])
        draw_shadow(draw, (bx + (bw - vw)//2, bsy + 18), val, fonts["h1"], cat_col)
        for li, line in enumerate(lbl.split("\n")):
            lw, _ = tsize(draw, line, fonts["small"])
            draw.text((bx + (bw - lw)//2, bsy + 18 + vh + 12 + li * 40),
                      line, font=fonts["small"], fill=LIGHT_GRAY)

    # Bar chart — top 5 picks
    chart_y = bsy + bh + 50
    draw_centered(draw, chart_y, "TOP 5 PICKS — CATALYST SCORE", fonts["small"], GRAY)

    cstart = chart_y + 48
    BAR_H  = 68
    BAR_GAP = 20
    MAX_W  = W - 260
    MAX_SCORE = 16.0

    for idx, (t, s) in enumerate(top5[:5]):
        row_y = cstart + idx * (BAR_H + BAR_GAP)
        is_top = (idx == 0)
        lf = fonts["chart"]
        lc = cat_col if is_top else LIGHT_GRAY
        tw, th = tsize(draw, f"${t}", lf)
        draw_shadow(draw, (56, row_y + (BAR_H - th)//2), f"${t}", lf, lc)

        bar_x = 210
        draw_rr(draw, bar_x, row_y, bar_x + MAX_W, row_y + BAR_H, BAR_H//2,
                (18, 22, 54))
        fill_w = int(MAX_W * min(1.0, s / MAX_SCORE))
        if fill_w > BAR_H:
            if is_top:
                draw_hbar(img, bar_x, row_y, bar_x + fill_w, row_y + BAR_H,
                          cat_col, lerp(cat_col, WHITE, 0.5))
                draw = ImageDraw.Draw(img)
            else:
                draw_rr(draw, bar_x, row_y, bar_x + fill_w, row_y + BAR_H,
                        BAR_H//2, lerp(cat_col, GRAY, 0.55))
        sc_lbl = f"{s:.0f}"
        slw, slh = tsize(draw, sc_lbl, fonts["small"])
        sx = (bar_x + fill_w - slw - 14) if fill_w > slw + 28 else (bar_x + fill_w + 8)
        draw.text((sx, row_y + (BAR_H - slh)//2), sc_lbl, font=fonts["small"], fill=WHITE)

    # Price
    pr_y = cstart + 5 * (BAR_H + BAR_GAP) + 26
    if price:
        try:
            pf = float(price)
            if pf > 0:
                draw_centered(draw, pr_y, "CURRENT PRICE", fonts["small"], GRAY)
                draw_centered(draw, pr_y + 44, f"${pf:.2f}", fonts["h1"], WHITE)
        except (ValueError, TypeError):
            pass

    draw_bottom_bar(draw, fonts)
    return img

# ── Slide 5: Product Intro ────────────────────────────────────────────────────
def slide_product_intro(category, fonts) -> Image.Image:
    """Shows the Catalyst Edge product suite: Scanner, Cerebro HUD, AI, Newsletter."""
    img = new_canvas((7, 5, 18), (14, 10, 32))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    draw_top_bar(img, draw, fonts, "THE CATALYST EDGE SUITE")

    draw_centered(draw, 185, "FOUR TOOLS. ONE EDGE.", fonts["h2"], WHITE)
    draw_centered(draw, 260, "BUILT FOR TRADERS WHO MOVE FIRST", fonts["small"], GRAY)

    products = [
        ("THE SCANNER",   "catalystedgescanner.com",
         "Live dashboard — SEC filings ranked in real time"),
        ("CEREBRO HUD",   "catalystedge.agency/cerebro/",
         "3D WebGL graph of 15,000+ tickers — see the whole market"),
        ("CATALYST AI",   "catalystedge.agency",
         "Conversational AI — ask about any filing or pick"),
        ("NEWSLETTER",    "catalystedge.agency",
         "Free daily picks before the open — no paywall"),
    ]

    for i, (name, url, desc) in enumerate(products):
        cy = 330 + i * 330
        # Card background
        draw_rr(draw, 56, cy, W - 56, cy + 290, 18, CARD_BG, cat_col, 1)
        draw_rr(draw, 56, cy, 82, cy + 290, 6, cat_col)

        # Number badge
        bcx, bcy = 122, cy + 60
        draw.ellipse([bcx - 36, bcy - 36, bcx + 36, bcy + 36], fill=cat_col)
        n = str(i + 1)
        nw, nh = tsize(draw, n, fonts["tag"])
        draw.text((bcx - nw // 2, bcy - nh // 2), n, font=fonts["tag"], fill=WHITE)

        # Product name
        draw_shadow(draw, (176, cy + 28), name, fonts["h3"], cat_col)

        # URL
        draw.text((176, cy + 90), url, font=fonts["small"], fill=lerp(BLUE, WHITE, 0.5))

        # Description (wrap if needed)
        desc_text = desc
        dw, _ = tsize(draw, desc_text, fonts["body"])
        avail = W - 56 - 56 - 176
        if dw <= avail:
            draw_shadow(draw, (176, cy + 140), desc_text, fonts["body"], LIGHT_GRAY)
        else:
            ws = desc_text.split()
            half = max(1, len(ws) // 2)
            draw_shadow(draw, (176, cy + 140), " ".join(ws[:half]), fonts["body"], LIGHT_GRAY)
            draw_shadow(draw, (176, cy + 188), " ".join(ws[half:]), fonts["body"], LIGHT_GRAY)

    # Pricing callout
    draw_centered(draw, H - 240, "FREE  |  $12/MO READER  |  $39/MO PRO", fonts["h3"],
                  lerp(BLUE, WHITE, 0.4))

    draw_bottom_bar(draw, fonts)
    return img

# ── Slide 6: CTA ──────────────────────────────────────────────────────────────
def slide_cta(ticker, category, fonts) -> Image.Image:
    img = new_canvas((8, 5, 22), (5, 4, 14))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    for coords in [(0,0,W,20), (0,H-20,W,H), (0,0,20,H), (W-20,0,W,H)]:
        draw.rectangle(list(coords), fill=cat_col)

    # Lightning bolt polygon
    bolt = [(460,120),(340,480),(400,480),(365,780),(600,400),(515,400),(555,120)]
    glow_circle(img, W//2, 450, 310, lerp(BLUE, PURPLE, 0.5))
    draw = ImageDraw.Draw(img)
    draw.polygon(bolt, fill=lerp(BLUE, PURPLE, 0.45))

    fy = H // 2 + 30
    draw_centered(draw, fy,      "FOLLOW FOR",  fonts["h2"], WHITE)
    draw_centered(draw, fy + 95, "FREE PICKS",  fonts["h1"], cat_col)

    # Newsletter CTA button
    btn_y = fy + 95 + 85
    draw_rr(draw, 76, btn_y, W - 76, btn_y + 100, 24, (20, 12, 60))
    draw_hbar(img, 78, btn_y + 2, W - 78, btn_y + 98, BLUE, PURPLE)
    draw = ImageDraw.Draw(img)
    uw, _ = tsize(draw, "FREE NEWSLETTER: CATALYSTEDGE.AGENCY", fonts["small"])
    draw.text(((W - uw)//2, btn_y + 12), "FREE NEWSLETTER: CATALYSTEDGE.AGENCY",
              font=fonts["small"], fill=WHITE)
    lw, _ = tsize(draw, "LINK IN BIO", fonts["body"])
    draw.text(((W - lw)//2, btn_y + 54), "LINK IN BIO",
              font=fonts["body"], fill=lerp(WHITE, BLUE, 0.3))

    # Product suite summary
    suite_y = btn_y + 130
    draw_centered(draw, suite_y,      "3D MARKET HUD AT /CEREBRO/", fonts["small"],
                  lerp(PURPLE, WHITE, 0.5))
    draw_centered(draw, suite_y + 42, "TALK TO CATALYST AI AT CATALYSTEDGE.AGENCY", fonts["small"],
                  lerp(BLUE, WHITE, 0.4))
    draw_centered(draw, suite_y + 84, "LIVE SCANNER AT CATALYSTEDGESCANNER.COM", fonts["small"],
                  lerp(GREEN, WHITE, 0.4))

    draw_centered(draw, H - 280, "#SEC  #STOCKS  #CATALYST", fonts["small"], GRAY)
    draw_centered(draw, H - 215, f"TODAY'S TOP PICK: ${ticker}", fonts["h3"], cat_col)
    draw_centered(draw, H - 130, "FREE  |  $12/MO READER  |  $39/MO PRO", fonts["small"],
                  lerp(BLUE, WHITE, 0.4))
    draw_centered(draw, H - 80, "START FREE AT CATALYSTEDGE.AGENCY/PRICING/", fonts["small"],
                  lerp(BLUE, WHITE, 0.4))
    draw_centered(draw, H - 40, DISCLAIMER, fonts["small"], (120, 120, 140))
    return img

# ── Data loaders ──────────────────────────────────────────────────────────────
def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []

def load_pick():
    picks_json = ROOT / "newsletter_picks.json"
    picks_data: dict = {}
    if picks_json.exists():
        picks_data = json.loads(picks_json.read_text())

    top_ticker = picks_data.get("top_pick", "")
    tickers = picks_data.get("top5_tickers", [])
    if not top_ticker and tickers:
        top_ticker = tickers[0]
    if not top_ticker:
        return None, {}, {}

    for csv_path in [ROOT/"sec_top_gappers.csv", ROOT/"sec_top_value.csv",
                     ROOT/"sec_top_moat.csv", ROOT/"combined_priority.csv"]:
        for r in read_csv(csv_path):
            if r.get("ticker","").strip().upper() == top_ticker.upper():
                return top_ticker, r, picks_data

    return top_ticker, {}, picks_data

def load_top5_scores(tickers: list[str]) -> list[tuple[str, float]]:
    score_map: dict[str, float] = {}
    for csv_path in [ROOT/"combined_priority.csv", ROOT/"sec_catalyst_ranked.csv",
                     ROOT/"sec_top_gappers.csv", ROOT/"sec_top_value.csv",
                     ROOT/"sec_top_moat.csv"]:
        for r in read_csv(csv_path):
            t = r.get("ticker","").strip().upper()
            if t and t not in score_map:
                gs = float(r.get("gapper_score", 0) or 0)
                vs = float(r.get("value_score",  0) or 0)
                ms = float(r.get("moat_score",   0) or 0)
                total = gs + vs + ms
                if total > 0:
                    score_map[t] = total
    return [(t, score_map.get(t.upper(), 8.0)) for t in tickers]

def get_category(row: dict) -> str:
    gs = float(row.get("gapper_score", 0) or 0)
    ms = float(row.get("moat_score",   0) or 0)
    vs = float(row.get("value_score",  0) or 0)
    if gs >= ms and gs >= vs and gs > 0:
        return "gapper"
    if ms >= vs and ms > 0:
        return "moat"
    return "value"

def clean_tags(tags_str: str) -> list[str]:
    if not tags_str:
        return []
    return [t.lstrip("+").strip().title()
            for t in tags_str.split(";") if t.strip().startswith("+")][:4]

def form_spoken(form_code: str) -> str:
    labels = {
        "8-K":     "8-K earnings or material event filing",
        "4":       "Form 4 insider transaction",
        "S-3":     "S-3 shelf registration",
        "6-K":     "6-K foreign private issuer report",
        "13D":     "Schedule 13-D activist position",
        "13G":     "Schedule 13-G institutional stake",
        "DEF 14A": "proxy statement",
        "S-1":     "S-1 initial public offering filing",
    }
    return labels.get(form_code.strip().upper(), f"{form_code} SEC filing")

# ── Script builder ────────────────────────────────────────────────────────────
def build_script(ticker: str, row: dict, category: str, picks_data: dict) -> str:
    form       = row.get("form", "8-K")
    tags       = clean_tags(row.get("tags", ""))
    price      = row.get("price", "")
    gs         = float(row.get("gapper_score", 0) or 0)
    vs         = float(row.get("value_score",  0) or 0)
    ms         = float(row.get("moat_score",   0) or 0)
    total      = gs + vs + ms
    gcount     = picks_data.get("gapper_count",  0)
    vcount     = picks_data.get("value_count",   0)
    mcount     = picks_data.get("moat_count",    0)
    scanned    = picks_data.get("total_combined", 0)
    total_picks = gcount + vcount + mcount

    cat_intro = {
        "gapper": "a high-momentum event-driven play",
        "value":  "a deep value catalyst opportunity",
        "moat":   "an institutional-grade moat signal",
    }[category]

    price_line = ""
    if price:
        try:
            pf = float(price)
            if pf > 0:
                price_line = f"It is currently trading at {pf:.2f}."
        except (ValueError, TypeError):
            pass

    tag_line = ""
    if tags:
        tag_line = f"The filing is highlighting: {', '.join(tags[:3])}."

    # Load Polymarket signal for macro hook if fresh
    pm_hook = ""
    try:
        import json as _json, datetime as _dt
        from datetime import timezone as _tz
        pm_path = ROOT / "polymarket_signals.json"
        if pm_path.exists():
            pm_data = _json.loads(pm_path.read_text())
            generated = pm_data.get("generated_at", "")
            if generated:
                age_h = (_dt.datetime.now(_tz.utc) -
                         _dt.datetime.fromisoformat(generated)).total_seconds() / 3600
                if age_h <= 36:
                    sigs = [s for s in pm_data.get("signals", [])
                            if 10 <= s.get("probability", 0) <= 90]
                    if sigs:
                        s = min(sigs, key=lambda x: abs(x["probability"] - 50))
                        pm_hook = (
                            f"Polymarket is giving {s['probability']:.0f}% odds on "
                            f"{s['title'].rstrip('?')}. "
                            f"Here is what that means for {s['impact'].lower()}. "
                            f"And here is what our SEC scanner found this morning."
                        )
    except Exception:
        pass

    # Brand intro hook — establishes authority before the pick
    brand_intro = (
        f"Catalyst Edge scans {scanned} SEC filings every morning before the open. "
        "Here is what the algorithm flagged today."
    )

    # Scroll-stopping hook — pattern interrupt, no pleasantries
    hook_variants = {
        "gapper": (
            pm_hook or
            f"One ticker is about to move. Here is what we found."
        ),
        "value": (
            pm_hook or
            f"The SEC just flagged something most traders have not seen yet. "
            f"We ran the numbers so you do not have to."
        ),
        "moat": (
            pm_hook or
            f"Institutional money just showed its hand in an SEC filing. "
            f"We caught it before the market opens."
        ),
    }

    lines = [
        brand_intro,
        hook_variants[category],
        # Build suspense before the reveal
        f"Our scanner reviewed {scanned} filings and identified {total_picks} catalyst setups today.",
        "One rose above all of them.",
        f"The ticker is {ticker}. And here is why it matters.",
        f"{ticker} just filed a {form_spoken(form)} with the Securities and Exchange Commission.",
    ]

    if tag_line:
        lines.append(tag_line)

    lines.append(
        f"Our catalyst model scored it {total:.0f} out of 16. That puts it in the top tier today."
    )

    if price_line:
        lines.append(price_line)

    lines.append(
        "Watch the opening bell. When a catalyst lines up like this, the window is short."
    )

    # Product suite mention + closing CTA
    lines.append(
        "Catalyst Edge is more than just picks. "
        "We have a live scanner at catalystedgescanner.com, "
        "a 3D market visualization called Cerebro with over 15,000 tickers, "
        "and a conversational AI you can ask about any filing at catalystedge.agency."
    )
    lines.append(
        "We publish picks like this every single morning, completely free. "
        "Upgrade to Reader for 12 dollars a month, or go Pro for 39. "
        "Follow us, subscribe in the bio, "
        "and tell us — are you watching {ticker} today?".format(ticker=ticker)
    )

    return " ".join(lines)

# ── Audio + ASS captions ──────────────────────────────────────────────────────
async def _generate_audio(script: str, out_mp3: Path, out_ass: Path) -> list[dict]:
    tts = edge_tts.Communicate(script, voice=VOICE, rate="-5%", pitch="+0Hz")
    words: list[dict] = []
    sentences: list[dict] = []
    audio = bytearray()

    async for chunk in tts.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            words.append({
                "text":      chunk["text"],
                "offset_ms": chunk["offset"] // 10_000,
                "dur_ms":    chunk["duration"] // 10_000,
            })
        elif chunk["type"] == "SentenceBoundary":
            sentences.append({
                "text":      chunk["text"],
                "offset_ms": chunk["offset"] // 10_000,
                "dur_ms":    chunk["duration"] // 10_000,
            })

    out_mp3.write_bytes(bytes(audio))

    # GuyNeural doesn't emit WordBoundary — estimate per-word timing from sentences
    if not words and sentences:
        words = _words_from_sentences(sentences)

    _write_ass(words, out_ass)
    return words

def _words_from_sentences(sentences: list[dict]) -> list[dict]:
    """Distribute per-word timing evenly within each sentence boundary."""
    words: list[dict] = []
    for sent in sentences:
        ws = sent["text"].split()
        if not ws:
            continue
        per_word = max(80, sent["dur_ms"] // len(ws))
        for i, w in enumerate(ws):
            words.append({
                "text":      w,
                "offset_ms": sent["offset_ms"] + i * per_word,
                "dur_ms":    per_word,
            })
    return words

def _ms_to_ass(ms: int) -> str:
    ms = max(0, ms)
    cs = (ms % 1000) // 10
    s  = (ms // 1000) % 60
    m  = (ms // 60_000) % 60
    h  =  ms // 3_600_000
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _write_ass(words: list[dict], path: Path):
    """3-word window karaoke — current word highlighted yellow, neighbours dimmed."""
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {W}\n"
        f"PlayResY: {H}\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,"
        "-1,0,0,0,100,100,0.5,0,1,2,1,2,60,60,120,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    for i, word in enumerate(words):
        start_ms = word["offset_ms"]
        end_ms   = start_ms + word["dur_ms"] + 60

        win_s = max(0, i - 1)
        win_e = min(len(words), i + 2)

        parts: list[str] = []
        for j in range(win_s, win_e):
            txt = words[j]["text"].upper()
            if j == i:
                # Highlighted: yellow + bold + subtle shadow
                parts.append(f"{{\\c&H0000FFFF&\\b1\\shad2}}{txt}{{\\r}}")
            else:
                # Context: dimmed gray
                parts.append(f"{{\\c&H00A0A0A0&}}{txt}{{\\r}}")

        events.append(
            f"Dialogue: 0,{_ms_to_ass(start_ms)},{_ms_to_ass(end_ms)},"
            f"Default,,0,0,0,,{' '.join(parts)}"
        )

    path.write_text(header + "\n".join(events), encoding="utf-8")

def _elevenlabs_audio(script: str, out_mp3: Path, out_ass: Path) -> list[dict]:
    el_key = _load_el_key()
    client = _ElevenLabsClient(api_key=el_key)
    chunks = client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        text=script,
        model_id="eleven_turbo_v2",
        output_format="mp3_44100_128",
    )
    data = b"".join(chunks) if not isinstance(chunks, bytes) else chunks
    out_mp3.write_bytes(data)
    # Estimate word timing from total duration
    dur_ms = int(get_audio_duration(out_mp3) * 1000)
    all_words = script.split()
    per_word = max(80, dur_ms // len(all_words)) if all_words else 200
    words = [{"text": w, "offset_ms": i * per_word, "dur_ms": per_word}
             for i, w in enumerate(all_words)]
    _write_ass(words, out_ass)
    return words

def _load_el_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        env_file = ROOT / ".sec_email_env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("ELEVENLABS_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    return key

def generate_audio(script: str, out_mp3: Path, out_ass: Path) -> list[dict]:
    el_key = ""  # ElevenLabs quota exhausted — use edge-tts (free, unlimited)
    if el_key and HAS_ELEVENLABS:
        try:
            print("  Voice: ElevenLabs Lily (British, velvety)")
            return _elevenlabs_audio(script, out_mp3, out_ass)
        except Exception as e:
            print(f"  ElevenLabs failed ({e}) — falling back to edge-tts")
    print("  Voice: edge-tts Libby (British, fallback)")
    return asyncio.run(_generate_audio(script, out_mp3, out_ass))

def get_audio_duration(mp3_path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(mp3_path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 44.0

# ── Music bed ─────────────────────────────────────────────────────────────────
def generate_music_bed(duration_s: float, out_wav: Path) -> bool:
    """A-minor ambient pad: A2 + E3 + A3 + C4 with gentle tremolo.
    Generated via FFmpeg aevalsrc — no Python synthesis needed."""
    expr = (
        "0.10*sin(2*PI*110.0*t)*(1+0.04*sin(2*PI*0.22*t))+"
        "0.07*sin(2*PI*164.8*t)*(1+0.04*sin(2*PI*0.27*t))+"
        "0.06*sin(2*PI*220.0*t)*(1+0.03*sin(2*PI*0.18*t))+"
        "0.04*sin(2*PI*261.6*t)*(1+0.03*sin(2*PI*0.32*t))+"
        "0.03*sin(2*PI*329.6*t)*(1+0.02*sin(2*PI*0.14*t))"
    )
    total = duration_s + 4.0
    fade_out_at = max(0.5, duration_s - 2.5)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"aevalsrc={expr}:s=44100:d={total:.2f}",
        "-af", (
            f"lowpass=f=700,"
            f"afade=t=in:d=2.5,"
            f"afade=t=out:st={fade_out_at:.2f}:d=3,"
            f"volume=0.15"
        ),
        str(out_wav),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("  Music bed skipped (ffmpeg aevalsrc failed):", r.stderr[-200:])
        return False
    return True

# ── Video composition ─────────────────────────────────────────────────────────
def compose_video(slides: list[tuple[Path, float]], audio_path: Path,
                  ass_path: Path, music_path: Path | None, out_path: Path):
    """
    Pass 1 — Ken Burns zoompan per slide + xfade concat → silent video.
    Pass 2 — voice + music bed (optional) + ASS karaoke captions → final MP4.
    """
    tmp = Path(tempfile.mkdtemp(prefix="catalyst_tmp_")) / "_tmp_silent.mp4"

    # ── Pass 1: Ken Burns ─────────────────────────────────────────────────────
    input_args: list[str] = []
    for img_path, dur in slides:
        input_args += ["-loop", "1", "-t", f"{dur + 0.65:.2f}", "-i", str(img_path)]

    n = len(slides)
    kb_styles = ["push_in", "pull_out", "pan_right", "pan_left", "push_in"]
    fc: list[str] = []

    for i, (_, dur) in enumerate(slides):
        frames = max(30, int((dur + 0.65) * FPS))
        style  = kb_styles[i % len(kb_styles)]

        # Each expression uses `on` (0-based output frame) and `d` (total frames)
        if style == "push_in":
            zp = (f"z='1+0.06*(on/{frames})':"
                  "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'")
        elif style == "pull_out":
            zp = (f"z='1.06-0.06*(on/{frames})':"
                  "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'")
        elif style == "pan_right":
            zp = (f"z=1.05:"
                  f"x='iw*0.025*(on/{frames})':y='ih/2-(ih/zoom/2)'")
        else:  # pan_left
            zp = (f"z=1.05:"
                  f"x='iw*0.025*(1-(on/{frames}))':y='ih/2-(ih/zoom/2)'")

        fc.append(
            f"[{i}:v]zoompan={zp}:d={frames}:s={W}x{H}:fps={FPS},"
            f"setsar=1[v{i}]"
        )

    prev   = "v0"
    offset = 0.0
    for i in range(1, n):
        offset += slides[i-1][1] - 0.45
        nxt = f"x{i}"
        fc.append(
            f"[{prev}][v{i}]xfade=transition=fade:duration=0.45:"
            f"offset={offset:.3f}[{nxt}]"
        )
        prev = nxt
    fc.append(f"[{prev}]null[vout]")

    cmd1 = (
        ["ffmpeg", "-y"] + input_args
        + ["-filter_complex", ";".join(fc),
           "-map", "[vout]",
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart",
           str(tmp)]
    )
    print("  Pass 1 (Ken Burns + xfade)...")
    r1 = subprocess.run(cmd1, capture_output=True, text=True)
    if r1.returncode != 0:
        print("ffmpeg pass-1 error:", r1.stderr[-2000:])
        raise SystemExit(1)

    # ── Pass 2: audio mix + ASS captions ─────────────────────────────────────
    ass_esc = str(ass_path).replace("\\", "/").replace(":", "\\:")

    print("  Pass 2 (audio + captions)...")
    if music_path and music_path.exists():
        cmd2 = [
            "ffmpeg", "-y",
            "-i", str(tmp),
            "-i", str(audio_path),
            "-i", str(music_path),
            "-filter_complex",
            (
                "[1:a]volume=1.0[voice];"
                "[2:a]volume=0.13[music];"
                "[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout];"
                f"[0:v]subtitles={ass_esc}[vout]"
            ),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-shortest",
            str(out_path),
        ]
    else:
        cmd2 = [
            "ffmpeg", "-y",
            "-i", str(tmp),
            "-i", str(audio_path),
            "-vf", f"subtitles={ass_esc}",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-shortest",
            str(out_path),
        ]

    r2 = subprocess.run(cmd2, capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r2.returncode != 0:
        print("ffmpeg pass-2 error:", r2.stderr[-2000:])
        raise SystemExit(1)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"generate_tiktok_video v2 (Pillow + Ken Burns + karaoke) date={TODAY}")

    if not HAS_PIL:
        print("  ERROR: Pillow not installed.")
        print("  Run: python3 -m pip install --break-system-packages Pillow")
        raise SystemExit(1)

    if not HAS_TTS:
        print("  ERROR: edge-tts not installed.")
        print("  Run: python3 -m pip install --break-system-packages edge-tts")
        raise SystemExit(1)

    ticker, row, picks_data = load_pick()
    if not ticker:
        print("  No pick data — skipping video generation")
        return

    category    = get_category(row)
    form        = row.get("form", "8-K")
    tags        = clean_tags(row.get("tags", ""))
    price       = row.get("price", "")
    gs          = float(row.get("gapper_score", 0) or 0)
    vs          = float(row.get("value_score",  0) or 0)
    ms          = float(row.get("moat_score",   0) or 0)
    total_score = gs + vs + ms

    top5_tickers = picks_data.get("top5_tickers", [ticker])
    top5_scores  = load_top5_scores(top5_tickers)

    print(f"  Pick: ${ticker}  category={category}  score={total_score:.0f}  form={form}")
    print(f"  Tags: {tags}")
    print(f"  Top5: {top5_scores}")

    fonts = load_fonts()
    print(f"  Fonts loaded: {list(fonts.keys())}")

    script = build_script(ticker, row, category, picks_data)
    print(f"  Script ({len(script.split())} words):\n    {script[:110]}...")

    TMP     = Path(tempfile.mkdtemp(prefix="catalyst_vid_"))
    mp3     = TMP / "voice.mp3"
    ass     = TMP / "captions.ass"
    music   = TMP / "music.wav"

    print("  Generating voiceover...")
    words = generate_audio(script, mp3, ass)
    audio_dur = get_audio_duration(mp3)
    print(f"  Audio: {audio_dur:.1f}s  |  {len(words)} words  |  ASS captions written")

    print("  Generating music bed...")
    has_music = generate_music_bed(audio_dur, music)
    print(f"  Music: {'OK' if has_music else 'skipped'}")

    # Slide timing: Hook 9% | Reveal 20% | Signals 23% | Setup 20% | ProductIntro 16% | CTA 12%
    ratios    = [0.09, 0.20, 0.23, 0.20, 0.16, 0.12]
    total_dur = audio_dur + 1.5
    durations = [total_dur * r for r in ratios]

    print("  Rendering slides with Pillow...")
    slide_defs = [
        ("hook",    lambda: slide_hook(ticker, category, fonts)),
        ("reveal",  lambda: slide_ticker_reveal(ticker, category, form, total_score, fonts)),
        ("signals", lambda: slide_signals(ticker, category, tags, fonts)),
        ("setup",   lambda: slide_setup(ticker, category, price, top5_scores, picks_data, fonts)),
        ("product", lambda: slide_product_intro(category, fonts)),
        ("cta",     lambda: slide_cta(ticker, category, fonts)),
    ]

    slide_files: list[tuple[Path, float]] = []
    for name, fn in slide_defs:
        print(f"    {name}...", end=" ", flush=True)
        img_path = TMP / f"slide_{name}.png"
        fn().save(str(img_path))
        slide_files.append((img_path, durations[len(slide_files)]))
        print("done")

    WIN_OUT.mkdir(parents=True, exist_ok=True)
    out_local = ROOT / "tiktok_video.mp4"
    out_win   = WIN_OUT / f"tiktok_{TODAY}.mp4"

    print(f"\n  Composing {audio_dur:.0f}s video (Ken Burns + karaoke captions + music)...")
    compose_video(slide_files, mp3, ass, music if has_music else None, out_win)

    shutil.copy(str(out_win), str(out_local))

    # Copy to Windows Desktop so it's ready to upload manually
    WIN_DESKTOP = Path("/path/to/local/Desktop/catalyst-edge/social")
    if WIN_DESKTOP.exists():
        dest = WIN_DESKTOP / f"tiktok_{TODAY}.mp4"
        shutil.copy(str(out_win), str(dest))
        print(f"  Copied to Windows Desktop: {dest.name}")
        # Write a "READY" marker so the correct file is obvious
        (WIN_DESKTOP / f"UPLOAD_TODAY_tiktok_{TODAY}.txt").write_text(
            f"TikTok/YouTube Shorts upload — {TODAY_DISPLAY}\n"
            f"File: tiktok_{TODAY}.mp4\n"
            f"Caption: Today's top SEC catalyst picks — {TODAY_DISPLAY}\n"
            f"Newsletter: https://catalystedge.agency\n"
            f"Live Scanner: https://catalystedgescanner.com\n"
            f"Cerebro HUD: https://catalystedge.agency/cerebro/\n"
            f"Talk to AI: https://catalystedge.agency\n"
            f"Pricing: https://catalystedge.agency/pricing/\n"
            f"#stocks #investing #SEC #fintwit #stockstowatch\n",
            encoding="utf-8",
        )
    else:
        print("  Windows Desktop path not found — video at workspace/social/ only")

    shutil.rmtree(TMP, ignore_errors=True)

    mb = out_win.stat().st_size / 1e6
    print(f"\n  Done! {mb:.1f} MB → {out_win}")
    print(f"  Also at: {out_local}")


if __name__ == "__main__":
    main()
