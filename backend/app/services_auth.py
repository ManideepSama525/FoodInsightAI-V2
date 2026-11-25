from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from backend.app.core.config import get_settings

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password, password_hash)
    except Exception:
        return False


def create_access_token(user_id: int, token_version: int = 0) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "ver": int(token_version),
        "iat": now,
        "exp": expires,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_access_token_claims(token: str) -> tuple[int, int] | None:
    """Return (user_id, token_version); legacy tokens are version zero."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
        if payload.get("type") != "access":
            return None
        user_id = int(payload["sub"])
        token_version = int(payload.get("ver", 0))
        if user_id <= 0 or token_version < 0:
            return None
        return user_id, token_version
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        return None


def decode_access_token(token: str) -> int | None:
    claims = decode_access_token_claims(token)
    return claims[0] if claims is not None else None