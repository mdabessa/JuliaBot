"""SQLAlchemy models for JuliaBot database entities.

Defines User, Server, Reminder, AnimesNotifier, AnimesList, TwitchNotifier,
and BotConfig models along with database initialization and auto-migration helpers.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List

import pytz
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    and_,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateColumn
from sqlalchemy.sql import func

from .config import DATABASE_URL, PREFIX

engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)
session = Session()

Base = declarative_base()
logger = logging.getLogger(__name__)


class Model(Base):
    """Abstract base model for all database entities.

    Provides common CRUD operations: create, update, delete, and query methods
    (select, select_one, select_all).
    """

    __abstract__ = True

    def __init__(self, **data) -> None:
        """Initialize and persist a model instance to the database.

        Args:
            **data: Column values to initialize the model.
        """
        super().__init__(**data)

        session.add(self)
        self.update()

    def delete(self) -> None:
        """Delete this model instance from the database."""
        session.delete(self)
        self.update()

    def update(self) -> None:
        """Commit changes to this instance to the database.

        Raises:
            Exception: If the database commit fails.
        """
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise Exception("Failed to commit to database")

    @classmethod
    def select(cls, key: str, value: str) -> list:
        """Query all instances matching a column value.

        Args:
            key (str): Column name to filter by.
            value (str): Value to match.

        Returns:
            list: All matching instances.
        """
        return session.query(cls).filter(getattr(cls, key) == value).all()

    @classmethod
    def select_one(cls, key: str, value):
        """Query a single instance matching a column value.

        Args:
            key (str): Column name to filter by.
            value: Value to match.

        Returns:
            The first matching instance or None.
        """
        return session.query(cls).filter(getattr(cls, key) == value).first()

    @classmethod
    def select_all(cls) -> list:
        """Query all instances of this model.

        Returns:
            list: All instances in the database.
        """
        return session.query(cls).all()

    @classmethod
    def delete_all(cls):
        """Delete all instances of this model from the database."""
        for i in cls.select_all().copy():
            i.delete()


class User(Model):
    """Represents a Discord user with anime language preferences."""

    __tablename__ = "users"

    user_id = Column(String, primary_key=True)
    anime_lang = Column(String, default="pt-br")

    def __init__(self, user_id: str, anime_lang: str = "pt-br") -> None:
        super().__init__(user_id=user_id, anime_lang=anime_lang)

    def set_anime_lang(self, anime_lang: str) -> None:
        """Update the user's preferred anime language.

        Args:
            anime_lang (str): Language code (e.g., 'pt-br').
        """
        self.anime_lang = anime_lang
        self.update()

    @classmethod
    def get_or_create(cls, user_id: str) -> User:
        """Fetch or create a user by ID.

        Args:
            user_id (str): Discord user ID.

        Returns:
            User: Existing or newly created user instance.
        """
        user = cls.select_one("user_id", user_id)

        if user is None:
            user = cls(user_id)

        return user


class Server(Model):
    """Represents a Discord server with configuration settings.

    Stores server-specific preferences including command prefix, anime channel,
    changelog channel, and timezone.
    """

    __tablename__ = "servers"

    server_id = Column(String, primary_key=True)
    prefix = Column(String, default=PREFIX)
    anime_channel = Column(String)
    changelog_channel = Column(String)
    last_changelog_hash = Column(String)
    timezone = Column(String, default="UTC")

    def __init__(self, server_id: str) -> None:
        super().__init__(server_id=str(server_id))

    def set_prefix(self, prefix: str) -> None:
        """Update the server's command prefix.

        Args:
            prefix (str): New prefix string.

        Raises:
            Exception: If prefix is empty.
        """
        if not prefix:
            raise "Prefix can not be empty"

        self.prefix = str(prefix)
        self.update()

    def set_anime_channel(self, channel_id: str):
        """Set the server's anime notification channel.

        Args:
            channel_id (str): Discord channel ID.
        """
        self.anime_channel = str(channel_id)
        self.update()

    def set_timezone(self, timezone: pytz.timezone) -> None:
        """Set the server's timezone.

        Args:
            timezone (pytz.timezone): Timezone object.
        """
        self.timezone = str(timezone.zone)
        self.update()

    def get_timezone(self) -> pytz.timezone:
        """Retrieve the server's configured timezone.

        Returns:
            pytz.timezone: The associated timezone object.
        """
        return pytz.timezone(self.timezone)

    @classmethod
    def get(cls, server_id: str) -> Server | None:
        """Fetch a server by ID.

        Args:
            server_id (str): Discord server ID.

        Returns:
            Server or None: Found server or None if not found.
        """
        return cls.select_one(key="server_id", value=str(server_id))

    @classmethod
    def get_or_create(cls, server_id: str) -> Server:
        """Fetch or create a server by ID.

        Args:
            server_id (str): Discord server ID.

        Returns:
            Server: Existing or newly created server instance.
        """

    @classmethod
    def get_servers_with_changelog_channel(cls) -> List[Server]:
        """Fetch all servers with a configured changelog channel.

        Returns:
            List[Server]: Servers that have changelog notifications enabled.
        """
        return session.query(cls).filter(cls.changelog_channel != None).all()


class Reminder(Model):
    """Represents a scheduled reminder in a Discord server channel.

    Stores reminder metadata including timing, user, and optional recurrence command.
    """

    __tablename__ = "reminder"

    id = Column(Integer, primary_key=True)
    server_id = Column(String, nullable=False)
    channel_id = Column(String, nullable=False)
    message_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    time_created = Column(DateTime(timezone=True), server_default=func.now())
    time_reminder = Column(DateTime, nullable=False)
    date_command = Column(String, default=None)

    def __init__(
        self,
        server_id: str,
        channel_id: str,
        message_id: str,
        user_id: str,
        time_reminder: datetime,
        date_command: str = None,
    ) -> None:
        super().__init__(
            server_id=str(server_id),
            channel_id=str(channel_id),
            message_id=str(message_id),
            user_id=str(user_id),
            time_reminder=time_reminder,
            date_command=date_command,
        )

    def get_server(self) -> Server:
        """Retrieve the server this reminder belongs to.

        Returns:
            Server: Associated server instance.
        """
        return Server.get(self.server_id)

    def get_date_str(self) -> str:
        """Format the reminder trigger time as a timezone-aware string.

        Returns:
            str: Formatted date including server timezone.
        """
        timezone = pytz.utc
        server = self.get_server()
        if server:
            timezone = server.get_timezone()

        date = self.time_reminder.astimezone(timezone)
        date = date.strftime("%d/%m/%Y %H:%M")

        return date + f" [{timezone.zone}]"

    def get_created_str(self) -> str:
        """Format the reminder creation time as a timezone-aware string.

        Returns:
            str: Formatted creation date including server timezone.
        """
        timezone = pytz.utc
        server = self.get_server()
        if server:
            timezone = server.get_timezone()

        date = self.time_created.astimezone(timezone)
        date = date.strftime("%d/%m/%Y %H:%M")

        return date + f" [{timezone.zone}]"

    @classmethod
    def get_expired(cls) -> List[Reminder]:
        """Fetch all reminders past their trigger time.

        Returns:
            List[Reminder]: Expired reminders ready to be triggered.
        """
        now = datetime.now()
        now = now.astimezone(pytz.utc)
        now = now.replace(second=59, microsecond=999999)
        return session.query(cls).filter(cls.time_reminder <= now).all()

    @classmethod
    def get_all(cls, user_id: str) -> List[Reminder]:
        """Fetch all reminders for a user.

        Args:
            user_id (str): Discord user ID.

        Returns:
            List[Reminder]: User's reminders.
        """
        return session.query(cls).filter(cls.user_id == str(user_id)).all()


class AnimesNotifier(Model):
    """Represents a tracked anime episode release for notifications.

    Tracks episode releases with language and dub variants, and notified status.
    """

    __tablename__ = "animes_notifier"

    # My Anime List ID
    mal_id = Column(Integer, primary_key=True)
    episode = Column(Integer, primary_key=True)
    dubbed = Column(Boolean, primary_key=True, default=False)
    lang = Column(String, primary_key=True, default="pt-BR")
    name = Column(String, nullable=False)
    image = Column(String, nullable=False)
    url = Column(String, nullable=False)
    site = Column(String, nullable=False)
    notified = Column(Boolean, nullable=False, default=False)
    date = Column(DateTime(timezone=True), server_default=func.now())

    def __init__(
        self,
        mal_id: int,
        episode: int,
        name: str,
        image: str,
        url: str,
        site: str,
        dubbed: bool = False,
        lang: str = "pt-BR",
    ) -> None:
        super().__init__(
            mal_id=int(mal_id),
            episode=int(episode),
            name=str(name),
            image=str(image),
            url=str(url),
            site=str(site),
            dubbed=bool(dubbed),
            lang=str(lang),
        )

    def set_notified(self, notified: bool):
        """Mark this anime episode as notified.

        Args:
            notified (bool): Notification status.
        """
        self.notified = bool(notified)
        self.update()

    @classmethod
    def get_not_notified(cls) -> List[AnimesNotifier]:
        """Fetch all anime episodes not yet notified.

        Returns:
            List[AnimesNotifier]: Unnotified episode releases.
        """
        return session.query(cls).filter(cls.notified == False).all()

    @classmethod
    def get(
        cls, mal_id: int, episode: int, dubbed: bool, lang: str
    ) -> AnimesNotifier | None:
        """Fetch a specific anime episode notification entry.

        Args:
            mal_id (int): MyAnimeList ID.
            episode (int): Episode number.
            dubbed (bool): Whether dubbed version.
            lang (str): Language code.

        Returns:
            AnimesNotifier or None: Matching entry or None.
        """
        return (
            session.query(cls)
            .filter(
                and_(
                    cls.mal_id == int(mal_id),
                    cls.episode == int(episode),
                    cls.dubbed == bool(dubbed),
                    cls.lang == str(lang),
                )
            )
            .first()
        )

    @classmethod
    def get_desc(cls) -> List[AnimesNotifier]:
        """Fetch all anime episodes sorted by date (newest first).

        Returns:
            List[AnimesNotifier]: Anime episodes in descending date order.
        """
        return session.query(cls).order_by(cls.date.desc()).all()  # Oldest first


class AnimesList(Model):
    """Represents a user's saved anime in their watchlist."""

    __tablename__ = "anime_list"

    user_id = Column(String, primary_key=True)
    mal_id = Column(Integer, primary_key=True)
    dubbed = Column(Boolean, primary_key=True, default=False)

    def __init__(self, user_id: str, mal_id: str, dubbed: bool = False) -> None:
        super().__init__(user_id=str(user_id), mal_id=int(mal_id), dubbed=bool(dubbed))

    @classmethod
    def get(cls, user_id: str, mal_id: int, dubbed: bool) -> AnimesList | None:
        """Fetch user's watchlist entry for an anime.

        Args:
            user_id (str): Discord user ID.
            mal_id (int): MyAnimeList ID.
            dubbed (bool): Whether dubbed version.

        Returns:
            AnimesList or None: Watchlist entry or None.
        """
        return (
            session.query(cls)
            .filter(
                and_(
                    cls.user_id == str(user_id),
                    cls.mal_id == int(mal_id),
                    cls.dubbed == bool(dubbed),
                )
            )
            .first()
        )

    @classmethod
    def get_user(cls, user_id: str) -> List[AnimesList]:
        """Fetch all anime in user's watchlist.

        Args:
            user_id (str): Discord user ID.

        Returns:
            List[AnimesList]: User's watchlist entries.
        """
        return session.query(cls).filter(cls.user_id == str(user_id)).all()

    @classmethod
    def get_anime(cls, mal_id: int, dubbed: bool = False) -> List[AnimesList]:
        """Fetch all users who have an anime in their watchlist.

        Args:
            mal_id (int): MyAnimeList ID.
            dubbed (bool, optional): Filter dubbed versions. Defaults to False.

        Returns:
            List[AnimesList]: All watchlist entries for the anime.
        """
        return (
            session.query(cls)
            .filter(and_(cls.mal_id == int(mal_id), cls.dubbed == bool(dubbed)))
            .all()
        )


