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

### Review routing: hard rules plus a provisional threshold (2026-08-14)

A record is approved only when nothing argues against it. Two rules are
hard, independent of any threshold: a supporting quote that isn't found
verbatim in the clause is never approvable (the extraction can't be traced
to the contract), and a relative deadline whose business-vs-calendar basis
the clause doesn't state always goes to review — the extraction is honest,
but the distinction can move a real deadline by days, so a person confirms
it against the contract's definitions section. On top of those, records
below the confidence threshold go to review. The threshold ships at a
provisional 0.8, biased toward over-reviewing because a bad approval is a
missed legal deadline; choosing it properly is still blocked on a labeled
set, and both approved and needs-review records are always written together
so nothing is silently dropped.

### Writer is a seam; JSON/CSV default, Graph is the deployment target (2026-08-14)

The write stage is an interface, not a single destination. Demo and
development write local JSON (full fidelity) or CSV (flat rows shaped like
the target SharePoint list). The Graph API writer is the deployment target
and lands with the permission-scope decision below — it needs a tenant, an
app registration, and admin consent, none of which a demo should depend on.
Rows always carry review status and reasons.

### Document metadata: one pass over the opening text (2026-08-14)

Parties, project name, contract value, and effective date are a separate,
single extraction over the document's opening (capped at a few thousand
characters) — that is where preambles and recitals put this information,
and keeping it out of the clause pipeline keeps that pipeline deadline-only.
Values are verbatim spans (the stated dollar amount, the stated date — never
reformatted or computed) and each populated field is containment-checked
against the source text, the same discipline as deadline quotes. Fields the
opening doesn't state come back null rather than guessed. Metadata defined
only in exhibits, or changed by amendment, is missed — recorded in
LIMITATIONS.

### Graph permission scope: Sites.Selected, granted to one site (2026-08-16)

When the Graph writer lands, the service's app registration will request
`Sites.Selected`, not `Sites.ReadWrite.All`. With `ReadWrite.All` the app
credential can touch every SharePoint site in the tenant — at a law firm
that is a skeleton key past every matter-level access boundary, and an
unacceptable blast radius for a service that only writes rows to one
deadlines list. `Sites.Selected` grants nothing by default; a tenant admin
then grants the app write access to exactly the one site hosting the
contracts library and the deadlines list. If the service's credentials
leak or the code misbehaves, the damage is bounded to that site.

The grant mechanics (a per-site Graph call made by an admin, separate from
admin consent on the permission itself) still need to be validated against
a real tenant alongside the writer implementation — that part stays open
until there is tested code.

Access control is three separate layers, and this decision covers only the
first: `Sites.Selected` limits where the *software* can reach; ordinary
SharePoint permissions limit what *people* can see (this tool neither adds
to nor bypasses them — the contracts library keeps whatever matter-level
permissions the firm already set); and the notification flows decide who
gets *told*. A Copilot front-end, if used, retrieves documents as the
chatting user and cannot fetch anything that user could not already open.

One governance question is deliberately left to the deploying firm: the
deadlines list contains fragments *of* contracts (quotes, clause numbers,
party names). If a source contract is restricted but the list is broadly
visible, the list leaks fragments of a restricted document. The options —
per-matter lists, item-level permissions on rows, or an explicit policy
that deadline metadata is more widely visible than the contracts — are a
firm policy choice, not a code change. Recorded in LIMITATIONS so the
question is raised before deployment, not discovered after.

### Model provider: Claude, deployed via Microsoft Foundry in M365 shops (2026-08-14)

The extraction model is Claude. For development and demo, the service calls
the Anthropic API directly (an API key). In a real M365 deployment the same
model is served through Microsoft Foundry in the firm's Azure tenant: Entra
ID auth, Microsoft billing, data residency inside their Azure boundary, and
no second AI vendor to onboard. The Anthropic SDK supports both — the
difference is the client constructor (`Anthropic()` vs `AnthropicFoundry`)
injected into the extractor, which is why the extractor takes its client as
a parameter. Copilot Studio, if used, is a front-end over the SharePoint
list or an HTTP caller of this service; it never makes the extraction call.
