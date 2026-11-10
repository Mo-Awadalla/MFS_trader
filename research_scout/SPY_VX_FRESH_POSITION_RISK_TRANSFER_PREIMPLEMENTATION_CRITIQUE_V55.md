# SPY VX Fresh-Position Risk Transfer — Preimplementation Critique v55

## Frozen hypothesis

A change in the front standard-monthly VX settlement is more informative when
the same contract's open interest expands. Price supplies the direction; rising
open interest distinguishes fresh position formation from a move dominated by
position closure.

For complete CFE/SPY sessions:

1. Select the nearest standard-monthly VX contract expiring strictly after the
   signal date. Weekly contracts are prohibited.
2. Require that the same contract was also front on the immediately preceding
   complete session. Roll transitions remain cash.
3. Measure that contract's settlement change from the prior session.
4. Align open interest causally: the public CSV's `Open Interest` is a
   start-of-day field. The change attributable to signal-day trading is the
   next session's start-of-day value minus the signal day's start-of-day value.
5. If settlement rose and open interest strictly rose, buy SPXU on the next SPY
   session. If settlement fell and open interest strictly rose, buy UPRO.
   Otherwise remain in cash.
6. Enter at the exact 09:31 observed ask and exit at the exact 15:30 observed
   bid. Hold no overnight position.

There is no magnitude, curve-level, volatility, volume, weekday, gap, or regime
threshold.

## Market mechanism

VX futures are a direct S&P 500 volatility and protection market. A rising
front contract with expanding positions is consistent with fresh protection
demand or fresh volatility risk transfer; a falling front contract with
expanding positions is consistent with fresh short-volatility/carry supply.
Because institutional hedging and risk-budget changes can be executed across
sessions, the state may persist into the next U.S. cash session.

The construction does not claim that open interest identifies buyer and seller
types. Every new contract creates both a long and a short. The price move is
used only as evidence of which side demanded more price concession.

## Would a high-end trading firm take it seriously?

A systematic volatility or index desk would recognize the inputs as relevant:
actual VX contracts, explicit rolls, settlement direction, and position
formation. The experiment is slow, causal, and executable without pretending
that one-minute ETF data can capture a latency arbitrage.

The desk would treat it as a research hypothesis, not an established edge.
Professional implementation would want timestamped clearing/open-interest
publication, participant classifications, VX trade direction, options surface
changes, and an ES/SPY execution benchmark. Those are absent here.

## Hard internal critique

1. **Open interest has no directional ownership.** A rise means new contracts,
   not informed long volatility. Settlement direction is an imperfect
   aggressor proxy.
2. **Publication timing is inferred.** Cboe describes CFE open interest as a
   start-of-day field and has documented approximately 10 p.m. CT
   dissemination, but the historical CSV has no row-level publication
   timestamp. A delayed operational file could violate a 09:31 decision.
3. **Overnight markets may absorb the state.** VX, ES, options, and SPY
   premarket all trade before the cash entry.
4. **The front contract is roll-sensitive.** Requiring the identical contract
   on adjacent settlement dates avoids synthetic roll returns but removes some
   sessions.
5. **The topology has prior exposure.** BTC fresh-position risk transfer v44
   failed. VX is economically closer to SPY, but reusing price-plus-open-
   interest confirmation increases the program-level multiplicity burden.
6. **2022 can dominate.** Volatility-position signals may look excellent only
   during the tightening/bear regime. Every development year, both sleeves,
   and winner deletion must pass.
7. **SPXU is expensive to cross.** The risk-off sleeve must overcome its wider
   spread and inverse-wrapper drag.
8. **V47 just failed later years.** V55 is not allowed to use V47's curve
   signal, flip, regime behavior, or holdout result as a filter. Its defining
   observable is same-contract position formation.

## Decision before implementation

Advance only to a returns-blind feasibility audit. The causal quantity is new
to the VX program and economically relevant, but the open-interest alignment
and cadence must be verified before any post-entry ETF price is read.

Development is 2021-2023. The 2024-2025 return partition remains locked unless
all frozen development gates pass. No failed sign may be inverted and no
threshold, curve input, alternative contract, clock, or regime filter may be
added after outcomes.

