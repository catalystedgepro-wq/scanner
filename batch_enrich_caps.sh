#!/bin/bash
# batch_enrich_caps.sh — Cerebro Universe Enrichment Wrapper
#
# Populates "Mass" (Market Cap) for 10,433+ ticker nodes in entity_master.json.
# Runs in safe increments of 500 to stay under Yahoo Finance rate limits.
# Sorts by filing recency first (Inner Galaxy: active tickers enriched first).
#
# Run: bash batch_enrich_caps.sh
# Estimated time: ~6 hours (21 batches × 5-min cooldown + fetch time)
# Resume: safe to re-run — already-enriched tickers are skipped.

set -euo pipefail

BATCH_SIZE=500
TOTAL_TICKERS=10500
SLEEP_INTERVAL=300   # 5-min cooldown between batches
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$SCRIPT_DIR/universe_gravity.log"

echo "======================================================" | tee -a "$LOG"
echo "Cerebro Universe Enrichment — $(date '+%F %T')"         | tee -a "$LOG"
echo "Batch size: $BATCH_SIZE | Total: $TOTAL_TICKERS"        | tee -a "$LOG"
echo "======================================================" | tee -a "$LOG"

completed=0
for (( offset=0; offset<TOTAL_TICKERS; offset+=BATCH_SIZE )); do
    batch_num=$(( offset / BATCH_SIZE + 1 ))
    total_batches=$(( (TOTAL_TICKERS + BATCH_SIZE - 1) / BATCH_SIZE ))

    echo "" | tee -a "$LOG"
    echo "Batch $batch_num/$total_batches — offset=$offset to $((offset + BATCH_SIZE - 1)) — $(date '+%H:%M:%S')" | tee -a "$LOG"

    python3 "$SCRIPT_DIR/build_universe_gravity.py" \
        --enrich-caps \
        --cap-limit=$BATCH_SIZE \
        --offset=$offset 2>&1 | tee -a "$LOG"

    completed=$((completed + BATCH_SIZE))

    # Skip cooldown after the last batch
    if (( offset + BATCH_SIZE < TOTAL_TICKERS )); then
        echo "Cooling down ${SLEEP_INTERVAL}s to reset Yahoo Finance rate limits..." | tee -a "$LOG"
        sleep $SLEEP_INTERVAL
    fi
done

echo "" | tee -a "$LOG"
echo "Universe enrichment complete — $(date '+%F %T')" | tee -a "$LOG"

# Final gravity computation pass
echo "Running final gravity score pass..." | tee -a "$LOG"
python3 "$SCRIPT_DIR/build_universe_gravity.py" 2>&1 | tee -a "$LOG"
echo "Done." | tee -a "$LOG"
