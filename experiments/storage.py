"""Experiment persistence — SQLite query index + per-uuid metadata.json."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.hashing import experiment_from_metadata_dict, experiment_to_metadata_dict
from experiments.models import Experiment, ExperimentNotFoundError, PromotionStatus

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiments (
    uuid                    TEXT PRIMARY KEY,
    label                   TEXT NOT NULL,
    experiment_hash         TEXT NOT NULL UNIQUE,
    strategy                TEXT NOT NULL,
    strategy_template_version TEXT NOT NULL,
    promotion_status        TEXT NOT NULL,
    data_source             TEXT,
    created_at              TEXT NOT NULL,
    superseded_by           TEXT,
    metadata_path           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_experiments_strategy
    ON experiments(strategy);
CREATE INDEX IF NOT EXISTS idx_experiments_promotion
    ON experiments(promotion_status);
CREATE INDEX IF NOT EXISTS idx_experiments_template
    ON experiments(strategy_template_version);
CREATE INDEX IF NOT EXISTS idx_experiments_data_source
    ON experiments(data_source);
CREATE INDEX IF NOT EXISTS idx_experiments_label
    ON experiments(label);
"""


def utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ExperimentStore:
    """SQLite index at experiments/index.sqlite; metadata at experiments/<uuid>/metadata.json."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or "experiments")
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifacts = ArtifactManager(self.root)
        self.index_path = self.root / "index.sqlite"
        self._conn = self._open()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.index_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        return conn

    def close(self) -> None:
        self._conn.close()

    def metadata_path_for(self, uuid: str) -> Path:
        return self.artifacts.path(uuid, ArtifactKind.METADATA_JSON)

    def write_metadata(self, experiment: Experiment) -> Path:
        payload = experiment_to_metadata_dict(experiment)
        return self.artifacts.write_json(
            experiment.uuid,
            ArtifactKind.METADATA_JSON,
            payload,
            overwrite=self.artifacts.exists(experiment.uuid, ArtifactKind.METADATA_JSON),
        )

    def read_metadata(self, uuid: str) -> Experiment:
        path = self.metadata_path_for(uuid)
        if not path.exists():
            raise ExperimentNotFoundError(f"No metadata for experiment {uuid}")
        data = self.artifacts.read_json(uuid, ArtifactKind.METADATA_JSON)
        return experiment_from_metadata_dict(data)

    def insert_index(self, experiment: Experiment, metadata_path: Path) -> None:
        self._conn.execute(
            """
            INSERT INTO experiments (
                uuid, label, experiment_hash, strategy, strategy_template_version,
                promotion_status, data_source, created_at, superseded_by, metadata_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment.uuid,
                experiment.label,
                experiment.experiment_hash,
                experiment.snapshot.strategy,
                experiment.snapshot.strategy_template_version,
                experiment.promotion_status.value,
                experiment.snapshot.data_version.source,
                experiment.created_at,
                experiment.superseded_by,
                str(metadata_path),
            ),
        )
        self._conn.commit()

    def update_index_status(
        self,
        uuid: str,
        *,
        promotion_status: PromotionStatus,
        superseded_by: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE experiments
            SET promotion_status = ?, superseded_by = COALESCE(?, superseded_by)
            WHERE uuid = ?
            """,
            (promotion_status.value, superseded_by, uuid),
        )
        if self._conn.total_changes == 0:
            raise ExperimentNotFoundError(f"Experiment {uuid} not in index")
        self._conn.commit()

    def get_by_uuid(self, uuid: str) -> Experiment | None:
        row = self._conn.execute("SELECT uuid FROM experiments WHERE uuid = ?", (uuid,)).fetchone()
        if row is None:
            return None
        return self.read_metadata(uuid)

    def get_by_hash(self, experiment_hash: str) -> Experiment | None:
        row = self._conn.execute(
            "SELECT uuid FROM experiments WHERE experiment_hash = ?", (experiment_hash,)
        ).fetchone()
        if row is None:
            return None
        return self.read_metadata(str(row["uuid"]))

    def list_uuids(
        self,
        *,
        strategy: str | None = None,
        promotion_status: PromotionStatus | None = None,
        strategy_template_version: str | None = None,
        data_source: str | None = None,
        label: str | None = None,
    ) -> list[str]:
        clauses: list[str] = []
        params: list[Any] = []
        if strategy is not None:
            clauses.append("strategy = ?")
            params.append(strategy)
        if promotion_status is not None:
            clauses.append("promotion_status = ?")
            params.append(promotion_status.value)
        if strategy_template_version is not None:
            clauses.append("strategy_template_version = ?")
            params.append(strategy_template_version)
        if data_source is not None:
            clauses.append("data_source = ?")
            params.append(data_source)
        if label is not None:
            clauses.append("label = ?")
            params.append(label)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT uuid FROM experiments {where} ORDER BY created_at"
        rows = self._conn.execute(sql, params).fetchall()
        return [str(row["uuid"]) for row in rows]
