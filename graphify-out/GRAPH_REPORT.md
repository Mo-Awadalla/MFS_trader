# Graph Report - .  (2026-06-25)

## Corpus Check
- Corpus is ~39,019 words - fits in a single context window. You may not need a graph.

## Summary
- 1307 nodes · 3458 edges · 81 communities (76 shown, 5 thin omitted)
- Extraction: 74% EXTRACTED · 26% INFERRED · 0% AMBIGUOUS · INFERRED: 894 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `SimBroker` - 84 edges
2. `EventLogger` - 82 edges
3. `DrawdownState` - 78 edges
4. `PortfolioState` - 77 edges
5. `SimBrokerConfig` - 70 edges
6. `CostModelConfig` - 66 edges
7. `AssetClass` - 65 edges
8. `RiskLimits` - 53 edges
9. `TradingEngine` - 53 edges
10. `Config` - 52 edges

## Surprising Connections (you probably didn't know these)
- `Connection` --uses--> `EventLogger`  [INFERRED]
  tests/unit/test_storage.py → storage/event_logger.py
- `TestMAReplayVsVectorBT` --uses--> `Mode`  [INFERRED]
  tests/replay/test_ma_replay_vs_vectorbt.py → config/schema.py
- `SimBroker` --uses--> `Mode`  [INFERRED]
  tests/integration/test_pre_paper_gauntlet.py → config/schema.py
- `TestConfigLoader` --uses--> `Mode`  [INFERRED]
  tests/unit/test_config.py → config/schema.py
- `TestLiveConfigValidation` --uses--> `Mode`  [INFERRED]
  tests/unit/test_config.py → config/schema.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Gauntlet Validation Pipeline** — docs_plan_wfa, docs_plan_montecarlo, docs_plan_dsr, docs_plan_parameterstability [EXTRACTED 1.00]
- **Phase 4: Real Strategy Expansion** — docs_plan_bbstrategy, docs_plan_pairsstrategy, docs_plan_csmrstrategy [EXTRACTED 1.00]
- **Strategy Lifecycle** — docs_plan_strategysourcingphilosophy, docs_plan_gauntlet, docs_plan_livedeploymentgate, docs_plan_strategyretirement [INFERRED 0.85]

## Communities (81 total, 5 thin omitted)

### Community 0 - "Data Download & Pipeline"
Cohesion: 0.05
Nodes (63): ABC, BaseDownloader, get_broker_creds(), Retrieve actual API key/secret from environment for a broker., AlpacaDownloader, DownloadRequest, DownloadResult, Alpaca data downloader — US equity OHLCV bars.  Uses the Alpaca Markets Historic (+55 more)

### Community 1 - "Event Logging & Error Handling"
Cohesion: 0.06
Nodes (32): EventLogger, Exception, BrokerAdapter, BrokerOrderResponse, Connection, IllegalTransitionError, is_filled_state(), is_terminal() (+24 more)

### Community 2 - "Telegram Alert Manager"
Cohesion: 0.07
Nodes (29): AlertManager, AlertState, Alert manager — Telegram notifications with throttling.  Features:   - Dedup ale, Get all currently active (unresolved) alerts., Send an alert (with throttling). Returns True if sent., Send alert via Telegram bot (best-effort, no crash on failure)., Track one alert's state for throttling., Throttled alert manager — prevents alert storms.      Rules:       - Same event_ (+21 more)

### Community 3 - "MA Strategy Signals & Tests"
Cohesion: 0.08
Nodes (33): MA signal generator should work on loaded data., Full pipeline: load → signals → backtest → metrics., Prove the full pipeline works: data → signals → backtest., TestVerticalSlice, compute_ma(), default_params(), generate_signals(), MAParams (+25 more)

### Community 4 - "Walk-Forward Analysis & Tests"
Cohesion: 0.07
Nodes (34): Protocol, DataFrame, Timedelta, _make_ohlcv(), Tests for walk-forward analysis., A strategy with consistently positive returns should pass WFA., TestGenerateFolds, TestParseWindow (+26 more)

