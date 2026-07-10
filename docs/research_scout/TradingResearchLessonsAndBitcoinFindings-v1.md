# Trading Research Lessons and Bitcoin Findings v1

Date: 2026-07-10

Status: research handoff. No strategy in this document is approved for paper or live trading.

## The actual objective

The research objective is not to find any statistically positive relationship. It is to find a strategy that deserves capital relative to SPY:

- meaningful after-cost returns;
- enough opportunity to matter;
- public, point-in-time historical inputs;
- no latency race, co-location, or unavailable proprietary data;
- one or a few trades per day where possible;
- frozen rules and honest chronological validation;
- either a capital-matched SPY challenger or a demonstrably useful defensive/diversifying sleeve.

A strategy with a low drawdown because it sits in cash, a positive result only during one regime, or a few basis points of gross expectancy is not automatically useful. It must clear opportunity cost, operational risk, and validation requirements.

## Repository research lessons

1. **Mechanism is not implementation.** A source can support funding, price discovery, event drift, or derivatives anchoring without proving a chosen threshold, clock, horizon, sign, or execution rule.
2. **Gross significance is not economic utility.** A statistically clear one-basis-point relative-value effect can still be untradeable after four executions.
3. **Carry needs recurrence.** A profitable historical carry regime is not a strategy if the unchanged rule produces no opportunities in validation.
4. **Rare-event evidence needs regime-aware uncertainty.** Fifteen clustered observations cannot support a trading rule, even when the mean is positive.
5. **Do not rescue failed candidates.** No threshold lowering, sign inversion, adjacent clock, added filter, changed horizon, or ML classifier after seeing development results.
6. **Holdouts are progression gates, not tuning data.** A failed development or validation gate locks later partitions.
7. **A defensive label requires evidence.** A low-return or market-neutral strategy is not an SPY overlay unless it demonstrably improves the combined portfolio or protects during SPY stress.
8. **Trade-count and deployment matter.** A strategy earning a few percent over several years while inactive for long periods may be inferior to simple cash or SPY after operational and counterparty risks.
9. **Execution accounting must be leg-specific.** Spot/perpetual positions need separate quantities, fees, slippage, funding cash flows, margin assumptions, and actual settlement timestamps.
10. **Public does not mean licensed or complete.** Binance archives are freely accessible and checksum-verifiable, but license terms, archive gaps, venue concentration, and missing liquidation/event history must remain explicit.

## Bitcoin candidates tested

| Candidate | Development result | Validation/result | Decision |
|---|---|---|---|
| Binance BTCUSDT U.S.-session close momentum | -0.6231 bps/trade gross after corrected execution semantics; 51.05% accuracy | Failed development gates | Reject |
| Extreme positive funding + rising OI, seven-hour short | +58.82 bps gross on 15 events; bootstrap interval included negative values | Failed minimum-event and uncertainty gates | Reject |
| Intraday spot–perpetual basis convergence | +1.0273 bps capital/trade; bootstrap gross interval positive | Failed 15 bps fee-only / 25 bps conservative economics | Reject for normal execution |
| Seven-day delta-neutral funding carry | +48.19 bps gross and +23.20 bps conservative per active trade in 2020–2022; 41 trades | Zero qualifying trades in 2023 validation | Historically interesting but not deployable |

Detailed artifacts:

- `docs/research_scout/BinanceBitcoinDerivativesPublicData-v1.md`
- `docs/research_scout/BitcoinUSSessionCloseMomentumBinance-v1-results.md`
- `docs/research_scout/BitcoinCrowdedLongUnwindBinance-v1-logical-end.md`
- `docs/research_scout/BitcoinSpotPerpBasisConvergenceBinance-v1-results.md`
- `docs/research_scout/BitcoinDeltaNeutralFundingCarryBinance-v1-results.md`

## Bitcoin data lesson

The Binance public archive is sufficient for a reproducible Binance-specific research scout:

- spot BTCUSDT 30-minute klines;
- USD-M perpetual klines;
- mark, index, and premium-index klines;
- settled funding rates;
- five-minute open interest and positioning metrics.

The dataset was downloaded with official SHA-256 checksums, normalized to Parquet, and integrity-audited. It is not a global crypto market dataset and does not support claims about all venues. Historical liquidation snapshots, trader-level positions, and commercial analytics were not available in an honest free public form and were not fabricated or substituted.

## What the Bitcoin work established

### Session momentum

The source-shaped session-close proxy did not reproduce a stable edge on Binance. It had essentially zero signal correlation, negative gross expectancy, and costs larger than any plausible effect.

### Crowded-long unwind

Some late-2020/2021 extreme-positive-funding plus rising-OI observations preceded large seven-hour declines. The interaction was suggestive but based on 15 clustered events. The 2022 funding distribution also made the strict trigger unreachable. This is a research observation, not a validated signal.

### Basis convergence

Rich perpetual basis contracted toward spot with approximately 68.8% positive capital-return days and a positive gross bootstrap interval. However, the mean capital payoff was only 1.03 bps against at least 15 bps of fee-only round-trip friction. The mechanism is real; the normal-account implementation is not economically viable.

### Funding carry

A seven-day long-spot/short-perpetual position collected enough actual funding in 2020–2021 to survive conservative costs. Development compounded to approximately +9.94% over 2020–2022, equivalent to roughly +3.21% simple annualized if idle capital earns nothing. The rule generated zero trades in 2022 and zero in 2023 validation. It is a dormant historical regime, not a current SPY challenger.

## Correct portfolio conclusion

Bitcoin is not mathematically exhausted, but the tested public-data mechanisms do not currently produce a strategy with sufficient utility relative to SPY under ordinary execution assumptions.

The remaining credible Bitcoin possibilities require relaxing a goal:

- institutional low-fee/maker execution for basis convergence;
- multi-day funding carry with current opportunities, which has not validated;
- cross-venue pre-positioned arbitrage with materially higher operational and counterparty risk.

None should be presented as a retail-scale, non-latency SPY challenger without new independent evidence.

## Recommended research direction

Stop searching nearby Bitcoin variants on the consumed sample. Return to a U.S.-equity information mechanism that is directly benchmarkable against SPY, especially:

1. SEC Item 2.02 earnings-event continuation after a deliberately delayed entry;
2. scheduled macro-event response with non-latency execution;
3. only then, delayed market-to-sector diffusion if its incremental information survives controls.

The first candidate should be frozen with a utility hurdle before returns are inspected. It should be stopped if it cannot produce meaningful after-cost capital returns, chronological stability, and a credible SPY-comparison role.

## Verification references

The individual Bitcoin scouts, specs, reports, normalized dataset manifest, and integrity report remain in the repository working tree. The aggregate lessons in this document deliberately exclude secrets, credentials, raw archives, and local test fixtures.