class TwitchNotifier(Model):
    """Represents a Twitch streamer notification subscription for a Discord channel."""

    __tablename__ = "twitch_notifier"

    streamer_id = Column(String, primary_key=True)
    channel_id = Column(String, primary_key=True)
    dm = Column(Boolean, nullable=False, default=False)
    notified = Column(Boolean, nullable=False, default=True)

    def __init__(self, streamer_id: str, channel_id: str, dm: bool = False) -> None:
        super().__init__(
            streamer_id=str(streamer_id), channel_id=str(channel_id), dm=bool(dm)
        )

    @classmethod
    def get(cls, streamer_id: str, channel_id: str) -> TwitchNotifier | None:
        """Fetch a Twitch notification subscription.

        Args:
            streamer_id (str): Twitch streamer name/ID.
            channel_id (str): Discord channel ID.

        Returns:
            TwitchNotifier or None: Notification subscription or None.
        """
        return (
            session.query(cls)
            .filter(
                and_(
                    cls.streamer_id == str(streamer_id),
                    cls.channel_id == str(channel_id),
                )
            )
            .first()
        )

    @classmethod
    def get_all(cls) -> List[TwitchNotifier]:
        """Fetch all Twitch notification subscriptions.

        Returns:
            List[TwitchNotifier]: All active subscriptions.
        """
        return cls.select_all()

    @classmethod
    def get_by_channel(cls, channel_id: str) -> List[TwitchNotifier]:
        """Fetch all streamers being tracked in a channel.

        Args:
            channel_id (str): Discord channel ID.

        Returns:
            List[TwitchNotifier]: Channel's tracker subscriptions.
        """
        return session.query(cls).filter(cls.channel_id == str(channel_id)).all()

    @classmethod
    def reset(cls) -> None:
        """Reset all notification flags for live detection.

        Used to re-alert for streamers who are currently online.
        """
        for i in cls.get_all():
            i.notified = False
            i.update()


