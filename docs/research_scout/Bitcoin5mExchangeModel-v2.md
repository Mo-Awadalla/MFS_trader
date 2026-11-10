# Bitcoin five-minute exchange model v2

Version 2 repairs the data and validation defects found in the September 30, 2026 audit.
It is a research implementation with no order-submission capability.

Opt into v2 with the existing entry point.

```powershell
python scripts/run_bitcoin_5m_probability_model.py --exchange-v2 --output-dir research_scout/bitcoin_5m_v2_reproduction
```

The dedicated command is equivalent:

```powershell
python scripts/run_bitcoin_5m_exchange_model.py --output-dir research_scout/bitcoin_5m_v2_reproduction
```

Choose a new output directory for each run. A reservation file prevents overwriting completed
or interrupted evidence. The runner checks the frozen specification hash, saves executed source
snapshots, serializes each quarterly model, and verifies preservation of v1 and previous results.
The historical inputs are the existing original price/OI/funding archives plus the separately
acquired January–August 2026 files. Restore the archived inputs at the repository-relative paths listed by the runner before replay. The runner reports missing input paths before reserving an output directory.

Implementation: `research/bitcoin_5m_exchange_model.py` and
`research/bitcoin_5m_exchange_validation.py`.
Specification and original repair results: `research_scout/bitcoin_5m_repaired_v2_20260930/`.
The final-source verification rerun is in that directory's `verification_rerun/` subdirectory.

Features use completed bars through t-5 minutes for a prediction at t. No current or future
candle is required. All 289 closes used by the longest volatility input must be continuous.
Sparse trader ratios are removed; optional OI remains missing with explicit flags until
training-only median imputation. Input checks reject nonfinite values, inconsistent OHLC,
invalid taker volume, duplicates, missing timestamps, and off-grid bars.

Targets are next-open/current-open returns, including zero-return ties. Unknown targets remain
null and do not remove decision rows. Fitting partitions purge labels reaching the next boundary.
The model estimates P(return > 0), mean positive return size, and mean nonpositive loss size.
Its expected return is probability × expected win minus complementary probability × expected loss.
Direction and magnitude calibration use a subsequent, disjoint period.

Models update at UTC quarter starts, with 24 months of training, two months of calibration,
then a separate month for admission. Candidate trades require at least 2bps expected net edge
after an assumed 6bps round-trip cost. Admission requires at least 100 trades on 20 active days
and a positive lower 95% block-bootstrap bound after 6bps costs in the admission month.
Failed admission returns flat actionable signals; ungated candidates are exported as diagnostics.
Do not lower these frozen thresholds after seeing their results and describe it as confirmation.

Historical economics use optimistic Binance bar-open references with both-side notional fees,
available settled funding, and zero/one-bar entry delay. They do not establish Coinbase fills,
maker execution, actual account fees, or live profitability. All these historical data are already
exposed to research. A subsequent model revision requires a new declared experiment, then new
prospective evidence before any profitability or deployment claim.

Legacy v1 reproduction:

```powershell
python scripts/run_bitcoin_5m_probability_model.py --legacy-v1 --output-dir research_scout/bitcoin_5m_v1_reproduction
```

Original v1 source and serialized artifacts remain unchanged.
