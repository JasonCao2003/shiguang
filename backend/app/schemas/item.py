"""物品登记与匹配模式。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import ItemStatus, ItemType, MatchStatus
from app.schemas.common import ORMModel


class ItemImageRead(ORMModel):
    id: uuid.UUID
    url: str
    caption: str | None


class ItemCreate(BaseModel):
    type: ItemType
    title: str = Field(max_length=200)
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    color: str | None = None
    material: str | None = None
    event_time: datetime | None = None
    location_tag: str | None = None
    distinguishing_features: str | None = None
    image_urls: list[str] = Field(default_factory=list)


class ItemRead(ORMModel):
    id: uuid.UUID
    type: ItemType
    reporter_id: uuid.UUID
    title: str
    description: str | None
    category: str | None
    brand: str | None
    color: str | None
    material: str | None
    event_time: datetime | None
    location_tag: str | None
    distinguishing_features: str | None
    status: ItemStatus
    images: list[ItemImageRead] = Field(default_factory=list)
    created_at: datetime


class MatchRead(ORMModel):
    id: uuid.UUID
    lost_item_id: uuid.UUID
    found_item_id: uuid.UUID
    score: float
    reason: str | None
    status: MatchStatus
    created_at: datetime


class ParseResult(BaseModel):
    """Intake Agent 结构化解析结果。"""

    category: str | None = None
    title: str | None = None
    brand: str | None = None
    color: str | None = None
    material: str | None = None
    event_time: str | None = None
    location_tag: str | None = None
    distinguishing_features: str | None = None
    caption: str | None = None
