from __future__ import annotations

from validation.gauntlet import ValidationPolicy, ValidationRequest


def test_validation_policy_preserves_documented_defaults() -> None:
    policy = ValidationPolicy()

    assert policy.initial_capital == 10000.0
    assert policy.ruin_threshold == -0.50
    assert policy.max_dd_limit == -0.30
    assert policy.mc_num_paths == 10000
    assert policy.mc_block_size == 20
    assert policy.mc_annualization_factor == 252.0
    assert policy.seed == 42


def test_validation_request_has_explicit_policy_and_wfa_extension_points() -> None:
    request = ValidationRequest(
        strategy_name="test",
        df=None,
        train_fn=lambda **_: {},
        test_fn=lambda **_: {},
        sweep_results=None,
        param_columns=[],
        wfa_kwargs={"n_splits": 3},
    )

    assert request.policy == ValidationPolicy()
    assert request.wfa_kwargs == {"n_splits": 3}
