# UPRO/SPXU Desk-Grade Hypothesis Screen v15

This screen was completed before any v15 afternoon return or strategy P&L was
calculated.

## Admission standard

A candidate may reach a backtest only when:

1. the proposed causal quantity is directly observed or defensibly
   instrumented;
2. the signal is available before the executable entry;
3. the trade implementation matches the economic mechanism;
4. a returns-blind audit demonstrates at least two opportunities per week;
5. available feeds measure the feature consistently; and
6. the idea is materially distinct from a previously rejected family.

The relevant institutional question is not merely whether an ETF desk would
find the story interesting. It is whether the desk could defend implementing
this exact experiment with these exact data.

## Candidate 1: Early Closing-Rebalance Footprint

### Hypothesis

Both +3 and -3 daily-reset funds must hedge in the same underlying direction
after an index move. A joint late-day activity surge might reveal mechanical
rebalance demand early enough to trade the remaining close.

### Rejection

The available UPRO/SPXU share volume does not observe fund derivative trades,
AUM, creations/redemptions, or hedge direction. The repository's stronger ES
aggressor-flow implementation of aligned closing pressure already failed its
2024-2025 holdout. Replacing observed futures aggressor flow with unsigned ETF
share volume would repeat a failed mechanism using a weaker proxy.

No implementation.

## Candidate 2: Listing-Venue Participation Tilt

### Hypothesis

For each leveraged ETF, measure first-hour NYSE Arca volume as a fraction of
consolidated volume. A higher listing-venue share in UPRO than SPXU might
identify professional/AP inventory transfer toward bullish exposure, and the
reverse might identify bearish transfer.

### Why a desk might initially listen

ETF desks care about venue-conditioned toxicity, listing-exchange participation,
and whether institutional flow differs from fragmented retail routing. Relative
venue share is conceptually different from raw ETF volume or price momentum.

### Returns-blind audit

Artifact:
`research_scout/upro_spxu_listing_venue_returns_blind_audit_v15.json`

- Eligible sessions: 666.
- Nonzero signals: 666, or 4.62 per calendar week.
- Raw-volume and dollar-volume definitions agreed on direction 99.85% of the
  time.
- UPRO direction: 612 sessions.
- SPXU direction: 54 sessions.
- Median supposed Arca/consolidated volume ratio:
  - UPRO: 2.84.
  - SPXU: 1.32.
- Fraction of sessions in which Arca volume was contained by the proposed
  consolidated denominator: 0%.

### Rejection

EQUS.MINI OHLCV is not a full consolidated-volume denominator for this purpose.
A venue share above one is economically impossible. The extreme 612/54
direction split is therefore primarily a dataset/instrument-liquidity bias, not
evidence of directional professional flow.

No afternoon returns were read and no P&L backtest was run.

## Candidate 3: Primary/Secondary-Market Convexity Gap

### Hypothesis

Compare UPRO/SPXU secondary-market prices with contemporaneous NAV-implied
leveraged values to identify AP inventory that should transmit into the
underlying.

### Rejection

Historical intraday NAV/iNAV, shares outstanding, creations/redemptions, basket
files, and financing marks are absent. Trade-price tracking residuals cannot
identify a primary-market imbalance. The prior leverage-spectrum result showed
that such residuals are highly venue-dependent.

No implementation.

## Candidate 4: Futures-Cash Basis Relay

### Hypothesis

Use an ES-versus-SPY first-hour basis residual as a leading signal for
UPRO/SPXU.

### Rejection

An executable ES/SPY basis is an event-time relative-value object. One-minute
bars cannot distinguish a genuine basis from asynchronous prints, and a
one-legged leveraged ETF position does not match the naturally hedged trade.
The mechanism should decay much faster than the proposed holding period.

No implementation.

## Candidate 5: Constituent-Breadth Internalization Gap

### Hypothesis

Use prior-day disagreement between equal-weight constituent breadth and
cap-weight SPY to predict next-day index catch-up.

### Rejection

The local constituent universe is not point-in-time membership data and creates
survivorship/selection bias. Daily bars also cannot establish that every
constituent opening print was available before a proposed early entry. A
high-end index desk would require historical membership, corporate-action, and
timestamped constituent data.

No implementation.

## Decision

No v15 hypothesis qualifies for a P&L backtest. This is the intended outcome of
the harder screen, not a blocked search.

The most valuable next data would be:

- full consolidated trades with exchange identifiers for UPRO and SPXU;
- historical intraday NAV/iNAV, AUM, shares outstanding, and
  creation/redemption files;
- aggressor-side UPRO/SPXU and ES flow on synchronized timestamps; or
- point-in-time constituent membership with timestamped opening-auction data.

Without at least one of those, the remaining sophisticated ETF stories are not
identified strongly enough to justify another historical strategy test.

