"""Agent 工具集（PDR §5.8）。以薄封装形式调用 service 层。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Item
from app.services.embedding import get_embedder
from app.services.llm import DeepSeekClient
from app.services.matching import recall_candidates, rerank

_PARSE_SYSTEM = (
    "你是失物招领登记助手。根据用户描述与图片，抽取结构化字段，只输出 JSON。\n"
    "字段：category, title, brand, color, material, event_time(ISO或空), "
    "location_tag, distinguishing_features, caption(图片内容简述)。\n"
    "不确定的字段留空字符串。"
)

_INTENT_SYSTEM = """判断用户意图，只输出 JSON：{"intent": "report|query|claim|other"}。
- report：发布失物或招领信息
- query：查询某物品是否有匹配/进度
- claim：申请认领某物品
- other：其他咨询"""


async def parse_item(
    llm: DeepSeekClient, text: str, image_urls: list[str] | None = None
) -> dict[str, Any]:
    """Intake Agent：解析结构化字段（deepseek-flash，支持图片）。"""
    if image_urls:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": f"{_PARSE_SYSTEM}\n\n用户描述：{text}"}
        ]
        for url in image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})
        parsed = await llm.complete_json([{"role": "user", "content": content}], thinking=False)
    else:
        parsed = await llm.complete_json(
            [
                {"role": "system", "content": _PARSE_SYSTEM},
                {"role": "user", "content": text},
            ],
            thinking=False,
        )
    return parsed


async def classify_intent(llm: DeepSeekClient, text: str) -> str:
    data = await llm.complete_json(
        [
            {"role": "system", "content": _INTENT_SYSTEM},
            {"role": "user", "content": text},
        ],
        thinking=False,
    )
    intent = str(data.get("intent", "other")).lower()
    return intent if intent in {"report", "query", "claim", "other"} else "other"


async def embed_item(item: Item, image_captions: list[str] | None = None) -> list[float]:
    """生成物品向量。"""
    from app.services.matching import item_embedding_text

    text = await item_embedding_text(item, image_captions)
    return await get_embedder().embed_one(text)


async def search_candidates(session: AsyncSession, item: Item, k: int | None = None) -> list[Item]:
    return await recall_candidates(session, item, k)


async def score_match(lost: Item, found: Item) -> tuple[float, str]:
    return await rerank(lost, found)


def to_match_dict(match: Any) -> dict[str, Any]:
    return {
        "id": str(match.id),
        "lost_item_id": str(match.lost_item_id),
        "found_item_id": str(match.found_item_id),
        "score": match.score,
        "reason": match.reason,
    }


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
