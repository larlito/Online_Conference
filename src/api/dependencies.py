"""Внедрение единицы работы, времени и доступа."""

from collections.abc import Iterator
from typing import Annotated
from typing import cast

from fastapi import Depends
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from usecases.errors import Problem
from usecases.service import ConferenceService

bearer = HTTPBearer(
    auto_error=False, description="Ключ входа организатора или ключ гостевой заявки."
)


def get_service(request: Request) -> Iterator[ConferenceService]:
    """Открывает SQLAlchemy Session как Unit of Work на один запрос."""
    sessions = cast(sessionmaker[Session], request.app.state.sessions)
    with sessions.begin() as session:
        yield ConferenceService(session, request.app.state.clock)


def get_token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
    """Извлекает ключ доступа из заголовка Authorization."""
    if credentials is None or not 1 <= len(credentials.credentials) <= 128:
        raise Problem(401, "Укажите действующий ключ доступа.")
    return credentials.credentials


Service = Annotated[ConferenceService, Depends(get_service, scope="function")]
Token = Annotated[str, Depends(get_token)]
