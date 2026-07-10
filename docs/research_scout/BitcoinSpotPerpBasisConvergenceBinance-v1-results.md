# Bitcoin Spot–Perpetual Basis Convergence — Binance v1 Results

Status: **MECHANISM CONFIRMED GROSS; STRATEGY REJECTED AFTER COSTS**

Specification: `research_scout/bitcoin_spot_perp_basis_convergence_binance_v1.json`

Specification SHA-256: `cb00c2fa31e47a7c072ada0398ff58645323a8063eab1f8657663c981bb90666`

Machine evidence:

- `data/parquet/bitcoin_spot_perp_basis_convergence_binance_v1/development/report.json`
- `data/parquet/bitcoin_spot_perp_basis_convergence_binance_v1/development/report.md`
- `data/parquet/bitcoin_spot_perp_basis_convergence_binance_v1/development/panel.parquet`

## Goal and verdict

This scout tested the Bitcoin lead most relevant to the user's constraints: one trade per day maximum, no latency race, no outright BTC direction prediction, no options, public point-in-time data, and 1.0 gross exposure split equally between long spot and short perpetual.

The economic mechanism is visible: unusually rich perpetual basis subsequently contracted with high consistency. But the executable capital return was only about one basis point per trade. Four required executions cost at least fifteen basis points under the frozen retail fee model.

**Reject this as a day-trading alpha sleeve.** It is a real microstructure relationship that is too small for the user's executable strategy goals.

## Frozen rule

At 00:05 UTC daily:

1. Use the fully closed 23:30–00:00 Binance BTCUSDT spot and perpetual closes.
2. Compute `log(perpetual_close / spot_close)`.
3. Trigger when basis is positive and strictly above the 90th percentile of the 90 strictly prior daily observations, with at least 60 priors.
4. At 00:30, allocate 0.5 capital to long spot and 0.5 to an equal-notional short perpetual.
5. Exit both legs at 07:30.
6. Skip any missing exact boundary or actual funding settlement in `(entry, exit]`.

No funding receipt was credited.

## Development results

Period: 2020-01-01 through 2022-12-31.

| Metric | Result |
|---|---:|
| Complete synchronized days | 1,033 |
| Triggered days | 93 |
| Mean signal basis | 10.0246 bps |
| Mean entry basis | 10.3095 bps |
| Mean exit basis | 8.2398 bps |
| Mean basis change | **-2.0697 bps** |
| Mean gross capital return | **+1.0273 bps** |
| Directional accuracy | **68.82%** |
| Bootstrap 95% gross interval | **[+0.5610, +1.5005] bps** |
| Mean after 15 bps fee-only cost | **-13.9727 bps** |
| Mean after 25 bps conservative cost | **-23.9727 bps** |
| Gross total return | +0.96% |
| Conservative total return | **-20.01%** |

The positive gross relationship was not an outlier artifact:

- First chronological half: +1.0678 bps/trade.
- Second chronological half: +0.9877 bps/trade.
- Mean after removing the largest 5% absolute outcomes: +0.9534 bps.
- Top 5% profit contribution: 19.39%.

## Mechanism versus implementation

### Mechanism result: pass

The rich perpetual converged toward spot:

- Average basis contraction: 2.0697 bps.
- Gross hedged return: +1.0273 bps of capital.
- Positive-return frequency: 68.82%.
- Bootstrap lower bound: +0.5610 bps.
- Both chronological halves were positive.

The capital return is approximately half the basis contraction because the frozen portfolio assigns half of capital to each leg.

### Executable implementation: decisive failure

The frozen round-trip costs are:

- Spot fees: 20 bps round trip on the 0.5-weight leg = 10 capital bps.
- Perpetual fees: 10 bps round trip on the 0.5-weight leg = 5 capital bps.
- Fee-only total: 15 capital bps.
- Conservative slippage: another 10 capital bps.
- Conservative total: 25 capital bps.

Break-even total round-trip cost would need to be no more than **1.0273 capital bps**. That is 93% below the fee-only assumption.

Even complete convergence of the average 10.31 bps entry basis to zero would produce only about 5.15 capital bps before simple-return approximation effects—still far below the frozen 15 bps fee-only cost.

Therefore, better timing cannot plausibly rescue this daily two-leg implementation without an unrealistically different fee/execution regime.

## Leg decomposition

Average weighted contributions:

- Spot leg: -9.8062 bps.
- Perpetual short leg: +10.8335 bps.
- Net hedged capital return: +1.0273 bps.

The strategy did not profit because Bitcoin fell outright. The large directional leg moves mostly offset, leaving the small relative convergence return as intended.

## Year diagnostics

| Year | Trades | Gross capital return | Basis change | Accuracy |
|---|---:|---:|---:|---:|
| 2020 | 32 | +0.9809 bps | -1.9951 bps | 62.50% |
| 2021 | 56 | +1.1572 bps | -2.3204 bps | 75.00% |
| 2022 | 5 | **-0.1307 bps** | +0.2602 bps | 40.00% |

The gross mechanism was strongest in 2020–2021 and absent in the small 2022 sample. This is secondary to the cost failure: even the strongest year was nowhere close to tradable after four-leg costs.

## Frozen gates

Passed:

- At least 60 selected days.
- Positive gross mean.
- Positive gross mean in both chronological halves.
- Bootstrap lower bound above zero.
- Positive after removing the largest 5% absolute outcomes.
- Acceptable profit concentration.
- Complete timestamp alignment.
- Average basis contraction.

Failed:

- **Positive after conservative costs.**

All gates were conjunctive, so development failed.

The internal-validation command was executed only to test the progression lock and returned:

`BLOCKED: internal_validation locked: development did not pass`

No 2023–2025 relative-value outcomes were evaluated.

## Why this should not be rescued

Do not respond by:

- lowering the basis threshold;
- changing the holding window;
- adding funding, OI, flow, volume, or volatility filters;
- using maker-fee assumptions without fill evidence;
- assuming zero fees;
- increasing leverage;
- trading only the perpetual leg and reintroducing BTC direction;
- crediting future funding not known or crossed by the position;
- applying ML to identify larger convergence events;
- opening 2023–2025 to search for a cheaper-looking variant.

The problem is not lack of gross statistical significance. It is economic scale: approximately 1 bp of gross capital edge against 15–25 bps of required round-trip friction.

## Relevance to the portfolio goal

This cannot serve as:

- a capital-matched SPY challenger;
- a practical day-trading alpha sleeve;
- a defensive overlay at retail costs.

It could matter to a market maker or institutional participant with near-zero fees, existing inventory, and execution infrastructure, but that is outside the user's non-latency retail-scale objective.

A longer-horizon funding-carry position could amortize entry costs over multiple settlements, but it would be a different swing/carry strategy with exchange, collateral, funding-sign, and tail risks. It is not the requested one/few-trades-per-day day-trading lead and should not be smuggled in as a rescue of this failed scout.

## Final assessment

**The basis-convergence mechanism is real in development, but it is not monetizable for the user's stated setup. Reject `Bitcoin-SpotPerp-Basis-Convergence-Binance-v1`.**

This result narrows the Bitcoin search substantially: same-venue, intraday, two-leg relative value is too efficient after retail execution costs, even when its gross convergence is stable and statistically clear.
