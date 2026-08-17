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
- Enforce access control on its output. Extracted records quote from their
  source contracts — party names, clause text, dollar figures. If a source
  document is restricted (ethical walls, matter-level permissions) but the
  deadlines list it feeds is broadly visible, the list leaks fragments of a
  restricted document. Permissions on the list are the deploying firm's
  configuration decision, made before rollout — per-matter lists, item-level
  permissions, or an explicit policy that deadline metadata is more widely
  visible than the contracts. See the access-control decision in
  `ARCHITECTURE.md`.

## Known failure modes

- **Incorporation by reference.** Contracts routinely incorporate general
  conditions or specifications by reference. Deadlines in those documents are
  invisible unless those documents are also ingested.
- **Amendments and change orders.** A later document can modify an earlier
  deadline. Nothing here tracks that automatically.
- **Business vs calendar days.** Determined by contract definitions that may sit
  in an entirely different section. Extraction can get this wrong.
- **Long documents.** Extraction quality degrades on very long agreements.
- **DOCX tables.** Text inside Word tables is not ingested. Deadline-bearing
  content in tables (submittal schedules, milestone tables) is invisible.
- **Metadata comes from the opening pages.** Parties, project name,
  contract value, and effective date are read from the document's opening
  text only. Values defined in an exhibit, or changed by amendment, are
  missed.
- **Warranty and coverage periods are not tracked.** A duration of coverage
  ("warrants the Work for one year") is not extracted as a deadline — only
  act-by obligations are. See `examples/README.md`.
- **Word auto-numbering.** When a DOCX relies on Word's automatic list
  numbering, the rendered numbers ("7.3") are not present in the extracted
  text. Ingest captures that a paragraph is a numbered list item and at what
  level, but clause numbers reconstructed from that signal are less reliable
  than printed ones.

## Accuracy

No accuracy figure is claimed until measured against a labeled set. Any number
quoted without a stated test set and methodology should be treated as marketing.

## Intended use

Assistive. Output is reviewed by a person before anyone relies on it. This is
not a system of record for deadlines.
