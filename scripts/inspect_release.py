"""Inspect release archives and report secret-pattern locations without secret values.

Uses only the standard library and git. History means ancestors of --revision,
not all local refs (which can include obsolete, unsanitized history). Findings
are heuristic and require private review; no credential validity checks occur.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

PACKAGES = {
    "config", "storage", "data", "strategies", "research", "validation",
    "portfolio", "risk", "execution", "engine", "monitoring", "experiments",
}
CONFIGS = {"research.toml", "paper.toml", "paper_shakedown.toml", "paper_etf_tsm.toml"}
SOURCE_METADATA = {
    "README.md", "LICENSE", "LICENSE.txt", "PKG-INFO", "pyproject.toml",
    "setup.cfg", "MANIFEST.in", "requirements-dev.txt", "requirements-dev-py311.txt",
}
PATTERNS = {
    "aws_access_key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "alpaca_paper_key": re.compile(rb"\bPK[A-Z0-9]{18}\b"),
    "apca_header_reference": re.compile(rb"APCA-(?:API-KEY-ID|API-SECRET-KEY)"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "provider_literal_assignment": re.compile(
        rb"(?i)(?:alpaca|apca|binance|coinbase)[A-Z0-9_-]*(?:key|secret)"
        rb"[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_+/=-]{16,}[\"']"
    ),
}


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
    ).stdout


def secret_classes(content: bytes) -> list[str]:
    return [name for name, pattern in PATTERNS.items() if pattern.search(content)]


def is_env(path: str) -> bool:
    return any(part == ".env" or part.startswith(".env.") for part in PurePosixPath(path).parts)


def scan_tree(repo: Path) -> list[dict[str, object]]:
    findings = []
    paths = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    for relative in sorted(set(paths.decode().split("\0")) - {""}):
        path = repo / relative
        if is_env(relative):
            findings.append({"path": relative, "classes": ["env_file_not_opened"]})
        elif path.is_file() and not path.is_symlink():
            classes = secret_classes(path.read_bytes())
            if classes:
                findings.append({"path": relative, "classes": classes})
    # Ignored root dotenv files are reported by name, never opened.
    for path in sorted(repo.glob(".env*")):
        if path.is_file() and not any(f["path"] == path.name for f in findings):
            findings.append({"path": path.name, "classes": ["env_file_not_opened"]})
    return findings


def scan_history(repo: Path, revision: str) -> tuple[int, list[dict[str, object]]]:
    findings = []
    checked: set[tuple[str, str]] = set()
    commits = git(repo, "rev-list", revision).decode().splitlines()
    for commit in commits:
        for entry in git(repo, "ls-tree", "-rz", commit).split(b"\0"):
            if not entry:
                continue
            meta, raw_path = entry.split(b"\t", 1)
            _, kind, oid = meta.decode().split()
            if kind != "blob":
                continue
            path = raw_path.decode(errors="replace")
            key = (oid, path)
            if key in checked:
                continue
            checked.add(key)
            if is_env(path):
                classes = ["env_file_not_opened"]
            else:
                classes = secret_classes(git(repo, "cat-file", "blob", oid))
            if classes:
                findings.append({"commit": commit, "path": path, "classes": classes})
    return len(commits), findings


def allowed_member(name: str, *, wheel: bool) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return False
    parts = path.parts if wheel else path.parts[1:]
    if not parts:
        return False
    if any(part.startswith(".env") or part == "__pycache__" for part in parts):
        return False
    root = parts[0]
    if root.endswith(".dist-info") and wheel:
        return len(parts) == 2 and parts[1] in {
            "METADATA", "WHEEL", "RECORD", "entry_points.txt", "top_level.txt", "LICENSE", "LICENSE.txt",
        }
    if not wheel and root.endswith(".egg-info"):
        return len(parts) == 2 and parts[1] in {
            "PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt",
            "requires.txt", "top_level.txt", "not-zip-safe",
        }
    if not wheel and len(parts) == 1 and root in SOURCE_METADATA:
        return True
    if root not in PACKAGES:
        return False
    if root == "experiments" and len(parts) != 2:
        return False
    if root == "portfolio" and "research_artifacts" in parts:
        return False
    return path.suffix == ".py" or (
        root == "config" and len(parts) == 2 and parts[1] in CONFIGS
    )


def inspect_archive(path: Path) -> dict[str, object]:
    wheel = path.suffix == ".whl"
    if wheel:
        with zipfile.ZipFile(path) as archive:
            names = [member.filename for member in archive.infolist() if not member.is_dir()]
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            names = [member.name for member in archive.getmembers() if not member.isdir()]
            if any(member.issym() or member.islnk() for member in archive.getmembers()):
                raise ValueError("Release archives must not contain links")
    else:
        raise ValueError("Expected a .whl or .tar.gz archive")
    forbidden = [name for name in names if not allowed_member(name, wheel=wheel)]
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"archive": str(path), "sha256": digest, "members": len(names), "forbidden": forbidden}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--revision", default="HEAD", help="Scan this commit and its ancestors only")
    parser.add_argument("--scan-secrets", action="store_true")
    parser.add_argument("--archive", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path, help="Create a new redacted JSON report (never overwrite)")
    args = parser.parse_args()
    if not args.scan_secrets and not args.archive:
        parser.error("choose --scan-secrets and/or --archive")
    report: dict[str, object] = {"secret_values_redacted": True}
    try:
        archives = [inspect_archive(path) for path in args.archive]
        report["archives"] = archives
        if args.scan_secrets:
            repo = args.repo.resolve()
            revision = git(repo, "rev-parse", "--verify", f"{args.revision}^{{commit}}").decode().strip()
            count, findings = scan_history(repo, revision)
            report.update(
                revision=revision, commits_scanned=count,
                tree_findings=scan_tree(repo), history_findings=findings,
                note="Heuristic report only; APCA header references and synthetic fixtures are not proof of secrets",
            )
        encoded = json.dumps(report, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
        print(encoded, end="")
        return int(any(item["forbidden"] for item in archives))
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError, zipfile.BadZipFile) as exc:
        # Never echo subprocess stdout/stderr: git or external tools may expose data.
        print(json.dumps({"inspection_error_class": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
