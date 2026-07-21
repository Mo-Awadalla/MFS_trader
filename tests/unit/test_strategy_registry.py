"""Tests for active and shelved strategy registry behavior."""

from strategies.registry import get_strategy, registered_strategies


def test_funding_time_reversal_is_shelved_but_resolvable() -> None:
    assert "funding_time_reversal" not in registered_strategies()
    assert get_strategy("funding_time_reversal").name == "funding_time_reversal"
