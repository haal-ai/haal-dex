"""Authentication service with JWT token issuance and validation."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import jwt

from app.config import Settings, get_settings
from app.models.auth import AuthToken, LoginRequest, UserContext


# ---------------------------------------------------------------------------
# In-memory user store (replaceable with a DB later)
# Passwords are stored as SHA-256 hex digests.
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    """Return the SHA-256 hex digest of *password*."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# Pre-seeded users for development / testing.
_USERS: dict[str, dict] = {
    "admin": {
        "user_id": "user-001",
        "username": "admin",
        "password_hash": _hash_password("admin"),
        "roles": ["admin", "user"],
    },
    "user": {
        "user_id": "user-002",
        "username": "user",
        "password_hash": _hash_password("user"),
        "roles": ["user"],
    },
}


class AuthService:
    """Handles credential validation, JWT issuance, and role checking."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def authenticate(self, credentials: LoginRequest) -> AuthToken:
        """Validate credentials and return a signed JWT token.

        Raises ``ValueError`` when the username is unknown or the password
        does not match.
        """
        record = _USERS.get(credentials.username)
        if record is None:
            raise ValueError("Invalid username or password")

        if record["password_hash"] != _hash_password(credentials.password):
            raise ValueError("Invalid username or password")

        expires_delta = timedelta(minutes=self._settings.jwt_expiration_minutes)
        expire = datetime.now(timezone.utc) + expires_delta

        payload = {
            "sub": record["user_id"],
            "username": record["username"],
            "roles": record["roles"],
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }

        access_token = jwt.encode(
            payload,
            self._settings.secret_key,
            algorithm=self._settings.jwt_algorithm,
        )

        return AuthToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=int(expires_delta.total_seconds()),
            user_id=record["user_id"],
            roles=record["roles"],
        )

    async def validate_token(self, token: str) -> UserContext:
        """Decode and validate a JWT token, returning the user context.

        Raises ``ValueError`` for expired or otherwise invalid tokens.
        """
        try:
            payload = jwt.decode(
                token,
                self._settings.secret_key,
                algorithms=[self._settings.jwt_algorithm],
            )
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as exc:
            raise ValueError(f"Invalid token: {exc}")

        return UserContext(
            user_id=payload["sub"],
            username=payload["username"],
            roles=payload.get("roles", []),
            token=token,
        )

    def has_role(self, user: UserContext, required_role: str) -> bool:
        """Return ``True`` if *user* possesses *required_role*."""
        return required_role in user.roles
