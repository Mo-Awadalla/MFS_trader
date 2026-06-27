"""Artifact Manager — canonical filesystem authority for Experiment evidence."""

from __future__ import annotations

import json
import os
import tempfile
import uuid as uuidlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal


class ArtifactKind(StrEnum):
    """Canonical Experiment artifact kinds."""

    METADATA_JSON = "metadata_json"
    VALIDATION_REPORT_JSON = "validation_report_json"
    VALIDATION_REPORT_MD = "validation_report_md"
    VALIDATION_VERDICT_TXT = "validation_verdict_txt"
    REPLAY_ATTRIBUTION_JSON = "replay_attribution_json"
    DIAGNOSTICS_SIGNALS_JSON = "diagnostics_signals_json"
    FEASIBILITY_REPORT_JSON = "feasibility_report_json"
    PAPER_SESSION_JSON = "paper_session_json"
    PAPER_OPERATOR_REPORT_JSON = "paper_operator_report_json"
    PAPER_OPERATOR_REPORT_MD = "paper_operator_report_md"
    LIVE_SESSION_JSON = "live_session_json"
    RUN_LOG = "run_log"


ArtifactFormat = Literal["json", "text"]


@dataclass(frozen=True)
class ArtifactDefinition:
    relative_path: Path
    format: ArtifactFormat
    mutable: bool = False


ARTIFACT_DEFINITIONS: dict[ArtifactKind, ArtifactDefinition] = {
    ArtifactKind.METADATA_JSON: ArtifactDefinition(
        Path("metadata.json"), format="json", mutable=True
    ),
    ArtifactKind.VALIDATION_REPORT_JSON: ArtifactDefinition(
        Path("validation") / "report.json", format="json"
    ),
    ArtifactKind.VALIDATION_REPORT_MD: ArtifactDefinition(
        Path("validation") / "report.md", format="text"
    ),
    ArtifactKind.VALIDATION_VERDICT_TXT: ArtifactDefinition(
        Path("validation") / "verdict.txt", format="text"
    ),
    ArtifactKind.REPLAY_ATTRIBUTION_JSON: ArtifactDefinition(
        Path("replay") / "attribution.json", format="json"
    ),
    ArtifactKind.DIAGNOSTICS_SIGNALS_JSON: ArtifactDefinition(
        Path("diagnostics") / "signals.json", format="json"
    ),
    ArtifactKind.FEASIBILITY_REPORT_JSON: ArtifactDefinition(
        Path("feasibility") / "report.json", format="json"
    ),
    ArtifactKind.PAPER_SESSION_JSON: ArtifactDefinition(
        Path("paper") / "session.json", format="json"
    ),
    ArtifactKind.PAPER_OPERATOR_REPORT_JSON: ArtifactDefinition(
        Path("paper") / "operator_report.json", format="json"
    ),
    ArtifactKind.PAPER_OPERATOR_REPORT_MD: ArtifactDefinition(
        Path("paper") / "operator_report.md", format="text"
    ),
    ArtifactKind.LIVE_SESSION_JSON: ArtifactDefinition(Path("live") / "session.json", format="json"),
    ArtifactKind.RUN_LOG: ArtifactDefinition(Path("logs") / "run.log", format="text"),
}


class ArtifactError(Exception):
    """Base class for artifact persistence errors."""


class UnknownArtifactKindError(ArtifactError):
    """Raised when a caller provides an unknown ArtifactKind."""


class InvalidExperimentUUIDError(ArtifactError):
    """Raised when an Experiment UUID is not a valid canonical UUID string."""


class ArtifactExistsError(ArtifactError):
    """Raised when a mutable artifact exists and overwrite was not explicit."""


class ArtifactImmutableError(ArtifactError):
    """Raised when a caller attempts to overwrite immutable evidence."""


class ArtifactFormatError(ArtifactError):
    """Raised when a caller uses the wrong serializer for an artifact kind."""


ArtifactKindInput = ArtifactKind | str


