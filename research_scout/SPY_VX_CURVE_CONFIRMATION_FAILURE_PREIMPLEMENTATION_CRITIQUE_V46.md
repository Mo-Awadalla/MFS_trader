# SPY VX-Curve Confirmation Failure — Preimplementation Critique v46

## Frozen hypothesis

A prior-session SPY cash move that is contradicted by the same session's change in the official Cboe monthly VX futures curve reflects unstable cash-equity repricing. The VX curve aggregates forward volatility demand and hedging pressure. When that market moves toward stress while SPY rises, or toward relief while SPY falls, the unsupported SPY move should reverse during the next cash session.

For signal session `d`:

1. Select the nearest two standard monthly VX contracts whose expirations are strictly after `d`. Weekly VX contracts are prohibited.
2. Compute the normalized settlement slope `(VX2 settlement - VX1 settlement) / VX1 settlement`.
3. Compute its change from the immediately preceding complete CFE/SPY signal session.
4. Compute SPY regular-session return from the 09:30 ARCX.PILLAR one-minute bar open through the 15:59 bar close.
5. If SPY rose and the VX slope fell, buy SPXU on the next SPY session.
6. If SPY fell and the VX slope rose, buy UPRO on the next SPY session.
7. Otherwise hold cash.
8. Enter at the exact 09:31 observed ask and exit at the exact 15:30 observed bid. No overnight position.

There is no return, volatility, slope, volume, open-interest, weekday, expiration-distance, or gap threshold.

## Why this is genuinely different

V46 is not another opening range, same-clock tendency, ES volume scar, auction signal, BTC-to-equity relay, or post-release continuation. Its defining observable is the roll-aware term structure of actual standard monthly Cboe VX contracts. The SPY price input only establishes whether cash equities and forward volatility repriced in opposite risk directions during the completed prior session.

It is also not a post-result repair of V45. V45 asked whether a scheduled announcement's first cash reaction continued. V46 uses no announcement calendar and forms its state entirely before the trade day.

## Mechanism

A broad SPY rally accompanied by a flatter or more inverted VX curve says that forward volatility demand did not validate the apparent risk-on move. A SPY decline accompanied by a steeper contango curve says that forward-volatility pricing did not validate the apparent risk-off move. Cash equity can be temporarily dominated by flows, closing imbalances, or localized positioning while the VX curve reflects a broader forward hedge market. The next cash session provides a slow, non-HFT horizon over which the disagreement may resolve.

The rule waits until the next regular session. It does not claim to arbitrage a contemporaneous basis or compete on announcement latency.

## Source and data fidelity

- Official source page: `https://www.cboe.com/markets/us/futures/market-statistics/historical-data/futures`
- Raw package: `data/raw/cboe_vx_monthly_v46/`
- Package size: 62 standard monthly-contract CSVs, 11,565 data rows, 979,828 bytes.
- Contract expirations: January 2021 through February 2026.
- Weekly `VX01`–`VX53` files are explicitly excluded.
- Primary SPY signal bars: ARCX.PILLAR OHLCV-1m.
- Primary executions: observed ARCA.PILLAR UPRO/SPXU BBO.
- Independent overlap: EQUS.MINI SPY OHLCV-1m and UPRO/SPXU BBO beginning 2023-03-28.

Cboe files provide `Trade Date`, contract label, OHLC, settlement, change, total volume, EFP, and open interest. The signal uses settlement only. Exact publication timestamps are absent from the historical CSV, so the full overnight delay to the next 09:31 entry is mandatory.

## Strongest reasons it may work

1. **Defining data are economically relevant.** Actual front and second VX settlements encode the relative price of near versus later volatility protection, not a transformed SPY chart indicator.
2. **The signal is a disagreement, not raw momentum.** It requires the cash and forward-volatility markets to imply opposite risk changes.
3. **The execution horizon is slow.** All information is from the previous session, leaving an overnight observability buffer and avoiding latency claims.
4. **Daily opportunity set.** The state can occur repeatedly without rare-event thresholds and can plausibly meet the two-trades-per-week requirement.
5. **Proper contract handling is possible.** Actual monthly contracts, expiration dates, settlements, and rolls are available; no back-adjusted continuous future is needed.

## Strongest reasons it may fail

1. **No lead is established.** SPY and VX settlements respond to the same information. Disagreement can be noise rather than a forward-volatility lead.
2. **The overnight market can resolve it first.** ES, SPY premarket, options, and VX trade before 09:31. Any useful reconciliation may be gone by entry.
3. **Settlement is not a live close.** The official settlement methodology and timing differ from a contemporaneous executable VX quote. The overnight delay solves causality, not measurement equivalence.
4. **Curve changes include roll mechanics.** Even actual-contract selection can create discontinuities around expiration. Strict post-expiration selection and a roll-policy sensitivity are required.
5. **The conjunction may merely select prior-day SPY reversal.** A SPY-only reversal control and a VX-only direction control must show whether the curve adds anything.
6. **Inverse-leveraged execution is expensive.** SPXU spread and path dependence can erase a small underlying effect.
7. **Static next-day timing may be stale.** A full session after the signal is economically long for cross-market information diffusion.
8. **The 2022 stress regime can dominate.** Every development year, both UPRO/SPXU sleeves, and winner-deletion stress must independently survive.

## Economic upper-bound screen

The candidate is not structurally unmonetizable before testing: UPRO/SPXU routinely move materially over a 09:31–15:30 hold, while execution uses two marketable fills rather than a four-leg relative-value basket. This only establishes that costs need not mechanically exceed every conceivable move. It is not evidence of positive expectancy.

## Frozen partitions

- Development: 2021-01-01 through 2023-12-31.
- Holdout: 2024-01-01 through 2025-12-31, locked unless every development gate passes.

## Returns-blind gates

Before post-entry returns may be inspected:

1. at least 98% of eligible signal sessions have two valid positive VX settlements and complete SPY signal bars;
2. executable cadence is at least two trades per calendar week;
3. every development year has at least 100 executable trades;
4. the minority UPRO/SPXU direction is at least 20%;
5. exact primary entry and exit quote coverage is at least 95%;
6. independent-overlap action agreement is at least 90%;
7. excluding the last two sessions before each VX expiration preserves at least 80% of actions including cash;
8. signal dates strictly precede trade dates and no position survives 15:30.

## Development rejection gates

V46 passes only if all are true:

- at least two trades per week;
- fixed-$100 P&L positive and profit factor at least 1.05;
- every development year positive;
- UPRO and SPXU sleeves both positive;
- compounded ending cash beats split/dividend-adjusted SPY over the same period;
- positive after one extra cent at each fill;
- positive after a five-minute delayed entry;
- positive after deleting the ten best trades;
- positive on independent EQUS overlap;
- higher mean trade P&L than the SPY-only reversal, VX-only direction, one-session-lagged-curve, and sign-flipped controls.

Failure is terminal. No inversion, threshold, level bucket, roll window, alternative VX pair, opening filter, or hold-time repair is permitted on exposed dates.
