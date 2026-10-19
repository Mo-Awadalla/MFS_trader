from __future__ import annotations

from execution.contracts import ALPACA_EQUITY_DAY, execution_contract_for


def test_alpaca_equity_contract_truncates_quantity_and_cash_without_rounding_up():
    contract = execution_contract_for("alpaca", "equity")
    assert contract is ALPACA_EQUITY_DAY
    assert contract.constrain_quantity(0.1234569, 10.0) == 0.123456
    assert contract.constrain_quantity(1.1234569, 10.0, available_cash=10.0) == 1.0
    assert contract.constrain_quantity(0.009999, 100.0) == 0.0


def test_unknown_broker_asset_pair_has_no_guessed_quantity_contract():
    try:
        execution_contract_for("unknown", "equity")
    except ValueError as error:
        assert "no explicit execution contract" in str(error)
    else:
        raise AssertionError("an unconfigured broker must not inherit an assumed contract")
