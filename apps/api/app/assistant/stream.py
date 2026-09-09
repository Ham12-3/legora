"""Stream the ``answer`` field out of a Structured Outputs JSON as it arrives.

The model emits ``{"answer": "...", "citations": [...], "insufficient": ...}``
token by token. Users should see the prose appear as it is written, so this
tiny state machine watches the raw text for the ``answer`` string and yields
its decoded characters, stopping at the closing quote. Everything else in the
JSON is parsed properly once the response is complete.
"""

import json


class AnswerFieldStreamer:
    def __init__(self) -> None:
        self._buffer = ""
        self._in_answer = False
        self._done = False
        self._escape = ""

    def feed(self, delta: str) -> str:
        """Feed raw JSON text; return the decoded answer text newly available."""
        if self._done:
            return ""
        out: list[str] = []
        for ch in delta:
            if not self._in_answer:
                self._buffer += ch
                idx = self._buffer.find('"answer"')
                if idx == -1:
                    if len(self._buffer) > 64:
                        self._buffer = self._buffer[-64:]
                    continue
                rest = self._buffer[idx + len('"answer"') :]
                colon = rest.find(":")
                if colon == -1:
                    continue
                quote = rest.find('"', colon)
                if quote == -1:
                    continue
                self._in_answer = True
                self._buffer = ""
                # Anything after the opening quote in this same chunk is answer text.
                out.append(self.feed(rest[quote + 1 :]))
                continue

            if self._escape:
                self._escape += ch
                decoded = _try_decode_escape(self._escape)
                if decoded is not None:
                    out.append(decoded)
                    self._escape = ""
                elif len(self._escape) > 6:
                    self._escape = ""  # malformed; drop it rather than stall
                continue
            if ch == "\\":
                self._escape = "\\"
                continue
            if ch == '"':
                self._done = True
                break
            out.append(ch)
        return "".join(out)


def _try_decode_escape(seq: str) -> str | None:
    if seq.startswith("\\u"):
        if len(seq) < 6:
            return None
        try:
            return json.loads(f'"{seq}"')  # type: ignore[no-any-return]
        except ValueError:
            return ""
    if len(seq) == 2:
        try:
            return json.loads(f'"{seq}"')  # type: ignore[no-any-return]
        except ValueError:
            return ""
    return None
