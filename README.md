# Contract Deadline Agent

Extracts notice provisions, cure periods, and other time-bound obligations from
construction and commercial contracts, then writes them to a tracked list with
reminders.

## The problem

Construction contracts are dense with notice provisions. A contractor who
discovers a differing site condition may have seven days to give written notice
and twenty-one days to submit a priced claim. Miss the notice window and an
otherwise valid claim is gone, regardless of merit. These deadlines are scattered
through documents that run hundreds of pages, and they are usually tracked by
hand.

## Who this is for

Legal and IT teams at midsize firms with construction-heavy or transactional
practices, working inside Microsoft 365. Also useful to in-house counsel and
contract administrators on the owner or contractor side.

## What it does

- Ingests a contract (PDF or DOCX) and identifies clauses that create a deadline
- Extracts parties, project name, contract value, effective dates, and every
  notice, cure, and submission window it finds
- Normalizes relative deadlines ("within 10 days of discovery") into a structured
  trigger + duration representation rather than guessing a calendar date
- Writes structured output to a tracked list — SharePoint via the Graph API in
  deployment, local JSON/CSV for demo and development
- Reminders come from Power Automate on top of the SharePoint list: a person
  supplies the trigger date on the list item, and the flow computes the
  reminder from it. The tool itself never computes a calendar date.
- Flags low-confidence extractions for human review instead of silently guessing

## See it run

`examples/` contains a synthetic one-page construction contract and the
unedited output of a real end-to-end run against it: 7 obligations extracted,
2 auto-approved, 5 routed to human review — every one for an honest reason.
`examples/README.md` walks through what the output shows and what the
pipeline deliberately declined to extract. Start there if you want to see
what this tool actually produces before reading any code.

## Architecture

See `docs/ARCHITECTURE.md`.

## Limitations

See `docs/LIMITATIONS.md`. Read this before evaluating the tool. It is the most
important document in the repository.

## Running it

```sh
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"

# Segment a contract into clauses (no API calls)
python -m deadline_agent contract.pdf
python -m deadline_agent contract.pdf --candidates   # mark deadline-bearing clauses

# Full pipeline: extract, score, triage, write (calls the Claude API)
export ANTHROPIC_API_KEY=...
python -m deadline_agent contract.pdf --extract --out deadlines.json
python -m deadline_agent contract.pdf --extract --out deadlines.csv

# Tests run without network or credentials
python -m pytest
```

In an M365 deployment the extraction model is Claude served through
Microsoft Foundry (Entra ID auth, Microsoft billing — no separate Anthropic
key or vendor relationship); the direct Anthropic API is the development
path. The code difference is one client constructor.

## Data

Testing uses publicly available contract corpora and synthetic documents.
No client or confidential material is used anywhere in this project.

## License

MIT. See `LICENSE`.
