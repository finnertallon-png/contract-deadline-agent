"""Segment: split ingested blocks into clauses along numbering markers.

Approach: rule-based, driven by the printed numbering markers ("ARTICLE 5",
"7.3", "(a)", "(iv)") rather than an ML model or fixed-size chunks. Contract
numbering is the one structural signal that is both reliable and cheap, and a
notice provision split across two chunks extracts wrong — so clause boundaries
have to be exact, which favors deterministic rules that can be unit-tested.

Hierarchy is rebuilt with a stack. Decimal markers ("7.3.1") describe their
own ancestry through their components. Non-decimal markers (letters, romans)
attach as siblings when they continue an open sequence at some stack level,
and as children of the current clause otherwise. Sequence continuation is
also how "(i)" is disambiguated: after "(h)" it is the letter i, otherwise it
is roman one.

Known gaps, deliberate for now: unnumbered ALL-CAPS headings are treated as
clause body text, exhibits/schedules restart numbering and will nest wrongly,
and a bare-integer line like "2021." can false-positive as a marker (guarded
by requiring it to be 1, continue an open sequence, or be followed by
heading-like text).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .models import Block, Clause

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
_ROMAN_CHARS = set(_ROMAN_VALUES)


class Kind(Enum):
    ARTICLE = "article"
    DECIMAL = "decimal"
    CAP_LETTER = "cap_letter"
    PAREN_LETTER = "paren_letter"
    PAREN_ROMAN = "paren_roman"
    PAREN_DIGIT = "paren_digit"


@dataclass
class Marker:
    kind: Kind
    value: str  # normalized: "7.3", "V", "a", "iv", "3"
    raw: str  # as printed: "7.3", "ARTICLE V", "(a)", "(iv)", "(3)"
    rest: str  # text on the same line after the marker


_ARTICLE_RE = re.compile(r"^ARTICLE\s+([IVXLCDM]+|\d+)\b\s*[.:—–-]?\s*(.*)$", re.IGNORECASE)
_SECTION_WORD_RE = re.compile(r"^(?:SECTION|Section|§)\s*(\d+(?:\.\d+)*)[.:]?\s+(.*)$")
_MULTI_DECIMAL_RE = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+(.*)$")
_SINGLE_DECIMAL_RE = re.compile(r"^(\d+)[.)]\s+(.*)$")
_PAREN_RE = re.compile(r"^\(([A-Za-z]+|\d+)\)\s*(.*)$")
_CAP_LETTER_RE = re.compile(r"^([A-Z])\.\s+(.*)$")

_STOPWORDS = {"a", "an", "and", "by", "for", "in", "of", "on", "or", "the", "to", "with"}


def _is_heading_like(s: str) -> bool:
    """Short, title-cased text: "Notice of Claims." yes, "The parties agree" no."""
    s = s.strip().rstrip(".")
    if not s or len(s) > 90 or not s[0].isupper():
        return False
    words = re.findall(r"[A-Za-z][\w'’-]*", s)
    if not words or len(words) > 10:
        return False
    significant = [w for w in words[1:] if w.lower() not in _STOPWORDS]
    if not significant:
        return True
    capitalized = sum(1 for w in significant if w[0].isupper())
    return capitalized / len(significant) >= 0.6


def parse_marker(text: str) -> Marker | None:
    """Parse a clause-numbering marker at the start of a line, if present.

    Parenthesized single letters that are also roman numerals ("(i)", "(v)",
    "(x)") come back as PAREN_ROMAN; the segmenter reclassifies them as
    letters when they continue an open letter sequence.
    """
    m = _ARTICLE_RE.match(text)
    if m:
        return Marker(Kind.ARTICLE, m.group(1).upper(), text[: m.end(1)], m.group(2))
    m = _SECTION_WORD_RE.match(text)
    if m:
        return Marker(Kind.DECIMAL, m.group(1), text[: m.end(1)], m.group(2))
    m = _MULTI_DECIMAL_RE.match(text)
    if m:
        return Marker(Kind.DECIMAL, m.group(1), m.group(1), m.group(2))
    m = _SINGLE_DECIMAL_RE.match(text)
    if m:
        return Marker(Kind.DECIMAL, m.group(1), text[: m.end(1) + 1], m.group(2))
    m = _PAREN_RE.match(text)
    if m:
        inner = m.group(1)
        raw = f"({inner})"
        if inner.isdigit():
            return Marker(Kind.PAREN_DIGIT, inner, raw, m.group(2))
        if inner.islower() and set(inner) <= _ROMAN_CHARS and (len(inner) > 1 or inner in ("i", "v", "x")):
            return Marker(Kind.PAREN_ROMAN, inner, raw, m.group(2))
        if len(inner) == 1:
            return Marker(Kind.PAREN_LETTER, inner.lower(), raw, m.group(2))
        return None
    m = _CAP_LETTER_RE.match(text)
    if m:
        return Marker(Kind.CAP_LETTER, m.group(1).lower(), m.group(1) + ".", m.group(2))
    return None


def _roman_to_int(s: str) -> int | None:
    total, prev = 0, 0
    for ch in reversed(s.lower()):
        v = _ROMAN_VALUES.get(ch)
        if v is None:
            return None
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


def _int_value(kind: Kind, value: str) -> int | None:
    """Ordinal position of a marker value within its own sequence type."""
    if kind == Kind.ARTICLE:
        return int(value) if value.isdigit() else _roman_to_int(value)
    if kind == Kind.PAREN_ROMAN:
        return _roman_to_int(value)
    if kind in (Kind.PAREN_LETTER, Kind.CAP_LETTER):
        return ord(value) - ord("a") + 1 if len(value) == 1 else None
    if kind == Kind.PAREN_DIGIT:
        return int(value)
    return None  # DECIMAL handled by components


def is_successor(prev: Marker, new: Marker) -> bool:
    """True if ``new`` directly continues ``prev`` in the same sequence."""
    if new.kind == Kind.DECIMAL:
        if prev.kind != Kind.DECIMAL:
            return False
        p, n = prev.value.split("."), new.value.split(".")
        return len(p) == len(n) and p[:-1] == n[:-1] and int(n[-1]) == int(p[-1]) + 1
    if prev.kind != new.kind:
        # letter sequences: "(h)" -> "(i)" arrives parsed as roman
        if prev.kind == Kind.PAREN_LETTER and new.kind == Kind.PAREN_ROMAN and len(new.value) == 1:
            return ord(new.value) == ord(prev.value) + 1
        return False
    p_val, n_val = _int_value(prev.kind, prev.value), _int_value(new.kind, new.value)
    return p_val is not None and n_val is not None and n_val == p_val + 1


@dataclass
class _Open:
    marker: Marker
    clause: Clause


def segment(blocks: list[Block]) -> list[Clause]:
    clauses: list[Clause] = []
    stack: list[_Open] = []
    current: Clause | None = None

    def start(marker: Marker, block: Block) -> None:
        nonlocal current
        path = tuple(o.marker.raw for o in stack) + (marker.raw,)
        heading, body = _split_heading(marker.rest)
        clause = Clause(
            number=marker.raw,
            heading=heading,
            text=body,
            level=len(stack),
            path=path,
            page_start=block.page,
            page_end=block.page,
            block_indexes=[block.index],
        )
        clauses.append(clause)
        stack.append(_Open(marker, clause))
        current = clause

    for block in blocks:
        marker = parse_marker(block.text)
        if marker is not None and not _accept(marker, stack):
            marker = None
        if marker is None:
            if current is None:
                current = Clause(
                    number=None, heading=None, text="", level=0, path=(),
                    page_start=block.page, page_end=block.page,
                )
                clauses.append(current)
            current.text = _append_text(current.text, block.text)
            current.page_end = block.page
            current.block_indexes.append(block.index)
            continue
        marker = _resolve_ambiguity(marker, stack)
        _pop_to_parent(marker, stack)
        start(marker, block)

    return clauses


def _accept(marker: Marker, stack: list[_Open]) -> bool:
    """Guard against sentence text that happens to look like a marker.

    Bare integers ("2021.") are the risky case: accept only 1, a sequence
    continuation, or a marker followed by heading-like text. Everything else
    is punctuated distinctively enough to accept outright.
    """
    if marker.kind != Kind.DECIMAL or "." in marker.value:
        return True
    if marker.value == "1":
        return True
    if any(is_successor(o.marker, marker) for o in stack):
        return True
    return _is_heading_like(marker.rest)


def _resolve_ambiguity(marker: Marker, stack: list[_Open]) -> Marker:
    """Reclassify "(i)"-style markers as letters when a letter sequence expects them."""
    if marker.kind == Kind.PAREN_ROMAN and len(marker.value) == 1:
        for open_ in reversed(stack):
            if open_.marker.kind == Kind.PAREN_LETTER and is_successor(open_.marker, marker):
                return Marker(Kind.PAREN_LETTER, marker.value, marker.raw, marker.rest)
            if open_.marker.kind == Kind.PAREN_ROMAN:
                break
    return marker


def _pop_to_parent(marker: Marker, stack: list[_Open]) -> None:
    """Pop the stack until the top is this marker's parent."""
    if marker.kind == Kind.ARTICLE:
        stack.clear()
        return
    if marker.kind == Kind.DECIMAL:
        # Ancestry is written into the components: keep an ARTICLE root plus
        # any open decimal that is a strict component-prefix of this one.
        components = marker.value.split(".")
        keep = 0
        for open_ in stack:
            if open_.marker.kind == Kind.ARTICLE and keep == 0:
                keep += 1
                continue
            if open_.marker.kind != Kind.DECIMAL:
                break
            oc = open_.marker.value.split(".")
            if len(oc) < len(components) and components[: len(oc)] == oc:
                keep += 1
            else:
                break
        del stack[keep:]
        return
    # Letters/romans/digits: sibling of the nearest open sequence they
    # continue, otherwise a child of the current clause.
    for depth in range(len(stack) - 1, -1, -1):
        if is_successor(stack[depth].marker, marker):
            del stack[depth:]
            return


def _split_heading(rest: str) -> tuple[str | None, str]:
    """Split "Notice of Claims. Contractor shall..." into heading and body.

    A heading is the leading sentence when it is short and title-like; if the
    whole line is short and title-like it is a heading with the body to
    follow in later blocks.
    """
    rest = rest.strip()
    if not rest:
        return None, ""
    if _is_heading_like(rest):
        return rest.rstrip("."), ""
    m = re.match(r"^([^.]{1,90})\.\s+(?=[A-Z(])", rest)
    if m and _is_heading_like(m.group(1)):
        return m.group(1), rest[m.end():]
    return None, rest


def _append_text(existing: str, addition: str) -> str:
    if not existing:
        return addition
    if existing.endswith("-") and addition[:1].islower():
        return existing[:-1] + addition
    return existing + " " + addition
