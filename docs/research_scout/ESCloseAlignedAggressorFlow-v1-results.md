# ES Close Aligned-Aggressor Flow v1 — Final Result

Date: 2026-07-25

Status: **REJECTED FOR PAPER AND LIVE TRADING**

## Decision

Do not trade this rule.

The frozen development rule was profitable, but the untouched 2024–2025
holdout lost money after executable spread and the baseline commission. It
failed two required live gates: positive holdout expectancy and a positive
lower clustered confidence bound.

This is evidence against the strategy, not a near miss. No threshold, clock,
direction, cost, stop, or weekday should be changed using the consumed
2024–2025 sample.

## What was tested

The paper-style proposition was that a large regular-session ES move tends to
continue into the close. That proposition was modified before returns were
read to require evidence of outstanding demand:

1. Measure the ES move from the 09:30 one-minute open to the 15:29
   one-minute close.
2. Require its absolute size to be at least the prior 60 eligible sessions'
   sample standard deviation.
3. Require 15:00–15:30 ES buyer-aggressor minus seller-aggressor volume to
   have the same sign as the price move.
4. Require the MES entry spread to be no more than one tick.
5. Enter at the first executable MES quote at or after 15:30:05 ET and exit
   at the first executable quote at or after 15:59:45 ET.
6. Charge the crossed spread through bid/ask fills and $1.24 round-trip
   commission per MES contract.

The specification, exclusions, controls, statistics, and gates were frozen in
`research_scout/es_close_flow_prereg_v1.json`. Its evaluation-code,
feature-code, and feature-artifact SHA-256 hashes were recorded before
performance was opened.

## Why the paper premise was insufficient

The original price-continuation idea did not by itself establish a tradeable
edge:

- A close-to-close or bar-return pattern is not an executable strategy. It
  omits the bid/ask spread, fees, entry delay, and the quote actually available
  at exit.
- A large price move does not identify forced demand. It can reflect
  information, absorption, dealer hedging, a rebalance, or ordinary
  volatility.
- Continuous futures can introduce roll and contract-selection errors unless
  the bar, trade, and quote instruments are checked point in time.
- Intraday observations are clustered by regime and month; treating trades as
  independent makes uncertainty look smaller than it is.
- A result concentrated in one year is weak evidence even when its pooled
  average is positive.

The aligned-aggressor requirement directly addressed the missing-flow problem,
while executable MES quotes, actual contract IDs, shifted volatility, session
exclusions, and month-clustered intervals addressed the principal measurement
problems. The modified hypothesis was economically more defensible, but it
still failed out of sample.

## Data and integrity audit

- Databento `GLBX.MDP3`, 2021-01-01 through 2025-12-31.
- 3,761 of 3,761 expected session files present; no partial files.
- 38,904,582 session-window rows:
  - 26,453,358 ES trades;
  - 2,984,629 MES entry-window MBP-1 rows;
  - 9,466,595 MES exit-window MBP-1 rows.
- 1,767,973 ES one-minute bars.
- 1,289 RTH dates, of which 1,245 contained exactly 390 one-minute bars.
- Forty-four short/holiday sessions excluded.
- Provider-degraded weekdays excluded.
- Zero ES bar/trade roll mismatches and zero MES entry/exit roll mismatches on
  eligible sessions.
- Zero invalid non-excluded session files.
- 1,183 valid sessions after the 60-session warm-up and all exclusions.

The independent free Massive 2025 minute-bar pull produced 238 complete RTH
sessions. Its source gaps and short sessions were excluded rather than
imputed. Massive was used as a price-data cross-check only; it cannot supply
the aggressor-side trades and historical executable quotes needed for this
test.

The protected Databento estimate was $90.59 against the confirmed $100
historical monthly limit and $125 starting credit. The last user-confirmed
portal usage during the run was $20.95. The final portal amount must be checked
in Databento; the local pipeline does not infer it.

## Results

All dollar figures are per one MES contract and include the baseline $1.24
round-trip commission.

