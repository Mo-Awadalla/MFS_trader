# Contributing

This project is a source-visible research workbench. Contributions should keep experiments reproducible and simulated by default.

- Do not commit credentials, broker data, vendor-derived archives, or retained API responses without documented redistribution rights.
- Treat strategy-rule changes as new frozen Experiments; do not edit evidence under `experiments/<uuid>/`.
- Use `requirements-dev-py311.txt` on Python 3.11 and `requirements-dev.txt` on Python 3.12. Keep existing compatible pins when regenerating locks; do not introduce unrelated upgrades.
- Run `python -m ruff check .` and `RUN_LIVE_BROKER_TESTS=0 MFS_TEST_LOAD_DOTENV=0 python -m pytest tests/unit tests/contracts tests/integration/test_ma_shakedown.py` before proposing a change. The pytest session blocks external Python socket access by default; never supply broker credentials to offline tests.
- Do not add live-trading behavior or modify promotion, order-state, reconciliation, or risk-limit rules without explicit maintainer approval.

Open an issue before proposing a material strategy, execution, or data-governance change.

For an installable release, build both wheel and sdist, inspect their contents, and run `scripts/verify_release.py` with clean runtime-only Python 3.11 and 3.12 environments from outside the checkout. Use the matching lock as constraints (`pip install -c`), not as runtime requirements (`-r`). See [the release verification contract](docs/release/installable-release.md) for exact commands and evidence requirements.

Report security concerns privately as described in [SECURITY.md](SECURITY.md). Keep scanner output redacted and never attach real broker evidence or secrets to a public issue.
