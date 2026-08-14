"""CLI: dump segmented clauses from a contract as JSON, for inspection."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from .ingest import IngestError, ingest
from .segment import segment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="deadline-agent",
        description="Ingest a contract (PDF/DOCX) and print its clauses as JSON.",
    )
    parser.add_argument("path", help="contract file (.pdf or .docx)")
    parser.add_argument(
        "--candidates",
        action="store_true",
        help="also run the deadline prefilter and mark candidate clauses",
    )
    args = parser.parse_args(argv)

    try:
        result = ingest(args.path)
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    clauses = segment(result.blocks)
    signals_by_id = {}
    if args.candidates:
        from .classify import find_candidates

        signals_by_id = {id(c.clause): c.signals for c in find_candidates(clauses)}
    payload = {
        "source": result.path,
        "kind": result.kind,
        "page_count": result.page_count,
        "clause_count": len(clauses),
        "clauses": [
            {k: v for k, v in dataclasses.asdict(c).items() if k != "block_indexes"}
            | ({"deadline_signals": signals_by_id.get(id(c))} if args.candidates else {})
            for c in clauses
        ],
    }
    if args.candidates:
        payload["candidate_count"] = len(signals_by_id)
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False, default=list)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
