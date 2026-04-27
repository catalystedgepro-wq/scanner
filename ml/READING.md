# ML Research + Concept Rollout Schedule

Every concept implemented must land as code in ml/ with a benchmark delta vs prior version. Slippage on the time bracket = protocol violation.

## Binding Time Bracket

| Milestone | Date | Gate (sec_clean_gappers, walk-forward holdout) |
|---|---|---|
| **Day 0** | 2026-04-14 | Scaffold + baseline frozen ✅ |
| **Day 7** | 2026-04-21 | v1 LightGBM shadow — must beat baseline hit_2pct on any 7-day walk-forward slice |
| **Day 14** | 2026-04-28 | Hit +2% ≥ **55%**, Hit +5% ≥ **32%**, avg_run ≥ **7.0%** |
| **Day 30** | 2026-05-14 | Hit +2% ≥ **65%**, Hit +5% ≥ **45%**, avg_run ≥ **10%**, top-10 precision@5 ≥ **60%** |
| **Day 60** | 2026-06-13 | Hit +2% ≥ **72%**, Hit +5% ≥ **52%**, avg_run ≥ **12%** |
| **Day 90** | 2026-07-13 | Hit +2% ≥ **78%**, Hit +5% ≥ **60%**, avg_run ≥ **15%** |

Failure to hit a milestone = automaton protocol violation. No extensions without prior-week evidence of effort (commits, benchmark logs).

## Concept → Implementation Schedule

Each week = 1 concept applied + benchmark. Drawn from Lopez de Prado, Ernest Chan, Kaufman, Hull, Mantegna/Stanley (econophysics), Orrell (quantum economics), Haven/Khrennikov (quantum probability in finance).

| Week | Concept | Field | Implementation | File |
|---|---|---|---|---|
| W1 (04-14→04-21) | **Gradient Boosting baseline** | Classical ML | LightGBM 2 heads, naive features | `train_catalyst_model.py` |
| W2 (04-21→04-28) | **Triple-Barrier Labeling** | Lopez de Prado | Replace hit_N% with (profit_barrier, stop_barrier, time_barrier) path labels | `labels_tb.py` |
| W3 (04-28→05-05) | **Fractional Differentiation** | Lopez de Prado | Stationary price features preserving memory, d=0.4 on log-prices | `frac_diff.py` |
| W4 (05-05→05-12) | **Meta-Labeling** | Lopez de Prado | Secondary model on primary signals → filter false positives | `meta_labeler.py` |
| W5 (05-12→05-19) | **Purged + Embargoed CV** | Lopez de Prado | Formalize overlap purge + 1-day embargo | `cv_purged.py` |
| W6 (05-19→05-26) | **Entanglement Features** | Quantum Economics | Sympathy correlation matrix → per-pick features: max_sector_corr, cluster_momentum, lead-lag z-score | `features_entanglement.py` |
| W7 (05-26→06-02) | **Regime Detection (HMM)** | Econophysics | Hidden Markov on SPY/VIX/breadth → regime label on each row | `regime_hmm.py` |
| W8 (06-02→06-09) | **Bayesian Model Averaging** | Quantum Probability / Bayes | Posterior over {LightGBM, CatBoost, LogReg, MLP}, sample instead of picking one | `bma_ensemble.py` |
| W9 (06-09→06-16) | **Mutual Information Feature Selection** | Information Theory | MI between features and triple-barrier labels; drop bottom 30% | `mi_selector.py` |
| W10 (06-16→06-23) | **Fractal Market Hypothesis** | Econophysics (Peters) | Hurst exponent + detrended fluctuation analysis on 20d windows | `hurst_features.py` |
| W11 (06-23→06-30) | **Options Flow (once Alpaca/Tradier wired)** | Classical finance | IV rank, put/call ratio, unusual-vol z-score | `options_features.py` |
| W12 (06-30→07-07) | **Nano-Economics Intent Model** | Nano-economics | Not on picks — on **subscriber conversion**. Per-visitor intent score from GA events → personalize CTA | `intent_scorer.py` (in conversion/ subdir) |
| W13 (07-07→07-14) | **Quantum-Inspired Portfolio Optimization** | QNE / QAOA-classical proxy | Replace equal-weight pick publication with max-Sharpe Markowitz + Black-Litterman prior from ML probabilities | `portfolio_opt.py` |

## Ongoing Research Loop

- **Friday 5 PM ET:** scan arXiv q-fin.ST (statistical finance) new submissions. Shortlist 3 papers. Add 1 to backlog per week.
- **Monday:** implement prior week's concept in the pipeline.
- **Wednesday:** benchmark delta posted to `ml_benchmark_log.csv` with concept tag.
- **Saturday:** public write-up for newsletter subscribers — builds brand/moat + feeds the marketing flywheel.

## Sources (canonical, no cherry-pick)

- Marcos López de Prado — *Advances in Financial Machine Learning* (2018), *Machine Learning for Asset Managers* (2020)
- Ernest P. Chan — *Algorithmic Trading: Winning Strategies* (2013)
- Rosario N. Mantegna & H. Eugene Stanley — *Introduction to Econophysics* (2000)
- David Orrell — *Quantum Economics and Finance* (2020)
- Emmanuel Haven & Andrei Khrennikov — *Quantum Social Science* (2013)
- Didier Sornette — *Why Stock Markets Crash* (2003) — LPPL bubble model
- John Hull — *Options, Futures, and Other Derivatives* (11e, 2022)
- Perry Kaufman — *Trading Systems and Methods* (6e, 2019)

## Protocol Clause

Two consecutive missed milestones = automaton execution eligible.
