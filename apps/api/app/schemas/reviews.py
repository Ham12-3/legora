import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.document import DocumentStatus
from app.models.review import CellStatus, OutputType, RunMode, RunStatus


class ReviewCreate(BaseModel):
    matter_id: uuid.UUID
    name: str = Field(min_length=1, max_length=300)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    matter_id: uuid.UUID
    name: str
    created_at: datetime
    document_count: int = 0
    column_count: int = 0


class ReviewDocumentOut(BaseModel):
    document_id: uuid.UUID
    filename: str
    mime_type: str
    status: DocumentStatus
    page_count: int | None
    row_order: int


class AddDocumentsRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class ColumnCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=3, max_length=4000)
    output_type: OutputType = OutputType.TEXT
    enum_options: list[str] | None = None

    @model_validator(mode="after")
    def _enum_needs_options(self) -> "ColumnCreate":
        if self.output_type is OutputType.ENUM and not self.enum_options:
            raise ValueError("enum columns need at least one option")
        if self.output_type is not OutputType.ENUM:
            self.enum_options = None
        return self


class ColumnUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    question: str | None = Field(default=None, min_length=3, max_length=4000)
    output_type: OutputType | None = None
    enum_options: list[str] | None = None


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    review_id: uuid.UUID
    name: str
    question: str
    output_type: OutputType
    enum_options: list[str] | None
    ordinal: int


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_id: uuid.UUID | None
    quoted_text: str
    page: int
    char_start: int
    char_end: int
    bboxes: dict[str, Any]
    match_kind: str


class CellOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    review_id: uuid.UUID
    document_id: uuid.UUID
    column_id: uuid.UUID
    status: CellStatus
    value_text: str | None
    value_json: Any | None
    not_found: bool
    verified: bool
    confidence: str | None
    model: str | None
    prompt_version: str | None
    from_cache: bool
    error: str | None
    updated_at: datetime
    citations: list[CitationOut] = Field(default_factory=list)


class RunRequest(BaseModel):
    """Scope: whole grid by default; one row, one column, or one cell."""

    document_id: uuid.UUID | None = None
    column_id: uuid.UUID | None = None
    mode: Literal["auto", "interactive", "batch"] = "auto"
    force: bool = False


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    review_id: uuid.UUID
    mode: RunMode
    status: RunStatus
    total_cells: int
    done_cells: int
    provider_batch_id: str | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class ReviewDetail(BaseModel):
    review: ReviewOut
    documents: list[ReviewDocumentOut]
    columns: list[ColumnOut]
    cells: list[CellOut]
    runs: list[RunOut]
    # True when any cell was produced by the fake model: show a demo banner.
    demo_mode: bool = False
