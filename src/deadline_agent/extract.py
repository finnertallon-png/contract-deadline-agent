"""Extract: one LLM pass per candidate clause does classify + extract together.

The prefilter (classify.py) has already bounded the call count; a second
model call just to classify would double cost for no signal we can't get
from the extraction itself (a clause with no time-bound obligation extracts
to an empty list).

The extractor sits behind a Protocol so the pipeline and tests never need
network access; ``ClaudeExtractor`` is the real implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from . import confidence
from .classify import Candidate, find_candidates
from .models import Clause
from .schema import ClauseExtraction, Obligation

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
You extract time-bound obligations from clauses of construction and \
commercial contracts. For each obligation in the clause that carries a \
deadline, notice window, cure period, or submission window, produce one \
record.

Rules:
- Use only the clause text provided. Never rely on outside knowledge of \
what contracts usually say.
- quote must be an exact contiguous span copied verbatim from the clause.
- A deadline is relative (trigger event + duration) or absolute (a date the \
clause states). Never compute a calendar date from a relative window.
- Set calendar to business or calendar ONLY if the clause says so \
explicitly. Otherwise use unspecified. Do not infer it.
- If the clause creates no time-bound obligation, return an empty list. \
Do not invent obligations to have something to return.
- If drafting is genuinely ambiguous about the duration or trigger, still \
extract the obligation but keep description faithful to the ambiguity."""


class Extractor(Protocol):
    def extract(self, candidate: Candidate) -> ClauseExtraction: ...


@dataclass
class DeadlineRecord:
    """An extracted obligation with provenance and derived confidence."""

    obligation: Obligation
    source_clause: str | None
    source_path: tuple[str, ...]
    source_page: int | None
    prefilter_signals: tuple[str, ...]
    confidence: float
    confidence_signals: dict[str, bool]


def _clause_prompt(clause: Clause) -> str:
    parts = []
    if clause.path:
        parts.append(f"Clause {' > '.join(clause.path)}")
    if clause.heading:
        parts.append(f"Heading: {clause.heading}")
    parts.append("Text:")
    parts.append(clause.text)
    return "\n".join(parts)


class ClaudeExtractor:
    """Real extractor backed by the Claude API.

    Requires ANTHROPIC_API_KEY (or an active `ant auth login` profile) in
    the environment; construction does not touch the network, only calls do.
    """

    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model

    def extract(self, candidate: Candidate) -> ClauseExtraction:
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=4096,
            # The system prompt is byte-identical across every clause of a
            # document, so cache it and pay full price only once per run.
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": _clause_prompt(candidate.clause)}],
            output_format=ClauseExtraction,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            return ClauseExtraction(obligations=[])
        return response.parsed_output


def extract_deadlines(clauses: list[Clause], extractor: Extractor) -> list[DeadlineRecord]:
    """Run prefilter + extraction + confidence over segmented clauses."""
    records: list[DeadlineRecord] = []
    for candidate in find_candidates(clauses):
        clause = candidate.clause
        clause_text = clause.text if clause.heading is None else f"{clause.heading}. {clause.text}"
        for obligation in extractor.extract(candidate).obligations:
            value, signals = confidence.score(obligation, clause_text)
            records.append(
                DeadlineRecord(
                    obligation=obligation,
                    source_clause=clause.number,
                    source_path=clause.path,
                    source_page=clause.page_start,
                    prefilter_signals=candidate.signals,
                    confidence=value,
                    confidence_signals=signals,
                )
            )
    return records
