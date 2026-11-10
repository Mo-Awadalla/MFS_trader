# UPRO/SPXU Cross-Inverse Signed-Impact Asymmetry — Preimplementation Critique v18

## Frozen hypothesis before outcome inspection

Aggressor count alone confuses noise trading with informed trading. A more
relevant question is which projected S&P direction obtains more subsequent
quote movement from an aggressor event.

For fresh UPRO and SPXU last trades from 09:31–10:13 ET:

1. map a UPRO aggressor sign directly into S&P direction and invert SPXU;
2. map each wrapper's next-minute log-midpoint return into S&P direction by
   dividing by +3 for UPRO and -3 for SPXU;
3. multiply projected trade sign by projected next-minute return to measure
   own-direction impact;
4. separately average the impact of bullish and bearish events within each
   wrapper, then equally average the two wrappers;
5. subtract bearish-direction impact from bullish-direction impact.

A positive difference buys UPRO; a negative difference buys SPXU. An exact tie
or a session with fewer than three fresh events in any wrapper/direction cell
means cash. The minimum event count is a measurement-validity requirement, not
a fitted alpha threshold.

## Why a high-end ETF desk might listen

The inverse wrapper supplies a sign-reversed replication channel. If bullish
aggressors obtain unusually high subsequent quote impact in both the long and
inverse products, while bearish aggressors do not, the state is harder to
explain as wrapper-specific retail flow. Equal wrapper weighting prevents the
more active product from dominating.

This is a crude sampled estimate of a directional impact surface—the kind of
object an ETF execution desk cares about—rather than a candlestick, momentum,
or raw-volume rule. Its trade direction is fixed by the premise that informed
metaorders have persistent impact.

## Why it may fail

1. **The data sees only the last trade per minute.** It cannot estimate complete
   signed volume or a structural price-impact coefficient.
2. **Underlying news is a common cause.** A trade can precede a quote move
   without causing it. “Impact” is predictive shorthand, not causal proof.
3. **One-minute response may be too slow and too fast simultaneously.** True ETF
   arbitrage happens faster, while metaorder persistence is much slower.
4. **The impact/exhaustion sign is contestable.** High realized impact could
   mean informed continuation, or it could mean the price has already adjusted.
   Continuation is frozen because persistent metaorder execution supplies an
   ex-ante mechanism; the sign cannot be flipped after results.
5. **Last-sale side is forward-filled unless explicitly screened.** Only
   `ts_event` values inside their own BBO interval count.
6. **Quote endpoints are sampled.** The next-minute midpoint is not a
   time-weighted response and can reflect transient or stale quotes.
7. **Venue disagreement is fatal.** If ARCA and EQUS.MINI infer different
   directions, the state is feed composition rather than a stable impact
   asymmetry.
8. **SPXU spread drag and positive market drift remain adversaries.** Both
   wrappers, all years, cost/delay stress, winner-removal, and SPY
   outperformance remain mandatory.

## Distinctness from failed families

- V16 counted cross-wrapper aggressor-sign relays and ignored quote response.
- V10 used unsigned relative ETF participation preceding SPY price changes.
- V4 used displayed depth and activity masks.
- The ES aggressor studies operated in futures and did not use inverse-wrapper
  replication.

V18 asks whether sign-conditioned *quote response* agrees across inverse ETF
wrappers. No prior UPRO/SPXU rule estimated that object.

## Returns-blind admission gates

- valid paired impact states on at least 90% of feed session dates;
- at least two nonzero signals per calendar week;
- minority direction at least 20%;
- median of at least ten qualifying events per wrapper/direction cell;
- at least 60% same direction when both feeds signal;
- at least 50% identical action across all overlap dates.

## Preimplementation decision

**Advance to a returns-blind audit.** The state variable is identifiable, the
direction is fixed, and the inverse wrapper creates a meaningful replication
test. Low event counts or poor feed invariance reject it before P&L.

