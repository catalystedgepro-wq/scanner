#!/usr/bin/env python3
"""Generate a 1500x500 Twitter/X profile banner for Catalyst Edge."""

from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1500, 500
OUT  = Path(__file__).parent / "twitter_banner.png"
WIN  = Path("/path/to/local/Desktop/catalyst-edge/social/twitter_banner.png")

NAVY  = (8,  12,  25)
NAVY2 = (12, 18,  40)
NAVY3 = (18, 28,  65)
INDIGO= (79, 70, 229)
BLUE  = (59,130, 246)
PURPLE=(139,92, 246)
WHITE = (255,255,255)
GRAY  = (148,163,184)
DIM   = (71, 85, 105)
GREEN = (16, 185,129)
AMBER = (245,158, 11)
RED   = (239, 68, 68)

FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def fnt(size, bold=False):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, size)
    except:
        return ImageFont.load_default()

def gradient_bg(img):
    draw = ImageDraw.Draw(img)
    for x in range(W):
        t = x / W
        r = int(NAVY[0] + (NAVY3[0] - NAVY[0]) * t)
        g = int(NAVY[1] + (NAVY3[1] - NAVY[1]) * t)
        b = int(NAVY[2] + (NAVY3[2] - NAVY[2]) * t)
        draw.line([(x, 0), (x, H)], fill=(r, g, b))

def draw_grid(draw):
    """Subtle grid lines for a data/terminal feel."""
    for x in range(0, W, 60):
        draw.line([(x, 0), (x, H)], fill=(255,255,255,8), width=1)
    for y in range(0, H, 60):
        draw.line([(0, y), (W, y)], fill=(255,255,255,8), width=1)

def draw_accent_bar(draw):
    """Thin indigo gradient bar across the top."""
    for x in range(W):
        t = x / W
        r = int(INDIGO[0] + (PURPLE[0] - INDIGO[0]) * t)
        g = int(INDIGO[1] + (PURPLE[1] - INDIGO[1]) * t)
        b = int(INDIGO[2] + (PURPLE[2] - INDIGO[2]) * t)
        draw.line([(x, 0), (x, 4)], fill=(r, g, b))

def draw_ticker_strip(draw):
    """Fake live ticker strip at the bottom."""
    strip_y = H - 48
    draw.rectangle([(0, strip_y), (W, H)], fill=(6, 9, 20))
    draw.line([(0, strip_y), (W, strip_y)], fill=INDIGO, width=1)

    items = [
        ("8-K CATALYSTS", GREEN),
        ("FORM 4 INSIDER BUYS", AMBER),
        ("SHORT SQUEEZE RADAR", RED),
        ("INSTITUTIONAL MOAT SIGNALS", PURPLE),
        ("DEEP VALUE SCREEN", BLUE),
        ("CONVERGENCE ALERTS", GREEN),
        ("SEC EDGAR INTELLIGENCE", GRAY),
    ]

    x = 24
    f = fnt(13, bold=True)
    sep_f = fnt(13)
    y_text = strip_y + 14
    for label, color in items:
        draw.text((x, y_text), label, font=f, fill=color)
        bbox = draw.textbbox((x, y_text), label, font=f)
        x = bbox[2] + 12
        if x < W - 60:
            draw.text((x, y_text), "·", font=sep_f, fill=DIM)
            x += 18

