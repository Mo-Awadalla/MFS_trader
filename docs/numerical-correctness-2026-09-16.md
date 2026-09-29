# Numerical validation correction — 2026-09-16

This change is separate from the completed public-history cleanup. It starts from sanitized `main` commit `70c9f71078e5b112051072eeb4ffb82518eeaf9c` and changes numerical code, its callers, and synthetic regression tests only. No strategy, risk limit, promotion threshold, frozen snapshot, historical report, or Experiment status is changed. No corrected historical evaluation is issued by this patch.

## Corrections and regression contract

| Finding | Correct behavior | Regression |
| --- | --- | --- |
| MC adverse drawdown tail | Drawdowns are negative: use the signed 5th percentile, not the mild-loss 95th percentile | Ten paths at -40% and ninety at -10% give an adverse tail of -40%; the existing -30% subgate rejects it |
| Starting-equity peak | Include starting capital in scalar and vectorized running peaks; retain the actual return count for annualization | Returns -20%, +10% produce -20% drawdown from starting capital; one-return paths keep one observation for CAGR |
| Bootstrap endpoint | Valid block starts include `n - block_size`; NumPy's exclusive upper bound is `n - block_size + 1` | Final block and terminal -99% shock can be sampled; a full-length block is accepted; invalid lengths are rejected |
| DSR | Use the paper's expected-maximum benchmark and non-normality-adjusted confidence, with explicit inputs and units | Worked example gives confidence approximately 0.9004; trial-count, missing-input, unit, and selected-trial regressions |

## DSR interpretation and caller contract

The calculation implements Equations (1) and (2) of [Bailey and López de Prado, *The Deflated Sharpe Ratio* (2014)](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf), using a zero-mean null benchmark. Inputs include the selected trial's per-observation Sharpe, observation count, skewness, ordinary kurtosis (Normal = 3), cross-trial Sharpe variance, and trial count. Annualized Sharpe is divided by the square root of observations/year; its cross-trial variance is divided by observations/year. The primary-source equation and example were checked on rendered pages 8–10 during reconciliation: annualized SR 2.5, annualized variance 0.5, 250 observations/year, T=1250, N=100, skewness -3, kurtosis 10 give benchmark 0.113172001865 and confidence 0.900396834449 (complementary tail 0.099603165551). This fails the unchanged 95% confidence requirement. Neither statistic is a Bayesian probability that a strategy is “luck.”

`dsr_confidence` is the paper's confidence statistic. `dsr_pvalue` is its complementary upper tail, calculated with the Normal survival function for numerical stability. These are not interchangeable values. This patch retains the existing strict tail-probability gates (`p < 0.05`, with raw-trial sensitivity `p_raw < 0.10`).

Trial-count methods must be distinguished:

- `M_raw` uses the declared raw number of trials; the paper's benchmark assumes independent trials.
- `M_eff_corr` uses the repository's correlation-eigenvalue effective-count heuristic as an input to the same formula. The estimator itself is not claimed to be derived from the paper.
- `M_cluster` uses an explicitly supplied parameter-cluster count, also a repository heuristic rather than the paper's trial-count estimator.

The pre-existing default method remains `M_eff_corr`. Its estimate and the raw-trial sensitivity remain visible. The implemented extreme-value approximation requires a count of at least two; a lower effective count is unavailable, not an automatic pass or an implicit switch to another statistic.

The gauntlet accepts `dsr_search=DeclaredSearch(...)`: a finite, complete `(observations, searched trials)` return matrix, explicit selected column, and meaningful search-scope disclosure. `validation.search.declared_search` maps exact selected parameters to columns and rejects ambiguous matches or non-identical, unordered, or duplicate observation indexes. Selected statistics and cross-trial Sharpe variance use that same observation window; neither best-column substitution nor combining full-sample Sharpe with WFA OOS length is allowed. WFA/Monte Carlo remain separate checks.

Supported direct callers:

