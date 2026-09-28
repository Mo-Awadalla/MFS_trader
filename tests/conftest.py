"""Pytest configuration — skip live_broker tests and block external network by default."""

from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path

import pytest


class BlockedNetworkError(RuntimeError):
    """A test tried to reach a non-loopback host without RUN_LIVE_BROKER_TESTS=1.

    Deliberately not an ``OSError``: HTTP clients must not swallow it as a
    retryable connection failure.
    """


_ORIGINAL_NETWORK: dict[str, object] = {}


def _live_network_allowed() -> bool:
    return os.environ.get("RUN_LIVE_BROKER_TESTS", "0") == "1"


def _is_local_host(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    text = str(host).strip("[]").split("%", 1)[0]
    if text.lower() in {"", "localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    return address.is_loopback


def _check_address(address: object) -> None:
    if isinstance(address, str | bytes):  # AF_UNIX path
        return
    host = address[0] if isinstance(address, tuple) and address else address
    if not _is_local_host(host):
        raise BlockedNetworkError(
            f"Network access to {host!r} is blocked in tests; "
            "set RUN_LIVE_BROKER_TESTS=1 only for explicit live-broker runs"
        )


def _install_network_guard() -> None:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    original_sendto = socket.socket.sendto
    original_gethostbyname = socket.gethostbyname
    original_gethostbyname_ex = socket.gethostbyname_ex
    _ORIGINAL_NETWORK.update(
        connect=original_connect,
        connect_ex=original_connect_ex,
        getaddrinfo=original_getaddrinfo,
        sendto=original_sendto,
        gethostbyname=original_gethostbyname,
        gethostbyname_ex=original_gethostbyname_ex,
    )

    def guarded_connect(self, address):
        _check_address(address)
        return original_connect(self, address)

    def guarded_connect_ex(self, address):
        _check_address(address)
        return original_connect_ex(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        _check_address((host,))
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_sendto(self, data, *args):
        _check_address(args[-1])
        return original_sendto(self, data, *args)

    def guarded_gethostbyname(host):
        _check_address((host,))
        return original_gethostbyname(host)

    def guarded_gethostbyname_ex(host):
        _check_address((host,))
        return original_gethostbyname_ex(host)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.getaddrinfo = guarded_getaddrinfo
    socket.socket.sendto = guarded_sendto
    socket.gethostbyname = guarded_gethostbyname
    socket.gethostbyname_ex = guarded_gethostbyname_ex


def pytest_configure(config):
    """Block external network unless live-broker tests are explicitly enabled.

    Optionally load .env before test collection for explicit live-broker runs.
    """
    if not _live_network_allowed():
        _install_network_guard()

    if not _live_network_allowed() or os.environ.get("MFS_TEST_LOAD_DOTENV", "0") != "1":
        return

    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def pytest_unconfigure(config):
    if not _ORIGINAL_NETWORK:
        return
    socket.socket.connect = _ORIGINAL_NETWORK.pop("connect")
    socket.socket.connect_ex = _ORIGINAL_NETWORK.pop("connect_ex")
    socket.getaddrinfo = _ORIGINAL_NETWORK.pop("getaddrinfo")
    socket.socket.sendto = _ORIGINAL_NETWORK.pop("sendto")
    socket.gethostbyname = _ORIGINAL_NETWORK.pop("gethostbyname")
    socket.gethostbyname_ex = _ORIGINAL_NETWORK.pop("gethostbyname_ex")


def pytest_collection_modifyitems(config, items):
    """Skip live_broker tests unless RUN_LIVE_BROKER_TESTS=1 is set."""
    if os.environ.get("RUN_LIVE_BROKER_TESTS", "0") == "1":
        return

    skip_live = pytest.mark.skip(reason="live_broker tests require RUN_LIVE_BROKER_TESTS=1")
    for item in items:
        if "live_broker" in item.keywords:
            item.add_marker(skip_live)
