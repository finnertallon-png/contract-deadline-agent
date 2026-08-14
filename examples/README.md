# Example: synthetic contract, end to end

Everything here is synthetic. Every party, project, and figure is invented,
and the contract carries a `SYNTHETIC - GENERATED TEST DATA` header in its
body. No client or real-matter material appears anywhere in this repository.

| File | What it is |
| --- | --- |
| `generate_sample.py` | Regenerates the PDF. `python examples/generate_sample.py` |
| `sample_contract.pdf` | A one-page synthetic construction contract: preamble with parties/project/value/date, then claims, payment, completion, submittal, termination, and warranty clauses |
| `sample_contract.deadlines.json` | Actual pipeline output from a real run (`python -m deadline_agent examples/sample_contract.pdf --extract`), unedited |

## What the output shows

From 12 segmented clauses, the pipeline extracted 7 obligations:

- **2 approved**: the progress-payment clause (the contract says "business
  days" explicitly, so every confidence signal passes) and the absolute
  Final Completion date (stated verbatim, never computed).
- **5 routed to review**, every one for the same honest reason: the clause
  gives a day count without saying business or calendar days. The model
  reported `unspecified` instead of guessing, and the review rule sends
  that to a person, because the distinction can move a real deadline by
  days and is often defined in a section the extractor never saw.

Document metadata (both parties with roles, project name, contract value,
effective date) extracted verbatim with all containment checks passing.

## What it deliberately does not show

The warranty clause (6.3, "warrants the Work for a period of one year")
passed the prefilter but the extractor returned no obligation for it — a
warranty *period* is a duration of coverage, not an act-by deadline. That
is a judgment call, and reasonable people could want warranty periods
tracked; if that requirement lands, it becomes an obligation type rather
than a prompt tweak. Recorded here so the gap is visible, not discovered.
