# Day-Trading Candidates After Repository Evidence v2

Status: research and candidate-selection memo. No candidate in this document is a validated Experiment or approved for paper/live trading.

Date: 2026-07-10

## Executive conclusion

The repository should not run another generic opening-range, same-clock, short-term reversal, or small-ETF intraday-momentum variant. Those families have already produced terminal negative evidence. The next candidates must change either the information source, the market, or the economic mechanism.

Four candidates remain defensible enough to scout without competing on latency:

1. **SEC Item 2.02 earnings-event continuation** — event-conditioned stock price continuation after a timestamped earnings disclosure. Best US-equity mechanism, but promotion-quality testing first needs a better point-in-time security master.
2. **Bitcoin U.S.-session close momentum** — a source-shaped BTC/USD intraday-momentum replication on public Binance BTCUSDT archives. Cleanest fully public data path and one trade per day at most.
3. **Pre-FOMC morning drift** — long SPY only on scheduled FOMC decision days, from shortly after the open until before the policy statement. Sparse but genuinely different, calendar-known, and non-latency-dependent.
4. **Market-to-sector delayed diffusion** — a single fixed morning test of whether a positive SPY move is incorporated into lagging sector ETFs during the next 30-minute bar. Cheapest US-equity OHLCV candidate, but the weakest source-to-proxy mapping of the four.

These are candidates for falsification, not claims of profitability. Candidate 1 has the most attractive information mechanism. Candidate 2 has the cleanest public data and closest direct paper mapping. Candidate 3 is the simplest event-risk-premium test. Candidate 4 is a lower-confidence reserve because efficient sector ETFs may absorb market information too quickly.

## 1. What this repository actually is

This is not a collection of chart scripts. It is an evidence-gated trading research and execution platform:

- `data/` downloads, normalizes, validates, resamples, and stores market/event data.
- `strategies/` contains reusable signal templates under the `StrategyTemplate` contract.
- `research/` owns vectorized research and candidate-specific validation pipelines.
- `validation/` runs WFA, Monte Carlo, DSR, parameter stability, and intraday-specific gates.
- `experiments/` freezes the complete hypothesis as an immutable Experiment and stores write-once evidence.
- `portfolio/`, `risk/`, `execution/`, and `engine/` provide sizing, controls, OMS, broker adapters, replay, and paper/live lifecycle gates.

Material changes to rules, data, universe, costs, execution, or decision-path code require a new Experiment. Validation pass is not paper approval. Paper operation proves implementation behavior, not alpha.

Relevant implementation surfaces:

- Strategy contract: `strategies/contract.py`
- Strategy registry: `strategies/registry.py`
- Standard gauntlet: `validation/gauntlet.py`
- Intraday gates: `validation/intraday.py`
- Alpaca bars: `data/alpaca_downloader.py`
- Public crypto bars through CCXT: `data/ccxt_downloader.py`
- Point-in-time SEC filing events: `data/sec_filings.py`
- Existing 30-minute multi-asset pattern: `research/market_intraday_momentum_pipeline.py`

The current intraday research path already handles:

- 30-minute synchronized panels;
- one-bar-delayed held weights;
- flat-by-close checks;
- intraday annualization;
- minimum trades and sessions;
- maximum trades and turnover per session;
- holding-period limits;
- day-level profit concentration;
- profit factor and expectancy;
- immutable report/verdict artifacts.

The major execution limitation is that scheduled multi-asset intraday engine replay is not yet available. Existing intraday reports explicitly say `engine_replay_available: false`. A candidate can be researched and statistically validated first, but paper operation requires a session scheduler and an engine path that can enforce its exact entry/exit clock.

## 2. Evidence already consumed

Evidence hygiene matters in the current worktree. There are 16 tracked Experiment metadata records. `experiments/9a08eaef-e9d5-4517-989a-3b35575519d7/` (same-clock seasonality), `experiments/33e52c7b-fd04-4679-8125-17aec1d3063d/`, and `experiments/a7dc94be-2578-4821-9706-cd268c013222/` are complete but untracked snapshots. The same-clock implementation and IEX Level-1/order-flow scout are also untracked. This memo uses those outputs as provisional local evidence, not canonical independent Experiments. Tracked artifacts remain canonical by default.

