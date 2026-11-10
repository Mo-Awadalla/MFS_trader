# IEF / SHY Duration-Impulse Persistence — Preimplementation Critique v58

## Frozen hypothesis

The prior session's relative total return of intermediate versus short
Treasuries is a slow discount-rate impulse that can persist into the next U.S.
equity cash session.

For each common IEF/SHY session:

1. Compute split/dividend-adjusted close-to-close IEF and SHY returns using
   only the completed session and the immediately preceding common session.
2. If IEF's return is strictly greater than SHY's, buy UPRO on the next SPY
   session.
3. If IEF's return is strictly less than SHY's, buy SPXU on the next SPY
   session.
4. If the returns are equal or an input is missing, remain in cash.
5. Enter at the exact 09:31 observed ask and exit at the exact 15:30 observed
   bid. Hold no overnight position.

There is no magnitude, yield, duration, volatility, weekday, gap, trend,
calendar, or regime threshold.

## Market mechanism

IEF targets U.S. Treasuries with seven-to-ten-year remaining maturities; SHY
targets one-to-three-year Treasuries. Their relative total return suppresses
some common Treasury carry and cash-rate movement while retaining much more
intermediate-duration sensitivity. IEF outperformance is consistent with
discount-rate relief; underperformance is consistent with a tightening
duration shock. The next cash session tests whether slower equity-duration,
balanced-fund, and systematic-allocation flows continue that impulse.

The signal contains no SPY, commodity, crypto, volatility-futures, or auction
input. V58 is not a repair or asset substitution inside V57's frozen
commodity/Treasury-opposition rule.

## Would a high-end trading firm take it seriously?

A systematic macro desk would take cross-maturity Treasury repricing and its
effect on equity duration seriously. It would also value a rule that is liquid,
causal, threshold-free, and easy to falsify against IEF-only, SHY-only,
prior-equity, lagged-spread, and sign-flipped controls.

The exact ETF rule is not production quality. A high-end desk would use
Treasury futures or cash-curve key rates, point-in-time DV01, carry/roll
adjustments, macro-surprise controls, and overnight equity-futures price
discovery. This implementation is a bounded direction test.

## Hard internal critique

1. **The spread is not duration neutral.** Subtracting ETF percentage returns
   does not equal a clean yield-curve factor. IEF's much larger duration means
   the rule may be little more than IEF direction.
2. **Rates down is not always bullish.** Intermediate Treasuries can rally on
   recession or flight-to-quality news; rates up can accompany strong growth.
3. **The information may be stale.** Treasury and equity futures trade
   overnight, so a 09:31 entry may occur after the equity response.
4. **Tiny moves receive full weight.** A negligible relative return has the
   same action as a large shock. No magnitude threshold may be added later.
5. **ETF total returns mix the intended state with carry and distributions.**
   Adjusted history is not a point-in-time yield curve. Alternate unadjusted
   actions must agree at least 95% including cash.
6. **SHY may add no information.** Candidate mean trade P&L must exceed raw
   IEF-direction continuation; otherwise the relative-maturity story is not
   identified.
7. **2022 can dominate.** The hiking cycle produced unusually persistent bond
   losses. Every year, both sleeves, and best-ten deletion must pass.
8. **SPXU friction remains asymmetric.** A real tightening state may still be
   too weak for the inverse wrapper.
9. **Daily equity risk premium is a confound.** The rule must outperform
   prior-SPY-direction continuation on mean trade P&L and beat total-return
   SPY in compounded development wealth.
10. **Multiplicity is severe.** V58 is one frozen maturity-spread test. No
    duration estimate, alternative maturity ETF, threshold, side deletion,
    inversion, or regime split can be chosen from its outcomes.

## Decision before implementation

Advance only to a returns-blind feasibility and source-invariance audit.

Development is 2021-2023. The 2024-2025 target-return partition remains locked
unless every development gate passes. Assets, mapping, clocks, controls, and
gates are frozen before candidate P&L is computed.

