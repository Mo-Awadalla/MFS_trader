# Bitcoin U.S.-Session Close Momentum — Binance Spot v1 Results

Status: **DEVELOPMENT SCOUT FAILED — STOPPED**

This is a frozen falsification scout, not a registered Experiment, validated Strategy, paper candidate, or live-trading authorization.

## Executive result

The Binance spot BTCUSDT long/flat proxy did not reproduce an economically usable first-half-hour-to-last-half-hour momentum effect in the frozen development partition.

- Development sessions requested: 2017-09-01 through 2020-12-31.
- Complete sessions: 1,209 of 1,218 calendar sessions (99.26%).
- Positive-signal/triggered sessions: 621.
- Mean selected final-half-hour return before costs: **-0.6231 bps**.
- Mean after 20 bps fee-only round trip: **-20.6231 bps**.
- Mean after 30 bps conservative round trip: **-30.6231 bps**.
- Directional accuracy: 51.05%, but winning returns were not large enough to create positive expectancy.
- Session-bootstrap 95% interval for gross selected return: **[-5.3614, 3.9723] bps**.
- Predictive slope on all complete sessions: 0.000735; R-squared 0.000017; IID p-value 0.887089.
- Gross zero-cash strategy total return: **-4.8335%**; annualized return -1.4856%, Sharpe -0.1450, maximum drawdown -16.73%.
- The frozen development verdict is **FAIL**.

The internal-validation and final-holdout partitions were not downloaded. The runner was explicitly tested and returned:

`BLOCKED: internal_validation locked: development did not pass`

## What was tested

Primary source:

Shen, Urquhart, and Wang, “Bitcoin intraday time series momentum,” *Financial Review* 57 (2022), DOI `10.1111/fire.12290`.

Frozen implementation:

- Venue/pair: Binance spot BTCUSDT.
- Public data: official checksum-protected Binance monthly 30-minute kline archives.
- Session timezone: `America/New_York`, including DST.
- Opening proxy: 09:00 ET.
- Signal: price at 09:30 ET divided by the prior calendar session's 17:00 ET price minus one.
- Trigger: signal strictly positive.
- Entry boundary: 16:30 ET.
- Exit boundary: 17:00 ET.
- Position: long one unit of capital when triggered; flat otherwise.
- Maximum one round trip per calendar session.
- No short side, leverage, volume/volatility condition, funding feature, weekday filter, stop, target, or alternate clock.

The signal ends seven hours before the held interval starts. No return in the final half-hour is used to decide the position.

The machine-readable frozen specification is:

`research_scout/bitcoin_us_session_close_momentum_binance_v1.json`

Its SHA-256 recorded in the result is:

`37a5f20d3ec66dcc3754a1e6b3ed75519ff93b95bfc9476f4d26f6c7bc5d48ed`

### Execution-semantics correction

The first development run used the preceding kline's 16:30 close as the entry proxy. Independent review correctly identified that an executable 30-minute-bar implementation should use the **open of the 16:30-17:00 kline**. The specification and implementation were corrected transparently and the same development partition was rerun without opening later data. The correction worsened gross mean from -0.1298 to -0.6231 bps and did not change the rejection.

## Relationship to the paper

This is not an exact replication.

The paper:

- uses BTC/USD tick data aggregated to one minute;
- pools Bitfinex, Bitstamp, CEX.IO, Coinbase, and Kraken;
- chooses exchange-specific openings from volume spikes: 09:05, 09:00, 09:00, 09:40, and 09:15 EST respectively;
- uses 17:00 EST as the close because CME Bitcoin futures begin their daily break then;
- defines ONFH from the prior close through the end of the first half-hour;
- estimates pooled Newey-West regressions and recursive out-of-sample forecasts;
- trades long when ONFH is positive and short when it is negative in its first timing strategy.

This scout intentionally uses one Binance BTCUSDT proxy, 30-minute bars, a 09:00 New York civil-time opening, and a long/flat rule. These deviations were declared before downloading development returns.

The paper's own transaction-cost section is a major caution. It reports a roughly **3 bps break-even cost** for the first ONFH timing strategy without leverage and states that the strategy is not profitable against a cited Bitstamp fee of 25 bps. That source evidence already implied severe cost sensitivity. The repository's 20 bps fee-only and 30 bps conservative round trips are therefore intentionally much harder than the paper's gross timing result.

## Data audit

### Acquisition

- 41 monthly archives were used, including August 2017 only as a one-day warm-up source for the September 1 signal.
- Every archive's local SHA-256 matched Binance's official `.CHECKSUM` value.
- Normalized bars used in the bounded dataset: recorded in `development/manifest.json`.
- Requested development sessions: 1,218.
- Complete four-boundary sessions: 1,209.
- Nine sessions were skipped because at least one required boundary was unavailable.

### Historical archive irregularities

The public Binance archives contain real exchange-history irregularities:

- whole missing 30-minute intervals;
- eight truncated klines across the downloaded archive set;
- 85 off-grid emergency klines, concentrated in February 2018;
- a large February 2018 outage/disruption block.

The downloader does not forward-fill or synthesize prices. It:

1. verifies the official archive checksum;
2. detects milliseconds versus microseconds;
3. removes truncated and off-grid klines;
4. preserves whole-grid gaps;
5. admits a session only when prior close, signal, entry, and exit boundaries all exist.

This behavior was discovered during data validation before a successful scout run. It changed only malformed-data handling, not the hypothesis, clocks, trigger, costs, partitions, or gates.

## Frozen gate results

