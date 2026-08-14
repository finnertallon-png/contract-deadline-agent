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
- Writes structured output to a SharePoint list, with reminders via Power Automate
- Flags low-confidence extractions for human review instead of silently guessing

## Architecture

See `docs/ARCHITECTURE.md`.

## Limitations

See `docs/LIMITATIONS.md`. Read this before evaluating the tool. It is the most
important document in the repository.

## Running it

TODO once implementation lands.

## Data

Testing uses publicly available contract corpora and synthetic documents.
No client or confidential material is used anywhere in this project.

## License

MIT. See `LICENSE`.
