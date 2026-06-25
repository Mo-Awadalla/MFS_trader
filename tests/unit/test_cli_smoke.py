from __future__ import annotations

import pytest

from engine import cli
from storage.event_logger import EventLogger
from storage.schema import init_db


def test_engine_cli_help_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    assert "mfs-engine" in capsys.readouterr().out


def test_engine_preflight_loads_paper_config(capsys):
    rc = cli.main(["--config", "config/paper.toml", "preflight"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Config OK" in out
    assert "mode: paper" in out


def test_engine_report_command_reads_sqlite(tmp_path, capsys):
    db_path = tmp_path / "engine.sqlite"
    conn = init_db(db_path)
    logger = EventLogger(conn, environment="paper")
    logger.log("ENGINE_HEARTBEAT", cycle_id="cycle-1", message="Processing bar 2024-01-01")
    logger.log("ENGINE_HEARTBEAT", cycle_id="cycle-1", message="Bar 2024-01-01 complete — cycle 1")
    conn.close()

    rc = cli.main(["report", "--db", str(db_path), "--allow-blockers"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Operational Report" in out
    assert "Bars started/completed: 1/1" in out
