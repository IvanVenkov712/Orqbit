import asyncio
from collections import defaultdict
from typing import Callable, Awaitable

from event_dispatcher.events.event import Event

EventCallback = Callable[[Event], Awaitable[None]]

class EventBus:

    def __init__(self):
        self.subscribers: dict[type[Event], list[EventCallback]] = defaultdict(list)

    def subscribe(self, event_type: type[Event], callback: EventCallback):
        self.subscribers[event_type].append(callback)

    async def dispatch_event(self, event: Event):
        await asyncio.gather(
            *(subscriber(event) for subscriber in self.subscribers[type(event)])
        )