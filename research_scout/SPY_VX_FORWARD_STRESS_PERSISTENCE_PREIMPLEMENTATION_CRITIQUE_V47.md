# SPY VX Forward-Stress Persistence — Preimplementation Critique v47

## Frozen hypothesis

A daily change in the official front-to-second standard-monthly VX settlement curve identifies a persistent forward-volatility risk state that carries into the next U.S. cash session:

- normalized VX slope increases: near-term stress falls relative to later volatility; buy UPRO next session;
- normalized VX slope decreases: near-term stress rises relative to later volatility; buy SPXU next session;
- exact zero: cash.

The normalized slope is `(VX2 settlement - VX1 settlement) / VX1 settlement`. Front and second contracts are the nearest two standard monthly VX expirations strictly after the signal date. Enter at the next SPY session's exact 09:31 observed ask and exit at its exact 15:30 observed bid. No overnight position and no magnitude, level, volume, open-interest, weekday, expiration-distance, SPY-price, gap, or volatility filter.

## Relationship to V46

V46 required SPY and the VX curve to disagree. Its returns-blind audit failed cadence at 1.401 trades/week; no target return or P&L was inspected. V47 does not delete a failed-return condition or invert an exposed result. It tests the separately declared VX-only control as a new causal hypothesis, with a new number, critique, preregistration, and stopping gates before any target return is opened.

V47's economic claim is persistence in forward-volatility risk appetite. V46's claim was reversal of an unsupported cash-equity move. They are not the same sign logic.

## Why it might work

1. **Forward hedging is persistent.** Institutional protection demand, volatility targeting, and risk-budget changes may execute over multiple sessions rather than one close.
2. **Term structure is richer than spot volatility.** Relative near-versus-next-month pricing distinguishes changes concentrated in immediate stress from parallel volatility moves.
3. **Actual contracts avoid continuous-series artifacts.** The rule uses official settlements and explicit expiration ordering, not a back-adjusted curve.
4. **Slow implementation.** The trade occurs only the following cash session, so the hypothesis does not rely on reacting to settlement publication faster than other participants.
5. **Natural cadence.** Strictly nonzero daily curve changes should produce substantially more than two trades per week without a fitted trigger threshold.

## Why it probably fails

1. **The information is stale.** VX, ES, SPY premarket, and options trade overnight. Persistence may be complete before 09:31.
2. **Common-information problem.** VX curve changes can simply summarize the prior day's equity move. They do not establish that VX leads next-day cash returns.
3. **Volatility persistence does not imply price direction.** Higher expected variance can coexist with positive equity risk premia; the frozen negative mapping may be wrong.
4. **Settlement is non-executable.** Official settlement is an auditable state, not a live tradable spread at one exact instant.
5. **Roll sensitivity.** Front/second identity changes mechanically around expiry. Early-roll action stability is required before returns.
6. **Inverse ETF drag and spread.** Frequent SPXU exposure can turn a small underlying relation negative.
7. **Likely beta timing rather than alpha.** If the rule mostly follows prior SPY direction, it may not add information or beat buy-and-hold.
8. **Multiplicity burden.** V47 follows many failed SPY intraday families. A marginal gross result is not enough; every frozen robustness and SPY-relative gate must pass.

## Source boundary

Official Cboe data package:

- `data/raw/cboe_vx_monthly_v46/manifest.json`
- 62 standard monthly contracts, January 2021 through February 2026
- weekly VX01–VX53 excluded
- 11,565 rows, 979,828 bytes
- source: `https://www.cboe.com/markets/us/futures/market-statistics/historical-data/futures`

The literature on variance risk premia and volatility term structure motivates forward-volatility state as an equity-risk observable, but it does not validate this exact daily sign mapping or 09:31–15:30 leveraged-ETF implementation. V47 is a mechanism scout, not a paper replication.

## Economic upper-bound screen

The held UPRO/SPXU session can move far more than one quoted spread, and the construction has two—not four—marketable executions. It is not mechanically below break-even before measurement. This says nothing about expected sign.

## Frozen partitions

- Development: 2021-01-01 through 2023-12-31.
- Holdout: 2024-01-01 through 2025-12-31, locked unless all development gates pass.

## Returns-blind gates

1. curve-state coverage at least 98%;
2. at least two executable trades per calendar week;
3. at least 200 executable trades in every development year;
4. minority UPRO/SPXU direction at least 20%;
5. primary execution coverage at least 95%;
6. independent EQUS execution coverage at least 95%;
7. early-roll action agreement including cash at least 80%;
8. signal date strictly before trade date.

## Development gates

All must pass:

- at least two trades per week;
- positive fixed-$100 P&L and profit factor at least 1.05;
- every development year positive;
- UPRO and SPXU sleeves both positive;
- ending cash above split/dividend-adjusted SPY;
- positive with one extra cent at both fills;
- positive with entry delayed five minutes;
- positive after deleting the ten best trades;
- positive on independent EQUS execution overlap;
- mean trade P&L above prior-SPY-direction continuation, prior-SPY-direction reversal, one-session-lagged VX-change, and sign-flipped controls.

Failure is terminal. Do not repair with curve levels, backwardation filters, magnitude thresholds, SPY confirmation, volume/open-interest gates, alternative contracts, or another hold window.
