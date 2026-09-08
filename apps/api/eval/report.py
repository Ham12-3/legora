# ruff: noqa: E501 -- markdown table rows are long by nature
"""Write the eval results as JSON (for diffing) and Markdown (for reading)."""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"


@dataclass
class QuestionStats:
    key: str
    name: str
    output_type: str
    total: int = 0
    correct: int = 0
    hallucinated: int = 0
    expected_absent: int = 0
    unverified: int = 0
    failed: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass
class EvalSummary:
    run_at: str
    model: str
    prompt_version: str
    provider: str
    embeddings: str
    documents: int
    questions: int
    cells: int
    accuracy: float
    citation_verification_rate: float
    hallucination_rate: float
    not_found_when_present_rate: float
    failed_cells: int
    model_calls: int
    latency_p50_ms: float
    latency_p95_ms: float
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cost_total_usd: float
    cost_per_document_usd: float
    cost_per_cell_usd: float
    ingestion_seconds: float
    grid_seconds: float
    targets: dict[str, Any]
    per_question: list[dict[str, Any]]


def write_results(summary: EvalSummary, per_question: list[QuestionStats]) -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_model = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in summary.model)
    stem = f"{stamp}_{summary.prompt_version}_{safe_model}"
    json_path = RESULTS_DIR / f"{stem}.json"
    md_path = RESULTS_DIR / f"{stem}.md"

    payload = asdict(summary)
    payload["per_question"] = [
        {**asdict(q), "accuracy": round(q.accuracy, 4)} for q in per_question
    ]
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(summary, per_question), encoding="utf-8")
    (RESULTS_DIR / "latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    return json_path, md_path


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def _target(value: float, target: float, higher_is_better: bool) -> str:
    ok = value >= target if higher_is_better else value <= target
    return "PASS" if ok else "FAIL"


def render_markdown(s: EvalSummary, per_question: list[QuestionStats]) -> str:
    lines = [
        f"# Eval - {s.run_at}",
        "",
        f"- model: `{s.model}` (provider `{s.provider}`), prompt `{s.prompt_version}`, embeddings `{s.embeddings}`",
        f"- {s.documents} documents x {s.questions} questions = {s.cells} cells, {s.model_calls} model calls",
        f"- ingestion {s.ingestion_seconds:.1f}s, grid {s.grid_seconds:.1f}s",
        "",
        "## Headline",
        "",
        "| Metric | Value | Target | |",
        "|---|---|---|---|",
        f"| Accuracy (all questions) | {_pct(s.accuracy)} | - | |",
        f"| Citation verification rate | {_pct(s.citation_verification_rate)} | >= 95% | {_target(s.citation_verification_rate, 0.95, True)} |",
        f'| Hallucination rate on "not present" | {_pct(s.hallucination_rate)} | <= 2% | {_target(s.hallucination_rate, 0.02, False)} |',
        f'| "Not found" where an answer exists | {_pct(s.not_found_when_present_rate)} | - | |',
        f"| Failed cells | {s.failed_cells} | 0 | |",
        f"| Latency p50 / p95 (per model call) | {s.latency_p50_ms:.0f} ms / {s.latency_p95_ms:.0f} ms | - | |",
        f"| Cost per cell | ${s.cost_per_cell_usd:.4f} | <= $0.02 | {_target(s.cost_per_cell_usd, 0.02, False)} |",
        f"| Cost per document | ${s.cost_per_document_usd:.4f} | - | |",
        f"| Tokens in / cached / out | {s.input_tokens:,} / {s.cached_input_tokens:,} / {s.output_tokens:,} | - | |",
        "",
        "## Per question",
        "",
        "| Question | Type | Accuracy | Hallucinated / absent | Unverified | Failed |",
        "|---|---|---|---|---|---|",
    ]
    for q in per_question:
        lines.append(
            f"| {q.name} | {q.output_type} | {_pct(q.accuracy)} ({q.correct}/{q.total}) "
            f"| {q.hallucinated} / {q.expected_absent} | {q.unverified} | {q.failed} |"
        )
    misses = [(q.name, m) for q in per_question for m in q.misses[:3]]
    if misses:
        lines += ["", "## Sample misses", ""]
        lines += [f"- **{name}**: {m}" for name, m in misses[:30]]
    if s.provider == "fake":
        lines += [
            "",
            "> The placeholder model produced these answers (no OPENAI_API_KEY). The numbers "
            "measure the harness and the verification path, not extraction quality.",
        ]
    return "\n".join(lines) + "\n"
