"""ID generation utilities."""

import uuid


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


def generate_short_id() -> str:
    """Generate a short unique ID."""
    return str(uuid.uuid4())[:12]
