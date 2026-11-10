# Bitcoin five-minute model: direct exchange economics

Date: September 30, 2026. Research only. No credentials, accounts, orders, subscriptions, or paid data were used.

The existing five-minute signal is too small to support ordinary exchange execution. A bounded comparison of three model alternatives across five-, fifteen-, and thirty-minute horizons found no qualified profitable candidate. This rejects these tested implementations; it does not prove that every possible BTC strategy is unprofitable.

## Original model, measured in money

The original frozen logistic model was tested using long signals at p(up) >= 0.55 and short signals at p(up) <= 0.45. Each position holds for five minutes at 1x fixed initial notional. Entry/exit prices are optimistic Binance perpetual bar opens, not bid/ask fills. One basis point is 0.01%. Net rows include the available Binance settled-funding reference.

| Period | Trades | Gross bps/trade | Net at 2bps costs | Net at 4bps costs | Net at 6bps costs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025 diagnostic | 4,334 | 0.479 | -1.520 | -3.520 | -5.520 |
| Jan–Aug 2026, all decisions | 2,614 | 0.611 | -1.390 | -3.389 | -5.389 |

The 2026 mean gross plus funding has a seven-day-block 95% interval of [-0.066, 1.275] bps/trade. Even zero-cost profitability is uncertain. At 2bps friction the entire 95% interval is negative: [-2.066, -0.725] bps/trade.

At $1,000 of BTC notional, the 2026 gross mean is about $0.061; a favorable 4bps fee-only round trip costs about $0.40. The modeled mean becomes approximately $-0.339 per trade before adding any unmodeled execution friction. These are sample means, not future income forecasts.

The observed mean win is 13.27bps and mean loss is -14.32bps, with 54.13% price-return wins. The model's greater-than-chance directional accuracy does not imply a large economic edge.

## Bounded model improvement experiment

The specification was written before the candidate outcomes. Alternatives: (1) a logistic model trained on a more recent 24-month window, (2) fixed nonlinear histogram gradient boosting for direction, and (3) fixed nonlinear regression for return size. Nonlinear models add lagged realized volatility, volatility-scaled returns, flow/return interaction, candle shape, and cyclical UTC clock features. No feature uses the current incomplete candle. Hyperparameters are fixed in spec.json. The models are not a rolling retraining system.

Training: July 2021–June 2023. Separate calibration: July–December 2023. Trading threshold selection: 2024. Diagnostic evaluation: 2025. Boundary-crossing labels are purged. Three thresholds per model/horizon are compared only on 2024. Selection favors 12bps net expectancy among rules with at least 500 trades. When no rule meets that count, the declared first rule is retained as an insufficient-sample diagnostic rather than promoted.

| Model | Minutes | 2025 trades | Gross bps/trade | Net 2bps | Net 4bps | Gate passed |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| recent_logistic | 5 | 5,838 | 0.432 | -1.568 | -3.568 | No |
| nonlinear_direction | 5 | 16,369 | 0.493 | -1.506 | -3.506 | No |
| nonlinear_return | 5 | 55 | -0.976 | -2.976 | -4.977 | No |
| recent_logistic | 15 | 9,980 | 0.427 | -1.575 | -3.575 | No |
| nonlinear_direction | 15 | 1,631 | 0.595 | -1.408 | -3.408 | No |
| nonlinear_return | 15 | 163 | 2.789 | 0.783 | -1.217 | No |
| recent_logistic | 30 | 1,177 | 1.450 | -0.565 | -2.565 | No |
| nonlinear_direction | 30 | 2,259 | 1.476 | -0.535 | -2.535 | No |
| nonlinear_return | 30 | 553 | 3.627 | 1.620 | -0.380 | No |

Every candidate failed the 2024 admission gate, either economics or sample size. Their 2025 results are retained as inexpensive diagnostics on previously exposed history; none was granted new candidate confirmation. All nine are negative at the favorable 4bps round-trip scenario. The sparse fifteen- and thirty-minute return-model rows are positive at 2bps in 2025, but fail 2024 gates and their gross uncertainty intervals include losses. They are not survivors.

