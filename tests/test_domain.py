"""Проверки прав, приглашений и ограничений конференции."""

from datetime import timedelta

import pytest

from accounts import Account
from accounts import Accounts
from conferences.models import GuestStatus
from conferences.models import MeetingStatus
from conferences.room import Room
from conferences.service import Conferences
from tests.conftest import ADMIN
from tests.conftest import HOST
from tests.conftest import PASSWORD
from tests.conftest import Clock


def test_invite_rotation_keeps_existing_request(
    prepared: tuple[Clock, Accounts, Account, Conferences, Room],
) -> None:
    """Прежнее приглашение не принимает новые заявки, сохраняя старые."""
    _, _, _, conferences, room = prepared
    old_invite = room.invite
    _, guest = conferences.request(old_invite, "Anna")
    room.rotate_invite()
    with pytest.raises(ValueError, match="Приглашение не найдено"):
        conferences.request(old_invite, "Boris")
    assert conferences.resume(guest.access_key) == (room, guest)
    assert guest.status == GuestStatus.WAITING


def test_owner_access_and_block(
    prepared: tuple[Clock, Accounts, Account, Conferences, Room],
) -> None:
    """Чужая карточка закрыта, а блокировка завершает активную встречу."""
    clock, accounts, host, conferences, room = prepared
    admin = accounts.authenticate(ADMIN, PASSWORD)
    other = accounts.add_host(admin, "other@example.test", PASSWORD)
    with pytest.raises(ValueError, match="среди ваших"):
        conferences.owned(other, room.id)
    room.start(clock())
    accounts.set_blocked(admin, HOST, True)
    conferences.close_for(host)
    assert room.status == MeetingStatus.FINISHED
    with pytest.raises(ValueError, match="активному организатору"):
        conferences.owned(host, room.id)
    with pytest.raises(ValueError, match="Не удалось войти"):
        accounts.authenticate(HOST, PASSWORD)


def test_room_limit_and_expiring_reservation(
    prepared: tuple[Clock, Accounts, Account, Conferences, Room],
) -> None:
    """Зарезервированное место организатора не выдаётся двадцатому гостю."""
    clock, _, host, conferences, room = prepared
    room.start(clock())
    guests = [conferences.request(room.invite, f"Гость {number}")[1] for number in range(20)]
    for guest in guests[:19]:
        room.decide(guest.id, True, clock())
    with pytest.raises(ValueError, match="Свободных мест нет"):
        room.decide(guests[-1].id, True, clock())
    assert guests[-1].status == GuestStatus.WAITING
    clock.now += timedelta(seconds=60)
    conferences.owned(host, room.id)
    assert guests[0].status == GuestStatus.WAITING
    room.decide(guests[-1].id, True, clock())


def test_speaker_and_screen_limits(
    prepared: tuple[Clock, Accounts, Account, Conferences, Room],
) -> None:
    """Организатор учитывается в лимите, а отзыв права освобождает экран."""
    clock, _, _, conferences, room = prepared
    room.start(clock())
    guests = [conferences.request(room.invite, f"Гость {number}")[1] for number in range(4)]
    for guest in guests:
        room.decide(guest.id, True, clock())
        room.join(guest, clock())
    for guest in guests[:3]:
        room.set_speaker(guest.id, True)
    with pytest.raises(ValueError, match="лимит выступающих"):
        room.set_speaker(guests[3].id, True)
    room.set_device(guests[0], "screen", True)
    room.set_device(guests[0], "mic", True)
    with pytest.raises(ValueError, match="Экран уже"):
        room.set_device(guests[1], "screen", True)
    room.set_speaker(guests[0].id, False)
    assert not guests[0].microphone and room.screen_owner is None
    room.set_device(guests[1], "screen", True)
    assert room.screen_owner == guests[1].id


def test_meeting_expires_at_scheduled_end(
    prepared: tuple[Clock, Accounts, Account, Conferences, Room],
) -> None:
    """При позднем обращении интервал закрывается расчётным временем."""
    clock, _, host, conferences, room = prepared
    room.start(clock())
    clock.now = room.schedule.ends_at + timedelta(minutes=5)
    conferences.owned(host, room.id)
    assert room.status == MeetingStatus.FINISHED
    assert room.host_presence is not None
    assert room.host_presence.left_at == room.schedule.ends_at
