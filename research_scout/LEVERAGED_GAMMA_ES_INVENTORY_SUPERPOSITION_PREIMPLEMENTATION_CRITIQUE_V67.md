# Leveraged-Fund Gamma / ES Inventory Superposition — Preimplementation Critique v67

## Decision before implementation

Advance exactly one construction to a returns-blind audit. Do not inspect any
post-entry price unless every measurement, cadence, balance, stability,
distinctness, and execution-evidence gate in the preregistration passes.

This is not the rejected v63/v64 auction-capacity rule with a field renamed.
The economic object is a signed sum of two inventories already created or
scheduled before entry:

1. a public estimate of closing S&P exposure that daily leveraged funds must
   add or remove; and
2. inventory transferred to passive ES liquidity providers by completed
   aggressive futures trading.

Both are expressed in S&P-dollar exposure. The construction uses their
magnitudes and can disagree with either component's direction.

## Frozen hypothesis

At 15:30 ET on each full 2021–2023 session:

1. Use the prior session's official ProShares AUM for UPRO, SPXU, SSO, and
   SDS.
2. Estimate first-order leveraged-fund rebalance demand through the completed
   SPY 15:29 bar:

   `D_fund = Σ[L × (L - 1) × prior AUM] × SPY return from prior official close`.

3. From completed ES trades between 15:00:00 and 15:29:59.999, calculate:

   `D_ES = (buyer-aggressor contracts - seller-aggressor contracts)
   × current ES price × $50`.

4. Define `D_net = D_fund + D_ES`.
5. If `D_net > 0`, buy UPRO at the recorded 15:31 ask. If `D_net < 0`, buy
   SPXU. An exact zero means cash.
6. Exit at the recorded 15:59 bid. Never carry overnight.

There is no magnitude cutoff, volatility filter, weekday filter, side filter,
or fitted coefficient.

## Participant constraint and causal chain

Daily leveraged funds cannot passively retain their opening leverage after the
index moves. For a fund targeting leverage `L`, a first-order exposure
adjustment is proportional to `L(L-1) × AUM × index return`. For both positive
and inverse daily leverage, the resulting S&P demand has the same sign as the
index move. The amount grows with the actual public scale of the funds.

ES aggressor flow creates a second inventory transfer. Buyer-aggressors trade
against passive sellers, leaving the passive side short the executed futures
inventory; seller-aggressors leave the passive side long. If liquidity
providers subsequently neutralize that inventory, the unwind direction has
the aggressor-flow sign. Adding this completed inventory transfer to scheduled
leveraged-fund demand produces a parameter-free net exposure balance.

The hypothesized horizon is deliberately the closing half-hour. It does not
claim that stale ETF quotes can be arbitraged. It claims that scheduled
exposure adjustment and residual dealer inventory can affect the same closing
liquidity pool after 15:30.

## Would a high-end ETF or index-arbitrage desk take it seriously?

Yes as a falsifiable inventory model, not as a deployable rule.

A serious desk estimates leveraged-product rebalance demand, watches futures
flow, and reasons in common delta-notional units. It would recognize the
attempt to superpose scheduled gamma-like demand and recently transferred
futures inventory.

The desk would not accept the public-data implementation without the
falsification tests below. It would have fund-specific swap books, AP flows,
all issuers' AUM, counterparty identity, cross-venue futures depth, options
delta/gamma, and live closing-auction information. This research has proxies,
not those proprietary states.

## Hard internal critique

1. **Aggressor flow is not dealer inventory.** Passive ES counterparties can be
   asset managers, algorithms, spread traders, or informed principals. They
   need not unwind.
2. **Inventory may be hedged immediately.** A futures market maker can hedge in
   SPY, options, other futures, or correlated instruments before 15:30.
3. **Gross transfer can double count information.** Aggressive flow may already
   have moved price, and its sign may forecast nothing after the window.
4. **The rebalance estimate is incomplete.** It contains four ProShares funds,
   not all leveraged products, and uses a first-order formula rather than
   actual swaps, futures, creations, redemptions, or intraday hedge execution.
5. **Prior AUM is stale by design.** The one-session delay protects causality
   but misses same-day fund flows.
6. **SPY is only the reference index proxy.** Official fund objectives refer
   to the S&P 500, while SPY has distributions, tracking differences, and a
   separate close.
7. **The two terms may operate on different books.** Fund counterparties and
   passive ES liquidity providers need not share a balance sheet.
8. **The signal may collapse to one component.** If action nearly always
   equals ES-flow sign or SPY-return sign, the superposition story is not
   identified.
9. **The remaining move may be too small.** UPRO/SPXU spreads can consume a
   genuine S&P closing effect.
10. **Prior ES evidence is hostile.** The earlier large-move/aligned-flow MES
    rule was 2022-concentrated in development and failed in 2024–2025. This
    candidate must not inherit credibility from that result.
11. **SPXU remains structurally expensive.** Every year and both sleeves must
    work after observed marketable fills.
12. **Benchmark difficulty is intentional.** Positive P&L is insufficient; a
    compounded $100 account must beat dividend-adjusted SPY over 2021–2023.

## What would falsify the mechanism

The hypothesis fails if any of the following occurs:

- the combined action is almost identical to fund-only or ES-only action;
- using the first eligible 2021 AUM coefficient produces effectively the same
  action and equal or better returns;
- a one-session-shifted ES inventory term performs as well as the
  contemporaneous term;
- the combined rule's mean trade result does not exceed both component-only
  controls on identical executable dates;
- annual or sleeve results are negative;
- one extra cent per ETF fill, a five-minute delay, or deleting the ten best
  sessions removes profitability;
- clustered/bootstrap uncertainty includes a nonpositive mean;
- the compounded account does not beat adjusted SPY;
- an independent 2023 quote feed makes the overlap nonpositive.

## Relationship to consumed failures

- v63 added a closing-auction quantity to modeled fund demand but selected
  96% of sessions and agreed 96% with plain late-day momentum.
- v64 isolated opposing auction capacity but failed the frozen 2021 cadence
  gate before P&L.
- the earlier ES aligned-flow rule used a volatility threshold and MES
  continuation direction; it did not add actual leveraged-fund exposure in
  common notional units or execute the cash wrappers.

The v67 construction is allowed only because the ES term changes the proposed
direction through a magnitude comparison and because component-only controls
are binding. A sign-only opposition rule was considered and rejected before
implementation because it made AUM algebraically irrelevant.

## Anti-repair rule

If v67 fails, do not invert it, select agreement or disagreement cases, add a
net-pressure threshold, rescale either term, drop SPXU, select 2022, change the
15:00–15:30 flow window, or change entry/exit clocks. Recent years remain
locked unless every development gate passes.

