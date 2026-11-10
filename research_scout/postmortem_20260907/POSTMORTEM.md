# Complete research postmortem

September 7, 2026 UTC. Goal: algorithmic day trading that beats matched-period SPY after realistic costs, with no overnight positions. This review preserves the original experiment results and stopping rules; it does not launch replacement backtests.

## Decision

The repository has already investigated most of the broad ideas recently suggested in conversation: opening momentum, opening reversals, related-ETF convergence, stock/bond transmission, constituent breadth, company-event continuation, flow proxies, and adaptive historical analogs. Presenting those categories again as new directions was a mistake.

The remaining work is more specific. Some exact mechanisms have negative economic evidence, others have unstable or ambiguous measurements, some stopped solely because of the old cadence mandate, and a smaller set lacks an observation necessary to test it. These are different outcomes. Neither “everything failed” nor “we just need more data” accurately describes the archive.

**The postmortem does not establish company-announcement data as the best next purchase.** It establishes several conditional gaps. The most immediately actionable step is to reconcile old quote-coverage blockers against data and access acquired since those decisions. The largest informational gap for a company-news strategy would be first-publication content and prior expectations; for ETF arbitrage it would instead be basket/quote/hedge information. There is no measured basis to rank their future alpha in dollars.

## Scope and coverage

The [full ledger](ALL_HYPOTHESES.md) contains **232 research records**. It covers every V1–V92 number, expands 46 child rules inside multi-candidate result files, includes the separate SPY/SH batch, 33 ES/MES records, all 19 formal Experiment metadata instances, other stock/crypto/futures scouts, explicit screened proposals, and supporting diagnostics. Numbered versions are chronology, not a count of independent hypotheses.

| Record group | Records |
|---|---:|
| Cash-ETF batches, expanded into rules | 52 |
| Numbered continuation V15–V92 | 78 |
| ES/MES rules and portfolios | 33 |
| Formal Experiment instances | 19 |
| Other scouts | 15 |
| Explicit screened/proposed ideas | 29 |
| Additional diagnostics/protocols | 6 |
| **Total records** | **232** |

The totals include aliases, portfolio combinations, data audits and repeated Experiment instances. They must not be interpreted as 232 independent backtests or 232 statistically independent chances to find alpha. Parameter sweeps remain recorded in their source reports and [sweep-exposure appendix](formal_sweep_exposure.json); a parameter grid is not silently converted into independent hypotheses. Literature-only examples and strategy factories with no instantiated research proposal are not treated as tested rules.

The source manifest contains 546 artifacts; 447 are directly linked from ledger entries. Automated reconciliation confirmed complete numbered coverage, every child in the targeted batch result containers, every formal metadata instance, existing source paths, and unchanged hashes of linked historical sources during this audit. See [coverage verification](coverage_verification.json). This is an artifact and decision review, not a fresh execution of every historical engine. No new strategy returns or market-data acquisitions were produced by this postmortem.

Each ledger row includes the result stage, primary classification, specific reason, evidence that could change the assessment, related attempts and source links. Original claims are quoted as hypotheses, not endorsed as established causality. Machine-readable versions are [JSON](hypothesis_ledger.json) and [CSV](hypothesis_ledger.csv).

## What the classifications show

| Primary classification | Records | Meaning |
|---|---:|---|
| Economic/predictive failure | 72 | Negative net economics or failed descriptive prediction in the recorded implementation. This does not mean every rule was negative before costs. |
| Robustness or benchmark failure | 59 | Some positive results, but failure of later periods, costs, concentration, controls, SPY or other frozen requirements. |
| Missing necessary observations | 23 | Includes data-blocked rules, data-admission audits and unimplemented proposals. Not 23 demonstrated profitable opportunities. |
| Cadence/component/protocol rejection | 18 | The old frequency or component requirements stopped progress; no economic inference should be invented where P&L was not evaluated. |
| Measurement failure | 13 | Invalid denominators, feed-sensitive states or endpoint-sensitive actions. |
| Duplicate/ambiguous mechanism | 14 | A new label did not identify a distinct causal quantity or direction. |
| Incomplete tradable-edge evidence | 9 | Proposals without completed tests, probability studies without executable prices, or missing result evidence. |
| Outside the day-trading mandate | 6 | Overnight or slower hypotheses, including withdrawn proposals. |
| Positive evidence outside day trading | 3 | Two formal UUIDs for the same daily ETF family and one daily futures scout. |
| Diagnostics/protocols | 8 | Operational, input or outcome-attribution evidence; not alpha passes. |
| Proposal aliases | 7 | Earlier names/proposals linked to their later research; not additional backtests. |