def main():
    img  = Image.new("RGB", (W, H), NAVY)
    gradient_bg(img)
    draw = ImageDraw.Draw(img)
    draw_grid(draw)
    draw_accent_bar(draw)

    # ── Left side: brand block ────────────────────────────────────────────────
    # Tag line above name
    tag_f = fnt(14, bold=True)
    draw.text((60, 90), "SEC EDGAR INTELLIGENCE  ·  DAILY CATALYST SCAN", font=tag_f, fill=INDIGO)

    # Main brand name
    name_f = fnt(72, bold=True)
    draw.text((60, 118), "Catalyst", font=name_f, fill=WHITE)
    # "Edge" in indigo
    bbox = draw.textbbox((60, 118), "Catalyst ", font=name_f)
    draw.text((bbox[2], 118), "Edge", font=name_f, fill=(129, 140, 248))

    # Tagline
    tag2_f = fnt(20)
    draw.text((62, 212), "300+ SEC filings scanned every morning before the open.", font=tag2_f, fill=GRAY)

    # Feature pills
    features = [
        ("⚡ Gapper Plays", RED),
        ("💎 Value Picks", BLUE),
        ("🏰 Moat Signals", PURPLE),
        ("🔥 Squeeze Radar", AMBER),
    ]
    px = 62
    py = 260
    pill_f = fnt(14, bold=True)
    for label, color in features:
        bbox = draw.textbbox((0, 0), label, font=pill_f)
        pw = bbox[2] - bbox[0] + 20
        ph = 28
        draw.rounded_rectangle([(px, py), (px+pw, py+ph)], radius=4,
                                fill=(color[0]//6, color[1]//6, color[2]//6),
                                outline=color, width=1)
        draw.text((px+10, py+7), label, font=pill_f, fill=color)
        px += pw + 10

    # CTA
    cta_f = fnt(18, bold=True)
    draw.text((62, 318), "Free daily newsletter →  catalystedge.agency", font=cta_f, fill=WHITE)

    # ── Right side: mock data panel ───────────────────────────────────────────
    panel_x = 960
    panel_w = 480
    panel_h = 320
    panel_y = 60
    draw.rounded_rectangle(
        [(panel_x, panel_y), (panel_x+panel_w, panel_y+panel_h)],
        radius=8, fill=(10,15,32), outline=(30,40,80), width=1
    )
    # Panel header
    ph_f = fnt(11, bold=True)
    draw.text((panel_x+16, panel_y+12), "TODAY'S TOP PICKS", font=ph_f, fill=INDIGO)
    draw.line([(panel_x, panel_y+34), (panel_x+panel_w, panel_y+34)], fill=(20,30,60), width=1)

    rows = [
        ("$CIB",  "GAPPER",  "+8.3%", GREEN),
        ("$BNTX", "VALUE",   "+4.1%", BLUE),
        ("$ARM",  "MOAT",    "+2.7%", PURPLE),
        ("$ASPI", "SQUEEZE", "+11.2%",RED),
        ("$BSAC", "VALUE",   "+3.5%", BLUE),
    ]
    row_f  = fnt(14, bold=True)
    cat_f  = fnt(12)
    pct_f  = fnt(14, bold=True)
    for i, (ticker, cat, pct, color) in enumerate(rows):
        ry = panel_y + 46 + i * 48
        # Row bg on alternates
        if i % 2 == 0:
            draw.rectangle([(panel_x+1, ry-4), (panel_x+panel_w-1, ry+34)], fill=(12,18,38))
        draw.text((panel_x+16, ry+2),  ticker, font=row_f, fill=WHITE)
        draw.text((panel_x+100, ry+6), cat,    font=cat_f, fill=color)
        draw.text((panel_x+390, ry+2), pct,    font=pct_f, fill=GREEN)

    # "LIVE" badge
    live_f = fnt(10, bold=True)
    draw.rounded_rectangle([(panel_x+panel_w-54, panel_y+8), (panel_x+panel_w-8, panel_y+26)],
                            radius=3, fill=(16,185,129,40), outline=GREEN, width=1)
    draw.text((panel_x+panel_w-46, panel_y+12), "● LIVE", font=live_f, fill=GREEN)

    draw_ticker_strip(draw)

    img.save(OUT, "PNG", optimize=True)
    print(f"Saved: {OUT}")

    WIN.parent.mkdir(parents=True, exist_ok=True)
    img.save(WIN, "PNG", optimize=True)
    print(f"Saved: {WIN}")

if __name__ == "__main__":
    main()
