"""Verify an installed mfs-trader distribution outside the source checkout.

Run with the Python interpreter of a venv where the wheel was installed with
runtime dependencies only (no dev lock, no extras)::

    /path/to/venv/bin/python /path/to/checkout/scripts/verify_release.py

Every check runs as a subprocess from a fresh temporary working directory that
contains no ``.env``. Commands are credential-free: provider credential
variables are stripped from the child environment and no command contacts a
broker or market-data endpoint. The checker uses only the standard library plus
``verify_offline_shakedown`` from this directory.

Exit status is 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from verify_offline_shakedown import verify_shakedown

DISTRIBUTION = "mfs-trader"
CHECKOUT_ROOT = Path(__file__).resolve().parents[1]
OPTIONAL_PROVIDERS = ("alpaca", "ccxt", "vectorbt", "statsmodels", "streamlit", "telegram")
CREDENTIAL_ENV_PREFIXES = ("ALPACA_", "APCA_", "COINBASE_", "BINANCE_", "TELEGRAM_", "DATABENTO_")
FORBIDDEN_SUFFIXES = (".env", ".parquet", ".csv", ".sqlite", ".db", ".bundle", ".zip", ".pkl")
FORBIDDEN_TOP_LEVEL = ("tests", "research_scout", "scripts", "docs")

CRYPTO_ONLY_CONFIG = """\
mode = "paper"
strategy_name = "dual_ma_crossover"

[[brokers]]
name = "coinbase"
asset_class = "crypto"
api_key_env = "MFS_RELEASE_CHECK_DUMMY_KEY"
api_secret_env = "MFS_RELEASE_CHECK_DUMMY_SECRET"
base_url = "https://example.invalid"
is_paper = true

[[data]]
symbols = ["BTC/USD"]
asset_class = "crypto"
exchange = "coinbase"
storage_dir = "parquet/crypto"
"""

GAUNTLET_PROBE = """
import json
from pathlib import Path
import numpy as np
import pandas as pd
from validation.gauntlet import run_gauntlet
from validation.search import declared_search

rng = np.random.default_rng(728)
index = pd.date_range("2020-01-01", periods=1100, freq="B", tz="UTC")
# Independent streams keep M_eff_corr >= 2, as required by the corrected DSR.
noise = rng.normal(size=(len(index), 3))
noise = (noise - noise.mean(axis=0)) / noise.std(axis=0, ddof=1)
params = [{"candidate": i} for i in range(3)]
trials = [
    pd.Series(0.004 * noise[:, i] + mean, index=index)
    for i, mean in enumerate((0.001, 0.00101, 0.00099))
]
frame = pd.DataFrame({i: series for i, series in enumerate(trials)})
sweep = pd.DataFrame([
    {**p, "sharpe": float(r.mean() / r.std() * np.sqrt(252))}
    for p, r in zip(params, trials, strict=True)
])
selected = params[1]
search = declared_search(
    params, trials, selected,
    search_scope="Synthetic release check only: all three declared candidate return streams",
)

def train(train_df):
    scores = train_df.mean() / train_df.std()
    return {"candidate": int(scores.idxmax())}

def evaluate(test_df, fitted):
    returns = test_df[fitted["candidate"]]
    downside = np.sqrt(np.mean(np.minimum(returns, 0) ** 2))
    wealth = (1 + returns).cumprod()
    return {
        "returns": returns,
        "sharpe": float(returns.mean() / returns.std() * np.sqrt(252)),
        "sortino": float(returns.mean() / downside * np.sqrt(252)),
        "total_return": float(wealth.iloc[-1] - 1),
        "max_drawdown": float((wealth / wealth.cummax() - 1).min()),
    }

