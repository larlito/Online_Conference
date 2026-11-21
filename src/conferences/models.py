"""Состояния встречи, её расписание и посещаемость."""

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from enum import StrEnum

ENTRY_WINDOW = timedelta(minutes=15)


class MeetingStatus(StrEnum):
    """Статусы конференции."""

    PLANNED = "Запланирована"
    LIVE = "Идёт"
    FINISHED = "Завершена"
    CANCELLED = "Отменена"


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
