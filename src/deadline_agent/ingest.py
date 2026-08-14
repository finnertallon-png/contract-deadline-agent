"""Ingest: PDF or DOCX in, ordered text blocks out.

PDFs are emitted one Block per visual line, keeping the page number and left
x-coordinate of each line. Clause numbering in contracts is a line-start
signal, so line granularity is what segmentation needs; paragraph reassembly
happens there, where marker context is available.

DOCX is emitted one Block per paragraph. Word's automatic list numbering is
not rendered into the text by python-docx, so where a document relies on it
we only get *that* a paragraph is a numbered list item and at what level —
captured on the Block for segmentation to use as a fallback signal. Text
inside DOCX tables is not ingested (recorded in docs/LIMITATIONS.md).
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from docx import Document as _open_docx

from .models import Block, IngestResult


class IngestError(Exception):
    """Base class for ingest failures."""


class UnsupportedFormatError(IngestError):
    pass


class NoTextLayerError(IngestError):
    """The PDF has no extractable text (scanned without OCR)."""


def ingest(path: str | Path) -> IngestResult:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _ingest_pdf(path)
    if suffix == ".docx":
        return _ingest_docx(path)
    raise UnsupportedFormatError(
        f"Unsupported file type {suffix!r}; expected .pdf or .docx"
    )


def _ingest_pdf(path: Path) -> IngestResult:
    blocks: list[Block] = []
    index = 0
    with pymupdf.open(path) as doc:
        page_count = doc.page_count
        for page_number, page in enumerate(doc, start=1):
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:  # skip images
                    continue
                for line in block["lines"]:
                    text = "".join(span["text"] for span in line["spans"]).strip()
                    if not text:
                        continue
                    blocks.append(
                        Block(
                            text=text,
                            index=index,
                            page=page_number,
                            indent=line["bbox"][0],
                        )
                    )
                    index += 1
    if page_count > 0 and not blocks:
        raise NoTextLayerError(
            f"{path.name} has no extractable text layer. Scanned documents "
            "must be OCRed before ingest; OCR is out of scope here."
        )
    return IngestResult(path=str(path), kind="pdf", blocks=blocks, page_count=page_count)


def _ingest_docx(path: Path) -> IngestResult:
    blocks: list[Block] = []
    index = 0
    for paragraph in _open_docx(str(path)).paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        is_list_item, list_level = _docx_numbering(paragraph)
        indent = None
        left = paragraph.paragraph_format.left_indent
        if left is not None:
            indent = left.pt
        blocks.append(
            Block(
                text=text,
                index=index,
                indent=indent,
                is_list_item=is_list_item,
                list_level=list_level,
            )
        )
        index += 1
    return IngestResult(path=str(path), kind="docx", blocks=blocks, page_count=None)


def _docx_numbering(paragraph) -> tuple[bool, int | None]:
    # Numbering can sit on the paragraph directly or come from its style.
    for element in (paragraph._p, getattr(paragraph.style, "element", None)):
        if element is None:
            continue
        if element.xpath(".//w:pPr/w:numPr") or element.xpath("./w:pPr/w:numPr"):
            ilvl = element.xpath(".//w:pPr/w:numPr/w:ilvl/@w:val")
            return True, int(ilvl[0]) if ilvl else 0
    return False, None
