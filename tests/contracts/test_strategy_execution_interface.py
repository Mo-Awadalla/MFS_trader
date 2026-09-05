from __future__ import annotations

from strategies.contract import StrategyExecution
from strategies.registry import (
    get_execution_strategy,
    registered_execution_strategies,
    registered_strategies,
)


def test_registered_strategies_expose_compact_execution_interface() -> None:
    execution = registered_execution_strategies()

    assert set(execution) == set(registered_strategies())
    for name, strategy in execution.items():
        assert isinstance(strategy, StrategyExecution)
        assert strategy.name == name
        assert strategy.strategy_template_version.startswith(f"{name}:")
        assert callable(strategy.generate_signals)
        assert callable(strategy.validate_inputs)
        assert callable(strategy.required_columns)
        assert callable(strategy.warmup_bars)


def test_execution_accessor_preserves_registered_object_identity() -> None:
    assert get_execution_strategy("dual_ma_crossover") is get_execution_strategy(
        "dual_ma_crossover"
    )