class BotConfig(Model):
    """Stores bot-wide configuration key-value pairs."""

    __tablename__ = "bot_config"

    key = Column(String, primary_key=True)
    value = Column(String)

    def __init__(self, key: str, value: str) -> None:
        super().__init__(key=str(key), value=str(value))

    @classmethod
    def get(cls, key: str) -> BotConfig | None:
        """Fetch a configuration value by key.

        Args:
            key (str): Configuration key.

        Returns:
            BotConfig or None: Configuration entry or None.
        """
        return cls.select_one("key", key)

    @classmethod
    def get_all(cls) -> List[BotConfig]:
        """Fetch all bot configuration entries.

        Returns:
            List[BotConfig]: All configuration key-value pairs.
        """
        return cls.select_all()


def init_db():
    """Initialize the database schema and apply auto-migrations.

    Creates all tables and auto-applies safe schema changes (simple ADD COLUMN
    operations) to bring the database schema in sync with the model definitions.
    """
    Model.metadata.create_all(engine)
    applied_columns = _auto_add_missing_simple_columns()
    if applied_columns:
        labels = [f"{table}.{column}" for table, column in applied_columns]
        logger.info(
            "Database auto migration applied %d column(s): %s",
            len(applied_columns),
            ", ".join(labels),
        )
    else:
        logger.info("Database schema is up to date (no auto migration needed)")


