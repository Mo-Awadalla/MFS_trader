"""Save audited free-data provenance and one untested passive-spread opportunity."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from research_scout.databento_public_spread_supply_20261003 import OUT as SUPPLY
from research_scout.inspect_databento_public_sample_20261003 import OUT
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write


def main():
    acquisition = json.loads((OUT / "acquisition.json").read_text())
    inventory = json.loads((OUT / "inventory.json").read_text())
    book = json.loads((OUT / "book_verification_v3.json").read_text())
    supply = json.loads((SUPPLY / "results.json").read_text())
    audit = json.loads((SUPPLY / "independent_verification.json").read_text())
    nasdaq_cost = json.loads((OUT / "zero_cost_metadata_check.json").read_text())
    mini_cost = json.loads((OUT / "mini_zero_cost_metadata_check.json").read_text())
    assert book["verified"] and book["source_inventory_sha256"] == sha(OUT / "inventory.json")
    assert audit["verified"] and audit["results_sha256"] == sha(SUPPLY / "results.json")
    assert supply["eligible_cells"] == 1 and len(supply["eligible"]) == 1
    assert inventory["acquisition_sha256"] == sha(OUT / "acquisition.json")
    for checks in (nasdaq_cost, mini_cost):
        assert checks["paid_calls"] == checks["market_data_requests"] == 0
        assert all(not quote["quoted_zero"] for quote in checks["quotes"])
    event = supply["eligible"][0]
    report = OUT / "REPORT.txt"
    assert not report.exists()
    lines = [
        "FREE DATABENTO NASDAQ DATA VERIFIED; ONE SPREAD BUDGET NEEDS EXECUTION TESTING",
        "Updated " + datetime.now(UTC).isoformat(), "",
        "No reliable edge or trading profit has been established. The new result is one fee-viable hypothetical passive spread in one vendor-selected NVDA day. It is not a fill, a profitable strategy, or independent temporal validation.", "",
        "FREE SOURCE ACQUISITION",
        "Downloaded the two Nasdaq samples publicly linked by Databento, without a credential or account credit. Full HTTP responses reached EOF and their first64KiB matched the separately inspected prefixes. Total downloaded full-file size:1,242,973,169bytes. Sources remain immutable; no paid market-data request, signup, billing change, order or third-party message was made.",
        "Official download page: https://databento.com/tick-data",
        "MBO:6,480,679NVDA records;855,632,910CSV bytes; SHA256 " + next(s["sha256"] for s in acquisition["sources"] if s["schema"] == "mbo"),
        "MBP-1:2,400,522NVDA records;387,340,259CSV bytes; SHA256 " + next(s["sha256"] for s in acquisition["sources"] if s["schema"] == "mbp1"),
        "Both files contain2025-09-16, publisher2/XNAS.ITCH, instrument11667. MBO starts with a clear record at07:05:06.677677658UTC and ends23:59:59.748544733UTC; quotes begin08:00:00.015462508UTC and end23:59:56.024803407UTC. These are normalized vendor samples, not original ITCH packets. Sequence gaps are expected in a one-symbol extract and do not establish market-wide packet continuity.", "",
        "SOURCE VERIFICATION",
        "Reconstructed every displayed order add/cancel from6,480,679MBO records and reconciled EVERY one of the2,400,522MBP-1 records, including intermediate records, against the resulting exact prices, sizes, order counts and clocks. Zero mismatches. All221,772resting fill records referenced an existing displayed order with sufficient size. Four CSV-typing, five book-lifecycle and four reconciliation regression tests passed. No timestamp, identifier or price was converted through float.",
        "Native and capture timestamps and native sequences were nondecreasing. Every non-reset record matched ts_recv minus ts_event to ts_in_delta exactly. The one initial R record carries BAD_TS_RECV: it initializes an empty book but is never treated as a tradable timestamp. No later quality-flagged record was dropped or repaired.6,041orders remain at the sample end; no assumption is made about their subsequent fate.",
        "The reconciliation uses separate MBO reconstruction and vendor MBP-1 outputs from the same normalized feed. It is not an independent raw ITCH decoder, private-fill audit, consolidated NBBO or live latency measurement.", "",
        "AUDIT REPAIRS BEFORE ECONOMIC TESTING",
        "The first auditor incorrectly assumed one F_LAST per native sequence. The sample has81,060native sequence groups with multiple F_LAST records. Example301782contains T,F,C,each flagged128, with different pre-fill and post-cancel BBOs. Version2 reconciled each normalized action instead. A causal strategy must use the final state after every record at a capture timestamp strictly precedes its information cutoff.",
        "Version2 also incorrectly treated the displayed order price as a private limit. Nasdaq's specification distinguishes display and execution prices. Version3 preserved and counted7,584fills at different prices, while continuing to verify resting IDs, sides and sizes. A simulated order must enforce its own explicit limit and queue; these other orders' fills cannot simply be copied. Both failed audit versions remain preserved. No economic result was generated by either failure.",
        "Databento normalization: https://databento.com/docs/venues-and-datasets/xnas-itch",
        "Order-state conventions: https://databento.com/docs/examples/order-book/order-tracking",
        "Nasdaq ITCH specification,sections1.3and1.4.2: https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHSpecification.pdf", "",
        "FROZEN SPREAD SUPPLY SCREEN",
        "Every10ms from09:30:05through15:59:30ET; information cutoff decision minus1ms. Latest quote strictly before cutoff, including all same-capture-clock records; it must be complete, positive, uncrossed, cent-priced,5..1000USD,<=50bp spread and<=5msold on native and capture clocks. No fallback from a rejected latest quote. Quantity is at most10%of both touches and10000USD at a2%ask collar rounded up to cents.",
        "The budget assumes buying the current bid and selling the current ask. It subtracts two max(1USD,0.005USD/share)commissions,1bp adverse cost on each leg, and sales charges0.00003of notional+0.000166/share. No rebate. Admission requires at least2bp net of entry notional. Integer cash units are1e-14USD, with five focused size/cost/clock tests passed.",
        "2,336,501grids:22invalid/incomplete books;2,116,553quote-age rejections;0spread-cap rejections;1,567zero quantities;218,359computed budgets. Three were positive and exactly one reached2bp. These grids are repeated market observations, not independent trades.",
        f"The sole qualifying decision is2025-09-16 09:31:43.610ET ({event['decision_ns']}epoch ns), quote source row{event['quote_source_row']}. Buy41shares at176.74 and sell at176.87 would imply {event['projected_net_usd']}USD / {event['projected_net_bp']}bp after modeled costs IF both passive fills occurred. No future execution or exit prices were used or replayed. The displayed13cent spread alone does not establish fillability.",
        "A separate full-grid audit read the original CSV with Python's standard CSV reader, integer timestamp parsing and independent Decimal costs. It verified all2,336,501admissions/rejections, every computable budget, the best budget, and the one qualifying cell. It did not reuse the Arrow reader, NumPy, production clock helper or production budget function.", "",
        "PAID DATA WAS NOT REQUESTED",
        "Databento explicitly documents metadata access as free. Four authenticated metadata.get_cost checks were made, and no corresponding timeseries request followed. For NVDA2025-09-17, the account returned nonzero estimates for XNAS.ITCH MBO and MBP-1 and EQUS.MINI MBP-1 and trades. These quotes are not charges and are not a claim about every dataset/date.",
        "Pricing documentation: https://databento.com/docs/api-reference-historical/basics/metered-pricing",
        "Nasdaq estimates: " + json.dumps([q["estimated_cost_usd"] for q in nasdaq_cost["quotes"]]),
        "Mini estimates: " + json.dumps([q["estimated_cost_usd"] for q in mini_cost["quotes"]]), "",
        "NEXT GATE",
        "Freeze a small, causal passive-order protocol before inspecting the qualifying event's subsequent economics. Use actual displayed IDs ahead of the order, separate fills from cancellations, strict own limit prices, latency and fill-notification delays, cancel races, and a mandatory inventory horizon below30s. Never infer a fill from a quote touch. Preserve unknown inventory and fees on partial fills. One passing event cannot establish reliability even if the replay is positive; independent dates are required before promotion.",
        "The earlier SPY-sweep/follower hypothesis is closed after694cached2023-2025opening windows:1,132computable budgets,all negative,zero signals. Keep the112cached2026ETF files out of that family. This new NVDA sample is distinct data and a different liquidity-provision test, not a rescued threshold.",
        "Global ledger143economic configurations/195implementation versions/462focused tests. This source work and supply screen add18tests after the444-test follower checkpoint, but no economic configuration or return. Goal active; no strategy is ready for deployment.",
        "Book verification SHA256: " + sha(OUT / "book_verification_v3.json"),
        "Supply specification SHA256: " + sha(SUPPLY / "specification.json"),
        "Supply results SHA256: " + sha(SUPPLY / "results.json"),
        "Supply independent verification SHA256: " + sha(SUPPLY / "independent_verification.json")]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    next_note = OUT / "NEXT_RESEARCH.txt"
    next_note.write_text(
        "Goal active. User prioritizes raw outperformance and actual reliability,strict HFT,stocks/ETFs/crypto,conservative fees,no paid calls. No reliable edge.\n\n"
        "Official free Databento XNAS.ITCH sample downloaded fully without credentials:NVDA2025-09-16,MBO6,480,679records and MBP-1 2,400,522records. Sources and exact typed parquet live underresearch_scout/databento_public_mbo_20261003. book_verification_v3.json fully reconciles every quote from MBO,all221,772restingF IDs/side/size. Shared upstream normalization,notrawITCH/privateexecution. InitialRflag8isinitializationnottradabletime. Preserve immutable files/code hashes.\n\n"
        "Critical rules:multiple F_LAST can occur withinone native sequence; use final receive-clock group strictly before cutoff for causal state.7,584Fprices differ fromdisplay; own passive limits must be checked explicitly. Keepv1/v2failedauditors;v3corrects assumptions with regression tests and official docs. No financial replay has run.\n\n"
        "spread_supply/specification.json andresults.json arefrozen. IndependentrawCSVfullgrid audit passed:2,336,501grids,218,359budgets,3positive,1>=2bp. Sole qualifying signal:" + json.dumps(event) + ". Thisis only a budget ifpassivebuybid/sellaskfill;notPnL.\n\n"
        "Next safe step:freeze one strict HFT order protocol and latency/fee/clock stress scenarios BEFORE opening thissignal's forward economic outcome. IdentifiedNasdaq MBO supports exact displayedqueue-ahead tracking. Model end-to-end causalentry,partialfills,notifications,cancellations,askposting,forcedexit<30s withknownbiddepth;unknownsarenotzero. Noquote-touchfills,nofuturequantityresizing,noassumedreplicationfromone day. Positiveoneeventwouldbeexploratoryonly.\n\n"
        "The free cost endpoint was called4times. AdditionalNVDA2025-09-17XNASMBO/MBP1andEQUS.MINIMBP1/trades estimatesareNONZERO. Correspondingtime-serieswereNOTrequested. Userforbids paidcalls;do notconsumecreditsorplacebillablequeries. Cacheddata andpublishedunauthenticatedsamplesremainusable.\n\n"
        "Earlierfollowerfamilyclosed694sessions/178,487,408records/1,132negativebudgets,zeroeconomicruns;reserve2026forproperselected-candidateevaluation. Globalcounts143economic/195implementation/462focusedtests. Noactiveprocessatthischeckpoint,noorders,noexternalmessages,nosubagents. Latestturnprogress,notblocked.\n",
        encoding="utf-8")
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert (state["current_configurations"], state["implementation_versions"], state["focused_tests_total"]) == (143, 195, 444)
    state.update(updated_at_utc=datetime.now(UTC).isoformat(), status="active", active_research_jobs=[],
                 latest_report=str(report), next_research_note=str(next_note), focused_tests_total=462,
                 databento_public_sample_report=str(report), databento_public_sample_book_verified=True,
                 databento_public_sample_records=8881201, databento_public_sample_dates=1,
                 databento_public_sample_quote_reconciliation_mismatches=0,
                 databento_public_spread_verified=True, databento_public_spread_qualifying_cells=1,
                 databento_public_spread_best_budget_usd=str(Decimal(event["projected_net_usd"])),
                 databento_public_spread_economic_configurations_executed=0,
                 databento_free_metadata_cost_checks=4, databento_extra_history_quoted_zero=False,
                 databento_public_sample_paid_calls=0, reliable_edge_found=False,
                 previous_goal_turn_classification="progress",
                 remaining_evidence_work="Free Nasdaq NVDA sample fully reconciled. One independently audited passive spread budget>=2bp;freeze causal queue/latency protocol and test actual conditional economics. One sample day cannot establish reliability. Extra history cost checks nonzero;no paid delivery. Followerfamilyclosed.")
    write(checkpoint, state)
    print(json.dumps({"report": str(report), "qualified_budget_cells": 1, "economic_returns_calculated": False,
                      "counts": [143, 195, 462], "paid_calls": 0, "goal": "active"}))


if __name__ == "__main__":
    main()
