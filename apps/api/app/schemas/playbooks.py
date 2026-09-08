import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.playbook import MatchedPosition, PlaybookRunStatus, Severity


class RuleCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    preferred_position: str = Field(min_length=1, max_length=4000)
    fallback_position: str | None = Field(default=None, max_length=4000)
    unacceptable_position: str | None = Field(default=None, max_length=4000)


class RuleUpdate(BaseModel):
    topic: str | None = Field(default=None, min_length=1, max_length=200)
    preferred_position: str | None = Field(default=None, min_length=1, max_length=4000)
    fallback_position: str | None = Field(default=None, max_length=4000)
    unacceptable_position: str | None = Field(default=None, max_length=4000)


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    playbook_id: uuid.UUID
    topic: str
    preferred_position: str
    fallback_position: str | None
    unacceptable_position: str | None
    ordinal: int


class PlaybookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    rules: list[RuleCreate] = Field(default_factory=list, max_length=100)


class PlaybookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class PlaybookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    rule_count: int = 0


class PlaybookDetail(BaseModel):
    playbook: PlaybookOut
    rules: list[RuleOut]


class PlaybookRunRequest(BaseModel):
    document_id: uuid.UUID


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_id: uuid.UUID | None
    document_id: uuid.UUID
    ordinal: int
    topic: str
    matched_position: MatchedPosition
    severity: Severity
    clause_reference: str
    rationale: str
    suggested_language: str
    verified: bool
    chunk_id: uuid.UUID | None
    quoted_text: str | None
    page: int | None
    char_start: int | None
    char_end: int | None
    bboxes: dict[str, Any]
    match_kind: str | None


class PlaybookRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    playbook_id: uuid.UUID
    document_id: uuid.UUID
    status: PlaybookRunStatus
    model: str | None
    prompt_version: str | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class PlaybookRunDetail(BaseModel):
    run: PlaybookRunOut
    playbook_name: str
    document_filename: str
    document_mime_type: str
    findings: list[FindingOut]
    demo_mode: bool = False
