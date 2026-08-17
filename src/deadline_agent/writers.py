"""Write: deliver triaged deadline records to a destination.

The writer is a seam, not a single implementation. The deployment target is
a SharePoint list via the Graph API (with Power Automate reminders on top),
but that needs a tenant, an app registration, and admin consent — none of
which a demo or a test run should depend on. So the demo defaults are local:
JSON (full fidelity) and CSV (flat, shaped like the SharePoint list the
Graph writer will populate). The Graph writer lands when the permission
scope decision in docs/ARCHITECTURE.md is made; anything that can produce
these rows can push them to SharePoint.

Every row carries its review status and reasons — approved and
needs-review records are written together, never silently split.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Protocol

from .extract import DeadlineRecord
from .review import TriageResult
from .schema import AbsoluteDeadline, RelativeDeadline

FIELDS = [
    "status",
    "review_reasons",
    "obligation_type",
    "description",
    "obligor",
    "deadline_kind",
    "trigger",
    "duration_value",
    "duration_unit",
    "calendar",
    "date_text",
    "quote",
    "source_clause",
    "source_path",
    "source_page",
    "confidence",
    "confidence_signals",
]


def flatten(record: DeadlineRecord, reasons: list[str] | None = None) -> dict:
    """One record as a flat dict whose keys are FIELDS, in that order."""
    ob = record.obligation
    deadline = ob.deadline
    row = {
        "status": "needs_review" if reasons else "approved",
        "review_reasons": reasons or [],
        "obligation_type": ob.obligation_type.value,
        "description": ob.description,
        "obligor": ob.obligor,
        "deadline_kind": deadline.kind,
        "trigger": None,
        "duration_value": None,
        "duration_unit": None,
        "calendar": None,
        "date_text": None,
        "quote": ob.quote,
        "source_clause": record.source_clause,
        "source_path": " > ".join(record.source_path),
        "source_page": record.source_page,
        "confidence": record.confidence,
        "confidence_signals": record.confidence_signals,
    }
    if isinstance(deadline, RelativeDeadline):
        row.update(
            trigger=deadline.trigger,
            duration_value=deadline.duration_value,
            duration_unit=deadline.duration_unit.value,
            calendar=deadline.calendar.value,
        )
    elif isinstance(deadline, AbsoluteDeadline):
        row["date_text"] = deadline.date_text
    return row


def _rows(result: TriageResult) -> list[dict]:
    rows = [flatten(r) for r in result.approved]
    rows += [flatten(item.record, item.reasons) for item in result.needs_review]
    return rows


class Writer(Protocol):
    # Returns where the records landed: a local Path, or a URL for
    # destinations that aren't files (the SharePoint list's web address).
    def write(self, result: TriageResult, contract: dict | None = None) -> Path | str: ...


class JsonWriter:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def write(self, result: TriageResult, contract: dict | None = None) -> Path:
        payload = {
            "contract": contract,
            "threshold": result.threshold,
            "approved_count": len(result.approved),
            "needs_review_count": len(result.needs_review),
            "records": _rows(result),
        }
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return self.path


class CsvWriter:
    """Flat rows shaped like the target SharePoint list. List-valued and
    dict-valued fields are JSON-encoded in their cell. Contract metadata is
    not row data — it is carried by the JSON output only."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def write(self, result: TriageResult, contract: dict | None = None) -> Path:
        with self.path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for row in _rows(result):
                writer.writerow(
                    {
                        k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                        for k, v in row.items()
                    }
                )
        return self.path
