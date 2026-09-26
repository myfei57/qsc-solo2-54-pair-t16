"""加注队列与并发确认。"""

from __future__ import annotations

import pytest

from hydrorefuel.errors import InterlockError


def test_queue_is_first_come_first_served(platform):
    platform.enqueue_vehicle("v1")
    platform.enqueue_vehicle("v2")
    assert platform.queue.position("v2") == 2
    assert platform.queue.waiting()[0]["vehicle"] == "v1"
    assert platform.dequeue_vehicle()["vehicle"] == "v1"
    assert platform.queue.size() == 1


def test_queue_capacity_is_limited(platform):
    for index in range(platform.config.queue.max_waiting):
        platform.enqueue_vehicle(f"v{index}")
    with pytest.raises(InterlockError):
        platform.enqueue_vehicle("overflow")


def test_confirmation_accepts_only_the_first(platform, clock):
    confirm = platform.confirm
    confirm.open("v1", clock.now())
    assert confirm.confirm("v1", clock.now() + 1.0) is True
    assert confirm.confirm("v1", clock.now() + 2.0) is False
    assert confirm.outstanding() == []
    confirm.open("v2", clock.now())
    assert confirm.pending("v2") is True
    clock.advance(platform.config.queue.confirm_timeout_s + 1.0)
    assert confirm.expired("v2", clock.now()) is True
    assert confirm.clear("v2") is True
