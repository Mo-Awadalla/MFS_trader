"""Displayed single-instrument order state for native Nasdaq-normalized MBO records."""

import heapq
from dataclasses import dataclass


@dataclass(slots=True)
class Order:
    side: str
    price: int
    size: int
    priority: int


class Book:
    def __init__(self):
        self.orders = {}
        self.levels = {"A": {}, "B": {}}
        self.heaps = {"A": [], "B": []}
        self.initialized = False

    def _change(self, side, price, size_delta, count_delta):
        levels, heap = self.levels[side], self.heaps[side]
        old_size, old_count = levels.get(price, (0, 0))
        size, count = old_size + size_delta, old_count + count_delta
        assert size >= 0 and count >= 0 and (size == 0) == (count == 0)
        if size == 0:
            del levels[price]
        else:
            if old_size == 0:
                heapq.heappush(heap, price if side == "A" else -price)
            levels[price] = (size, count)
        if len(heap) > 2 * len(levels) + 1024:
            heap[:] = [p if side == "A" else -p for p in levels]
            heapq.heapify(heap)

    def apply(self, action, side, order_id, price, size, ordinal):
        if action == "R":
            self.orders.clear()
            for key in ("A", "B"):
                self.levels[key].clear()
                self.heaps[key].clear()
            self.initialized = True
            return
        assert self.initialized, "Order event before a known initial clear"
        if action in ("T", "F", "N"):
            return
        assert side in ("A", "B") and price is not None and price > 0 and size > 0
        if action == "A":
            assert order_id not in self.orders, "Duplicate outstanding order ID"
            self.orders[order_id] = Order(side, price, size, ordinal)
            self._change(side, price, size, 1)
        elif action == "C":
            assert order_id in self.orders, "Cancellation references an absent order"
            order = self.orders[order_id]
            assert (side, price) == (order.side, order.price) and size <= order.size
            self._change(side, price, -size, -int(size == order.size))
            order.size -= size
            if order.size == 0:
                del self.orders[order_id]
        elif action == "M":
            assert order_id in self.orders, "Modification references an absent order"
            order = self.orders[order_id]
            assert order.side == side
            priority = ordinal if price != order.price or size > order.size else order.priority
            self._change(side, order.price, -order.size, -1)
            self.orders[order_id] = Order(side, price, size, priority)
            self._change(side, price, size, 1)
        else:
            raise ValueError("Unsupported MBO action: " + action)

    def best(self, side):
        heap, levels = self.heaps[side], self.levels[side]
        while heap:
            price = heap[0] if side == "A" else -heap[0]
            if price in levels:
                return (price, *levels[price])
            heapq.heappop(heap)
        assert not levels
        return None, 0, 0

    def bbo(self):
        return self.best("B"), self.best("A")
