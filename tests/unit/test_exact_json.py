"""Preserve nanosecond integers and refuse unrelated object coercion."""

import json

import numpy as np
import pytest

from research.exact_json import integer_default


def test_native_integer_clock_round_trips_exactly():
    value = np.int64(1727800077166707300)
    encoded = json.dumps({"clock": value}, default=integer_default, allow_nan=False)
    result = json.loads(encoded)["clock"]
    assert type(result) is int and result == int(value)


def test_no_array_or_float32_string_coercion():
    for value in (np.array([1, 2]), np.float32(1.25)):
        with pytest.raises(TypeError, match="Unsupported JSON type"):
            json.dumps({"value": value}, default=integer_default, allow_nan=False)
