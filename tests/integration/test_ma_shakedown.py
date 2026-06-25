from __future__ import annotations

from pathlib import Path

from engine.shakedown import run_ma_shakedown


def test_ma_shakedown_writes_reports_and_exercises_failure_modes(tmp_path):
    result = run_ma_shakedown(
        out_dir=tmp_path / "ma_shakedown",
        bars=140,
        seed=7,
        fast_window=5,
        slow_window=20,
        trend_filter_active=False,
    )

    assert result.passed
    assert Path(result.report_path).exists()
    assert Path(result.json_path).exists()
    assert result.data_quality["result"] in {"PASS", "WARN"}
    assert result.research_metrics["final_equity"] > 0

    scenarios = {scenario.name: scenario for scenario in result.scenarios}
    assert scenarios["baseline"].replay.orders_filled > 0
    assert scenarios["rejection"].replay.orders_rejected > 0
    assert scenarios["timeout"].replay.orders_timed_out > 0
    assert scenarios["partial_fill"].report.order_state_counts["PARTIALLY_FILLED"] > 0