result = run_gauntlet(
    "synthetic_installed_release_check", frame, train, evaluate, sweep, ["candidate"],
    dsr_search=search, mc_num_paths=256, seed=728,
)
report = result.to_dict()
mc, dsr = report["monte_carlo"], report["dsr"]
checks = {
    "report_schema": report["report_schema_version"] == "gauntlet_report_v2",
    "mc_formula": mc["formula_version"] == "mc_block_bootstrap_v2",
    "evidence_available": mc["available"] and dsr["available"],
    "adverse_drawdown_field": "pct_5_max_dd" in mc and "pct_95_max_dd" not in mc,
    "declared_search_window": dsr["m_raw"] == 3 and dsr["track_record_length"] == len(index),
    "search_scope": dsr["search_scope"] == search.search_scope,
    "wfa_folds": report["wfa"]["num_folds"] >= 2,
    "gauntlet_passed": result.passed,
}
if not all(checks.values()):
    raise RuntimeError(json.dumps({"checks": checks, "report": report}, allow_nan=False))
with Path("synthetic_gauntlet_report.json").open("x", encoding="utf-8") as stream:
    json.dump(report, stream, indent=2, allow_nan=False)
print("Synthetic corrected gauntlet: PASS (not strategy or paper qualification)")
"""

NETWORK_GUARD = """
import sys
def deny_network(event, args):
    if event in {
        "socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
        "socket.gethostbyaddr", "socket.sendto", "socket.sendmsg",
    }:
        raise RuntimeError("Release verification forbids network access")
sys.addaudithook(deny_network)
"""


class ReleaseCheckError(RuntimeError):
    """A release check failed."""


def _child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(CREDENTIAL_ENV_PREFIXES) and key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    env["RUN_LIVE_BROKER_TESTS"] = "0"
    env["MFS_TEST_LOAD_DOTENV"] = "0"
    env.update(extra or {})
    return env


def _script(name: str) -> str:
    bin_dir = Path(sys.executable).parent
    for candidate in (bin_dir / name, bin_dir / f"{name}.exe"):
        if candidate.is_file():
            return str(candidate)
    raise ReleaseCheckError(f"Console script {name!r} not found next to {sys.executable}")


def _run(
    label: str,
    argv: Sequence[str],
    cwd: Path,
    *,
    expect_code: int = 0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    child_env = dict(env or _child_env())
    child_env["PYTHONPATH"] = str(cwd / "_offline_guard")
    result = subprocess.run(
        list(argv),
        cwd=cwd,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    print(f"[{label}] exit={result.returncode}: {' '.join(argv)}")
    if result.returncode != expect_code:
        raise ReleaseCheckError(
            f"{label}: expected exit {expect_code}, got {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def check_installed_distribution(work: Path) -> None:
    """Imports and data files come from the installed wheel, not the checkout."""

    probe = f"""
import importlib, importlib.metadata as md, importlib.util, json, sys
dist = md.distribution({DISTRIBUTION!r})
mods = {{name: importlib.import_module(name).__file__ for name in
        ("config", "data.cli", "engine.cli", "storage", "strategies", "research", "experiments")}}
