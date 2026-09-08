from pathlib import Path

import yaml

from app.models.review import OutputType
from eval.scoring import CellObservation, judge, percentile

GOLDEN = Path(__file__).parent / "golden"


def obs(
    value: str | None, *, not_found: bool = False, typed: object = None, status: str = "done"
) -> CellObservation:
    return CellObservation(
        status=status, not_found=not_found, verified=True, value_text=value, value_json=typed
    )


def test_not_present_is_correct_only_when_not_found() -> None:
    assert judge(obs(None, not_found=True), "not present", OutputType.TEXT).correct
    j = judge(obs("3 years"), "not present", OutputType.TEXT)
    assert not j.correct and j.hallucinated


def test_text_matches_by_containment_or_similarity() -> None:
    assert judge(
        obs("The laws of England and Wales govern."), "England and Wales", OutputType.TEXT
    ).correct
    assert judge(obs("Englnd and Wales"), "England and Wales", OutputType.TEXT).correct  # fuzzy
    assert not judge(obs("New York"), "England and Wales", OutputType.TEXT).correct
    assert judge(obs("125% of the Fees"), "125", OutputType.TEXT).correct


def test_boolean_uses_typed_value() -> None:
    assert judge(obs("Yes", typed=True), "yes", OutputType.BOOLEAN).correct
    assert not judge(obs("No", typed=False), "yes", OutputType.BOOLEAN).correct
    assert not judge(obs("unclear", typed=None), "yes", OutputType.BOOLEAN).correct


def test_not_found_where_answer_exists_is_wrong_but_not_hallucination() -> None:
    j = judge(obs(None, not_found=True), "three (3) years", OutputType.TEXT)
    assert not j.correct and not j.hallucinated


def test_failed_cells_count_as_wrong() -> None:
    j = judge(obs(None, status="failed"), "yes", OutputType.BOOLEAN)
    assert not j.correct and not j.hallucinated


def test_percentile() -> None:
    assert percentile([], 50) == 0.0
    assert percentile([10.0, 20.0, 30.0, 40.0, 50.0], 50) == 30.0
    assert percentile([10.0, 20.0, 30.0, 40.0, 50.0], 95) == 50.0


def test_golden_set_is_complete() -> None:
    questions = yaml.safe_load((GOLDEN / "questions.yaml").read_text(encoding="utf-8"))
    expected = yaml.safe_load((GOLDEN / "expected.yaml").read_text(encoding="utf-8"))
    assert len(questions) == 15
    assert len(expected) == 20
    keys = {q["key"] for q in questions}
    for name, answers in expected.items():
        assert (GOLDEN / name).exists(), name
        assert set(answers) == keys, name
    absent = sum(1 for a in expected.values() for v in a.values() if v == "not present")
    assert absent >= 40, "the set needs enough 'not present' cells to measure hallucination"
