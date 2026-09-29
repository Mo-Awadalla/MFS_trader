"""The test session must not reach broker or market-data hosts by accident."""

from __future__ import annotations

import socket

import pytest

from tests.conftest import BlockedNetworkError


@pytest.mark.parametrize(
    "address",
    [("paper-api.alpaca.markets", 443), ("192.0.2.10", 443), ("2001:db8::1", 443)],
)
def test_external_connections_are_blocked(address):
    with pytest.raises(BlockedNetworkError):
        socket.create_connection(address, timeout=1)


def test_requests_to_broker_host_are_blocked_not_retried_as_connection_errors():
    import requests

    with pytest.raises(BlockedNetworkError):
        requests.get("https://paper-api.alpaca.markets/v2/account", timeout=1)


def test_loopback_connections_remain_available():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            accepted, _ = server.accept()
            accepted.close()


def test_external_datagrams_are_blocked():
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client,
        pytest.raises(BlockedNetworkError),
    ):
        client.sendto(b"offline guard probe", ("192.0.2.10", 443))


def test_legacy_dns_lookup_is_blocked():
    with pytest.raises(BlockedNetworkError):
        socket.gethostbyname("paper-api.alpaca.markets")
