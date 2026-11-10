# Ten day-trading hypotheses using the existing data

Date: 2026-09-07 UTC. Original proposal and input screen retained below.

**Backtest update:** V83–V86 were tested and all failed the frozen development
SPY hurdle. V87 failed its pre-return side-balance/distinctness screen. V88–V92
remain data-blocked. See
`daytrade_batch_v83_v92/artifacts/FINAL_REPORT.md` and the frozen specification,
input hashes, trade ledgers and verification records in that directory.
No failed rule was tuned and no later confirmation was evaluated.
This expands V83/V84 to ten total candidates, with eight additional mechanisms.
Numbers count attempts, including blocked ideas. No data purchase is authorized
or needed for this screen. No subagents were used.

## Common objective and admission rules

Every proposed position must close the same day. The main objective is higher
net compounded wealth than full-period dividend-adjusted SPY buy-and-hold,
including SPY's overnight returns, on matched dates and initial capital. Also
require at least SPY's Sharpe and no worse drawdown. Report a weaker result as
such, never rename a failed return challenger a success because it is defensive.

UPRO/SPXU rules buy the selected ETF with cash, not borrowed money or short sales.
These funds embed leverage; compare against unconditional UPRO at the identical
clock, SPY, and a risk-matched benchmark. A $100 fractional-share simulation is
not proof of real fractional order execution or historical settled-cash capacity.
BTC and futures ideas explicitly identify their different implementation needs.

The sources have already been exposed in earlier research. No later historical
period is called pristine. No threshold, clock, sign, universe or profitable
subset is selected using a proposed rule's P&L. The following constants are
proposed design choices, not empirically optimized facts. Freeze a separate
machine-readable specification and hashes before signal/outcome evaluation.

For ETF execution, cross observed asks/bids, add frozen repo regulatory fees
and 1 bp per fill; stress an additional cent per share per fill and five-minute
entry delay. Do not use midpoint/passive fills. Use exact-clock valid quotes,
exclude scheduled early closes when the exit is unavailable, and require >=95%
execution coverage of eligible signals. Audit excluded and missing days without
using their outcomes to decide eligibility. Prove daily liquidation.

Use 2021–2023 development where available, 2024–2025 gated confirmation, and
2026 only as a disclosed extension. V84 starts March 2023 and needs especially
cautious interpretation. Treasury/lending local sources end in 2023: divide
2021–2022 development and 2023 confirmation before evaluating returns; do not
promise a 2024–2025 test from nonexistent inputs. Sparse mechanisms use event-
cluster inference and can fail on sample size without any P&L being opened.

## 1. V83 — Month-end fixed-allocation demand

**Driver:** stock/bond portfolios restoring target weights.
**Local data:** Yahoo SPY/IEF daily bars; UPRO/SPXU minute quotes.
**Rule:** on the last three scheduled NYSE sessions of each month, use prior-close
month-to-date total returns to calculate drift from a 60/40 SPY/IEF allocation.
Stock overweight -> buy SPXU; underweight -> buy UPRO. Enter 15:01, exit 15:55.
Otherwise cash. The drift sign equals SPY-minus-IEF relative return; the formula
does not observe actual institutional assets or trading schedules.
**Novelty:** scheduled target-weight restoration rather than V56–V58 daily
macro votes or V63/V64 leveraged-fund resets.
**Falsifier:** the same rule mid-month performs as well, or costs eliminate the
month-end interaction. Roughly 36 opportunities/year makes beating SPY difficult.
**Status:** inputs present; calendar/quote alignment audit next.
Source motivation: https://www.nber.org/papers/w33554 . The exact rule is ours.

## 2. V84 — Opening displayed-liquidity replenishment

