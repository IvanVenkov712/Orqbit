from typing import Type, Callable, Any

from event_dispatcher.events.event import Event

EventCallback = Callable[[Any], Any]

class EventDispatcher:
    callbacks: dict[type[Event], list[EventCallback]]

    def __init__(self):
        self.callbacks = {}

    def subscribe(self, event_type: type[Event], callback: EventCallback):
        self.callbacks.setdefault(event_type, []).append(callback)

    def dispatch_event(self, event: Event):
        ev_type = type(event)
        if ev_type not in self.callbacks:
            raise ValueError("This type of event is not registered")

        return [
            callback(event) for callback in self.callbacks.get(ev_type, [])
        ]