import pytest
from jikan4 import AioJikan

from juliabot import jikan_catalog as catalog
from juliabot import jikan_render as renderer


@pytest.fixture(scope="module")
def specs() -> dict[str, catalog.RouteSpec]:
    return {spec.route: spec for spec in catalog.load_specs()}


class FakeModel:
    def __init__(self, data):
        self._data = data

    def model_dump(self):
        return self._data


class FakeLegacyModel:
    def __init__(self, data):
        self._data = data

    def dict(self):
        return self._data


def test_list_with_pagination_becomes_titled_pages(specs):
    payload = {
        "data": [
            {"title": "Frieren", "url": "https://x/1", "type": "TV", "score": 9.3},
            {"title": "Monster", "url": "https://x/2", "type": "TV", "score": 8.9},
        ],
        "pagination": {
            "current_page": 2,
            "last_visible_page": 7,
            "has_next_page": True,
        },
    }

    result = renderer.render(payload, specs["get_anime"], color=123)

    assert len(result.embeds) == 1
    embed = result.embeds[0]
    assert embed.title == specs["get_anime"].brief
    assert embed.color.value == 123
    assert "[Frieren](https://x/1)" in embed.description
    assert "type: TV" in embed.description
    assert "2 resultado(s)" in embed.footer.text
    assert "API página 2/7" in embed.footer.text
    assert "tem próxima" in embed.footer.text


def test_flat_list_without_pagination_has_no_api_note(specs):
    payload = {"data": [{"name": "Akira"}, {"name": "Berserk"}]}

    result = renderer.render(payload, specs["get_anime_external"])

    footer = result.embeds[0].footer.text
    assert "2 resultado(s)" in footer
    assert "API página" not in footer


def test_list_of_primitives_is_rendered_as_bullets(specs):
    payload = {"data": [1, 2, 3]}

    result = renderer.render(payload, specs["get_anime_external"])

    assert result.embeds[0].description == "• 1\n• 2\n• 3"


def test_empty_list_is_reported(specs):
    result = renderer.render({"data": []}, specs["get_anime"])

    assert result.content == renderer.EMPTY_MESSAGE
    assert result.embeds == ()


def test_long_lists_are_split_into_bounded_embeds(specs):
    payload = {"data": [{"name": f"Character {index}"} for index in range(400)]}

    result = renderer.render(payload, specs["get_characters"])

    assert len(result.embeds) <= renderer.MAX_EMBEDS
    for embed in result.embeds:
        assert len(embed.description) <= renderer.MAX_DESCRIPTION
        assert len(embed.footer.text) <= renderer.MAX_FOOTER


def test_object_payload_becomes_key_value_fields(specs):
    payload = {"data": {"openings": ["OP1", "OP2"], "endings": ["ED1"]}}

    result = renderer.render(payload, specs["get_anime_themes"])

    embed = result.embeds[0]
    fields = {field.name: field.value for field in embed.fields}
    assert fields["Openings"] == "OP1\nOP2"
    assert fields["Endings"] == "ED1"


def test_entity_payload_becomes_a_summary_embed(specs):
    payload = {
        "mal_id": 1,
        "title": "Cowboy Bebop",
        "url": "https://myanimelist.net/anime/1",
        "synopsis": "Space bounty hunters.",
        "images": {
            "jpg": {
                "image_url": "https://cdn/small.jpg",
                "large_image_url": "https://cdn/large.jpg",
            }
        },
        "episodes": 26,
        "score": 8.75,
    }

    result = renderer.render(payload, specs["get_anime"])

    embed = result.embeds[0]
    assert embed.title == "Cowboy Bebop"
    assert embed.url == "https://myanimelist.net/anime/1"
    assert embed.description == "Space bounty hunters."
    assert embed.thumbnail.url == "https://cdn/large.jpg"
    names = {field.name for field in embed.fields}
    assert {"MAL ID", "Episodes", "Score"} <= names
    assert "Title" not in names
    assert "Images" not in names


def test_entity_without_url_or_image_still_renders(specs):
    payload = {"title": "Unknown", "url": "not-a-url", "images": {}}

    result = renderer.render(payload, specs["get_anime"])

    embed = result.embeds[0]
    assert embed.title == "Unknown"
    assert embed.url is None
    assert embed.thumbnail.url is None


