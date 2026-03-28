import pytest
from dataclasses import dataclass


@dataclass
class TestEvent:
    value: int


def test_sync_event_bus_dispatches_to_subscriber():
    from app.services.event_bus import SyncEventBus

    bus = SyncEventBus()
    received = []

    bus.subscribe(TestEvent, lambda e: received.append(e.value))
    bus.publish(TestEvent(value=42))

    assert received == [42]


def test_sync_event_bus_multiple_subscribers():
    from app.services.event_bus import SyncEventBus

    bus = SyncEventBus()
    log = []

    bus.subscribe(TestEvent, lambda e: log.append(f"a:{e.value}"))
    bus.subscribe(TestEvent, lambda e: log.append(f"b:{e.value}"))
    bus.publish(TestEvent(value=7))

    assert "a:7" in log
    assert "b:7" in log


def test_sync_event_bus_no_subscriber_no_error():
    from app.services.event_bus import SyncEventBus

    bus = SyncEventBus()
    # Should not raise even with no subscribers
    bus.publish(TestEvent(value=1))


def test_sync_event_bus_different_event_types_isolated():
    from app.services.event_bus import SyncEventBus

    @dataclass
    class OtherEvent:
        msg: str

    bus = SyncEventBus()
    test_log = []
    other_log = []

    bus.subscribe(TestEvent, lambda e: test_log.append(e.value))
    bus.subscribe(OtherEvent, lambda e: other_log.append(e.msg))

    bus.publish(TestEvent(value=99))
    assert test_log == [99]
    assert other_log == []