### Terminal intraday/price-pattern evidence

| Family | Evidence | Result | Selection consequence |
| --- | --- | --- | --- |
| Market first-half-hour to late-day continuation | `experiments/004c70b3-81d4-491c-87cf-9a4af22c8574/validation/report.md` | Alpaca IEX SPY/QQQ/IWM 30-minute Experiment failed: research Sharpe -0.4408, total return -17.64%, WFA/MC/DSR failed | Do not change the opening window, threshold, or ETF set to rescue it. A different market or genuinely different data source is required. |
| ETF opening-range breakout | `experiments/b561f4a3-d360-4e1e-b663-a81a54e63375/validation/report.md` | Research Sharpe -1.8083, total return -47.00%, WFA/MC/DSR failed | No more ORB buffers, stops, targets, volume filters, or symbol substitutions on this sample. |
| Same-clock ETF seasonality | Provisional local evidence: `experiments/9a08eaef-e9d5-4517-989a-3b35575519d7/validation/report.md` | Untracked snapshot reports research Sharpe -5.0944, total return -74.68%, and failed WFA/MC/DSR plus several intraday gates | Do not select clock slots or change lookback after seeing this result; do not call it canonical until the worktree evidence is deliberately admitted. |
| Volatility-standardized intraday stock momentum | `experiments/f5fc4a35-f999-476e-a1ec-b8546360dde3/validation/report.md` | Only 15 trades because 19,832 of 19,833 rebalances were skipped; WFA and stability failed | The static 20-stock hourly panel did not implement the declared broad cross-section. It is data/coverage failure plus failed observed evidence, not support for another small-panel variant. |
| IBB morning-loss afternoon reversal | `docs/research_scout/IBBIntradayAfternoonRecovery-v1-results.md` | Gross and net means were negative; both halves failed | Do not search another threshold/window on IBB or call it a news filter. |
| SPY opening-hour descriptive continuation | `docs/research_scout/SPYOpeningHourCorrelation-v1-results.md` | First-hour/last-hour Pearson 0.0285, Spearman -0.0391, positive-minus-negative spread negative | The simple opening-hour correlation did not establish a signal. |
| IEX order-flow composite | Provisional local scout: `data/parquet/alpaca_iex_orderflow_v1/development/report.md` | Untracked frozen development output failed every economic/consistency gate: -11.4183 bps signed midpoint return and -41.9389 bps after IEX crossing plus friction | Do not invert the sign or test nearby thresholds/windows. Free one-venue Level 1 did not justify further partitions; this is not canonical Experiment evidence. |

### Nearby daily-family evidence

The repository also has decisive failures in Bollinger Bands, daily cross-sectional mean reversion, residual reversal, SEC-event-veto reversal, daily momentum variants, and pairs feasibility/validation. The fundamental-event reversal scout had no gross reversal edge and the wrong Rank-IC sign (`docs/reports/fundamental_event_smart_reversal_lessons.md`). Therefore an earnings candidate below is continuation after a structured event, not another reversal filter.

### Positive evidence that does not solve day trading

`ETFTimeSeriesMomentumVolTarget-v1-YahooAdjustedDaily-2005-2026` is the only canonical validation-passed Experiment (`experiments/119131fa-0f67-48d7-ab87-f20d81c70c1f/`). It is a defensive daily ETF allocator, not a day-trading alpha result. Its existence proves that the platform can preserve a source-backed hypothesis and pass the gauntlet; it does not imply that intraday price patterns work.

## 3. Selection standard used here

A candidate is retained only if:

1. Its mechanism differs materially from consumed failures.
2. Its signal is known before execution and does not require queue position, co-location, or subsecond reaction.
3. Public historical inputs exist for at least an honest frozen scout.
4. Entry and exit can be represented without same-bar accounting.
5. The rule can trade zero or one basket/position per day in its first version.
6. A failed gross expected-sign test can terminate it cheaply before a full Experiment.
7. The source mechanism is separated from this memo's implementation choices.

