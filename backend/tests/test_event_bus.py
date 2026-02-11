"""Tests for EventBus in-process pub/sub."""

import asyncio

import pytest

from src.core.event_bus import EventBus, GoalEvent


@pytest.mark.asyncio
async def test_event_bus_publish_subscribe():
    bus = EventBus()
    queue = bus.subscribe("goal-1")
    await bus.publish(
        GoalEvent(
            goal_id="goal-1",
            user_id="user-1",
            event_type="progress.update",
            data={"progress": 50},
        )
    )
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event.event_type == "progress.update"
    assert event.data["progress"] == 50
    bus.unsubscribe("goal-1", queue)


@pytest.mark.asyncio
async def test_event_bus_multiple_subscribers():
    bus = EventBus()
    q1 = bus.subscribe("goal-1")
    q2 = bus.subscribe("goal-1")
    await bus.publish(
        GoalEvent(
            goal_id="goal-1",
            user_id="user-1",
            event_type="agent.started",
            data={"agent": "hunter"},
        )
    )
    e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert e1.event_type == e2.event_type
    bus.unsubscribe("goal-1", q1)
    bus.unsubscribe("goal-1", q2)


@pytest.mark.asyncio
async def test_event_bus_no_crosstalk():
    bus = EventBus()
    q1 = bus.subscribe("goal-1")
    q2 = bus.subscribe("goal-2")
    await bus.publish(
        GoalEvent(
            goal_id="goal-1",
            user_id="user-1",
            event_type="progress.update",
            data={},
        )
    )
    # q1 should have the event
    e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    assert e1.event_type == "progress.update"
    # q2 should be empty (different goal_id)
    assert q2.empty()
    bus.unsubscribe("goal-1", q1)
    bus.unsubscribe("goal-2", q2)


@pytest.mark.asyncio
async def test_event_bus_unsubscribe_cleanup():
    bus = EventBus()
    q = bus.subscribe("goal-1")
    assert "goal-1" in bus._subscribers
    bus.unsubscribe("goal-1", q)
    assert "goal-1" not in bus._subscribers


@pytest.mark.asyncio
async def test_event_bus_singleton():
    EventBus.reset()
    b1 = EventBus.get_instance()
    b2 = EventBus.get_instance()
    assert b1 is b2
    EventBus.reset()


@pytest.mark.asyncio
async def test_goal_event_to_dict():
    event = GoalEvent(
        goal_id="g1",
        user_id="u1",
        event_type="goal.complete",
        data={"result": "success"},
    )
    d = event.to_dict()
    assert d["goal_id"] == "g1"
    assert d["event_type"] == "goal.complete"
    assert "timestamp" in d
