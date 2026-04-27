#!/usr/bin/env python3
"""generate_gap_winner_video.py — AI talking-head video for gap winner folders.

For a gap winner folder in catalyst-edge/social/gap_winners/{TICKER}_{DATE}/,
generates a short-form talking-head video using:
  1. ElevenLabs TTS — converts tiktok_script.txt spoken lines to MP3 audio
  2. D-ID Talks API — lip-syncs the audio onto an avatar image → MP4

Output written to the winner folder:
  tiktok_video.mp4  — ready to upload to TikTok / Reels / Shorts

Fallback: if API keys are missing, skips gracefully with a clear message.

Required env vars (same as daily pipeline):
  ELEVENLABS_API_KEY
  D_ID_API_KEY

Optional:
  ELEVENLABS_VOICE_ID  (default: pFZP5JQG7iQjIQuC4Bku — Lily, British velvety)
  D_ID_AGENT_ID        (if set, fetches presenter from D-ID Studio agent)

Avatar image (falls back in order):
  workspace/avatars/avatar.png
  workspace/avatars/avatar_mon.png  (etc.)

Usage:
  python3 generate_gap_winner_video.py --ticker UGRO
  python3 generate_gap_winner_video.py --ticker UGRO --date 2026-03-25
  python3 generate_gap_winner_video.py          # process all folders missing a video
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
import datetime as dt
from pathlib import Path

ROOT        = Path(__file__).parent
WINNERS_DIR = Path("/path/to/local/Desktop/catalyst-edge/social/gap_winners")
AVATAR_DIR  = ROOT / "avatars"

EL_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pFZP5JQG7iQjIQuC4Bku")  # Lily


# ── Script text extraction ────────────────────────────────────────────────────

def extract_spoken(tiktok_script: str) -> str:
    """Pull only the [SPOKEN] lines from the TikTok script — what gets voiced."""
    spoken_lines: list[str] = []
    in_spoken = False
    for line in tiktok_script.splitlines():
        stripped = line.strip()
        if stripped.startswith("[SPOKEN]"):
            in_spoken = True
            after = stripped[len("[SPOKEN]"):].strip().lstrip(":").strip()
            if after:
                spoken_lines.append(after)
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_spoken = False
        elif in_spoken and stripped:
            spoken_lines.append(stripped)
    # Also grab the CAPTION section (great for voiceover hook)
    caption_match = re.search(r"CAPTION FOR POST:\s*(.+)", tiktok_script)
    return " ".join(spoken_lines).strip()


# ── ElevenLabs TTS ────────────────────────────────────────────────────────────

def elevenlabs_tts(text: str, api_key: str, out_path: Path) -> bool:
    """Convert text to MP3 via ElevenLabs API. Returns True on success."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE_ID}"
    payload = json.dumps({
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.82},
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "xi-api-key":   api_key,
        "Content-Type": "application/json",
        "Accept":       "audio/mpeg",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            out_path.write_bytes(resp.read())
        mb = out_path.stat().st_size / 1e6
        print(f"  ElevenLabs TTS ✓  {mb:.2f} MB → {out_path.name}")
        return True
    except urllib.error.HTTPError as e:
        print(f"  ElevenLabs TTS ✗  HTTP {e.code}: {e.read()[:300]}")
        return False
    except Exception as e:
        print(f"  ElevenLabs TTS ✗  {e}")
        return False


# ── D-ID helpers ──────────────────────────────────────────────────────────────

def _did_auth(api_key: str) -> str:
    # D-ID stores credentials as base64(email):api_key.
    # For the Authorization header: Basic base64("base64(email):api_key")
    if api_key.startswith("Basic ") or api_key.startswith("Bearer "):
        return api_key
    cred = base64.b64encode(api_key.encode()).decode()
    return f"Basic {cred}"


def _did_req(method: str, endpoint: str, api_key: str,
             data: bytes | None = None, content_type: str = "application/json") -> dict:
    url = f"https://api.d-id.com{endpoint}"
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": _did_auth(api_key),
        "Content-Type":  content_type,
        "Accept":        "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"D-ID {method} {endpoint} → HTTP {e.code}: {body[:400]}")


def did_get_agent_presenter(agent_id: str, api_key: str) -> dict | None:
    """Fetch presenter_id and driver_id from a D-ID Studio agent."""
    try:
        result = _did_req("GET", f"/agents/{agent_id}", api_key)
        presenter = result.get("presenter") or {}
        pid = presenter.get("presenter_id", "")
        did = presenter.get("driver_id", "")
        ptype = presenter.get("type", "")
        if pid:
            print(f"  D-ID agent presenter: {pid} (type={ptype})")
            return {"presenter_id": pid, "driver_id": did, "type": ptype}
    except Exception as e:
        print(f"  Could not fetch agent presenter: {e}")
    return None


def did_create_clip(presenter_id: str, driver_id: str, spoken_text: str,
                    api_key: str, el_api_key: str = "") -> str:
    """POST /clips — returns clip_id."""
    if el_api_key:
        script = {
            "type": "text",
            "input": spoken_text,
            "provider": {
                "type": "elevenlabs",
                "voice_id": EL_VOICE_ID,
                "voice_config": {"stability": 0.45, "similarity_boost": 0.82},
            },
        }
    else:
        script = {"type": "text", "input": spoken_text,
                  "provider": {"type": "microsoft", "voice_id": "en-US-GuyNeural"}}

    payload = json.dumps({
        "presenter_id": presenter_id,
        "driver_id":    driver_id,
        "script":       script,
        "config":       {"result_format": "mp4", "stitch": True},
        "background":   {},
    }).encode()
    result  = _did_req("POST", "/clips", api_key, data=payload)
    clip_id = result["id"]
    print(f"  D-ID clip created: {clip_id}")
    return clip_id


def did_poll(job_id: str, api_key: str, timeout: int = 480,
             endpoint: str = "/clips") -> str:
    """Poll /clips/{id} or /talks/{id} until done. Returns result_url."""
    deadline = time.time() + timeout
    print(f"  Polling D-ID...", end=" ", flush=True)
    while time.time() < deadline:
        result = _did_req("GET", f"{endpoint}/{job_id}", api_key)
        status = result.get("status", "")
        if status == "done":
            url = result.get("result_url", "")
            print("done")
            return url
        if status == "error":
            raise RuntimeError(f"D-ID job failed: {result.get('error', result)}")
        print(".", end="", flush=True)
        time.sleep(10)
    raise TimeoutError(f"D-ID job timed out after {timeout}s")


def did_download(url: str, dest: Path) -> None:
    urllib.request.urlretrieve(url, str(dest))
    print(f"  Downloaded: {dest.stat().st_size / 1e6:.1f} MB → {dest.name}")


# ── Avatar finder ─────────────────────────────────────────────────────────────

def find_avatar() -> Path | None:
    dow = dt.date.today().strftime("%a").lower()   # mon, tue…
    candidates = [
        AVATAR_DIR / f"avatar_{dow}.png",
        AVATAR_DIR / f"avatar_{dow}.jpg",
        AVATAR_DIR / "avatar.png",
        AVATAR_DIR / "avatar.jpg",
        AVATAR_DIR / "avatar_mon.png",
        AVATAR_DIR / "avatar_mon.jpg",
    ]
    for p in candidates:
        if p.exists():
            return p
    # Any image in the avatars dir
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        for p in AVATAR_DIR.glob(ext):
            return p
    return None


# ── Core: generate video for one winner folder ────────────────────────────────

def generate_video(folder: Path) -> bool:
    """Generate tiktok_video.mp4 in the given winner folder. Returns True on success."""
    out_mp4    = folder / "tiktok_video.mp4"
    script_txt = folder / "tiktok_script.txt"
    summary_p  = folder / "summary.json"

    if out_mp4.exists():
        print(f"  {folder.name}: video already exists — skipping")
        return True

    if not script_txt.exists():
        print(f"  {folder.name}: no tiktok_script.txt — skipping")
        return False

    el_key  = os.environ.get("ELEVENLABS_API_KEY", "")
    did_key = os.environ.get("D_ID_API_KEY", "")

    if not did_key:
        print(f"  {folder.name}: D_ID_API_KEY not set — cannot generate video")
        return False

    spoken = extract_spoken(script_txt.read_text(encoding="utf-8"))
    if not spoken:
        print(f"  {folder.name}: no spoken text found in script")
        return False

    print(f"\n→ Generating video for {folder.name}")
    print(f"  Script: {len(spoken)} chars")

    agent_id = os.environ.get("D_ID_AGENT_ID", "")

    # Get presenter from D-ID Studio agent
    presenter = None
    if agent_id:
        presenter = did_get_agent_presenter(agent_id, did_key)

    if not presenter:
        print(f"  D_ID_AGENT_ID not set or agent fetch failed — cannot create clip")
        return False

    # Create clip using agent's presenter
    try:
        clip_id = did_create_clip(
            presenter["presenter_id"], presenter["driver_id"],
            spoken, did_key, el_api_key=el_key,
        )
    except Exception as e:
        print(f"  D-ID create_clip failed: {e}")
        return False

    # Poll until done
    try:
        result_url = did_poll(clip_id, did_key, endpoint="/clips")
    except Exception as e:
        print(f"  D-ID poll failed: {e}")
        return False

    # Download
    try:
        did_download(result_url, out_mp4)
    except Exception as e:
        print(f"  D-ID download failed: {e}")
        return False

    # Update summary.json
    if summary_p.exists():
        try:
            data = json.loads(summary_p.read_text(encoding="utf-8"))
            data["tiktok_video"] = str(out_mp4)
            data["video_generated"] = dt.date.today().isoformat()
            summary_p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    print(f"  ✓ Video ready: {out_mp4}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Ticker symbol")
    parser.add_argument("--date",   help="Alert date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    if not WINNERS_DIR.exists():
        print("generate_gap_winner_video: winners directory not found")
        return 1

    if args.ticker:
        ticker   = args.ticker.upper()
        date_str = args.date or dt.date.today().isoformat()
        folder   = WINNERS_DIR / f"{ticker}_{date_str}"
        if not folder.exists():
            # Try any date for this ticker
            matches = sorted(WINNERS_DIR.glob(f"{ticker}_*"), reverse=True)
            if not matches:
                print(f"generate_gap_winner_video: no folder found for {ticker}")
                return 1
            folder = matches[0]
            print(f"  Using most recent folder: {folder.name}")
        ok = generate_video(folder)
        return 0 if ok else 1

    # No ticker specified — process all folders missing a video
    folders = sorted(WINNERS_DIR.glob("*_*"))
    if not folders:
        print("generate_gap_winner_video: no winner folders found")
        return 0

    generated = 0
    for folder in folders:
        if folder.is_dir() and not (folder / "tiktok_video.mp4").exists():
            if generate_video(folder):
                generated += 1

    print(f"\ngenerate_gap_winner_video: {generated} video(s) generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
