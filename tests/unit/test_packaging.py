"""Installed-release contracts: optional extras, bundled configs, offline CLI import."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from config.loader import ConfigError, load_config
from config.schema import Mode

REPO_ROOT = Path(__file__).resolve().parents[2]
OPTIONAL_PROVIDER_MODULES = ("alpaca", "ccxt", "vectorbt", "statsmodels", "streamlit", "telegram")

CRYPTO_ONLY_CONFIG = """
mode = "paper"
strategy_name = "dual_ma_crossover"

[[brokers]]
name = "coinbase"
asset_class = "crypto"
api_key_env = "MFS_TEST_DUMMY_KEY"
api_secret_env = "MFS_TEST_DUMMY_SECRET"
base_url = "https://example.invalid"
is_paper = true

[[data]]
symbols = ["BTC/USD"]
asset_class = "crypto"
exchange = "coinbase"
storage_dir = "parquet/crypto"
"""


def test_download_without_crypto_extra_fails_with_install_hint(tmp_path, monkeypatch, capsys):
    from data import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, "ccxt", None)
    monkeypatch.setenv("MFS_TEST_DUMMY_KEY", "dummy")
    monkeypatch.setenv("MFS_TEST_DUMMY_SECRET", "dummy")
    config_path = tmp_path / "crypto.toml"
    config_path.write_text(CRYPTO_ONLY_CONFIG, encoding="utf-8")

    download_code = cli.main(["--config", str(config_path), "download"])
    download_err = capsys.readouterr().err
    status_code = cli.main(["--config", str(config_path), "status"])

    assert download_code == 1
    assert "pip install 'mfs-trader[crypto]'" in download_err
    assert "Traceback" not in download_err
    assert status_code == 0


def test_pairs_cointegration_without_research_extra_names_the_extra(monkeypatch):
    import numpy as np
    import pandas as pd

    from config.optional_deps import MissingExtraError
    from strategies.pairs.discovery import PairCandidate, PairsParams, fit_pair_relationship

    params = PairsParams(formation_window_days=30)
    index = pd.date_range("2024-01-01", periods=30, freq="D", tz="UTC")
    close = 100.0 + np.arange(30, dtype=float)
    formation = pd.concat(
        {
            "AAA": pd.DataFrame({"close": close}, index=index),
            "BBB": pd.DataFrame({"close": close * 1.01}, index=index),
        },
        axis=1,
    )
    monkeypatch.setitem(sys.modules, "statsmodels.tsa.stattools", None)

    with pytest.raises(MissingExtraError, match=r"mfs-trader\[research\]"):
        fit_pair_relationship(formation, PairCandidate("AAA", "BBB", 1e8, 1e8), params)


def test_cli_entry_points_import_and_run_offline_without_optional_providers(tmp_path):
    blocked = ", ".join(repr(name) for name in OPTIONAL_PROVIDER_MODULES)
    script = textwrap.dedent(
        f"""
        import sys
        for name in ({blocked},):
            sys.modules[name] = None
        import data.cli
        import engine.cli
        raise SystemExit(engine.cli.main(["--config", "builtin:paper", "preflight"]))
        """
    )
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Config OK" in result.stdout


def test_builtin_config_resolves_to_bundled_template():
    cfg = load_config("builtin:paper", load_env=False)

    assert cfg.mode == Mode.PAPER


@pytest.mark.parametrize("value", ["builtin:live", "builtin:../pyproject", "builtin:"])
def test_builtin_config_rejects_unshipped_or_invalid_names(value):
    with pytest.raises(ConfigError, match="Unknown bundled config"):
        load_config(value, load_env=False)


def test_plain_config_name_never_falls_back_to_bundled_template(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError, match="Config file not found"):
        load_config("paper.toml", load_env=False)


def test_broken_optional_dependency_is_not_misreported_as_missing_extra(monkeypatch):
    from config import optional_deps

    failure = ModuleNotFoundError("SDK internal dependency is missing", name="sdk_internal")

    def broken_import(name):
        raise failure

    monkeypatch.setattr(optional_deps.importlib, "import_module", broken_import)
    with pytest.raises(ModuleNotFoundError) as caught:
        optional_deps.require_extra("ccxt", extra="crypto", purpose="download")
    assert caught.value is failure


@pytest.mark.parametrize(
    "member",
    [
        "config/.env",
        "data/prices.parquet",
        "data/prices.csv",
        "experiments/123/metadata.json",
        "experiments/123/strategy_snapshot.py",
        "docs/reports/etf_campaign_inputs/restricted_bundle.zip",
        "research_scout/results.json",
        "../outside.py",
    ],
)
def test_release_archive_inspector_rejects_evidence_and_data(tmp_path, member):
    import zipfile

    from scripts.inspect_release import inspect_archive

    wheel = tmp_path / "mfs_trader.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("engine/__init__.py", "")
        archive.writestr("config/paper.toml", 'mode = "paper"')
        archive.writestr(member, "synthetic forbidden member")

    report = inspect_archive(wheel)
    assert report["forbidden"] == [member]
