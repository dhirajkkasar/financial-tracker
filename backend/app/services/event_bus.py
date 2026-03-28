"""
Lightweight synchronous event bus — no external dependencies.

Usage:
    bus = SyncEventBus()
    bus.subscribe(ImportCompletedEvent, corp_actions_service.on_import_completed)
    bus.publish(ImportCompletedEvent(asset_id=1, asset_type=AssetType.STOCK_IN, inserted_count=5))

Adding a new observer: bus.subscribe(EventType, handler_fn). No changes to publishers.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Protocol

from app.models.asset import AssetType


@dataclass
class ImportCompletedEvent:
    """Published after ImportOrchestrator.commit() succeeds."""
    asset_id: int
    asset_type: AssetType
    inserted_count: int


class IEventBus(Protocol):
    def publish(self, event: object) -> None: ...
    def subscribe(self, event_type: type, handler: Callable) -> None: ...


class SyncEventBus:
    """
    Synchronous in-process event bus. Handlers are called in subscription order.

    If a handler raises, the exception propagates (fail-fast). Wrap handlers
    in try/except if you need fault isolation.
    """

    def __init__(self):
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: object) -> None:
        for handler in self._handlers.get(type(event), []):
            handler(event)
