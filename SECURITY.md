# Security policy

MFS-Trader is an experimental research/validation workbench with simulated execution, not a supported live-trading system. No release result authorizes order placement, paper qualification, or promotion of an Experiment.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/Mo-Awadalla/MFS_trader/security/advisories/new) when available. If private reporting is unavailable, request a private contact channel in a public issue without including vulnerability details, credentials, account identifiers, broker responses, or proprietary data. Do not demonstrate a finding against a real broker/account.

Include the affected revision, component, impact, and a minimal synthetic offline reproduction. Redact secret values completely; provide only paths, commit IDs and secret-pattern classes. If a credential may have escaped, revoke/rotate it through the provider's normal account controls; deleting a file or rewriting history does not revoke it.

## Safe verification

- Do not load `.env`, supply broker credentials, call market-data/account endpoints, or start paper/live sessions during release verification.
- Set `RUN_LIVE_BROKER_TESTS=0 MFS_TEST_LOAD_DOTENV=0`. The test socket guard reduces accidental external access but is not an operating-system sandbox.
- Never alter real `experiments/<uuid>/` evidence or lifecycle records to make a check pass. Use temporary registries and synthetic artifacts.
- Do not publish vendor data, SIP bundles, retained API responses, credentials, or market-data archives without established redistribution rights.
- Scan only the sanitized release history, not every local ref. Keep scanner reports redacted and do not paste raw matches into public issues or logs.

The [installable-release contract](docs/release/installable-release.md) documents artifact allowlists, redacted tree/history scanning, runtime-only wheel checks and dependency-audit limitations. Security scans and dependency audits are evidence at a point in time, not a guarantee of safety.
