"""Tests for the Nextcloud feature flag.

A configuration only exists when every setting is present, so an incomplete
environment must disable the mirror instead of producing a half-configured
client.
"""

from __future__ import annotations

import pytest

from juliabot.nextcloud import NextcloudConfig

SETTINGS = {
    "NEXTCLOUD_URL": "https://cloud.example.com/",
    "NEXTCLOUD_USER": "julia",
    "NEXTCLOUD_APP_PASSWORD": "app-password",
    "NEXTCLOUD_CALENDAR": "Lembretes",
    "REMINDER_CALENDAR_USER_ID": "1234",
}


@pytest.fixture
def configured_env(monkeypatch):
    for name, value in SETTINGS.items():
        monkeypatch.setenv(name, value)
    return SETTINGS


def test_config_is_none_when_every_setting_is_missing(monkeypatch):
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)

    assert NextcloudConfig.from_env() is None


@pytest.mark.parametrize("missing", sorted(SETTINGS))
def test_config_is_none_when_one_setting_is_missing(monkeypatch, missing):
    for name, value in SETTINGS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(missing)

    assert NextcloudConfig.from_env() is None


@pytest.mark.parametrize("blank", sorted(SETTINGS))
def test_config_is_none_when_one_setting_is_blank(monkeypatch, blank):
    for name, value in SETTINGS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(blank, "   ")

    assert NextcloudConfig.from_env() is None


def test_config_reads_every_setting_and_normalises_the_url(configured_env):
    config = NextcloudConfig.from_env()

    assert config == NextcloudConfig(
        url="https://cloud.example.com",
        user="julia",
        app_password="app-password",
        calendar="Lembretes",
        reminder_user_id="1234",
    )


def test_calendars_url_points_at_the_user_collection(configured_env):
    config = NextcloudConfig.from_env()

    assert (
        config.calendars_url
        == "https://cloud.example.com/remote.php/dav/calendars/julia/"
    )


def test_calendars_url_quotes_the_user_name(monkeypatch):
    monkeypatch.setenv("NEXTCLOUD_URL", "https://cloud.example.com")
    monkeypatch.setenv("NEXTCLOUD_USER", "julia silva")
    monkeypatch.setenv("NEXTCLOUD_APP_PASSWORD", "app-password")
    monkeypatch.setenv("NEXTCLOUD_CALENDAR", "Lembretes")
    monkeypatch.setenv("REMINDER_CALENDAR_USER_ID", "1234")

    config = NextcloudConfig.from_env()

    assert config.calendars_url.endswith("/remote.php/dav/calendars/julia%20silva/")
