#!/usr/bin/env python3
"""generate_avatar.py — Generate Catalyst Edge anchor avatar images using Google Imagen 3.

Uses Google's free Gemini API (aistudio.google.com) to generate 7 portrait images
of a Black British female news anchor with different outfits per weekday.

Output:
    workspace/avatars/avatar.png          — base image (fallback)
    workspace/avatars/avatar_mon.png … avatar_sun.png — daily outfit rotation

Usage:
    python3 generate_avatar.py            — generate all 7 days
    python3 generate_avatar.py --day mon  — regenerate one specific day
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

try:
    from google import genai
    from google.genai import types as genai_types
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

ROOT       = Path(__file__).parent
AVATAR_DIR = ROOT / "avatars"
DAYS       = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

OUTFITS = {
    "mon": "sleek burgundy blazer, pearl earrings, natural hair in an elegant bun",
    "tue": "royal blue power suit, gold hoop earrings, hair in defined curls",
    "wed": "crisp white blazer, statement necklace, protective updo with braids",
    "thu": "deep emerald green jacket, diamond stud earrings, hair in a straight press",
    "fri": "charcoal grey blazer with subtle pinstripe, silver earrings, hair in loose waves",
    "sat": "casual chic cream blouse, small gold earrings, natural afro out",
    "sun": "rich plum blazer, bold red lip, hair in a sleek low ponytail",
}

BASE_PROMPT = (
    "Professional Black British female news anchor, early 30s, beautiful natural features, "
    "warm dark brown skin, strong confident expression, looking directly into the camera, "
    "professional studio photography lighting, soft neutral dark grey studio background, "
    "sharp focus on face, photo-realistic, 4K portrait, BBC news presenter style. "
    "She is wearing a {outfit}. "
    "Upper body portrait, professional composition, no text, no watermarks, no logos."
)


def generate_image(client, day: str) -> Path:
    out = AVATAR_DIR / (f"avatar_{day}.png" if day != "base" else "avatar.png")
    outfit = OUTFITS.get(day, OUTFITS["mon"])
    prompt = BASE_PROMPT.format(outfit=outfit)

    print(f"  [{day}] {outfit}")

    response = client.models.generate_images(
        model="imagen-3.0-generate-002",
        prompt=prompt,
        config=genai_types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="1:1",
            safety_filter_level="block_only_high",
            person_generation="allow_adult",
        ),
    )

    if not response.generated_images:
        raise RuntimeError(f"No images returned for {day}")

    image_bytes = response.generated_images[0].image.image_bytes
    out.write_bytes(image_bytes)
    print(f"  Saved: {out.name} ({out.stat().st_size // 1024} KB)")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", choices=DAYS, help="Regenerate one specific day")
    args = parser.parse_args()

    if not HAS_GOOGLE:
        print("ERROR: pip install --break-system-packages google-genai")
        sys.exit(1)

    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set.")
        print("  Get a free key at aistudio.google.com → Get API key")
        print("  Then add: GOOGLE_API_KEY=your_key  to .sec_email_env")
        sys.exit(1)

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=api_key)

    print(f"generate_avatar.py — Imagen 3 — output: {AVATAR_DIR}")

    if args.day:
        generate_image(client, args.day)
        return

    failed = []
    for day in DAYS:
        out = AVATAR_DIR / f"avatar_{day}.png"
        if out.exists():
            print(f"  [{day}] already exists — skipping (delete to regenerate)")
            continue
        try:
            generate_image(client, day)
            time.sleep(2)   # stay within free-tier rate limits
        except Exception as exc:
            print(f"  [{day}] FAILED: {exc}")
            failed.append(day)

    # Copy Monday as the generic fallback
    base = AVATAR_DIR / "avatar.png"
    mon  = AVATAR_DIR / "avatar_mon.png"
    if not base.exists() and mon.exists():
        shutil.copy(str(mon), str(base))
        print(f"  Copied avatar_mon.png → avatar.png (fallback)")

    print(f"\nDone.")
    for f in sorted(AVATAR_DIR.glob("avatar*.png")):
        print(f"  {f.name}  ({f.stat().st_size // 1024} KB)")

    if failed:
        print(f"\nFailed: {failed}")
        print("Retry with: python3 generate_avatar.py --day <day>")


if __name__ == "__main__":
    main()
