from typing import Any

from pydantic import HttpUrl

from event_dispatcher.events.event import Event

class CreateTaskEvent(Event):
    webhook_url: HttpUrl
    type: str
    payload: dict[str, Any]

class GetJobEvent(Event):
    job_id: int

