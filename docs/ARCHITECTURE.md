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

- Confidence threshold and how it was chosen (blocked on a labeled set —
  the confidence *signals* are decided, see below)
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

### Deadline schema: tagged union, calendar allows unspecified (2026-08-14)

The original schema assumed every deadline is relative (trigger + duration).
Contracts also state fixed dates ("by December 31, 2026"), so the deadline
is a tagged union: `relative` (trigger, duration_value, duration_unit,
calendar) or `absolute` (the stated date, verbatim). Extracting a stated
date is not computing one, so the LIMITATIONS promise holds.

`calendar` is `business | calendar | unspecified` rather than a forced
binary. Whether "days" means business or calendar days is often defined in a
different section of the contract (a known failure mode); forcing a binary
choice would make the model guess, and a guess about a deadline basis is
worse than an honest "unspecified" routed to human review.

### Classification: lexical prefilter, then one LLM pass per clause (2026-08-14)

Classify and Extract are not two model calls. Classification is a cheap,
recall-biased regex prefilter (duration expressions, time-window phrases,
absolute dates); only clauses with a signal go to the model, and a single
structured-output call does classify + extract together — a clause with no
time-bound obligation extracts to an empty list. Rationale: a second model
pass would double cost for no signal the extraction doesn't already give,
and a prefilter false positive costs one wasted call while a false negative
is a missed deadline, so the filter errs open.

Extraction runs per-clause, not per-document: the verbatim-quote confidence
check needs a bounded source text to verify against, per-clause calls avoid
the long-document degradation named in LIMITATIONS, and cost stays bounded
because the prefilter has already cut the call count. The per-clause system
prompt is cached, so the fixed prompt is paid for roughly once per run.

### Confidence: derived from checkable signals, not self-reported (2026-08-14)

Self-reported model confidence is uncalibrated, so the pipeline never asks
for it. Confidence is computed from checks that can be verified mechanically
against the clause text: the supporting quote appears verbatim (failing this
caps confidence at 0.2 — a fabricated quote dominates everything), the
extracted duration is findable in the quote including number-word forms
("twenty-one (21) days"), the business/calendar choice matches what the
quote actually says, and a stated absolute date appears in the quote. The
weights are provisional and marked as such in `confidence.py`; the review
threshold is undecided until there is a labeled set to choose it against —
per the no-numbers-without-a-test-set standard.
