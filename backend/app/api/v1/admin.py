"""管理员路由：争议/高风险认领审核。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.models import Claim, ClaimStatus, User
from app.db.session import get_session
from app.schemas.claim import ClaimRead

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/claims", response_model=list[ClaimRead])
async def list_disputed_claims(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Claim]:
    stmt = select(Claim).where(Claim.status == ClaimStatus.disputed)
    return list((await session.execute(stmt)).scalars().all())


@router.post("/claims/{claim_id}/approve", response_model=ClaimRead)
async def approve_claim(
    claim_id: uuid.UUID,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Claim:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "认领不存在")
    claim.status = ClaimStatus.passed
    await session.commit()
    await session.refresh(claim)
    return claim


@router.post("/claims/{claim_id}/reject", response_model=ClaimRead)
async def reject_claim(
    claim_id: uuid.UUID,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Claim:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "认领不存在")
    claim.status = ClaimStatus.rejected
    await session.commit()
    await session.refresh(claim)
    return claim
