# ES Three-Clock Sensor / Leveraged-ETF Actuator — Preimplementation Critique v22

## Hypothesis stated before ETF outcome inspection

Three already frozen ES engines identify different forms of unfinished intraday
inventory:

1. **Compressed opening-auction convexity**: a narrow opening range followed by
   a confirmed range escape.
2. **Opening-auction center migration**: both the opening close and its
   volume-weighted center migrate away from the cash open.
3. **Midday inventory reload**: lunch partially reverses the morning move
   without crossing the cash open.

The ES signal, side, structural stop, and time exit are unchanged. ES is only
the sensor. The $100 account buys fractional UPRO for a bullish ES state or
fractional SPXU for a bearish state at the observed ask, then sells at the
observed bid when the ES structural stop fires or the frozen clock expires.

The account may hold only one position and make only one trade per RTH session.
It uses the pre-existing first-signal rule: choose the earliest geometrically
valid engine; for an exact entry-minute tie choose smaller frozen ES risk, then
engine name. Ignore all later signals even if the selected trade stops. ETF
entry is delayed one full minute after the ES base entry so every ES input and
the tie breaker are observable. If the ES stop is touched during that dead
minute, cancel the day and do not substitute a later engine.

## Would a high-end ETF trade desk listen?

**Yes, as a transport and execution-cost hypothesis.**

The non-obvious claim is that a strategy can fail as a small futures account
without its information state being false. MES charges a large fixed toll
relative to a $100 account and realizes stops on a coarse tick grid. Fractional
UPRO/SPXU instead express the same underlying direction with continuous
notional sizing, no explicit commission in the supplied model, and observed
wrapper spreads. The experiment therefore separates *signal quality* from the
economics of the original actuator.

The three clocks are also economically distinct. Opening center migration is an
auction-state signal, convexity waits for a later range escape, and reload asks
whether a morning inventory move survives lunch. This is not a parameter sweep
over one feature, and the portfolio rule predates this ETF transport.

## Strongest argument that it should work

All three engines forecast completion of an already identified inventory
direction rather than unconditional drift. Their ES portfolio was positive in
each year from 2021 through 2025 and survived a chronological holdout before
this transport was proposed. If its weak small-account economics mainly came
from MES's fixed commission and tick-sized fills, a $100 fractional ETF
actuator can preserve the directional information while sharply reducing the
fixed-dollar implementation burden. Earliest-signal selection makes the
capital constraint explicit and avoids choosing engines by historical return.

## Strongest arguments that it should not work

1. **This is not a new untouched signal.** The ES engines and the first-signal
   portfolio have already been observed through 2025. The ETF transport can
   test actuator economics, not restore prospective status.
2. **The futures portfolio was tail-fragile.** Its one-position challenger was
   negative after removing its five largest holdout winners. A cheaper wrapper
   cannot rescue information that exists only in rare outliers.
3. **ETF leverage is reset daily, not a frictionless ES multiple.** UPRO and
   SPXU have asymmetric spreads, tracking, financing, and rebalance effects.
4. **A one-minute causal bridge can erase the edge.** The futures entry was
   sensitive to delay. Cancelling stale states reduces frequency; entering
   later worsens price.
5. **The ES stop cannot specify an ETF fill price.** It only specifies an exit
   time. A fast ES break can move the wrapper substantially before the next
   one-minute BBO observation.
6. **Earliest signal discards diversification later in the day.** The rule is
   required by the $100 capital constraint, but may disproportionately select
   opening engines and leave too few reload trades.
7. **SPXU is a hard implementation test.** A bullish-market sample can make
   UPRO look good while bearish trades lose to spread and decay.
8. **Passive SPY is a severe hurdle.** Frequent round trips must beat SPY's
   2021–2025 compounding after every observed spread, not merely produce
   positive fixed-notional P&L.

## Returns-blind admission gates

Before reading any post-entry ETF price or P&L on development:

- at least two executable entries per calendar week;
- at least 95% entry-quote availability among otherwise eligible ARCA days;
- neither UPRO nor SPXU may be less than 20% of executable entries;
- every development year must contain at least 150 executable entries;
- every engine must contribute at least 25 executable development entries.

Failure ends the candidate without a return backtest.

## Frozen return gates

Development must have PF above one; positive 2021, 2022, and 2023; positive UPRO
and SPXU sleeves; positive contribution from every active engine; compounded
cash above passive SPY; positive fixed-$100 P&L after one extra cent on both
fills and after an additional five-minute entry delay with stale-state
cancellation; positive P&L after deleting the ten best trades; and higher P&L
than the sign-flipped placebo.

Only then may 2024–2025 be opened. Holdout must independently pass the analogous
year, side, engine, SPY, cost, delay, and remove-best-five gates, plus positive
execution on the consolidated EQUS feed. No rule may change after development.

## Preimplementation decision

**Advance to a returns-blind feasibility audit only.** The mechanism is
specific, the signal and capital-allocation rule are frozen outside the ETF
return sample, and the actuator change addresses a known economic failure
directly. The prior tail fragility is serious enough that concentration gates,
not headline return, decide whether this is impressive.
