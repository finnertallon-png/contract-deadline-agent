"""Pipeline tests with a fake extractor — no network, no API key."""

from deadline_agent.extract import extract_deadlines
from deadline_agent.models import Clause
from deadline_agent.schema import (
    CalendarBasis,
    ClauseExtraction,
    DurationUnit,
    Obligation,
    ObligationType,
    RelativeDeadline,
)

NOTICE_CLAUSE = Clause(
    number="4.2",
    heading="Differing Site Conditions",
    text=(
        "The Contractor shall give written notice within 7 days of discovery "
        "of any concealed or unknown condition."
    ),
    level=1,
    path=("ARTICLE 4", "4.2"),
    page_start=12,
    page_end=12,
)

PLAIN_CLAUSE = Clause(
    number="4.3",
    heading="Cooperation",
    text="The parties shall cooperate in good faith in the performance of the Work.",
    level=1,
    path=("ARTICLE 4", "4.3"),
    page_start=12,
    page_end=12,
)


class FakeExtractor:
    def __init__(self, results):
        self.results = results
        self.seen = []

    def extract(self, candidate):
        self.seen.append(candidate.clause.number)
        return self.results.get(candidate.clause.number, ClauseExtraction(obligations=[]))


def good_obligation():
    return Obligation(
        obligation_type=ObligationType.NOTICE,
        description="Contractor must give written notice of a concealed condition.",
        obligor="Contractor",
        deadline=RelativeDeadline(
            trigger="discovery of a concealed or unknown condition",
            duration_value=7,
            duration_unit=DurationUnit.DAYS,
            calendar=CalendarBasis.UNSPECIFIED,
        ),
        quote="written notice within 7 days of discovery",
    )


def test_only_candidates_reach_the_extractor():
    fake = FakeExtractor({"4.2": ClauseExtraction(obligations=[good_obligation()])})
    extract_deadlines([NOTICE_CLAUSE, PLAIN_CLAUSE], fake)
    assert fake.seen == ["4.2"]


def test_record_carries_provenance_and_confidence():
    fake = FakeExtractor({"4.2": ClauseExtraction(obligations=[good_obligation()])})
    records = extract_deadlines([NOTICE_CLAUSE, PLAIN_CLAUSE], fake)
    assert len(records) == 1
    record = records[0]
    assert record.source_clause == "4.2"
    assert record.source_path == ("ARTICLE 4", "4.2")
    assert record.source_page == 12
    assert record.confidence == 1.0
    assert "duration" in record.prefilter_signals


def test_fabricated_quote_gets_low_confidence():
    bad = good_obligation()
    bad.quote = "written notice within 14 days of substantial completion"
    fake = FakeExtractor({"4.2": ClauseExtraction(obligations=[bad])})
    records = extract_deadlines([NOTICE_CLAUSE], fake)
    assert records[0].confidence <= 0.2
    assert not records[0].confidence_signals["quote_verbatim"]


def test_empty_extraction_produces_no_records():
    fake = FakeExtractor({})
    assert extract_deadlines([NOTICE_CLAUSE], fake) == []


def test_schema_discriminates_deadline_kinds():
    data = {
        "obligations": [{
            "obligation_type": "submission",
            "description": "Submit the final application by the stated date.",
            "deadline": {"kind": "absolute", "date_text": "December 31, 2026"},
            "quote": "by December 31, 2026",
        }]
    }
    extraction = ClauseExtraction.model_validate(data)
    assert extraction.obligations[0].deadline.kind == "absolute"
