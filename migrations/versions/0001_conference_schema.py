"""conference schema

Revision ID: 0001
Revises:
Create Date: 2026-11-23 17:06:20.867107

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "permissions",
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_table(
        "roles",
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_table(
        "accounts",
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("digest", sa.LargeBinary(), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role"],
            ["roles.name"],
        ),
        sa.PrimaryKeyConstraint("email"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("permission", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["permission"], ["permissions.name"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role"], ["roles.name"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role", "permission"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("account_email", sa.String(length=254), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_email"], ["accounts.email"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_email", sa.String(length=254), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("offset_minutes", sa.Integer(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("invite", sa.String(length=48), nullable=False),
        sa.Column("screen_owner", sa.Integer(), nullable=True),
        sa.Column("host_microphone", sa.Boolean(), nullable=False),
        sa.Column("host_camera", sa.Boolean(), nullable=False),
        sa.Column("host_joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("host_left_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("minutes BETWEEN 15 AND 180", name="ck_meeting_minutes"),
        sa.CheckConstraint("offset_minutes BETWEEN -1439 AND 1439", name="ck_meeting_offset"),
        sa.ForeignKeyConstraint(
            ["owner_email"],
            ["accounts.email"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite"),
    )
    op.create_table(
        "guests",
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("hold_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("speaker", sa.Boolean(), nullable=False),
        sa.Column("microphone", sa.Boolean(), nullable=False),
        sa.Column("camera", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("meeting_id", "id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_table(
        "messages",
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(length=254), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("meeting_id", "id"),
    )
    op.create_table(
        "presence",
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("guest_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["meeting_id", "guest_id"], ["guests.meeting_id", "guests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("meeting_id", "guest_id", "seq"),
    )

    op.bulk_insert(
        sa.table("roles", sa.column("name", sa.String())),
        [{"name": "администратор"}, {"name": "организатор"}],
    )
    op.bulk_insert(
        sa.table("permissions", sa.column("name", sa.String())),
        [{"name": "manage_accounts"}, {"name": "manage_meetings"}, {"name": "sign_in"}],
    )
    op.bulk_insert(
        sa.table(
            "role_permissions", sa.column("role", sa.String()), sa.column("permission", sa.String())
        ),
        [
            {"role": "администратор", "permission": "manage_accounts"},
            {"role": "администратор", "permission": "sign_in"},
            {"role": "организатор", "permission": "manage_meetings"},
            {"role": "организатор", "permission": "sign_in"},
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("presence")
    op.drop_table("messages")
    op.drop_table("guests")
    op.drop_table("meetings")
    op.drop_table("auth_sessions")
    op.drop_table("role_permissions")
    op.drop_table("accounts")
    op.drop_table("roles")
    op.drop_table("permissions")
