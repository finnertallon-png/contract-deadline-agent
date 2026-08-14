from deadline_agent.metadata import ContractMetadata, Party, opening_text, verify
from deadline_agent.models import Block

PREAMBLE = (
    "This Agreement is made as of March 1, 2026 (the 'Effective Date'), "
    "between Riverbend Development LLC (the 'Owner') and Cardinal "
    "Structures, Inc. (the 'Contractor') for the project known as the "
    "Maple Street Parking Structure. The Contract Sum is Four Million Five "
    "Hundred Thousand Dollars ($4,500,000)."
)


def metadata(**overrides):
    fields = dict(
        parties=[
            Party(name="Riverbend Development LLC", role="Owner"),
            Party(name="Cardinal Structures, Inc.", role="Contractor"),
        ],
        project_name="Maple Street Parking Structure",
        contract_value_text="Four Million Five Hundred Thousand Dollars ($4,500,000)",
        effective_date_text="March 1, 2026",
    )
    fields.update(overrides)
    return ContractMetadata(**fields)


class TestVerify:
    def test_all_fields_found(self):
        signals = verify(metadata(), PREAMBLE)
        assert signals == {
            "parties_found": True,
            "project_name_found": True,
            "contract_value_found": True,
            "effective_date_found": True,
        }

    def test_invented_party_fails(self):
        m = metadata(parties=[Party(name="Acme Holdings LLC", role="Owner")])
        assert verify(m, PREAMBLE)["parties_found"] is False

    def test_reformatted_value_fails(self):
        # "$4.5M" is a conversion, not a verbatim span
        m = metadata(contract_value_text="$4.5M")
        assert verify(m, PREAMBLE)["contract_value_found"] is False

    def test_absent_fields_get_no_signal(self):
        m = ContractMetadata()
        assert verify(m, PREAMBLE) == {}


class TestOpeningText:
    def blocks(self, texts):
        return [Block(text=t, index=i, page=1) for i, t in enumerate(texts)]

    def test_joins_in_order(self):
        text = opening_text(self.blocks(["first line", "second line"]))
        assert text == "first line second line"

    def test_caps_at_max_chars(self):
        text = opening_text(self.blocks(["x" * 100] * 100), max_chars=250)
        assert len(text) < 400  # stops after crossing the cap, not at 10,000
