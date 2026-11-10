# Day-trading SPY challenger proposals V83–V84

Date: 2026-09-07 UTC
Status: two proposed rules; no new return evaluation or validation pass.

## Mandate

Day trading only. No overnight positions. Use already downloaded data only.
Trade long UPRO or long SPXU, at most one position and round trip per day,
with no account borrowing or short sales. Their embedded 3x exposure must be
reported explicitly. Start with the repo's $100 fractional-share research
account; do not assume a real broker permits every modeled fractional fill or
unsettled-cash reuse. Reserve settled capital in an operational simulation.

V80 and V82 were withdrawn after clarification, without testing. V81 duplicated
the earlier variance-state work and was rejected. These two new numbers preserve
that history. Novelty means different from the inspected repo rules, not globally
original research. Neither proposal is currently an immutable Experiment.

Full-period, dividend-adjusted SPY buy-and-hold is the primary hurdle, including
overnight gains. Same-clock SPY and unconditional UPRO are additional controls,
not easier replacement benchmarks. Require higher net ending wealth, at least
SPY's Sharpe and no worse drawdown to call a strategy a SPY beater. Cash earns
zero in the primary comparison. Report exposure and beta alongside performance.

## V83 — Calendar-linked fixed-allocation selling into the close

Claim: stock/bond funds restoring target weights should create directional
equity demand near month-end. Predict that demand before the session and trade
only its late-session execution window.

Existing inputs: adjusted SPY/IEF daily files in
`data/parquet/equity/yahoo_chart/`; UPRO/SPXU minute BBO under
`external_artifacts/databento_leveraged_etf/`; EQUS.MINI overlap for verification.
No Treasury-flow, CFTC, fund-holdings or auction-imbalance input is required.

Exact proposed rule:

1. Eligible days are the last three scheduled NYSE sessions of each month.
   Use a calendar known before trading, not the last three available rows.
2. At the preceding close, calculate SPY and IEF total returns Rs and Rb from
   the preceding month-end. Estimate a drifted 60/40 equity weight:
   `w = 0.6*(1+Rs)/(0.6*(1+Rs)+0.4*(1+Rb))`.
3. If w > 0.6, buy SPXU at the observed 15:01 ask. If w < 0.6, buy UPRO.
   Equality or missing inputs means cash. No magnitude filter.
4. Sell at the observed 15:55 bid that day. Exclude shortened sessions using
   the pre-known schedule. No overnight, stop optimization or entry search.

Why distinct: V56–V58 were daily macro price-direction proxies. Here the
testable claim is a calendar interaction with target-weight restoration, with
the predicted trading direction opposite the excess stock weight. V63/V64
concern leveraged ETF reset demand, not stock/bond fixed-allocation mandates.
The sign is algebraically the sign of stock-minus-bond relative return; the
60/40 equation alone adds no information and is not claimed to measure actual
fund dollars. Do not reuse rejected TGA/RRP month-end subsets.

Critical controls: the same rule on the middle three scheduled sessions of each
month; SPY-only month-to-date reversal; unconditional UPRO in the same window.
Require positive incremental net expectancy versus those controls, and demonstrate
that the predicted calendar interaction survives month-cluster uncertainty.

Main weakness: only about 36 possible days a year. Beating full-time SPY with
this limited exposure is a demanding hurdle. It is an event strategy, not a
daily-frequency promise. Actual institutional schedules and weights are unknown.
Do not widen the window after a sparse or negative result.

Source motivation: https://www.nber.org/papers/w33554 and
https://www.nber.org/papers/w28028 support portfolio-rebalancing price pressure;
the exact three-day/15:01 rule is an untested implementation hypothesis.

## V84 — Persistent asymmetry in displayed quote replenishment

Claim: repeated failure to restore displayed liquidity on one side of SPY's
opening book may identify persistent liquidity stress. A slow aggregate of these
episodes could predict subsequent direction after a one-minute execution delay.

Existing inputs: SPY EQUS.MINI MBP-1 in
`external_artifacts/databento_cash_etf_mbp1_open_v55/`, whose 806 downloaded
sessions contain full top-of-book updates in the 09:20–09:40 window. Use existing
UPRO/SPXU minute BBO for 09:40 entry and 10:00 exit. No new quote purchase.
Use only completed, valid sessions; no assumption that the missing 30 sessions
can be filled for free.

Exact proposed feature:

1. Observe two blocks, 09:30–09:34 and 09:35–09:39 ET. Retain the minute between
   blocks and the minute before entry for episode completion and processing.
