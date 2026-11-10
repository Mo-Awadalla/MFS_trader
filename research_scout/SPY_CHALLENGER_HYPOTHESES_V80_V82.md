# SPY challenger hypotheses V80–V82

Date: 2026-09-07 UTC
Status: proposed specifications; no new strategy returns calculated.

**Superseded by the user's day-trading-only clarification.** V80 and V82 below
are withdrawn from the active shortlist because they hold overnight. Retained
only as proposal history. Active replacements are in
`DAYTRADE_SPY_CHALLENGER_HYPOTHESES_V83_V84.md`. V81 remains rejected as a duplicate.

## Scope

Use existing local market data only. No paid calls or new market-data acquisition.
The current request permits algorithmic strategies broadly; these proposals assume
overnight holdings are allowed. They do not inherit the earlier twice-weekly,
flat-by-close mandate. They remain long-only, unlevered, and fully cash funded.
Novelty means distinct from the repository constructions inspected, not an
assertion that nobody has published the idea. This is a proposal document, not
an immutable Experiment or a validation pass.

The chronology continues after V79. V81 is counted despite rejection. The old
cash-ETF registry and its frozen failures are preserved.

## Common decision standard

Primary comparator: SPY buy-and-hold total return with reinvested distributions,
identical start/end timestamps and initial capital. Primary success means higher
net terminal wealth/CAGR AND at least SPY's Sharpe AND no worse maximum drawdown.
A Sharpe-only improvement is a defensive result, not a claim to beat SPY.

Before any P&L run, freeze exact input hashes, split dates, adjustment handling,
execution semantics, transaction costs, missing-data rules and code revision in
a machine-readable preregistration. Signals must precede fills. Verify adjusted
OHLC consistency; never add dividends again to a total-return-adjusted series.
No borrowed capital, inverse ETFs, optimized symbol selection or hindsight blends.

Proposed historical partitions: 2010–2017 development, 2018–2020 sequential
confirmation, 2021–2025 later confirmation; 2009 is warmup. Require metadata-only
coverage checks first. If coverage fails, stop rather than silently move dates.
These dates are already exposed at the research-program level. Confirmation
is not an untouched holdout; prospective evidence is still required.

Daily-bar economics: 5 bps one-way on traded notional, stressed to 10 bps;
charge initial purchases and final liquidation consistently for all portfolios.
These are research assumptions, not observed spreads. Assess small-account
fractional fills and settlement separately before operational promotion.

Report all annual returns and rolling three-year SPY-relative returns. Require
positive SPY-relative performance in both confirmation partitions, positive
excess return under cost stress, and a positive 95% lower confidence bound for
mean daily excess return using paired 20-session block bootstrap (10,000 draws,
seed 80). Apply Holm correction across the two tested candidates. Remove the
five best active months as an additional concentration stress. Controls are
diagnostics, never substitutes to promote after a candidate fails.

## V80 — Anticipate fixed-allocation month-end stock selling

**Hypothesis:** funds restoring stock/bond target weights create predictable
equity selling after stocks outperform bonds. Briefly avoiding that selling
while otherwise retaining SPY may improve SPY's compounded return.

Inputs already present:

- `data/parquet/equity/yahoo_chart/SPY_1d.parquet`
- `data/parquet/equity/yahoo_chart/IEF_1d.parquet`
- `data/parquet/equity/yahoo_chart/SHY_1d.parquet`

Theoretical proxy: initialize a hypothetical 60/40 SPY/IEF allocation at the
previous month-end. At the close five scheduled NYSE sessions before the current
month-end, calculate month-to-date total returns Rs and Rb and drifted equity
weight:

`w = 0.6*(1+Rs) / (0.6*(1+Rs) + 0.4*(1+Rb))`

If w > 0.6, hold SHY instead of SPY from the next session's open through the first
session of the next month's open. Otherwise keep SPY. Return to SPY at that next
month's first open. No threshold sweep, short-selling or bullish leverage.
Use an exchange calendar known in advance; do not infer month-end from the last
available price. At most one round-trip switch per month.

Economic justification: scheduled portfolio weight restoration, not a generic
stock/bond macro-direction vote. The 60/40 equation is only a demand proxy; it
does not observe actual funds, their size or their execution dates. Its sign is
equivalent to stock-minus-bond relative return, which must be acknowledged.

