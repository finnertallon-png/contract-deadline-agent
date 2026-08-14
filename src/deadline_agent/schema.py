"""Extraction schema: what one time-bound obligation looks like.

The deadline itself is a tagged union. ``relative`` stores the rule —
trigger + duration + unit — never a computed date, because the trigger event
usually has not happened yet. ``absolute`` stores a date the contract states
verbatim ("by December 31, 2026"); extracting a stated date is not computing
one, so this stays inside the LIMITATIONS promise.

``calendar`` allows ``unspecified`` deliberately: whether days are business
or calendar days is often defined elsewhere in the contract (a known failure
mode), and forcing a binary choice would make the model guess.

Pydantic rather than dataclasses here because these models double as the
structured-output schema for the extraction call, which validates against
them at the API layer.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Union

from pydantic import BaseModel, Field


class ObligationType(str, Enum):
    NOTICE = "notice"
    CURE = "cure"
    SUBMISSION = "submission"
    PAYMENT = "payment"
    OTHER = "other"


class DurationUnit(str, Enum):
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"


class CalendarBasis(str, Enum):
    BUSINESS = "business"
    CALENDAR = "calendar"
    UNSPECIFIED = "unspecified"


class RelativeDeadline(BaseModel):
    kind: Literal["relative"] = "relative"
    trigger: str = Field(description="The event that starts the clock, as described in the clause")
    duration_value: int = Field(description="Number of units in the window")
    duration_unit: DurationUnit
    calendar: CalendarBasis = Field(
        description="business or calendar ONLY if the clause says so explicitly; otherwise unspecified"
    )


class AbsoluteDeadline(BaseModel):
    kind: Literal["absolute"] = "absolute"
    date_text: str = Field(
        description="The date exactly as stated in the clause, verbatim. Never a computed date."
    )


class Obligation(BaseModel):
    obligation_type: ObligationType
    description: str = Field(description="One sentence: who must do what")
    obligor: str | None = Field(
        default=None, description="The party that must act, as named in the clause"
    )
    deadline: Union[RelativeDeadline, AbsoluteDeadline] = Field(discriminator="kind")
    quote: str = Field(
        description="The exact contiguous span of clause text stating this obligation, verbatim"
    )


class ClauseExtraction(BaseModel):
    obligations: list[Obligation]
