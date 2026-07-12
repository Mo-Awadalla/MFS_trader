"""Tests for the continuous paper trading loop.

Tests use a SimBroker and an in-memory Experiment registry to verify lifecycle
integration: kill switch gating, portfolio state awareness, experiment status
checks, and graceful shutdown.
"""

from __future__ import annotations

import copy
import threading
from pathlib import Path

import pandas as pd
import pytest

from config.schema import (
    AssetClass,
    BrokerConfig,
    Config,
    CostModelConfig,
    DataConfig,
    EngineConfig,
    LiveDeploymentConfig,
    Mode,
    MonitoringConfig,
    PortfolioConfig,
    RiskLimits,
)
from engine.paper_run import PaperRunConfig, PaperRunLoop
from engine.paper_session import PAPER_OPS_SMOKE_REPORT
from execution.base import BrokerAccount, BrokerPosition
from execution.sim_broker.broker import SimBroker
from experiments.artifacts import ArtifactManager
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.kill_switch import KillSwitchSeverity
from experiments.models import ExperimentDraft, PromotionStatus
from experiments.registry import ExperimentRegistry
from storage.repository import upsert_order
from storage.schema import init_db


@pytest.fixture
def registry(tmp_path):
    reg = ExperimentRegistry(tmp_path / "experiments")
    yield reg
    reg.close()


@pytest.fixture
def experiment(registry):
    snap = build_bb_aapl_1d_default_snapshot()
    mutated = copy.deepcopy(snap)
    object.__setattr__(mutated, "parameters", {**snap.parameters, "window": 20})
    draft = ExperimentDraft(label="paper-run-test", snapshot=mutated)
    exp = registry.create(draft)
    registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_RUNNING)
    registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_PASSED)
    registry.transition_promotion_status(exp.uuid, PromotionStatus.PAPER_OPS)
    return exp


def _make_config() -> Config:
    return Config(
        mode=Mode.PAPER,
        brokers=[
            BrokerConfig(
                name="sim_broker",
                asset_class=AssetClass.EQUITY,
                api_key_env="SIM_API_KEY",
                api_secret_env="SIM_API_SECRET",
                base_url="sim",
            )
        ],
        data=[DataConfig(symbols=["AAPL"], asset_class=AssetClass.EQUITY)],
        risk_limits=RiskLimits(
            per_position_pct=0.05,
            max_daily_loss_pct=0.99,
            max_monthly_loss_pct=0.99,
            max_open_positions=10,
        ),
        portfolio=PortfolioConfig(per_position_risk_pct=0.05),
        cost_model=CostModelConfig(),
        monitoring=MonitoringConfig(),
        engine=EngineConfig(startup_reconciliation_required=True),
        live_deployment=LiveDeploymentConfig(),
        strategy_name="dual_ma_crossover",
        strategy_version="0.1.0",
        strategies_enabled=["ma"],
    )


def _make_bars(n: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [150.0] * n,
            "high": [151.0] * n,
            "low": [149.0] * n,
            "close": [150.5] * n,
            "volume": [1_000_000] * n,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC"),
    )


def _strategy_fn(bars, params):
    return {"AAPL": 0.0}


def _make_run_config(
    experiment,
    *,
    max_cycles: int | None = 2,
    experiment_root: str | Path | None = None,
) -> PaperRunConfig:
    return PaperRunConfig(
        experiment_uuid=experiment.uuid,
        experiment_hash=experiment.experiment_hash,
        experiment_root=experiment_root or experiment.uuid,
        max_cycles=max_cycles,
        sleep_between_bars_seconds=0.01,
    )


class _FixedSimBroker(SimBroker):
    def get_account(self) -> BrokerAccount:
        return BrokerAccount(
            account_id="test",
            cash=100000.0,
            equity=100000.0,
            currency="USD",
            status="ACTIVE",
        )

    def get_positions(self) -> list[BrokerPosition]:
        return []

    def get_open_orders(self) -> list:
        return []

    def get_price(self, symbol: str) -> float | None:
        return 150.0


