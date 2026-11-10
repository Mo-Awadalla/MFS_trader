# SH→SPXU Leverage-Escalation Latency — Preimplementation Critique v28

## Frozen hypothesis

SH and SPXU express the same inverse S&P exposure at -1x and -3x. Map a
buy-initiated trade in either fund to bearish underlying intent and a
sell-initiated trade to bullish intent.

From 09:30–10:29, retain only timestamp-verified fresh last-sale events. Match
each SPXU event to the most recent earlier unmatched SH event with the same
projected underlying sign. This creates non-reused low-leverage-to-high-leverage
transitions. Separately calculate the median SH→SPXU latency for bullish and
bearish transitions.

The direction with shorter median escalation latency is the urgent state:
shorter bullish latency buys UPRO; shorter bearish latency buys SPXU. Require at
least three matched transitions in each direction; an exact latency tie means
cash. Enter at the observed 10:31 ask and exit at the 15:30 bid, using $100,
one long fractional position, no margin, no futures, and no overnight holding.

## Would an elite ETF desk listen?

**Yes, as a leverage-demand transmission measurement.** The same economic
exposure is observed at two leverage points. A move from SH aggressor intent
into same-signed SPXU intent is an escalation along the leverage axis, not
merely confirmation between inverse products. Comparing bullish and bearish
transition speeds within the same session removes much of the instruments'
permanent liquidity difference.

This is distinct from V16. V16 counted adjacent UPRO/SPXU relays across opposite
wrappers. V28 uses only the inverse leverage ladder, matches low-to-high events
without reuse, and trades a relative latency surface rather than a relay count.

## Hard critique

- BBO-1m observes only each interval's last sale, not complete event flow.
- SH and SPXU have very different natural activity and clientele; latency may
  measure product liquidity rather than urgency.
- A common market maker can generate both legs, so transmission is not proof of
  investor escalation.
- Faster escalation may mark completed price discovery rather than continuation.
- Median latency is coarse under one-minute sampling.
- Venue composition is fatal: independently rebuilt ARCA and EQUS actions must
  agree before any return test.
- SPXU spread drag and passive SPY remain difficult hurdles.

## Returns-blind gates

- valid two-sided latency measurements on at least 90% of eligible sessions;
- at least two executable signals per week;
- at least 100 signals in every development year;
- minority direction at least 20%;
- median of at least five matched transitions per direction;
- at least 65% direction agreement when both feeds signal;
- at least 55% identical action across all overlap dates;
- at least 95% entry-quote availability.

## Frozen return gates

PF above one; all development years positive; UPRO and SPXU positive; cash
above SPY; positive after one extra cent each fill, five-minute delay, and
removing ten best trades; outperform sign-flipped, reverse-latency
(SPXU→SH), and unmatched raw-event-count contrasts. Holdout is opened only
after every development gate and must pass the analogous 2024/2025,
remove-best-five, cost, SPY, sleeve, and consolidated-execution gates.

## Decision

Advance to returns-blind audit only. No latency cutoff, event-count threshold
beyond the frozen measurement floor, clock, side, weekday, or venue selection
may be fitted.
