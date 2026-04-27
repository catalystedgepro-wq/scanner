# Cerebro Score Field Inventory

Scope: documentation only. This maps the current score-related fields in the repo and their likely producers.

## Core Ranking Lanes

| Lane | Current fields | Likely producer(s) | Notes |
| --- | --- | --- | --- |
| Master convergence | `convergence_score`, `conviction_level`, `signal_count`, `signals_fired`, `sec_pts`, `insider_pts`, `deepvalue_pts`, `squeeze_pts`, `smart_pts`, `inflection_pts`, `darkpool_pts`, `nt_pts`, `merger_pts`, `keyword_pts` | [build_convergence_score.py](/home/operator/.openclaw/workspace/build_convergence_score.py) | This is the closest thing to a top-level combined rank today. |
| News + SEC blend | `total_score`, `sec_score`, `news_score`, `gapper_score`, `value_score`, `moat_score` | [build_news_momentum.py](/home/operator/.openclaw/workspace/build_news_momentum.py) | `total_score` here is a different concept from convergence. |
| SEC list scoring | `gapper_score`, `value_score`, `moat_score`, `insider_signal_score`, `risk_flags`, `market_flags`, `recency_min` | SEC list builders such as [build_news_momentum.py](/home/operator/.openclaw/workspace/build_news_momentum.py) and the `sec_*` CSV producers | These are list-specific scores that downstream tools often treat as if they were universal. |
| Income screen | `income_score`, `dividend_score`, `quality_score` | Income screening pipeline, reflected in `sec_income_picks.csv` | Separate ranking lane, but `quality_score` is a collision risk because the name sounds like a master rank. |
| Deep value | `deepvalue_score`, `grade` | [build_deepvalue_screen.py](/home/operator/.openclaw/workspace/build_deepvalue_screen.py) | Another standalone score family. |
| Gap scanner | `gap_score`, `overnight_gap_pct`, `intraday_ext_pct`, `effective_gap_pct`, `gap_atr_ratio`, `vol_ratio`, `vol_building`, `accum_label`, `consec_up_days` | [build_gap_scanner.py](/home/operator/.openclaw/workspace/build_gap_scanner.py) | Strong operational scorer, but it is not the same as master convergence. |
| Squeeze hunter | `squeeze_score`, `stage`, `stage_emoji`, `si_score`, `dtc_score`, `activist_score`, `insider_score`, `gamma_pts`, `wsb_score`, `trend_score`, `score_breakdown` | [build_squeeze_hunter.py](/home/operator/.openclaw/workspace/build_squeeze_hunter.py) | This is the richest explainability surface in the repo today. |
| News momentum | `news_score`, `sector_score`, `total_score` | [build_news_momentum.py](/home/operator/.openclaw/workspace/build_news_momentum.py) | `sector_score` is an aggregate, not an entity score. |

## Signal Inputs That Feed Scores

| Layer | Current fields | Likely producer(s) | Notes |
| --- | --- | --- | --- |
| Macro | `fed_funds_rate`, `treasury_10y`, `treasury_2y`, `yield_curve_spread`, `yield_curve_inverted`, `real_rate`, `cpi_yoy`, `pce_yoy`, `m2_yoy`, `unemployment`, `nonfarm_payrolls`, `payrolls_mom`, `employment_signal`, `environment`, `sector_multipliers`, `sector_signals`, `multipliers`, `signals` | [build_macro_layer.py](/home/operator/.openclaw/workspace/build_macro_layer.py), [macro_engine.py](/home/operator/.openclaw/workspace/macro_engine.py) | Macro currently exists as both a layer snapshot and a live pressure snapshot. |
| Macro pressure | `global_multiplier`, sector-specific pressure fields, recession warning flags | [macro_engine.py](/home/operator/.openclaw/workspace/macro_engine.py) | This is what the HUD/API read at runtime. |
| Short interest | `short_pct_float`, `days_to_cover`, `si_trend_pct`, `float_shares_m`, `avg_volume_m`, `si_pct_raw` | [build_short_data.py](/home/operator/.openclaw/workspace/build_short_data.py), [build_short_interest.py](/home/operator/.openclaw/workspace/build_short_interest.py) | Fuel for squeeze logic and a potential standalone signal lane. |
| Sympathy | `gap_score`, `trigger_ticker`, `sector`, `form`, `price_t0`, `price_t1`, `price_t2`, `return_1d_pct`, `return_2d_pct` | [build_sympathy_logger.py](/home/operator/.openclaw/workspace/build_sympathy_logger.py) | This is logging first, scoring later. |
| Options / flow | `current_price`, `call_oi`, `put_oi`, `pc_ratio`, `gamma_score`, `max_pain`, `atm_call_iv`, `unusual_call_vol` | [build_options_flow.py](/home/operator/.openclaw/workspace/build_options_flow.py), [spoke_options.py](/home/operator/.openclaw/workspace/spoke_options.py) | `gamma_score` is the main normalized field here. |
| Dark pool proxy | `signal_type`, `today_volume`, `avg_volume_30d`, `volume_ratio`, `price_change_pct`, `dark_pool_flag` | [build_dark_pool.py](/home/operator/.openclaw/workspace/build_dark_pool.py) | Proxy signal, not literal dark-pool data. |
| Institutional | `fund_count`, `latest_fund_name`, `latest_filed_date`, `total_mentions`, `signal`, `primary_link` | [build_smart_money.py](/home/operator/.openclaw/workspace/build_smart_money.py) | Used as confirmation fuel in squeeze/convergence flows. |
| Gravity / universe | `gravity`, `etf_weights_sum`, `etf_overlords`, `cap_tier`, `sector`, `is_rogue` | [build_universe_gravity.py](/home/operator/.openclaw/workspace/build_universe_gravity.py), gravity enrichment scripts | This is a structural rank input, not a catalyst score. |
| Brightness | `brightness`, `velocity`-derived live overlays | [api_server.py](/home/operator/.openclaw/workspace/api_server.py) | Brightness is a live display metric computed from gravity + spark velocity, not a standalone score family. |

## Biggest Semantic Collisions

- `total_score` is overloaded. In `build_news_momentum.py` it means news + SEC blend, while in other places users may read it as "the top score overall."
- `gapper_score`, `value_score`, and `moat_score` are reused as component scores inside list-specific SEC outputs and as inputs to blended scores.
- `quality_score` is dangerously generic. It lives in the income lane and can be mistaken for a universal rank or master score.
- `convergence_score`, `squeeze_score`, `gap_score`, and `deepvalue_score` all sound like final ranks, but each belongs to a different lane with different math and intent.
- `gravity` and `brightness` are structural/live display concepts, not catalyst scores, but they read like rank fields because they sort the HUD.
- `macro_layer`, `macro_pressure`, `multipliers`, and `signals` are all macro outputs with slightly different scopes, so downstream code needs to be explicit about which snapshot it is using.
- `dark_pool_flag` is a proxy label, not source-truth dark pool data.

## Practical Rule

If a field is meant to rank the whole universe, it should be named and documented as a universal rank.
If it is lane-specific, keep the lane in the name and avoid reusing the same field as a cross-lane final score.
