"""通知服务（站内 + 邮件/短信，当前为落库占位）。"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Notification

logger = get_logger(__name__)

TEMPLATES = {
    "match_found": "可能匹配到你的物品",
    "claim_status": "认领状态更新",
    "contact_exchanged": "已交换联系方式，请自行约定见面",
    "dispute": "认领进入人工复核",
}


async def notify(
    session: AsyncSession,
    user_id: uuid.UUID,
    template: str,
    payload: dict | None = None,
    channel: str = "inapp",
) -> Notification:
    note = Notification(user_id=user_id, channel=channel, template=template, payload=payload or {})
    session.add(note)
    await session.flush()
    # TODO: 接入 SMTP / 短信网关；异步化（Redis 队列）
    logger.info("通知 user=%s template=%s channel=%s", user_id, template, channel)
    return note
