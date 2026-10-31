import pytest

from juliabot import jikan_catalog as catalog
from juliabot.jikan_args import JikanArgumentError, parse_arguments


@pytest.fixture(scope="module")
def specs() -> dict[str, catalog.RouteSpec]:
    return {spec.name: spec for spec in catalog.load_specs()}


def test_single_required_parameter_is_positional(specs):
    parsed = parse_arguments(specs["anime_themes"], "1")

    assert parsed == {"anime_id": 1}


def test_multiple_required_parameters_keep_declaration_order(specs):
    parsed = parse_arguments(specs["season"], "2024 spring")

    assert parsed == {"year": 2024, "season": "spring"}


def test_search_term_is_positional_even_when_optional(specs):
    parsed = parse_arguments(specs["search_manga"], "naruto")

    assert parsed == {"query": "naruto"}


def test_required_and_search_term_can_be_combined(specs):
    parsed = parse_arguments(specs["anime_stacks"], '1 "movie"')

    assert parsed == {"anime_id": 1, "q": "movie"}


def test_positional_values_are_coerced_to_the_declared_type(specs):
    parsed = parse_arguments(specs["season"], "2024 spring")

    assert parsed["year"] == 2024
    assert isinstance(parsed["year"], int)


def test_key_value_pairs_are_coerced_per_annotation(specs):
    parsed = parse_arguments(
        specs["search_manga"], "naruto page=2 limit=5 score=8.5 status=airing"
    )

    assert parsed == {
        "query": "naruto",
        "page": 2,
        "limit": 5,
        "score": 8.5,
        "status": "airing",
    }
    assert isinstance(parsed["page"], int)
    assert isinstance(parsed["score"], float)


@pytest.mark.parametrize("value", ["yes", "y", "true", "1", "on", "sim", "ENABLE"])
def test_true_spellings(specs, value):
    assert parse_arguments(specs["anime_full"], f"1 sfw={value}") == {
        "anime_id": 1,
        "sfw": True,
    }


@pytest.mark.parametrize("value", ["no", "n", "false", "0", "off", "não", "nao"])
def test_false_spellings(specs, value):
    assert parse_arguments(specs["anime_full"], f"1 sfw={value}") == {
        "anime_id": 1,
        "sfw": False,
    }


def test_boolean_flag_bare_name_sets_true_once_positionals_are_filled(specs):
    parsed = parse_arguments(specs["anime_full"], "1 sfw")

    assert parsed == {"anime_id": 1, "sfw": True}


def test_bare_word_matching_a_bool_is_a_value_while_a_slot_is_open(specs):
    parsed = parse_arguments(specs["search_manga"], "sfw")

    assert parsed == {"query": "sfw"}


def test_quoted_value_keeps_its_spaces(specs):
    parsed = parse_arguments(specs["search_manga"], 'query="full metal panic"')

    assert parsed == {"query": "full metal panic"}


def test_quoted_positional_keeps_its_spaces(specs):
    parsed = parse_arguments(specs["search_manga"], '"full metal panic"')

    assert parsed == {"query": "full metal panic"}


def test_single_quotes_are_supported(specs):
    parsed = parse_arguments(specs["search_manga"], "query='full metal panic'")

    assert parsed == {"query": "full metal panic"}


def test_value_may_contain_equals_signs(specs):
    parsed = parse_arguments(specs["search_manga"], "query=a=b")

    assert parsed == {"query": "a=b"}


def test_apostrophe_inside_a_value_stays_literal(specs):
    parsed = parse_arguments(specs["search_manga"], "k-on's")

    assert parsed == {"query": "k-on's"}


def test_keyword_may_target_a_positional_parameter(specs):
    parsed = parse_arguments(specs["anime_themes"], "anime_id=1")

    assert parsed == {"anime_id": 1}


def test_keywords_and_positionals_can_be_interleaved(specs):
    parsed = parse_arguments(specs["anime_stacks"], "page=2 1 order_by=members")

    assert parsed == {"anime_id": 1, "page": 2, "order_by": "members"}


def test_only_supplied_arguments_are_returned(specs):
    parsed = parse_arguments(specs["anime_themes"], "1")

    assert set(parsed) == {"anime_id"}


def test_arguments_follow_the_declaration_order(specs):
    parsed = parse_arguments(specs["anime_full"], "sfw=yes 1")

    assert list(parsed) == ["anime_id", "sfw"]


def test_empty_tail_is_fine_when_nothing_is_required(specs):
    assert parse_arguments(specs["top_anime"], "") == {}
    assert parse_arguments(specs["top_anime"], None) == {}


def test_missing_required_argument_is_reported_with_usage(specs):
    with pytest.raises(JikanArgumentError) as excinfo:
        parse_arguments(specs["season"], "2024")

    message = str(excinfo.value)
    assert "Faltou informar: season" in message
    assert "Uso: season <year> <season>" in message


def test_unknown_key_lists_the_accepted_parameters(specs):
    with pytest.raises(JikanArgumentError) as excinfo:
        parse_arguments(specs["anime_full"], "1 nope=1")

    message = str(excinfo.value)
    assert "Parâmetro desconhecido: `nope`" in message
    assert "anime_id, sfw, sfw_strict" in message


def test_extra_positional_is_reported_with_usage(specs):
    with pytest.raises(JikanArgumentError) as excinfo:
        parse_arguments(specs["anime_themes"], "1 2")

    message = str(excinfo.value)
    assert "Valor extra: `2`" in message
    assert "Uso: anime_themes <anime_id>" in message


def test_duplicate_keyword_is_rejected(specs):
    with pytest.raises(JikanArgumentError, match="informado mais de uma vez"):
        parse_arguments(specs["top_anime"], "page=1 page=2")


def test_duplicate_between_positional_and_keyword_is_rejected(specs):
    with pytest.raises(JikanArgumentError, match="informado mais de uma vez"):
        parse_arguments(specs["anime_themes"], "1 anime_id=2")


def test_bad_integer_names_the_parameter_and_the_value(specs):
    with pytest.raises(JikanArgumentError) as excinfo:
        parse_arguments(specs["top_anime"], "page=abc")

    message = str(excinfo.value)
    assert "`page` precisa ser um número inteiro" in message
    assert "abc" in message


def test_bad_float_is_reported(specs):
    with pytest.raises(JikanArgumentError, match="precisa ser um número"):
        parse_arguments(specs["search_manga"], "score=high")


def test_bad_boolean_is_reported(specs):
    with pytest.raises(JikanArgumentError, match="aceita sim ou não"):
        parse_arguments(specs["anime_full"], "1 sfw=maybe")


def test_unterminated_quote_is_reported(specs):
    with pytest.raises(JikanArgumentError, match="aspas sem fechar"):
        parse_arguments(specs["search_manga"], 'q="full metal')


def test_error_is_a_user_input_error(specs):
    from discord.ext import commands

    with pytest.raises(commands.UserInputError):
        parse_arguments(specs["anime_themes"], "")


def test_empty_value_is_accepted_for_text_parameters(specs):
    assert parse_arguments(specs["search_manga"], "query=") == {"query": ""}
