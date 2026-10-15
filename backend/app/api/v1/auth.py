"""认证路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.db.session import get_session
from app.schemas.user import LoginRequest, Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate, session: Annotated[AsyncSession, Depends(get_session)]
) -> User:
    if not payload.email and not payload.phone:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "需要邮箱或手机号")
    existing = await session.execute(
        select(User).where((User.email == payload.email) | (User.phone == payload.phone))
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户已存在")
    user = User(
        email=payload.email,
        phone=payload.phone,
        name=payload.name,
        role=payload.role,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    payload: LoginRequest, session: Annotated[AsyncSession, Depends(get_session)]
) -> Token:
    stmt = select(User)
    if payload.email:
        stmt = stmt.where(User.email == payload.email)
    else:
        stmt = stmt.where(User.phone == payload.phone)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if (
        user is None
        or not user.password_hash
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号或密码错误")
    token = create_access_token(str(user.id), {"role": user.role.value})
    return Token(access_token=token)
