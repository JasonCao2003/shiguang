"""v1 路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, auth, chat, claims, items, uploads

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(items.router)
api_router.include_router(claims.router)
api_router.include_router(chat.router)
api_router.include_router(uploads.router)
api_router.include_router(admin.router)