Controls: unconditional final-four-session SPY avoidance; identical avoidance
in the middle of the month; stock-only month-to-date sign. The candidate must
beat the unconditional calendar control after costs and show a positive paired
return difference between predicted-selling and other month-end windows.

Novelty screen: V56–V58 used daily joint price directions/duration impulses to
trade intraday leveraged ETFs. This proposal specifies calendar-linked portfolio
restoration and temporary reduction of a permanent SPY position. It is not a
new sign or clock chosen from their failed returns. Do not use TGA/RRP/settlement
data or select their previously rejected month-end subsets.

Main objection: rebalancing can be anticipated or occur throughout the month;
missed SPY rallies and switching costs can overwhelm the effect. Monthly cadence
also limits attainable excess CAGR. Reject if the calendar interaction adds no
incremental value; do not invert into a post-month-end reversal strategy.

Source motivation (the exact calendar and trading rule are our hypothesis):
https://www.nber.org/papers/w33554
https://www.nber.org/papers/w28028

Priority: first. Smallest implementation and clearest falsifiable mechanism.

## V81 — Downside-variance crash avoidance: rejected during novelty review

An initial idea was to reduce equity exposure after downside-dominated realized
variance. Reading `upro_spxu_variance_state_prereg_v9.json` showed that V9 already
tested downside-variance handoff and quiet-variance carry. Changing the traded
ETF, hold length or defensive label would not supply sufficiently new information.
No implementation, return calculation or suggested promotion.

## V82 — Transaction-cost-aware online mixture of fixed ETF allocations

**Hypothesis:** adaptively allocating across a fixed family of diversified
portfolios can benefit from changing asset leadership and repeated rebalancing,
enough to exceed SPY after costs without predicting tomorrow's direction.

Inputs: existing adjusted daily SPY, QQQ, IWM, IEF, GLD, DBC and SHY files under
`data/parquet/equity/yahoo_chart/`. All seven remain in the universe.

Define every nonnegative allocation in 25-percentage-point increments across
these seven assets summing to 100%: 210 fixed allocations, including pure SPY.
Each virtual portfolio rebalances on the first NYSE session open of each month.
Initialize all virtual wealths equally. Track their causal, cost-adjusted wealth
through the prior session's close, including drift between rebalances. At each
monthly open, the actual portfolio targets the wealth-weighted average of the
210 fixed allocations, using only those prior-close wealths. No winner selection,
lookback tuning, temperature, reset, leverage or parameter search. Actual account
costs use its own net trades; virtual account costs penalize expensive experts.
Report virtual and actual accounting separately to avoid double-charging costs.

This finite monthly algorithm is inspired by universal portfolios. It does not
inherit a guarantee to beat SPY over a finite sample, especially after transaction
costs. Including pure SPY as one expert does not guarantee the mixture beats it.
The grid is part of one fixed algorithm, not 210 candidates from which to report
the best historical performer. Any later best-expert selection is another trial.

Controls: equal-weight seven-asset monthly portfolio, a buy-and-hold equal initial
allocation, SPY, and the existing validated ETF momentum strategy on identical
dates. Require higher net CAGR than equal-weight monthly rebalancing as well as
the common SPY gates. Report QQQ exposure, average equity exposure and beta so a
technology tilt cannot be mistaken for timing alpha.

Novelty screen: existing momentum ranks 12-month returns and sizes by volatility;
this algorithm aggregates fixed portfolio wealth paths without sign forecasts or
top-N selection. V9's paired UPRO/SPXU intraday rebalance uses inverse daily-reset
wrappers and a different mechanism. This proposal uses unlevered asset classes,
monthly allocations, and no inverse positions. Broad price-data exposure remains.

Main objection: learning can be too slow, diversification can lag SPY throughout
a long bull market, and a finite grid may dilute winning assets. A nice theorem
or lower drawdown is insufficient. Reject if after-cost SPY outperformance fails.

Source motivation:
https://statistics.stanford.edu/technical-reports/universal-portfolios
https://isl.stanford.edu/~cover/portfolio-theory.html

Priority: second. Algorithmically distinct; weaker specific economic edge than
V80 and a serious risk of simply diluting SPY's return.

## Work completed and boundary

Inspected prior registry, V9 and V56 specifications, cached file inventory and
primary research sources. Proposed two executable research designs and rejected
one duplicate. No market data was purchased, no strategy backtest was run, no
historical winner was selected, and no claim of global originality is made.