| Gate | Result | Evidence |
| --- | --- | --- |
| At least 500 triggered sessions | PASS | 621 |
| Positive mean gross return | **FAIL** | -0.6231 bps |
| Directional accuracy above 50% | PASS | 51.05% |
| Positive gross return in both chronological halves | **FAIL** | -2.7198 bps, +1.4668 bps |
| Bootstrap 95% lower bound above zero | **FAIL** | lower bound -5.3614 bps |
| Positive after conservative costs | **FAIL** | -30.6231 bps/trade |
| Positive after removing largest 5% absolute sessions | PASS | +0.5431 bps |
| Top 5% profitable-session contribution <=50% | PASS | 24.35% |
| Complete timestamp alignment | PASS | all admitted sessions |

Four terminal gates failed. Passing the trimmed-return gate does not rescue the negative full-sample mean. Removing observations because they hurt the result would be post-result selection.

## Year decomposition

| Year | Triggered sessions | Mean gross | Mean after conservative costs |
| --- | ---: | ---: | ---: |
| 2017 partial | 67 | -3.6374 bps | -33.6374 bps |
| 2018 | 170 | +0.0395 bps | -29.9605 bps |
| 2019 | 189 | -4.1540 bps | -34.1540 bps |
| 2020 | 195 | +3.2571 bps | -26.7429 bps |

The effect is unstable and economically tiny even in positive years. A 3.2571 bps gross mean in 2020 remains far below either frozen cost model.

## Why 51.05% accuracy did not help

Direction alone is insufficient. The median selected return was slightly positive, but the loss tail was larger than the gain tail:

- minimum: -653.76 bps;
- 1st percentile: -155.38 bps;
- 5th percentile: -78.69 bps;
- median: +0.46 bps;
- 95th percentile: +82.92 bps;
- 99th percentile: +162.33 bps;
- maximum: +296.38 bps.

The positive hit rate coexisted with negative gross expectancy. This is exactly why a classification-accuracy claim cannot substitute for executable P&L.

## Statistical interpretation

The full-session ONFH/final-half-hour Pearson correlation was about 0.004. The simple single-venue slope was near zero and statistically indistinguishable from zero. Its R-squared was approximately 0.0017%, versus the materially larger pooled relationships reported by the source paper.

This diagnostic is not a source-faithful pooled Newey-West replication because there is one Binance series and one frozen opening. Nevertheless, the trading question is answered more directly: the predeclared long/flat Binance implementation had no positive gross expectancy and could not absorb costs.

The bootstrap resampled whole sessions, not 30-minute bars. That preserves the independent decision unit and avoids pretending the dataset has tens of thousands of independent final-half-hour trades.

## Performance interpretation

The strategy was active on 51.36% of complete sessions. It produced approximately one trade every two days, matching the desired activity level without latency competition. Mechanically it fit the job. Economically it failed.

The 30 bps conservative cost is severe, but costs are not the reason for the primary rejection: **gross expectancy was already negative**. Even fee-free execution would not clear the expected-sign or bootstrap gates.

The source paper's own first timing strategy had only about 3 bps of break-even capacity. A modern retail implementation with two taker executions is unlikely to preserve such an edge unless fees and spread/slippage are dramatically lower. That would still not repair this sample's negative gross mean.

## Verification

- Independent manual recomputation matched report gross and net means exactly.
- All archive checksums matched.
- Signal timestamp < entry timestamp < exit timestamp on every admitted session.
- Development boundary handling was corrected to load one prior day before the requested partition; the final run includes September 1, 2017 where data permitted.
- Targeted tests: 6 passed.
- Ruff: passed on all new Python files.
- Full repository suite: 597 passed, 12 skipped, 6 failed. The six failures are unrelated pre-existing/worktree integration problems: missing registry entries for ETF tactical and VS-ICSM strategies plus an invalid TOML hex value in an MA replay integration test. No Bitcoin-specific test failed.
- Mypy could not run because the installed NumPy stubs use Python 3.12 syntax while the repository's mypy target is Python 3.11.

## Artifacts

- Source/frozen rule memo: `docs/strategy_sources/BitcoinUSSessionCloseMomentumBinance-v1.md`
- Machine specification: `research_scout/bitcoin_us_session_close_momentum_binance_v1.json`
- Archive downloader: `data/binance_public_archive.py`
- Scout implementation: `research/bitcoin_intraday_momentum_scout.py`
- Runner: `scripts/run_bitcoin_intraday_momentum_scout.py`
- Tests: `tests/unit/test_bitcoin_intraday_momentum_scout.py`
- Development manifest: `data/parquet/bitcoin_us_session_close_momentum_binance_v1/development/manifest.json`
- Development panel: `data/parquet/bitcoin_us_session_close_momentum_binance_v1/development/panel.parquet`
- Machine report: `data/parquet/bitcoin_us_session_close_momentum_binance_v1/development/report.json`
- Human report: `data/parquet/bitcoin_us_session_close_momentum_binance_v1/development/report.md`

Raw monthly archives are cached beneath `data/parquet/bitcoin_us_session_close_momentum_binance_v1/raw/` with their source checksum files.

## Final verdict

**Reject Bitcoin-US-Session-Close-Momentum-BinanceSpot-v1.**

Do not open the 2021-2023 or 2024-2025 partitions. Do not rescue this consumed development sample by:

- adding the paper's short side;
- selecting only 2020;
- conditioning on volume or volatility;
- changing 09:00 or 17:00;
- using Binance futures;
- switching to ETH;
- adding leverage, funding, stops, or targets;
- trimming the adverse tail;
- lowering costs.

A future Bitcoin candidate must introduce a genuinely different ex-ante information mechanism—not a nearby timing variant of this failed session-close momentum rule.
