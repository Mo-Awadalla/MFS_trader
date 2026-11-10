# Constituent Liquidity Relay: Preimplementation Critique v77

## Frozen hypothesis

A participation-scheduled index or large basket order need not move all
constituents simultaneously.  The opening half-hour can first move names where
liquidity is immediately available.  If, during the next nonoverlapping
half-hour, trading participation migrates into the earlier laggards, those
laggards join the original cross-sectional direction, and the early leaders do
not reverse, the observation is consistent with an unfinished parent order
being worked through the basket.

For the frozen 133-stock universe:

1. define the first-half direction as the sign of the cross-sectional median
   09:30--10:00 return;
2. call stocks with a first-half return in that direction `leaders` and stocks
   with the opposite sign `laggards`;
3. calculate the laggard share of total universe trade volume separately for
   09:30--10:00 and 10:00--10:30;
4. require the laggard volume share to rise strictly in the second half;
5. require the median laggard second-half return to have joined the first-half
   direction; and
6. require the median leader second-half return not to have reversed.

Trade UPRO for a positive direction or SPXU for a negative direction from the
observed 10:31 ask to the observed 15:55 bid.  There is no return magnitude,
volume magnitude, percentile, volatility, calendar, or regime threshold.

## Why an ETF desk could take the question seriously

The hypothesis concerns the execution path of a multi-name parent order rather
than an unexplained price correlation.  Participation algorithms distribute
orders according to available volume, while index and ETF market makers monitor
whether cash-basket pressure is broadening or being absorbed.  A migration of
actual trading participation into earlier contra-direction names, accompanied
by their directional catch-up, is a more specific footprint than index
momentum or breadth alone.

The exact public-data implementation remains only a research proxy.  A
sophisticated desk would use signed child orders, consolidated venue data,
point-in-time index weights, futures and ETF inventory, and event-time impact
curves.  The present test asks whether a coarse, public footprint survives
strong falsification; it does not claim to identify a particular initiator.

## Adversarial internal critique

### The grouping can create a mechanical catch-up effect

Laggards are selected because their first-half returns oppose the median
direction.  Their subsequent movement toward that direction can be ordinary
short-horizon mean reversion, not completion of a basket order.  The frozen
price-only relay control therefore uses the same leader/laggard construction
without the volume-migration condition.  V77 must add value over that control.

### IEX volume is venue-local and unsigned

Alpaca's free IEX feed does not measure consolidated volume or aggressor side.
A change in IEX routing share can masquerade as a change in participation, and
volume cannot establish whether buyers or sellers initiated trades.  This is
why volume-share migration is compared within the same venue and day, and why
odd/even and modulo-three subuniverses must independently reproduce the action.
Passing those checks would improve measurement credibility but would not make
the source production-grade.

### Opening microstructure can contaminate the comparison

The first half-hour differs structurally from the second: price discovery and
opening prints are concentrated near 09:30.  Comparing volume levels would be
invalid.  The rule instead compares the laggard group's share of same-window
universe volume.  Even that share can change mechanically, so the price-only
and volume-migration-only controls remain mandatory.

### This may collapse to breadth or SPY momentum

The action direction is derived from constituent returns and may merely echo
SPY's first-hour sign.  Before P&L, action agreement with ordinary SPY
first-hour momentum must be at most 85%, and signal-date overlap with both V75
and V76 must be at most 80%.  Failure means no backtest.

### Static membership is survivorship-biased

The large-cap universe was frozen earlier but is not point-in-time S&P 500
membership.  The experiment can test reproducibility of a public proxy, not
claim an unbiased historical index-basket estimate.  A passing result would
still require later locked years and prospective validation.

### The proposed horizon may be wrong

An institutional basket can finish before 10:30, be completely hedged in
futures, or reverse after its benchmark window.  The 10:31--15:55 hold is
inherited from V73--V76 to avoid an exit search.  No alternative clock is
allowed after results.

### SPXU friction remains a hard falsifier

Many previous candidates looked tolerable in aggregate only because UPRO
masked a losing inverse sleeve.  Both sleeves and every year must be positive.
No UPRO-only rescue is allowed.

### Multiple testing is severe

This is candidate V77 in a heavily exposed research program.  Exact freezing
prevents local repair but cannot restore pristine development data.  A
development survivor remains provisional until untouched recent years and
prospective paper trading also pass.

## Returns-blind admission gates

Before any post-10:31 return is read:

- at least 2.0 signals per calendar week and at least 100 in each year;
- at least 30% of actions in the minority direction and 25 direction switches
  in each year;
- selection of 20%--80% of valid sessions;
- at least 70% action agreement for odd, even, and each modulo-three
  subuniverse;
- at most 85% action agreement with SPY first-hour momentum;
- at most 80% signal-date overlap with V75 and separately with V76;
- at least 95% valid-session source coverage, positive volume on at least 99%
  of included bars, and exact source-hash reconciliation;
- at most 6% of signals in any one calendar month; and
- at least 95% primary and 90% independent execution-quote coverage.

Failure of any gate rejects V77 without P&L.

## Frozen development gates if admitted

All are required on 2021--2023:

1. at least two executed trades per week;
2. profit factor strictly above 1.10;
3. positive fixed-notional P&L in 2021, 2022, and 2023 separately;
4. positive UPRO and SPXU sleeves separately;
5. compounded ending cash above adjusted buy-and-hold SPY;
6. positive after one extra cent per share at entry and exit;
7. positive with entry delayed five minutes;
8. positive after deleting the ten best sessions;
9. positive five-session-block bootstrap 95% lower mean-return bound;
10. permutation p-value at most 0.05;
11. positive independent-feed overlap; and
12. primary mean trade return strictly above SPY-momentum, price-only relay,
    and volume-migration-only controls under identical execution.

No sign flip, parameter search, threshold, universe deletion, sleeve deletion,
alternate clock, or favorable subset is permitted.  Recent years stay locked
unless every gate passes.
