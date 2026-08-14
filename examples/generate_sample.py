"""Regenerate examples/sample_contract.pdf.

Fully synthetic — every name, project, and figure is invented, and the
document carries the SYNTHETIC header in its body per workspace policy.
Run from the repository root:

    python examples/generate_sample.py
"""

from pathlib import Path

import pymupdf

LINES = [
    "SYNTHETIC - GENERATED TEST DATA",
    "",
    "STANDARD FORM OF AGREEMENT BETWEEN OWNER AND CONTRACTOR",
    "",
    "This Agreement is made as of March 1, 2026 (the 'Effective Date'),",
    "between Riverbend Development LLC (the 'Owner') and Cardinal",
    "Structures, Inc. (the 'Contractor') for the project known as the",
    "Maple Street Parking Structure, Columbus, Ohio (the 'Project').",
    "The Contract Sum is Four Million Five Hundred Thousand Dollars",
    "($4,500,000), subject to additions and deductions as provided herein.",
    "",
    "ARTICLE 4 - CLAIMS AND DISPUTES",
    "4.1 Notice of Claims. Claims by either party must be initiated by",
    "written notice to the other party within twenty-one (21) days after",
    "occurrence of the event giving rise to such Claim.",
    "4.2 Differing Site Conditions. If the Contractor encounters a concealed",
    "or unknown physical condition, the Contractor shall give written notice",
    "to the Owner within 7 days of discovery, and shall submit a priced",
    "claim within 21 days thereafter, failing which the claim is waived.",
    "",
    "ARTICLE 5 - PAYMENT AND COMPLETION",
    "5.1 Progress Payments. The Owner shall pay each approved application",
    "for payment within ten (10) business days of receipt.",
    "5.2 Final Completion. The Contractor shall achieve Final Completion of",
    "the Work no later than December 31, 2026.",
    "5.3 Submittals. The Contractor shall deliver the submittal schedule to",
    "the Architect within fourteen (14) days after the Effective Date.",
    "",
    "ARTICLE 6 - GENERAL PROVISIONS",
    "6.1 Governing Law. This Agreement shall be governed by the laws of the",
    "State of Ohio, without regard to its conflict of laws principles.",
    "6.2 Termination for Cause. The Owner may terminate this Agreement if",
    "the Contractor fails to cure a default within seven (7) days after",
    "receipt of written notice of default from the Owner.",
    "6.3 Warranty. The Contractor warrants the Work for a period of one",
    "year after the date of Substantial Completion.",
]


def main() -> Path:
    out = Path(__file__).with_name("sample_contract.pdf")
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in LINES:
        if line:
            page.insert_text((72, y), line, fontsize=11)
        y += 16
    doc.save(str(out))
    doc.close()
    return out


if __name__ == "__main__":
    print(main())
