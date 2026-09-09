"""Internal JWT shared between the Next.js server and this API.

The Next.js server, after checking the Auth.js session, mints a short-lived
HS256 token carrying ``sub`` (user id) and optionally ``wid`` (the workspace
the user is currently acting in). The API verifies the signature here and then,
separately in ``deps``, checks that a membership row actually exists. The token
asserts intent; the database decides.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings

ISSUER = "legora-web"
ALGORITHM = "HS256"


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    workspace_id: uuid.UUID | None


class InvalidTokenError(Exception):
    pass


def mint_internal_token(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID | None = None,
    *,
    ttl_seconds: int | None = None,
) -> str:
    """Used by tests and tooling. Production tokens are minted in Next.js."""
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = ttl_seconds or settings.internal_token_max_age_seconds
    payload: dict[str, str | int] = {
        "iss": ISSUER,
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    if workspace_id is not None:
        payload["wid"] = str(workspace_id)
    return jwt.encode(payload, settings.internal_api_secret, algorithm=ALGORITHM)


def verify_internal_token(token: str) -> TokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.internal_api_secret,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    try:
        user_id = uuid.UUID(str(payload["sub"]))
        wid_raw = payload.get("wid")
        workspace_id = uuid.UUID(str(wid_raw)) if wid_raw else None
    except ValueError as exc:
        raise InvalidTokenError("malformed id claim") from exc

    return TokenClaims(user_id=user_id, workspace_id=workspace_id)
