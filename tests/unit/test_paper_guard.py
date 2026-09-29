"""No second paper effect may rely on a terminal but unreconciled order."""
from dataclasses import replace

import pytest

from storage.schema import init_db
from tests.unit.test_paper_run import FakeBroker, bars, capped_config, make_loop
from tests.unit.test_paper_run import setup as _paper_setup

paper_setup = _paper_setup


@pytest.mark.parametrize("failure", ["unavailable", "mismatch", None])
def test_each_fill_is_reconciled_before_next_submission(paper_setup, failure):
    class StatusBroker(FakeBroker):
        def get_order_status(self, client_order_id):
            status = super().get_order_status(client_order_id)
            if failure == "unavailable":
                return None
            if failure == "mismatch" and status is not None:
                return replace(status, filled_qty=status.filled_qty + 1)
            return status

    broker = StatusBroker()
    broker.set_price("MSFT", 150)
    broker._config.slippage_pct = 0
    rc = replace(paper_setup[3], symbols=("AAPL", "MSFT"))
    result = make_loop(
        paper_setup, broker=broker, config=capped_config(), run_config=rc,
        strategy=lambda frame, params: {"AAPL": 0.01, "MSFT": 0.01},
    ).run(bars(), paper_setup[-1])
    assert result.halted is (failure is not None)
    assert len(broker.submissions) == (1 if failure else 2)
    conn = init_db(paper_setup[-1])
    statuses = [r[0] for r in conn.execute("SELECT reconciliation_status FROM orders_live")]
    assert statuses == (["NOT_CHECKED"] if failure else ["MATCHED", "MATCHED"])
    conn.close()


@pytest.mark.parametrize("status", ["NOT_CHECKED", "REPAIRED", "UNKNOWN", "MISMATCHED", "UNRESOLVED"])
def test_terminal_unreconciled_restart_refuses_broker_access(paper_setup, status):
    db = paper_setup[-1]
    rc = replace(paper_setup[3], max_cycles=None, window_market_sessions=2)
    broker = FakeBroker()
    first = make_loop(
        paper_setup, broker=broker, run_config=rc, config=capped_config(),
        strategy=lambda frame, params: {"AAPL": 0.01},
    )
    first._bars_provider = lambda: (first._handle_sigterm(None, None) or bars())
    assert not first.run(bars(), db).halted
    conn = init_db(db)
    with conn:
        conn.execute("UPDATE orders_live SET reconciliation_status=?", (status,))
    conn.close()
    replacement = FakeBroker()
    result = make_loop(
        paper_setup, broker=replacement, run_config=rc, config=capped_config(),
        strategy=lambda frame, params: {"AAPL": 0.01},
    ).run(bars(), db)
    assert result.halted
    assert replacement.connections == 0 and replacement.submissions == []
