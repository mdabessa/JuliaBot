import os

# Ensure imports that read env vars at import-time do not crash in tests.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DISCORD_TOKEN", "")
os.environ.setdefault("PREFIX", "!")
os.environ.setdefault("TZ", "UTC")

# Importing the config folds in the developer's .env file, if any, so drop the
# reminder-mirror settings afterwards: no test may reach the network by
# accident, and only the explicit configuration tests may enable the mirror.
import juliabot.config  # noqa: E402  (the ordering is the point)

for _name in (
    "NEXTCLOUD_URL",
    "NEXTCLOUD_USER",
    "NEXTCLOUD_APP_PASSWORD",
    "NEXTCLOUD_CALENDAR",
    "REMINDER_CALENDAR_USER_ID",
):
    os.environ.pop(_name, None)
