"""Graph integration, exercised entirely against a mock transport.

No network, no tenant. What these pin down: the token is fetched once and
cached, the list schema mirrors the writer fields and schema enums, the
provisioning is idempotent, the writer's field payloads match the flatten
convention, and a 403 explains the Sites.Selected grant instead of leaking
a raw Graph error.
"""

import json

import httpx
import pytest

from deadline_agent.graph import (
    GraphClient,
    GraphConfig,
    GraphError,
    SharePointWriter,
    ensure_list,
    list_columns,
)
from deadline_agent.review import triage
from deadline_agent.schema import ObligationType
from deadline_agent.writers import FIELDS

from test_review import record

CONFIG = GraphConfig(
    tenant_id="tenant-guid",
    client_id="client-guid",
    client_secret="secret",
    site_url="https://contoso.sharepoint.com/sites/Demos",
)

SITE_ID = "contoso.sharepoint.com,aaa,bbb"


class FakeGraph:
    """Programmable mock transport recording every request."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.token_calls = 0
        self.lists: list[dict] = []
        self.columns: list[dict] = []
        self.items: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if "login.microsoftonline.com" in url:
            self.token_calls += 1
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok"
        if url.endswith("/sites/contoso.sharepoint.com:/sites/Demos"):
            return httpx.Response(200, json={"id": SITE_ID})
        if url.endswith("/lists") and request.method == "POST":
            body = json.loads(request.content)
            created = {"id": "list-1", "displayName": body["displayName"],
                       "webUrl": "https://contoso.sharepoint.com/x"}
            self.lists.append(body)
            return httpx.Response(201, json=created)
        if "$select" in url and "/lists" in url:
            return httpx.Response(200, json={"value": self.lists})
        if url.endswith("/columns") and request.method == "GET":
            return httpx.Response(200, json={"value": self.columns})
        if url.endswith("/columns") and request.method == "POST":
            self.columns.append(json.loads(request.content))
            return httpx.Response(201, json={})
        if url.endswith("/items") and request.method == "POST":
            self.items.append(json.loads(request.content))
            return httpx.Response(201, json={})
        if url.endswith("/drive") and request.method == "GET":
            return httpx.Response(200, json={"id": "drive-1"})
        if "/drives/drive-1/root:" in url and request.method == "PUT":
            self.uploaded = request.content
            return httpx.Response(
                201, json={"webUrl": "https://contoso.sharepoint.com/c.pdf"}
            )
        return httpx.Response(404, json={"error": "unhandled"})


@pytest.fixture
def fake():
    return FakeGraph()


@pytest.fixture
def client(fake):
    http = httpx.Client(transport=httpx.MockTransport(fake.handler))
    return GraphClient(CONFIG, http=http)


def test_token_fetched_once_and_cached(client, fake):
    client.site_id()
    client.site_id()
    assert fake.token_calls == 1


def test_site_resolution_uses_hostname_colon_path(client):
    assert client.site_id() == SITE_ID


def test_schema_mirrors_writer_fields_and_enums():
    names = {c["name"] for c in list_columns()}
    # every writer field except description (which lands in Title) has a column
    assert set(FIELDS) - {"description"} <= names
    types = next(c for c in list_columns() if c["name"] == "obligation_type")
    assert set(types["choice"]["choices"]) == {t.value for t in ObligationType}
    # date_text is a text column by design, never a Date column
    assert "text" in next(c for c in list_columns() if c["name"] == "date_text")


def test_ensure_list_creates_with_full_schema(client, fake):
    ensure_list(client, SITE_ID)
    [created] = fake.lists
    assert created["displayName"] == "Contract Deadlines"
    assert {c["name"] for c in created["columns"]} == {
        c["name"] for c in list_columns()
    }


def test_ensure_list_adds_only_missing_columns(client, fake):
    fake.lists = [{"id": "list-1", "displayName": "Contract Deadlines"}]
    fake.columns = [{"name": c["name"]} for c in list_columns()[:-2]]
    ensure_list(client, SITE_ID)
    added = {c["name"] for c in fake.columns} - {
        c["name"] for c in list_columns()[:-2]
    }
    assert added == {c["name"] for c in list_columns()[-2:]}


def test_writer_posts_rows_with_flatten_convention(client, fake):
    result = triage([record(), record(confidence=0.5)])
    url = SharePointWriter(client, source_file="https://x/contract.pdf").write(result)
    assert url.startswith("https://")
    assert len(fake.items) == 2
    fields = fake.items[0]["fields"]
    assert fields["Title"]  # description lands in Title
    assert "description" not in fields
    assert json.loads(fields["confidence_signals"])["quote_verbatim"] is True
    assert fields["source_file"] == "https://x/contract.pdf"
    review = next(
        i["fields"] for i in fake.items if i["fields"]["status"] == "needs_review"
    )
    assert json.loads(review["review_reasons"])


def test_upload_returns_web_url_and_sends_bytes(client, fake, tmp_path):
    from deadline_agent.graph import upload_to_library

    pdf = tmp_path / "contract.pdf"
    pdf.write_bytes(b"%PDF-fake")
    url = upload_to_library(client, SITE_ID, pdf)
    assert url == "https://contoso.sharepoint.com/c.pdf"
    assert fake.uploaded == b"%PDF-fake"


def test_403_explains_the_site_grant():
    def deny(request):
        if "login" in str(request.url):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 60})
        return httpx.Response(403, json={"error": "accessDenied"})

    client = GraphClient(
        CONFIG, http=httpx.Client(transport=httpx.MockTransport(deny))
    )
    client._DENIED_RETRY_DELAYS = ()  # no propagation waits in tests
    with pytest.raises(GraphError, match="Sites.Selected"):
        client.site_id()


def test_missing_env_lists_all_gaps(monkeypatch):
    for key in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID",
                "GRAPH_CLIENT_SECRET", "GRAPH_SITE_URL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(GraphError, match="GRAPH_TENANT_ID.*GRAPH_SITE_URL"):
        GraphConfig.from_env()
