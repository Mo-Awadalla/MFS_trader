# Leveraged-ETF Post-Open Fair-Value Simplex — Preimplementation Critique v49

## Causal family

V49 is not an auction-imbalance sign, opening-gap continuation, or a modification of V48's official close-to-open basis. It measures the first continuous-market repricing after the official Core Open.

The lower-leverage cash ETFs form an implied SPY-return consensus:

`consensus = median(SPY return, SSO return / 2, -SH return, -SDS return / 2)`

All returns run from each instrument's own official ARCX opening price to a fresh EQUS.MINI trade-event pre-trade midpoint immediately after 09:30:05.

The two 3× fair-value residuals are:

- `UPRO residual = 3 × consensus - UPRO return`
- `SPXU residual = -3 × consensus - SPXU return`

Each residual is centered by its own trailing 20 eligible observations. If exactly one residual is positive, buy that underpriced 3× ETF. If both or neither are positive, remain in cash.

## Institutional mechanism

SPY and the 1×/2× products can complete price discovery before a thinner 3× wrapper. A market maker or AP can hedge a temporarily underpriced 3× ETF in the lower-leverage products, pulling the wrapper toward the cross-leverage consensus. The simulated account takes only the permitted long cash-ETF leg.

This is a convergence claim, not a directional momentum claim: UPRO can be underpriced after either an up or down move, and the same is true for SPXU.

## Adversarial desk response

- EQUS.MINI is trade-event-conditioned and not official SIP NBBO.
- Cross-symbol observations can be asynchronous enough to manufacture a residual.
- The standing age of each displayed quote is unknown.
- A true ETF arbitrage should vanish faster than retail execution latency.
- Official opening prices and anonymized continuous BBOs are different market views.
- Without iNAV/NAV and baskets, the lower-leverage median is only a proxy for fair value.
- Earlier leverage-geometry families failed; complexity cannot make the same economics new.

V49 addresses, rather than hand-waves, these objections:

1. Every defining pre-trade BBO must be observed at a trade event no more than five seconds after 09:30:05.
2. The six defining event timestamps must span no more than five seconds.
3. Every defining event and all official opening statistics must be received before a fixed 09:31:00 signal boundary.
4. Orders occur only after 09:31:01, 09:31:05, or 09:32:00, giving 1/5/60-second delays after the boundary.
5. Action stability is checked at the adjacent 09:30:01 observation.
6. Failure of synchronization, cadence, or latency is terminal without P&L.

## Returns-blind gates

- At least two synchronized feature signals per declared week from 2023-03-28 through 2023-12-31.
- At least 80 development-overlap signals and at least 20 signals in 2026.
- Both UPRO and SPXU, with minority actuator at least 20%.
- At least 90% complete 1/5/60-second entry-plus-exit evidence among feature signals.
- At least 60% identical action including cash at the adjacent 09:30:01 observation.
- Every six-symbol observation has event wait and cross-symbol timestamp span at most five seconds.
- Every opening statistic and defining quote is received before 09:31:00.
- Signal selection between 20% and 80% of synchronized warm sessions.
- Ten- and 40-observation residual baselines must each agree with the primary action including cash at least 70%.

## Frozen execution if feasible

- Signal boundary: 09:31:00 ET.
- Entry asks: first eligible events after 09:31:01, 09:31:05, and 09:32:00.
- Primary delay: five seconds.
- Exit bid: first eligible event after 09:35:00.
- Maximum execution-event wait: 60 seconds.
- Fixed $100 fractional long UPRO or SPXU, one position, no margin, no shorting, no overnight.

## Alpha controls if authorized

The preregistered test must include a one-session-shifted simplex, randomized session matching, reversed residual selection, SPY trading, 1×/2×/3× leverage-scaled outcomes, gap-only and recent-momentum-only rules, spread/volatility matching, and one-cent-per-share adverse execution.

## Decision

**Pass V49 to returns-blind feasibility only.** The idea is interesting only if the measured lead is demonstrably larger than synchronization error and execution latency.
