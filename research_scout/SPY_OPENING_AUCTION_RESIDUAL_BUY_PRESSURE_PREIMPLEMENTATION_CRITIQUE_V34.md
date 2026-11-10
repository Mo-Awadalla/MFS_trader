# SPY Opening-Auction Residual Buy Pressure — Preimplementation Critique v34

## Decision

**Accept one bounded frozen scout.** Do not promote it beyond research unless every development, holdout, execution, concentration, and SPY-relative gate passes unchanged.

## Hypothesis

At 09:29 ET, an official NYSE Arca SPY opening-auction message that still reports a buy-side total imbalance represents deadline-bound residual demand that has not been paired away. Some of that demand and the associated dealer/AP inventory adjustment may continue after the opening uncross. The frozen strategy therefore buys UPRO after the opening print and exits during the first hour. Sell-side states remain cash; prior tests show that inverse leveraged ETFs impose asymmetric spread and decay drag.

This is not a gap, opening-range, bar-momentum, displayed-depth, last-sale relay, or auction-price-proxy rule. Its economically defining input is the actual primary-listing auction imbalance state purchased after v33.

## Adversarial critique

### Reasons it may fail

- The auction exists to clear the imbalance. Residual demand visible before 09:29 may be fully absorbed at the opening print, leaving reversal rather than continuation.
- SPY auction flow may be mechanical benchmark flow with no information about the subsequent index path.
- The signal may merely rediscover the overnight gap or broad bullish drift.
- UPRO magnifies exposure, not alpha. A weak SPY effect will lose to its spread and tracking drag.
- A one-hour continuation is slow relative to institutional reaction time. Any genuine price-discovery effect may disappear at the uncross.
- Arca is the primary listing venue for SPY, but the message is not a complete view of all US equity demand.
- Historical market outcomes have been examined in many earlier experiments. Exact-rule preregistration limits local repair but does not create a pristine program-level holdout.

### Why a sophisticated firm would still run the scout

- The input is a structural, deadline-bound exchange event rather than another transform of ordinary bars.
- The rule is frequent, threshold-free, timestamped, and cheap to falsify.
- The mechanism can be identified against a sign-flipped state, a lagged-state placebo, and positive/negative pre-open reference gaps.
- Observed ask-to-bid execution and a second feed are available.
- Long-UPRO/cash avoids the repeatedly observed SPXU failure class while retaining enough convex exposure to face the SPY hurdle.

A sophisticated market-making or ETF desk could reasonably spend bounded research time on this mechanism. It would not deploy it from a backtest alone, and neither will this project.

## Rejected alternatives before implementation

- **Closing-auction continuation:** too little post-signal time to enter and exit before the close without becoming a latency/auction-fill study.
- **Auction extension/collar events:** structurally too rare for two trades per week.
- **Tick-level cross-wrapper quote parity:** likely an HFT/AP latency edge and not executable for this account.
- **Another signed-flow relay:** too adjacent to v16/v18/v28 and vulnerable to the same spread/feed failures.
- **Inverse-ETF bearish sleeve:** rejected ex ante because previous work established asymmetric SPXU execution drag and inverse-fund decay.
- **Thresholded imbalance magnitude or rolling-percentile filters:** rejected because they create a tuning surface before the sign mechanism itself has earned support.

## Stopping policy

One signal sign, one cutoff, one actuator, one entry, and one exit are frozen. Development failure locks all later return partitions. No sign inversion, magnitude threshold, time search, stop, alternate actuator, or bearish sleeve may rescue v34.
