# Alpaca Paper Runs Are Explicitly Gated Broker Sessions

Alpaca paper access is enabled only as an explicitly confirmed broker session behind Experiment lifecycle gates, tiny notional caps, and immutable paper-session evidence. We rejected making Alpaca the default `paper-run` broker because the dangerous part is broker authority, not the command name; keeping `sim_broker` as the default while requiring `--broker alpaca_paper --confirm-paper-broker` makes the real paper path visible, auditable, and fail-closed.

**Consequences**

- The Alpaca Paper Smoke path may submit at most one tiny far-limit DAY order, then immediately cancel and reconcile it.
- Simulated reject, timeout, and reconciliation drills must pass before the Alpaca Paper Smoke path is allowed.
- Continuous Alpaca paper sessions are allowed only with `--broker alpaca_paper --confirm-paper-broker` under `promotion_status=paper_ops`; they remain Paper Ops evidence, not live dry-run.
- `confirm-paper-ops-pass` remains manual, but refuses promotion without passing paper-session and operator-report evidence.
