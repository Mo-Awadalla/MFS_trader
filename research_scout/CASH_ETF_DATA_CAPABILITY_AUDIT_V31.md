# Cash-ETF Data Capability Audit v31

## Decision at this checkpoint

There is no evidence that profitable intraday variation is absent. The
impossible daily wrapper oracle in v30 proves the opposite. The current
constraint is narrower:

> The available non-futures data has not produced a causal, frequent,
> feed-stable predictor whose edge survives observed marketable execution,
> winner deletion, multiple years, and the passive-SPY hurdle.

This is the first formal blocker audit, not a declaration that intraday ETF
alpha is impossible. The search remains open. Futures-derived hypotheses are
excluded at the user's request because they require a margin-enabled account.

## What v30 established about the actuator

All figures use a $100 account, observed 10:31 ask to observed 15:30 bid, and
2021–2025 unless otherwise noted.

| Actuator | Fixed-$100 P&L | Compounded ending cash | Midpoint ending cash | Mean round-trip spread drag |
|---|---:|---:|---:|---:|
| Always UPRO | +$65.20 | $146.13 | $201.03 | 2.58 bps |
| Always SPXU | -$177.93 | $12.68 | $28.67 | 6.61 bps |
| Passive SPY | — | $181.68 | — | price-only benchmark |

Interpretation:

- UPRO's midpoint exposure had enough gross drift to beat price-only SPY, but
  repeated marketable crossings and volatility drag reduced executable ending
  cash below SPY.
- SPXU suffered both negative long-run drift/decay and roughly 2.5 times UPRO's
  quoted-spread drag.
- Always-UPRO fixed-notional P&L fell from +$65.20 to -$28.81 after deleting
  its ten best sessions. Even unconditional positive equity exposure is
  heavily winner-concentrated.
- A look-ahead choice of the better wrapper each day was enormously positive.
  That is not a strategy, but it rules out a payoff-side impossibility. The
  missing object is a pre-entry predictor with adequate fidelity.

## Observable inventory

### 1. SPY one-minute OHLCV on ARCX.PILLAR and EQUS.MINI

Observed:

- minute open, high, low, close, and volume;
- regular-session and available premarket price paths;
- two independently sourced feeds over their common period;
- enough history for 2021–2025 development/holdout partitions.

Identifiable slow objects:

- fixed-clock return and range;
- approximate volume-weighted typical-price centers;
- anchor visits and state transitions;
- minute activity masks;
- feed-stable path topology.

Not identifiable:

- price-level traded-volume distribution inside a minute;
- aggressor side from OHLCV alone;
- quote queue, fill probability, or sub-minute ordering;
- opening/closing auction imbalance messages;
- consolidated exchange-by-exchange routing.

### 2. UPRO and SPXU ARCX.PILLAR/EQUS.MINI data

Observed:

- one-minute BBO snapshots usable for conservative ask-to-bid execution;
- one-minute trades/last sales, with fresh-quote matching where available;
- displayed top-of-book prices and sizes;
- two-feed signal/execution comparisons over the overlap period.

Identifiable:

- executable marketable-fill hurdles;
- coarse spread, displayed depth, event density, and signed last-sale features;
- relative +3/-3 wrapper modes that persist for minutes or hours.

Not identifiable:

- queue position and passive fill probability;
- dealer identity or inventory;
- AP versus retail flow;
- National Best Bid and Offer event history at transaction time;
- primary-market hedge trades;
- financing marks and contemporaneous fair-value inputs.

### 3. SH and the -1x/-3x inverse ladder

Observed:

- SH and SPXU top-of-book/event data sufficient for coarse same-side
  leverage-ladder comparisons.

Limitation:

- v28 found only 55.7% cross-feed direction agreement and 51.2% identical
  action for the leverage-escalation latency object. This is venue
  microstructure, not a stable market state.
- No synchronized SPY event-level BBO is present for a defensible
  underlying-versus-inverse convergence trade.

### 4. QQQ/IWM/SPY 30-minute IEX bars

