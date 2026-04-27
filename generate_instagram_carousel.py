#!/usr/bin/env python3
"""generate_instagram_carousel.py — Auto-generate a 5-slide Instagram carousel.

Carousels are the highest organic-reach format on Instagram — the swipe
mechanic drives completion rate and saves, both strong ranking signals.

Slides:
  1. Hook     — scroll-stopper, no ticker shown yet
  2. Reveal   — big $TICKER + catalyst score
  3. Signals  — 3 key tags from filing
  4. Picks    — top 5 bar chart
  5. CTA      — follow + subscribe

Output: instagram_carousel_YYYY-MM-DD_1.png … _5.png
        (also copied to Desktop social dir)
"""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

ROOT    = Path(__file__).parent
WIN_OUT = Path(__file__).parent / "social"
TODAY   = datetime.date.today().isoformat()
TODAY_DISPLAY = datetime.date.today().strftime("%B %d, %Y")

W = H = 1080   # Square for feed + carousel

# ── Colours ───────────────────────────────────────────────────────────────────
DARK_BG    = (6,   8,  20)
NAVY       = (10, 15,  30)
CARD_BG    = (18, 26,  58)
BLUE       = (59, 130, 246)
PURPLE     = (139, 92, 246)
RED        = (210,  35,  35)
GREEN      = (16,  185, 129)
WHITE      = (255, 255, 255)
GRAY       = (110, 130, 165)
LIGHT_GRAY = (190, 205, 225)
DARK_RED   = (38,   8,   8)
DARK_GREEN = (8,   35,  20)
DARK_PURPLE= (28,  12,  55)

CAT_COLOR = {"gapper": RED,  "value": GREEN,  "moat": PURPLE}
CAT_BG    = {"gapper": DARK_RED, "value": DARK_GREEN, "moat": DARK_PURPLE}
CAT_LABEL = {"gapper": "GAPPER PLAY", "value": "VALUE PLAY", "moat": "INSTITUTIONAL MOAT"}

# ── Fonts ─────────────────────────────────────────────────────────────────────
def load_fonts():
    bold = next((p for p in [
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ] if Path(p).exists()), None)
    reg = next((p for p in [
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ] if Path(p).exists()), None)

    def f(path, size):
        if path:
            try: return ImageFont.truetype(path, size)
            except Exception: pass
        return ImageFont.load_default()

    return {
        "giant": f(bold, 160), "h1": f(bold, 90), "h2": f(bold, 64),
        "h3":    f(bold,  48), "body": f(reg,  38), "small": f(reg, 30),
        "tag":   f(bold,  36), "brand": f(bold, 46), "score": f(bold, 110),
    }

# ── Drawing helpers ───────────────────────────────────────────────────────────
def lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i]*(1-t) + c2[i]*t) for i in range(3))

def new_canvas(top=DARK_BG, bot=(3, 4, 12)):
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W-1, y)], fill=lerp(top, bot, t))
    return img

def draw_rr(draw, x1, y1, x2, y2, r, fill, outline=None, ow=0):
    try:
        draw.rounded_rectangle([x1,y1,x2,y2], radius=r, fill=fill, outline=outline, width=ow)
    except TypeError:
        draw.rounded_rectangle([x1,y1,x2,y2], radius=r, fill=fill)

def tsize(draw, text, font):
    bb = draw.textbbox((0,0), text, font=font)
    return bb[2]-bb[0], bb[3]-bb[1]

def shadow(draw, xy, text, font, fill, d=3):
    draw.text((xy[0]+d, xy[1]+d), text, font=font, fill=(0,0,0,180))
    draw.text(xy, text, font=font, fill=fill)

def centered(draw, y, text, font, fill, shad=True):
    w, h = tsize(draw, text, font)
    x = (W - w) // 2
    if shad: draw.text((x+3, y+3), text, font=font, fill=(0,0,0,180))
    draw.text((x, y), text, font=font, fill=fill)
    return h

