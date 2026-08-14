import csv
import json

from deadline_agent.review import triage
from deadline_agent.writers import FIELDS, CsvWriter, JsonWriter, flatten

from test_review import record
from deadline_agent.schema import AbsoluteDeadline, CalendarBasis


def triaged():
    return triage([
        record(),                                          # approved
        record(confidence=0.5),                            # review: low confidence
        record(deadline=AbsoluteDeadline(date_text="December 31, 2026")),  # approved
    ])


class TestFlatten:
    def test_relative_fields(self):
        row = flatten(record())
        assert row["deadline_kind"] == "relative"
        assert row["duration_value"] == 7 and row["duration_unit"] == "days"
        assert row["date_text"] is None
        assert row["source_path"] == "ARTICLE 4 > 4.2"
        assert list(row) == FIELDS

    def test_absolute_fields(self):
        row = flatten(record(deadline=AbsoluteDeadline(date_text="December 31, 2026")))
        assert row["deadline_kind"] == "absolute"
        assert row["date_text"] == "December 31, 2026"
        assert row["trigger"] is None

    def test_review_status(self):
        assert flatten(record())["status"] == "approved"
        row = flatten(record(), reasons=["confidence 0.50 below threshold 0.80"])
        assert row["status"] == "needs_review" and row["review_reasons"]


def test_json_writer_roundtrip(tmp_path):
    path = JsonWriter(tmp_path / "out.json").write(triaged())
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["approved_count"] == 2
    assert payload["needs_review_count"] == 1
    assert len(payload["records"]) == 3
    statuses = {r["status"] for r in payload["records"]}
    assert statuses == {"approved", "needs_review"}


def test_csv_writer_roundtrip(tmp_path):
    path = CsvWriter(tmp_path / "out.csv").write(triaged())
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert set(rows[0]) == set(FIELDS)
    review_rows = [r for r in rows if r["status"] == "needs_review"]
    assert len(review_rows) == 1
    # list/dict cells are JSON so a SharePoint import can parse them back
    assert json.loads(review_rows[0]["review_reasons"])
    assert json.loads(rows[0]["confidence_signals"])["quote_verbatim"] is True
