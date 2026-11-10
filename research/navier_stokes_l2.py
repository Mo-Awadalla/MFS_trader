"""Streaming full-depth features for the liquidity-concentration experiment."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np


def _lp(values: np.ndarray, order: float) -> float:
    values = np.abs(values[np.isfinite(values)])
    if values.size == 0:
        return 0.0
    if math.isinf(order):
        return float(values.max())
    return float(np.mean(values**order) ** (1.0 / order))


def _ratio(numerator: float, denominator: float, epsilon: float = 1e-12) -> float:
    return float(numerator / max(abs(denominator), epsilon))


@dataclass
class L2Book:
    """Absolute-size L2 book with per-window flow accounting."""

    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    directional_flow: dict[tuple[str, float], float] = field(default_factory=dict)
    additions: float = 0.0
    removals: float = 0.0
    positive_pressure: float = 0.0
    negative_pressure: float = 0.0
    event_count: int = 0
    event_subbins: np.ndarray = field(default_factory=lambda: np.zeros(100, dtype=np.int64))
    first_event_us: int | None = None
    last_event_us: int | None = None

    def apply(
        self,
        *,
        side: str,
        price: float,
        amount: float,
        is_snapshot: bool,
        timestamp_us: int,
        bin_start_us: int,
        bin_seconds: int,
    ) -> None:
        if side not in {"bid", "ask"}:
            raise ValueError(f"invalid side: {side}")
        book = self.bids if side == "bid" else self.asks
        old = book.get(price, 0.0)
        if amount <= 0.0:
            book.pop(price, None)
        else:
            book[price] = amount

        if is_snapshot:
            return
        delta = amount - old
        signed = delta if side == "bid" else -delta
        key = (side, price)
        self.directional_flow[key] = self.directional_flow.get(key, 0.0) + signed
        if delta >= 0.0:
            self.additions += delta
        else:
            self.removals -= delta
        if signed >= 0.0:
            self.positive_pressure += signed
        else:
            self.negative_pressure -= signed
        self.event_count += 1
        self.first_event_us = timestamp_us if self.first_event_us is None else self.first_event_us
        self.last_event_us = timestamp_us
        offset = max(0, timestamp_us - bin_start_us)
        index = min(len(self.event_subbins) - 1, int(offset * len(self.event_subbins) / (bin_seconds * 1_000_000)))
        self.event_subbins[index] += 1

    def reset_window(self) -> None:
        self.directional_flow.clear()
        self.additions = 0.0
        self.removals = 0.0
        self.positive_pressure = 0.0
        self.negative_pressure = 0.0
        self.event_count = 0
        self.event_subbins.fill(0)
        self.first_event_us = None
        self.last_event_us = None

    def features(self, *, levels: int, bin_seconds: int) -> dict[str, float]:
        if not self.bids or not self.asks:
            raise ValueError("both sides of book are required")
        bid_prices = heapq.nlargest(levels, self.bids)
        ask_prices = heapq.nsmallest(levels, self.asks)
        if len(bid_prices) < 2 or len(ask_prices) < 2:
            raise ValueError("insufficient book levels")
        best_bid, best_ask = bid_prices[0], ask_prices[0]
        if best_ask < best_bid:
            raise ValueError("crossed book")
        midpoint = (best_bid + best_ask) / 2.0
        prices = np.asarray([*reversed(bid_prices), *ask_prices], dtype=float)
        sides = [*["bid"] * len(bid_prices), *["ask"] * len(ask_prices)]
        ordered_prices = np.asarray([*reversed(bid_prices), *ask_prices], dtype=float)
        amounts = np.asarray(
            [*[self.bids[p] for p in reversed(bid_prices)], *[self.asks[p] for p in ask_prices]],
            dtype=float,
        )
        positions = 10_000.0 * (ordered_prices - midpoint) / midpoint
        total_depth = float(amounts.sum())
        normalized_depth = amounts / max(total_depth, 1e-12)
        edge_order = np.argsort(np.abs(positions))
        cumulative = np.cumsum(normalized_depth[edge_order])
        half_index = min(int(np.searchsorted(cumulative, 0.5)), len(edge_order) - 1)
        core_width = float(np.max(np.abs(positions[edge_order[: half_index + 1]])))

        flow_values = []
        for side, price, amount in zip(sides, prices, amounts, strict=True):
            flow = self.directional_flow.get((side, float(price)), 0.0)
            flow_values.append(flow / max(amount, 1e-9))
        velocity = np.asarray(flow_values, dtype=float) / bin_seconds
        l2 = _lp(velocity, 2.0)
        gradient = np.gradient(normalized_depth, positions)
        curvature = np.gradient(gradient, positions)

        centered = self.event_subbins.astype(float) - float(self.event_subbins.mean())
        power = np.abs(np.fft.rfft(centered)) ** 2
        freq = np.fft.rfftfreq(len(centered), d=bin_seconds / len(centered))
        high_power = float(power[(freq >= 1.0) & (freq <= 5.0)].sum())
        low_power = float(power[(freq >= 0.1) & (freq < 1.0)].sum())
        active_span = (
            (self.last_event_us - self.first_event_us) / 1_000_000.0
            if self.first_event_us is not None and self.last_event_us is not None
            else 0.0
        )
        mean_interevent_ms = (
            1_000.0 * active_span / max(self.event_count - 1, 1)
            if self.event_count > 1
            else bin_seconds * 1_000.0
        )
        bid_depth = float(sum(self.bids[p] for p in bid_prices))
        ask_depth = float(sum(self.asks[p] for p in ask_prices))
        replenishment = self.additions / max(total_depth * bin_seconds, 1e-12)
        transport = self.removals / max(total_depth * bin_seconds, 1e-12)
        gross_directional = self.positive_pressure + self.negative_pressure
        net_directional = self.positive_pressure - self.negative_pressure
        return {
            "midpoint": midpoint,
            "spread_bps": 10_000.0 * (best_ask - best_bid) / midpoint,
            "top_depth": total_depth,
            "book_imbalance": _ratio(bid_depth - ask_depth, bid_depth + ask_depth),
            "core_width_bps": core_width,
            "liquidity_linf_l2": _ratio(_lp(normalized_depth, math.inf), _lp(normalized_depth, 2.0)),
            "u_linf_l2": _ratio(_lp(velocity, math.inf), l2),
            "u_l4_l2": _ratio(_lp(velocity, 4.0), l2),
            "gradient_max": float(np.max(np.abs(gradient))),
            "gradient_energy": float(np.mean(gradient**2)),
            "curvature_energy": float(np.mean(curvature**2)),
            "book_flow_gross": gross_directional,
            "book_flow_net": net_directional,
            "gross_to_net_flow": _ratio(gross_directional, abs(net_directional) + 1.0),
            "opposing_flow_stress": _ratio(
                math.sqrt(self.positive_pressure * self.negative_pressure), total_depth
            ),
            "replenishment_rate": replenishment,
            "transport_rate": transport,
            "transport_to_replenishment": _ratio(transport, replenishment),
            "event_rate": self.event_count / bin_seconds,
            "mean_interevent_ms": mean_interevent_ms,
            "spectral_cascade_ratio": _ratio(high_power, low_power),
        }
