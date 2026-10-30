import inspect

import pytest
from jikan4 import AioJikan

from juliabot import jikan_catalog as catalog

EXPECTED_HIDDEN = {
    "get_anime_deleted",
    "get_anime_unapproved",
    "get_anime_denied",
    "get_manga_deleted",
    "get_manga_unapproved",
    "get_manga_denied",
    "get_anime_ids",
    "get_manga_ids",
    "get_character_ids",
    "get_person_ids",
    "get_producer_ids",
}


@pytest.fixture(scope="module")
def specs() -> tuple[catalog.RouteSpec, ...]:
    return catalog.load_specs()


def test_every_public_client_route_has_a_spec(specs):
    assert {spec.route for spec in specs} == set(catalog.route_names())


def test_route_names_skip_private_helpers_and_lifecycle(specs):
    routes = set(catalog.route_names())

    assert "close" not in routes
    assert "_get" not in routes
    assert all(not route.startswith("_") for route in routes)


def test_every_spec_resolves_to_a_client_coroutine(specs):
    for spec in specs:
        method = getattr(AioJikan, spec.route, None)
        assert method is not None, f"{spec.route} is not defined on AioJikan"
        assert inspect.iscoroutinefunction(method), f"{spec.route} is not a coroutine"


def test_command_labels_are_unique(specs):
    labels = [label for spec in specs for label in (spec.name, *spec.aliases)]

    assert len(labels) == len(set(labels))


def test_policy_only_references_real_routes():
    stale = set(catalog.POLICY) - set(catalog.route_names())

    assert not stale, f"POLICY references unknown route(s): {sorted(stale)}"


def test_get_anime_is_renamed_so_the_anime_alias_stays_free(specs):
    spec = next(spec for spec in specs if spec.route == "get_anime")

    assert spec.name == "anime_info"
    assert "anime" not in spec.aliases
    assert all(spec.name != "anime" for spec in specs)
    assert all("anime" not in spec.aliases for spec in specs)


def test_search_anime_is_curated_by_the_hand_written_command(specs):
    curated = [spec.route for spec in specs if spec.curated]

    assert curated == ["search_anime"]


def test_hidden_routes_match_the_policy(specs):
    hidden = {spec.route for spec in specs if spec.hidden}

    assert hidden == EXPECTED_HIDDEN


def test_bulk_dumps_use_the_debug_renderer(specs):
    for spec in specs:
        if spec.route.endswith("_ids") and "genre" not in spec.route:
            assert spec.renderer == catalog.RENDERER_DEBUG, spec.route
            assert spec.hidden, spec.route


def test_embed_renderer_is_reserved_for_non_paginated_payloads(specs):
    embed_routes = {
        spec.route for spec in specs if spec.renderer == catalog.RENDERER_EMBED
    }

    assert "get_anime_themes" in embed_routes
    assert "get_random_anime" in embed_routes
    assert "get_anime_themes" not in {
        spec.route for spec in specs if spec.renderer == catalog.RENDERER_AUTO
    }


def test_groups_cover_the_whole_catalog(specs):
    groups = {spec.group for spec in specs}

    assert groups == {catalog.GROUP_ANIME, catalog.GROUP_MANGA, catalog.GROUP_CATALOG}
    assert sum(1 for spec in specs if spec.group == catalog.GROUP_ANIME) == 26
    assert sum(1 for spec in specs if spec.group == catalog.GROUP_MANGA) == 18


@pytest.mark.parametrize(
    ("route", "shape"),
    [
        ("get_anime", catalog.SHAPE_ENTITY),
        ("search_anime", catalog.SHAPE_PAGINATED),
        ("get_anime_themes", catalog.SHAPE_OBJECT),
        ("get_anime_external", catalog.SHAPE_LIST),
        ("get_seasons", catalog.SHAPE_LIST),
        ("get_characters", catalog.SHAPE_PAGINATED),
    ],
)
def test_response_shape_is_derived_from_the_model(specs, route, shape):
    spec = next(spec for spec in specs if spec.route == route)

    assert spec.shape == shape