These are explanatory primary labels. A record can have several problems; its detailed row preserves them. Counts are descriptive and cannot be used as a statistical success rate because the records overlap and the historical gate definitions changed.

## Findings by mechanism

### 1. Opening price patterns and accepted-value stories were heavily explored

Formal market intraday momentum and opening-range breakout lost approximately 17.6% and 47.0%, respectively. Same-clock seasonality lost approximately 74.7% and also failed execution/holding-period requirements. The individual-ETF IBB afternoon recovery rule lost before and after its modeled costs. The SPY first-hour correlation study did not find its specified predictive relationship.

The SPY/SH batch tested five additional rules. Counterauction effort and opening volume-scar parallax had small positive zero-slippage diagnostics but negative baseline results. Premarket false-probe relay, rejected excursion transfer and center/close disagreement did not supply a useful gross/net alternative. These were already individual cash-ETF tests, not exclusively UPRO/SPXU research.

The ES series explored many variations of opening centers, displacement, entropy, activity, pressure, scars, lunch handoffs and path geometry. Some had attractive developmental profit, often concentrated in 2022, but failed yearly/side consistency or later periods. This history provides little justification for another renamed price-anchor rule on the same observations.

### 2. More elaborate cross-market features frequently reproduced ordinary momentum

V11 and V12 tested broad-index diffusion and transition rules; V13 added index geometry. Later constituent-level inputs did not establish independence merely by increasing symbol count:

- V75 breadth acceleration agreed with SPY opening momentum on 90.51% of actions.
- V77 liquidity relay agreed on 95.30%, with poor subuniverse replication.
- V76 dispersion compression was stable but its simple SPY path control was stronger; ending cash was $123.29 versus SPY $132.40.
- V63 four-fund rebalance/auction modeling agreed with its plain late-day direction control on 96.18% of actions.
- V71 settlement/RRP netting agreed with RRP alone on 90.60%.
- V79 cross-asset fund flow agreed with HYG alone on 86.08%.

These are rejections of the frozen action rules, not proof that the underlying variables contain no magnitude or risk information. However, adding another ETF to a sign vote is not a demonstrated new hypothesis.

The exact broad sector-ETF lead-lag proposal was not found as a completed implementation. Therefore our earlier conversational claim that all sector transmission questions had already been answered was too broad. The related index/constituent history strongly constrains the proposal, but does not exactly falsify every sector-specific mechanism.

### 3. Marketable costs repeatedly consumed small effects

V1 Second-Auction Ownership Lease changed from +$24.16 to -$6.82 fixed-notional P&L with one additional cent per share at each fill. V56 stock/bond impulse similarly changed from +$29.64 to -$2.86. V62 creation-conditioned convergence failed extra-cost, temporal, control and independent-feed checks despite positive aggregate development.

The BTC spot/perpetual basis study is especially clear: average gross profit was about 1.03 basis points of capital, but conservative modeled profit was -23.97 basis points. A high rate of basis contraction did not create enough dollars to pay for implementation.

Replacing ask/bid fills with midpoints, assuming passive fills, or reporting gross accuracy would change the answer through the assumptions. Where passive execution itself is the proposed edge, order/queue/fill information becomes a new necessary measurement.

### 4. Good-looking development results did not predict generalization

V47 VX forward-stress persistence passed development and grew simulated $100 to $408.90, then ended the 2024–2025 holdout at $30.60. Opening-center migration and activity entropy also deteriorated in later samples. Adaptive analog memory was already tested: V7 ended $125.23 versus price-only SPY $170.34; the V8 SH execution substitution improved cash to $137.33 but still failed benchmark and robustness requirements.

This rules out “we only tried simple fixed indicators” as a complete explanation. Adaptive selection and richer feature geometry were investigated too.

### 5. Flow measurement and flow interpretation are separate problems

The repository acquired daily NAV, AUM, shares, Treasury awards, CFTC categories and realized Treasury cash flows. Several old missing-data claims are therefore obsolete. Subsequent evidence matters:

