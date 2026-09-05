# FTRE v1 — Funding-Time Reversal Experiment

- **Universe**: BTCUSDT, ETHUSDT, SOLUSDT USDⓈ-M perps.
- **Direction**: long-only fade of the dislocation.
- **Trigger (all required, evaluated over 60-min pre-settlement window)**: funding F > 20 bps; OI collapse z < −2.0 (60-min change vs 20-day rolling std); perp discount z < −1.5 (same construction); perp taker sell ratio > 0.55; spot taker buy ratio ≥ 0.50; market filter BTC 60-min return > −1.0%.
- **Entry**: first 5-min bar close after funding settlement confirms conditions; enter next bar open.
- **Dislocation** (frozen definition): perp price at window start (60 min pre-settlement) − entry price.
- **Target exit**: entry + 0.5 × dislocation.
- **Time stop**: 90 minutes. **Spot failure stop**: spot < 60-min VWAP − 1.0 × ATR(14). **Vol stop**: entry − 1.5 × 5-min ATR(14).
- **Sizing**: 5% paper equity per trade, 1× leverage, max 1 position/asset, 3 total, 50% cash buffer.
- v2 variants (90-min window etc.) are recorded but not implemented; they count toward DSR trial accounting.

## Data availability and validation window

The qualifying window is the intersection of every required series for each symbol. Open-interest
metrics are the binding input, so pre-window price history is context only and is not part of the
Phase 1 completeness gate. After the frozen 20-day z-score warmup, the effective validation window
is 2021-12-21 00:00 UTC through 2026-06-30 16:00 UTC for all three symbols.

Mark-price klines are non-blocking context: no frozen FTRE v1 feature consumes them. Perp-discount
z-scores use `premiumIndexKlines`; entries, targets, and volatility stops use perp trade klines;
spot confirmation and VWAP stops use spot trade klines. Missing required bars are never
interpolated. A scheduled funding event is excluded if its 60-minute observation window or
90-minute trade window overlaps a required-series gap.

| Symbol | Series | Available from | Known effective-window gaps |
|---|---|---:|---:|
| BTCUSDT | Perp trade klines | 2020-01-01 | 0 |
| BTCUSDT | Premium-index klines | 2020-01-01 | 10 |
| BTCUSDT | Spot trade klines | 2019-09-01 | 1 |
| BTCUSDT | Funding | 2020-01-01 | 0 required 8-hour settlements missing |
| BTCUSDT | OI/taker metrics | 2021-12-01 | 17 |
| ETHUSDT | Perp trade klines | 2021-12-01 | 0 |
| ETHUSDT | Premium-index klines | 2021-12-01 | 10 |
| ETHUSDT | Spot trade klines | 2021-12-01 | 1 |
| ETHUSDT | Funding | 2021-12-01 | 0 required 8-hour settlements missing |
| ETHUSDT | OI/taker metrics | 2021-12-01 | 17 |
| SOLUSDT | Perp trade klines | 2021-12-01 | 2 |
| SOLUSDT | Premium-index klines | 2021-12-01 | 8 |
| SOLUSDT | Spot trade klines | 2021-12-01 | 2 |
| SOLUSDT | Funding | 2021-12-01 | 0 required 8-hour settlements missing; 75 extra off-cycle settlements retained as context |
| SOLUSDT | OI/taker metrics | 2021-12-01 | 22 |

### Event exclusions

| Symbol | Scheduled candidate events | Gap-overlap exclusions | Exclusion rate |
|---|---:|---:|---:|
| BTCUSDT | 4,959 | 25 | 0.504% |
| ETHUSDT | 4,959 | 25 | 0.504% |
| SOLUSDT | 4,959 | 44 | 0.887% |

All exclusion rates are below the 2% bias-review stop threshold. However, no scheduled event in
the effective window passes the frozen `funding > 20 bps` condition. Maximum observed funding was
8.81 bps for BTCUSDT, 10.17 bps for ETHUSDT, and 11.93 bps for SOLUSDT. FTRE v1 therefore has zero
qualifying observations and cannot pass walk-forward validation.
