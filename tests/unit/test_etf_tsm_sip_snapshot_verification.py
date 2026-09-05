from __future__ import annotations

import json

import pytest

from scripts.verify_etf_tsm_sip_snapshot import _atomic_create_json


def test_snapshot_verification_report_is_immutable(tmp_path) -> None:
    report = tmp_path / "verification.json"
    _atomic_create_json(report, {"campaign_gate_status": "blocked"})

    with pytest.raises(FileExistsError):
        _atomic_create_json(report, {"campaign_gate_status": "passed"})

    assert json.loads(report.read_text()) == {"campaign_gate_status": "blocked"}
