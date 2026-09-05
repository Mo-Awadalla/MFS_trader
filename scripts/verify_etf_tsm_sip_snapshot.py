"""Verify a retained ETF SIP input bundle without changing its immutable manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.catalog import BarRequest, DataCatalog, StrictPanelRequest  # noqa: E402
from scripts.acquire_etf_tsm_sip_inputs import (  # noqa: E402
    calendar_session_close_utc,
    completed_calendar_entries,
)
from scripts.preflight_alpaca_sip_entitlement import (  # noqa: E402
    write_immutable_json as _atomic_create_json,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_snapshot(bundle: Path, manifest_path: Path) -> dict[str, Any]:
    """Recheck retained bundle hashes and strict completed-session panel semantics."""
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    snapshot = manifest["snapshot_id"]
    archive_root = f"data/parquet/etf_tsm_sip_campaign/{snapshot}"
    expected_members = {
        f"{archive_root}/{relative_path}": digest
        for relative_path, digest in manifest["files"].items()
    }
    with tarfile.open(bundle, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers() if member.isfile()}
        bundled_manifest = members.get(f"docs/reports/etf_campaign_inputs/{snapshot}/manifest.json")
        if bundled_manifest is None or archive.extractfile(bundled_manifest).read() != manifest_bytes:
            raise ValueError("bundle manifest does not match retained manifest")
        if set(expected_members).difference(members):
            raise ValueError("bundle omits manifest-listed input files")
        for name, expected_hash in expected_members.items():
            contents = archive.extractfile(members[name]).read()
            if _sha256_bytes(contents) != expected_hash:
                raise ValueError(f"bundle hash mismatch: {name}")

        with tempfile.TemporaryDirectory() as directory:
            extraction_root = Path(directory)
            archive.extractall(extraction_root, filter="data")
            data_root = extraction_root / archive_root
            calendar = _load_json(data_root / "http/calendar.json")
            if not isinstance(calendar, list):
                raise ValueError("retained calendar is not a list")
            panels = [panel for group in manifest["artifacts"].values() for panel in group.values()]
            common_start = max(pd.Timestamp(panel["start"]).date().isoformat() for panel in panels)
            common_end = min(pd.Timestamp(panel["end"]).date().isoformat() for panel in panels)
            cutoff = manifest["completed_session_cutoff"]
            completed = completed_calendar_entries(calendar, common_start, common_end, cutoff)
            if len({item["date"] for item in completed}) != len(completed):
                raise ValueError("retained completed calendar has duplicate dates")
            sessions = tuple(f"{item['date']}T00:00:00Z" for item in completed)
            closes = tuple(calendar_session_close_utc(item) for item in completed)
            request = BarRequest(data_root, tuple(manifest["symbols"]), "1d", "alpaca_sip_raw")
            DataCatalog().load_strict_panel(
                StrictPanelRequest(request, sessions, closes, manifest["acquired_at"])
            )
            adjusted_request = BarRequest(
                data_root, tuple(manifest["symbols"]), "1d", "alpaca_sip_adjusted"
            )
            DataCatalog().load_strict_panel(
                StrictPanelRequest(adjusted_request, sessions, closes, manifest["acquired_at"])
            )

    close_times = [pd.Timestamp(value) for value in closes]
    local_offsets = [
        pd.Timestamp(f"{item['date']} {item['close']}").tz_localize("America/New_York").utcoffset()
        for item in completed
    ]
    return {
        "schema_version": 1,
        "verification_status": "passed",
        "source_manifest_status": manifest["status"],
        "input_gate_status": "passed" if manifest["status"] == "passed" else "blocked",
        "campaign_progression_authorized": False,
        "verification": "retained_sip_calendar_and_panel_integrity",
        "snapshot_id": snapshot,
        "source_manifest_sha256": _sha256_bytes(manifest_bytes),
        "source_bundle_sha256": _sha256_bytes(bundle.read_bytes()),
        "source_acquired_at": manifest["acquired_at"],
        "completed_session_cutoff": cutoff,
        "calendar": {
            "total_records": len(calendar),
            "completed_panel_sessions": len(completed),
            "first_session": completed[0]["date"],
            "last_session": completed[-1]["date"],
            "first_close_utc": closes[0],
            "last_close_utc": closes[-1],
            "regular_closes": sum(item["close"] == "16:00" for item in completed),
            "early_closes": sum(item["close"] != "16:00" for item in completed),
            "est_closes": sum(offset.total_seconds() == -18_000 for offset in local_offsets),
            "edt_closes": sum(offset.total_seconds() == -14_400 for offset in local_offsets),
            "closes_after_acquisition": sum(
                timestamp > pd.Timestamp(manifest["acquired_at"]) for timestamp in close_times
            ),
            "duplicate_dates": len(completed) - len({item["date"] for item in completed}),
        },
        "panels": {"variants": 2, "symbols_per_variant": len(manifest["symbols"]), "rows_per_symbol": len(sessions)},
        "manifest_input_hashes": {"checked": len(expected_members), "mismatches": 0},
        "limitations": [
            "This verifies retained calendar interpretation and panel alignment only.",
            "It does not prove complete corporate-action endpoint coverage or reconcile raw and adjusted price factors.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a retained ETF SIP input bundle")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--supersedes-report",
        type=Path,
        help="optional prior verification report retained as historical evidence",
    )
    args = parser.parse_args(argv)
    report = verify_snapshot(args.bundle, args.manifest)
    if args.supersedes_report is not None:
        report["supersedes"] = {
            "path": str(args.supersedes_report),
            "sha256": _sha256_bytes(args.supersedes_report.read_bytes()),
        }
    _atomic_create_json(args.report, report)
    print(f"verification_status={report['verification_status']} report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
