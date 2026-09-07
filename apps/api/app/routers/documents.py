"""Documents: presigned upload, registration, listing, download.

Upload is two calls. ``presign`` hands the browser a ticket (id, key, URL) or
tells it the bytes already exist in this matter. ``register`` runs after the
PUT succeeded and creates the row. Nothing is written to the database until
the object is in storage.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app import storage
from app.auth.deps import CurrentPrincipal, DbSession
from app.config import get_settings
from app.errors import ConflictError
from app.models.document import Document, DocumentStatus
from app.repositories.documents import DocumentRepository
from app.repositories.matters import MatterRepository
from app.schemas.documents import (
    DocumentOut,
    DownloadOut,
    PresignRequest,
    PresignResponse,
    RegisterDocumentRequest,
)

router = APIRouter(tags=["documents"])


@router.get("/matters/{matter_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    matter_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> list[DocumentOut]:
    await MatterRepository(session, principal.workspace_id).get(matter_id)
    docs = await DocumentRepository(session, principal.workspace_id).list_for_matter(matter_id)
    return [DocumentOut.model_validate(d) for d in docs]


@router.post("/matters/{matter_id}/documents/presign", response_model=PresignResponse)
async def presign_document(
    matter_id: uuid.UUID,
    body: PresignRequest,
    principal: CurrentPrincipal,
    session: DbSession,
) -> PresignResponse:
    settings = get_settings()
    if body.size_bytes > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"file exceeds {settings.max_upload_bytes} bytes",
        )

    await MatterRepository(session, principal.workspace_id).get(matter_id)
    docs = DocumentRepository(session, principal.workspace_id)

    existing = await docs.find_duplicate(matter_id, body.sha256)
    if existing is not None:
        return PresignResponse(duplicate=True, document=DocumentOut.model_validate(existing))

    document_id = uuid.uuid4()
    key = storage.build_storage_key(principal.workspace_id, matter_id, document_id)
    return PresignResponse(
        duplicate=False,
        document_id=document_id,
        storage_key=key,
        upload_url=storage.presign_upload(key, body.mime_type),
        expires_in=settings.presign_expiry_seconds,
    )


@router.post(
    "/matters/{matter_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def register_document(
    matter_id: uuid.UUID,
    body: RegisterDocumentRequest,
    principal: CurrentPrincipal,
    session: DbSession,
) -> DocumentOut:
    await MatterRepository(session, principal.workspace_id).get(matter_id)

    # The key is derived, never trusted: a client cannot register a row that
    # points at another tenant's object.
    expected_key = storage.build_storage_key(principal.workspace_id, matter_id, body.document_id)
    if body.storage_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="storage_key does not match ticket"
        )

    if get_settings().storage_verify_uploads and not storage.object_exists(body.storage_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="object not found in storage"
        )

    docs = DocumentRepository(session, principal.workspace_id)
    document = docs.add(
        Document(
            id=body.document_id,
            workspace_id=principal.workspace_id,
            matter_id=matter_id,
            filename=body.filename,
            mime_type=body.mime_type,
            size_bytes=body.size_bytes,
            storage_key=body.storage_key,
            sha256=body.sha256,
            status=DocumentStatus.UPLOADED,
            created_by=principal.user_id,
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        # Two presigns for the same bytes raced; the constraint is the arbiter.
        await session.rollback()
        raise ConflictError("a document with this content already exists in the matter") from exc

    await session.refresh(document)
    return DocumentOut.model_validate(document)


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> DocumentOut:
    document = await DocumentRepository(session, principal.workspace_id).get(document_id)
    return DocumentOut.model_validate(document)


@router.get("/documents/{document_id}/download", response_model=DownloadOut)
async def download_document(
    document_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> DownloadOut:
    document = await DocumentRepository(session, principal.workspace_id).get(document_id)
    return DownloadOut(
        url=storage.presign_download(document.storage_key, document.filename),
        expires_in=get_settings().presign_expiry_seconds,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> None:
    await DocumentRepository(session, principal.workspace_id).delete(document_id)
    await session.commit()
