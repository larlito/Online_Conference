"""Консольный интерфейс для проверки сценариев встречи в одном терминале."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
from pathlib import Path
from shlex import split

from accounts import Account
from accounts import Accounts
from conferences.models import Guest
from conferences.models import GuestStatus
from conferences.models import Schedule
from conferences.reports import write_attendance
from conferences.room import Room
from conferences.service import Conferences


@dataclass(frozen=True)
class Command:
    """Имя, формат, описание и обработчик команды."""

    syntax: str
    description: str
    action: Callable[..., str]


class Console:
    """Разбирает ввод, управляет текущим пользователем и выводит результаты."""

    def __init__(self, accounts: Accounts, conferences: Conferences, output: Path) -> None:
        """Подключает операции с учётными записями, встречами и отчётами."""
        self._accounts = accounts
        self._conferences = conferences
        self._output = output
        self._account: Account | None = None
        self._guest_session: tuple[Room, Guest] | None = None
        self._commands = (
            Command("login EMAIL", "войти, пароль вводится отдельно", self._login),
            Command("logout", "сбросить текущий вход", self._logout),
            Command("add-host EMAIL", "создать организатора", self._add_host),
            Command(
                "block EMAIL STATE", "заблокировать (on) или разблокировать (off)", self._block
            ),
            Command("create TITLE DATE MINUTES [DESCRIPTION]", "создать встречу", self._create),
            Command("edit ID TITLE DATE MINUTES [DESCRIPTION]", "изменить встречу", self._edit),
            Command("list", "показать свои встречи и приглашения", self._list),
            Command(
                "meeting ACTION ID", "старт, отмена, завершение или замена кода", self._meeting
            ),
            Command("guest INVITE NAME", "подать гостевую заявку", self._guest),
            Command("resume KEY", "вернуться к гостевой заявке и увидеть её статус", self._resume),
            Command("queue ID", "показать заявки и их статусы", self._queue),
            Command(
                "moderate ACTION ID GUEST", "обработать заявку или права гостя", self._moderate
            ),
            Command("join", "подключиться по допуску", self._join),
            Command("leave", "отключиться с возможностью вернуться", self._leave),
            Command("roster ID", "показать подключённых участников и устройства", self._roster),
            Command("device ID TYPE STATE", "изменить состояние устройства", self._device),
            Command("send ID TEXT", "написать в общий чат", self._send),
            Command("chat ID", "прочитать видимые сообщения", self._chat),
            Command("hide ID MESSAGE", "скрыть сообщение", self._hide),
            Command("report ID", "выгрузить CSV после встречи", self._report),
        )
        self._by_name = {command.syntax.split()[0]: command for command in self._commands}

    def run(self) -> None:
        """Читает и выполняет команды до выхода из программы."""
        print("ПК-01 · Консольная платформа онлайн-конференций")
        print("Учебный вход: admin@example.test / Admin-demo-2026")
        print("help — список команд, exit — выход")
        while True:
            try:
                raw = input(f"{self._identity()}> ")
                if raw.strip() == "exit":
                    break
                result = self.execute(raw)
                if result:
                    print(result)
            except ValueError as error:
                print(f"Ошибка · {error}")
            except OSError as error:
                print(f"Ошибка ввода или вывода · {error}")
            except (EOFError, KeyboardInterrupt):
                print()
                break
        print("Работа завершена.")

    def execute(self, raw: str) -> str:
        """Проверяет формат одной команды и возвращает результат."""
        parts = split(raw)
        if not parts:
            return ""
        name, *arguments = parts
        if name == "help" and not arguments:
            return "\n".join(
                f"{command.syntax:<29} {command.description}" for command in self._commands
            )
        command = self._by_name.get(name)
        if command is None:
            raise ValueError("Неизвестная команда. Введите help.")
        parameters = command.syntax.split()[1:]
        required = sum(not parameter.startswith("[") for parameter in parameters)
        if not required <= len(arguments) <= len(parameters):
            raise ValueError(f"Формат команды · {command.syntax}")
        return command.action(*arguments)

    def _identity(self) -> str:
        """Возвращает подпись текущего пользователя для приглашения ввода."""
        if self._guest_session is not None:
            return self._guest_session[1].name
        if self._account is not None:
            return self._account.email
        return "ПК-01"

    def _login(self, email: str) -> str:
        """Открывает сессию администратора или организатора."""
        self._account = self._accounts.authenticate(email, getpass("Пароль: "))
        self._guest_session = None
        return f"Вход · {self._account.role}"

    def _logout(self) -> str:
        """Возвращает терминал в режим выбора пользователя."""
        self._account = None
        self._guest_session = None
        return "Текущий вход сброшен."

    def _add_host(self, email: str) -> str:
        """Запрашивает пароль и регистрирует организатора от имени администратора."""
        admin = self._current_account()
        account = self._accounts.add_host(admin, email, getpass("Пароль организатора: "))
        return f"Организатор создан · {account.email}"

    def _block(self, email: str, state: str) -> str:
        """Изменяет статус организатора и закрывает его встречи при блокировке."""
        blocked = _switch(state)
        account = self._accounts.set_blocked(self._current_account(), email, blocked)
        if blocked:
            self._conferences.close_for(account)
        return f"{account.email} · {'заблокирован' if blocked else 'разблокирован'}"

    def _create(self, title: str, date: str, minutes: str, description: str = "") -> str:
        """Добавляет встречу в кабинет и показывает её приглашение."""
        room = self._conferences.create(
            self._current_account(), _schedule(title, date, minutes, description)
        )
        return _room_label(room)

    def _edit(
        self, room_id: str, title: str, date: str, minutes: str, description: str = ""
    ) -> str:
        """Обновляет расписание своей встречи."""
        room = self._owner_room(room_id)
        room.reschedule(_schedule(title, date, minutes, description), self._conferences.clock())
        return _room_label(room)

    def _list(self) -> str:
        """Показывает карточки вошедшего организатора."""
        rooms = self._conferences.list_owned(self._current_account())
        return "\n".join(_room_label(room) for room in rooms) or "У вас пока нет встреч."

    def _meeting(self, action: str, room_id: str) -> str:
        """Выполняет действие владельца над жизненным циклом встречи."""
        room = self._owner_room(room_id)
        now = self._conferences.clock()
        if action == "start":
            room.start(now)
        elif action == "cancel":
            room.cancel()
        elif action == "finish":
            room.finish(now)
        elif action == "renew":
            room.rotate_invite()
        else:
            raise ValueError("Действия со встречей · start, cancel, finish, renew.")
        return _room_label(room)

    def _guest(self, invite: str, name: str) -> str:
        """Подаёт заявку и переключает терминал на нового гостя."""
        room, guest = self._conferences.request(invite, name)
        self._account = None
        self._guest_session = room, guest
        return f"Заявка #{guest.id} · {guest.status}\nГостевой ключ: {guest.access_key}"

    def _resume(self, key: str) -> str:
        """Переключает терминал на существующего гостя."""
        room, guest = self._conferences.resume(key)
        self._account = None
        self._guest_session = room, guest
        return f"Заявка #{guest.id} · {guest.status}"

    def _queue(self, room_id: str) -> str:
        """Показывает владельцу заявки и их текущее состояние."""
        guests = self._owner_room(room_id).guests()
        return "\n".join(f"#{guest.id} · {guest.name} · {guest.status}" for guest in guests) or (
            "Заявок пока нет."
        )

    def _moderate(self, action: str, room_id: str, guest_id: str) -> str:
        """Обрабатывает гостевую заявку или право на публикацию."""
        room = self._owner_room(room_id)
        number = _number(guest_id)
        now = self._conferences.clock()
        if action in {"admit", "reject"}:
            room.decide(number, action == "admit", now)
        elif action == "kick":
            room.remove(number, now)
        elif action in {"speaker-on", "speaker-off"}:
            room.set_speaker(number, action == "speaker-on")
        else:
            raise ValueError("Действия с гостем · admit, reject, kick, speaker-on, speaker-off.")
        return "Решение принято."

    def _join(self) -> str:
        """Отмечает начало гостевого подключения."""
        room, guest = self._current_guest()
        room.join(guest, self._conferences.clock())
        return f"Вы подключены · {room.schedule.title}"

    def _leave(self) -> str:
        """Отмечает отключение гостя от комнаты."""
        room, guest = self._current_guest()
        room.leave(guest, self._conferences.clock())
        return "Вы отключены. Для возвращения в течение 60 секунд введите join."

    def _roster(self, room_id: str) -> str:
        """Показывает активную комнату и состояния устройств участников."""
        room, guest = self._room_context(room_id)
        room.ensure_access(guest)
        lines = [
            _person_label(
                0, room.owner, True, room.host_microphone, room.host_camera, room.screen_owner
            )
        ]
        for member in room.guests():
            if member.status == GuestStatus.CONNECTED:
                lines.append(
                    _person_label(
                        member.id,
                        member.name,
                        member.speaker,
                        member.microphone,
                        member.camera,
                        room.screen_owner,
                    )
                )
        return "\n".join(lines)

    def _device(self, room_id: str, device: str, state: str) -> str:
        """Меняет учебный флаг устройства."""
        room, guest = self._room_context(room_id)
        room.set_device(guest, device, _switch(state))
        return "Состояние устройства изменено."

    def _send(self, room_id: str, text: str) -> str:
        """Публикует текст в общем чате."""
        room, guest = self._room_context(room_id)
        room.post(guest, text, self._conferences.clock())
        return "Сообщение отправлено."

    def _chat(self, room_id: str) -> str:
        """Выводит доступную историю чата."""
        room, guest = self._room_context(room_id)
        return (
            "\n".join(
                f"#{item.id} {item.sent_at.astimezone(room.schedule.starts_at.tzinfo):%H:%M:%S} "
                f"{item.author} · {item.text}"
                for item in room.messages(guest)
            )
            or "Чат пока пуст."
        )

    def _hide(self, room_id: str, message_id: str) -> str:
        """Скрывает выбранное сообщение от участников."""
        self._owner_room(room_id).hide(_number(message_id))
        return "Сообщение скрыто."

    def _report(self, room_id: str) -> str:
        """Сохраняет отчёт по своей завершённой встрече."""
        path = write_attendance(self._owner_room(room_id), self._output)
        return f"Отчёт сохранён · {path}"

    def _current_account(self) -> Account:
        """Возвращает текущую активную учётную запись."""
        if self._account is None or self._account.blocked:
            raise ValueError("Сначала войдите с помощью login.")
        return self._account

    def _owner_room(self, room_id: str) -> Room:
        """Проверяет, что встреча принадлежит вошедшему организатору."""
        return self._conferences.owned(self._current_account(), _number(room_id))

    def _current_guest(self) -> tuple[Room, Guest]:
        """Возвращает гостевую сессию с учётом прошедшего времени."""
        if self._guest_session is None:
            raise ValueError("Сначала подайте заявку командой guest или используйте resume.")
        return self._conferences.resume(self._guest_session[1].access_key)

    def _room_context(self, room_id: str) -> tuple[Room, Guest | None]:
        """Разрешает владельцу указать номер, а гостю — текущую комнату через прочерк."""
        if room_id == "-":
            return self._current_guest()
        return self._owner_room(room_id), None


def _schedule(title: str, date: str, minutes: str, description: str) -> Schedule:
    """Разбирает дату ISO 8601 и длительность из команды."""
    try:
        starts_at = datetime.fromisoformat(date)
    except ValueError as error:
        raise ValueError("Формат даты · ГГГГ-ММ-ДДTчч:мм+03:00.") from error
    return Schedule(title, starts_at, _number(minutes), description)


def _number(value: str) -> int:
    """Преобразует аргумент команды в целое число."""
    try:
        return int(value)
    except ValueError as error:
        raise ValueError("Укажите целое число.") from error


def _switch(value: str) -> bool:
    """Разбирает переключатель on или off."""
    if value not in {"on", "off"}:
        raise ValueError("Значение должно быть on или off.")
    return value == "on"


def _room_label(room: Room) -> str:
    """Формирует строку карточки конференции."""
    return (
        f"#{room.id} · {room.schedule.title} · {room.status} · "
        f"{room.schedule.starts_at.isoformat(timespec='minutes')} · {room.schedule.minutes} мин · "
        f"приглашение {room.invite}"
        + (f"\nОписание · {room.schedule.description}" if room.schedule.description else "")
    )


def _person_label(
    number: int, name: str, speaker: bool, mic: bool, camera: bool, screen_owner: int | None
) -> str:
    """Формирует строку участника с правами и состояниями устройств."""
    return (
        f"#{number} · {name} · выступает: {'да' if speaker else 'нет'} · "
        f"микрофон: {mic} · камера: {camera} · экран: {screen_owner == number}"
    )