- V60 admitted primary-market flow inputs; V61 then lost in every development year.
- V66 Treasury awards did not establish that dealers still held unhedged exposure the next morning.
- V67 combined AUM-based demand and ES aggressor transfer with stable measurements, yet lost in every year and both wrappers.
- V74 safely lagged realized TGA transfers produced ending cash of $55.09.
- V78 FINRA short-volume direction was rejected before acquisition because the same reported quantity can arise from different customer/inventory workflows.

The missing object is often the identity, timing or surprise of an obligation—not another transformation of a public flow proxy. Public data need not identify participants to have predictive utility, but an asserted dealer/AP mechanism should not be treated as observed when it is inferred.

### 6. Company-event research is neither absent nor comprehensively disproved

Three relevant layers already failed:

1. SEC-associated single-stock continuation: +5.24 bps gross stock return became -4.76 bps after fixed costs; coverage and uncertainty also failed.
2. SEC-event-veto daily reversal: wrong-sign, near-zero rank IC and negative gross performance; default net return -43.47%.
3. Earnings breadth/network transmission: V73 and V85 failed the SPY hurdle and robustness; V85 had about 44.8% daily drawdown.

These studies did not measure complete first-publication text, issuer guidance surprises or prior analyst-expectation vintages. Those remain distinct potential information, but their absence does not establish that buying them is the highest-value next action. “Try earnings” would repeat history; “measure this specific previously unobserved surprise with verified availability” would be a different research proposition.

## What remains unresolved, and why

| Record | What the archive actually established | Appropriate evidence task |
|---|---|---|
| V37 / V40 | Plausible measured opening features failed quote-coverage gates; V37 also had a semantic critique | Reconcile historical quotes with existing SIP and opening MBP-1. Do not assume coverage completion resolves the economic critique. |
| V49 / V35-R4 | Trade-associated snapshots could not establish synchronized six-ETF quote states | Audit the newer complete opening updates and existing historical SIP. Preserve original history and registration; no immediate favorable-date P&L selection. |
| V68 | Missing SSO/SDS continuous quotes blocked a two-legged relative-value rule | Check historical SIP window coverage, then historical short/borrow and two-leg execution requirements. |
| V43 | Premarket signal measured well, execution mostly absent; spread tails and later field participation problematic | Premarket quote and venue-protocol audit, including missingness and spread distributions before outcomes. |
| V88 / V89 | Auction/lending result availability at the historical decision time not established | Find first-publication and revision evidence. More rows without availability timestamps do not solve the problem. |
| V59 / V15-R3 | Daily historical derivative holdings and intraday basket context incomplete | Verify archive existence and public timing before any purchase; holdings still do not equal observed dealer hedging. |
| V90 | Simultaneous front/next executable futures quotes absent | Raw-contract synchronization and realistic two-leg/capital model. Reading futures as a signal does not itself require margin; trading them does require the corresponding execution/account model. |
| V91 | Actual issuer buyback policy/capacity not observed | Authenticated dated issuer rules and authorization changes; a generic calendar is not actual buying. |
| V92 / POLY-PROXY | Outcomes or sampled prices available, executable simultaneous books absent | Contract-level bid/ask/depth and fee/fill accounting; model-label accuracy is not an edge over the market's price. |
| DT3 / INST1 / INST5 | Explicit proposals for overnight-loser intraday reversal, earnings revisions and reconstitution flow lack completed exact tests | Point-in-time universe/events/expectations appropriate to the exact rule, with prior-family overlap retained. |

V21, V22, V24, V31, V46 and V64 are important counterexamples to a blanket data-gap explanation. They had substantial or complete measurements and stopped on cadence/component requirements. V64 had 335 balanced, locally stable signals and complete independent action agreement; one year had 73 rather than the frozen minimum of 90. That is not proof its returns are negative, nor a reason to acquire another feed.

The old two-trades-per-week and positive-every-year/sleeve rules are historical mandate gates, not universal statistical laws. They should remain intact in their original experiments. Any future mandate permitting sparse sleeves should state that before testing, count the selection history and use fresh evidence. This postmortem does not reopen their returns or lower their gates.

## Evidence and accounting issues that affect interpretation

