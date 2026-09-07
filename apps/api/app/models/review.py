"""Tabular Review: rows are documents, columns are questions, cells are answers.

Every answer carries verbatim quotes that were string-matched against the
source in Python before being stored (CLAUDE.md rule 2). ``Cell.verified`` is
false when no quote survived that check, and the UI must render such cells
differently.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import CreatedAt, UUIDPrimaryKey, WorkspaceScoped


def _varchar_enum(enum_cls: type[enum.StrEnum], length: int = 20) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
    )


class OutputType(enum.StrEnum):
    TEXT = "text"
    BOOLEAN = "boolean"
    DATE = "date"
    MONEY = "money"
    ENUM = "enum"


class CellStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class RunMode(enum.StrEnum):
    INTERACTIVE = "interactive"
    BATCH = "batch"


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUBMITTED = "submitted"  # batch handed to the provider, awaiting results
    DONE = "done"
    FAILED = "failed"


class Review(UUIDPrimaryKey, WorkspaceScoped, CreatedAt, Base):
    __tablename__ = "reviews"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    documents: Mapped[list["ReviewDocument"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", order_by="ReviewDocument.row_order"
    )
    columns: Mapped[list["ReviewColumn"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", order_by="ReviewColumn.ordinal"
    )


class ReviewDocument(Base):
    __tablename__ = "review_documents"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    row_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    review: Mapped[Review] = relationship(back_populates="documents")


class ReviewColumn(UUIDPrimaryKey, WorkspaceScoped, CreatedAt, Base):
    __tablename__ = "review_columns"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    output_type: Mapped[OutputType] = mapped_column(
        _varchar_enum(OutputType), nullable=False, default=OutputType.TEXT
    )
    enum_options: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    review: Mapped[Review] = relationship(back_populates="columns")


class Cell(UUIDPrimaryKey, WorkspaceScoped, Base):
    __tablename__ = "cells"
    __table_args__ = (
        UniqueConstraint("review_id", "document_id", "column_id", name="uq_cells_position"),
    )
    # updated_at is server-generated; fetch it with the INSERT/UPDATE so the
    # row can be serialised after commit without a lazy load (async sessions
    # cannot lazy-load).
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    column_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_columns.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[CellStatus] = mapped_column(
        _varchar_enum(CellStatus), nullable=False, default=CellStatus.PENDING
    )
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Typed value: bool, ISO date string, {"amount", "currency"}, enum option.
    value_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    not_found: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_cache: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    citations: Mapped[list["Citation"]] = relationship(
        back_populates="cell", cascade="all, delete-orphan"
    )


class Citation(UUIDPrimaryKey, WorkspaceScoped, Base):
    """A verified (or corrected) verbatim span. Never stored unverified: an
    unverified quote is dropped and the cell is marked unverified instead."""

    __tablename__ = "citations"

    cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cells.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    bboxes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # exact | fuzzy | relocated — how the quote was matched to the source.
    match_kind: Mapped[str] = mapped_column(String(12), nullable=False, default="exact")

    cell: Mapped[Cell] = relationship(back_populates="citations")


class CellCache(Base):
    """Raw model answers keyed by (document sha256, question, type, model,
    prompt version). Verification is re-run on a hit, so a re-ingested
    document with new chunk ids still verifies against current text."""

    __tablename__ = "cell_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReviewRun(UUIDPrimaryKey, WorkspaceScoped, CreatedAt, Base):
    """One invocation of POST /reviews/{id}/run. Interactive runs fan out to
    worker jobs; batch runs are one provider batch polled to completion."""

    __tablename__ = "review_runs"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[RunMode] = mapped_column(_varchar_enum(RunMode), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        _varchar_enum(RunStatus), nullable=False, default=RunStatus.QUEUED
    )
    total_cells: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done_cells: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Cell positions in this run, as [[document_id, column_id], ...].
    targets: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    force: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_batch_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Batch mode: provider custom_id -> {"document_id", "column_ids"}. The
    # provider caps custom_id length, so the mapping lives here.
    batch_plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
