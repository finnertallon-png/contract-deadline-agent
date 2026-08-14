# Architecture

## Pipeline

1. **Ingest** — PDF or DOCX in, text and layout out. Layout matters: numbered
   clause hierarchy is the main structural signal in a construction contract.
2. **Segment** — split into clauses rather than fixed-size chunks. A notice
   provision split across two chunks extracts wrong.
3. **Classify** — identify which clauses create a time-bound obligation.
4. **Extract** — pull the obligation into a structured record.
5. **Normalize** — resolve relative windows into trigger + duration + units.
6. **Review** — anything below the confidence threshold is queued for a human.
7. **Write** — approved records go to a SharePoint list via Graph API.

## Deadline representation

Store the rule, not a date. A deadline is:

    { trigger, duration, unit, calendar (business|calendar), source_clause,
      source_page, confidence }

Computing a fixed date at extraction time is wrong, because the trigger event
usually has not happened yet.

## Design decisions to record here as they are made

- Clause segmentation approach and why
- Confidence threshold and how it was chosen
- Whether extraction runs per-clause or per-document, and the cost tradeoff
- Graph API permission scope requested, and why it is the minimum
