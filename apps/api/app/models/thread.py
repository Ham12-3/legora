"""Assistant threads: a conversation grounded on a selected set of documents.

Messages store their citations as JSON (already verified in Python before
they were written) and a ``verified`` flag that is false when the assistant
answered but no quote could be located in the sources. Messages with
``insufficient`` set are the refusal path: the assistant said it could not
answer from the documents rather than guessing.
"""

import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import CreatedAt, UUIDPrimaryKey, WorkspaceScoped


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Thread(UUIDPrimaryKey, WorkspaceScoped, CreatedAt, Base):
    __tablename__ = "threads"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="New conversation")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    documents: Mapped[list["ThreadDocument"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class ThreadDocument(Base):
    __tablename__ = "thread_documents"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )

    thread: Mapped[Thread] = relationship(back_populates="documents")


class Message(UUIDPrimaryKey, WorkspaceScoped, CreatedAt, Base):
    __tablename__ = "messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            native_enum=False,
            length=12,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # [{marker, document_id, chunk_id, quoted_text, page, char_start, char_end,
    #   bboxes, match_kind}] — verified before storage
    citations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    insufficient: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    thread: Mapped[Thread] = relationship(back_populates="messages")
