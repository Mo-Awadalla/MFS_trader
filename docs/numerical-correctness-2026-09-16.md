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

The calculation implements Equations (1) and (2) of [Bailey and López de Prado, *The Deflated Sharpe Ratio* (2014)](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf), using a zero-mean null benchmark. Inputs include the selected trial's per-observation Sharpe, observation count, skewness, ordinary kurtosis (Normal = 3), cross-trial Sharpe variance, and trial count. Annualized Sharpe is divided by the square root of observations/year; its cross-trial variance is divided by observations/year. The reference test uses 250 observations/year; daily pipeline comparisons explicitly use 252.

`dsr_confidence` is the paper's confidence statistic. `dsr_pvalue` is its complementary upper tail, calculated with the Normal survival function for numerical stability. These are not interchangeable values. This patch retains the existing strict tail-probability gates (`p < 0.05`, with raw-trial sensitivity `p_raw < 0.10`).

Trial-count methods must be distinguished:

- `M_raw` uses the declared raw number of trials; the paper's benchmark assumes independent trials.
- `M_eff_corr` uses the repository's correlation-eigenvalue effective-count heuristic as an input to the same formula. The estimator itself is not claimed to be derived from the paper.
- `M_cluster` uses an explicitly supplied parameter-cluster count, also a repository heuristic rather than the paper's trial-count estimator.

The pre-existing default method remains `M_eff_corr`. Its estimate and the raw-trial sensitivity remain visible. The implemented extreme-value approximation requires a count of at least two; a lower effective count is unavailable, not an automatic pass or an implicit switch to another statistic.

The gauntlet requires a finite, complete `(observations, searched trials)` return matrix, an explicit selected column, and a meaningful `dsr_search_scope`. It calculates selected statistics and cross-trial Sharpe variance on that same observation window. It must not substitute the best column for the actual selected candidate or combine full-sample Sharpe with WFA OOS length. WFA/Monte Carlo remain separate checks.

The BB caller now supplies the full sweep, maps the exact selected parameter configuration into stable matrix-column order, and declares annualization explicitly. Missing/ambiguous configuration matches are unavailable. Empty or zero-volatility trials are not silently dropped to reduce the apparent search; insufficient statistics fail unavailable. The scope string describes this supplied sweep, not unrecorded exploratory research outside it.

Other callers that do not yet supply complete scope and selection evidence receive a non-passing unavailable DSR result. This deliberate fail-closed behavior does not establish that their underlying strategies fail statistical validation; it establishes that the required evidence was not provided. No missing data or favorable result is invented to preserve an old PASS.

## Report/API compatibility

- `MCResult.pct_95_max_dd` and its serialized key are replaced by `pct_5_max_dd`. Do not relabel an old stored percentile: it must be recomputed from path drawdowns or by rerunning the simulation.
- The corrected DSR formula is identified by `bailey_lopez_de_prado_eq2_v1`. Reports disclose availability/reason, method, search scope, per-observation units, confidence/tail probability, benchmark, track length, moments, and trial variance.
- Previous DSR values came from a different expression and cannot be converted into corrected confidence by renaming a field. Missing evidence produces `available=False` and `passed=False`.
- BB's returns-matrix builder no longer accepts a top-trials truncation limit; all declared sweep trials must be represented.

## Historical evidence and corrected evaluations

Historical results produced with the affected MC/DSR code require re-evaluation. They are original evidence of what was computed, not corrected validation claims. This patch does not recalculate their Sharpe, drawdown, or promotion verdict, and it must not be cited as doing so.

For any subsequent corrected evaluation:

1. Verify the original Experiment UUID **and** hash; preserve its frozen snapshot, report bytes, report hash, and original verdict/status. A strategy modification requires a new frozen Experiment.
2. Establish the exact input identity, lawful/private availability, observation frequency, cost configuration, random seed, selected parameters, and complete searched-trial scope. Do not restore excluded inputs into public history.
3. Record the corrected source commit, formula/schema versions, input hashes, full evaluation configuration, and the original report's identity/hash in a **new, uniquely versioned artifact location**. Write atomically and refuse overwrites. A separate versioned re-evaluation writer/workflow must be reviewed before use; the existing canonical report path is immutable, not a destination to overwrite.
4. Label the new artifact as a corrected evaluation linked to the original; keep original and corrected verdicts distinguishable. Missing prerequisites mean `requiring_re_evaluation`/unavailable, not a fabricated correction.
5. Do not infer a lifecycle transition from a corrected report. Any promotion still requires explicit UUID/hash verification and all applicable gates. No live authorization follows from this change.

No historical rerun, evidence overwrite, metadata migration, or lifecycle transition is part of this implementation. The ordinary tests use synthetic data and temporary test storage. Public release-readiness repairs and historical re-evaluations remain separate from both this patch and the completed history rewrite.
