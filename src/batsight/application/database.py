"""SQLAlchemy engine and session setup for the local SQLite database."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base for application persistence models."""


def create_database(database_url: str) -> tuple[Engine, sessionmaker[Session]]:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or url.drivername not in ("sqlite", "sqlite+pysqlite"):
        raise ValueError("BatSight local application supports SQLite databases only")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return engine, factory


def get_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