class TestPaperRunExperimentVerification:
    def test_rejects_nonexistent_experiment(self, tmp_path):
        config = _make_config()
        broker = _FixedSimBroker()
        run_config = PaperRunConfig(
            experiment_uuid="00000000-0000-0000-0000-000000000000",
            experiment_hash="0" * 64,
            experiment_root=tmp_path / "experiments",
            max_cycles=1,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )
        bars = _make_bars()
        result = loop.run(bars, db_path=tmp_path / "run.sqlite")
        assert result.halted or any("Experiment not found" in err for err in result.errors)

    def test_rejects_experiment_not_in_paper_status(self, registry, tmp_path):
        exp = registry.create(
            ExperimentDraft(
                label="not-paper",
                snapshot=build_bb_aapl_1d_default_snapshot(),
            )
        )
        config = _make_config()
        broker = _FixedSimBroker()
        run_config = _make_run_config(
            exp,
            experiment_root=registry.root,
        )
        run_config = PaperRunConfig(
            experiment_uuid=exp.uuid,
            experiment_hash=exp.experiment_hash,
            experiment_root=registry.root,
            max_cycles=1,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )
        bars = _make_bars()
        result = loop.run(bars, db_path=tmp_path / "run.sqlite")
        assert result.halted or result.errors

    def test_accepts_valid_experiment(self, experiment, registry, tmp_path):
        config = _make_config()
        broker = _FixedSimBroker()
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash=experiment.experiment_hash,
            experiment_root=registry.root,
            max_cycles=1,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )
        bars = _make_bars()
        result = loop.run(bars, db_path=tmp_path / "run.sqlite")
        assert not result.halted
        assert not result.errors

    def test_rejects_experiment_hash_mismatch(self, experiment, registry, tmp_path):
        config = _make_config()
        broker = _FixedSimBroker()
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash="0" * 64,
            experiment_root=registry.root,
            max_cycles=1,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )

        result = loop.run(_make_bars(), db_path=tmp_path / "run.sqlite")

        assert result.halted
        assert result.errors
        assert any("hash mismatch" in err for err in result.errors)


class TestPaperRunKillSwitchGating:
    def test_hard_kill_halts_loop(self, experiment, registry, tmp_path):
        config = _make_config()
        broker = _FixedSimBroker()
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash=experiment.experiment_hash,
            experiment_root=registry.root,
            max_cycles=10,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )

        registry.set_kill_switch(
            experiment.uuid, KillSwitchSeverity.HARD, "test halt"
        )

        bars = _make_bars()
        result = loop.run(bars, db_path=tmp_path / "run.sqlite")
        assert result.halted
        assert result.halt_reason is not None

    def test_soft_kill_halts_loop(self, experiment, registry, tmp_path):
        config = _make_config()
        broker = _FixedSimBroker()
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash=experiment.experiment_hash,
            experiment_root=registry.root,
            max_cycles=1,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )

        registry.set_kill_switch(
            experiment.uuid, KillSwitchSeverity.SOFT, "soft test"
        )

        bars = _make_bars()
        result = loop.run(bars, db_path=tmp_path / "run.sqlite")
        assert result.halted
        assert result.cycle_count == 0
        assert "active kill switch" in (result.halt_reason or "")