## 4. Candidate 1 — SEC Item 2.02 earnings-event continuation

### Job

US-equity, long/flat, event-driven intraday alpha sleeve. Zero to several names may qualify on an earnings day; most symbols do not trade on most days.

### Why this survives the repository audit

The prior SEC strategy used filing presence to veto a five-day reversal signal. It failed because the underlying reversal ranking had no gross edge and because filing presence did not measure information direction. This candidate uses SEC data differently:

- the event defines when structured corporate information arrived;
- Item 2.02 narrows the event to results of operations/financial condition;
- the stock's post-event market-adjusted price move supplies direction;
- the hypothesis is continuation after public information, not reversal of a price move.

Chan, “Stock Price Reaction to News and No-news: Drift and Reversal after Headlines,” reports drift after public-news moves and reversal after no-news moves (JFE 2003, DOI `10.1016/S0304-405X(03)00146-6`). Doyle and Magilke, “Event Day 0? After-Hours Earnings Announcements,” show why after-hours timing matters for event studies (JAR 2009, DOI `10.1111/j.1475-679X.2008.00312.x`). These sources support the mechanism and timestamp discipline. They do not validate the exact first-hour rule below.

### Frozen cheap-scout rule shape

This is a proposed scout specification, not yet an Experiment:

- Event: Form 8-K or 8-K/A with Item 2.02.
- Event availability: SEC `acceptanceDateTime` must be after the prior regular close and no later than 09:25 ET on the trading session.
- Initial bounded universe: the repository's frozen 133-stock liquid panel, explicitly labeled a survivorship-biased mechanism scout.
- Bars: 5-minute regular-session adjusted OHLCV plus SPY.
- Direction measure: stock return from 09:30 open through 10:00 close minus SPY return over the same interval.
- Trigger: residual return strictly positive. No magnitude threshold in v1.
- Entry: next executable 5-minute bar after 10:00; never the signal bar.
- Exit: open of the final 5-minute bar, leaving the strategy flat for the last bar and overnight.
- Position: equal weight among qualifying names, maximum gross 1.0, long only.
- No gap, relative-volume, surprise, sentiment, analyst, sector, VWAP, stop, target, or market-regime filter.
- No re-entry.

### Economic reasoning

An earnings disclosure can require investors to process revenue, margins, guidance, and cross-firm implications. The first market reaction supplies a direction without requiring a licensed consensus-surprise series. If information is incorporated gradually, a positive market-adjusted first 30-minute move may continue during the session. Waiting until after 10:00 gives up the fastest reaction by design; any surviving edge is less dependent on latency.

### Public data feasibility

Verdict: **PASS for a bounded mechanism scout; PARTIAL for promotion-quality validation.**

Available now:

- `data/sec_filings.py` already downloads official SEC submissions JSON, preserves `acceptance_datetime`, `form`, `items`, accession, CIK, and raw caches.
- Alpaca Basic/IEX supplies historical bars since 2016 with a free account; the repository already downloads 5-minute bars.
- SPY residualization uses the same feed and timestamps.

Blockers before promotion:

- the SEC current ticker map is not a historical security master;
- renamed/delisted issuers and historical identifiers must be retained;
- the filing may follow an earlier earnings press release, so SEC acceptance is an auditable event marker, not necessarily the first public timestamp;
- IEX is venue-local and adjusted bars are not official opening-auction prints;
- broad historical 5-minute stock downloads are much larger than the current ETF cache.

The first scout should therefore ask only whether gross continuation exists in the frozen static panel. It cannot authorize an Experiment for promotion without a point-in-time universe/security-master audit.

### Cheap terminal gates

Stop the branch if any fail:

1. Positive gross mean residual return from entry to exit.
2. Positive gross result in both chronological halves.
3. Positive net mean after frozen round-trip costs.
4. Positive result after removing the top 5% of event sessions by absolute return.
5. No one issuer, sector, year, or small set of sessions dominates profits.
6. At least 100 independent event sessions and adequate eligible-name coverage.
7. No event becomes visible after its trade decision.

