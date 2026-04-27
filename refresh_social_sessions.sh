#!/usr/bin/env bash
# refresh_social_sessions.sh — Open browser windows for manual login to each social platform.
#
# Usage:
#   bash refresh_social_sessions.sh              # refresh ALL expired sessions
#   bash refresh_social_sessions.sh instagram    # refresh only Instagram
#   bash refresh_social_sessions.sh linkedin youtube  # refresh specific platforms
#
# Each platform opens in its persistent Playwright profile (non-headless).
# Log in manually, then close the browser when done.

set -euo pipefail

PROFILES="/mnt/c/playwright_tools"

declare -A PLATFORM_URLS=(
  [instagram]="https://www.instagram.com/accounts/login/"
  [linkedin]="https://www.linkedin.com/login"
  [youtube]="https://accounts.google.com/signin/v2/identifier?service=youtube&continue=https%3A%2F%2Fstudio.youtube.com%2F"
  [tiktok]="https://www.tiktok.com/login"
  [reddit]="https://www.reddit.com/login/"
  [beehiiv]="https://app.beehiiv.com/login"
  [x]="https://x.com/i/flow/login"
)

declare -A PLATFORM_PROFILES=(
  [instagram]="instagram_profile"
  [linkedin]="linkedin_profile"
  [youtube]="youtube_profile"
  [tiktok]="tiktok_profile"
  [reddit]="reddit_profile"
  [beehiiv]="beehiiv_profile"
  [x]="x_profile"
)

refresh_platform() {
  local platform="$1"
  local profile_dir="$PROFILES/${PLATFORM_PROFILES[$platform]}"
  local url="${PLATFORM_URLS[$platform]}"

  if [[ ! -d "$profile_dir" ]]; then
    echo "Creating profile: $profile_dir"
    mkdir -p "$profile_dir"
  fi

  echo ""
  echo "════════════════════════════════════════════════════════"
  echo "  Opening $platform — log in, then close the browser"
  echo "════════════════════════════════════════════════════════"
  echo "  Profile: $profile_dir"
  echo "  URL: $url"
  echo ""

  node -e "
    const { chromium } = require('playwright');
    (async () => {
      const ctx = await chromium.launchPersistentContext('$profile_dir', {
        headless: false,
        args: ['--disable-blink-features=AutomationControlled', '--no-sandbox'],
        viewport: { width: 1280, height: 900 },
      });
      const page = await ctx.newPage();
      await page.goto('$url', { waitUntil: 'domcontentloaded', timeout: 60000 });
      console.log('Browser open. Log in manually, then close the window.');
      // Wait for user to close the browser
      await new Promise(resolve => ctx.on('close', resolve));
      console.log('$platform session saved.');
    })();
  "
}

# Determine which platforms to refresh
if [[ $# -eq 0 ]]; then
  # No args = refresh ALL that need it
  TARGETS=("instagram" "linkedin" "youtube" "tiktok" "reddit" "beehiiv")
else
  TARGETS=("$@")
fi

echo "Refreshing sessions for: ${TARGETS[*]}"
echo "Each platform opens a visible browser. Log in, then close the window."

for target in "${TARGETS[@]}"; do
  if [[ -z "${PLATFORM_URLS[$target]+x}" ]]; then
    echo "ERROR: Unknown platform '$target'. Available: ${!PLATFORM_URLS[*]}"
    continue
  fi
  refresh_platform "$target"
done

echo ""
echo "Done. All sessions refreshed."
echo "Run 'bash run_social_posts.sh' to verify posting works."
