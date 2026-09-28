# ETF TSM execution-parity boundary

## Status contract

`replay-etf-tsm` is a **structural_replay**. Its structural PASS means the runtime engine, sizing, risk checks, OMS, SQLite and simulated fills completed their operational checks. It does not mean the research and runtime paths produce equal money, qualify broker-paper operation, revalidate an Experiment, or authorize promotion.

Reports separately expose `financial_parity`:

- `not_established`: no predeclared assumptions were supplied; the observed configuration is still recorded.
- `attributed`: both real paths match their respective declarations on every checked bar and field, their decisions agree after the declared lag, and the ordered attribution reconciles the final gap. This is **not equality**.
- `established`: identical assumptions and equal ledgers; deliberate differences are never relabeled equality merely because their final effect happens to be zero.
- `failed`: an unexplained ledger/decision discrepancy, unsupported assumption difference, nonfinite comparison, or incomplete runtime replay.

`--assert-financial-parity` requires `--assumptions PATH` and succeeds only for `established`. Missing/mismatched declarations fail before replay writes. `--allow-diffs` cannot waive a financial-parity assertion failure. Ordinary structural replay never silently asserts financial parity.

## Predeclared assumptions

`engine.etf_tsm_replay.declare_etf_tsm_execution(config, params=...)` returns an `ExecutionAssumptionsDeclaration` before either path is run. `engine.parity.write_declaration(declaration, path)` atomically writes its JSON. The CLI reads that JSON using `--assumptions`; the complete declaration must match the requested replay configuration. Both declaration and report are versioned (`etf_tsm_execution_assumptions.v1`, `etf_tsm_execution_parity.v1`). Reports embed the field-level diff.

| Mechanism | Research | Runtime replay |
| --- | --- | --- |
| Decisions | Frozen monthly ETF TSM signals using preceding history | Same frozen signal function, previous-bar target adapter |
| Fill timing | Implicit shares at signal-bar close earn the next close-to-close return | Previous-bar signal is filled at the current close; does not earn that bar's return |
| Prices/corporate actions | Input close as supplied | Same input close; no corporate-action processing or assertion that a cache is adjusted |
| Sizing/cash | Mark-to-market equity, implicit residual cash | Fixed initial capital, cash reconstructed from signed fill notional; may become negative |
| Rebalancing | Daily restoration to target weights, with free drift rebalancing | Share deltas subject to existing quantity, notional and relative-position thresholds |
| Costs | Weight-change costs deducted in the following return; sell-side extra costs and borrow model | SimBroker slippage embedded in every fill price; configured commission is currently not applied; no borrow charges |
| Rounding/spread | Fractional shares implied by weights, no separate spread | Fractional quantities (flat cutoff 1e-9), no separate spread |
| Risk | No runtime risk layer | Existing per-position, gross exposure and max-open-position constraints; no controls removed |

The default research cost calculation includes its existing variable-slippage surrogate (another fixed-slippage term when the coefficient is nonzero) and sell-side constant. Those are declared as implemented, not corrected or silently harmonized here. SimBroker's account cash/equity is not updated on fills: reported financial cash/equity is reconstructed, not broker authority. The replay supplies constant equity and drawdown to the existing risk engine, so loss limits see zero loss. Net exposure checks can report reductions without changing quantities; sector/correlation inputs are absent. This work does not change those behaviors.

## Ledger evidence and attribution

The production research backtest exports its decision weights and gross/cost/borrow return components without changing validation callers or calculations. `research_ledger` derives the shares and residual cash implied by the actual vectorized return identity. Research orders are **implied rebalancing quantities**, not broker fills.

The actual runtime target adapter records each bar's decisions. The replay observes OMS positions after each processed bar; `runtime_ledger` reads filled quantities and prices from the real temporary SQLite database, reconstructs cash and slippage cost, and marks those observed positions at close. No mocked execution or copied reference results stand in for either path. Ledgers are exposed on `ETFEngineReplayComparison`; `to_long_frame()` provides an export seam. Money fields in the long frame repeat per symbol and must not be summed across symbols.

