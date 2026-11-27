"""Запросы SQLAlchemy внутри транзакции вызывающего сервиса."""

from datetime import datetime

from sqlalchemy import Select
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from accounts import Account
from conferences.room import Room
from storage.mappers import to_account_row
from storage.mappers import token_hash
from storage.mappers import update_room
from storage.models import AccountRow
from storage.models import GuestRow
from storage.models import MeetingRow
from storage.models import SessionRow


class AccountRepository:
    """Доступ к учётным записям, ролям и сессиям."""

    def __init__(self, session: Session) -> None:
        """Подключает репозиторий к текущей единице работы."""
        self.session = session

    def find(self, email: str) -> AccountRow | None:
        """Находит и блокирует строку профиля на время операции."""
        return self.session.scalar(
            select(AccountRow).where(AccountRow.email == email.strip().lower()).with_for_update()
        )

    def add(self, account: Account) -> None:
        """Регистрирует профиль в текущей транзакции."""
        self.session.add(to_account_row(account))

    def open_session(self, token: str, email: str, expires_at: datetime) -> None:
        """Сохраняет хеш токена, адрес и срок действия."""
        self.session.add(
            SessionRow(token_hash=token_hash(token), account_email=email, expires_at=expires_at)
        )

    def find_session(self, token: str) -> SessionRow | None:
        """Ищет сессию по хешу предъявленного токена."""
        return self.session.get(SessionRow, token_hash(token), populate_existing=True)

    def revoke(self, email: str) -> None:
        """Завершает все сессии заблокированного профиля."""
        self.session.execute(delete(SessionRow).where(SessionRow.account_email == email))


class RoomRepository:
    """Доступ к агрегатам комнат и их дочерним записям."""

    def __init__(self, session: Session) -> None:
        """Подключает хранилище комнат к текущей транзакции."""
        self.session = session

    def add(self, room: Room) -> None:
        """Добавляет встречу и возвращает ей выданный базой номер."""
        row = MeetingRow()
        update_room(row, room)
        self.session.add(row)
        self.session.flush()
        room.id = row.id

    def find(self, meeting_id: int) -> MeetingRow | None:
        """Загружает комнату с блокировкой строки встречи."""
        return self.session.scalar(self._query().where(MeetingRow.id == meeting_id))

    def owned(self, email: str) -> list[MeetingRow]:
        """Загружает комнаты владельца в порядке номеров блокировок."""
        result = self.session.scalars(
            self._query().where(MeetingRow.owner_email == email).order_by(MeetingRow.id)
        )
        return list(result)

    def by_invite(self, invite: str) -> MeetingRow | None:
        """Находит комнату по действующему приглашению."""
        return self.session.scalar(self._query().where(MeetingRow.invite == invite))

    def guest_id(self, meeting_id: int, token: str) -> int | None:
        """Возвращает номер заявки только для комнаты и подходящего ключа."""
        return self.session.scalar(
            select(GuestRow.id).where(
                GuestRow.meeting_id == meeting_id, GuestRow.key_hash == token_hash(token)
            )
        )

    @staticmethod
    def _query() -> Select[tuple[MeetingRow]]:
        """Сериализует изменения агрегата в PostgreSQL и загружает дочерние записи."""
        return (
            select(MeetingRow)
            .options(
                selectinload(MeetingRow.guests).selectinload(GuestRow.intervals),
                selectinload(MeetingRow.messages),
            )
            .with_for_update()
        )
