"""Characterization tests for the legacy ``Script`` engine.

These pin the current behavior of ``juliabot.scripts`` — including its quirks — so
the session framework migration can prove parity. The engine is removed in phase 8,
at which point this module is deleted.
"""

import asyncio
import warnings

import pytest

from juliabot.scripts import Script


@pytest.fixture(autouse=True)
def reset_script_state():
    Script.index = 0
    Script.functions = []
    Script.scripts = []
    yield
    Script.index = 0
    Script.functions = []
    Script.scripts = []


def test_script_register_and_fetch_function():
    @Script.function(name="echo", events=["on_message"], limit_by_name=2)
    async def handler(*args, **kwargs):
        return None

    funcs = Script.fetch_function("echo")
    assert len(funcs) == 1
    assert funcs[0]["name"] == "echo"
    assert funcs[0]["events"] == ["on_message"]


@pytest.mark.asyncio
async def test_script_execute_and_auto_close():
    @Script.function(name="run_once")
    async def run_once(*args, **kwargs):
        kwargs["cache"]["status"] = 0

    s = Script("worker", "run_once")
    assert s in Script.get_scripts()

    await s.execute()

    assert s not in Script.get_scripts()


def test_script_limit_by_name_closes_oldest():
    @Script.function(name="limited", limit_by_name=1)
    async def limited(*args, **kwargs):
        return None

    first = Script("same", "limited")
    second = Script("same", "limited")

    scripts = Script.get_scripts()
    assert first not in scripts
    assert second in scripts


def test_fetch_script_by_script_function_and_cache():
    @Script.function(name="f", events=["on_message", "on_edit"])
    async def f(*args, **kwargs):
        return None

    s = Script("abc", "f")
    s.cache["tag"] = "x"

    by_ref = Script.fetch_script("abc", by="refname", _in="script")
    by_event = Script.fetch_script("on_edit", by="events", _in="function")
    by_cache = Script.fetch_script("x", by="tag", _in="cache")

    assert s in by_ref
    assert s in by_event
    assert s in by_cache


def test_script_decorator_defaults_to_on_message_trigger():
    @Script.function(name="defaulted")
    async def defaulted(*args, **kwargs):
        return None

    func = Script.fetch_function("defaulted")[0]

    assert func["events"] == ["on_message"]
    assert func["limit_by_name"] == 1


def test_script_decorator_wrapper_discards_the_coroutine():
    # The decorator returns a *sync* wrapper that calls the coroutine and throws the
    # result away, so the decorated name is no longer an awaitable API.
    @Script.function(name="trapped")
    async def trapped(*args, **kwargs):
        return "unreachable"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        assert trapped() is None

    assert len(Script.fetch_function("trapped")) == 1


def test_script_instance_mangles_name_and_keeps_refname():
    @Script.function(name="f")
    async def f(*args, **kwargs):
        return None

    script = Script("abc", "f")

    assert script.name == "abc_ind0"
    assert script.refname == "abc"
    assert Script.index == 1


def test_script_with_unknown_function_raises():
    with pytest.raises(Exception, match="Nenhuma função registrada"):
        Script("abc", "does_not_exist")


def test_close_is_not_idempotent():
    @Script.function(name="f")
    async def f(*args, **kwargs):
        return None

    script = Script("abc", "f")
    script.close()

    with pytest.raises(ValueError):
        script.close()


@pytest.mark.asyncio
async def test_status_false_closes_because_false_equals_zero():
    @Script.function(name="falsy")
    async def falsy(*args, **kwargs):
        kwargs["cache"]["status"] = False

    script = Script("worker", "falsy")

    await script.execute()

    assert script not in Script.get_scripts()


@pytest.mark.asyncio
async def test_status_string_zero_does_not_close():
    @Script.function(name="stringy")
    async def stringy(*args, **kwargs):
        kwargs["cache"]["status"] = "0"

    script = Script("worker", "stringy")

    await script.execute()

    assert script in Script.get_scripts()


@pytest.mark.asyncio
async def test_execute_refreshes_last_execute():
    @Script.function(name="tick")
    async def tick(*args, **kwargs):
        await asyncio.sleep(0.02)

    script = Script("worker", "tick")
    before = script.last_execute

    await script.execute()

    assert script.last_execute > before


@pytest.mark.asyncio
async def test_execute_error_propagates_and_skips_last_execute_update():
    @Script.function(name="boom")
    async def boom(*args, **kwargs):
        raise RuntimeError("boom")

    script = Script("worker", "boom")
    before = script.last_execute

    with pytest.raises(RuntimeError):
        await script.execute()

    assert script.last_execute == before
    assert script in Script.get_scripts()


def test_limit_by_name_is_scoped_to_the_refname():
    @Script.function(name="limited", limit_by_name=1)
    async def limited(*args, **kwargs):
        return None

    first = Script("a", "limited")
    second = Script("b", "limited")
    scripts = Script.get_scripts()

    assert first in scripts
    assert second in scripts


def test_message_dispatch_only_sees_live_instances():
    # CoreCog.on_message scans *instances* whose registered function listens to
    # "on_message" rather than the registrations themselves, so the path can only
    # react to already spawned sessions. No production function registers
    # "on_message" today, which makes the loop a no-op.
    @Script.function(name="on_msg", events=["on_message"])
    async def on_msg(*args, **kwargs):
        return None

    assert Script.fetch_script("on_message", by="events", _in="function") == []

    script = Script("chan", "on_msg")

    assert Script.fetch_script("on_message", by="events", _in="function") == [script]


def test_fetch_script_swallows_missing_attributes():
    @Script.function(name="f")
    async def f(*args, **kwargs):
        return None

    Script("abc", "f")

    assert Script.fetch_script("x", by="missing", _in="script") == []
    assert Script.fetch_script("x", by="missing", _in="cache") == []
    assert Script.fetch_script("x", by="missing", _in="function") == []


def test_get_scripts_returns_a_copy():
    @Script.function(name="f")
    async def f(*args, **kwargs):
        return None

    script = Script("abc", "f")
    scripts = Script.get_scripts()
    scripts.clear()

    assert Script.get_scripts() == [script]
