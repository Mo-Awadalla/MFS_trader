"""Freeze the displayed-depth variant of the already specified short-hold probe."""

import json
from datetime import UTC, datetime

from research_scout.prepare_iex_deep_20261002 import OUT, PARENT, ROOT, digest


def main():
    results = json.loads((OUT / "screen_results.json").read_text())
    audit = json.loads((OUT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == digest(OUT / "screen_results.json")
    prior = json.loads((PARENT / "price_probe_v1/specification.json").read_text())
    identities = dict(prior["instrument_identities"])
    identities.update({
        "TQQQ": {"classification": "ProShares UltraPro QQQ ETF", "primary_source": "https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq"},
        "HUM": {"classification": "Humana common stock", "primary_source": "https://www.sec.gov/Archives/edgar/data/49071/000004907124000012/hum-20231231.htm"},
        "ADBE": {"classification": "Adobe common stock", "primary_source": "https://www.sec.gov/Archives/edgar/data/796343/000079634324000006/adbe-20231201.htm"},
    })
    spec = {k: prior[k] for k in ("policy", "timing", "order_type", "post_only_history_source",
                                 "entry_proxy", "exit_proxy", "fill_models", "strict_model", "eligible_trades",
                                 "costs", "cases", "acquisition", "portfolio_scope", "promotion")}
    spec.update(
        created_at_utc=datetime.now(UTC).isoformat(),
        dates=json.loads((OUT / "specification.json").read_text())["dates"],
        parent_screen_sha256=digest(OUT / "screen_results.json"),
        parent_audit_sha256=digest(OUT / "independent_verification.json"),
        prior_tops_policy_sha256=digest(PARENT / "price_probe_v1/specification.json"),
        selected_events=results["selected"], unknown_admission_dates=[r["date"] for r in results["errors"]],
        instrument_identities={s: identities[s] for s in sorted({e["symbol"] for e in results["selected"]})},
        economic_policy_variant_count=1,
        variant="Same order timings, costs and touch/strict-through price proxies, but DEEP-derived displayed best prices/sizes determine causal ranking, quantity and execution reference. Count this changed signal-data variant as another exploratory economic configuration.",
        quote_reference="Signal quotes are committed atomic DEEP books in capture order, before d-250ms. For venue-clock execution, order selected-symbol price-level updates by exact native event time then native sequence, commit only at EventFlags1, and collapse equal-event-time states to their final state. Do not use intermediate states. No Q/H/O at exact order arrival is resolved by tie-breaking. Require a subsequent complete native quote beyond a forced reference. Preserve original levels and derived quotes.",
        depth_limit="Future aggressive/forced reference fills still ignore execution depth under the inherited conditional probe. Book levels are retained for review, not used to increase order size. A positive result is never promoted without actual depth, queue, NBBO and acceptance modeling.",
        source_incomplete_scope="2023-11-29 DEEP starts at sequence45296, missing the opening book history. It remains an unknown admission and unknown full-calendar cash outcome in every case. Known no-candidate dates count as no-signal, not missing. Observed selected-event totals must be separately labeled.",
        selection_scope="2023 exploratory development after prior TOPS result; no temporal holdout or reliability claim. Source classification only, no company financial performance enters selection.",
        source_implementation_sha256=digest(ROOT / "research/iex_deep_probe_source.py"),
        deep_book_sha256=digest(ROOT / "research/iex_deep_supply.py"),
        packet_decoder_sha256=digest(ROOT / "research/iex_native_prefix.py"),
        price_proxy_sha256=digest(ROOT / "research/iex_spread_proxy.py"),
        aggregator_sha256=digest(ROOT / "research_scout/run_iex_spread_probe_20261002.py"),
    )
    folder = OUT / "price_probe_v1"
    folder.mkdir(exist_ok=True)
    path = folder / "specification.json"
    assert not path.exists()
    path.write_text(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"path": str(path), "sha256": digest(path), "selected_events": len(results["selected"])}))


if __name__ == "__main__":
    main()
