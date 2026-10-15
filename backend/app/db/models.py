"""核心数据模型（对应 PDR §9）。"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    owner = "owner"  # 失主
    finder = "finder"  # 拾获者
    admin = "admin"  # 管理员/运营


class ItemType(str, enum.Enum):
    lost = "LOST"
    found = "FOUND"


class ItemStatus(str, enum.Enum):
    active = "active"  # 在库/待匹配
    matched = "matched"  # 已匹配
    claimed = "claimed"  # 已认领
    removed = "removed"  # 已清理/下架


class MatchStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"


class ClaimStatus(str, enum.Enum):
    initiated = "initiated"
    verifying = "verifying"
    passed = "passed"
    rejected = "rejected"
    disputed = "disputed"  # 争议/高风险，转人工
    contacted = "contacted"  # 已交换联系方式


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.owner)
    name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # 联系方式验证（短信/邮箱验证码通过）——不强制实名
    contact_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    trust_score: Mapped[float] = mapped_column(Float, default=1.0)


class Item(Base, TimestampMixin):
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[ItemType] = mapped_column(SAEnum(ItemType), index=True)
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    category: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(120))
    color: Mapped[str | None] = mapped_column(String(64))
    material: Mapped[str | None] = mapped_column(String(64))
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 校园地点标签（图书馆/教学楼/食堂...）
    location_tag: Mapped[str | None] = mapped_column(String(120))
    distinguishing_features: Mapped[str | None] = mapped_column(Text)

    status: Mapped[ItemStatus] = mapped_column(
        SAEnum(ItemStatus), default=ItemStatus.active, index=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))
    # 认领成功后用于定时清理
    retention_delete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    images: Mapped[list[ItemImage]] = relationship(
        back_populates="item", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_items_type_status", "type", "status"),)


class ItemImage(Base):
    __tablename__ = "item_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(1024))
    caption: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))

    item: Mapped[Item] = relationship(back_populates="images")


class Match(Base, TimestampMixin):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lost_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"))
    found_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"))
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MatchStatus] = mapped_column(SAEnum(MatchStatus), default=MatchStatus.pending)

    __table_args__ = (
        UniqueConstraint("lost_item_id", "found_item_id", name="uq_match_pair"),
        Index("ix_matches_score", "score"),
    )


class Claim(Base, TimestampMixin):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"))
    claimant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ClaimStatus] = mapped_column(SAEnum(ClaimStatus), default=ClaimStatus.verifying)
    risk_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel), default=RiskLevel.low)
    confidence: Mapped[float | None] = mapped_column(Float)


class VerificationQA(Base):
    __tablename__ = "verification_qa"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    judgement: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ContactExchange(Base):
    __tablename__ = "contact_exchanges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    lost_contact: Mapped[str | None] = mapped_column(String(255))
    found_contact: Mapped[str | None] = mapped_column(String(255))
    consent_lost: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_found: Mapped[bool] = mapped_column(Boolean, default=False)
    exchanged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="inapp")
    template: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class PurgeJob(Base):
    """认领成功后的数据清理任务（PDR §4.7 FR-7.6）。"""

    __tablename__ = "purge_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
