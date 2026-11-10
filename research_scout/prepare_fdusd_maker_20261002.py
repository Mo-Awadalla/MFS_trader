"""Freeze a necessary spread/depth screen in published maker-fee markets."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_spot_perp_20261002 import ROOT, sha

OUT = ROOT / "research_scout/fdusd_maker_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    roots = [ROOT / "research_scout/spot_perp_hft_20261002",
             ROOT / "research_scout/spot_perp_clock_hft_20261002"]
    manifests = [roots[0] / "spot_manifest.json", roots[1] / "source_manifest.json"]
    sources = []
    audits = []
    for directory, manifest_path in zip(roots, manifests, strict=True):
        manifest = json.loads(manifest_path.read_text())
        audit_path = directory / "independent_verification.json"
        audit = json.loads(audit_path.read_text())
        assert manifest["complete"] and audit["verified"]
        audits.append({"path": str(audit_path.relative_to(ROOT)), "sha256": sha(audit_path)})
        for source in manifest["files"]:
            if source.get("venue", "spot") != "spot":
                continue
            offset = source.get("offset", source["params"]["offset"])
            sources.append({**source, "offset": offset,
                            "parent_manifest": str(manifest_path.relative_to(ROOT)),
                            "parent_manifest_sha256": sha(manifest_path)})
    sources.sort(key=lambda r: (r["date"], r["offset"]))
    assert len(sources) == len({(r["date"], r["offset"]) for r in sources}) == 60
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Passive HFT spread supply under publicly documented FDUSD maker-fee terms",
        "relationship": "A dependent market/fee-structure change after failed perpetual passive and cross-market studies. Existing FDUSD prices have not been used to select this screen's symbols or thresholds. Source minutes were acquired in prior studies; this is not a globally pristine sample.",
        "universe": "All contemporaneously recorded Binance spot symbols ending FDUSD, discovered from native streams, without a current-survivor list. General 2023 and May 2024 exchange notices state zero maker fees on FDUSD pairs; pair-specific listing/lifecycle and fee eligibility must still be checked before any execution study. FDUSDUSDT is recorded separately for later quote-currency valuation, not presumed one US dollar.",
        "coverage": "The existing sixty complete first-of-month 2024 spot minutes: 00:00, 06:00, 09:00, 12:00 and 18:00 UTC on each of twelve dates. No new acquisition, date/time selection or future-return labels.",
        "causal_grid": "Fifty one-second decisions from second 10 through second 59 inclusive. Use native full BBO updates captured strictly before decision minus 250ms. A disconnect clears books and id histories; exact duplicates never refresh age; conflicting/reversed ids poison the state until a strictly higher id. No invented spot matching timestamp.",
        "valid_state": "Finite positive bid, ask and both quantities, bid<ask, valid update sequence, capture age at the actual decision <=5 seconds. This is a deliberate signal freshness condition, not a claim that older standing quotes have expired.",
        "per_grid_supply": "Relative spread from 8 through 100bp inclusive and both displayed touch notionals >=2000 FDUSD. This is necessary supply for a later <=200 FDUSD long-only spot order at <=10% displayed touch; it does not establish a queue fill or an order grid. All values stay in FDUSD until an explicit FX/cash calculation.",
        "window_supply": "At least forty valid grids and thirty grids meeting spread/depth supply, out of fifty. Retain every qualifying symbol/window, with no return ranking or top-N selection. A hypothetical strategy may begin only after the screening minute finishes.",
        "cost_budget": "Although the cited maker fee is zero, budget a 1bp fee reserve plus 1bp adverse allowance on each of two maker executions. Also report the doubled maker-fee-reserve and doubled adverse-allowance budgets. The 8bp minimum leaves approximately 2bp under either separate stress before queue losses. Report a flat-price emergency sale at a 10bp taker fee plus 1bp adverse allowance, after the 1bp+1bp maker entry costs. Never assume zero taker fees or VIP eligibility.",
        "budget_equations": "For one base-asset unit, hypothetical passive round trip buys at bid b and sells at ask a: a-b-(b+a)*0.0002. Each separate doubled-cost stress uses 0.0003 instead. Hypothetical same-bid forced exit loses b*(0.0002+0.0011). Divide by b for bp values. If passive net is positive, the simplified minimum two-maker-exit probability is forced_loss/(forced_loss+passive_net). This excludes price movement, queue uncertainty, FX conversion and inventory constraints and is not a return forecast.",
        "next_stage": "Only if necessary supply survives: freeze a native trade/depth queue replay before any subsequent prices, with complete displayed queue ahead, no assumed cancellation advancement, explicit partial base-asset inventory and actual fee-asset deductions, delayed arrival/cancellation, forced taker cleanup, at most thirty-second planned inventory and 15-second central hold. Include FDUSD/USDT conversion and terminal inventory valuation before any account outperformance claim. If no supply survives, stop this branch at the screen.",
        "primary_sources": [
            "https://www.binance.com/en/support/announcement/detail/0e4155610e6f4e8bbaaa332545dc43a2",
            "https://www.binance.com/en/support/announcement/detail/f7c6bd7931db40aa83931556b5a43565",
            "https://www.binance.com/en/support/announcement/detail/3d8514bbc817423eba52fb23483bcbed",
            "https://www.binance.com/en-TR/support/announcement/detail/4856a6d4e4014d4e8a5a29ec5fb44857"],
        "sources": sources, "parent_source_audits": audits,
        "economic_implementations": 0, "future_returns_evaluated": False,
        "actual_execution_verified": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"cached_spot_minutes": 60, "universe": "all contemporaneous FDUSD spot symbols",
                      "new_downloads": 0, "future_returns_evaluated": False}))


if __name__ == "__main__":
    main()
