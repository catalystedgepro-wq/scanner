#!/usr/bin/env python3
"""
generate_voice_content.py — Voice AI content pipeline for Catalyst Edge.

Reads pipeline data and generates:
  1. Voice-over MP3 for daily market scan (60-90 second clip)
  2. Script text files for each platform (YouTube Shorts, TikTok, Instagram Reels)
  3. Telegram voice message ready to send

Uses Edge TTS (free, unlimited, zero latency) as primary.
Falls back to ElevenLabs when quota is available for premium emotional delivery.

Usage:
    python3 generate_voice_content.py                    # generate all
    python3 generate_voice_content.py --platform tiktok  # specific platform
    python3 generate_voice_content.py --voice brian      # specific voice
    python3 generate_voice_content.py --elevenlabs       # use ElevenLabs (if quota)
    python3 generate_voice_content.py --dry-run          # scripts only, no audio

Output:
    social/voice_daily_{date}.mp3          — Full scan voice-over
    social/voice_hook_{date}.mp3           — 15s hook clip (for Reels/TikTok intro)
    social/voice_squeeze_{date}.mp3        — Squeeze radar voice-over
    social/voice_script_{date}.txt         — Full script
    social/tiktok_script_{date}.txt        — TikTok-optimized script
    social/youtube_short_script_{date}.txt — YouTube Shorts script
"""

import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).parent
SOCIAL_DIR = WORKSPACE / "social"
PICKS_JSON = WORKSPACE / "newsletter_picks.json"
SQUEEZE_CSV = WORKSPACE / "squeeze_candidates.csv"
CONVERGENCE_CSV = WORKSPACE / "convergence_alerts.csv"

# Voice mapping
VOICES = {
    "brian": "en-US-BrianNeural",       # Confident, clear
    "andrew": "en-US-AndrewNeural",     # Natural, warm
    "guy": "en-US-GuyNeural",           # Deep, authoritative
    "christopher": "en-US-ChristopherNeural",  # Energetic
    "roger": "en-US-RogerNeural",       # Mature, trustworthy
    "eric": "en-US-EricNeural",         # Professional
}
DEFAULT_VOICE = "andrew"

DATE_STR = datetime.now().strftime("%Y-%m-%d")
DATE_HUMAN = datetime.now().strftime("%B %d")


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
    reader = csv.DictReader(lines)
    return list(reader)


def ticker_spoken(ticker):
    """Convert ticker to spoken form: AAOI → A-A-O-I, AB → A-B."""
    if len(ticker) <= 2:
        return " ".join(ticker)
    if len(ticker) <= 4:
        return " ".join(ticker)
    return ticker


def build_daily_script(picks, squeeze_rows, convergence_rows):
    """Build the 60-90 second daily scan voice-over script."""
    total = picks.get("total_combined", 0)
    top5 = picks.get("top5_tickers", [])[:5]
    g = int(picks.get("gapper_count", 0))
    v = int(picks.get("value_count", 0))
    m = int(picks.get("moat_count", 0))

    coiled = [r for r in squeeze_rows if r.get("stage") in ("COILED", "IGNITION")][:3]
    conv = [r for r in convergence_rows if r.get("conviction_level") in ("HIGH", "ELEVATED")][:3]

    lines = []

    # Hook (first 3 seconds)
    lines.append(f"Just scanned {total} S-E-C filings before the open.")
    lines.append(f"Here's what the market doesn't know yet.")
    lines.append("")

    # Top picks
    top_spoken = ", ".join(ticker_spoken(t) for t in top5[:3])
    lines.append(f"Today's top picks: {top_spoken}.")
    lines.append(f"We found {g} gapper setups, {v} deep value plays, and {m} wide moat positions.")
    lines.append("")

    # Squeeze radar
    if coiled:
        lines.append("The squeeze radar is flashing.")
        for r in coiled:
            si = r.get("short_pct_float", "")
            ticker = ticker_spoken(r.get("ticker", "?"))
            stage = r.get("stage", "COILED")
            if si:
                lines.append(f"{ticker} is {stage.lower()} with {si} percent short interest.")
            else:
                lines.append(f"{ticker} is {stage.lower()} and showing catalyst pressure.")
        lines.append("")

    # Convergence
    if conv:
        lines.append("Multiple signals are converging.")
        r = conv[0]
        signals = (r.get("signals_fired", "") or "").replace(";", ", ")
        ticker = ticker_spoken(r.get("ticker", "?"))
        lines.append(f"{ticker} has {signals} all firing at once. Score: {r.get('convergence_score', '?')}.")
        lines.append("")

    # CTA
    lines.append("Full scan with charts and scoring at catalyst edge dot agency.")
    lines.append("Link in bio. This is not financial advice.")

    return "\n".join(lines)


