from __future__ import annotations

from datetime import datetime
from typing import List

import pytz
from sqlalchemy import Boolean, Column, DateTime, Integer, String, and_, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

from .config import DATABASE_URL, PREFIX

engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)
session = Session()

Base = declarative_base()


class Model(Base):
    __abstract__ = True

    def __init__(self, **data) -> None:
        super().__init__(**data)

        session.add(self)
        self.update()

    def delete(self) -> None:
        session.delete(self)
        self.update()

    def update(self) -> None:
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise Exception("Failed to commit to database")

    @classmethod
    def select(cls, key: str, value: str) -> list:
        return session.query(cls).filter(getattr(cls, key) == value).all()

    @classmethod
    def select_one(cls, key: str, value):
        return session.query(cls).filter(getattr(cls, key) == value).first()

    @classmethod
    def select_all(cls) -> list:
        return session.query(cls).all()

    @classmethod
    def delete_all(cls):
        for i in cls.select_all().copy():
            i.delete()


class User(Model):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True)
    anime_lang = Column(String, default="pt-br")

    def __init__(self, user_id: str, anime_lang: str = "pt-br") -> None:
        super().__init__(user_id=user_id, anime_lang=anime_lang)

    def set_anime_lang(self, anime_lang: str) -> None:
        self.anime_lang = anime_lang
        self.update()

    @classmethod
    def get_or_create(cls, user_id: str) -> User:
        user = cls.select_one("user_id", user_id)

        if user is None:
            user = cls(user_id)

        return user


class Server(Model):
    __tablename__ = "servers"

    server_id = Column(String, primary_key=True)
    prefix = Column(String, default=PREFIX)
    anime_channel = Column(String)
    timezone = Column(String, default="UTC")

    def __init__(self, server_id: str) -> None:
        super().__init__(server_id=str(server_id))

    def set_prefix(self, prefix: str) -> None:
        if not prefix:
            raise "Prefix can not be empty"

        self.prefix = str(prefix)
        self.update()

    def set_anime_channel(self, channel_id: str):
        self.anime_channel = str(channel_id)
        self.update()

    def set_timezone(self, timezone: pytz.timezone) -> None:
        self.timezone = str(timezone.zone)
        self.update()

    def get_timezone(self) -> pytz.timezone:
        return pytz.timezone(self.timezone)

    @classmethod
    def get(cls, server_id: str) -> Server | None:
        return cls.select_one(key="server_id", value=str(server_id))

    @classmethod
    def get_or_create(cls, server_id: str) -> Server:
        # Query a discord server in the database, if it doesn't exist insert a new one into it.
        server = cls.get(str(server_id))
        if not server:
            server = Server(str(server_id))

        return server


class Reminder(Model):
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
        return Server.get(self.server_id)

    def get_date_str(self) -> str:
        timezone = pytz.utc
        server = self.get_server()
        if server:
            timezone = server.get_timezone()

        date = self.time_reminder.astimezone(timezone)
        date = date.strftime("%d/%m/%Y %H:%M")

        return date + f" [{timezone.zone}]"

    def get_created_str(self) -> str:
        timezone = pytz.utc
        server = self.get_server()
        if server:
            timezone = server.get_timezone()

        date = self.time_created.astimezone(timezone)
        date = date.strftime("%d/%m/%Y %H:%M")

        return date + f" [{timezone.zone}]"

    @classmethod
    def get_expired(cls) -> List[Reminder]:
        now = datetime.now()
        now = now.astimezone(pytz.utc)
        now = now.replace(second=59, microsecond=999999)
        return session.query(cls).filter(cls.time_reminder <= now).all()

    @classmethod
    def get_all(cls, user_id: str) -> List[Reminder]:
        return session.query(cls).filter(cls.user_id == str(user_id)).all()


class AnimesNotifier(Model):
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
        self.notified = bool(notified)
        self.update()

    @classmethod
    def get_not_notified(cls) -> List[AnimesNotifier]:
        return session.query(cls).filter(cls.notified == False).all()

    @classmethod
    def get(
        cls, mal_id: int, episode: int, dubbed: bool, lang: str
    ) -> AnimesNotifier | None:
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
        return session.query(cls).order_by(cls.date.desc()).all()  # Oldest first


class AnimesList(Model):
    __tablename__ = "anime_list"

    user_id = Column(String, primary_key=True)
    mal_id = Column(Integer, primary_key=True)
    dubbed = Column(Boolean, primary_key=True, default=False)

    def __init__(self, user_id: str, mal_id: str, dubbed: bool = False) -> None:
        super().__init__(user_id=str(user_id), mal_id=int(mal_id), dubbed=bool(dubbed))

    @classmethod
    def get(cls, user_id: str, mal_id: int, dubbed: bool) -> AnimesList | None:
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
        return session.query(cls).filter(cls.user_id == str(user_id)).all()

    @classmethod
    def get_anime(cls, mal_id: int, dubbed: bool = False) -> List[AnimesList]:
        return (
            session.query(cls)
            .filter(and_(cls.mal_id == int(mal_id), cls.dubbed == bool(dubbed)))
            .all()
        )


class RocketLeague(Model):
    __tablename__ = "rocket_league"

    user_id = Column(String, primary_key=True)
    ballchasing_token = Column(String)

    def __init__(self, user_id: str) -> None:
        super().__init__(user_id=str(user_id))

    def set_ballchasing_token(self, ballchasing_token: str):
        self.ballchasing_token = str(ballchasing_token)
        self.update()

    @classmethod
    def get(cls, user_id: str) -> RocketLeague:
        return cls.select_one(key="user_id", value=str(user_id))


class TwitchNotifier(Model):
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
        return cls.select_all()

    @classmethod
    def get_by_channel(cls, channel_id: str) -> List[TwitchNotifier]:
        return session.query(cls).filter(cls.channel_id == str(channel_id)).all()

    @classmethod
    def reset(cls) -> None:
        for i in cls.get_all():
            i.notified = False
            i.update()


class BotConfig(Model):
    __tablename__ = "bot_config"

    key = Column(String, primary_key=True)
    value = Column(String)

    def __init__(self, key: str, value: str) -> None:
        super().__init__(key=str(key), value=str(value))

    @classmethod
    def get(cls, key: str) -> BotConfig | None:
        return cls.select_one("key", key)

    @classmethod
    def get_all(cls) -> List[BotConfig]:
        return cls.select_all()


def init_db():
    Model.metadata.create_all(engine)


def rollback():
    session.rollback()
