from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from scripts.acquire_etf_tsm_sip_inputs import (
    _atomic_json,
    _bars,
    _pages,
    calendar_session_close_utc,
    completed_calendar_entries,
)


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def test_pages_follows_token_and_bars_keeps_adjustments_separate() -> None:
    calls: list[dict[str, str]] = []

    def get(url: str, **kwargs: object) -> _Response:
        params = kwargs["params"]
        assert isinstance(params, dict)
        calls.append(params)
        if len(calls) == 1:
            return _Response({"bars": {"SPY": [{"t": "2024-01-01T00:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2, "v": 3}]}, "next_page_token": "next"})
        return _Response({"bars": {"SPY": [{"t": "2024-01-02T00:00:00Z", "o": 2, "h": 3, "l": 2, "c": 3, "v": 4}]}})

    import scripts.acquire_etf_tsm_sip_inputs as subject

    original = subject.requests.get
    subject.requests.get = get
    try:
        pages = _pages("https://example.test", {"adjustment": "raw"}, {"x": "y"})
    finally:
        subject.requests.get = original
    frame = _bars(pages, "SPY")
    assert len(frame) == 2 and calls[1]["page_token"] == "next"
    assert frame.index.equals(pd.DatetimeIndex(["2024-01-01", "2024-01-02"], tz="UTC"))


def test_atomic_json_rejects_existing_output(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    _atomic_json(path, {"raw": True})
    with pytest.raises(FileExistsError):
        _atomic_json(path, {"adjusted": True})
    assert json.loads(path.read_text()) == {"raw": True}


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"date": "2026-01-02", "close": "16:00"}, "2026-01-02T21:00:00+00:00"),
        ({"date": "2026-06-01", "close": "16:00"}, "2026-06-01T20:00:00+00:00"),
        ({"date": "2026-11-27", "close": "13:00"}, "2026-11-27T18:00:00+00:00"),
    ],
)
def test_calendar_session_close_uses_date_new_york_timezone_and_early_close(
    entry: dict[str, str], expected: str
) -> None:
    assert calendar_session_close_utc(entry) == expected


def test_completed_calendar_entries_excludes_partial_current_session() -> None:
    entries = [
        {"date": "2026-09-03", "close": "16:00"},
        {"date": "2026-09-04", "close": "16:00"},
        {"date": "2026-09-05", "close": "16:00"},
    ]
    assert completed_calendar_entries(entries, "2026-09-03", "2026-09-05", "2026-09-04") == entries[:2]


class _MainResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


def _bar_payload() -> dict[str, object]:
    bars = {
        symbol: [{"t": "2024-01-02T00:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2, "v": 3}]
        for symbol in ("DBC", "GLD", "IEF", "IWM", "QQQ", "SHY", "SPY")
    }
    return {"bars": bars}


def _run_main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dividend: dict[str, object]) -> dict[str, object]:
    import scripts.acquire_etf_tsm_sip_inputs as subject

    monkeypatch.setattr(subject, "ROOT", tmp_path)
    monkeypatch.setattr(subject, "CUTOFF", "2024-01-02")
    monkeypatch.setattr(
        subject,
        "dotenv_values",
        lambda _: {"ALPACA_API_KEY": "key", "ALPACA_API_SECRET": "secret"},
    )

    def get(url: str, **_: object) -> _MainResponse:
        if url == subject.DATA_URL:
            return _MainResponse(_bar_payload())
        if url == subject.CALENDAR_URL:
            return _MainResponse([{"date": "2024-01-02", "close": "16:00"}])
        if url == subject.CA_URL:
            return _MainResponse({"corporate_actions": {"cash_dividends": [dividend]}})
        if "/v2/assets/" in url:
            return _MainResponse({"tradable": True, "fractionable": True})
        raise AssertionError(url)

    monkeypatch.setattr(subject.requests, "get", get)
    result = subject.main(["--acquire", "--env-file", str(tmp_path / ".env"), "--snapshot-id", "test-snapshot"])
    report = json.loads((tmp_path / "docs/reports/etf_campaign_inputs/test-snapshot/manifest.json").read_text())
    report["exit_code"] = result
    return report


def test_main_blocks_missing_payable_date_and_records_missing_record_diagnostic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = _run_main(
        monkeypatch,
        tmp_path,
        {"id": "event", "symbol": "SPY", "ex_date": "2024-01-02", "payable_date": None, "record_date": None},
    )
    assert report["exit_code"] == 2
    assert report["status"] == "failed"
    assert report["failures"] == ["corporate_actions: 1 cash dividends lack payable_date"]
    assert len(report["corporate_action_coverage"]["cash_dividend_missing_record_date"]) == 1


def test_main_keeps_missing_record_date_as_diagnostic_not_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = _run_main(
        monkeypatch,
        tmp_path,
        {"id": "event", "symbol": "SPY", "ex_date": "2024-01-02", "payable_date": "2024-01-05", "record_date": None},
    )
    assert report["exit_code"] == 0
    assert report["status"] == "passed"
    assert report["failures"] == []
    assert len(report["corporate_action_coverage"]["cash_dividend_missing_payable_date"]) == 0
    assert len(report["corporate_action_coverage"]["cash_dividend_missing_record_date"]) == 1