Do not rescue failure with a residual threshold, negative-event short side, volume filter, gap bucket, different holding window, or another 8-K item.

## 5. Candidate 2 — Bitcoin U.S.-session close momentum

### Job

Crypto intraday alpha sleeve. One BTCUSDT long trade per day at most; flat otherwise and flat after the selected session close.

### Source support

Shen, Urquhart, and Wang, “Bitcoin intraday time series momentum,” Financial Review 2022, DOI `10.1111/fire.12290`, directly studies whether an opening/overnight-plus-first-half-hour Bitcoin return predicts the last half-hour. The paper uses BTC/USD from Bitfinex, Bitstamp, CEX.IO, Coinbase, and Kraken through 2020. It selects exchange opening times from volume spikes and uses 17:00 ET as the close because CME Bitcoin futures begin their daily break then. It reports stronger predictability during high-volume/high-volatility openings and attributes the pattern to liquidity provision rather than late-informed trading.

This candidate is a Binance/BTCUSDT source replication, not evidence about the paper's five exchanges. The failed SPY/QQQ/IWM market-intraday-momentum Experiment does not falsify Bitcoin's different 24/7 market structure, but it raises the burden of proof and prohibits importing ETF results as support.

### Frozen cheap-scout rule shape

- Instrument: Binance spot `BTCUSDT` only.
- Data: public Binance 30-minute klines.
- Session timezone: `America/New_York`, with DST handled by timezone conversion rather than fixed UTC offsets.
- Frozen proxy opening: 09:00 ET, matching the common opening used for several exchanges in the source paper.
- Frozen close: 17:00 ET.
- Signal return: prior session's 17:00 close to current session's 09:30 close. This preserves the source-shaped overnight-plus-first-half-hour signal.
- Trigger: signal return strictly positive.
- Entry: 16:30 ET bar open or first executable observation after 16:30; no same-bar use of the 16:30-17:00 return.
- Exit: 17:00 ET.
- Position: 1.0 long BTCUSDT when triggered, otherwise flat.
- No short side, leverage, volatility/volume condition, alternative opening time, weekday filter, funding-rate filter, or stop/target in v1.

### Economic reasoning

The hypothesis is not that every recent Bitcoin move continues. It is that inventory/liquidity provision and traders' reluctance to carry risk across a conventional U.S./CME session boundary can make the earlier session direction reappear in the final half-hour. The signal is known many hours before entry, so there is no latency race.

### Public data feasibility

Verdict: **PASS.**

- Binance's official public archive provides daily/monthly spot and futures klines, trades, and aggregate trades without authentication.
- Kline intervals include 30 minutes.
- Each archive has a checksum file.
- Direct checks confirmed public BTCUSDT 30-minute monthly archives for 2017-08, 2017-09, and 2025-12.
- `data/ccxt_downloader.py` already supports unauthenticated Binance OHLCV and `30min` frequency.

For reproducibility, use the official archive plus pinned file checksums rather than relying only on mutable paginated CCXT responses. Preserve raw zip hashes and note Binance's timestamp-unit change for spot files from 2025 onward.

### Cost and market caveats

- The source used BTC/USD across five exchanges, not Binance BTCUSDT.
- Binance availability starts later, making the replication mostly post-discovery evidence.
- Crypto taker fees are large relative to many half-hour effects. Gross sign is not enough.
- The repository's frozen cost model must include the actual venue fee tier, spread/slippage, and two executions per trade.
- Binance availability, jurisdiction, and deployment venue are separate operational questions from historical alpha.

### Cheap terminal gates

1. Positive gross mean last-half-hour return when the signal is positive.
2. Positive gross result in development and untouched chronological validation periods.
3. Positive net result under taker execution plus slippage.
4. Positive result by at least two broad market regimes, not only 2020-2021.
5. Profit not dominated by the top 5% of sessions.
6. Entry/exit timestamps survive DST conversion and never overlap the signal interval.

