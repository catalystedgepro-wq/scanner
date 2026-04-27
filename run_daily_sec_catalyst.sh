#!/usr/bin/env bash
set -euo pipefail

resolve_root() {
  local real_script_dir
  real_script_dir="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
  local -a candidates=()

  if [[ -n "${CEREBRO_ROOT:-}" ]]; then
    candidates+=("${CEREBRO_ROOT}")
  fi
  if [[ -n "${PWD:-}" ]]; then
    candidates+=("${PWD}")
  fi
  candidates+=(
    "${real_script_dir}"
    "/home/operator/.openclaw/workspace"
    "/opt/catalyst"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    [[ -n "${candidate}" ]] || continue
    if [[ -f "${candidate}/api_server.py" && -d "${candidate}/docs" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  echo "Unable to resolve Cerebro root from known candidates." >&2
  return 1
}

ROOT="$(resolve_root)"
cd "$ROOT"
echo "$(date '+%F %T %Z') job_start"
echo "$(date '+%F %T %Z') root=$ROOT"

# Optional local secrets file for email delivery.
if [[ -f "$ROOT/.sec_email_env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.sec_email_env"
  set +a
fi

RUN_MODE="${CEREBRO_RUN_MODE:-daily}"
STAMP="$(date +%F)"
case "$RUN_MODE" in
  daily|build_only|intraday|ui_only) ;;
  *)
    echo "$(date '+%F %T %Z') invalid_run_mode=$RUN_MODE"
    exit 2
    ;;
esac
echo "$(date '+%F %T %Z') run_mode=$RUN_MODE"

EDGAR_FETCH_RETRIES="${EDGAR_FETCH_RETRIES:-4}"
EDGAR_BACKOFF_BASE="${EDGAR_BACKOFF_BASE:-1.5}"
EDGAR_BACKOFF_CAP="${EDGAR_BACKOFF_CAP:-20}"
EDGAR_FALLBACK_MAX_HOURS="${EDGAR_FALLBACK_MAX_HOURS:-48}"
UNIVERSE_CAP_ENRICH="${UNIVERSE_CAP_ENRICH:-1}"
UNIVERSE_CAP_LIMIT="${UNIVERSE_CAP_LIMIT:-250}"
UNIVERSE_SECTOR_ENRICH="${UNIVERSE_SECTOR_ENRICH:-1}"
UNIVERSE_SECTOR_LIMIT="${UNIVERSE_SECTOR_LIMIT:-250}"
UNIVERSE_SIC_FETCH_LIMIT="${UNIVERSE_SIC_FETCH_LIMIT:-2500}"
LONG_TAIL_BURNIN_ENABLED="${LONG_TAIL_BURNIN_ENABLED:-1}"
LONG_TAIL_BURNIN_LIMIT="${LONG_TAIL_BURNIN_LIMIT:-10}"
LONG_TAIL_BURNIN_MODEL="${LONG_TAIL_BURNIN_MODEL:-gemma4:latest}"
LONG_TAIL_BURNIN_OLLAMA_BASE_URL="${LONG_TAIL_BURNIN_OLLAMA_BASE_URL:-${OLLAMA_BASE_URL:-http://127.0.0.1:11434/v1}}"
LONG_TAIL_BURNIN_API_KEY="${LONG_TAIL_BURNIN_API_KEY:-${OLLAMA_API_KEY:-ollama-local}}"
LONG_TAIL_BURNIN_TIMEOUT_SECONDS="${LONG_TAIL_BURNIN_TIMEOUT_SECONDS:-120}"
LONG_TAIL_BURNIN_MIN_CONFIDENCE="${LONG_TAIL_BURNIN_MIN_CONFIDENCE:-0.64}"
LONG_TAIL_BURNIN_COOLDOWN_SECONDS="${LONG_TAIL_BURNIN_COOLDOWN_SECONDS:-0.2}"
LONG_TAIL_BURNIN_MAX_LOAD1="${LONG_TAIL_BURNIN_MAX_LOAD1:-3.0}"
LONG_TAIL_BURNIN_MAX_MEM_USED_PCT="${LONG_TAIL_BURNIN_MAX_MEM_USED_PCT:-88.0}"
LONG_TAIL_BURNIN_FORCE="${LONG_TAIL_BURNIN_FORCE:-0}"
LONG_TAIL_BURNIN_INCLUDE_SEC="${LONG_TAIL_BURNIN_INCLUDE_SEC:-0}"
BEDROCK_TOP_N="${BEDROCK_TOP_N:-800}"

# ── Failure alert helper — sends Telegram message and exits with code ────────
fail_alert() {
  local reason="$1"
  local code="${2:-1}"
  echo "$(date '+%F %T %Z') FATAL: $reason"
  /usr/bin/python3 "$ROOT/everos_pipeline_ingest.py" --mode "$RUN_MODE" --status failure --reason "$reason" || true
  /usr/bin/python3 "$ROOT/alert_pipeline_failure.py" "$reason" || true
  exit "$code"
}

csv_has_rows() {
  local path="$1"
  [[ -f "$path" ]] || return 1
  [[ -s "$path" ]] || return 1
  local line_count
  line_count="$(wc -l < "$path")"
  [[ "${line_count}" -gt 1 ]]
}

artifact_age_hours() {
  local path="$1"
  local now_ts mtime_ts age_seconds
  now_ts="$(date +%s)"
  mtime_ts="$(stat -c %Y "$path" 2>/dev/null || echo 0)"
  age_seconds=$(( now_ts - mtime_ts ))
  echo $(( age_seconds / 3600 ))
}

write_sec_fetch_status() {
  local mode="$1"
  local source="$2"
  local reason="$3"
  local stale_hours="$4"
  local artifact_path="$5"
  /usr/bin/python3 - "$ROOT/sec_catalyst_fetch_status.json" "$mode" "$source" "$reason" "$stale_hours" "$artifact_path" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

out_path = Path(sys.argv[1])
mode = sys.argv[2]
source = sys.argv[3]
reason = sys.argv[4]
stale_hours = sys.argv[5]
artifact_path = sys.argv[6]

payload = {
    "kind": "sec_catalyst_fetch_status",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "mode": mode,
    "source": source or None,
    "reason": reason or None,
    "stale_hours": int(stale_hours) if stale_hours.isdigit() else None,
    "artifact_path": artifact_path or None,
}
out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

select_sec_fallback() {
  local -a candidates=()
  candidates+=("$ROOT/sec_catalyst_latest.csv")
  candidates+=("$ROOT/sec_catalyst_latest.last_good.csv")

  local dated_candidate
  dated_candidate="$(find "$ROOT" -maxdepth 1 -type f -name 'sec_catalyst_20*.csv' ! -name 'sec_catalyst_latest.csv' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)"
  if [[ -n "$dated_candidate" ]]; then
    candidates+=("$dated_candidate")
  fi

  local candidate age_hours
  for candidate in "${candidates[@]}"; do
    [[ -n "$candidate" ]] || continue
    if ! csv_has_rows "$candidate"; then
      continue
    fi
    age_hours="$(artifact_age_hours "$candidate")"
    if [[ "$age_hours" -le "$EDGAR_FALLBACK_MAX_HOURS" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

refresh_sec_catalyst_latest() {
  local tmp_csv tmp_log reason fallback age_hours
  tmp_csv="$(mktemp "$ROOT/sec_catalyst_latest.tmp.XXXXXX.csv")"
  tmp_log="$(mktemp "$ROOT/sec_catalyst_latest.tmp.XXXXXX.log")"

  if /usr/bin/python3 sec_catalyst_list.py \
    --limit 1500 \
    --max-per-form 100 \
    --retries "$EDGAR_FETCH_RETRIES" \
    --backoff-base "$EDGAR_BACKOFF_BASE" \
    --backoff-cap "$EDGAR_BACKOFF_CAP" \
    --ticker-cache "$ROOT/.sec_company_tickers_cache.json" \
    >"$tmp_csv" 2>"$tmp_log"; then
    if csv_has_rows "$tmp_csv"; then
      mv "$tmp_csv" "$ROOT/sec_catalyst_latest.csv"
      cp "$ROOT/sec_catalyst_latest.csv" "$ROOT/sec_catalyst_latest.last_good.csv"
      rm -f "$tmp_log"
      write_sec_fetch_status "live" "edgar" "" "0" "$ROOT/sec_catalyst_latest.csv"
      echo "$(date '+%F %T %Z') sec_fetch=live"
      return 0
    fi
    echo "SEC fetch returned no catalyst rows" >"$tmp_log"
  fi

  reason="$(tr '\n' ' ' < "$tmp_log" | sed 's/[[:space:]]\+/ /g' | cut -c1-400)"
  rm -f "$tmp_csv" "$tmp_log"

  if fallback="$(select_sec_fallback)"; then
    age_hours="$(artifact_age_hours "$fallback")"
    if [[ "$fallback" != "$ROOT/sec_catalyst_latest.csv" ]]; then
      cp "$fallback" "$ROOT/sec_catalyst_latest.csv"
    fi
    cp "$ROOT/sec_catalyst_latest.csv" "$ROOT/sec_catalyst_latest.last_good.csv" || true
    write_sec_fetch_status "fallback" "$fallback" "$reason" "$age_hours" "$fallback"
    echo "$(date '+%F %T %Z') sec_fetch=fallback age_hours=$age_hours source=$fallback reason=${reason:-unknown}"
    return 0
  fi

  write_sec_fetch_status "failed" "" "$reason" "" ""
  fail_alert "sec_catalyst_list.py failed and no fresh fallback artifact exists — ${reason:-EDGAR unreachable or rate-limited}"
}

write_pipeline_manifest() {
  local manifest_path="$ROOT/pipeline_manifest.json"
  local latest_path="$ROOT/pipeline_manifest_latest.json"
  local dated_path="$ROOT/pipeline_manifest_${STAMP}.json"

  /usr/bin/python3 - "$ROOT" "$STAMP" "$manifest_path" "$latest_path" "$dated_path" <<"PY"
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
stamp = sys.argv[2]
manifest_path = Path(sys.argv[3])
latest_path = Path(sys.argv[4])
dated_path = Path(sys.argv[5])

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def file_meta(rel_path: str) -> dict:
    path = root / rel_path
    meta = {"path": rel_path, "exists": path.exists()}
    if path.exists():
        stat = path.stat()
        meta.update(
            {
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
                "sha256": sha256(path),
            }
        )
    return meta

def git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""

manifest = {
    "kind": "cerebro_pipeline_manifest",
    "status": "complete",
    "stamp": stamp,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "root": str(root),
    "git_commit": git("rev-parse", "HEAD"),
    "git_short_commit": git("rev-parse", "--short", "HEAD"),
    "git_branch": git("branch", "--show-current"),
    "outputs": {
        "sec_catalyst_latest": file_meta("sec_catalyst_latest.csv"),
        "sec_catalyst_ranked": file_meta("sec_catalyst_ranked.csv"),
        "combined_priority": file_meta("combined_priority.csv"),
        "newsletter_body": file_meta("newsletter_body.html"),
        "sec_fetch_status": file_meta("sec_catalyst_fetch_status.json"),
        "entity_master": file_meta("entity_master.json"),
        "macro_layer": file_meta("macro_layer.json"),
        "scanner_index": file_meta("docs/index.html"),
        "scanner_artifact_status": file_meta("scanner_artifact_status.json"),
        "hud_index": file_meta("docs/hud/index.html"),
        "api_server": file_meta("api_server.py"),
    },
    "hud_assets": sorted(
        str(path.relative_to(root))
        for path in (root / "docs/hud/assets").glob("index-*.js")
        if path.is_file()
    ),
}

payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
for target in (manifest_path, latest_path, dated_path):
    target.write_text(payload, encoding="utf-8")
print("{} written with {} tracked outputs".format(manifest_path.name, len(manifest["outputs"])))
PY
}

if [[ "$RUN_MODE" == "intraday" ]]; then
  echo "$(date '+%F %T %Z') intraday_mode evaluate_outcomes skipped"
  echo "$(date '+%F %T %Z') intraday_mode tune_scoring skipped"
elif [[ "$RUN_MODE" == "ui_only" ]]; then
  echo "$(date '+%F %T %Z') ui_only_mode upstream_builds skipped"
else
  /usr/bin/python3 evaluate_sec_outcomes.py --days 60 || echo "$(date '+%F %T') evaluate_outcomes skipped (network/data unavailable)"
  /usr/bin/python3 tune_scoring_config.py || echo "$(date '+%F %T') tune_scoring skipped"
fi

# SEC-compliant User-Agent: app + contact identity.
SEC_USER_AGENT="${SEC_USER_AGENT:-LocalScanner/1.0 (Catalyst Edge Maintainers Catalyst@gmail.com)}"
export SEC_USER_AGENT

if [[ "$RUN_MODE" == "ui_only" ]]; then
  /usr/bin/python3 generate_glossary_pages.py 2>/dev/null || true
/usr/bin/python3 generate_seo_site.py || fail_alert "generate_seo_site.py failed — scanner artifact invalid or empty"
  write_pipeline_manifest
  /usr/bin/python3 "$ROOT/cerebro_verify.py" \
    --mode manifest \
    --manifest "$ROOT/pipeline_manifest.json" \
    --base-url "http://127.0.0.1:8000" \
    || fail_alert "cerebro_verify manifest check failed"
  /usr/bin/python3 cerebro_publisher.py --event=pipeline_complete || true
  echo "$(date '+%F %T %Z') ui_only_refresh_complete"
  echo "$(date '+%F %T %Z') job_end"
  exit 0
fi

refresh_sec_catalyst_latest

# Ticker-only list for quick Thinkorswim watchlist paste
/usr/bin/tail -n +2 sec_catalyst_latest.csv | /usr/bin/cut -d, -f1 | /usr/bin/awk '!seen[$1]++' > sec_catalyst_tickers.txt
/usr/bin/python3 rank_sec_catalysts.py
/usr/bin/python3 classify_sec_catalysts.py
/usr/bin/python3 classify_sec_income.py || echo "$(date '+%F %T') income_classify skipped"
/usr/bin/python3 build_news_momentum.py
/usr/bin/python3 build_gics_mapper.py          || echo "$(date '+%F %T') gics_mapper skipped"
/usr/bin/python3 build_gics_hierarchy.py       || echo "$(date '+%F %T') gics_hierarchy skipped"
# Cerebro Sprint 1 — Gravity + Velocity + Atmospheric Pressure
/usr/bin/python3 macro_engine.py               || echo "$(date '+%F %T') macro_engine skipped"
if [[ "$LONG_TAIL_BURNIN_ENABLED" == "1" && "$RUN_MODE" != "intraday" && "$RUN_MODE" != "ui_only" ]]; then
  burnin_args=(
    "--limit=${LONG_TAIL_BURNIN_LIMIT}"
    "--model=${LONG_TAIL_BURNIN_MODEL}"
    "--ollama-base-url=${LONG_TAIL_BURNIN_OLLAMA_BASE_URL}"
    "--api-key=${LONG_TAIL_BURNIN_API_KEY}"
    "--timeout-seconds=${LONG_TAIL_BURNIN_TIMEOUT_SECONDS}"
    "--min-confidence=${LONG_TAIL_BURNIN_MIN_CONFIDENCE}"
    "--cooldown-seconds=${LONG_TAIL_BURNIN_COOLDOWN_SECONDS}"
    "--max-load1=${LONG_TAIL_BURNIN_MAX_LOAD1}"
    "--max-mem-used-pct=${LONG_TAIL_BURNIN_MAX_MEM_USED_PCT}"
    "--write-cache"
    "--save-company-cache"
  )
  if [[ "$LONG_TAIL_BURNIN_INCLUDE_SEC" == "1" ]]; then
    burnin_args+=("--include-sec")
  fi
  if [[ "$LONG_TAIL_BURNIN_FORCE" == "1" ]]; then
    burnin_args+=("--force")
  fi
  echo "$(date '+%F %T %Z') phase4_long_tail_burnin start limit=${LONG_TAIL_BURNIN_LIMIT} model=${LONG_TAIL_BURNIN_MODEL}"
  /usr/bin/python3 ops/phase4_long_tail_burnin.py "${burnin_args[@]}" || echo "$(date '+%F %T') phase4_long_tail_burnin skipped"
fi
universe_gravity_args=()
if [[ "$UNIVERSE_CAP_ENRICH" == "1" && "$RUN_MODE" != "intraday" && "$RUN_MODE" != "ui_only" ]]; then
  universe_gravity_args+=(--enrich-caps "--cap-limit=${UNIVERSE_CAP_LIMIT}")
fi
if [[ "$UNIVERSE_SECTOR_ENRICH" == "1" && "$RUN_MODE" != "intraday" && "$RUN_MODE" != "ui_only" ]]; then
  universe_gravity_args+=("--sector-limit=${UNIVERSE_SECTOR_LIMIT}" "--sic-limit=${UNIVERSE_SIC_FETCH_LIMIT}")
fi
/usr/bin/python3 build_universe_gravity.py "${universe_gravity_args[@]}" || echo "$(date '+%F %T') universe_gravity skipped"
/usr/bin/python3 gravity_engine.py             || echo "$(date '+%F %T') gravity_engine skipped"
if [[ "$RUN_MODE" != "intraday" && "$RUN_MODE" != "ui_only" ]] && [[ -f "$ROOT/.fmp_env" || -n "${FMP_API_KEY:-}" ]]; then
  /usr/bin/python3 spoke_bedrock.py --top="${BEDROCK_TOP_N}" || echo "$(date '+%F %T') spoke_bedrock skipped"
fi
# Tether snapshot runs weekly (Sunday only) — too slow for daily
[ "$(date +%u)" = "7" ] && /usr/bin/python3 tether_engine.py --snapshot || true
/usr/bin/python3 build_macro_layer.py      || echo "$(date '+%F %T') macro_layer skipped"
/usr/bin/python3 build_nobel_physics.py    || echo "$(date '+%F %T') nobel_physics skipped"
/usr/bin/python3 build_gap_scanner.py      || echo "$(date '+%F %T') gap_scanner skipped"

# Enhancement scripts — failures are non-fatal
/usr/bin/python3 detect_insider_clusters.py  || echo "$(date '+%F %T') insider_clusters skipped"
/usr/bin/python3 build_keyword_hits.py       || echo "$(date '+%F %T') keyword_hits skipped"
/usr/bin/python3 build_macro_context.py      || echo "$(date '+%F %T') macro_context skipped"
/usr/bin/python3 build_short_interest.py     || echo "$(date '+%F %T') short_interest skipped"
/usr/bin/python3 build_sympathy_logger.py    || echo "$(date '+%F %T') sympathy_logger skipped"

# Squeeze Hunter — Roaring Kitty model (runs after insider clusters are ready)
/usr/bin/python3 build_short_data.py        || echo "$(date '+%F %T') short_data skipped"
/usr/bin/python3 fetch_options_flow.py      || echo "$(date '+%F %T') options_flow skipped"
/usr/bin/python3 spoke_gamma.py             || echo "$(date '+%F %T') gamma_wells skipped"
/usr/bin/python3 reddit_wsb_pulse.py        || echo "$(date '+%F %T') wsb_pulse skipped"
/usr/bin/python3 build_squeeze_hunter.py    || echo "$(date '+%F %T') squeeze_hunter skipped"

# 8 Intelligence Layers — failures are non-fatal
/usr/bin/python3 build_deepvalue_screen.py  || echo "$(date '+%F %T') deepvalue_screen skipped"
/usr/bin/python3 build_smart_money.py       || echo "$(date '+%F %T') smart_money skipped"
/usr/bin/python3 build_dark_pool.py         || echo "$(date '+%F %T') dark_pool skipped"
/usr/bin/python3 build_merger_radar.py      || echo "$(date '+%F %T') merger_radar skipped"
/usr/bin/python3 build_lockup_calendar.py   || echo "$(date '+%F %T') lockup_calendar skipped"
/usr/bin/python3 build_nt_radar.py          || echo "$(date '+%F %T') nt_radar skipped"
/usr/bin/python3 build_revenue_inflection.py || echo "$(date '+%F %T') revenue_inflection skipped"
/usr/bin/python3 build_convergence_score.py || echo "$(date '+%F %T') convergence_score skipped"

# ── SAFETY-NET SCANNER HTML BUILD ────────────────────────────────────────────
# Runs here with all critical CSVs ready (gappers/ranked/squeeze/insiders/darkpool/sectors).
# Options flow + polymarket arrive later and will be picked up by the final
# generate_seo_site.py call at the end of the pipeline. This early build ensures
# the public /scanner/ page has fresh data even if a downstream spoke stalls.
/usr/bin/python3 generate_seo_site.py || echo "$(date '+%F %T') safety_net_scanner_build failed (continuing)"

/usr/bin/python3 build_polymarket_signals.py || echo "$(date '+%F %T') polymarket_signals skipped"
if [[ "$RUN_MODE" != "intraday" ]]; then
  /usr/bin/python3 build_newsletter_picks.py     || fail_alert "build_newsletter_picks.py failed — newsletter will not be sent"
  # Verify newsletter_body.html was built today — grep for ISO stamp injected by build_newsletter_picks.py
  TODAY="$(date +%F)"
  if [[ ! -f "newsletter_body.html" ]]; then
    fail_alert "newsletter_body.html missing — build_newsletter_picks.py failed silently"
  fi
  if ! grep -q "newsletter-date:${TODAY}" newsletter_body.html; then
    fail_alert "newsletter_body.html does not contain today's stamp (newsletter-date:${TODAY}) — stale or failed build"
  fi
  echo "$(date '+%F %T') newsletter_body.html freshness verified"
  /usr/bin/python3 build_compelling_subject.py || echo "$(date '+%F %T') build_compelling_subject skipped"
else
  echo "$(date '+%F %T %Z') intraday_mode newsletter_build skipped"
fi
# Domain 5: Options sweep/flow scan — runs before site generation
# Wall-clock caps: external-API steps must never stall the pipeline.
/usr/bin/timeout 180 /usr/bin/python3 spoke_options.py --limit=50 || echo "$(date '+%F %T') spoke_options skipped (or timed out)"
/usr/bin/timeout 180 /usr/bin/python3 build_options_flow.py || echo "$(date '+%F %T') build_options_flow skipped (or timed out)"
/usr/bin/python3 cerebro_publisher.py --event=macro_update || true
# Domain 6: Digital Footprint — Google Trends search velocity (runs during market hours only)
HOUR_ET_DIGITAL=$(TZ="America/New_York" date +%H)
if [[ "$HOUR_ET_DIGITAL" -ge 6 && "$HOUR_ET_DIGITAL" -lt 20 ]]; then
  /usr/bin/timeout 180 /usr/bin/python3 spoke_digital.py --limit=100 || echo "$(date '+%F %T') spoke_digital skipped (or timed out)"
fi
# Domain 7: Legal Risk — CourtListener or SEC enforcement fallback
/usr/bin/timeout 240 /usr/bin/python3 spoke_legal.py --limit=200 --days=30 || echo "$(date '+%F %T') spoke_legal skipped (or timed out)"
# Domain 8: Options Flow — ThetaData or Yahoo Finance fallback (Yahoo 401-storms here; hard cap)
/usr/bin/timeout 180 /usr/bin/python3 spoke_thetadata.py --limit=100 || echo "$(date '+%F %T') spoke_thetadata skipped (or timed out)"
# Domain 9: Supply Chain Tethers — FRED freight/commodity + weather cross-ref
/usr/bin/timeout 240 /usr/bin/python3 spoke_supplychain.py || echo "$(date '+%F %T') spoke_supplychain skipped (or timed out)"
/usr/bin/python3 generate_glossary_pages.py 2>/dev/null || true
/usr/bin/python3 build_performance_breakdown.py 2>/dev/null || true
/usr/bin/python3 build_lead_magnet.py 2>/dev/null || true

# ── Free-Data Wiring Sprint (Apr 2026) ───────────────────────────────────────
# 28 public feeds covering government releases, exchange data, social signal,
# wire copy, and macro context. All non-fatal: pipeline continues on skip.
# Full inventory: free_data_inventory.md
/usr/bin/timeout 90  /usr/bin/python3 build_dod_contracts.py        || echo "$(date '+%F %T') dod_contracts skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_cftc_cot.py             || echo "$(date '+%F %T') cftc_cot skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_eia_petroleum.py        || echo "$(date '+%F %T') eia_petroleum skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_earnings_calendar.py    || echo "$(date '+%F %T') earnings_calendar skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_press_wires.py          || echo "$(date '+%F %T') press_wires skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_stocktwits_trending.py  || echo "$(date '+%F %T') stocktwits_trending skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_reddit_velocity.py      || echo "$(date '+%F %T') reddit_velocity skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_google_trends.py        || echo "$(date '+%F %T') google_trends skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_13f_whales.py           || echo "$(date '+%F %T') 13f_whales skipped"
/usr/bin/timeout 180 /usr/bin/python3 build_edgar_fulltext.py       || echo "$(date '+%F %T') edgar_fulltext skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_fred_macro.py           || echo "$(date '+%F %T') fred_macro skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_uspto_feed.py           || echo "$(date '+%F %T') uspto_feed skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_bls_calendar.py         || echo "$(date '+%F %T') bls_calendar skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_treasury_ofac.py        || echo "$(date '+%F %T') treasury_ofac skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sedar_canada.py         || echo "$(date '+%F %T') sedar_canada skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_usda_wasde.py           || echo "$(date '+%F %T') usda_wasde skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_courtlistener_recap.py  || echo "$(date '+%F %T') courtlistener_recap skipped"
/usr/bin/timeout 240 /usr/bin/python3 build_github_velocity.py      || echo "$(date '+%F %T') github_velocity skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_arxiv_cashtag.py        || echo "$(date '+%F %T') arxiv_cashtag skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_adsb_jets.py            || echo "$(date '+%F %T') adsb_jets skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fomc_calendar.py        || echo "$(date '+%F %T') fomc_calendar skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_ism_adp.py              || echo "$(date '+%F %T') ism_adp skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_opensecrets.py          || echo "$(date '+%F %T') opensecrets skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_tsa_volume.py           || echo "$(date '+%F %T') tsa_volume skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_crypto_correlation.py   || echo "$(date '+%F %T') crypto_correlation skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fda_pdufa.py            || echo "$(date '+%F %T') fda_pdufa skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_regsho_threshold.py     || echo "$(date '+%F %T') regsho_threshold skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_clinical_trials.py      || echo "$(date '+%F %T') clinical_trials skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_form_144.py             || echo "$(date '+%F %T') form_144 skipped"

# ── Free-Data Wiring Sprint — Wave 2 (Apr 17-18, 2026) ────────────────────
# +46 free public feeds covering macro (FRED bundle), consumer (TSA/app store),
# disaster/weather (NOAA/USGS/FEMA/CPSC), sanctions (OFAC), crypto (DefiLlama/
# CoinGecko), SEC filings (Form D, 13F, FTD, IPOs), commodities (gas/oil/rig),
# global events (GDELT), and sentiment (Reddit cashtags, wiki pageviews).
/usr/bin/timeout 60  /usr/bin/python3 build_pce_prices.py           || echo "$(date '+%F %T') pce_prices skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_aaa_gas_prices.py       || echo "$(date '+%F %T') aaa_gas skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fed_funds_futures.py    || echo "$(date '+%F %T') fed_funds_futures skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_mortgage_rates.py       || echo "$(date '+%F %T') mortgage_rates skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_zillow_rent.py          || echo "$(date '+%F %T') zillow_rent skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fda_approvals.py        || echo "$(date '+%F %T') fda_approvals skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_fda_recalls.py          || echo "$(date '+%F %T') fda_recalls skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fda_drug_shortages.py   || echo "$(date '+%F %T') fda_drug_shortages skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_jobless_claims.py       || echo "$(date '+%F %T') jobless_claims skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_money_supply.py         || echo "$(date '+%F %T') money_supply skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_philly_fed.py           || echo "$(date '+%F %T') philly_fed skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_durable_goods.py        || echo "$(date '+%F %T') durable_goods skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_leading_index.py        || echo "$(date '+%F %T') leading_index skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_global_rates.py         || echo "$(date '+%F %T') global_rates skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fx_rates.py             || echo "$(date '+%F %T') fx_rates skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_commodity_spot.py       || echo "$(date '+%F %T') commodity_spot skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sec_form_d.py           || echo "$(date '+%F %T') sec_form_d skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_edgar_ipos.py           || echo "$(date '+%F %T') edgar_ipos skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sec_13f.py              || echo "$(date '+%F %T') sec_13f skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_noaa_hurricane.py       || echo "$(date '+%F %T') noaa_hurricane skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_usgs_earthquakes.py     || echo "$(date '+%F %T') usgs_earthquakes skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_noaa_weather_alerts.py  || echo "$(date '+%F %T') noaa_weather_alerts skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_cpsc_recalls.py         || echo "$(date '+%F %T') cpsc_recalls skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_opec_crude.py           || echo "$(date '+%F %T') opec_crude skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_reddit_investing.py     || echo "$(date '+%F %T') reddit_investing skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_crypto_defi.py          || echo "$(date '+%F %T') crypto_defi skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_crypto_exchanges.py     || echo "$(date '+%F %T') crypto_exchanges skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_crypto_stablecoins.py   || echo "$(date '+%F %T') crypto_stablecoins skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_federal_register.py     || echo "$(date '+%F %T') federal_register skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_ofac_sanctions.py       || echo "$(date '+%F %T') ofac_sanctions skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_treasury_auctions.py    || echo "$(date '+%F %T') treasury_auctions skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_wiki_pageviews.py       || echo "$(date '+%F %T') wiki_pageviews skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_eia_nat_gas.py          || echo "$(date '+%F %T') eia_nat_gas skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_app_store_top.py        || echo "$(date '+%F %T') app_store_top skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_finra_reg_sho.py        || echo "$(date '+%F %T') finra_reg_sho skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_baker_hughes_rigs.py    || echo "$(date '+%F %T') baker_hughes_rigs skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_sec_ftd.py              || echo "$(date '+%F %T') sec_ftd skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_tsa_throughput.py       || echo "$(date '+%F %T') tsa_throughput skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_bls_employment.py       || echo "$(date '+%F %T') bls_employment skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_bea_trade.py            || echo "$(date '+%F %T') bea_trade skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_aar_railroad.py         || echo "$(date '+%F %T') aar_railroad skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_macro_bundle.py         || echo "$(date '+%F %T') macro_bundle skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fdic_failures.py        || echo "$(date '+%F %T') fdic_failures skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fema_disasters.py       || echo "$(date '+%F %T') fema_disasters skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_gdelt_events.py         || echo "$(date '+%F %T') gdelt_events skipped"

# ── Free-Data Wiring Sprint — Wave 3 (Apr 18, 2026) ───────────────────────
/usr/bin/timeout 60  /usr/bin/python3 build_vix_complex.py          || echo "$(date '+%F %T') vix_complex skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_oecd_cli.py             || echo "$(date '+%F %T') oecd_cli skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_cdc_hospital.py         || echo "$(date '+%F %T') cdc_hospital skipped"

# ── Free-Data Wiring Sprint — Wave 4 (Apr 18, 2026) ───────────────────────
# Macro surprise + financial conditions + consumer mobility + sentiment +
# labor slack. All stdlib-only, no API key.
/usr/bin/timeout 60  /usr/bin/python3 build_gdpnow.py               || echo "$(date '+%F %T') gdpnow skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_nfci.py                 || echo "$(date '+%F %T') nfci skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_mta_ridership.py        || echo "$(date '+%F %T') mta_ridership skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fear_greed.py           || echo "$(date '+%F %T') fear_greed skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_jolts.py                || echo "$(date '+%F %T') jolts skipped"
/usr/bin/timeout 420 /usr/bin/python3 build_trade_flows.py          || echo "$(date '+%F %T') trade_flows skipped"

# ── Free-Data Wiring Sprint — Wave 5 (Apr 18, 2026) ───────────────────────
# Retail attention + consumer discretionary signals.
/usr/bin/timeout 120 /usr/bin/python3 build_wiki_attention.py       || echo "$(date '+%F %T') wiki_attention skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fda_enforcement.py      || echo "$(date '+%F %T') fda_enforcement skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_treasury_fiscal.py      || echo "$(date '+%F %T') treasury_fiscal skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_unemployment_claims.py  || echo "$(date '+%F %T') unemployment_claims skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_going_concern.py        || echo "$(date '+%F %T') going_concern skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_crypto_fear_greed.py    || echo "$(date '+%F %T') crypto_fear_greed skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_btc_mining.py           || echo "$(date '+%F %T') btc_mining skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_hurricane_radar.py      || echo "$(date '+%F %T') hurricane_radar skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_usgs_quakes.py          || echo "$(date '+%F %T') usgs_quakes skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_faa_delays.py           || echo "$(date '+%F %T') faa_delays skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_nasa_eonet.py           || echo "$(date '+%F %T') nasa_eonet skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_bls_macro.py            || echo "$(date '+%F %T') bls_macro skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_space_weather.py        || echo "$(date '+%F %T') space_weather skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_worldbank_gdp.py        || echo "$(date '+%F %T') worldbank_gdp skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_epa_tri.py              || echo "$(date '+%F %T') epa_tri skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fbi_crime.py            || echo "$(date '+%F %T') fbi_crime skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_coingecko_top.py        || echo "$(date '+%F %T') coingecko_top skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_statcan_macro.py        || echo "$(date '+%F %T') statcan_macro skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_cb_press.py             || echo "$(date '+%F %T') cb_press skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_usaspending_awards.py   || echo "$(date '+%F %T') usaspending_awards skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_treasury_fx.py          || echo "$(date '+%F %T') treasury_fx skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_edgar_fts.py            || echo "$(date '+%F %T') edgar_fts skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_congress_events.py      || echo "$(date '+%F %T') congress_events skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_goes_xray.py            || echo "$(date '+%F %T') goes_xray skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_nasa_neo.py             || echo "$(date '+%F %T') nasa_neo skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_swpc_alerts.py          || echo "$(date '+%F %T') swpc_alerts skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_swpc_kp.py              || echo "$(date '+%F %T') swpc_kp skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_solar_cycle.py          || echo "$(date '+%F %T') solar_cycle skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_ace_mag.py              || echo "$(date '+%F %T') ace_mag skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fda_drug_ae.py          || echo "$(date '+%F %T') fda_drug_ae skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_fda_device_ae.py        || echo "$(date '+%F %T') fda_device_ae skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_fda_tobacco.py          || echo "$(date '+%F %T') fda_tobacco skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_sec_425.py              || echo "$(date '+%F %T') sec_425 skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_sec_schedules.py        || echo "$(date '+%F %T') sec_schedules skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sec_proxy_fight.py      || echo "$(date '+%F %T') sec_proxy_fight skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_regs_dockets.py         || echo "$(date '+%F %T') regs_dockets skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_spaceflight_news.py     || echo "$(date '+%F %T') spaceflight_news skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_fhfa_hpi.py             || echo "$(date '+%F %T') fhfa_hpi skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_swpc_forecast.py        || echo "$(date '+%F %T') swpc_forecast skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_swpc_wind.py            || echo "$(date '+%F %T') swpc_wind skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_worldbank_unemployment.py || echo "$(date '+%F %T') worldbank_unemployment skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_worldbank_cpi.py        || echo "$(date '+%F %T') worldbank_cpi skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_bis_dollar.py           || echo "$(date '+%F %T') bis_dollar skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_schedule_13d.py         || echo "$(date '+%F %T') schedule_13d skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_blockchair_onchain.py   || echo "$(date '+%F %T') blockchair_onchain skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_comtrade_flows.py       || echo "$(date '+%F %T') comtrade_flows skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_climate_signals.py      || echo "$(date '+%F %T') climate_signals skipped"
/usr/bin/timeout 180 /usr/bin/python3 build_bis_rates.py            || echo "$(date '+%F %T') bis_rates skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_defillama_dexs.py       || echo "$(date '+%F %T') defillama_dexs skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fao_food_prices.py      || echo "$(date '+%F %T') fao_food_prices skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_github_ai_velocity.py   || echo "$(date '+%F %T') github_ai_velocity skipped"
/usr/bin/timeout 180 /usr/bin/python3 build_ecb_monetary.py         || echo "$(date '+%F %T') ecb_monetary skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_fda_510k.py             || echo "$(date '+%F %T') fda_510k skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_zillow_zhvi.py          || echo "$(date '+%F %T') zillow_zhvi skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_realtor_inventory.py    || echo "$(date '+%F %T') realtor_inventory skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_spc_storms.py           || echo "$(date '+%F %T') spc_storms skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_stablecoins.py          || echo "$(date '+%F %T') stablecoins skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_btc_mempool.py          || echo "$(date '+%F %T') btc_mempool skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_ofr_fsi.py              || echo "$(date '+%F %T') ofr_fsi skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sec_litigation.py       || echo "$(date '+%F %T') sec_litigation skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_pypi_velocity.py        || echo "$(date '+%F %T') pypi_velocity skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_npm_velocity.py         || echo "$(date '+%F %T') npm_velocity skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fbx_freight.py          || echo "$(date '+%F %T') fbx_freight skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_ercot_fuelmix.py        || echo "$(date '+%F %T') ercot_fuelmix skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_caiso_grid.py           || echo "$(date '+%F %T') caiso_grid skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_nyiso_grid.py           || echo "$(date '+%F %T') nyiso_grid skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_bpa_balancing.py        || echo "$(date '+%F %T') bpa_balancing skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_cve_velocity.py         || echo "$(date '+%F %T') cve_velocity skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_kalshi_macro.py         || echo "$(date '+%F %T') kalshi_macro skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_eu_indpro.py            || echo "$(date '+%F %T') eu_indpro skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_eu_retail.py            || echo "$(date '+%F %T') eu_retail skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fed_speeches.py         || echo "$(date '+%F %T') fed_speeches skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_gdacs_disasters.py      || echo "$(date '+%F %T') gdacs_disasters skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_sec_delisting.py        || echo "$(date '+%F %T') sec_delisting skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_hnews_attention.py      || echo "$(date '+%F %T') hnews_attention skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_producthunt_launches.py || echo "$(date '+%F %T') producthunt_launches skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_asx_announcements.py    || echo "$(date '+%F %T') asx_announcements skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_rba_rates.py            || echo "$(date '+%F %T') rba_rates skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_hkma_peg.py             || echo "$(date '+%F %T') hkma_peg skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_nbp_fx.py               || echo "$(date '+%F %T') nbp_fx skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_boe_rates.py            || echo "$(date '+%F %T') boe_rates skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_boi_israel.py           || echo "$(date '+%F %T') boi_israel skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_lbma_metals.py          || echo "$(date '+%F %T') lbma_metals skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_worldbank_reserves.py   || echo "$(date '+%F %T') worldbank_reserves skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_treasury_mspd.py        || echo "$(date '+%F %T') treasury_mspd skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_snb_swiss.py            || echo "$(date '+%F %T') snb_swiss skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_sec_splits.py           || echo "$(date '+%F %T') sec_splits skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_sec_buybacks.py         || echo "$(date '+%F %T') sec_buybacks skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sec_corpactions.py      || echo "$(date '+%F %T') sec_corpactions skipped"
/usr/bin/timeout 75  /usr/bin/python3 build_sec_risks.py            || echo "$(date '+%F %T') sec_risks skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sec_biotech.py          || echo "$(date '+%F %T') sec_biotech skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sec_distress.py         || echo "$(date '+%F %T') sec_distress skipped"
/usr/bin/timeout 75  /usr/bin/python3 build_sec_contracts.py        || echo "$(date '+%F %T') sec_contracts skipped"
/usr/bin/timeout 75  /usr/bin/python3 build_sec_legal.py            || echo "$(date '+%F %T') sec_legal skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_financing.py        || echo "$(date '+%F %T') sec_financing skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_cmgmt.py            || echo "$(date '+%F %T') sec_cmgmt skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_restruct.py         || echo "$(date '+%F %T') sec_restruct skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_despac.py           || echo "$(date '+%F %T') sec_despac skipped"
/usr/bin/timeout 75  /usr/bin/python3 build_sec_governance.py       || echo "$(date '+%F %T') sec_governance skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_crisis.py           || echo "$(date '+%F %T') sec_crisis skipped"
/usr/bin/timeout 75  /usr/bin/python3 build_sec_whistleblower.py    || echo "$(date '+%F %T') sec_whistleblower skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_fda.py              || echo "$(date '+%F %T') sec_fda skipped"
/usr/bin/timeout 75  /usr/bin/python3 build_sec_labor.py            || echo "$(date '+%F %T') sec_labor skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_dealterms.py        || echo "$(date '+%F %T') sec_dealterms skipped"
/usr/bin/timeout 75  /usr/bin/python3 build_sec_crypto.py           || echo "$(date '+%F %T') sec_crypto skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_geopol.py           || echo "$(date '+%F %T') sec_geopol skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_sec_divest.py           || echo "$(date '+%F %T') sec_divest skipped"
/usr/bin/timeout 150 /usr/bin/python3 build_sec_audit.py            || echo "$(date '+%F %T') sec_audit skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_banking.py          || echo "$(date '+%F %T') sec_banking skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_energy_tx.py        || echo "$(date '+%F %T') sec_energy_tx skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_sec_weather.py          || echo "$(date '+%F %T') sec_weather skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_finra_short_volume.py   || echo "$(date '+%F %T') finra_short_volume skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_cma_uk.py               || echo "$(date '+%F %T') cma_uk skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_jpx_tdnet.py            || echo "$(date '+%F %T') jpx_tdnet skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_sec_press.py            || echo "$(date '+%F %T') sec_press skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_fed_register.py         || echo "$(date '+%F %T') fed_register skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_clinicaltrials.py       || echo "$(date '+%F %T') clinicaltrials skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fda_press.py            || echo "$(date '+%F %T') fda_press skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_securities_litigation.py || echo "$(date '+%F %T') securities_litigation skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_xbrl_frames.py      || echo "$(date '+%F %T') sec_xbrl_frames skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_tech_status.py          || echo "$(date '+%F %T') tech_status skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_form3.py            || echo "$(date '+%F %T') sec_form3 skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_predictit.py            || echo "$(date '+%F %T') predictit skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_form144.py          || echo "$(date '+%F %T') sec_form144 skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sec_s4.py               || echo "$(date '+%F %T') sec_s4 skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_tender.py           || echo "$(date '+%F %T') sec_tender skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_merger_proxy.py     || echo "$(date '+%F %T') sec_merger_proxy skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_sec_ipo_pipe.py         || echo "$(date '+%F %T') sec_ipo_pipe skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_sec_restatements.py     || echo "$(date '+%F %T') sec_restatements skipped"
/usr/bin/timeout 150 /usr/bin/python3 build_sec_arrangements.py     || echo "$(date '+%F %T') sec_arrangements skipped"
/usr/bin/timeout 180 /usr/bin/python3 build_sec_debt.py             || echo "$(date '+%F %T') sec_debt skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_sec_spinoff_reg.py      || echo "$(date '+%F %T') sec_spinoff_reg skipped"
/usr/bin/timeout 180 /usr/bin/python3 build_sec_poison_pill.py      || echo "$(date '+%F %T') sec_poison_pill skipped"
/usr/bin/timeout 150 /usr/bin/python3 build_sec_late_filing.py      || echo "$(date '+%F %T') sec_late_filing skipped"
/usr/bin/timeout 150 /usr/bin/python3 build_sec_uplist.py           || echo "$(date '+%F %T') sec_uplist skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_ftc_actions.py          || echo "$(date '+%F %T') ftc_actions skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_cfpb_enforcement.py     || echo "$(date '+%F %T') cfpb_enforcement skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_fca_uk.py               || echo "$(date '+%F %T') fca_uk skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_csa_canada.py           || echo "$(date '+%F %T') csa_canada skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_esma_eu.py              || echo "$(date '+%F %T') esma_eu skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_doj_news.py             || echo "$(date '+%F %T') doj_news skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_fed_enforcement.py      || echo "$(date '+%F %T') fed_enforcement skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_boj_japan.py            || echo "$(date '+%F %T') boj_japan skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_boc_canada.py           || echo "$(date '+%F %T') boc_canada skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_ecb_press.py            || echo "$(date '+%F %T') ecb_press skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_cboe_vix_gaps.py        || echo "$(date '+%F %T') cboe_vix_gaps skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_aisi_steel.py           || echo "$(date '+%F %T') aisi_steel skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_worldsteel.py           || echo "$(date '+%F %T') worldsteel skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_who_health.py           || echo "$(date '+%F %T') who_health skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_volcano_activity.py     || echo "$(date '+%F %T') volcano_activity skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_boeing_press.py         || echo "$(date '+%F %T') boeing_press skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_rbi_india.py            || echo "$(date '+%F %T') rbi_india skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_cdc_newsroom.py         || echo "$(date '+%F %T') cdc_newsroom skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_china_nbs.py            || echo "$(date '+%F %T') china_nbs skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_fsb_stability.py       || echo "$(date '+%F %T') fsb_stability skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_eba_banking.py         || echo "$(date '+%F %T') eba_banking skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_ustr_trade.py          || echo "$(date '+%F %T') ustr_trade skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_cbo_fiscal.py          || echo "$(date '+%F %T') cbo_fiscal skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_gao_reports.py         || echo "$(date '+%F %T') gao_reports skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_eia_tie.py             || echo "$(date '+%F %T') eia_tie skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_nasa_news.py           || echo "$(date '+%F %T') nasa_news skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_space_force.py         || echo "$(date '+%F %T') space_force skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_army_amc.py            || echo "$(date '+%F %T') army_amc skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_uscourts.py            || echo "$(date '+%F %T') uscourts skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_bbc_business.py        || echo "$(date '+%F %T') bbc_business skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_cointelegraph.py       || echo "$(date '+%F %T') cointelegraph skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_bea_news.py           || echo "$(date '+%F %T') bea_news skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_bostonfed.py          || echo "$(date '+%F %T') bostonfed skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_sffed.py              || echo "$(date '+%F %T') sffed skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_nber.py               || echo "$(date '+%F %T') nber skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_dallasfed.py          || echo "$(date '+%F %T') dallasfed skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_stlouisfed.py         || echo "$(date '+%F %T') stlouisfed skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_boe_news.py           || echo "$(date '+%F %T') boe_news skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_fred_blog.py          || echo "$(date '+%F %T') fred_blog skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_census_news.py        || echo "$(date '+%F %T') census_news skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_ons_uk_releases.py    || echo "$(date '+%F %T') ons_uk_releases skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_nist_news.py          || echo "$(date '+%F %T') nist_news skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_congress_bills.py     || echo "$(date '+%F %T') congress_bills skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_sec_speeches.py       || echo "$(date '+%F %T') sec_speeches skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_bis_cb_speeches.py    || echo "$(date '+%F %T') bis_cb_speeches skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_usda_ams.py           || echo "$(date '+%F %T') usda_ams skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_nsf_news.py           || echo "$(date '+%F %T') nsf_news skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_eu_commission.py      || echo "$(date '+%F %T') eu_commission skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_iaea_nuclear.py       || echo "$(date '+%F %T') iaea_nuclear skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_un_news.py            || echo "$(date '+%F %T') un_news skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_bis_workingpapers.py  || echo "$(date '+%F %T') bis_workingpapers skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fedscoop.py           || echo "$(date '+%F %T') fedscoop skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_cyberscoop.py         || echo "$(date '+%F %T') cyberscoop skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_defensescoop.py       || echo "$(date '+%F %T') defensescoop skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_statescoop.py         || echo "$(date '+%F %T') statescoop skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_nextgov.py            || echo "$(date '+%F %T') nextgov skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_federalnewsnetwork.py || echo "$(date '+%F %T') federalnewsnetwork skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_govexec.py            || echo "$(date '+%F %T') govexec skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_meritalk.py           || echo "$(date '+%F %T') meritalk skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_ustr.py               || echo "$(date '+%F %T') ustr skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_occ.py                || echo "$(date '+%F %T') occ skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fed_testimony.py     || echo "$(date '+%F %T') fed_testimony skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_paho.py              || echo "$(date '+%F %T') paho skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_usitc.py             || echo "$(date '+%F %T') usitc skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_ftc.py               || echo "$(date '+%F %T') ftc skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_doj.py               || echo "$(date '+%F %T') doj skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_ferc.py              || echo "$(date '+%F %T') ferc skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_cftc.py              || echo "$(date '+%F %T') cftc skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_osha.py              || echo "$(date '+%F %T') osha skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fcc.py               || echo "$(date '+%F %T') fcc skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_fec_fundraising.py      || echo "$(date '+%F %T') fec_fundraising skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_bcb_brazil.py           || echo "$(date '+%F %T') bcb_brazil skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_sarb_safrica.py         || echo "$(date '+%F %T') sarb_safrica skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_cbr_russia.py           || echo "$(date '+%F %T') cbr_russia skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_norges_bank.py          || echo "$(date '+%F %T') norges_bank skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_bcrp_peru.py            || echo "$(date '+%F %T') bcrp_peru skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_banrep_colombia.py      || echo "$(date '+%F %T') banrep_colombia skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_jpl_news.py             || echo "$(date '+%F %T') jpl_news skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_fedreg_preview.py       || echo "$(date '+%F %T') fedreg_preview skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_openalex_biotech.py     || echo "$(date '+%F %T') openalex_biotech skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_treasury_interest.py    || echo "$(date '+%F %T') treasury_interest skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_treasury_sales.py       || echo "$(date '+%F %T') treasury_sales skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_coingecko_derivatives.py || echo "$(date '+%F %T') coingecko_derivatives skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_enso_state.py           || echo "$(date '+%F %T') enso_state skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_ecb_fx.py               || echo "$(date '+%F %T') ecb_fx skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_wiki_trending.py        || echo "$(date '+%F %T') wiki_trending skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_form144.py              || echo "$(date '+%F %T') form144 skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_census_retail.py        || echo "$(date '+%F %T') census_retail skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_census_wholesale.py     || echo "$(date '+%F %T') census_wholesale skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_census_bfs.py           || echo "$(date '+%F %T') census_bfs skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_pubmed_biotech.py       || echo "$(date '+%F %T') pubmed_biotech skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_usgs_streamflow.py      || echo "$(date '+%F %T') usgs_streamflow skipped"
/usr/bin/timeout 300 /usr/bin/python3 build_nhtsa_recalls.py        || echo "$(date '+%F %T') nhtsa_recalls skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_vix_term.py             || echo "$(date '+%F %T') vix_term skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_sec_13f.py              || echo "$(date '+%F %T') sec_13f skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_openfda_adverse.py      || echo "$(date '+%F %T') openfda_adverse skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_usa_spending.py         || echo "$(date '+%F %T') usa_spending skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_fec_megadonors.py       || echo "$(date '+%F %T') fec_megadonors skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_nyfed_sofr.py           || echo "$(date '+%F %T') nyfed_sofr skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_bts_border.py           || echo "$(date '+%F %T') bts_border skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sec_late_filers.py      || echo "$(date '+%F %T') sec_late_filers skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fed_press.py            || echo "$(date '+%F %T') fed_press skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_wh_actions.py           || echo "$(date '+%F %T') wh_actions skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_xbrl_revenue.py     || echo "$(date '+%F %T') sec_xbrl_revenue skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_sec_xbrl_netincome.py   || echo "$(date '+%F %T') sec_xbrl_netincome skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_census_permits.py       || echo "$(date '+%F %T') census_permits skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_census_inventory_sales.py || echo "$(date '+%F %T') census_inv_sales skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_census_intl_trade_hs.py  || echo "$(date '+%F %T') census_intl_trade_hs skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_bls_jolts.py             || echo "$(date '+%F %T') bls_jolts skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_treasury_dts.py          || echo "$(date '+%F %T') treasury_dts skipped"
/usr/bin/timeout 600 /usr/bin/python3 build_census_trade_china.py    || echo "$(date '+%F %T') census_trade_china skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_nyfed_soma.py            || echo "$(date '+%F %T') nyfed_soma skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_nhc_tropical.py          || echo "$(date '+%F %T') nhc_tropical skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_noaa_tides.py            || echo "$(date '+%F %T') noaa_tides skipped"
/usr/bin/timeout 180 /usr/bin/python3 build_epa_echo.py              || echo "$(date '+%F %T') epa_echo skipped"
/usr/bin/timeout 90  /usr/bin/python3 build_eia_steo.py              || echo "$(date '+%F %T') eia_steo skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_census_resconst.py       || echo "$(date '+%F %T') census_resconst skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_census_vacancies.py      || echo "$(date '+%F %T') census_vacancies skipped"
/usr/bin/timeout 180 /usr/bin/python3 build_usdm_drought.py          || echo "$(date '+%F %T') usdm_drought skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_nyfed_rates.py           || echo "$(date '+%F %T') nyfed_rates skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_nyfed_rrp.py             || echo "$(date '+%F %T') nyfed_rrp skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_imf_macro.py             || echo "$(date '+%F %T') imf_macro skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_eurostat_inflation.py    || echo "$(date '+%F %T') eurostat_inflation skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_treasury_mts.py          || echo "$(date '+%F %T') treasury_mts skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_crypto_funding.py        || echo "$(date '+%F %T') crypto_funding skipped"
/usr/bin/timeout 180 /usr/bin/python3 build_manifold_macro.py        || echo "$(date '+%F %T') manifold_macro skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_nws_alerts.py            || echo "$(date '+%F %T') nws_alerts skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_metar_hubs.py            || echo "$(date '+%F %T') metar_hubs skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_usgs_waterflow.py        || echo "$(date '+%F %T') usgs_waterflow skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_openmeteo_ag.py          || echo "$(date '+%F %T') openmeteo_ag skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_wildfires.py             || echo "$(date '+%F %T') wildfires skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_govtrack_bills.py        || echo "$(date '+%F %T') govtrack_bills skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_crypto_global.py         || echo "$(date '+%F %T') crypto_global skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_nasdaq_halts.py          || echo "$(date '+%F %T') nasdaq_halts skipped"
/usr/bin/timeout 120 /usr/bin/python3 build_nse_india.py             || echo "$(date '+%F %T') nse_india skipped"

# Wave-6c (2026-04-18): FX, global yield, air quality, AI sector, trade-flow
/usr/bin/timeout 45  /usr/bin/python3 build_coinbase_spot.py         || echo "$(date '+%F %T') coinbase_spot skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_boc_yields.py            || echo "$(date '+%F %T') boc_yields skipped"
/usr/bin/timeout 180 /usr/bin/python3 build_open_meteo_aq.py         || echo "$(date '+%F %T') open_meteo_aq skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_huggingface_trending.py  || echo "$(date '+%F %T') huggingface_trending skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_cbp_border_wait.py       || echo "$(date '+%F %T') cbp_border_wait skipped"
/usr/bin/timeout 180 /usr/bin/python3 build_ndbc_buoys.py            || echo "$(date '+%F %T') ndbc_buoys skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_nasa_neos.py             || echo "$(date '+%F %T') nasa_neos skipped"

# Wave-6d (2026-04-18): UK ONS, energy-weather, top movers, on-chain
/usr/bin/timeout 45  /usr/bin/python3 build_uk_ons_inflation.py      || echo "$(date '+%F %T') uk_ons_inflation skipped"
/usr/bin/timeout 240 /usr/bin/python3 build_nasa_power.py            || echo "$(date '+%F %T') nasa_power skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_av_movers.py             || echo "$(date '+%F %T') av_movers skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_btc_eth_network.py       || echo "$(date '+%F %T') btc_eth_network skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_uk_grid_transport.py     || echo "$(date '+%F %T') uk_grid_transport skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_github_trending.py       || echo "$(date '+%F %T') github_trending skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_nordic_grid.py           || echo "$(date '+%F %T') nordic_grid skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_yahoo_trending.py        || echo "$(date '+%F %T') yahoo_trending skipped"
/usr/bin/timeout 45  /usr/bin/python3 build_space_launches.py        || echo "$(date '+%F %T') space_launches skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_hn_tech.py               || echo "$(date '+%F %T') hn_tech skipped"

# ── Wave-6 orphan-spoke reclaim (Apr 18): working stdlib-only spokes ──
# Rates / macro
/usr/bin/timeout 30  /usr/bin/python3 build_yield_curve.py          || echo "$(date '+%F %T') yield_curve skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fed_balance_sheet.py    || echo "$(date '+%F %T') fed_balance_sheet skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_credit_spreads.py       || echo "$(date '+%F %T') credit_spreads skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_cpi_components.py       || echo "$(date '+%F %T') cpi_components skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_ppi_components.py       || echo "$(date '+%F %T') ppi_components skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_mba_mortgage.py         || echo "$(date '+%F %T') mba_mortgage skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_industrial_production.py || echo "$(date '+%F %T') industrial_production skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_consumer_credit.py      || echo "$(date '+%F %T') consumer_credit skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_treasury_tic.py         || echo "$(date '+%F %T') treasury_tic skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_adp_payrolls.py         || echo "$(date '+%F %T') adp_payrolls skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_bls_wages.py            || echo "$(date '+%F %T') bls_wages skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_retail_sales.py         || echo "$(date '+%F %T') retail_sales skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_housing_starts.py       || echo "$(date '+%F %T') housing_starts skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_home_sales.py           || echo "$(date '+%F %T') home_sales skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_case_shiller.py         || echo "$(date '+%F %T') case_shiller skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_umich_sentiment.py      || echo "$(date '+%F %T') umich_sentiment skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_trade_balance.py        || echo "$(date '+%F %T') trade_balance skipped"
# Sectoral / alt-data
/usr/bin/timeout 30  /usr/bin/python3 build_eia_natgas.py           || echo "$(date '+%F %T') eia_natgas skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_bts_airline_delays.py   || echo "$(date '+%F %T') bts_airline_delays skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_aar_railcars.py         || echo "$(date '+%F %T') aar_railcars skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fda_warning_letters.py  || echo "$(date '+%F %T') fda_warning_letters skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_cdc_fluview.py          || echo "$(date '+%F %T') cdc_fluview skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_cdc_wastewater.py       || echo "$(date '+%F %T') cdc_wastewater skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_fdic_bank_watch.py      || echo "$(date '+%F %T') fdic_bank_watch skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_cfpb_complaints.py      || echo "$(date '+%F %T') cfpb_complaints skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_cisa_kev.py             || echo "$(date '+%F %T') cisa_kev skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_usgs_earthquake.py      || echo "$(date '+%F %T') usgs_earthquake skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_netflix_top10.py        || echo "$(date '+%F %T') netflix_top10 skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_box_office.py           || echo "$(date '+%F %T') box_office skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_canopy.py               || echo "$(date '+%F %T') canopy skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_global_cb_calendar.py   || echo "$(date '+%F %T') global_cb_calendar skipped"
# Alt-data sentiment
/usr/bin/timeout 30  /usr/bin/python3 build_reddit_wsb.py           || echo "$(date '+%F %T') reddit_wsb skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_hacker_news.py          || echo "$(date '+%F %T') hacker_news skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_steam_concurrent.py     || echo "$(date '+%F %T') steam_concurrent skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_world_bank_gdp.py       || echo "$(date '+%F %T') world_bank_gdp skipped"
# Crypto
/usr/bin/timeout 30  /usr/bin/python3 build_crypto_treasury.py      || echo "$(date '+%F %T') crypto_treasury skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_crypto_onchain.py       || echo "$(date '+%F %T') crypto_onchain skipped"
/usr/bin/timeout 30  /usr/bin/python3 build_defillama_tvl.py        || echo "$(date '+%F %T') defillama_tvl skipped"
# Scanner internals
/usr/bin/timeout 60  /usr/bin/python3 build_alpha_factors.py        || echo "$(date '+%F %T') alpha_factors skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_sympathy_matrix.py      || echo "$(date '+%F %T') sympathy_matrix skipped"
/usr/bin/timeout 60  /usr/bin/python3 build_penny_universe.py       || echo "$(date '+%F %T') penny_universe skipped"

/usr/bin/python3 generate_seo_site.py || fail_alert "generate_seo_site.py failed — scanner artifact invalid or empty"
/usr/bin/python3 "$ROOT/everos_pipeline_ingest.py" --mode "$RUN_MODE" --status success || echo "everos_pipeline_ingest skipped"
# Phase 2: publish pipeline_complete to Redis → HUD WebSocket clients
/usr/bin/python3 cerebro_publisher.py --event=pipeline_complete || true

# ── Data Integrity Watchdog — runs after site generation ─────────────────────
# Checks 5 atomic-layer factors; alerts Telegram on any drift.
/usr/bin/python3 data_integrity_watchdog.py --quiet &&   echo "$(date '+%F %T %Z') watchdog_clean" ||   echo "$(date '+%F %T %Z') watchdog_ALERT_sent"

if [[ "$RUN_MODE" == "intraday" ]]; then
  write_pipeline_manifest
  /usr/bin/python3 "$ROOT/cerebro_verify.py"   --mode manifest   --manifest "$ROOT/pipeline_manifest.json"   --base-url "http://127.0.0.1:8000"   || fail_alert "cerebro_verify manifest check failed"
  echo "$(date '+%F %T %Z') intraday_refresh_complete"
  echo "$(date '+%F %T %Z') job_end"
  exit 0
fi

if [[ "$RUN_MODE" == "build_only" ]]; then
  write_pipeline_manifest
  /usr/bin/python3 "$ROOT/cerebro_verify.py"   --mode manifest   --manifest "$ROOT/pipeline_manifest.json"   --base-url "http://127.0.0.1:8000"   || fail_alert "cerebro_verify manifest check failed"
  echo "$(date '+%F %T %Z') build_only_refresh_complete"
  echo "$(date '+%F %T %Z') job_end"
  exit 0
fi

# Push updated site to GitHub Pages
cd "$ROOT"
git add docs/
git commit -m "chore: daily scanner update $(date '+%F')" && \
  git push origin main && \
  echo "$(date '+%F %T') github_pages_pushed" || \
  echo "$(date '+%F %T') github_pages_push_failed"

# ElevenLabs agent knowledge refresh — keeps the website voice agent up to date
/usr/bin/python3 update_agent_knowledge.py || echo "$(date '+%F %T') agent_knowledge_update skipped"

# Distribution — API-based channels (skip gracefully if env vars missing)
/usr/bin/python3 post_to_telegram.py   || echo "$(date '+%F %T') telegram_post failed"
/usr/bin/python3 post_to_twitter.py    || echo "$(date '+%F %T') twitter_api_post failed"
/usr/bin/python3 post_to_discord.py    || echo "$(date '+%F %T') discord_post failed"
/usr/bin/python3 post_to_reddit.py     || echo "$(date '+%F %T') reddit_post failed"
/usr/bin/python3 post_to_stocktwits.py || echo "$(date '+%F %T') stocktwits_post failed"
/usr/bin/python3 post_to_linkedin.py   || echo "$(date '+%F %T') linkedin_post failed"

# Lead magnet drip emails
/usr/bin/python3 send_cheatsheet_drip.py || echo "$(date '+%F %T') cheatsheet_drip skipped"

# Welcome drip for scanner subscribers
/usr/bin/python3 send_welcome_drip.py || echo "$(date '+%F %T') welcome_drip skipped"

# Congressional trades scraper
/usr/bin/python3 build_congressional_trades.py || echo "$(date '+%F %T') congressional_trades skipped"

# AlphaInsider trade bridge (dry-run + sync positions)
/usr/bin/python3 alphainsider_bridge.py --sync || echo "$(date '+%F %T') alphainsider_bridge skipped"

# Dated archive
STAMP="$(date +%F)"
/usr/bin/cp sec_catalyst_latest.csv "sec_catalyst_${STAMP}.csv"
/usr/bin/cp sec_catalyst_tickers.txt "sec_catalyst_tickers_${STAMP}.txt"
/usr/bin/cp sec_catalyst_ranked.csv "sec_catalyst_ranked_${STAMP}.csv"
/usr/bin/cp sec_catalyst_priority_tickers.txt "sec_catalyst_priority_tickers_${STAMP}.txt"
/usr/bin/cp sec_catalyst_ranked_momentum.csv "sec_catalyst_ranked_momentum_${STAMP}.csv"
/usr/bin/cp sec_catalyst_priority_momentum.txt "sec_catalyst_priority_momentum_${STAMP}.txt"
/usr/bin/cp sec_catalyst_ranked_quality.csv "sec_catalyst_ranked_quality_${STAMP}.csv"
/usr/bin/cp sec_catalyst_priority_quality.txt "sec_catalyst_priority_quality_${STAMP}.txt"
/usr/bin/cp sec_top_gappers.csv "sec_top_gappers_${STAMP}.csv"
/usr/bin/cp sec_top_gappers_tickers.txt "sec_top_gappers_tickers_${STAMP}.txt"
/usr/bin/cp sec_top_value.csv "sec_top_value_${STAMP}.csv"
/usr/bin/cp sec_top_value_tickers.txt "sec_top_value_tickers_${STAMP}.txt"
/usr/bin/cp sec_top_moat.csv "sec_top_moat_${STAMP}.csv"
/usr/bin/cp sec_top_moat_tickers.txt "sec_top_moat_tickers_${STAMP}.txt"
/usr/bin/cp sec_top_moat_core.csv "sec_top_moat_core_${STAMP}.csv"
/usr/bin/cp sec_top_moat_core_tickers.txt "sec_top_moat_core_tickers_${STAMP}.txt"
/usr/bin/cp sec_top_moat_emerging.csv "sec_top_moat_emerging_${STAMP}.csv"
/usr/bin/cp sec_top_moat_emerging_tickers.txt "sec_top_moat_emerging_tickers_${STAMP}.txt"
/usr/bin/cp sec_clean_gappers.csv "sec_clean_gappers_${STAMP}.csv"
/usr/bin/cp sec_clean_gappers_tickers.txt "sec_clean_gappers_tickers_${STAMP}.txt"
/usr/bin/cp sec_clean_value.csv "sec_clean_value_${STAMP}.csv"
/usr/bin/cp sec_clean_value_tickers.txt "sec_clean_value_tickers_${STAMP}.txt"
/usr/bin/cp sec_clean_moat_core.csv "sec_clean_moat_core_${STAMP}.csv"
/usr/bin/cp sec_clean_moat_core_tickers.txt "sec_clean_moat_core_tickers_${STAMP}.txt"
/usr/bin/cp sec_outcome_rows.csv "sec_outcome_rows_${STAMP}.csv"
/usr/bin/cp sec_outcome_summary.csv "sec_outcome_summary_${STAMP}.csv"
/usr/bin/cp news_signals.csv "news_signals_${STAMP}.csv"
/usr/bin/cp news_sector_momentum.csv "news_sector_momentum_${STAMP}.csv"
/usr/bin/cp combined_priority.csv "combined_priority_${STAMP}.csv"
/usr/bin/cp combined_priority_tickers.txt "combined_priority_tickers_${STAMP}.txt"
/usr/bin/cp headline_only_momentum.csv "headline_only_momentum_${STAMP}.csv"
/usr/bin/cp bloomberg_headlines_used.csv "bloomberg_headlines_used_${STAMP}.csv"
/usr/bin/cp scoring_config.json "scoring_config_${STAMP}.json"
if [[ -f scoring_tuning_log.csv ]]; then
  /usr/bin/cp scoring_tuning_log.csv "scoring_tuning_log_${STAMP}.csv"
fi
if [[ -f insider_clusters.csv ]]; then
  /usr/bin/cp insider_clusters.csv "insider_clusters_${STAMP}.csv"
fi
if [[ -f keyword_hits.csv ]]; then
  /usr/bin/cp keyword_hits.csv "keyword_hits_${STAMP}.csv"
fi
if [[ -f macro_context.json ]]; then
  /usr/bin/cp macro_context.json "macro_context_${STAMP}.json"
fi
if [[ -f short_interest.csv ]]; then
  /usr/bin/cp short_interest.csv "short_interest_${STAMP}.csv"
fi
if [[ -f short_data.csv ]]; then
  /usr/bin/cp short_data.csv "short_data_${STAMP}.csv"
fi
if [[ -f options_flow.csv ]]; then
  /usr/bin/cp options_flow.csv "options_flow_${STAMP}.csv"
fi
if [[ -f wsb_mentions.csv ]]; then
  /usr/bin/cp wsb_mentions.csv "wsb_mentions_${STAMP}.csv"
fi
if [[ -f squeeze_candidates.csv ]]; then
  /usr/bin/cp squeeze_candidates.csv "squeeze_candidates_${STAMP}.csv"
fi
if [[ -f convergence_alerts.csv ]]; then
  /usr/bin/cp convergence_alerts.csv "convergence_alerts_${STAMP}.csv"
fi
if [[ -f deepvalue_screen.csv ]]; then
  /usr/bin/cp deepvalue_screen.csv "deepvalue_screen_${STAMP}.csv"
fi
if [[ -f smart_money.csv ]]; then
  /usr/bin/cp smart_money.csv "smart_money_${STAMP}.csv"
fi
if [[ -f dark_pool.csv ]]; then
  /usr/bin/cp dark_pool.csv "dark_pool_${STAMP}.csv"
fi
if [[ -f merger_signals.csv ]]; then
  /usr/bin/cp merger_signals.csv "merger_signals_${STAMP}.csv"
fi
if [[ -f lockup_calendar.csv ]]; then
  /usr/bin/cp lockup_calendar.csv "lockup_calendar_${STAMP}.csv"
fi
if [[ -f nt_radar.csv ]]; then
  /usr/bin/cp nt_radar.csv "nt_radar_${STAMP}.csv"
fi
if [[ -f revenue_inflection.csv ]]; then
  /usr/bin/cp revenue_inflection.csv "revenue_inflection_${STAMP}.csv"
fi
if [[ -f newsletter_body.html ]]; then
  /usr/bin/cp newsletter_body.html "newsletter_body_${STAMP}.html"
fi
if [[ -f newsletter_picks.json ]]; then
  /usr/bin/cp newsletter_picks.json "newsletter_picks_${STAMP}.json"
fi
if [[ -f daily_recap_summary.json ]]; then
  /usr/bin/cp daily_recap_summary.json "daily_recap_summary_${STAMP}.json"
fi
if [[ -f sec_income_picks.csv ]]; then
  /usr/bin/cp sec_income_picks.csv "sec_income_picks_${STAMP}.csv"
fi

write_pipeline_manifest
/usr/bin/python3 "$ROOT/cerebro_verify.py"   --mode manifest   --manifest "$ROOT/pipeline_manifest.json"   --base-url "http://127.0.0.1:8000"   || fail_alert "cerebro_verify manifest check failed"

# Newsletter delivery — premium and free sent separately, each gated by its own flag.
# Premium: sent by send_premium_newsletter.sh at 3:30 AM ET.
# Free:    sent here at 4:05 AM ET (FREE_ONLY=1).
FREE_FLAG="$ROOT/.newsletter_free_sent_${STAMP}"
if [[ -f "$FREE_FLAG" ]]; then
  echo "$(date '+%F %T %Z') free newsletter already sent today - skipping"
else
  SMTP_OK=0
  BEEHIIV_OK=0

  if [[ -n "${SMTP_HOST:-}" && -n "${SMTP_PORT:-}" && -n "${SMTP_USER:-}" && -n "${SMTP_PASS:-}" ]]; then
    echo "$(date '+%F %T %Z') free_email_send_start"
    set +e
    NEWSLETTER_MODE=1 FREE_ONLY=1 /usr/bin/python3 "$ROOT/send_sec_catalyst_email.py"
    SEND_EXIT=$?
    set -e
    if [[ $SEND_EXIT -eq 0 ]]; then
      echo "$(date '+%F %T %Z') free_email_send_ok"
      SMTP_OK=1
    elif [[ $SEND_EXIT -eq 2 ]]; then
      echo "$(date '+%F %T %Z') free_email_send_partial_failure - check delivery_log_${STAMP}.txt"
      SMTP_OK=1
    else
      echo "$(date '+%F %T %Z') free_email_send_FAILED exit=$SEND_EXIT"
    fi
  else
    echo "$(date '+%F %T %Z') free_email_send_skipped: SMTP env vars not fully set"
  fi

  if [[ $SMTP_OK -eq 1 ]]; then
    touch "$FREE_FLAG"
    # Keep old flag name for backwards compat with any external checks
    touch "$ROOT/.newsletter_sent_${STAMP}"
  else
    echo "$(date '+%F %T %Z') free_delivery_failed - no free newsletter transport succeeded (WSL sends instead)"
    # NOTE: Do NOT exit 1 here. DigitalOcean blocks SMTP port 587.
    # Newsletter delivery is handled by WSL cron at 4:15 AM ET.
  fi
fi

# Welcome journey: runs every pipeline pass (not gated by newsletter flag)
# to catch new subscribers quickly and send timely Day 0/3/7/14 emails.
if [[ -n "${BEEHIIV_API_KEY:-}" && -n "${SMTP_HOST:-}" && -n "${SMTP_USER:-}" && -n "${SMTP_PASS:-}" ]]; then
  echo "$(date '+%F %T %Z') welcome_journey_start"
  /usr/bin/python3 welcome_journey.py && \
    echo "$(date '+%F %T %Z') welcome_journey_ok" || \
    echo "$(date '+%F %T %Z') welcome_journey_failed"
else
  echo "$(date '+%F %T') welcome_journey skipped: BEEHIIV_API_KEY or SMTP env vars not set"
fi

# Social post generation: runs every pipeline pass.
echo "$(date '+%F %T %Z') social_post_start"
/usr/bin/python3 social_post.py && \
  echo "$(date '+%F %T %Z') social_post_ok" || \
  echo "$(date '+%F %T %Z') social_post_failed"

# Reddit engagement comments: generated once per day alongside social posts
/usr/bin/python3 build_reddit_comments.py && \
  echo "$(date '+%F %T %Z') reddit_comments_ok" || \
  echo "$(date '+%F %T %Z') reddit_comments_skipped"

# Referral share messages + performance scorecard
/usr/bin/python3 build_referral_engine.py && \
  echo "$(date '+%F %T %Z') referral_engine_ok" || \
  echo "$(date '+%F %T %Z') referral_engine_skipped"

# Educational thread: generated once per week (Monday), saved for manual review/posting.
if [[ "$(date +%u)" == "1" ]]; then
  EDU_FLAG="$ROOT/.edu_thread_generated_$(date +%Y-%W)"
  if [[ ! -f "$EDU_FLAG" ]]; then
    /usr/bin/python3 build_educational_thread.py && \
      touch "$EDU_FLAG" && \
      echo "$(date '+%F %T %Z') edu_thread_generated" || \
      echo "$(date '+%F %T %Z') edu_thread_failed"
  fi
  # NOTE: edu thread posting via post_edu_thread.cjs removed (requires Windows Playwright).
  # The thread is still generated and saved for manual posting or API-based posting later.
fi

# StockTwits: removed — posting access lost, platform no longer viable.

# Generate social media visual assets — gated by own flag so they run once/day
# regardless of whether the newsletter email was sent.
SOCIAL_ASSETS_FLAG="$ROOT/.social_assets_generated_${STAMP}"
if [[ ! -f "$SOCIAL_ASSETS_FLAG" ]]; then
  echo "$(date '+%F %T %Z') social_assets_start"

  # Instagram card (1080x1080 PNG) + carousel (5-slide swipeable)
  /usr/bin/python3 generate_instagram_card.py && \
    echo "$(date '+%F %T %Z') instagram_card_ok" || \
    echo "$(date '+%F %T %Z') instagram_card_failed"
  /usr/bin/python3 generate_instagram_carousel.py && \
    echo "$(date '+%F %T %Z') instagram_carousel_ok" || \
    echo "$(date '+%F %T %Z') instagram_carousel_failed"

  # TikTok/Shorts video (1080x1920 MP4)
  /usr/bin/python3 generate_tiktok_video.py && \
    echo "$(date '+%F %T %Z') tiktok_video_ok" || \
    echo "$(date '+%F %T %Z') tiktok_video_failed"

  # Cinematic daily briefing (Pillow + FFmpeg Ken Burns — no paid APIs)
  /usr/bin/python3 generate_cinematic_video.py && \
    echo "$(date '+%F %T %Z') cinematic_video_ok" || \
    echo "$(date '+%F %T %Z') cinematic_video_skipped"

  touch "$SOCIAL_ASSETS_FLAG"
  echo "$(date '+%F %T %Z') social_assets_generated stamp=${STAMP}"

  # Create a trigger file that Windows Task Scheduler or run_social_posts.sh picks up
  touch "$ROOT/.social_post_pending_${STAMP}"
  echo "$(date '+%F %T %Z') social_post_pending_flag_created stamp=${STAMP}"
fi

# ── Intraday posts: time-gated by ET hour ─────────────────────────────────────
HOUR_ET=$(TZ="America/New_York" date +%H)
MIN_ET=$(TZ="America/New_York" date +%M)

# Market open recap (9:30am-10:30am ET)
if [[ "$HOUR_ET" -eq 9 && "$MIN_ET" -ge 30 ]] || [[ "$HOUR_ET" -eq 10 ]]; then
  echo "$(date '+%F %T %Z') open_recap_start"
  /usr/bin/python3 post_open_recap.py && \
    echo "$(date '+%F %T %Z') open_recap_ok" || \
    echo "$(date '+%F %T %Z') open_recap_failed"
fi

# Price alerts (9:30am-4pm ET — run every pass during market hours)
if [[ "$HOUR_ET" -ge 9 && "$HOUR_ET" -lt 16 ]]; then
  if [[ "$HOUR_ET" -gt 9 || "$MIN_ET" -ge 30 ]]; then
    echo "$(date '+%F %T %Z') price_alert_check"
    /usr/bin/python3 post_price_alert.py && \
      echo "$(date '+%F %T %Z') price_alert_ok" || \
      echo "$(date '+%F %T %Z') price_alert_failed"
  fi
fi

# Midday update (1:00pm-3:00pm ET)
if [[ "$HOUR_ET" -ge 13 && "$HOUR_ET" -lt 15 ]]; then
  echo "$(date '+%F %T %Z') midday_update_start"
  /usr/bin/python3 post_midday_update.py && \
    echo "$(date '+%F %T %Z') midday_update_ok" || \
    echo "$(date '+%F %T %Z') midday_update_failed"
fi

# EOD recap (4:00pm-5:30pm ET)
if [[ "$HOUR_ET" -ge 16 && "$HOUR_ET" -lt 18 ]]; then
  echo "$(date '+%F %T %Z') eod_recap_start"
  # Daily win-rate scorecard — Top 10 combined + Top 10 gappers
  /usr/bin/python3 daily_recap.py --top 10 --source combined && \
    echo "$(date '+%F %T %Z') daily_recap_combined_ok" || \
    echo "$(date '+%F %T %Z') daily_recap_combined_failed"
  /usr/bin/python3 daily_recap.py --top 10 --source gappers && \
    echo "$(date '+%F %T %Z') daily_recap_gappers_ok" || \
    echo "$(date '+%F %T %Z') daily_recap_gappers_failed"
  /usr/bin/python3 post_eod_recap.py && \
    echo "$(date '+%F %T %Z') eod_recap_ok" || \
    echo "$(date '+%F %T %Z') eod_recap_failed"
fi

# ── Cerebro Overnight Enrichment (Sunday 11 PM ET, non-blocking) ──────────────
# LEI/FIGI warm-up: top 2K tickers — runs once weekly, results are permanent
# LLM classifier: ambiguous SIC → verified GICS sub-industry via Anthropic API
if [[ "$(date +%u)" = "7" && "$HOUR_ET" -ge 23 ]]; then
  echo "$(date '+%F %T %Z') cerebro_enrichment_start"
  /usr/bin/python3 build_lei_enrichment.py --limit=2000 || \
    echo "$(date '+%F %T %Z') lei_enrichment skipped"
  /usr/bin/python3 classify_ambiguous_gics.py --limit=500 || \
    echo "$(date '+%F %T %Z') gics_classify skipped"
  # Re-run gravity engine after enrichment to pick up new market caps
  /usr/bin/python3 gravity_engine.py || \
    echo "$(date '+%F %T %Z') gravity_engine skipped"
  echo "$(date '+%F %T %Z') cerebro_enrichment_end"
fi

echo "$(date '+%F %T %Z') job_end"
