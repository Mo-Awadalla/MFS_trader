"""Focused, network-free tests for SEC filing-event ingestion."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from data.sec_filings import (
    CIK_OVERRIDES,
    MATERIAL_FORMS,
    SecFilingDownloader,
    build_event_flag_matrix,
)


def _response(payload: object) -> Mock:
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_requires_identifying_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        SecFilingDownloader(delay_seconds=0.11)
    with pytest.raises(ValueError, match="0.11"):
        SecFilingDownloader(user_agent="Researcher research@example.com", delay_seconds=0.1)


def test_company_tickers_are_normalized_and_frozen_overrides_win(tmp_path: Path) -> None:
    session = Mock()
    session.get.return_value = _response(
        {
            "0": {"cik_str": 320193, "ticker": "aapl", "title": "Apple Inc."},
            "1": {"cik_str": 111, "ticker": "MMC", "title": "wrong historical mapping"},
        }
    )
    downloader = SecFilingDownloader(
        user_agent="Researcher research@example.com",
        cache_dir=tmp_path,
        session=session,
        delay_seconds=0.11,
        sleep=lambda _seconds: None,
    )

    mapping = downloader.company_ticker_mapping()

    assert mapping["AAPL"] == "0000320193"
    assert {symbol: mapping[symbol] for symbol in CIK_OVERRIDES} == CIK_OVERRIDES
    assert session.get.call_args.kwargs["headers"] == {
        "User-Agent": "Researcher research@example.com",
        "Accept-Encoding": "gzip, deflate",
    }
    assert json.loads((tmp_path / "raw" / "company_tickers.json").read_text())["0"]["ticker"] == "aapl"


def test_download_parses_recent_and_archive_filters_material_and_deduplicates(
    tmp_path: Path,
) -> None:
    company_tickers = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"}}
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001-24-000001", "0001-24-000002", "0001-24-000003"],
                "filingDate": ["2024-01-02", "2024-02-01", "2024-01-31"],
                "acceptanceDateTime": ["20240102163000", "2024-02-01T15:00:00Z", ""],
                "form": ["8-K", "4", "10-Q"],
                "items": ["2.02", "", ""],
                "primaryDocument": ["event.htm", "ownership.xml", "quarterly.htm"],
            },
            "files": [
                {
                    "name": "CIK0000320193-submissions-001.json",
                    "filingFrom": "2023-01-01",
                    "filingTo": "2023-12-31",
                }
            ],
        }
    }
    archive = {
        "accessionNumber": ["0001-23-000010", "0001-24-000001"],
        "filingDate": ["2023-06-01", "2024-01-02"],
        "acceptanceDateTime": ["2023-06-01T17:45:00-04:00", "20240102163000"],
        "form": ["10-K/A", "8-K"],
        "items": ["", "2.02"],
        "primaryDocument": ["annual-amendment.htm", "event.htm"],
    }
    session = Mock()
    session.get.side_effect = [
        _response(company_tickers),
        _response(submissions),
        _response(archive),
    ]
    sleep = Mock()
    downloader = SecFilingDownloader(
        user_agent="Researcher research@example.com",
        cache_dir=tmp_path,
        session=session,
        delay_seconds=0.11,
        sleep=sleep,
    )

    events = downloader.download(["aapl"], start="2023-01-01", end="2024-01-31")

    assert list(events["accession_number"]) == [
        "0001-23-000010",
        "0001-24-000001",
        "0001-24-000003",
    ]
    assert list(events["symbol"]) == ["AAPL", "AAPL", "AAPL"]
    assert set(events["form"]) <= MATERIAL_FORMS
    assert events.loc[0, "acceptance_datetime"] == pd.Timestamp("2023-06-01T21:45:00Z")
    assert events.loc[1, "acceptance_datetime"] == pd.Timestamp("2024-01-02T16:30:00Z")
    assert events.loc[2, "acceptance_datetime"] == pd.Timestamp("2024-01-31T00:00:00Z")
    assert list(events.columns) == [
        "symbol",
        "cik",
        "accession_number",
        "acceptance_datetime",
        "filing_date",
        "form",
        "items",
        "primary_document",
    ]
    assert len(session.get.call_args_list) == 3
    assert sleep.call_count == 2
    assert (tmp_path / "raw" / "CIK0000320193.json").exists()
    assert (tmp_path / "raw" / "CIK0000320193-submissions-001.json").exists()
    normalized = pd.read_parquet(tmp_path / "sec_filing_events.parquet")
    pd.testing.assert_frame_equal(normalized, events)


def test_filing_date_fallback_and_conservative_next_session_flags(tmp_path: Path) -> None:
    events = pd.DataFrame(
        {
            "symbol": ["BBB", "AAA", "AAA"],
            "cik": ["0000000002", "0000000001", "0000000001"],
            "accession_number": ["b", "a", "a-duplicate"],
            "acceptance_datetime": pd.to_datetime(
                ["2024-01-05T00:00:00Z", "2024-01-05T23:59:59Z", "2024-01-05T12:00:00Z"],
                utc=True,
            ),
        }
    )
    sessions = pd.DatetimeIndex(
        ["2024-01-05 21:00:00+00:00", "2024-01-08 21:00:00+00:00", "2024-01-09 21:00:00+00:00"]
    )

    flags = build_event_flag_matrix(events, sessions, symbols=["BBB", "AAA", "CCC"])

    assert list(flags.columns) == ["AAA", "BBB", "CCC"]
    assert flags.dtypes.tolist() == ["int8", "int8", "int8"]
    assert flags.loc[sessions[0]].sum() == 0
    assert flags.loc[sessions[1]].to_dict() == {"AAA": 1, "BBB": 1, "CCC": 0}
    assert flags.loc[sessions[2]].sum() == 0


def test_unknown_symbol_fails_before_submissions_request(tmp_path: Path) -> None:
    session = Mock()
    session.get.return_value = _response(
        {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"}}
    )
    downloader = SecFilingDownloader(
        user_agent="Researcher research@example.com",
        cache_dir=tmp_path,
        session=session,
        delay_seconds=0.11,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(KeyError, match="MISSING"):
        downloader.download(["MISSING"], start="2024-01-01", end="2024-01-31")
    assert session.get.call_count == 1


def test_shared_cik_is_downloaded_once_and_event_propagates_to_both_symbols(
    tmp_path: Path,
) -> None:
    session = Mock()
    session.get.side_effect = [
        _response(
            {
                "0": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet"},
                "1": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet"},
            }
        ),
        _response(
            {
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001-24-000001"],
                        "filingDate": ["2024-01-02"],
                        "acceptanceDateTime": ["2024-01-02T21:00:00Z"],
                        "form": ["8-K"],
                        "items": ["2.02"],
                        "primaryDocument": ["event.htm"],
                    },
                    "files": [],
                }
            }
        ),
    ]
    downloader = SecFilingDownloader(
        user_agent="Researcher research@example.com",
        cache_dir=tmp_path,
        session=session,
        delay_seconds=0.11,
        sleep=lambda _seconds: None,
    )

    events = downloader.download(["GOOG", "GOOGL"], start="2024-01-01", end="2024-01-31")

    assert set(events["symbol"]) == {"GOOG", "GOOGL"}
    assert events["accession_number"].nunique() == 1
    assert session.get.call_count == 2


def test_download_script_reads_user_agent_only_from_environment_and_never_prints_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import download_sec_filing_events as script

    secret_user_agent = "Private Name private@example.com"
    monkeypatch.setenv("SEC_USER_AGENT", secret_user_agent)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download_sec_filing_events.py",
            "--symbols",
            "aapl,MSFT",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-31",
            "--cache-dir",
            str(tmp_path),
        ],
    )
    downloader = Mock()
    downloader.download.return_value = pd.DataFrame({"symbol": ["AAPL"]})
    constructor = Mock(return_value=downloader)
    monkeypatch.setattr(script, "SecFilingDownloader", constructor)

    assert script.main() == 0

    constructor.assert_called_once_with(
        user_agent=secret_user_agent,
        cache_dir=tmp_path,
        refresh=False,
    )
    downloader.download.assert_called_once_with(
        ["AAPL", "MSFT"], start="2024-01-01", end="2024-01-31"
    )
    assert secret_user_agent not in capsys.readouterr().out
