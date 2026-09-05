"""Check a configured Alpaca SIP entitlement without downloading bars or trading.

The endpoint and explicit ``feed=sip`` follow Alpaca's latest-stock-bars API:
https://docs.alpaca.markets/us/reference/stocklatestbars-1 .  The legacy
``split_dividend`` configuration alias maps to Alpaca's ``all`` adjustment,
which includes splits, dividends, and spin-offs:
https://docs.alpaca.markets/us/reference/stockbarsingle-1 .
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.loader import ConfigError, load_config  # noqa: E402
from config.schema import AssetClass, Config, DataConfig  # noqa: E402
from data.alpaca_downloader import effective_alpaca_adjustment  # noqa: E402

LATEST_BARS_ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars/latest"
HISTORICAL_BARS_ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
SYMBOL = "SPY"
ETF_SYMBOLS = ("DBC", "GLD", "IEF", "IWM", "QQQ", "SHY", "SPY")
# A completed Friday session: one bounded daily request, never a campaign download.
HISTORICAL_START = "2026-08-28T00:00:00Z"
HISTORICAL_END = "2026-08-29T00:00:00Z"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sanitize_message(message: str, *, secrets: tuple[str, ...]) -> str:
    """Return a bounded message that cannot repeat supplied credentials."""
    sanitized = " ".join(message.split())
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "[redacted]")
    return sanitized[:500]


def _config_identity(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _sip_data_config(config: Config) -> DataConfig:
    matches = [
        data_config
        for data_config in config.data
        if data_config.asset_class == AssetClass.EQUITY and data_config.feed == "sip"
    ]
    if len(matches) != 1:
        raise ValueError("preflight requires exactly one equity data config with explicit feed = 'sip'")
    effective_alpaca_adjustment(matches[0].adjustment)
    return matches[0]


def _evidence(
    *,
    checked_at: str,
    config_path: Path,
    data_config: DataConfig,
    latest_sip_access: dict[str, Any],
    historical_sip_access: dict[str, Any],
) -> dict[str, Any]:
    historical_available = historical_sip_access["available"]
    latest_status = latest_sip_access["http"]["status_code"]
    latest_message = latest_sip_access["http"]["message"]
    outcome = (
        "available"
        if historical_available
        else "credentials_unavailable"
        if latest_status is None and latest_message == "Alpaca credentials are unavailable"
        else "unavailable"
    )
    return {
        "schema_version": 1,
        "check": "alpaca_sip_entitlement_historical_bars",
        "checked_at": checked_at,
        "endpoint": HISTORICAL_BARS_ENDPOINT,
        "symbols": list(ETF_SYMBOLS),
        "feed": "sip",
        "config": _config_identity(config_path),
        "data_configuration": {
            "configured_adjustment": data_config.adjustment,
            "effective_alpaca_adjustment": effective_alpaca_adjustment(data_config.adjustment),
        },
        # Historical daily access is the default campaign-acquisition gate. A
        # latest 403 does not by itself prove that completed daily SIP bars are
        # unavailable; callers can independently require latest access.
        "outcome": outcome,
        "available": historical_available,
        "http": historical_sip_access["http"],
        "latest_sip_access": latest_sip_access,
        "historical_sip_access": historical_sip_access,
    }


def _has_valid_bar(bar: Any) -> bool:
    """Return whether an Alpaca bar has a timestamp and finite positive OHLC values."""
    if not isinstance(bar, dict) or not isinstance(bar.get("t"), str) or not bar["t"]:
        return False
    for field in ("o", "h", "l", "c"):
        value = bar.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not math.isfinite(value) or value <= 0:
            return False
    return True


def _access_result(
    *,
    endpoint: str,
    available: bool,
    status_code: int | None,
    message: str,
    request_parameters: dict[str, str],
) -> dict[str, Any]:
    return {
        "available": available,
        "endpoint": endpoint,
        "request_parameters": request_parameters,
        "http": {"status_code": status_code, "message": message},
    }


def _request_sip_access(
    *,
    endpoint: str,
    params: dict[str, str],
    api_key: str,
    api_secret: str,
    request_get: Callable[..., Any],
    response_is_valid: Callable[[Any], bool],
    success_message: str,
    failure_message: str,
) -> dict[str, Any]:
    """Perform one explicit SIP HTTP request and return sanitized access evidence."""
    try:
        response = request_get(
            endpoint,
            headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret},
            params=params,
            timeout=15,
        )
    except requests.RequestException as exc:
        return _access_result(
            endpoint=endpoint,
            available=False,
            status_code=None,
            message=f"request failed: {type(exc).__name__}",
            request_parameters=params,
        )

    message = _sanitize_message(response.text, secrets=(api_key, api_secret))
    if response.status_code != requests.codes.ok:
        return _access_result(
            endpoint=endpoint,
            available=False,
            status_code=response.status_code,
            message=message or f"HTTP {response.status_code}",
            request_parameters=params,
        )
    try:
        payload = response.json()
    except ValueError:
        payload = None
    is_valid = response_is_valid(payload)
    return _access_result(
        endpoint=endpoint,
        available=is_valid,
        status_code=response.status_code,
        message=success_message if is_valid else failure_message,
        request_parameters=params,
    )


def _has_valid_latest_spy_bar(payload: Any) -> bool:
    """Return whether the latest-bars response contains a usable SPY bar."""
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("bars"), dict)
        and _has_valid_bar(payload["bars"].get(SYMBOL))
    )


def _has_valid_historical_etf_bars(payload: Any) -> bool:
    """Return whether every ETF has a usable bar inside the requested completed range."""
    if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
        return False
    bars_by_symbol = payload["bars"]
    start = pd.Timestamp(HISTORICAL_START)
    end = pd.Timestamp(HISTORICAL_END)

    def valid_completed_bar(bar: Any) -> bool:
        if not _has_valid_bar(bar):
            return False
        try:
            timestamp = pd.Timestamp(bar["t"])
            if timestamp.tzinfo is None:
                timestamp = timestamp.tz_localize("UTC")
            else:
                timestamp = timestamp.tz_convert("UTC")
        except (TypeError, ValueError):
            return False
        return start <= timestamp < end

    return all(
        isinstance(bars_by_symbol.get(symbol), list)
        and any(valid_completed_bar(bar) for bar in bars_by_symbol[symbol])
        for symbol in ETF_SYMBOLS
    )


def check_sip_entitlement(
    *,
    config_path: Path,
    config: Config,
    api_key: str,
    api_secret: str,
    request_get: Callable[..., Any] = requests.get,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Check SIP access to a bounded, completed historical ETF session."""
    data_config = _sip_data_config(config)
    timestamp = checked_at or _utc_now()
    if not api_key or not api_secret:
        unavailable = _access_result(
            endpoint=LATEST_BARS_ENDPOINT,
            available=False,
            status_code=None,
            message="Alpaca credentials are unavailable",
            request_parameters={"symbols": SYMBOL, "feed": "sip"},
        )
        historical_unavailable = _access_result(
            endpoint=HISTORICAL_BARS_ENDPOINT,
            available=False,
            status_code=None,
            message="Alpaca credentials are unavailable",
            request_parameters={
                "symbols": ",".join(ETF_SYMBOLS),
                "timeframe": "1Day",
                "start": HISTORICAL_START,
                "end": HISTORICAL_END,
                "adjustment": effective_alpaca_adjustment(data_config.adjustment),
                "feed": "sip",
            },
        )
        return _evidence(
            checked_at=timestamp,
            config_path=config_path,
            data_config=data_config,
            latest_sip_access=unavailable,
            historical_sip_access=historical_unavailable,
        )

    latest_sip_access = _request_sip_access(
        endpoint=LATEST_BARS_ENDPOINT,
        params={"symbols": SYMBOL, "feed": "sip"},
        api_key=api_key,
        api_secret=api_secret,
        request_get=request_get,
        response_is_valid=_has_valid_latest_spy_bar,
        success_message="latest SIP bar returned for SPY",
        failure_message="latest SIP response omitted a usable SPY bar",
    )
    historical_sip_access = _request_sip_access(
        endpoint=HISTORICAL_BARS_ENDPOINT,
        params={
            "symbols": ",".join(ETF_SYMBOLS),
            "timeframe": "1Day",
            "start": HISTORICAL_START,
            "end": HISTORICAL_END,
            "adjustment": effective_alpaca_adjustment(data_config.adjustment),
            "feed": "sip",
        },
        api_key=api_key,
        api_secret=api_secret,
        request_get=request_get,
        response_is_valid=_has_valid_historical_etf_bars,
        success_message="completed historical SIP bars returned for all campaign ETFs",
        failure_message="historical SIP response omitted a usable campaign ETF bar",
    )
    return _evidence(
        checked_at=timestamp,
        config_path=config_path,
        data_config=data_config,
        latest_sip_access=latest_sip_access,
        historical_sip_access=historical_sip_access,
    )


