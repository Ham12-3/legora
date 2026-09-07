"""Pre-session endpoints, reachable only by the Next.js server.

Auth.js's Credentials provider calls ``/auth/login`` from ``authorize()``.
Neither endpoint issues a token: the session is Auth.js's, and the internal
JWT for subsequent API calls is minted by the Next.js server from that session.
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.deps import DbSession, InternalSecret
from app.auth.passwords import hash_password, verify_password
from app.models.user import User
from app.models.workspace import Membership, Role, Workspace
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[InternalSecret])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: DbSession) -> User:
    user = User(
        email=body.email.lower(),
        name=body.name,
        password_hash=hash_password(body.password),
    )
    session.add(user)

    try:
        # Flush now so a duplicate email fails before any workspace is created.
        await session.flush()
        if body.workspace_name:
            workspace = Workspace(name=body.workspace_name)
            session.add(workspace)
            await session.flush()
            session.add(Membership(user_id=user.id, workspace_id=workspace.id, role=Role.OWNER))
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="email already registered"
        ) from exc

    return user


@router.post("/login", response_model=UserOut)
async def login(body: LoginRequest, session: DbSession) -> User:
    stmt = select(User).where(User.email == body.email.lower())
    user = (await session.execute(stmt)).scalar_one_or_none()
    # Same response for unknown email and wrong password.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return user
