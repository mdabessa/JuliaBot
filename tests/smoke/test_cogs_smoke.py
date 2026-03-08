import importlib

import pytest

COGS = [
    "juliabot.cogs.ai",
    "juliabot.cogs.animes",
    "juliabot.cogs.core",
    "juliabot.cogs.debug",
    "juliabot.cogs.error_handler",
    "juliabot.cogs.fun",
    "juliabot.cogs.game",
    "juliabot.cogs.help",
    "juliabot.cogs.reminder",
    "juliabot.cogs.server_config",
    "juliabot.cogs.twitch",
    "juliabot.cogs.utilities",
]


@pytest.mark.parametrize("module_name", COGS)
def test_cog_module_import_and_setup_exists(module_name):
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.skip(f"Missing optional dependency for {module_name}: {exc.name}")

    assert hasattr(module, "setup")
    assert callable(module.setup)
