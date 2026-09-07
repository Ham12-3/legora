"""Normalise a model's string answer into the column's typed value.

Returns ``(value_text, value_json)``. ``value_json`` is what exports and
filters use; ``value_text`` is what the grid shows. A value that does not fit
the type keeps its text and gets ``None`` as its typed value — the UI shows
it, the export marks it, nothing is silently coerced.
"""

import re
from datetime import date
from typing import Any

from dateutil import parser as dateparser

from app.models.review import OutputType

_YES = {"yes", "true", "y", "affirmative"}
_NO = {"no", "false", "n", "negative", "none"}
_CURRENCY_SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR", "¥": "JPY"}
_MONEY = re.compile(
    r"(?P<sym>[£$€¥])?\s*(?P<amt>\d[\d,]*(?:\.\d+)?)\s*(?P<code>GBP|USD|EUR|AUD|CAD|CHF|JPY)?",
    re.IGNORECASE,
)


def normalize_value(
    raw: str, output_type: OutputType, enum_options: list[str] | None
) -> tuple[str, Any | None]:
    text = " ".join(raw.split())
    if not text:
        return "", None

    if output_type is OutputType.BOOLEAN:
        head = text.lower().rstrip(".").split()[0] if text.split() else ""
        if head in _YES:
            return "Yes", True
        if head in _NO:
            return "No", False
        return text, None

    if output_type is OutputType.DATE:
        try:
            parsed: date = date.fromisoformat(text)
        except ValueError:
            # Written dates in contracts are day-first ("1 March 2025", "01/03/2025").
            try:
                parsed = dateparser.parse(text, dayfirst=True, fuzzy=True).date()
            except (ValueError, OverflowError):
                return text, None
        return parsed.isoformat(), parsed.isoformat()

    if output_type is OutputType.MONEY:
        m = _MONEY.search(text)
        if not m or not m.group("amt"):
            return text, None
        amount = float(m.group("amt").replace(",", ""))
        code = (m.group("code") or "").upper() or _CURRENCY_SYMBOLS.get(m.group("sym") or "", "")
        return text, {"amount": amount, "currency": code or None}

    if output_type is OutputType.ENUM:
        options = enum_options or []
        match = next((o for o in options if o.lower() == text.lower()), None)
        if match is None:
            match = next((o for o in options if o.lower() in text.lower()), None)
        return (match, match) if match is not None else (text, None)

    return text, text
