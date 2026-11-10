import json

import exchange_calendars as xc
import pandas as pd

from research_scout import new_information_tests_20260907 as study


def test_processing_buffer_and_early_close_are_respected():
    schedule = xc.get_calendar("XNYS", start="2021-11-01", end="2021-12-01").schedule
    assert study.first_full_session("2021-11-24T21:01:00Z", schedule) == "2021-11-29"
    assert study.first_full_session("2021-11-29T14:00:00Z", schedule) == "2021-11-30"
    assert study.first_full_session("2021-11-29T13:59:00Z", schedule) == "2021-11-29"


def test_report_lag_uses_prior_same_period_and_excludes_ambiguous_originals(tmp_path, monkeypatch):
    metadata = tmp_path / "events.parquet"
    pd.DataFrame({"symbol": ["MOCK"], "cik": ["0000001234"]}).to_parquet(metadata)
    blob = {
        "form": ["10-Q"] * 5,
        "reportDate": ["2019-03-31", "2020-03-31", "2021-03-31", "2021-03-31", "2026-03-31"],
        "acceptanceDateTime": [
            "2019-05-02T20:01:00Z",
            "2020-04-24T20:01:00Z",
            "2021-04-24T20:01:00Z",
            "2021-04-25T20:01:00Z",
            "2026-04-01T20:01:00Z",
        ],
        "accessionNumber": ["a", "b", "c", "d", "e"],
    }
    (tmp_path / "CIK0000001234.json").write_text(json.dumps({"filings": {"recent": blob}}))
    monkeypatch.setattr(study, "RAW", tmp_path)
    monkeypatch.setattr(study, "EVENTS", metadata)
    monkeypatch.setattr(study, "ROOT", tmp_path)
    events, exclusions = study.reporting_events(["MOCK"])
    assert len(events) == 1
    assert events[0]["acceleration_days"] == 8 and events[0]["selected"]
    assert events[0]["prior_accession"] == "a"
    assert sum(r["reason"] == "ambiguous_original_fiscal_report" for r in exclusions) == 2
    assert not any(r["accession"] == "e" for r in events + exclusions)
