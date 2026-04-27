#!/usr/bin/env python3
"""
generate_seedance_prompts.py — Cinematic video prompt generator for Seedance 2.0 / Higgsfield.

Reads pipeline data and generates platform-specific cinematic prompts
for TikTok, YouTube Shorts, Instagram Reels, and brand hero videos.

Pairs with voice audio from generate_voice_content.py.

Usage:
    python3 generate_seedance_prompts.py                # all platforms
    python3 generate_seedance_prompts.py --platform tiktok
    python3 generate_seedance_prompts.py --style cyberpunk
    python3 generate_seedance_prompts.py --list-styles

Output:
    social/seedance_tiktok_{date}.txt
    social/seedance_youtube_{date}.txt
    social/seedance_reels_{date}.txt
    social/seedance_hero_{date}.txt
"""

import json
import csv
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).parent
SOCIAL_DIR = WORKSPACE / "social"
PICKS_JSON = WORKSPACE / "newsletter_picks.json"
SQUEEZE_CSV = WORKSPACE / "squeeze_candidates.csv"
CONVERGENCE_CSV = WORKSPACE / "convergence_alerts.csv"

DATE_STR = datetime.now().strftime("%Y-%m-%d")
DATE_DISPLAY = datetime.now().strftime("%b %d, %Y")

STYLES = {
    "trading-floor": {
        "palette": "deep navy, electric gold, white terminal text",
        "mood": "high-stakes trading floor energy, precision, urgency",
        "texture": "dark surfaces with glowing data streams, glass reflections",
        "lighting": "practical neon: visible monitors casting blue-gold spill on subject. Hard shadows from multiple screens. Trading floor ambient.",
    },
    "cyberpunk": {
        "palette": "neon cyan, hot magenta, deep black, holographic purple",
        "mood": "futuristic intelligence network, data flows as light",
        "texture": "holographic overlays, particle systems, volumetric light through haze",
        "lighting": "neon lighting: visible neon signs cast colored spill. Flickering. Cool-blue and hot-pink. Cyberpunk fog.",
    },
    "dark-luxury": {
        "palette": "matte black, brushed gold, ivory text, subtle emerald accent",
        "mood": "exclusive intelligence briefing, institutional confidence",
        "texture": "matte surfaces, gold edge-lighting, minimal type on dark fields",
        "lighting": "chiaroscuro: 85% shadow, 15% illumination. Single directional light. Gold rim. Film noir wealth.",
    },
    "data-cascade": {
        "palette": "deep charcoal, electric green matrix, white highlights",
        "mood": "data waterfall, information overload distilled into signal",
        "texture": "falling data characters, code streams, terminal aesthetics",
        "lighting": "practical screen-glow: green-tinted light from data cascade illuminating face from below. Dark environment. Matrix atmosphere.",
    },
}

DEFAULT_STYLE = "trading-floor"


def load_picks():
    if not PICKS_JSON.exists():
        return {}
    try:
        return json.loads(PICKS_JSON.read_text())
    except Exception:
        return {}


def parse_csv(path):
    if not path.exists():
        return []
    lines = path.read_text().strip().split("\n")
    if len(lines) < 2:
        return []
    return list(csv.DictReader(lines))


