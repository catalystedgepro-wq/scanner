#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${CEREBRO_DEPLOY_HOST:-cerebro}"
REMOTE_ROOT="${CEREBRO_REMOTE_ROOT:-auto}"
SERVICE="${CEREBRO_SERVICE:-cerebro}"
BASE_URL="${CEREBRO_BASE_URL:-http://67.205.148.181}"
MODE="all"
VERIFY_INTELLIGENCE="${CEREBRO_VERIFY_INTELLIGENCE:-0}"
VERIFY_RANKED_SCAN_LIMIT="${CEREBRO_VERIFY_RANKED_SCAN_LIMIT:-25}"
VERIFY_TICKERS=()
declare -a REMOTE_ROOTS=()

SYNC_FILES=(
  "api_server.py"
  "build_universe_gravity.py"
  "build_options_flow.py"
  "build_sympathy_logger.py"
  "cerebro.service"
  "cerebro-logger.service"
  "generate_seo_site.py"
  "macro_engine.py"
  "market_data_contract.py"
  "openbb_bridge.py"
  "velocity_deck_schema.py"
  "everos_memory_client.py"
  "everos_pipeline_ingest.py"
  "run_daily_sec_catalyst.sh"
  "send_free_newsletter.sh"
  "send_premium_newsletter.sh"
  "send_sec_catalyst_email.py"
  "sec_catalyst_list.py"
  "rank_sec_catalysts.py"
  "classify_sec_catalysts.py"
  "build_news_momentum.py"
  "evaluate_sec_outcomes.py"
  "tune_scoring_config.py"
  "scoring_engine.py"
  "scoring_config.json"
  "build_newsletter_picks.py"
  "publish_to_beehiiv.cjs"
  "silent_logger.py"
  "spoke_options.py"
  "spoke_bedrock.py"
  "spoke_weather.py"
  "spoke_memory.py"
  "spoke_legal.py"
  "spoke_thetadata.py"
  "spoke_supplychain.py"
  "CEREBRO_EVERMIND_INTEGRATION.md"
  "CEREBRO_MEMORY_AGENT_POLICY.md"
  ".agents/skills/everos-memory-os/SKILL.md"
  ".agents/skills/msa-memory-sparse-attention/SKILL.md"
  "ops/check_mnemosyne_lanes.sh"
  "ops/check_sympathy_burst.py"
  "ops/sympathy_burst_watch.sh"
  "ops/install_sympathy_monitor_cron_droplet.sh"
  "ops/CEREBRO_SYMPATHY_MONITOR.md"
  "ops/phase4_long_tail_burnin.py"
  "ops/everos_dark_launch.sh"
  "ops/run_pipeline_droplet.sh"
  "ops/scanner_refresh.crontab.example"
  "ops/install_scanner_cron_droplet.sh"
  "ops/sync_openbb_provider_settings.py"
  "ops/n8n/.env.example"
  "ops/n8n/docker-compose.yml.example"
  "ops/n8n/workflows/cerebro_premarket_pipeline.json"
  "ops/n8n/workflows/cerebro_intraday_refresh_gatekeeper.json"
  "ops/n8n/workflows/cerebro_mnemosyne_gate.json"
  "sector_lookup.json"
  ".gics_sic_cache.json"
  # Free-Data Wiring Sprint (Apr 2026) — 29 public feeds
  "build_dod_contracts.py"
  "build_cftc_cot.py"
  "build_eia_petroleum.py"
  "build_earnings_calendar.py"
  "build_press_wires.py"
  "build_stocktwits_trending.py"
  "build_reddit_velocity.py"
  "build_google_trends.py"
  "build_13f_whales.py"
  "build_edgar_fulltext.py"
  "build_fred_macro.py"
  "build_uspto_feed.py"
  "build_bls_calendar.py"
  "build_treasury_ofac.py"
  "build_sedar_canada.py"
  "build_usda_wasde.py"
  "build_courtlistener_recap.py"
  "build_github_velocity.py"
  "build_arxiv_cashtag.py"
  "build_adsb_jets.py"
  "build_fomc_calendar.py"
  "build_ism_adp.py"
  "build_opensecrets.py"
  "build_tsa_volume.py"
  "build_crypto_correlation.py"
  "build_fda_pdufa.py"
  "build_regsho_threshold.py"
  "build_clinical_trials.py"
  "build_form_144.py"
  "free_data_inventory.md"
  # Wave 2 (Apr 17-18, 2026) — +44 public feeds
  "build_pce_prices.py"
  "build_aaa_gas_prices.py"
  "build_fed_funds_futures.py"
  "build_mortgage_rates.py"
  "build_zillow_rent.py"
  "build_fda_approvals.py"
  "build_fda_recalls.py"
  "build_fda_drug_shortages.py"
  "build_jobless_claims.py"
  "build_money_supply.py"
  "build_philly_fed.py"
  "build_durable_goods.py"
  "build_leading_index.py"
  "build_global_rates.py"
  "build_fx_rates.py"
  "build_commodity_spot.py"
  "build_sec_form_d.py"
  "build_edgar_ipos.py"
  "build_sec_13f.py"
  "build_noaa_hurricane.py"
  "build_usgs_earthquakes.py"
  "build_noaa_weather_alerts.py"
  "build_cpsc_recalls.py"
  "build_opec_crude.py"
  "build_reddit_investing.py"
  "build_crypto_defi.py"
  "build_crypto_exchanges.py"
  "build_crypto_stablecoins.py"
  "build_federal_register.py"
  "build_ofac_sanctions.py"
  "build_treasury_auctions.py"
  "build_wiki_pageviews.py"
  "build_eia_nat_gas.py"
  "build_app_store_top.py"
  "build_finra_reg_sho.py"
  "build_baker_hughes_rigs.py"
  "build_sec_ftd.py"
  "build_tsa_throughput.py"
  "build_bls_employment.py"
  "build_bea_trade.py"
  "build_aar_railroad.py"
  "build_macro_bundle.py"
  "build_fdic_failures.py"
  "build_fema_disasters.py"
  "build_gdelt_events.py"
  # Wave 3 (Apr 18, 2026) — +3 feeds
  "build_vix_complex.py"
  "build_oecd_cli.py"
  "build_cdc_hospital.py"
  # Wave 4 (Apr 18, 2026) — macro surprise, financial conditions,
  # consumer mobility, sentiment, and labor slack.
  "build_gdpnow.py"
  "build_nfci.py"
  "build_mta_ridership.py"
  "build_fear_greed.py"
  "build_jolts.py"
  "build_trade_flows.py"
  # Wave 5 (Apr 18, 2026) — retail attention, FDA recalls, treasury fiscal
  "build_wiki_attention.py"
  "build_fda_enforcement.py"
  "build_treasury_fiscal.py"
  "build_unemployment_claims.py"
  "build_going_concern.py"
  "build_crypto_fear_greed.py"
  "build_btc_mining.py"
  "build_hurricane_radar.py"
  "build_usgs_quakes.py"
  "build_faa_delays.py"
  "build_nasa_eonet.py"
  "build_bls_macro.py"
  "build_space_weather.py"
  "build_worldbank_gdp.py"
  "build_epa_tri.py"
  "build_fbi_crime.py"
  "build_coingecko_top.py"
  "build_statcan_macro.py"
  "build_cb_press.py"
  "build_usaspending_awards.py"
  "build_treasury_fx.py"
  "build_edgar_fts.py"
  "build_congress_events.py"
  "build_goes_xray.py"
  "build_nasa_neo.py"
  "build_swpc_alerts.py"
  "build_swpc_kp.py"
  "build_solar_cycle.py"
  "build_ace_mag.py"
  "build_fda_drug_ae.py"
  "build_fda_device_ae.py"
  "build_fda_tobacco.py"
  "build_sec_425.py"
  "build_sec_schedules.py"
  "build_sec_proxy_fight.py"
  "build_regs_dockets.py"
  "build_spaceflight_news.py"
  "build_fhfa_hpi.py"
  "build_swpc_forecast.py"
  "build_swpc_wind.py"
  "build_worldbank_unemployment.py"
  "build_worldbank_cpi.py"
  "build_bis_dollar.py"
  "build_schedule_13d.py"
  "build_blockchair_onchain.py"
  "build_comtrade_flows.py"
  "build_climate_signals.py"
  "build_bis_rates.py"
  "build_defillama_dexs.py"
  "build_fao_food_prices.py"
  "build_github_ai_velocity.py"
  "build_ecb_monetary.py"
  "build_fda_510k.py"
  "build_zillow_zhvi.py"
  "build_realtor_inventory.py"
  "build_spc_storms.py"
  "build_stablecoins.py"
  "build_btc_mempool.py"
  "build_ofr_fsi.py"
  "build_sec_litigation.py"
  "build_pypi_velocity.py"
  "build_npm_velocity.py"
  "build_fbx_freight.py"
  "build_ercot_fuelmix.py"
  "build_caiso_grid.py"
  "build_nyiso_grid.py"
  "build_bpa_balancing.py"
  "build_cve_velocity.py"
  "build_kalshi_macro.py"
  "build_eu_indpro.py"
  "build_eu_retail.py"
  "build_fed_speeches.py"
  "build_gdacs_disasters.py"
  "build_sec_delisting.py"
  "build_hnews_attention.py"
  "build_producthunt_launches.py"
  "build_asx_announcements.py"
  "build_rba_rates.py"
  "build_hkma_peg.py"
  "build_nbp_fx.py"
  "build_boe_rates.py"
  "build_boi_israel.py"
  "build_lbma_metals.py"
  "build_worldbank_reserves.py"
  "build_treasury_mspd.py"
  "build_snb_swiss.py"
  "build_sec_splits.py"
  "build_sec_buybacks.py"
  "build_sec_corpactions.py"
  "build_sec_risks.py"
  "build_sec_biotech.py"
  "build_sec_distress.py"
  "build_sec_contracts.py"
  "build_sec_legal.py"
  "build_sec_financing.py"
  "build_sec_cmgmt.py"
  "build_sec_restruct.py"
  "build_sec_despac.py"
  "build_sec_governance.py"
  "build_sec_crisis.py"
  "build_sec_whistleblower.py"
  "build_sec_fda.py"
  "build_sec_labor.py"
  "build_sec_dealterms.py"
  "build_sec_crypto.py"
  "build_sec_geopol.py"
  "build_sec_divest.py"
  "build_sec_audit.py"
  "build_sec_banking.py"
  "build_sec_energy_tx.py"
  "build_sec_weather.py"
  "build_finra_short_volume.py"
  "build_cma_uk.py"
  "build_jpx_tdnet.py"
  "build_sec_press.py"
  "build_fed_register.py"
  "build_clinicaltrials.py"
  "build_fda_press.py"
  "build_securities_litigation.py"
  "build_sec_xbrl_frames.py"
  "build_tech_status.py"
  "build_sec_form3.py"
  "build_predictit.py"
  "build_sec_form144.py"
  "build_sec_s4.py"
  "build_sec_tender.py"
  "build_sec_merger_proxy.py"
  "build_sec_ipo_pipe.py"
  "build_sec_restatements.py"
  "build_sec_arrangements.py"
  "build_sec_debt.py"
  "build_sec_spinoff_reg.py"
  "build_sec_poison_pill.py"
  "build_sec_late_filing.py"
  "build_sec_uplist.py"
  "build_ftc_actions.py"
  "build_cfpb_enforcement.py"
  "build_fca_uk.py"
  "build_csa_canada.py"
  "build_esma_eu.py"
  "build_doj_news.py"
  "build_fed_enforcement.py"
  "build_boj_japan.py"
  "build_boc_canada.py"
  "build_ecb_press.py"
  "build_cboe_vix_gaps.py"
  "build_aisi_steel.py"
  "build_worldsteel.py"
  "build_who_health.py"
  "build_volcano_activity.py"
  "build_boeing_press.py"
  "build_rbi_india.py"
  "build_cdc_newsroom.py"
  "build_china_nbs.py"
  "build_fsb_stability.py"
  "build_eba_banking.py"
  "build_ustr_trade.py"
  "build_cbo_fiscal.py"
  "build_gao_reports.py"
  "build_eia_tie.py"
  "build_nasa_news.py"
  "build_space_force.py"
  "build_army_amc.py"
  "build_uscourts.py"
  "build_bbc_business.py"
  "build_cointelegraph.py"
  "build_bea_news.py"
  "build_bostonfed.py"
  "build_sffed.py"
  "build_nber.py"
  "build_dallasfed.py"
  "build_stlouisfed.py"
  "build_boe_news.py"
  "build_fred_blog.py"
  "build_census_news.py"
  "build_ons_uk_releases.py"
  "build_nist_news.py"
  "build_congress_bills.py"
  "build_sec_speeches.py"
  "build_bis_cb_speeches.py"
  "build_usda_ams.py"
  "build_nsf_news.py"
  "build_eu_commission.py"
  "build_iaea_nuclear.py"
  "build_un_news.py"
  "build_bis_workingpapers.py"
  "build_fedscoop.py"
  "build_cyberscoop.py"
  "build_defensescoop.py"
  "build_statescoop.py"
  "build_nextgov.py"
  "build_federalnewsnetwork.py"
  "build_govexec.py"
  "build_meritalk.py"
  "build_ustr.py"
  "build_occ.py"
  "build_fed_testimony.py"
  "build_paho.py"
  "build_usitc.py"
  "build_ftc.py"
  "build_doj.py"
  "build_ferc.py"
  "build_cftc.py"
  "build_osha.py"
  "build_fcc.py"
  "build_fec_fundraising.py"
  "build_bcb_brazil.py"
  "build_sarb_safrica.py"
  "build_cbr_russia.py"
  "build_norges_bank.py"
  "build_bcrp_peru.py"
  "build_banrep_colombia.py"
  "build_jpl_news.py"
  "build_fedreg_preview.py"
  "build_openalex_biotech.py"
  "build_treasury_interest.py"
  "build_treasury_sales.py"
  "build_coingecko_derivatives.py"
  "build_enso_state.py"
  "build_ecb_fx.py"
  "build_wiki_trending.py"
  "build_form144.py"
  "build_census_retail.py"
  "build_census_wholesale.py"
  "build_census_bfs.py"
  "build_pubmed_biotech.py"
  "build_usgs_streamflow.py"
  "build_nhtsa_recalls.py"
  "build_openfda_adverse.py"
  "build_vix_term.py"
  "build_sec_13f.py"
  "build_usa_spending.py"
  "build_fec_megadonors.py"
  "build_nyfed_sofr.py"
  "build_bts_border.py"
  "build_sec_late_filers.py"
  "build_fed_press.py"
  "build_wh_actions.py"
  "build_sec_xbrl_revenue.py"
  "build_sec_xbrl_netincome.py"
  "build_census_permits.py"
  "build_census_inventory_sales.py"
  "build_census_intl_trade_hs.py"
  "build_bls_jolts.py"
  "build_treasury_dts.py"
  "build_census_trade_china.py"
  "build_nyfed_soma.py"
  "build_nhc_tropical.py"
  "build_noaa_tides.py"
  "build_epa_echo.py"
  "build_eia_steo.py"
  "build_census_resconst.py"
  "build_census_vacancies.py"
  "build_usdm_drought.py"
  "build_nyfed_rates.py"
  "build_nyfed_rrp.py"
  "build_imf_macro.py"
  "build_eurostat_inflation.py"
  "build_treasury_mts.py"
  "build_crypto_funding.py"
  "build_manifold_macro.py"
  "build_nws_alerts.py"
  "build_metar_hubs.py"
  "build_usgs_waterflow.py"
  "build_openmeteo_ag.py"
  "build_wildfires.py"
  "build_govtrack_bills.py"
  "build_crypto_global.py"
  "build_nasdaq_halts.py"
  "build_nse_india.py"
  "build_coinbase_spot.py"
  "build_boc_yields.py"
  "build_open_meteo_aq.py"
  "build_huggingface_trending.py"
  "build_cbp_border_wait.py"
  "build_ndbc_buoys.py"
  "build_nasa_neos.py"
  "build_uk_ons_inflation.py"
  "build_nasa_power.py"
  "build_av_movers.py"
  "build_btc_eth_network.py"
  "build_uk_grid_transport.py"
  "build_github_trending.py"
  "build_nordic_grid.py"
  "build_yahoo_trending.py"
  "build_space_launches.py"
  "build_hn_tech.py"
  "build_yield_curve.py"
  "build_fed_balance_sheet.py"
  "build_credit_spreads.py"
  "build_cpi_components.py"
  "build_ppi_components.py"
  "build_mba_mortgage.py"
  "build_industrial_production.py"
  "build_consumer_credit.py"
  "build_treasury_tic.py"
  "build_adp_payrolls.py"
  "build_bls_wages.py"
  "build_retail_sales.py"
  "build_housing_starts.py"
  "build_home_sales.py"
  "build_case_shiller.py"
  "build_umich_sentiment.py"
  "build_trade_balance.py"
  "build_eia_natgas.py"
  "build_bts_airline_delays.py"
  "build_aar_railcars.py"
  "build_fda_warning_letters.py"
  "build_cdc_fluview.py"
  "build_cdc_wastewater.py"
  "build_fdic_bank_watch.py"
  "build_cfpb_complaints.py"
  "build_cisa_kev.py"
  "build_usgs_earthquake.py"
  "build_netflix_top10.py"
  "build_box_office.py"
  "build_canopy.py"
  "build_global_cb_calendar.py"
  "build_reddit_wsb.py"
  "build_hacker_news.py"
  "build_steam_concurrent.py"
  "build_world_bank_gdp.py"
  "build_crypto_treasury.py"
  "build_crypto_onchain.py"
  "build_defillama_tvl.py"
  "build_alpha_factors.py"
  "build_sympathy_matrix.py"
  "build_penny_universe.py"
)

