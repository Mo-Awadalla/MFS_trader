from __future__ import annotations

import copy

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
from engine import cli
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.models import ExperimentDraft, PromotionStatus
from experiments.registry import ExperimentRegistry
from storage.event_logger import EventLogger
from storage.schema import init_db
from tests.qualification import enter_paper_ops


def test_engine_cli_help_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    assert "mfs-engine" in capsys.readouterr().out


def test_engine_preflight_loads_paper_config(capsys):
    rc = cli.main(["--config", "config/paper.toml", "preflight"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Config OK" in out
    assert "mode: paper" in out


def test_engine_report_command_reads_sqlite(tmp_path, capsys):
    db_path = tmp_path / "engine.sqlite"
    conn = init_db(db_path)
    logger = EventLogger(conn, environment="paper")
    logger.log("ENGINE_HEARTBEAT", cycle_id="cycle-1", message="Processing bar 2024-01-01")
    logger.log("ENGINE_HEARTBEAT", cycle_id="cycle-1", message="Bar 2024-01-01 complete — cycle 1")
    conn.close()

    rc = cli.main(["report", "--db", str(db_path), "--allow-blockers"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Operational Report" in out
    assert "Bars started/completed: 1/1" in out


def _make_paper_config() -> Config:
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


def _paper_ops_experiment(registry: ExperimentRegistry):
    snap = build_bb_aapl_1d_default_snapshot()
    mutated = copy.deepcopy(snap)
    object.__setattr__(mutated, "parameters", {**snap.parameters, "window": 20})
    exp = registry.create(ExperimentDraft(label="cli-paper-run", snapshot=mutated))
    registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_RUNNING)
    registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_PASSED)
    return enter_paper_ops(registry, exp.uuid)


def test_paper_run_cli_refuses_alpaca_paper_before_broker_construction(
    tmp_path, monkeypatch, capsys
):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _paper_ops_experiment(registry)
        monkeypatch.setattr(cli, "load_config", lambda path, **kwargs: _make_paper_config())

        rc = cli.main(
            [
                "--config",
                "unused.toml",
                "paper-run",
                "--experiment-root",
                str(registry.root),
                "--experiment-uuid",
                exp.uuid,
                "--experiment-hash",
                exp.experiment_hash,
                "--broker",
                "alpaca_paper",
                "--session-id",
                "alpaca-refuse",
                "--max-cycles",
                "1",
            ]
        )

        assert rc == 1
        assert "max_notional_per_order" in capsys.readouterr().err
    finally:
        registry.close()


def test_paper_run_cli_exposes_explicit_alpaca_smoke_mode():
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "--config",
            "unused.toml",
            "paper-run",
            "--experiment-root",
            "experiments",
            "--experiment-uuid",
            "fd42a55c-abc4-59f3-abd3-c70c0380482b",
            "--experiment-hash",
            "a" * 64,
            "--broker",
            "alpaca_paper",
            "--confirm-paper-broker",
            "--alpaca-paper-smoke",
            "--session-id",
            "smoke",
        ]
    )

    assert args.broker == "alpaca_paper"
    assert args.confirm_paper_broker is True
    assert args.alpaca_paper_smoke is True
