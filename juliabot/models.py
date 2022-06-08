from __future__ import annotations

from sqlalchemy import Column, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from .config import DATABASE_URL


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
        session.commit()

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


class Server(Model):
    __tablename__ = 'servers'
    
    server_id = Column(String, primary_key=True)
    prefix = Column(String, default='j!')

    def __init__(self, server_id: str) -> None:
        super().__init__(server_id=server_id)
    
    def set_prefix(self, prefix: str) -> None:
        if not prefix:
            raise 'Prefix can not be empty'

        self.prefix = prefix
        self.update()

    @classmethod
    def get(cls, server_id: str) -> Server:
        return cls.select_one(key='server_id', value=server_id)

    @classmethod
    def get_or_create(cls, server_id: str) -> Server:
        # Query a discord server in the database, if it doesn't exist insert a new one into it.
        server = cls.get(server_id)
        if not server:
            server = Server(server_id)
        
        return server



def init_db():
    Model.metadata.create_all(engine)