def build_hook_script(picks, squeeze_rows):
    """Build 15-second hook for Reels/TikTok intro."""
    total = picks.get("total_combined", 0)
    top = picks.get("top_pick", "")
    coiled = [r for r in squeeze_rows if r.get("stage") in ("COILED", "IGNITION")]

    lines = []
    if coiled:
        ticker = ticker_spoken(coiled[0].get("ticker", "?"))
        si = coiled[0].get("short_pct_float", "?")
        lines.append(f"{ticker} is about to squeeze.")
        lines.append(f"{si} percent short interest. Catalyst just hit.")
        lines.append("Here's what I found scanning S-E-C filings today.")
    else:
        lines.append(f"I scanned {total} S-E-C filings this morning.")
        if top:
            lines.append(f"Top pick: {ticker_spoken(top)}.")
        lines.append("Here's what Wall Street hasn't priced in yet.")

    return "\n".join(lines)


def build_squeeze_script(squeeze_rows):
    """Build squeeze radar deep-dive clip."""
    coiled = [r for r in squeeze_rows if r.get("stage") in ("COILED", "IGNITION")][:5]
    if not coiled:
        return "No squeeze setups showing today. The radar is quiet."

    lines = []
    lines.append(f"Squeeze radar: {len(coiled)} setups are coiled and ready.")
    lines.append("")

    for r in coiled:
        ticker = ticker_spoken(r.get("ticker", "?"))
        si = r.get("short_pct_float", "?")
        dtc = r.get("days_to_cover", "?")
        stage = r.get("stage", "COILED")

        lines.append(f"{ticker}. {stage}.")
        if si and si != "?":
            lines.append(f"Short interest at {si} percent.")
        if dtc and dtc != "?":
            lines.append(f"Days to cover: {dtc}.")
        lines.append("")

    lines.append("Full data and live scanner at catalyst edge dot agency.")
    return "\n".join(lines)


def build_tiktok_script(picks, squeeze_rows, convergence_rows):
    """TikTok-optimized: punchy, fast, under 60 seconds."""
    total = picks.get("total_combined", 0)
    top5 = picks.get("top5_tickers", [])[:3]
    coiled = [r for r in squeeze_rows if r.get("stage") in ("COILED", "IGNITION")][:2]

    lines = []
    lines.append("Stop scrolling.")
    lines.append(f"I just scanned {total} S-E-C filings.")
    lines.append("")

    if coiled:
        r = coiled[0]
        ticker = ticker_spoken(r.get("ticker", "?"))
        si = r.get("short_pct_float", "?")
        lines.append(f"{ticker} is about to pop.")
        if si and si != "?":
            lines.append(f"{si} percent of the float is shorted.")
        lines.append("And a catalyst filing just dropped.")
        lines.append("")

    if top5:
        spoken = ", ".join(ticker_spoken(t) for t in top5)
        lines.append(f"Top picks today: {spoken}.")
        lines.append("")

    lines.append("I run this scan every morning.")
    lines.append("Follow for the next one.")
    lines.append("Not financial advice.")

    return "\n".join(lines)


