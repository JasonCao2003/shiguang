"""Agent 对话与会话模式。"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class AgentMatch(BaseModel):
    """Agent 返回的候选匹配（非 ORM，字段较精简）。"""

    id: str
    lost_item_id: str
    found_item_id: str
    score: float
    reason: str | None = None


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # LangGraph 会话 ID（多轮）
    image_urls: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    intent: str | None = None
    item_id: uuid.UUID | None = None
    matches: list[AgentMatch] = Field(default_factory=list)
    # HITL
    interrupted: bool = False
    interrupt: dict | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    decision: str


class ThreadState(BaseModel):
    thread_id: str
    history: list[dict] = Field(default_factory=list)
    status: str | None = None
    interrupted: bool = False


class AgentRunSummary(BaseModel):
    thread_id: str
    status: str
    intent: str | None = None
