# SPY Day-Trading Hypothesis Screen v44

## Objective

Find a causal, non-HFT, flat-by-close strategy that:

- averages at least two executable trades per calendar week;
- compounds above same-period split-and-dividend-adjusted SPY after observed marketable execution;
- does not depend on a few exceptional winners;
- remains positive across years, directions, delays, and an independent execution feed;
- does not repair or invert an outcome-exposed V1–V43 construction.

No V44 post-entry ETF return was inspected while this screen was written.

## Failure-derived design constraints

The existing research program makes several attractive-looking directions inadmissible or low priority:

1. Opening-range, opening-value, same-clock seasonality, late-day continuation, wrapper-flow geometry, ES scars, BTC spot-flow transfer, and opening/closing-auction families are outcome-exposed.
2. Small gross effects do not survive ask-to-bid execution. A candidate needs meaningful economic amplitude, not merely a statistically nonzero sign.
3. Specific rules often fail the two-trade/week requirement; cadence must be tested before returns.
4. UPRO can look profitable while SPXU loses. A symmetric story is not enough: both actuator sleeves must make money.
5. Development results repeatedly collapsed in 2024–2026. Holdout remains locked unless every frozen development gate passes.
6. Best-five or best-ten deletion killed many historical candidates. Concentration is a primary gate, not a diagnostic footnote.
7. The standard repository benchmark is price-only SPY. V44 strengthens the hurdle by also requiring the strategy to beat locally stored split-and-dividend-adjusted SPY.
8. New data does not reset multiplicity. Every candidate below is part of the same continuing research program.

## Candidate 1 — Scheduled macro-release delayed discovery

Mechanism: CPI, payrolls, PCE, ISM, JOLTS, retail-sales, and FOMC releases can initiate multi-hour portfolio reallocation after the initial latency race.

Proposed shape: observe SPY's first ten minutes of post-release direction, enter after a dead interval, and exit before the close.

Why it might work: macro information changes discount rates and aggregate earnings assumptions, and slower asset allocators cannot all transact in the first seconds.

Hard critique:

- SPY and ES are among the fastest markets in the world; a delayed sign rule may be plain stale momentum.
- The repository has no frozen, audited official historical calendar across all listed event families.
- Mixing release types can conceal that only one class works; splitting them destroys cadence and increases multiplicity.
- A hand-built or revised calendar risks timestamp leakage.
- Two trades/week is plausible but unproven.

Decision: **defer**. The mechanism is strong, but the causal calendar is not yet a local audited input. Building the calendar should be a separate data project, not improvised inside a return test.

## Candidate 2 — Credit-to-equity delayed stress diffusion

Mechanism: duration-adjusted HYG weakness can reveal funding/default stress before broad equities finish repricing.

Proposed shape: estimate a prior-session-only HYG/IEI duration control, then trade SPY when the credit residual and morning SPY direction disagree.

Why it might work: corporate bonds are held by different participants and may process financing stress differently from equity-index flows.

Hard critique:

- SPY may lead HYG, making the proposed direction backwards.
- HYG embeds equity beta, stale underlying bond marks, and ETF-specific creation/redemption noise.
- The required synchronized HYG/IEI intraday history is not in the verified local inventory.
- Adding it now would introduce source and adjustment choices before the mechanism is proven.

Decision: **reject for current pass** because the local data prerequisite is absent.

## Candidate 3 — SEC earnings-information breadth

Mechanism: multiple premarket Item 2.02 filings jointly reveal aggregate demand, margins, labor costs, and financing conditions; a cross-firm median reaction may diffuse into SPY.

Proposed shape: on sessions with at least two eligible filings, use the median issuer-minus-SPY 09:30–10:00 return to trade SPY from after 10:05 to before the close.

Why it might work: aggregation can diversify company-specific noise and isolate an economy-wide information component.

Hard critique:

- The 133-name universe is static and survivorship-biased.
- SEC acceptance often follows an earlier press release, so the timestamp may be causal but economically stale.
- The underlying Item 2.02 event/reaction panel is already outcome-exposed through a failed single-stock continuation study.
- Earnings clustering may average two sessions/week while leaving many zero-trade weeks.
- A promotion-quality result requires a point-in-time security master that is not locally available.

Decision: **retain only as a bounded later scout**, not the strongest candidate.

## Candidate 4 — Megacap breadth versus SPY disagreement

Mechanism: the equal-weight sign breadth of twenty economically important stocks may reveal broad risk direction when cap-weighted SPY is temporarily dominated by a few names.

Proposed shape: use the fixed SIP hourly panel to compare premarket or first-hour median constituent direction with SPY, trading disagreement toward the broad direction.

Why it might work: information diffuses asynchronously through constituent firms, and cap concentration can mask broad participation.