def write_immutable_json(output: Path, evidence: dict[str, Any]) -> None:
    """Atomically create evidence once; reject a pre-existing output path."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite preflight evidence: {output}")

    encoded = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only SIP entitlement preflight command parser."""
    parser = argparse.ArgumentParser(description="Check Alpaca SIP entitlement without downloading data")
    parser.add_argument("--config", type=Path, required=True, help="TOML with explicit data.feed = sip")
    parser.add_argument(
        "--env-file",
        type=Path,
        required=True,
        help="Explicit dotenv file used in process memory only",
    )
    parser.add_argument("--feed", choices=("sip",), required=True, help="Explicitly confirm SIP")
    parser.add_argument(
        "--require-latest",
        action="store_true",
        help="Also require current/latest SIP access instead of daily historical access alone",
    )
    parser.add_argument("--output", type=Path, required=True, help="New JSON evidence path")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the preflight and return nonzero when SIP is unavailable or invalid."""
    args = build_parser().parse_args(argv)
    config_path = args.config.resolve()
    env_file = args.env_file.resolve()
    if not env_file.is_file():
        print(f"preflight failed: env file not found: {env_file}", file=sys.stderr)
        return 2

    try:
        config = load_config(config_path, load_env=False)
        data_config = _sip_data_config(config)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        return 2

    broker = next(
        (broker for broker in config.brokers if broker.asset_class == data_config.asset_class), None
    )
    if broker is None:
        print("preflight failed: no equity broker configured", file=sys.stderr)
        return 2

    dotenv_values_map = dotenv_values(env_file)
    evidence = check_sip_entitlement(
        config_path=config_path,
        config=config,
        api_key=dotenv_values_map.get(broker.api_key_env, "") or "",
        api_secret=dotenv_values_map.get(broker.api_secret_env, "") or "",
    )
    try:
        write_immutable_json(args.output, evidence)
    except (FileExistsError, OSError) as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        return 3

    status = evidence["http"]["status_code"]
    required_available = evidence["historical_sip_access"]["available"] and (
        not args.require_latest or evidence["latest_sip_access"]["available"]
    )
    print(
        "SIP entitlement preflight "
        f"historical_available={evidence['historical_sip_access']['available']} "
        f"latest_available={evidence['latest_sip_access']['available']} http_status={status}"
    )
    print(f"evidence={args.output}")
    return 0 if required_available else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
