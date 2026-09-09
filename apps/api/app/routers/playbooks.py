"""Playbooks, rules, and playbook runs. Nothing here calls a model: a run is
recorded and handed to the worker."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth.deps import CurrentPrincipal, DbSession
from app.errors import ConflictError, NotFoundError
from app.models.document import Document
from app.models.playbook import Finding, Playbook, PlaybookRule, PlaybookRun, PlaybookRunStatus
from app.playbook.export import issues_list_docx
from app.queue import enqueue
from app.repositories.base import WorkspaceScopedRepository
from app.repositories.documents import DocumentRepository
from app.schemas.playbooks import (
    FindingOut,
    PlaybookCreate,
    PlaybookDetail,
    PlaybookOut,
    PlaybookRunDetail,
    PlaybookRunOut,
    PlaybookRunRequest,
    PlaybookUpdate,
    RuleCreate,
    RuleOut,
    RuleUpdate,
)

router = APIRouter(tags=["playbooks"])


class PlaybookRepository(WorkspaceScopedRepository[Playbook]):
    model = Playbook

    async def get_full(self, playbook_id: uuid.UUID) -> Playbook:
        stmt = self.scoped().where(Playbook.id == playbook_id).options(selectinload(Playbook.rules))
        playbook = (await self.session.execute(stmt)).scalar_one_or_none()
        if playbook is None:
            raise NotFoundError("playbook")
        return playbook


class PlaybookRunRepository(WorkspaceScopedRepository[PlaybookRun]):
    model = PlaybookRun


def _out(playbook: Playbook) -> PlaybookOut:
    return PlaybookOut(
        id=playbook.id,
        name=playbook.name,
        description=playbook.description,
        created_at=playbook.created_at,
        rule_count=len(playbook.rules),
    )


# --- playbooks --------------------------------------------------------------


@router.get("/playbooks", response_model=list[PlaybookOut])
async def list_playbooks(principal: CurrentPrincipal, session: DbSession) -> list[PlaybookOut]:
    repo = PlaybookRepository(session, principal.workspace_id)
    rows = (
        (
            await session.execute(
                repo.scoped().options(selectinload(Playbook.rules)).order_by(Playbook.name)
            )
        )
        .scalars()
        .all()
    )
    return [_out(p) for p in rows]


@router.post("/playbooks", response_model=PlaybookDetail, status_code=status.HTTP_201_CREATED)
async def create_playbook(
    body: PlaybookCreate, principal: CurrentPrincipal, session: DbSession
) -> PlaybookDetail:
    playbook = Playbook(
        workspace_id=principal.workspace_id,
        name=body.name,
        description=body.description,
        created_by=principal.user_id,
    )
    PlaybookRepository(session, principal.workspace_id).add(playbook)
    await session.flush()
    for ordinal, rule in enumerate(body.rules):
        session.add(
            PlaybookRule(
                playbook_id=playbook.id,
                workspace_id=principal.workspace_id,
                ordinal=ordinal,
                **rule.model_dump(),
            )
        )
    await session.commit()
    return await get_playbook(playbook.id, principal, session)


@router.get("/playbooks/{playbook_id}", response_model=PlaybookDetail)
async def get_playbook(
    playbook_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> PlaybookDetail:
    playbook = await PlaybookRepository(session, principal.workspace_id).get_full(playbook_id)
    return PlaybookDetail(
        playbook=_out(playbook), rules=[RuleOut.model_validate(r) for r in playbook.rules]
    )


@router.patch("/playbooks/{playbook_id}", response_model=PlaybookDetail)
async def update_playbook(
    playbook_id: uuid.UUID, body: PlaybookUpdate, principal: CurrentPrincipal, session: DbSession
) -> PlaybookDetail:
    playbook = await PlaybookRepository(session, principal.workspace_id).get_full(playbook_id)
    if body.name is not None:
        playbook.name = body.name
    if body.description is not None:
        playbook.description = body.description
    await session.commit()
    return await get_playbook(playbook_id, principal, session)


@router.delete("/playbooks/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook(
    playbook_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> None:
    await PlaybookRepository(session, principal.workspace_id).delete(playbook_id)
    await session.commit()


# --- rules ------------------------------------------------------------------


@router.post(
    "/playbooks/{playbook_id}/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED
)
async def add_rule(
    playbook_id: uuid.UUID, body: RuleCreate, principal: CurrentPrincipal, session: DbSession
) -> RuleOut:
    playbook = await PlaybookRepository(session, principal.workspace_id).get_full(playbook_id)
    rule = PlaybookRule(
        playbook_id=playbook.id,
        workspace_id=principal.workspace_id,
        ordinal=max((r.ordinal for r in playbook.rules), default=-1) + 1,
        **body.model_dump(),
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return RuleOut.model_validate(rule)


async def _rule(
    session: DbSession, principal: CurrentPrincipal, playbook_id: uuid.UUID, rule_id: uuid.UUID
) -> PlaybookRule:
    await PlaybookRepository(session, principal.workspace_id).get(playbook_id)
    rule = (
        await session.execute(
            select(PlaybookRule).where(
                PlaybookRule.id == rule_id,
                PlaybookRule.playbook_id == playbook_id,
                PlaybookRule.workspace_id == principal.workspace_id,
            )
        )
    ).scalar_one_or_none()
    if rule is None:
        raise NotFoundError("rule")
    return rule


@router.patch("/playbooks/{playbook_id}/rules/{rule_id}", response_model=RuleOut)
async def update_rule(
    playbook_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: RuleUpdate,
    principal: CurrentPrincipal,
    session: DbSession,
) -> RuleOut:
    rule = await _rule(session, principal, playbook_id, rule_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await session.commit()
    await session.refresh(rule)
    return RuleOut.model_validate(rule)


@router.delete("/playbooks/{playbook_id}/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    playbook_id: uuid.UUID, rule_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> None:
    rule = await _rule(session, principal, playbook_id, rule_id)
    await session.delete(rule)
    await session.commit()


# --- runs -------------------------------------------------------------------


@router.post(
    "/playbooks/{playbook_id}/run",
    response_model=PlaybookRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_playbook(
    playbook_id: uuid.UUID,
    body: PlaybookRunRequest,
    principal: CurrentPrincipal,
    session: DbSession,
) -> PlaybookRunOut:
    playbook = await PlaybookRepository(session, principal.workspace_id).get_full(playbook_id)
    document = await DocumentRepository(session, principal.workspace_id).get(body.document_id)
    if not playbook.rules:
        raise ConflictError("the playbook has no rules")
    run = PlaybookRun(
        workspace_id=principal.workspace_id,
        playbook_id=playbook.id,
        document_id=document.id,
        status=PlaybookRunStatus.QUEUED,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    await enqueue("run_playbook", str(run.id))
    return PlaybookRunOut.model_validate(run)


@router.get("/playbook-runs", response_model=list[PlaybookRunOut])
async def list_runs(
    principal: CurrentPrincipal,
    session: DbSession,
    document_id: Annotated[uuid.UUID | None, Query()] = None,
    matter_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[PlaybookRunOut]:
    stmt = PlaybookRunRepository(session, principal.workspace_id).scoped()
    if document_id is not None:
        stmt = stmt.where(PlaybookRun.document_id == document_id)
    if matter_id is not None:
        stmt = stmt.join(Document, Document.id == PlaybookRun.document_id).where(
            Document.matter_id == matter_id
        )
    rows = (await session.execute(stmt.order_by(PlaybookRun.created_at.desc()))).scalars().all()
    return [PlaybookRunOut.model_validate(r) for r in rows]


async def _run_detail(
    session: DbSession, principal: CurrentPrincipal, run_id: uuid.UUID
) -> tuple[PlaybookRun, Playbook, Document, list[Finding]]:
    run = await PlaybookRunRepository(session, principal.workspace_id).get(run_id)
    playbook = await session.get(Playbook, run.playbook_id)
    document = await DocumentRepository(session, principal.workspace_id).get(run.document_id)
    if playbook is None:
        raise NotFoundError("playbook")
    findings = list(
        (
            await session.execute(
                select(Finding).where(Finding.run_id == run.id).order_by(Finding.ordinal)
            )
        ).scalars()
    )
    return run, playbook, document, findings


@router.get("/playbook-runs/{playbook_run_id}", response_model=PlaybookRunDetail)
async def get_run(
    playbook_run_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> PlaybookRunDetail:
    run, playbook, document, findings = await _run_detail(session, principal, playbook_run_id)
    return PlaybookRunDetail(
        run=PlaybookRunOut.model_validate(run),
        playbook_name=playbook.name,
        document_filename=document.filename,
        document_mime_type=document.mime_type,
        findings=[FindingOut.model_validate(f) for f in findings],
        demo_mode=run.model == "fake",
    )


@router.get("/playbook-runs/{playbook_run_id}/export")
async def export_run(
    playbook_run_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> Response:
    run, playbook, document, findings = await _run_detail(session, principal, playbook_run_id)
    payload = issues_list_docx(
        playbook_name=playbook.name,
        document_name=document.filename,
        findings=findings,
        model=run.model,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in document.filename)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="issues-{safe}-{stamp}.docx"'},
    )
