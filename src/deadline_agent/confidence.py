"""Confidence: derived from checkable signals, never self-reported.

Asking a model how sure it is produces uncalibrated numbers. Instead, every
extraction is checked against things we can verify mechanically:

- ``quote_verbatim`` — the supporting quote actually appears in the clause.
  A fabricated quote is the strongest fabrication signal we have, so failing
  it caps the score hard.
- ``duration_in_quote`` — the extracted duration (value + unit) can be found
  in the quote text, including number-word forms ("seven (7) days").
- ``calendar_consistent`` — the business/calendar/unspecified choice matches
  what the quote says (unspecified must NOT co-occur with an explicit
  "business days"/"calendar days" in the quote, and vice versa).
- ``date_in_quote`` — for absolute deadlines, the stated date appears in the
  quote.

The review-queue threshold is a separate decision, recorded in
docs/ARCHITECTURE.md once a labeled set exists to choose it against.
"""

from __future__ import annotations

import re

from .schema import AbsoluteDeadline, CalendarBasis, Obligation, RelativeDeadline

_WORD_VALUES = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "twenty": 20,
    "twenty-one": 21, "twenty-four": 24, "thirty": 30, "forty-five": 45,
    "sixty": 60, "ninety": 90,
}

_DURATION_RE = re.compile(
    r"\b(?:(?P<word>[a-z]+(?:-[a-z]+)?)\s*)?\(?(?P<digits>\d+)\)?\s*"
    r"(?:business\s+|calendar\s+|working\s+)?"
    r"(?P<unit>hours?|days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)
_WORD_DURATION_RE = re.compile(
    rf"\b(?P<word>{'|'.join(_WORD_VALUES)})\s+"
    r"(?:business\s+|calendar\s+|working\s+)?(?P<unit>hours?|days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_verbatim(quote: str, clause_text: str) -> bool:
    """Whitespace-insensitive containment check; empty quotes never pass."""
    q = normalize_ws(quote)
    return bool(q) and q in normalize_ws(clause_text)


def durations_in(text: str) -> set[tuple[int, str]]:
    """All (value, unit) durations stated in text, units normalized singular."""
    found: set[tuple[int, str]] = set()
    for m in _DURATION_RE.finditer(text):
        found.add((int(m.group("digits")), m.group("unit").lower().rstrip("s")))
    for m in _WORD_DURATION_RE.finditer(text):
        found.add((_WORD_VALUES[m.group("word").lower()], m.group("unit").lower().rstrip("s")))
    return found


def _calendar_consistent(deadline: RelativeDeadline, quote: str) -> bool:
    q = quote.lower()
    says_business = "business day" in q or "working day" in q
    says_calendar = "calendar day" in q
    if deadline.calendar == CalendarBasis.BUSINESS:
        return says_business
    if deadline.calendar == CalendarBasis.CALENDAR:
        return says_calendar
    return not (says_business or says_calendar)


def score(obligation: Obligation, clause_text: str) -> tuple[float, dict[str, bool]]:
    """Return (confidence, signals). Weights are provisional and documented
    in docs/ARCHITECTURE.md; they will be tuned once a labeled set exists."""
    signals: dict[str, bool] = {}
    signals["quote_verbatim"] = quote_verbatim(obligation.quote, clause_text)

    value = 1.0
    deadline = obligation.deadline
    if isinstance(deadline, RelativeDeadline):
        unit = deadline.duration_unit.value.rstrip("s")
        signals["duration_in_quote"] = (deadline.duration_value, unit) in durations_in(
            obligation.quote
        )
        signals["calendar_consistent"] = _calendar_consistent(deadline, obligation.quote)
        if not signals["duration_in_quote"]:
            value -= 0.4
        if not signals["calendar_consistent"]:
            value -= 0.2
    elif isinstance(deadline, AbsoluteDeadline):
        signals["date_in_quote"] = normalize_ws(deadline.date_text) in normalize_ws(obligation.quote)
        if not signals["date_in_quote"]:
            value -= 0.4

    if not signals["quote_verbatim"]:
        value = min(value, 0.2)  # a fabricated quote dominates everything else
    return max(value, 0.0), signals
