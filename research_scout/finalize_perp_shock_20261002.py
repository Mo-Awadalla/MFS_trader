"""Preserve the completed shock experiment without promoting a fragile gain."""

import json
from datetime import UTC, datetime

from research_scout.prepare_perp_shock_replay_20261002 import FLOW, OUT, PARENT, ROOT


def main():
    quote = json.loads((PARENT / "independent_verification.json").read_text())
    flow = json.loads((FLOW / "independent_verification.json").read_text())
    audit = json.loads((OUT / "replay_v1/independent_verification.json").read_text())
    result = json.loads((OUT / "replay_v1/results.json").read_text())
    assert all(a["verified"] for a in (quote, flow, audit))
    (PARENT / "REPORT.txt").write_text(
        "PERPETUAL PRICE-SHOCK QUOTE SCREEN — COMPLETE\n\n"
        "Sixty cached one-minute Binance USDT perpetual sources across twelve first-of-month 2024 dates. "
        "At 250ms decisions, require both bid and ask to move at least 30bp over one second, with fresh native "
        "capture/T/E clocks, spread at most 10bp and at least 2000 USDT on both sides at both endpoints.\n\n"
        "27,502,201 native messages; 3,732,360 signal rows; 3,797,840 quote rows. "
        "Eight raw qualifying rows became five events after the fixed 30-second cooldown: ADA, CELO, XRP, BAKE, ZRO. "
        "Independent raw-source audit reconciled every quote, clock, gate, selection and aggregate; "
        "maximum derived Decimal difference 5e-24. Nine focused tests passed.\n\n"
        "No P&L at the screen stage. These are previously exposed development sources, not independent validation. "
        "Continue to ../perp_shock_flow_hft_20261002/REPORT.txt and ../perp_shock_response_hft_20261002/REPORT.txt.\n",
        encoding="utf-8")
    (FLOW / "REPORT.txt").write_text(
        "PERPETUAL PRICE-SHOCK TRADE CONFIRMATION — COMPLETE\n\n"
        "All five parent events passed the already frozen requirement: at least five native MARKET trades, "
        "5000 USDT notional and 75% notional in the shock direction in the preceding matching-time second, "
        "captured strictly before the information cutoff. No future trade was used to validate a past signal.\n\n"
        "Five free public source files; 26,697 native executions, 16,626 pre-cutoff prefix rows independently "
        "checked for IDs/clocks/disconnects, 5,730 trades counted in the signal windows. "
        "Independent audit matched all rows, gates and selections exactly. Eight focused tests passed.\n\n"
        "Confirmation establishes observable activity, not a profitable response. "
        "All five events were carried into the fixed execution replay.\n", encoding="utf-8")
    lines = [
        "PERPETUAL PRICE-SHOCK RESPONSE — NO RELIABLE EDGE ESTABLISHED", "",
        "Both predeclared controls (follow and fade) used all five confirmed events across four dates. "
        "Orders were at most 200 USDT, at most 10% of causal touch depth, with fixed quantity and 10bp FOK collar. "
        "Exit decision was 15 seconds after entry acknowledgement; planned inventory remained below 30 seconds. "
        "Costs: 6bp taker fee plus 1bp adverse allowance on entry and exit. No funding payment credited.", "",
        "Rule | Scenario | Full sample net lower/upper USDT | Completed round trips | Known component lower (not full net if unknown)"]
    for row in result["scenarios"]:
        net = f"{row['net_lower']} / {row['net_upper']}" if row["complete"] else "UNKNOWN"
        lines.append(f"{row['rule']} | {row['scenario']} | {net} | {row['completed_round_trips']} | {row['known_component_lower']}")
    lines.extend(["",
        "Following lost in all five fully known cases; the 100ms clock case retained an unknown entry. "
        "Fading lost 0.2203602 USDT at 250ms delay. Its 3-second-delay result gained 0.217154 USDT from "
        "three completed trades on two dates, with two no-fills; removing the best three dates leaves zero. "
        "The baseline fade is UNKNOWN: BAKE offered insufficient complete touch depth for the frozen quantity, "
        "so ZRO later that date was halted. The known baseline component of +1.0607811 USDT includes "
        "CELO +1.166832; removing CELO makes that known component negative. Do not present it as full strategy P&L.", "",
        "Independent verification: all 69,047 native messages (68,447 BBO, 600 funding marks), ten causal plans, "
        "112 execution envelopes, 42 cash rectangles and twelve scenario aggregates matched exactly. "
        "Fourteen focused execution tests and Ruff passed. Quote and trade-flow parent audits also passed.", "",
        "Limits: displayed-book execution is conditional, not private fill evidence. Historical order filters "
        "and account permissions remain unverified. Price grids and coarse ten-unit quantity increments "
        "were frozen assumptions; ZRO's launch tick is supported by the official notice at "
        "https://www.binance.com/en/support/announcement/detail/09bdfa5901c94bf6a4e60ab66078a75c . "
        "Five events cannot establish reliability. No candidate is promoted and no 2025 selection data was opened.", "",
        "Search accounting: two new economic configurations and two implementation versions; 31 focused "
        "tests across the quote, flow and execution stages. Cumulative 132 configurations, 182 implementation "
        "versions and 327 focused tests. The goal remains active; no reliable edge or competition win is claimed."])
    (OUT / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    assert checkpoint["current_configurations"] == 130 and checkpoint["implementation_versions"] == 180
    checkpoint.update(status="active", reliable_edge_found=False, current_configurations=132,
                      implementation_versions=182, focused_tests_total=327,
                      updated_at_utc=datetime.now(UTC).isoformat(), report=str(OUT / "REPORT.txt"),
                      active_research_jobs=[], paused_at_user_request=False,
                      perp_shock_reports=[str(p / "REPORT.txt") for p in (PARENT, FLOW, OUT)],
                      perp_shock_quote_and_flow_verified=True, perp_shock_events=5,
                      perp_shock_economic_configurations=2, perp_shock_execution_and_cash_verified=True,
                      perp_shock_scenario_cases=12, perp_shock_complete_scenarios=result["complete_scenarios"],
                      perp_shock_positive_complete_scenarios=result["positive_complete_scenarios"],
                      perp_shock_actual_execution_verified=False, perp_shock_candidates=[],
                      perp_shock_selection_2025_opened=False,
                      remaining_evidence_work="Shock response completed and independently audited. No robust candidate; one tiny positive delayed control is not a reliable edge. Next freeze a distinct coherent BTC/ETH move versus fresh lagging-coin quotes screen using audited cached information-time states; no threshold fitting or 2025 selection exposure.")
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(OUT / "REPORT.txt"), "current_configurations": 132,
                      "implementation_versions": 182, "focused_tests_total": 327, "reliable_edge_found": False}))


if __name__ == "__main__":
    main()
