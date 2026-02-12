"""Telemetry events."""

from typing import Any


class EventEmitter:
    """Event emitter."""

    def emit(self, event_name: str, data: dict[str, Any]) -> None:
        """Emit an event."""
        pass
