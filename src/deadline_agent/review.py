"""Review: route extractions that shouldn't be trusted silently to a human.

A record is approved only when nothing argues against it. Three things do:

- The supporting quote was not found verbatim in the clause. This is never
  approvable regardless of the score — it means the extraction cannot be
  traced back to the contract text.
- Confidence fell below the threshold. The threshold is PROVISIONAL until a
  labeled set exists to choose it against (see docs/ARCHITECTURE.md); the
  value here errs toward sending more to review, because the cost of a bad
  approval is a missed legal deadline.
- A relative deadline whose business-vs-calendar basis the clause doesn't
  state. The extraction is honest ("unspecified"), but the distinction can
  move a real deadline by days, so a person confirms it against the
  contract's definitions section.
"""

from __future__ import annotations

from dataclasses import dataclass

from .extract import DeadlineRecord
from .schema import CalendarBasis, RelativeDeadline

DEFAULT_THRESHOLD = 0.8  # provisional — pending a labeled set


@dataclass
class ReviewItem:
    record: DeadlineRecord
    reasons: list[str]


@dataclass
class TriageResult:
    approved: list[DeadlineRecord]
    needs_review: list[ReviewItem]
    threshold: float


def triage(records: list[DeadlineRecord], threshold: float = DEFAULT_THRESHOLD) -> TriageResult:
    approved: list[DeadlineRecord] = []
    needs_review: list[ReviewItem] = []
    for record in records:
        reasons = []
        if not record.confidence_signals.get("quote_verbatim", False):
            reasons.append("supporting quote not found verbatim in the clause")
        if record.confidence < threshold:
            reasons.append(
                f"confidence {record.confidence:.2f} below threshold {threshold:.2f}"
            )
        deadline = record.obligation.deadline
        if isinstance(deadline, RelativeDeadline) and deadline.calendar == CalendarBasis.UNSPECIFIED:
            reasons.append("business vs calendar days not stated in the clause")
        if reasons:
            needs_review.append(ReviewItem(record=record, reasons=reasons))
        else:
            approved.append(record)
    return TriageResult(approved=approved, needs_review=needs_review, threshold=threshold)
