# Artifact Manager Owns Canonical Experiment Artifacts

The Artifact Manager is the file-system authority for Experiment artifacts: it owns the canonical `experiments/<uuid>/` layout, artifact kind definitions, serialization format enforcement, atomic persistence, and write-once evidence policy. The Experiment Registry/Store remains the semantic authority for Experiment identity, metadata content, and lifecycle transitions; `metadata.json` is physically written through Artifact Manager but semantically owned by Registry/Store. Engine databases remain the authority for runtime state.

This boundary keeps evidence discoverable by Experiment UUID without turning Artifact Manager into an identity service or runtime logger. Artifact Manager is identity-blind, forward-looking only, refuses legacy `runs/` paths for new evidence, archives completed logs rather than streaming them, and rejects overwrites for immutable evidence even when callers ask for overwrite.

**Consequences**

- New evidence belongs under `experiments/<experiment_uuid>/`; no random run folders or strategy-specific artifact paths.
- Artifact kinds define canonical path, format, and mutability policy.
- Immutable evidence is created exactly once; readers must never observe partial artifacts.
- Legacy artifact paths are historical provenance only, not a second storage backend.
