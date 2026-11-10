# Creation-Conditioned Wrapper Discount — Preimplementation Critique v62

## Hypothesis

Positive split-adjusted share creation in UPRO or SPXU on session *t-1*
identifies a wrapper in which authorized participants recently transferred
inventory. If that same wrapper is below a simple SPY-implied fair value after
the next cash open, the discount should narrow as primary-market arbitrage and
continuous-market price discovery reconnect the ETF to its underlying exposure.

The signal is relative value, not an S&P 500 direction forecast:

- UPRO residual = `(UPRO midpoint / prior UPRO NAV - 1) / 3 - SPY return`.
- SPXU residual = `(SPXU midpoint / prior SPXU NAV - 1) / 3 + SPY return`.
- Only a fund with positive prior-session estimated creation and a strictly
  negative residual is eligible.
- If both qualify, buy the fund with the more negative residual in underlying
  units.

The prior NAV is reconstructed in point-in-time split units. SPY return uses
the prior official close and the completed 09:31 one-minute bar. The wrapper is
observed at the 09:32 BBO midpoint. No entry is allowed before 09:33.

## Why a serious ETF desk could care

This combines three economically separate observations:

1. Official shares outstanding identify primary-market inventory transfer.
2. Prior official NAV anchors the wrapper to its portfolio rather than to a
   potentially rich or cheap prior market close.
3. SPY supplies a liquid contemporaneous estimate of the underlying equity move.

Creation alone should not forecast index direction; V61 directly rejected that
interpretation. A discount conditional on creation is different. The relevant
mechanism is AP arbitrage and wrapper inventory normalization. That is a
recognizable ETF relative-value question that an institutional desk could take
seriously.

The returns-blind construction is measurable: 315 signals in 2021-2023
(2.092/week), 116/107/92 by year, 151 UPRO and 164 SPXU. Exact actions were
92.53% stable at both neighboring minute pairs and 96.15% stable across the
2023 ARCX/EQUS overlap.

## Hard critique

1. **Creation is observed after the fact.** A one-session delay makes the state
   causal, but the AP trade and its hedge may have been completed on the source
   day. There may be no inventory left to mean-revert.
2. **Shares outstanding do not identify the actor.** The change can reflect
   client facilitation, tax activity, rebalance demand, or mechanical fund
   operations rather than stressed dealer inventory.
3. **The fair-value model is deliberately crude.** UPRO and SPXU target daily
   returns through swaps and futures, not exactly three times SPY's traded
   return. Financing, expenses, dividends, futures basis, and derivative marks
   are omitted.
4. **Prior NAV is a mutable historical series.** ProShares restates old NAVs
   into current split units. The audit reverses every later split using the
   official split history, but a missing or revised corporate action would
   corrupt the anchor.
5. **The observations are not event-synchronous.** SPY uses a completed
   09:31 trade bar and the wrappers use a 09:32 sampled BBO. The one-minute
   separation is causal and feed-stable, but it is not a live index basket or
   simultaneous executable fair value.
6. **A negative residual is not necessarily an arbitrageable discount.** It can
   be compensation for spread, stale marks, leverage carry, or expected
   rebalancing. Buying at the ask and selling at the bid is therefore binding.
7. **The position is not market-neutral.** The strategy buys either a +3× or
   -3× fund and carries beta until 10:30. A correct wrapper-discount diagnosis
   can still lose if the underlying moves before convergence.
8. **The zero threshold is vulnerable to micro-noise.** No magnitude threshold
   is allowed because fitting one would overfit. Neighboring-clock and
   independent-feed stability are encouraging but do not prove that the
   residual exceeds executable costs.
9. **SPXU is a structural burden.** The inverse wrapper has wider spreads,
   reverse splits, derivative carry, and historically weak sleeves in several
   failed candidates. Both sleeves must remain; deleting SPXU after seeing P&L
   is forbidden.
10. **Multiplicity is substantial.** V62 follows many rejected opening,
    leverage-basis, flow, and macro hypotheses. Strong headline P&L is
    insufficient without annual, sleeve, cost, concentration, bootstrap,
    control, benchmark, and independent-feed survival.

## Frozen economic test

- Development only: 2021-01-04 through 2023-12-29.
- One long trade at most per session.
- Entry: exact 09:33 ask in the selected wrapper.
- Exit: exact 10:30 bid.
- Position size: $100 fractional notional, no leverage beyond the ETF, no
  overnight position.
- No stop, target, residual threshold, volatility filter, or regime filter.
- Primary execution feed: existing ARCX.PILLAR BBO-1m.
- Independent overlap: recompute the signal and fills using existing EQUS.MINI
  SPY bars and UPRO/SPXU BBO-1m.

The 09:33-10:30 window is fixed before return inspection. It gives the completed
bar and sampled quote a full minute to become observable and retains the
previously used first-hour endpoint rather than searching for a new profitable
horizon.

## Frozen controls

All controls use the same 09:33 ask and 10:30 bid:

1. **Discount only:** ignore creation and buy the more negative wrapper whenever
   at least one residual is negative.
2. **Creation only:** among positively created funds, buy the lower-residual fund
   even when its residual is positive.
3. **Redemption-conditioned discount:** replace positive creation with negative
   flow; this tests whether any recent share change, rather than creation
   inventory, explains the effect.
4. **Extra-lag creation discount:** use creation information delayed one
   additional trading session while retaining the current residual.
5. **Creation-conditioned premium continuation:** among positively created
   funds with positive residuals, buy the richest wrapper. This is the
   direction placebo.

V19 and V48 are already failed and outcome-exposed. Their action overlap was
checked returns-blind for distinctness; their parameters will not be retested or
repaired.

## Frozen admission standard

V62 advances only if every development gate passes:

- at least 2 executed trades per week;
- profit factor strictly above 1.10;
- positive fixed-$100 P&L in 2021, 2022, and 2023;
- positive fixed-$100 P&L in both UPRO and SPXU;
- compounded ending cash strictly above adjusted buy-and-hold SPY;
- positive after one extra cent per share at both entry and exit;
- positive with entry delayed five minutes to 09:38;
- positive after deleting the ten best sessions;
- five-session moving-block bootstrap 95% lower mean return above zero;
- positive independent-feed overlap with profit factor above one;
- actual mean trade return above every frozen control;
- at least 95% execution coverage of the 315 audited signals.

If any gate fails, V62 is rejected and 2024-2025 remains locked.

## Forbidden repairs

- residual-magnitude thresholds or ranks;
- sign inversion;
- alternate SPY/wrapper clocks;
- alternate entry or exit search;
- use of prior market close instead of NAV after seeing outcomes;
- creation-size thresholds or AUM scaling;
- deleting UPRO or SPXU;
- selecting only one year, weekday, volatility regime, or gap regime;
- adding futures, options, or short positions;
- opening 2024-2025 after any failed development gate.

## Decision

The market mechanism is coherent enough for a professional desk to test, and
the returns-blind measurement passed unusually strong stability checks. It is
not yet evidence of edge. Freeze the specification and open only the
2021-2023 execution outcomes.

