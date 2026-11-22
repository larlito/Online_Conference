"""Правила жизненного цикла встречи и работы внутри комнаты."""

from datetime import datetime
from secrets import token_urlsafe

from conferences.models import CAPACITY
from conferences.models import ENTRY_WINDOW
from conferences.models import RECONNECT_WINDOW
from conferences.models import SPEAKER_LIMIT
from conferences.models import Guest
from conferences.models import GuestStatus
from conferences.models import MeetingStatus
from conferences.models import Message
from conferences.models import Presence
from conferences.models import Schedule
from conferences.models import checked_text


class Room:
    """Хранит состояние одной встречи и проверяет правила переходов."""

    def __init__(self, room_id: int, owner: str, schedule: Schedule, now: datetime) -> None:
        """Создаёт запланированную встречу с действующим приглашением."""
        self.id = room_id
        self.owner = owner
        self.status = MeetingStatus.PLANNED
        self.invite = token_urlsafe(18)
        self.screen_owner: int | None = None
        self.host_microphone = False
        self.host_camera = False
        self.host_presence: Presence | None = None
        self._guests: dict[int, Guest] = {}
        self._messages: list[Message] = []
        self.reschedule(schedule, now)

    def reschedule(self, schedule: Schedule, now: datetime) -> None:
        """Меняет карточку запланированной встречи."""
        if self.status != MeetingStatus.PLANNED:
            raise ValueError("Редактируется только запланированная встреча.")
        if schedule.starts_at <= now:
            raise ValueError("Начало встречи должно быть в будущем.")
        self.schedule = schedule

    def refresh(self, now: datetime) -> None:
        """Применяет истечение времени встречи и временных резервов мест."""
        if now >= self.schedule.ends_at:
            if self.status == MeetingStatus.LIVE:
                self.finish(self.schedule.ends_at)
            elif self.status == MeetingStatus.PLANNED:
                self.cancel()
        for guest in self._guests.values():
            if guest.hold_until is None or now < guest.hold_until:
                continue
            guest.status = (
                GuestStatus.WAITING if guest.status == GuestStatus.APPROVED else GuestStatus.CLOSED
            )
            guest.hold_until = None

    def rotate_invite(self) -> str:
        """Меняет код для новых заявок и сохраняет прежние допуски."""
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
        """Закрывает запланированную встречу и очередь."""
        if self.status == MeetingStatus.CANCELLED:
            return
        if self.status != MeetingStatus.PLANNED:
            raise ValueError("Отменяется только запланированная встреча.")
        self.status = MeetingStatus.CANCELLED
        self._close_guests(self.schedule.starts_at)

    def finish(self, now: datetime) -> None:
        """Завершает конференцию и закрывает интервалы присутствия."""
        if self.status == MeetingStatus.FINISHED:
            return
        self._require_live()
        self.status = MeetingStatus.FINISHED
        if self.host_presence is not None:
            self.host_presence.left_at = now
        self.host_microphone = self.host_camera = False
        self._close_guests(now)

    def request(self, name: str, now: datetime) -> Guest:
        """Принимает заявку в пределах окна гостевого входа."""
        self._require_open()
        if not self._in_entry_window(now):
            raise ValueError("Зал ожидания открывается за 15 минут до начала.")
        guest = Guest(len(self._guests) + 1, checked_text(name, "Имя", 2, 60))
        self._guests[guest.id] = guest
        return guest

    def guests(self) -> tuple[Guest, ...]:
        """Возвращает заявки и участников в порядке их появления."""
        return tuple(self._guests.values())

    def decide(self, guest_id: int, approve: bool, now: datetime) -> None:
        """Отклоняет заявку или резервирует место на 60 секунд."""
        self._require_live()
        guest = self._get_guest(guest_id)
        if guest.status != GuestStatus.WAITING:
            raise ValueError("Заявка больше не находится в очереди.")
        if not approve:
            guest.status = GuestStatus.REJECTED
            return
        occupying = {GuestStatus.APPROVED, GuestStatus.CONNECTED, GuestStatus.OFFLINE}
        if sum(item.status in occupying for item in self._guests.values()) >= CAPACITY - 1:
            raise ValueError("Свободных мест нет. Гость остаётся в очереди.")
        guest.status = GuestStatus.APPROVED
        guest.hold_until = now + RECONNECT_WINDOW

    def join(self, guest: Guest, now: datetime) -> None:
        """Фиксирует первое соединение или возвращение в пределах резерва."""
        self._require_live()
        if self._get_guest(guest.id) is not guest:
            raise ValueError("Гость не относится к этой встрече.")
        if guest.status == GuestStatus.CONNECTED:
            return
        if guest.status not in {GuestStatus.APPROVED, GuestStatus.OFFLINE}:
            raise ValueError("Подключение доступно только по действующему допуску.")
        guest.status = GuestStatus.CONNECTED
        guest.hold_until = None
        guest.intervals.append(Presence(now))

    def leave(self, guest: Guest, now: datetime) -> None:
        """Закрывает текущий интервал и сохраняет место для переподключения."""
        self.ensure_access(guest)
        self._disconnect(guest, now)
        guest.status = GuestStatus.OFFLINE
        guest.hold_until = now + RECONNECT_WINDOW

    def remove(self, guest_id: int, now: datetime) -> None:
        """Отзывает действующий допуск и освобождает место."""
        self._require_live()
        guest = self._get_guest(guest_id)
        if guest.status not in {GuestStatus.APPROVED, GuestStatus.CONNECTED, GuestStatus.OFFLINE}:
            raise ValueError("У гостя нет действующего допуска.")
        self._disconnect(guest, now)
        guest.status = GuestStatus.REMOVED
        guest.hold_until = None

    def set_speaker(self, guest_id: int, enabled: bool) -> None:
        """Назначает выступающего или снимает право и выключает его устройства."""
        guest = self._get_guest(guest_id)
        self.ensure_access(guest)
        if enabled and not guest.speaker:
            if sum(item.speaker for item in self._guests.values()) >= SPEAKER_LIMIT - 1:
                raise ValueError("Достигнут лимит выступающих с учётом организатора.")
            guest.speaker = True
        if not enabled:
            guest.speaker = guest.microphone = guest.camera = False
            if self.screen_owner == guest.id:
                self.screen_owner = None

    def set_device(self, guest: Guest | None, device: str, enabled: bool) -> None:
        """Меняет состояние микрофона, камеры или общего слота демонстрации."""
        self._require_live()
        if guest is not None:
            self.ensure_access(guest)
            if not guest.speaker:
                raise ValueError("У гостя нет права выступления.")
        if device == "screen":
            person = guest.id if guest is not None else 0
            if enabled:
                if self.screen_owner not in {None, person}:
                    raise ValueError("Экран уже демонстрирует другой участник.")
                self.screen_owner = person
            elif self.screen_owner == person:
                self.screen_owner = None
        elif device == "mic":
            if guest is None:
                self.host_microphone = enabled
            else:
                guest.microphone = enabled
        elif device == "camera":
            if guest is None:
                self.host_camera = enabled
            else:
                guest.camera = enabled
        else:
            raise ValueError("Устройства · mic, camera, screen.")

    def post(self, guest: Guest | None, text: str, now: datetime) -> None:
        """Добавляет сообщение от организатора или подключённого гостя."""
        self.ensure_access(guest)
        author = self.owner if guest is None else guest.name
        self._messages.append(
            Message(len(self._messages) + 1, author, checked_text(text, "Сообщение", 1, 1000), now)
        )

    def messages(self, guest: Guest | None) -> tuple[Message, ...]:
        """Возвращает видимые сообщения активной встречи."""
        self.ensure_access(guest)
        return tuple(message for message in self._messages if message.visible)

    def hide(self, message_id: int) -> None:
        """Скрывает сообщение из общего просмотра."""
        self._require_live()
        if not 1 <= message_id <= len(self._messages):
            raise ValueError("Сообщение не найдено.")
        self._messages[message_id - 1].visible = False

    def _get_guest(self, guest_id: int) -> Guest:
        """Возвращает гостя по номеру заявки."""
        if guest_id not in self._guests:
            raise ValueError("Заявка не найдена.")
        return self._guests[guest_id]

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

    def ensure_access(self, guest: Guest | None) -> None:
        """Проверяет доступ организатора или подключённого гостя к комнате."""
        self._require_live()
        if guest is not None:
            if self._get_guest(guest.id) is not guest or guest.status != GuestStatus.CONNECTED:
                raise ValueError("Сначала подключитесь к комнате командой join.")

    def _disconnect(self, guest: Guest, now: datetime) -> None:
        """Выключает устройства гостя и его демонстрацию."""
        guest.close_connection(now)
        if self.screen_owner == guest.id:
            self.screen_owner = None

    def _close_guests(self, now: datetime) -> None:
        """Закрывает очередь и подключения при окончании встречи."""
        self.screen_owner = None
        for guest in self._guests.values():
            if guest.status not in {GuestStatus.REJECTED, GuestStatus.REMOVED}:
                guest.close_connection(now)
                guest.status = GuestStatus.CLOSED
                guest.hold_until = None