For each bar, the independent share-level reference model checks target weights, signed order quantities, positions, cash, fees (including slippage), and equity against each path's declaration. An intermediate discrepancy fails even if final equity coincides. Missing/nonfinite compared values fail. Pre-inception missing prices are permitted only for unheld, unrequested symbols; a missing close for a held/requested symbol prevents attribution.

Attribution analytically toggles one declared mechanism at a time in this fixed order:

1. Fill timing.
2. Sizing basis (and associated cash handling).
3. Rebalance policy/thresholds.
4. Costs.
5. Runtime risk constraints.

The sequential equity deltas telescope from research to runtime. Separate isolated toggles and an interaction residual make order dependence explicit; the contributions are not unique causal estimates. Intermediate counterfactuals are mathematical models, **not supported trading modes**. Risk is varied only inside this analytical reference; actual runtime risk controls remain enabled and unchanged. Zero contribution is reported as zero, not evidence that risk checks were absent. The risk-modified bar count includes floating-point-size adjustments.

An additional real-runtime check varies only the existing `min_notional_delta` and `min_pct_position_delta` configuration knobs and compares its effect with the model. No strategy parameters, risk limits, validation thresholds, or tolerance adjustments are used to force equality.

### Tolerances

- Target weights: absolute 1e-12, no relative tolerance, because both paths consume the same deterministic decisions.
- Quantities: absolute 1e-9 plus relative 1e-9, matching the runtime's flat-quantity boundary and permitting floating-point arithmetic differences, not whole-share rounding.
- Money: absolute `initial_capital * 1e-8` plus relative 1e-9. At $10,000 the absolute allowance is $0.0001, well below a cent; this accommodates repeated floating-point cash subtraction versus vectorized compounding over thousands of bars.

Every field reports its maximum absolute discrepancy, divergent-bar count, first divergent timestamp and applied tolerances. The final-gap residual uses the same money tolerance. Nonfinite maxima are JSON null and never agreement.

## Historical and retained-data limits

The historical report's 5,405 bars, 1,072 orders and zero operational blockers describe a structural pass only. Its $50,944.37 research equity versus $27,759.42 runtime equity remains a $23,184.95 historical discrepancy, not an established equality.

Read-only local retained Yahoo bars were available, but contain only 1,260 union-panel bars, not the historical 5,405-bar input. Their replay produced 207 fills and $16,387.95364550593 research versus $15,442.025381473148 runtime equity. All six ledger fields matched their own declarations; the cross-path differences were attributed, not equal. Ordered contributions (runtime minus research) were:

| Mechanism | Equity contribution |
| --- | ---: |
| Fill timing | +241.12358431546454 |
| Fixed sizing basis | -1305.5043430173537 |
| Rebalance thresholds | +45.795429204885295 |
| Costs | +72.65706546421279 |
| Risk constraints | 0.0 |
| Total | -945.928264032791 |

The actual gap was -945.9282640327838; numerical residual was 7.28e-12. This is a **different retained-input window**, not counterfactual attribution of the original $23,184.95 gap. Reproducing that exact historical discrepancy requires the original full input panel/provenance; no substitute data or successor identity is created. Retained market-data bytes are never committed. Local versioned attribution evidence and SHA-256 input hashes belong only under `/Users/mohamedawadalla/Projects/rr-evidence/parity/`.

The local immutable artifact is `retained-yahoo-attribution-v1-20260928.json` in that external directory (SHA-256 `29b2bc53101e8ee93f1ba5dea94e43c48b18e187fe8e7a8799e9c9a289ac68f4`). It records each input file's hash, the declaration, frozen parameters and field-by-field attribution, not market-data bytes. Its retained window is 2021-07-01 through 2026-07-09; it is not part of a public distributable.

## Offline verification

`tests/integration/test_execution_parity.py` generates a multi-ETF OHLCV panel with several regimes in-test and uses the same unmodified frozen defaults on both real paths. It covers all per-bar fields, intermediate corruption, timing regression, missing values, supported threshold counterfactuals, pre-I/O declaration rejection and CLI assertion precedence. No broker endpoints, credentials, real Experiment evidence, or cache are needed by these tests.

Run with `RUN_LIVE_BROKER_TESTS=0 MFS_TEST_LOAD_DOTENV=0` on both supported Python environments. Full-suite/lint acceptance belongs to release integration; a local replay smoke is not a claim that those commands passed.
