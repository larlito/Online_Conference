"""Маршруты встреч, допуска, комнаты и отчётности."""

from typing import Annotated

from fastapi import APIRouter
from fastapi import Path

from api.dependencies import Service
from api.dependencies import Token
from api.errors import errors
from conferences.models import Schedule
from conferences.room import Room
from dtos.requests import ChatInput
from dtos.requests import ConnectionAction
from dtos.requests import DeviceAction
from dtos.requests import GuestApplication
from dtos.requests import MeetingAction
from dtos.requests import MeetingInput
from dtos.requests import Moderation
from dtos.responses import GuestDTO
from dtos.responses import GuestTicketDTO
from dtos.responses import MeetingDTO
from dtos.responses import MessageDTO
from dtos.responses import ReportDTO
from dtos.responses import ResultDTO
from dtos.responses import RoomDTO
from usecases.service import connected_guests

ResourceId = Annotated[int, Path(ge=1, le=2147483647, examples=[1])]
meetings = APIRouter(prefix="/api/meetings", tags=["Встречи"], responses=errors(401, 403, 422, 503))
guests = APIRouter(prefix="/api", tags=["Гостевой доступ"], responses=errors(422, 503))
room = APIRouter(
    prefix="/api/meetings/{meeting_id}",
    tags=["Комната и чат"],
    responses=errors(401, 403, 404, 409, 422, 503),
)


def schedule(payload: MeetingInput) -> Schedule:
    """Преобразует DTO запроса в объект расписания."""
    return Schedule(payload.title, payload.starts_at, payload.minutes, payload.description)


def meeting_dto(current: Room) -> MeetingDTO:
    """Собирает карточку владельца из агрегата."""
    return MeetingDTO(
        id=current.id,
        title=current.schedule.title,
        status=current.status,
        invite=current.invite,
        starts_at=current.schedule.starts_at,
        minutes=current.schedule.minutes,
        description=current.schedule.description,
    )


def room_dto(current: Room) -> RoomDTO:
    """Показывает организатора, подключённых гостей и слот экрана."""
    return RoomDTO(
        host=current.owner,
        host_microphone=current.host_microphone,
        host_camera=current.host_camera,
        screen_owner=current.screen_owner,
        guests=[GuestDTO.model_validate(guest) for guest in connected_guests(current)],
    )


@meetings.get(
    "",
    response_model=list[MeetingDTO],
    summary="Показать встречи",
    description="Возвращает встречи текущего организатора.",
)
def list_meetings(token: Token, service: Service) -> list[MeetingDTO]:
    """Выдаёт список встреч владельца."""
    return [meeting_dto(item) for item in service.list_meetings(token)]


@meetings.post(
    "",
    response_model=MeetingDTO,
    status_code=201,
    responses=errors(400, 409),
    summary="Запланировать встречу",
    description="Проверяет время и выдаёт новый код приглашения.",
)
def create_meeting(payload: MeetingInput, token: Token, service: Service) -> MeetingDTO:
    """Регистрирует встречу организатора."""
    return meeting_dto(service.create(token, schedule(payload)))


@meetings.put(
    "/{meeting_id}",
    response_model=MeetingDTO,
    responses=errors(400, 404, 409),
    summary="Изменить расписание",
    description="Меняет карточку доступной запланированной встречи.",
)
def edit_meeting(
    meeting_id: ResourceId, payload: MeetingInput, token: Token, service: Service
) -> MeetingDTO:
    """Сохраняет изменённое расписание."""
    return meeting_dto(service.edit(token, meeting_id, schedule(payload)))


@meetings.post(
    "/{meeting_id}/actions",
    response_model=MeetingDTO,
    responses=errors(404, 409),
    summary="Управлять встречей",
    description="Запускает, завершает, отменяет встречу или обновляет приглашение.",
)
def meeting_action(
    meeting_id: ResourceId, payload: MeetingAction, token: Token, service: Service
) -> MeetingDTO:
    """Выполняет действие организатора."""
    return meeting_dto(service.change(token, meeting_id, payload.action))


@meetings.get(
    "/{meeting_id}/queue",
    response_model=list[GuestDTO],
    responses=errors(404),
    summary="Получить очередь",
    description="Показывает владельцу заявки и состояния допуска.",
)
def queue(meeting_id: ResourceId, token: Token, service: Service) -> list[GuestDTO]:
    """Выдаёт очередь владельцу."""
    return [GuestDTO.model_validate(item) for item in service.queue(token, meeting_id)]


