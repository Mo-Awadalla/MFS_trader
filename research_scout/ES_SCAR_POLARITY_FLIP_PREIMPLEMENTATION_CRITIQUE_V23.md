# ES Scar Polarity Flip / Center Reacquisition — Preimplementation Critique v23

## Hypothesis stated before outcome inspection

The exact ES price with the most transacted volume from the prior session's
15:00–15:29 window begins the next day as inherited accepted value. If the new
09:30–09:59 auction moves both its volume-weighted center and terminal close
strictly across that scar, the scar's role may change from an attractor into a
boundary.

The first later contact with the old scar is the falsification event:

1. Use the unchanged prior-scar handoff state from v20.
2. From 10:00 through 13:29, inspect only the first ES bar whose range touches
   the prior scar.
3. The state survives only if that bar closes back on the new-center side,
   never trades one tick through the scar, and does not already touch the new
   opening center.
4. Wait one full dead minute. Cancel if that minute touches either boundary.
5. Buy fractional UPRO for a bullish state or SPXU for a bearish state at the
   following observed ask.
6. Exit at the observed bid one minute after ES first touches either a stop one
   tick through the old scar or the new opening center. If neither occurs, exit
   at 15:30.

When the first contact closes through the scar, breaches the one-tick
invalidation, or completes the trip to the center, the day is permanently
discarded. No later retest may substitute.

## Would a high-end ETF or index-arbitrage desk listen?

**Yes, as an auction-memory state-transition test.**

The interesting claim is not generic “support becomes resistance.” Both
boundaries are independently formed transaction-value objects: the old one is
an exact price-level volume mode from the prior close, while the new one is a
volume-weighted center from the cash opening auction. Opening acceptance first
changes their ordering; first contact then tests whether inventory at the old
mode has changed sign. The payoff is a bounded traversal between those two
anchors, not a fitted number of ATRs and not a close-carry lottery.

The strategy also changes the question raised by v20. V20 showed that immediate
opening acceptance carried directional information but depended on rare trend
survivors. V23 asks whether waiting for the inherited anchor to be challenged
can convert that information into a high-hit-rate, structurally bounded
reacquisition of new value.

## Strongest argument that it should work

Participants transacting heavily at the prior closing mode can remain anchored
there. When a new auction establishes accepted value across it, the first return
tests whether those inventories defend, capitulate, or reverse. A rejection
without a one-tick breach provides a much tighter invalidation than immediate
10:01 entry, while the opening center supplies a price objective created by a
different participant set. The expected payoff therefore does not require a
full afternoon trend.

## Strongest arguments that it should not work

1. **It may be decorated support/resistance.** A volume mode is not proof of
   identifiable inventory ownership.
2. **One-minute bars hide event order.** Requiring the contact bar to touch
   neither stop nor target is deliberately conservative but cannot prove the
   within-bar sequence.
3. **The target can be economically tiny.** A high hit rate is irrelevant if
   UPRO/SPXU spread crossing consumes the center traversal.
4. **First contact may occur after the information is stale.** The 13:29 cutoff
   is a frozen morning/lunch boundary, not an estimated decay constant.
5. **One ES tick is a fragile boundary.** It is structurally clean but may
   cancel many valid economic retests because ordinary noise crosses it.
6. **ES-triggered ETF exits are delayed.** A stop or target is observed only
   after the ES minute completes, and the ETF fill comes from the next BBO
   minute.
7. **The lineage is contaminated.** V23 is motivated by v20's known tail
   problem and uses the same opening handoff state. It is a new payoff test, not
   independent discovery or prospective evidence.
8. **A passive SPY hurdle remains difficult.** Bounded small gains must compound
   past SPY after every observed spread.

## Returns-blind admission gates

Before reading any ETF price after entry:

- at least two executable development entries per calendar week;
- at least 95% ARCA entry-quote availability;
- neither direction below 20%;
- at least 75 executable entries in every development year;
- median target distance at least four times the one-tick stop distance. This
  is a geometry gate measured entirely before ETF outcome inspection.

Failure ends the candidate without P&L.

## Frozen return gates

Development must have PF above one; positive P&L in 2021, 2022, and 2023;
positive UPRO and SPXU sleeves; compounded cash above passive SPY; positive P&L
after one extra cent on entry and exit; positive P&L with five extra minutes of
entry delay and stale-state cancellation; positive P&L after deleting the ten
best trades; and higher P&L than an equal-clock sign-flipped placebo.

Only a complete development survivor may open 2024–2025. The holdout must pass
the analogous year, direction, SPY, cost, delay, remove-best-five, and
consolidated-feed gates without a rule change.

## Preimplementation decision

**Advance only to a returns-blind feasibility audit.** The two-anchor role
transition is specific enough to interest a desk and the bounded payoff attacks
the precise weakness of v20. Frequency and economic geometry may still reject
it before any return is read.
