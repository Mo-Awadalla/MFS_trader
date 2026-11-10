"""Freeze a returns-unopened supply screen for same-index ETF relative prices."""

import json
from datetime import UTC, datetime
from pathlib import Path

import exchange_calendars as xc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/same_index_hft_20260930"


def main():
    OUT.mkdir(exist_ok=True)
    path = OUT/"specification.json"
    if path.exists():
        raise RuntimeError("Do not overwrite the frozen supply protocol")
    calendar = xc.get_calendar("XNYS", start="2023-01-01", end="2023-12-31")
    dates = [str(calendar.sessions[calendar.sessions.month == m][0].date()) for m in range(1, 13)]
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Same-index unlevered ETF pair convergence over seconds",
        "relation_to_prior": "Related cross-ETF price/flow hypotheses and wrapper studies exist and failed or were unresolved. New pairs and a paired convergence payoff are a variation in the global exposed search, not an independent discovery. Top-level727research files contained no IVV/QQQM/VTWO/VOO mention; recursive search found only unrelated earnings-text examples. This is limited search evidence, not exhaustive novelty.",
        "pairs": [["SPY", "IVV"], ["QQQ", "QQQM"], ["IWM", "VTWO"]],
        "dates": dates,
        "scope": "First XNYS session of every2023month; first five regular-session minutes. Feasibility only before any future returns. Same-day ratio calibration avoids using unadjusted prior-day prices around different distribution dates. Does not imply interchangeable shares, identical NAV, riskless arbitrage or guaranteed convergence.",
        "planned_configurations": [{"pair": p, "hold_seconds": h} for p in ["SPY_IVV", "QQQ_QQQM", "IWM_VTWO"] for h in [15, 30]],
        "download": {"window_et": ["09:30:00", "09:35:20"], "feed": "sip", "max_pages": 100,
                     "per_file_max_bytes": 100_000_000, "total_max_bytes": 4_000_000_000,
                     "max_seconds_per_file": 180, "market_data_only": True, "paid_fallback": False},
        "observation": "250msdecision grid09:32:00inclusive through09:34:30exclusive ET. At each decision use strictly earlier source quotes than decision-100ms. Conditional historical quote availability only, not proven historical receipt or a free real-time SIP feed. Complete source prefix, valid regular R two-sided uncrossed positive prices/sizes; conflicting same-timestamp states cause explicit no-order policy. No arbitrary standing-quote expiry. Bothspreads<=20bp.",
        "reference": "For each decision sourcecutoff, sample both standing midquotes at integer-second offsets5..64seconds earlier, always strictly earlier than each target. At least45of60joint valid samples. FairratioR=exp(median(log(midA/midB))). UncertaintyMAD=median(abs(logratio-median)). No full-day, forward, close or future-return calibration.",
        "sizing": "Daily benchmarkequity$10000;eachlegnotional<=5000/1.01,>=100.100sharehistoricallotassumptionconditionalpendingdefinitionverification. Integersfixedfromknownquotes,atmost10%ofdirectionaldisplayeddepth. EnumerateqA; qB=nearestinteger(qA*R). Requireabs(qB/R-qA)/qA<=2.5%. Choosehighestminimumlegnotional,thenlowesthedgemismatch. No future resizing. Separate pairbooks, no shared-capital aggregate return claimed.",
        "supply_payoff": "Evaluatebothorientations. FairmidA=sqrt(midA*R*midB),fairmidB=fairmidA/R. Hypothetical immediate full convergence liquidation at fairmid minus currenthalfspread forlong andplus currenthalfspread forshort. Entryask/bid,all4commissions,sellcharges,4adversecharges,andonecalendar-day5%annualborrowcost. This is a conditional convergence budget, NEVER an observed profit or guaranteed upperbound. Eligibleifbudget>=minlegnotional*(5bp+2*MAD). Directionwithhighestmarginchosen. Stockborrow/locates/shortpermissionnotestablished;feasibilityconditional.",
        "costs": {"commission_per_share": .0075, "minimum_per_order": 1., "sell_rate": .00003,
                  "sell_per_share": .0002, "adverse_per_execution": .0001, "short_annual_rate": .05,
                  "minimum_borrow_days_per_pair_attempt": 1},
        "supply_gate": "Countall600decisiongridsperpairdayandretainfailedsources. Countdistincthypotheticalattemptsgreedilywith60secondcooldownafterfirsteligibility. Require>=12attemptsacross>=6ofthe12datesbeforebuildingthepairedexecutionreplay. No P&L is evaluated by this screen. Positive feasibility does not pass economics.",
        "planned_execution": "Ifsupplypasses,freezeimplementationbeforeevaluatingfutureprices. Baseprocessing50ms,outgoing100ms,return100ms;exit15/30secondsafterlastentryACKplusprocessing/outgoing. Stress250msand1ssource/outgoing/return,2xfees,2xadverse,+/-100msalignment. GuardedFOKlimit10bpfromeachknownentryquote; neverassumeatomicpairfills. Onefilled/onefailedlegmustunwindwithitscashflow;unresolvedfillsretaininventoryunknown. Allquotes/depthstatesin+/-1msincludingalltiedpredecessors;fullfixedquantityandsuccessorrequired. Historicalquotescannotproveactualroutingorborrow.",
        "progression": "At leastsupplygatebeforeeconomics. Laterrequirecompletepositiveaftercostbaseand250msstress,positivebothdirectionsandafterremovingbest3days,date-blockuncertaintycontrolacrosssixplannedrules. A1sstressfailuremustestablishalatencybudget,notbesilentlyomitted. Separatefixed2024-25selectiononlyafterdevelopmentandmechanicschecks. Noreliabilityclaimwithoutactualfeed/order/borrowevidenceandforwardvalidation.",
        "sources": [
            "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf-ivv",
            "https://www.sec.gov/Archives/edgar/data/1378872/0001193125-23-299209-index.htm",
            "https://www.sec.gov/Archives/edgar/data/1021882/000110465923121982/0001104659-23-121982-index.htm",
            "https://www.sec.gov/Archives/edgar/data/1100663/000119312524125249/d799229d497.htm",
            "https://docs.alpaca.markets/us/docs/market-data-faq"],
        "selection_opened": False, "actual_execution_verified": False, "reliable_edge_established": False,
    }
    path.write_text(json.dumps(spec, indent=2)+"\n")
    print(json.dumps({"dates": dates, "pairs": spec["pairs"], "planned_configurations": 6, "economic_tests": 0}))


if __name__ == "__main__":
    main()