Observed:

- broad, growth-heavy, and small-cap cash-index proxies.

Already tested:

- consensus, sequential relay, synthetic-index catch-up, acceleration,
  consensus formation, leadership curvature, and simplex coherence.

Limitation:

- these are IEX 30-minute bars, not synchronized full-market index baskets.
  The strongest development effects failed later years, winner deletion, or
  SPY outperformance.

### 5. Daily cross-asset and large-cap bars

Observed:

- SPY daily history from 2018-11-01 through 2026-06-26;
- EEM, EFA, DBC, GLD, IEF, TLT, and SHY daily history beginning
  2020-07-27 and extending into June 2026;
- a static collection of large-cap single-stock daily files.

Limitations:

- a daily bar completed yesterday can support a next-session regime signal,
  but cannot identify today's intraday information transfer;
- the large-cap collection is not point-in-time constituent membership and
  cannot support an unbiased historical S&P 500 breadth claim;
- a generic risk-on/risk-off composite is not a new ETF microstructure
  mechanism and would have weak intraday identification.

### 6. Sparse IEX event panel

Observed:

- 792 five-minute rows for SPY, QQQ, and IWM;
- only 24 session dates from 2023-01-11 through 2023-12-27.

The existing report found negative mean signed midpoint return and failed every
predictiveness gate. Twenty-four sessions cannot test a two-trades-per-week
strategy across 2021–2025.

The separate raw L1 feasibility capture contains AAPL on 2026-07-08 only. It
does not supply a historical SPY/UPRO/SPXU panel.

### 7. BTC spot

Observed:

- Binance BTCUSDT spot bars and taker-flow fields, without using perpetuals or
  futures.

Result:

- v26's Asia-to-Europe spot-flow baton was coherent in its own market and
  frequent, but lost $39.76 fixed-notional in 2021–2023; every year was
  negative and the SPXU sleeve lost $56.78.

The available single-venue BTC spot flow does not justify another transformed
risk-sentiment score after the direct causal mapping failed.

An independent challenge nevertheless tested one economically different
response map in v32. BTC flow-sign agreement was used only as a binary global
risk-attention state, while the SPY official cash gap supplied direction. The
returns-blind object was excellent—426 entries, 2.73 per week, balanced sides,
and 99.5% cross-feed direction agreement—but development lost $30.58. Its
one-session-shifted BTC gate made +$19.58, while the contemporaneous gate lost,
and the independent-feed overlap lost $38.89. This directly rejects causal
timing; the shifted placebo may not be promoted.

## Mechanism-family coverage

| Family | Best available test | Failure mode | May it be repaired? |
|---|---|---|---|
| Opening accepted value / ownership | Opening-Center, v1, v24, v27, v29 | later-year decay, cost, or cadence | No outcome-derived thresholds/clocks |
| Multi-anchor path topology | v31 memory reset | 0.67 entries/week despite excellent feed agreement | No clock widening or sequence relaxation |
| Wrapper price geometry / tracking | v2, v14, v19 | negative, sparse, or feed-dependent | No sign/side selection |
| Activity topology | v4–v6 | holdout failure or winner concentration | No density cutoff fitted to winners |
| Spread/depth liquidity modes | v1, v4, v17 | negative or too sparse | No long-only relabel |
| Signed ETF last-sale flow | v16, v18, v25 | concentration, negative P&L, or feed-action failure | No event threshold fit |
| Price-volume temporal geometry | v10, v29 | holdout or development failure | No center-migration rescue |
| Realized variance / paired convexity | v9 | below SPY, concentration, decay | No paired-leg reweighting |
| Cross-index information diffusion | v11–v13 | holdout/2026 decay and concentration | No selecting known bullish sleeve |
| Same-side inverse leverage ladder | v28 | venue-specific measurement | Requires better synchronized data |
| BTC spot risk baton | v26 | economically negative | No transformation search |
| BTC attention × SPY response mapping | v32 | contemporaneous gate lost to its one-session-shift placebo | No shifted-gate or UPRO-only rescue |
| Same-issuer inverse leverage-liquidity curve | v33 | clean measurement, negative every year and on both feeds | No sign inversion or spread threshold |
| Generic adaptive similarity | v7 | weak, costly, unstable | No feature/neighbor tuning |

