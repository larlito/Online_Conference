"""Проверки API на временной схеме и управляемых часах."""

import csv
from collections.abc import Iterator
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from api.application import create_app
from dtos.requests import MeetingInput
from storage.database import make_engine
from storage.models import AccountRow
from storage.models import GuestRow
from storage.models import RoleRow
from storage.models import SessionRow
from storage.repositories import RoomRepository
from tests.conftest import ADMIN
from tests.conftest import HOST
from tests.conftest import PASSWORD
from tests.conftest import START
from tests.conftest import Clock
from usecases.service import ConferenceService

MEETINGS = "/api/meetings"


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Создаёт отдельную временную SQLite только миграцией Alembic."""
    url = f"sqlite:///{tmp_path / 'conference.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    return url


@pytest.fixture
def client(database: str) -> Iterator[tuple[TestClient, Clock]]:
    """Поднимает приложение в процессе без сторонних сетевых подключений."""
    clock = Clock()
    with TestClient(create_app(database, clock, ADMIN, PASSWORD)) as http:
        yield http, clock


def login(http: TestClient, email: str) -> dict[str, str]:
    """Получает заголовки для тестовой учётной записи."""
    response = http.post("/api/sessions", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def create_host(http: TestClient, email: str = HOST) -> dict[str, str]:
    """Создаёт организатора через административный маршрут."""
    response = http.post(
        "/api/accounts", headers=login(http, ADMIN), json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    assert sorted(response.json()) == ["blocked", "email", "role"]
    return login(http, email)


def meeting_data() -> dict[str, str | int]:
    """Возвращает параметры встречи в пределах окна запуска."""
    return {
        "title": "Защита проекта",
        "starts_at": "2030-05-12T15:05:00+03:00",
        "minutes": 45,
    }


def create_meeting(http: TestClient, owner: dict[str, str]) -> dict[str, object]:
    """Создаёт встречу для сквозных проверок."""
    response = http.post(MEETINGS, headers=owner, json=meeting_data())
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("minutes", [15, 180])
def test_duration_accepts_bounds(minutes: int) -> None:
    """Валидация включает оба крайних допустимых значения."""
    assert MeetingInput.model_validate(meeting_data() | {"minutes": minutes}).minutes == minutes


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("minutes", 14),
        ("minutes", 181),
        ("title", "   "),
        ("title", "x" * 121),
        ("starts_at", "2030-05-12T12:05:00"),
        ("starts_at", "9999-12-31T23:30:00-14:00"),
    ],
)
def test_duration_and_schedule_reject_invalid_values(field: str, value: str | int) -> None:
    """Границы, пустые строки и даты проверяются до обращения к базе."""
    with pytest.raises(ValueError):
        MeetingInput.model_validate(meeting_data() | {field: value})


def test_owners_validation_and_conflicts(client: tuple[TestClient, Clock]) -> None:
    """Проверяет пустой список, коды отказа и нормализацию формы."""
    http, _clock = client
    owner = create_host(http)
    assert http.get(MEETINGS, headers=owner).json() == []
    assert http.get(MEETINGS).status_code == 401
    assert http.get(MEETINGS, headers=login(http, ADMIN)).status_code == 403
    invalid = http.post(MEETINGS, headers=owner, json=meeting_data() | {"minutes": 0})
    assert invalid.status_code == 422 and isinstance(invalid.json()["detail"], str)
    past = http.post(
        MEETINGS, headers=owner, json=meeting_data() | {"starts_at": START.isoformat()}
    )
    assert past.status_code == 400
    created = create_meeting(http, owner)
    meeting_id = created["id"]
    other = create_host(http, "other@example.test")
    assert http.get(f"{MEETINGS}/{meeting_id}/queue", headers=other).status_code == 404
    assert http.get(f"{MEETINGS}/{meeting_id}/attendance", headers=owner).status_code == 409
    duplicate = http.post(
        "/api/accounts",
        headers=login(http, ADMIN),
        json={"email": HOST.upper(), "password": PASSWORD},
    )
    assert duplicate.status_code == 409


def test_web_flow_persists_intervals_and_chat(client: tuple[TestClient, Clock]) -> None:
    """Проходит гостевой сценарий через разные HTTP-запросы и проверяет CSV."""
    http, clock = client
    owner = create_host(http)
    created = create_meeting(http, owner)
    path = f"{MEETINGS}/{created['id']}"
    assert http.post(path + "/actions", headers=owner, json={"action": "start"}).is_success
    ticket = http.post(
        "/api/guest-applications", json={"invite": created["invite"], "name": "Участник"}
    )
    assert ticket.status_code == 201, ticket.text
    guest = {"Authorization": f"Bearer {ticket.json()['token']}"}
    connection_path = path + "/guest/connection"
    assert http.post(connection_path, headers=guest, json={"action": "join"}).status_code == 409
    assert http.get(path + "/guest", headers=guest).json()["status"] == "Ожидает"
    assert http.patch(path + "/guests/1", headers=owner, json={"action": "admit"}).is_success
    assert http.post(connection_path, headers=guest, json={"action": "join"}).is_success
    assert http.patch(path + "/guests/1", headers=owner, json={"action": "speaker-on"}).is_success
    device = http.put(
        path + "/room/device", headers=guest, json={"device": "screen", "enabled": True}
    )
    assert device.json()["screen_owner"] == 1
    assert (
        http.post(path + "/messages", headers=guest, json={"text": "Проверка"}).status_code == 201
    )
    assert http.get(path + "/messages", headers=owner).json()[0]["text"] == "Проверка"
    assert http.delete(path + "/messages/1", headers=owner).is_success
    assert http.get(path + "/messages", headers=guest).json() == []
    assert http.delete(path + "/messages/99", headers=owner).status_code == 404
    clock.now += timedelta(seconds=30)
    assert http.post(connection_path, headers=guest, json={"action": "leave"}).is_success
    clock.now += timedelta(seconds=20)
    assert http.post(connection_path, headers=guest, json={"action": "join"}).is_success
    clock.now += timedelta(seconds=10)
    assert http.post(path + "/actions", headers=owner, json={"action": "finish"}).is_success
    csv_report = http.get(path + "/attendance", headers=owner).json()
    rows = list(csv.DictReader(StringIO(csv_report["content"])))
    assert [row["connected_seconds"] for row in rows] == ["60", "40"]
    assert all(row["first_join_at"].endswith("+03:00") for row in rows)
    assert csv_report["file_name"] == "attendance_1.csv"


def test_reopen_preserves_records_and_hashes(database: str) -> None:
    """После нового запуска встречи сохраняются, секреты хранятся как хеши."""
    with TestClient(create_app(database, Clock(), ADMIN, PASSWORD)) as http:
        owner = create_host(http)
        created = create_meeting(http, owner)
        ticket = http.post(
            "/api/guest-applications", json={"invite": created["invite"], "name": "Гость"}
        )
        assert ticket.status_code == 201
    with TestClient(create_app(database, Clock(), ADMIN, PASSWORD)) as http:
        assert http.get(MEETINGS, headers=owner).json()[0]["title"] == created["title"]

    engine = make_engine(database)
    with Session(engine) as session:
        assert session.scalars(select(RoleRow)).first().permissions
        assert session.scalars(select(AccountRow)).first().digest != PASSWORD.encode()
        assert session.scalars(select(SessionRow)).first().token_hash not in owner["Authorization"]
        assert session.scalars(select(GuestRow)).first().key_hash != ticket.json()["token"]
    assert len(inspect(engine).get_foreign_keys("presence")) == 1
    engine.dispose()


def test_database_failure_is_sanitized(
    client: tuple[TestClient, Clock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Отказ репозитория выдаёт 503 без текста внутреннего SQL."""
    http, _clock = client
    owner = create_host(http)
    failure = Mock(side_effect=OperationalError("SELECT secret", {}, RuntimeError("failed")))
    monkeypatch.setattr(RoomRepository, "owned", failure)
    response = http.get(MEETINGS, headers=owner)
    assert response.status_code == 503
    assert response.json() == {"detail": "Хранилище временно недоступно."}
    failure.assert_called_once()


def test_database_transaction_rolls_back_on_failure(database: str) -> None:
    """Unit of Work откатывает записи, если операция выбрасывает исключение."""
    engine = make_engine(database)
    with pytest.raises(RuntimeError, match="rollback"):
        with Session(engine) as session, session.begin():
            ConferenceService(session, Clock()).bootstrap(ADMIN, PASSWORD)
            session.flush()
            raise RuntimeError("rollback")
    with Session(engine) as session:
        assert session.get(AccountRow, ADMIN) is None
    engine.dispose()


def test_openapi_documents_routes(client: tuple[TestClient, Clock]) -> None:
    """У операций есть описания, схемы успеха и ответы с ErrorDTO."""
    http, _clock = client
    assert http.get("/docs").status_code == 200
    spec = http.get("/openapi.json").json()
    for operations in spec["paths"].values():
        for operation in operations.values():
            assert operation["summary"] and operation["description"] and operation["tags"]
            for code, result in operation["responses"].items():
                assert result["description"]
                schema = result["content"]["application/json"]["schema"]
                if int(code) >= 400:
                    assert schema["$ref"].endswith("/ErrorDTO")
