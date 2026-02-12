"""Serialization utilities.

Provides helpers for JSON serialization, handling types like Decimal.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def json_serializer(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default json code.

    Args:
        obj: Object to serialize

    Returns:
        Serializable representation (e.g. float for Decimal)
    """
    if isinstance(obj, Decimal):
        # Return as float for JSON compatibility
        # Precision loss is acceptable for output representation
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")
