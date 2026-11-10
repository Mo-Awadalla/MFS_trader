# SEC Earnings-Breadth Index Read-Through Postmortem v73

## Decision

Rejected in frozen 2021–2023 development.  Recent years remain locked.

## What was real

The returns-blind construction was strong: 438 signals, 2.91 per week,
144/146/148 by year, balanced directions, 85% neighboring-window action
stability, only 51% agreement with SPY momentum, low issuer concentration, and
complete execution evidence.

The outcome was not pure noise in every view:

- gross fixed-$100 P&L was +$22.16;
- the multi-issuer sleeve made +$28.02 with PF 1.134;
- 2022 and 2023 were positive;
- the five-minute-delayed implementation made +$38.30;
- independent 2023 overlap made +$16.21 with PF 1.287;
- the actual mean exceeded both frozen controls.

Those observations do not authorize a rescue because they were exposed only
after the specification was frozen.

## Why it failed

- PF was 1.062 versus the required 1.10.
- 2021 lost $15.35 and SPXU lost $2.78.
- Single-issuer sessions lost $5.86.
- One adverse cent at each fill changed +$22.16 to -$14.57.
- Removing the ten best sessions changed the result to -$47.05.
- The block-bootstrap lower mean was -0.001731.
- The month-stratified permutation p-value was 0.127.
- Compounded ending cash was $110.35 versus adjusted SPY at $132.40.

The aggregate filing reaction appears to contain some genuine cross-sectional
information, especially when several firms report.  It is too thin and
cluster-dependent to survive leveraged-ETF execution or establish reliable
index read-through.  SPY incorporates most large-cap cash-flow news too
efficiently for a 10:31 continuation rule.

## Binding lessons

1. Clean causal event timing and balanced actions do not imply an economically
   large transmission to SPY.
2. Independent-feed strength confined to 2023 cannot override a negative 2021
   or a failed full-period bootstrap.
3. A profitable multi-issuer diagnostic is not an admissible strategy when it
   was not the frozen rule and falls below the cadence requirement.
4. Gross event alpha below one cent per ETF fill is not suitable for this
   execution model.

## Forbidden repairs

Do not select multi-issuer sessions, remove single-issuer sessions, keep only
UPRO, exclude 2021, use the 10:36 entry because it performed better, threshold
the residual, delete issuers/sectors, reweight by filing count, or use the
independent 2023 overlap as a new development set.  The Item 2.02
first-hour-to-close index-read-through specification is consumed.
