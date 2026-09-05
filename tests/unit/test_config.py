"""Tests for the config loader and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.loader import ConfigError, load_config
from config.schema import Mode

RESEARCH_CONFIG = Path(__file__).resolve().parents[2] / "config" / "research.toml"
PAPER_CONFIG = Path(__file__).resolve().parents[2] / "config" / "paper.toml"
LIVE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "live.toml"


class TestConfigLoader:
    def test_load_research_config(self):
        cfg = load_config(RESEARCH_CONFIG, load_env=False)
        assert cfg.mode == Mode.RESEARCH
        assert len(cfg.brokers) == 2
        assert len(cfg.data) == 2
        assert cfg.risk_limits.per_position_pct > 0

    def test_load_paper_config(self):
        cfg = load_config(PAPER_CONFIG, load_env=False)
        assert cfg.mode == Mode.PAPER

    def test_missing_file_raises(self):
        with pytest.raises(ConfigError):
            load_config("/nonexistent/path.toml")

    def test_research_config_has_alpaca_broker(self):
        cfg = load_config(RESEARCH_CONFIG, load_env=False)
        brokers = [b.name for b in cfg.brokers]
        assert "alpaca" in brokers

    def test_research_config_has_equity_and_crypto_data(self):
        cfg = load_config(RESEARCH_CONFIG, load_env=False)
        asset_classes = [d.asset_class.value for d in cfg.data]
        assert "equity" in asset_classes
        assert "crypto" in asset_classes

    def test_equity_data_defaults_round_trip_to_legacy_iex_and_split_dividend(self, tmp_path):
        config_path = tmp_path / "defaults.toml"
        config_path.write_text(
            """
mode = "research"
[[brokers]]
name = "alpaca"
asset_class = "equity"
api_key_env = "ALPACA_API_KEY"
api_secret_env = "ALPACA_API_SECRET"
base_url = "https://paper-api.alpaca.markets"

[[data]]
symbols = ["SPY"]
asset_class = "equity"
""",
            encoding="utf-8",
        )
        cfg = load_config(config_path, load_env=False)

        assert cfg.data[0].feed == "iex"
        assert cfg.data[0].adjustment == "split_dividend"

    def test_equity_data_explicit_sip_feed_round_trips(self, tmp_path):
        config_path = tmp_path / "sip.toml"
        config_path.write_text(
            """
mode = "research"
[[brokers]]
name = "alpaca"
asset_class = "equity"
api_key_env = "ALPACA_API_KEY"
api_secret_env = "ALPACA_API_SECRET"
base_url = "https://paper-api.alpaca.markets"

[[data]]
symbols = ["SPY"]
asset_class = "equity"
feed = "sip"
adjustment = "all"
""",
            encoding="utf-8",
        )
        cfg = load_config(config_path, load_env=False)

        assert cfg.data[0].feed == "sip"
        assert cfg.data[0].adjustment == "all"


class TestLiveConfigValidation:
    """Live mode must refuse to start without proper authorization and keys."""

    def test_live_config_refuses_without_authorization(self, monkeypatch):
        # The default live.toml has authorized=false — load_config should refuse
        with pytest.raises(ConfigError, match="authorized"):
            load_config(LIVE_CONFIG, load_env=False)

    def test_live_config_refuses_with_paper_key(self, monkeypatch, tmp_path):
        # Create a live config with authorized=true but paper-like key
        live_toml = tmp_path / "live.toml"
        live_toml.write_text(
            """
mode = "live"
strategy_name = "test"
strategy_version = "0.1.0"

[[brokers]]
name = "alpaca"
asset_class = "equity"
api_key_env = "TEST_LIVE_KEY"
api_secret_env = "TEST_LIVE_SECRET"
base_url = "https://api.alpaca.markets"
is_paper = false

[[data]]
symbols = ["AAPL"]
asset_class = "equity"

[risk_limits]
per_position_pct = 0.01
max_daily_loss_pct = 0.03
max_monthly_loss_pct = 0.15

[live_deployment]
authorized = true
starting_capital = 1000.0
max_live_capital = 2000.0
strategy_capital_limit = 200.0
"""
        )
        monkeypatch.setenv("TEST_LIVE_KEY", "PKTESTPAPERKEY123")
        monkeypatch.setenv("TEST_LIVE_SECRET", "secret")

        with pytest.raises(ConfigError, match="paper"):
            load_config(live_toml)

    def test_live_config_refuses_with_paper_url(self, monkeypatch, tmp_path):
        live_toml = tmp_path / "live.toml"
        live_toml.write_text(
            """
