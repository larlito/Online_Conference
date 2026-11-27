"""Адаптеры между строками SQLAlchemy и объектами предметной области."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from hashlib import sha256

from accounts import Account
from accounts import Role
from conferences.models import Guest
from conferences.models import GuestStatus
from conferences.models import MeetingStatus
from conferences.models import Message
from conferences.models import Presence
from conferences.models import Schedule
from conferences.room import Room
from storage.models import AccountRow
from storage.models import GuestRow
from storage.models import MeetingRow
from storage.models import MessageRow
from storage.models import PresenceRow


def token_hash(token: str) -> str:
    """Вычисляет идентификатор ключа для хранения и поиска."""
    return sha256(token.encode()).hexdigest()


def utc(value: datetime) -> datetime:
    """Восстанавливает UTC для метки, которую SQLite вернула без зоны."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def optional_utc(value: datetime | None) -> datetime | None:
    """Нормализует необязательную метку времени."""
    return utc(value) if value is not None else None


def to_account(row: AccountRow) -> Account:
    """Восстанавливает профиль и данные проверки пароля."""
    return Account(row.email, Role(row.role_name), row.salt, row.digest, row.blocked)


def to_account_row(account: Account) -> AccountRow:
    """Преобразует новый профиль в запись базы."""
    return AccountRow(
        email=account.email,
        role_name=account.role.value,
        salt=account.salt,
        digest=account.digest,
        blocked=account.blocked,
    )


def to_guest(row: GuestRow) -> Guest:
    """Восстанавливает заявку, сохраняя исходный ключ только у клиента."""
    return Guest(
        id=row.id,
        name=row.name,
        access_key="",
        status=GuestStatus(row.status),
        hold_until=optional_utc(row.hold_until),
        speaker=row.speaker,
        microphone=row.microphone,
        camera=row.camera,
        intervals=[
            Presence(utc(item.joined_at), optional_utc(item.left_at)) for item in row.intervals
        ],
    )


def to_room(row: MeetingRow) -> Room:
    """Восстанавливает агрегат из SQL без повторного создания встречи."""
    room = Room.__new__(Room)
    room.id = row.id
    room.owner = row.owner_email
    zone = timezone(timedelta(minutes=row.offset_minutes))
    room.schedule = Schedule(
        row.title, utc(row.starts_at).astimezone(zone), row.minutes, row.description
    )
    room.status = MeetingStatus(row.status)
    room.invite = row.invite
    room.screen_owner = row.screen_owner
    room.host_microphone = row.host_microphone
    room.host_camera = row.host_camera
    room.host_presence = (
        Presence(utc(row.host_joined_at), optional_utc(row.host_left_at))
        if row.host_joined_at is not None
        else None
    )
    room._guests = {item.id: to_guest(item) for item in row.guests}
    room._messages = [
        Message(item.id, item.author, item.text, utc(item.sent_at), item.visible)
        for item in row.messages
    ]
    return room


def update_guest(row: GuestRow, guest: Guest) -> None:
    """Записывает состояние заявки и её интервалы, сохраняя существующие ключи."""
    row.status = guest.status.value
    row.hold_until = optional_utc(guest.hold_until)
    row.speaker = guest.speaker
    row.microphone = guest.microphone
    row.camera = guest.camera
    for seq, interval in enumerate(guest.intervals, 1):
        if seq > len(row.intervals):
            row.intervals.append(PresenceRow(seq=seq, joined_at=utc(interval.joined_at)))
        row.intervals[seq - 1].left_at = optional_utc(interval.left_at)


def update_room(row: MeetingRow, room: Room) -> None:
    """Сохраняет поля, заявки, интервалы и видимость сообщений агрегата."""
    schedule = room.schedule
    row.owner_email = room.owner
    row.title = schedule.title
    row.description = schedule.description
    row.starts_at = utc(schedule.starts_at)
    offset = schedule.starts_at.utcoffset()
    row.offset_minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    row.minutes = schedule.minutes
    row.status = room.status.value
    row.invite = room.invite
    row.screen_owner = room.screen_owner
    row.host_microphone = room.host_microphone
    row.host_camera = room.host_camera
    if room.host_presence is not None:
        row.host_joined_at = utc(room.host_presence.joined_at)
        row.host_left_at = optional_utc(room.host_presence.left_at)

    guests = {item.id: item for item in row.guests}
    for guest in room.guests():
        saved = guests.get(guest.id)
        if saved is None:
            saved = GuestRow(id=guest.id, name=guest.name, key_hash=token_hash(guest.access_key))
            row.guests.append(saved)
        update_guest(saved, guest)

    messages = {item.id: item for item in row.messages}
    for message in room._messages:
        saved_message = messages.get(message.id)
        if saved_message is None:
            saved_message = MessageRow(
                id=message.id,
                author=message.author,
                text=message.text,
                sent_at=utc(message.sent_at),
            )
            row.messages.append(saved_message)
        saved_message.visible = message.visible