**Driver:** persistent asymmetry in recovery after visible liquidity depletion.
**Local data:** 806 downloaded SPY MBP-1 opening sessions; UPRO/SPXU minute quotes.
**Rule:** use the exact V84 specification in
`DAYTRADE_SPY_CHALLENGER_HYPOTHESES_V83_V84.md`: same-price >=50% size drops,
five-second recovery, two opening blocks, >=20 episodes per side per block.
Higher bid recovery in both -> UPRO; higher ask recovery -> SPXU. 09:40–10:00.
**Novelty:** full quote-path recovery, not static size or trade-conditioned BBO.
**Falsifier:** no incremental information beyond SPY price direction and static
depth, unstable subsamples, or the edge vanishes with delayed execution.
**Status:** inputs present; event semantics and duplication audit required.
Size changes do not identify cancellations, hidden liquidity or dealer identity.

## 3. V85 — Earnings information travelling through a stock network

**Driver:** information from a reporting firm reaches economically related
non-reporters at different speeds.
**Local data:** SEC Item 2.02 timestamps, daily stock histories, and 134-symbol
09:30/10:00 half-hour bars already cached under `alpaca_iex_liquidity_relay_v77`.
**Rule:** before each month, connect each issuer to its five most positively
correlated peers using 60 prior daily stock-minus-SPY returns (>=50 observations;
no positive peers -> no event). Exclude peers with their own known earnings filing
since the preceding close. For premarket/previous-after-close earnings issuers,
compare the issuer's first-half-hour residual return with peers' completed
first-hour residual return. Define an issuer gap only when the issuer's residual
and issuer-minus-peer residual gap have the same sign. Median nonzero gap across
issuers selects UPRO/SPXU at 10:31; exit 15:30. No gap -> cash.
**Novelty:** lag along a precomputed cross-name network, not V73's median issuer
reaction or V75–V77 generic breadth. This is related to the same broad information
family; count that dependence and reject if it merely reconstructs V73 actions.
**Falsifier:** a degree-preserving shuffled graph works as well; SPY momentum or
the issuer-only control explains the signal. Require <80% action agreement with
V73 and a real gap between connected and shuffled-peer measurements before P&L.
**Status:** required feature fields present. Execution uses ETF quotes because
the broad stock cache has no afternoon stock bars. Survivorship is a limitation;
do not describe the static universe as historical S&P 500 membership.

## 4. V86 — Bitcoin spot buying after negative funding settlement

**Driver:** traders collecting negative funding in long-perpetual/short-spot
positions may unwind the spot hedge after payment, creating spot buying.
**Local data:** Binance settled funding and spot/perpetual 30-minute bars.
**Rule:** on US equity trading days, if the actual 16:00 UTC funding observation
is negative, buy cash BTC spot at 16:30 UTC and sell at 18:00 UTC that day.
Require an actual archived 16:00 payment record and established public availability
by entry. No assumed constant funding schedule; no trade if records are absent.
No perpetual position and no funding credited to the spot strategy.
**Novelty:** event-time spot hedge removal, not seven-day funding carry, basis
convergence, OI/price risk transfer to SPY or crowded-long shorting.
**Falsifier:** identical nonpayment-clock and next-day controls have the same
effect, or the movement is too small after spot taker fees. Observe mark/spot
spread changes for attribution only, not a post-result entry filter.
**Status:** feature/bar inputs present, but no spot BBO. This supports a conservative
economic screen, not execution validation: 10 bps fee plus 5 bps slippage per
side (30 bps round trip), stressed to 50 bps round trip. Compare unconditional
same-clock BTC as well as SPY. US venue/account availability is not assumed.
Source semantics: https://www.binance.com/en-AE/support/faq/detail/360033525031 .

## 5. V87 — Crowded futures trader groups hit by an adverse opening move