- **Benchmark changes:** early reports often used price-only SPY, later ones total-return SPY. Some results beat the easier hurdle or had higher Sharpe without beating total wealth. Do not pool them into one success ranking.
- **Different sizing:** fixed-$100 summed P&L, cash-compounded equity and one-MES dollar profit are different quantities. Futures dollar totals do not establish returns on an adequately funded account.
- **Multiplicity and reused holdouts:** V2's later “curiosity” test, ES post-result diagnostics, related families and formal parameter sweeps all count as exposure. A new dataset or UUID does not reset that history.
- **Historical versus genuinely forward:** V6 was frozen July 26 for a January–July 24 sample. Its original “prospective” label means uninspected before acquisition, not orders observed after registration in live time. It produced zero trades because the binary synchronization state saturated.
- **CFTC availability:** V65 used report-date plus seven calendar days. The later V87 audit explicitly excluded the 2023 reporting outage. V65's old broadly safe-timing claim therefore needs qualification; its quoted metrics are historical results, not newly corrected causal estimates.
- **Sparse/incomplete implementations:** daily pairs had zero trades. VS-ICSM's static hourly panel skipped 19,832 of 19,833 rebalances and recorded only 15 trades; its total-return/CAGR relationship also needs annualization reconciliation. Neither result validates an active broad intraday implementation.
- **Research versus runtime:** the daily TSM replay passed structural checks, but recorded about $27,759 final equity versus $50,944 in vectorized research. A plumbing pass is not economic replication or a live approval.
- **Incomplete evidence:** one legacy Bollinger metadata directory lacks a canonical validation report. The ledger labels it incomplete rather than fabricating a result. The newer Bollinger validation does have failed evidence.

## Positive evidence worth preserving

The daily ETF TSM family passed formal validation and offered lower risk, but its documented CAGR was 7.89% versus SPY's 10.86%. Its two passed UUIDs represent the same family, not two independent discoveries. It holds overnight and does not meet the current day-trading goal.

Cross-asset daily futures carry/trend passed its public-data scout, with net Sharpe about 0.608 and useful diversification. Its SPY-plus-sleeve figures involve additional exposure, not a cash-funded intraday comparison. Raw-contract replication and operational validation remain outstanding.

Among intraday work, ES prior-close volume scar, compressed opening convexity and related portfolios retain weak positive historical evidence. They failed tail, uncertainty and/or execution robustness. V20's cash-ETF translation also failed winner deletion. V83 month-end pressure had positive development and specified cost/delay checks but failed SPY wealth and excess-return uncertainty. These deserve preservation as exactly documented; none is a validated day-trading SPY beater.

## Revised next-step priorities

1. **First: reconcile quote availability, without new P&L.** Existing credentials already returned historical SIP bars, quotes and trades in the preceding audit. Determine whether the original V37/V40/V49/V68 measurement requirements are now actually observable. This is the cheapest concrete way to distinguish a stale blocker from a persistent one. It is not a prediction that these rules will win.
2. **Second: resolve the small, precise publication gaps.** V88/V89 need historical result-availability evidence; V65 needs outage-aware reconciliation. If source archives cannot establish it, retain the block rather than guess a clock.
3. **Third: match any new information acquisition to one distinct surviving question.** Options/basket/participant information, company expectations and index event histories are different alternatives. Require a bounded availability sample and an explicit mechanism before paying for breadth.
4. **For existing weak positives: fresh execution evidence.** A prespecified forward record can assess persistence and execution for a retained exact candidate. It cannot convert previous failure into a passed historical result. No monitoring, trading or new acquisition was started by this review.

The portfolio objective remains matched-capital, after-cost total wealth versus SPY, including idle cash and simultaneous-position constraints. Risk-adjusted performance, diversification and uncertainty should be reported alongside that objective rather than substituted for it.

## Corrections to the prior conversation

I should not have presented broad sector transmission, opening price discovery or company events as fresh ideas before reconciling this history. I also should not have inferred that company-event data was the best acquisition simply because it was missing. Conversely, saying our past tests answered every ETF question was too strong: some exact proposals were never implemented and several failed only admission gates.

The evidence now supports a narrower decision: stop recycling the tested constructions; resolve identifiable, potentially stale measurement blockers first; keep mandate failures distinct from economic failures; and require a concrete independent observation before proposing the next research family.
