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

- Confidence threshold and how it was chosen
- Whether extraction runs per-clause or per-document, and the cost tradeoff
- Graph API permission scope requested, and why it is the minimum

## Recorded decisions

### Clause segmentation: rule-based on printed numbering markers (2026-08-14)

Segmentation is deterministic, driven by the numbering markers actually
printed in the text ("ARTICLE 5", "7.3.1", "(a)", "(iv)"), not an ML model
and not fixed-size chunks. Reasons:

- Clause boundaries must be exact — a notice provision split across two
  chunks extracts wrong — and only deterministic rules make boundaries
  unit-testable.
- Numbering is the one structural signal that survives both PDF text
  extraction and DOCX, and it costs nothing per document.
- Failure modes are inspectable: when segmentation is wrong you can point at
  the marker rule that fired, which matters for a tool a firm has to trust.

Mechanics: PDFs ingest as one block per visual line (page number + left
x-coordinate preserved); DOCX as one block per paragraph. Hierarchy is
rebuilt with a stack — decimal markers describe their own ancestry through
their components, letters/romans attach by sequence continuation, and the
"(i)" letter-vs-roman ambiguity is resolved by whether an open letter
sequence expects it (after "(h)" it is a letter, otherwise roman one).
Bare-integer markers are only accepted when they are 1, continue an open
sequence, or are followed by title-like heading text, which keeps sentence
wraps such as "2021. The parties agree..." out of the clause list.

Known gaps, accepted for now and noted in `segment.py`: exhibits and
schedules restart numbering and will nest wrongly; unnumbered ALL-CAPS
headings are treated as body text; Word auto-numbering is only visible as
"this paragraph is a numbered list item", not as the rendered number.
