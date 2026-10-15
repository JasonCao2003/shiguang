"""认领与核验模式。"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.db.models import ClaimStatus, RiskLevel
from app.schemas.common import ORMModel


class ClaimCreate(BaseModel):
    match_id: uuid.UUID


class ClaimRead(ORMModel):
    id: uuid.UUID
    match_id: uuid.UUID
    claimant_id: uuid.UUID
    status: ClaimStatus
    risk_level: RiskLevel
    confidence: float | None


class VerificationQuestion(BaseModel):
    question: str


class VerificationAnswer(BaseModel):
    question: str
    answer: str


class VerificationResult(BaseModel):
    passed: bool
    confidence: float
    risk_level: RiskLevel
    judgement: str


class ContactExchangeRead(ORMModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    lost_contact: str | None
    found_contact: str | None
    consent_lost: bool
    consent_found: bool