mode = "live"
strategy_name = "test"
strategy_version = "0.1.0"

[[brokers]]
name = "alpaca"
asset_class = "equity"
api_key_env = "TEST_LIVE_KEY"
api_secret_env = "TEST_LIVE_SECRET"
base_url = "https://paper-api.alpaca.markets"
is_paper = false

[[data]]
symbols = ["AAPL"]
asset_class = "equity"

[risk_limits]
per_position_pct = 0.01
max_daily_loss_pct = 0.03
max_monthly_loss_pct = 0.15

[live_deployment]
authorized = true
starting_capital = 1000.0
max_live_capital = 2000.0
strategy_capital_limit = 200.0
"""
        )
        monkeypatch.setenv("TEST_LIVE_KEY", "AABBCCDDEE1122334455")
        monkeypatch.setenv("TEST_LIVE_SECRET", "secret")

        with pytest.raises(ConfigError, match="paper"):
            load_config(live_toml)

    def test_live_config_refuses_with_is_paper_true(self, monkeypatch, tmp_path):
        live_toml = tmp_path / "live.toml"
        live_toml.write_text(
            """
mode = "live"
strategy_name = "test"
strategy_version = "0.1.0"

[[brokers]]
name = "alpaca"
asset_class = "equity"
api_key_env = "TEST_LIVE_KEY"
api_secret_env = "TEST_LIVE_SECRET"
base_url = "https://api.alpaca.markets"
is_paper = true

[[data]]
symbols = ["AAPL"]
asset_class = "equity"

[risk_limits]
per_position_pct = 0.01
max_daily_loss_pct = 0.03
max_monthly_loss_pct = 0.15

[live_deployment]
authorized = true
starting_capital = 1000.0
max_live_capital = 2000.0
strategy_capital_limit = 200.0
"""
        )
        monkeypatch.setenv("TEST_LIVE_KEY", "AABBCCDDEE1122334455")
        monkeypatch.setenv("TEST_LIVE_SECRET", "secret")

        with pytest.raises(ConfigError, match="paper"):
            load_config(live_toml)

    def test_live_config_refuses_without_capital(self, monkeypatch, tmp_path):
        live_toml = tmp_path / "live.toml"
        live_toml.write_text(
            """
mode = "live"
strategy_name = "test"
strategy_version = "0.1.0"

[[brokers]]
name = "alpaca"
asset_class = "equity"
api_key_env = "TEST_LIVE_KEY"
api_secret_env = "TEST_LIVE_SECRET"
base_url = "https://api.alpaca.markets"
is_paper = false

[[data]]
symbols = ["AAPL"]
asset_class = "equity"

[risk_limits]
per_position_pct = 0.01
max_daily_loss_pct = 0.03
max_monthly_loss_pct = 0.15

[live_deployment]
authorized = true
starting_capital = 0
max_live_capital = 2000.0
strategy_capital_limit = 200.0
"""
        )
        monkeypatch.setenv("TEST_LIVE_KEY", "AABBCCDDEE1122334455")
        monkeypatch.setenv("TEST_LIVE_SECRET", "secret")

        with pytest.raises(ConfigError, match="capital"):
            load_config(live_toml)

    def test_live_config_refuses_missing_key(self, monkeypatch, tmp_path):
        live_toml = tmp_path / "live.toml"
        live_toml.write_text(
            """
mode = "live"
strategy_name = "test"
strategy_version = "0.1.0"

[[brokers]]
name = "alpaca"
asset_class = "equity"
api_key_env = "MISSING_LIVE_KEY"
api_secret_env = "MISSING_LIVE_SECRET"
base_url = "https://api.alpaca.markets"
is_paper = false

[[data]]
symbols = ["AAPL"]
asset_class = "equity"

[risk_limits]
per_position_pct = 0.01
max_daily_loss_pct = 0.03
max_monthly_loss_pct = 0.15

[live_deployment]
authorized = true
starting_capital = 1000.0
max_live_capital = 2000.0
strategy_capital_limit = 200.0
"""
        )
        monkeypatch.delenv("MISSING_LIVE_KEY", raising=False)
        monkeypatch.delenv("MISSING_LIVE_SECRET", raising=False)

        with pytest.raises(ConfigError, match="key"):
            load_config(live_toml)
