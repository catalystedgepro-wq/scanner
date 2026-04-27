#!/usr/bin/env python3
"""build_og_images.py — generate 1200×630 Open Graph PNG cards for major pages.

Output: /home/operator/.openclaw/workspace/docs/og/<slug>.png

Brand:
  - bg navy #04070d with cyan→gold radial gradient
  - top-left lightning bolt + "CATALYST · EDGE" wordmark
  - center-left page title (56pt cyan bold) + subtitle (26pt ink-dim)
  - bottom-right "● 89% audited hit rate" gold status pill
"""
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path("/home/operator/.openclaw/workspace/docs/og")
OUT_DIR.mkdir(parents=True, exist_ok=True)

W, H = 1200, 630
NAVY = (4, 7, 13)
INK = (230, 241, 255)
INK_DIM = (155, 176, 200)
INK_MUTE = (110, 129, 152)
CYAN = (90, 215, 255)
GOLD = (245, 198, 98)
BULL = (92, 242, 164)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
FONT_REG_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def load_font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    candidates = FONT_CANDIDATES if bold else FONT_REG_CANDIDATES
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def radial_gradient(size: tuple[int, int], center: tuple[int, int],
                    inner: tuple[int, int, int, int],
                    outer: tuple[int, int, int, int],
                    radius: int) -> Image.Image:
    """Draw a radial gradient by repeated alpha-falling ellipses."""
    layer = Image.new("RGBA", size, outer[:3] + (0,))
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    steps = 60
    for i in range(steps, 0, -1):
        r = int(radius * i / steps)
        # blend inner→outer
        t = 1.0 - (i / steps)
        rr = int(inner[0] * (1 - t) + outer[0] * t)
        gg = int(inner[1] * (1 - t) + outer[1] * t)
        bb = int(inner[2] * (1 - t) + outer[2] * t)
        aa = int(inner[3] * (1 - t) + outer[3] * t)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(rr, gg, bb, aa))
    return layer


def draw_bolt(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int = 30) -> None:
    """Lightning bolt polygon centered at (cx, cy)."""
    pts = [
        (cx + 4,  cy - r),
        (cx - r/1.4, cy + r/8),
        (cx - 2,  cy + r/8),
        (cx - 8,  cy + r),
        (cx + r/1.2, cy - r/6),
        (cx + 4,  cy - r/6),
    ]
    d.polygon(pts, fill=GOLD)


def make_card(slug: str, title: str, subtitle: str) -> Path:
    img = Image.new("RGB", (W, H), NAVY)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # Cyan glow upper-left
    overlay = Image.alpha_composite(
        overlay,
        radial_gradient((W, H), (260, 220), (90, 215, 255, 80), (4, 7, 13, 0), 600),
    )
    # Gold glow bottom-right
    overlay = Image.alpha_composite(
        overlay,
        radial_gradient((W, H), (1000, 480), (245, 198, 98, 70), (4, 7, 13, 0), 540),
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)

    # Top-left: bolt + wordmark
    draw_bolt(d, 80, 70, r=28)
    d.text((124, 50), "CATALYST · EDGE", fill=GOLD, font=load_font(22))
    d.text((124, 84), "SCANNER", fill=INK_MUTE, font=load_font(14))

    # Title (centered-left), wrap at ~22 chars per line
    title_font = load_font(64)
    sub_font = load_font(28, bold=False)

    # naive wrap on words
    def wrap(text: str, max_chars: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        cur = ""
        for w in words:
            cand = (cur + " " + w).strip()
            if len(cand) > max_chars and cur:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        if cur:
            lines.append(cur)
        return lines

    title_lines = wrap(title, 22)[:3]
    y = 220
    for line in title_lines:
        d.text((80, y), line, fill=CYAN, font=title_font)
        y += 78

    sub_lines = wrap(subtitle, 50)[:2]
    y += 14
    for line in sub_lines:
        d.text((80, y), line, fill=INK_DIM, font=sub_font)
        y += 38

    # Bottom-left: domain
    d.text((80, H - 70), "catalystedgescanner.com", fill=INK_MUTE, font=load_font(20))

    # Bottom-right: gold pill "● 89% audited hit rate"
    pill_text = "  89% audited hit rate"
    pill_font = load_font(20)
    pad_x, pad_y = 18, 12
    bbox = d.textbbox((0, 0), pill_text, font=pill_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pill_w = tw + pad_x * 2 + 14  # extra for the dot
    pill_h = th + pad_y * 2
    px = W - pill_w - 60
    py = H - pill_h - 60
    # background
    d.rounded_rectangle([px, py, px + pill_w, py + pill_h],
                        radius=pill_h // 2, fill=(245, 198, 98, 32),
                        outline=GOLD, width=2)
    # bull-dot (using bull color so it pops)
    dot_r = 7
    d.ellipse([px + pad_x - 2, py + pill_h // 2 - dot_r,
               px + pad_x - 2 + dot_r * 2, py + pill_h // 2 + dot_r],
              fill=BULL)
    d.text((px + pad_x + 22, py + pad_y - 2), "89% audited hit rate", fill=GOLD, font=pill_font)

    out = OUT_DIR / f"{slug}.png"
    img.save(out, "PNG", optimize=True)
    return out


TARGETS = [
    ("landing",         "Bloomberg killer",
                        "Audited 89% hit rate · 43 countries · $9-39/mo"),
    ("pricing",         "Pricing",
                        "Bloomberg $24K/yr → Catalyst Edge $108/yr · ROI calculator inside"),
    ("trust",           "We grade ourselves in public",
                        "50-row audit · methodology open · 89% hit rate"),
    ("benchmarks",      "vs Bloomberg, FactSet, Refinitiv",
                        "12-dimension head-to-head · honest table"),
    ("sdk",             "Catalyst Edge in 1 import",
                        "pip install catalyst-edge · npm install @catalyst-edge/sdk"),
    ("blog-why-we-publish",  "Why we publish our hit rate",
                             "Bloomberg never will. Here is why we do."),
    ("blog-cross-border",    "How the cross-border convergence score works",
                             "4-point composite signal · math + worked example"),
    ("blog-30-days",         "30 days to build a Bloomberg killer",
                             "Phase by phase. Misses included."),
]


def main() -> int:
    for slug, title, subtitle in TARGETS:
        path = make_card(slug, title, subtitle)
        print(f"  rendered {slug:24s} → {path}  ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
