"""FastAPI dependencies that resolve the caller.

Two levels:

* ``CurrentUser``: a valid token with ``sub``. Enough to list your workspaces
  or create one.
* ``CurrentPrincipal``: a valid token with ``wid`` AND a membership row proving
  the user belongs to that workspace. Every tenant-scoped route depends on it.

``InternalSecret`` gates the pre-session endpoints (register, login) so only
the Next.js server can reach them.
"""

import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import InvalidTokenError, TokenClaims, verify_internal_token
from app.config import get_settings
from app.db import get_session
from app.models.user import User
from app.models.workspace import Membership, Role

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_session)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenClaims:
    if credentials is None:
        raise _unauthorized("missing bearer token")
    try:
        return verify_internal_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise _unauthorized(f"invalid token: {exc}") from exc


async def get_current_user(
    claims: Annotated[TokenClaims, Depends(get_claims)],
    session: DbSession,
) -> User:
    user = await session.get(User, claims.user_id)
    if user is None:
        raise _unauthorized("unknown user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    role: Role


async def get_principal(
    claims: Annotated[TokenClaims, Depends(get_claims)],
    session: DbSession,
) -> Principal:
    if claims.workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no active workspace",
        )
    stmt = select(Membership).where(
        Membership.user_id == claims.user_id,
        Membership.workspace_id == claims.workspace_id,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    if membership is None:
        # 403, not 404: the caller is authenticated, they are simply not in
        # the workspace their token names.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not a member of this workspace",
        )
    return Principal(
        user_id=claims.user_id,
        workspace_id=claims.workspace_id,
        role=membership.role,
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def require_internal_secret(
    x_internal_secret: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().internal_api_secret
    if x_internal_secret is None or not secrets.compare_digest(x_internal_secret, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="internal only")


InternalSecret = Depends(require_internal_secret)