def build_tiktok_prompt(picks, squeeze_rows, convergence_rows, style_key):
    """9:16 vertical, 10-15 seconds. 2-second hook → data reveal → CTA."""
    style = STYLES[style_key]
    total = picks.get("total_combined", 243)
    top5 = picks.get("top5_tickers", [])[:3]
    g = int(picks.get("gapper_count", 0))
    v = int(picks.get("value_count", 0))
    top_pick = picks.get("top_pick", "")
    coiled = [r for r in squeeze_rows if r.get("stage") in ("COILED", "IGNITION")][:2]
    conv = [r for r in convergence_rows if r.get("conviction_level") in ("HIGH", "ELEVATED")][:1]

    ticker_display = ", ".join(top5) if top5 else "AB, BE, AAOI"
    squeeze_line = ""
    if coiled:
        t = coiled[0].get("ticker", "")
        si = coiled[0].get("short_pct_float", "")
        squeeze_line = f"Squeeze alert ticker '{t}' glows red-hot with '{si}% SI' label."

    conv_line = ""
    if conv:
        t = conv[0].get("ticker", "")
        s = conv[0].get("convergence_score", "")
        signals = conv[0].get("signals_fired", "").replace(";", " + ")
        conv_line = f"Convergence badge appears for '{t}': signal icons ({signals}) stack vertically, score '{s}' pulses."

    return f"""SEEDANCE 2.0 — TIKTOK / REELS (9:16 vertical, 10-15s)
Platform: TikTok, Instagram Reels
Audio: @material[voice_hook] (pair with social/voice_hook_{DATE_STR}.mp3)
Style: {style_key}
Palette: {style['palette']}

---

HOOK (0-2s):
Black screen. Complete silence for 0.8 seconds.
At 0.8s — explosive burst of {style['palette'].split(',')[1].strip()} light from center of frame.
Camera snaps to extreme close-up of a single stock ticker character filling 80% of frame: "{top_pick}".
Typography: sharp sans-serif, {style['palette'].split(',')[0].strip()} background.
{style['lighting']}
Lens flare blooms across center. Motion blur trails at edges.
Audio sync: beat drop at 0.8s marker.

DATA CASCADE (2-5s):
Camera pulls back 15 feet over 2 seconds revealing a wall of scrolling SEC filing data.
{total} filing count number cascades down from top of frame in {style['palette'].split(',')[1].strip()} digits.
Filings scroll like a matrix waterfall behind the main counter.
Text overlay appears bottom-center: "SEC FILINGS SCANNED" in clean sans-serif.
{style['texture']}
Shallow depth of field: background data blurs, foreground numbers sharp.

TOP PICKS REVEAL (5-8s):
Three ticker cards snap into frame from left, staggered 0.3s apart: {ticker_display}.
Each card: dark glass surface with {style['palette'].split(',')[1].strip()} border glow.
Category badges underneath: "{g} Gappers · {v} Deep Value" in small caps.
{squeeze_line}
Camera pushes in slowly toward the cards (dolly forward 2 feet over 2 seconds).

{conv_line}

CTA (8-12s):
All data elements blur. Single text line fades in center:
"catalystedge.agency" in {style['palette'].split(',')[1].strip()}, large, breathing glow animation.
Below: "Free daily scan · Link in bio" in small white text.
Below that: "Not financial advice" in 60% opacity small text.
Camera holds steady. Slight vignette darkens edges.
End card: 2 seconds of clean URL on dark background.
"""


def build_youtube_prompt(picks, squeeze_rows, convergence_rows, style_key):
    """9:16 vertical, 15 seconds. Slightly more educational, data-rich."""
    style = STYLES[style_key]
    total = picks.get("total_combined", 243)
    top5 = picks.get("top5_tickers", [])[:5]
    g = int(picks.get("gapper_count", 0))
    v = int(picks.get("value_count", 0))
    m = int(picks.get("moat_count", 0))
    coiled = [r for r in squeeze_rows if r.get("stage") in ("COILED", "IGNITION")][:3]
    conv = [r for r in convergence_rows if r.get("conviction_level") in ("HIGH", "ELEVATED")][:2]

    ticker_display = ", ".join(top5) if top5 else "AB, BE, AAOI, BSAC, AEHR"

    squeeze_block = ""
    if coiled:
        items = []
        for r in coiled:
            t = r.get("ticker", "?")
            si = r.get("short_pct_float", "?")
            items.append(f"'{t}' card with short interest bar filling to {si}%")
        squeeze_block = f"""
SQUEEZE RADAR (7-10s):
Screen wipes to dark background. Header: "SQUEEZE RADAR" in red-orange with pulse animation.
Horizontal bar chart slides in from right:
{chr(10).join(f"  - {item}" for item in items)}
Bars animate from 0% to their values over 1.5 seconds.
Camera: static, locked-off. Clean data visualization.
Atmosphere: {style['mood']}
"""

    conv_block = ""
    if conv:
        r = conv[0]
        t = r.get("ticker", "?")
        signals = r.get("signals_fired", "").replace(";", ", ")
        score = r.get("convergence_score", "?")
        conv_block = f"""
CONVERGENCE (10-12s):
Badge overlay: "{t}" in center with radiating signal lines.
Signal labels orbit around ticker: {signals}.
Score counter animates from 0 to {score} in bottom-right corner.
{style['lighting']}
"""

    return f"""SEEDANCE 2.0 — YOUTUBE SHORTS (9:16 vertical, 15s)
Platform: YouTube Shorts
Audio: @material[voice_daily] (pair with social/voice_daily_{DATE_STR}.mp3)
Style: {style_key}
Palette: {style['palette']}

---

ESTABLISHING SHOT (0-2s):
Bird's eye view of a data visualization landscape — geometric grid of glowing nodes representing {total} SEC filings.
Camera positioned 40 feet above, looking straight down. Nodes pulse with {style['palette'].split(',')[1].strip()} light.
At 0.5s, camera begins crane descent toward the grid.
{style['lighting']}
Film grain: subtle 35mm texture in shadow areas. Cinematic.

SCAN RESULTS (2-5s):
Camera completes descent, settling at eye-level with the data grid.
Rack focus from background grid to foreground display panel.
Panel shows: "{DATE_DISPLAY} — CATALYST SCAN" header.
Below: "{g} Gappers · {v} Deep Value · {m} Wide Moat" in three columns.
Numbers animate from 0 to their values.
{style['texture']}

TOP PICKS (5-7s):
Five ticker cards materialize from particle effects, arranged in slight arc:
{ticker_display}
Each card: glass-morphism surface with frosted edges, {style['palette'].split(',')[1].strip()} accent line.
Cards stagger in 0.2s apart. Camera slow push-in (1 foot over 2 seconds).
Shallow depth of field: f/1.4 cinema equivalent. Nearest card sharp, farthest slightly soft.
{squeeze_block}
{conv_block}

END CARD (13-15s):
All elements dissolve to particles flowing toward center.
Particles coalesce into "catalystedge.agency" text.
Subtle breathing glow on the URL. Clean dark background.
"Subscribe for daily scans" below URL in small text.
"Not financial advice" in 50% opacity at bottom.
Camera: locked-off, slight vignette. 2-second hold.
"""


