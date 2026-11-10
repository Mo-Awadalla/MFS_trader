# CFTC Relative-Transfer / ES Opening Acceptance Critique v65

## Frozen hypothesis

For each CFTC S&P 500 Consolidated futures-only report, define:

`asset_manager_net_change = change_long - change_short`

`leveraged_fund_net_change = change_long - change_short`

`relative_transfer = asset_manager_net_change - leveraged_fund_net_change`

The state direction is the strict sign of `relative_transfer`. It becomes
usable seven calendar days after the Tuesday report date and is then carried
forward only until the next safe report state.

On each development cash session:

1. Observe ES continuous-contract one-minute bars from 09:30 through 09:34 ET.
2. At 09:35, compare the completed 09:34 close with the 09:30 open.
3. Trade only if that five-minute ES direction strictly agrees with the
   relative-transfer direction.
4. A positive state selects UPRO; a negative state selects SPXU.
5. Prospective execution is the exact 09:36 ask, with the exact 15:30 bid as
   the exit, using $100 fixed notional and fractional shares.
6. There is no magnitude threshold, stop, volatility filter, weekday filter,
   side filter, or parameter fit.

## Why the mechanism could be real

The slow feature asks which participant category became more directionally
exposed relative to the other. The fast feature asks whether the next cash
participant handoff actually accepts that direction in the underlying futures
market. Agreement is intended to identify a risk-transfer state that has
survived both reporting delay and a fresh price-discovery event.

The leveraged ETF is an actuator, not the source of the prediction. UPRO and
SPXU provide symmetric long-only execution while every position remains
intraday.

This is a hypothesis a serious systematic desk could investigate because the
inputs refer to identifiable participant categories, the confirming market is
the S&P futures complex itself, publication lag is explicit, and execution is
tested at observed BBOs rather than bar closes.

## Internal attack

### 1. “Transfer” may be an overstatement

The two CFTC categories are not identified counterparties. Both can trade
against dealers, nonreportables, or one another, and spreading positions are
reported separately. The feature is therefore a **relative directional
change**, not proof of bilateral risk transfer.

Consequence: the report and code must retain that wording. A compelling story
cannot rescue weak controls.

### 2. The state is stale

Tuesday positions are normally published Friday and are deliberately held back
until the next Tuesday in this test. By entry, the underlying positions may
have changed materially.

Consequence: no same-week timing optimization is allowed. A one-report-shifted
placebo is mandatory, and the effect must exist across all three years.

### 3. Opening confirmation can dominate the construction

Five-minute ES direction is a familiar momentum variable. If the CFTC state
merely selects a random half of otherwise similar opening-momentum trades, the
hypothesis has failed even if gross P&L is positive.

Consequence: the returns-blind action must be distinct from ES-only opening
momentum and COT-only direction. In the P&L test, shifted-state and state-only
controls must not explain the result.

### 4. Repeated daily trades are pseudoreplication

One CFTC observation can govern roughly five sessions. Trade-level bootstrap
confidence would exaggerate the sample size.

Consequence: winner deletion, bootstrap, and permutation inference are grouped
by source COT report. A strategy dependent on a handful of profitable report
weeks fails.

### 5. Category units and rolls can distort change

The consolidated contract can experience large open-interest changes around
rolls. Raw contract changes are intentionally used because no fitted
normalization is permitted, but their sign can still be affected by position
maintenance rather than conviction.

Consequence: report-level direction-switch counts, year balance, and collision
diagnostics are inspected before returns. No roll-week deletion may be added
after outcomes.

### 6. SPXU can be a materially worse actuator

Inverse leveraged ETFs have higher path and execution friction. Prior research
repeatedly found apparent aggregate profit supported by UPRO while SPXU lost.

Consequence: both sleeves must be profitable after spread-crossing, and the
extra-cent stress must remain positive. Dropping SPXU is prohibited.

## Returns-blind construction gates

- Exactly one valid consolidated S&P futures-only record per report date.
- At least 50 report states in every development year.
- At least 90% of expected SPY cash sessions have a safe COT state and the
  completed primary ES observation.
- At least 2.0 signals per week and at least 90 signals in each year.
- Minority actuator share at least 30%.
- Relative-transfer direction changes at least 15 times in every year.
- Exact 09:36 UPRO/SPXU quote coverage at least 90% on the primary feed.
- Four-minute and six-minute neighboring opening observations each preserve
  at least 75% of actions including cash.
- On the independent 2023 overlap, the SPY opening proxy preserves at least
  85% of actions including cash.
- Candidate action agreement with ES-only momentum and COT-only direction is
  below 80% for each control.

Failure of any construction gate ends v65 without reading an entry fill, exit
fill, strategy return, or any 2024–2025 outcome.

## Frozen development P&L gates

If and only if every construction gate passes:

- 2021–2023 only; recent years remain unread.
- More than 2.0 completed trades per week.
- Profit factor greater than 1.10.
- Positive fixed-notional P&L in 2021, 2022, and 2023.
- Positive UPRO and SPXU P&L separately.
- Ending cash from $100 exceeds split/dividend-adjusted SPY buy-and-hold over
  the same dates.
- Positive P&L after one extra cent adverse at both entry and exit.
- Positive P&L with a five-minute entry delay.
- Positive P&L after deleting the five best source-report clusters.
- Positive 2.5th percentile of a moving-block bootstrap over source-report
  clusters.
- One-sided source-report direction-permutation p-value below 0.05.
- Positive independent-feed overlap result with both sleeves represented.
- The actual state beats the one-report-shifted placebo and the state-only
  control on frozen diagnostics.

Any miss rejects the candidate. No clock change, magnitude threshold,
collision-only subset, side removal, normalization, report-lag change, or
year-specific repair is allowed.

