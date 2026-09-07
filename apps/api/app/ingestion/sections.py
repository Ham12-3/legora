"""Clause and section numbering detection.

Contracts number their structure in a handful of conventional ways. Each
pattern maps to a depth so the chunker can keep a stack:

    depth 0  ARTICLE IV / Article 4 / SECTION 3 / PART 2 / an ALL-CAPS heading
    depth 1  8.
    depth 2  8.2
    depth 3  8.2.1 / (a)
    depth 4  (i) / 8.2.1.1

The exact depth of "(a)" relative to "8.2.1" is not knowable in general;
what matters is that a new heading closes everything at or below its own
depth, and that is stable across all these conventions.
"""

import re
from dataclasses import dataclass

_ROMAN = r"(?=[IVXLC])M*(?:C[MD]|D?C{0,3})(?:X[CL]|L?X{0,3})(?:I[XV]|V?I{0,3})"

_ARTICLE = re.compile(
    rf"^\s*(?:ARTICLE|Article|SECTION|Section|PART|Part)\s+(?:{_ROMAN}|\d+)\b[.:\-\s]*(.*)$"
)
_DECIMAL = re.compile(r"^\s*(\d+(?:\.\d+)*)(\.)?\s+(\S.*)$")
_DECIMAL_BARE = re.compile(r"^\s*(\d+(?:\.\d+)+)\s*$")
_ALPHA = re.compile(r"^\s*\(([a-z])\)\s+(\S.*)$")
_ROMAN_ITEM = re.compile(rf"^\s*\(({_ROMAN.lower()})\)\s+(\S.*)$", re.IGNORECASE)
_ALLCAPS_HEADING = re.compile(r"^[A-Z][A-Z0-9 ,&'\-/()]{3,80}$")

MAX_LABEL = 72


@dataclass(frozen=True)
class SectionMarker:
    depth: int
    label: str  # e.g. "8. Indemnities" or "8.2" or "(a)"


def _label(number: str, title: str) -> str:
    title = " ".join(title.split())
    if not title:
        return number
    if len(title) > MAX_LABEL:
        title = title[: MAX_LABEL - 1].rstrip() + "…"
    return f"{number} {title}".strip()


def detect_marker(block_text: str) -> SectionMarker | None:
    """Classify the start of a block. ``None`` means body text."""
    first_line = block_text.strip().split("\n", 1)[0]
    if not first_line:
        return None

    if m := _ARTICLE.match(first_line):
        head = first_line[: m.start(1)].strip().rstrip(".:-").strip()
        return SectionMarker(0, _label(head, m.group(1)))

    if m := _DECIMAL_BARE.match(first_line):
        number = m.group(1)
        return SectionMarker(min(number.count(".") + 1, 4), number)

    if m := _DECIMAL.match(first_line):
        number, dot, title = m.group(1), m.group(2), m.group(3)
        depth = number.count(".") + 1
        # "1. Definitions" is a heading; "30 days after the Effective Date" is
        # a sentence. The dot after a bare integer is the discriminator.
        if depth == 1 and (dot is None or len(title) > 120):
            return None
        display = f"{number}." if depth == 1 else number
        return SectionMarker(min(depth, 4), _label(display, title if depth <= 2 else ""))

    if m := _ALPHA.match(first_line):
        return SectionMarker(3, f"({m.group(1)})")

    if m := _ROMAN_ITEM.match(first_line):
        return SectionMarker(4, f"({m.group(1).lower()})")

    if _ALLCAPS_HEADING.match(first_line) and len(block_text.strip()) == len(first_line):
        return SectionMarker(0, _label("", first_line.title()))

    return None


class SectionStack:
    """Tracks the current heading path as blocks stream past."""

    def __init__(self) -> None:
        self._stack: list[SectionMarker] = []

    def push(self, marker: SectionMarker) -> None:
        while self._stack and self._stack[-1].depth >= marker.depth:
            self._stack.pop()
        self._stack.append(marker)

    @property
    def path(self) -> str:
        return " > ".join(m.label for m in self._stack)

    @property
    def depth(self) -> int:
        return self._stack[-1].depth if self._stack else 0

    @property
    def root_label(self) -> str | None:
        """The enclosing ARTICLE/PART heading, if the document has that level."""
        if self._stack and self._stack[0].depth == 0:
            return self._stack[0].label
        return None
