"""Проверки прав, приглашений и ограничений конференции."""

from datetime import timedelta

import pytest

from accounts import Account
from accounts import Accounts
from conferences.models import MeetingStatus
from conferences.room import Room
from conferences.service import Conferences
from tests.conftest import ADMIN
from tests.conftest import HOST
from tests.conftest import PASSWORD
from tests.conftest import Clock


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
