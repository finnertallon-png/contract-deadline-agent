"""Classify: cheap, high-recall lexical prefilter for deadline-bearing clauses.

This stage never calls a model. It exists to bound LLM cost: only clauses
that show at least one deadline signal go to extraction, and the signals are
recall-biased on purpose — a false positive costs one wasted extraction call,
a false negative is a missed deadline. When in doubt, pass it through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Clause

_NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    "fourteen|fifteen|twenty|twenty-one|twenty-four|thirty|forty-five|sixty|ninety"
)

# Signal name -> pattern. Order is presentation only; any single hit qualifies.
SIGNALS: dict[str, re.Pattern[str]] = {
    "duration": re.compile(
        rf"\b(?:\d+|{_NUMBER_WORDS})\s*(?:\(\d+\)\s*)?(?:business\s+|calendar\s+|working\s+)?"
        r"(?:days?|weeks?|months?|years?|hours?)\b",
        re.IGNORECASE,
    ),
    "time_window": re.compile(
        r"\b(?:within|no later than|not later than|prior to|on or before|"
        r"at least .{0,30} (?:before|prior)|upon receipt|after receipt|"
        r"promptly (?:after|upon)|by the (?:earlier|later) of)\b",
        re.IGNORECASE,
    ),
    "absolute_date": re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4}\b"
    ),
    "obligation_language": re.compile(
        r"\b(?:notice|notify|notification|cure|remedy|submit|submission|"
        r"claim|respond|response|deadline|waive[dr]?|time is of the essence)\b",
        re.IGNORECASE,
    ),
}

# Signals that qualify a clause on their own. "obligation_language" alone
# does not — plenty of clauses mention notice with no time bound — but it is
# reported when present because it is a useful hint for the extractor.
_QUALIFYING = ("duration", "time_window", "absolute_date")


@dataclass(frozen=True)
class Candidate:
    clause: Clause
    signals: tuple[str, ...]


def find_candidates(clauses: list[Clause]) -> list[Candidate]:
    candidates = []
    for clause in clauses:
        text = clause.text if clause.heading is None else f"{clause.heading}. {clause.text}"
        hits = tuple(name for name, pattern in SIGNALS.items() if pattern.search(text))
        if any(name in _QUALIFYING for name in hits):
            candidates.append(Candidate(clause=clause, signals=hits))
    return candidates
