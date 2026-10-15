"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-15

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIM = 1024

userrole = postgresql.ENUM("owner", "finder", "admin", name="userrole")
itemtype = postgresql.ENUM("LOST", "FOUND", name="itemtype")
itemstatus = postgresql.ENUM("active", "matched", "claimed", "removed", name="itemstatus")
matchstatus = postgresql.ENUM("pending", "confirmed", "rejected", name="matchstatus")
claimstatus = postgresql.ENUM(
    "initiated", "verifying", "passed", "rejected", "disputed", "contacted", name="claimstatus"
)
risklevel = postgresql.ENUM("low", "medium", "high", name="risklevel")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role", userrole, nullable=False),
        sa.Column("name", sa.String(120)),
        sa.Column("email", sa.String(255), unique=True),
        sa.Column("phone", sa.String(32), unique=True),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("contact_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_phone", "users", ["phone"])

    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", itemtype, nullable=False),
        sa.Column("reporter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("category", sa.String(64)),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("brand", sa.String(120)),
        sa.Column("color", sa.String(64)),
        sa.Column("material", sa.String(64)),
        sa.Column("event_time", sa.DateTime(timezone=True)),
        sa.Column("location_tag", sa.String(120)),
        sa.Column("distinguishing_features", sa.Text()),
        sa.Column("status", itemstatus, nullable=False),
        sa.Column("embedding", Vector(DIM)),
        sa.Column("retention_delete_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_items_type", "items", ["type"])
    op.create_index("ix_items_reporter_id", "items", ["reporter_id"])
    op.create_index("ix_items_status", "items", ["status"])
    op.create_index("ix_items_type_status", "items", ["type", "status"])
    op.execute("CREATE INDEX ix_items_embedding ON items USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        "item_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
        ),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("caption", sa.Text()),
        sa.Column("embedding", Vector(DIM)),
    )

    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lost_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id")),
        sa.Column("found_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id")),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("status", matchstatus, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("lost_item_id", "found_item_id", name="uq_match_pair"),
    )
    op.create_index("ix_matches_score", "matches", ["score"])

    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matches.id")),
        sa.Column("claimant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("status", claimstatus, nullable=False),
        sa.Column("risk_level", risklevel, nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "verification_qa",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("judgement", sa.Text()),
        sa.Column("confidence", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "contact_exchanges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
        ),
        sa.Column("lost_contact", sa.String(255)),
        sa.Column("found_contact", sa.String(255)),
        sa.Column("consent_lost", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consent_found", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exchanged_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("channel", sa.String(32), nullable=False, server_default="inapp"),
        sa.Column("template", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64)),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("detail", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "purge_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("purge_jobs")
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("contact_exchanges")
    op.drop_table("verification_qa")
    op.drop_table("claims")
    op.drop_table("matches")
    op.drop_table("item_images")
    op.execute("DROP INDEX IF EXISTS ix_items_embedding")
    op.drop_table("items")
    op.drop_table("users")

    for enum in (risklevel, claimstatus, matchstatus, itemstatus, itemtype, userrole):
        enum.drop(op.get_bind(), checkfirst=True)
