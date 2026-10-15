"""FastAPI 入口。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    logger.info("启动 %s v%s (env=%s)", settings.app_name, __version__, settings.environment)
    try:
        from app.services.storage import ensure_bucket

        ensure_bucket()
    except Exception as exc:  # noqa: BLE001 - 对象存储不可用不应阻塞启动
        logger.warning("对象存储初始化跳过: %s", exc)

    # LangGraph checkpointer → 会话持久化与 HITL
    from app.agents import build_graph, set_app
    from app.agents.checkpointer import close_checkpointer, init_checkpointer

    saver = await init_checkpointer()
    set_app(build_graph().compile(checkpointer=saver) if saver else build_graph().compile())
    logger.info("Agent 图已就绪（checkpointer=%s）", "on" if saver else "off")

    yield

    await close_checkpointer()
    logger.info("关闭 %s", settings.app_name)


app = FastAPI(
    title=f"{settings.app_name} API",
    version=__version__,
    description="校园失物招领平台 — 智能匹配 / 核验 / 联系交换",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)

# 本地存储后端：由后端静态提供 /media
if settings.storage_backend.lower() == "local":
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    _media_dir = Path(settings.local_media_dir)
    _media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(_media_dir)), name="media")


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
