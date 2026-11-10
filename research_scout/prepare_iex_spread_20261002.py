"""Freeze a new native-venue activity and spread admission before outcomes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/iex_spread_hft_20261002"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT / "specification.json").exists()
    supply = json.loads((ROOT / "research_scout/iex_hft_supply_20260930/specification.json").read_text())
    dates = sorted({p.replace("\\", "/").split("/")[-2] for p in supply["source_files"]})
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis": "Native IEX displayed spread capture in active cash securities, fixed one minute after the regular open; long entry, passive target and a mandatory sub-30-second inventory deadline if a lead survives screening.",
        "dates": dates,
        "selection": "All 24 dates of the pre-existing 2023 IEX development cohort, independent of returns. All native alphabetic 1-5 character symbols; exclude explicitly flagged test securities. Confirm stock/ETF identity of each selected symbol before economic replay.",
        "decision": "09:31:00 America/New_York on each fixed date. Information cutoff 250ms earlier. Full native sequence and byte offset continuity from start, no future reference, original event/send/capture clocks retained.",
        "quote": "Latest maintained TOPS state with flags zero, H=T and O=N; no arbitrary quote-age expiry when the complete feed maintains the book. Both prices in [5,1000] USD on whole-cent grid; positive sizes; bid<ask; spread<=50bp; at least 2000 USD on each touch.",
        "activity": "At least ten native positive-size trades and 10000 USD during the preceding 30 seconds of native event time, received strictly before cutoff; exclude extended-hours, trade-through-exempt and single-price-cross flags (0x58), plus causally known trade breaks. Latest eligible received trade price must lie within current quote.",
        "size": "Integer min(floor(10000 USD/ask), floor(10% current bid shares), floor(10% current ask shares)), fixed before future quotes.",
        "costs": "Two legs each max(1 USD,0.005 USD/share), adverse 1bp each leg, sale levy 0.00003 times sale notional plus 0.000166 USD/share. No rebates.",
        "budget": "Current ask-minus-bid dollars at causal size less all stated costs, at least 2bp of midpoint notional. This is a displayed spread budget, NOT a return or prediction of a fill.",
        "ranking": "Highest quoted net budget bps, then highest prior trade notional, then symbol ascending. One selected candidate per day. No re-ranking on future profits.",
        "acquisition": "Use free HIST TOPS prefixes only. Existing 32MiB Jan11 prefix first. Other dates start at 32MiB and extend by 32MiB only until fixed cutoff is covered, capped 256MiB. Preserve all prefix hashes and failure/coverage states; never call an incomplete prefix a zero-event day.",
        "economic_implementations_executed": 0,
        "next_gate": "Freeze exact passive fill hypotheses, acknowledgement/cancel clocks and forced-exit mechanics before any future-price test. A positive proxy requires conservative queue/acceptance/source-clock verification and untouched temporal replication.",
        "source_metadata_sha256": digest(ROOT / "research_scout/iex_units_hft_20261002/hist_metadata.json"),
        "implementation_sha256": digest(ROOT / "research/iex_spread_supply.py"),
        "decoder_sha256": digest(ROOT / "research/iex_native_prefix.py"),
    }
    (OUT / "specification.json").write_text(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"dates": len(dates), "specification_sha256": digest(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
