import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus

ALLOWED_MIME_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

Sha256 = Field(pattern=r"^[0-9a-f]{64}$")


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    matter_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    page_count: int | None
    status: DocumentStatus
    is_ocr: bool
    error: str | None
    created_at: datetime


class PresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    mime_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    size_bytes: int = Field(gt=0)
    sha256: str = Sha256


class PresignResponse(BaseModel):
    """Either an upload ticket, or the document that already has these bytes."""

    duplicate: bool
    document: DocumentOut | None = None
    document_id: uuid.UUID | None = None
    storage_key: str | None = None
    upload_url: str | None = None
    expires_in: int | None = None


class RegisterDocumentRequest(BaseModel):
    document_id: uuid.UUID
    storage_key: str
    filename: str = Field(min_length=1, max_length=500)
    mime_type: str
    size_bytes: int = Field(gt=0)
    sha256: str = Sha256


class DownloadOut(BaseModel):
    url: str
    expires_in: int


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordinal: int
    section_path: str
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    token_count: int
    text: str