print(json.dumps({{
    "version": dist.version,
    "install_root": str(dist.locate_file("")),
    "entry_points": sorted(ep.name for ep in dist.entry_points if ep.group == "console_scripts"),
    "files": [str(f) for f in dist.files or ()],
    "modules": mods,
    "optional_missing": [n for n in {OPTIONAL_PROVIDERS!r} if importlib.util.find_spec(n) is None],
}}))
"""
    result = _run("installed-distribution", [sys.executable, "-c", probe], work)
    info = json.loads(result.stdout)
    for name, path in info["modules"].items():
        if Path(path).resolve().is_relative_to(CHECKOUT_ROOT):
            raise ReleaseCheckError(f"{name} imported from the source checkout: {path}")
        if not Path(path).resolve().is_relative_to(Path(info["install_root"]).resolve()):
            raise ReleaseCheckError(f"{name} did not import from the installed distribution: {path}")
    if {"mfs-data", "mfs-engine"} - set(info["entry_points"]):
        raise ReleaseCheckError(f"Missing console scripts: {info['entry_points']}")
    offending = [
        f
        for f in info["files"]
        if f.split("/", 1)[0] in FORBIDDEN_TOP_LEVEL or f.lower().endswith(FORBIDDEN_SUFFIXES)
    ]
    if offending:
        raise ReleaseCheckError(f"Distribution ships forbidden files: {offending[:20]}")
    print(
        f"  {DISTRIBUTION} {info['version']}; optional providers absent: "
        f"{', '.join(info['optional_missing']) or '(none)'}"
    )
    if set(info["optional_missing"]) != set(OPTIONAL_PROVIDERS):
        raise ReleaseCheckError("Use a clean runtime-only venv with no optional provider extras")


def check_offline_commands(work: Path) -> None:
    """Documented credential-free commands succeed from outside the checkout."""

    _run("data-status", [_script("mfs-data"), "--config", "builtin:research", "status"], work)
    preflight = _run(
        "preflight", [_script("mfs-engine"), "--config", "builtin:paper", "preflight"], work
    )
    if "Config OK" not in preflight.stdout:
        raise ReleaseCheckError(f"preflight did not report Config OK:\n{preflight.stdout}")

    out_dir = work / "ma_shakedown"
    shakedown = _run(
        "shakedown-ma", [_script("mfs-engine"), "shakedown-ma", "--out-dir", str(out_dir)], work
    )
    if "MA shakedown status: PASS" not in shakedown.stdout:
        raise ReleaseCheckError(f"shakedown did not PASS:\n{shakedown.stdout}")
    print("  MA shakedown status: PASS")

    _run(
        "report",
        [
            _script("mfs-engine"),
            "report",
            "--db",
            str(out_dir / "baseline.sqlite"),
            "--allow-blockers",
        ],
        work,
    )
    verify_shakedown(out_dir)
    print("  offline shakedown report verification: PASS")


def check_missing_crypto_extra(work: Path) -> None:
    """A command needing an absent extra fails with an install hint, not a traceback."""

    probe = _run(
        "crypto-extra-probe",
        [sys.executable, "-c", "import importlib.util as u; print(u.find_spec('ccxt') is None)"],
        work,
    )
    if probe.stdout.strip() != "True":
        raise ReleaseCheckError("ccxt must be absent in the runtime-only verification venv")
    config_path = work / "crypto_only.toml"
    config_path.write_text(CRYPTO_ONLY_CONFIG, encoding="utf-8")
    env = _child_env(
        {"MFS_RELEASE_CHECK_DUMMY_KEY": "dummy", "MFS_RELEASE_CHECK_DUMMY_SECRET": "dummy"}
    )
    result = _run(
        "download-without-crypto-extra",
        [_script("mfs-data"), "--config", str(config_path), "download"],
        work,
        expect_code=1,
        env=env,
    )
    if f"pip install '{DISTRIBUTION}[crypto]'" not in result.stderr or "Traceback" in result.stderr:
        raise ReleaseCheckError(f"Missing-extra error is not actionable:\n{result.stderr}")
    print(f"  missing extra reported: {result.stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Empty directory outside the checkout for artifacts (default: a new temp dir)",
    )
    args = parser.parse_args()

    work = args.work_dir or Path(tempfile.mkdtemp(prefix="mfs-release-check-"))
    work = work.resolve()
    if work.exists() and any(work.iterdir()):
        print(f"work dir must be empty: {work}", file=sys.stderr)
        return 2
    if work.is_relative_to(CHECKOUT_ROOT):
        print(f"work dir must be outside the checkout: {work}", file=sys.stderr)
        return 2
    work.mkdir(parents=True, exist_ok=True)
    guard_dir = work / "_offline_guard"
    guard_dir.mkdir()
    (guard_dir / "sitecustomize.py").write_text(NETWORK_GUARD, encoding="utf-8")

    print(f"Release verification in {work} using {sys.executable}")
    try:
        check_installed_distribution(work)
        check_offline_commands(work)
        gauntlet = _run("synthetic-gauntlet", [sys.executable, "-c", GAUNTLET_PROBE], work)
        print(gauntlet.stdout.strip().splitlines()[-1])
        check_missing_crypto_extra(work)
    except (ReleaseCheckError, SystemExit, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Release verification: FAIL\n{exc}", file=sys.stderr)
        return 1
    print("Release verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
