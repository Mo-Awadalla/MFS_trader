# Contributing

This project is a source-visible research workbench. Contributions should keep experiments reproducible and simulated by default.

- Do not commit credentials, broker data, vendor-derived archives, or retained API responses without documented redistribution rights.
- Treat strategy-rule changes as new frozen Experiments; do not edit evidence under `experiments/<uuid>/`.
- Run `python -m ruff check .` and `python -m pytest tests/unit tests/contracts tests/integration/test_ma_shakedown.py` before proposing a change.
- Do not add live-trading behavior or modify promotion, order-state, reconciliation, or risk-limit rules without explicit maintainer approval.

Open an issue before proposing a material strategy, execution, or data-governance change.
