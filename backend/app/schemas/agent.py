"""Agent 对话与会话模式。"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.schemas.item import MatchRead


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # LangGraph 会话 ID（多轮）
    image_urls: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    intent: str | None = None
    item_id: uuid.UUID | None = None
    matches: list[MatchRead] = Field(default_factory=list)


class AgentRunSummary(BaseModel):
    thread_id: str
    status: str
    intent: str | None = None
