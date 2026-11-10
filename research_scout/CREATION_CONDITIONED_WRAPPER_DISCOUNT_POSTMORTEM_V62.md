# Creation-Conditioned Wrapper Discount Postmortem v62

## Decision

V62 is rejected in 2021-2023 development. The 2024-2025 partition remains
locked and unread.

The construction was frequent, causal, stable across neighboring minutes, and
stable across feeds. It showed a small positive gross result. That is not enough:
the result failed the preregistered benchmark, annual, sleeve, cost,
concentration, bootstrap, independent-feed, and control standards.

## Frozen result

| Test | Result |
|---|---:|
| Feature / executed signals | 315 / 315 |
| Trades per declared week | 2.092 |
| Fixed-$100 P&L | +$10.85 |
| Ending compounded cash | $108.84 |
| Adjusted SPY ending value | $132.40 |
| Profit factor | 1.077 |
| 2021 / 2022 / 2023 P&L | +$10.97 / +$5.41 / -$5.53 |
| UPRO / SPXU P&L | +$12.21 / -$1.36 |
| One-extra-cent stress | -$16.87 |
| Five-minute-delay stress | +$7.13 |
| Delete ten best sessions | -$19.36 |
| Five-session bootstrap lower mean | -0.001109 |
| Independent 2023 overlap | -$5.55, PF 0.783 |

Only cadence, execution coverage, and the five-minute-delay stress passed.

## What the controls say

The actual mean fixed-notional P&L was +$0.0344 per trade. It did not beat every
control:

- discount only: +$0.0205 mean, but negative in 2022 and 2023 and negative after
  deleting ten winners;
- creation only: -$0.0231 mean;
- redemption-conditioned discount: +$0.0426 mean, higher than V62, but negative
  in 2022 and negative after deleting ten winners;
- extra-lag creation discount: -$0.0367 mean;
- creation-conditioned premium continuation: -$0.1276 mean.

The very poor premium-continuation placebo is consistent with some gross
wrapper mean reversion. It does not validate the creation mechanism. The
redemption-conditioned control beating the actual rule is direct evidence that
positive creation did not uniquely identify the effect.

These controls are outcome exposed. Pooling creations and redemptions, selecting
redemptions, or promoting discount-only would be a post hoc repair. Each also
fails its own annual/concentration robustness.

## Why the apparent edge is not actionable

1. Median entry spread was 5.16 bps. The gross edge was smaller than a modest
   additional execution charge: one cent at each fill changed +$10.85 to
   -$16.87.
2. The inverse sleeve remained negative, repeating a major failure pattern
   across prior leveraged-ETF candidates.
3. The result decayed across the development years and was negative in 2023.
4. Independent consolidated-feed execution was negative for both wrappers.
5. The ten best sessions were larger than the entire gross profit.
6. The block-bootstrap lower bound was negative, so the average trade was not
   distinguishable from zero under the frozen dependence-aware test.
7. Even the unstressed compounded result lagged passive adjusted SPY by
   $23.56 per $100.

## Data-integrity lesson

The official ProShares historical NAV file is restated into current split
units. Before the audit, comparing that series directly with point-in-time BBOs
produced zero valid sessions because UPRO and SPXU were on incompatible units.
V62 corrected this without changing the hypothesis by reversing every later
official split. Any future use of mutable fund-history files must make the
point-in-time unit convention explicit before feature inspection.

## Prohibited repairs

- select the redemption-conditioned control;
- pool creation and redemption states;
- delete SPXU;
- choose 2021-2022 or exclude 2023;
- add a residual, flow-size, spread, or gap threshold;
- replace prior NAV with the prior market close;
- choose a different observation, entry, or exit minute;
- invert the signal;
- inspect 2024-2025.

## Next-direction boundary

Another opening wrapper-basis strategy is not justified by this result. The
next hypothesis must introduce a genuinely different causal observable and
mechanism, not another filter on the same residual. Candidate data must first be
audited for point-in-time availability, semantics, cadence, and independence
from V19, V48, and V62 before any return is opened.

