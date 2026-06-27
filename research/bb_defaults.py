"""Shared BB research defaults (avoids circular imports with bb_pipeline)."""

from __future__ import annotations

from config.schema import CostModelConfig


def default_cost_config() -> CostModelConfig:
    """Match the MA compatibility / replay golden cost assumptions."""
    return CostModelConfig(
        slippage_fixed_pct=0.0005,
        slippage_variable_coeff=0.5,
        commission_pct=0.0,
        sec_fee_per_dollar_sold=5.1e-6,
        finra_taf_per_share_sold=0.000119,
    )
