"""ORM-отображение схемы, описанной в ER-диаграмме и миграции."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import LargeBinary
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class Base(DeclarativeBase):
    """Общие метаданные SQLAlchemy."""


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role", ForeignKey("roles.name", ondelete="CASCADE"), primary_key=True),
    Column("permission", ForeignKey("permissions.name", ondelete="CASCADE"), primary_key=True),
)


class RoleRow(Base):
    """Роль с набором разрешений."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    permissions: Mapped[list[PermissionRow]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )
    accounts: Mapped[list[AccountRow]] = relationship(back_populates="role")


class PermissionRow(Base):
    """Переиспользуемое разрешение на действие."""

    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    roles: Mapped[list[RoleRow]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )


class AccountRow(Base):
    """Учётная запись и параметры хеша пароля."""

    __tablename__ = "accounts"

    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    role_name: Mapped[str] = mapped_column("role", ForeignKey("roles.name"), nullable=False)
    salt: Mapped[bytes] = mapped_column(LargeBinary)
    digest: Mapped[bytes] = mapped_column(LargeBinary)
    blocked: Mapped[bool]
    role: Mapped[RoleRow] = relationship(back_populates="accounts", lazy="selectin")
    meetings: Mapped[list[MeetingRow]] = relationship(back_populates="owner", passive_deletes="all")
    sessions: Mapped[list[SessionRow]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )


class SessionRow(Base):
    """Хеш временного ключа авторизации."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_email: Mapped[str] = mapped_column(ForeignKey("accounts.email", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    account: Mapped[AccountRow] = relationship(back_populates="sessions")


class MeetingRow(Base):
    """Карточка встречи и сохранённое состояние комнаты."""

    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint("minutes BETWEEN 15 AND 180", name="ck_meeting_minutes"),
        CheckConstraint("offset_minutes BETWEEN -1439 AND 1439", name="ck_meeting_offset"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_email: Mapped[str] = mapped_column(ForeignKey("accounts.email"))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    offset_minutes: Mapped[int]
    minutes: Mapped[int]
    status: Mapped[str] = mapped_column(String(24))
    invite: Mapped[str] = mapped_column(String(48), unique=True)
    screen_owner: Mapped[int | None]
    host_microphone: Mapped[bool]
    host_camera: Mapped[bool]
    host_joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    host_left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner: Mapped[AccountRow] = relationship(back_populates="meetings")
    guests: Mapped[list[GuestRow]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GuestRow.id",
    )
    messages: Mapped[list[MessageRow]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MessageRow.id",
    )


class GuestRow(Base):
    """Гостевая заявка и состояние подключения."""

    __tablename__ = "guests"

    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(24))
    hold_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    speaker: Mapped[bool]
    microphone: Mapped[bool]
    camera: Mapped[bool]
    meeting: Mapped[MeetingRow] = relationship(back_populates="guests")
    intervals: Mapped[list[PresenceRow]] = relationship(
        back_populates="guest",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PresenceRow.seq",
    )


class PresenceRow(Base):
    """Один интервал участия гостя."""

    __tablename__ = "presence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["meeting_id", "guest_id"], ["guests.meeting_id", "guests.id"], ondelete="CASCADE"
        ),
    )

    meeting_id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    guest: Mapped[GuestRow] = relationship(back_populates="intervals")


class MessageRow(Base):
    """Сообщение комнаты с последовательным номером."""

    __tablename__ = "messages"

    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    author: Mapped[str] = mapped_column(String(254))
    text: Mapped[str] = mapped_column(String(1000))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    visible: Mapped[bool]
    meeting: Mapped[MeetingRow] = relationship(back_populates="messages")
