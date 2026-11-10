"""Freeze one short-hold limit-order policy and explicitly conditional fill proxies."""

import json
from datetime import UTC, datetime

from research_scout.prepare_iex_spread_20261002 import OUT, ROOT, digest


def main():
    result = json.loads((OUT / "screen_results.json").read_text())
    audit = json.loads((OUT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["source_results_sha256"] == digest(OUT / "screen_results.json")
    identities = {
        "DDOG": ("Datadog Class A common stock", "https://www.sec.gov/Archives/edgar/data/1561550/000156155023000055/ddog-20230930.htm"),
        "LMT": ("Lockheed Martin common stock", "https://www.sec.gov/Archives/edgar/data/936468/000093646824000010/lmt-20231231.htm"),
        "LRCX": ("Lam Research common stock", "https://www.sec.gov/Archives/edgar/data/707549/000070754923000102/lrcx-20230625.htm"),
        "FERG": ("Ferguson plc ordinary shares", "https://www.sec.gov/Archives/edgar/data/1832433/000183243323000066/ferg-20230731.htm"),
        "PH": ("Parker-Hannifin common shares", "https://www.sec.gov/Archives/edgar/data/76334/000007633423000028/ph-20230331.htm"),
        "BABA": ("Alibaba American depositary shares", "https://www.sec.gov/Archives/edgar/data/1577552/000095017023033752/baba-20230331.htm"),
        "FDX": ("FedEx common stock", "https://www.sec.gov/Archives/edgar/data/1048911/000095017023033201/fdx-20230531.htm"),
        "BDX": ("Becton Dickinson common stock", "https://www.sec.gov/Archives/edgar/data/10795/000001079523000098/bdx-20230930.htm"),
        "V": ("Visa Class A common stock", "https://www.sec.gov/Archives/edgar/data/1403161/000119312523290300/d541456dars.pdf"),
        "CRM": ("Salesforce common stock", "https://www.sec.gov/Archives/edgar/data/1108524/000110852423000011/crm-20230131.htm"),
        "CME": ("CME Group Class A common stock", "https://www.sec.gov/Archives/edgar/data/1156375/000115637524000010/cme-20231231.htm"),
        "TSLA": ("Tesla common stock", "https://www.sec.gov/Archives/edgar/data/1318605/000162828024002390/tsla-20231231.htm"),
        "META": ("Meta Platforms Class A common stock", "https://www.sec.gov/Archives/edgar/data/1326801/000132680123000103/meta-20230930.htm"),
        "RBLX": ("Roblox Class A common stock", "https://www.sec.gov/Archives/edgar/data/1315098/000131509824000026/rblx-20231231.htm"),
        "SPY": ("SPDR S&P 500 ETF Trust", "https://www.sec.gov/Archives/edgar/data/884394/000119312523017928/d449477d497.htm"),
        "ARKK": ("ARK Innovation ETF", "https://www.ark-funds.com/funds/arkk"),
        "MBB": ("iShares MBS ETF", "https://www.ishares.com/us/products/239465/ishares-mbs-etf"),
        "XLU": ("Utilities Select Sector SPDR ETF", "https://www.ssga.com/us/en/institutional/etfs/state-street-utilities-select-sector-spdr-etf-xlu"),
        "AAPL": ("Apple common stock", "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"),
        "ALB": ("Albemarle common stock", "https://www.sec.gov/Archives/edgar/data/915913/000091591323000166/alb-20230630.htm"),
    }
    assert {r["symbol"] for r in result["selected"]} == set(identities)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "parent_screen_sha256": digest(OUT / "screen_results.json"),
        "parent_audit_sha256": digest(OUT / "independent_verification.json"),
        "selected_events": result["selected"],
        "instrument_identities": {s: {"classification": c, "primary_source": u} for s, (c, u) in identities.items()},
        "identity_scope": "Confirm stock/ETF classification after causal ranking; no company financial results or future returns enter selection. This is not a full corporate-action or eligibility audit.",
        "economic_policy_count": 1,
        "policy": "Buy the original signal bid with fixed causal quantity; cancel remainder at local decision+5s; after cancel acknowledgement, offer bought shares at the original signal ask; cancel target at local decision+15s; wait for acknowledgement, then market-sell residual inventory. Long only; one signal per date.",
        "timing": "One-way delay L. Entry arrival d+50ms+L. Entry cancellation arrival d+5s+L; acknowledgement d+5s+2L. Target sell arrival d+5.05s+3L. Target cancellation arrival d+15s+L; acknowledgement d+15s+2L. Forced residual sale arrival d+15.05s+3L. Maximum planned exposure under 30 seconds in every case.",
        "order_type": "Ordinary non-routable limits. Post Only was implemented February 15, 2024, so its protections are not assumed in 2023. Reject/reprice/hidden liquidity and NBBO price-slide behavior are unresolved in this proxy and must be verified for promotion.",
        "post_only_history_source": "https://www.sec.gov/files/rules/sro/iex/2024/34-99471.pdf",
        "entry_proxy": "At arrival, if valid observed venue ask<=buy limit, assume the intended quantity fills at the limit, ignoring future depth. Otherwise allocate sequential eligible native prints at/below limit, up to intended quantity, strictly between arrival and cancel arrival. Preserve partial quantity. No queue priority assumed to be proven.",
        "exit_proxy": "At target arrival, if valid observed venue bid>=sell limit, assume all inventory fills at the limit. Otherwise allocate eligible native prints at/above limit until target cancellation. Force remaining shares at maintained valid observed bid at forced-sale arrival, ignoring execution depth. Charge separate commissions on partial target and forced sell orders.",
        "fill_models": ["touch", "strict_trade_through"],
        "strict_model": "Change passive buy print price<=limit to <limit and sell >=limit to >limit. This removes equality/queue claims but is still a conditional price proxy; acceptance, repricing and private fills remain unverified.",
        "eligible_trades": "Native T with positive price/size and flags & 0x58 ==0. Ignore causally known broken prints; any break referring to a used fill by the fixed source endpoint makes that case unknown. Prints at exact order boundaries make the case unknown, rather than assigned by tie-breaking.",
        "quote_reference": "For venue replay use last Q at/before native event time of arrival, never an older valid substitute. Maintain H/O status in event time. A Q/H/O exactly at an order arrival makes its state unknown because venue ordering is unresolved. Require at least one subsequent quote beyond the forced-exit timestamp to confirm the selected-symbol prefix covers the reference. Invalid state, missing source or halt leaves net unknown.",
        "costs": "Per nonempty order max(1 USD,0.005 USD per executed share), 1bp adverse each actual bought/sold notional, 0.00003 sell-notional plus0.000166 per sold share. Costs apply also to aggressive proxy fills; zero rebates.",
        "cases": [
            {"name": "base", "latency_ns": 1_000_000_000, "fee_factor": 1, "adverse_factor": 1},
            {"name": "fees_2x", "latency_ns": 1_000_000_000, "fee_factor": 2, "adverse_factor": 1},
            {"name": "adverse_2x", "latency_ns": 1_000_000_000, "fee_factor": 1, "adverse_factor": 2},
            {"name": "latency_250ms", "latency_ns": 250_000_000, "fee_factor": 1, "adverse_factor": 1},
            {"name": "latency_3s", "latency_ns": 3_000_000_000, "fee_factor": 1, "adverse_factor": 1},
        ],
        "acquisition": "Extend existing pinned native prefixes only to a fixed decision+35-second publication endpoint, capped 256MiB total per date; no outcome-based extension. Only selected symbols need parsing. Never modify original screen sources or hashes.",
        "portfolio_scope": "Independent 10000 USD event budgets, no compounding or capital-return claim. All no-fill classifications conditional on the proxy assumptions. Unknown inventory/cash is not zero.",
        "promotion": "Any positive sum is exploratory. Require native source and cash audit, actual historical order-acceptance/price-sliding constraints, queue and hidden-liquidity uncertainty, clock sensitivity, execution depth, cost/latency stability, temporal holdout and concentration/multiple-search tests before claiming an edge.",
        "implementation_sha256": digest(ROOT / "research/iex_spread_proxy.py"),
        "decoder_sha256": digest(ROOT / "research/iex_native_prefix.py"),
    }
    folder = OUT / "price_probe_v1"
    folder.mkdir(exist_ok=True)
    path = folder / "specification.json"
    assert not path.exists()
    path.write_text(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"path": str(path), "sha256": digest(path), "selected_events": len(result["selected"])}))


if __name__ == "__main__":
    main()
