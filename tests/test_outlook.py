"""Calendar sync, exercised against a mock transport.

What these pin down: stated dates parse only against the explicit format
list (everything else is skipped with a reason, never guessed), relative
and needs-review records are reported rather than calendared, the
deadline key is stable across runs and blind to description rewording,
and the reconcile loop is idempotent — second sync is a no-op, a changed
record patches, a vanished record deletes, and a hand-made event in the
same calendar is left alone.
"""

import datetime as dt
import json

import httpx
import pytest

from deadline_agent.graph import GraphClient, GraphConfig, GraphError
from deadline_agent.outlook import (
    CALENDAR_NAME,
    SYNC_PROP,
    deadline_key,
    parse_date_text,
    plan_events,
    sync,
)

CONFIG = GraphConfig(
    tenant_id="tenant-guid",
    client_id="client-guid",
    client_secret="secret",
    site_url="https://contoso.sharepoint.com/sites/Demos",
)
USER = "pat@contoso.com"


def row(**over) -> dict:
    base = {
        "status": "approved",
        "obligation_type": "other",
        "description": "The Contractor must achieve Final Completion.",
        "obligor": "The Contractor",
        "deadline_kind": "absolute",
        "trigger": None,
        "date_text": "December 31, 2026",
        "quote": "no later than December 31, 2026.",
        "source_clause": "5.2",
        "source_path": "ARTICLE 5 > 5.2",
    }
    return base | over

def payload(*rows) -> dict:
    return {
        "contract": {"project_name": "Maple Street Parking Structure"},
        "records": list(rows),
    }


# -- date parsing ----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "December 31, 2026",
        "Dec 31, 2026",
        "31 December 2026",
        "12/31/2026",
        "2026-12-31",
        "December 31st, 2026",  # ordinal stripped: transcription, not guessing
        "  December  31,  2026 ",
    ],
)
def test_parse_date_text_recognized_formats(text):
    assert parse_date_text(text) == dt.date(2026, 12, 31)


@pytest.mark.parametrize(
    "text",
    [
        "within thirty (30) days",
        "the date of Substantial Completion",
        "Q1 2027",
        "December 2026",  # month alone is not a deadline date
        "",
    ],
)
def test_parse_date_text_refuses_everything_else(text):
    assert parse_date_text(text) is None


# -- planning --------------------------------------------------------------


def test_plan_skips_with_reasons_and_plans_the_rest():
    plans, skipped = plan_events(
        payload(
            row(),
            row(status="needs_review", description="Review me."),
            row(deadline_kind="relative", date_text=None,
                trigger="receipt of notice", description="Relative one."),
            row(date_text="the Substantial Completion date",
                description="Vague one."),
        ),
        source="sample_contract",
    )
    assert [p.description for p in plans] == [
        "The Contractor must achieve Final Completion."
    ]
    reasons = {s["description"]: s["reason"] for s in skipped}
    assert "needs review" in reasons["Review me."]
    assert "trigger" in reasons["Relative one."]
    assert "'the Substantial Completion date'" in reasons["Vague one."]


def test_planned_event_is_all_day_with_reminder():
    [plan], _ = plan_events(payload(row()), "sample_contract")
    event = plan.payload
    assert event["isAllDay"] is True
    assert event["start"] == {"dateTime": "2026-12-31T00:00:00",
                              "timeZone": "UTC"}
    assert event["end"]["dateTime"].startswith("2027-01-01")
    assert event["reminderMinutesBeforeStart"] == 7 * 24 * 60
    assert "Maple Street" in event["body"]["content"]
    assert "overwritten on the next sync" in event["body"]["content"]


def test_list_row_event_links_the_contract_file():
    [plan], _ = plan_events(
        payload(row(source_file="https://contoso.sharepoint.com/c.pdf")),
        "sharepoint-list")
    assert ("Contract file: https://contoso.sharepoint.com/c.pdf"
            in plan.payload["body"]["content"])


def test_deadline_key_ignores_description_wording():
    assert deadline_key(row()) == deadline_key(row(description="Reworded."))
    assert deadline_key(row()) != deadline_key(row(source_clause="9.9"))


# -- relative deadlines with a recorded trigger date -----------------------


def rel_row(**over) -> dict:
    base = row(
        deadline_kind="relative", date_text=None,
        description="Either party must initiate a Claim by written notice.",
        trigger="the event giving rise to the Claim",
        duration_value=21, duration_unit="days", calendar="calendar",
        trigger_date="August 19, 2026",
    )
    return base | over


def test_recorded_trigger_computes_the_due_date():
    [plan], skipped = plan_events(payload(rel_row()), "sharepoint-list")
    assert not skipped
    assert plan.payload["start"]["dateTime"] == "2026-09-09T00:00:00"
    body = plan.payload["body"]["content"]
    assert "Trigger date (recorded in the deadlines list): 2026-08-19" in body
    assert "2026-08-19 + 21 calendar days = 2026-09-09" in body


def test_week_durations_compute_and_floats_from_graph_are_fine():
    # Graph number columns come back as floats.
    [plan], _ = plan_events(
        payload(rel_row(duration_value=2.0, duration_unit="weeks")),
        "sharepoint-list")
    assert plan.payload["start"]["dateTime"] == "2026-09-02T00:00:00"


def test_unspecified_basis_computes_with_stated_assumption():
    [plan], _ = plan_events(
        payload(rel_row(calendar="unspecified")), "sharepoint-list")
    assert "earliest the deadline could fall" in plan.payload["body"]["content"]


