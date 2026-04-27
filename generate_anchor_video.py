#!/usr/bin/env python3
"""generate_anchor_video.py — AI talking-head anchor video for Catalyst Edge.

Full-anchor layout: avatar face fills the 1080×1920 frame.
Data overlays (branding bar + ticker/score panel) float on top.
Karaoke captions and music bed are mixed in.

Avatar images:  workspace/avatars/avatar_mon.png … avatar_sun.png
                (7 outfits, one per weekday — same face, different look)
                Falls back to avatars/avatar.png if day file missing.

Voice:  en-GB-SoniaNeural via edge-tts (generated fresh each run)
Lip-sync:  D-ID Talks API  (D_ID_API_KEY env var)
Output:  Desktop/catalyst-edge/social/anchor_YYYY-MM-DD.mp4
         workspace/tiktok_video.mp4  (replaces slides video when successful)

Setup:
  1.  pip install --break-system-packages edge-tts Pillow
  2.  Add D_ID_API_KEY=<your key> to .sec_email_env
  3.  Place avatar_mon.png … avatar_sun.png in workspace/avatars/
      (portrait orientation recommended, 1080×1920 or 1:1 minimum)
  4.  Run: python3 generate_anchor_video.py
"""

from __future__ import annotations

import asyncio
import base64
import csv
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

ROOT    = Path(__file__).parent
WIN_OUT = Path(__file__).parent / "social"
AVATAR_DIR = ROOT / "avatars"
TODAY   = datetime.date.today().isoformat()
TODAY_DISPLAY = datetime.date.today().strftime("%B %d, %Y")
DOW     = datetime.date.today().strftime("%a").lower()   # mon … sun

W, H   = 1080, 1920
FPS    = 30
VOICE_EDGE = "en-GB-LibbyNeural"          # edge-tts fallback
ELEVENLABS_VOICE_ID = "pFZP5JQG7iQjIQuC4Bku"  # Lily — British, confident, velvety

# ── Colours ───────────────────────────────────────────────────────────────────
DARK_BG    = (6,   8,  20)
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
    """Lerp including alpha channel."""
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i]*(1-t) + c2[i]*t) for i in range(len(c1)))

def draw_rr(draw, x1, y1, x2, y2, r, fill, outline=None, ow=0):
    try:
        draw.rounded_rectangle([x1,y1,x2,y2], radius=r, fill=fill, outline=outline, width=ow)
    except TypeError:
        draw.rounded_rectangle([x1,y1,x2,y2], radius=r, fill=fill)

def tsize(draw, text, font):
    bb = draw.textbbox((0,0), text, font=font)
    return bb[2]-bb[0], bb[3]-bb[1]

def shadow(draw, xy, text, font, fill, d=3):
    draw.text((xy[0]+d, xy[1]+d), text, font=font, fill=(*fill[:3], 150))
    draw.text(xy, text, font=font, fill=fill)

def centered(draw, y, text, font, fill, w=W, shad=True):
    tw, th = tsize(draw, text, font)
    x = (w - tw) // 2
    if shad: draw.text((x+3, y+3), text, font=font, fill=(*fill[:3], 140) if len(fill)>3 else (0,0,0,140))
    draw.text((x, y), text, font=font, fill=fill)