If the gross sign fails, do not try the negative side, a different opening clock, a volatility filter, ETH, futures, or leverage on the consumed sample.

## 6. Candidate 3 — Pre-FOMC morning drift

### Job

Very selective US-equity event sleeve. One SPY trade on a scheduled FOMC decision day; no trade on almost every other day.

### Source support

Lucca and Moench, “The Pre-FOMC Announcement Drift,” Journal of Finance 2015, DOI `10.1111/jofi.12196`, documents large average S&P 500 excess returns in the 24 hours before scheduled FOMC decisions. The source strategy bought at 14:00 on the prior day and sold shortly before the announcement. Its intraday evidence says the market rose slightly the prior afternoon and then sharply during the morning of scheduled announcement days.

The proposed rule below intentionally removes the overnight leg to satisfy the day-trading objective. It is therefore a test of the day-of morning component, not a replication of the paper's full 24-hour strategy.

### Frozen cheap-scout rule shape

- Instrument: SPY only.
- Events: regularly scheduled FOMC policy-decision dates from the official Federal Reserve calendar; exclude unscheduled/emergency announcements.
- Period: the maximum Alpaca IEX history available from 2016 onward.
- Bars: 5-minute regular-session bars.
- Entry: first executable bar after 09:35 ET.
- Exit: 5 minutes before the scheduled policy-statement release time; for the modern sample this is normally 13:55 ET before a 14:00 release.
- Position: 1.0 long SPY; no short side.
- No yield-curve, VIX, prior-return, press-conference, SEP, meeting-type, month, or regime filter.
- If the event time is missing or ambiguous, skip the event.

### Economic reasoning

This is an event-risk-premium/attention candidate, not a chart pattern. The event schedule is public long in advance, and the source reports the return accumulated before rather than after the policy surprise. Entering after the open and exiting before the release deliberately avoids a latency race with the announcement itself.

### Public data feasibility

Verdict: **PASS for a bounded scout; sample-size constrained for a full gauntlet.**

- The Federal Reserve publishes official meeting calendars, statements, minutes, and historical materials.
- Alpaca Basic/IEX provides 5-minute SPY bars since 2016.
- The source notes approximately eight scheduled meetings per year. The free Alpaca period therefore yields only roughly eighty independent event days through 2025, even though it contains many intraday bars.

The independent sample size is the number of meetings, not the number of 5-minute bars. WFA, bootstrap, concentration, and significance must operate at the event/session level. A multi-ETF basket would not create more independent events and must not be used to inflate sample size.

### Main risks

- Most source evidence predates publication; the free sample is primarily a post-publication test where crowding/decay is plausible.
- The full source rule held overnight; the day-only slice may contain much less return.
- FOMC event days can have unusual variance and a few meetings can dominate results.
- Current statement timing differs from older historical timing, which is why each event needs an explicit timestamp.

### Cheap terminal gates

1. Positive gross mean open-to-preannouncement return.
2. Positive result in both chronological halves.
3. Positive median event return and a bootstrap lower bound above zero at the event level.
4. Positive net result after SPY spread/slippage.
5. Positive result after removing the best three meetings.
6. No post-announcement exposure.

If it fails, do not add VIX, yield-curve, meeting-type, press-conference, or prior-return filters.

## 7. Candidate 4 — Market-to-sector delayed information diffusion

### Job

US sector-ETF, long/flat, one morning basket per day at most. This is a reserve candidate after the first three, not the first implementation target.

### Source support and limitation

Chordia and Swaminathan, “Trading Volume and Cross-Autocorrelations in Stock Returns,” Journal of Finance 2000, DOI `10.1111/0022-1082.00231`, reports that high-volume portfolios lead low-volume portfolios. Hou, “Industry Information Diffusion and the Lead-lag Effect in Stock Returns,” Review of Financial Studies 2007, DOI `10.1093/revfin/hhm003`, documents gradual diffusion of industry information, especially into less-visible stocks.

