"""用户与认证模式。"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.db.models import UserRole
from app.schemas.common import ORMModel


class UserCreate(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None
    name: str | None = None
    password: str = Field(min_length=6)
    role: UserRole = UserRole.owner


class UserRead(ORMModel):
    id: uuid.UUID
    role: UserRole
    name: str | None
    email: str | None
    phone: str | None
    contact_verified: bool
    trust_score: float


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None
    password: str
