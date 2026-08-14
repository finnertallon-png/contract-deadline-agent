from deadline_agent.models import Block
from deadline_agent.segment import Kind, parse_marker, segment


def blocks(*lines: str) -> list[Block]:
    return [Block(text=t, index=i, page=1) for i, t in enumerate(lines)]


class TestParseMarker:
    def test_article_roman(self):
        m = parse_marker("ARTICLE V — CHANGES IN THE WORK")
        assert m.kind == Kind.ARTICLE and m.value == "V"

    def test_article_arabic(self):
        m = parse_marker("Article 7. Claims and Disputes")
        assert m.kind == Kind.ARTICLE and m.value == "7"

    def test_multi_decimal(self):
        m = parse_marker("7.3.1 The Contractor shall provide written notice.")
        assert m.kind == Kind.DECIMAL and m.value == "7.3.1"
        assert m.rest.startswith("The Contractor")

    def test_section_word(self):
        m = parse_marker("Section 4.2 Notice of Claims. All claims shall...")
        assert m.kind == Kind.DECIMAL and m.value == "4.2"

    def test_single_integer_requires_punctuation(self):
        assert parse_marker("7 days after discovery of the condition") is None
        m = parse_marker("7. Time for Completion")
        assert m is not None and m.value == "7"

    def test_paren_letter(self):
        m = parse_marker("(a) within seven days of discovery;")
        assert m.kind == Kind.PAREN_LETTER and m.value == "a"

    def test_paren_roman_multichar(self):
        m = parse_marker("(iv) the date of Substantial Completion;")
        assert m.kind == Kind.PAREN_ROMAN and m.value == "iv"

    def test_paren_i_defaults_to_roman(self):
        m = parse_marker("(i) any delay caused by the Owner;")
        assert m.kind == Kind.PAREN_ROMAN and m.value == "i"

    def test_plain_prose_is_not_a_marker(self):
        assert parse_marker("The Contractor shall promptly notify the Owner.") is None


class TestSegment:
    def test_preamble_before_first_marker(self):
        cs = segment(blocks("SYNTHETIC — GENERATED TEST DATA", "This Agreement is made...", "1. Definitions"))
        assert cs[0].number is None
        assert "SYNTHETIC" in cs[0].text
        assert cs[1].number == "1."

    def test_decimal_hierarchy_from_components(self):
        cs = segment(blocks(
            "7. Claims",
            "7.1 Notice of Claims. Claims must be initiated by written notice.",
            "7.1.1 Claims for additional cost shall follow this section.",
            "7.2 Time Limits. All claims are waived after final payment.",
        ))
        by_number = {c.number: c for c in cs}
        assert by_number["7.1.1"].path == ("7.", "7.1", "7.1.1")
        assert by_number["7.2"].path == ("7.", "7.2")
        assert by_number["7.2"].level == 1

    def test_article_resets_hierarchy(self):
        cs = segment(blocks(
            "ARTICLE I — DEFINITIONS",
            "1.1 The Work means the construction required by the Contract Documents.",
            "ARTICLE II — CONTRACT SUM",
            "2.1 The Owner shall pay the Contract Sum as provided below.",
        ))
        by_number = {c.number: c for c in cs}
        assert by_number["2.1"].path[0].startswith("ARTICLE II")
        assert len(by_number["2.1"].path) == 2

    def test_letters_nest_under_decimals(self):
        cs = segment(blocks(
            "4.3 Notice. The Contractor shall give notice:",
            "(a) within 7 days of discovery; and",
            "(b) within 21 days, a priced claim.",
            "4.4 Cure. The Owner may cure after 10 days.",
        ))
        by_number = {c.number: c for c in cs}
        assert by_number["(a)"].path == ("4.3", "(a)")
        assert by_number["(b)"].path == ("4.3", "(b)")
        assert by_number["4.4"].level == 0

    def test_i_after_h_is_a_letter(self):
        lines = [f"({ch}) item {ch};" for ch in "abcdefghi"]
        cs = segment(blocks("3.1 List of Events.", *lines))
        i_clause = [c for c in cs if c.number == "(i)"][0]
        assert i_clause.level == cs[1].level  # sibling of (a), not a child of it

    def test_i_after_letter_a_starts_roman_sublist(self):
        cs = segment(blocks(
            "3.1 Termination Events.",
            "(a) if the Contractor fails to perform:",
            "(i) after written notice; or",
            "(ii) after a second notice;",
            "(b) if the Owner fails to pay.",
        ))
        by_number = {c.number: c for c in cs}
        assert by_number["(i)"].path == ("3.1", "(a)", "(i)")
        assert by_number["(b)"].path == ("3.1", "(b)")

    def test_year_at_line_start_is_not_a_marker(self):
        cs = segment(blocks(
            "5.2 Commencement. The Work commenced on March 1,",
            "2021. The parties agree that time is of the essence.",
        ))
        assert len(cs) == 1
        assert "2021. The parties agree" in cs[0].text

    def test_continuation_lines_join_into_clause_text(self):
        cs = segment(blocks(
            "8.1 Notice of Delay. The Contractor shall notify the Owner of any",
            "delay within seven (7) days of the event giving rise to the",
            "delay, failing which the claim is waived.",
        ))
        assert len(cs) == 1
        assert "notify the Owner of any delay within seven (7) days" in cs[0].text

    def test_heading_split(self):
        cs = segment(blocks("9.1 Final Payment. Final payment shall be made within 30 days."))
        assert cs[0].heading == "Final Payment"
        assert cs[0].text.startswith("Final payment shall be made")

    def test_heading_does_not_swallow_sentence_continuation(self):
        # Found by the first live run: repeated title-case words made the
        # whole wrapped line pass the heading check, splitting a sentence.
        cs = segment(blocks(
            "5.2 Final Completion. The Contractor shall achieve Final Completion of",
            "the Work no later than December 31, 2026.",
        ))
        assert cs[0].heading == "Final Completion"
        assert cs[0].text.startswith("The Contractor shall achieve")
        assert "Completion of the Work no later" in cs[0].text

    def test_no_heading_when_body_starts_directly(self):
        cs = segment(blocks("9.2 The Contractor shall submit its final application for payment."))
        assert cs[0].heading is None
        assert cs[0].text.startswith("The Contractor")

    def test_page_span(self):
        bs = [
            Block(text="10.1 Indemnity. The Contractor shall indemnify", index=0, page=3),
            Block(text="the Owner against all claims arising from the Work.", index=1, page=4),
        ]
        cs = segment(bs)
        assert cs[0].page_start == 3 and cs[0].page_end == 4
