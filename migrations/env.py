"""Миграции используют тот же URL, что и приложение."""

from alembic import context

from storage.database import database_url
from storage.database import make_engine
from storage.models import Base


def run_migrations() -> None:
    """Применяет ревизии онлайн или выводит соответствующий SQL."""
    if context.is_offline_mode():
        context.configure(url=database_url(), target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = make_engine(database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
