"""Tests for the Phase 1 in-memory store."""

from datetime import datetime, timedelta, timezone

import pytest

from juliabot.sessions import (
    InteractionEvent,
    MemoryStore,
    Registration,
    Scope,
    Session,
    TriggerType,
)


class StoredTestSession(Session):
    pass


def make_session(key: str = "message-1", *, timeout: float = 60) -> Session:
    registration = Registration(
        name="stored",
        session_class=StoredTestSession,
        trigger=TriggerType.COMPONENT,
        scope=Scope.USER,
        timeout=timeout,
        resumable=True,
    )
    return StoredTestSession(
        registration,
        InteractionEvent(
            transport=TriggerType.COMPONENT,
            key=key,
            user_id=42,
            channel_id=7,
            message_id=8,
        ),
        payload={"index": 3, "ids": [1, 2]},
    )


@pytest.mark.asyncio
async def test_memory_store_round_trips_a_defensive_snapshot():
    store = MemoryStore()
    session = make_session()

    await store.save(session)
    record = await store.load(session.id)

    assert record is not None
    assert record.kind == "stored"
    assert record.routing_key == "message-1"
    assert record.payload == {"index": 3, "ids": [1, 2]}
    assert record.trigger is TriggerType.COMPONENT

    record.payload["ids"].append(99)

    fresh_record = await store.load(session.id)
    assert fresh_record.payload == {"index": 3, "ids": [1, 2]}


@pytest.mark.asyncio
async def test_memory_store_load_keys_returns_saved_records():
    store = MemoryStore()
    first = make_session("first")
    second = make_session("second")

    await store.save(first)
    await store.save(second)

    assert {record.routing_key for record in await store.load_keys()} == {
        "first",
        "second",
    }


@pytest.mark.asyncio
async def test_memory_store_delete_and_purge_expired_records():
    store = MemoryStore()
    keep = make_session("keep", timeout=60)
    expire = make_session("expire", timeout=1)
    await store.save(keep)
    await store.save(expire)

    await store.delete(keep.id)
    removed = await store.purge_expired(
        datetime.now(timezone.utc) + timedelta(seconds=2)
    )

    assert removed == 1
    assert await store.load(keep.id) is None
    assert await store.load(expire.id) is None
