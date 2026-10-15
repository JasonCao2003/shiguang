"""物品登记与匹配路由。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_user
from app.db.models import Item, ItemImage, ItemStatus, ItemType, Match, User
from app.db.session import get_session
from app.schemas.item import ItemCreate, ItemRead, MatchRead
from app.services.matching import find_and_store_matches

router = APIRouter(prefix="/items", tags=["items"])


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: ItemCreate,
    user: Annotated[User | None, Depends(get_optional_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Item:
    """提交失物/招领（文字 + 图片 URL），并实时匹配。"""
    from app.agents.tools import embed_item, parse_item
    from app.services.llm import get_llm

    parsed = await parse_item(get_llm(), payload.description or payload.title, payload.image_urls)

    item = Item(
        type=payload.type,
        reporter_id=user.id if user else uuid.uuid4(),
        title=payload.title,
        description=payload.description,
        category=payload.category or parsed.get("category") or None,
        brand=payload.brand or parsed.get("brand") or None,
        color=payload.color or parsed.get("color") or None,
        material=payload.material or parsed.get("material") or None,
        event_time=payload.event_time,
        location_tag=payload.location_tag or parsed.get("location_tag") or None,
        distinguishing_features=payload.distinguishing_features
        or parsed.get("distinguishing_features")
        or None,
        status=ItemStatus.active,
    )
    captions = [parsed["caption"]] if parsed.get("caption") else []
    item.embedding = await embed_item(item, captions)

    session.add(item)
    for url in payload.image_urls:
        session.add(ItemImage(item_id=item.id, url=url, caption=parsed.get("caption")))
    await session.flush()

    await find_and_store_matches(session, item)
    await session.commit()
    await session.refresh(item)
    return item


@router.get("", response_model=list[ItemRead])
async def list_items(
    session: Annotated[AsyncSession, Depends(get_session)],
    type: ItemType | None = None,
    limit: int = 50,
) -> list[Item]:
    stmt = select(Item).where(Item.status != ItemStatus.removed)
    if type:
        stmt = stmt.where(Item.type == type)
    stmt = stmt.order_by(Item.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{item_id}", response_model=ItemRead)
async def get_item(
    item_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> Item:
    item = await session.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "物品不存在")
    return item


@router.get("/{item_id}/matches", response_model=list[MatchRead])
async def get_matches(
    item_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[Match]:
    stmt = (
        select(Match)
        .where((Match.lost_item_id == item_id) | (Match.found_item_id == item_id))
        .order_by(Match.score.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post("/{item_id}/rematch", response_model=list[MatchRead])
async def rematch(
    item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[Match]:
    item = await session.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "物品不存在")
    matches = await find_and_store_matches(session, item)
    await session.commit()
    return matches
