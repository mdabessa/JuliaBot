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