| Partition / rule | Trades | Mean net | Total net | Win rate | Profit factor | Month-clustered 95% CI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Development 2021–2023, price only | 206 | $2.86 | $589.56 | 50.5% | 1.13 | −$7.16 to $14.50 |
| Development, price + spread | 197 | $3.74 | $736.97 | 51.3% | 1.17 | −$6.20 to $15.56 |
| Development, frozen aligned flow | 127 | **$6.61** | **$840.02** | 54.3% | 1.32 | −$5.12 to $19.08 |
| Development, opposed-flow control | 70 | −$1.47 | −$103.05 | 45.7% | 0.94 | −$16.95 to $14.68 |
| Holdout 2024–2025, price only | 133 | −$3.83 | −$509.92 | 46.6% | 0.87 | −$15.09 to $7.69 |
| Holdout, price + spread | 131 | −$6.94 | −$908.69 | 45.8% | 0.77 | −$18.03 to $4.66 |
| Holdout, frozen aligned flow | 74 | **−$1.58** | **−$116.76** | 48.6% | 0.94 | **−$20.13 to $18.09** |
| Holdout, opposed-flow control | 57 | −$13.89 | −$791.93 | 42.1% | 0.63 | −$38.83 to $6.59 |

Development aligned flow beat opposed flow by $8.09 per trade, but the
one-sided permutation p-value was 0.206. In the holdout the difference was
$12.32, with p=0.198. Flow alignment may describe a relative state difference,
but neither partition establishes that the aligned state has positive
standalone expectancy.

The development result was also unstable by year: frozen-rule net totals were
$26.52 in 2021, $754.25 in 2022, and $59.25 in 2023. Holdout totals were
−$245.89 in 2024 and $129.13 in 2025.

The result does not improve before commission: holdout aligned-flow gross
expectancy was already −$0.34 per trade. At the $2.00 stress commission,
holdout expectancy fell to −$2.34.

## Frozen-gate decision

| Gate | Result |
| --- | --- |
| Development gate passes | Pass |
| At least 30 holdout trades | Pass: 74 |
| Positive holdout mean net P&L | **Fail: −$1.58** |
| Positive holdout aligned-minus-opposed difference | Pass: $12.32 |
| Positive lower holdout clustered 95% bound | **Fail: −$20.13** |

Overall live-recommendation gate: **FAIL**.

The development JSON SHA-256 is
`67451ccc6e9332cbae1afb43d8f371db54aea9a1a33b5ff9bb12414256c74512`.
The one-time holdout JSON SHA-256 is
`d2bbd1d435a05ddccbc89856307e448d983cfad82a245a99fff51f6f2c982b9e`.

## What the failure changes

The evidence supports only a narrow conclusion: aggressive-flow alignment
separated less-bad continuation states from worse continuation states. It did
not turn close continuation into a positive strategy.

Reversing the opposed-flow trades is not a valid rescue. Checked
exploratorily after the holdout was opened, that fade lost $3.56 per trade in
2021–2023 and made $8.89 in 2024–2025, with the gain concentrated in 2025.
That is another unstable regime split, not a strategy.

## New research plan

Stop spending on this ES close family. The next candidate should be a genuinely
different, high-recurrence day-trading mechanism using free data:
cross-sectional crypto liquidity-shock reversal.

The proposed mechanism is temporary, idiosyncratic order-flow pressure rather
than a short squeeze or close effect. At fixed 15-minute decisions, rank a
point-in-time universe of liquid perpetuals by return residual relative to
BTC/ETH and by aggressive-volume imbalance. Test whether extreme residual
moves with a one-sided liquidity shock partially reverse over the next
30–60 minutes in a beta-neutral long/short basket.

Before any return is opened:

1. Use free Binance bulk files; spend no additional Databento credit.
2. Build the universe from trailing dollar volume only, with delisted symbols
   retained point in time.
3. Audit event frequency, timestamps, spreads or conservative taker costs, and
   survivorship.
4. Freeze one horizon, one shock definition, execution costs, partitions, and
   a minimum event count.
5. Require positive results across instruments and calendar blocks, not merely
   a pooled backtest, with an untouched final period.

This next candidate is not approved for trading. Its advantage as a research
target is more independent events, cross-sectional controls, free source data,
and a mechanism that does not depend on inferring rare forced liquidations.
