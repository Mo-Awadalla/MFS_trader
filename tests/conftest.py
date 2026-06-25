"""Pytest configuration — skip live_broker tests by default."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_configure(config):
    """Load .env before test collection."""
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def pytest_collection_modifyitems(config, items):
    """Skip live_broker tests unless RUN_LIVE_BROKER_TESTS=1 is set."""
    if os.environ.get("RUN_LIVE_BROKER_TESTS", "0") == "1":
        return

    skip_live = pytest.mark.skip(reason="live_broker tests require RUN_LIVE_BROKER_TESTS=1")
    for item in items:
        if "live_broker" in item.keywords:
            item.add_marker(skip_live)
