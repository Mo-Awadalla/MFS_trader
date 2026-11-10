"""Finish the authorized one-off pipeline after the source download completes."""

import time

from research_scout import report_v98_20260907 as report
from research_scout import v98_backtest_20260907 as backtest
from research_scout import v98_earnings_answers_20260907 as source
from research_scout import v98_market_data_20260907 as market
from research_scout import v98_prefetch_training_20260907 as prefetch


def main():
    deadline = time.monotonic() + 1800
    while not (source.OUT / "transcript_retrieval.json").exists():
        if time.monotonic() > deadline:
            raise TimeoutError("Source collection did not finish within the bounded wait")
        time.sleep(1)
    if len(source.read("transcript_retrieval.json")) != len(source.read("source_manifest.json")):
        raise ValueError("Final source collection is incomplete")
    effective = source.read("implementation_freeze_repair_1.json")
    if not all(source.sha((source.ROOT/p).read_bytes()) == h for p, h in effective["hashes"].items()):
        raise ValueError("Effective pre-outcome implementation freeze changed")
    source.parse_sources()
    market.plan()
    prefetch.adopt()
    market.collect()
    market.normalize()
    backtest.panel()
    backtest.predictions()
    backtest.evaluate_all()
    report.main()


if __name__ == "__main__":
    main()
