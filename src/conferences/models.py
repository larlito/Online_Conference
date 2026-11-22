"""Состояния встречи, гостевого допуска и посещаемости."""

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from enum import StrEnum
from secrets import token_urlsafe

CAPACITY = 20
ENTRY_WINDOW = timedelta(minutes=15)
RECONNECT_WINDOW = timedelta(seconds=60)


class MeetingStatus(StrEnum):
    """Статусы конференции."""

    PLANNED = "Запланирована"
    LIVE = "Идёт"
    FINISHED = "Завершена"
    CANCELLED = "Отменена"


class GuestStatus(StrEnum):
    """Статусы гостевой заявки и подключения."""

    WAITING = "Ожидает"
    APPROVED = "Допущен"
    CONNECTED = "В комнате"
    OFFLINE = "Связь прервана"
    REJECTED = "Отклонён"
    REMOVED = "Удалён"
    CLOSED = "Доступ закрыт"


def checked_text(value: str, title: str, minimum: int, maximum: int) -> str:
    """Убирает крайние пробелы и проверяет длину пользовательского текста."""
    value = value.strip()
    if not minimum <= len(value) <= maximum:
        raise ValueError(f"{title} · допустимая длина от {minimum} до {maximum}.")
    return value


@dataclass(frozen=True)
class Schedule:
    """Карточка запланированной встречи с явным смещением времени."""

    title: str
    starts_at: datetime
    minutes: int
    description: str = ""

    def __post_init__(self) -> None:
        """Проверяет введённые значения до создания карточки."""
        object.__setattr__(self, "title", checked_text(self.title, "Тема", 3, 120))
        object.__setattr__(self, "description", checked_text(self.description, "Описание", 0, 1000))
        if self.starts_at.utcoffset() is None:
            raise ValueError("Укажите дату со смещением, например +03:00 или Z.")
        if not 15 <= self.minutes <= 180:
            raise ValueError("Длительность должна составлять от 15 до 180 минут.")

    @property
    def ends_at(self) -> datetime:
        """Возвращает расчётное окончание встречи."""
        return self.starts_at + timedelta(minutes=self.minutes)


@dataclass
class Presence:
    """Интервал между подключением и выходом из комнаты."""

    joined_at: datetime
    left_at: datetime | None = None


@dataclass
class Guest:
    """Заявка, приватный ключ восстановления и состояние устройств гостя."""

    id: int
    name: str
    access_key: str = field(default_factory=lambda: token_urlsafe(18), repr=False)
    status: GuestStatus = GuestStatus.WAITING
    hold_until: datetime | None = None
    speaker: bool = False
    microphone: bool = False
    camera: bool = False
    intervals: list[Presence] = field(default_factory=list)

    def close_connection(self, now: datetime) -> None:
        """Закрывает открытый интервал и отключает устройства."""
        if self.intervals and self.intervals[-1].left_at is None:
            self.intervals[-1].left_at = now
        self.speaker = False
        self.microphone = False
        self.camera = False