usage() {
  cat <<'EOF'
Usage:
  bash ops/deploy_cerebro_droplet.sh [options]

Options:
  --stage-only              Sync backend files and docs/hud to the droplet, but do not restart.
  --restart-only            Restart the remote service and run health checks without syncing files.
  --verify-only             Run public verification checks only.
  --verify-intelligence     Require live intelligence surfaces instead of allowing fallback/disabled paths.
  --verify-ticker SYMBOL    Add an optional manual probe ticker. Live ranked/public canaries remain the primary deploy gate.
  --host NAME               SSH host or host alias. Defaults to "cerebro".
  --remote-root PATH        Remote app root. Defaults to auto-detect and sync all live roots.
  --service NAME            Systemd service name. Defaults to cerebro.
  --base-url URL            Public base URL. Defaults to http://67.205.148.181.
  --help                    Show this help.

Modes:
  all         local Mnemosyne check + stage + env check + remote Mnemosyne check + atomic restart + public verify
  stage-only  local Mnemosyne check + stage + env check + remote Mnemosyne check
  restart-only env check + remote Mnemosyne check + atomic restart + public verify
  verify-only public verify only
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage-only)
      MODE="stage-only"
      shift
      ;;
    --restart-only)
      MODE="restart-only"
      shift
      ;;
    --verify-only)
      MODE="verify-only"
      shift
      ;;
    --verify-intelligence)
      VERIFY_INTELLIGENCE="1"
      shift
      ;;
    --verify-ticker)
      [[ $# -ge 2 ]] || { echo "Missing value for --verify-ticker" >&2; exit 1; }
      VERIFY_TICKERS+=("$2")
      shift 2
      ;;
    --host)
      [[ $# -ge 2 ]] || { echo "Missing value for --host" >&2; exit 1; }
      HOST="$2"
      shift 2
      ;;
    --remote-root)
      [[ $# -ge 2 ]] || { echo "Missing value for --remote-root" >&2; exit 1; }
      REMOTE_ROOT="$2"
      shift 2
      ;;
    --service)
      [[ $# -ge 2 ]] || { echo "Missing value for --service" >&2; exit 1; }
      SERVICE="$2"
      shift 2
      ;;
    --base-url)
      [[ $# -ge 2 ]] || { echo "Missing value for --base-url" >&2; exit 1; }
      BASE_URL="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

remote() {
  ssh "$HOST" "$@"
}

add_remote_root() {
  local candidate="${1:-}"
  [[ -n "$candidate" ]] || return 0
  local existing
  for existing in "${REMOTE_ROOTS[@]:-}"; do
    [[ "$existing" == "$candidate" ]] && return 0
  done
  REMOTE_ROOTS+=("$candidate")
}

detect_remote_roots() {
  if [[ "$REMOTE_ROOT" != "auto" ]]; then
    add_remote_root "$REMOTE_ROOT"
    return 0
  fi

  local runtime_root
  runtime_root="$(remote "systemctl show -p WorkingDirectory --value '$SERVICE' 2>/dev/null || true")"
  if [[ -n "$runtime_root" ]] && remote "[ -d '$runtime_root' ]"; then
    add_remote_root "$runtime_root"
  fi

  while IFS= read -r candidate; do
    add_remote_root "$candidate"
  done < <(remote "for candidate in /home/operator/.openclaw/workspace /opt/catalyst; do [[ -d \"\$candidate\" ]] && printf '%s\n' \"\$candidate\"; done")

  if [[ ${#REMOTE_ROOTS[@]} -eq 0 ]]; then
    echo "Unable to detect a remote Cerebro root on $HOST" >&2
    exit 1
  fi
}

primary_remote_root() {
  printf '%s\n' "${REMOTE_ROOTS[0]}"
}

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

check_prereqs() {
  require_cmd ssh
  require_cmd rsync
  require_cmd curl
  require_cmd python3
}

check_verify_prereqs() {
  require_cmd curl
  require_cmd python3
}

check_local_mnemosyne_surface() {
  log "Checking local Mnemosyne release surface"
  bash "$WORKSPACE_ROOT/ops/check_mnemosyne_lanes.sh" --mode release
}

_ranked_candidates_from_remote() {
  local remote_root="${1:-}"
  local limit="${2:-$VERIFY_RANKED_SCAN_LIMIT}"
  [[ -n "$remote_root" ]] || return 0
  remote "if [[ -f '$remote_root/sec_catalyst_ranked.csv' ]]; then awk -F, 'NR>1 && NF {print \$1; if (++n==$limit) exit}' '$remote_root/sec_catalyst_ranked.csv'; fi" \
    | tr '[:lower:]' '[:upper:]' | tr -d '\r'
}

_ranked_candidates_from_local() {
  local limit="${1:-$VERIFY_RANKED_SCAN_LIMIT}"
  if [[ -f "$WORKSPACE_ROOT/sec_catalyst_ranked.csv" ]]; then
    awk -F, 'NR>1 && NF {print $1; if (++n=='"$limit"') exit}' "$WORKSPACE_ROOT/sec_catalyst_ranked.csv" \
      | tr '[:lower:]' '[:upper:]' | tr -d '\r'
  fi
}

_ranked_candidates_from_public_universe() {
  curl -fsS "$BASE_URL/api/universe?page=1&per_page=200&min_gravity=0" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
rows = payload.get("tickers") or payload.get("rows") or []
for row in rows:
    ticker = str(row.get("ticker") or "").strip().upper()
    sources = [str(item).lower() for item in (row.get("scanner_sources") or [])]
    if ticker and "ranked" in sources:
        print(ticker)
'
}

public_ticker_probe() {
  local ticker="${1^^}"
  curl -fsS "$BASE_URL/api/ticker/$ticker"
}

ticker_has_ranked_source() {
  local ticker="${1^^}"
  public_ticker_probe "$ticker" | python3 -c '
import json, sys
expected = sys.argv[1]
payload = json.load(sys.stdin)
actual = str(payload.get("ticker") or "").strip().upper()
sources = [str(item).lower() for item in (payload.get("scanner_sources") or [])]
if actual != expected:
    raise SystemExit(1)
if "ranked" not in sources:
    raise SystemExit(1)
' "$ticker"
}

stage_sync() {
  local remote_root rel_path src
  for remote_root in "${REMOTE_ROOTS[@]}"; do
    log "Ensuring remote directories exist on $HOST:$remote_root"
    remote "mkdir -p '$remote_root/docs/hud' '$remote_root/docs/landing' '$remote_root/docs/scanner' '$remote_root/docs/cerebro-landing' '$remote_root/docs/pricing' '$remote_root/docs/glossary' '$remote_root/docs/agency' '$remote_root/docs/videos'"

    log "Syncing backend and Mnemosyne files to $remote_root"
    for rel_path in "${SYNC_FILES[@]}"; do
      src="$WORKSPACE_ROOT/$rel_path"
      if [[ -f "$src" ]]; then
        remote "mkdir -p '$remote_root/$(dirname "$rel_path")'"
        rsync -av "$src" "$HOST:$remote_root/$rel_path"
      fi
    done

    log "Syncing compiled HUD assets to $remote_root"
    rsync -av --delete "$WORKSPACE_ROOT/docs/hud/" "$HOST:$remote_root/docs/hud/"

    log "Syncing landing page to $remote_root"
    rsync -av "$WORKSPACE_ROOT/docs/landing/" "$HOST:$remote_root/docs/landing/"

    log "Syncing Cerebro explainer page to $remote_root"
    rsync -av "$WORKSPACE_ROOT/docs/cerebro-landing/" "$HOST:$remote_root/docs/cerebro-landing/"

    log "Syncing pricing page to $remote_root"
    rsync -av "$WORKSPACE_ROOT/docs/pricing/" "$HOST:$remote_root/docs/pricing/"

    if [[ -d "$WORKSPACE_ROOT/docs/glossary" ]]; then
      log "Syncing glossary pages to $remote_root"
      rsync -av "$WORKSPACE_ROOT/docs/glossary/" "$HOST:$remote_root/docs/glossary/"
    fi

    log "Syncing agency hub page to $remote_root"
    rsync -av "$WORKSPACE_ROOT/docs/agency/" "$HOST:$remote_root/docs/agency/"

    # Sync latest video for agency page
    if [[ -f "$WORKSPACE_ROOT/anchor_video.mp4" ]]; then
      log "Syncing latest briefing video to $remote_root"
      rsync -av "$WORKSPACE_ROOT/anchor_video.mp4" "$HOST:$remote_root/docs/videos/latest-brief.mp4"
    fi
  done
}

check_env() {
  local remote_root env_value
  for remote_root in "${REMOTE_ROOTS[@]}"; do
    log "Checking remote EVEROS guard for $remote_root"
    env_value="$(remote "grep -h '^EVEROS_ENABLED=' '$remote_root/.env' '$remote_root/.sec_email_env' 2>/dev/null | tail -n 1 | cut -d= -f2-")"
    if [[ -z "$env_value" ]]; then
      echo "EVEROS_ENABLED is not set on the droplet for $remote_root. Refusing to proceed." >&2
      exit 1
    fi
    printf 'Remote root %s EVEROS_ENABLED=%s\n' "$remote_root" "$env_value"
    if [[ "$env_value" != "0" ]]; then
      echo "Expected EVEROS_ENABLED=0 before parity deployment for $remote_root." >&2
      exit 1
    fi
  done
}

check_remote_mnemosyne_surface() {
  local remote_root
  for remote_root in "${REMOTE_ROOTS[@]}"; do
    log "Checking remote Mnemosyne runtime surface for $remote_root"
    remote "cd '$remote_root' && bash ops/check_mnemosyne_lanes.sh --mode runtime"
  done
}

atomic_restart() {
  local runtime_root
  runtime_root="$(primary_remote_root)"

  if [[ -f "$WORKSPACE_ROOT/$SERVICE.service" ]]; then
    log "Installing systemd unit /etc/systemd/system/$SERVICE.service"
    rsync -av "$WORKSPACE_ROOT/$SERVICE.service" "$HOST:/etc/systemd/system/$SERVICE.service"
  fi
  if [[ -f "$WORKSPACE_ROOT/${SERVICE}-logger.service" ]]; then
    log "Installing systemd unit /etc/systemd/system/${SERVICE}-logger.service"
    rsync -av "$WORKSPACE_ROOT/${SERVICE}-logger.service" "$HOST:/etc/systemd/system/${SERVICE}-logger.service"
  fi

  log "Reloading systemd units"
  remote "systemctl daemon-reload"

  log "Compiling remote api_server.py in $runtime_root"
  remote "python3 -m py_compile '$runtime_root/api_server.py'"

  log "Restarting $SERVICE.service"
  remote "systemctl restart '$SERVICE'"
  sleep 3

  if ! remote "systemctl is-active --quiet '$SERVICE'"; then
    remote "systemctl status '$SERVICE' --no-pager -n 80" || true
    echo "Remote service failed to become active." >&2
    exit 1
  fi
}

verify_public() {
  log "Verifying public health"
  curl -fsS "$BASE_URL/api/health" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
status = payload.get("status")
redis = payload.get("redis")
contract = payload.get("contract_version")
print(f"health: status={status} redis={redis} contract_version={contract}")
if status != "ok":
    raise SystemExit("Public health check did not return status=ok")
'

  log "Inspecting public HUD bundle"
  local bundle expected_bundle
  bundle="$(curl -fsS "$BASE_URL/" | python3 -c '
import re, sys
html = sys.stdin.read()
match = re.search(r"assets/index-[^\"]+\.js", html)
print(match.group(0) if match else "")
')"
  if [[ -z "$bundle" ]]; then
    echo "Could not find compiled HUD bundle reference on $BASE_URL" >&2
    exit 1
  fi
  expected_bundle="$(python3 -c '
import re, sys
from pathlib import Path
path = Path(sys.argv[1])
if not path.exists():
    print("")
    raise SystemExit(0)
html = path.read_text(encoding="utf-8")
match = re.search(r"assets/index-[^\"]+\.js", html)
print(match.group(0) if match else "")
' "$WORKSPACE_ROOT/docs/hud/index.html")"
  printf 'bundle: public=%s local=%s\n' "$bundle" "${expected_bundle:-unknown}"
  if [[ "$MODE" != "verify-only" && -n "$expected_bundle" && "$bundle" != "$expected_bundle" ]]; then
    echo "Public HUD bundle does not match the local built artifact." >&2
    exit 1
  fi

  local tickers=()
  mapfile -t tickers < <(resolve_verify_tickers)

  for ticker in "${tickers[@]}"; do
    log "Verifying parity canary $ticker"
    if ! curl -fsS "$BASE_URL/api/ticker/$ticker" | python3 -c '
import json, sys
expected = sys.argv[1]
payload = json.load(sys.stdin)
actual = str(payload.get("ticker", "")).upper()
name = payload.get("name", "")
scanner_only = payload.get("scanner_only")
sources = payload.get("scanner_sources") or []
if actual != expected:
    raise SystemExit(f"Expected ticker {expected}, got {actual!r}")
source_text = ",".join(sources) or "-"
print(f"{actual}: name={name} scanner_only={scanner_only} sources={source_text}")
' "$ticker"; then
      if [[ " ${VERIFY_TICKERS[*]} " == *" ${ticker} "* ]]; then
        log "WARN manual verify ticker $ticker failed live resolution; continuing with dynamic ranked canary gate"
        continue
      fi
      exit 1
    fi
  done

  local ranked_ticker
  ranked_ticker="$(resolve_ranked_verify_ticker)"
  log "Verifying ranked overlay canary $ranked_ticker"
  curl -fsS "$BASE_URL/api/ticker/$ranked_ticker" | python3 -c '
import json, sys
expected = sys.argv[1]
payload = json.load(sys.stdin)
actual = str(payload.get("ticker", "")).upper()
sources = [str(item).lower() for item in (payload.get("scanner_sources") or [])]
if actual != expected:
    raise SystemExit(f"Expected ranked canary {expected}, got {actual!r}")
if "ranked" not in sources:
    raise SystemExit(f"{actual} no longer resolves with ranked scanner overlay sources")
joined = ",".join(sources)
scanner_only = payload.get("scanner_only")
print(f"{actual}: ranked_sources={joined} scanner_only={scanner_only}")
' "$ranked_ticker"

  verify_intelligence_surfaces
}

resolve_verify_tickers() {
  local -a resolved=()
  local -A seen=()
  local ticker remote_root

  for ticker in "${VERIFY_TICKERS[@]}"; do
    local upper="${ticker^^}"
    [[ -n "$upper" ]] || continue
    if [[ -z "${seen[$upper]:-}" ]]; then
      seen[$upper]=1
      resolved+=("$upper")
    fi
  done

  if [[ ${#resolved[@]} -eq 0 ]]; then
    for remote_root in "${REMOTE_ROOTS[@]:-}"; do
      while IFS= read -r ticker; do
        ticker="${ticker^^}"
        [[ -n "$ticker" ]] || continue
        if [[ -z "${seen[$ticker]:-}" ]]; then
          seen[$ticker]=1
          resolved+=("$ticker")
        fi
        [[ ${#resolved[@]} -ge 3 ]] && break 2
      done < <(_ranked_candidates_from_remote "$remote_root" 3)
    done
  fi

  if [[ ${#resolved[@]} -eq 0 ]]; then
    while IFS= read -r ticker; do
      ticker="${ticker^^}"
      [[ -n "$ticker" ]] || continue
      if [[ -z "${seen[$ticker]:-}" ]]; then
        seen[$ticker]=1
        resolved+=("$ticker")
      fi
      [[ ${#resolved[@]} -ge 3 ]] && break
    done < <(_ranked_candidates_from_local 3)
  fi

  if [[ ${#resolved[@]} -eq 0 ]]; then
    while IFS= read -r ticker; do
      ticker="${ticker^^}"
      [[ -n "$ticker" ]] || continue
      if [[ -z "${seen[$ticker]:-}" ]]; then
        seen[$ticker]=1
        resolved+=("$ticker")
      fi
      [[ ${#resolved[@]} -ge 3 ]] && break
    done < <(_ranked_candidates_from_public_universe)
  fi

  if [[ ${#resolved[@]} -eq 0 ]]; then
    while IFS= read -r ticker; do
      ticker="${ticker^^}"
      [[ -n "$ticker" ]] || continue
      if [[ -z "${seen[$ticker]:-}" ]]; then
        seen[$ticker]=1
        resolved+=("$ticker")
      fi
      [[ ${#resolved[@]} -ge 3 ]] && break
    done < <(curl -fsS "$BASE_URL/api/universe?page=1&per_page=3&min_gravity=1" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
for row in payload.get("tickers") or payload.get("rows") or []:
    ticker = str(row.get("ticker") or "").strip().upper()
    if ticker:
        print(ticker)
')
  fi

  if [[ ${#resolved[@]} -eq 0 ]]; then
    echo "Could not derive a current public verification canary." >&2
    exit 1
  fi

  printf '%s\n' "${resolved[@]}"
}

resolve_ranked_verify_ticker() {
  local -a candidates=()
  local -A seen=()
  local ticker remote_root

  for ticker in "${VERIFY_TICKERS[@]}"; do
    ticker="${ticker^^}"
    [[ -n "$ticker" ]] || continue
    if [[ -z "${seen[$ticker]:-}" ]]; then
      seen[$ticker]=1
      candidates+=("$ticker")
    fi
  done

  for remote_root in "${REMOTE_ROOTS[@]:-}"; do
    while IFS= read -r ticker; do
      [[ -n "$ticker" ]] || continue
      if [[ -z "${seen[$ticker]:-}" ]]; then
        seen[$ticker]=1
        candidates+=("$ticker")
      fi
    done < <(_ranked_candidates_from_remote "$remote_root")
  done

  while IFS= read -r ticker; do
    [[ -n "$ticker" ]] || continue
    if [[ -z "${seen[$ticker]:-}" ]]; then
      seen[$ticker]=1
      candidates+=("$ticker")
    fi
  done < <(_ranked_candidates_from_local)

  for ticker in "${candidates[@]}"; do
    if ticker_has_ranked_source "$ticker"; then
      printf '%s\n' "$ticker"
      return 0
    fi
  done

  ticker="$(_ranked_candidates_from_public_universe | head -n 1 | tr -d '\r')"
  if [[ -n "$ticker" ]]; then
    printf '%s\n' "$ticker"
    return 0
  fi

  echo "Could not derive a ranked verification canary from live public data." >&2
  exit 1
}

verify_intelligence_surfaces() {
  log "Inspecting intelligence surfaces"
  curl -fsS "$BASE_URL/api/health" | python3 -c '
import json, sys
require_live = sys.argv[1] == "1"
payload = json.load(sys.stdin)
openbb = payload.get("openbb") or {}
everos = payload.get("everos") or {}
anthropic = payload.get("anthropic") or {}
openai = payload.get("openai") or {}
model_runtime = payload.get("model_runtime") or {}
openbb_enabled = bool(openbb.get("enabled"))
everos_enabled = bool(everos.get("enabled"))
everos_backend = bool(everos.get("backend_available"))
anthropic_configured = bool(anthropic.get("configured"))
openai_configured = bool(openai.get("configured"))
anthropic_fast = anthropic.get("fast_model") or "-"
anthropic_smart = anthropic.get("smart_model") or "-"
fast_provider = model_runtime.get("fast_provider") or "-"
smart_provider = model_runtime.get("smart_provider") or "-"
live_configured = bool(model_runtime.get("live_configured"))
print(
    "health_truth: "
    f"openbb_enabled={openbb_enabled} "
    f"everos_enabled={everos_enabled} "
    f"everos_backend={everos_backend} "
    f"anthropic_configured={anthropic_configured} "
    f"openai_configured={openai_configured} "
    f"fast_provider={fast_provider} "
    f"smart_provider={smart_provider} "
    f"anthropic_fast={anthropic_fast} "
    f"anthropic_smart={anthropic_smart}"
)
if require_live and not live_configured:
    raise SystemExit("No live model provider is configured for intelligence verification")
' "$VERIFY_INTELLIGENCE"

  curl -fsS "$BASE_URL/api/openbb/pilot" | python3 -c '
import json, sys
require_live = sys.argv[1] == "1"
payload = json.load(sys.stdin)
pilot = payload.get("pilot") or {}
status = str(pilot.get("status") or "")
reason = str(pilot.get("reason") or "") or "-"
enabled = bool((pilot.get("settings") or {}).get("enabled"))
status_text = status or "-"
print(f"openbb: status={status_text} enabled={enabled} reason={reason}")
if require_live and (not enabled or status in {"disabled", "unavailable", "error"}):
    raise SystemExit("OpenBB pilot is not live")
' "$VERIFY_INTELLIGENCE"

  curl -fsS "$BASE_URL/api/briefing" | python3 -c '
import json, sys
require_live = sys.argv[1] == "1"
payload = json.load(sys.stdin)
meta = payload.get("model_metadata") or {}
source = str(payload.get("source") or "")
is_fallback = bool(meta.get("is_fallback"))
reason = str(meta.get("fallback_reason") or "") or "-"
model = str(meta.get("model") or "") or "-"
source_text = source or "-"
print(f"briefing: source={source_text} fallback={is_fallback} model={model} reason={reason}")
if require_live and (source != "model_synthesis" or is_fallback):
    raise SystemExit("Briefing intelligence is still fallback-driven")
' "$VERIFY_INTELLIGENCE"

  curl -fsS "$BASE_URL/api/ai-summary/CAR" | python3 -c '
import json, sys
require_live = sys.argv[1] == "1"
payload = json.load(sys.stdin)
meta = payload.get("model_metadata") or {}
source = str(payload.get("source") or "")
is_fallback = bool(meta.get("is_fallback"))
reason = str(meta.get("fallback_reason") or "") or "-"
model = str(meta.get("model") or "") or "-"
source_text = source or "-"
print(f"ai_summary: source={source_text} fallback={is_fallback} model={model} reason={reason}")
if require_live and (source != "model_synthesis" or is_fallback):
    raise SystemExit("AI summary intelligence is still fallback-driven")
' "$VERIFY_INTELLIGENCE"
}

main() {
  if [[ "$MODE" == "verify-only" ]]; then
    check_verify_prereqs
  else
    check_prereqs
    detect_remote_roots
    printf 'Remote deploy roots: %s\n' "${REMOTE_ROOTS[*]}"
  fi

  case "$MODE" in
    all)
      check_local_mnemosyne_surface
      stage_sync
      check_env
      check_remote_mnemosyne_surface
      atomic_restart
      verify_public
      ;;
    stage-only)
      check_local_mnemosyne_surface
      stage_sync
      check_env
      check_remote_mnemosyne_surface
      ;;
    restart-only)
      check_env
      check_remote_mnemosyne_surface
      atomic_restart
      verify_public
      ;;
    verify-only)
      verify_public
      ;;
    *)
      echo "Unsupported mode: $MODE" >&2
      exit 1
      ;;
  esac
}

main
