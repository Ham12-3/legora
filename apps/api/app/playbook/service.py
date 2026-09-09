"""Run a playbook against one document.

Reuses the grid's context router (``review.context``) and citation verifier
(``review.verify``) — there is one verification path in this codebase.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.ingestion.embeddings import Embedder
from app.llm.client import LLMClient
from app.llm.schema import PlaybookRequest, PlaybookRuleSpec
from app.models.document import Document, DocumentStatus
from app.models.playbook import (
    Finding,
    MatchedPosition,
    Playbook,
    PlaybookRun,
    PlaybookRunStatus,
    Severity,
)
from app.playbook.prompt import load_playbook_prompt
from app.review.context import build_context
from app.review.verify import verify_quote

log = logging.getLogger(__name__)


class PlaybookError(Exception):
    """Permanent: mark the run failed, do not retry."""


def rule_label(index: int) -> str:
    return f"r{index + 1}"


async def run_playbook(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    client: LLMClient,
    embedder: Embedder | None,
    settings: Settings | None = None,
) -> PlaybookRun:
    settings = settings or get_settings()
    run = await session.get(PlaybookRun, run_id)
    if run is None:
        raise PlaybookError("run no longer exists")
    playbook = (
        await session.execute(
            select(Playbook)
            .where(Playbook.id == run.playbook_id)
            .options(selectinload(Playbook.rules))
        )
    ).scalar_one_or_none()
    document = await session.get(Document, run.document_id)
    if playbook is None or document is None:
        raise PlaybookError("playbook or document no longer exists")

    run.status = PlaybookRunStatus.RUNNING
    run.error = None
    await session.commit()

    try:
        if document.status is not DocumentStatus.READY:
            raise PlaybookError(f"document is {document.status.value}, not ready")
        if not playbook.rules:
            raise PlaybookError("playbook has no rules")

        rules = list(playbook.rules)
        labels = {rule_label(i): r for i, r in enumerate(rules)}
        context = await build_context(
            session,
            document,
            [f"{r.topic} {r.preferred_position}" for r in rules],
            embedder=embedder,
        )
        request = PlaybookRequest(
            model=settings.model_synth,
            system_prompt=load_playbook_prompt(settings.prompt_version),
            playbook_name=playbook.name,
            rules=tuple(
                PlaybookRuleSpec(
                    label=label,
                    topic=r.topic,
                    preferred_position=r.preferred_position,
                    fallback_position=r.fallback_position or "",
                    unacceptable_position=r.unacceptable_position or "",
                )
                for label, r in labels.items()
            ),
            document_title=document.filename,
            outline=context.outline,
            passages=context.passages,
            metadata={"playbook_run_id": str(run.id)},
        )
        result = await client.review_playbook(request)
    except PlaybookError as exc:
        run.status = PlaybookRunStatus.FAILED
        run.error = str(exc)
        run.completed_at = datetime.now(UTC)
        await session.commit()
        return run
    except Exception as exc:
        run.status = PlaybookRunStatus.FAILED
        run.error = f"{type(exc).__name__}: {exc}"
        run.completed_at = datetime.now(UTC)
        await session.commit()
        raise

    await session.execute(delete(Finding).where(Finding.run_id == run.id))
    by_label = {f.rule_id: f for f in result.findings.findings}
    for ordinal, (label, rule) in enumerate(labels.items()):
        raw = by_label.get(label)
        finding = Finding(
            run_id=run.id,
            workspace_id=run.workspace_id,
            rule_id=rule.id,
            document_id=document.id,
            ordinal=ordinal,
            topic=rule.topic,
            matched_position=MatchedPosition.NOT_ADDRESSED,
            severity=Severity.MEDIUM,
            rationale="The model returned no finding for this rule.",
        )
        if raw is not None:
            finding.matched_position = MatchedPosition(raw.matched_position)
            finding.severity = Severity(raw.severity)
            finding.clause_reference = raw.clause_reference[:300]
            finding.rationale = raw.rationale
            finding.suggested_language = raw.suggested_language
            for quote in raw.quotes:
                span = verify_quote(
                    quote.text,
                    context.by_label.get(quote.chunk_id),
                    parsed=context.parsed,
                    chunks=context.chunks,
                    fuzzy_threshold=settings.citation_fuzzy_threshold,
                )
                if span is None:
                    continue
                finding.verified = True
                finding.chunk_id = span.chunk.id if span.chunk is not None else None
                finding.quoted_text = span.quoted_text
                finding.page = span.page
                finding.char_start = span.char_start
                finding.char_end = span.char_end
                finding.bboxes = span.bboxes
                finding.match_kind = span.match_kind
                break
            if finding.matched_position is MatchedPosition.NOT_ADDRESSED:
                # Nothing to cite; the claim is about absence.
                finding.verified = True
        session.add(finding)

    run.status = PlaybookRunStatus.DONE
    run.model = result.model
    run.prompt_version = settings.prompt_version
    run.completed_at = datetime.now(UTC)
    await session.commit()
    log.info(
        "playbook run %s: %d rules, mode=%s, %d passages, %dms",
        run.id,
        len(rules),
        context.mode,
        len(context.passages),
        result.latency_ms,
    )
    return run