def build_reels_prompt(picks, squeeze_rows, convergence_rows, style_key):
    """9:16 vertical, 10 seconds. Fast-paced, visual-first for Instagram."""
    style = STYLES[style_key]
    total = picks.get("total_combined", 243)
    top5 = picks.get("top5_tickers", [])[:3]
    g = int(picks.get("gapper_count", 0))
    coiled = [r for r in squeeze_rows if r.get("stage") in ("COILED", "IGNITION")][:1]

    ticker_display = ", ".join(top5) if top5 else "AB, BE, AAOI"

    squeeze_flash = ""
    if coiled:
        t = coiled[0].get("ticker", "?")
        si = coiled[0].get("short_pct_float", "?")
        squeeze_flash = f"""At 6s: red flash frame (0.1s). "{t}" appears in large bold text.
Below: "{si}% Short Interest" with red underline.
Text shakes subtly (2px vibration, 4Hz) for urgency."""

    return f"""SEEDANCE 2.0 — INSTAGRAM REELS (9:16 vertical, 10s)
Platform: Instagram Reels
Audio: @material[voice_hook] (pair with social/voice_hook_{DATE_STR}.mp3)
Style: {style_key}
Palette: {style['palette']}

---

DISORIENTING OPEN (0-1.5s):
Camera rotates 90 degrees clockwise over 1 second. Tilted horizon.
Frame shows an abstract data visualization: concentric circles of {style['palette'].split(',')[1].strip()} light pulses.
Each ring represents a filing category. Center ring brightest.
{style['lighting']}
At 1s: camera snaps level. Stabilization creates satisfying visual pop.

NUMBER SLAM (1.5-3.5s):
"{total}" slams into frame center from top — large, bold, {style['palette'].split(',')[1].strip()}.
Below it: "SEC FILINGS" types in character by character (typewriter effect, 0.05s per char).
Background: subtle data cascade behind the number, barely visible through blur.
Quick zoom: camera pushes in 3 feet in 0.5 seconds toward the number.

TICKER FLASH (3.5-6s):
Three tickers flash in rapid succession, each held for 0.4 seconds:
Frame 1: "{top5[0] if len(top5) > 0 else 'AB'}" — white on dark, off-center left
Frame 2: "{top5[1] if len(top5) > 1 else 'BE'}" — {style['palette'].split(',')[1].strip()} on dark, center
Frame 3: "{top5[2] if len(top5) > 2 else 'AAOI'}" — white on dark, off-center right
Each transition: whip-pan right (0.1s motion blur between).
Category badge: "{g} Gappers Found" fades in at bottom during last ticker.

SQUEEZE FLASH (6-7.5s):
{squeeze_flash if squeeze_flash else "Particle burst from center — gold sparks radiate outward. 'CATALYST DETECTED' text appears for 1.5 seconds."}

CTA (7.5-10s):
Extreme depth of field rack focus: foreground blur clears to reveal URL.
"catalystedge.agency" centered, clean, {style['palette'].split(',')[1].strip()} glow.
"Follow for daily scans" appears below with subtle fade-in.
"Not financial advice" at bottom in small, 50% opacity text.
Hold for 2.5 seconds. Slight vignette. End.
"""


