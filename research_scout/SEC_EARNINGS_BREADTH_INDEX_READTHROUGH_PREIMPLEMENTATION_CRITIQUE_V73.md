# SEC Earnings-Breadth Index Read-Through: Preimplementation Critique v73

## Failure lineage

The repository's earlier SEC Item 2.02 scout bought individual stocks whose
first 30-minute residual reaction was positive.  It failed costs, chronological
stability, bootstrap, and profit-factor gates.  V73 does not rescue that rule:
it never trades a filing issuer, never selects only positive issuers, and never
uses its event-level outcome.  The new question is whether the *signed
cross-sectional center* of large-cap earnings reactions is an index-level
cash-flow-news state.

## Hypothesis

Item 2.02 filings accepted after the prior cash close and by 09:25 ET disclose
completed operating results.  During the first cash-session hour, each issuer's
return relative to SPY measures the market's signed reaction to that company
news after removing the common market move.  The median reaction across all
eligible filers is a robust earnings-breadth shock.

If that median is positive, broad cash-flow expectations are being revised
upward and systematic/sector portfolios may continue transmitting the
read-through through the S&P complex; buy UPRO.  If negative, buy SPXU.  This is
a continuation hypothesis about aggregate fundamental news, not a claim that
the filing timestamp mechanically moves SPY.

## Would a high-end ETF desk investigate it?

Yes, as a bounded research hypothesis:

- the event is an official, timestamped corporate disclosure;
- direction comes from issuer price discovery, not a fitted text score;
- SPY is removed from every issuer reaction before aggregation;
- the median prevents one extreme earnings move from setting magnitude;
- the decision is formed after a standard first-hour discovery window and
  before ETF entry.

But the strongest objections are substantial:

1. SPY and its constituents are arbitraged continuously; a direct ETF basis
   effect should disappear in seconds, not persist after 10:30.
2. Any edge must therefore be slower sector/fundamental read-through, which may
   be too weak for leveraged-ETF spreads.
3. The 95-name static large-cap universe has survivorship and historical-index
   membership bias.
4. Free Alpaca IEX bars are venue-local, not consolidated price discovery.
5. A one-issuer session is not genuinely broad, even if that issuer is large.

A historical pass would justify point-in-time constituent/weight and SIP
replication.  It would not by itself be production evidence.

## Frozen event assignment and signal

- Universe: the repository's already-frozen 95-name large-cap universe.
- Forms: 8-K and 8-K/A containing Item 2.02.
- Acceptances from 16:00:00 ET after the prior session through 09:25:00 ET map
  to the next/current cash session.
- Retain the earliest filing per symbol/session.
- Use split/dividend-adjusted Alpaca IEX 30-minute bars.
- Issuer reaction: 10:00 bar close divided by 09:30 bar open minus one.
- SPY reaction: same exact interval.
- Issuer residual: issuer reaction minus SPY reaction.
- Earnings-breadth shock: median residual across that session's filers.
- Positive: UPRO. Negative: SPXU. Exact zero: cash.
- Enter at the observed 10:31 ask and exit at the observed 15:55 bid.

There is no magnitude threshold, issuer weight, earnings-surprise field,
sentiment model, sector filter, or fitted coefficient.

## Returns-blind gates

No P&L may be opened unless all pass:

- at least 2 signals/week and 100/year;
- both directions at least 30%, with at least 25 switches/year;
- complete issuer-and-SPY signal bars for at least 95% of event sessions;
- one-issuer sessions no more than 45% of active sessions;
- first-hour actions agree at least 70% with the first-30-minute version;
- actions agree no more than 80% with SPY first-hour direction, proving the rule
  is not ordinary index momentum;
- no issuer supplies more than 10% of absolute residual contribution;
- no month supplies more than 8% of signals;
- exact primary and independent entry/exit quote coverage at least 95% and 90%.

## Frozen outcome gates if admitted

The 2021–2023 rule must have PF at least 1.10, positive P&L in every year and
both actions, positive single-issuer and multi-issuer sleeves, and ending cash
above adjusted buy-and-hold SPY.  It must remain positive with one extra cent at
each fill, a 10:36 entry, deletion of the ten best sessions, a positive
bootstrap lower bound, month-cluster permutation p below 0.05, and positive
independent-feed execution.  Its mean trade must exceed both event-day SPY
first-hour momentum and the same rule restricted to the prior premarket-only
filing window.

## Forbidden repairs

No sign inversion, residual or filing-reaction threshold, issuer/sector
deletion, market-cap or hand-chosen weights, minimum-filer filter, positive-only
filers, alternate filing window, alternate signal/entry/exit clock, regime
filter, or selection of single- versus multi-issuer sessions.  Recent years
remain locked after any miss.