def hbar_rgba(img, x1, y1, x2, y2, c1, c2):
    draw = ImageDraw.Draw(img)
    span = max(1, x2-x1)
    step = max(1, span // 150)
    for x in range(x1, x2, step):
        col = lerp_a(c1, c2, (x-x1)/span)
        draw.rectangle([x, y1, min(x+step, x2), y2], fill=col)

# ── Overlay generators ────────────────────────────────────────────────────────
def make_top_bar(fonts) -> Image.Image:
    """1080×115 RGBA branding bar — semi-transparent dark."""
    img = Image.new("RGBA", (W, 115), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Dark gradient from top
    for y in range(115):
        alpha = int(220 * (1 - y / 115))
        draw.line([(0, y), (W-1, y)], fill=(6, 8, 20, alpha))
    # BREAKING stripe
    draw.rectangle([0, 0, W, 52], fill=(185, 18, 18, 210))
    centered(draw, 10, "BREAKING — SEC CATALYST", fonts["small"], WHITE)
    # Brand
    draw.text((44, 60), "CATALYST EDGE", font=fonts["brand"], fill=(*lerp(BLUE, WHITE, 0.5), 255))
    dw, _ = tsize(draw, TODAY_DISPLAY.upper(), fonts["small"])
    draw.text((W-dw-44, 68), TODAY_DISPLAY.upper(), font=fonts["small"], fill=(*GRAY, 200))
    return img

def make_bottom_panel(ticker, category, form, score, tags, top5, picks_data, fonts) -> Image.Image:
    """1080×680 RGBA data panel — sits at the bottom of the frame."""
    PH = 680
    img = Image.new("RGBA", (W, PH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient from transparent at top to opaque at bottom
    for y in range(PH):
        alpha = int(235 * (y / PH) ** 0.55)
        draw.line([(0, y), (W-1, y)], fill=(*DARK_BG, alpha))

    cat_col = CAT_COLOR[category]
    cat_bg  = CAT_BG[category]
    PAD = 50

    # Category pill
    ctext = CAT_LABEL[category]
    cw, _ = tsize(draw, ctext, fonts["tag"])
    cx1 = (W - cw - 56) // 2; cx2 = cx1 + cw + 56
    draw_rr(draw, cx1, 18, cx2, 70, 26, (*cat_bg, 210), (*cat_col, 255), 2)
    centered(draw, 28, ctext, fonts["tag"], (*cat_col, 255))

    # Giant ticker + $ prefix
    ds_w, ds_h = tsize(draw, "$", fonts["h2"])
    tk_w, tk_h = tsize(draw, ticker, fonts["giant"])
    total_w = ds_w + 8 + tk_w
    sx = (W - total_w) // 2
    ty = 85

    # Subtle card behind ticker
    draw_rr(draw, sx-32, ty-10, sx+total_w+32, ty+tk_h+10, 18, (12, 12, 38, 160))
    shadow(draw, (sx, ty + (tk_h - ds_h)//2 + 10), "$", fonts["h2"], (*lerp(cat_col, WHITE, 0.5), 255), 3)
    shadow(draw, (sx + ds_w + 8, ty), ticker, fonts["giant"], (*cat_col, 255), 5)

    # Score bar
    sc_y = ty + tk_h + 22
    sc_str = f"Score  {score:.0f}/16"
    sw, _ = tsize(draw, sc_str, fonts["small"])
    draw.text(((W - sw)//2, sc_y), sc_str, font=fonts["small"], fill=(*GRAY, 220))

    BX1, BX2, BH = PAD, W-PAD, 28
    bar_y = sc_y + 38
    draw_rr(draw, BX1, bar_y, BX2, bar_y+BH, BH//2, (18, 22, 54, 200))
    fill_px = int((BX2-BX1) * min(1.0, score/16.0))
    if fill_px > BH:
        hbar_rgba(img, BX1, bar_y, BX1+fill_px, bar_y+BH,
                  (*cat_col, 230), (*lerp(cat_col, WHITE, 0.55), 230))
        draw = ImageDraw.Draw(img)

    # Signal tags
    tag_y = bar_y + BH + 22
    used_tags = tags[:3] if tags else ["SEC Catalyst", "Event-Driven", "Top Score"]
    tag_x = PAD
    for tag in used_tags:
        tw, th = tsize(draw, tag.title(), fonts["small"])
        draw_rr(draw, tag_x, tag_y, tag_x+tw+28, tag_y+th+14, 8, (18, 26, 58, 180))
        draw.text((tag_x+14, tag_y+7), tag.title(), font=fonts["small"], fill=(*WHITE, 220))
        tag_x += tw + 40
        if tag_x > W - 150:
            break

    # Top 5 mini bar chart
    chart_y = tag_y + 60
    draw.line([(PAD, chart_y), (W-PAD, chart_y)], fill=(*GRAY, 80), width=1)
    chart_y += 16
    BAR_H = 44; GAP = 10; MAX_W = W - PAD*2 - 100

    for idx, (t, s) in enumerate(top5[:5]):
        row_y = chart_y + idx * (BAR_H + GAP)
        is_top = (idx == 0)
        lc = (*cat_col, 255) if is_top else (*LIGHT_GRAY, 180)
        lf = fonts["tag"] if is_top else fonts["small"]
        draw.text((PAD, row_y + (BAR_H - tsize(draw, f"${t}", lf)[1])//2), f"${t}", font=lf, fill=lc)
        bar_x = PAD + 100
        draw_rr(draw, bar_x, row_y, bar_x+MAX_W, row_y+BAR_H, BAR_H//2, (18, 22, 54, 160))
        fw = int(MAX_W * min(1.0, s/16.0))
        if fw > BAR_H:
            hbar_rgba(img, bar_x, row_y, bar_x+fw, row_y+BAR_H,
                      (*lerp(cat_col, DARK_BG, 0.3 if not is_top else 0), 200),
                      (*lerp(cat_col, WHITE, 0.45 if is_top else 0.1), 200))
            draw = ImageDraw.Draw(img)
        sl = f"{s:.0f}"
        slw, slh = tsize(draw, sl, fonts["small"])
        sx2 = (bar_x+fw-slw-10) if fw > slw+20 else (bar_x+fw+6)
        draw.text((sx2, row_y+(BAR_H-slh)//2), sl, font=fonts["small"], fill=(*WHITE, 200))

    # Footer CTA — full product suite
    footer_y = chart_y + 5*(BAR_H+GAP) + 18
    draw.line([(PAD, footer_y), (W-PAD, footer_y)], fill=(*BLUE, 120), width=2)
    centered(draw, footer_y+10, "NEWSLETTER  |  SCANNER  |  CEREBRO HUD  |  AI", fonts["small"],
             (*lerp(BLUE, WHITE, 0.5), 230))
    centered(draw, footer_y+46, "CATALYSTEDGE.AGENCY  |  START FREE AT /PRICING/", fonts["small"],
             (*lerp(BLUE, WHITE, 0.4), 200))
    centered(draw, footer_y+78, "Not financial advice. For informational purposes only.", fonts["small"],
             (120, 120, 140, 200))

    return img

# ── Replicate lip-sync ────────────────────────────────────────────────────────
def replicate_wav2lip(face_path: Path, audio_path: Path,
                      api_key: str, out_path: Path) -> bool:
    """Call Replicate's Wav2Lip model. Returns True on success."""
    import base64

    print("  Encoding inputs for Replicate...")
    face_mime  = "image/jpeg" if face_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    audio_mime = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
    face_b64   = base64.b64encode(face_path.read_bytes()).decode()
    audio_b64  = base64.b64encode(audio_path.read_bytes()).decode()
    face_uri   = f"data:{face_mime};base64,{face_b64}"
    audio_uri  = f"data:{audio_mime};base64,{audio_b64}"

    # POST prediction — use /v1/predictions with explicit version hash
    WAVLIP_VERSION = "8d65e3f4f4298520e079198b493c25adfc43c058ffec924f2aefc8010ed25eef"
    payload = json.dumps({
        "version": WAVLIP_VERSION,
        "input": {
            "face":          face_uri,
            "audio":         audio_uri,
            "fps":           25,
            "pads":          "0 10 0 0",
            "smooth":        True,
            "resize_factor": 1,
        }
    }).encode()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "Prefer":        "wait",   # ask Replicate to hold connection up to 60 s
    }
    req = urllib.request.Request(
        "https://api.replicate.com/v1/predictions",
        data=payload, headers=headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"  Replicate POST error HTTP {e.code}: {body[:400]}")
        return False
    except Exception as e:
        print(f"  Replicate POST error: {e}")
        return False

    pred_id = result.get("id", "")
    status  = result.get("status", "")
    print(f"  Prediction id={pred_id} status={status}")

    # Poll until done (Prefer:wait may have already resolved it)
    deadline = time.time() + 600
    while status not in ("succeeded", "failed", "canceled") and time.time() < deadline:
        time.sleep(8)
        poll_req = urllib.request.Request(
            f"https://api.replicate.com/v1/predictions/{pred_id}",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        try:
            with urllib.request.urlopen(poll_req, timeout=30) as r:
                result = json.loads(r.read())
            status = result.get("status", "")
            print(f"    ... {status}")
        except Exception as e:
            print(f"    poll error: {e}")

    if status != "succeeded":
        err = result.get("error") or result.get("logs", "")
        print(f"  Replicate failed: {status} — {str(err)[:300]}")
        return False

    # Download output video
    output = result.get("output") or ""
    if isinstance(output, list):
        output = output[0] if output else ""
    if not output:
        print("  Replicate: no output URL in response")
        return False

    print(f"  Downloading lip-sync video from Replicate...")
    try:
        urllib.request.urlretrieve(output, str(out_path))
        mb = out_path.stat().st_size / 1e6
        print(f"  Lip-sync video: {mb:.1f} MB → {out_path.name}")
        return True
    except Exception as e:
        print(f"  Download error: {e}")
        return False


def make_circle_mask(size: int, out: Path):
    """Grayscale PNG — white circle on black. Used by ffmpeg alphamerge."""
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    mask.save(str(out))


# ── Avatar overlay ────────────────────────────────────────────────────────────
def make_avatar_overlay(fonts) -> "Image.Image | None":
    """1080×1920 RGBA with circular avatar photo centered in the anchor zone.
    Returns None if no avatar image is available."""
    avatar_path = pick_avatar()
    if avatar_path is None:
        # Also try .jpg extension (thispersondoesnotexist download)
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

    # Crop source to square from center
    aw, ah = av.size
    side = min(aw, ah)
    left = (aw - side) // 2
    top_crop = (ah - side) // 2
    av = av.crop((left, top_crop, left + side, top_crop + side))

    # Anchor zone: y=115 (top bar bottom) → y=1240 (bottom panel top, H-680)
    # Circle diameter fits comfortably inside that zone
    panel_top = H - 680
    zone_h    = panel_top - 115
    circle_d  = min(820, int(zone_h * 0.84))  # at most 84 % of zone height
    av = av.resize((circle_d, circle_d), Image.LANCZOS)

    # Circular mask
    mask = Image.new("L", (circle_d, circle_d), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, circle_d - 1, circle_d - 1], fill=255)
    av.putalpha(mask)

    # Build overlay canvas (transparent)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    # Centre position
    cx = (W - circle_d) // 2
    cy_centre = 115 + zone_h // 2
    cy = cy_centre - circle_d // 2

    # Glowing concentric rings behind the avatar
    for i, (col, alpha, thickness) in enumerate([
        (PURPLE, 50,  34),
        (lerp(BLUE, PURPLE, 0.5), 90, 22),
        (BLUE,  160,  12),
        (WHITE,  80,   4),
    ]):
        r = circle_d // 2 + 6 + i * 12
        draw.ellipse([cx - 6 - i*12, cy - 6 - i*12,
                      cx + circle_d + 6 + i*12, cy + circle_d + 6 + i*12],
                     outline=(*col, alpha), width=thickness)

    # Paste circular avatar
    overlay.paste(av, (cx, cy), av)

    # Small "AI ANCHOR" caption below the circle
    label_y = cy + circle_d + 16
    if label_y + 36 < panel_top:
        centered(draw, label_y, "CATALYST EDGE  AI ANCHOR", fonts["small"], (*GRAY, 200))

    return overlay


def make_avatar_ring_only(fonts, circle_d: int) -> "Image.Image":
    """1080×1920 RGBA with glow rings + 'AI ANCHOR' label but transparent center.
    Used when the lip-sync video fills the circle area."""
    panel_top = H - 680
    zone_h    = panel_top - 115
    overlay   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw      = ImageDraw.Draw(overlay)

    cx       = W // 2
    cy_centre = 115 + zone_h // 2
    cy_top    = cy_centre - circle_d // 2

    # Glow rings
    for i, (col, alpha, thickness) in enumerate([
        (PURPLE, 50,  34),
        (lerp(BLUE, PURPLE, 0.5), 90, 22),
        (BLUE,  160,  12),
        (WHITE,  80,   4),
    ]):
        r = circle_d // 2 + 6 + i * 12
        draw.ellipse([cx - r, cy_centre - r, cx + r, cy_centre + r],
                     outline=(*col, alpha), width=thickness)

    label_y = cy_top + circle_d + 16
    if label_y + 36 < panel_top:
        centered(draw, label_y, "CATALYST EDGE  AI ANCHOR", fonts["small"], (*GRAY, 200))

    return overlay


# ── Studio background ─────────────────────────────────────────────────────────
def make_background(fonts) -> Image.Image:
    """1080×1920 dark news-studio background with grid lines and vignette."""
    img = Image.new("RGB", (W, H), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Radial vignette — dark corners, slightly lighter centre
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

    # Subtle horizontal scan-lines
    for y in range(0, H, 6):
        draw.line([(0, y), (W, y)], fill=(255, 255, 255, 8), width=1)

    # Faint grid
    for x in range(0, W, 120):
        draw.line([(x, 0), (x, H)], fill=(*BLUE, 12))
    for y in range(0, H, 120):
        draw.line([(0, y), (W, y)], fill=(*BLUE, 12))

    # Subtle glow behind the speaker area
    for r in range(320, 0, -4):
        alpha = int(18 * (1 - r / 320))
        x0, y0 = W//2 - r, H//2 - r
        draw.ellipse([x0, y0, x0+r*2, y0+r*2],
                     fill=(*lerp(DARK_BG, BLUE, 0.18), alpha))

    # Thin accent line at bottom of top bar area
    draw.line([(0, 115), (W, 115)], fill=(*BLUE, 100), width=2)

    return img

# ── Avatar picker ─────────────────────────────────────────────────────────────
def pick_avatar() -> Path | None:
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    # Try day-specific outfit first
    day_file = AVATAR_DIR / f"avatar_{DOW}.png"
    if day_file.exists():
        return day_file
    # Numbered fallback (rotate through avatar_1.png … avatar_7.png)
    day_index = datetime.date.today().weekday() + 1
    for n in [day_index, 1]:
        p = AVATAR_DIR / f"avatar_{n}.png"
        if p.exists():
            return p
    # Generic fallback
    generic = AVATAR_DIR / "avatar.png"
    if generic.exists():
        return generic
    return None

# ── D-ID API helpers ──────────────────────────────────────────────────────────
def _did_auth(api_key: str) -> str:
    return "Basic " + base64.b64encode(f"{api_key}:".encode()).decode()

def _did_request(method: str, endpoint: str, api_key: str,
                 data: bytes | None = None, content_type: str = "application/json") -> dict:
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

def _upload_multipart(endpoint: str, api_key: str, field: str,
                      file_path: Path, mime: str) -> str:
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

def did_get_agent_presenter(agent_id: str, api_key: str) -> dict | None:
    """Fetch presenter info from a D-ID Studio agent.
    Returns dict with presenter_id, driver_id, type, thumbnail."""
    try:
        result = _did_request("GET", f"/agents/{agent_id}", api_key)
        presenter = result.get("presenter") or {}
        ptype = presenter.get("type", "")
        pid   = presenter.get("presenter_id", "")
        did   = presenter.get("driver_id", "")
        thumb = presenter.get("thumbnail", "")
        if pid:
            print(f"    Agent presenter: {pid}  type={ptype}  driver={did}")
            return {"presenter_id": pid, "driver_id": did, "type": ptype, "thumbnail": thumb}
        return None
    except Exception as exc:
        print(f"    WARNING: Could not fetch agent presenter ({exc}); falling back to file upload.")
        return None

def did_upload_image(path: Path, api_key: str) -> str:
    print("    Uploading avatar image to D-ID...")
    url = _upload_multipart("/images/uploads", api_key, "image", path, "image/png")
    print(f"    Image uploaded: {url[:60]}...")
    return url

def did_create_talk(source_url: str, script_text: str, api_key: str) -> tuple[str, str]:
    """POST /talks — for photo-based presenters. Returns (talk_id, endpoint)."""
    print("    Creating D-ID talk (photo presenter)...")
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
    talk_id = result["id"]
    print(f"    Talk created: {talk_id}")
    return talk_id, "/talks"

def did_create_clip(presenter_id: str, driver_id: str, script_text: str,
                    api_key: str, el_api_key: str = "") -> tuple[str, str]:
    """POST /clips — for D-ID clip/video presenters. Returns (clip_id, endpoint)."""
    print("    Creating D-ID clip (video presenter)...")
    if el_api_key:
        provider = {
            "type": "elevenlabs",
            "voice_id": ELEVENLABS_VOICE_ID,
            "api_key": el_api_key,
        }
        print("    Voice provider: ElevenLabs (Lily — British, velvety)")
    else:
        provider = {"type": "microsoft", "voice_id": "en-GB-LibbyNeural"}
        print("    Voice provider: Microsoft (Libby — fallback)")
    payload = json.dumps({
        "presenter_id": presenter_id,
        "driver_id":    driver_id,
        "script": {
            "type": "text",
            "input": script_text,
            "provider": provider,
        },
        "config": {"result_format": "mp4", "stitch": True},
        "background": {},
    }).encode()
    result = _did_request("POST", "/clips", api_key, data=payload)
    clip_id = result["id"]
    print(f"    Clip created: {clip_id}")
    return clip_id, "/clips"

def did_poll(job_id: str, endpoint: str, api_key: str, timeout: int = 420) -> str:
    """Poll /talks/{id} or /clips/{id} until done. Returns result_url."""
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
    raise TimeoutError(f"D-ID job timed out after {timeout}s")

def did_download_video(url: str, dest: Path):
    print(f"    Downloading talking-head video...")
    urllib.request.urlretrieve(url, str(dest))
    print(f"    Downloaded: {dest.stat().st_size / 1e6:.1f} MB")

# ── Audio generation ──────────────────────────────────────────────────────────
def gen_audio_elevenlabs(script: str, mp3: Path, ass: Path, api_key: str) -> list[dict]:
    """Generate audio with ElevenLabs Lily voice; build ASS captions from word timing."""
    client = _ElevenLabsClient(api_key=api_key)
    audio_bytes = client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        text=script,
        model_id="eleven_turbo_v2",
        output_format="mp3_44100_128",
    )
    # elevenlabs SDK returns a generator of bytes chunks
    data = b"".join(audio_bytes) if not isinstance(audio_bytes, bytes) else audio_bytes
    mp3.write_bytes(data)
    # ElevenLabs doesn't give word-level timing via this SDK call,
    # so estimate from sentence boundaries using the same fallback as edge-tts
    words = _estimate_words_from_text(script, mp3)
    _write_ass(words, ass)
    return words

def _estimate_words_from_text(script: str, mp3: Path) -> list[dict]:
    """Estimate per-word timing from total audio duration + word count."""
    dur_ms = int(audio_duration(mp3) * 1000)
    all_words = script.split()
    if not all_words:
        return []
    per_word = max(80, dur_ms // len(all_words))
    return [{"text": w, "offset_ms": i * per_word, "dur_ms": per_word}
            for i, w in enumerate(all_words)]

async def _gen_audio_edge(script: str, mp3: Path, ass: Path) -> list[dict]:
    tts = edge_tts.Communicate(script, voice=VOICE_EDGE, rate="-5%", pitch="+0Hz")
    words: list[dict] = []
    sentences: list[dict] = []
    audio = bytearray()
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
            parts.append(f"{{\\c&H0000FFFF&\\b1\\shad2}}{txt}{{\\r}}" if j == i
                         else f"{{\\c&H00AAAAAA&}}{txt}{{\\r}}")
        events.append(f"Dialogue: 0,{_ms_to_ass(s)},{_ms_to_ass(e)},Default,,0,0,0,,{' '.join(parts)}")
    path.write_text(header + "\n".join(events), encoding="utf-8")


def audio_duration(mp3: Path) -> float:
    r = subprocess.run(
        ["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",str(mp3)],
        capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except ValueError: return 60.0

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

# ── Script builder ────────────────────────────────────────────────────────────
def build_script(ticker, row, category, picks_data) -> str:
    import csv as _csv
    form   = row.get("form", "8-K")
    price  = row.get("price", "")
    tags_raw = row.get("tags", "")
    tags   = [t.lstrip("+").strip().title() for t in tags_raw.split(";")
              if t.strip().startswith("+")][:3]
    gs = float(row.get("gapper_score",0) or 0)
    vs = float(row.get("value_score", 0) or 0)
    ms = float(row.get("moat_score",  0) or 0)
    score  = gs + vs + ms
    scanned = picks_data.get("total_combined", 0)
    gcount  = picks_data.get("gapper_count", 0)
    vcount  = picks_data.get("value_count",  0)
    mcount  = picks_data.get("moat_count",   0)
    total_picks = gcount + vcount + mcount

    form_labels = {
        "8-K":"8-K material event","4":"Form 4 insider trade","S-3":"S-3 shelf filing",
        "6-K":"6-K foreign issuer report","13D":"Schedule 13-D activist position",
        "13G":"Schedule 13-G institutional stake","S-1":"S-1 IPO filing",
    }
    form_spoken = form_labels.get(form.strip().upper(), f"{form} filing")

    # Brand intro hook — establishes authority
    brand_intro = (
        f"Catalyst Edge scans {scanned} SEC filings every morning before the open. "
        "Here is what the algorithm flagged today."
    )

    cat_hooks = {
        "gapper": "One ticker is set up for a high-momentum move at the open.",
        "value":  "The SEC just flagged something most traders have not seen yet. I ran the numbers, and this one is worth your attention.",
        "moat":   "Institutional positioning just showed up in an SEC filing. Here is what the smart money is doing before the market opens.",
    }

    price_line = ""
    if price:
        try:
            pf = float(price)
            if pf > 0: price_line = f"It is currently trading at {pf:.2f}."
        except (ValueError, TypeError): pass

    tag_line = f"The filing is flagging: {', '.join(tags)}." if tags else ""

    lines = [
        brand_intro,
        cat_hooks[category],
        f"Out of {scanned} filings reviewed, we identified {total_picks} catalyst setups worth watching today.",
        "But one rose above all of them.",
        f"The ticker is {ticker}.",
        f"{ticker} just filed a {form_spoken} with the Securities and Exchange Commission.",
    ]
    if tag_line: lines.append(tag_line)
    lines.append(f"{ticker} scored {score:.0f} out of 16 on our catalyst model. That puts it at the top of today's list.")
    if price_line: lines.append(price_line)
    lines.append("Watch the opening bell closely. Catalyst events like this one move fast.")
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
        f"Follow, subscribe in the bio, and tell me — are you watching {ticker} today?"
    )
    return " ".join(lines)

# ── Data loaders ──────────────────────────────────────────────────────────────
def read_csv(path: Path) -> list[dict]:
    if not path.exists(): return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception: return []

def load_pick():
    picks_data = {}
    pj = ROOT / "newsletter_picks.json"
    if pj.exists(): picks_data = json.loads(pj.read_text())
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

# ── Video composition ─────────────────────────────────────────────────────────
def compose_anchor(talking_head: Path, background_png: Path,
                   top_bar_png: Path, bottom_panel_png: Path,
                   ass_path: Path, music_wav: Path | None,
                   out_path: Path):
    """
    Full-anchor composite with green-screen removal:
      background.png    → 1080×1920 studio background (index 1)
      talking_head.mp4  → chromakey green removed, scaled/cropped (index 0)
      top_bar.png       → overlaid at y=0 (index 2)
      bottom_panel.png  → overlaid at y=H-680 (index 3 or 4)
      ASS captions + music bed
    """
    panel_h = 680
    ass_esc = str(ass_path).replace("\\", "/").replace(":", "\\:")

    # Chroma key green screen (pure green #00ff00), then scale/crop to portrait
    face_filter = (
        f"[0:v]chromakey=0x00ff00:similarity=0.25:blend=0.08[keyed];"
        f"[keyed]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H}[face];"
        # Composite keyed face over background
        f"[1:v][face]overlay=0:0[onbg];"
        # Cover D-ID watermark area with a dark brand stamp
        f"[onbg]drawbox=x=0:y=1150:w={W}:h=90:color=black@0.72:t=fill[nobrand];"
        f"[nobrand]drawtext=text='CATALYST EDGE':fontcolor=white@0.55:fontsize=26:"
        f"x=(w-text_w)/2:y=1170[stamped]"
    )

    if music_wav and music_wav.exists():
        audio_filter = (
            "[0:a]volume=1.0[voice];"
            f"[{3 if True else 3}:a]volume=0.13[music];"
            "[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        inputs = ["-i", str(talking_head),
                  "-i", str(background_png),
                  "-i", str(top_bar_png),
                  "-i", str(music_wav),
                  "-i", str(bottom_panel_png)]
        video_filter = (
            face_filter + ";"
            f"[stamped][2:v]overlay=0:0[v1];"
            f"[v1][4:v]overlay=0:{H-panel_h}[v2];"
            f"[v2]subtitles={ass_esc}[vout]"
        )
        audio_filter = (
            "[0:a]volume=1.0[voice];"
            "[3:a]volume=0.13[music];"
            "[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        map_args = ["-map", "[vout]", "-map", "[aout]"]
    else:
        inputs = ["-i", str(talking_head),
                  "-i", str(background_png),
                  "-i", str(top_bar_png),
                  "-i", str(bottom_panel_png)]
        audio_filter = None
        video_filter = (
            face_filter + ";"
            f"[stamped][2:v]overlay=0:0[v1];"
            f"[v1][3:v]overlay=0:{H-panel_h}[v2];"
            f"[v2]subtitles={ass_esc}[vout]"
        )
        map_args = ["-map", "[vout]", "-map", "0:a"]

    fc = (video_filter + ";" + audio_filter) if audio_filter else video_filter

    cmd = (
        ["ffmpeg", "-y"] + inputs
        + ["-filter_complex", fc]
        + map_args
        + ["-c:v", "libx264", "-preset", "fast", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart",
           "-shortest", str(out_path)]
    )
    print("  Compositing full-anchor video...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FFmpeg error:", r.stderr[-2000:])
        raise SystemExit(1)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"generate_anchor_video date={TODAY} dow={DOW}")

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
    if el_api_key and HAS_ELEVENLABS:
        print("  ElevenLabs: key found — Lily voice active")
    else:
        print("  ElevenLabs: no key — using Microsoft Libby fallback")
    if repl_api_key:
        print("  Replicate: key found — lip-sync enabled")
    else:
        print("  Replicate: no key — using static avatar")

    ticker, row, picks_data = load_pick()
    if not ticker:
        print("  No pick data — skipping"); return

    category    = get_category(row)
    form        = row.get("form", "8-K")
    tags        = clean_tags(row.get("tags", ""))
    gs          = float(row.get("gapper_score",0) or 0)
    vs          = float(row.get("value_score", 0) or 0)
    ms          = float(row.get("moat_score",  0) or 0)
    total_score = gs + vs + ms
    top5        = load_top5_scores(picks_data.get("top5_tickers", [ticker]))

    print(f"  Pick: ${ticker}  category={category}  score={total_score:.0f}")

    fonts = load_fonts()
    script = build_script(ticker, row, category, picks_data)
    print(f"  Script ({len(script.split())} words):\n    {script[:100]}...")

    TMP = Path(tempfile.mkdtemp(prefix="anchor_vid_"))
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

    # 1. Generate voice (Lily via ElevenLabs or Libby fallback)
    print("  Generating voiceover...")
    gen_audio(script, mp3, ass, el_api_key)
    dur = audio_duration(mp3)
    print(f"  Audio: {dur:.1f}s")

    # 2. Music bed
    print("  Generating music bed...")
    has_music = gen_music(dur, music)

    # 3. Render overlay PNGs
    print("  Rendering overlay panels...")
    make_background(fonts).save(str(bg_png))
    make_top_bar(fonts).save(str(top_png))
    make_bottom_panel(ticker, category, form, total_score, tags, top5, picks_data, fonts).save(str(bot_png))
    print("  Overlays done.")

    # 4. Avatar: try Replicate lip-sync, fall back to static photo
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
            if p.exists():
                avatar_path = p
                break

    use_lipsync        = False
    has_static_avatar  = False
    if repl_api_key and avatar_path:
        use_lipsync = replicate_wav2lip(avatar_path, mp3, repl_api_key, lipsync_mp4)
        if use_lipsync:
            # Generate circle mask + ring overlay for ffmpeg compositing
            make_circle_mask(circle_d, mask_png)
            make_avatar_ring_only(fonts, circle_d).save(str(ring_png))
            print("  Circle mask + ring overlay ready.")

    if not use_lipsync:
        av_overlay = make_avatar_overlay(fonts) if avatar_path else None
        has_static_avatar = av_overlay is not None
        if has_static_avatar:
            av_overlay.save(str(avatar_png))
            print("  Static avatar overlay saved.")

    # 5. Compose final video
    WIN_OUT.mkdir(parents=True, exist_ok=True)
    out_win    = WIN_OUT / f"anchor_{TODAY}.mp4"
    out_local  = ROOT / "anchor_video.mp4"
    tmp_silent = TMP / "silent.mp4"
    ass_esc    = str(ass).replace("\\", "/").replace(":", "\\:")
    panel_h    = 680

    print("  Composing studio video...")

    # ── Pass 1: compose visual layers → silent video ───────────────────────────
    if use_lipsync:
        # Inputs: [0]=lipsync, [1]=circle_mask, [2]=bg, [3]=ring, [4]=topbar, [5]=bottompanel
        # alphamerge requires both inputs same size — scale mask to match lipsync frame
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
            "-i",    str(lipsync_mp4),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(mask_png),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(bg_png),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(ring_png),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(top_png),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(bot_png),
            "-filter_complex", vf,
            "-map", "[vout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-r", "30", "-pix_fmt", "yuv420p", "-t", f"{dur:.2f}",
            str(tmp_silent),
        ]
    elif has_static_avatar:
        # Inputs: [0]=bg, [1]=avatar_overlay, [2]=topbar, [3]=bottompanel
        vf = (
            f"[0:v][1:v]overlay=0:0[v1];"
            f"[v1][2:v]overlay=0:0[v2];"
            f"[v2][3:v]overlay=0:{H - panel_h}[v3];"
            f"[v3]subtitles={ass_esc}[vout]"
        )
        cmd1 = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(bg_png),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(avatar_png),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(top_png),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(bot_png),
            "-filter_complex", vf,
            "-map", "[vout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-r", "30", "-pix_fmt", "yuv420p",
            str(tmp_silent),
        ]
    else:
        # No avatar at all
        vf = (
            f"[0:v][1:v]overlay=0:0[v1];"
            f"[v1][2:v]overlay=0:{H - panel_h}[v2];"
            f"[v2]subtitles={ass_esc}[vout]"
        )
        cmd1 = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(bg_png),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(top_png),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(bot_png),
            "-filter_complex", vf,
            "-map", "[vout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-r", "30", "-pix_fmt", "yuv420p",
            str(tmp_silent),
        ]

    r1 = subprocess.run(cmd1, capture_output=True, text=True)
    if r1.returncode != 0:
        print("FFmpeg pass-1 error:", r1.stderr[-1500:])
        raise SystemExit(1)

    # ── Pass 2: add Lily voice + music bed ────────────────────────────────────
    if has_music and (TMP / "music.wav").exists():
        af   = "[0:a]volume=1.0[v];[1:a]volume=0.13[m];[v][m]amix=inputs=2:duration=first[aout]"
        cmd2 = [
            "ffmpeg", "-y",
            "-i", str(mp3), "-i", str(music), "-i", str(tmp_silent),
            "-filter_complex", af,
            "-map", "2:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out_win),
        ]
    else:
        cmd2 = [
            "ffmpeg", "-y",
            "-i", str(mp3), "-i", str(tmp_silent),
            "-map", "1:v", "-map", "0:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out_win),
        ]
    r2 = subprocess.run(cmd2, capture_output=True, text=True)
    if r2.returncode != 0:
        print("FFmpeg pass-2 error:", r2.stderr[-1000:])
        raise SystemExit(1)

    shutil.copy(str(out_win), str(out_local))

    # Copy to Windows Desktop so it's ready to upload manually
    WIN_DESKTOP = Path("/path/to/local/Desktop/catalyst-edge/social")
    if WIN_DESKTOP.exists():
        dest = WIN_DESKTOP / f"anchor_{TODAY}.mp4"
        shutil.copy(str(out_win), str(dest))
        print(f"  Copied to Windows Desktop: {dest.name}")
        # Write a "READY" marker so the correct file is obvious
        (WIN_DESKTOP / f"UPLOAD_TODAY_anchor_{TODAY}.txt").write_text(
            f"YouTube Shorts / TikTok anchor upload — {TODAY_DISPLAY}\n"
            f"File: anchor_{TODAY}.mp4\n"
            f"Title: {TODAY_DISPLAY} Top SEC Catalyst Pick\n"
            f"Description: Free daily stock picks from 300+ SEC filings.\n"
            f"Newsletter: https://catalystedge.agency\n"
            f"Live Scanner: https://catalystedgescanner.com\n"
            f"Cerebro HUD: https://catalystedge.agency/cerebro/\n"
            f"Talk to AI: https://catalystedge.agency\n"
            f"Pricing: https://catalystedge.agency/pricing/\n"
            f"#stocks #investing #SEC #fintwit #YouTubeShorts\n",
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