def build_hero_prompt(picks, squeeze_rows, convergence_rows, style_key):
    """16:9 horizontal, 15 seconds. Brand hero for website/landing page."""
    style = STYLES[style_key]
    total = picks.get("total_combined", 243)
    top5 = picks.get("top5_tickers", [])[:5]
    g = int(picks.get("gapper_count", 0))
    v = int(picks.get("value_count", 0))
    m = int(picks.get("moat_count", 0))

    ticker_display = ", ".join(top5) if top5 else "AB, BE, AAOI, BSAC, AEHR"

    return f"""SEEDANCE 2.0 — BRAND HERO (16:9 horizontal, 15s)
Platform: Website hero, YouTube banner, LinkedIn
Audio: @material[voice_daily] or ambient electronic score
Style: {style_key}
Palette: {style['palette']}

---

WIDE ESTABLISHING (0-3s):
Extreme wide shot: vast dark space with a single point of {style['palette'].split(',')[1].strip()} light at center.
Scale impossibility: tiny human figure (silhouette) standing before an impossibly vast data visualization wall.
The wall stretches beyond frame edges — {total} nodes of light in geometric grid patterns.
Volumetric light beams: light passes through particle-filled atmosphere creating visible rays.
Dust motes visible in light shafts. Spiritual, otherworldly mood.
Camera: locked-off establishing shot. 3-second hold. Viewer absorbs scale.
{style['lighting']}

APPROACH (3-6s):
Camera dollies forward 20 feet over 3 seconds toward the data wall.
Parallax: foreground particles drift slowly, mid-ground data nodes at medium speed, background wall stationary.
As camera approaches, individual filing nodes become readable — tiny text labels appear.
The grid resolves into organized sections: Gappers ({g}), Deep Value ({v}), Wide Moat ({m}).
Color temperature shifts from cool blue to warm {style['palette'].split(',')[1].strip()} as we approach the data.
Film grain visible. Cinematic 2.39:1 aspect ratio feel within 16:9 frame (letterboxing optional).

DATA EXTRACTION (6-10s):
Camera settles at arm's length from the wall. Rack focus to sharp foreground.
Five nodes brighten and detach from the wall, floating toward camera:
{ticker_display}
Each node transforms into a glass card with ticker, category badge, and score.
Cards arrange in slight perspective arc — nearest card largest, edges receding.
{style['texture']}
Handheld micro-vibrations (1mm jitter) add organic feel to locked-off framing.

BRAND RESOLVE (10-15s):
Cards dissolve into particle streams flowing rightward off-frame.
Camera pulls back (reverse dolly, 10 feet over 3 seconds).
The data wall reconfigures: all {total} nodes rearrange to spell "CATALYST EDGE" in large formation.
Letters hold for 2 seconds — each letter composed of dozens of glowing filing nodes.
Below the title: "catalystedge.agency" fades in. Clean. Minimal.
"Daily SEC Catalyst Intelligence · Free Scanner" in small type below URL.
Final 1-second hold. Vignette darkens edges. {style['mood']}.
"""


def main():
    args = set(sys.argv[1:])

    if "--list-styles" in args:
        print("Available styles:")
        for key, val in STYLES.items():
            print(f"  {key}: {val['mood']}")
        return

    style_key = DEFAULT_STYLE
    platform_filter = None

    for arg in list(args):
        if arg.startswith("--style="):
            style_key = arg.split("=")[1]
        elif arg.startswith("--platform="):
            platform_filter = arg.split("=")[1]
        elif arg == "--style" and len(sys.argv) > sys.argv.index(arg) + 1:
            style_key = sys.argv[sys.argv.index(arg) + 1]
        elif arg == "--platform" and len(sys.argv) > sys.argv.index(arg) + 1:
            platform_filter = sys.argv[sys.argv.index(arg) + 1]

    if style_key not in STYLES:
        print(f"Unknown style '{style_key}'. Available: {', '.join(STYLES.keys())}")
        sys.exit(1)

    SOCIAL_DIR.mkdir(exist_ok=True)

    picks = load_picks()
    squeeze_rows = parse_csv(SQUEEZE_CSV)
    convergence_rows = parse_csv(CONVERGENCE_CSV)

    generators = {
        "tiktok": ("seedance_tiktok", build_tiktok_prompt),
        "youtube": ("seedance_youtube", build_youtube_prompt),
        "reels": ("seedance_reels", build_reels_prompt),
        "hero": ("seedance_hero", build_hero_prompt),
    }

    for platform, (prefix, gen_fn) in generators.items():
        if platform_filter and platform != platform_filter:
            continue

        prompt = gen_fn(picks, squeeze_rows, convergence_rows, style_key)
        path = SOCIAL_DIR / f"{prefix}_{DATE_STR}.txt"
        path.write_text(prompt)
        print(f"Generated: {path.name} ({len(prompt)} chars)")

    print(f"\nStyle: {style_key}")
    print(f"Pair audio from: social/voice_hook_{DATE_STR}.mp3 (TikTok/Reels)")
    print(f"                 social/voice_daily_{DATE_STR}.mp3 (YouTube/Hero)")
    print(f"\nCopy prompt text into Seedance 2.0 on Higgsfield.")
    print(f"Upload matching audio as @material reference.")


if __name__ == "__main__":
    main()
