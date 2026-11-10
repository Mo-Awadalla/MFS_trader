import pytest

from scripts import run_bitcoin_5m_probability_model as entry
from scripts.run_bitcoin_5m_exchange_model import DEFAULT_OUTPUT, run


def test_opt_in_entrypoint_selects_repaired_v2(monkeypatch, tmp_path):
    received = []

    def fake_run(output, spec):
        received.append((output, spec))
        return {"status": "test"}

    monkeypatch.setattr(entry, "run", fake_run)
    monkeypatch.setattr("sys.argv", ["run", "--exchange-v2", "--output-dir", str(tmp_path)])
    assert entry.main() == 0
    assert received == [(tmp_path, DEFAULT_OUTPUT / "spec.json")]


def test_legacy_runner_refuses_to_overwrite_evidence(monkeypatch, tmp_path):
    artifact = tmp_path / "model.pkl"
    artifact.write_bytes(b"preserve")
    monkeypatch.setattr("sys.argv", ["run", "--legacy-v1", "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        entry.main()
    assert error.value.code == 2
    assert artifact.read_bytes() == b"preserve"


def test_modified_spec_is_rejected_before_writing(tmp_path):
    spec = tmp_path / "changed.json"
    spec.write_bytes((DEFAULT_OUTPUT / "spec.json").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="specification changed"):
        run(tmp_path / "new_output", spec)
    assert not (tmp_path / "new_output").exists()


def test_default_entrypoint_still_runs_v1(monkeypatch, tmp_path):
    received = []
    monkeypatch.setattr(entry, "run_experiment", lambda **kwargs: received.append(kwargs) or {})
    monkeypatch.setattr(entry, "format_report", lambda _: "legacy")
    monkeypatch.setattr("sys.argv", ["run", "--output-dir", str(tmp_path)])
    assert entry.main() == 0
    assert received[0]["output_dir"] == tmp_path


def test_v2_runner_preserves_an_existing_report(tmp_path):
    archived = tmp_path / "results.json"
    archived.write_text("original evidence", encoding="utf-8")
    with pytest.raises(FileExistsError, match="fresh output directory"):
        run(tmp_path, DEFAULT_OUTPUT / "spec.json")
    assert archived.read_text(encoding="utf-8") == "original evidence"
