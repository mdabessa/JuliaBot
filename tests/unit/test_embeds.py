import datetime
from types import SimpleNamespace

import pytest
import pytz

from juliabot.embeds.anime import anime_embed, episode_embed
from juliabot.embeds.reminder import reminder_embed


def test_anime_embed_builds_expected_fields():
    anime = SimpleNamespace(
        title="Title",
        url="https://example.org/anime",
        synopsis="desc",
        episodes=12,
        score=8.7,
        type="TV",
        airing=True,
        mal_id=10,
        images=SimpleNamespace(jpg=SimpleNamespace(image_url="https://img")),
    )

    embed = anime_embed(anime, color=0x123456)

    assert embed.title == "Title"
    assert str(embed.url) == "https://example.org/anime"
    assert embed.description == "desc"
    assert embed.fields[-1].name == "Links:"


def test_episode_embed_includes_dubbed_label():
    anime = SimpleNamespace(
        name="Anime",
        url="https://example.org/ep",
        episode=5,
        dubbed=True,
        image="https://img",
        site="Site",
        lang="pt-BR",
        mal_id=1,
    )

    embed = episode_embed(anime, color=0x111111)

    assert embed.title == "Anime"
    assert "Dublado" in embed.description
    assert "mal_id: 1" in embed.footer.text


@pytest.mark.asyncio
async def test_reminder_embed_without_recurrence():
    reminder = SimpleNamespace(
        channel_id="999",
        date_command=None,
        get_date_str=lambda: "01/01/2025 10:00 [UTC]",
        get_created_str=lambda: "01/01/2025 09:00 [UTC]",
    )
    bot = SimpleNamespace(
        color=0xABCDEF,
        get_channel=lambda _id: SimpleNamespace(name="general"),
    )

    embed = await reminder_embed(reminder, bot)

    names = [f.name for f in embed.fields]
    assert "Data:" in names
    assert "Canal:" in names
    assert "Criado em:" in names
    assert "Comando:" not in names


@pytest.mark.asyncio
async def test_reminder_embed_with_recurrence(monkeypatch):
    base_time = datetime.datetime(2025, 1, 1, 10, 0, tzinfo=pytz.utc)

    async def fake_convert(*args, **kwargs):
        # Called as DeltaToDate.convert(None, None, "1d", start=...)
        assert args[2] == "1d"
        assert kwargs["start"] == base_time
        return base_time + datetime.timedelta(days=1)

    monkeypatch.setattr("juliabot.embeds.reminder.DeltaToDate.convert", fake_convert)

    server = SimpleNamespace(get_timezone=lambda: pytz.utc)
    reminder = SimpleNamespace(
        channel_id="999",
        server_id="1",
        date_command="1d",
        time_reminder=base_time,
        get_date_str=lambda: "01/01/2025 10:00 [UTC]",
        get_created_str=lambda: "01/01/2025 09:00 [UTC]",
        get_server=lambda: server,
    )
    bot = SimpleNamespace(
        color=0xABCDEF,
        get_channel=lambda _id: None,
    )

    embed = await reminder_embed(reminder, bot)

    names = [f.name for f in embed.fields]
    assert "Comando:" in names
    assert any("Pr" in f.name for f in embed.fields)