Those papers establish an information-diffusion mechanism. They do not establish that SPY leads already-liquid sector ETFs over a 30-minute interval. The ETF implementation is a low-cost public-data proxy and should be rejected quickly if gross evidence is absent.

### Frozen cheap-scout rule shape

- Leader: SPY.
- Followers: `XLK`, `XLF`, `XLE`, `XLV`, `XLY`, `XLP`, `XLI`, `XLU`, `XLB`.
- Exclude XLC in v1 because its later inception changes panel history.
- Bars: synchronized 30-minute regular-session adjusted OHLCV from one feed.
- Signal interval: first regular-session 30-minute bar only.
- Trigger: SPY first-bar return is strictly positive.
- Eligible followers: sector first-bar return is less than or equal to zero.
- Portfolio: equal-weight all eligible followers, maximum gross 1.0.
- Entry: next 30-minute bar open after the signal is known.
- Exit: end of that next 30-minute bar.
- No beta estimate, rank cutoff, return threshold, relative-volume filter, volatility filter, sector selection, short side, or repeated intraday entries.

### Economic reasoning

A broad market move may be incorporated first into the most visible market instrument while sector-specific vehicles adjust with delay. Requiring a positive SPY move and a nonpositive sector move gives the hypothesis a clear catch-up direction. The 30-minute delay is intentionally slow enough to avoid a latency claim.

### Public data feasibility

Verdict: **PASS for a bounded ETF proxy.**

- Alpaca Basic/IEX provides 30-minute adjusted bars since 2016 with a free account.
- The repository already has the multi-ETF 30-minute signal/backtest/validation pattern.
- The fixed ETF list avoids historical constituent and delisting bias, although fund inception and feed completeness still require explicit checks.

### Why it is ranked fourth

- Prior intraday ETF price-only results are poor.
- Sector ETFs are themselves efficient and liquid, so the documented stock/industry diffusion may not transfer.
- A positive result could simply be delayed SPY beta rather than sector alpha; report SPY beta and same-window SPY return.
- IEX-only bars can differ in volume and prints from consolidated SIP.

### Cheap terminal gates

1. Positive gross follower-basket return.
2. Positive residual return versus SPY over the held interval.
3. Positive gross and residual results in both chronological halves.
4. Positive net return after costs.
5. No sector or small set of days dominates.

Failure ends this ETF proxy. Do not add negative-SPY shorts, sector ranks, thresholds, or additional time slots.

## 8. Why common technical-indicator candidates are not selected

The repository has already tested or scouted several price-only constructions. An indicator transforms prices; it does not add information. RSI, MACD, VWAP bands, Bollinger Bands, moving averages, ATR stops, volume confirmation, and candlestick labels create many degrees of freedom without changing the underlying information source.

That does not make all technical indicators useless. It means a new candidate needs an independent mechanism first. In the retained list:

- earnings acceptance supplies a timestamped information event;
- the Bitcoin rule uses a source-defined market-session/liquidity boundary;
- the FOMC calendar supplies a scheduled risk event;
- the sector rule tests cross-instrument diffusion rather than a standalone chart shape.

Price action is used to measure direction after the mechanism is declared, not to search hundreds of visual patterns.

## 9. Data-source matrix

| Candidate | Public source | Required fields | Feasibility | Main data risk |
| --- | --- | --- | --- | --- |
| SEC earnings continuation | SEC submissions JSON + Alpaca IEX bars | CIK, accession, acceptance timestamp, form, items; stock/SPY 5-minute OHLCV | Bounded scout PASS; promotion PARTIAL | Historical ticker/identifier/delisting coverage and disclosure timestamp may differ from first press release |
| Bitcoin session-close momentum | Binance public archive | 30-minute BTCUSDT OHLCV, archive checksum | PASS | Binance proxy differs from paper's exchanges; post-discovery history; fee drag |
| Pre-FOMC morning drift | Federal Reserve calendar + Alpaca IEX SPY | scheduled decision date/time; SPY 5-minute OHLCV | Bounded scout PASS | Only about eight independent events/year and mostly post-publication sample |
| Market-to-sector diffusion | Alpaca IEX | synchronized SPY/sector 30-minute adjusted OHLCV | Bounded proxy PASS | One-venue feed and weak transfer from stock-level literature to liquid ETFs |

