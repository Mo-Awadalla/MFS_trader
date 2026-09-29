# Installable experimental release

This release is a research/validation workbench with simulated execution. It is not a live-trading release. Installation, a synthetic gauntlet PASS, and simulated shakedown evidence do not qualify a strategy, authorize broker-paper operation, or change any Experiment lifecycle state.

## Runtime and optional dependencies

Python 3.11 and 3.12 have separate reproducible development constraints:

- `requirements-dev-py311.txt`: Python 3.11.
- `requirements-dev.txt`: Python 3.12.

Both resolve the same `pyproject.toml` direct requirements and `dev,crypto` extras. The 3.11 lock was seeded from the 3.12 lock to retain compatible versions; compatibility forces different NumPy and SciPy pins and adds the Python-3.11-only transitive `tomli` dependency. Do not use the 3.12 lock with 3.11.

A runtime-only install needs **neither** development dependencies **nor** provider extras. Passing a lock with `pip install -c` constrains versions; it does not install the extra packages listed in that lock. Offline entry points do not require `alpaca-py`, `ccxt`, `vectorbt`, `statsmodels`, `streamlit`, or `python-telegram-bot`. Scikit-learn and urllib3 are declared runtime requirements because runtime modules import them directly.

Optional functionality is installed explicitly with `mfs-trader[alpaca]`, `[crypto]`, `[research]`, `[monitoring]`, or `[alerts]`. CCXT downloads/execution and pairs cointegration defer their optional imports until used and name the required extra on failure. Existing Alpaca HTTP adapters use requests, not the optional Alpaca SDK; installing or omitting the SDK does not disable those adapters. Never use credentials during release verification.

`research_scout/` contains source-checkout research material, not runtime code, and is deliberately excluded. Tests, scripts, documentation trees, market-data files, Experiment evidence, research artifacts, and dotenv files are not distribution assets. Only the explicitly listed credential-free config templates accompany Python modules.

The CCXT **data downloader** is read-only. A requested testnet uses sandbox URLs only when the exchange advertises them; otherwise PR3 deliberately falls through to public production historical OHLCV. Coinbase download credentials are cleared to avoid its private fee-summary endpoint. This fallback does not produce sandbox evidence or grant trading authority. The separate execution adapter's sandbox configuration is unchanged; never infer execution authorization from a successful public download.

## Config resolution outside a checkout

`--config builtin:<name>` resolves a shipped template, never a similarly named file from a checkout. Available names are `research`, `paper`, `paper_shakedown`, and `paper_etf_tsm`. The live template is not shipped. Unknown names and traversal-like names fail. Explicit paths remain relative to the working directory; a missing path never silently falls back to a bundled template.

Config loading does not read `.env` by default. Broker/data credentials must be supplied explicitly as environment variables; the Python loader's `load_env=True` opt-in reads only the current directory and is forbidden by the offline test guard. Config-relative storage values are working-directory-relative; templates do not grant data rights or provide market data.

For a runtime-only installed environment, from an empty directory outside the source tree:

```sh
mfs-data --config builtin:research status
mfs-engine --config builtin:paper preflight
mfs-engine shakedown-ma --out-dir ./ma_shakedown
mfs-engine report --db ./ma_shakedown/baseline.sqlite --allow-blockers
/path/to/runtime/bin/python /path/to/checkout/scripts/verify_offline_shakedown.py --out-dir ./ma_shakedown
```

The expected shakedown output includes `MA shakedown status: PASS`. `--allow-blockers` is an operational-report display option, not a qualification bypass. The verifier checks simulated baseline, rejection, timeout and partial-fill evidence, not broker or financial parity.

## Build and verify on both Python versions

Use an absolute checkout path and a fresh evidence directory. Build in a separate venv, not a development or runtime venv. For example (substitute the paths):

