"""Workspaces and membership.

``/me`` and ``/workspaces`` need only a user (the token may lack ``wid``).
``/workspace/...`` acts on the token's active workspace and needs a principal.
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth.deps import CurrentPrincipal, CurrentUser, DbSession
from app.errors import ConflictError, ForbiddenError, NotFoundError
from app.models.user import User
from app.models.workspace import Membership, Role, Workspace
from app.schemas.workspaces import (
    MemberAdd,
    MemberOut,
    MeOut,
    WorkspaceCreate,
    WorkspaceDetail,
    WorkspaceOut,
)

router = APIRouter(tags=["workspaces"])


async def _memberships_for(session: DbSession, user: User) -> list[WorkspaceOut]:
    stmt = (
        select(Membership)
        .where(Membership.user_id == user.id)
        .options(selectinload(Membership.workspace))
        .order_by(Membership.created_at)
    )
    memberships = (await session.execute(stmt)).scalars().all()
    return [
        WorkspaceOut(
            id=m.workspace.id,
            name=m.workspace.name,
            role=m.role,
            created_at=m.workspace.created_at,
        )
        for m in memberships
    ]


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser, session: DbSession) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        workspaces=await _memberships_for(session, user),
    )


@router.get("/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(user: CurrentUser, session: DbSession) -> list[WorkspaceOut]:
    return await _memberships_for(session, user)


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate, user: CurrentUser, session: DbSession
) -> WorkspaceOut:
    workspace = Workspace(name=body.name)
    session.add(workspace)
    await session.flush()
    session.add(Membership(user_id=user.id, workspace_id=workspace.id, role=Role.OWNER))
    await session.commit()
    await session.refresh(workspace)
    return WorkspaceOut(
        id=workspace.id, name=workspace.name, role=Role.OWNER, created_at=workspace.created_at
    )


@router.get("/workspace", response_model=WorkspaceDetail)
async def current_workspace(principal: CurrentPrincipal, session: DbSession) -> WorkspaceDetail:
    workspace = await session.get(Workspace, principal.workspace_id)
    if workspace is None:
        raise NotFoundError("workspace")
    stmt = (
        select(Membership)
        .where(Membership.workspace_id == principal.workspace_id)
        .options(selectinload(Membership.user))
        .order_by(Membership.created_at)
    )
    memberships = (await session.execute(stmt)).scalars().all()
    return WorkspaceDetail(
        id=workspace.id,
        name=workspace.name,
        role=principal.role,
        members=[
            MemberOut(user_id=m.user.id, email=m.user.email, name=m.user.name, role=m.role)
            for m in memberships
        ],
    )


@router.post("/workspace/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def add_member(body: MemberAdd, principal: CurrentPrincipal, session: DbSession) -> MemberOut:
    if not principal.role.can_manage_members:
        raise ForbiddenError("only owners and admins can add members")
    if body.role is Role.OWNER and principal.role is not Role.OWNER:
        raise ForbiddenError("only an owner can grant ownership")

    user = (
        await session.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if user is None:
        # Invitations for people without an account are a later concern.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no account with that email"
        )

    existing = await session.get(Membership, (user.id, principal.workspace_id))
    if existing is not None:
        raise ConflictError("already a member")

    session.add(Membership(user_id=user.id, workspace_id=principal.workspace_id, role=body.role))
    await session.commit()
    return MemberOut(user_id=user.id, email=user.email, name=user.name, role=body.role)
