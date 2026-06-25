# Graph Report - untitled_project  (2026-06-25)

## Corpus Check
- 103 files · ~49,705 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1573 nodes · 4728 edges · 92 communities (76 shown, 16 thin omitted)
- Extraction: 71% EXTRACTED · 29% INFERRED · 0% AMBIGUOUS · INFERRED: 1392 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `251c8f2e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Data Download & Pipeline|Data Download & Pipeline]]
- [[_COMMUNITY_Event Logging & Error Handling|Event Logging & Error Handling]]
- [[_COMMUNITY_Telegram Alert Manager|Telegram Alert Manager]]
- [[_COMMUNITY_MA Strategy Signals & Tests|MA Strategy Signals & Tests]]
- [[_COMMUNITY_Walk-Forward Analysis & Tests|Walk-Forward Analysis & Tests]]
- [[_COMMUNITY_Cost Model & Backtest Config|Cost Model & Backtest Config]]
- [[_COMMUNITY_Risk Engine & Kill Switch|Risk Engine & Kill Switch]]
- [[_COMMUNITY_Parameter Stability Analysis|Parameter Stability Analysis]]
- [[_COMMUNITY_DSR (Deflated Sharpe Ratio)|DSR (Deflated Sharpe Ratio)]]
- [[_COMMUNITY_Monte Carlo Bootstrap|Monte Carlo Bootstrap]]
- [[_COMMUNITY_Gauntlet Orchestrator|Gauntlet Orchestrator]]
- [[_COMMUNITY_Order State Machine & OMS|Order State Machine & OMS]]
- [[_COMMUNITY_Storage Schema & Repository|Storage Schema & Repository]]
- [[_COMMUNITY_Config Loader & Schema|Config Loader & Schema]]
- [[_COMMUNITY_Pre-Paper Gauntlet Integration|Pre-Paper Gauntlet Integration]]
- [[_COMMUNITY_CCXT Binance Adapter|CCXT Binance Adapter]]
- [[_COMMUNITY_Alpaca Adapter|Alpaca Adapter]]
- [[_COMMUNITY_Engine Runtime & Replay|Engine Runtime & Replay]]
- [[_COMMUNITY_Sim Broker & Tests|Sim Broker & Tests]]
- [[_COMMUNITY_Portfolio Sizing|Portfolio Sizing]]
- [[_COMMUNITY_Validation Unit Tests|Validation Unit Tests]]
- [[_COMMUNITY_Quality Validation (Data)|Quality Validation (Data)]]
- [[_COMMUNITY_Resample Helper & Tests|Resample Helper & Tests]]
- [[_COMMUNITY_Research Backtest Runner|Research Backtest Runner]]
- [[_COMMUNITY_Monitoring Watcdog|Monitoring Watcdog]]
- [[_COMMUNITY_CLI Interface|CLI Interface]]
- [[_COMMUNITY_Storage Event Logger|Storage Event Logger]]
- [[_COMMUNITY_Parquet IO|Parquet IO]]
- [[_COMMUNITY_Market Data Testing|Market Data Testing]]
- [[_COMMUNITY_Position Data Model|Position Data Model]]
- [[_COMMUNITY_Active Alert Querying|Active Alert Querying]]
- [[_COMMUNITY_BB Strategy Skeleton|BB Strategy Skeleton]]
- [[_COMMUNITY_CSMR Strategy Skeleton|CSMR Strategy Skeleton]]
- [[_COMMUNITY_Pairs Strategy Skeleton|Pairs Strategy Skeleton]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]

## God Nodes (most connected - your core abstractions)
1. `DrawdownState` - 118 edges
2. `PortfolioState` - 117 edges
3. `EventLogger` - 113 edges
4. `AssetClass` - 112 edges
5. `Config` - 100 edges
6. `SimBrokerConfig` - 97 edges
7. `MAParams` - 97 edges
8. `RiskEngine` - 87 edges
9. `SimBroker` - 84 edges
10. `CostModelConfig` - 78 edges

## Surprising Connections (you probably didn't know these)
- `Connection` --uses--> `EventLogger`  [INFERRED]
  tests/unit/test_storage.py → storage/event_logger.py
- `ArgumentParser` --uses--> `ConfigError`  [INFERRED]
  engine/cli.py → config/loader.py
- `Namespace` --uses--> `ConfigError`  [INFERRED]
  engine/cli.py → config/loader.py
- `CostModel` --uses--> `AssetClass`  [INFERRED]
  research/runner.py → config/schema.py
- `Any` --uses--> `AssetClass`  [INFERRED]
  data/pipeline.py → config/schema.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Gauntlet Validation Pipeline** — docs_plan_wfa, docs_plan_montecarlo, docs_plan_dsr, docs_plan_parameterstability [EXTRACTED 1.00]
- **Phase 4: Real Strategy Expansion** — docs_plan_bbstrategy, docs_plan_pairsstrategy, docs_plan_csmrstrategy [EXTRACTED 1.00]
- **Strategy Lifecycle** — docs_plan_strategysourcingphilosophy, docs_plan_gauntlet, docs_plan_livedeploymentgate, docs_plan_strategyretirement [INFERRED 0.85]

## Communities (92 total, 16 thin omitted)

### Community 0 - "Data Download & Pipeline"
Cohesion: 0.08
Nodes (38): ABC, BaseDownloader, get_broker_creds(), Retrieve actual API key/secret from environment for a broker., AlpacaDownloader, DownloadRequest, DownloadResult, Alpaca data downloader — US equity OHLCV bars.  Uses the Alpaca Markets Historic (+30 more)

### Community 1 - "Event Logging & Error Handling"
Cohesion: 0.06
Nodes (34): Exception, BrokerAdapter, BrokerOrderResponse, Connection, EventLogger, Update order state in DB, validating transitions., Reconcile a timed-out order by querying the broker.          Does NOT retry blin, IllegalTransitionError (+26 more)

### Community 2 - "Telegram Alert Manager"
Cohesion: 0.08
Nodes (17): AlertManager, AlertState, Alert manager — Telegram notifications with throttling.  Features:   - Dedup ale, Get all currently active (unresolved) alerts., Send an alert (with throttling). Returns True if sent., Send alert via Telegram bot (best-effort, no crash on failure)., Track one alert's state for throttling., Throttled alert manager — prevents alert storms.      Rules:       - Same event_ (+9 more)

### Community 3 - "MA Strategy Signals & Tests"
Cohesion: 0.08
Nodes (35): MA signal generator should work on loaded data., Full pipeline: load → signals → backtest → metrics., Prove the full pipeline works: data → signals → backtest., TestVerticalSlice, compute_ma(), default_params(), generate_signals(), MAParams (+27 more)

### Community 4 - "Walk-Forward Analysis & Tests"
Cohesion: 0.07
Nodes (34): Protocol, DataFrame, Timedelta, _make_ohlcv(), Tests for walk-forward analysis., A strategy with consistently positive returns should pass WFA., TestGenerateFolds, TestParseWindow (+26 more)

### Community 5 - "Cost Model & Backtest Config"
Cohesion: 0.17
Nodes (19): CostModel, Convenience: run the MA crossover strategy through the research pipeline.  This, BacktestResult, compute_metrics(), _empty_result(), _extract_trades(), print_report(), Any (+11 more)

### Community 6 - "Risk Engine & Kill Switch"
Cohesion: 0.09
Nodes (21): Any, PortfolioState, RiskLimits, Activate the global kill switch — blocks all trading., Manually clear the kill switch., Halt a single strategy (soft exception)., Resume a halted strategy., Evaluate target positions against all risk limits.          Args:             ta (+13 more)

### Community 7 - "Parameter Stability Analysis"
Cohesion: 0.18
Nodes (5): AlpacaAdapter, Get latest price for a symbol from Alpaca data API., Alpaca Markets broker adapter for US equities.      Args:         api_key: Alpac, adapter(), TestGetOpenOrders

### Community 8 - "DSR (Deflated Sharpe Ratio)"
Cohesion: 0.06
Nodes (125): BrokerConfig, ConfigError, default_config_path(), load_config(), _looks_like_paper_key(), _parse_brokers(), _parse_data(), Any (+117 more)

### Community 9 - "Monte Carlo Bootstrap"
Cohesion: 0.08
Nodes (32): Trading engine — the runtime loop.  One engine, three modes: research | paper |, Engine startup sequence — reconciliation before trading.          Returns True i, Reconcile internal state with broker state., Graceful shutdown — persist state and exit., Halt the engine — persists to DB, survives restart., Manually resume after halt., Order Management System (OMS) — ties state machine, broker, and storage together, Strategy-level kill switch persists across restart. (+24 more)

### Community 10 - "Gauntlet Orchestrator"
Cohesion: 0.19
Nodes (11): block_bootstrap_returns(), Run block-bootstrap Monte Carlo simulation on a return series.      Args:, Generate block-bootstrapped return paths.      Args:         returns: Original d, run_monte_carlo(), Series, _make_returns(), Tests for Monte Carlo simulation., Generate synthetic daily returns with a target Sharpe ratio. (+3 more)

### Community 11 - "Order State Machine & OMS"
Cohesion: 0.15
Nodes (19): _check_completeness(), _check_duplicates(), _check_gap_detection(), _check_ohlcv_sanity(), _check_staleness(), _check_volume(), Any, DataFrame (+11 more)

### Community 12 - "Storage Schema & Repository"
Cohesion: 0.09
Nodes (20): Alpaca broker adapter — US equities via Alpaca Markets REST API v2.  Implements, CCXT Binance spot adapter — crypto via CCXT unified interface.  Binance-specific, BrokerAccount, BrokerAdapter, BrokerOrderResponse, BrokerPosition, OrderSide, OrderType (+12 more)

### Community 13 - "Config Loader & Schema"
Cohesion: 0.17
Nodes (7): adapter(), mock_exchange(), CCXT Binance adapter mocked tests — deterministic tests with monkeypatched excha, Create a CCXTBinanceAdapter with a mocked exchange., Verify CCXT status values map correctly to our state machine., TestGetPositions, TestStatusMapping

### Community 14 - "Pre-Paper Gauntlet Integration"
Cohesion: 0.06
Nodes (40): make_synthetic_bars(), Generate deterministic daily OHLCV data that normally produces MA trades., _config_with_storage(), FakeReadOnlyBroker, test_dry_run_mode_never_calls_broker_submit(), test_dry_run_rejects_broker_price_far_from_last_close(), _config_with_storage(), FakePaperBroker (+32 more)

### Community 15 - "CCXT Binance Adapter"
Cohesion: 0.08
Nodes (33): DrawdownState, EngineMode, EngineState, Any, BrokerAdapter, Config, Connection, DataFrame (+25 more)

### Community 16 - "Alpaca Adapter"
Cohesion: 0.13
Nodes (20): PortfolioState, Current portfolio state — capital, equity, open positions., classify_exception(), determine_emergency_action(), ExceptionSeverity, Risk engine — circuit breakers, exposure limits, correlation, kill switches.  St, Classify an exception into SOFT / HARD / CATASTROPHIC.      Soft:      one strat, Determine the correct emergency action.      Known-risk emergency + risk breach (+12 more)

### Community 17 - "Engine Runtime & Replay"
Cohesion: 0.17
Nodes (16): Configuration for the simulated broker's failure modes., SimBrokerConfig, get_order(), Connection, SimBroker, broker(), db(), _make_intent() (+8 more)

### Community 18 - "Sim Broker & Tests"
Cohesion: 0.13
Nodes (8): BrokerAdapter, CCXTBinanceAdapter, Fetch account balance from Binance., Get latest price for a trading pair (e.g. BTC/USDT)., Binance spot adapter via CCXT.      Args:         api_key: Binance API key (from, Verify connection by fetching balance., BrokerAccount, ccxt_adapter()

### Community 19 - "Portfolio Sizing"
Cohesion: 0.13
Nodes (8): Same target twice → no duplicate orders., Same bar replayed twice → identical position state., DrawdownState, Current drawdown tracking state., _make_target(), TestDrawdownLimits, TestExposureLimits, TestKillSwitch

### Community 20 - "Validation Unit Tests"
Cohesion: 0.08
Nodes (25): _apply_dollar_neutral(), compute_position_delta(), compute_target_positions(), ExecutionMode, _position_side(), PortfolioConfig, Portfolio construction — convert strategy exposures to target positions.  Strate, Size position so that max loss = risk_pct * equity.      If stop_price is provid (+17 more)

### Community 21 - "Quality Validation (Data)"
Cohesion: 0.16
Nodes (9): Initialize HTTP session and verify credentials., Make an HTTP request to the Alpaca API with retry logic., Fetch all open positions from Alpaca., Fetch account state from Alpaca., Parse Alpaca position JSON into BrokerPosition., Any, BrokerAccount, BrokerPosition (+1 more)

### Community 22 - "Resample Helper & Tests"
Cohesion: 0.16
Nodes (12): available_frequencies(), DataFrame, Resample 1-min raw bars to higher frequencies.  Source of truth is 1-min. All do, Resample a 1-min OHLCV DataFrame to a higher frequency.      Args:         df: D, Detect what frequencies the data can be resampled to based on the index., resample_to(), 1-min data should resample to daily correctly., DataFrame (+4 more)

### Community 23 - "Research Backtest Runner"
Cohesion: 0.07
Nodes (19): BrokerAccount, Set the current price for a symbol (for testing)., Cancel an order. Returns True if cancelled, False if not found/cancellable., Get current price for a symbol., Clear all positions (simulate manual close)., A simulated broker with configurable failure modes.      Use this to test the en, SimBroker, _make_request() (+11 more)

### Community 24 - "Monitoring Watcdog"
Cohesion: 0.11
Nodes (32): _blocked_reason(), _current_qty(), _dry_run_blockers(), _log_risk(), _orders_to_dicts(), PaperDryRunDecision, PaperDryRunResult, _portfolio_positions() (+24 more)

### Community 25 - "CLI Interface"
Cohesion: 0.18
Nodes (25): load_bars(), Load bars from Parquet for a symbol at a given frequency., _find_data_config(), _normalize_bars(), _current_qty(), _finish_result(), _order_count(), _order_type_and_limit() (+17 more)

### Community 26 - "Storage Event Logger"
Cohesion: 0.08
Nodes (26): compute_dsr(), _dsr_pvalue(), _dsr_statistic(), DSRResult, estimate_m_cluster(), estimate_m_eff_corr(), Deflated Sharpe Ratio (DSR).  Answers: "Given the number of trials/strategies/pa, Compute the Deflated Sharpe Ratio.      Args:         observed_sharpe: The best (+18 more)

### Community 27 - "Parquet IO"
Cohesion: 0.11
Nodes (10): BrokerOrderRequest, Request to submit an order to a broker., Submit an invalid order and verify it's rejected without position change., Submit a tiny paper order, verify it, then cancel it.          Uses a limit orde, Verify client_order_id is passed through to Alpaca for idempotency., TestIdempotencyClientOrderId, TestSubmitOrder, Verify client_order_id is passed through to Binance for idempotency. (+2 more)

### Community 28 - "Market Data Testing"
Cohesion: 0.21
Nodes (7): Submit an order to Alpaca., Cancel an order by client_order_id.          First looks up the order to get the, Get order status by client_order_id., Fetch currently open Alpaca orders., Parse Alpaca order JSON into BrokerOrderResponse., BrokerOrderRequest, BrokerOrderResponse

### Community 29 - "Position Data Model"
Cohesion: 0.17
Nodes (11): Current Readiness, Handoff: mfs-trader Medium-Frequency Trading System, Important Constraints, Key Fixes and Additions From Latest Work, Phase 1 (Data pipeline, config, storage, MA strategy, research), Phase 2 (Validation engine), Phase 3 (Execution skeleton), Recommended Next Steps (+3 more)

### Community 30 - "Active Alert Querying"
Cohesion: 0.08
Nodes (31): Bollinger Bands Strategy, Build Order (4 Phases), Cross-Sectional Mean Reversion (CSMR), Directory Structure, Deflated Sharpe Ratio (DSR), Execution Skeleton, The Gauntlet, Gauntlet Summary (+23 more)

### Community 31 - "BB Strategy Skeleton"
Cohesion: 0.14
Nodes (10): BrokerOrderRequest, BrokerOrderResponse, BrokerPosition, Submit an order — may reject, timeout, or partially fill based on config., Get the current status of an order., Get current positions — may be stale or mismatched per config., Update internal position after a fill., Inject a position for testing reconciliation. (+2 more)

### Community 32 - "CSMR Strategy Skeleton"
Cohesion: 0.23
Nodes (7): format_ma_replay_report(), MAReplayComparison, Any, Write JSON and Markdown comparison reports., Render the replay comparison as Markdown., _safe_name(), write_ma_replay_reports()

### Community 33 - "Pairs Strategy Skeleton"
Cohesion: 0.12
Nodes (13): CostModel, AssetClass, Transaction cost model — modular, configurable per asset class and venue.  Compo, Dispatch to the right cost function by asset class., Approximate total cost as a percentage of notional (for quick vectorized backtes, Total cost for a buy + sell round trip, as % of notional., Cost breakdown for a single round-trip or per-side trade., Compute transaction costs per trade, per asset class. (+5 more)

### Community 34 - "Community 34"
Cohesion: 0.24
Nodes (12): analyze_stability(), _check_isolated_peak(), _compute_sensitivity(), _estimate_step_size(), Parameter stability analysis.  Checks that the selected parameters are on a stab, Check if the best result is an isolated peak (neighbors are much worse).      An, Estimate the step size for a numeric parameter column., Compute how sensitive Sharpe is to each parameter.      Returns a dict {param: s (+4 more)

### Community 35 - "Community 35"
Cohesion: 0.17
Nodes (8): alpaca_adapter(), Alpaca live smoke tests — only run with real paper account keys.  These tests hi, Live smoke tests against Alpaca paper account., Verify account fetch returns real data., Verify positions fetch works (may be empty)., Verify open orders fetch works and no smoke leftovers remain., Verify price fetch for a liquid symbol., TestAlpacaLiveSmoke

### Community 36 - "Community 36"
Cohesion: 0.17
Nodes (7): Submit an invalid order and verify rejection., Live smoke tests against Binance testnet., Verify account/balance fetch returns real data., Verify positions fetch works (may be empty)., Verify price fetch for a major pair., Submit a tiny limit order on testnet, verify, then cancel., TestCCXTLiveSmoke

### Community 37 - "Community 37"
Cohesion: 0.18
Nodes (8): compute_path_metrics(), MCResult, Monte Carlo simulation — block-bootstrap + parameter perturbation.  Generates 10, Compute terminal wealth, Sharpe, Sortino, max DD, CAGR for one path., Results of a Monte Carlo simulation., Compute summary statistics from the simulated paths., TestComputePathMetrics, ndarray

### Community 38 - "Community 38"
Cohesion: 0.11
Nodes (35): _assumption_gaps(), Attribution, build_attribution(), build_comparison_checks(), _build_differences(), _close_abs(), _close_pct(), ComparisonChecks (+27 more)

### Community 39 - "Community 39"
Cohesion: 0.27
Nodes (5): DataFrame, _make_sweep_results(), Generate parameter sweep results.      If stable=True, creates a smooth plateau., If the plateau region straddles positive and negative, it's unstable., TestAnalyzeStability

### Community 40 - "Community 40"
Cohesion: 0.22
Nodes (7): Submit an order to Binance via CCXT., Cancel an order by client_order_id.          Binance supports cancel-by-clientOr, Get order status by client_order_id.          CCXT doesn't have a direct "get by, Parse CCXT order dict into BrokerOrderResponse., Any, BrokerOrderRequest, BrokerOrderResponse

### Community 41 - "Community 41"
Cohesion: 0.24
Nodes (9): GauntletResult, Any, DataFrame, ndarray, Series, Validation gauntlet — orchestrates WFA + MC + DSR + parameter stability.  This i, Final result of the validation gauntlet., Run the full validation gauntlet on a strategy.      Args:         strategy_name (+1 more)

### Community 42 - "Community 42"
Cohesion: 0.31
Nodes (5): check_wfa_consistency(), Check if the same parameter region performs well across WFA folds.      Args:, Tests for parameter stability analysis., TestWFAConsistency, Any

### Community 43 - "Community 43"
Cohesion: 0.27
Nodes (5): DataFrame, _make_ohlcv(), The backtest should not use future data — changing the future         should not, Backtest with costs should have lower returns than without., TestBacktestRunner

### Community 44 - "Community 44"
Cohesion: 0.29
Nodes (6): Perturb strategy parameters and re-run backtests.      Args:         df: Full da, run_parameter_perturbation(), TestParameterPerturbation, Any, DataFrame, Series

### Community 45 - "Community 45"
Cohesion: 0.33
Nodes (5): pytest_collection_modifyitems(), pytest_configure(), Pytest configuration — skip live_broker tests by default., Load .env before test collection., Skip live_broker tests unless RUN_LIVE_BROKER_TESTS=1 is set.

### Community 46 - "Community 46"
Cohesion: 0.07
Nodes (47): ArgumentParser, build_parser(), cmd_paper_dry_run_ma(), cmd_paper_halt(), cmd_paper_trade_ma(), cmd_preflight(), cmd_replay_ma(), cmd_report() (+39 more)

### Community 47 - "Community 47"
Cohesion: 0.40
Nodes (3): Partial fill → position = filled qty, remaining tracked., Cancelled partial fill → filled qty preserved., TestPartialFills

## Knowledge Gaps
- **45 isolated node(s):** `Any`, `Response`, `BrokerOrderRequest`, `BrokerAccount`, `BrokerOrderRequest` (+40 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_wfa()` connect `Walk-Forward Analysis & Tests` to `Community 41`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **Why does `WFATier` connect `Walk-Forward Analysis & Tests` to `Storage Schema & Repository`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Why does `ReadOnlyBroker` connect `Monitoring Watcdog` to `MA Strategy Signals & Tests`, `Walk-Forward Analysis & Tests`, `Risk Engine & Kill Switch`, `DSR (Deflated Sharpe Ratio)`, `CCXT Binance Adapter`, `Alpaca Adapter`, `Portfolio Sizing`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **Are the 80 inferred relationships involving `DrawdownState` (e.g. with `DrawdownState` and `Attribution`) actually correct?**
  _`DrawdownState` has 80 INFERRED edges - model-reasoned connections that need verification._
- **Are the 93 inferred relationships involving `PortfolioState` (e.g. with `DrawdownState` and `Attribution`) actually correct?**
  _`PortfolioState` has 93 INFERRED edges - model-reasoned connections that need verification._
- **Are the 72 inferred relationships involving `EventLogger` (e.g. with `DrawdownState` and `PaperDryRunDecision`) actually correct?**
  _`EventLogger` has 72 INFERRED edges - model-reasoned connections that need verification._
- **Are the 95 inferred relationships involving `AssetClass` (e.g. with `BrokerConfig` and `ConfigError`) actually correct?**
  _`AssetClass` has 95 INFERRED edges - model-reasoned connections that need verification._