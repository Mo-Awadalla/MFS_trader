# Intraday research contract

This contract applies to new, fully funded, same-day-flat, long ETF or stock research. Buying an inverse ETF is a long position in that ETF. The objective remains beating SPY's adjusted-price total-return benchmark after costs over the same calendar. Higher Sharpe alone is a different objective and must not silently replace this one.

The implementation is `research/intraday_contract.py`. It separates signal construction from accounting. The six-family migration example and diagnostic evidence are in `research_scout/research_reset_20260907/REPORT.md`. Historical scout engines remain frozen; this is not a migration of every old script or the live trading engine.

## Freeze the experiment

Before inspecting new outcomes, save a specification containing the mechanism, source files and hashes, feature availability, universe and membership policy, entry and exit clocks, early-close policy, eligible dates, cost profile, benchmark basis, controls, original admission gates, exposed periods, and genuinely untouched confirmation period. Keep a registry of related variants. A later repair is a separately labeled diagnostic, not a retroactive preregistration or independent confirmation.

Retain separate fields for data readiness, signal stability, economics, robustness and confirmation. Frequency, source agreement and similar admission failures must not be described as realized losses. A `preliminary_economic_pass` from the accounting module cannot override another gate or authorize trading.

## Data and time

Use `data.equity_contract.equity_request_bounds` for US-equity downloads. A date-only end includes the whole New York date. Explicit timestamps remain inclusive instants; timezone-free clock timestamps retain the legacy UTC interpretation. Prefer explicit offsets. Use `equity_session_coverage` to audit all fully requested exchange sessions, including wholly absent days, holidays and early closes. Hourly Alpaca bars use clock-hour labels, so 09:00 overlaps the first regular-session half-hour.

`DownloadRequest.require_complete_sessions` defaults to true. Disabling it exposes a partial download for inspection; it does not certify the data, and the normal storage pipeline rejects incomplete coverage. An explicit partial-session request is reported as partial. Missing venue bars can mean no qualifying trades, but cannot be certified as a complete observed grid. For instruments listed after a requested start, specify the actual eligible lifetime rather than silently shortening the sample.

The Yahoo parser requires valid adjusted-close fields and scales OHLC consistently. New downloads are checked for session coverage. Existing cached SPY data remain a `legacy_adjusted_proxy`; this repair does not reconstruct historical dividend reinvestment or certify an old download's raw response. Preserve old caches and acquire any repairs into a new data version. No cache is automatically backfilled by these changes.

Use actual traded ETF prices for execution. Do not apply an extra 3x multiplier to UPRO/SPXU returns. Mark bar-reference scenarios explicitly and obtain quote evidence before promoting them as executable strategies. Quote sampling, event versus receive timestamps, quote age, positive displayed size and venue scope remain adapter responsibilities; the common accounting module cannot verify information it has not received.

## Decisions, allocations and costs

Provide one explicit `cash`, `trade` or `missing` decision for each benchmark session. A no-signal day with verified inputs is cash. An unavailable signal, missing required fill, or an unspecified exit on an early-close day is missing. Missing is never a zero return. Declared historical data exclusions must be disclosed separately; complete accounting conditional on those exclusions is not proof that the same exclusions were available in real time.

Each `Leg` records the symbol, signal-availability time, entry and exit times, capital fraction and both sides of the entry/exit quote. Availability must strictly precede entry, which must precede exit on the same New York date. The adapter must include bar completion and publication/processing delay in availability, rather than using the start label of an unfinished bar.

Simultaneous legs with common entry/exit times form a basket whose weights sum to at most one. Sequential baskets reuse released capital and compound. The evaluator rejects partially overlapping baskets; it is not a general margin, short-borrow or asynchronous execution engine. Idle cash earns zero. Fractional shares are assumed, with no extra borrowing. All reported $100 values are normalized research capital, not a claim about account restrictions or deployable size.

For observed quotes, buy at ask and sell at bid. The baseline research scenario adds 1bp slippage each side, a sell-notional charge of 0.0000051 and a $0.000119-per-share sell charge. These are explicit comparison assumptions inherited from the recent quote experiments, not a historically calibrated broker fee schedule. The stress doubles the assumed bps while retaining the observed spread and fee assumptions. Spread must not be charged twice.

Bar scenarios use an explicitly declared all-in bps profile, with no separate invented observed spread. The stock replay preserves its original 5bps each side and zero additional fee fields. Profiles describe different evidence; passing a cheaper bar scenario does not establish that quote execution will pass.

## Comparison and inference

Build the SPY benchmark from adjusted prices across the full declared calendar, including strategy cash days. Start at the first day's adjusted open, then retain SPY through the final adjusted close. Never compare only the strategy's trade days or drop missing benchmark sessions. Report the benchmark price basis.

Report reference movement, observed spread crossing where available, net return, doubled-cost stress, drawdown, daily Sharpe, and fixed-initial-notional P&L separately. Missing data block a full equity value and formal economic pass; any available-case result must be labeled. Distinguish event trades, legs and distinct trade days.

The common diagnostic interval is a paired 5-session circular block bootstrap of mean daily strategy-minus-SPY return, 5,000 draws, seed 70926. It is not a multiple-testing correction, proof of annual dominance, or a full validation procedure. Preserve original controls and confirmation requirements. Already inspected history stays exposed.

A fixed additional one-minute entry delay, unchanged signal and exit, is the common quote-replay stress demonstrated in the reset. It is separate from the base hypothesis and never a timing search. Where the data cannot resolve that delay, report the stress as unavailable.

## Verification and promotion

Run the focused contract tests, reconcile exported share/cash accounting independently, and verify preservation of historical artifacts. Controlled positive and shuffled-null examples test accounting and obvious failure modes; they do not prove power to detect a small real edge or establish realistic fills.

Before a new signal earns a full confirmation test, require incremental value over simple matched-time controls, sufficient margin over observed trading costs, and an explanation of what new information distinguishes it from failed variants. A candidate additionally needs source/clock robustness, executable sizing, appropriate selection-bias controls and fresh confirmation before deployment. Never treat a shared-engine diagnostic pass as a deployment decision.

Stop a candidate when a verified result clearly fails its declared objective. Record the failure stage and evidence, then abort remaining expensive candidate tests. Do not open confirmation history, search rescue parameters or continue cosmetic variations. Data or implementation uncertainty may justify a bounded diagnostic; a clear economic rejection does not justify an indefinite salvage effort. This stop rule follows the user's September 7 instruction.