### Community 5 - "Cost Model & Backtest Config"
Cohesion: 0.13
Nodes (34): BacktestResult, AssetClass, CostModelConfig, CostModel, MAParams, CostModel, CostModelConfig, Transaction cost model — modular, configurable per asset class and venue.  Compo (+26 more)

### Community 6 - "Risk Engine & Kill Switch"
Cohesion: 0.09
Nodes (22): Any, PortfolioState, Activate the global kill switch — blocks all trading., Manually clear the kill switch., Halt a single strategy (soft exception)., Resume a halted strategy., Evaluate target positions against all risk limits.          Args:             ta, Convert a target to flat (exit). (+14 more)

### Community 7 - "Parameter Stability Analysis"
Cohesion: 0.06
Nodes (16): AlpacaAdapter, Get latest price for a symbol from Alpaca data API., Alpaca Markets broker adapter for US equities.      Args:         api_key: Alpac, alpaca_adapter(), adapter(), Alpaca adapter mocked tests — deterministic CI tests with mocked HTTP responses., Verify all Alpaca status values map correctly to our state machine., Verify client_order_id is passed through to Alpaca for idempotency. (+8 more)

### Community 8 - "DSR (Deflated Sharpe Ratio)"
Cohesion: 0.32
Nodes (36): BrokerConfig, _parse_brokers(), Any, Config, DataConfig, Mode, Path, BrokerConfig (+28 more)

### Community 9 - "Monte Carlo Bootstrap"
Cohesion: 0.11
Nodes (24): Trading engine — the runtime loop.  One engine, three modes: research | paper |, Engine startup sequence — reconciliation before trading.          Returns True i, Reconcile internal state with broker state., Graceful shutdown — persist state and exit., Halt the engine — persists to DB, survives restart., Manually resume after halt., Order Management System (OMS) — ties state machine, broker, and storage together, Update position after a fill. (+16 more)

### Community 10 - "Gauntlet Orchestrator"
Cohesion: 0.09
Nodes (25): block_bootstrap_returns(), compute_path_metrics(), MCResult, Monte Carlo simulation — block-bootstrap + parameter perturbation.  Generates 10, Compute terminal wealth, Sharpe, Sortino, max DD, CAGR for one path., Run block-bootstrap Monte Carlo simulation on a return series.      Args:, Perturb strategy parameters and re-run backtests.      Args:         df: Full da, Results of a Monte Carlo simulation. (+17 more)

### Community 11 - "Order State Machine & OMS"
Cohesion: 0.14
Nodes (20): _check_completeness(), _check_duplicates(), _check_gap_detection(), _check_ohlcv_sanity(), _check_staleness(), _check_volume(), Any, DataFrame (+12 more)

### Community 12 - "Storage Schema & Repository"
Cohesion: 0.10
Nodes (19): Alpaca broker adapter — US equities via Alpaca Markets REST API v2.  Implements, CCXT Binance spot adapter — crypto via CCXT unified interface.  Binance-specific, BrokerAccount, BrokerAdapter, BrokerOrderResponse, BrokerPosition, OrderSide, OrderType (+11 more)

### Community 13 - "Config Loader & Schema"
Cohesion: 0.07
Nodes (13): adapter(), mock_exchange(), MockExchange, CCXT Binance adapter mocked tests — deterministic tests with monkeypatched excha, Create a CCXTBinanceAdapter with a mocked exchange., Mock CCXT exchange for testing., Verify CCXT status values map correctly to our state machine., TestCancelOrder (+5 more)

### Community 14 - "Pre-Paper Gauntlet Integration"
Cohesion: 0.10
Nodes (19): ConfigError, default_config_path(), load_config(), _looks_like_paper_key(), _parse_data(), Config loader — reads TOML, resolves env-var secrets, validates., Validate config — raises ConfigError on any unsafe or missing setup., Strict validation for live mode — refuse to start on any unsafe condition. (+11 more)

### Community 15 - "CCXT Binance Adapter"
Cohesion: 0.12
Nodes (22): DrawdownState, EngineMode, EngineState, Any, BrokerAdapter, Config, Connection, DataFrame (+14 more)

