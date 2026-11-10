"""Freeze the new activity-selection variant and reuse exact previously audited outcomes."""

import json
from datetime import UTC, datetime

from research_scout.prepare_iex_flow_20261002 import OUT, PARENT, ROOT, digest


def main():
    flow = json.loads((OUT / "screen_results.json").read_text())
    audit = json.loads((OUT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == digest(OUT / "screen_results.json")
    prior_folder = PARENT / "price_probe_v1"
    prior = json.loads((prior_folder / "specification.json").read_text())
    prior_audit = json.loads((prior_folder / "independent_verification.json").read_text())
    assert prior_audit["verified"] and prior_audit["results_sha256"] == digest(prior_folder / "results.json")
    spec = {k: prior[k] for k in ("policy", "timing", "order_type", "post_only_history_source", "entry_proxy",
                                 "exit_proxy", "fill_models", "strict_model", "eligible_trades", "costs", "cases",
                                 "portfolio_scope", "promotion", "quote_reference", "depth_limit", "source_incomplete_scope")}
    spec.update(
        created_at_utc=datetime.now(UTC).isoformat(),
        selected_events=flow["selected"], dates=prior["dates"], unknown_admission_dates=flow["unknown_admission_dates"],
        parent_flow_sha256=digest(OUT / "screen_results.json"), parent_flow_audit_sha256=digest(OUT / "independent_verification.json"),
        prior_specification_sha256=digest(prior_folder / "specification.json"),
        prior_results_sha256=digest(prior_folder / "results.json"), prior_audit_sha256=digest(prior_folder / "independent_verification.json"),
        instrument_identities={s: prior["instrument_identities"][s] for s in {e["symbol"] for e in flow["selected"]}},
        variant="Causal two-sided activity changes selection only. Order policy, quantity formula, conservative fees and all timing cases remain fixed. This is one additional exploratory economic configuration.",
        reuse="If the full original candidate/event and policy are exactly identical to a prior independently audited event, reuse its immutable ten outcomes and provenance hashes. Replay only newly selected events. Reused outcomes are not independent validation.",
        acquisition="Use the existing same-date, generation-pinned DEEP probe prefix covering the fixed decision+35s endpoint. No new data, no paid API. Preserve original hashes and all unknown dates.",
        implementation_sha256=digest(ROOT / "research_scout/run_iex_flow_probe_20261002.py"),
        source_implementation_sha256=digest(ROOT / "research/iex_deep_probe_source.py"),
        deep_book_sha256=digest(ROOT / "research/iex_deep_supply.py"),
        packet_decoder_sha256=digest(ROOT / "research/iex_native_prefix.py"),
        price_proxy_sha256=digest(ROOT / "research/iex_spread_proxy.py"),
        aggregator_sha256=digest(ROOT / "research_scout/run_iex_spread_probe_20261002.py"),
        economic_configurations_executed=0, actual_execution_verified=False, reliable_edge_established=False,
    )
    folder = OUT / "price_probe_v1"
    folder.mkdir(exist_ok=True)
    path = folder / "specification.json"
    assert not path.exists()
    path.write_text(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"path": str(path), "sha256": digest(path), "events": len(flow["selected"])}))


if __name__ == "__main__":
    main()
