"""Run the grid over the golden set and report.

Uses its own database (``legora_eval`` by default) so it never touches dev
data: created and migrated on first run, wiped at the start of every run. The
model provider follows LLM_PROVIDER / OPENAI_API_KEY exactly as the app does.
"""

import argparse
import asyncio
import hashlib
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Isolation before anything imports app.config.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("QUEUE_ENABLED", "false")
os.environ.setdefault("STORAGE_ENABLED", "false")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://legora:legora@localhost:5432/legora_eval"
)

import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db import SessionLocal
from app.ingestion import pipeline
from app.ingestion.embeddings import get_embedder
from app.llm.client import get_llm_client
from app.models.document import Document, DocumentStatus
from app.models.matter import Matter
from app.models.review import Cell, OutputType, Review, ReviewColumn, ReviewDocument
from app.models.user import User
from app.models.workspace import Membership, Role, Workspace
from app.review import executor
from eval.instrumented import InstrumentedClient
from eval.report import EvalSummary, QuestionStats, write_results
from eval.scoring import CellObservation, judge, percentile

GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "eval" / "golden"

# USD per million tokens. Override per model with EVAL_PRICE_* env vars; the
# defaults are placeholders so the report always has a cost column.
PRICE_INPUT = float(os.environ.get("EVAL_PRICE_INPUT_PER_M", "0.25"))
PRICE_CACHED = float(os.environ.get("EVAL_PRICE_CACHED_INPUT_PER_M", "0.025"))
PRICE_OUTPUT = float(os.environ.get("EVAL_PRICE_OUTPUT_PER_M", "2.00"))

TABLES = (
    "findings, playbook_runs, playbook_rules, playbooks, messages, thread_documents, threads, "
    "citations, cells, review_runs, review_columns, review_documents, reviews, cell_cache, "
    "chunks, document_pages, documents, matters, memberships, workspaces, users"
)


async def ensure_database() -> None:
    url = get_settings().database_url
    db_name = url.rsplit("/", 1)[1]
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
        )
        if exists.scalar_one_or_none() is None:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    await engine.dispose()


def migrate() -> None:
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")


async def reset() -> None:
    async with SessionLocal() as session:
        await session.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        await session.commit()


def load_golden() -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    questions = yaml.safe_load((GOLDEN / "questions.yaml").read_text(encoding="utf-8"))
    expected = yaml.safe_load((GOLDEN / "expected.yaml").read_text(encoding="utf-8"))
    return questions, expected


