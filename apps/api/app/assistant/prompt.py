"""Chat prompt assembly: system, passages, history, question LAST."""

from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.llm.schema import ChatRequest
from app.review.prompt import PROMPTS_DIR


@lru_cache
def load_assistant_prompt(version: str | None = None) -> str:
    version = version or get_settings().prompt_version
    path = PROMPTS_DIR / f"assistant.{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"no assistant prompt for version {version!r}: {path}")
    return path.read_text(encoding="utf-8").strip()


def render_passages(request: ChatRequest) -> str:
    parts = ["# Passages from the selected documents"]
    for passage in request.passages:
        header = f"[{passage.label}]"
        if passage.section_path:
            header += f" ({passage.section_path})"
        parts.append(f"{header}\n{passage.text}")
    return "\n\n".join(parts)


def render_chat_messages(request: ChatRequest) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": request.system_prompt},
        {"role": "user", "content": render_passages(request)},
    ]
    for turn in request.history:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append(
        {
            "role": "user",
            "content": (
                f"Question: {request.question}\n\n"
                "Answer from the passages above only, with numbered markers and verbatim quotes."
            ),
        }
    )
    return messages