### Community 16 - "Alpaca Adapter"
Cohesion: 0.14
Nodes (19): PortfolioState, Current portfolio state — capital, equity, open positions., classify_exception(), determine_emergency_action(), ExceptionSeverity, Risk engine — circuit breakers, exposure limits, correlation, kill switches.  St, Classify an exception into SOFT / HARD / CATASTROPHIC.      Soft:      one strat, Determine the correct emergency action.      Known-risk emergency + risk breach (+11 more)

### Community 17 - "Engine Runtime & Replay"
Cohesion: 0.14
Nodes (18): OMS, Manually unfreeze the OMS., Order Management System — orchestrates order lifecycle.      Flow:         1. cr, get_order(), Connection, SimBroker, broker(), db() (+10 more)

### Community 18 - "Sim Broker & Tests"
Cohesion: 0.08
Nodes (17): BrokerAdapter, CCXTBinanceAdapter, Submit an order to Binance via CCXT., Cancel an order by client_order_id.          Binance supports cancel-by-clientOr, Get order status by client_order_id.          CCXT doesn't have a direct "get by, Fetch all non-zero balances from Binance.          In spot trading, "positions", Fetch account balance from Binance., Get latest price for a trading pair (e.g. BTC/USDT). (+9 more)

### Community 19 - "Portfolio Sizing"
Cohesion: 0.15
Nodes (8): Same bar replayed twice → identical position state., DrawdownState, Current drawdown tracking state., _make_target(), TestCorrelationCluster, TestDrawdownLimits, TestExposureLimits, TestKillSwitch

