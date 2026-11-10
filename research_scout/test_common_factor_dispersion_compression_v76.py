"""Frozen 2021-2023 P&L test of common-factor dispersion compression v76."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

from research_scout import audit_common_factor_dispersion_compression_v76 as audit  # noqa: E402
from research_scout import audit_constituent_participation_acceleration_v75 as v75  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_sec_earnings_breadth_index_readthrough_v73 as helper  # noqa: E402
from research_scout import test_spy_btc_perpetual_fresh_position_v44 as v44  # noqa: E402

PREREG = ROOT / "research_scout" / "common_factor_dispersion_compression_prereg_v76.json"
BLIND = ROOT / "research_scout" / "common_factor_dispersion_compression_returns_blind_audit_v76.json"
OUTPUT = ROOT / "research_scout" / "common_factor_dispersion_compression_results_v76.json"
REPORT = ROOT / "research_scout" / "COMMON_FACTOR_DISPERSION_COMPRESSION_REPORT_V76.md"
START = helper.pd.Timestamp("2021-01-04")
END = helper.pd.Timestamp("2023-12-29")
YEARS = (2021, 2022, 2023)
EXPECTED_SIGNALS = 376


def variants(states):
    old, _ = v75.load_states()
    return {
        "actual": {day: row["action"] for day, row in states.items()},
        "two_half_spy_momentum": {
            day: row["spy_control_action"] for day, row in states.items()
        },
        "final_breadth_only": {
            day: old.get(day, {}).get("final_breadth_action", "CASH")
            for day in states
        },
    }


def gates(dev, independent):
    actual = dev["observed_bbo"]
    years = actual.get("year_pnl_usd", {})
    sleeves = actual.get("instrument_pnl_usd", {})
    return {
        "at_least_2_trades_per_week": actual["trades_per_declared_week"] >= 2,
        "execution_coverage_at_least_95_percent": dev["execution_coverage"] >= 0.95,
        "profit_factor_at_least_1_10": actual["profit_factor"] >= 1.10,
        "positive_each_year": all(years.get(str(y), 0) > 0 for y in YEARS),
        "both_actions_positive": all(sleeves.get(s, 0) > 0 for s in ("UPRO", "SPXU")),
        "ending_cash_above_adjusted_spy": actual["ending_cash_usd"] > dev["spy_hurdle"]["ending_cash_usd"],
        "positive_extra_cent": dev["extra_cent"]["fixed_notional_pnl_usd"] > 0,
        "positive_10_36_delay": dev["delay"]["fixed_notional_pnl_usd"] > 0,
        "positive_delete_best_10": actual["pnl_without_best_10_sessions_usd"] > 0,
        "bootstrap_lower_above_zero": dev["bootstrap_lower"] > 0,
        "month_permutation_p_below_0_05": dev["permutation"]["one_sided_p_value"] < 0.05,
        "independent_positive_pf_above_one": independent["fixed_notional_pnl_usd"] > 0 and independent["profit_factor"] > 1,
        "mean_above_two_half_spy_control": actual["mean_session_pnl_usd"] > dev["controls"]["two_half_spy_momentum"]["mean_session_pnl_usd"],
        "mean_above_final_breadth_control": actual["mean_session_pnl_usd"] > dev["controls"]["final_breadth_only"]["mean_session_pnl_usd"],
    }


def render(payload):
    dev = payload["development"]
    actual = dev["observed_bbo"]
    failed = [k for k, v in dev["gates"].items() if not v]
    return "\n".join(
        [
            "# Common-Factor Dispersion Compression v76",
            "",
            "**Development survivor; recent years authorized.**" if dev["gate_passed"] else "**Rejected in 2021–2023; recent years locked.**",
            "",
            f"- Trades: {actual['sessions']} ({actual['trades_per_declared_week']:.3f}/week)",
            f"- P&L / PF: ${actual['fixed_notional_pnl_usd']:.2f} / {actual['profit_factor']:.3f}",
            f"- Ending cash / SPY: ${actual['ending_cash_usd']:.2f} / ${dev['spy_hurdle']['ending_cash_usd']:.2f}",
            f"- Annual: {actual.get('year_pnl_usd', {})}",
            f"- Sleeves: {actual.get('instrument_pnl_usd', {})}",
            f"- Extra cent / delay / delete10: ${dev['extra_cent']['fixed_notional_pnl_usd']:.2f} / ${dev['delay']['fixed_notional_pnl_usd']:.2f} / ${actual['pnl_without_best_10_sessions_usd']:.2f}",
            f"- Bootstrap lower / permutation p: {dev['bootstrap_lower']:.6f} / {dev['permutation']['one_sided_p_value']:.4f}",
            f"- Independent: ${payload['independent']['fixed_notional_pnl_usd']:.2f}, PF {payload['independent']['profit_factor']:.3f}",
            f"- Control means: {dev['controls']['two_half_spy_momentum']['mean_session_pnl_usd']:.4f}, {dev['controls']['final_breadth_only']['mean_session_pnl_usd']:.4f}",
            "",
            "Failed gates: " + (", ".join(failed) if failed else "none"),
            "",
        ]
    )


def main():
    if not json.loads(BLIND.read_text(encoding="utf-8"))["gate_passed"]:
        raise RuntimeError("blind audit did not pass")
    states, _ = audit.load_states()
    actions = variants(states)
    if sum(a != "CASH" for a in actions["actual"].values()) != EXPECTED_SIGNALS:
        raise RuntimeError("signal count changed")
    arca = relay.sessions(relay.ARCA_PATH)
    excluded = relay.degraded(relay.ARCA_CONDITIONS)
    actual_rows = helper.make_rows(arca, excluded, actions["actual"], states)
    dev = {
        "execution_coverage": len(actual_rows) / EXPECTED_SIGNALS,
        "observed_bbo": helper.summarize(actual_rows, 10),
        "extra_cent": helper.summarize(helper.make_rows(arca, excluded, actions["actual"], states, adverse_cents=0.01)),
        "delay": helper.summarize(helper.make_rows(arca, excluded, actions["actual"], states, delay_minutes=5)),
        "controls": {
            name: helper.summarize(helper.make_rows(arca, excluded, value, states))
            for name, value in actions.items() if name != "actual"
        },
        "spy_hurdle": v44.adjusted_spy_hurdle(START, END),
        "bootstrap_lower": helper.bootstrap_lower(actual_rows),
    }
    panel = helper.return_panel(arca, excluded, sorted(states))
    dev["permutation"] = helper.month_stratified_permutation(actual_rows, states, panel)
    equs = relay.sessions(relay.EQUS_PATH)
    independent = helper.summarize(
        helper.make_rows(equs, relay.degraded(relay.EQUS_CONDITIONS), actions["actual"], states)
    )
    dev["gates"] = gates(dev, independent)
    dev["gate_passed"] = all(dev["gates"].values())
    payload = {
        "candidate": "v76",
        "specification_sha256": hashlib.sha256(PREREG.read_bytes()).hexdigest(),
        "status": "development_survivor" if dev["gate_passed"] else "rejected_recent_years_locked",
        "development": dev,
        "independent": independent,
        "recent_years_status": "unlocked" if dev["gate_passed"] else "locked_not_read",
        "new_databento_calls_or_purchases": False,
    }
    safe = helper.json_safe(payload)
    OUTPUT.write_text(json.dumps(safe, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    REPORT.write_text(render(safe), encoding="utf-8")
    print(json.dumps(safe, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
