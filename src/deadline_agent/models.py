"""Core data types shared across pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Block:
    """One line- or paragraph-level unit of source text, in document order.

    PDFs produce one Block per visual line (page numbers are meaningful there);
    DOCX produces one Block per paragraph (page is None because DOCX has no
    fixed pagination).
    """

    text: str
    index: int
    page: int | None = None
    indent: float | None = None
    is_list_item: bool = False
    list_level: int | None = None


@dataclass
class IngestResult:
    path: str
    kind: Literal["pdf", "docx"]
    blocks: list[Block]
    page_count: int | None


@dataclass
class Clause:
    """A contiguous clause identified by its numbering marker.

    ``number`` is the marker as printed ("7.3", "ARTICLE 5", "(a)");
    ``path`` is the chain of markers from the top of the hierarchy down to
    this clause, so "(a)" under section 7.3 has path ("7", "7.3", "(a)").
    Text preceding the first marker becomes a single preamble clause with
    ``number=None``.
    """

    number: str | None
    heading: str | None
    text: str
    level: int
    path: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    block_indexes: list[int] = field(default_factory=list)
