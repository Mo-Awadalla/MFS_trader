# Bitcoin Spot–Perpetual Basis Convergence — Binance v1

Status: **FROZEN BEFORE RELATIVE-VALUE RETURN INSPECTION**

Specification: `research_scout/bitcoin_spot_perp_basis_convergence_binance_v1.json`

## Goal alignment

This is a non-latency, one-trade-per-day maximum, market-neutral candidate. It is evaluated as a possible alpha sleeve, not as a replacement for SPY. It avoids another outright Bitcoin direction forecast.

## Mechanism and evidence

Perpetual funding is designed to anchor perpetual prices toward a spot/index reference. Ackerer, Hugonnier, and Jermann, “Perpetual Futures Pricing,” DOI `10.3386/w32936`, establishes the anchoring mechanism. Makarov and Schoar, DOI `10.1016/j.jfineco.2019.07.001`, establishes that crypto price discrepancies can persist under arbitrage frictions.

Neither source proves that this exact Binance basis threshold converges profitably over seven hours. Threshold, daily clock, and horizon are frozen implementation choices.

## Rule

At 00:05 UTC daily:

1. Use the fully closed 23:30–00:00 spot and perpetual trade-price kline closes.
2. Compute `log(perpetual_close / spot_close)`.
3. Trigger if basis is positive and strictly above the 90th percentile of the 90 strictly prior available daily basis observations; require at least 60 priors.
4. At 00:30, use both kline opens as execution proxies: long spot at 0.5 capital weight and short equal-notional perpetual at 0.5.
5. Exit both legs at the 07:30 kline opens.
6. Skip days missing any exact boundary or containing an actual funding settlement in `(entry, exit]`.

Gross exposure is 1.0 and initial net BTC exposure is approximately zero. No leverage benefit is claimed.

Capital return is:

`0.5 * (spot_exit / spot_entry - 1) + 0.5 * (1 - perp_exit / perp_entry)`

This separates relative convergence from outright BTC direction. Basis contraction alone is not sufficient if asynchronous fills or costs consume it.

## Costs

Four executions are charged:

- Spot: 10 bps per side.
- Perpetual: 5 bps per side.
- Fee-only capital-weighted round trip: 15 bps.
- Conservative slippage: 5 bps per side on both legs, capital-weighted 10 bps.
- Conservative total: 25 bps per triggered day.

No funding receipt is credited because the position exits before the scheduled 08:00 settlement and actual funding events are guarded.

## Partitions and stopping

- Development: 2020–2022
- Internal validation: 2023
- Final holdout: 2024–2025

All development gates are conjunctive: at least 60 trades, positive gross mean in both chronological halves, bootstrap lower bound above zero, positive after 25 bps, robust to removing the largest 5% absolute outcomes, acceptable profit concentration, correct timestamps, and average basis contraction.

If development fails, the family stops. OI, funding, volume, trader ratios, alternate thresholds/horizons, ML, and other venues cannot rescue this consumed specification.
