"""LangGraph Postgres Checkpointer。

用于：
- 会话持久化（同一 thread_id 跨请求保留状态）→ 多轮记忆
- HITL（`interrupt()` 暂停/恢复）

无数据库时自动降级为无状态（不影响服务启动）。
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_pool: AsyncConnectionPool | None = None
_saver: object | None = None


def _dsn() -> str:
    """Checkpointer 走 psycopg（同步驱动），需把 SQLAlchemy 的 asyncpg 前缀去掉。"""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


async def init_checkpointer():  # noqa: ANN201 - 返回 AsyncPostgresSaver | None
    global _pool, _saver
    if _saver is not None:
        return _saver
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        _pool = AsyncConnectionPool(
            conninfo=_dsn(),
            max_size=5,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        await _pool.open()
        saver = AsyncPostgresSaver(_pool)
        await saver.setup()
        _saver = saver
        logger.info("LangGraph checkpointer 就绪")
    except Exception as exc:  # noqa: BLE001 - 降级为无状态，不阻塞启动
        logger.warning("checkpointer 初始化失败，将退化为无状态: %s", exc)
        _saver = None
    return _saver


async def close_checkpointer() -> None:
    global _pool, _saver
    if _pool is not None:
        try:
            await _pool.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("关闭 checkpointer 连接池出错: %s", exc)
    _pool = None
    _saver = None


def get_checkpointer():  # noqa: ANN201
    return _saver
