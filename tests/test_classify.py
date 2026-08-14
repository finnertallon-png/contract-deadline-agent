from deadline_agent.classify import find_candidates
from deadline_agent.models import Clause


def clause(text, heading=None, number="1.1"):
    return Clause(
        number=number, heading=heading, text=text, level=1,
        path=(number,), page_start=1, page_end=1,
    )


class TestPrefilterRecall:
    """These must ALL be caught — a miss here is a missed deadline."""

    def test_numeric_duration(self):
        cs = find_candidates([clause("Notice shall be given within 7 days of discovery.")])
        assert len(cs) == 1
        assert "duration" in cs[0].signals and "time_window" in cs[0].signals

    def test_word_duration(self):
        assert find_candidates([clause("within seven days after the event")])

    def test_word_and_parenthetical_digits(self):
        assert find_candidates([clause("no later than twenty-one (21) days thereafter")])

    def test_business_days(self):
        assert find_candidates([clause("respond within ten business days")])

    def test_absolute_date(self):
        assert find_candidates([clause("Final completion shall occur by December 31, 2026.")])

    def test_time_window_without_number(self):
        assert find_candidates([clause("Contractor shall notify Owner promptly after discovery.")])

    def test_heading_counts_toward_signals(self):
        c = clause("The Contractor shall comply with Section 4.", heading="Notice Within 10 Days")
        assert find_candidates([c])


class TestPrefilterPrecision:
    """Cheap rejections — no time signal at all."""

    def test_plain_clause_skipped(self):
        cs = find_candidates([clause("The Work shall be performed in a workmanlike manner.")])
        assert cs == []

    def test_obligation_word_alone_not_enough(self):
        # "notice" with no time bound: mention, not a deadline
        cs = find_candidates([clause("All notices shall be delivered to the addresses below.")])
        assert cs == []

    def test_money_is_not_a_duration(self):
        cs = find_candidates([clause("The Contract Sum is $4,500,000 payable as set forth herein.")])
        assert cs == []