2. For each SPY bid and ask independently, start an episode when displayed size
   drops by at least 50% between successive records at the SAME best price.
   Save the pre-drop price and size. Require both sizes to be positive.
3. Recovery succeeds if displayed size at that unchanged price reaches the saved
   size within five seconds. A price change, invalid quote or five-second timeout
   before recovery is a failure. Finalize episodes using only records available
   by 09:35 and 09:40 respectively. Do not open a second same-side episode while
   one is active. Use receive-time availability and source sequence ordering;
   fail the audit if ordering cannot be established.
4. In each block compute bid and ask recovery fractions, including failures in
   the denominator. Require at least 20 completed episodes per side per block.
5. If bid recovery exceeds ask recovery in BOTH blocks, buy UPRO at the 09:40
   observed ask. If ask recovery exceeds bid recovery in BOTH, buy SPXU.
   Otherwise cash. The last episode begins strictly before 09:39, leaving at
   least 55 seconds after its maximum completion time before the entry.
6. Exit at the observed 10:00 bid. No passive orders, queue-fill assumption,
   intraday averaging down or sign reversal after results.

Why distinct: the feature is recovery after individual same-price displayed
depletions in a full quote-update stream. It is not static depth imbalance,
trade-event quote lag, auction quantity, realized semivariance, or the MES
static-size shadow rule. Search the earlier liquidity-state implementations
before freezing; if the same episode statistic already exists, reject as duplicate.

Semantic limitation: aggregate MBP-1 does not tell us whether a size reduction
was a cancellation, trade, routing change or participant action. EQUS.MINI is
not official SIP NBBO. Call this observed displayed replenishment, never dealer
inventory, hidden orders or spoofing. Price changes are censored as failures,
so apparent predictiveness may simply reproduce price momentum.

Blind controls: opening SPY return direction, static time-weighted depth
imbalance, event count, and fraction of episodes ending in price changes.
Require at least 70% action agreement when calculated from alternating event
blocks, and no more than 85% agreement with the simple price-direction control.
Also show the signal with price-change episodes reported separately; do not
select the profitable subset. Neighboring block-boundary shifts of +/-30 seconds
are stability diagnostics, never alternative rules to promote.

Main weakness: queue replenishment may have only millisecond value. The fixed
one-minute delay and 20-minute holding period are deliberate economic tests;
failure must not be repaired into an HFT strategy. The 50%/five-second/20-event
constants are proposed engineering choices with no claimed optimality.

Priority: strongest day-trading novelty candidate, conditional on the blind
semantic and duplicate audit. V83 is cheaper and economically clearer but sparse.

## Required sequence before a backtest

1. Verify file hashes, schemas, timestamp semantics, quote coverage and local
   calendar availability. No new market data requests. Save a JSON specification
   before calculating candidate signals or returns. Record every diagnostic.
2. V83 development: 2021–2023. V84 development: available March–December 2023
   MBP-1 sessions. A short development period is a limitation, not an invitation
   to use later years to tune. Confirmation: 2024–2025; 2026 is a gappy extension.
3. Require >=95% exact entry/exit quote coverage among feature-eligible sessions,
   no silent forward filling, at least 30 executable V83 events or 60 V84 events
   in development, and at least 20% observations per direction. Stop on failure.
4. Cross actual observed spreads. Add frozen repo regulatory fees and 1 bp per
   side slippage; stress one extra cent per share per fill and five-minute delay.
   Never treat quotes as guaranteed fractional market fills. Ensure exit evidence
   proves every simulated position was closed the same day.
5. Report annual and compounded performance, drawdown, Sharpe, trade counts,
   beta/exposure, cost decomposition and identical-date SPY total returns.
   Require positive development P&L in each observed year and both directions,
   PF >1.10, positive P&L after removing the five best days, positive stressed P&L,
   and the full-period SPY hurdle before opening confirmation results.
6. Use paired month-cluster bootstrap for V83 and five-session blocks for V84
   (10,000 draws, seed 83). Require positive 95% lower bound on net excess daily
   return; adjust inference across both tested proposals and disclose the much
   larger historical research multiplicity. No historical partition is pristine.
7. No sign inversions, clock selection, weaker gates, favorable-year deletion,
   new constituent symbols or combination of failures after P&L. Any survivor
   still requires the repo's full validation and prospective paper evidence.

Deliverable boundary: these are concrete new hypotheses and test designs.
Neither has been backtested or shown to beat SPY. No money was spent.
