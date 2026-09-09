from app.assistant.stream import AnswerFieldStreamer


def _run(chunks: list[str]) -> str:
    s = AnswerFieldStreamer()
    return "".join(s.feed(c) for c in chunks)


def test_streams_only_the_answer_field() -> None:
    raw = (
        '{"answer": "Hello, world.", '
        '"citations": [{"marker": 1, "chunk_id": "d1c2", "text": "x"}], "insufficient": false}'
    )
    assert _run([raw]) == "Hello, world."


def test_handles_arbitrary_chunk_boundaries() -> None:
    raw = '{"answer": "The cap is 125% of the Fees [1].", "citations": [], "insufficient": false}'
    for size in (1, 2, 3, 5, 7, 11):
        chunks = [raw[i : i + size] for i in range(0, len(raw), size)]
        assert _run(chunks) == "The cap is 125% of the Fees [1].", size


def test_decodes_escapes_and_stops_at_closing_quote() -> None:
    raw = '{"answer": "Line one.\\nShe said \\"yes\\" \\u2014 done.", "citations": []}'
    assert _run([raw]) == 'Line one.\nShe said "yes" — done.'


def test_ignores_answer_word_inside_other_strings() -> None:
    raw = (
        '{"insufficient": false, '
        '"citations": [{"text": "no answer here", "marker": 1, "chunk_id": "c"}], '
        '"answer": "Real."}'
    )
    assert _run([raw]) == "Real."