def build_youtube_short_script(picks, squeeze_rows, convergence_rows):
    """YouTube Shorts: slightly longer, more educational."""
    total = picks.get("total_combined", 0)
    top5 = picks.get("top5_tickers", [])[:5]
    g = int(picks.get("gapper_count", 0))
    v = int(picks.get("value_count", 0))
    coiled = [r for r in squeeze_rows if r.get("stage") in ("COILED", "IGNITION")][:3]
    conv = [r for r in convergence_rows if r.get("conviction_level") in ("HIGH", "ELEVATED")][:2]

    lines = []
    lines.append(f"Every morning I scan over {total} S-E-C filings.")
    lines.append("Looking for catalysts the market hasn't priced in.")
    lines.append("")
    lines.append(f"Today: {g} gapper setups and {v} deep value plays.")
    lines.append("")

    if top5:
        spoken = ", ".join(ticker_spoken(t) for t in top5[:3])
        lines.append(f"Leading the scan: {spoken}.")
        lines.append("")

    if coiled:
        r = coiled[0]
        ticker = ticker_spoken(r.get("ticker", "?"))
        si = r.get("short_pct_float", "?")
        lines.append("Now the squeeze radar.")
        lines.append(f"{ticker} is coiled.")
        if si and si != "?":
            lines.append(f"Short interest sitting at {si} percent.")
        lines.append("When the catalyst hits, shorts scramble to cover.")
        lines.append("That's how squeezes start.")
        lines.append("")

    if conv:
        r = conv[0]
        ticker = ticker_spoken(r.get("ticker", "?"))
        score = r.get("convergence_score", "?")
        lines.append(f"Convergence alert: {ticker} has a score of {score}.")
        lines.append("Multiple signals all pointing the same direction.")
        lines.append("")

    lines.append("Full breakdown and live scanner at catalyst edge dot agency.")
    lines.append("Link in the description.")
    lines.append("This is not financial advice. Do your own research.")

    return "\n".join(lines)


async def generate_audio(text, output_path, voice_name=DEFAULT_VOICE, rate="+5%", pitch="+0Hz"):
    """Generate MP3 audio from text using Edge TTS."""
    try:
        import edge_tts
    except ImportError:
        print("ERROR: edge-tts not installed. Run: pip install edge-tts")
        return False

    voice_id = VOICES.get(voice_name, VOICES[DEFAULT_VOICE])
    comm = edge_tts.Communicate(text, voice_id, rate=rate, pitch=pitch)
    await comm.save(str(output_path))
    size = output_path.stat().st_size
    print(f"  Generated: {output_path.name} ({size / 1024:.0f} KB)")
    return True


async def generate_audio_elevenlabs(text, output_path, voice_id="pFZP5JQG7iQjIQuC4Bku"):
    """Generate audio using ElevenLabs API (requires quota)."""
    import urllib.request

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        print("  ERROR: ELEVENLABS_API_KEY not set")
        return False

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    data = json.dumps({
        "text": text,
        "model_id": "eleven_v3_conversational",
        "voice_settings": {
            "stability": 0.4,
            "similarity_boost": 0.8,
            "style": 0.6,
            "use_speaker_boost": True,
        },
    }).encode()

    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "xi-api-key": api_key,
            "Accept": "audio/mpeg",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio = resp.read()
            output_path.write_bytes(audio)
            print(f"  Generated (ElevenLabs): {output_path.name} ({len(audio) / 1024:.0f} KB)")
            return True
    except Exception as e:
        print(f"  ElevenLabs failed: {e}")
        return False


