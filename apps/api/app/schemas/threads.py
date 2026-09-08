import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus
from app.models.thread import MessageRole


class ThreadCreate(BaseModel):
    matter_id: uuid.UUID
    title: str | None = Field(default=None, max_length=300)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class ThreadDocumentsUpdate(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    matter_id: uuid.UUID
    title: str
    created_at: datetime
    document_count: int = 0
    message_count: int = 0


class ThreadDocumentOut(BaseModel):
    document_id: uuid.UUID
    filename: str
    mime_type: str
    status: DocumentStatus


class MessageCitation(BaseModel):
    marker: int
    document_id: uuid.UUID
    filename: str
    chunk_id: uuid.UUID | None
    quoted_text: str
    page: int
    char_start: int
    char_end: int
    bboxes: dict[str, Any]
    match_kind: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    thread_id: uuid.UUID
    role: MessageRole
    content: str
    citations: list[MessageCitation] = Field(default_factory=list)
    verified: bool
    insufficient: bool
    model: str | None
    error: str | None
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class ThreadDetail(BaseModel):
    thread: ThreadOut
    documents: list[ThreadDocumentOut]
    messages: list[MessageOut]
    demo_mode: bool = False
