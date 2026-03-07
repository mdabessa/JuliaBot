from types import SimpleNamespace

from pydantic import BaseModel

from juliabot.ai import ResponseFormat, generate_response


class CustomFormat(BaseModel):
    answer: str


def test_generate_response_uses_provider_and_returns_response(monkeypatch):
    calls = {}

    class FakeClient:
        def create(self, response_model, messages):
            calls["response_model"] = response_model
            calls["messages"] = messages
            return ResponseFormat(response="ok")

    def fake_from_provider(model, base_url):
        calls["model"] = model
        calls["base_url"] = base_url
        return FakeClient()

    monkeypatch.setattr("juliabot.ai.instructor.from_provider", fake_from_provider)

    messages = [{"role": "user", "content": "hello"}]
    response = generate_response(messages)

    assert response.response == "ok"
    assert calls["model"] == "deepseek/deepseek-chat"
    assert calls["base_url"] == "https://api.deepseek.com"
    assert calls["response_model"] is ResponseFormat
    assert calls["messages"] == messages


def test_generate_response_custom_format(monkeypatch):
    class FakeClient:
        def create(self, response_model, messages):
            assert response_model is CustomFormat
            return CustomFormat(answer="42")

    monkeypatch.setattr(
        "juliabot.ai.instructor.from_provider",
        lambda *args, **kwargs: FakeClient(),
    )

    response = generate_response([{"role": "user", "content": "q"}], CustomFormat)
    assert response.answer == "42"
