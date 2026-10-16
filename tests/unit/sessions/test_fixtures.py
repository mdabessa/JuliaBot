"""Tests for the shared session fixtures themselves.

These keep the fixtures honest: phase 1 onwards relies on them, so a broken
fixture should fail here rather than in a confusing place later.
"""

from __future__ import annotations

import pytest


def test_fake_clock_advances_deterministically(fake_clock):
    start = fake_clock.now()

    fake_clock.advance(90)

    assert (fake_clock.now() - start).total_seconds() == 90


def test_fake_client_records_persistent_views(fake_client):
    view = object()

    fake_client.add_view(view)

    assert fake_client.views == [view]


@pytest.mark.asyncio
async def test_counting_store_records_every_call(counting_store):
    assert counting_store.count("load_keys") == 0

    await counting_store.load_keys()
    await counting_store.load("missing")
    await counting_store.delete("missing")

    assert counting_store.calls == ["load_keys", "load", "delete"]


@pytest.mark.asyncio
async def test_counting_store_round_trips_records(counting_store):
    session = type("Session", (), {"id": "abc"})()

    await counting_store.save(session)

    assert await counting_store.load("abc") is session

    await counting_store.delete("abc")

    assert await counting_store.load("abc") is None