## Candidates rejected by the desk-level smell test before implementation

### Long-only repair of a known bullish sleeve

UPRO's actuator is structurally superior to SPXU, so a new hypothesis may be
long-only from inception. It is not legitimate, however, to delete SPXU from
Breadth Consensus, center migration, v16, v29, or another tested rule after
observing that its bearish sleeve lost. That would be outcome selection, not a
new mechanism.

### Premarket downside-insurance liquidity

The story is that expensive SPXU liquidity reveals dealer demand for crash
insurance and therefore makes cash equity risk attractive. With current fields,
this is another relative/common spread-mode rule. Opening Liquidity Seesaw and
v17 already tested that observable family. A new label does not create new
information.

### Closing leveraged-fund rebalance

The sign of daily leveraged-fund rebalance demand is economically sound, but
fund AUM, shares outstanding, creations/redemptions, derivative hedge flow, and
auction imbalance data are absent. Price/volume proxies already failed Closing
Rebalance Torque, and unsigned share volume cannot identify hedge demand.

### Long UPRO plus long SPXU as an intraday straddle

To first order, +3r and -3r cancel. The pair is not an option straddle; spread,
financing, tracking, and volatility decay remain. The frozen paired-variance
test in v9 failed. Reweighting after its result would be a repair.

### Cross-venue or underlying-wrapper convergence

This can be a real institutional strategy, but its edge lives in synchronized
event time and queue economics. One-minute terminal BBOs cannot prove a stale
executable quote, queue position, or fill before the discrepancy disappears.
Backtesting it here would manufacture latency.

### Passive limit-order improvement

Replacing observed asks/bids with midpoint or favorable limit fills would make
several rejected strategies look better. The data does not observe queue
position or counterfactual fills, so this is an execution assumption rather
than alpha.

### Prior-day macro coherence composite

Daily cross-asset data can create countless plausible scores. Without intraday
timestamps or a distinct transmission event, choosing asset signs and weights
would be a broad conventional risk model with a large researcher-degrees-of-
freedom problem. It does not pass the "would a high-end ETF desk implement this
exact test?" standard.

## Exact missing data that would open genuinely new tests

Priority order:

1. **Historical intraday iNAV/NAV, shares outstanding, AUM, and
   creation/redemption basket files for UPRO/SPXU.** This identifies
   primary-market inventory and leverage-rebalance pressure.
2. **Synchronized consolidated event-level trades and quotes for SPY, UPRO,
   SPXU, and SH with exchange identifiers and quote conditions.** This enables
   defensible lead/lag and convergence work.
3. **Auction imbalance messages and official opening/closing auction prints.**
   This turns approximate bar centers into actual auction-transfer variables.
4. **Point-in-time S&P 500 membership plus timestamped constituent trades and
   quotes.** This enables unbiased breadth/internalization hypotheses.
5. **Options surface and option-volume/greeks data.** This identifies dealer
   gamma and hedging pressure without trading the options or using margin.
6. **Order-book depth or message data sufficient for queue-aware passive-fill
   simulation.**

These additions do not guarantee a profitable strategy. They make new causal
quantities observable instead of producing more transformations of the same
minute bars.

## Current conclusion

The current data supports two kinds of interesting findings:

- rare, structurally clean events such as v23 and v31 that fail the required
  frequency; and
- frequent signals that are too weak, too feed-specific, too SPXU-damaged, or
  too winner-concentrated to beat SPY at observed quotes.

The blocker is therefore **predictive identification at the required cadence**,
not imagination and not an absence of ex-post movement. One independent audit
cycle should now challenge this inventory and try to produce a genuinely
distinct non-futures mechanism. If it cannot, the same blocker must recur
before the research goal can be formally marked blocked.
