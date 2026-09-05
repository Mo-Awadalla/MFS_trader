"""Candidate registry: one record per research candidate.

Registry is declarative. Runner entries reference module callables so a
candidate can be evaluated with one command via ``research.candidate_runner``.
Historical candidate records mirror their existing artifacts; adding them
here does not modify or re-run them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    name: str
    family: str
    hypothesis: str
    parameters: dict[str, Any]
    data_requirements: dict[str, Any]
    status: str
    runner: str | None = None  # "module:function" run with candidate_id argument
    artifact_path: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_ETF_DAILY_DATA = {
    "source": "Massive adjusted daily flatfiles",
    "storage": "data/parquet/equity/massive_daily",
    "universe": ["DBC", "EEM", "EFA", "GLD", "IEF", "IWM", "QQQ", "SHY", "SPY", "TLT", "VNQ"],
    "bar_size": "1d",
    "limitation": "history starts 2021-06-30 under current credentials",
}

_C12_HYPOTHESIS = (
    "The 12-week weekly TSMOM base should not be sped up (C5 falsified that); instead, "
    "avoid trading during high cross-sectional dispersion regimes where asset-selection "
    "lag is worst. Gate exposure when smoothed weekly cross-sectional dispersion exceeds "
    "a threshold estimated on the training window only."
)

_SECTOR_SPDR_UNIVERSE = [
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK",
    "XLP", "XLU", "XLV", "XLY", "XLRE", "XHB",
]


def _c12_spec(variant_id: str, window_weeks: int, gate_action: str) -> CandidateSpec:
    return CandidateSpec(
        candidate_id=variant_id,
        name=f"DispersionGated TSMOM ({variant_id})",
        family="C12_DispersionGated_TSMOM",
        hypothesis=_C12_HYPOTHESIS,
        parameters={
            "base_signal": "weekly 12-week TSMOM (63-day momentum, long-only, inverse-vol, cap 0.50, gross <= 1.0)",
            "rebalance": "W-FRI, execute next session open",
            "rolling_dispersion_window_weeks": window_weeks,
            "threshold_quantile": 0.80,
            "threshold_train_weeks": 52,
            "gate_action": gate_action,
            "cash_proxy": "SHY",
        },
        data_requirements=_ETF_DAILY_DATA,
        status="declared",
        runner="research.etf_tsmom_c12:run_variant",
        artifact_path=f"research/artifacts/c12/{variant_id}/report.json",
        notes="Pre-declared variant; no parameter search permitted.",
    )


REGISTRY: dict[str, CandidateSpec] = {
    spec.candidate_id: spec
    for spec in (
        CandidateSpec(
            candidate_id="C2_voltarget",
            name="ETFTimeSeriesMomentumVolTarget-v1",
            family="ETF_TSMOM",
            hypothesis="Monthly 12-month TSMOM with vol targeting is deployable on the 10-ETF universe.",
            parameters={"lookback_days": 252, "rebalance": "monthly", "annual_vol_target": 0.10},
            data_requirements=_ETF_DAILY_DATA,
            status="rejected_stability_failure",
            artifact_path="research/artifacts/etf_tsmom_voltarget_v1_backtest.json",
        ),
        CandidateSpec(
            candidate_id="C3_noleverage",
            name="ETFTimeSeriesMomentumNoLeverage-v1",
            family="ETF_TSMOM",
            hypothesis="Clamping gross exposure to 1.0 fixes C2's stability failure.",
            parameters={"lookback_days": 252, "rebalance": "monthly", "max_gross_exposure": 1.0},
            data_requirements=_ETF_DAILY_DATA,
            status="rejected_stability_failure",
            artifact_path="research/artifacts/etf_tsmom_noleverage_v1_backtest.json",
        ),
        CandidateSpec(
            candidate_id="C5_dma",
            name="BayesianDMAWeeklyETF-v1",
            family="ETF_TSMOM_DMA",
            hypothesis="Dynamic lookback selection (Bayesian DMA) speeds up the signal and fixes stability.",
            parameters={"lookbacks": [21, 63, 126], "lambda_t": 0.99, "rebalance": "W-FRI"},
            data_requirements=_ETF_DAILY_DATA,
            status="rejected_dma_weighting_class",
            artifact_path="research/artifacts/bayesian_dma_weekly_etf_v1_backtest.json",
            notes="Falsified: dynamic lookback selection degraded performance.",
        ),
        CandidateSpec(
            candidate_id="dispersion_gate_v1",
            name="CrossSectionalDispersionGateWeeklyETF-v1",
            family="Dispersion_Gate",
            hypothesis="Daily-dispersion rolling-quantile gate on weekly TSMOM (prior formulation).",
            parameters={"dispersion_window": 21, "threshold_lookback": 252, "threshold_percentile": 0.80},
            data_requirements=_ETF_DAILY_DATA,
            status="validation_failed",
            artifact_path="research/artifacts/dispersion_gate_v1_backtest.json",
            notes="Prior daily-dispersion formulation; preserved, superseded by C12 spec.",
        ),
        _c12_spec("C12_v1_hard_cash", 4, "cash"),
        _c12_spec("C12_v2_soft_shrink", 4, "50_percent_exposure"),
        _c12_spec("C12_v3_8w_hard_cash", 8, "cash"),
        CandidateSpec(
            candidate_id="OvernightLoser_v1_lo_sector",
            name="OvernightLoserOpenToCloseReversal-v1-sector-spdrs",
            family="OvernightLoser",
            hypothesis=(
                "Worst overnight losers among sector SPDRs revert intraday "
                "(Lou/Polk/Skouras 2019; Bogousslavsky 2021). Long-only: buy the 4 "
                "worst overnight losers at the open, exit at the same close."
            ),
            parameters={
                "universe": "sector_spdrs",
                "num_long_positions": 4,
                "num_short_positions": 0,
                "min_history_days": 20,
                "min_price": 10.0,
                "min_median_dollar_volume": 50_000_000.0,
                "liquidity_lookback_days": 20,
                "long_gross": 1.0,
                "short_gross": 0.0,
                "spread_bps": 3.0,
                "delay_bps": 0.0,
            },
            data_requirements={
                "source": "Massive adjusted daily flatfiles",
                "storage": "data/parquet/equity/massive_daily",
                "universe": _SECTOR_SPDR_UNIVERSE,
                "bar_size": "1d",
            },
            status="declared",
            runner="research.overnight_loser_pipeline:run_variant",
            artifact_path="research/artifacts/overnight_loser/v1_lo_sector/report.json",
            notes=(
                "Frozen hypothesis v1. Sector SPDRs only; broad equity universe is v2. "
                "Long-only; num_short_positions reserved for a future long/short variant. "
                "delay_bps is a fixed-cost proxy — precise delay sensitivity needs 1-min bars."
            ),
        ),
    )
}


def get_candidate(candidate_id: str) -> CandidateSpec:
    if candidate_id not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown candidate {candidate_id!r}; known: {known}")
    return REGISTRY[candidate_id]


def runnable_candidates() -> list[str]:
    return sorted(cid for cid, spec in REGISTRY.items() if spec.runner)
