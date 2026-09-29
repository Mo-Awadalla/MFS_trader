from __future__ import annotations

import copy
import json
import sqlite3
from dataclasses import asdict, replace

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
from engine.paper_evidence import digest
from config.loader import load_config
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.models import ExperimentDraft, PromotionStatus
from experiments.registry import ExperimentRegistry
from storage.event_logger import EventLogger
from storage.schema import init_db
from tests.qualification import enter_paper_ops
from strategies.ma.signal import MAParams
from tests.unit.test_paper_strategy import snapshot_for_config


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


@pytest.mark.parametrize("command", ["paper-trade-ma", "paper-dry-run-ma"])
def test_retired_legacy_cli_cannot_load_configuration(command, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("retired route reached configuration or credentials")
    monkeypatch.setattr(cli, "load_config", forbidden)
    monkeypatch.setattr(cli, "get_broker_creds", forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--config", "unused.toml", command])
    assert exc.value.code == 2


def test_retired_smoke_repeated_session_different_symbol_has_no_effects(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("retired smoke reached credentials or configuration")
    monkeypatch.setattr(cli, "load_config", forbidden)
    monkeypatch.setattr(cli, "get_broker_creds", forbidden)
    monkeypatch.setattr(cli, "AlpacaAdapter", forbidden)
    for symbol in ("AAPL", "MSFT"):
        with pytest.raises(SystemExit) as exc:
            cli.main(["--config", "unused.toml", "paper-run",
                      "--experiment-root", str(tmp_path / "experiments"),
                      "--experiment-uuid", "synthetic", "--experiment-hash", "a" * 64,
                      "--broker", "alpaca_paper", "--confirm-paper-broker",
                      "--alpaca-paper-smoke", "--session-id", "same-smoke", "--symbol", symbol])
        assert exc.value.code == 2
    assert not (tmp_path / "experiments").exists()


@pytest.fixture
def qualified_ma(tmp_path, monkeypatch):
    config = load_config("builtin:paper_shakedown", load_env=False)
    config = replace(config, live_deployment=replace(
        config.live_deployment, max_notional_per_order=25.,
        max_paper_session_notional=100., max_open_paper_exposure=100.,
    ))
    registry = ExperimentRegistry(tmp_path / "experiments")
    experiment = registry.create(ExperimentDraft(
        label="synthetic CLI MA", snapshot=snapshot_for_config(
            config, parameters=asdict(MAParams()), symbols=("AAPL",),
        ),
    ))
    registry.transition_promotion_status(experiment.uuid, PromotionStatus.VALIDATION_RUNNING)
    registry.transition_promotion_status(experiment.uuid, PromotionStatus.VALIDATION_PASSED)
    experiment = enter_paper_ops(registry, experiment.uuid)
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: config)
    from engine.shakedown import make_synthetic_bars
    monkeypatch.setattr("data.pipeline.load_bars", lambda *a, **k: make_synthetic_bars(n=240, seed=21))
    args = ["--config", "unused.toml", "paper-run",
            "--experiment-root", str(registry.root), "--experiment-uuid", experiment.uuid,
            "--experiment-hash", experiment.experiment_hash, "--broker", "alpaca_paper",
            "--confirm-paper-broker", "--session-id", "admission",
            "--out-dir", str(tmp_path / "output"), "--max-cycles", "1"]
    yield config, registry, experiment, args
    registry.close()


@pytest.mark.parametrize("url", ["https://attacker.invalid", "http://data.alpaca.markets", "https://data.alpaca.markets@attacker.invalid"])
def test_cli_wrong_data_origin_precedes_credentials(qualified_ma, monkeypatch, url):
    config, registry, experiment, args = qualified_ma
    config = replace(config, brokers=[replace(config.brokers[0], data_url=url)])
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: config)
    def forbidden(*args, **kwargs):
        raise AssertionError("untrusted data origin reached credentials")
    monkeypatch.setattr(cli, "get_broker_creds", forbidden)
    monkeypatch.setattr(cli, "AlpacaAdapter", forbidden)
    assert cli.main(args) == 1


def test_cli_wrong_checkpoint_precedes_credentials(qualified_ma, tmp_path, monkeypatch):
    _, _, _, args = qualified_ma
    output = tmp_path / "output"
    output.mkdir()
    payload = {"identity": {"session_id": "another-session"}, "halted": False, "halt_reason": None, "errors": []}
    checkpoint = output / "paper_run.paper_run_checkpoint.json"
    checkpoint.write_text(json.dumps({"payload": payload, "sha256": digest(payload)}))
    before = checkpoint.read_bytes()
    def forbidden(*args, **kwargs):
        raise AssertionError("mismatched checkpoint reached credentials or broker")
    monkeypatch.setattr(cli, "get_broker_creds", forbidden)
    monkeypatch.setattr(cli, "AlpacaAdapter", forbidden)
    assert cli.main(args) == 1
    assert checkpoint.read_bytes() == before
    with sqlite3.connect(output / "paper_run.sqlite") as conn:
        outcome, reason = conn.execute("SELECT outcome,reason FROM paper_attempts").fetchone()
    assert outcome == "halted"
    assert "checkpoint" in reason


def test_cli_durably_starts_attempt_before_credentials(qualified_ma, tmp_path, monkeypatch):
    _, _, _, args = qualified_ma
    calls = []
    def unavailable_credentials(*args, **kwargs):
        with sqlite3.connect(tmp_path / "output" / "paper_run.sqlite") as conn:
            calls.append(conn.execute("SELECT ended_at FROM paper_attempts").fetchall())
        raise ValueError("synthetic credential refusal")
    monkeypatch.setattr(cli, "get_broker_creds", unavailable_credentials)
    assert cli.main(args) == 1
    assert calls == [[(None,)]]
    with sqlite3.connect(tmp_path / "output" / "paper_run.sqlite") as conn:
        outcome, reason = conn.execute("SELECT outcome,reason FROM paper_attempts").fetchone()
    assert outcome == "halted"
    assert reason == "synthetic credential refusal"


@pytest.mark.parametrize("override", [
    ["--fast-window", "7"], ["--symbol", "MSFT"],
])
def test_cli_wrong_ma_hypothesis_precedes_credentials(qualified_ma, monkeypatch, override):
    _, _, _, args = qualified_ma
    def forbidden(*args, **kwargs):
        raise AssertionError("wrong MA hypothesis reached credentials or broker")
    monkeypatch.setattr(cli, "get_broker_creds", forbidden)
    monkeypatch.setattr(cli, "AlpacaAdapter", forbidden)
    assert cli.main([*args, *override]) == 1
