"""Публичные DTO. Пароли и хеши исключены из ответов."""

from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from accounts import Role
from conferences.models import GuestStatus
from conferences.models import MeetingStatus


class ErrorDTO(BaseModel):
    """Единое сообщение об ошибке."""

    detail: str = Field(examples=["Встреча не найдена среди ваших встреч."])


class AccountDTO(BaseModel):
    """Безопасное представление учётной записи."""

    model_config = ConfigDict(from_attributes=True)
    email: str = Field(examples=["host@example.test"])
    role: Role = Field(examples=[Role.HOST])
    blocked: bool = Field(examples=[False])


class LoginDTO(BaseModel):
    """Временный ключ входа и данные активной роли."""

    model_config = ConfigDict(from_attributes=True)
    account: AccountDTO
    token: str = Field(examples=["session-token"])
    expires_at: datetime = Field(examples=["2030-05-12T23:00:00+03:00"])


class MeetingDTO(BaseModel):
    """Карточка встречи владельца."""

    id: int = Field(examples=[1])
    title: str = Field(examples=["Защита проекта"])
    status: MeetingStatus = Field(examples=[MeetingStatus.PLANNED])
    invite: str = Field(examples=["code-from-meeting"])
    starts_at: datetime = Field(examples=["2030-05-12T15:05:00+03:00"])
    minutes: int = Field(examples=[45])
    description: str = Field(examples=["Показ прототипа"])


class GuestDTO(BaseModel):
    """Состояние заявки без ключа и внутренних интервалов."""

    model_config = ConfigDict(from_attributes=True)
    id: int = Field(examples=[1])
    name: str = Field(examples=["Иван Иванов"])
    status: GuestStatus = Field(examples=[GuestStatus.WAITING])
    speaker: bool = Field(examples=[False])
    microphone: bool = Field(examples=[False])
    camera: bool = Field(examples=[False])


class GuestTicketDTO(BaseModel):
    """Первичный ответ гостю с ключом для следующих запросов."""

    meeting_id: int = Field(examples=[1])
    guest: GuestDTO
    token: str = Field(examples=["guest-token"])


class RoomDTO(BaseModel):
    """Подключённые участники и состояния демонстрации."""

    host: str = Field(examples=["host@example.test"])
    host_microphone: bool = Field(examples=[False])
    host_camera: bool = Field(examples=[False])
    screen_owner: int | None = Field(examples=[None, 0, 1])
    guests: list[GuestDTO]


class MessageDTO(BaseModel):
    """Публичное сообщение чата."""

    model_config = ConfigDict(from_attributes=True)
    id: int = Field(examples=[1])
    author: str = Field(examples=["Иван Иванов"])
    text: str = Field(examples=["Презентация готова"])
    sent_at: datetime = Field(examples=["2030-05-12T12:05:00Z"])


class ResultDTO(BaseModel):
    """Подтверждение выполненного действия."""

    ok: bool = Field(examples=[True])


class ReportDTO(BaseModel):
    """Название файла и его содержимое в формате CSV."""

    file_name: str = Field(examples=["attendance_1.csv"])
    content: str = Field(
        examples=["participant_id,display_name,first_join_at,last_leave_at,connected_seconds"]
    )