Official/public references:

- Federal Reserve FOMC calendars: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`
- Federal Reserve historical materials: `https://www.federalreserve.gov/monetarypolicy/fomc_historical.htm`
- New York Fed pre-FOMC paper page: `https://www.newyorkfed.org/research/staff_reports/sr512.html`
- SEC submissions endpoint pattern: `https://data.sec.gov/submissions/CIK##########.json`
- SEC company ticker map: `https://www.sec.gov/files/company_tickers.json`
- Alpaca historical stock data: `https://docs.alpaca.markets/us/docs/historical-stock-data-1`
- Binance archive: `https://data.binance.vision/`
- Binance archive schema/code: `https://github.com/binance/binance-public-data`
- Bitcoin accepted manuscript: `https://centaur.reading.ac.uk/100181/3/21Sep2021Bitcoin%20Intraday%20Time-Series%20Momentum.R2.pdf`

## 10. Required validation design

### Stage 0 — data audit

Before returns:

- freeze source, feed, symbols, dates, frequency, timezone, event policy, and adjustment policy;
- hash raw and normalized files;
- validate complete pagination/downloads and inclusive date bounds;
- build a session calendar rather than grouping blindly by UTC date;
- preserve missing bars as missing and block incomplete signal/holding windows;
- separate signal timestamps from execution timestamps;
- verify event availability before each trade;
- report venue/feed limitations in every artifact.

### Stage 1 — cheap mechanism scout

Before the Experiment registry or full gauntlet:

- expected-sign gross mean and median;
- chronological halves;
- net result under frozen costs;
- event/session-block bootstrap;
- top-day/top-event concentration;
- per-symbol/sector/year decomposition;
- trade count, active-session count, and turnover;
- explicit no-same-bar and flat-by-close assertions.

A gross-sign failure ends the candidate. Do not invert or filter it.

### Stage 2 — immutable Experiment

Only a scout that passes every frozen progression gate receives:

- a source memo with exact rules;
- a registered `StrategyTemplate` version;
- a frozen Experiment UUID/hash;
- WFA, MC, DSR, and stability/no-tuning evidence;
- `validation.intraday` gates;
- strategy-role benchmarks.

For sparse event strategies, WFA and bootstrap units must be whole events/sessions, not bars. For BTC, define the 24/7 session in `America/New_York` and do not use `252 * bars_per_session` annualization; crypto needs a separately frozen annualization policy. For stocks/ETFs, preserve complete regular sessions and early-close handling.

### Stage 3 — practical utility

- Long/flat day sleeves are not automatically SPY replacements.
- Report return on deployed capital, exposure fraction, event frequency, and cash treatment.
- Measure alpha/beta and a predeclared risk-matched SPY-plus-sleeve blend.
- Cost stress must include spread, slippage, fees, and actual turnover.
- Paper readiness requires scheduled runtime ingestion, correct signal timing, EOD flattening, broker reconciliation, and immutable paper-session evidence.

## 11. Recommended order

1. **Run a data-only Bitcoin archive shakedown, then freeze one BTCUSDT source-replication scout.** It is the lowest-cost complete public dataset and the closest direct rule mapping.
2. **Run an SEC Item 2.02 coverage/timestamp audit on the existing 133-stock panel before any returns.** If event count and timing pass, freeze the event-continuation scout. Do not call the static panel promotion-quality.
3. **Build the FOMC event table and count independent usable meetings before backtesting.** Proceed only if the event sample can support the predeclared sparse-event gates.
4. **Use the sector lead-lag proxy only if the first three are blocked or rejected.** It is cheap, but adjacent ETF OHLCV evidence and source-transfer risk make it the lowest-priority candidate.

The goal is not to produce four backtests. It is to consume one frozen candidate at a time, stop on failed expected-sign evidence, and preserve untouched data for the next genuinely independent mechanism.
