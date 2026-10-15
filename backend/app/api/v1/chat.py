"""对话助手路由（含 SSE 真流式）。"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agents import run_agent
from app.agents.nodes import build_chat_messages, retrieve_user_context
from app.api.deps import get_optional_user
from app.db.models import User
from app.schemas.agent import AgentMatch, ChatRequest, ChatResponse
from app.services.llm import get_llm

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _user_id(user: User | None) -> str | None:
    return str(user.id) if user else None


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: Annotated[User | None, Depends(get_optional_user)],
) -> ChatResponse:
    thread_id = payload.thread_id or uuid.uuid4().hex
    state = {
        "thread_id": thread_id,
        "user_id": _user_id(user),
        "message": payload.message,
        "image_urls": payload.image_urls,
    }
    result = await run_agent(state)
    return ChatResponse(
        thread_id=thread_id,
        reply=result.get("reply", ""),
        intent=result.get("intent"),
        item_id=uuid.UUID(result["item_id"]) if result.get("item_id") else None,
        matches=[AgentMatch(**m) for m in result.get("matches", [])],
    )


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    user: Annotated[User | None, Depends(get_optional_user)],
) -> StreamingResponse:
    """SSE 真流式：先推 meta（含匹配），再逐 token 推送回复增量。"""
    thread_id = payload.thread_id or uuid.uuid4().hex
    context, matches = await retrieve_user_context(_user_id(user))
    messages = build_chat_messages(context, payload.message)

    async def event_stream() -> AsyncIterator[str]:
        yield _sse("meta", {"thread_id": thread_id, "matches": matches})
        try:
            async for delta in get_llm().stream(messages, thinking=False):
                yield _sse("delta", {"delta": delta})
        except Exception as exc:  # noqa: BLE001 - 流中断时告知前端
            yield _sse("error", {"message": str(exc)})
        yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
