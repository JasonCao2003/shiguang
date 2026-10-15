"""对话助手路由（含 SSE 流式）。"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import run_agent
from app.api.deps import get_optional_user
from app.db.models import User
from app.db.session import get_session
from app.schemas.agent import AgentMatch, ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: Annotated[User | None, Depends(get_optional_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatResponse:
    thread_id = payload.thread_id or uuid.uuid4().hex
    state = {
        "thread_id": thread_id,
        "user_id": str(user.id) if user else None,
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
):
    """SSE 流式对话（骨架：跑完整图后按块推送）。"""
    thread_id = payload.thread_id or uuid.uuid4().hex
    state = {
        "thread_id": thread_id,
        "user_id": str(user.id) if user else None,
        "message": payload.message,
        "image_urls": payload.image_urls,
    }

    async def event_stream():
        result = await run_agent(state)
        meta = json.dumps({"thread_id": thread_id, "intent": result.get("intent")})
        yield f"event: meta\ndata: {meta}\n\n"
        reply = result.get("reply", "")
        for i in range(0, len(reply), 24):
            yield f"data: {json.dumps({'delta': reply[i : i + 24]})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
