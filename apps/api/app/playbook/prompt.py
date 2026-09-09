"""Playbook prompt assembly: system, playbook, document, instruction LAST.

The playbook is static per firm, so it sits before the document content and
shares the cached prefix across every document reviewed against it.
"""

from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.llm.schema import PlaybookRequest
from app.review.prompt import PROMPTS_DIR, render_document


@lru_cache
def load_playbook_prompt(version: str | None = None) -> str:
    version = version or get_settings().prompt_version
    path = PROMPTS_DIR / f"playbook.{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"no playbook prompt for version {version!r}: {path}")
    return path.read_text(encoding="utf-8").strip()


def render_playbook(request: PlaybookRequest) -> str:
    lines = [f"# Playbook: {request.playbook_name}"]
    for rule in request.rules:
        lines.append(f"## {rule.label} — {rule.topic}")
        lines.append(f"Preferred: {rule.preferred_position}")
        if rule.fallback_position:
            lines.append(f"Fallback: {rule.fallback_position}")
        if rule.unacceptable_position:
            lines.append(f"Unacceptable: {rule.unacceptable_position}")
    return "\n".join(lines)


def render_playbook_messages(request: PlaybookRequest) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": request.system_prompt + "\n\n" + render_playbook(request)},
        {"role": "user", "content": render_document(request)},
        {
            "role": "user",
            "content": (
                "Produce exactly one finding per playbook rule, by rule label "
                f"({', '.join(r.label for r in request.rules)}), following the rules above."
            ),
        },
    ]
