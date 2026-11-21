"""Правила жизненного цикла встречи и работы внутри комнаты."""

from datetime import datetime
from secrets import token_urlsafe

from conferences.models import ENTRY_WINDOW
from conferences.models import MeetingStatus
from conferences.models import Presence
from conferences.models import Schedule


class Room:
    """Хранит состояние одной встречи и проверяет правила переходов."""

    def __init__(self, room_id: int, owner: str, schedule: Schedule, now: datetime) -> None:
        """Создаёт запланированную встречу с действующим приглашением."""
        self.id = room_id
        self.owner = owner
        self.status = MeetingStatus.PLANNED
        self.invite = token_urlsafe(18)
        self.host_presence: Presence | None = None
        self.reschedule(schedule, now)

    def reschedule(self, schedule: Schedule, now: datetime) -> None:
        """Меняет карточку запланированной встречи."""
        if self.status != MeetingStatus.PLANNED:
            raise ValueError("Редактируется только запланированная встреча.")
        if schedule.starts_at <= now:
            raise ValueError("Начало встречи должно быть в будущем.")
        self.schedule = schedule

    def refresh(self, now: datetime) -> None:
        """Применяет истечение времени встречи."""
        if now >= self.schedule.ends_at:
            if self.status == MeetingStatus.LIVE:
                self.finish(self.schedule.ends_at)
            elif self.status == MeetingStatus.PLANNED:
                self.cancel()

    def rotate_invite(self) -> str:
        """Меняет код приглашения."""
        self._require_open()
        self.invite = token_urlsafe(18)
        return self.invite

    def start(self, now: datetime) -> None:
        """Открывает комнату в разрешённое окно и отмечает присутствие организатора."""
        if self.status == MeetingStatus.LIVE:
            return
        if self.status != MeetingStatus.PLANNED or not self._in_entry_window(now):
            raise ValueError("Запуск доступен с 15 минут до начала и до расчётного окончания.")
        self.status = MeetingStatus.LIVE
        self.host_presence = Presence(now)

    def cancel(self) -> None:
        """Закрывает запланированную встречу."""
        if self.status == MeetingStatus.CANCELLED:
            return
        if self.status != MeetingStatus.PLANNED:
            raise ValueError("Отменяется только запланированная встреча.")
        self.status = MeetingStatus.CANCELLED

    def finish(self, now: datetime) -> None:
        """Завершает конференцию и закрывает интервалы присутствия."""
        if self.status == MeetingStatus.FINISHED:
            return
        self._require_live()
        self.status = MeetingStatus.FINISHED
        if self.host_presence is not None:
            self.host_presence.left_at = now

    def _in_entry_window(self, now: datetime) -> bool:
        """Проверяет время открытия и окончания встречи."""
        return self.schedule.starts_at - ENTRY_WINDOW <= now < self.schedule.ends_at

    def _require_open(self) -> None:
        """Проверяет, что встреча допускает работу с приглашением."""
        if self.status not in {MeetingStatus.PLANNED, MeetingStatus.LIVE}:
            raise ValueError("Встреча закрыта.")

    def _require_live(self) -> None:
        """Проверяет, что медиакомната открыта."""
        if self.status != MeetingStatus.LIVE:
            raise ValueError("Встреча сейчас не идёт.")
