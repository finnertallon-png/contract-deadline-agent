"""Provision the SharePoint demo site: contract library + deadline list.

    python scripts/provision_list.py

Idempotent — safe to re-run; it creates what is missing and leaves what
exists. Requires GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET,
and GRAPH_SITE_URL in the environment or a .env in the working directory,
and requires that the app has been granted access to the site (one-time
admin step — see scripts/grant_site_access.md). A 403 here means that
grant has not happened yet.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from deadline_agent.cli import _load_dotenv  # noqa: E402
from deadline_agent.graph import (  # noqa: E402
    GraphClient,
    GraphConfig,
    GraphError,
    ensure_library,
    ensure_list,
)


def main() -> int:
    _load_dotenv()
    try:
        client = GraphClient(GraphConfig.from_env())
        site_id = client.site_id()
        print(f"site resolved: {site_id}")
        library = ensure_library(client, site_id)
        print(f"library ready: {library['displayName']}  {library.get('webUrl', '')}")
        deadlines = ensure_list(client, site_id)
        print(f"list ready:    {deadlines['displayName']}  {deadlines.get('webUrl', '')}")
    except GraphError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("\nProvisioned. Suggested manual finishing touch (Graph cannot "
          "create list views): add a 'Review queue' view filtered to "
          "status = needs_review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