### Community 20 - "Validation Unit Tests"
Cohesion: 0.13
Nodes (14): _apply_dollar_neutral(), compute_target_positions(), PortfolioConfig, Portfolio construction — convert strategy exposures to target positions.  Strate, Size position so that max loss = risk_pct * equity.      If stop_price is provid, Size position targeting a constant volatility contribution.      qty = (risk_pct, Adjust positions so gross long = gross short (dollar-neutral)., Convert strategy exposures into target positions.      Args:         exposures: (+6 more)

### Community 21 - "Quality Validation (Data)"
Cohesion: 0.11
Nodes (15): Initialize HTTP session and verify credentials., Make an HTTP request to the Alpaca API with retry logic., Submit an order to Alpaca., Cancel an order by client_order_id.          First looks up the order to get the, Get order status by client_order_id., Fetch all open positions from Alpaca., Fetch account state from Alpaca., Parse Alpaca order JSON into BrokerOrderResponse. (+7 more)

### Community 22 - "Resample Helper & Tests"
Cohesion: 0.16
Nodes (12): available_frequencies(), DataFrame, Resample 1-min raw bars to higher frequencies.  Source of truth is 1-min. All do, Resample a 1-min OHLCV DataFrame to a higher frequency.      Args:         df: D, Detect what frequencies the data can be resampled to based on the index., resample_to(), 1-min data should resample to daily correctly., DataFrame (+4 more)

### Community 23 - "Research Backtest Runner"
Cohesion: 0.11
Nodes (9): BrokerAccount, Set the current price for a symbol (for testing)., Cancel an order. Returns True if cancelled, False if not found/cancellable., Get current price for a symbol., Clear all positions (simulate manual close)., A simulated broker with configurable failure modes.      Use this to test the en, SimBroker, TestCancelOrder (+1 more)

### Community 24 - "Monitoring Watcdog"
Cohesion: 0.12
Nodes (14): broker(), engine(), _make_bars(), _make_config(), Same target twice → no duplicate orders., Rejected order → no position change., Timeout → reconcile, not retry blindly., Partial fill → position = filled qty, remaining tracked. (+6 more)

### Community 25 - "CLI Interface"
Cohesion: 0.13
Nodes (16): _extract_trades_from_replay(), _make_config(), _make_synthetic_bars(), Golden comparison: MA engine replay vs vectorbt research baseline.  This is the, Generate synthetic daily OHLCV for golden comparison., Extract trade-like info from replay events., Golden comparison: engine replay must match vectorbt baseline., VectorBT and engine replay should produce the same trade count. (+8 more)

### Community 26 - "Storage Event Logger"
Cohesion: 0.14
Nodes (16): compute_dsr(), _dsr_pvalue(), _dsr_statistic(), DSRResult, estimate_m_eff_corr(), Deflated Sharpe Ratio (DSR).  Answers: "Given the number of trials/strategies/pa, Compute the Deflated Sharpe Ratio.      Args:         observed_sharpe: The best, Compute the DSR p-value for a given M and T.      Under the null hypothesis, the (+8 more)

### Community 27 - "Parquet IO"
Cohesion: 0.14
Nodes (7): BrokerOrderRequest, Request to submit an order to a broker., TestSubmitOrder, Verify client_order_id is passed through to Binance for idempotency., TestClientIdPassthrough, TestGetOrderStatus, TestSubmitOrder

### Community 28 - "Market Data Testing"
Cohesion: 0.14
Nodes (11): Freeze new order submission (after DB failure, etc.)., Generate a deterministic client_order_id.          Format: {strategy}_{symbol}_{, Create an order intent, log to DB, and submit to broker.          Returns client, Log the order intent to DB (orders_live + events)., Any, Connection, Write one event row. Returns the event id., utc_now_iso() (+3 more)

### Community 29 - "Position Data Model"
Cohesion: 0.19
Nodes (10): compute_position_delta(), Compute the delta between target and current position.      Returns:         {"a, A target position for one symbol., TargetPosition, RiskLimits, PortfolioState, Tests for portfolio sizing and target position construction., state() (+2 more)

### Community 30 - "Active Alert Querying"
Cohesion: 0.16
Nodes (16): Bollinger Bands Strategy, Cross-Sectional Mean Reversion (CSMR), Deflated Sharpe Ratio (DSR), Execution Skeleton, The Gauntlet, Live Deployment Gate, MA Baseline Strategy, Monte Carlo Simulation (MC) (+8 more)

### Community 31 - "BB Strategy Skeleton"
Cohesion: 0.14
Nodes (10): BrokerOrderRequest, BrokerOrderResponse, BrokerPosition, Submit an order — may reject, timeout, or partially fill based on config., Get the current status of an order., Get current positions — may be stale or mismatched per config., Update internal position after a fill., Inject a position for testing reconciliation. (+2 more)

### Community 32 - "CSMR Strategy Skeleton"
Cohesion: 0.20
Nodes (6): _make_request(), Tests for the simulated broker — the malicious fake broker., Same target twice → no duplicate orders (idempotency)., TestIdempotency, TestPositionMismatch, TestSimBrokerBasic

### Community 33 - "Pairs Strategy Skeleton"
Cohesion: 0.18
Nodes (8): AssetClass, Dispatch to the right cost function by asset class., Approximate total cost as a percentage of notional (for quick vectorized backtes, Total cost for a buy + sell round trip, as % of notional., Cost breakdown for a single round-trip or per-side trade., Cost for a single equity trade (one side)., Cost for a single crypto trade (one side)., TradeCost

### Community 34 - "Community 34"
Cohesion: 0.24
Nodes (12): analyze_stability(), _check_isolated_peak(), _compute_sensitivity(), _estimate_step_size(), Parameter stability analysis.  Checks that the selected parameters are on a stab, Check if the best result is an isolated peak (neighbors are much worse).      An, Estimate the step size for a numeric parameter column., Compute how sensitive Sharpe is to each parameter.      Returns a dict {param: s (+4 more)

### Community 35 - "Community 35"
Cohesion: 0.17
Nodes (7): Submit an invalid order and verify it's rejected without position change., Live smoke tests against Alpaca paper account., Verify account fetch returns real data., Verify positions fetch works (may be empty)., Verify price fetch for a liquid symbol., Submit a tiny paper order, verify it, then cancel it.          Uses a limit orde, TestAlpacaLiveSmoke

### Community 36 - "Community 36"
Cohesion: 0.17
Nodes (7): Submit an invalid order and verify rejection., Live smoke tests against Binance testnet., Verify account/balance fetch returns real data., Verify positions fetch works (may be empty)., Verify price fetch for a major pair., Submit a tiny limit order on testnet, verify, then cancel., TestCCXTLiveSmoke

### Community 37 - "Community 37"
Cohesion: 0.26
Nodes (5): Configuration for the simulated broker's failure modes., SimBrokerConfig, TestStaleData, TestTimeouts, TestUnreachable

### Community 38 - "Community 38"
Cohesion: 0.20
Nodes (10): Any, Config, DataFrame, Path, Engine replay mode — historical bars through the full pipeline.  This is the dep, Results of a replay run., Run a replay backtest — historical bars through the full engine.      Args:, ReplayResult (+2 more)

### Community 39 - "Community 39"
Cohesion: 0.27
Nodes (5): DataFrame, _make_sweep_results(), Generate parameter sweep results.      If stable=True, creates a smooth plateau., If the plateau region straddles positive and negative, it's unstable., TestAnalyzeStability

### Community 40 - "Community 40"
Cohesion: 0.18
Nodes (6): All three p-value methods should be computed., If DSR passes with M_eff but fails with M_raw, it should not pass., A high Sharpe with long track record and few trials should pass., A low Sharpe should fail DSR., With many trials, even a decent Sharpe should be deflated., TestComputeDSR

### Community 41 - "Community 41"
Cohesion: 0.24
Nodes (9): GauntletResult, Any, DataFrame, ndarray, Series, Validation gauntlet — orchestrates WFA + MC + DSR + parameter stability.  This i, Final result of the validation gauntlet., Run the full validation gauntlet on a strategy.      Args:         strategy_name (+1 more)

### Community 42 - "Community 42"
Cohesion: 0.31
Nodes (5): check_wfa_consistency(), Check if the same parameter region performs well across WFA folds.      Args:, Tests for parameter stability analysis., TestWFAConsistency, Any

### Community 43 - "Community 43"
Cohesion: 0.38
Nodes (4): estimate_m_cluster(), Estimate M by clustering the parameter space.      Groups parameter combinations, Tests for Deflated Sharpe Ratio., TestEstimateMCluster

### Community 44 - "Community 44"
Cohesion: 0.33
Nodes (3): Process the broker's response and update state., Update order state in DB, validating transitions., Reconcile a timed-out order by querying the broker.          Does NOT retry blin

### Community 45 - "Community 45"
Cohesion: 0.33
Nodes (5): pytest_collection_modifyitems(), pytest_configure(), Pytest configuration — skip live_broker tests by default., Load .env before test collection., Skip live_broker tests unless RUN_LIVE_BROKER_TESTS=1 is set.

### Community 46 - "Community 46"
Cohesion: 0.30
Nodes (3): Connection, db(), TestSchema

### Community 47 - "Community 47"
Cohesion: 0.40
Nodes (3): Partial fill → position = filled qty, remaining tracked., Cancelled partial fill → filled qty preserved., TestPartialFills

## Knowledge Gaps
- **24 isolated node(s):** `Any`, `Response`, `BrokerOrderRequest`, `BrokerAccount`, `BrokerOrderRequest` (+19 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `WFATier` connect `Walk-Forward Analysis & Tests` to `Storage Schema & Repository`?**
  _High betweenness centrality (0.213) - this node is a cross-community bridge._
- **Why does `run_wfa()` connect `Walk-Forward Analysis & Tests` to `Community 41`?**
  _High betweenness centrality (0.152) - this node is a cross-community bridge._
- **Why does `SimBroker` connect `Research Backtest Runner` to `CSMR Strategy Skeleton`, `Community 37`, `Community 38`, `DSR (Deflated Sharpe Ratio)`, `Storage Schema & Repository`, `Community 47`, `Community 48`, `Engine Runtime & Replay`, `Sim Broker & Tests`, `Community 49`, `Monitoring Watcdog`, `BB Strategy Skeleton`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Are the 38 inferred relationships involving `SimBroker` (e.g. with `Any` and `Config`) actually correct?**
  _`SimBroker` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `EventLogger` (e.g. with `DrawdownState` and `EngineMode`) actually correct?**
  _`EventLogger` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Are the 46 inferred relationships involving `DrawdownState` (e.g. with `DrawdownState` and `Any`) actually correct?**
  _`DrawdownState` has 46 INFERRED edges - model-reasoned connections that need verification._
- **Are the 59 inferred relationships involving `PortfolioState` (e.g. with `DrawdownState` and `Any`) actually correct?**
  _`PortfolioState` has 59 INFERRED edges - model-reasoned connections that need verification._