The nonlinear five-minute classifier has 51.26% directional accuracy, Brier 0.249766, and AUC 0.521522 on its 2025 open-to-open target. That modest predictive improvement still produces only 0.493bps gross per selected trade. Accuracy metrics for the original close-versus-open binary label are not exactly like-for-like with this open-to-open execution target.

## Carrying consecutive positions and long-only diagnostics

A separately labeled post-result diagnostic nets adjacent same-direction positions rather than artificially paying for a close/reopen on every five-minute boundary. It uses actual net BTC quantity changes and includes funding on carried positions. This is an accounting sensitivity check, not an additional preregistered trading candidate.

For the original confident long/short rule on all 2026 decisions, the break-even all-in round-trip friction improves to 0.789bps (0.00789%), still below 2bps and far below 4bps. Its 95% interval includes negative values. Keeping positions therefore does not rescue this rule.

The confident long-only perpetual-price proxy loses money before trading fees in 2026 under the carried-position diagnostic. It is not a spot-exchange backtest, and spot prices would have to be collected before making a positive spot claim.

## Exchange choice for a US/New York resident

The best practical fit found for this specific small-contract, long/short API bot is Coinbase Financial Markets US derivatives, subject to successful account qualification. Coinbase Advanced requires no paid subscription. Its US perpetual-style BTC products and US derivatives API provide the relevant direction and automation capabilities. This is a product-fit recommendation, not a claim that Coinbase is cheapest for every account size or volume tier. [Advanced](https://www.coinbase.com/advanced-trade), [US product and eligibility](https://help.coinbase.com/en/coinbase/derivatives/us-perpetual-futures-overview), [US futures API](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/guides/futures).

Coinbase advertises fees as low as 0.02% per US perpetual-style contract execution, with a $0.15 contract minimum inclusive of clearing/exchange/NFA charges. The 4bps test deliberately assumes that favorable advertised rate on both entry and exit. It is not a verified account-specific maker/taker quote. A 6bps scenario adds 2bps assumed spread/slippage; 12bps is a higher-friction scenario. Current applicable rates require signing in. The developer guide still refers to an introductory 0.05% rate, so public documentation does not justify promising the advertised minimum for a new account. [US launch pricing](https://www.coinbase.com/en-fr/blog/perpetual-futures-have-arrived-in-the-us), [current fee instructions](https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees).

| Compared service | Relevant costs and capability | Decision |
| --- | --- | --- |
| Coinbase CFM US derivatives | BTC long/short, API, small contract, no Advanced subscription; favorable advertised 2bps per side subject to tier/minimum | Best practical product fit found; signal fails even this optimistic fee scenario |
| Interactive Brokers futures | API and Coinbase nano/CME micro BTC products; commissions plus exchange/regulatory charges; contract and capital needs differ | Credible alternative; absolute cheapest depends on trade size, contract, volume and data charges |
| Coinbase Advanced spot | US published entry rates 0.50% maker / 0.90% taker; API | Far too costly for this five-minute effect at entry tier |
| Gemini ActiveTrader spot | Published Sept 2026 entry rates 0.60% maker / 1.20% taker; API; its non-US perps are unavailable to US residents | Does not offer an economical substitute for this bot at entry tier |
| Robinhood Crypto | BTC spot and custom crypto API available in US; no commission on market-maker routing, but execution spread includes routing compensation | Fee-free commission is not free execution; spot API does not replicate this perp long/short implementation |
| Bitstamp | NY licensed and documented trading API; current fee table not readable in public text retrieval | Do not invent a verified current fee or rank it as cheapest |
| Kraken / MEXC | Kraken says New York unsupported; MEXC prohibits US users | Ineligible choices for this account |

The current Robinhood routing disclosure says it receives $0.95 per $100 notional from market makers, included in the spread. This is not a precise independent measurement of every BTC fill, but it directly contradicts modeling that commission-free route as costless. [Routing disclosure](https://robinhood.com/us/en/support/articles/smart-exchange-routing/), [crypto API](https://robinhood.com/us/en/support/articles/crypto-api/), [fee schedule](https://cdn.robinhood.com/assets/robinhood/legal/rhc-fee-schedule.pdf).

Other comparison sources: [IBKR futures commissions](https://www.interactivebrokers.com/en/pricing/commissions-futures.php), [Coinbase US spot pricing update](https://www.coinbase.com/blog/were-lowering-fees-for-many-active-traders-on-coinbase-advanced), [Gemini API fee table](https://www.gemini.com/fees/activetrader-fee-schedule), [Gemini non-US derivatives](https://www.gemini.com/blog/five-new-perpetual-contracts-on-geminis-derivatives-platform), [Bitstamp API](https://www.bitstamp.net/api/), [NYDFS entity list](https://www.dfs.ny.gov/virtual_currency_businesses), [Kraken US restrictions](https://support.kraken.com/articles/quick-start-for-clients-in-the-united-states), [MEXC US restrictions](https://www.mexc.com/et-EE/announcements/17827791523371).

MEXC also illustrates an API pricing trap: its official March 2026 announcement specifies separate futures API fees of 0.01% maker / 0.05% taker, overriding web/app fees. It is ineligible here regardless. [Official API launch](https://www.mexc.com/announcements/article/introducing-api-futures-trading-on-mar-31-2026-17827791534551).

## Data, checks, and interpretation limits

The later baseline uses 259 official checksum-verified archives: eight monthly price archives, eight funding archives, and 243 daily positioning-metric archives. There are 69,984 price bars and 69,984 metric records over January–August 2026, with no missing five-minute grid observations. Source URLs and SHA-256 checksums are retained in later_data/manifest.json. The frozen model exactly reproduces its stored probabilities under the installed dependency versions (maximum error zero).

The original scoring panel excludes bars whose eventual open equals close. That exclusion cannot be known at decision time. The separate all_decisions_diagnostic reconstructs identical causal features, verifies agreement with the original feature panel to 1e-12, and predicts all 2026 decisions, including 202 tied bars. This raises confident trades from 2,602 to 2,614 and leaves the economic rejection unchanged. The earlier original-panel results remain preserved rather than overwritten.

Checks passed: future-bar perturbation leaves current/past features unchanged; explicit long/short price P&L; millisecond-offset funding sign and magnitude; fees on both execution notionals; no overlapping fixed-horizon positions; internal missing prices block trades; no signal generates no order. Funding preserves actual settlement timestamps, using the containing five-minute open as an approximate mark-price reference. Exact entry/exit-boundary funding is excluded in fixed-horizon reference rows; the carried-position diagnostic charges carried boundary exposure. Neither method establishes Coinbase hourly funding costs.

These are Binance perpetual bar-reference diagnostics, not Coinbase contract executions. Coinbase has its own prices, order books, fees, hourly funding, contract multiplier, and a Friday 5–6pm ET closure; cross-venue transfer and maker fill quality remain unverified. Treat the assumed 2bps, 4bps, 6bps and higher friction rows as cost sensitivities. Zero-fee maker execution would need observed queue, partial-fill, cancel, inventory and adverse-selection evidence. A limit order does not guarantee a maker fill.

All 2020–2025 history was already viewed by this repository, so 2025 cannot be presented as untouched confirmation. The newly acquired 2026 period is later historical evidence for the unchanged original model, not a prospective live trial and not an assertion that no other prior research ever viewed that period. Candidate multiple comparison intervals are diagnostic; they do not correct the repository’s full search history.

Fixed-initial-notional aggregate P&L is a mathematical exposure sum. Some high-cost rows fall below -100%; an actual account would stop or become insolvent earlier. Those sums must not be described as feasible compounded returns. Per-trade expectancy, trade counts, uncertainty and failure gates are the decision evidence here.

No further thresholds, horizons, sign flips or model tuning were searched after the bounded failure. A different strategy may work, but it needs a new source of information or payoff mechanism with enough margin over executable costs. These tested model upgrades do not justify deploying this bot or paying for a new venue.

## Reproduce and inspect

Run scripts from this directory with the project Python environment. run.py and later_baseline.py refuse to overwrite completed result files; choose a new versioned output directory for a rerun. download_later.py only fetches public inputs into its separate cache. Supporting exports: spec.json, amendment_before_candidate_results.json, results.json, candidate_summary.csv, later_baseline_results.json, all_decisions_diagnostic.json, continuous_diagnostic.json, verification.json and per-rule prediction/trade Parquet files.
