"""Outlook calendar sync: put approved absolute deadlines on a calendar.

This is where the "calendaring is a human decision" boundary from
docs/LIMITATIONS.md gets crossed — deliberately, in one auditable place.
The pipeline stores absolute deadlines as the clause states them
(``date_text``, verbatim); this module parses that text against a fixed
list of explicit date formats at sync time. Anything the list does not
match is *skipped and reported*, never guessed. Relative deadlines are
skipped too: their clock starts at a trigger event the record cannot
date. Both show up in the sync report, so what did not reach the
calendar is as visible as what did.

Idempotency: every synced event carries a single-value extended property
``source|key|content-hash``. The key hashes the record's identifying
fields (clause, quote, stated date), the content hash covers the rendered
event. A re-run compares desired against existing per source contract:
unchanged events are untouched, changed ones are patched, events whose
record disappeared are deleted. Running the sync twice is a no-op.

Permission note (the reason scripts/grant_calendar_access.md exists):
application-permission ``Calendars.ReadWrite`` is tenant-wide by default —
there is no ``Sites.Selected`` equivalent for calendars. The deployment
answer is an Exchange ApplicationAccessPolicy restricting the app to the
mailboxes it serves; the sync itself only ever touches the single mailbox
named by ``GRAPH_CALENDAR_USER``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from dataclasses import dataclass, field

from .graph import GraphClient, GraphError

CALENDAR_NAME = "Contract Deadlines"
CATEGORY = "Contract Deadline"
REMINDER_MINUTES = 7 * 24 * 60  # a week out — deadline work, not meetings

# Fixed GUID so every run reads and writes the same property. MAPI named
# property, invisible in Outlook's UI, survives event edits.
SYNC_PROP = "String {b7d1a9f2-3c64-4e8a-9b57-2f0d8c41e6a3} Name deadlineAgentSync"

DENIED_HINT = (
    "401/403 from Graph for the calendar mailbox — the app needs the "
    "Calendars.ReadWrite application permission with admin consent, and "
    "the mailbox must be inside the app's ApplicationAccessPolicy scope "
    "(see scripts/grant_calendar_access.md)."
)

# Explicit formats only. A stated date outside this list is reported as
# skipped rather than fuzzily parsed — a wrong date on a lawyer's calendar
# is worse than a gap they can see.
_DATE_FORMATS = (
    "%B %d, %Y",   # December 31, 2026
    "%b %d, %Y",   # Dec 31, 2026
    "%d %B %Y",    # 31 December 2026
    "%d %b %Y",    # 31 Dec 2026
    "%m/%d/%Y",    # 12/31/2026
    "%Y-%m-%d",    # 2026-12-31
)

_ORDINAL = re.compile(r"(\d{1,2})(st|nd|rd|th)\b")


def parse_date_text(text: str) -> dt.date | None:
    """Parse a verbatim stated date; None for anything not clearly a date."""
    cleaned = _ORDINAL.sub(r"\1", " ".join(text.split())).strip(" .")
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def calendar_user_from_env() -> str:
    user = os.environ.get("GRAPH_CALENDAR_USER")
    if not user:
        raise GraphError(
            "missing environment variable: GRAPH_CALENDAR_USER "
            "(the mailbox whose calendar receives deadlines — set it in .env)"
        )
    return user


def deadline_key(row: dict) -> str:
    """Stable identity of one deadline record across sync runs.

    Keyed on the verbatim fields (clause number, quote, stated date), not
    the model-written description — extraction wording can drift between
    runs; the contract text does not.
    """
    basis = "\x00".join(
        str(row.get(k) or "") for k in ("source_clause", "quote", "date_text")
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


@dataclass
class EventPlan:
    key: str
    content_hash: str
    payload: dict  # Graph event body, without the sync property
    description: str


@dataclass
class SyncReport:
    user: str
    calendar: str = CALENDAR_NAME
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # {description, reason}

    def summary(self) -> dict:
        return {
            "user": self.user,
            "calendar": self.calendar,
            "created": len(self.created),
            "updated": len(self.updated),
            "removed": len(self.removed),
            "skipped": self.skipped,
        }


def _event_body(row: dict, contract: dict | None, source: str) -> str:
    lines = []
    if contract and contract.get("project_name"):
        lines.append(f"Contract: {contract['project_name']}")
    lines += [
        f"Obligation type: {row.get('obligation_type')}",
        f"Obligor: {row.get('obligor') or 'not stated'}",
        f"Clause: {row.get('source_path') or row.get('source_clause')}",
        f"Deadline as stated: \"{row.get('date_text')}\"",
        "",
        f"\"{row.get('quote')}\"",
        "",
        f"Synced by contract-deadline-agent from {source}. "
        "Do not edit this event — edits are overwritten on the next sync.",
    ]
    return "\n".join(lines)


def _event_payload(row: dict, date: dt.date, contract: dict | None,
                   source: str) -> dict:
    # All-day events, UTC midnight to midnight: contracts state dates,
    # not times, and an all-day banner renders the same in any timezone.
    return {
        "subject": row["description"],
        "body": {"contentType": "text",
                 "content": _event_body(row, contract, source)},
        "start": {"dateTime": f"{date.isoformat()}T00:00:00",
                  "timeZone": "UTC"},
        "end": {"dateTime": f"{(date + dt.timedelta(days=1)).isoformat()}"
                            "T00:00:00",
                "timeZone": "UTC"},
        "isAllDay": True,
        "isReminderOn": True,
        "reminderMinutesBeforeStart": REMINDER_MINUTES,
        "categories": [CATEGORY],
    }


def plan_events(payload: dict, source: str) -> tuple[list[EventPlan], list[dict]]:
    """Decide which records become events; report every one that does not."""
    plans: list[EventPlan] = []
    skipped: list[dict] = []
    contract = payload.get("contract")

    def skip(row, reason):
        skipped.append({"description": row["description"], "reason": reason})

    for row in payload["records"]:
        if row.get("status") != "approved":
            skip(row, "needs review — approve before calendaring")
        elif row.get("deadline_kind") != "absolute":
            skip(row, "relative deadline — the clock starts at a trigger "
                      "event; calendaring it needs the trigger date")
        else:
            date = parse_date_text(row.get("date_text") or "")
            if date is None:
                skip(row, "stated date not in a recognized format: "
                          f"{row.get('date_text')!r}")
                continue
            event = _event_payload(row, date, contract, source)
            content_hash = hashlib.sha256(
                json.dumps(event, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            plans.append(EventPlan(deadline_key(row), content_hash, event,
                                   row["description"]))
    return plans, skipped


# -- Graph side ------------------------------------------------------------


def ensure_calendar(client: GraphClient, user: str) -> str:
    """Find or create the dedicated deadlines calendar; returns its id."""
    url = f"/users/{user}/calendars?$select=id,name&$top=100"
    while url:
        page = client.get(url, denied_hint=DENIED_HINT)
        for cal in page["value"]:
            if cal["name"] == CALENDAR_NAME:
                return cal["id"]
        url = page.get("@odata.nextLink")
    created = client.post(f"/users/{user}/calendars",
                          {"name": CALENDAR_NAME}, denied_hint=DENIED_HINT)
    return created["id"]


def existing_events(client: GraphClient, user: str, calendar_id: str,
                    source: str) -> dict[str, tuple[str, str, str]]:
    """Synced events for this source: key -> (event id, content hash, subject)."""
    out: dict[str, tuple[str, str, str]] = {}
    url = (f"/users/{user}/calendars/{calendar_id}/events"
           f"?$select=id,subject&$top=50"
           f"&$expand=singleValueExtendedProperties"
           f"($filter=id eq '{SYNC_PROP}')")
    while url:
        page = client.get(url, denied_hint=DENIED_HINT)
        for event in page["value"]:
            props = event.get("singleValueExtendedProperties") or []
            value = next((p["value"] for p in props if p["id"] == SYNC_PROP),
                         None)
            if not value:
                continue  # not ours (hand-made event in the calendar)
            parts = value.split("|")
            if len(parts) == 3 and parts[0] == source:
                out[parts[1]] = (event["id"], parts[2],
                                 event.get("subject", ""))
        url = page.get("@odata.nextLink")
    return out


def sync(client: GraphClient, user: str, payload: dict,
         source: str) -> SyncReport:
    """Reconcile the calendar with one contract's records. Idempotent."""
    plans, skipped = plan_events(payload, source)
    report = SyncReport(user=user, skipped=skipped)
    calendar_id = ensure_calendar(client, user)
    existing = existing_events(client, user, calendar_id, source)

    for plan in plans:
        marker = f"{source}|{plan.key}|{plan.content_hash}"
        body = {**plan.payload,
                "singleValueExtendedProperties": [
                    {"id": SYNC_PROP, "value": marker}]}
        if plan.key not in existing:
            client.post(f"/users/{user}/calendars/{calendar_id}/events",
                        body, denied_hint=DENIED_HINT)
            report.created.append(plan.description)
        elif existing[plan.key][1] != plan.content_hash:
            client.request("PATCH",
                           f"/users/{user}/events/{existing[plan.key][0]}",
                           json=body, denied_hint=DENIED_HINT)
            report.updated.append(plan.description)

    planned_keys = {p.key for p in plans}
    for key, (event_id, _, subject) in existing.items():
        if key not in planned_keys:
            client.request("DELETE", f"/users/{user}/events/{event_id}",
                           denied_hint=DENIED_HINT)
            report.removed.append(subject)
    return report
