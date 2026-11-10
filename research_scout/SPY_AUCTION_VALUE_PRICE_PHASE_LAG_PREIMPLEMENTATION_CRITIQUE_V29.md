# SPY Auction Value/Price Phase-Lag — Preimplementation Critique v29

## Frozen hypothesis

Use two disjoint SPY cohorts: 09:30–09:59 and 10:00–10:29. For each, compute:

- volume-weighted typical-price center;
- terminal close;
- phase gap = center minus terminal close.

The signal is `second phase gap - first phase gap`, equivalently the movement
of accepted value minus the movement of terminal price. A positive residual
means accepted value migrated upward more than the terminal print, so price is
lagging value and V29 buys UPRO. A negative residual buys SPXU. Exact zero means
cash. Observe the complete 10:30 minute, enter $100 at the 10:31 ask, and exit
at the 15:30 bid. One long fractional position, no futures, margin, shorting, or
overnight exposure.

## Institutional-interest test

**Pass.** This is a phase relationship between two independently formed
auction objects, not a price-return direction. A volume center summarizes where
activity accepted price; the terminal print is where the cohort stopped. Their
gap is an inventory displacement. The change in that gap asks whether accepted
value is leading or lagging the observable endpoint as control passes to a new
participant cohort.

It is not V24 with a relaxed filter. V24 traded only monotonic center migration
confirmed by the second close. V29 removes absolute direction entirely and
trades the signed *difference between value displacement and endpoint
displacement*. It can be bullish on a down morning or bearish on an up morning.

## Hard critique

- The volume center may be only a smoothed price, making the residual an
  over-described short-term reversal statistic.
- ARCA and EQUS volume compositions differ; a true accepted-value state must
  preserve direction across feeds.
- The catch-up sign is contestable: a lagging terminal price can reflect value
  reverting toward price rather than price catching value.
- Exact-zero entry with no magnitude floor may trade economically negligible
  residuals. A threshold is forbidden because it would invite optimization.
- The signal is nearly daily, so spread drag accumulates rapidly.
- Close-carry may have no relation to a first-hour phase gap; mechanism
  contrasts must beat pure first-hour momentum and simple center migration.

## Returns-blind gates

- at least 98% valid measurement coverage;
- at least four executable signals per week;
- at least 150 signals in every development year;
- minority direction at least 30%;
- at least 85% cross-feed direction agreement;
- at least 80% identical cross-feed action;
- at least 95% entry-quote availability.

## Frozen return gates

PF above one; every development year and both actuators positive; ending cash
above SPY; positive after one extra cent each fill, five-minute delay, and
removing ten best trades; outperform sign-flipped, first-hour price momentum,
and raw center-migration contrasts. Holdout remains locked unless every gate
passes, then requires analogous year, sleeve, SPY, cost, concentration, and
consolidated-execution success.

## Decision

Advance to returns-blind audit only. No residual threshold, standardization,
sign inversion, clock change, or regime filter may be introduced.
