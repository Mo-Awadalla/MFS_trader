# SPY BTC-Perpetual Fresh-Position Risk Transfer — Preimplementation Critique v44

## Frozen hypothesis

An overnight BTCUSDT perpetual price move accompanied by rising BTC-denominated Binance open interest represents fresh leveraged position formation rather than only the closing of old exposure. If this is a shared speculative-risk allocation rather than a crypto-only event, its direction may continue into the U.S. cash-equity session.

For each eligible SPY session:

1. Identify the immediately prior eligible SPY session.
2. Measure the BTCUSDT perpetual close-to-close return from that prior session's 16:00 New York boundary to the current session's 09:00 boundary, using exact completed 30-minute bars.
3. Measure the change in Binance `sum_open_interest` over the same boundaries. Use BTC-denominated OI, not USD notional OI.
4. Treat futures metrics as available only five minutes after actual `create_time`; decide at 09:05.
5. Rising OI plus positive BTC return maps to UPRO. Rising OI plus negative BTC return maps to SPXU. All other states map to cash.
6. Buy at the observed 09:31 ask and sell at the observed 15:30 bid.
7. Allocate at most the available $100 account value to one fractional long ETF. No short sale, margin, crypto position, stop, target, or overnight ETF holding is allowed.

## Why an institutional cross-asset desk might care

The economic object is not another BTC-return rule. It is a decomposition of price movement by contract creation:

- price up, OI up: fresh risk-seeking exposure is being established;
- price down, OI up: fresh defensive/speculative short exposure is being established;
- price up, OI down: short covering, direction potentially exhausted;
- price down, OI down: long liquidation, direction potentially exhausted.

The rule trades only the first two states. That is a simple inventory-state distinction using a 24/7 derivative venue before the U.S. cash open. It does not require millisecond transmission or queue priority.

## Strongest positive case

Large directional positions are often executed over time. A price move with expanding contracts is more consistent with new risk being warehoused than a price move produced by forced exits. BTC's round-the-clock market can reveal a globally active speculative-risk state while U.S. cash equities are closed. If the underlying shock concerns dollar liquidity, technology-duration appetite, geopolitical risk, or broad deleveraging, U.S. equity allocation can continue after 09:30.

BTC-denominated OI is important. USD OI rises mechanically when BTC price rises and falls when price falls, potentially manufacturing the desired quadrant. Contract-count OI avoids that direct price contamination.

The rule has no fitted percentile or magnitude threshold. Expanding versus non-expanding OI should occur often enough to meet cadence without widening a rare pattern after measurement.

## Strongest negative case

The hypothesis may be categorically wrong because SPY is not waiting for BTC. ES, SPY, and U.S. equity baskets trade overnight. Any shared macro information should already be reflected before the cash open. Binance BTC activity may instead reflect crypto regulation, stablecoin flows, exchange-specific positioning, token liquidations, or weekend inventory with no S&P implication.

Even inside BTC, OI expansion is ambiguous: every contract has a long and a short, and aggregate OI does not reveal which side is informed. Price supplies the sign, making the rule potentially no more than BTC overnight momentum under a noisy thinning gate.

## Relation to consumed V26 and V32

V26 directly transferred the sign of Binance **spot taker flow** across Asia and Europe into UPRO/SPXU. It lost in every development year, ended at $58.57 versus $126.66 price-only SPY, and failed every economic gate.

V32 used persistent BTC spot flow only as an attention gate while SPY's own opening gap supplied direction. It ended at $64.50, lost to its shifted placebo, and failed every economic gate.

V44 neither reuses their spot-flow sign nor their SPY-gap direction. Its causal variable is BTC-denominated **perpetual open-interest expansion**, a field absent from both rules. This is still one continuing BTC-to-equity research family, so the controls are binding:

- V44 must beat the same BTC price sign without the OI gate.
- V44 must beat the BTC price sign when OI decreases.
- V44 must beat a one-equity-session-shifted expansion gate.
- V44 must beat the exact sign-flipped rule.

A failure cannot be repaired with extreme OI thresholds, funding, premium, trader ratios, only one direction, another clock, or an SPY-gap overlay.

