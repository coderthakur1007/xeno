"""Security utilities: password hashing, JWT tokens, and FastAPI auth dependencies.

Provides password hashing via SHA-256 with per-password random salt, JWT
access-token creation and validation via PyJWT (HS256), and FastAPI
dependency callables for extracting the current user from a request and
enforcing role-based access control.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.domain.models import Tenant, User


# ---------------------------------------------------------------------------
# Password hashing (hashlib + random salt)
# ---------------------------------------------------------------------------

_SALT_LENGTH = 32  # bytes


def hash_password(password: str) -> str:
    """Hash *password* with a random salt using SHA-256.

    Returns a string in the format ``<hex-salt>$<hex-digest>`` so the salt
    is preserved alongside the digest for later verification.
    """
    salt = os.urandom(_SALT_LENGTH)
    digest = hashlib.sha256(salt + password.encode("utf-8")).hexdigest()
    return f"{salt.hex()}${digest}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify *password* against a previously hashed value.

    Args:
        password: The plaintext password to check.
        hashed: The stored hash in ``<hex-salt>$<hex-digest>`` format.

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    try:
        salt_hex, expected_digest = hashed.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, AttributeError):
        return False
    actual_digest = hashlib.sha256(salt + password.encode("utf-8")).hexdigest()
    # Constant-time comparison via hmac.compare_digest
    import hmac

    return hmac.compare_digest(actual_digest, expected_digest)


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------

_ALGORITHM = "HS256"


def create_access_token(
    data: dict[str, Any],
    settings: Settings | None = None,
) -> str:
    """Create a signed JWT access token.

    The token embeds the provided *data* claims plus an ``exp`` claim derived
    from ``settings.access_token_expire_minutes``.

    Args:
        data: Arbitrary claims to encode.
        settings: App settings (resolved lazily if not supplied).

    Returns:
        Encoded JWT string.
    """
    if settings is None:
        settings = get_settings()
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload["exp"] = expire
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(
    token: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: The raw JWT string.
        settings: App settings (resolved lazily if not supplied).

    Returns:
        The decoded payload dict.

    Raises:
        HTTPException: 401 if the token is expired, invalid, or otherwise
            cannot be decoded.
    """
    if settings is None:
        settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """FastAPI dependency that resolves the current authenticated user.

    Resolution order:
    1. ``Authorization: Bearer <token>`` header → decode JWT → look up user.
    2. ``X-Tenant-Id`` header fallback (demo / backward-compatibility mode):
       looks up the first user for the given tenant.

    Raises:
        HTTPException(401): If no valid credentials are provided or the user
            cannot be found.
    """
    # --- Attempt 1: Bearer token ---
    auth_header: str | None = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        payload = decode_access_token(token, settings)
        user_id = payload.get("user_id") or payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing user identifier")
        try:
            uid = uuid.UUID(str(user_id))
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid user id in token")
        user = db.get(User, uid)
        if user is None or not getattr(user, "is_active", True):
            raise HTTPException(status_code=401, detail="User not found or inactive")
        return user

    # --- Attempt 2: X-Tenant-Id header (demo mode) ---
    tenant_header: str | None = request.headers.get("X-Tenant-Id")
    if tenant_header:
        try:
            tenant_uuid = uuid.UUID(tenant_header)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid X-Tenant-Id")
        tenant = db.get(Tenant, tenant_uuid)
        if tenant is None:
            raise HTTPException(status_code=401, detail="Tenant not found")
        user = db.scalar(select(User).where(User.tenant_id == tenant_uuid).limit(1))
        if user is None:
            raise HTTPException(status_code=401, detail="No user for tenant")
        return user

    raise HTTPException(status_code=401, detail="Missing Authorization header")


def require_role(*roles: str):
    """Dependency factory that checks the current user has one of *roles*.

    Usage::

        @app.get("/admin", dependencies=[Depends(require_role("admin"))])
        def admin_endpoint(): ...

    Or inject the user object::

        @app.get("/admin")
        def admin_endpoint(user: User = Depends(require_role("admin", "marketer"))):
            ...

    Args:
        *roles: One or more role strings that are permitted.

    Returns:
        A FastAPI dependency callable that returns the ``User`` if authorised
        or raises ``HTTPException(403)``.
    """
    allowed = set(roles)

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.role}' is not permitted; required one of {sorted(allowed)}",
            )
        return user

    return _dependency
