"""Валидация входных данных API средствами Pydantic."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Annotated
from typing import Literal
from typing import Self

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

Email = Annotated[
    str,
    Field(
        min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+$", examples=["host@example.test"]
    ),
]
Password = Annotated[str, Field(min_length=12, max_length=128, examples=["Host-demo-2026"])]


class RequestDTO(BaseModel):
    """Отклоняет поля, которых нет в контракте."""

    model_config = ConfigDict(extra="forbid")


class Credentials(RequestDTO):
    """Адрес и пароль администратора или организатора."""

    email: Email
    password: Password

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        """Приводит строковый адрес к форме хранилища."""
        return value.strip().lower() if isinstance(value, str) else value


class AccountBlock(RequestDTO):
    """Целевое состояние блокировки организатора."""

    blocked: bool = Field(examples=[True])


class MeetingInput(RequestDTO):
    """Карточка с временем начала и длительностью."""

    title: str = Field(min_length=3, max_length=120, examples=["Защита проекта"])
    starts_at: datetime = Field(examples=["2030-05-12T15:05:00+03:00"])
    minutes: int = Field(ge=15, le=180, examples=[45])
    description: str = Field(default="", max_length=1000, examples=["Показ прототипа"])

    @field_validator("title", "description", mode="before")
    @classmethod
    def trim(cls, value: object) -> object:
        """Удаляет крайние пробелы перед проверкой длины."""
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        """Требует явное смещение и проверяет вычислимость окончания встречи."""

        offset = self.starts_at.utcoffset()
        if offset is None or offset.total_seconds() % 60:
            raise ValueError("Укажите смещение UTC с точностью до минуты.")
        try:
            self.starts_at.astimezone(UTC) + timedelta(minutes=self.minutes)
        except OverflowError as error:
            raise ValueError("Время окончания выходит за допустимый диапазон.") from error
        return self


class MeetingAction(RequestDTO):
    """Переход между состояниями встречи или обновление приглашения."""

    action: Literal["start", "finish", "cancel", "renew"] = Field(examples=["start"])


class GuestApplication(RequestDTO):
    """Гостевая заявка по действующему коду приглашения."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    invite: str = Field(min_length=1, max_length=48, examples=["code-from-meeting"])
    name: str = Field(min_length=2, max_length=60, examples=["Иван Иванов"])


class Moderation(RequestDTO):
    """Решение владельца по гостю."""

    action: Literal["admit", "reject", "kick", "speaker-on", "speaker-off"] = Field(
        examples=["admit"]
    )


class ConnectionAction(RequestDTO):
    """Начало или завершение гостевого подключения."""

    action: Literal["join", "leave"] = Field(examples=["join"])


class DeviceAction(RequestDTO):
    """Состояние выбранного устройства."""

    device: Literal["mic", "camera", "screen"] = Field(examples=["mic"])
    enabled: bool = Field(examples=[True])


class ChatInput(RequestDTO):
    """Сообщение общего чата."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=1000, examples=["Презентация готова"])
