"""Compare a cell against the golden answer.

Rules by output type:

    "not present"   correct iff the cell is not_found. Answering anyway is a
                    hallucination — the metric lawyers care about most.
    boolean         typed value equals the expected yes/no
    text            the expected key phrase appears in the answer after
                    whitespace/case normalisation, or the two are >= 0.8 similar
    money/date/enum typed values equal after the same normalisation the
                    executor applies (values.normalize_value)
"""

import difflib
from dataclasses import dataclass

from app.models.review import OutputType
from app.review.values import normalize_value

NOT_PRESENT = "not present"
APOSTROPHE = chr(0x2019)  # typographic; folded so a quote compares either way


@dataclass(frozen=True)
class CellObservation:
    status: str  # done | failed | ...
    not_found: bool
    verified: bool
    value_text: str | None
    value_json: object


@dataclass(frozen=True)
class Judgement:
    correct: bool
    hallucinated: bool  # answered where the golden answer is "not present"
    expected_present: bool
    note: str = ""


def _norm(text: str) -> str:
    return " ".join(text.lower().replace(APOSTROPHE, "'").split())


def judge(observed: CellObservation, expected: str, output_type: OutputType) -> Judgement:
    expected_present = expected.strip().lower() != NOT_PRESENT

    if observed.status != "done":
        return Judgement(False, False, expected_present, f"cell {observed.status}")

    if not expected_present:
        if observed.not_found:
            return Judgement(True, False, False)
        return Judgement(
            False, True, False, f"answered {observed.value_text!r} where nothing exists"
        )

    if observed.not_found:
        return Judgement(False, False, True, "said not found; answer exists")

    predicted = _norm(observed.value_text or "")
    target = _norm(expected)

    if output_type is OutputType.BOOLEAN:
        _, want = normalize_value(expected, output_type, None)
        return Judgement(observed.value_json == want and want is not None, False, True)

    if output_type in (OutputType.MONEY, OutputType.DATE, OutputType.ENUM):
        _, want = normalize_value(expected, output_type, None)
        return Judgement(observed.value_json == want, False, True)

    if target and target in predicted:
        return Judgement(True, False, True)
    ratio = difflib.SequenceMatcher(None, predicted, target).ratio()
    if ratio >= 0.8:
        return Judgement(True, False, True, f"fuzzy {ratio:.2f}")
    # A bare number in the target (e.g. a cap percentage) matching the answer
    # is enough for text questions whose key fact is numeric.
    if target.isdigit() and target in predicted.replace(",", ""):
        return Judgement(True, False, True, "numeric")
    return Judgement(False, False, True, f"expected {expected!r}, got {observed.value_text!r}")


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]
