#!/usr/bin/env bash
# setup_social_profiles.sh — One-time setup for all social media Playwright profiles.
#
# Creates persistent browser profiles at /mnt/c/playwright_tools/ and opens
# a login page for each platform so you can sign in with Google (opensource@example.com).
#
# Run from WSL with Windows filesystem mounted:
#   bash setup_social_profiles.sh
#   bash setup_social_profiles.sh --only x
#   bash setup_social_profiles.sh --only instagram
#   bash setup_social_profiles.sh --only tiktok
#   bash setup_social_profiles.sh --only youtube
#   bash setup_social_profiles.sh --only beehiiv

set -euo pipefail

PROFILE_ROOT="/mnt/c/playwright_tools"

# Check Windows mount
if [[ ! -d "/mnt/c/Windows" ]]; then
  echo "ERROR: Windows filesystem not mounted at /mnt/c/"
  echo "Run this from WSL when Windows is running."
  echo "Try: sudo mount -t drvfs C: /mnt/c"
  exit 1
fi

# Check Node.js
NODE=""
for candidate in \
    "/mnt/c/Program Files/nodejs/node.exe" \
    "/path/to/local/AppData/Local/Programs/nodejs/node.exe" \
    "$(command -v node 2>/dev/null || true)"; do
  if [[ -n "$candidate" && -f "$candidate" ]]; then
    NODE="$candidate"
    break
  fi
done

if [[ -z "$NODE" ]]; then
  echo "ERROR: Node.js not found. Install from https://nodejs.org/"
  exit 1
fi

echo "Using Node.js: $NODE"
echo "Profile root: $PROFILE_ROOT"
echo ""

# Ensure Playwright is installed
cd /home/operator/.openclaw/workspace
if [[ ! -d "node_modules/playwright" ]]; then
  npm install playwright 2>/dev/null || true
fi

# Parse --only flag
ONLY="${1:-}"
ONLY_PLATFORM="${2:-}"
if [[ "$ONLY" == "--only" && -n "$ONLY_PLATFORM" ]]; then
  PLATFORMS=("$ONLY_PLATFORM")
else
  PLATFORMS=("x" "reddit" "linkedin" "instagram" "tiktok" "youtube")
fi

# Platform configs
declare -A URLS
URLS[x]="https://x.com/login"
URLS[reddit]="https://www.reddit.com/login/"
URLS[linkedin]="https://www.linkedin.com/login"
URLS[instagram]="https://www.instagram.com/accounts/login/"
URLS[tiktok]="https://www.tiktok.com/login"
URLS[youtube]="https://accounts.google.com/ServiceLogin?service=youtube"

declare -A PROFILE_DIRS
PROFILE_DIRS[x]="$PROFILE_ROOT/x_profile"
PROFILE_DIRS[reddit]="$PROFILE_ROOT/reddit_profile"
PROFILE_DIRS[linkedin]="$PROFILE_ROOT/linkedin_profile"
PROFILE_DIRS[instagram]="$PROFILE_ROOT/instagram_profile"
PROFILE_DIRS[tiktok]="$PROFILE_ROOT/tiktok_profile"
PROFILE_DIRS[youtube]="$PROFILE_ROOT/youtube_profile"

for platform in "${PLATFORMS[@]}"; do
  url="${URLS[$platform]:-}"
  profile="${PROFILE_DIRS[$platform]:-}"
  if [[ -z "$url" || -z "$profile" ]]; then
    echo "Unknown platform: $platform"
    continue
  fi

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Setting up: $platform"
  echo "Profile: $profile"
  echo "URL: $url"
  echo ""

  mkdir -p "$profile"

  # Convert WSL path to Windows path for Windows Node.exe (double backslashes for JS)
  if [[ "$NODE" == *".exe" ]]; then
    win_profile=$(wslpath -w "$profile" | sed 's/\\/\\\\/g')
  else
    win_profile="$profile"
  fi

  # Launch HEADED stealth browser so user can log in without anti-bot blocks.
  # The stealth_launcher hides webdriver flag, masks WebGL/canvas/plugin
  # fingerprints, and pins a real-Chrome user-agent. Without this, X /
  # TikTok / YouTube intercept the login form with captchas or refuse
  # auth entirely.
  "$NODE" -e "
    const { launchStealthContext } = require('/home/operator/.openclaw/workspace/stealth_launcher.cjs');
    (async () => {
      const context = await launchStealthContext('${win_profile}', {
        headless: false,
        viewport: { width: 1280, height: 800 },
      });
      const page = await context.newPage();
      await page.goto('${url}', { waitUntil: 'domcontentloaded', timeout: 60000 });
      console.log('');
      console.log('=== LOGIN TO ${platform^^} ===');
      console.log('Sign in with Google (opensource@example.com)');
      console.log('When done, close the browser window to save the session.');
      console.log('');
      await new Promise(resolve => context.on('close', resolve));
      console.log('${platform} session saved!');
    })().catch(e => { console.error(e.message); process.exit(1); });
  " || echo "WARNING: $platform setup failed"

  echo ""
done

echo ""
echo "All profiles set up at: $PROFILE_ROOT"
echo "Sessions will persist until platform invalidates them (~7-14 days)."
echo ""
echo "To refresh a single profile later:"
echo "  bash setup_social_profiles.sh --only x"
echo "  bash setup_social_profiles.sh --only instagram"
