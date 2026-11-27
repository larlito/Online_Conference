"""Маршруты входа и администрирования."""

from fastapi import APIRouter

from api.dependencies import Service
from api.dependencies import Token
from api.errors import errors
from dtos.requests import AccountBlock
from dtos.requests import Credentials
from dtos.requests import Email
from dtos.responses import AccountDTO
from dtos.responses import LoginDTO

sessions = APIRouter(prefix="/api/sessions", tags=["Сессии"], responses=errors(422, 503))
accounts = APIRouter(
    prefix="/api/accounts", tags=["Учётные записи"], responses=errors(401, 403, 422, 503)
)


@sessions.post(
    "",
    response_model=LoginDTO,
    status_code=201,
    responses=errors(401, 409),
    summary="Войти по учётной записи",
    description="Выдаёт ключ на восемь часов.",
)
def login(payload: Credentials, service: Service) -> LoginDTO:
    """Создаёт сессию администратора или организатора."""
    return LoginDTO.model_validate(service.login(payload.email, payload.password))


@accounts.post(
    "",
    response_model=AccountDTO,
    status_code=201,
    responses=errors(409),
    summary="Создать организатора",
    description="Операция доступна администратору.",
)
def add_host(payload: Credentials, token: Token, service: Service) -> AccountDTO:
    """Регистрирует нового организатора."""
    return AccountDTO.model_validate(service.add_host(token, payload.email, payload.password))


@accounts.patch(
    "/{email}",
    response_model=AccountDTO,
    responses=errors(404, 409),
    summary="Изменить блокировку",
    description="Блокировка закрывает встречи и отзывает сессии.",
)
def block_host(email: Email, payload: AccountBlock, token: Token, service: Service) -> AccountDTO:
    """Блокирует или разблокирует организатора."""
    return AccountDTO.model_validate(service.block(token, email, payload.blocked))
