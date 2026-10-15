"""认领、核验与联系方式交换路由（PDR §4.4 / §4.6）。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import _judge_answers  # noqa: PLC2701 - 复用核验判定
from app.api.deps import get_current_user
from app.db.models import (
    Claim,
    ClaimStatus,
    ContactExchange,
    Match,
    RiskLevel,
    User,
    VerificationQA,
)
from app.db.session import get_session
from app.schemas.claim import (
    ClaimCreate,
    ClaimRead,
    ContactExchangeRead,
    VerificationAnswer,
    VerificationQuestion,
    VerificationResult,
)
from app.services.llm import get_llm

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("", response_model=ClaimRead, status_code=status.HTTP_201_CREATED)
async def create_claim(
    payload: ClaimCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Claim:
    match = await session.get(Match, payload.match_id)
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "匹配不存在")
    claim = Claim(match_id=match.id, claimant_id=user.id, status=ClaimStatus.verifying)
    session.add(claim)
    await session.commit()
    await session.refresh(claim)
    return claim


@router.get("/{claim_id}", response_model=ClaimRead)
async def get_claim(
    claim_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> Claim:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "认领不存在")
    return claim


@router.post("/{claim_id}/verify", response_model=VerificationResult)
async def verify_claim(
    claim_id: uuid.UUID,
    answers: list[VerificationAnswer],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VerificationResult:
    """提交核验回答，由 deepseek-flash 判定；低置信/高风险转争议。"""
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "认领不存在")

    verification = {"answers": [a.model_dump() for a in answers]}
    result = await _judge_answers(get_llm(), verification)

    for a in answers:
        session.add(
            VerificationQA(
                claim_id=claim.id,
                question=a.question,
                answer=a.answer,
                judgement=result["judgement"],
                confidence=result["confidence"],
            )
        )
    claim.confidence = result["confidence"]
    claim.risk_level = RiskLevel(result["risk_level"])
    if result["risk_level"] == "high" or not result["passed"]:
        claim.status = ClaimStatus.disputed
    else:
        claim.status = ClaimStatus.passed
    await session.commit()
    return VerificationResult(**result)


@router.post("/{claim_id}/exchange-contacts", response_model=ContactExchangeRead)
async def exchange_contacts(
    claim_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    consent: bool = True,
) -> ContactExchange:
    """核验通过后交换双方联系方式，供自行约定见面。"""
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "认领不存在")
    if claim.status not in (ClaimStatus.passed, ClaimStatus.contacted):
        raise HTTPException(status.HTTP_409_CONFLICT, "认领尚未通过核验")

    exchange = (
        await session.execute(select(ContactExchange).where(ContactExchange.claim_id == claim_id))
    ).scalar_one_or_none()
    if exchange is None:
        exchange = ContactExchange(claim_id=claim_id)
        session.add(exchange)

    if user.id == claim.claimant_id:
        exchange.consent_lost = consent
        exchange.lost_contact = user.email or user.phone
    else:
        exchange.consent_found = consent
        exchange.found_contact = user.email or user.phone

    if exchange.consent_lost and exchange.consent_found:
        exchange.exchanged_at = datetime.now(UTC)
        claim.status = ClaimStatus.contacted

    await session.commit()
    await session.refresh(exchange)
    return exchange


@router.get("/{claim_id}/questions", response_model=list[VerificationQuestion])
async def get_questions(
    claim_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[VerificationQuestion]:
    """生成核验问题（生产应基于物品非公开细节）。"""
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "认领不存在")
    from app.agents.nodes import _generate_questions

    questions = await _generate_questions(get_llm(), str(claim.match_id))
    return [VerificationQuestion(question=q) for q in questions]
