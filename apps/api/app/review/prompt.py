"""Prompt assembly.

The order is an architectural constraint, not a style choice (CLAUDE.md rule
8): system instructions, then playbook, then document content, then the
questions LAST. Prompt caching bills a repeated prefix at a fraction of the
price, and every cell in a column shares everything but the questions. Put
the questions first and every call is a cache miss.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.llm.schema import ExtractionRequest

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@lru_cache
def load_system_prompt(version: str | None = None) -> str:
    version = version or get_settings().prompt_version
    path = PROMPTS_DIR / f"extract_cells.{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"no prompt file for version {version!r}: {path}")
    return path.read_text(encoding="utf-8").strip()


def render_document(request: ExtractionRequest) -> str:
    parts = [f"# Document: {request.document_title}"]
    if request.outline:
        parts.append("## Outline")
        parts.extend(f"- {line}" for line in request.outline)
    parts.append("## Passages")
    for passage in request.passages:
        header = f"[{passage.label}]"
        if passage.section_path:
            header += f" ({passage.section_path})"
        parts.append(f"{header}\n{passage.text}")
    return "\n\n".join(parts)


def render_questions(request: ExtractionRequest) -> str:
    lines = ["## Questions"]
    for q in request.questions:
        line = f"{q.label} | type: {q.output_type}"
        if q.enum_options:
            line += " | options: " + ", ".join(q.enum_options)
        line += f" | {q.question}"
        lines.append(line)
    lines.append(
        "Answer every question above by its label, with verbatim quotes and passage labels."
    )
    return "\n".join(lines)


def render_messages(request: ExtractionRequest) -> list[dict[str, Any]]:
    """Responses API input. Static-first ordering for prefix caching."""
    system = request.system_prompt
    if request.playbook:
        system += "\n\n# Firm playbook\n" + request.playbook
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": render_document(request)},
        {"role": "user", "content": render_questions(request)},
    ]
