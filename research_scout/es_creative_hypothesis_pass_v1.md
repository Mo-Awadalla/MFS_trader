# ES Creative Hypothesis Pass v1

Saved: 2026-07-25

## Mandate

Invent genuinely new intraday mechanisms using the available Databento data while enforcing:

- at least two trades per week;
- one MES per engine;
- no overnight positions;
- conservative fills and commissions;
- positive development P&L in 2021, 2022, and 2023;
- positive development P&L on both long and short signals;
- no post-hoc side, year, clock, volatility, or magnitude filters;
- no 2024-2025 evaluation unless every development gate passes.

The research budget was fixed at three orthogonal families before proceeding further.

## Candidate 1: Closing Auction Value Ratchet

Mechanism: cumulative cash-session value migrates away from the opening auction center, while 13:59 price leads that migrated value into the closing participant handoff.

Development:

- 546 trades; 3.500 per week.
- +$647.92; profit factor 1.045.
- 2021: -$1,166.51.
- 2022: +$2,140.95.
- 2023: -$326.52.
- Long: +$390.07; short: +$257.85.

Decision: rejected without holdout access.

Lesson: closing-session price displacement was almost entirely a 2022 effect. A meaningful clock boundary does not by itself make late value migration persistent.

## Candidate 2: Opening Auction Pressure Vessel

Mechanism: unusually high opening volume per point of range represents absorbed pressure, and the final opening price relative to the auction center reveals the residual side.

Development:

- 351 trades; 2.250 per week.
- -$604.26; profit factor 0.911.
- 2021: -$268.53.
- 2022: -$465.10.
- 2023: +$129.36.
- Long: -$302.40; short: -$301.86.

Decision: rejected without holdout access.

Lesson: high effort per unit of movement behaved like completed two-sided matching, not stored directional energy. Volume is useful as an acceptance weight, but this test provides no evidence that volume/range pressure predicts direction.

## Candidate 3: Passive Absorption Paradox

Mechanism: from 15:00-15:30, price moving opposite net ES aggressor flow reveals control by passive liquidity. Trade in the direction price managed to move against aggression, using recorded MES bid/ask fills from 15:30:05 to 15:59:45.

Development:

- 176 trades; 1.128 per week.
- +$754.26; profit factor 1.267.
- 2021: +$754.37.
- 2022: +$577.97.
- 2023: -$578.08.
- Long: +$234.82; short: +$519.44.
- Median recorded MES spread: one tick at both entry and exit.

Decision: rejected without holdout access.

Lesson: passive-control information may be real but episodic. It is too sparse for the user's frequency constraint and failed in 2023. Widening the window, adding magnitude thresholds, or following the opposite signal after seeing this result is prohibited.

## Cross-candidate conclusion

Three ideas failed for three different reasons:

1. Value migration near the close was regime-dependent.
2. Opening volume/range pressure had the wrong economic interpretation.
3. Price-flow divergence contained some information but lacked frequency and temporal stability.

This is useful negative evidence. The available bars support accepted-value and structural-anchor concepts more consistently than synthetic pressure, arbitrary repeated clocks, overnight anchors, or late flow alone.

The recurring 2022 concentration is now an automatic rejection signature. A candidate must make money without 2022 being its sole engine.

## Current benchmark

No candidate from this pass replaces the unchanged three-engine paper portfolio:

- Compressed Opening-Auction Convexity.
- Opening Auction Center Migration.
- Midday Inventory Reload.

That portfolio meets the desired activity level but remains unsuitable for live deployment because its holdout edge is sensitive to approximately one additional tick at entry and exit and to removal of a small number of large winners.

## Next untouched research direction

The next pass should not mutate these three failures. It should investigate **state transitions between structural anchors**, rather than direction from a single anchor:

- whether the cash open, opening volume center, and cumulative session center change their price ordering;
- whether an anchor-order transition survives a subsequent participant handoff;
- whether a single symmetric finite-state rule can operate at least twice per week without clock replication.

This concept remains untested and intentionally unspecified here. Its exact state machine must be preregistered before any result is calculated.
