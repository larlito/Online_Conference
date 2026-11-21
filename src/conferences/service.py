"""Работа с коллекцией встреч и проверка принадлежности карточек."""

from collections.abc import Callable
from datetime import datetime

from accounts import Account
from accounts import Role
from conferences.models import MeetingStatus
from conferences.models import Schedule
from conferences.room import Room


class Conferences:
    """Координирует доступ к встречам и хранит их до выхода из программы."""

    def __init__(self, clock: Callable[[], datetime]) -> None:
        """Принимает источник времени для операций со встречами."""
        self.clock = clock
        self._rooms: dict[int, Room] = {}

    def create(self, host: Account, schedule: Schedule) -> Room:
        """Добавляет встречу активного организатора."""
        self._check_host(host)
        room_id = len(self._rooms) + 1
        room = Room(room_id, host.email, schedule, self.clock())
        self._rooms[room_id] = room
        return room

    def owned(self, host: Account, room_id: int) -> Room:
        """Возвращает карточку только её владельцу."""
        self._check_host(host)
        room = self._rooms.get(room_id)
        if room is None or room.owner != host.email:
            raise ValueError("Встреча не найдена среди ваших встреч.")
        room.refresh(self.clock())
        return room

    def list_owned(self, host: Account) -> tuple[Room, ...]:
        """Возвращает карточки владельца с актуальными статусами."""
        self._check_host(host)
        now = self.clock()
        rooms = [room for room in self._rooms.values() if room.owner == host.email]
        for room in rooms:
            room.refresh(now)
        upcoming = sorted(
            (room for room in rooms if room.status in {MeetingStatus.PLANNED, MeetingStatus.LIVE}),
            key=lambda room: room.schedule.starts_at,
        )
        closed = sorted(
            (
                room
                for room in rooms
                if room.status in {MeetingStatus.CANCELLED, MeetingStatus.FINISHED}
            ),
            key=lambda room: room.schedule.starts_at,
            reverse=True,
        )
        return (*upcoming, *closed)

    def close_for(self, host: Account) -> None:
        """Закрывает открытые встречи заблокированного организатора."""
        now = self.clock()
        for room in self._rooms.values():
            if room.owner != host.email:
                continue
            room.refresh(now)
            if room.status == MeetingStatus.LIVE:
                room.finish(now)
            elif room.status == MeetingStatus.PLANNED:
                room.cancel()

    @staticmethod
    def _check_host(host: Account) -> None:
        """Проверяет, что действующая роль пользователя — организатор."""
        if host.role != Role.HOST or host.blocked:
            raise ValueError("Действие доступно активному организатору.")
