"""后台任务：认领成功后的数据留存清理（PDR §4.7 FR-7.6）。

用 ARQ 运行：
    cd backend && uv run arq app.workers.purge.WorkerSettings
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models import Item, ItemStatus, PurgeJob
from app.db.session import SessionLocal

logger = get_logger(__name__)


async def purge_expired(ctx: dict | None = None) -> int:  # noqa: ARG001
    """清理到期物品：标记 removed、删除个人信息、记录执行时间。

    物品记录与图片 URL 的物理删除可在此扩展（含对象存储删除）。
    """
    now = datetime.now(UTC)
    count = 0
    async with SessionLocal() as session:
        jobs = (
            (
                await session.execute(
                    select(PurgeJob).where(
                        PurgeJob.executed_at.is_(None), PurgeJob.scheduled_at <= now
                    )
                )
            )
            .scalars()
            .all()
        )

        for job in jobs:
            item = await session.get(Item, job.item_id)
            if item is not None:
                item.status = ItemStatus.removed
                item.description = None
                item.distinguishing_features = None
                item.embedding = None
            job.executed_at = now
            count += 1
        await session.commit()

    logger.info("清理完成，处理 %d 项", count)
    return count


async def startup(ctx: dict) -> None:  # pragma: no cover
    logger.info("purge worker 启动")


async def shutdown(ctx: dict) -> None:  # pragma: no cover
    logger.info("purge worker 关闭")


class WorkerSettings:  # pragma: no cover
    functions = [purge_expired]
    cron_jobs = []
    on_startup = startup
    on_shutdown = shutdown

    @staticmethod
    def redis_settings():  # type: ignore[override]
        from arq.connections import RedisSettings

        from app.core.config import settings

        return RedisSettings.from_dsn(settings.redis_url)
