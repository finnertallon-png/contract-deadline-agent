"""Microsoft Graph integration: auth, list provisioning, SharePoint writer.

This is the deployment seam the writers module promised: anything that can
produce flattened rows can push them to a SharePoint list, and this module
does it through Graph with app-only credentials. Two decisions carried over
from docs/ARCHITECTURE.md:

- The app registration holds ``Sites.Selected`` only. It can reach nothing
  until an admin grants it a specific site, so a leaked credential's blast
  radius is one demo site, not the tenant.
- The list schema is derived from the writer's ``FIELDS`` and the schema
  enums at provisioning time, in code. The list and the pipeline cannot
  drift apart on a column name or a choice value, because there is exactly
  one definition of both.

Column internal names are the snake_case field names from writers.FIELDS —
created that way on purpose so the writer's row dicts map to Graph
``fields`` payloads without a translation table. ``description`` lands in
the built-in Title column.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from .review import TriageResult
from .schema import CalendarBasis, DurationUnit, ObligationType
from .writers import FIELDS, _rows

GRAPH = "https://graph.microsoft.com/v1.0"
LIST_NAME = "Contract Deadlines"
LIBRARY_NAME = "Contracts"


class GraphError(RuntimeError):
    pass


@dataclass
class GraphConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    site_url: str

    @classmethod
    def from_env(cls) -> "GraphConfig":
        missing = [
            k
            for k in (
                "GRAPH_TENANT_ID",
                "GRAPH_CLIENT_ID",
                "GRAPH_CLIENT_SECRET",
                "GRAPH_SITE_URL",
            )
            if not os.environ.get(k)
        ]
        if missing:
            raise GraphError(
                f"missing environment variables: {', '.join(missing)} "
                "(set them in .env — see README)"
            )
        return cls(
            tenant_id=os.environ["GRAPH_TENANT_ID"],
            client_id=os.environ["GRAPH_CLIENT_ID"],
            client_secret=os.environ["GRAPH_CLIENT_SECRET"],
            site_url=os.environ["GRAPH_SITE_URL"],
        )


class GraphClient:
    """Minimal app-only Graph client: client-credentials token + requests.

    Deliberately not MSAL — one token endpoint call and an expiry check is
    all the flow needs, and a dependency-free client is easier to audit.
    """

    def __init__(self, config: GraphConfig, http: httpx.Client | None = None):
        self.config = config
        self._http = http or httpx.Client(timeout=30.0)
        self._token: str | None = None
        self._token_expiry = 0.0

    # -- auth --------------------------------------------------------------

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        resp = self._http.post(
            f"https://login.microsoftonline.com/{self.config.tenant_id}"
            "/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        if resp.status_code != 200:
            raise GraphError(f"token request failed ({resp.status_code}): {resp.text}")
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + int(payload.get("expires_in", 3600))
        return self._token

    # 401/403 retry schedule (seconds). A freshly made Sites.Selected grant
    # propagates unevenly across SharePoint frontends for a few minutes, so
    # the same call can flip between 200 and 403 — observed live, not
    # hypothesized. A truly ungranted app just spends the schedule and then
    # gets the explanatory error.
    _DENIED_RETRY_DELAYS = (3, 6, 12, 24)

    def request(
        self,
        method: str,
        path: str,
        headers: dict | None = None,
        denied_hint: str | None = None,
        **kwargs,
    ) -> httpx.Response:
        url = path if path.startswith("http") else f"{GRAPH}{path}"
        for attempt, delay in enumerate((*self._DENIED_RETRY_DELAYS, None)):
            resp = self._http.request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {self._access_token()}",
                    **(headers or {}),
                },
                **kwargs,
            )
            if resp.status_code not in (401, 403):
                break
            if delay is not None:
                time.sleep(delay)
        if resp.status_code in (401, 403):
            # Sites.Selected with no grant surfaces as 401 (spException) or
            # 403 depending on the endpoint; Graph deliberately won't even
            # confirm an ungranted site exists. Callers hitting a different
            # permission boundary (the calendar sync) pass their own hint.
            raise GraphError(
                denied_hint
                or f"{resp.status_code} from Graph — the app has "
                "Sites.Selected but has not been granted access to this "
                "site (see scripts/grant_site_access.md for the one-time "
                "admin grant), or GRAPH_SITE_URL points at a site that "
                "does not exist."
            )
        if resp.status_code >= 400:
            raise GraphError(f"{method} {path} failed ({resp.status_code}): {resp.text}")
        return resp

    def get(self, path: str, **kw) -> dict:
        return self.request("GET", path, **kw).json()

    def post(self, path: str, body: dict, **kw) -> dict:
        return self.request("POST", path, json=body, **kw).json()

    # -- site --------------------------------------------------------------

    def site_id(self) -> str:
        """Resolve the configured site URL to a Graph site id."""
        parsed = urlparse(self.config.site_url)
        path = parsed.path.rstrip("/")
        return self.get(f"/sites/{parsed.hostname}:{path}")["id"]


# -- list schema -----------------------------------------------------------


def _choice(name: str, values: list[str]) -> dict:
    return {
        "name": name,
        "choice": {"choices": values, "displayAs": "dropDownMenu"},
    }


def _text(name: str, multiline: bool = False) -> dict:
    col: dict = {"name": name, "text": {}}
    if multiline:
        col["text"] = {"allowMultipleLines": True, "textType": "plain"}
    return col


def _number(name: str, decimals: str = "automatic") -> dict:
    return {"name": name, "number": {"decimalPlaces": decimals}}


def list_columns() -> list[dict]:
    """Column definitions mirroring writers.FIELDS (description → Title)."""
    return [
        _choice("status", ["approved", "needs_review"]),
        _text("review_reasons", multiline=True),
        _choice("obligation_type", [t.value for t in ObligationType]),
        _text("obligor"),
        _choice("deadline_kind", ["relative", "absolute"]),
        _text("trigger", multiline=True),
        _number("duration_value", decimals="none"),
        _choice("duration_unit", [u.value for u in DurationUnit]),
        _choice("calendar", [c.value for c in CalendarBasis]),
        # Text on purpose, not a Date column: the pipeline records absolute
        # deadlines as the clause states them and never computes a calendar
        # date. Converting is a human decision at calendaring time.
        _text("date_text"),
        # Not a pipeline output: a person (often via the review chatbot)
        # records when a relative deadline's trigger event occurred. The
        # calendar sync computes the due date from it. Text like date_text —
        # parsed strictly at sync time, unparseable values reported.
        _text("trigger_date"),
        _text("quote", multiline=True),
        _text("source_clause"),
        _text("source_path"),
        _number("source_page", decimals="none"),
        _number("confidence"),
        _text("confidence_signals", multiline=True),
        _text("source_file"),
    ]


def ensure_list(client: GraphClient, site_id: str) -> dict:
    """Create the deadline list if absent; add any missing columns if not.

    Idempotent so provisioning can be re-run after schema additions.
    Returns the list resource.
    """
    lists = client.get(
        f"/sites/{site_id}/lists?$select=id,displayName,webUrl"
    )["value"]
    existing = next((x for x in lists if x["displayName"] == LIST_NAME), None)
    if existing is None:
        return client.post(
            f"/sites/{site_id}/lists",
            {
                "displayName": LIST_NAME,
                "list": {"template": "genericList"},
                "columns": list_columns(),
            },
        )
    have = {
        c["name"]
        for c in client.get(f"/sites/{site_id}/lists/{existing['id']}/columns")["value"]
    }
    for col in list_columns():
        if col["name"] not in have:
            client.post(f"/sites/{site_id}/lists/{existing['id']}/columns", col)
    return existing


def ensure_library(client: GraphClient, site_id: str) -> dict:
    """Create the contract inbox document library if absent."""
    lists = client.get(
        f"/sites/{site_id}/lists?$select=id,displayName,list"
    )["value"]
    existing = next((x for x in lists if x["displayName"] == LIBRARY_NAME), None)
    if existing is not None:
        return existing
    return client.post(
        f"/sites/{site_id}/lists",
        {"displayName": LIBRARY_NAME, "list": {"template": "documentLibrary"}},
    )


def upload_to_library(client: GraphClient, site_id: str, path) -> str:
    """Upload a file into the contract library; returns its web URL.

    Simple PUT — contracts are single-digit megabytes, far below the size
    where Graph requires an upload session.
    """
    library = ensure_library(client, site_id)
    drive = client.get(f"/sites/{site_id}/lists/{library['id']}/drive")
    item = client.request(
        "PUT",
        f"/drives/{drive['id']}/root:/{path.name}:/content",
        content=path.read_bytes(),
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    return item["webUrl"]


# -- reader ----------------------------------------------------------------


def read_list_rows(client: GraphClient, site_id: str) -> list[dict]:
    """Current rows of the deadlines list, shaped like writer rows.

    The read half of the SharePointWriter convention: internal column
    names are the writer FIELDS, description comes back out of Title.
    This is what makes the list the system of record for the calendar
    sync — a status flipped to approved in the list (by a person or by
    the review chatbot) is picked up here, no re-extraction involved.
    """
    lists = client.get(f"/sites/{site_id}/lists?$select=id,displayName")["value"]
    target = next((x for x in lists if x["displayName"] == LIST_NAME), None)
    if target is None:
        raise GraphError(
            f"list '{LIST_NAME}' not found on the configured site — "
            "run scripts/provision_list.py first"
        )
    rows = []
    url = f"/sites/{site_id}/lists/{target['id']}/items?$expand=fields&$top=200"
    while url:
        page = client.get(url)
        for item in page["value"]:
            fields = item.get("fields", {})
            row = {k: fields.get(k) for k in FIELDS if k != "description"}
            row["description"] = fields.get("Title")
            row["source_file"] = fields.get("source_file")
            row["trigger_date"] = fields.get("trigger_date")
            rows.append(row)
        url = page.get("@odata.nextLink")
    return rows


# -- writer ----------------------------------------------------------------


class SharePointWriter:
    """Writer implementation that posts triaged rows as list items.

    Same contract as JsonWriter/CsvWriter: approved and needs-review rows
    written together, never silently split. ``source_file`` (a link back to
    the contract in the library) is per-run context the flat rows don't
    carry, so it is set on the writer, not smuggled into the records.
    """

    def __init__(self, client: GraphClient, source_file: str | None = None):
        self._client = client
        self.source_file = source_file

    def write(self, result: TriageResult, contract: dict | None = None) -> str:
        site_id = self._client.site_id()
        target = ensure_list(self._client, site_id)
        list_path = f"/sites/{site_id}/lists/{target['id']}"
        for row in _rows(result):
            fields = {
                "Title": row["description"],
                **{
                    k: v
                    for k, v in row.items()
                    if k != "description" and v not in (None, [])
                },
            }
            # List- and dict-valued fields land as JSON in text columns,
            # same convention as CsvWriter cells.
            for key in ("review_reasons", "confidence_signals"):
                if key in fields:
                    fields[key] = json.dumps(fields[key], ensure_ascii=False)
            if self.source_file:
                fields["source_file"] = self.source_file
            self._client.post(f"{list_path}/items", {"fields": fields})
        return target.get("webUrl", LIST_NAME)
