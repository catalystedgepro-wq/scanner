#!/usr/bin/env python3
"""generate_higgsfield_video.py — Automate Seedance 2.0 video creation on Higgsfield.

Uses Playwright to:
1. Navigate to Higgsfield's Seedance 2.0 video creation page
2. Authenticate via Google (opensource@example.com)
3. Paste a pre-generated cinematic prompt
4. Generate and download the video
5. Save to social/ directory for distribution

Requires:
  - Playwright installed: npx playwright install chromium
  - Browser profile with active Higgsfield session (or Google auth)

Usage:
  python3 generate_higgsfield_video.py [--prompt "custom prompt"]
  python3 generate_higgsfield_video.py --style social-hook
  python3 generate_higgsfield_video.py --style cinematic
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
SOCIAL_DIR = ROOT / "social"
SOCIAL_DIR.mkdir(exist_ok=True)
PROFILE_DIR = ROOT / "playwright-profiles" / "higgsfield"
TODAY = dt.date.today().isoformat()

HIGGSFIELD_CREATE_URL = "https://www.higgsfield.ai/flow/video/prompt?model=seedance_2_0"
HIGGSFIELD_BASE = "https://www.higgsfield.ai"

# ── Pre-built prompts for Catalyst Edge marketing ──────────────────────

PROMPTS = {
    "social-hook": (
        "Open with extreme close-up of a glowing stock ticker screen showing green numbers "
        "rapidly scrolling upward — the screen fills the entire frame with cinematic shallow "
        "depth of field. At 0.8 seconds, whip pan right to reveal a trader's focused face "
        "illuminated by multiple monitors in a dark room, amber and cyan light reflecting off "
        "their glasses. At 2 seconds, camera pulls back dramatically to reveal a massive wall "
        "of SEC filing documents morphing into a 3D data visualization — glowing nodes connected "
        "by golden lines forming a network graph. Text overlay fades in with motion blur: "
        "'CATALYST EDGE — Free SEC Scanner'. The visualization pulses with energy as new filing "
        "nodes appear. At 4 seconds, rapid montage: Form 4 document close-up, insider buying "
        "arrow pointing up, stock chart with 44.5% win rate badge glowing gold. Final frame: "
        "clean dark background with 'catalystedgescanner.com' in elegant gold typography and "
        "a subtle particle effect. Sound: electronic tension building, data processing sounds, "
        "then a satisfying bass drop at the reveal. 9:16 vertical format, 15 seconds."
    ),
    "cinematic": (
        "Cinematic establishing shot: camera descends through clouds at golden hour, revealing "
        "a vast digital landscape made of SEC filing documents floating like monoliths in space. "
        "Each document glows with amber light at its edges. At 2 seconds, camera pushes through "
        "one of the documents and enters a stream of data — ticker symbols flow past like stars "
        "in hyperspace, each tagged with catalyst labels: '8-K Event', 'Insider Buy', 'Activist "
        "Position'. Dramatic orchestral swell builds. At 5 seconds, the data stream coalesces "
        "into a single golden badge showing '44.5% Win Rate — 602 Picks Tracked'. Camera "
        "orbits the badge with shallow depth of field. At 8 seconds, dissolve to a clean "
        "composition: 'CATALYST EDGE' in cinematic serif typography on dark navy background "
        "with subtle gold particle dust. Subtitle: 'Free SEC Filing Scanner — No Signup Required'. "
        "At 12 seconds, URL 'catalystedgescanner.com' appears with elegant fade. Sound: "
        "epic orchestral score transitioning to clean electronic outro. Anamorphic lens flare "
        "at title reveal. Letterbox format 2.39:1, 15 seconds."
    ),
    "brand-story": (
        "Documentary-style opening: close-up of hands scrolling through SEC EDGAR website on "
        "a laptop, morning light streaming through window. Voiceover cadence style. At 1.5 "
        "seconds, match cut to the same data being processed — abstract visualization of 300+ "
        "filings being scanned, sorted, and scored. Gold and navy color palette throughout. "
        "At 4 seconds, split screen: left shows raw SEC filings, right shows the clean Catalyst "
        "Edge scanner output with ranked tickers. The contrast is immediate — chaos to clarity. "
        "At 7 seconds, montage of stock charts with successful picks highlighted in gold — "
        "each showing the 2%+ move our scanner predicted. Performance counter ticks up: "
        "'44.5% Win Rate'. At 10 seconds, clean dark frame with statement: 'Every morning. "
        "300+ filings. Ranked by catalyst strength. Free.' URL and newsletter CTA appear with "
        "subtle animation. Sound: ambient morning sounds, then clean electronic production "
        "music building throughout. 9:16 vertical, 15 seconds."
    ),
}


def _ensure_profile():
    """Create browser profile directory if it doesn't exist."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILE_DIR


