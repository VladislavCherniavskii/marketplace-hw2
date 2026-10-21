from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token_or_raise,
    hash_password,
    verify_password,
)
from app.db.models import User, UserRole
from app.db.session import get_db
from app.generated.models import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)

router = APIRouter()


@router.post("/register", status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise AppError("VALIDATION_ERROR", "Email already registered", 400)

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole(data.role.value),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "email": user.email, "role": user.role.value}


@router.post("/login", response_model=TokenPair)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise AppError("TOKEN_INVALID", "Invalid credentials", 401)

    return TokenPair(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
        token_type="bearer",
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token_or_raise(data.refresh_token, "refresh")
    user_id = int(payload["sub"])
    user = await db.get(User, user_id)
    if not user:
        raise AppError("REFRESH_TOKEN_INVALID", "User not found", 401)

    return TokenPair(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
        token_type="bearer",
    )