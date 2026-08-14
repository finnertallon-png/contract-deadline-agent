"""CLI: dump segmented clauses from a contract as JSON, for inspection."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

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
    parser.add_argument(
        "--extract",
        action="store_true",
        help="run the full pipeline (calls the Claude API; needs credentials)",
    )
    parser.add_argument(
        "--out",
        help="output file for --extract; .json or .csv (default: <input>.deadlines.json)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="review threshold for --extract (default: the provisional value in review.py)",
    )
    parser.add_argument("--model", default=None, help="model override for --extract")
    args = parser.parse_args(argv)

    try:
        result = ingest(args.path)
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    clauses = segment(result.blocks)
    if args.extract:
        return _run_extract(args, result, clauses)
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


def _run_extract(args, result, clauses) -> int:
    import anthropic

    from .extract import DEFAULT_MODEL, ClaudeExtractor, extract_deadlines
    from .review import DEFAULT_THRESHOLD, triage
    from .writers import CsvWriter, JsonWriter

    out = Path(args.out) if args.out else Path(args.path).with_suffix(".deadlines.json")
    writer = CsvWriter(out) if out.suffix.lower() == ".csv" else JsonWriter(out)

    extractor = ClaudeExtractor(model=args.model or DEFAULT_MODEL)
    try:
        records = extract_deadlines(clauses, extractor)
    except (anthropic.AuthenticationError, TypeError) as exc:
        # The SDK raises TypeError when no credential source resolves at all.
        if isinstance(exc, TypeError) and "authentication" not in str(exc).lower():
            raise
        print(
            "error: no valid Anthropic credentials. Set ANTHROPIC_API_KEY "
            "(or run `ant auth login`).",
            file=sys.stderr,
        )
        return 1
    except anthropic.APIError as exc:
        print(f"error: Claude API request failed: {exc}", file=sys.stderr)
        return 1

    triaged = triage(records, threshold=args.threshold or DEFAULT_THRESHOLD)
    path = writer.write(triaged)
    json.dump(
        {
            "source": result.path,
            "clause_count": len(clauses),
            "extracted": len(records),
            "approved": len(triaged.approved),
            "needs_review": len(triaged.needs_review),
            "output": str(path),
        },
        sys.stdout,
        indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
