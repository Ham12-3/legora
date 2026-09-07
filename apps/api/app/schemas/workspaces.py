import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.workspace import Role


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    role: Role
    created_at: datetime


class MemberAdd(BaseModel):
    email: EmailStr
    role: Role = Role.MEMBER


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    name: str
    role: Role


class WorkspaceDetail(BaseModel):
    id: uuid.UUID
    name: str
    role: Role
    members: list[MemberOut]


class MeOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    workspaces: list[WorkspaceOut]
