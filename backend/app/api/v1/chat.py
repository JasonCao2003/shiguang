"""对话助手路由（SSE 真流式 + 会话持久化 + HITL）。"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.agents import (
    get_app,
    get_thread_snapshot,
    has_checkpointer,
    resume_agent,
    run_agent,
)
from app.agents.nodes import build_chat_messages, retrieve_user_context
from app.api.deps import get_optional_user
from app.db.models import User
from app.schemas.agent import (
    AgentMatch,
    ChatRequest,
    ChatResponse,
    ResumeRequest,
    ThreadState,
)
from app.services.llm import get_llm

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _user_id(user: User | None) -> str | None:
    return str(user.id) if user else None


def _first_interrupt(result: dict[str, Any]) -> dict | None:
    items = result.get("__interrupt__")
    if not items:
        return None
    first = items[0]
    value = getattr(first, "value", None)
    return value if isinstance(value, dict) else {"value": str(value)}


def _to_response(thread_id: str, result: dict[str, Any]) -> ChatResponse:
    interrupt = _first_interrupt(result)
    reply = result.get("reply", "")
    if not reply and interrupt:
        reply = interrupt.get("question", "需要你确认后才能继续。")
    return ChatResponse(
        thread_id=thread_id,
        reply=reply,
        intent=result.get("intent"),
        item_id=uuid.UUID(result["item_id"]) if result.get("item_id") else None,
        matches=[AgentMatch(**m) for m in result.get("matches", [])],
        interrupted=interrupt is not None,
        interrupt=interrupt,
    )


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
    result = await run_agent(state, thread_id=thread_id)
    return _to_response(thread_id, result)


@router.post("/resume", response_model=ChatResponse)
async def resume(
    payload: ResumeRequest,
    user: Annotated[User | None, Depends(get_optional_user)],
) -> ChatResponse:
    """恢复被 HITL interrupt 暂停的会话。"""
    if not has_checkpointer():
        raise HTTPException(status.HTTP_409_CONFLICT, "当前无会话持久化，无法恢复")
    result = await resume_agent(payload.thread_id, payload.decision)
    return _to_response(payload.thread_id, result)


@router.get("/state", response_model=ThreadState)
async def thread_state(
    thread_id: str,
    user: Annotated[User | None, Depends(get_optional_user)],
) -> ThreadState:
    """查看会话的持久化状态（多轮历史 / 是否暂停）。"""
    if not has_checkpointer():
        return ThreadState(thread_id=thread_id)
    snap = await get_thread_snapshot(thread_id)
    values = snap["values"]
    return ThreadState(
        thread_id=thread_id,
        history=values.get("history") or [],
        status=values.get("status"),
        interrupted=bool(snap["next"]),
    )


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    user: Annotated[User | None, Depends(get_optional_user)],
) -> StreamingResponse:
    """SSE 真流式。

    先用同一张图做「路由/检索/HITL」（route_only），再流式生成回复：
    - 命中 HITL → 推 `interrupt` 事件，等待 `/chat/resume`
    - 图已产出回复（登记/认领分支）→ 直接分段推送
    - 其余（查询/其他）→ 逐 token 流式生成并回写历史
    """
    thread_id = payload.thread_id or uuid.uuid4().hex
    user_id = _user_id(user)
    config = {"configurable": {"thread_id": thread_id}}

    async def event_stream() -> AsyncIterator[str]:
        pre = await run_agent(
            {
                "thread_id": thread_id,
                "user_id": user_id,
                "message": payload.message,
                "image_urls": payload.image_urls,
                "route_only": True,
            },
            thread_id=thread_id,
        )

        # 先发 meta（含 thread_id），确保前端即使遇到 HITL 也能拿到会话 ID 去恢复
        yield _sse("meta", {"thread_id": thread_id, "matches": pre.get("matches", [])})

        interrupt = _first_interrupt(pre)
        if interrupt:
            yield _sse("interrupt", interrupt)
            yield _sse("done", {})
            return

        pre_reply = pre.get("reply")
        if pre_reply:
            for i in range(0, len(pre_reply), 12):
                yield _sse("delta", {"delta": pre_reply[i : i + 12]})
        else:
            history = list(pre.get("history") or [])
            context, _ = await retrieve_user_context(user_id)
            messages = build_chat_messages(context, history)
            chunks: list[str] = []
            try:
                async for delta in get_llm().stream(messages, thinking=False):
                    chunks.append(delta)
                    yield _sse("delta", {"delta": delta})
            except Exception as exc:  # noqa: BLE001
                yield _sse("error", {"message": str(exc)})

            if has_checkpointer() and payload.message:
                try:
                    await get_app().aupdate_state(
                        config,
                        {"history": [*history, {"role": "assistant", "content": "".join(chunks)}]},
                    )
                except Exception as exc:  # noqa: BLE001
                    yield _sse("error", {"message": f"历史保存失败：{exc}"})

        yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
