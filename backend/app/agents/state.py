"""LangGraph 共享状态与意图枚举。"""

from __future__ import annotations

import enum
from typing import Any, TypedDict


class Intent(str, enum.Enum):
    report = "report"  # 登记失物/招领
    query = "query"  # 查询进度
    claim = "claim"  # 认领
    other = "other"  # 咨询/其他


class AgentState(TypedDict, total=False):
    # 会话（随 checkpointer 持久化）
    thread_id: str
    user_id: str | None
    history: list[dict[str, str]]  # 多轮对话 [{"role","content"}]
    decision: str | None  # HITL 恢复值
    route_only: bool  # 仅路由不生成（流式接口复用）

    # 输入
    message: str
    image_urls: list[str]
    item_type: str  # LOST / FOUND

    # 中间结果
    intent: str
    parsed: dict[str, Any]
    item_id: str | None
    matches: list[dict[str, Any]]

    # 核验
    verification: dict[str, Any]

    # 输出
    status: str
    reply: str