async def main(limit: int | None, force_provider: str | None) -> int:
    settings = get_settings()
    if force_provider:
        settings.llm_provider = force_provider
    questions, expected = load_golden()
    files = sorted(expected)[:limit] if limit else sorted(expected)
    missing = [f for f in files if not (GOLDEN / f).exists()]
    if missing:
        print(
            f"golden PDFs missing: {missing}. Run tests/eval/golden/build_golden.py",
            file=sys.stderr,
        )
        return 2

    await reset()

    embedder = get_embedder(settings)
    client = InstrumentedClient(get_llm_client(settings))
    print(
        f"provider={client.name} model={settings.model_extract} prompt={settings.prompt_version} "
        f"embeddings={getattr(embedder, 'name', 'disabled')} documents={len(files)}"
    )

    async with SessionLocal() as session:
        user = User(email="eval@legora.local", name="Eval", password_hash="x")
        workspace = Workspace(name="Eval")
        session.add_all([user, workspace])
        await session.flush()
        session.add(Membership(user_id=user.id, workspace_id=workspace.id, role=Role.OWNER))
        matter = Matter(workspace_id=workspace.id, name="Golden set", created_by=user.id)
        session.add(matter)
        await session.flush()

        documents: list[Document] = []
        for name in files:
            data = (GOLDEN / name).read_bytes()
            doc = Document(
                workspace_id=workspace.id,
                matter_id=matter.id,
                filename=name,
                mime_type="application/pdf",
                size_bytes=len(data),
                storage_key=f"eval/{name}",
                sha256=hashlib.sha256(data).hexdigest(),
                status=DocumentStatus.UPLOADED,
            )
            session.add(doc)
            documents.append(doc)
        await session.commit()
        workspace_id, matter_id = workspace.id, matter.id
        doc_ids = [d.id for d in documents]

    # --- ingest --------------------------------------------------------------
    t0 = time.monotonic()
    for name, doc_id in zip(files, doc_ids, strict=True):
        data = (GOLDEN / name).read_bytes()

        async def loader(_: str, _data: bytes = data) -> bytes:
            return _data

        async with SessionLocal() as session:
            await pipeline.run_all(session, doc_id, loader=loader, embedder=embedder)
    ingestion_seconds = time.monotonic() - t0
    print(f"ingested {len(files)} documents in {ingestion_seconds:.1f}s")

    # --- review -------------------------------------------------------------
    async with SessionLocal() as session:
        review = Review(workspace_id=workspace_id, matter_id=matter_id, name="Eval")
        session.add(review)
        await session.flush()
        for order, doc_id in enumerate(doc_ids):
            session.add(ReviewDocument(review_id=review.id, document_id=doc_id, row_order=order))
        columns: list[ReviewColumn] = []
        for ordinal, q in enumerate(questions):
            column = ReviewColumn(
                review_id=review.id,
                workspace_id=workspace_id,
                name=q["name"],
                question=q["question"],
                output_type=OutputType(q["output_type"]),
                ordinal=ordinal,
            )
            session.add(column)
            columns.append(column)
        await session.commit()
        review_id = review.id
        column_ids = [c.id for c in columns]
        column_keys = {c.id: q["key"] for c, q in zip(columns, questions, strict=True)}

    t1 = time.monotonic()
    for doc_id in doc_ids:
        for group in executor.group_columns(column_ids, settings.columns_per_call):
            async with SessionLocal() as session:
                try:
                    await executor.run_cells(
                        session,
                        review_id=review_id,
                        document_id=doc_id,
                        column_ids=group,
                        force=True,
                        client=client,
                        embedder=embedder,
                        settings=settings,
                    )
                except executor.CellExecutionError as exc:
                    print(f"  document {doc_id}: {exc}", file=sys.stderr)
    grid_seconds = time.monotonic() - t1
    total = len(doc_ids) * len(column_ids)
    print(f"grid: {total} cells in {grid_seconds:.1f}s, {len(client.calls)} calls")

    # --- score ----------------------------------------------------------------
    async with SessionLocal() as session:
        cells = (
            (await session.execute(select(Cell).where(Cell.review_id == review_id))).scalars().all()
        )
        filenames = {
            d.id: d.filename
            for d in (
                await session.execute(select(Document).where(Document.id.in_(doc_ids)))
            ).scalars()
        }

    stats = {q["key"]: QuestionStats(q["key"], q["name"], q["output_type"]) for q in questions}
    types = {q["key"]: OutputType(q["output_type"]) for q in questions}
    answered = verified = hallucinated = absent = missed_present = present = failed = 0
    for cell in cells:
        key = column_keys[cell.column_id]
        want = expected[filenames[cell.document_id]][key]
        obs = CellObservation(
            status=cell.status.value,
            not_found=cell.not_found,
            verified=cell.verified,
            value_text=cell.value_text,
            value_json=cell.value_json,
        )
        j = judge(obs, want, types[key])
        st = stats[key]
        st.total += 1
        st.correct += int(j.correct)
        st.hallucinated += int(j.hallucinated)
        st.expected_absent += int(not j.expected_present)
        if cell.status.value != "done":
            st.failed += 1
            failed += 1
        if cell.status.value == "done" and not cell.not_found:
            answered += 1
            verified += int(cell.verified)
            if not cell.verified:
                st.unverified += 1
        if not j.expected_present:
            absent += 1
            hallucinated += int(j.hallucinated)
        else:
            present += 1
            if cell.status.value == "done" and cell.not_found:
                missed_present += 1
        if not j.correct:
            st.misses.append(f"{filenames[cell.document_id]}: {j.note}")

    latencies = [float(c.latency_ms) for c in client.calls]
    in_tok = sum(c.input_tokens for c in client.calls)
    cached = sum(c.cached_input_tokens for c in client.calls)
    out_tok = sum(c.output_tokens for c in client.calls)
    cost = ((in_tok - cached) * PRICE_INPUT + cached * PRICE_CACHED + out_tok * PRICE_OUTPUT) / 1e6
    per_question = [stats[q["key"]] for q in questions]
    total_cells = len(cells)

    summary = EvalSummary(
        run_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        model=settings.model_extract if client.name != "fake" else "fake",
        prompt_version=settings.prompt_version,
        provider=client.name,
        embeddings=getattr(embedder, "name", "disabled"),
        documents=len(doc_ids),
        questions=len(questions),
        cells=total_cells,
        accuracy=sum(s.correct for s in per_question) / total_cells if total_cells else 0.0,
        citation_verification_rate=verified / answered if answered else 0.0,
        hallucination_rate=hallucinated / absent if absent else 0.0,
        not_found_when_present_rate=missed_present / present if present else 0.0,
        failed_cells=failed,
        model_calls=len(client.calls),
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
        input_tokens=in_tok,
        cached_input_tokens=cached,
        output_tokens=out_tok,
        cost_total_usd=cost,
        cost_per_document_usd=cost / len(doc_ids) if doc_ids else 0.0,
        cost_per_cell_usd=cost / total_cells if total_cells else 0.0,
        ingestion_seconds=ingestion_seconds,
        grid_seconds=grid_seconds,
        targets={
            "citation_verification_rate": 0.95,
            "hallucination_rate": 0.02,
            "cost_per_cell_usd": 0.02,
        },
        per_question=[],
    )
    json_path, md_path = write_results(summary, per_question)
    # Windows consoles may not be UTF-8; never let the report crash the run.
    sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    print(md_path.read_text(encoding="utf-8"))
    print(f"wrote {json_path.name} and {md_path.name}")
    return 0


def cli() -> None:
    parser = argparse.ArgumentParser(description="Run the grid over the golden set.")
    parser.add_argument("--limit", type=int, default=None, help="only the first N documents")
    parser.add_argument("--provider", choices=["auto", "openai", "fake"], default=None)
    args = parser.parse_args()
    # Alembic's env.py runs its own event loop, so migrate before entering ours.
    asyncio.run(ensure_database())
    migrate()
    raise SystemExit(asyncio.run(main(args.limit, args.provider)))


if __name__ == "__main__":
    cli()
