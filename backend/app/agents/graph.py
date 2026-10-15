"""LangGraph 图构建（PDR §5.7）。

    START -> record(写入历史) -> classify(intent)
      ├── report -> intake        -> finish
      ├── claim  -> review(interrupt 人工确认) -> claim -> finish
      └── query/other -> chat     -> finish

可选挂载 Postgres Checkpointer 实现持久化与 HITL（interrupt）。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.checkpointer import get_checkpointer
from app.agents.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)

_app = None


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("record", nodes.record_user_node)
    graph.add_node("classify", nodes.classify_node)
    graph.add_node("intake", nodes.intake_node)
    graph.add_node("review", nodes.human_review_node)
    graph.add_node("claim", nodes.claim_node)
    graph.add_node("chat", nodes.chat_node)
    graph.add_node("finish", nodes.finish_node)

    graph.add_edge(START, "record")
    graph.add_edge("record", "classify")
    graph.add_conditional_edges(
        "classify",
        nodes.route_by_intent,
        {"intake": "intake", "review": "review", "chat": "chat"},
    )
    graph.add_edge("intake", "finish")
    graph.add_edge("review", "claim")
    graph.add_edge("claim", "finish")
    graph.add_edge("chat", "finish")
    graph.add_edge("finish", END)

    return graph


def set_app(app: Any) -> None:
    """由启动流程注入带 checkpointer 的编译图。"""
    global _app
    _app = app


def _no_ckpt_app():
    global _app
    if _app is None:
        _app = build_graph().compile()
    return _app


def get_app():
    """返回当前编译图（若已注入 checkpointer 版本则优先使用）。"""
    return _app if _app is not None else _no_ckpt_app()


def has_checkpointer() -> bool:
    return get_checkpointer() is not None


def _config(thread_id: str | None) -> dict[str, Any] | None:
    return {"configurable": {"thread_id": thread_id}} if thread_id else None


async def run_agent(
    state: dict[str, Any],
    thread_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> AgentState:
    """执行一次 Agent 流程（thread_id 存在时状态持久化）。"""
    cfg = config or _config(thread_id)
    return await get_app().ainvoke(state, config=cfg)


async def resume_agent(thread_id: str, decision: str) -> AgentState:
    """用人工决策恢复被 interrupt 暂停的流程。"""
    from langgraph.types import Command

    return await get_app().ainvoke(Command(resume=decision), config=_config(thread_id))


async def get_thread_state(thread_id: str) -> dict[str, Any]:
    """读取某个会话的持久化状态。"""
    snapshot = await get_app().aget_state(_config(thread_id))
    return dict(snapshot.values or {})


async def get_thread_snapshot(thread_id: str) -> dict[str, Any]:
    """读取会话状态及其待执行节点（用于判断是否被 interrupt 暂停）。"""
    snapshot = await get_app().aget_state(_config(thread_id))
    return {
        "values": dict(snapshot.values or {}),
        "next": list(snapshot.next or []),
    }
