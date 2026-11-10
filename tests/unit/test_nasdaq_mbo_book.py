"""Book lifecycle regressions required before using MBO for queue research."""

import pytest

from research.nasdaq_mbo_book import Book


def initialized():
    book = Book()
    book.apply("R", "N", 0, None, 0, 0)
    return book


def test_fill_and_trade_do_not_double_remove_cancelled_volume():
    book = initialized()
    book.apply("A", "B", 1, 100, 100, 1)
    book.apply("T", "A", 0, 100, 40, 2)
    book.apply("F", "B", 1, 100, 40, 3)
    assert book.best("B") == (100, 100, 1)
    book.apply("C", "B", 1, 100, 40, 4)
    assert book.best("B") == (100, 60, 1)


def test_multiple_orders_aggregate_and_full_cancel_exposes_next_level():
    book = initialized()
    book.apply("A", "A", 1, 102, 20, 1)
    book.apply("A", "A", 2, 102, 30, 2)
    book.apply("A", "A", 3, 103, 40, 3)
    assert book.best("A") == (102, 50, 2)
    book.apply("C", "A", 1, 102, 20, 4)
    book.apply("C", "A", 2, 102, 30, 5)
    assert book.best("A") == (103, 40, 1)


def test_modified_order_loses_priority_only_for_price_or_size_increase():
    book = initialized()
    book.apply("A", "B", 1, 100, 100, 1)
    book.apply("M", "B", 1, 100, 80, 2)
    assert book.orders[1].priority == 1
    book.apply("M", "B", 1, 100, 90, 3)
    assert book.orders[1].priority == 3
    book.apply("M", "B", 1, 101, 90, 4)
    assert book.best("B") == (101, 90, 1) and book.orders[1].priority == 4


def test_uninitialized_missing_duplicate_and_overcancel_rejected():
    book = Book()
    with pytest.raises(AssertionError):
        book.apply("A", "A", 1, 100, 10, 0)
    book = initialized()
    with pytest.raises(AssertionError):
        book.apply("C", "A", 1, 100, 10, 1)
    book.apply("A", "A", 1, 100, 10, 1)
    with pytest.raises(AssertionError):
        book.apply("A", "A", 1, 100, 10, 2)
    with pytest.raises(AssertionError):
        book.apply("C", "A", 1, 100, 11, 3)


def test_clear_removes_all_levels_and_allows_order_id_reuse():
    book = initialized()
    book.apply("A", "B", 1, 100, 10, 1)
    book.apply("R", "N", 0, None, 0, 2)
    assert book.bbo() == ((None, 0, 0), (None, 0, 0))
    book.apply("A", "A", 1, 102, 20, 3)
    assert book.best("A") == (102, 20, 1)