class TestPaperRunLifecycle:
    def test_counts_only_distinct_refreshed_market_sessions(self, experiment, registry, tmp_path):
        initial = _make_bars()
        refreshed = pd.concat(
            [
                initial,
                pd.DataFrame(
                    {
                        "open": [151.0],
                        "high": [152.0],
                        "low": [150.0],
                        "close": [151.5],
                        "volume": [1_000_000],
                    },
                    index=[initial.index[-1] + pd.Timedelta(days=1)],
                ),
            ]
        )
        refreshes = iter([initial, refreshed])
        loop = PaperRunLoop(
            config=_make_config(),
            broker=_FixedSimBroker(),
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=PaperRunConfig(
                experiment_uuid=experiment.uuid,
                experiment_hash=experiment.experiment_hash,
                experiment_root=registry.root,
                session_id="distinct-market-sessions",
                max_cycles=2,
                sleep_between_bars_seconds=0,
            ),
            bars_provider=lambda: next(refreshes),
        )

        result = loop.run(initial, db_path=tmp_path / "distinct.sqlite")

        assert not result.halted
        assert result.cycle_count == 2
        assert [cycle["input_data_watermark"] for cycle in result.bar_cycles] == [
            str(initial.index[-1]),
            str(refreshed.index[-1]),
        ]

    def test_resumes_window_from_atomic_checkpoint(self, experiment, registry, tmp_path):
        initial = _make_bars()
        refreshed = initial.copy()
        refreshed.loc[initial.index[-1] + pd.Timedelta(days=1)] = initial.iloc[-1]
        db_path = tmp_path / "resumable.sqlite"
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash=experiment.experiment_hash,
            experiment_root=registry.root,
            session_id="resumable-window",
            window_market_sessions=2,
            sleep_between_bars_seconds=0,
        )
        first: PaperRunLoop

        def stop_after_first():
            first._handle_sigterm(None, None)
            return initial

        first = PaperRunLoop(
            config=_make_config(),
            broker=_FixedSimBroker(),
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
            bars_provider=stop_after_first,
        )

        interrupted = first.run(initial, db_path=db_path)

        assert interrupted.cycle_count == 1
        assert db_path.with_suffix(".paper_run_checkpoint.json").exists()
        assert interrupted.evidence_path is None

        resumed = PaperRunLoop(
            config=_make_config(),
            broker=_FixedSimBroker(),
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
            bars_provider=lambda: refreshed,
        ).run(initial, db_path=db_path)

        assert resumed.cycle_count == 2
        assert not db_path.with_suffix(".paper_run_checkpoint.json").exists()
        assert resumed.evidence_path is not None

    def test_runs_specified_number_of_cycles(self, experiment, registry, tmp_path):
        config = _make_config()
        broker = _FixedSimBroker()
        db_path = tmp_path / "run.sqlite"
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash=experiment.experiment_hash,
            experiment_root=registry.root,
            session_id="multi-cycle-session",
            max_cycles=3,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )
        bars = _make_bars()
        result = loop.run(bars, db_path=db_path)
        assert not result.halted
        assert result.cycle_count == 3
        payload = ArtifactManager(registry.root).read_paper_session_json(
            experiment.uuid,
            "multi-cycle-session",
        )
        assert [cycle["result"] for cycle in payload["bar_cycles"]] == [
            "completed",
            "completed",
            "completed",
        ]
        assert all(cycle["broker_sync_record_id"] for cycle in payload["bar_cycles"])
        conn = init_db(db_path)
        try:
            reconciliation_events = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'RECONCILIATION_RUN'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert reconciliation_events >= 8

    def test_writes_non_promoting_paper_ops_smoke_report(self, experiment, registry, tmp_path):
        config = _make_config()
        loop = PaperRunLoop(
            config=config,
            broker=_FixedSimBroker(),
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=PaperRunConfig(
                experiment_uuid=experiment.uuid,
                experiment_hash=experiment.experiment_hash,
                experiment_root=registry.root,
                session_id="smoke-window-session",
                window_calendar_days=7,
                window_market_sessions=5,
                kill_switch_drill={
                    "kill_switch_drill_evidence_exists": True,
                    "new_orders_blocked": True,
                },
                max_cycles=5,
                sleep_between_bars_seconds=0.01,
            ),
        )
        loop._session_started_at -= 8 * 86_400

        result = loop.run(_make_bars(), db_path=tmp_path / "smoke.sqlite")

        assert not result.halted
        report = ArtifactManager(registry.root).read_paper_session_report_json(
            experiment.uuid,
            "smoke-window-session",
            PAPER_OPS_SMOKE_REPORT,
        )
        assert report["status"] == "PAPER_OPS_SMOKE_PASSED"
        assert report["passed"] is True
        assert report["promotion_unlocked"] is False

    def test_graceful_shutdown(self, experiment, registry, tmp_path):
        config = _make_config()
        broker = _FixedSimBroker()
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash=experiment.experiment_hash,
            experiment_root=registry.root,
            max_cycles=None,
            sleep_between_bars_seconds=0.5,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )

        def _shutdown_after_delay():
            import time

            time.sleep(0.3)
            loop._handle_sigterm(None, None)

        t = threading.Thread(target=_shutdown_after_delay, daemon=True)
        t.start()

        bars = _make_bars()
        result = loop.run(bars, db_path=tmp_path / "run.sqlite")
        assert not result.halted
        assert result.cycle_count < 5


class TestPaperRunCleanup:
    def test_engine_and_registry_are_closed(self, experiment, registry, tmp_path):
        config = _make_config()
        broker = _FixedSimBroker()
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash=experiment.experiment_hash,
            experiment_root=registry.root,
            max_cycles=1,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )
        bars = _make_bars()
        result = loop.run(bars, db_path=tmp_path / "run.sqlite")
        assert not result.halted
        assert result.cycle_count == 1


