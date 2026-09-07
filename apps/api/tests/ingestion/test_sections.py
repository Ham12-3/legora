import pytest

from app.ingestion.sections import SectionStack, detect_marker


@pytest.mark.parametrize(
    ("text", "depth", "label"),
    [
        ("ARTICLE IV RISK", 0, "ARTICLE IV RISK"),
        ("Article 4 Risk Allocation", 0, "Article 4 Risk Allocation"),
        ("SECTION 2 DATA PROTECTION", 0, "SECTION 2 DATA PROTECTION"),
        ("PART 3 BREAK AND RENEWAL", 0, "PART 3 BREAK AND RENEWAL"),
        ("8. Indemnities", 1, "8. Indemnities"),
        ("8.2 Supplier shall indemnify Customer against all losses.", 2, "8.2 Supplier shall"),
        ("8.2.1 Notice of claims", 3, "8.2.1"),
        ("(a) is or becomes public other than through breach;", 3, "(a)"),
        ("(iv) any Affiliate of the Customer.", 4, "(iv)"),
        ("DEFINITIONS AND INTERPRETATION", 0, "Definitions And Interpretation"),
    ],
)
def test_detects_numbering_conventions(text: str, depth: int, label: str) -> None:
    marker = detect_marker(text)
    assert marker is not None, text
    assert marker.depth == depth
    assert marker.label.startswith(label)


@pytest.mark.parametrize(
    "text",
    [
        "30 days after the Effective Date, Supplier shall deliver the Services.",
        "The parties acknowledge that this provision has been negotiated at arm's length.",
        "2 million pounds sterling shall be payable on completion.",
        "",
        "IN WITNESS WHEREOF the parties have executed this Agreement on the date above.",
    ],
)
def test_body_text_is_not_a_marker(text: str) -> None:
    assert detect_marker(text) is None


def test_stack_closes_deeper_levels() -> None:
    stack = SectionStack()
    for line in ["ARTICLE IV RISK", "8. Indemnities", "8.2 Supplier shall indemnify", "(a) notice"]:
        marker = detect_marker(line)
        assert marker is not None
        stack.push(marker)
    assert stack.path == "ARTICLE IV RISK > 8. Indemnities > 8.2 Supplier shall indemnify > (a)"

    marker = detect_marker("9. Limitation of Liability")
    assert marker is not None
    stack.push(marker)
    assert stack.path == "ARTICLE IV RISK > 9. Limitation of Liability"

    marker = detect_marker("ARTICLE V GENERAL")
    assert marker is not None
    stack.push(marker)
    assert stack.path == "ARTICLE V GENERAL"
