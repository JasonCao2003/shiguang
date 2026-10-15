"""LangGraph 共享状态与意图枚举。"""

from __future__ import annotations

import enum
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class Intent(str, enum.Enum):
    report = "report"  # 登记失物/招领
    query = "query"  # 查询进度
    claim = "claim"  # 认领
    other = "other"  # 咨询/其他


class AgentState(TypedDict, total=False):
    # 会话
    messages: Annotated[list, add_messages]
    thread_id: str
    user_id: str | None

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
