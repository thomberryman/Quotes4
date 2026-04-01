from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _get_sqlalchemy_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = _get_sqlalchemy_database_url(get_settings().database_url)
    connect_args: dict[str, object] = {}
    pool_pre_ping = True

    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        pool_pre_ping = False

    engine = create_engine(database_url, pool_pre_ping=pool_pre_ping, connect_args=connect_args)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_db_session() -> Generator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_db_state() -> None:
    try:
        engine = get_engine()
    except Exception:
        engine = None
    if engine is not None:
        engine.dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
