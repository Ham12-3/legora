import pytest

from app.models.review import OutputType
from app.review.values import normalize_value


@pytest.mark.parametrize(
    ("raw", "text", "typed"),
    [
        ("yes", "Yes", True),
        ("Yes.", "Yes", True),
        ("No — the agreement is silent", "No", False),
        ("unclear", "unclear", None),
    ],
)
def test_boolean(raw: str, text: str, typed: bool | None) -> None:
    assert normalize_value(raw, OutputType.BOOLEAN, None) == (text, typed)


def test_date_parses_written_dates_day_first() -> None:
    assert normalize_value("1 March 2025", OutputType.DATE, None) == ("2025-03-01", "2025-03-01")
    assert normalize_value("2025-03-01", OutputType.DATE, None) == ("2025-03-01", "2025-03-01")
    text, typed = normalize_value("on signature", OutputType.DATE, None)
    assert text == "on signature" and typed is None


def test_money_extracts_amount_and_currency() -> None:
    text, typed = normalize_value("£48,000 per annum", OutputType.MONEY, None)
    assert text == "£48,000 per annum"
    assert typed == {"amount": 48000.0, "currency": "GBP"}
    _, typed = normalize_value("125% of the Fees", OutputType.MONEY, None)
    assert typed == {"amount": 125.0, "currency": None}


def test_enum_matches_options_case_insensitively() -> None:
    options = ["England and Wales", "New York", "Other"]
    assert normalize_value("new york", OutputType.ENUM, options) == ("New York", "New York")
    assert normalize_value("the laws of England and Wales", OutputType.ENUM, options) == (
        "England and Wales",
        "England and Wales",
    )
    text, typed = normalize_value("Scotland", OutputType.ENUM, options)
    assert text == "Scotland" and typed is None


def test_text_passthrough_collapses_whitespace() -> None:
    assert normalize_value("  three   (3)\nyears ", OutputType.TEXT, None) == (
        "three (3) years",
        "three (3) years",
    )
    assert normalize_value("", OutputType.TEXT, None) == ("", None)