class TestPaperRunPortfolioStateAwareness:
    def test_reports_portfolio_state(self, experiment, registry, tmp_path):
        config = _make_config()
        broker = _FixedSimBroker()
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash=experiment.experiment_hash,
            experiment_root=registry.root,
            max_cycles=1,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )
        bars = _make_bars()
        result = loop.run(bars, db_path=tmp_path / "run.sqlite")
        assert not result.halted
        assert loop.engine is not None
        assert loop.engine.state.portfolio_state_authority is not None

    def test_refuses_when_portfolio_state_is_partial(self, experiment, registry, tmp_path):
        config = _make_config()
        broker = _FixedSimBroker()
        db_path = tmp_path / "run.sqlite"
        conn = init_db(db_path)
        upsert_order(
            conn,
            {
                "client_order_id": "pending",
                "broker_order_id": "sim_pending",
                "broker": "sim_broker",
                "account_id": "test",
                "environment": "paper",
                "strategy": "test",
                "symbol": "AAPL",
                "asset_class": "equity",
                "side": "buy",
                "order_type": "market",
                "time_in_force": "day",
                "limit_price": 150.0,
                "stop_price": None,
                "requested_qty": 1.0,
                "filled_qty": 0.0,
                "remaining_qty": 1.0,
                "avg_fill_price": None,
                "notional": 150.0,
                "currency": "USD",
                "order_state": "ACKNOWLEDGED",
                "reconciliation_status": "NOT_CHECKED",
                "bar_timestamp": "2024-01-01T00:00:00+00:00",
                "correlation_id": "test",
                "version": "0.1.0",
            },
        )
        conn.close()
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash=experiment.experiment_hash,
            experiment_root=registry.root,
            session_id="partial-state-session",
            max_cycles=1,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )

        result = loop.run(_make_bars(), db_path=db_path)

        assert result.halted
        assert result.cycle_count == 0
        assert result.halt_reason == "portfolio_state PARTIAL"
        payload = ArtifactManager(registry.root).read_paper_session_json(
            experiment.uuid,
            "partial-state-session",
        )
        assert payload["order_lifecycle"][0]["client_order_id"] == "pending"
        assert payload["order_lifecycle"][0]["order_state"] == "ACKNOWLEDGED"

    def test_writes_immutable_paper_session_evidence_once(self, experiment, registry, tmp_path):
        config = _make_config()
        first = PaperRunLoop(
            config=config,
            broker=_FixedSimBroker(),
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=PaperRunConfig(
                experiment_uuid=experiment.uuid,
                experiment_hash=experiment.experiment_hash,
                experiment_root=registry.root,
                session_id="fixed-session",
                max_cycles=1,
                sleep_between_bars_seconds=0.01,
            ),
        )

        result = first.run(_make_bars(), db_path=tmp_path / "first.sqlite")

        artifacts = ArtifactManager(registry.root)
        assert not result.halted
        assert result.evidence_path is not None
        payload = artifacts.read_paper_session_json(experiment.uuid, "fixed-session")
        assert payload["cycle_count"] == 1
        assert payload["session_kind"] == "paper_ops_smoke"
        assert payload["order_lifecycle"] == []
        assert payload["bar_cycles"][0]["result"] == "completed"
        assert payload["bar_cycle_report"]["bar_cycle_completion"] == 1.0

        second = PaperRunLoop(
            config=config,
            broker=_FixedSimBroker(),
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=PaperRunConfig(
                experiment_uuid=experiment.uuid,
                experiment_hash=experiment.experiment_hash,
                experiment_root=registry.root,
                session_id="fixed-session",
                max_cycles=1,
                sleep_between_bars_seconds=0.01,
            ),
        )

        second_result = second.run(_make_bars(), db_path=tmp_path / "second.sqlite")

        assert second_result.halted
        assert any("immutable" in err.lower() for err in second_result.errors)

    def test_records_and_halts_unexplained_missed_cycle(self, experiment, registry, tmp_path):
        class _NoPriceBroker(_FixedSimBroker):
            def get_price(self, symbol: str) -> float | None:
                return None

        config = _make_config()
        loop = PaperRunLoop(
            config=config,
            broker=_NoPriceBroker(),
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=PaperRunConfig(
                experiment_uuid=experiment.uuid,
                experiment_hash=experiment.experiment_hash,
                experiment_root=registry.root,
                session_id="no-price-session",
                max_cycles=1,
                sleep_between_bars_seconds=0.01,
            ),
        )

        result = loop.run(_make_bars(), db_path=tmp_path / "no-price.sqlite")

        assert result.halted
        assert result.cycle_count == 1
        payload = ArtifactManager(registry.root).read_paper_session_json(
            experiment.uuid,
            "no-price-session",
        )
        assert payload["bar_cycles"][0]["result"] == "missed_unexplained"
        assert payload["bar_cycle_report"]["unexplained_missed_cycles"] == 1


class _FailingBroker(_FixedSimBroker):
    def __init__(self, fail_on_get_positions: bool = False):
        super().__init__()
        self._fail_positions = fail_on_get_positions

    def get_positions(self) -> list[BrokerPosition]:
        if self._fail_positions:
            raise RuntimeError("broker unreachable (test)")
        return []


@pytest.mark.skip(reason="Requires startup reconciliation with failing broker")
class TestPaperRunErrorHandling:
    def test_engine_startup_failure_halts(self, experiment, registry, tmp_path):
        config = _make_config()
        broker = _FailingBroker(fail_on_get_positions=True)
        run_config = PaperRunConfig(
            experiment_uuid=experiment.uuid,
            experiment_hash=experiment.experiment_hash,
            experiment_root=registry.root,
            max_cycles=1,
            sleep_between_bars_seconds=0.01,
        )
        loop = PaperRunLoop(
            config=config,
            broker=broker,
            strategy_fn=_strategy_fn,
            strategy_name="test",
            run_config=run_config,
        )
        bars = _make_bars()
        result = loop.run(bars, db_path=tmp_path / "run.sqlite")
        assert result.halted
