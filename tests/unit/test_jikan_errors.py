import asyncio

import aiohttp
import pytest

from juliabot import jikan_catalog as catalog
from juliabot import jikan_errors


def _response_error(status, headers=None):
    return aiohttp.ClientResponseError(
        request_info=None,
        history=(),
        status=status,
        message="boom",
        headers=headers or {},
    )


@pytest.fixture(autouse=True)
def reset_guard():
    jikan_errors.GUARD.reset()
    yield
    jikan_errors.GUARD.reset()


@pytest.fixture
def guard():
    return jikan_errors.RateLimitGuard()


@pytest.fixture(scope="module")
def spec() -> catalog.RouteSpec:
    return next(
        spec for spec in catalog.load_specs() if spec.route == "get_anime_themes"
    )


class FlakyClient:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    async def get_anime_themes(self, **_kwargs):
        self.calls += 1
        raise self.error


class OkClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def get_anime_themes(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, "A API recusou os parâmetros dessa consulta."),
        (401, "A API bloqueou essa consulta."),
        (403, "A API bloqueou essa consulta."),
        (404, "Não encontrei nada com esse id ou critério."),
        (418, "A API respondeu com erro 418."),
        (500, "A API do MyAnimeList está instável agora."),
        (503, "A API do MyAnimeList está instável agora."),
    ],
)
def test_status_messages(status, expected):
    error = jikan_errors.translate(_response_error(status))

    assert str(error).startswith(expected)


def test_404_is_friendly_for_an_invalid_id(spec, guard):
    client = FlakyClient(_response_error(404))

    with pytest.raises(jikan_errors.JikanCallError) as excinfo:
        asyncio.run(jikan_errors.call_route(client, spec, {"anime_id": 0}, guard=guard))

    assert "Não encontrei nada" in str(excinfo.value)
    assert guard.remaining() == 0


def test_429_uses_the_retry_after_header(spec, guard):
    client = FlakyClient(_response_error(429, {"Retry-After": "42"}))

    with pytest.raises(jikan_errors.JikanCallError) as excinfo:
        asyncio.run(jikan_errors.call_route(client, spec, {"anime_id": 1}, guard=guard))

    message = str(excinfo.value)
    assert "limitando as requisições" in message
    assert "42s" in message
    assert guard.remaining() > 40


def test_429_without_header_uses_the_default_window(spec, guard):
    client = FlakyClient(_response_error(429))

    with pytest.raises(jikan_errors.JikanCallError):
        asyncio.run(jikan_errors.call_route(client, spec, {"anime_id": 1}, guard=guard))

    assert guard.remaining() == pytest.approx(jikan_errors.DEFAULT_RETRY_AFTER, abs=2)


def test_retry_after_is_capped(spec, guard):
    client = FlakyClient(_response_error(429, {"Retry-After": "99999"}))

    with pytest.raises(jikan_errors.JikanCallError):
        asyncio.run(jikan_errors.call_route(client, spec, {"anime_id": 1}, guard=guard))

    assert guard.remaining() <= jikan_errors.MAX_RETRY_AFTER


def test_unparseable_retry_after_falls_back_to_the_default(spec, guard):
    client = FlakyClient(
        _response_error(429, {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
    )

    with pytest.raises(jikan_errors.JikanCallError):
        asyncio.run(jikan_errors.call_route(client, spec, {"anime_id": 1}, guard=guard))

    assert guard.remaining() == pytest.approx(jikan_errors.DEFAULT_RETRY_AFTER, abs=2)


def test_a_blocked_guard_refuses_calls_without_hitting_the_api(spec, guard):
    guard.block(20)
    client = OkClient({"data": {}})

    with pytest.raises(jikan_errors.JikanCallError) as excinfo:
        asyncio.run(jikan_errors.call_route(client, spec, {"anime_id": 1}, guard=guard))

    assert "limitando as requisições" in str(excinfo.value)
    assert client.calls == []


def test_a_reset_guard_allows_calls_again(spec, guard):
    guard.block(20)
    guard.reset()
    client = OkClient({"data": {}})

    payload = asyncio.run(
        jikan_errors.call_route(client, spec, {"anime_id": 1}, guard=guard)
    )

    assert payload == {"data": {}}


def test_timeouts_are_reported(spec, guard):
    client = FlakyClient(asyncio.TimeoutError())

    with pytest.raises(jikan_errors.JikanCallError) as excinfo:
        asyncio.run(jikan_errors.call_route(client, spec, {"anime_id": 1}, guard=guard))

    assert "demorou demais" in str(excinfo.value)


def test_connection_errors_are_reported(spec, guard):
    client = FlakyClient(aiohttp.ClientConnectionError("down"))

    with pytest.raises(jikan_errors.JikanCallError) as excinfo:
        asyncio.run(jikan_errors.call_route(client, spec, {"anime_id": 1}, guard=guard))

    assert "Não consegui falar com a API" in str(excinfo.value)


def test_invalid_json_is_reported(spec, guard):
    error = aiohttp.ContentTypeError(request_info=None, history=())
    client = FlakyClient(error)

    with pytest.raises(jikan_errors.JikanCallError) as excinfo:
        asyncio.run(jikan_errors.call_route(client, spec, {"anime_id": 1}, guard=guard))

    assert "formato inesperado" in str(excinfo.value)


def test_unknown_failures_get_a_generic_message():
    assert "Não foi possível concluir" in str(jikan_errors.translate(ValueError("x")))


def test_successful_calls_return_the_payload(spec, guard):
    client = OkClient({"data": {"openings": ["OP1"]}})

    payload = asyncio.run(
        jikan_errors.call_route(client, spec, {"anime_id": 1}, guard=guard)
    )

    assert payload == {"data": {"openings": ["OP1"]}}
    assert client.calls == [{"anime_id": 1}]


def test_the_guard_is_shared_by_default(spec):
    jikan_errors.GUARD.reset()
    jikan_errors.GUARD.block(5)
    client = OkClient({"data": {}})

    try:
        with pytest.raises(jikan_errors.JikanCallError):
            asyncio.run(jikan_errors.call_route(client, spec, {"anime_id": 1}))
    finally:
        jikan_errors.GUARD.reset()

    assert client.calls == []
