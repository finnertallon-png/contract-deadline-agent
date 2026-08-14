# Limitations

Written plainly, because a tool that touches deadlines needs to be honest about
where it fails.

## This tool does not

- Provide legal advice, or decide whether a deadline applies to a given situation
- Compute actual calendar dates. It extracts the rule; a human supplies the
  trigger date.
- Handle handwritten or scanned-without-OCR documents
- Resolve conflicts between a prime contract and a subcontract that flows down
  different terms
- Interpret ambiguous drafting. Where a clause is genuinely ambiguous, it flags
  rather than picks.

## Known failure modes

- **Incorporation by reference.** Contracts routinely incorporate general
  conditions or specifications by reference. Deadlines in those documents are
  invisible unless those documents are also ingested.
- **Amendments and change orders.** A later document can modify an earlier
  deadline. Nothing here tracks that automatically.
- **Business vs calendar days.** Determined by contract definitions that may sit
  in an entirely different section. Extraction can get this wrong.
- **Long documents.** Extraction quality degrades on very long agreements.

## Accuracy

No accuracy figure is claimed until measured against a labeled set. Any number
quoted without a stated test set and methodology should be treated as marketing.

## Intended use

Assistive. Output is reviewed by a person before anyone relies on it. This is
not a system of record for deadlines.