def test_every_route_has_a_known_shape(specs):
    shapes = {spec.shape for spec in specs}

    assert catalog.SHAPE_UNKNOWN not in shapes
    assert shapes == {
        catalog.SHAPE_PAGINATED,
        catalog.SHAPE_LIST,
        catalog.SHAPE_OBJECT,
        catalog.SHAPE_ENTITY,
    }
    paginated = sum(1 for spec in specs if spec.shape == catalog.SHAPE_PAGINATED)
    assert paginated == 49


def test_params_are_typed_with_supported_annotations(specs):
    annotations = {param.annotation for spec in specs for param in spec.params}

    assert annotations
    assert annotations <= set(catalog.SUPPORTED_PARAM_TYPES)


def test_required_params_precede_optional_ones(specs):
    for spec in specs:
        flags = [param.required for param in spec.params]
        assert flags == sorted(flags, reverse=True), spec.route


def test_positional_names_are_required_plus_the_search_term(specs):
    season = next(spec for spec in specs if spec.route == "get_season")
    assert season.positional_names == ("year", "season")

    search = next(spec for spec in specs if spec.route == "search_manga")
    assert search.positional_names[0] == "query"

    themes = next(spec for spec in specs if spec.route == "get_anime_themes")
    assert themes.positional_names == ("anime_id",)


def test_usage_marks_positional_and_key_value_parameters(specs):
    themes = next(spec for spec in specs if spec.route == "get_anime_themes")
    assert themes.usage == "anime_themes <anime_id>"

    full = next(spec for spec in specs if spec.route == "get_anime_full")
    assert full.usage == "anime_full <anime_id> [sfw=bool] [sfw_strict=bool]"


def test_brief_is_a_single_sentence(specs):
    for spec in specs:
        assert spec.brief, spec.route
        assert "\n" not in spec.brief, spec.route
        assert "Args:" not in spec.description, spec.route
        assert ">>>" not in spec.description, spec.route


def test_catalog_is_deterministic_and_ordered_by_group_then_name(specs):
    assert catalog.load_specs() == specs
    assert list(specs) == sorted(specs, key=lambda spec: (spec.group, spec.name))


def test_split_docstring_drops_the_section_body():
    brief, description = catalog._split_docstring(
        "Get anime information\n\nArgs:\n    anime_id (int): Anime ID\n"
    )

    assert brief == "Get anime information"
    assert description == "Get anime information"


def test_split_docstring_without_sections_keeps_the_summary():
    brief, description = catalog._split_docstring(
        "Search for manga.\n\nSupports several filters."
    )

    assert brief == "Search for manga."
    assert description == "Search for manga.\n\nSupports several filters."


def test_split_docstring_of_a_missing_docstring_is_empty():
    assert catalog._split_docstring(None) == ("", "")


def test_duplicate_labels_are_rejected(monkeypatch):
    monkeypatch.setitem(
        catalog.POLICY,
        "get_top_anime",
        catalog.RoutePolicy(name="anime_themes"),
    )

    with pytest.raises(ValueError, match="Duplicate command label"):
        catalog.load_specs()


def test_stale_policy_entries_are_rejected(monkeypatch):
    monkeypatch.setitem(
        catalog.POLICY,
        "get_no_longer_exists",
        catalog.RoutePolicy(name="ghost"),
    )

    with pytest.raises(ValueError, match="unknown route"):
        catalog.load_specs()


def test_unknown_renderer_is_rejected(monkeypatch):
    monkeypatch.setitem(
        catalog.POLICY,
        "get_top_anime",
        catalog.RoutePolicy(renderer="hologram"),
    )

    with pytest.raises(ValueError, match="unknown renderer"):
        catalog.load_specs()


def test_unsupported_annotation_falls_back_to_str():
    param = inspect.Parameter(
        "filter", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=list[str]
    )

    spec = catalog._param_spec("get_anime", param, {})

    assert spec.annotation is str
