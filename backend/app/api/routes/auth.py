from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from backend.app.services_auth import (
    create_access_token,
    hash_password,
    verify_password,
)
from backend.app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    return user


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))

    if user is None or not verify_password(
        payload.password, user.password_hash if user else ""
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is inactive")

    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
        user=user,
    )


@router.get("/me", response_model=UserResponse)
def current_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    return user
