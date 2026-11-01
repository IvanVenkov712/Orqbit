from typing import Any

from event_dispatcher.events.event import Event


class ClaimJobEvent(Event):
    job_types: list[str]

class HeartbeatEvent(Event):
    claim_id: int

class CompleteEvent(Event):
    result: str | dict[str, Any]

class FailEvent(Event):
    error_type: str
    error_message: str
    error_details: dict[str, Any]