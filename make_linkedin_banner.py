#!/usr/bin/env python3
"""Generate a LinkedIn banner for Catalyst Edge."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────
W, H       = 1584, 396
BG         = "#0d1117"
GREEN      = "#3fb950"
GREEN_DIM  = "#2ea043"
TEXT_WHITE = "#e6edf3"
MUTED      = "#8b949e"
SURFACE    = "#161b22"
BORDER     = "#30363d"

FONT_BOLD  = "/usr/share/fonts/truetype/ubuntu/Ubuntu[wdth,wght].ttf"
FONT_MONO  = "/usr/share/fonts/truetype/ubuntu/UbuntuMono[wght].ttf"

OUT = Path(__file__).parent / "linkedin_banner.png"


def load(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + radius*2, y0 + radius*2], fill=fill)
    draw.ellipse([x1 - radius*2, y0, x1, y0 + radius*2], fill=fill)
    draw.ellipse([x0, y1 - radius*2, x0 + radius*2, y1], fill=fill)
    draw.ellipse([x1 - radius*2, y1 - radius*2, x1, y1], fill=fill)


img  = Image.new("RGB", (W, H), hex_to_rgb(BG))
draw = ImageDraw.Draw(img)

# ── Background grid lines (subtle) ───────────────────────────────────
for x in range(0, W, 60):
    draw.line([(x, 0), (x, H)], fill=(48, 54, 61, 40), width=1)
for y in range(0, H, 60):
    draw.line([(0, y), (W, y)], fill=(48, 54, 61, 40), width=1)

# ── Left green accent bar ─────────────────────────────────────────────
draw.rectangle([(0, 0), (6, H)], fill=hex_to_rgb(GREEN))

# ── Subtle right panel background ────────────────────────────────────
draw_rounded_rect(draw, (940, 40, W - 40, H - 40), 16, hex_to_rgb(SURFACE))
draw_rounded_rect(draw, (942, 42, W - 38, H - 38), 15, (22, 27, 34))

# ── LEFT SIDE ─────────────────────────────────────────────────────────
f_tag    = load(FONT_MONO,  22)
f_main   = load(FONT_BOLD,  62)
f_sub    = load(FONT_BOLD,  28)
f_chips  = load(FONT_MONO,  19)
f_url    = load(FONT_MONO,  24)

# Tag line
draw.text((60, 48), "⚡  FREE PRE-MARKET SCANNER", font=f_tag, fill=hex_to_rgb(GREEN))

# Main headline
draw.text((56, 88), "Catalyst Edge", font=f_main, fill=hex_to_rgb(TEXT_WHITE))

# Sub headline
draw.text((62, 168), "SEC EDGAR Intelligence — Before the Market Opens", font=f_sub, fill=hex_to_rgb(MUTED))

# Divider line
draw.line([(62, 214), (560, 214)], fill=hex_to_rgb(BORDER), width=1)

# Feature chips
chips = ["300+ SEC Filings", "1,600+ Tickers", "4 AM ET Daily", "Free · No Login"]
cx = 62
for chip in chips:
    tw = draw.textlength(chip, font=f_chips)
    pad = 14
    bw  = int(tw) + pad * 2
    bh  = 34
    cy  = 228
    draw_rounded_rect(draw, (cx, cy, cx + bw, cy + bh), 8, (22, 42, 22))
    # border
    draw.rounded_rectangle([cx, cy, cx + bw, cy + bh], radius=8,
                            outline=hex_to_rgb(GREEN_DIM), width=1)
    draw.text((cx + pad, cy + 8), chip, font=f_chips, fill=hex_to_rgb(GREEN))
    cx += bw + 10

# Bottom tagline
draw.text((62, 300), "Gap Plays  ·  Insider Alerts  ·  Squeeze Radar  ·  Dark Pool Signals",
          font=f_url, fill=hex_to_rgb(MUTED))

# ── RIGHT SIDE — URL card ─────────────────────────────────────────────
f_url_big  = load(FONT_MONO, 34)
f_url_lab  = load(FONT_BOLD, 18)
f_url_sub  = load(FONT_MONO, 18)

rx = 960

# Label
draw.text((rx + 30, 70), "🖥  Live Scanner", font=f_url_lab, fill=hex_to_rgb(MUTED))

# URL — big green
url_text = "catalystedgescanner.com"
draw.text((rx + 30, 108), url_text, font=f_url_big, fill=hex_to_rgb(GREEN))

# Underline
url_w = int(draw.textlength(url_text, font=f_url_big))
draw.line([(rx + 30, 152), (rx + 30 + url_w, 152)],
          fill=hex_to_rgb(GREEN_DIM), width=2)

# Stats row
stats = [("469", "visitors today"), ("5m 47s", "avg session"), ("Free", "forever")]
sx = rx + 30
for val, lbl in stats:
    draw.text((sx, 178), val, font=load(FONT_BOLD, 28), fill=hex_to_rgb(TEXT_WHITE))
    draw.text((sx, 215), lbl, font=f_url_sub, fill=hex_to_rgb(MUTED))
    sx += 170

# Divider
draw.line([(rx + 30, 258), (W - 60, 258)], fill=hex_to_rgb(BORDER), width=1)

# CTA line
draw.text((rx + 30, 274), "📬  Free daily picks before pre-market opens",
          font=f_url_sub, fill=hex_to_rgb(MUTED))

draw.text((rx + 30, 304), "No account · No credit card · No paywalls",
          font=f_url_sub, fill=hex_to_rgb(MUTED))

# ── Top right corner — green dot live indicator ───────────────────────
draw.ellipse([(W - 70, 24), (W - 56, 38)], fill=hex_to_rgb(GREEN))
draw.text((W - 52, 22), "LIVE", font=load(FONT_MONO, 18), fill=hex_to_rgb(GREEN))

# ── Save ──────────────────────────────────────────────────────────────
img.save(OUT, "PNG", quality=95)
print(f"Banner saved → {OUT}")
print(f"Size: {W}x{H}px — LinkedIn recommended: 1584x396px ✓")