class ArtifactManager:
    """Canonical filesystem authority for Experiment evidence."""

    def __init__(self, root: str | Path = "experiments") -> None:
        self.root = Path(root)

    def experiment_dir(self, experiment_uuid: str) -> Path:
        """Return the canonical Experiment artifact directory without creating it."""
        return self.root / self._validate_experiment_uuid(experiment_uuid)

    def path(self, experiment_uuid: str, kind: ArtifactKindInput) -> Path:
        """Return the canonical artifact path without creating it."""
        artifact_kind = self._normalize_kind(kind)
        definition = ARTIFACT_DEFINITIONS[artifact_kind]
        return self.experiment_dir(experiment_uuid) / definition.relative_path

    def write_json(
        self,
        experiment_uuid: str,
        kind: ArtifactKindInput,
        payload: Any,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Write a JSON artifact according to its kind policy."""
        artifact_kind = self._normalize_kind(kind)
        self._require_format(artifact_kind, "json")
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        return self._write_text_payload(
            experiment_uuid,
            artifact_kind,
            text,
            overwrite=overwrite,
        )

    def write_text(
        self,
        experiment_uuid: str,
        kind: ArtifactKindInput,
        text: str,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Write a text artifact according to its kind policy."""
        artifact_kind = self._normalize_kind(kind)
        self._require_format(artifact_kind, "text")
        return self._write_text_payload(
            experiment_uuid,
            artifact_kind,
            text,
            overwrite=overwrite,
        )

    def read_json(self, experiment_uuid: str, kind: ArtifactKindInput) -> Any:
        """Read a JSON artifact."""
        artifact_kind = self._normalize_kind(kind)
        self._require_format(artifact_kind, "json")
        return json.loads(self.path(experiment_uuid, artifact_kind).read_text(encoding="utf-8"))

    def exists(self, experiment_uuid: str, kind: ArtifactKindInput) -> bool:
        """Return whether the canonical artifact exists."""
        return self.path(experiment_uuid, kind).exists()

    def paper_session_path(self, experiment_uuid: str, session_id: str) -> Path:
        """Return the canonical immutable paper-session path."""
        safe_session_id = self._validate_session_id(session_id)
        return self.experiment_dir(experiment_uuid) / "paper" / "sessions" / f"{safe_session_id}.json"

    def write_paper_session_json(
        self,
        experiment_uuid: str,
        session_id: str,
        payload: Any,
    ) -> Path:
        """Write one immutable paper session artifact under ``paper/sessions``."""
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        path = self.paper_session_path(experiment_uuid, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._atomic_create(path, text)
        except ArtifactExistsError as exc:
            raise ArtifactImmutableError(
                f"Paper session artifact is immutable: {path}"
            ) from exc
        return path

    def read_paper_session_json(self, experiment_uuid: str, session_id: str) -> Any:
        """Read one immutable paper session artifact."""
        return json.loads(self.paper_session_path(experiment_uuid, session_id).read_text(encoding="utf-8"))

    def paper_session_report_path(
        self,
        experiment_uuid: str,
        session_id: str,
        report_name: str,
    ) -> Path:
        """Return an immutable report path for one paper session."""
        safe_session_id = self._validate_session_id(session_id)
        safe_report_name = self._validate_report_name(report_name)
        return (
            self.experiment_dir(experiment_uuid)
            / "paper"
            / "sessions"
            / safe_session_id
            / safe_report_name
        )

    def write_paper_session_report_json(
        self,
        experiment_uuid: str,
        session_id: str,
        report_name: str,
        payload: Any,
    ) -> Path:
        """Write one immutable JSON report for a paper session."""
        if not report_name.endswith(".json"):
            raise ArtifactError(f"Paper session report must be JSON: {report_name}")
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        path = self.paper_session_report_path(experiment_uuid, session_id, report_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._atomic_create(path, text)
        except ArtifactExistsError as exc:
            raise ArtifactImmutableError(
                f"Paper session report artifact is immutable: {path}"
            ) from exc
        return path

    def read_paper_session_report_json(
        self,
        experiment_uuid: str,
        session_id: str,
        report_name: str,
    ) -> Any:
        """Read one immutable JSON report for a paper session."""
        return json.loads(
            self.paper_session_report_path(
                experiment_uuid, session_id, report_name
            ).read_text(encoding="utf-8")
        )

    def list_paper_sessions(self, experiment_uuid: str) -> list[dict[str, Any]]:
        """Read all paper session artifacts for an Experiment, sorted by session id."""
        sessions_dir = self.experiment_dir(experiment_uuid) / "paper" / "sessions"
        if not sessions_dir.exists():
            return []
        sessions: list[dict[str, Any]] = []
        for path in sorted(sessions_dir.glob("*.json")):
            sessions.append(json.loads(path.read_text(encoding="utf-8")))
        return sessions

    def _write_text_payload(
        self,
        experiment_uuid: str,
        kind: ArtifactKind,
        text: str,
        *,
        overwrite: bool,
    ) -> Path:
        definition = ARTIFACT_DEFINITIONS[kind]
        path = self.path(experiment_uuid, kind)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists() and not definition.mutable:
            raise ArtifactImmutableError(f"Artifact is immutable: {kind.value} at {path}")
        if path.exists() and not overwrite:
            raise ArtifactExistsError(f"Artifact already exists: {kind.value} at {path}")

        if definition.mutable and overwrite:
            self._atomic_replace(path, text)
        else:
            try:
                self._atomic_create(path, text)
            except ArtifactExistsError as exc:
                if not definition.mutable:
                    raise ArtifactImmutableError(
                        f"Artifact is immutable: {kind.value} at {path}"
                    ) from exc
                raise
        return path

    def _atomic_create(self, path: Path, text: str) -> None:
        tmp_path = self._write_temp(path.parent, text)
        try:
            os.link(tmp_path, path)
        except FileExistsError as exc:
            raise ArtifactExistsError(f"Artifact already exists: {path}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)

    def _atomic_replace(self, path: Path, text: str) -> None:
        tmp_path = self._write_temp(path.parent, text)
        try:
            os.replace(tmp_path, path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _write_temp(self, directory: Path, text: str) -> Path:
        fd, name = tempfile.mkstemp(prefix=".artifact-", suffix=".tmp", dir=directory)
        tmp_path = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return tmp_path

    def _require_format(self, kind: ArtifactKind, expected: ArtifactFormat) -> None:
        actual = ARTIFACT_DEFINITIONS[kind].format
        if actual != expected:
            raise ArtifactFormatError(
                f"Artifact {kind.value} uses {actual} format, not {expected}"
            )

    def _normalize_kind(self, kind: ArtifactKindInput) -> ArtifactKind:
        if isinstance(kind, ArtifactKind):
            return kind
        try:
            return ArtifactKind(kind)
        except ValueError as exc:
            raise UnknownArtifactKindError(f"Unknown artifact kind: {kind}") from exc

    def _validate_experiment_uuid(self, experiment_uuid: str) -> str:
        try:
            parsed = uuidlib.UUID(experiment_uuid)
        except ValueError as exc:
            raise InvalidExperimentUUIDError(
                f"Invalid Experiment UUID: {experiment_uuid}"
            ) from exc
        canonical = str(parsed)
        if experiment_uuid != canonical:
            raise InvalidExperimentUUIDError(
                f"Experiment UUID must be canonical lowercase form: {canonical}"
            )
        return canonical

    def _validate_session_id(self, session_id: str) -> str:
        if not session_id:
            raise ArtifactError("Paper session id is required")
        if any(ch in session_id for ch in ("/", "\\", ".")):
            raise ArtifactError(f"Invalid paper session id: {session_id}")
        if not all(ch.isalnum() or ch in {"-", "_"} for ch in session_id):
            raise ArtifactError(f"Invalid paper session id: {session_id}")
        return session_id

    def _validate_report_name(self, report_name: str) -> str:
        if not report_name:
            raise ArtifactError("Paper session report name is required")
        if any(ch in report_name for ch in ("/", "\\")):
            raise ArtifactError(f"Invalid paper session report name: {report_name}")
        if report_name in {".", ".."}:
            raise ArtifactError(f"Invalid paper session report name: {report_name}")
        if not all(ch.isalnum() or ch in {"-", "_", "."} for ch in report_name):
            raise ArtifactError(f"Invalid paper session report name: {report_name}")
        return report_name
