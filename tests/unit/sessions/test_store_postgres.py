"""Tests for the SQLAlchemy-backed session store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from juliabot.migrations import upgrade
from juliabot.sessions import (
    InteractionEvent,
    PostgresStore,
    Registration,
    Scope,
    Session,
    TriggerType,
)


class PersistedTestSession(Session):
    pass


def make_session(key: str = "message-1", timeout: float = 60) -> Session:
    registration = Registration(
        name="persisted",
        session_class=PersistedTestSession,
        trigger=TriggerType.COMPONENT,
        scope=Scope.USER,
        timeout=timeout,
        resumable=True,
    )
    return PersistedTestSession(
        registration,
        InteractionEvent(
            transport=TriggerType.COMPONENT,
            key=key,
            user_id=42,
            guild_id=7,
            channel_id=8,
            message_id=9,
        ),
        payload={"index": 2, "ids": [1, 2]},
    )


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    upgrade(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def store(engine):
    return PostgresStore(engine)


@pytest.mark.asyncio
async def test_save_and_load_round_trip(store):
    session = make_session()

    await store.save(session)
    record = await store.load(session.id)

    assert record is not None
    assert record.kind == "persisted"
    assert record.routing_key == "message-1"
    assert record.trigger is TriggerType.COMPONENT
    assert record.owner_id == 42
    assert record.guild_id == 7
    assert record.channel_id == 8
    assert record.message_id == 9
    assert record.payload == {"index": 2, "ids": [1, 2]}
    assert record.created_at.tzinfo is not None
    assert record.expires_at > record.created_at


@pytest.mark.asyncio
async def test_save_updates_an_existing_record(store, engine):
    session = make_session()
    await store.save(session)

    session.set_payload("index", 5)
    await store.save(session)

    record = await store.load(session.id)
    assert record.payload["index"] == 5

    with engine.connect() as connection:
        rows = connection.exec_driver_sql("SELECT COUNT(*) FROM session").scalar()
    assert rows == 1


@pytest.mark.asyncio
async def test_load_keys_skips_expired_records(store):
    expired = make_session("expired")
    expired.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    active = make_session("active")
    await store.save(expired)
    await store.save(active)

    records = await store.load_keys()

    assert [record.routing_key for record in records] == ["active"]


@pytest.mark.asyncio
async def test_delete_and_purge_expired(store):
    first = make_session("first")
    second = make_session("second")
    await store.save(first)
    await store.save(second)

    await store.delete(first.id)
    assert await store.load(first.id) is None

    removed = await store.purge_expired(datetime.now(timezone.utc) + timedelta(hours=1))

    assert removed == 1
    assert await store.load(second.id) is None


@pytest.mark.asyncio
async def test_store_uses_the_migrated_table(store, engine):
    await store.save(make_session())

    assert "session" in set(inspect(engine).get_table_names())