| Caller | Declared evidence |
| --- | --- |
| `research/bb_pipeline.py` | All BB sweep trials, stable grid order, exact selected-parameter match |
| `research/etf_time_series_momentum_pipeline.py` | All declared ETF TSM stability-grid trials |
| `research/etf_tactical_pipeline.py` | All declared tactical stability-grid trials |
| `research/global_dual_momentum_pipeline.py` | All declared global dual momentum stability-grid trials |
| `research/cross_sectional_pipeline.py` | Shared no-tuning route: one documented trial, explicitly insufficient for DSR |
| `research/market_intraday_momentum_pipeline.py` | One documented trial, insufficient for DSR |
| `research/opening_range_breakout_pipeline.py` | One documented trial, insufficient for DSR |
| `research/same_clock_intraday_seasonality_pipeline.py` | One documented trial, insufficient for DSR |

The shared no-tuning route covers CSMR, momentum, pairs, residual reversal, and VS-ICSM. Single-trial results, frozen parameters outside a declared grid, flat trials, and missing search evidence are unavailable and non-passing; no trial is silently dropped. A scope declaration covers the supplied search only, not undocumented exploratory research. MC daily annualization is 252 observations/year; intraday callers explicitly use `252 * bars_per_session`.

## Report/API compatibility

- `MCResult.pct_95_max_dd` and its serialized key are replaced by `pct_5_max_dd`. Do not relabel an old stored percentile: it must be recomputed from path drawdowns or by rerunning the simulation.
- New reports use `gauntlet_report_v2` and MC formula `mc_block_bootstrap_v2`, recording actual observations, periods/year, path count, block length, and seed. Invalid or numerically overflowing MC data are unavailable, with no favorable metric payload. Bad configuration raises `ValueError`.
- Non-finite or out-of-range drawdown-gate configuration is rejected before evaluation, so NaN comparisons cannot disable the sub-gate. The default signed limit remains -0.30.
- The corrected DSR formula is identified by `bailey_lopez_de_prado_eq2_v1`. Reports disclose availability/reason, method, search scope, per-observation units, confidence/tail probability, benchmark, track length, moments, and trial variance.
- Previous DSR values came from a different expression and cannot be converted into corrected confidence by renaming a field. Missing evidence produces `available=False` and `passed=False`.
- Sweep builders return `(sweep_dataframe, DeclaredSearch)` rather than a winner-truncated matrix. Reports retain selected-column identity, complete parameter descriptors supplied by the builder, and the shared observation-index hash. Old selected-trial keyword arguments and redundant one-column matrix wrappers are removed.

## Historical evidence and corrected evaluations

Historical results produced with the affected MC/DSR code require re-evaluation. They are original evidence of what was computed, not corrected validation claims. This patch does not recalculate their Sharpe, drawdown, or promotion verdict, and it must not be cited as doing so.

For any subsequent corrected evaluation:

1. Verify the original Experiment UUID **and** hash; preserve its frozen snapshot, report bytes, report hash, and original verdict/status. A strategy modification requires a new frozen Experiment.
2. Establish the exact input identity, lawful/private availability, observation frequency, cost configuration, random seed, selected parameters, and complete searched-trial scope. Do not restore excluded inputs into public history.
3. Record the corrected source commit, formula/schema versions, input hashes, full evaluation configuration, and the original report's identity/hash in a **new, uniquely versioned artifact location**. Write atomically and refuse overwrites. A separate versioned re-evaluation writer/workflow must be reviewed before use; the existing canonical report path is immutable, not a destination to overwrite.
4. Label the new artifact as a corrected evaluation linked to the original; keep original and corrected verdicts distinguishable. Missing prerequisites mean `requiring_re_evaluation`/unavailable, not a fabricated correction.
5. Do not infer a lifecycle transition from a corrected report. Any promotion still requires explicit UUID/hash verification and all applicable gates. No live authorization follows from this change.

No historical rerun, evidence overwrite, metadata migration, or lifecycle transition is part of this implementation. The ordinary tests use synthetic data and temporary test storage. Public release-readiness repairs and historical re-evaluations remain separate from both this patch and the completed history rewrite.