def generate_video(prompt: str, style: str = "social-hook") -> str | None:
    """Use Playwright to generate a video on Higgsfield Seedance 2.0."""
    profile_dir = _ensure_profile()
    output_path = SOCIAL_DIR / f"seedance_{style}_{TODAY}.mp4"

    # Build the Playwright script as a Node.js file
    pw_script = f"""
const {{ chromium }} = require('playwright');

(async () => {{
    const browser = await chromium.launchPersistentContext(
        '{profile_dir}',
        {{
            headless: false,
            viewport: {{ width: 1280, height: 900 }},
            args: ['--disable-blink-features=AutomationControlled'],
        }}
    );

    const page = browser.pages()[0] || await browser.newPage();

    // Navigate to Higgsfield Seedance 2.0
    console.log('Navigating to Higgsfield...');
    await page.goto('{HIGGSFIELD_CREATE_URL}', {{ waitUntil: 'domcontentloaded', timeout: 60000 }});
    await page.waitForTimeout(5000);

    // Check if we need to authenticate
    const loginBtn = await page.$('button:has-text("Login"), a:has-text("Login"), button:has-text("Sign up")');
    if (loginBtn) {{
        console.log('AUTH_REQUIRED: Need to log in to Higgsfield');
        console.log('Run: python3 generate_higgsfield_video.py --login');
        await page.screenshot({{ path: '{SOCIAL_DIR}/higgsfield_auth_needed.png' }});
        await browser.close();
        process.exit(1);
    }}

    // Dismiss any promotion dialogs
    try {{
        const closeBtn = await page.$('[data-state="open"] button, [role="dialog"] button, button[aria-label="Close"], .close-button, [data-state="open"] [aria-label="close"]');
        if (closeBtn) {{
            await closeBtn.click();
            console.log('Dismissed promo dialog');
            await page.waitForTimeout(1000);
        }} else {{
            // Try pressing Escape to dismiss any modal
            await page.keyboard.press('Escape');
            console.log('Pressed Escape to dismiss overlay');
            await page.waitForTimeout(1000);
        }}
    }} catch (e) {{
        console.log('No dialog to dismiss: ' + e.message);
    }}

    // Wait for the prompt input area
    console.log('Waiting for prompt input...');
    try {{
        // Look for textarea or contenteditable prompt input
        const promptInput = await page.waitForSelector(
            'textarea, [contenteditable="true"], [data-testid="prompt-input"], .prompt-input, [placeholder*="prompt"], [placeholder*="Describe"]',
            {{ timeout: 15000 }}
        );

        if (promptInput) {{
            console.log('Found prompt input, filling...');
            await promptInput.click();
            await promptInput.fill(`{prompt.replace('`', '\\`').replace("'", "\\'")}`);
            console.log('Prompt filled');

            // Take a screenshot to verify
            await page.screenshot({{ path: '{SOCIAL_DIR}/higgsfield_prompt_filled.png' }});
            console.log('Screenshot: prompt_filled.png');

            // Look for generate/create button
            const generateBtn = await page.waitForSelector(
                'button:has-text("Generate"), button:has-text("Create"), button:has-text("Make"), button[type="submit"]',
                {{ timeout: 10000 }}
            );

            if (generateBtn) {{
                console.log('Clicking generate...');
                await generateBtn.click();

                // Wait for video generation (can take 1-5 minutes)
                console.log('Waiting for video generation (up to 5 min)...');
                await page.waitForSelector(
                    'video, [data-testid="video-result"], .video-player, a[download]',
                    {{ timeout: 300000 }}
                );

                // Try to find download button or video source
                const videoSrc = await page.evaluate(() => {{
                    const video = document.querySelector('video source, video[src]');
                    if (video) return video.src || video.getAttribute('src');
                    const downloadBtn = document.querySelector('a[download], button:has-text("Download")');
                    if (downloadBtn) return downloadBtn.href || 'CLICK_DOWNLOAD';
                    return null;
                }});

                if (videoSrc && videoSrc !== 'CLICK_DOWNLOAD') {{
                    console.log('VIDEO_URL:' + videoSrc);
                }} else {{
                    // Click download if available
                    const dlBtn = await page.$('a[download], button:has-text("Download")');
                    if (dlBtn) {{
                        await dlBtn.click();
                        console.log('Download clicked');
                    }}
                }}

                await page.screenshot({{ path: '{SOCIAL_DIR}/higgsfield_result.png' }});
                console.log('Screenshot: result.png');
            }}
        }}
    }} catch (e) {{
        console.log('ERROR: ' + e.message);
        await page.screenshot({{ path: '{SOCIAL_DIR}/higgsfield_error.png' }});
    }}

    await browser.close();
}})();
"""

    script_path = ROOT / "_higgsfield_playwright.cjs"
    script_path.write_text(pw_script, encoding="utf-8")

    print(f"Running Playwright for Higgsfield Seedance 2.0...")
    print(f"  Style: {style}")
    print(f"  Prompt: {prompt[:100]}...")

    try:
        result = subprocess.run(
            ["node", str(script_path)],
            capture_output=True,
            text=True,
            timeout=360,
            cwd=str(ROOT),
        )
        print(result.stdout)
        if result.stderr:
            print(f"  stderr: {result.stderr[:300]}")

        # Check for video URL in output
        for line in result.stdout.splitlines():
            if line.startswith("VIDEO_URL:"):
                video_url = line.split("VIDEO_URL:", 1)[1].strip()
                print(f"  Video URL: {video_url}")
                # Download the video
                import urllib.request
                urllib.request.urlretrieve(video_url, str(output_path))
                print(f"  Saved: {output_path}")
                return str(output_path)

        if "AUTH_REQUIRED" in result.stdout:
            print("\n  ⚠️  Higgsfield auth required.")
            print("  Run with --login to open browser for manual authentication first.")
            return None

        return None

    except subprocess.TimeoutExpired:
        print("  Timeout — video generation may still be processing on Higgsfield")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None
    finally:
        script_path.unlink(missing_ok=True)


