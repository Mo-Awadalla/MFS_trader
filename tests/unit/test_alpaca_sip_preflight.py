"""Tests for the read-only, SIP-only Alpaca entitlement preflight."""

from __future__ import annotations

import json

import pytest
import responses

from config.loader import load_config
from scripts.preflight_alpaca_sip_entitlement import (
    ETF_SYMBOLS,
    HISTORICAL_BARS_ENDPOINT,
    LATEST_BARS_ENDPOINT,
    check_sip_entitlement,
    write_immutable_json,
)


def _historical_bars_payload() -> dict[str, object]:
    return {
        "bars": {
            symbol: [
                {
                    "t": "2026-08-28T20:00:00Z",
                    "o": 100.0,
                    "h": 101.0,
                    "l": 99.0,
                    "c": 100.5,
                }
            ]
            for symbol in ETF_SYMBOLS
        }
    }


def _sip_config(tmp_path):
    path = tmp_path / "sip.toml"
    path.write_text(
        """
mode = "research"
[[brokers]]
name = "alpaca"
asset_class = "equity"
api_key_env = "TEST_ALPACA_KEY"
api_secret_env = "TEST_ALPACA_SECRET"
base_url = "https://paper-api.alpaca.markets"

[[data]]
symbols = ["SPY"]
asset_class = "equity"
feed = "sip"
adjustment = "split_dividend"
""",
        encoding="utf-8",
    )
    return path, load_config(path, load_env=False)


def test_sip_preflight_requires_credentials_without_request(tmp_path) -> None:
    path, config = _sip_config(tmp_path)
    calls = 0

    def request_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("must not make a request without credentials")

    evidence = check_sip_entitlement(
        config_path=path,
        config=config,
        api_key="",
        api_secret="",
        request_get=request_get,
        checked_at="2026-09-05T21:12:16+00:00",
    )

    assert calls == 0
    assert evidence["outcome"] == "credentials_unavailable"
    assert evidence["http"]["status_code"] is None


@responses.activate
def test_sip_preflight_403_has_no_feed_fallback(tmp_path) -> None:
    path, config = _sip_config(tmp_path)
    responses.add(
        responses.GET,
        LATEST_BARS_ENDPOINT,
        status=403,
        json={"message": "subscription does not permit querying recent SIP data"},
    )
    responses.add(responses.GET, HISTORICAL_BARS_ENDPOINT, status=200, json=_historical_bars_payload())

    evidence = check_sip_entitlement(
        config_path=path,
        config=config,
        api_key="test-key",
        api_secret="test-secret",
    )

    assert evidence["available"] is True
    assert evidence["outcome"] == "available"
    assert evidence["feed"] == "sip"
    assert evidence["http"]["status_code"] == 200
    assert evidence["latest_sip_access"]["http"]["status_code"] == 403
    assert "subscription does not permit" in evidence["latest_sip_access"]["http"]["message"]
    assert evidence["historical_sip_access"]["available"] is True
    assert len(responses.calls) == 2
    latest_request, historical_request = (call.request for call in responses.calls)
    assert latest_request.params == {"symbols": "SPY", "feed": "sip"}
    assert historical_request.params["feed"] == "sip"
    assert historical_request.params["adjustment"] == "all"
    assert "test-secret" not in json.dumps(evidence)


