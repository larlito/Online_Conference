"""Создание движка и конфигурация подключения к базе."""

import os
from sqlite3 import Connection

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import event


def database_url() -> str:
    """Возвращает URL PostgreSQL или локальной SQLite."""
    return os.environ.get("DATABASE_URL", "sqlite:///./conference.db")


def enable_foreign_keys(connection: Connection, _record: object) -> None:
    """Включает проверку внешних ключей для соединения SQLite."""
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url: str) -> Engine:
    """Создаёт отдельный движок для приложения или тестового стенда."""
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", enable_foreign_keys)
    return engine
