"""Document-level metadata: parties, project, contract value, effective date.

This is a separate, single pass over the document's opening text — contract
metadata lives in the preamble and recitals, not scattered through clauses,
so one bounded call is enough and the clause pipeline stays deadline-only.
Values are extracted verbatim (the stated dollar amount, the stated date)
and verified by containment against the source text, the same discipline as
the deadline quotes. Anything the opening pages don't state comes back None
rather than guessed; metadata defined only in exhibits or changed by
amendment is missed (recorded in docs/LIMITATIONS.md).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .confidence import normalize_ws
from .models import Block

METADATA_SYSTEM = """\
You extract document-level metadata from the opening text of a construction \
or commercial contract.

Rules:
- Use only the text provided.
- contract_value_text and effective_date_text are verbatim spans copied \
from the text, exactly as written. Never reformat, compute, or convert.
- Party names exactly as written, with the role the document assigns them \
(Owner, Contractor, Architect, ...) when it assigns one.
- Any field the text does not state is null (or an empty list). Never \
guess from what contracts usually say."""


class Party(BaseModel):
    name: str = Field(description="Party name exactly as written")
    role: str | None = Field(default=None, description="Role the document assigns, e.g. Owner")


class ContractMetadata(BaseModel):
    parties: list[Party] = Field(default_factory=list)
    project_name: str | None = None
    contract_value_text: str | None = Field(
        default=None, description="The stated contract value, verbatim"
    )
    effective_date_text: str | None = Field(
        default=None, description="The stated effective/agreement date, verbatim"
    )


def opening_text(blocks: list[Block], max_chars: int = 6000) -> str:
    """The document's opening, joined in order and capped by size."""
    parts: list[str] = []
    total = 0
    for block in blocks:
        parts.append(block.text)
        total += len(block.text) + 1
        if total >= max_chars:
            break
    return " ".join(parts)


def verify(metadata: ContractMetadata, source_text: str) -> dict[str, bool]:
    """Containment checks per populated field; absent fields get no signal."""
    source = normalize_ws(source_text)
    signals: dict[str, bool] = {}
    if metadata.parties:
        signals["parties_found"] = all(
            normalize_ws(p.name) in source for p in metadata.parties
        )
    if metadata.project_name is not None:
        signals["project_name_found"] = normalize_ws(metadata.project_name) in source
    if metadata.contract_value_text is not None:
        signals["contract_value_found"] = normalize_ws(metadata.contract_value_text) in source
    if metadata.effective_date_text is not None:
        signals["effective_date_found"] = normalize_ws(metadata.effective_date_text) in source
    return signals