@responses.activate
def test_sip_preflight_success_evidence_shape(tmp_path) -> None:
    path, config = _sip_config(tmp_path)
    responses.add(
        responses.GET,
        LATEST_BARS_ENDPOINT,
        status=200,
        json={
            "bars": {
                "SPY": {
                    "t": "2026-09-05T20:00:00Z",
                    "o": 649.0,
                    "h": 651.0,
                    "l": 648.0,
                    "c": 650.0,
                }
            }
        },
    )
    responses.add(responses.GET, HISTORICAL_BARS_ENDPOINT, status=200, json=_historical_bars_payload())

    evidence = check_sip_entitlement(
        config_path=path,
        config=config,
        api_key="test-key",
        api_secret="test-secret",
        checked_at="2026-09-05T21:12:16+00:00",
    )

    assert evidence["schema_version"] == 1
    assert evidence["check"] == "alpaca_sip_entitlement_historical_bars"
    assert evidence["checked_at"] == "2026-09-05T21:12:16+00:00"
    assert evidence["endpoint"] == HISTORICAL_BARS_ENDPOINT
    assert evidence["symbols"] == list(ETF_SYMBOLS)
    assert evidence["feed"] == "sip"
    assert evidence["config"]["path"] == str(path)
    assert evidence["data_configuration"] == {
        "configured_adjustment": "split_dividend",
        "effective_alpaca_adjustment": "all",
    }
    assert evidence["outcome"] == "available"
    assert evidence["available"] is True
    assert evidence["http"] == {
        "status_code": 200,
        "message": "completed historical SIP bars returned for all campaign ETFs",
    }
    assert evidence["latest_sip_access"]["available"] is True
    assert evidence["historical_sip_access"] == {
        "available": True,
        "endpoint": HISTORICAL_BARS_ENDPOINT,
        "request_parameters": {
            "symbols": ",".join(ETF_SYMBOLS),
            "timeframe": "1Day",
            "start": "2026-08-28T00:00:00Z",
            "end": "2026-08-29T00:00:00Z",
            "adjustment": "all",
            "feed": "sip",
        },
        "http": {
            "status_code": 200,
            "message": "completed historical SIP bars returned for all campaign ETFs",
        },
    }
    assert len(evidence["config"]["sha256"]) == 64


@responses.activate
def test_sip_preflight_rejects_historical_bars_outside_requested_session(tmp_path) -> None:
    path, config = _sip_config(tmp_path)
    responses.add(responses.GET, LATEST_BARS_ENDPOINT, status=403, json={"message": "no latest"})
    payload = _historical_bars_payload()
    for rows in payload["bars"].values():
        rows[0]["t"] = "2026-08-29T20:00:00Z"
    responses.add(responses.GET, HISTORICAL_BARS_ENDPOINT, status=200, json=payload)

    evidence = check_sip_entitlement(
        config_path=path,
        config=config,
        api_key="test-key",
        api_secret="test-secret",
    )

    assert evidence["available"] is False
    assert evidence["outcome"] == "unavailable"
    assert evidence["historical_sip_access"]["available"] is False


@responses.activate
def test_sip_preflight_malformed_historical_timestamp_fails_closed(tmp_path) -> None:
    path, config = _sip_config(tmp_path)
    responses.add(responses.GET, LATEST_BARS_ENDPOINT, status=403, json={"message": "no latest"})
    payload = _historical_bars_payload()
    for rows in payload["bars"].values():
        rows[0]["t"] = "not-a-timestamp"
    responses.add(responses.GET, HISTORICAL_BARS_ENDPOINT, status=200, json=payload)

    evidence = check_sip_entitlement(
        config_path=path,
        config=config,
        api_key="test-key",
        api_secret="test-secret",
    )

    assert evidence["outcome"] == "unavailable"
    assert evidence["historical_sip_access"]["available"] is False


@responses.activate
def test_sip_preflight_malformed_latest_response_fails_closed_for_latest_access(tmp_path) -> None:
    path, config = _sip_config(tmp_path)
    responses.add(responses.GET, LATEST_BARS_ENDPOINT, status=200, body="[]")
    responses.add(responses.GET, HISTORICAL_BARS_ENDPOINT, status=200, json=_historical_bars_payload())

    evidence = check_sip_entitlement(
        config_path=path,
        config=config,
        api_key="test-key",
        api_secret="test-secret",
    )

    assert evidence["available"] is True
    assert evidence["outcome"] == "available"
    assert evidence["latest_sip_access"]["available"] is False
    assert evidence["historical_sip_access"]["available"] is True
    assert evidence["http"]["status_code"] == 200


def test_preflight_evidence_refuses_overwrite(tmp_path) -> None:
    output = tmp_path / "evidence.json"
    write_immutable_json(output, {"outcome": "unavailable"})

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_immutable_json(output, {"outcome": "available"})

    assert json.loads(output.read_text(encoding="utf-8")) == {"outcome": "unavailable"}
