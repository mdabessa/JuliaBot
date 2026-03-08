from types import SimpleNamespace

import pytest

from juliabot.cogs.game import GameCog, GameResponse, GameSession


def test_game_session_context_contains_system_and_messages():
    session = GameSession(channel_id=10)
    session.add_message("user", "hello")

    context = session.get_context()

    assert context[0]["role"] == "system"
    assert context[1] == {"role": "user", "content": "hello"}


@pytest.mark.asyncio
async def test_start_play_end_game_flow(monkeypatch):
    class FakeResp:
        def __init__(self, response=None, game_response=None, grammar_correction=None):
            self.response = response
            self.game_response = game_response
            self.grammar_correction = grammar_correction

    responses = [
        FakeResp(response="Start"),
        GameResponse(game_response="Action result", grammar_correction="fixed"),
    ]

    monkeypatch.setattr(
        "juliabot.cogs.game.generate_response", lambda *a, **k: responses.pop(0)
    )

    sent = []

    async def send(msg):
        sent.append(msg)

    ctx = SimpleNamespace(channel=SimpleNamespace(id=42), send=send)
    cog = GameCog(bot=SimpleNamespace())

    await GameCog.start_game.callback(cog, ctx, seed="abc")
    await GameCog.play.callback(cog, ctx, action="go north")
    await GameCog.end_game.callback(cog, ctx)

    assert sent[0] == "Start"
    assert "Action result" in sent[1]
    assert "Grammar Correction" in sent[1]
    assert "encerrada" in sent[2]
    assert 42 not in cog.sessions
