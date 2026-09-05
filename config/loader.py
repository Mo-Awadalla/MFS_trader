"""Config loader — reads TOML, resolves env-var secrets, validates."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from dotenv import load_dotenv

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

CONFIG_DIR = Path(__file__).resolve().parent


class ConfigError(Exception):
    """Raised when a config is structurally invalid or unsafe."""


def load_config(path: str | Path, *, load_env: bool = True) -> Config:
    """Load and validate a TOML config file, resolving secrets from env vars."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    if load_env:
        load_dotenv()  # pulls .env from CWD

    with path.open("rb") as f:
        raw = tomllib.load(f)

    mode = Mode(raw.get("mode", "research"))

    brokers = _parse_brokers(raw.get("brokers", []), mode)
    data = _parse_data(raw.get("data", []))
    risk = RiskLimits(**raw.get("risk_limits", {}))
    portfolio = PortfolioConfig(**raw.get("portfolio", {}))
    cost = CostModelConfig(**raw.get("cost_model", {}))
    monitoring = MonitoringConfig(**raw.get("monitoring", {}))
    engine = EngineConfig(**raw.get("engine", {}))
    live = LiveDeploymentConfig(**raw.get("live_deployment", {}))

    cfg = Config(
        mode=mode,
        brokers=brokers,
        data=data,
        risk_limits=risk,
        portfolio=portfolio,
        cost_model=cost,
        monitoring=monitoring,
        engine=engine,
        live_deployment=live,
        artifacts_dir=raw.get("artifacts_dir", "~/trading_artifacts"),
        strategy_name=raw.get("strategy_name", ""),
        strategy_version=raw.get("strategy_version", "0.0.0"),
        strategies_enabled=raw.get("strategies_enabled", []),
        raw=raw,
    )

    validate_config(cfg)
    return cfg


def _parse_brokers(raw_brokers: list[dict[str, Any]], mode: Mode) -> list[BrokerConfig]:
    brokers: list[BrokerConfig] = []
    for b in raw_brokers:
        brokers.append(
            BrokerConfig(
                name=b["name"],
                asset_class=AssetClass(b["asset_class"]),
                api_key_env=b["api_key_env"],
                api_secret_env=b["api_secret_env"],
                base_url=b["base_url"],
                data_url=b.get("data_url"),
                is_paper=b.get("is_paper", True),
            )
        )
    return brokers


def _parse_data(raw_data: list[dict[str, Any]]) -> list[DataConfig]:
    configs: list[DataConfig] = []
    for d in raw_data:
        configs.append(
            DataConfig(
                symbols=d["symbols"],
                asset_class=AssetClass(d["asset_class"]),
                bar_frequency_raw=d.get("bar_frequency_raw", "1min"),
                target_frequencies=d.get("target_frequencies", ["1h", "1d"]),
                start_date=d.get("start_date", "2020-01-01"),
                end_date=d.get("end_date"),
                adjustment=d.get("adjustment", "split_dividend"),
                feed=d.get("feed", "iex"),
                exchange=d.get("exchange"),
                storage_dir=d.get("storage_dir", "data/parquet"),
                min_volume=d.get("min_volume", 0.0),
                price_floor=d.get("price_floor", 0.0),
            )
        )
    return configs


def validate_config(cfg: Config) -> None:
    """Validate config — raises ConfigError on any unsafe or missing setup."""
    if cfg.mode == Mode.LIVE:
        _validate_live_config(cfg)
    if not cfg.brokers:
        raise ConfigError("No brokers configured")
    if not cfg.data:
        raise ConfigError("No data sources configured")
    for b in cfg.brokers:
        if not b.api_key_env:
            raise ConfigError(f"Broker {b.name} missing api_key_env")
    for d in cfg.data:
        if not d.symbols:
            raise ConfigError(f"Data config for {d.asset_class} has no symbols")


def _validate_live_config(cfg: Config) -> None:
    """Strict validation for live mode — refuse to start on any unsafe condition."""
    live = cfg.live_deployment

    if not live.authorized:
        raise ConfigError(
            "live_deployment.authorized is false — cannot start engine in live mode "
            "without explicit manual authorization"
        )

    if live.starting_capital <= 0:
        raise ConfigError("live_deployment.starting_capital must be > 0 for live mode")

    if live.max_live_capital <= 0:
        raise ConfigError("live_deployment.max_live_capital must be > 0 for live mode")

    if live.strategy_capital_limit <= 0:
        raise ConfigError("live_deployment.strategy_capital_limit must be > 0 for live mode")

    # Check broker is not pointing at paper URLs
    for b in cfg.brokers:
        if b.is_paper:
            raise ConfigError(
                f"Broker {b.name} has is_paper=true but mode is 'live'. "
                "Refusing to start — paper broker URL in live config."
            )
        if "paper" in b.base_url.lower():
            raise ConfigError(
                f"Broker {b.name} base_url contains 'paper' but mode is 'live': {b.base_url}"
            )

        # Check the actual env var keys exist and don't look like paper/test keys
        key = os.environ.get(b.api_key_env, "")
        if not key:
            raise ConfigError(
                f"Environment variable {b.api_key_env} is not set but mode is 'live'. "
                "Refusing to start — missing live API key."
            )
        if _looks_like_paper_key(key):
            raise ConfigError(
                f"Environment variable {b.api_key_env} appears to be a paper/test key "
                "but mode is 'live'. Refusing to start — wrong key for environment."
            )

    # Risk limits must be present and non-zero
    r = cfg.risk_limits
    if r.per_position_pct <= 0:
        raise ConfigError("risk_limits.per_position_pct must be > 0 for live")
    if r.max_daily_loss_pct <= 0:
        raise ConfigError("risk_limits.max_daily_loss_pct must be > 0 for live")
    if r.max_monthly_loss_pct <= 0:
        raise ConfigError("risk_limits.max_monthly_loss_pct must be > 0 for live")

    # Config/environment/mode must agree
    if cfg.mode != Mode.LIVE:
        raise ConfigError(f"Config mode is {cfg.mode} but live validation triggered — inconsistency")


def _looks_like_paper_key(key: str) -> bool:
    """Heuristic check for paper/test API keys."""
    lower = key.lower()
    return any(tag in lower for tag in ("paper", "test", "sandbox", "demo", "dev"))


def get_broker_creds(broker: BrokerConfig) -> tuple[str, str]:
    """Retrieve actual API key/secret from environment for a broker."""
    key = os.environ.get(broker.api_key_env, "")
    secret = os.environ.get(broker.api_secret_env, "")
    if not key or not secret:
        raise ConfigError(
            f"Missing credentials for broker {broker.name}: "
            f"check env vars {broker.api_key_env} and {broker.api_secret_env}"
        )
    return key, secret


def default_config_path(mode: str) -> Path:
    """Return the path to a default config file for a given mode."""
    return CONFIG_DIR / f"{mode}.toml"


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) < 2:
        print("Usage: python -m config <config.toml>")
        sys.exit(1)
    cfg = load_config(sys.argv[1])
    print(f"Loaded config: mode={cfg.mode}, brokers={[b.name for b in cfg.brokers]}")
