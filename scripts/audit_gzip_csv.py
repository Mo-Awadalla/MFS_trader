#!/usr/bin/env python3
"""Stream-audit gzip CSV files without expanding them on disk."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def audit(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)

    uncompressed_bytes = 0
    newline_count = 0
    with gzip.open(path, "rb") as stream:
        header_bytes = stream.readline()
        first_row_bytes = stream.readline()
        uncompressed_bytes += len(header_bytes) + len(first_row_bytes)
        newline_count += header_bytes.count(b"\n") + first_row_bytes.count(b"\n")
        while chunk := stream.read(8 * 1024 * 1024):
            uncompressed_bytes += len(chunk)
            newline_count += chunk.count(b"\n")

    return {
        "path": str(path.resolve()),
        "compressed_bytes": path.stat().st_size,
        "uncompressed_bytes": uncompressed_bytes,
        "sha256": digest.hexdigest(),
        "header": header_bytes.decode("utf-8").rstrip("\r\n"),
        "first_row": first_row_bytes.decode("utf-8").rstrip("\r\n"),
        "data_rows": max(0, newline_count - 1),
        "gzip_crc_valid": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps([audit(path) for path in args.paths], indent=2))


if __name__ == "__main__":
    main()
