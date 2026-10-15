"""LangGraph 图构建（PDR §5.7）。

    START -> classify(intent)
      ├── report -> intake  -> finish
      ├── claim  -> verify  -> finish
      └── query  -> chat    -> finish

可选挂载 Postgres Checkpointer 实现持久化与 HITL（interrupt）。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("classify", nodes.classify_node)
    graph.add_node("intake", nodes.intake_node)
    graph.add_node("verify", nodes.verify_node)
    graph.add_node("chat", nodes.chat_node)
    graph.add_node("finish", nodes.finish_node)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify",
        nodes.route_by_intent,
        {"intake": "intake", "verify": "verify", "chat": "chat"},
    )
    graph.add_edge("intake", "finish")
    graph.add_edge("verify", "finish")
    graph.add_edge("chat", "finish")
    graph.add_edge("finish", END)

    return graph


# 默认无 checkpointer 的编译图（开发/无状态运行）
compiled_graph = build_graph().compile()


async def run_agent(state: dict[str, Any], config: dict[str, Any] | None = None) -> AgentState:
    """执行一次 Agent 流程。"""
    return await compiled_graph.ainvoke(state, config=config)


async def build_graph_with_checkpointer():  # pragma: no cover - 需要 Postgres
    """带 Postgres Checkpointer 的编译图，用于多轮与 HITL。

    用法：
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        async with AsyncPostgresSaver.from_conn_string(DSN) as saver:
            await saver.setup()
            app = build_graph().compile(checkpointer=saver)
            await app.ainvoke(state, config={"configurable": {"thread_id": tid}})
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from app.core.config import settings

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    saver = AsyncPostgresSaver.from_conn_string(dsn)
    await saver.setup()
    return build_graph().compile(checkpointer=saver)
