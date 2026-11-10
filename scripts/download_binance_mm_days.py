"""Download and verify preregistered free Binance market-making study days."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "research_scout" / "navier_stokes_liquidity_v2" / "free_data" / "binance-public" / "futures-um"
DATES = [
    "2023-08-15",
    "2023-09-15",
    "2023-10-15",
    "2023-11-15",
    "2023-12-15",
    "2024-01-15",
    "2024-02-15",
    "2024-03-15",
]
KINDS = ["bookTicker", "aggTrades"]
BASE_URL = "https://data.binance.vision/data/futures/um/daily"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    with requests.get(url, stream=True, timeout=(15, 120)) as response:
        response.raise_for_status()
        with temporary.open("wb") as stream:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    stream.write(chunk)
    temporary.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument(
        "--dates",
        nargs="+",
        default=DATES,
        help="Explicit YYYY-MM-DD dates; defaults to the original eight-day panel.",
    )
    args = parser.parse_args()
    symbol = args.symbol.upper()
    for date in args.dates:
        day = DESTINATION / symbol / date
        day.mkdir(parents=True, exist_ok=True)
        for kind in KINDS:
            name = f"{symbol}-{kind}-{date}.zip"
            archive = day / name
            checksum = day / f"{name}.CHECKSUM"
            url = f"{BASE_URL}/{kind}/{symbol}/{name}"
            print(f"acquiring {date} {kind}", flush=True)
            download(url, archive)
            download(f"{url}.CHECKSUM", checksum)
            expected = checksum.read_text().split()[0].lower()
            actual = sha256(archive)
            if actual != expected:
                raise ValueError(f"checksum mismatch for {archive}: {actual} != {expected}")
            print(f"verified {name} ({archive.stat().st_size:,} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
