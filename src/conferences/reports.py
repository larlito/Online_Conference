"""Экспорт подтверждённых интервалов присутствия в CSV."""

import csv
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from conferences.models import MeetingStatus
from conferences.models import Presence
from conferences.room import Room


def write_attendance(room: Room, directory: Path) -> Path:
    """Сохраняет отчёт завершённой встречи и возвращает путь к нему."""
    if room.status != MeetingStatus.FINISHED:
        raise ValueError("Отчёт доступен после завершения встречи.")
    participants: list[tuple[int, str, list[Presence]]] = []
    if room.host_presence is not None:
        participants.append((0, room.owner, [room.host_presence]))
    participants.extend(
        (guest.id, guest.name, guest.intervals) for guest in room.guests() if guest.intervals
    )
    participants.sort(key=lambda item: (item[2][0].joined_at, item[0]))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"attendance_{room.id}.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "participant_id",
                "display_name",
                "first_join_at",
                "last_leave_at",
                "connected_seconds",
            )
        )
        for identifier, name, intervals in participants:
            first, last, seconds = _summarize(intervals)
            zone = room.schedule.starts_at.tzinfo
            writer.writerow(
                (
                    identifier,
                    _safe_cell(name),
                    first.astimezone(zone).isoformat(),
                    last.astimezone(zone).isoformat(),
                    seconds,
                )
            )
    return path


def _summarize(intervals: Sequence[Presence]) -> tuple[datetime, datetime, int]:
    """Возвращает границы присутствия и длину подтверждённых интервалов."""
    first = intervals[0].joined_at
    last = intervals[-1].left_at
    if last is None:
        raise ValueError("Присутствие ещё не завершено.")
    seconds = sum(
        (item.left_at - item.joined_at).total_seconds()
        for item in intervals
        if item.left_at is not None
    )
    return first, last, int(seconds)


def _safe_cell(value: str) -> str:
    """Помечает имя, которое табличный редактор мог бы принять за формулу."""
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value
