#!/usr/bin/env python3
"""generate_whale_video.py — Contrarian Whale explainer video for Catalyst Edge.

Same full-anchor layout as generate_anchor_video.py:
  • 1080×1920 portrait (Shorts / TikTok / Reels)
  • Avatar face in circular zone, studio background
  • Branding bar at top, whale info panel at bottom
  • ElevenLabs Lily voice (or edge-tts Libby fallback)
  • Replicate Wav2Lip lip-sync (or static avatar fallback)
  • Karaoke captions + music bed via ffmpeg

Fixed content — not data-driven. The script explains the
Contrarian Whale signal: what it is, where to find it, how to use it.

Setup:
  1.  pip install --break-system-packages edge-tts Pillow
  2.  Add ELEVENLABS_API_KEY / REPLICATE_API_KEY to .sec_email_env
  3.  Avatar images in workspace/avatars/ (same as anchor video)
  4.  Run: python3 generate_whale_video.py

Output:
  workspace/social/whale_explainer.mp4
  Desktop/catalyst-edge/social/whale_explainer.mp4
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
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

ROOT       = Path(__file__).parent
WIN_OUT    = ROOT / "social"
AVATAR_DIR = ROOT / "avatars"
DOW        = datetime.date.today().strftime("%a").lower()

W, H   = 1080, 1920
FPS    = 30
VOICE_EDGE         = "en-GB-LibbyNeural"
ELEVENLABS_VOICE_ID = "pFZP5JQG7iQjIQuC4Bku"   # Lily — British, confident

# ── Colours ───────────────────────────────────────────────────────────────────
DARK_BG    = (6,   8,  20)
CARD_BG    = (14, 18,  42)
BLUE       = (59, 130, 246)
PURPLE     = (139, 92, 246)
TEAL       = (20, 184, 166)
GREEN      = (63, 185, 128)
WHITE      = (255, 255, 255)
GRAY       = (110, 130, 165)
LIGHT_GRAY = (190, 205, 225)
WHALE_COL  = (63, 185, 128)      # the signature whale green
WHALE_BG   = (8,  35,  24)
WARN_RED   = (210, 35,  35)
WARN_BG    = (38,   8,   8)

# ── Narration script (≈75 seconds at ~2.3 words/second) ──────────────────────
WHALE_SCRIPT = (
    "Most traders run from bad news filings. "
    "Contrarian Whales run toward them. And that is exactly what this signal tracks. "

    "A Contrarian Whale fires when our scanner detects two or more insider filings — "
    "Form 4s — at the same company, on the same day a negative tag is present. "
    "Think: a dilutive offering, a default notice, or a going-concern warning. "
    "Insiders are required by the SEC to disclose every transaction. "
    "When they keep filing — and buying — despite bad news, that is not noise. "
    "That is conviction. "

    "On the Catalyst Edge scanner, scroll to the Insider Filing Clusters table. "
    "Any ticker with the whale badge is your signal. "
    "Hover over it and you will see the exact details — "
    "how many insiders filed, and what the negative tag was. "
    "In this example: five insider filings despite a default notice. "
    "That is institutions accumulating before a potential restructuring catalyst. "

    "The Contrarian Whale is not a buy signal. It is a watch signal. "
    "Add the ticker to your watchlist, pull the SEC filing directly from EDGAR, "
    "and ask: is management buying shares into a fixable problem — or a fatal one? "
    "Restructurings, asset sales, debt renegotiations — "
    "these are the events where informed insiders front-run the market. "
    "Your job is to find them before the news breaks. "

    "The Contrarian Whale runs every morning before 4 AM — "
    "automatically, across three hundred filings. "
    "It is live now at Catalyst Edge scanner dot com. "
    "Free. No login. Check the link in the description."
)

# ── Font loading ──────────────────────────────────────────────────────────────
def load_fonts() -> dict:
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
        "giant":  f(bold, 110), "h1":    f(bold,  78),
        "h2":     f(bold,  56), "h3":    f(bold,  42),
        "body":   f(reg,   36), "small": f(reg,   28),
        "tag":    f(bold,  32), "brand": f(bold,  44),
        "score":  f(bold,  88),
    }

# ── Drawing helpers ───────────────────────────────────────────────────────────
def lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i]*(1-t) + c2[i]*t) for i in range(3))

def lerp_a(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i]*(1-t) + c2[i]*t) for i in range(len(c1)))

def draw_rr(draw, x1, y1, x2, y2, r, fill, outline=None, ow=0):
    try:
        draw.rounded_rectangle([x1,y1,x2,y2], radius=r, fill=fill, outline=outline, width=ow)
    except TypeError:
        draw.rounded_rectangle([x1,y1,x2,y2], radius=r, fill=fill)

def tsize(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2]-bb[0], bb[3]-bb[1]

def shadow(draw, xy, text, font, fill, d=3):
    draw.text((xy[0]+d, xy[1]+d), text, font=font, fill=(*fill[:3], 150))
    draw.text(xy, text, font=font, fill=fill)

def centered(draw, y, text, font, fill, w=W, shad=True):
    tw, _ = tsize(draw, text, font)
    x = (w - tw) // 2
    if shad:
        draw.text((x+3, y+3), text, font=font,
                  fill=(*fill[:3], 140) if len(fill) > 3 else (0,0,0,140))
    draw.text((x, y), text, font=font, fill=fill)

def hbar_rgba(img, x1, y1, x2, y2, c1, c2):
    draw = ImageDraw.Draw(img)
    span = max(1, x2-x1)
    step = max(1, span // 150)
    for x in range(x1, x2, step):
        col = lerp_a(c1, c2, (x-x1)/span)
        draw.rectangle([x, y1, min(x+step, x2), y2], fill=col)

# ── Studio background ─────────────────────────────────────────────────────────
def make_background(fonts) -> Image.Image:
    """1080×1920 dark studio background."""
    img  = Image.new("RGB", (W, H), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Radial vignette
    for y in range(0, H, 4):
        for x in range(0, W, 4):
            dx = (x - W/2) / (W/2)
            dy = (y - H/2) / (H/2)
            dist = min(1.0, (dx*dx + dy*dy) ** 0.5)
            brightness = int(30 * (1 - dist * 0.7))
            c = (max(0, DARK_BG[0] + brightness),
                 max(0, DARK_BG[1] + brightness),
                 max(0, DARK_BG[2] + brightness + 10))
            draw.rectangle([x, y, x+3, y+3], fill=c)

    # Scan-lines
    for y in range(0, H, 6):
        draw.line([(0, y), (W, y)], fill=(255, 255, 255, 8), width=1)

    # Faint grid
    for x in range(0, W, 120):
        draw.line([(x, 0), (x, H)], fill=(*GREEN, 10))
    for y in range(0, H, 120):
        draw.line([(0, y), (W, y)], fill=(*GREEN, 10))

    # Glow behind avatar zone
    for r in range(320, 0, -4):
        alpha = int(18 * (1 - r/320))
        x0 = W//2 - r; y0 = H//2 - r
        draw.ellipse([x0, y0, x0+r*2, y0+r*2],
                     fill=(*lerp(DARK_BG, GREEN, 0.14), alpha))

    # Accent line below top bar
    draw.line([(0, 115), (W, 115)], fill=(*GREEN, 80), width=2)
    return img

# ── Top branding bar ──────────────────────────────────────────────────────────
def make_top_bar(fonts) -> Image.Image:
    """1080×115 RGBA branding bar — whale edition."""
    img  = Image.new("RGBA", (W, 115), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark gradient
    for y in range(115):
        alpha = int(220 * (1 - y/115))
        draw.line([(0, y), (W-1, y)], fill=(*DARK_BG, alpha))

    # Top stripe — whale green instead of red
    draw.rectangle([0, 0, W, 52], fill=(*WHALE_BG, 230))
    draw.rectangle([0, 0, W, 52], fill=(*GREEN, 30))
    centered(draw, 10, "CONTRARIAN WHALE  —  SEC INSIDER SIGNAL", fonts["small"], WHITE)

    # Brand
    draw.text((44, 60), "CATALYST EDGE", font=fonts["brand"],
              fill=(*lerp(GREEN, WHITE, 0.5), 255))
    label = "CATALYSTEDGESCANNER.COM"
    dw, _ = tsize(draw, label, fonts["small"])
    draw.text((W - dw - 44, 68), label, font=fonts["small"], fill=(*GRAY, 200))
    return img

# ── Whale info panel ──────────────────────────────────────────────────────────
def make_whale_panel(fonts) -> Image.Image:
    """1080×680 RGBA whale explainer panel — sits at the bottom of the frame."""
    PH  = 680
    PAD = 50
    img  = Image.new("RGBA", (W, PH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient — transparent top → opaque bottom
    for y in range(PH):
        alpha = int(240 * (y/PH) ** 0.5)
        draw.line([(0, y), (W-1, y)], fill=(*DARK_BG, alpha))

    # ── Section header pill ───────────────────────────────────────────────────
    pill_text = "CONTRARIAN WHALE  🐋"
    pw, _ = tsize(draw, pill_text, fonts["tag"])
    px1 = (W - pw - 56) // 2; px2 = px1 + pw + 56
    draw_rr(draw, px1, 14, px2, 66, 26,
            (*WHALE_BG, 220), (*GREEN, 255), 2)
    centered(draw, 24, pill_text, fonts["tag"], (*GREEN, 255))

    # ── Signal trigger line ───────────────────────────────────────────────────
    centered(draw, 82, "2+ INSIDER FORM 4s  +  NEGATIVE SEC TAG", fonts["small"],
             (*LIGHT_GRAY, 220))

    # ── Three feature cards ───────────────────────────────────────────────────
    cards = [
        ("DILUTION\nWARNING",   GREEN,  WHALE_BG),
        ("DEFAULT\nNOTICE",     PURPLE, (20, 10, 50)),
        ("GOING\nCONCERN",      TEAL,   (6, 28, 32)),
    ]
    card_w = (W - PAD*2 - 20) // 3
    cx = PAD
    for label, col, bg in cards:
        draw_rr(draw, cx, 126, cx + card_w, 222, 14, (*bg, 200), (*col, 180), 1)
        lines = label.split("\n")
        ly = 140
        for ln in lines:
            lw, lh = tsize(draw, ln, fonts["small"])
            draw.text((cx + (card_w - lw)//2, ly), ln, font=fonts["small"],
                      fill=(*col, 240))
            ly += lh + 4
        cx += card_w + 10

    # ── Divider ───────────────────────────────────────────────────────────────
    draw.line([(PAD, 234), (W-PAD, 234)], fill=(*GREEN, 60), width=1)

    # ── How it works — 3-step list ────────────────────────────────────────────
    steps = [
        ("①", "Scanner detects 2+ Form 4s at same company on same day"),
        ("②", "Cross-checks for negative tag: dilution, default, going concern"),
        ("③", "Flags ticker with 🐋 badge in Insider Clusters table"),
    ]
    sy = 248
    for icon, text in steps:
        # Icon badge
        iw, ih = tsize(draw, icon, fonts["tag"])
        draw_rr(draw, PAD, sy, PAD + iw + 20, sy + ih + 12, 10,
                (*WHALE_BG, 200), (*GREEN, 160), 1)
        draw.text((PAD + 10, sy + 6), icon, font=fonts["tag"], fill=(*GREEN, 255))
        # Step text (wrap at ~55 chars)
        tx = PAD + iw + 36
        tw, th = tsize(draw, text, fonts["small"])
        draw.text((tx, sy + (ih + 12 - th)//2 + 2), text,
                  font=fonts["small"], fill=(*LIGHT_GRAY, 220))
        sy += ih + 28

    # ── Conviction quote ──────────────────────────────────────────────────────
    draw.line([(PAD, sy + 6), (W-PAD, sy + 6)], fill=(*GREEN, 50), width=1)
    sy += 18
    quote = '"Insiders filing despite bad news — that is conviction."'
    qw, qh = tsize(draw, quote, fonts["small"])
    if qw <= W - PAD*2:
        draw.text(((W - qw)//2, sy), quote, font=fonts["small"],
                  fill=(*lerp(GREEN, WHITE, 0.6), 200))
        sy += qh + 18
    else:
        # split at em-dash
        parts = ['"Insiders filing despite bad news —', 'that is conviction."']
        for part in parts:
            pw2, ph2 = tsize(draw, part, fonts["small"])
            draw.text(((W - pw2)//2, sy), part, font=fonts["small"],
                      fill=(*lerp(GREEN, WHITE, 0.6), 200))
            sy += ph2 + 6
        sy += 12

    # ── CTA footer ────────────────────────────────────────────────────────────
    footer_y = PH - 72
    draw.line([(PAD, footer_y), (W-PAD, footer_y)], fill=(*GREEN, 100), width=2)
    centered(draw, footer_y + 10,
             "CATALYSTEDGESCANNER.COM  |  FREE  |  UPDATED 4 AM DAILY",
             fonts["small"], (*lerp(GREEN, WHITE, 0.5), 230))
    centered(draw, footer_y + 44,
             "Not financial advice. For informational purposes only.",
             fonts["small"], (100, 110, 130, 190))

    return img

# ── Avatar helpers ────────────────────────────────────────────────────────────
def pick_avatar() -> Path | None:
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    day_file = AVATAR_DIR / f"avatar_{DOW}.png"
    if day_file.exists(): return day_file
    day_index = datetime.date.today().weekday() + 1
    for n in [day_index, 1]:
        p = AVATAR_DIR / f"avatar_{n}.png"
        if p.exists(): return p
    generic = AVATAR_DIR / "avatar.png"
    if generic.exists(): return generic
    return None

def make_circle_mask(size: int, out: Path):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size-1, size-1], fill=255)
    mask.save(str(out))

def make_avatar_overlay(fonts) -> "Image.Image | None":
    avatar_path = pick_avatar()
    if avatar_path is None:
        for ext in ("avatar.jpg", "avatar.jpeg"):
            p = AVATAR_DIR / ext
            if p.exists():
                avatar_path = p
                break
    if avatar_path is None:
        print("  No avatar found — skipping avatar overlay")
        return None
    try:
        av = Image.open(str(avatar_path)).convert("RGBA")
    except Exception as e:
        print(f"  Could not open avatar ({e}) — skipping overlay")
        return None

    aw, ah = av.size
    side = min(aw, ah)
    av = av.crop(((aw-side)//2, (ah-side)//2, (aw-side)//2+side, (ah-side)//2+side))

    panel_top = H - 680
    zone_h    = panel_top - 115
    circle_d  = min(820, int(zone_h * 0.84))
    av = av.resize((circle_d, circle_d), Image.LANCZOS)

    mask = Image.new("L", (circle_d, circle_d), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, circle_d-1, circle_d-1], fill=255)
    av.putalpha(mask)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)
    cx      = (W - circle_d) // 2
    cy      = 115 + zone_h//2 - circle_d//2

    # Glow rings — whale green palette
    for i, (col, alpha, thick) in enumerate([
        (WHALE_BG, 50,  34),
        (lerp(GREEN, TEAL, 0.4), 90, 22),
        (GREEN, 160, 12),
        (WHITE,  80,  4),
    ]):
        draw.ellipse([cx - 6 - i*12, cy - 6 - i*12,
                      cx + circle_d + 6 + i*12, cy + circle_d + 6 + i*12],
                     outline=(*col, alpha), width=thick)

    overlay.paste(av, (cx, cy), av)
    label_y = cy + circle_d + 16
    if label_y + 36 < panel_top:
        centered(draw, label_y, "CATALYST EDGE  AI ANCHOR", fonts["small"], (*GRAY, 200))
    return overlay

def make_avatar_ring_only(fonts, circle_d: int) -> "Image.Image":
    panel_top = H - 680
    zone_h    = panel_top - 115
    overlay   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw      = ImageDraw.Draw(overlay)
    cx        = W // 2
    cy_centre = 115 + zone_h // 2
    cy_top    = cy_centre - circle_d // 2

    for i, (col, alpha, thick) in enumerate([
        (WHALE_BG, 50,  34),
        (lerp(GREEN, TEAL, 0.4), 90, 22),
        (GREEN, 160, 12),
        (WHITE,  80,  4),
    ]):
        r = circle_d // 2 + 6 + i * 12
        draw.ellipse([cx - r, cy_centre - r, cx + r, cy_centre + r],
                     outline=(*col, alpha), width=thick)

    label_y = cy_top + circle_d + 16
    if label_y + 36 < panel_top:
        centered(draw, label_y, "CATALYST EDGE  AI ANCHOR", fonts["small"], (*GRAY, 200))
    return overlay

# ── D-ID helpers (identical to anchor video) ─────────────────────────────────
def _did_auth(api_key: str) -> str:
    return "Basic " + base64.b64encode(f"{api_key}:".encode()).decode()

def _did_request(method, endpoint, api_key, data=None, content_type="application/json"):
    url = f"https://api.d-id.com{endpoint}"
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": _did_auth(api_key),
        "Content-Type":  content_type,
        "Accept":        "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"D-ID {method} {endpoint} → HTTP {e.code}: {body[:400]}")

def _upload_multipart(endpoint, api_key, field, file_path, mime):
    boundary = f"----CatalystEdge{int(time.time())}"
    with open(file_path, "rb") as fh:
        file_bytes = fh.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{file_path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()
    result = _did_request("POST", endpoint, api_key, data=body,
                          content_type=f"multipart/form-data; boundary={boundary}")
    return result.get("url") or result.get("id") or ""

def did_upload_image(path: Path, api_key: str) -> str:
    print("    Uploading avatar image to D-ID...")
    url = _upload_multipart("/images/uploads", api_key, "image", path, "image/png")
    print(f"    Image uploaded: {url[:60]}...")
    return url

def did_create_talk(source_url, script_text, api_key):
    payload = json.dumps({
        "source_url": source_url,
        "script": {
            "type": "text",
            "input": script_text,
            "provider": {"type": "microsoft", "voice_id": "en-GB-LibbyNeural"},
        },
        "config": {"result_format": "mp4", "stitch": True},
    }).encode()
    result = _did_request("POST", "/talks", api_key, data=payload)
    return result["id"], "/talks"

def did_poll(job_id, endpoint, api_key, timeout=420):
    print(f"    Polling {endpoint}/{job_id}...", end=" ", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _did_request("GET", f"{endpoint}/{job_id}", api_key)
        status = result.get("status", "")
        if status == "done":
            url = result.get("result_url", "")
            print(f"done → {url[:60]}...")
            return url
        if status == "error":
            raise RuntimeError(f"D-ID job failed: {result.get('error', result)}")
        print(".", end="", flush=True)
        time.sleep(10)
    raise TimeoutError(f"D-ID timed out after {timeout}s")

def did_download_video(url, dest):
    print("    Downloading talking-head video...")
    urllib.request.urlretrieve(url, str(dest))
    print(f"    Downloaded: {dest.stat().st_size / 1e6:.1f} MB")

# ── Replicate Wav2Lip ─────────────────────────────────────────────────────────
def replicate_wav2lip(face_path: Path, audio_path: Path,
                      api_key: str, out_path: Path) -> bool:
    print("  Encoding inputs for Replicate...")
    face_mime  = "image/jpeg" if face_path.suffix.lower() in (".jpg",".jpeg") else "image/png"
    audio_mime = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
    face_b64   = base64.b64encode(face_path.read_bytes()).decode()
    audio_b64  = base64.b64encode(audio_path.read_bytes()).decode()

    WAVLIP_VERSION = "8d65e3f4f4298520e079198b493c25adfc43c058ffec924f2aefc8010ed25eef"
    payload = json.dumps({
        "version": WAVLIP_VERSION,
        "input": {
            "face":          f"data:{face_mime};base64,{face_b64}",
            "audio":         f"data:{audio_mime};base64,{audio_b64}",
            "fps": 25, "pads": "0 10 0 0", "smooth": True, "resize_factor": 1,
        }
    }).encode()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "Prefer":        "wait",
    }
    req = urllib.request.Request(
        "https://api.replicate.com/v1/predictions",
        data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        print(f"  Replicate POST error: {e}")
        return False

    pred_id = result.get("id", "")
    status  = result.get("status", "")
    print(f"  Prediction id={pred_id} status={status}")

    deadline = time.time() + 600
    while status not in ("succeeded","failed","canceled") and time.time() < deadline:
        time.sleep(8)
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    f"https://api.replicate.com/v1/predictions/{pred_id}",
                    headers={"Authorization": f"Bearer {api_key}"}),
                timeout=30) as r:
                result = json.loads(r.read())
            status = result.get("status", "")
            print(f"    ... {status}")
        except Exception as e:
            print(f"    poll error: {e}")

    if status != "succeeded":
        print(f"  Replicate failed: {status}")
        return False

    output = result.get("output") or ""
    if isinstance(output, list):
        output = output[0] if output else ""
    if not output:
        return False

    try:
        urllib.request.urlretrieve(output, str(out_path))
        print(f"  Lip-sync: {out_path.stat().st_size / 1e6:.1f} MB")
        return True
    except Exception as e:
        print(f"  Download error: {e}")
        return False

# ── Audio ─────────────────────────────────────────────────────────────────────
def audio_duration(mp3: Path) -> float:
    r = subprocess.run(
        ["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",str(mp3)],
        capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except ValueError: return 80.0

def gen_audio_elevenlabs(script: str, mp3: Path, ass: Path, api_key: str) -> list[dict]:
    client = _ElevenLabsClient(api_key=api_key)
    audio_bytes = client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        text=script,
        model_id="eleven_turbo_v2",
        output_format="mp3_44100_128",
    )
    data = b"".join(audio_bytes) if not isinstance(audio_bytes, bytes) else audio_bytes
    mp3.write_bytes(data)
    words = _estimate_words(script, mp3)
    _write_ass(words, ass)
    return words

def _estimate_words(script: str, mp3: Path) -> list[dict]:
    dur_ms = int(audio_duration(mp3) * 1000)
    all_words = script.split()
    if not all_words: return []
    per_word = max(80, dur_ms // len(all_words))
    return [{"text": w, "offset_ms": i*per_word, "dur_ms": per_word}
            for i, w in enumerate(all_words)]

async def _gen_audio_edge(script: str, mp3: Path, ass: Path) -> list[dict]:
    tts   = edge_tts.Communicate(script, voice=VOICE_EDGE, rate="-5%", pitch="+0Hz")
    words = []; sentences = []; audio = bytearray()
    async for chunk in tts.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            words.append({"text": chunk["text"],
                          "offset_ms": chunk["offset"]//10_000,
                          "dur_ms":    chunk["duration"]//10_000})
        elif chunk["type"] == "SentenceBoundary":
            sentences.append({"text": chunk["text"],
                               "offset_ms": chunk["offset"]//10_000,
                               "dur_ms":    chunk["duration"]//10_000})
    mp3.write_bytes(bytes(audio))
    if not words and sentences:
        for sent in sentences:
            ws = sent["text"].split()
            if not ws: continue
            pw = max(80, sent["dur_ms"] // len(ws))
            for i, w in enumerate(ws):
                words.append({"text": w,
                               "offset_ms": sent["offset_ms"] + i*pw,
                               "dur_ms": pw})
    _write_ass(words, ass)
    return words

def gen_audio(script: str, mp3: Path, ass: Path, el_api_key: str = "") -> list[dict]:
    if el_api_key and HAS_ELEVENLABS:
        print("    Using ElevenLabs (Lily)...")
        return gen_audio_elevenlabs(script, mp3, ass, el_api_key)
    print("    Using edge-tts (Libby fallback)...")
    return asyncio.run(_gen_audio_edge(script, mp3, ass))

def _ms_to_ass(ms: int) -> str:
    ms = max(0, ms)
    return f"{ms//3_600_000}:{(ms//60_000)%60:02d}:{(ms//1000)%60:02d}.{(ms%1000)//10:02d}"

def _write_ass(words: list[dict], path: Path):
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {W}\nPlayResY: {H}\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,36,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,"
        "-1,0,0,0,100,100,0.5,0,1,2,1,2,60,60,380,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    for i, word in enumerate(words):
        s = word["offset_ms"]; e = s + word["dur_ms"] + 60
        ws = max(0, i-1); we = min(len(words), i+2)
        parts = []
        for j in range(ws, we):
            txt = words[j]["text"].upper()
            parts.append(f"{{\\c&H0080FF3F&\\b1\\shad2}}{txt}{{\\r}}" if j == i
                         else f"{{\\c&H00AAAAAA&}}{txt}{{\\r}}")
        events.append(
            f"Dialogue: 0,{_ms_to_ass(s)},{_ms_to_ass(e)},Default,,0,0,0,,{' '.join(parts)}")
    path.write_text(header + "\n".join(events), encoding="utf-8")

def gen_music(duration_s: float, out: Path) -> bool:
    expr = ("0.10*sin(2*PI*110*t)*(1+0.04*sin(2*PI*0.22*t))+"
            "0.07*sin(2*PI*164.8*t)*(1+0.04*sin(2*PI*0.27*t))+"
            "0.06*sin(2*PI*220*t)*(1+0.03*sin(2*PI*0.18*t))+"
            "0.04*sin(2*PI*261.6*t)*(1+0.03*sin(2*PI*0.32*t))")
    fade_at = max(0.5, duration_s - 2.5)
    r = subprocess.run(
        ["ffmpeg","-y","-f","lavfi","-i",
         f"aevalsrc={expr}:s=44100:d={duration_s+4:.2f}",
         "-af",f"lowpass=f=700,afade=t=in:d=2.5,afade=t=out:st={fade_at:.2f}:d=3,volume=0.15",
         str(out)], capture_output=True, text=True)
    return r.returncode == 0

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("generate_whale_video.py — Contrarian Whale Explainer")

    if not HAS_PIL:
        print("ERROR: pip install --break-system-packages Pillow"); raise SystemExit(1)
    if not HAS_TTS:
        print("ERROR: pip install --break-system-packages edge-tts"); raise SystemExit(1)

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

    el_api_key   = _load_env_key("ELEVENLABS_API_KEY")
    repl_api_key = _load_env_key("REPLICATE_API_KEY")

    print(f"  ElevenLabs: {'key found — Lily voice' if el_api_key and HAS_ELEVENLABS else 'no key — Libby fallback'}")
    print(f"  Replicate:  {'key found — lip-sync enabled' if repl_api_key else 'no key — static avatar'}")

    fonts = load_fonts()

    TMP         = Path(tempfile.mkdtemp(prefix="whale_vid_"))
    mp3         = TMP / "voice.mp3"
    ass         = TMP / "captions.ass"
    music       = TMP / "music.wav"
    bg_png      = TMP / "background.png"
    top_png     = TMP / "top_bar.png"
    bot_png     = TMP / "bottom_panel.png"
    avatar_png  = TMP / "avatar_overlay.png"
    ring_png    = TMP / "avatar_ring.png"
    mask_png    = TMP / "circle_mask.png"
    lipsync_mp4 = TMP / "lipsync.mp4"
    tmp_silent  = TMP / "silent.mp4"

    # 1. Voiceover
    print("  Generating voiceover...")
    gen_audio(WHALE_SCRIPT, mp3, ass, el_api_key)
    dur = audio_duration(mp3)
    print(f"  Audio: {dur:.1f}s")

    # 2. Music bed
    print("  Generating music bed...")
    has_music = gen_music(dur, music)

    # 3. Overlay PNGs
    print("  Rendering overlay panels...")
    make_background(fonts).save(str(bg_png))
    make_top_bar(fonts).save(str(top_png))
    make_whale_panel(fonts).save(str(bot_png))
    print("  Overlays done.")

    # 4. Avatar / lip-sync
    panel_top = H - 680
    zone_h    = panel_top - 115
    circle_d  = min(820, int(zone_h * 0.84))
    cx_pos    = (W - circle_d) // 2
    cy_centre = 115 + zone_h // 2
    cy_pos    = cy_centre - circle_d // 2

    avatar_path = pick_avatar()
    if avatar_path is None:
        for ext in ("avatar.jpg", "avatar.jpeg"):
            p = AVATAR_DIR / ext
            if p.exists(): avatar_path = p; break

    use_lipsync       = False
    has_static_avatar = False

    if repl_api_key and avatar_path:
        use_lipsync = replicate_wav2lip(avatar_path, mp3, repl_api_key, lipsync_mp4)
        if use_lipsync:
            make_circle_mask(circle_d, mask_png)
            make_avatar_ring_only(fonts, circle_d).save(str(ring_png))
            print("  Circle mask + ring overlay ready.")

    if not use_lipsync:
        av_overlay = make_avatar_overlay(fonts) if avatar_path else None
        has_static_avatar = av_overlay is not None
        if has_static_avatar:
            av_overlay.save(str(avatar_png))
            print("  Static avatar overlay saved.")

    # 5. Compose
    WIN_OUT.mkdir(parents=True, exist_ok=True)
    out_file   = WIN_OUT / "whale_explainer.mp4"
    out_local  = ROOT / "whale_explainer.mp4"
    panel_h    = 680
    ass_esc    = str(ass).replace("\\", "/").replace(":", "\\:")

    print("  Composing studio video...")

    # Pass 1 — visual layers → silent mp4
    if use_lipsync:
        vf = (
            f"[0:v]scale={circle_d}:{circle_d}:force_original_aspect_ratio=decrease,"
            f"pad={circle_d}:{circle_d}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"format=rgba[sq];"
            f"[1:v]scale={circle_d}:{circle_d}[msk];"
            f"[sq][msk]alphamerge[face];"
            f"[2:v][face]overlay={cx_pos}:{cy_pos}[v1];"
            f"[v1][3:v]overlay=0:0[v2];"
            f"[v2][4:v]overlay=0:0[v3];"
            f"[v3][5:v]overlay=0:{H - panel_h}[v4];"
            f"[v4]subtitles={ass_esc}[vout]"
        )
        cmd1 = [
            "ffmpeg", "-y",
            "-i", str(lipsync_mp4),
            "-loop","1","-t",f"{dur:.2f}","-i", str(mask_png),
            "-loop","1","-t",f"{dur:.2f}","-i", str(bg_png),
            "-loop","1","-t",f"{dur:.2f}","-i", str(ring_png),
            "-loop","1","-t",f"{dur:.2f}","-i", str(top_png),
            "-loop","1","-t",f"{dur:.2f}","-i", str(bot_png),
            "-filter_complex", vf,
            "-map","[vout]",
            "-c:v","libx264","-preset","fast","-crf","22",
            "-r","30","-pix_fmt","yuv420p","-t",f"{dur:.2f}",
            str(tmp_silent),
        ]
    elif has_static_avatar:
        vf = (
            f"[0:v][1:v]overlay=0:0[v1];"
            f"[v1][2:v]overlay=0:0[v2];"
            f"[v2][3:v]overlay=0:{H - panel_h}[v3];"
            f"[v3]subtitles={ass_esc}[vout]"
        )
        cmd1 = [
            "ffmpeg", "-y",
            "-loop","1","-t",f"{dur:.2f}","-i", str(bg_png),
            "-loop","1","-t",f"{dur:.2f}","-i", str(avatar_png),
            "-loop","1","-t",f"{dur:.2f}","-i", str(top_png),
            "-loop","1","-t",f"{dur:.2f}","-i", str(bot_png),
            "-filter_complex", vf,
            "-map","[vout]",
            "-c:v","libx264","-preset","fast","-crf","22",
            "-r","30","-pix_fmt","yuv420p",
            str(tmp_silent),
        ]
    else:
        # No avatar — still looks good with just the whale panel
        vf = (
            f"[0:v][1:v]overlay=0:0[v1];"
            f"[v1][2:v]overlay=0:{H - panel_h}[v2];"
            f"[v2]subtitles={ass_esc}[vout]"
        )
        cmd1 = [
            "ffmpeg", "-y",
            "-loop","1","-t",f"{dur:.2f}","-i", str(bg_png),
            "-loop","1","-t",f"{dur:.2f}","-i", str(top_png),
            "-loop","1","-t",f"{dur:.2f}","-i", str(bot_png),
            "-filter_complex", vf,
            "-map","[vout]",
            "-c:v","libx264","-preset","fast","-crf","22",
            "-r","30","-pix_fmt","yuv420p",
            str(tmp_silent),
        ]

    r1 = subprocess.run(cmd1, capture_output=True, text=True)
    if r1.returncode != 0:
        print("FFmpeg pass-1 error:", r1.stderr[-1500:])
        raise SystemExit(1)

    # Pass 2 — add voice + music
    if has_music and music.exists():
        af   = "[0:a]volume=1.0[v];[1:a]volume=0.13[m];[v][m]amix=inputs=2:duration=first[aout]"
        cmd2 = [
            "ffmpeg", "-y",
            "-i", str(mp3), "-i", str(music), "-i", str(tmp_silent),
            "-filter_complex", af,
            "-map","2:v","-map","[aout]",
            "-c:v","copy","-c:a","aac","-b:a","192k",
            "-shortest", str(out_file),
        ]
    else:
        cmd2 = [
            "ffmpeg", "-y",
            "-i", str(mp3), "-i", str(tmp_silent),
            "-map","1:v","-map","0:a",
            "-c:v","copy","-c:a","aac","-b:a","192k",
            "-shortest", str(out_file),
        ]

    r2 = subprocess.run(cmd2, capture_output=True, text=True)
    if r2.returncode != 0:
        print("FFmpeg pass-2 error:", r2.stderr[-1000:])
        raise SystemExit(1)

    shutil.copy(str(out_file), str(out_local))

    # Copy to Windows Desktop
    WIN_DESKTOP = Path("/path/to/local/Desktop/catalyst-edge/social")
    if WIN_DESKTOP.exists():
        dest = WIN_DESKTOP / "whale_explainer.mp4"
        shutil.copy(str(out_file), str(dest))
        print(f"  Copied to Windows Desktop: {dest.name}")
        (WIN_DESKTOP / "UPLOAD_whale_explainer.txt").write_text(
            "Contrarian Whale Explainer — upload to YouTube / TikTok / Reels\n"
            "File: whale_explainer.mp4\n"
            "Title: The Signal Smart Money Uses at 4 AM (Contrarian Whale)\n"
            "Tags: #SECFilings #StockScanner #InsiderTrading #CatalystEdge\n"
            "Free Scanner: https://catalystedgescanner.com\n"
            "Newsletter: https://catalystedge.agency\n",
            encoding="utf-8",
        )
    else:
        print("  Windows Desktop path not found — video at workspace/social/ only")

    shutil.rmtree(TMP, ignore_errors=True)

    mb = out_file.stat().st_size / 1e6
    print(f"\n  Done! {mb:.1f} MB → {out_file}")
    print(f"  Also at: {out_local}")
    print("\n  YouTube title: 'The Signal Smart Money Uses at 4 AM (Contrarian Whale)'")
    print("  Thumbnail slide: whale badge glowing + '🐋 WHALES BUY BAD NEWS'")


if __name__ == "__main__":
    main()