def hbar(img, x1, y1, x2, y2, c1, c2):
    draw = ImageDraw.Draw(img)
    span = max(1, x2-x1)
    step = max(1, span//150)
    for x in range(x1, x2, step):
        draw.rectangle([x, y1, min(x+step, x2), y2], fill=lerp(c1, c2, (x-x1)/span))

def glow(img, cx, cy, r, color):
    draw = ImageDraw.Draw(img)
    bg = img.getpixel((cx, min(cy+r+2, H-1)))
    for frac, alpha in [(1.0,0.75),(0.75,0.45),(0.5,0.2),(0.3,0.08)]:
        ri = int(r*frac)
        draw.ellipse([cx-ri,cy-ri,cx+ri,cy+ri], fill=lerp(bg,color,alpha))

# ── Chrome ────────────────────────────────────────────────────────────────────
def top_bar(draw, fonts, label="BREAKING — SEC CATALYST"):
    draw.rectangle([0, 0, W, 82], fill=(185,18,18))
    draw.rectangle([0, 78, W, 82], fill=(80,5,5))
    centered(draw, 18, label, fonts["small"], WHITE, shad=False)
    draw.rectangle([0, 82, W, 138], fill=(10,6,28))
    shadow(draw, (44, 94), "CATALYST EDGE", fonts["brand"], lerp(BLUE,WHITE,0.5))
    dw, _ = tsize(draw, TODAY_DISPLAY.upper(), fonts["small"])
    draw.text((W-dw-44, 100), TODAY_DISPLAY.upper(), font=fonts["small"], fill=GRAY)

def swipe_hint(draw, fonts, slide_num, total=5):
    # Progress dots + "swipe" prompt at bottom
    draw.rectangle([0, H-90, W, H], fill=(8,6,18))
    dot_r = 7
    spacing = 26
    total_w = total * (dot_r*2) + (total-1) * (spacing - dot_r*2)
    sx = (W - total_w) // 2
    for i in range(total):
        cx = sx + i * spacing + dot_r
        cy = H - 52
        col = WHITE if i == slide_num - 1 else GRAY
        draw.ellipse([cx-dot_r, cy-dot_r, cx+dot_r, cy+dot_r], fill=col)
    if slide_num < total:
        hint = "SWIPE \u2192 FOR MORE"
        hw, _ = tsize(draw, hint, fonts["small"])
        draw.text(((W-hw)//2, H-28), hint, font=fonts["small"], fill=GRAY)

# ── Slide 1: Hook ─────────────────────────────────────────────────────────────
def slide_1_hook(ticker, category, total_scanned, fonts):
    img = new_canvas((8,5,22),(3,3,14))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    for coords in [(0,0,W,16),(0,H-16,W,H),(0,0,16,H),(W-16,0,W,H)]:
        draw.rectangle(list(coords), fill=cat_col)

    # Alert circle
    cx, cy = W//2, H//2 - 80
    glow(img, cx, cy, 280, RED)
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx-120,cy-120,cx+120,cy+120], fill=RED)
    bw, bh = tsize(draw, "!", fonts["h1"])
    shadow(draw, (cx-bw//2, cy-bh//2-8), "!", fonts["h1"], WHITE, 4)

    centered(draw, cy+210, "SEC ALERT", fonts["h1"], WHITE)
    centered(draw, cy+320, f"I scanned {total_scanned} filings.", fonts["h3"], LIGHT_GRAY)
    centered(draw, cy+380, "One ticker stands out.", fonts["h3"], cat_col)

    centered(draw, H-155, "SWIPE TO SEE THE PICK \u2192", fonts["tag"], lerp(cat_col,WHITE,0.4))
    centered(draw, H-105, "CATALYST EDGE  |  " + TODAY_DISPLAY.upper(), fonts["small"], GRAY)
    swipe_hint(draw, fonts, 1)
    return img

# ── Slide 2: Reveal ───────────────────────────────────────────────────────────
def slide_2_reveal(ticker, category, form, score, fonts):
    img = new_canvas((7,5,18),(14,10,32))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    top_bar(draw, fonts)

    # Category pill
    ctext = CAT_LABEL[category]
    cw, _ = tsize(draw, ctext, fonts["tag"])
    cx1 = (W-cw-60)//2; cx2 = cx1+cw+60
    draw_rr(draw, cx1, 162, cx2, 222, 30, CAT_BG[category], cat_col, 2)
    shadow(draw, (cx1+30, 180), ctext, fonts["tag"], cat_col)

    # Giant ticker
    tk_w, tk_h = tsize(draw, ticker, fonts["giant"])
    ds_w, _    = tsize(draw, "$", fonts["h2"])
    total_w = ds_w + 8 + tk_w
    sx = (W - total_w) // 2
    tk_y = 250
    draw_rr(draw, sx-36, tk_y-16, sx+total_w+36, tk_y+tk_h+16, 20, (12,12,38))
    shadow(draw, (sx, tk_y+(tk_h-tsize(draw,"$",fonts["h2"])[1])//2+12), "$", fonts["h2"], lerp(cat_col,WHITE,0.5))
    shadow(draw, (sx+ds_w+8, tk_y), ticker, fonts["giant"], cat_col, 5)

    # Score
    sc_y = tk_y + tk_h + 55
    centered(draw, sc_y, "CATALYST SCORE", fonts["small"], GRAY)
    sc_str = f"{score:.0f} / 16"
    sw, sh = tsize(draw, sc_str, fonts["score"])
    shadow(draw, ((W-sw)//2, sc_y+42), sc_str, fonts["score"], cat_col, 5)

    bar_y = sc_y + 42 + sh + 28
    BX1, BX2, BH = 70, W-70, 30
    draw_rr(draw, BX1, bar_y, BX2, bar_y+BH, BH//2, (18,22,54))
    fill_px = int((BX2-BX1)*min(1.0,score/16.0))
    if fill_px > BH:
        hbar(img, BX1, bar_y, BX1+fill_px, bar_y+BH, cat_col, lerp(cat_col,WHITE,0.55))
        draw = ImageDraw.Draw(img)

    centered(draw, bar_y+BH+44, "ADD TO WATCHLIST", fonts["h3"], lerp(cat_col,WHITE,0.35))
    centered(draw, bar_y+BH+104, f"Filed: {form.upper()}", fonts["small"], GRAY)

    swipe_hint(draw, fonts, 2)
    return img

# ── Slide 3: Signals ──────────────────────────────────────────────────────────
def slide_3_signals(ticker, category, tags, fonts):
    img = new_canvas((7,5,18),(14,10,32))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    top_bar(draw, fonts, "WHY THIS MATTERS")
    centered(draw, 162, f"${ticker} — KEY SIGNALS", fonts["h2"], cat_col)
    centered(draw, 240, "From the SEC filing", fonts["small"], GRAY)

    signals = (tags or ["SEC Material Event","Watch Opening Bell","High Catalyst Score"])[:3]
    for i, sig in enumerate(signals):
        cy = 300 + i * 210
        draw_rr(draw, 50, cy, W-50, cy+178, 18, CARD_BG, cat_col, 1)
        draw_rr(draw, 50, cy, 74, cy+178, 6, cat_col)
        bcx, bcy = 108, cy + 89
        draw.ellipse([bcx-34,bcy-34,bcx+34,bcy+34], fill=cat_col)
        n = str(i+1); nw, nh = tsize(draw, n, fonts["tag"])
        draw.text((bcx-nw//2, bcy-nh//2), n, font=fonts["tag"], fill=WHITE)
        sig_text = sig.title()
        sw, _ = tsize(draw, sig_text, fonts["body"])
        avail = W - 50 - 50 - 160
        if sw <= avail:
            shadow(draw, (160, cy+72), sig_text, fonts["body"], WHITE)
        else:
            ws = sig_text.split(); half = max(1, len(ws)//2)
            shadow(draw, (160, cy+52), " ".join(ws[:half]), fonts["body"], WHITE)
            shadow(draw, (160, cy+52+48), " ".join(ws[half:]), fonts["body"], WHITE)

    swipe_hint(draw, fonts, 3)
    return img

# ── Slide 4: Top 5 chart ──────────────────────────────────────────────────────
def slide_4_chart(ticker, category, top5, picks_data, fonts):
    img = new_canvas((7,5,18),(14,10,32))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    top_bar(draw, fonts, "TODAY'S TOP PICKS")

    scanned = picks_data.get("total_combined", 0)
    gcount  = picks_data.get("gapper_count",  0)
    vcount  = picks_data.get("value_count",   0)
    mcount  = picks_data.get("moat_count",    0)
    total_picks = gcount + vcount + mcount

    centered(draw, 162, f"From {scanned} SEC filings → {total_picks} catalyst setups", fonts["small"], GRAY)
    centered(draw, 205, "RANKED BY CATALYST SCORE", fonts["h3"], WHITE)

    cstart = 268
    BAR_H  = 72; BAR_GAP = 22; MAX_W = W - 240

    for idx, (t, s) in enumerate(top5[:5]):
        row_y = cstart + idx * (BAR_H + BAR_GAP)
        is_top = (idx == 0)
        lc = cat_col if is_top else LIGHT_GRAY
        lf = fonts["tag"] if is_top else fonts["body"]
        tw, th = tsize(draw, f"${t}", lf)
        shadow(draw, (50, row_y + (BAR_H-th)//2), f"${t}", lf, lc)
        bar_x = 200
        draw_rr(draw, bar_x, row_y, bar_x+MAX_W, row_y+BAR_H, BAR_H//2, (18,22,54))
        fill_w = int(MAX_W * min(1.0, s/16.0))
        if fill_w > BAR_H:
            if is_top:
                hbar(img, bar_x, row_y, bar_x+fill_w, row_y+BAR_H, cat_col, lerp(cat_col,WHITE,0.5))
                draw = ImageDraw.Draw(img)
            else:
                draw_rr(draw, bar_x, row_y, bar_x+fill_w, row_y+BAR_H, BAR_H//2, lerp(cat_col,GRAY,0.55))
        sc_lbl = f"{s:.0f}"; slw, slh = tsize(draw, sc_lbl, fonts["small"])
        sx = (bar_x+fill_w-slw-12) if fill_w > slw+24 else (bar_x+fill_w+8)
        draw.text((sx, row_y+(BAR_H-slh)//2), sc_lbl, font=fonts["small"], fill=WHITE)

    # Engagement question
    q_y = cstart + 5*(BAR_H+BAR_GAP) + 30
    centered(draw, q_y, f"Are you watching ${ticker} today?", fonts["h3"], lerp(cat_col,WHITE,0.4))
    centered(draw, q_y+62, "Drop a comment below \u2193", fonts["body"], GRAY)

    swipe_hint(draw, fonts, 4)
    return img

# ── Slide 5: CTA ──────────────────────────────────────────────────────────────
def slide_5_cta(ticker, category, fonts):
    img = new_canvas((8,5,22),(5,4,14))
    draw = ImageDraw.Draw(img)
    cat_col = CAT_COLOR[category]

    for coords in [(0,0,W,16),(0,H-16,W,H),(0,0,16,H),(W-16,0,W,H)]:
        draw.rectangle(list(coords), fill=cat_col)

    # Bolt polygon
    bolt = [(430,80),(320,380),(375,380),(345,660),(560,330),(480,330),(525,80)]
    glow(img, W//2, 380, 270, lerp(BLUE,PURPLE,0.5))
    draw = ImageDraw.Draw(img)
    draw.polygon(bolt, fill=lerp(BLUE,PURPLE,0.45))

    fy = 710
    centered(draw, fy,      "FOLLOW FOR",  fonts["h2"], WHITE)
    centered(draw, fy+85,   "FREE PICKS",  fonts["h1"], cat_col)

    btn_y = fy + 190
    draw_rr(draw, 64, btn_y, W-64, btn_y+104, 22, (20,12,60))
    hbar(img, 66, btn_y+2, W-66, btn_y+102, BLUE, PURPLE)
    draw = ImageDraw.Draw(img)
    uw, _ = tsize(draw, "CATALYSTEDGE.AGENCY", fonts["tag"])
    draw.text(((W-uw)//2, btn_y+14), "CATALYSTEDGE.AGENCY", font=fonts["tag"], fill=WHITE)
    lw, _ = tsize(draw, "FREE DAILY NEWSLETTER", fonts["small"])
    draw.text(((W-lw)//2, btn_y+60), "FREE DAILY NEWSLETTER", font=fonts["small"], fill=lerp(WHITE,BLUE,0.3))

    centered(draw, btn_y+128, f"Today's pick: ${ticker}", fonts["h3"], cat_col)
    centered(draw, btn_y+185, "#SEC #fintwit #stocks #catalyst", fonts["small"], GRAY)

    swipe_hint(draw, fonts, 5)
    return img

# ── Data loaders ──────────────────────────────────────────────────────────────
def read_csv(path):
    if not path.exists(): return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception: return []

def load_pick():
    picks_data = {}
    pj = ROOT / "newsletter_picks.json"
    if pj.exists():
        picks_data = json.loads(pj.read_text())
    top = picks_data.get("top_pick", "")
    tickers = picks_data.get("top5_tickers", [])
    if not top and tickers: top = tickers[0]
    if not top: return None, {}, {}
    for cp in [ROOT/"sec_top_gappers.csv", ROOT/"sec_top_value.csv",
               ROOT/"sec_top_moat.csv", ROOT/"combined_priority.csv"]:
        for r in read_csv(cp):
            if r.get("ticker","").strip().upper() == top.upper():
                return top, r, picks_data
    return top, {}, picks_data

def get_category(row):
    gs = float(row.get("gapper_score",0) or 0)
    ms = float(row.get("moat_score",  0) or 0)
    vs = float(row.get("value_score", 0) or 0)
    if gs >= ms and gs >= vs and gs > 0: return "gapper"
    if ms >= vs and ms > 0: return "moat"
    return "value"

def clean_tags(s):
    if not s: return []
    return [t.lstrip("+").strip().title() for t in s.split(";") if t.strip().startswith("+")][:3]

def load_top5_scores(tickers):
    sm = {}
    for cp in [ROOT/"combined_priority.csv", ROOT/"sec_catalyst_ranked.csv",
               ROOT/"sec_top_gappers.csv", ROOT/"sec_top_value.csv", ROOT/"sec_top_moat.csv"]:
        for r in read_csv(cp):
            t = r.get("ticker","").strip().upper()
            if t and t not in sm:
                gs = float(r.get("gapper_score",0) or 0)
                vs = float(r.get("value_score", 0) or 0)
                ms = float(r.get("moat_score",  0) or 0)
                total = gs+vs+ms
                if total > 0: sm[t] = total
    return [(t, sm.get(t.upper(), 8.0)) for t in tickers]

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"generate_instagram_carousel date={TODAY}")

    if not HAS_PIL:
        print("ERROR: pip install Pillow")
        raise SystemExit(1)

    ticker, row, picks_data = load_pick()
    if not ticker:
        print("No pick data — skipping carousel")
        return

    category    = get_category(row)
    form        = row.get("form", "8-K")
    tags        = clean_tags(row.get("tags", ""))
    gs          = float(row.get("gapper_score",0) or 0)
    vs          = float(row.get("value_score", 0) or 0)
    ms          = float(row.get("moat_score",  0) or 0)
    total_score = gs + vs + ms
    scanned     = picks_data.get("total_combined", 0)
    top5        = load_top5_scores(picks_data.get("top5_tickers", [ticker]))

    print(f"  Pick: ${ticker}  category={category}  score={total_score:.0f}")

    fonts = load_fonts()
    slides = [
        ("hook",    slide_1_hook(ticker, category, scanned, fonts)),
        ("reveal",  slide_2_reveal(ticker, category, form, total_score, fonts)),
        ("signals", slide_3_signals(ticker, category, tags, fonts)),
        ("chart",   slide_4_chart(ticker, category, top5, picks_data, fonts)),
        ("cta",     slide_5_cta(ticker, category, fonts)),
    ]

    WIN_OUT.mkdir(parents=True, exist_ok=True)
    for i, (name, img) in enumerate(slides, 1):
        local_path = ROOT / f"instagram_carousel_{TODAY}_{i}.png"
        win_path   = WIN_OUT / f"instagram_carousel_{TODAY}_{i}.png"
        img.save(str(local_path))
        img.save(str(win_path))
        print(f"  Slide {i} ({name}) → {win_path}")

    # Write a manifest for post_to_instagram.cjs to find the carousel
    manifest = {
        "type": "carousel",
        "date": TODAY,
        "ticker": ticker,
        "slides": [
            str(WIN_OUT / f"instagram_carousel_{TODAY}_{i}.png")
            for i in range(1, len(slides)+1)
        ],
    }
    manifest_path = ROOT / "instagram_carousel_manifest.json"
    import json as _json
    manifest_path.write_text(_json.dumps(manifest, indent=2))
    print(f"  Manifest → {manifest_path}")
    print(f"  Done — {len(slides)} slides ready for Instagram carousel post")


if __name__ == "__main__":
    main()
