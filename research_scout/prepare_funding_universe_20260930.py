"""Freeze a native broad-universe imminent funding screen, not carry returns."""

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/funding_universe_hft_20260930"


def main():
    OUT.mkdir(exist_ok=True)
    path = OUT/"specification.json"
    if path.exists():
        raise RuntimeError("Preserve the original funding-universe specification")
    spec = {"created_at_utc": datetime.now(UTC).isoformat(),
            "family": "Large imminent Binance funding payments hedged against Bybit over seconds",
            "relation_to_prior": "The earlier six-contract2024Binance/Bybit funding screen had zero eligible28bp differences. This broadens the instrument universe using contemporaneously recorded native Binance messages. It is a dependent research-family variation, not a new independent discovery or reduced-cost rescue.",
            "dates": [f"2024-{m:02d}-01" for m in range(1, 13)], "settlement_hours_utc": [8, 16],
            "scope": "All native Binance symbols endingUSDT, excluding dated suffixes, whose full markPrice messages identify upcoming funding. No current-survivor instrument list or chosen profitable symbols. This is specifically a large-Binance-rate universe: it does not cover extreme Bybit-only rates when Binance absrate<14bp. Native symbol/data absence remains visible.",
            "stage_a": "Last full native markPrice update received strictly before settlement-30seconds. Require positive finite mark, finite upcoming funding rate, nextfundingT equal target, both receive/event agespositive<=5s, event-to-capturelagbetween-1msand5s. Use nativeE as publication clock only, never as physical book transaction clock. Full snapshots supersede prior state; disconnect markers clear state. Absupcomingrate>=14bp is the fixed broad-universe prescreen. Do not use realized settlements or subsequent prices to choose contracts.",
            "stage_b": "Fetch full-day free Bybit derivative_ticker files for every stageA contract/date, exact symbol names only. Last received state beforeT-30s; positivefinite mark/rate; receive/event age<=5s; next fundingtimestamp=T. For equal contract units, quoted payment difference=abs(rB*mB-rY*mY)/max(mB,mY)*10000; require>28bp for four6bpfeesplusfour1bpadverseallowances, before spreads. Unit/underlying equivalence and native Bybit normalization must be independently established before any P&L; unmatched names, stale states and source failures remain unknown. No favorable deletion or negative-rate truncation.",
            "next_stage": "Only stageB supply justifies fixed paired execution replay: entry atT-30s, exit aboutT+30s, separate source/order/ACK clocks, native book transaction time, actual funding rates and mark cashflows, eligibility uncertainty, basis repricing, partial or missed legs and unwind, collateral, margin, conservative fees and latency. No overnight/multiday carry. Until then no strategy P&L or winning edge claim.",
            "download": {"native_exchange": "binance-futures", "channel": "markPrice", "slice_minutes": 1,
                         "minute_before_target": 1, "per_slice_decoded_cap": 20_000_000,
                         "total_decoded_cap": 600_000_000, "workers": 4,
                         "counterpart_per_file_compressed_cap": 32_000_000,
                         "counterpart_total_compressed_cap": 600_000_000,
                         "authenticated": False, "paid_fallback": False},
            "sources": ["https://docs.tardis.dev/api/http-api-reference.md",
                        "https://docs.tardis.dev/historical-data-details/binance-futures.md",
                        "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Mark-Price-Stream",
                        "https://bybit-exchange.github.io/docs/v5/websocket/public/ticker",
                        "https://www.bybit.com/en/help-center/article/Funding-fee-calculation"],
            "selection_opened": False, "strategy_pnl_tested": False, "reliable_edge_established": False}
    path.write_text(json.dumps(spec, indent=2)+"\n")
    print(json.dumps({"native_slices": 24, "universe": "all historical native Binance USDT perpetual symbols", "economic_tests": 0}))


if __name__ == "__main__":
    main()
