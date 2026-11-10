"""Freeze a Bybit-first funding supply screen before looking at its rates."""

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/bybit_funding_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Bybit-first imminent cross-venue funding payments over seconds",
        "relation_to_prior": "The prior broad screen required abs(Binance rate)>=14bp. This dependent supply extension instead requires abs(Bybit rate)>=14bp and therefore includes the previously unsearched Bybit-only extremes. Do not exclude previously seen overlap or call this independent discovery.",
        "dates": [f"2024-{m:02d}-01" for m in range(1,13)], "settlement_hours_utc": [8,16],
        "universe": "All contemporaneous native Bybit ticker symbols ending USDT, exact-symbol Binance counterparts only; no current-survivor selection or return-based symbol choice.",
        "signal_cutoff": "Target funding time minus 10.25 seconds; entry decision target minus 10 seconds. Last strictly prior capture only. The existing native Binance minute files cover the same cutoff and are reused.",
        "bybit_state": "Merge snapshot/delta ticker fields in captured order. A full snapshot replaces prior state. A disconnect clears state. Before using fundingRate, nextFundingTime and markPrice, each must have an observed native value; never seed missing fields from later records or realized rates. Require coherent monotonically increasing cs within a stream, valid positive mark and finite rate, last capture/publication ages <=5s, and nextFundingTime equal target. A carried field is usable only along an observed unbroken update stream after it became known; retain each field's provenance.",
        "prescreen": "abs(Bybit upcoming fundingRate)*10000 >=14, regardless of Binance rate. Keep all missing/invalid states and contracts in the ledger. A sample lacking fields cannot establish absence of a funding opportunity.",
        "pair_gate": "For equal units, abs(Bybit rate*Bybit mark - Binance rate*Binance mark)/max(marks)*10000 >28bp for four 6bp taker fees and four 1bp adverse allowances, before spreads. Both next funding timestamps must equal target. Historical contract equivalence, permissions, lifecycle and funding semantics must be checked before execution.",
        "hft_execution_if_supply": "Only if supply survives: predeclare paired entry at T-10 seconds and exit decision at T+10 seconds, one-second outbound/ACK base and three-second stress, native transaction-time books, partial legs/unwind, actual credited funding, basis repricing and collateral. Keep maximum inventory age <=30s. A rate gap is not a profit; account for price adjustment around funding.",
        "download": {"exchange":"bybit","channel":"tickers","slice_minutes":1,"per_slice_decoded_cap":96000000,
                     "total_decoded_cap":2304000000,"workers":3,"authenticated":False,"paid_fallback":False},
        "format_pilot": "First chronological window, 2024-01-01 07:59 UTC. Inspect field coverage and API metadata aliases before the remaining identical scheduled windows. Do not change economic thresholds based on the pilot.",
        "data_recovery": "If native windows lack a reconstructible field, document it as unknown. Any additional native prefix or normalized full-day acquisition must have a separate source-recovery plan and preserve the original missingness.",
        "primary_sources": ["https://bybit-exchange.github.io/docs/v5/websocket/public/ticker", "https://docs.tardis.dev/historical-data-details/bybit.md"],
        "selection_2025_opened":False,"economic_configurations_run":0,"reliable_edge_established":False,
    }
    with (OUT/"specification.json").open("x",encoding="utf-8") as stream:
        stream.write(json.dumps(spec,indent=2)+"\n")
    print(json.dumps({"planned_native_minutes":24,"pilot_date":"2024-01-01","stage":"source coverage before economic replay"}))


if __name__=="__main__":
    main()
