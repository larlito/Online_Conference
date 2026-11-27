"""Фабрика FastAPI и жизненный цикл учебного приложения."""

import os
from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC
from datetime import datetime

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from api.accounts import accounts
from api.accounts import sessions
from api.errors import conflict_handler
from api.errors import http_handler
from api.errors import integrity_handler
from api.errors import problem_handler
from api.errors import storage_handler
from api.errors import validation_handler
from api.meetings import guests
from api.meetings import meetings
from api.meetings import room
from storage.database import database_url
from storage.database import make_engine
from usecases.errors import Problem
from usecases.service import ConferenceService
from web.pages import DIRECTORY
from web.pages import pages


def system_clock() -> datetime:
    """Возвращает текущее время платформы."""
    return datetime.now(UTC)


def bootstrap_admin(app: FastAPI) -> None:
    """Регистрирует администратора при заданных учётных данных."""
    email = app.state.admin_email
    password = app.state.admin_password
    if email is None and password is None:
        return
    if not email or not password:
        raise RuntimeError("Задайте одновременно ADMIN_EMAIL и ADMIN_PASSWORD.")
    with app.state.sessions.begin() as session:
        ConferenceService(session, app.state.clock).bootstrap(email, password)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Подготавливает стартовую запись и освобождает пул после остановки."""
    try:
        await run_in_threadpool(bootstrap_admin, app)
        yield
    finally:
        app.state.engine.dispose()


def create_app(
    url: str | None = None,
    clock: Callable[[], datetime] = system_clock,
    admin_email: str | None = None,
    admin_password: str | None = None,
) -> FastAPI:
    """Собирает API с отдельным движком и управляемыми зависимостями."""
    app = FastAPI(
        title="Online Conference",
        description="Учебная платформа управления встречами, допуском гостей и посещаемостью.",
        lifespan=lifespan,
    )
    engine = make_engine(url or database_url())
    app.state.engine = engine
    app.state.sessions = sessionmaker(engine)
    app.state.clock = clock
    app.state.admin_email = (
        admin_email if admin_email is not None else os.environ.get("ADMIN_EMAIL")
    )
    app.state.admin_password = (
        admin_password if admin_password is not None else os.environ.get("ADMIN_PASSWORD")
    )
    app.add_exception_handler(Problem, problem_handler)
    app.add_exception_handler(RequestValidationError, validation_handler)
    app.add_exception_handler(ValueError, conflict_handler)
    app.add_exception_handler(IntegrityError, integrity_handler)
    app.add_exception_handler(SQLAlchemyError, storage_handler)
    app.add_exception_handler(HTTPException, http_handler)
    for router in (sessions, accounts, meetings, guests, room):
        app.include_router(router)
    app.include_router(pages)
    app.mount("/static", StaticFiles(directory=DIRECTORY / "static"), name="static")
    return app
