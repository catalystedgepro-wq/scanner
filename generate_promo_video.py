#!/usr/bin/env python3
"""generate_promo_video.py — Generate Catalyst Edge promo videos via Replicate API.

Uses minimax/video-01 text-to-video model. No browser needed.
Reads today's picks from newsletter_picks.json to customize the prompt.
Saves to social/ directory for distribution.

Requires REPLICATE_API_KEY in .sec_email_env.

Usage:
  python3 generate_promo_video.py
  python3 generate_promo_video.py --style cinematic
  python3 generate_promo_video.py --style social-hook
  python3 generate_promo_video.py --style brand-story
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
SOCIAL_DIR = ROOT / "social"
SOCIAL_DIR.mkdir(exist_ok=True)
TODAY = dt.date.today().isoformat()

API_URL = "https://api.replicate.com/v1/models/minimax/video-01/predictions"


def _get_api_key() -> str:
    key = os.environ.get("REPLICATE_API_KEY", "").strip()
    if not key:
        env_file = ROOT / ".sec_email_env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("REPLICATE_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        print("generate_promo_video: REPLICATE_API_KEY not set — skipping")
        raise SystemExit(0)
    return key


def _load_picks() -> dict:
    p = ROOT / "newsletter_picks.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _build_prompt(style: str, picks: dict) -> str:
    top_pick = picks.get("top_pick", "CATALYST")
    top5 = picks.get("top5_tickers", [])[:5]
    ticker_str = ", ".join(top5) if top5 else "top SEC filings"

    prompts = {
        "social-hook": (
            "Extreme close-up of a glowing stock market dashboard with green numbers rapidly scrolling "
            "upward on dark screens. Cinematic shallow depth of field. Amber and cyan light reflecting "
            "off glass surfaces. Camera pulls back to reveal multiple monitors in a dark professional "
            "trading room. Gold and navy color palette. Dramatic lighting with lens flares. "
            "Hyper-realistic, 4K quality, moody atmospheric cinematic style."
        ),
        "cinematic": (
            "Camera descends through clouds at golden hour revealing a vast digital landscape. "
            "Floating holographic documents glow with amber light at their edges. Data streams flow "
            "like stars in hyperspace with ticker symbols visible. Dramatic orchestral atmosphere. "
            "Deep navy and gold color palette. Anamorphic lens characteristics with subtle flare. "
            "Cinematic letterbox composition, film grain, professional color grading."
        ),
        "brand-story": (
            "Documentary style: morning light streaming through window onto laptop screen showing "
            "financial data. Match cut to abstract data visualization — hundreds of documents being "
            "scanned and sorted. Gold and navy color palette. Clean professional environment. "
            "Split screen transition from raw data to organized ranked list. "
            "Warm morning tones, natural lighting, shallow depth of field."
        ),
        "data-flow": (
            "Abstract visualization of data flowing through a neural network. Glowing golden nodes "
            "connected by luminous lines on dark navy background. Particles of light streaming "
            "between connection points. Slow camera orbit around the network structure. "
            "Deep blue and gold color palette. Cinematic shallow depth of field with bokeh. "
            "Futuristic, clean, professional atmosphere."
        ),
    }

    return prompts.get(style, prompts["social-hook"])


def submit_prediction(api_key: str, prompt: str) -> dict:
    payload = json.dumps({
        "input": {
            "prompt": prompt,
            "prompt_optimizer": True,
        }
    }).encode()

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


def poll_prediction(api_key: str, prediction_id: str, max_wait: int = 600) -> str | None:
    poll_url = f"https://api.replicate.com/v1/predictions/{prediction_id}"
    start = time.time()

    while time.time() - start < max_wait:
        time.sleep(10)
        req = urllib.request.Request(poll_url, headers={"Authorization": f"Bearer {api_key}"})
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        status = result["status"]
        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] {status}")

        if status == "succeeded":
            output = result.get("output", "")
            return output if isinstance(output, str) else None
        elif status in ("failed", "canceled"):
            print(f"  Error: {result.get('error', 'unknown')}")
            return None

    print("  Timeout waiting for video generation")
    return None


def download_video(url: str, save_path: Path) -> bool:
    try:
        urllib.request.urlretrieve(url, str(save_path))
        size = save_path.stat().st_size
        print(f"  Saved: {save_path} ({size / 1024 / 1024:.1f} MB)")
        return True
    except Exception as e:
        print(f"  Download failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate Catalyst Edge promo video")
    parser.add_argument("--style", choices=["social-hook", "cinematic", "brand-story", "data-flow"],
                        default="social-hook")
    parser.add_argument("--no-wait", action="store_true", help="Submit and exit without waiting")
    args = parser.parse_args()

    api_key = _get_api_key()
    picks = _load_picks()
    prompt = _build_prompt(args.style, picks)

    print(f"generate_promo_video: submitting {args.style} video...")
    print(f"  Prompt: {prompt[:120]}...")

    try:
        result = submit_prediction(api_key, prompt)
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:300]
        print(f"  Submit failed: {e.code} — {err}")
        return 1

    pred_id = result.get("id", "")
    print(f"  Prediction ID: {pred_id}")
    print(f"  Status: {result.get('status')}")

    if args.no_wait:
        print(f"  View: https://replicate.com/p/{pred_id}")
        # Save prediction ID for later retrieval
        meta_path = SOCIAL_DIR / f"video_prediction_{TODAY}.json"
        meta_path.write_text(json.dumps({
            "id": pred_id,
            "style": args.style,
            "date": TODAY,
            "prompt": prompt,
            "status": "submitted",
        }, indent=2), encoding="utf-8")
        print(f"  Metadata: {meta_path}")
        return 0

    print("  Waiting for generation (up to 10 min)...")
    video_url = poll_prediction(api_key, pred_id)

    if video_url:
        save_path = SOCIAL_DIR / f"promo_{args.style}_{TODAY}.mp4"
        if download_video(video_url, save_path):
            print(f"\n  Video ready: {save_path}")
            return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
