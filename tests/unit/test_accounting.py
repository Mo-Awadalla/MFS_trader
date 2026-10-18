from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from execution.base import BrokerAccount
from portfolio.accounting import AccountRiskRepository, PortfolioSnapshot
from storage.schema import init_db


def _snapshot(
    *, when: datetime, cash: float, equity: float, flow: float | None = 0.0,
    allow_new_baseline: bool = False,
) -> PortfolioSnapshot:
    return PortfolioSnapshot.from_broker(
        "offline",
        BrokerAccount("account-1", cash=cash, equity=equity),
        [],
        [],
        pending_orders_complete=True,
        pending_orders_observed_at=when,
        pending_orders_source="synthetic_fixture",
        observed_at=when,
        external_cash_flow=flow,
        allow_new_baseline=allow_new_baseline,
    )


def test_account_snapshot_rejects_stale_and_inconsistent_values():
    now = datetime(2026, 10, 18, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="stale"):
        _snapshot(when=now - timedelta(minutes=2), cash=100, equity=100).validate(now=now)
    with pytest.raises(ValueError, match="inconsistent"):
        _snapshot(when=now, cash=100, equity=150).validate(now=now)


def test_period_baselines_survive_restart_and_separate_cash_flows():
    conn = init_db(":memory:")
    first = datetime.now(UTC)
    repo = AccountRiskRepository(conn)
    initial = repo.record(_snapshot(when=first, cash=100, equity=100, allow_new_baseline=True))
    assert (initial.daily_pnl, initial.weekly_pnl, initial.monthly_pnl) == (0, 0, 0)

    after_loss = repo.record(_snapshot(when=datetime.now(UTC), cash=90, equity=90))
    assert (after_loss.daily_pnl, after_loss.weekly_pnl, after_loss.monthly_pnl) == (-10, -10, -10)

    restarted = AccountRiskRepository(conn)
    after_deposit = restarted.record(
        _snapshot(when=datetime.now(UTC), cash=110, equity=110, flow=20)
    )
    assert (after_deposit.daily_pnl, after_deposit.weekly_pnl, after_deposit.monthly_pnl) == (-10, -10, -10)
    count = conn.execute("SELECT COUNT(*) FROM account_risk_snapshots").fetchone()[0]
    assert count == 3
    conn.close()


def test_missing_flow_evidence_after_baseline_fails_closed():
    conn = init_db(":memory:")
    repo = AccountRiskRepository(conn)
    repo.record(_snapshot(when=datetime.now(UTC), cash=100, equity=100, flow=None, allow_new_baseline=True))
    with pytest.raises(ValueError, match="external cash-flow evidence"):
        repo.record(_snapshot(when=datetime.now(UTC), cash=100, equity=100, flow=None))
    conn.close()


def test_missing_current_period_baseline_fails_closed():
    conn = init_db(":memory:")
    repo = AccountRiskRepository(conn)
    repo.record(_snapshot(when=datetime.now(UTC), cash=100, equity=100, allow_new_baseline=True))
    conn.execute("DELETE FROM account_risk_periods WHERE period_kind='D'")
    conn.commit()
    with pytest.raises(ValueError, match="daily risk baseline history is missing"):
        repo.record(_snapshot(when=datetime.now(UTC), cash=100, equity=100))
    conn.close()


def test_existing_account_with_new_database_cannot_seed_midperiod_zero_pnl():
    conn = init_db(":memory:")
    repo = AccountRiskRepository(conn)
    with pytest.raises(ValueError, match="baseline initialization is permitted only"):
        repo.record(_snapshot(when=datetime.now(UTC), cash=90, equity=90))
    assert conn.execute("SELECT COUNT(*) FROM account_risk_snapshots").fetchone()[0] == 0
    conn.close()