```sh
REPO=/absolute/path/to/checkout
EVIDENCE=/absolute/path/to/new-release-evidence
mkdir -p "$EVIDENCE"
uv venv -p 3.12 "$EVIDENCE/build-venv"
uv pip install --python "$EVIDENCE/build-venv/bin/python" build
"$EVIDENCE/build-venv/bin/python" -m build "$REPO" --outdir "$EVIDENCE/dist"
"$EVIDENCE/build-venv/bin/python" "$REPO/scripts/inspect_release.py" \
  --archive "$EVIDENCE"/dist/*.whl --archive "$EVIDENCE"/dist/*.tar.gz \
  --output "$EVIDENCE/archive-inspection.json"

uv venv --seed -p 3.11 "$EVIDENCE/runtime311"
"$EVIDENCE/runtime311/bin/python" -m pip install \
  -c "$REPO/requirements-dev-py311.txt" "$EVIDENCE"/dist/*.whl
"$EVIDENCE/runtime311/bin/python" -m pip freeze > "$EVIDENCE/runtime311-freeze.txt"
RUN_LIVE_BROKER_TESTS=0 MFS_TEST_LOAD_DOTENV=0 \
  "$EVIDENCE/runtime311/bin/python" "$REPO/scripts/verify_release.py" \
  --work-dir "$EVIDENCE/check311"

uv venv --seed -p 3.12 "$EVIDENCE/runtime312"
"$EVIDENCE/runtime312/bin/python" -m pip install \
  -c "$REPO/requirements-dev.txt" "$EVIDENCE"/dist/*.whl
"$EVIDENCE/runtime312/bin/python" -m pip freeze > "$EVIDENCE/runtime312-freeze.txt"
RUN_LIVE_BROKER_TESTS=0 MFS_TEST_LOAD_DOTENV=0 \
  "$EVIDENCE/runtime312/bin/python" "$REPO/scripts/verify_release.py" \
  --work-dir "$EVIDENCE/check312"
```

`verify_release.py` requires an empty work directory outside the checkout, rejects installed optional providers, strips provider credential variables and source import paths, and installs a Python audit hook in its child processes to reject network activity. It proves installed module provenance, packaged entry points and assets, all commands above, and an actionable nonzero missing-crypto-extra error without a traceback.

It also runs the corrected gauntlet end-to-end on deterministic synthetic return streams through real WFA, MC, DSR, and stability code. It passes a `DeclaredSearch` built by `declared_search` via `dsr_search=`, checks `gauntlet_report_v2` and `mc_block_bootstrap_v2`, available MC/DSR evidence, declared trial count/window/scope, and the corrected adverse drawdown field. This small synthetic smoke uses 256 MC paths without changing production defaults or pass thresholds. Its report is not a real Experiment artifact or strategy qualification. The runtime packages must include the corrected validation code; an old PR3-only wheel must fail this check.

CI uses a 3.11/3.12 test matrix, runs Ruff once, and independently builds and verifies runtime-only wheels on both versions. This document describes the required checks, not a claim that remote CI has passed.

## Offline test boundary

Always run:

```sh
RUN_LIVE_BROKER_TESTS=0 MFS_TEST_LOAD_DOTENV=0 \
  python -m pytest tests/unit tests/contracts tests/integration/test_ma_shakedown.py
python -m ruff check .
```

The pytest session blocks non-loopback Python socket connections, standard DNS lookups and UDP `sendto` before collection. HTTP clients cannot swallow the guard error as a retryable connection failure. Loopback fixtures and Unix sockets remain available. Dotenv loading requires both explicit live-network and dotenv opt-ins. This is an accidental-access guard, not a sandbox: native libraries and child processes need their own network restrictions. Never supply broker credentials to offline CI.

Regenerate locks without broad upgrades:

```sh
uv pip compile pyproject.toml --extra dev --extra crypto --python-version 3.12 -o requirements-dev.txt
uv pip compile pyproject.toml --extra dev --extra crypto --python-version 3.11 -o requirements-dev-py311.txt
```

Retain existing outputs so uv prefers their compatible pins. Review every version change; no unrelated dependency upgrades belong in a release reconciliation.

## Redacted security and artifact inspection

```sh
python scripts/inspect_release.py --scan-secrets --revision HEAD --output /absolute/new/secret-pattern-report.json
```

The scanner examines the tracked/unignored current tree and every commit reachable from the specified sanitized revision, deduplicating unchanged blob/path pairs. It does not traverse every local ref. It reports paths, commits and pattern classes only, never matched values. Dotenv filenames are reported without opening them. APCA header references and synthetic fixtures require triage; heuristic matches do not prove an exposed credential. A zero-finding scan is not a guarantee that no secrets exist.

Archive inspection prints SHA-256 hashes and rejects unexpected members, including evidence/data files and nested Experiment packages. It returns nonzero on a forbidden member. The source distribution and wheel are both checked; do not rely on wheel inspection alone.

Use `gitleaks git --log-opts=HEAD --redact=100` on the sanitized branch when available; retain only redacted rule/path/commit metadata. Never scan obsolete refs accidentally. If `pip-audit` is available, run it from a separate audit environment against each runtime freeze file and retain its advisory report. It contacts advisory/package services, not brokers; keep credentials absent. If unavailable or unable to reach an advisory source, record that limitation rather than reporting a clean audit.

Release evidence should include build output, both archive hashes, both runtime freeze files, command exit codes, synthetic reports, test/lint results and redacted security findings. Builds, tests and runtime checks must be performed on the integrated release candidate, not inferred from partial worktree changes.