@pytest.mark.parametrize(
    ("over", "reason_match"),
    [
        ({"trigger_date": None}, "record the trigger date"),
        ({"trigger_date": "when notice arrives"}, "not in a recognized format"),
        ({"calendar": "business"}, "holiday calendar"),
        ({"duration_unit": "months"}, "only day and week arithmetic"),
        ({"duration_unit": "hours", "duration_value": 24},
         "only day and week arithmetic"),
    ],
)
def test_relative_refusal_boundaries(over, reason_match):
    plans, [skip] = plan_events(payload(rel_row(**over)), "sharepoint-list")
    assert not plans
    assert reason_match in skip["reason"]


def test_changed_trigger_date_patches_the_event(client, fake):
    sync(client, USER, payload(rel_row()), "sharepoint-list")
    report = sync(client, USER,
                  payload(rel_row(trigger_date="August 25, 2026")),
                  "sharepoint-list")
    assert len(report.updated) == 1 and not report.created and not report.removed
    [event] = fake.events.values()
    assert event["start"]["dateTime"] == "2026-09-15T00:00:00"


# -- reconcile loop --------------------------------------------------------


class FakeOutlook:
    """Programmable mock transport recording calendar traffic."""

    def __init__(self):
        self.calendars: list[dict] = []
        self.events: dict[str, dict] = {}
        self.patched: list[str] = []
        self._next_id = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        url, method = str(request.url), request.method
        if "login.microsoftonline.com" in url:
            return httpx.Response(200, json={"access_token": "tok",
                                             "expires_in": 3600})
        if url.endswith("$top=100") and "/calendars?" in url:
            return httpx.Response(200, json={"value": self.calendars})
        if url.endswith("/calendars") and method == "POST":
            cal = {"id": "cal-1", **json.loads(request.content)}
            self.calendars.append(cal)
            return httpx.Response(201, json=cal)
        if "/calendars/cal-1/events" in url and method == "GET":
            return httpx.Response(
                200, json={"value": list(self.events.values())})
        if "/calendars/cal-1/events" in url and method == "POST":
            self._next_id += 1
            event = {"id": f"ev-{self._next_id}", **json.loads(request.content)}
            self.events[event["id"]] = event
            return httpx.Response(201, json=event)
        if "/events/" in url and method == "PATCH":
            event_id = url.rsplit("/", 1)[1]
            self.events[event_id] |= json.loads(request.content)
            self.patched.append(event_id)
            return httpx.Response(200, json=self.events[event_id])
        if "/events/" in url and method == "DELETE":
            del self.events[url.rsplit("/", 1)[1]]
            return httpx.Response(204)
        return httpx.Response(404, json={"error": f"unhandled {method} {url}"})


@pytest.fixture
def fake():
    return FakeOutlook()


@pytest.fixture
def client(fake):
    return GraphClient(
        CONFIG, http=httpx.Client(transport=httpx.MockTransport(fake.handler))
    )


def test_first_sync_creates_calendar_and_events(client, fake):
    report = sync(client, USER, payload(row()), "sample_contract")
    assert [c["name"] for c in fake.calendars] == [CALENDAR_NAME]
    assert len(report.created) == 1 and not report.updated
    [event] = fake.events.values()
    [prop] = event["singleValueExtendedProperties"]
    assert prop["id"] == SYNC_PROP
    assert prop["value"].startswith(f"sample_contract|{deadline_key(row())}|")


def test_second_sync_is_a_noop(client, fake):
    sync(client, USER, payload(row()), "sample_contract")
    report = sync(client, USER, payload(row()), "sample_contract")
    assert not report.created and not report.updated and not report.removed
    assert not fake.patched


def test_changed_record_patches_in_place(client, fake):
    sync(client, USER, payload(row()), "sample_contract")
    report = sync(client, USER,
                  payload(row(description="Reworded description.")),
                  "sample_contract")
    assert report.updated == ["Reworded description."]
    assert not report.created and not report.removed  # same key, new content
    assert len(fake.events) == 1 and fake.patched


def test_vanished_record_deletes_its_event(client, fake):
    sync(client, USER, payload(row(), row(source_clause="7.1",
                                          date_text="March 1, 2027")),
         "sample_contract")
    assert len(fake.events) == 2
    report = sync(client, USER, payload(row()), "sample_contract")
    assert len(report.removed) == 1
    assert len(fake.events) == 1


def test_foreign_and_hand_made_events_are_untouched(client, fake):
    fake.events["ev-hand"] = {"id": "ev-hand", "subject": "Lunch"}
    fake.events["ev-other"] = {
        "id": "ev-other", "subject": "Other contract",
        "singleValueExtendedProperties": [
            {"id": SYNC_PROP, "value": "other_contract|abc123|def456"}],
    }
    sync(client, USER, payload(row()), "sample_contract")
    assert "ev-hand" in fake.events and "ev-other" in fake.events


def test_denied_explains_calendar_permission_not_site_grant():
    def deny(request):
        if "login" in str(request.url):
            return httpx.Response(200, json={"access_token": "tok",
                                             "expires_in": 60})
        return httpx.Response(403, json={"error": "accessDenied"})

    client = GraphClient(
        CONFIG, http=httpx.Client(transport=httpx.MockTransport(deny))
    )
    client._DENIED_RETRY_DELAYS = ()
    with pytest.raises(GraphError, match="Calendars.ReadWrite"):
        sync(client, USER, payload(row()), "sample_contract")


def test_missing_calendar_user_env(monkeypatch):
    from deadline_agent.outlook import calendar_user_from_env

    monkeypatch.delenv("GRAPH_CALENDAR_USER", raising=False)
    with pytest.raises(GraphError, match="GRAPH_CALENDAR_USER"):
        calendar_user_from_env()