def login_flow():
    """Open browser for manual Higgsfield authentication."""
    profile_dir = _ensure_profile()

    pw_script = f"""
const {{ chromium }} = require('playwright');

(async () => {{
    const browser = await chromium.launchPersistentContext(
        '{profile_dir}',
        {{
            headless: false,
            viewport: {{ width: 1280, height: 900 }},
            args: ['--disable-blink-features=AutomationControlled'],
        }}
    );

    const page = browser.pages()[0] || await browser.newPage();
    await page.goto('{HIGGSFIELD_BASE}', {{ waitUntil: 'domcontentloaded', timeout: 30000 }});
    await page.waitForTimeout(3000);

    console.log('Browser open — log in to Higgsfield manually.');
    console.log('Press Ctrl+C when done to save the session.');

    // Keep alive until user closes
    await new Promise(() => {{}});
}})();
"""

    script_path = ROOT / "_higgsfield_login.cjs"
    script_path.write_text(pw_script, encoding="utf-8")

    print("Opening Higgsfield for manual login...")
    print("Log in with opensource@example.com")
    print("Press Ctrl+C when authenticated to save the session.")

    try:
        subprocess.run(
            ["node", str(script_path)],
            cwd=str(ROOT),
        )
    except KeyboardInterrupt:
        print("\nSession saved.")
    finally:
        script_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Generate Catalyst Edge videos via Higgsfield Seedance 2.0")
    parser.add_argument("--style", choices=list(PROMPTS.keys()), default="social-hook",
                        help="Video style (default: social-hook)")
    parser.add_argument("--prompt", type=str, default=None,
                        help="Custom prompt (overrides --style)")
    parser.add_argument("--login", action="store_true",
                        help="Open browser for manual Higgsfield authentication")
    parser.add_argument("--list-prompts", action="store_true",
                        help="Show available pre-built prompts")
    args = parser.parse_args()

    if args.list_prompts:
        for name, prompt in PROMPTS.items():
            print(f"\n{'='*60}")
            print(f"  {name.upper()}")
            print(f"{'='*60}")
            print(prompt)
        return

    if args.login:
        login_flow()
        return

    prompt = args.prompt or PROMPTS[args.style]
    result = generate_video(prompt, style=args.style)

    if result:
        print(f"\n✅ Video saved: {result}")
        print(f"  Distribute with: python3 post_to_telegram.py / post_to_discord.py")
    else:
        print(f"\n❌ Video generation incomplete.")
        print(f"  Try: python3 generate_higgsfield_video.py --login")


if __name__ == "__main__":
    main()
