"""Overnight loser cost model — base costs plus spread and delay penalties.

Base assumption: 5 bps fixed slippage + 5 bps commission per trade side
(conservative for liquid sector SPDRs). ``spread_bps`` (half the round-trip
bid-ask) and ``delay_bps`` (proxy for entering slightly after the open) are
folded into fixed slippage so the shared ``CostModelConfig`` schema stays
unchanged.

Delay limitation: with daily bars, ``delay_bps`` is only a fixed-cost proxy
for late entry. Precise delay sensitivity analysis requires 1-minute bars.
"""

from __future__ import annotations

from config.schema import CostModelConfig
from strategies.overnight_loser.signal import OvernightLoserParams

BASE_SLIPPAGE_PCT = 0.0005  # 5 bps
BASE_COMMISSION_PCT = 0.0005  # 5 bps


def overnight_loser_cost_config(params: OvernightLoserParams) -> CostModelConfig:
    """Build the cost config with spread and delay folded into slippage."""
    spread_cost = params.spread_bps / 10_000.0
    delay_cost = params.delay_bps / 10_000.0
    return CostModelConfig(
        slippage_fixed_pct=BASE_SLIPPAGE_PCT + spread_cost + delay_cost,
        slippage_variable_coeff=0.0,
        commission_pct=BASE_COMMISSION_PCT,
        sec_fee_per_dollar_sold=5.1e-6,
        finra_taf_per_share_sold=0.000119,
        borrow_cost_annual_pct=0.01,
    )
