"""匹配引擎：向量召回 + DeepSeek LLM-judge 重排（PDR §6）。

1. recall：用 pgvector 按余弦距离召回 Top-K 反向类型候选。
2. rerank：DeepSeek deepseek-flash 作 judge，输出 score + 理由。
3. decide：按阈值分为高置信 / 观察池 / 忽略。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Item, ItemStatus, ItemType, Match, MatchStatus
from app.services.llm import get_llm

logger = get_logger(__name__)

_RERANK_SYSTEM = """你是失物招领匹配评审。给定"丢失物品"与"拾获物品"的结构化信息，\
判断它们是否为同一件物品。只输出 JSON：
{"score": 0~1 的小数, "reason": "简短中文理由"}
评分参考：类别一致、外观/品牌/颜色一致、时空邻近、特征吻合。"""


def _item_to_text(item: Item) -> str:
    parts = [
        f"类型: {'丢失' if item.type == ItemType.lost else '拾获'}",
        f"标题: {item.title}",
        f"类别: {item.category or '未知'}",
        f"品牌: {item.brand or '未知'}",
        f"颜色: {item.color or '未知'}",
        f"材质: {item.material or '未知'}",
        f"地点: {item.location_tag or '未知'}",
        f"时间: {item.event_time.isoformat() if item.event_time else '未知'}",
        f"描述: {item.description or '无'}",
        f"显著特征: {item.distinguishing_features or '无'}",
    ]
    return "\n".join(parts)


async def recall_candidates(session: AsyncSession, item: Item, k: int | None = None) -> list[Item]:
    """按向量召回反向类型的候选物品。"""
    if item.embedding is None:
        return []
    k = k or settings.match_recall_k
    target_type = ItemType.found if item.type == ItemType.lost else ItemType.lost

    stmt = (
        select(Item)
        .where(
            Item.type == target_type,
            Item.status == ItemStatus.active,
            Item.embedding.is_not(None),
            Item.id != item.id,
        )
        .order_by(Item.embedding.cosine_distance(item.embedding))
        .limit(k)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def rerank(lost_item: Item, found_item: Item) -> tuple[float, str]:
    """DeepSeek LLM-judge 打分 + 理由。"""
    llm = get_llm()
    prompt = (
        f"【丢失物品】\n{_item_to_text(lost_item)}\n\n【拾获物品】\n{_item_to_text(found_item)}"
    )
    data = await llm.complete_json(
        [
            {"role": "system", "content": _RERANK_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        thinking=False,
    )
    try:
        score = float(data.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    reason = str(data.get("reason", "")).strip()
    return score, reason


async def find_and_store_matches(
    session: AsyncSession, item: Item, k: int | None = None
) -> list[Match]:
    """召回 -> 重排 -> 落库，返回达到阈值的匹配。"""
    candidates = await recall_candidates(session, item, k)
    matches: list[Match] = []

    for cand in candidates:
        lost_item, found_item = (item, cand) if item.type == ItemType.lost else (cand, item)
        score, reason = await rerank(lost_item, found_item)
        if score < settings.match_mid_threshold:
            continue

        existing = await session.execute(
            select(Match).where(
                Match.lost_item_id == lost_item.id,
                Match.found_item_id == found_item.id,
            )
        )
        match = existing.scalar_one_or_none()
        if match is None:
            match = Match(
                lost_item_id=lost_item.id,
                found_item_id=found_item.id,
                score=score,
                reason=reason,
                status=MatchStatus.pending,
            )
            session.add(match)
        else:
            match.score = score
            match.reason = reason
        matches.append(match)

    await session.flush()
    high = [m for m in matches if m.score >= settings.match_high_threshold]
    logger.info(
        "匹配完成 item=%s 候选=%d 达标=%d 高置信=%d",
        item.id,
        len(candidates),
        len(matches),
        len(high),
    )
    return high


async def item_embedding_text(item: Item, image_captions: list[str] | None = None) -> str:
    """拼接待向量化文本（含图片 caption）。"""
    text = _item_to_text(item)
    if image_captions:
        text += "\n图片描述: " + "；".join(image_captions)
    return text


def new_match(lost_id: uuid.UUID, found_id: uuid.UUID, score: float, reason: str) -> Match:
    return Match(lost_item_id=lost_id, found_item_id=found_id, score=score, reason=reason)