## Data and timing audit requirements

- Perpetual 30-minute klines must contain exact bars ending at both formation boundaries.
- Metrics use actual `create_time`; off-grid timestamps are never rounded backward.
- Add a frozen five-minute public-availability lag to every metric observation.
- OI at a boundary must not be more than ten minutes stale relative to that boundary.
- The latest signal input must be available by 09:05 and before the 09:31 order.
- Missing values invalidate the day; no forward fill.
- Use the immediately prior eligible equity session, so Monday formation includes the weekend rather than pretending Sunday was an equity close.
- Exclude declared degraded ETF feed dates.

## Returns-blind feasibility gates

Before reading any post-09:31 ETF price:

1. Complete BTC price/OI measurement on at least 98% of eligible 2021–2023 SPY sessions.
2. At least two executable development entries per calendar week.
3. At least 100 executable entries in each of 2021, 2022, and 2023.
4. Neither UPRO nor SPXU below 20% of executable entries.
5. At least 95% ARCA entry-quote availability among otherwise valid signals.
6. At least 95% EQUS entry-quote availability during the overlapping development dates.
7. At least 52% agreement between formation-window BTC price direction and normalized perpetual taker-flow direction on signaled days. This validates orientation in BTC; it does not inspect equity outcomes.
8. At least 75% identical action including cash when the current endpoint is moved one completed bar earlier to 08:30. This guards against a single noisy final bar without creating an alternate return rule.
9. Every latest input availability timestamp must be at or before 09:05, and every proposed entry must be later than 09:05.

Failure is terminal without P&L.

## Frozen development return gates

Only after feasibility passes, 2021–2023 must satisfy all of the following:

- at least two observed-BBO trades/week;
- profit factor strictly above one;
- positive fixed-$100 P&L in 2021, 2022, and 2023;
- positive UPRO and SPXU sleeves;
- compounded ending cash above price-only SPY;
- compounded ending cash above locally stored split-and-dividend-adjusted SPY;
- positive P&L after one additional cent per share at entry and exit;
- positive P&L after a five-minute entry delay;
- positive P&L after deleting the ten best sessions;
- higher mean-trade P&L and higher winner-deleted P&L than the BTC-price-only control;
- higher fixed-notional P&L than the OI-decreasing, shifted-gate, and sign-flipped controls;
- positive P&L on the independent EQUS execution overlap.

Only a complete development survivor may unlock 2024–2025. Holdout must independently pass analogous year, sleeve, SPY-total-return, costs, delay, remove-best-five, and consolidated-feed gates without a rule change.

## Execution and benchmark critique

UPRO/SPXU are not frictionless three-times SPY. Their daily reset, financing, tracking, spreads, and inverse asymmetry matter. Observed ask entry and bid exit are mandatory. The SPXU sleeve is expected to be the hardest gate and may terminate an otherwise positive signal.

Compounding a fully invested $100 account is more demanding than summing fixed-$100 P&L. Both are reported. The same-period benchmark must include the repository's traditional price-only SPY hurdle for comparability and a split-and-dividend-adjusted local daily SPY hurdle for the user's actual objective.

## Statistical and research-program critique

- 2021–2025 has already supported many failed ETF and BTC experiments.
- V44 is preregistered relative to its own target, not a pristine discovery sample.
- Passing historical gates would justify forward paper observation only.
- Cross-asset beta is likely nonstationary across crypto winter, banking stress, ETF approval, and later institutional adoption.
- Calendar-week frequency can conceal clusters; monthly and annual counts must be reported.
- Winner deletion is binding because leveraged wrappers can concentrate results in a few shock days.
- Controls are identification tests, not a menu from which to select the best post hoc rule.

## Preimplementation decision

**Advance to a returns-blind feasibility audit only.** The rule uses a rich, locally complete, materially underused derivatives state and directly answers a weakness of prior BTC spot-flow work without inverting its losses. The claim remains weak because BTC-to-SPY transmission may be stale or nonexistent. Cadence, timestamp, orientation, and quote evidence must pass before any forward ETF price is read.
