"""Freeze causal depth admission before reading any DEEP candidate outcomes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/iex_deep_hft_20261002"
PARENT = ROOT / "research_scout/iex_spread_hft_20261002"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    parent = json.loads((PARENT / "specification.json").read_text())
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis": "Published protected TOPS prices can omit better-priced displayed odd lots. Reconstruct the actual displayed best price and its size from DEEP, then apply the same causal activity and spread-budget filters to find economically plausible seconds-long stock/ETF opportunities.",
        "dates": parent["dates"],
        "decision_time": "09:31:00 America/New_York; only messages captured before decision minus250ms and native event/send not after that cutoff",
        "book": "DEEP protocol0x8004; stream must start at sequence1 byteoffset0 and remain contiguous. Prices integer1e-4USD; quantities shares; clocks int64ns. Maintain aggregate bid/ask levels; size0 removes. Commit BBO only at final PLU EventFlags1, never intermediate flags0. A symbol mid-transaction at cutoff is ineligible. Require matching event timestamp within an atomic transaction; native clock monotonicity only within price-update message type. Unsupported states fail.",
        "signal": "Use unchanged parent eligibility on true DEEP displayed best bid/ask and respective level sizes: alphabetic1-5char, non-test, T/N statuses, positive uncrossed $5-$1000 cent prices, <=50bp spread, >=$2000 each touch, >=10 eligible prints and$10000 prior30s native trade notional, last eligible trade inside BBO. Quantity=min(floor10000/ask),floor10%bidqty,floor10%askqty). Spread budget after costs>=2bp.",
        "costs": "Two commissions max($1,$.005/share),1bp adverse each leg, sell levy .00003 notional+.000166/share; no rebates. Budget is not realized profit.",
        "rank": "Descending net displayed budgetbp, descending prior trade notional, ascending symbol; one candidate perdate, same as parent",
        "comparison": "For all original TOPS candidates report DEEP levels and protected aggregation assuming100-share round lot, solely as a diagnostic. Exact historical round lot and different feed publication timing must be checked before claiming full TOPS/DEEP identity.",
        "acquisition": "Free generation-pinned public IEX HIST DEEP1.0 prefixes,32MiB chunks only until fixed causal cutoff coverage or256MiB cap. Preserve immutable chunks, hashes and Content-Range. No2024+data, no future price response, no paid API.",
        "limitations": "DEEP lacks individual queue and hidden liquidity; it does not supply consolidated NBBO. Stock/ETF classification and historical order constraints remain required for economic replay. Discovery after parent negative price probe is exploratory, not untouched validation.",
        "parent_specification_sha256": digest(PARENT / "specification.json"),
        "parent_results_sha256": digest(PARENT / "screen_results.json"),
        "source_metadata_sha256": digest(ROOT / "research_scout/iex_units_hft_20261002/hist_metadata.json"),
        "implementation_sha256": digest(ROOT / "research/iex_deep_supply.py"),
        "packet_decoder_sha256": digest(ROOT / "research/iex_native_prefix.py"),
        "eligibility_sha256": digest(ROOT / "research/iex_spread_supply.py"),
        "primary_sources": [
            "https://www.sec.gov/rules/sro/iex/2021/34-90933.pdf",
            "https://assets-global.website-files.com/635ad1b3d188c10deb1ebcba/63bd4a1cb0d2bef3cbf36bcc_IEX%20DEEP%20Specification%20v1.08.pdf",
            "https://iextrading.com/trading/alerts/2017/011/",
        ],
        "attribution": "Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical Data Terms of Use.",
        "terms": "https://www.iex.io/legal/hist-data-terms",
        "economic_configurations_executed": 0, "returns_calculated": False,
        "actual_execution_verified": False, "reliable_edge_established": False,
    }
    path = OUT / "specification.json"
    assert not path.exists()
    path.write_text(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"path": str(path), "sha256": digest(path), "dates": len(spec["dates"])}))


if __name__ == "__main__":
    main()
