"""Обработчики и документация ответов об ошибках."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from dtos.responses import ErrorDTO
from usecases.errors import Problem

DESCRIPTIONS = {
    400: "Данные не подходят для операции",
    401: "Требуется действующий ключ или учётная запись",
    403: "У роли нет разрешения",
    404: "Ресурс не найден",
    409: "Операция конфликтует с текущим состоянием",
    422: "Неверный формат или значение входных данных",
    503: "Хранилище временно недоступно",
}


def errors(*codes: int) -> dict[int, dict[str, object]]:
    """Возвращает описания ответов маршрута для Swagger UI."""
    return {code: {"model": ErrorDTO, "description": DESCRIPTIONS[code]} for code in codes}


def problem_handler(_request: Request, error: Problem) -> JSONResponse:
    """Выводит ожидаемое сообщение прикладной операции."""
    headers = {"WWW-Authenticate": "Bearer"} if error.status == 401 else None
    return JSONResponse({"detail": str(error)}, status_code=error.status, headers=headers)


def validation_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
    """Собирает сообщения без исходных полей запроса и секретных значений."""
    messages = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"])
        messages.append(f"{location}: {item['msg']}")
    return JSONResponse({"detail": "; ".join(messages)}, status_code=422)


def conflict_handler(_request: Request, error: ValueError) -> JSONResponse:
    """Преобразует нарушение правила комнаты в конфликт."""
    return JSONResponse({"detail": str(error)}, status_code=409)


def integrity_handler(_request: Request, _error: IntegrityError) -> JSONResponse:
    """Отдаёт понятное сообщение при конфликте ограничений хранения."""
    return JSONResponse(
        {"detail": "Запись уже существует или нарушает ограничения данных."}, status_code=409
    )


def storage_handler(_request: Request, _error: SQLAlchemyError) -> JSONResponse:
    """Не раскрывает строку подключения и SQL пользователю."""
    return JSONResponse({"detail": "Хранилище временно недоступно."}, status_code=503)


def http_handler(_request: Request, error: HTTPException) -> JSONResponse:
    """Приводит встроенные ошибки маршрутизации к общей схеме."""
    return JSONResponse(
        {"detail": str(error.detail)}, status_code=error.status_code, headers=error.headers
    )