**Driver:** unusually large average positions per leveraged trader may amplify
de-risking when the cash open moves against that side.
**Local data:** CFTC ES leveraged-money positions AND trader counts; ES minute
bars; UPRO/SPXU quotes. The count fields are present in the downloaded archives.
**Rule:** use only the previous week's report, available by the following Tuesday,
with holiday/delay exclusions unless actual publication is established. Compute
long contracts per reported long trader minus short contracts per reported short
trader; suppress missing/zero/suppressed counts. If this is positive and ES fell
from 09:30 to the completed 10:00 boundary, buy SPXU at 10:01. If negative and ES
rose, buy UPRO. Exit 15:30; otherwise cash.
**Novelty:** position size per participant and adverse-shock response, not V65's
weekly asset-manager-minus-leveraged-fund position changes. This is related CFTC
research, not independent evidence or proof of actual stop orders.
**Falsifier:** count normalization does not change actions relative to ordinary
net positions; the signal is just ES momentum. Require <80% agreement with a
net-position-only control and use report-week clustering, not independent trades.
**Status:** fields present; publication and concentration interpretation conditional.

## 6. V88 — Treasury auction marginal-bid dispersion

**Driver:** unusually wide differences between marginal and typical accepted
bids may reveal uncertainty in demand for duration, with delayed equity effects.
**Local data:** 1,760 Treasury auction rows, including 382 with median yield;
`high_yield`, `avg_med_yield`, `low_yield`, term and bid-closing clock; ETF quotes.
**Rule:** nominal fixed-coupon notes/bonds only (different bill/FRN/TIPS rate
units are not mixed). Calculate high-minus-median yield, compare with the preceding
same-original-term auction. Widening -> SPXU; narrowing -> UPRO. With results
demonstrably public by 13:10, enter 13:16 and exit 15:30. Multiple eligible same-day
auctions use the median difference. Equality -> cash.
**Novelty:** auction bid-price distribution, not V66 dealer award weights or
V71 settlement cash; do not call this a when-issued auction tail.
**Falsifier:** the dispersion is mostly strategic bidding rather than uncertainty,
or high-minus-median adds nothing over bid-to-cover and prior rate movement.
**Status:** currently blocked for a same-day causal test: local result records
contain a bid-closing clock but no verified historical publication timestamp.
A fixed delay does not prove availability. No P&L until existing local evidence
establishes that distinction. No next-day substitute to evade this blocker.
Source semantics: https://www.treasurydirect.gov/auctions/ .

## 7. V89 — The price of borrowing scarce Treasury collateral

**Driver:** a broad increase in the fee paid to borrow specific securities may
measure collateral stress better than the amount requested.
**Local data:** NY Fed securities-lending CSVs, 2021–2023, with CUSIP, Weighted
Average Rate, accepted par, available supply, closing time and Last Updated.
**Rule:** among CUSIPs with positive accepted loans today and yesterday, take the
equal-CUSIP median change in weighted-average lending fee. Increase -> SPXU;
decrease -> UPRO; tie -> cash. Enter 12:31, exit 15:30, conditional on causal
availability. No Treasury-settlement-day selection or rescaling by quantity.
**Novelty:** actual collateral borrowing price rather than V72's matched issue-date
quantity/capacity residual. Price and quantity must lead to materially different
actions; a fee floor may make the price signal unusably sparse.
**Falsifier:** fees sit at their floor, fee changes lack breadth, or the signal
collapses to loan-volume changes. Thresholds must not be added to revive it.
**Status:** rate fields present; conditional on publication/revision audit.
The CSV's Release Time may mean the operation announcement, not results.
Last Updated is not automatically a first-publication timestamp. No same-day
signal is admitted merely because the auction had closed.

## 8. V90 — Futures roll pressure across two maturities

**Driver:** scheduled movement from an expiring futures contract to its successor
may temporarily dislocate the calendar spread, which then converges intraday.
**Local data considered:** pysystemtrade contract identifiers/prices, raw ES
trades, targeted MES BBO and ES bars.
**Proposed trade:** during the five sessions before quarterly expiry, measure
the front/next calendar spread against its prior-session same-clock level at
10:00; buy the cheap maturity and sell the rich maturity at 10:01, close both
at 15:30. Both legs need synchronized executable quotes, expiry mapping and
full spread/capital accounting. No back-adjusted price spread or synthetic fills.
**Novelty:** inter-maturity roll transfer, not directional ES volume scars or
the existing outright carry/trend scout.
**Falsifier:** the spread is explained by normal carry/roll changes or costs;
the measured dislocation must exceed two-leg round-trip costs before any claim.
**Status:** blocked by the inspected local execution package, which does not
establish simultaneous front/next bid/ask coverage. Daily multiple-price files
cannot supply intraday fills. Also requires a margin-enabled futures account;
not an executable $100 cash-ETF strategy. Do not acquire data or implement a
directional ETF proxy and pretend it is the same hypothesis.

