# Bitcoin Crowded-Long Unwind — Binance Perpetual v1

Status: **FROZEN BEFORE RETURN INSPECTION**

Specification: `research_scout/bitcoin_crowded_long_unwind_binance_v1.json`

## Evidence status

This is a weak-evidence falsification scout, not a source-faithful replication and not a validated Strategy.

The sources support the state variables and mechanism background:

- Ackerer, Hugonnier, and Jermann, “Perpetual Futures Pricing,” DOI `10.3386/w32936`: periodic funding anchors perpetual prices toward spot/index references.
- Alexander and Heck, “Price discovery in Bitcoin: The impact of unregulated markets,” DOI `10.1016/j.jfs.2020.100776`: derivatives can contribute information not already present in spot prices.
- Makarov and Schoar, “Trading and Arbitrage in Cryptocurrency Markets,” DOI `10.1016/j.jfineco.2019.07.001`: crypto-market discrepancies can persist under arbitrage frictions.
- Binance’s official USDⓈ-M documentation defines settled funding, mark/index/premium prices, and open-interest metrics.

They do **not** establish that positive funding plus rising OI predicts a reversal. Positive funding can accompany continuation. OI is not net-long exposure because every contract has a long and a short. The negative expected sign below is our predeclared falsification claim.

## Frozen mechanism

A strongly positive settled funding rate identifies completed long-side carrying pressure. Rising BTC-denominated OI during the preceding funding interval identifies expanding outstanding derivatives exposure without mechanically multiplying by the current BTC price. Their conjunction is treated as a crowded-long state that may be vulnerable to a short-horizon unwind.

Competing explanation: positive funding and rising OI may reflect persistent informed bullish demand. A negative or zero result therefore rejects this implementation rather than inviting sign inversion.

## Frozen rule

Once per UTC day:

1. At 00:10 UTC, use the latest funding settlement whose `calc_time + 5 minutes <= 00:10`. The fixed five-minute publication lag is conservative because true historical retrieval timestamps are unavailable.
2. Compare that settled rate with the 90th percentile of the 270 immediately preceding funding settlements. The current observation is excluded. Require at least 180 prior observations.
3. At the same cutoff, take the latest native OI record whose `create_time + 5 minutes <= 00:10` and compare it with the latest lagged record satisfying the same publication rule eight hours earlier.
4. Trigger only if:
   - settled funding is positive and strictly above its expanding threshold; and
   - BTC-denominated OI increased over the prior eight hours.
5. Enter short at the 00:30 UTC perpetual-kline open.
6. Exit at the 07:30 UTC perpetual-kline open.
7. Otherwise remain flat.

The current funding, current OI, and lagged OI observations must each be no more than ten minutes stale relative to their respective event-time cutoffs. Otherwise that day is incomplete and excluded rather than filled. Any actual funding settlement with `calc_time` in `(entry, exit]` invalidates the trade; a settlement exactly at exit is conservatively treated as crossed.

The delayed entry prevents use of a same-bar funding, OI, or price observation. The 00:30 and 07:30 kline opens are execution proxies, not guaranteed fills; the conservative slippage layer addresses this approximation. Missing boundary bars are skipped, never filled.

Short return is `1 - exit_open / entry_open`. The implementation must not use the inverse-contract formula or `entry / exit - 1`.

## Controls

Controls are fixed diagnostics, not replacement strategies:

- Funding-only: extreme positive settled funding, regardless of OI.
- OI-only: positive eight-hour OI change, regardless of funding.
- Basis-only: positive 00:00 premium-index close above the 90th percentile of the prior 270 available daily 00:00 observations, with at least 180 priors.

The combined trigger must improve mean gross short return over funding-only. No weighted score is allowed.

## Costs

- Fee-only: 5 bps per side, 10 bps round trip.
- Conservative: fee plus 5 bps slippage per side, 20 bps round trip.
- Costs apply only on triggered days.
- No leverage, liquidation benefit, maker rebate, VIP tier, BNB discount, or funding receipt is assumed.

These are modeling assumptions rather than a claim that Binance’s historical fee schedule was constant.

## Frozen partitions

- Development: 2020-09-01 through 2022-12-31
- Internal validation: 2023-01-01 through 2023-12-31
- Final holdout: 2024-01-01 through 2025-12-31

Only development may be inspected initially. Downloading the public archives did not authorize calculating later-period outcomes.

## Terminal development gates

All must pass:

- at least 40 triggered days;
- positive mean gross short return;
- short directional accuracy above 50%;
- positive gross mean in each chronological half;
- session-bootstrap 95% lower bound above zero;
- positive mean after 20 bps conservative round-trip cost;
- positive mean after removing the top 5% of absolute primary outcomes;
- top 5% of profitable days contribute no more than 50% of total positive profits;
- complete timestamp ordering;
- combined trigger mean exceeds funding-only mean.

If development fails, stop. Do not invert to continuation, alter the threshold/lookback, use USD OI instead, change the OI lag, change decision/entry/exit times, add ratios or technical indicators, introduce ML, use another venue/coin, or inspect later partitions for this specification.