Hard critique:

- The static twenty-stock list is hindsight-selected and not a point-in-time index universe.
- Hourly bars are too coarse for clean opening timing and cannot establish a marketable fill.
- SPY normally leads less-liquid constituent aggregation, so the causal lead-lag may run in the opposite direction.
- Existing breadth-diffusion candidates produced attractive development results and weak later years.

Decision: **reject for current pass**. It is adjacent to consumed breadth families and has a severe universe-bias problem.

## Candidate 5 — Same-day volatility-control deleveraging

Mechanism: unusually high realized variance by 13:30 can cause volatility-target and risk-control portfolios to sell into the close.

Proposed shape: short after 13:35 when current-to-clock realized variance exceeds its trailing-20 same-clock median.

Why it might work: systematic leverage reductions can be predictable and concentrated late in the session.

Hard critique:

- Many risk-control mandates use slower close-to-close estimates rather than the proposed same-day statistic.
- High variance and falling price are mechanically related through the leverage effect, so the signal may just short after a decline.
- The institutional flow is inferred rather than observed.
- A short-only late-day strategy has a difficult path to beating long-run SPY total return.
- The exact family is close to prior variance-state work that failed SPY-relative robustness.

Decision: **reject for current pass** because mechanism identification is weak and lineage is adjacent.

## Candidate 6 — Binance BTC perpetual fresh-position risk transfer

Mechanism: a BTC perpetual price move can be produced by closing old exposure or by opening new leveraged exposure. Only the latter should be expected to persist as a global speculative-risk state. BTC-denominated open interest distinguishes those cases without mechanically embedding BTC's price.

Frozen signal shape:

1. Formation starts at the immediately prior eligible SPY session's 16:00 New York boundary.
2. Formation ends at the current session's 09:00 boundary.
3. Use exact completed Binance BTCUSDT perpetual 30-minute closes at both boundaries.
4. Use the latest Binance BTC-denominated open-interest observations timestamped at or before each boundary. Treat each metric as public only five minutes after `create_time`; the final decision is 09:05.
5. If BTC price rose and BTC open interest strictly rose, buy UPRO at the observed 09:31 ask.
6. If BTC price fell and BTC open interest strictly rose, buy SPXU at the observed 09:31 ask.
7. If open interest did not rise, price was unchanged, any exact boundary is absent, or an input is stale, remain in cash.
8. Exit at the observed 15:30 bid. Hold at most one fractional long ETF position and remain flat overnight.

Why it might work:

- BTC is continuously traded while U.S. cash equities are closed and is sensitive to global speculative risk appetite.
- Rising BTC-denominated open interest says the move coincided with net contract creation rather than only liquidation or covering.
- Price supplies direction because open interest alone cannot identify long versus short initiation.
- Persistent leveraged position formation is consistent with a metaorder/risk-allocation state that may continue when U.S. cash participants arrive.
- The rule is threshold-free and should naturally trade on roughly the fraction of sessions with expanding overnight OI, offering a credible route to the required cadence.
- UPRO/SPXU provides enough amplitude to challenge buy-and-hold SPY if the conditional direction is real.

Why it may fail:

- Binance BTC is not SPY or ES, and crypto-specific news can dominate.
- ES and SPY trade outside regular hours; any shared information may already be in the opening gap.
- Open interest does not identify who initiated, trader quality, or whether new longs or shorts are informed.
- The price sign remains a generic BTC return even though the OI gate is new.
- BTC/equity beta changed sharply across 2021–2025.
- Binance is a single venue and cannot establish a global derivatives state.
- SPXU has materially worse spread economics and inverse-wrapper drag.
- A 09:31 entry can be stale relative to the 09:00 BTC endpoint.
- V26 and V32 showed that BTC spot-flow transfer and BTC-gated SPY gaps were decisively unprofitable. V44 is admissible only because it uses a previously unused directional state—BTC-denominated derivative open-interest expansion—and binds itself to controls proving that OI adds value beyond price alone.

Decision: **select for V44 returns-blind feasibility audit**. It is the strongest combination of underused rich local data, exact causal timestamps, threshold-free cadence, non-HFT execution, and a discriminating economic control.

## Frozen progression discipline

1. Audit only input coverage, cadence, side balance, timestamp causality, own-market coherence, quote availability, and neighboring-clock action stability.
2. If any feasibility gate fails, stop without reading post-entry ETF prices.
3. If feasibility passes, inspect only 2021–2023 development returns.
4. Compare actual V44 with price-only, OI-decreasing, shifted-gate, and sign-flipped controls.
5. Keep 2024–2025 locked unless every development gate passes.
6. No direction inversion, side deletion, magnitude threshold, alternate OI representation, clock change, stop, or regime filter may repair a failure.