## 9. V91 — Company repurchase windows reopening after earnings

**Driver:** company-specific repurchase restrictions ending after earnings could
restore a price-insensitive buyer during the next cash session.
**Local data considered:** SEC filing acceptance times and cached stock bars.
**Proposed trade:** for issuers with a previously authorized active buyback AND
an archived policy specifying the reopening, buy the issuer at 10:01 on the
first eligible session and sell at 15:30. Equal-weight simultaneous names;
no buyback-size tuning and no extrapolation from insider rules to issuer activity.
**Novelty:** legal/operational eligibility for corporate buying, not earnings
surprise continuation, SEC event-veto reversal, or peer information propagation.
**Falsifier:** no actual program capacity/issuer policy evidence, or eligibility
does not generate demand. Price changes alone cannot establish buyback activity.
**Status:** rejected for the current no-new-data slate. Local SEC metadata does
not establish issuer repurchase authorizations, capacity or company policies;
the broad opening-bar panel also lacks afternoon stock execution observations.
Do not silently assume a universal two-day blackout and backtest it.
An example of issuer-specific policy variation, not an input to this study:
https://www.sec.gov/Archives/edgar/data/846617/000084661726000013/dcom-20251231xex19.htm .

## 10. V92 — Complete a mispriced binary pair in BTC five-minute markets

**Driver:** separate outcome books can temporarily offer the two exhaustive
outcomes for less than their combined guaranteed payoff.
**Local data considered:** 54,626 BTC five-minute contracts and 1.55 million
sampled price rows in the downloaded Polymarket panel.
**Proposed trade:** buy equal YES and NO shares only when simultaneous executable
asks plus all fees/slippage total below $1, with sufficient depth on both sides.
For strict day trading, require liquidating both legs before a predeclared same-
day cutoff; do not assume market expiry guarantees settlement before that cutoff.
Any failed second leg needs explicitly priced unwind risk and capital reservation.
**Novelty:** complete-set execution consistency, not predicting BTC direction or
the previous five-minute probability-model calibration. Not globally novel arbitrage.
**Falsifier:** apparent underpricing vanishes at simultaneous asks or cannot be
captured after costs; separate sampled prices are not an executable opportunity.
**Status:** rejected from testing with current files. Sampled prices and resolution
labels cannot prove simultaneous asks, depth, atomicity or same-day liquidation.
No optimistic backtest from the local price samples.

## What the input screen actually established

Ten mechanisms considered: seven retained as research designs (V83–V89), with
V88 publication-blocked and V89 publication-conditional; three screened out of
the current executable slate (V90–V92). This is not ten proven distinct alphas
or ten complete backtests. CFTC and earnings ideas remain related to prior broad
families and must clear explicit incremental-information tests before outcomes.

Best order for additional work: V84, V85, V83, V86, V87, then V89/V88 only if
local timestamp evidence resolves their blockers. Ranking uses data and economic
specificity, not observed candidate P&L. V86 has coarse execution evidence.

For any admitted candidate: require positive P&L after costs, stress and deletion
of its five best events, report profit factor (target >1.10), yearly/sleeve results
and full-period SPY-relative growth. Use paired block bootstrap and event/report
clustering where appropriate; apply Holm correction across all tested rules and
disclose the much larger repo-wide selection history. Do not combine failures
or promote profitable controls after seeing results. Prospective paper validation
remains necessary for any historical survivor.

Supporting audit: `ten_daytrade_input_audit_v92.json`, generated by
`audit_ten_daytrade_inputs_v92.py`. It reads local schemas and counts only, makes
zero market-data downloads and calculates no strategy returns.