def test_entity_drops_empty_nested_models(specs):
    payload = {
        "title": "Cowboy Bebop",
        "trailer": {"youtube_id": None, "url": None, "embed_url": None},
        "aired": {"from_": None, "to": None},
        "theme": {"openings": [], "endings": []},
    }

    result = renderer.render(payload, specs["get_anime"])

    assert list(result.embeds[0].fields) == []


def test_entity_shows_the_interesting_fields_first(specs):
    payload = {"mal_id": 1, "members": 10, "type": "TV", "score": 9.0}

    result = renderer.render(payload, specs["get_anime"])

    names = [field.name for field in result.embeds[0].fields]
    assert names == ["Type", "Score", "Members", "MAL ID"]


def test_labels_expand_known_acronyms(specs):
    payload = {"data": {"mal_id": 1, "api_url": "x", "sfw_strict": True}}

    result = renderer.render(payload, specs["get_anime_themes"])

    names = [field.name for field in result.embeds[0].fields]
    assert names == ["MAL ID", "API URL", "SFW Strict"]


def test_empty_object_payload_is_reported(specs):
    result = renderer.render(
        {"data": {"openings": [], "endings": []}}, specs["get_anime_themes"]
    )

    assert result.content == renderer.EMPTY_MESSAGE


def test_pydantic_model_payloads_are_dumped(specs):
    payload = FakeModel({"data": {"openings": ["OP1"]}})

    result = renderer.render(payload, specs["get_anime_themes"])

    assert result.embeds[0].fields[0].value == "OP1"


def test_pydantic_v1_dict_payloads_are_dumped(specs):
    payload = FakeLegacyModel({"data": {"openings": ["OP1"]}})

    result = renderer.render(payload, specs["get_anime_themes"])

    assert result.embeds[0].fields[0].value == "OP1"


def test_small_unstructured_payloads_become_inline_json(specs):
    result = renderer.render("plain text", specs["get_top_anime"])

    assert result.content.startswith("```json")
    assert "plain text" in result.content


def test_debug_renderer_always_uses_json(specs):
    payload = {"data": [{"title": "Frieren"}]}

    result = renderer.render(payload, specs["get_anime_ids"])

    assert result.embeds == ()
    assert result.content is not None
    assert "Frieren" in result.content


def test_oversized_payloads_become_a_json_attachment(specs):
    payload = {"data": [{"name": f"Entry {index}"} for index in range(2000)]}

    result = renderer.render(payload, specs["get_anime_ids"])

    assert result.content is None
    assert result.file is not None
    assert result.file.filename == "anime_ids.json"


def test_broken_payloads_fall_back_to_json(specs):
    class Exploding:
        def model_dump(self):
            raise RuntimeError("boom")

    result = renderer.render(Exploding(), specs["get_anime"])

    assert result.content is not None


def test_entity_title_is_clipped(specs):
    payload = {"title": "x" * 500}

    result = renderer.render(payload, specs["get_anime"])

    assert len(result.embeds[0].title) == renderer.MAX_TITLE


def test_field_values_and_count_are_bounded(specs):
    payload = {"data": {f"key_{index}": "y" * 4000 for index in range(40)}}

    result = renderer.render(payload, specs["get_anime_themes"])

    embed = result.embeds[0]
    assert len(embed.fields) <= renderer.MAX_FIELDS
    assert all(len(field.value) <= renderer.MAX_FIELD_VALUE for field in embed.fields)


@pytest.mark.asyncio
async def test_renderer_handles_a_real_client_response_with_mocked_get(specs):
    client = AioJikan(rate_limit=0)

    async def fake_get(endpoint, params=None):
        assert endpoint == "anime/1/themes"
        return {"data": {"openings": ["OP1"], "endings": ["ED1"]}}

    client._get = fake_get

    payload = await client.get_anime_themes(1)
    result = renderer.render(payload, specs["get_anime_themes"])

    fields = {field.name: field.value for field in result.embeds[0].fields}
    assert fields == {"Openings": "OP1", "Endings": "ED1"}

    await client.close()