async def main():
    args = set(sys.argv[1:])
    dry_run = "--dry-run" in args
    use_elevenlabs = "--elevenlabs" in args
    voice = DEFAULT_VOICE

    # Parse --voice flag
    for arg in args:
        if arg.startswith("--voice="):
            voice = arg.split("=")[1]
        elif arg == "--voice" and len(sys.argv) > sys.argv.index(arg) + 1:
            voice = sys.argv[sys.argv.index(arg) + 1]

    if voice not in VOICES and not use_elevenlabs:
        print(f"Unknown voice '{voice}'. Available: {', '.join(VOICES.keys())}")
        sys.exit(1)

    # Load env
    env_file = WORKSPACE / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

    SOCIAL_DIR.mkdir(exist_ok=True)

    picks = load_picks()
    squeeze_rows = parse_csv(SQUEEZE_CSV)
    convergence_rows = parse_csv(CONVERGENCE_CSV)

    if not picks:
        print("WARNING: newsletter_picks.json empty — generating with minimal data")

    # Generate scripts
    daily_script = build_daily_script(picks, squeeze_rows, convergence_rows)
    hook_script = build_hook_script(picks, squeeze_rows)
    squeeze_script = build_squeeze_script(squeeze_rows)
    tiktok_script = build_tiktok_script(picks, squeeze_rows, convergence_rows)
    youtube_script = build_youtube_short_script(picks, squeeze_rows, convergence_rows)

    # Save scripts
    scripts = {
        f"voice_script_{DATE_STR}.txt": daily_script,
        f"tiktok_script_{DATE_STR}.txt": tiktok_script,
        f"youtube_short_script_{DATE_STR}.txt": youtube_script,
    }
    for name, content in scripts.items():
        path = SOCIAL_DIR / name
        path.write_text(content)
        print(f"Script: {path.name}")

    if dry_run:
        print("\n--- DAILY SCRIPT ---")
        print(daily_script)
        print("\n--- HOOK (15s) ---")
        print(hook_script)
        print("\n--- TIKTOK ---")
        print(tiktok_script)
        print("\n--- YOUTUBE SHORT ---")
        print(youtube_script)
        print("\nDry run complete. No audio generated.")
        return

    # Generate audio
    print(f"\nGenerating audio (voice: {voice})...")

    gen_fn = generate_audio_elevenlabs if use_elevenlabs else generate_audio

    if use_elevenlabs:
        await gen_fn(daily_script, SOCIAL_DIR / f"voice_daily_{DATE_STR}.mp3")
        await gen_fn(hook_script, SOCIAL_DIR / f"voice_hook_{DATE_STR}.mp3")
        await gen_fn(squeeze_script, SOCIAL_DIR / f"voice_squeeze_{DATE_STR}.mp3")
    else:
        await gen_fn(daily_script, SOCIAL_DIR / f"voice_daily_{DATE_STR}.mp3", voice)
        await gen_fn(hook_script, SOCIAL_DIR / f"voice_hook_{DATE_STR}.mp3", voice, rate="+8%")
        await gen_fn(squeeze_script, SOCIAL_DIR / f"voice_squeeze_{DATE_STR}.mp3", voice)

    # Send voice to Telegram
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_channel = os.environ.get("TELEGRAM_CHANNEL", "@CatalystEdgeDaily")
    voice_file = SOCIAL_DIR / f"voice_daily_{DATE_STR}.mp3"

    if tg_token and voice_file.exists():
        print(f"\nSending voice to Telegram ({tg_channel})...")
        try:
            import urllib.request
            boundary = "----VoiceBoundary"
            audio_data = voice_file.read_bytes()
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{tg_channel}\r\n'
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="voice"; filename="daily_scan.ogg"\r\n'
                f"Content-Type: audio/mpeg\r\n\r\n"
            ).encode() + audio_data + f"\r\n--{boundary}--\r\n".encode()

            req = urllib.request.Request(
                f"https://api.telegram.org/bot{tg_token}/sendVoice",
                data=body,
                method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    print("  Telegram voice message sent!")
                else:
                    print(f"  Telegram error: {result}")
        except Exception as e:
            print(f"  Telegram voice send failed: {e}")

    print(f"\nVoice content generated for {DATE_STR}.")
    print(f"Audio files in: {SOCIAL_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
