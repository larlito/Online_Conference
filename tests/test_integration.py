"""Проверки консольного сценария и экспорта отчёта."""

import csv
import re
from datetime import timedelta
from pathlib import Path

import pytest

from accounts import Account
from accounts import Accounts
from cli import Console
from conferences.reports import write_attendance
from conferences.room import Room
from conferences.service import Conferences
from tests.conftest import HOST
from tests.conftest import PASSWORD
from tests.conftest import Clock


def test_report_excludes_connection_gap_and_ignored_guest(
    prepared: tuple[Clock, Accounts, Account, Conferences, Room], tmp_path: Path
) -> None:
    """CSV суммирует два интервала одного гостя и пропускает ожидающего."""
    clock, _, _, conferences, room = prepared
    room.start(clock())
    _, guest = conferences.request(room.invite, "=Гость")
    conferences.request(room.invite, "Ожидающий")
    room.decide(guest.id, True, clock())
    room.join(guest, clock())
    clock.now += timedelta(seconds=30)
    room.leave(guest, clock())
    clock.now += timedelta(seconds=20)
    conferences.resume(guest.access_key)
    room.join(guest, clock())
    clock.now += timedelta(seconds=10)
    room.finish(clock())
    with write_attendance(room, tmp_path).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [(row["display_name"], row["connected_seconds"]) for row in rows] == [
        (HOST, "60"),
        ("'=Гость", "40"),
    ]


def test_console_flow(
    prepared: tuple[Clock, Accounts, Account, Conferences, Room],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Проверяет команды README от входа до выгрузки."""
    clock, accounts, _, conferences, room = prepared
    monkeypatch.setattr("cli.getpass", lambda _: PASSWORD)
    console = Console(accounts, conferences, tmp_path)
    assert "организатор" in console.execute(f"login {HOST}")
    assert "Идёт" in console.execute("meeting start 1")
    response = console.execute(f'guest {room.invite} "Тестовый гость"')
    key = re.search(r"Гостевой ключ: (\S+)", response)
    assert key is not None
    with pytest.raises(ValueError, match="действующему допуску"):
        console.execute("join")
    console.execute(f"login {HOST}")
    console.execute("moderate admit 1 1")
    console.execute(f"resume {key[1]}")
    console.execute("join")
    console.execute('send - "Готов к выступлению"')
    clock.now += timedelta(seconds=3)
    console.execute(f"login {HOST}")
    assert "Готов к выступлению" in console.execute("chat 1")
    console.execute("hide 1 1")
    assert "Чат пока пуст" in console.execute("chat 1")
    console.execute("meeting finish 1")
    assert "attendance_1.csv" in console.execute("report 1")
