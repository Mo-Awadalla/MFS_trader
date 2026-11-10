"""Serialize NumPy integer scalars without a float round trip or broad fallback."""

import numpy as np


def integer_default(value):
    if isinstance(value, np.integer):
        return int(value)
    raise TypeError(f"Unsupported JSON type: {type(value).__name__}")
