from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from backend.app.integrations.sentinel_xdr import publish_authentication_event
from backend.app.services.sentinel_login_guard import (
    enabled as sentinel_guard_enabled,
    is_probe_email,
    seconds_remaining as sentinel_hold_remaining,
)
from backend.app.services.login_throttle import (
    clear_login_failures,
    get_login_cooldown_seconds,
    register_failed_login,
)

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
    request: Request,
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:

    # Isolated synthetic-only Sentinel response, distinct from native throttle.
    # No live accounts, Docker/localhost addresses, or forwarding headers blocked.
    if sentinel_guard_enabled() and is_probe_email(payload.email):
        try:
            sentinel_seconds = sentinel_hold_remaining(db, payload.email)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Synthetic login protection is temporarily unavailable",
            ) from exc
        if sentinel_seconds > 0:
            raise HTTPException(
                status_code=429,
                detail="Synthetic login temporarily restricted by Sentinel-XDR.",
                headers={
                    "Retry-After": str(sentinel_seconds),
                    "X-Protection-Source": "Sentinel-XDR",
                },
            )

    try:
        cooldown_seconds = get_login_cooldown_seconds(db, payload.email)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication protection is temporarily unavailable",
        ) from exc

    if cooldown_seconds > 0:
        publish_authentication_event(
            request=request,
            email=payload.email,
            status_code=429,
            outcome="rate_limited",
        )
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(cooldown_seconds)},
        )

    user = db.scalar(select(User).where(User.email == payload.email))

    if user is None or not verify_password(
        payload.password, user.password_hash if user else ""
    ):

        try:
            register_failed_login(db, payload.email)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Authentication protection is temporarily unavailable",
            ) from exc

        publish_authentication_event(
            request=request,
            email=payload.email,
            status_code=401,
            outcome="failure", user_id=str(user.id) if user is not None else None,
            synthetic_probe=(user is None and sentinel_guard_enabled() and is_probe_email(payload.email)),
        )
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        publish_authentication_event(
            request=request,
            email=payload.email,
            status_code=403,
            outcome="denied", user_id=str(user.id),
        )
        raise HTTPException(status_code=403, detail="This account is inactive")


    try:
        clear_login_failures(db, payload.email)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication protection is temporarily unavailable",
        ) from exc

    publish_authentication_event(
        request=request,
        email=payload.email,
        status_code=200,
        outcome="success", user_id=str(user.id),
    )
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id, user.token_version),
        expires_in=settings.access_token_expire_minutes * 60,
        user=user,
    )


@router.get("/me", response_model=UserResponse)
def current_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    return user
