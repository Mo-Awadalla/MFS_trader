from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from engine import cli
from engine.ma_replay import run_ma_real_data_replay
from engine.shakedown import make_replay_config, make_synthetic_bars
from storage.parquet_io import parquet_path, write_bars


def test_ma_real_data_replay_loads_stored_bars_and_writes_comparison(tmp_path):
    bars = make_synthetic_bars(n=140, seed=11)
    config = _config_with_storage(tmp_path)
    path = parquet_path(tmp_path / "parquet", "AAPL", "1d", source="alpaca")
    write_bars(bars, path)

    result = run_ma_real_data_replay(
        config=config,
        symbol="AAPL",
        frequency="1d",
        source="alpaca",
        out_dir=tmp_path / "replay",
        fast_window=5,
        slow_window=20,
        trend_filter_active=False,
    )

    assert result.bars_loaded == 140
    assert result.research.bar_count == 140
    assert result.replay.bar_count == 140
    assert result.replay.orders_filled > 0
    assert Path(result.db_path).exists()
    assert (tmp_path / "replay" / "AAPL_1d_comparison.md").exists()
    assert (tmp_path / "replay" / "AAPL_1d_comparison.json").exists()


def test_replay_ma_cli_reports_stored_data(tmp_path, capsys):
    bars = make_synthetic_bars(n=140, seed=12)
    config = _config_with_storage(tmp_path)
    path = parquet_path(tmp_path / "parquet", "AAPL", "1d", source="alpaca")
    write_bars(bars, path)
    config_path = tmp_path / "research.toml"
    config_path.write_text(_toml_with_storage(tmp_path / "parquet"), encoding="utf-8")

    rc = cli.main(
        [
            "--config",
            str(config_path),
            "replay-ma",
            "--symbol",
            "AAPL",
            "--frequency",
            "1d",
            "--out-dir",
            str(tmp_path / "cli_replay"),
            "--fast-window",
            "5",
            "--slow-window",
            "20",
            "--no-trend-filter",
            "--allow-diffs",
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "MA real-data replay status:" in out
    assert "Replay DB:" in out
    assert (tmp_path / "cli_replay" / "AAPL_1d_comparison.md").exists()
    assert config.data[0].symbols == ["AAPL"]


def _config_with_storage(tmp_path):
    config = make_replay_config()
    data = replace(config.data[0], storage_dir=str(tmp_path / "parquet"))
    return replace(config, data=[data])


def _toml_with_storage(storage_dir: Path) -> str:
    return f"""
mode = "research"
strategy_name = "dual_ma_crossover"
strategy_version = "0.1.0"
strategies_enabled = ["ma"]

[[brokers]]
name = "sim_broker"
asset_class = "equity"
api_key_env = "SIM_API_KEY"
api_secret_env = "SIM_API_SECRET"
base_url = "sim"
is_paper = true

[[data]]
symbols = ["AAPL"]
asset_class = "equity"
bar_frequency_raw = "1min"
target_frequencies = ["1d"]
storage_dir = "{storage_dir}"

[risk_limits]
per_position_pct = 0.05
max_daily_loss_pct = 0.99
max_monthly_loss_pct = 0.99
max_open_positions = 10

[portfolio]
per_position_risk_pct = 0.05

[cost_model]
slippage_fixed_pct = 0.0005
slippage_variable_coeff = 0.5
commission_pct = 0.0
sec_fee_per_dollar_sold = 0.0000051
finra_taf_per_share_sold = 0.000119

[monitoring]
dashboard_enabled = false
telegram_alerts = false

[engine]
startup_reconciliation_required = false

[live_deployment]
authorized = false
""".strip()
