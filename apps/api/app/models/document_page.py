import uuid
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import CreatedAt, UUIDPrimaryKey, WorkspaceScoped


class DocumentPage(UUIDPrimaryKey, WorkspaceScoped, CreatedAt, Base):
    """One page of parsed text plus the geometry needed to highlight it.

    ``words`` is a list of ``[char_start, char_end, x0, y0, x1, y1]`` with the
    offsets relative to *this page's* ``text``. ``char_offset`` is where this
    page's text begins in the assembled document text (pages joined by "\\n"),
    so a document-global chunk offset maps to a page and then to words.
    """

    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_pages_doc_num"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    # list[[s, e, x0, y0, x1, y1]] — JSON, hence Any at the boundary
    words: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    is_ocr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
