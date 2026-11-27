"""Service Layer для SQL-хранилища и существующих правил комнаты."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from secrets import token_urlsafe

from sqlalchemy.orm import Session

from accounts import Account
from accounts import Role
from accounts import build_account
from accounts import matches_password
from conferences.models import Guest
from conferences.models import GuestStatus
from conferences.models import MeetingStatus
from conferences.models import Message
from conferences.models import Schedule
from conferences.reports import attendance_csv
from conferences.room import Room
from storage.mappers import to_account
from storage.mappers import to_room
from storage.mappers import update_room
from storage.mappers import utc
from storage.models import AccountRow
from storage.models import MeetingRow
from storage.repositories import AccountRepository
from storage.repositories import RoomRepository
from usecases.errors import Problem


@dataclass(frozen=True)
class Login:
    """Результат входа с ключом текущей сессии."""

    account: Account
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class MeetingContext:
    """Объект комнаты, его сохранённая запись и текущий гость."""

    row: MeetingRow
    room: Room
    guest: Guest | None = None


class ConferenceService:
    """Координирует действия пользователя в пределах одной SQLAlchemy Session."""

    def __init__(self, session: Session, clock: Callable[[], datetime]) -> None:
        """Использует репозитории с общей транзакцией и передаваемыми часами."""
        self.accounts = AccountRepository(session)
        self.rooms = RoomRepository(session)
        self.clock = clock

    def bootstrap(self, email: str, password: str) -> None:
        """Добавляет администратора при первом запуске, сохраняя существующий профиль."""
        row = self.accounts.find(email)
        if row is None:
            self.accounts.add(build_account(email, password, Role.ADMIN))
        elif row.role_name != Role.ADMIN:
            raise ValueError("Адрес начального администратора принадлежит организатору.")

    def login(self, email: str, password: str) -> Login:
        """Проверяет пароль и создаёт сессию на восемь часов."""
        row = self.accounts.find(email)
        if row is None or row.blocked or not self._allowed(row, "sign_in"):
            raise Problem(401, "Проверьте адрес и пароль.")
        account = to_account(row)
        if not matches_password(account, password):
            raise Problem(401, "Проверьте адрес и пароль.")
        token = token_urlsafe(32)
        expires_at = self.clock() + timedelta(hours=8)
        self.accounts.open_session(token, account.email, expires_at)
        return Login(account, token, expires_at)

    def add_host(self, token: str, email: str, password: str) -> Account:
        """Создаёт организатора по запросу администратора."""
        self._account(token, "manage_accounts")
        if self.accounts.find(email) is not None:
            raise Problem(409, "Этот адрес уже используется.")
        account = build_account(email, password, Role.HOST)
        self.accounts.add(account)
        return account

    def block(self, token: str, email: str, blocked: bool) -> Account:
        """Изменяет блокировку, завершает встречи и отзывает сессии владельца."""
        self._account(token, "manage_accounts")
        row = self.accounts.find(email)
        if row is None or row.role_name != Role.HOST:
            raise Problem(404, "Организатор не найден.")
        row.blocked = blocked
        if blocked:
            self.accounts.revoke(row.email)
            now = self.clock()
            for meeting in self.rooms.owned(row.email):
                current = self._context(meeting)
                if current.room.status == MeetingStatus.LIVE:
                    current.room.finish(now)
                elif current.room.status == MeetingStatus.PLANNED:
                    current.room.cancel()
                self._save(current)
        return to_account(row)

    def list_meetings(self, token: str) -> list[Room]:
        """Возвращает собственные встречи с актуальными состояниями."""
        owner = self._account(token, "manage_meetings")
        rooms = [self._context(row).room for row in self.rooms.owned(owner.email)]
        active = {MeetingStatus.PLANNED, MeetingStatus.LIVE}
        upcoming = sorted((r for r in rooms if r.status in active), key=self._starts_at)
        closed = sorted(
            (r for r in rooms if r.status not in active), key=self._starts_at, reverse=True
        )
        return upcoming + closed

    def create(self, token: str, schedule: Schedule) -> Room:
        """Создаёт встречу организатора с новым приглашением."""
        owner = self._account(token, "manage_meetings")
        now = self.clock()
        if schedule.starts_at <= now:
            raise Problem(400, "Начало встречи должно быть в будущем.")
        room = Room(0, owner.email, schedule, now)
        self.rooms.add(room)
        return room

    def edit(self, token: str, meeting_id: int, schedule: Schedule) -> Room:
        """Изменяет расписание запланированной встречи."""
        current = self._owner_room(token, meeting_id)
        now = self.clock()
        if schedule.starts_at <= now:
            raise Problem(400, "Начало встречи должно быть в будущем.")
        current.room.reschedule(schedule, now)
        return self._save(current)

    def change(self, token: str, meeting_id: int, action: str) -> Room:
        """Запускает, завершает, отменяет встречу или меняет приглашение."""
        current = self._owner_room(token, meeting_id)
        room = current.room
        if action == "start":
            room.start(self.clock())
        elif action == "finish":
            room.finish(self.clock())
        elif action == "cancel":
            room.cancel()
        elif action == "renew":
            room.rotate_invite()
        return self._save(current)

    def request(self, invite: str, name: str) -> tuple[int, Guest]:
        """Принимает заявку по коду и выдаёт гостевой ключ один раз."""
        row = self.rooms.by_invite(invite)
        if row is None:
            raise Problem(404, "Приглашение не найдено или заменено.")
        current = self._context(row)
        guest = current.room.request(name, self.clock())
        self._save(current)
        return current.room.id, guest

    def guest_status(self, token: str, meeting_id: int) -> Guest:
        """Читает состояние собственной заявки по гостевому ключу."""
        return self._guest_room(token, meeting_id)[1]

    def queue(self, token: str, meeting_id: int) -> tuple[Guest, ...]:
        """Возвращает владельцу очередь и состояния заявок."""
        return self._owner_room(token, meeting_id).room.guests()

    def moderate(self, token: str, meeting_id: int, guest_id: int, action: str) -> Guest:
        """Меняет допуск или право выступления гостя."""
        current = self._owner_room(token, meeting_id)
        room = current.room
        guest = next((item for item in room.guests() if item.id == guest_id), None)
        if guest is None:
            raise Problem(404, "Заявка не найдена.")
        if action in {"admit", "reject"}:
            room.decide(guest_id, action == "admit", self.clock())
        elif action == "kick":
            room.remove(guest_id, self.clock())
        elif action in {"speaker-on", "speaker-off"}:
            room.set_speaker(guest_id, action == "speaker-on")
        self._save(current)
        return guest

    def connection(self, token: str, meeting_id: int, join: bool) -> Guest:
        """Открывает или закрывает интервал подключения текущего гостя."""
        current, guest = self._guest_room(token, meeting_id)
        now = self.clock()
        if join:
            current.room.join(guest, now)
        else:
            current.room.leave(guest, now)
        self._save(current)
        return guest

    def roster(self, token: str, meeting_id: int) -> Room:
        """Возвращает состояние комнаты авторизованному участнику."""
        current = self._participant_room(token, meeting_id)
        current.room.ensure_access(current.guest)
        return current.room

    def device(self, token: str, meeting_id: int, name: str, enabled: bool) -> Room:
        """Меняет состояние устройства текущего участника."""
        current = self._participant_room(token, meeting_id)
        current.room.set_device(current.guest, name, enabled)
        return self._save(current)

    def messages(self, token: str, meeting_id: int) -> tuple[Message, ...]:
        """Возвращает видимые сообщения текущему участнику."""
        current = self._participant_room(token, meeting_id)
        return current.room.messages(current.guest)

    def post(self, token: str, meeting_id: int, message: str) -> Message:
        """Добавляет сообщение и возвращает его с номером и временем."""
        current = self._participant_room(token, meeting_id)
        current.room.post(current.guest, message, self.clock())
        self._save(current)
        return current.room.messages(current.guest)[-1]

    def hide(self, token: str, meeting_id: int, message_id: int) -> None:
        """Скрывает сообщение от имени владельца комнаты."""
        current = self._owner_room(token, meeting_id)
        try:
            current.room.hide(message_id)
        except ValueError as error:
            if current.room.status == MeetingStatus.LIVE:
                raise Problem(404, "Сообщение не найдено.") from error
            raise
        self._save(current)

    def report(self, token: str, meeting_id: int) -> str:
        """Возвращает CSV завершённой встречи её владельцу."""
        return attendance_csv(self._owner_room(token, meeting_id).room)

    def _account(self, token: str, permission: str) -> AccountRow:
        """Проверяет сессию, блокировку и разрешение роли."""
        login = self.accounts.find_session(token)
        if login is None or utc(login.expires_at) <= self.clock():
            raise Problem(401, "Требуется войти в систему.")
        row = self.accounts.find(login.account_email)
        if row is None or row.blocked or self.accounts.find_session(token) is None:
            raise Problem(401, "Учётная запись или сессия недоступна.")
        if not self._allowed(row, permission):
            raise Problem(403, "У этой роли нет нужного разрешения.")
        return row

    def _owner_room(self, token: str, meeting_id: int) -> MeetingContext:
        """Проверяет владельца прежде, чем вернуть агрегат."""
        owner = self._account(token, "manage_meetings")
        row = self.rooms.find(meeting_id)
        if row is None or row.owner_email != owner.email:
            raise Problem(404, "Встреча не найдена среди ваших встреч.")
        return self._context(row)

    def _guest_room(self, token: str, meeting_id: int) -> tuple[MeetingContext, Guest]:
        """Проверяет гостевой ключ в пределах указанной встречи."""
        guest_id = self.rooms.guest_id(meeting_id, token)
        if guest_id is None:
            raise Problem(401, "Ключ гостевого доступа недействителен.")
        row = self.rooms.find(meeting_id)
        if row is None:
            raise Problem(404, "Встреча не найдена.")
        current = self._context(row)
        guest = next((item for item in current.room.guests() if item.id == guest_id), None)
        if guest is None:
            raise Problem(404, "Заявка не найдена.")
        return MeetingContext(row, current.room, guest), guest

    def _participant_room(self, token: str, meeting_id: int) -> MeetingContext:
        """Определяет организатора или гостя по виду предъявленного ключа."""
        if self.accounts.find_session(token) is not None:
            return self._owner_room(token, meeting_id)
        return self._guest_room(token, meeting_id)[0]

    def _context(self, row: MeetingRow) -> MeetingContext:
        """Восстанавливает агрегат и применяет истечение времени."""
        room = to_room(row)
        room.refresh(self.clock())
        current = MeetingContext(row, room)
        self._save(current)
        return current

    @staticmethod
    def _save(current: MeetingContext) -> Room:
        """Передаёт изменённый агрегат мапперу в пределах транзакции."""
        update_room(current.row, current.room)
        return current.room

    @staticmethod
    def _allowed(row: AccountRow, permission: str) -> bool:
        """Проверяет разрешение по связи роли с таблицей разрешений."""
        return any(item.name == permission for item in row.role.permissions)

    @staticmethod
    def _starts_at(room: Room) -> datetime:
        """Возвращает начало встречи для сортировки."""
        return room.schedule.starts_at


def connected_guests(room: Room) -> list[Guest]:
    """Отбирает гостей, подключённых к комнате."""
    return [guest for guest in room.guests() if guest.status == GuestStatus.CONNECTED]