@meetings.patch(
    "/{meeting_id}/guests/{guest_id}",
    response_model=GuestDTO,
    responses=errors(404, 409),
    summary="Управлять гостем",
    description="Меняет допуск или право выступления.",
)
def moderate(
    meeting_id: ResourceId,
    guest_id: ResourceId,
    payload: Moderation,
    token: Token,
    service: Service,
) -> GuestDTO:
    """Применяет решение организатора."""
    return GuestDTO.model_validate(service.moderate(token, meeting_id, guest_id, payload.action))


@guests.post(
    "/guest-applications",
    response_model=GuestTicketDTO,
    status_code=201,
    responses=errors(404, 409),
    summary="Подать заявку",
    description="Выдаёт гостевой ключ по действующему приглашению.",
)
def apply_guest(payload: GuestApplication, service: Service) -> GuestTicketDTO:
    """Регистрирует заявку гостя."""
    meeting_id, guest = service.request(payload.invite, payload.name)
    return GuestTicketDTO(
        meeting_id=meeting_id, guest=GuestDTO.model_validate(guest), token=guest.access_key
    )


@guests.get(
    "/meetings/{meeting_id}/guest",
    response_model=GuestDTO,
    responses=errors(401, 404),
    summary="Узнать статус заявки",
    description="Определяет заявку по гостевому ключу.",
)
def guest_status(meeting_id: ResourceId, token: Token, service: Service) -> GuestDTO:
    """Возвращает состояние своей заявки."""
    return GuestDTO.model_validate(service.guest_status(token, meeting_id))


@guests.post(
    "/meetings/{meeting_id}/guest/connection",
    response_model=GuestDTO,
    responses=errors(401, 404, 409),
    summary="Войти или выйти из комнаты",
    description="Начинает либо закрывает интервал присутствия.",
)
def connection(
    meeting_id: ResourceId, payload: ConnectionAction, token: Token, service: Service
) -> GuestDTO:
    """Отмечает подключение или временный выход гостя."""
    return GuestDTO.model_validate(service.connection(token, meeting_id, payload.action == "join"))


@room.get(
    "/room",
    response_model=RoomDTO,
    summary="Показать комнату",
    description="Возвращает подключённых участников и состояние устройств.",
)
def roster(meeting_id: ResourceId, token: Token, service: Service) -> RoomDTO:
    """Показывает активную комнату участнику."""
    return room_dto(service.roster(token, meeting_id))


@room.put(
    "/room/device",
    response_model=RoomDTO,
    summary="Изменить состояние устройства",
    description="Проверяет право выступления и занятость показа.",
)
def device(
    meeting_id: ResourceId, payload: DeviceAction, token: Token, service: Service
) -> RoomDTO:
    """Обновляет одно состояние устройства."""
    return room_dto(service.device(token, meeting_id, payload.device, payload.enabled))


@room.get(
    "/messages",
    response_model=list[MessageDTO],
    summary="Прочитать чат",
    description="Показывает видимые сообщения активной комнаты.",
)
def messages(meeting_id: ResourceId, token: Token, service: Service) -> list[MessageDTO]:
    """Получает историю общего чата."""
    return [MessageDTO.model_validate(item) for item in service.messages(token, meeting_id)]


@room.post(
    "/messages",
    response_model=MessageDTO,
    status_code=201,
    summary="Отправить сообщение",
    description="Сохраняет сообщение подключённого участника.",
)
def post(meeting_id: ResourceId, payload: ChatInput, token: Token, service: Service) -> MessageDTO:
    """Публикует сообщение в чате."""
    return MessageDTO.model_validate(service.post(token, meeting_id, payload.text))


@room.delete(
    "/messages/{message_id}",
    response_model=ResultDTO,
    summary="Скрыть сообщение",
    description="Убирает сообщение из общего просмотра.",
)
def hide(
    meeting_id: ResourceId, message_id: ResourceId, token: Token, service: Service
) -> ResultDTO:
    """Скрывает запись по решению владельца."""
    service.hide(token, meeting_id, message_id)
    return ResultDTO(ok=True)


@meetings.get(
    "/{meeting_id}/attendance",
    response_model=ReportDTO,
    responses=errors(404, 409),
    summary="Выгрузить посещаемость",
    description="Формирует CSV завершённой встречи для владельца.",
)
def attendance(meeting_id: ResourceId, token: Token, service: Service) -> ReportDTO:
    """Выдаёт имя файла и текст CSV."""
    return ReportDTO(
        file_name=f"attendance_{meeting_id}.csv", content=service.report(token, meeting_id)
    )
