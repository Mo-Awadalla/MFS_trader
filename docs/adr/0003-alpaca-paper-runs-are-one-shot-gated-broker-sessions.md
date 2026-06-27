# Alpaca Paper Runs Are One-Shot Gated Broker Sessions

Alpaca paper access is enabled only as an explicitly confirmed broker session behind Experiment lifecycle gates, tiny notional caps, prior simulated failure drills, and immutable paper-session evidence. We rejected making Alpaca the default `paper-run` broker because the dangerous part is broker authority, not the command name; keeping `sim_broker` as the default while requiring `--broker alpaca_paper --confirm-paper-broker` makes the real paper path visible, auditable, and fail-closed.

**Consequences**

- Alpaca paper sessions may submit at most one tiny far-limit DAY order, then immediately cancel and reconcile it.
- Simulated reject, timeout, and reconciliation drills must pass before Alpaca paper is allowed.
- `confirm-paper-ops-pass` remains manual, but refuses promotion without passing paper-session and operator-report evidence.
