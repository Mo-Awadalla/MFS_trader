"""Tests for the candidate registry and runner plumbing."""

from __future__ import annotations

import pytest

from research.candidate_registry import REGISTRY, get_candidate, runnable_candidates


def test_registry_has_required_fields() -> None:
    for spec in REGISTRY.values():
        assert spec.candidate_id
        assert spec.family
        assert spec.hypothesis
        assert isinstance(spec.parameters, dict) and spec.parameters
        assert isinstance(spec.data_requirements, dict) and spec.data_requirements
        assert spec.status


def test_registry_contains_c12_variants_and_history() -> None:
    assert {"C12_v1_hard_cash", "C12_v2_soft_shrink", "C12_v3_8w_hard_cash"} <= set(REGISTRY)
    assert REGISTRY["C5_dma"].status == "rejected_dma_weighting_class"
    assert REGISTRY["dispersion_gate_v1"].status == "validation_failed"


def test_c12_variants_are_runnable() -> None:
    runnable = runnable_candidates()
    for variant in ("C12_v1_hard_cash", "C12_v2_soft_shrink", "C12_v3_8w_hard_cash"):
        assert variant in runnable
        module_name, function_name = REGISTRY[variant].runner.split(":")
        module = __import__(module_name, fromlist=[function_name])
        assert callable(getattr(module, function_name))


def test_unknown_candidate_raises() -> None:
    with pytest.raises(KeyError):
        get_candidate("C99_nonexistent")
