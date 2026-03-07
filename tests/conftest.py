import os

# Ensure imports that read env vars at import-time do not crash in tests.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DISCORD_TOKEN", "")
os.environ.setdefault("PREFIX", "!")
os.environ.setdefault("TZ", "UTC")
