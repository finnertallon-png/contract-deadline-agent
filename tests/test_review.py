from deadline_agent.extract import DeadlineRecord
from deadline_agent.review import triage
from deadline_agent.schema import (
    AbsoluteDeadline,
    CalendarBasis,
    DurationUnit,
    Obligation,
    ObligationType,
    RelativeDeadline,
)


def record(confidence=1.0, calendar=CalendarBasis.CALENDAR, quote_verbatim=True, deadline=None):
    if deadline is None:
        deadline = RelativeDeadline(
            trigger="discovery",
            duration_value=7,
            duration_unit=DurationUnit.DAYS,
            calendar=calendar,
        )
    return DeadlineRecord(
        obligation=Obligation(
            obligation_type=ObligationType.NOTICE,
            description="Contractor must give written notice.",
            obligor="Contractor",
            deadline=deadline,
            quote="within 7 calendar days of discovery",
        ),
        source_clause="4.2",
        source_path=("ARTICLE 4", "4.2"),
        source_page=12,
        prefilter_signals=("duration",),
        confidence=confidence,
        confidence_signals={"quote_verbatim": quote_verbatim},
    )


def test_clean_record_is_approved():
    result = triage([record()])
    assert len(result.approved) == 1 and result.needs_review == []


def test_low_confidence_goes_to_review():
    result = triage([record(confidence=0.6)])
    assert result.approved == []
    assert "below threshold" in result.needs_review[0].reasons[0]


def test_fabricated_quote_never_approved_even_with_high_confidence():
    result = triage([record(confidence=1.0, quote_verbatim=False)])
    assert result.approved == []
    assert any("verbatim" in r for r in result.needs_review[0].reasons)


def test_unspecified_calendar_goes_to_review():
    result = triage([record(calendar=CalendarBasis.UNSPECIFIED)])
    assert result.approved == []
    assert any("business vs calendar" in r for r in result.needs_review[0].reasons)


def test_absolute_deadline_has_no_calendar_rule():
    result = triage([record(deadline=AbsoluteDeadline(date_text="December 31, 2026"))])
    assert len(result.approved) == 1


def test_reasons_accumulate():
    result = triage([record(confidence=0.4, calendar=CalendarBasis.UNSPECIFIED, quote_verbatim=False)])
    assert len(result.needs_review[0].reasons) == 3


def test_custom_threshold():
    result = triage([record(confidence=0.75)], threshold=0.7)
    assert len(result.approved) == 1
