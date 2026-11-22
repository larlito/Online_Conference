"""Общая конфигурация тестов встречи."""

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest

from accounts import Account
from accounts import Accounts
from conferences.models import Schedule
from conferences.room import Room
from conferences.service import Conferences

ADMIN = "admin@example.test"
HOST = "host@example.test"
PASSWORD = "Prototype-2026"
START = datetime(2030, 5, 12, 12, tzinfo=UTC)


@dataclass
class Clock:
    """Управляемое время для проверки временных границ."""

    now: datetime = START

    def __call__(self) -> datetime:
        """Возвращает установленный момент."""
        return self.now


@pytest.fixture
def prepared() -> tuple[Clock, Accounts, Account, Conferences, Room]:
    """Создаёт владельца и встречу, которую можно запустить немедленно."""
    clock = Clock()
    accounts = Accounts(ADMIN, PASSWORD)
    admin = accounts.authenticate(ADMIN, PASSWORD)
    host = accounts.add_host(admin, HOST, PASSWORD)
    conferences = Conferences(clock)
    room = conferences.create(host, Schedule("Конференция", clock() + timedelta(minutes=5), 30))
    return clock, accounts, host, conferences, room