def _auto_add_missing_simple_columns() -> List[tuple[str, str]]:
    """Auto-sync simple schema drifts by adding missing columns.

    This is intentionally conservative and only applies straightforward
    `ALTER TABLE ADD COLUMN` operations. Complex changes still require
    explicit migrations.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    identifier_preparer = engine.dialect.identifier_preparer
    applied_columns: List[tuple[str, str]] = []

    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue

            existing_columns = {
                column["name"] for column in inspector.get_columns(table.name)
            }
            table_name = identifier_preparer.quote(table.name)

            for column in table.columns:
                if column.name in existing_columns:
                    continue

                if not _is_simple_auto_add_column(column):
                    logger.warning(
                        "Auto migration skipped for %s.%s (unsupported column change)",
                        table.name,
                        column.name,
                    )
                    continue

                column_sql = CreateColumn(column).compile(dialect=engine.dialect)
                ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"
                connection.execute(text(ddl))
                logger.info(
                    "Auto migration applied: added %s.%s", table.name, column.name
                )
                applied_columns.append((table.name, column.name))

    return applied_columns


def _is_simple_auto_add_column(column: Column) -> bool:
    """Check if a column is safe for automatic addition without migration.

    Args:
        column (sqlalchemy.Column): Column to check.

    Returns:
        bool: True if the column can be safely auto-added.
    """
    # Keep automatic changes limited to safe cases.
    if column.primary_key or column.unique or column.foreign_keys:
        return False

    # Non-null columns need a database-side default to be safely added
    # on already populated tables.
    if not column.nullable and column.server_default is None:
        return False

    return True


def rollback():
    """Rollback the current database transaction.

    Useful for reverting failed operations and restoring session state.
    """
    session.rollback()
