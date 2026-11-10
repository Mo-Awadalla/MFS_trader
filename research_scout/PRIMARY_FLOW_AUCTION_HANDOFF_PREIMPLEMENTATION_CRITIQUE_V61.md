# Primary-Flow / Opening-Auction Handoff — Preimplementation Critique v61

## Decision

Permit one frozen 2021-2023 development test. Keep 2024-2025 locked unless
every development gate passes without repair.

This candidate combines a newly admitted free official source with existing
timestamped exchange data:

1. split-adjusted UPRO and SPXU shares-outstanding changes estimate prior-day
   primary-market creations and redemptions;
2. the next session's last eligible SPY Arca opening-auction message strictly
   before 09:29 ET measures broad secondary-market deadline pressure; and
3. a trade occurs only when both layers imply the same S&P direction.

No return, P&L, winning threshold, or 2024-2025 outcome was inspected while
constructing the rule.

## Hypothesis

Net creations and redemptions in leveraged S&P 500 ETFs are not ordinary
price transforms. They record a completed primary-market transfer between the
fund and authorized participants. Some flows are transient arbitrage, but
some represent customer demand that persists beyond the closing hedge cycle.

The next SPY opening auction is a separate, deadline-bound measure of broad
cash-market demand. If lagged leveraged-fund exposure flow and the fresh
opening-auction side agree, the common direction is more likely to represent
persistent risk transfer than either observation alone. The strategy enters
the corresponding leveraged ETF after the uncross and exits during the first
cash-session hour.

The rule is:

- calculate source-day dollar flow as `NAV × split-adjusted change in shares`;
- define directional flow as `UPRO flow − SPXU flow`;
- delay that state by one U.S. trading session;
- select the latest eligible SPY `auction_type=M` message strictly before
  09:29 ET;
- buy UPRO when directional flow is positive and auction side is `B`;
- buy SPXU when directional flow is negative and auction side is `A`;
- otherwise hold cash;
- apply no flow, auction-quantity, return, volatility, or percentile threshold.

## Why a sophisticated firm could take it seriously

- It joins primary-market inventory transfer with a separate secondary-market
  deadline event.
- Both inputs have economic identities and fixed causal timestamps.
- The official share series has 100% 2021-2023 coverage after explicit split
  handling.
- The cross-state is frequent and balanced: 373 development signals,
  2.477/week, with 166 UPRO and 207 SPXU actions.
- It is materially distinct from flow-only, auction-only, and failed v34
  actions.
- The repo already contains observed ask/bid execution and an independent
  consolidated overlap, so the effect cannot hide at midpoint.

A professional ETF or index-arbitrage desk might fund this as a bounded
research test. It would also have intraday creation files, AP identifiers,
index futures, iNAV, and dealer inventory that this public-data implementation
does not.

## Adversarial critique

### The primary-market interpretation may be wrong

Shares outstanding identify net creations/redemptions, not end-investor
direction. An AP can create shares to close a short, satisfy market-making
inventory, or exploit a basis. The fund's exposure adjustment may be completed
on the source day, leaving no next-day obligation.

The historical ProShares file is a mutable current download rather than a
point-in-time archive. A one-session delay prevents same-day lookahead but
cannot prove that every historical value was never revised.

### The two markets are mismatched in scale

SPY's opening auction reflects the entire index ecosystem. UPRO/SPXU flows are
small relative to SPY, index futures, options hedging, and constituent
auctions. Agreement may merely label broad risk-on/risk-off days rather than a
causal handoff from these funds.

### The auction may clear rather than transmit pressure

The opening auction exists to absorb imbalance. A side visible before 09:29
can be fully resolved at the uncross or can attract offsetting liquidity.
Failed v34 is direct evidence that auction-side continuation alone was
unprofitable.

### SPXU remains structurally difficult

The bearish sleeve has wider spreads and repeatedly lost in earlier work. A
balanced classifier is not enough; the SPXU sleeve must be independently
positive after observed execution. Sleeve deletion after seeing results is
prohibited.

### Agreement can be a generic confirmation filter

Two noisy signs agree about half the time by construction. The hypothesis
earns identification only if it beats:

- primary flow alone;
- auction side alone;
- the failed v34 buy-only rule;
- a one-additional-session-lagged flow placebo; and
- prior-session SPY direction using the same execution window.

### The public data omit important state

There is no AP identity, creation-order timestamp, basket composition,
intraday iNAV, futures hedge, swap-counterparty hedge, or complete national
auction view. The result would remain a public-data proxy even if it passes.

### Multiple testing remains cumulative

This is v61 in a heavily outcome-exposed program. Exact preregistration blocks
local repair but cannot manufacture a pristine historical holdout. A survivor
would still require untouched later years and prospective paper evidence.

## Frozen execution and evaluation

- Primary development: 2021-01-04 through 2023-12-29 only.
- Entry: observed ask at 09:31 ET.
- Exit: observed bid at 10:30 ET.
- Account: $100 initial cash, fractional shares, one long ETF position or
  cash, no overnight position.
- Primary feed: existing ARCX.PILLAR one-minute BBO.
- Independent overlap: existing EQUS.MINI one-minute BBO, only on dates where
  both feeds and the frozen signal exist.
- Degraded source sessions remain excluded according to the existing
  condition files.

The 09:31-10:30 window is inherited from failed v34. It is not selected from a
new horizon search.

## Required development gates

All must pass:

1. at least two executed trades per week;
2. profit factor strictly above 1.10;
3. positive fixed-notional P&L in 2021, 2022, and 2023 separately;
4. both UPRO and SPXU sleeves positive;
5. compounded ending cash above adjusted buy-and-hold SPY;
6. positive after one extra cent per share at entry and exit;
7. positive after a five-minute delayed entry;
8. positive after deleting the ten best sessions;
9. session-block bootstrap 95% lower mean return above zero;
10. positive independent-feed overlap;
11. primary mean trade return above every frozen component/placebo control.

Failure locks 2024-2025. There will be no sign flip, threshold, alternate
clock, exit search, sleeve deletion, volatility gate, magnitude gate, or
favorable subset rescue.

