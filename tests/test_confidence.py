from deadline_agent.confidence import durations_in, quote_verbatim, score
from deadline_agent.schema import (
    AbsoluteDeadline,
    CalendarBasis,
    DurationUnit,
    Obligation,
    ObligationType,
    RelativeDeadline,
)

CLAUSE = (
    "Notice of Claims. Claims by either party must be initiated by written "
    "notice to the other party within twenty-one (21) days after occurrence "
    "of the event giving rise to such Claim."
)


def obligation(quote=None, calendar=CalendarBasis.UNSPECIFIED, value=21):
    return Obligation(
        obligation_type=ObligationType.NOTICE,
        description="Either party must give written notice of a claim.",
        obligor="either party",
        deadline=RelativeDeadline(
            trigger="occurrence of the event giving rise to the Claim",
            duration_value=value,
            duration_unit=DurationUnit.DAYS,
            calendar=calendar,
        ),
        quote=quote if quote is not None
        else "within twenty-one (21) days after occurrence of the event",
    )


class TestQuoteVerbatim:
    def test_whitespace_insensitive(self):
        assert quote_verbatim("within twenty-one (21)\n days", CLAUSE)

    def test_fabricated_quote_fails(self):
        assert not quote_verbatim("within thirty (30) days of discovery", CLAUSE)

    def test_empty_quote_fails(self):
        assert not quote_verbatim("   ", CLAUSE)


class TestDurations:
    def test_digits(self):
        assert (7, "day") in durations_in("within 7 days of discovery")

    def test_word_with_parenthetical(self):
        assert (21, "day") in durations_in("twenty-one (21) days after")

    def test_word_only(self):
        assert (7, "day") in durations_in("within seven days")

    def test_business_days(self):
        assert (10, "day") in durations_in("ten (10) business days")


class TestScore:
    def test_clean_extraction_scores_high(self):
        value, signals = score(obligation(), CLAUSE)
        assert value == 1.0
        assert all(signals.values())

    def test_fabricated_quote_caps_score(self):
        value, signals = score(obligation(quote="within thirty (30) days of discovery", value=30), CLAUSE)
        assert value <= 0.2
        assert not signals["quote_verbatim"]

    def test_duration_mismatch_penalized(self):
        value, signals = score(obligation(value=14), CLAUSE)
        assert not signals["duration_in_quote"]
        assert value < 1.0

    def test_calendar_guess_penalized(self):
        # Clause never says "business days"; claiming business is a guess.
        value, signals = score(obligation(calendar=CalendarBasis.BUSINESS), CLAUSE)
        assert not signals["calendar_consistent"]
        assert value < 1.0

    def test_unspecified_consistent_when_clause_is_silent(self):
        _, signals = score(obligation(calendar=CalendarBasis.UNSPECIFIED), CLAUSE)
        assert signals["calendar_consistent"]

    def test_unspecified_inconsistent_when_quote_says_business(self):
        clause = "Owner shall respond within ten (10) business days of receipt."
        ob = obligation(quote="within ten (10) business days of receipt", value=10)
        _, signals = score(ob, clause)
        assert not signals["calendar_consistent"]

    def test_absolute_date_checked_against_quote(self):
        ob = Obligation(
            obligation_type=ObligationType.SUBMISSION,
            description="Submit final application by the stated date.",
            deadline=AbsoluteDeadline(date_text="December 31, 2026"),
            quote="final application for payment shall be submitted by December 31, 2026",
        )
        clause = "The final application for payment shall be submitted by December 31, 2026."
        value, signals = score(ob, clause)
        assert value == 1.0 and signals["date_in_quote"]

    def test_absolute_date_not_in_quote_penalized(self):
        ob = Obligation(
            obligation_type=ObligationType.SUBMISSION,
            description="Submit final application by the stated date.",
            deadline=AbsoluteDeadline(date_text="January 15, 2027"),
            quote="final application for payment shall be submitted by December 31, 2026",
        )
        value, signals = score(ob, "shall be submitted by December 31, 2026")
        assert not signals["date_in_quote"]
        assert value < 1.0
