#!/bin/bash
# deploy_scanner_generator.sh — push generate_seo_site.py to droplet AND
# trigger a regen so the next cron tick produces the same content.
#
# Without this, edits to local generate_seo_site.py never reach prod —
# the droplet's cron uses /opt/catalyst/generate_seo_site.py which is a
# separate copy. See feedback_generator_blast_radius.md.
#
# Usage:  bash ops/deploy_scanner_generator.sh

set -e
ROOT=/home/operator/.openclaw/workspace
cd "$ROOT"

# 1. Local syntax check first — fail fast before touching prod
python3 -c "import ast; ast.parse(open('generate_seo_site.py').read())" \
  && echo "  ✓ generator syntax OK" \
  || { echo "  ✗ generator syntax error — aborting"; exit 1; }

# 2. Push the generator to the droplet
echo "  → scp generate_seo_site.py → cerebro:/opt/catalyst/"
scp -q -o ConnectTimeout=8 generate_seo_site.py cerebro:/opt/catalyst/generate_seo_site.py

# 3. Push the rendered HTML as belt-and-suspenders (covers the gap until
#    the next droplet cron tick produces the same output).
echo "  → scp docs/scanner/index.html → cerebro:/opt/catalyst/docs/scanner/"
scp -q -o ConnectTimeout=8 docs/scanner/index.html cerebro:/opt/catalyst/docs/scanner/index.html

# 4. Trigger a remote regen so cron-touched files match.
echo "  → remote regen on droplet"
ssh -o ConnectTimeout=8 cerebro 'cd /opt/catalyst && /usr/bin/python3 generate_seo_site.py 2>&1 | tail -2'

# 5. Validate live HTTP shows the bake markers.
echo "  → live verification"
sleep 2
LIVE=$(curl -fsS --max-time 8 "https://catalystedgescanner.com/scanner/" || echo "")
EXPECT_MARKERS=("📉 SHORT" "Bullish-biased by default" "Bearish Primary Target")
fail=0
for m in "${EXPECT_MARKERS[@]}"; do
  cnt=$(echo "$LIVE" | grep -c "$m" || true)
  if [ "$cnt" -ge 1 ]; then
    echo "    ✓ $m ($cnt hits)"
  else
    echo "    ✗ $m MISSING"
    fail=1
  fi
done
[ $fail -eq 0 ] && echo "  ✓ deploy complete — bake survived" \
                || { echo "  ✗ deploy verified FAIL"; exit 2; }
