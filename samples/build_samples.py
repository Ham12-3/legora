# ruff: noqa: E501 -- contract clauses are long sentences by nature
"""Assemble a sample pack for trying the application by hand.

    uv run --directory apps/api python ../../samples/build_samples.py

This is not another contract generator. Two already exist and they are the
source of most of this pack:

  tests/eval/golden/build_golden.py  20 contracts whose every answer is known,
                                     including which questions have none
  tests/fixtures/build_fixtures.py   the shapes the pipeline has to survive —
                                     a DOCX, and a scan with no text layer

What neither produces is a LONG agreement. The golden contracts are three
pages and about 900 tokens, comfortably under
``full_context_token_threshold``, so every cell over them is answered from the
whole document and the hybrid retrieval path never runs. ``long_msa`` below is
built to cross that line with margin: a handful of clauses that carry the real
answers, buried in schedules and statements of work, so the router has to
retrieve and you can see whether it retrieved the right passages.

Everything lands in samples/ with an answer key.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import pymupdf
import yaml

HERE = Path(__file__).parent
API = HERE.parent / "apps" / "api"
sys.path.insert(0, str(API))
from app.ingestion.types import estimate_tokens  # noqa: E402
from tests.fixtures.build_fixtures import write_pdf  # noqa: E402

GOLDEN = API / "tests" / "eval" / "golden"
FIXTURES = API / "tests" / "fixtures"
NOT_PRESENT_SLUG = "law-unstated"

# Golden contracts are chosen, not hardcoded: the generator repeats templates,
# so a fixed list picks up duplicates — and two documents with the same bytes
# in one matter hit the (matter_id, sha256) constraint and the second upload is
# rejected as a duplicate. Names are derived from the contract itself so they
# cannot drift from what is inside.
WANTED = 6

# Shapes rather than answers: these exist to exercise the DOCX branch of the
# parser and the OCR branch.
FROM_FIXTURES = [
    ("msa.docx", "07-master-services-agreement.docx"),
    ("scanned_nda.pdf", "08-nda-scanned-no-text-layer.pdf"),
]

LONG_ANSWERS = {
    "Which law governs this agreement?": "the laws of Singapore",
    "What is the cap on each party's aggregate liability?": "150% of the Charges paid in the preceding 12 months",
    "Does the agreement renew automatically after the initial term?": "Yes, successive periods of 24 months",
    "What are the payment terms?": "45 days from the date of invoice",
    "Is there a non-compete restriction on either party?": "Not present",
    "Can either party terminate the agreement for convenience?": "Yes, on 90 days written notice",
    "Who owns the intellectual property in the deliverables?": "Ashford Rail Holdings (the Customer)",
    "What is the confidentiality term?": "Five (5) years from disclosure",
}


def pick_golden() -> list[tuple[str, str]]:
    """(source name, destination name) for WANTED contracts with distinct text."""
    expected = yaml.safe_load((GOLDEN / "expected.yaml").read_text(encoding="utf-8"))
    seen: set[str] = set()
    chosen: list[tuple[str, str]] = []
    for name in sorted(expected):
        path = GOLDEN / name
        if not path.exists():
            continue
        with pymupdf.open(path) as doc:
            text = "\n".join(page.get_text() for page in doc)
            title = next((line.strip() for line in text.splitlines() if line.strip()), "AGREEMENT")
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        law = str(expected[name].get("governing_law", "")).lower()
        law = NOT_PRESENT_SLUG if law == "not present" else law
        slug = "-".join(
            part
            for part in f"{title.lower()} {law}".replace(",", " ").split()
            if part not in {"the", "of", "state", "as", "a"}
        )
        chosen.append((name, f"{len(chosen) + 1:02d}-{slug}.pdf"))
        if len(chosen) == WANTED:
            break
    return chosen


def long_msa() -> str:
    """A framework agreement long enough to force retrieval instead of full context."""
    parts = [
        "FRAMEWORK SERVICES AGREEMENT",
        'This framework services agreement (the "Agreement") is made between Ashford Rail Holdings plc ("Customer") and Pellwood Digital Pte. Ltd. ("Supplier").',
        "",
        "1.  DEFINITIONS AND INTERPRETATION",
        '1.1  In this Agreement the following words have the meanings given to them in this clause 1. "Charges" means the amounts payable by the Customer for the Services as set out in the relevant Statement of Work. "Deliverables" means any item created by the Supplier for the Customer under a Statement of Work. "Services" means the services described in a Statement of Work.',
        "1.2  Clause headings do not affect interpretation. A reference to a statute includes any subordinate legislation made under it and is a reference to that statute as amended or re-enacted from time to time.",
        "1.3  Words in the singular include the plural and vice versa, and a reference to one gender includes the other.",
        "",
        "2.  APPOINTMENT AND STATEMENTS OF WORK",
        "2.1  The Customer appoints the Supplier to provide the Services on a non-exclusive basis, and the Supplier accepts that appointment on the terms of this Agreement.",
        "2.2  No Statement of Work is binding until signed by an authorised representative of each party. Each Statement of Work forms a separate contract incorporating these terms.",
        "2.3  Where a Statement of Work conflicts with these terms, these terms prevail unless the Statement of Work expressly states which clause it overrides.",
        "",
        "3.  CHARGES AND PAYMENT",
        "3.1  The Customer shall pay the Charges within forty-five (45) days of the date of the Supplier's invoice.",
        "3.2  All amounts are exclusive of value added tax, which the Customer shall pay in addition at the prevailing rate against a valid tax invoice.",
        "3.3  The Supplier may charge interest on undisputed sums paid late at 2% above the base rate of the Monetary Authority of Singapore, accruing daily.",
        "3.4  The Customer may withhold payment of any amount it disputes in good faith, provided it notifies the Supplier of the dispute within fifteen (15) days of receiving the invoice and pays the undisputed balance when due.",
        "",
        "4.  TERM AND RENEWAL",
        "4.1  This Agreement begins on the Effective Date and continues for an initial term of thirty-six (36) months.",
        "4.2  On expiry of the initial term this Agreement renews automatically for successive periods of twenty-four (24) months unless either party gives written notice of non-renewal not less than one hundred and twenty (120) days before the end of the then-current term.",
        "",
        "5.  TERMINATION",
        "5.1  Either party may terminate this Agreement for convenience at any time on ninety (90) days written notice to the other party.",
        "5.2  Either party may terminate this Agreement immediately on written notice if the other commits a material breach which is incapable of remedy, or which it fails to remedy within thirty (30) days of being required to do so in writing.",
        "5.3  On termination the Customer shall pay for Services performed up to the effective date of termination, and the Supplier shall return or destroy the Customer's Confidential Information at the Customer's option.",
        "",
        "6.  INTELLECTUAL PROPERTY",
        "6.1  All intellectual property rights in the Deliverables vest in the Customer on creation, and the Supplier assigns those rights to the Customer with full title guarantee.",
        "6.2  The Supplier retains all rights in its pre-existing materials and grants the Customer a perpetual, non-exclusive, royalty-free licence to use them to the extent they are embedded in a Deliverable.",
        "",
        "7.  CONFIDENTIALITY",
        "7.1  Each party shall keep the other's Confidential Information confidential for five (5) years from the date of disclosure and shall not use it except to perform this Agreement.",
        "7.2  Clause 7.1 does not apply to information which is or becomes public through no fault of the receiving party, or which the receiving party is required to disclose by law or by a competent regulator.",
        "",
        "8.  LIMITATION OF LIABILITY",
        "8.1  Subject to clause 8.3, each party's aggregate liability arising out of or in connection with this Agreement, whether in contract, tort (including negligence) or otherwise, shall not exceed 150% of the Charges paid or payable in the twelve (12) months preceding the event giving rise to the claim.",
        "8.2  Neither party is liable for loss of profit, loss of anticipated savings, loss of business opportunity or any indirect or consequential loss.",
        "8.3  Nothing in this Agreement limits liability for death or personal injury caused by negligence, for fraud, or for any liability which cannot lawfully be limited.",
        "",
        "9.  GOVERNING LAW AND JURISDICTION",
        "9.1  This Agreement and any dispute arising out of or in connection with it are governed by the laws of Singapore.",
        "9.2  The parties submit to the exclusive jurisdiction of the courts of Singapore.",
        "",
    ]

    # Bulk. The clauses above are what the questions are about; everything from
    # here on is the operational detail a real framework agreement carries, and
    # its job in this fixture is to push the document past the full-context
    # threshold so the router has to retrieve.
    schedules = [
        (
            "SERVICE LEVELS",
            [
                "The Supplier shall provide the Services in accordance with the service levels set out in the applicable Statement of Work.",
                "Availability is measured monthly, excluding planned maintenance notified at least five (5) working days in advance and emergency maintenance notified as soon as reasonably practicable.",
                "Service credits are the Customer's sole financial remedy for a failure to meet a service level, save where the failure amounts to a material breach.",
                "The Supplier shall provide a monthly service report within ten (10) working days of the end of each month, covering availability, incident volumes by severity, and the status of any outstanding corrective actions.",
            ],
        ),
        (
            "CHANGE CONTROL",
            [
                "Either party may request a change to a Statement of Work by submitting a written change request describing the change and the reason for it.",
                "The Supplier shall respond within ten (10) working days with an impact assessment covering the effect on the Charges, the timetable and the service levels.",
                "No change takes effect until both parties have signed a change note. Work performed on an unsigned change is at the Supplier's risk and expense.",
            ],
        ),
        (
            "PERSONNEL",
            [
                "The Supplier shall ensure that all personnel engaged in providing the Services are suitably qualified, experienced and trained.",
                "The Supplier shall not remove or replace any person named as key personnel in a Statement of Work without the Customer's prior written consent, not to be unreasonably withheld.",
                "Each party shall comply with all applicable laws relating to the employment of its own personnel, and neither party's personnel become employees of the other.",
            ],
        ),
        (
            "DATA PROTECTION",
            [
                "Each party shall comply with applicable data protection legislation in performing its obligations under this Agreement.",
                "Where the Supplier processes personal data on behalf of the Customer it does so only on the Customer's documented instructions, and shall implement appropriate technical and organisational measures against unauthorised or unlawful processing.",
                "The Supplier shall notify the Customer without undue delay and in any event within forty-eight (48) hours of becoming aware of a personal data breach affecting the Customer's data.",
                "The Supplier shall not engage a sub-processor without the Customer's prior written authorisation, and shall impose on any authorised sub-processor obligations no less protective than those in this clause.",
            ],
        ),
        (
            "SECURITY",
            [
                "The Supplier shall maintain an information security management system aligned with ISO/IEC 27001 and shall provide evidence of certification on request.",
                "The Supplier shall encrypt Customer data in transit and at rest using algorithms and key lengths that are generally accepted as secure at the relevant time.",
                "The Customer may audit the Supplier's compliance with this schedule once in any twelve (12) month period on thirty (30) days notice, and more frequently following a security incident affecting the Customer.",
                "The Supplier shall remediate any critical vulnerability within seven (7) days of discovery and any high vulnerability within thirty (30) days.",
            ],
        ),
        (
            "BUSINESS CONTINUITY",
            [
                "The Supplier shall maintain a business continuity and disaster recovery plan and shall test it at least annually.",
                "The recovery time objective for the Services is four (4) hours and the recovery point objective is fifteen (15) minutes, unless a Statement of Work provides otherwise.",
                "The Supplier shall provide the Customer with a summary of each test and of any corrective action arising from it.",
            ],
        ),
        (
            "INSURANCE",
            [
                "The Supplier shall maintain professional indemnity insurance of not less than S$5,000,000 for each claim, and public liability insurance of not less than S$2,000,000.",
                "The Supplier shall provide evidence of cover on reasonable request and shall notify the Customer if cover lapses or is materially reduced.",
            ],
        ),
        (
            "COMPLIANCE",
            [
                "Each party shall comply with all applicable anti-bribery and anti-corruption laws and shall maintain policies and procedures designed to ensure compliance.",
                "Each party shall comply with applicable modern slavery legislation and shall take reasonable steps to ensure that slavery and human trafficking do not occur in its supply chain.",
                "Each party shall comply with applicable sanctions and export control laws, and neither shall require the other to act in a way that would breach them.",
            ],
        ),
        (
            "SUBCONTRACTING AND ASSIGNMENT",
            [
                "The Supplier may subcontract the performance of any part of the Services with the Customer's prior written consent, and remains responsible for the acts and omissions of its subcontractors.",
                "Neither party may assign or otherwise transfer any of its rights or obligations under this Agreement without the prior written consent of the other, such consent not to be unreasonably withheld or delayed.",
                "Either party may assign this Agreement in whole to a successor in title to the whole of its business without consent, on written notice to the other.",
            ],
        ),
        (
            "NOTICES AND GENERAL",
            [
                "Any notice under this Agreement shall be in writing and delivered by hand, by prepaid recorded delivery or by email to the address notified by the receiving party for that purpose.",
                "This Agreement constitutes the entire agreement between the parties and supersedes all previous agreements and understandings relating to its subject matter.",
                "No variation of this Agreement is effective unless it is in writing and signed by both parties.",
                "A failure or delay in exercising a right under this Agreement does not operate as a waiver of that right.",
                "If any provision is held to be invalid or unenforceable, the remaining provisions continue in full force, and the parties shall negotiate in good faith to replace the affected provision.",
                "Nothing in this Agreement creates a partnership, joint venture or relationship of employer and employee between the parties.",
                "A person who is not a party to this Agreement has no right to enforce any of its terms.",
            ],
        ),
    ]

    number = 10
    for title, clauses in schedules:
        parts.append(f"{number}.  {title}")
        for index, clause in enumerate(clauses, start=1):
            parts.append(f"{number}.{index}  {clause}")
        parts.append("")
        number += 1

    # Statements of work: the repetitive bulk a framework agreement really has.
    for sow in range(1, 43):
        parts.append(f"SCHEDULE {sow}  —  STATEMENT OF WORK {sow:02d}")
        parts.append(
            f"This Statement of Work {sow:02d} is entered into under the Framework Services Agreement and incorporates its terms. The Services comprise design, build and run activities for workstream {sow:02d} as described below."
        )
        parts.append(
            f"1.  Scope. The Supplier shall deliver the workstream {sow:02d} scope agreed in the project initiation document, including discovery, solution design, build, test, deployment and a period of hypercare of thirty (30) days following go-live."
        )
        parts.append(
            f"2.  Timetable. Work begins on the commencement date recorded in the project initiation document and is expected to complete within {6 + sow} months, subject to change control under clause 11."
        )
        parts.append(
            f"3.  Charges. The Charges for workstream {sow:02d} are calculated on a time and materials basis at the rate card in Schedule A, invoiced monthly in arrears, and are subject to the payment terms in clause 3."
        )
        parts.append(
            "4.  Acceptance. The Customer shall test each Deliverable within fifteen (15) working days of delivery and shall notify the Supplier of any failure to meet the acceptance criteria. A Deliverable not rejected within that period is deemed accepted."
        )
        parts.append(
            "5.  Dependencies. The Customer shall provide timely access to its personnel, systems, environments and data as reasonably required. The Supplier is relieved of a delay to the extent it is caused by the Customer's failure to meet a dependency."
        )
        parts.append("")

    return "\n".join(parts)


def answer_key(golden: list[tuple[str, str]], pages: int, tokens: int) -> str:
    expected = yaml.safe_load((GOLDEN / "expected.yaml").read_text(encoding="utf-8"))
    questions = yaml.safe_load((GOLDEN / "questions.yaml").read_text(encoding="utf-8"))
    by_key = {q["key"]: q for q in questions}
    shown = [
        "governing_law",
        "term",
        "liability_cap",
        "auto_renewal",
        "non_compete",
        "termination_for_convenience",
        "ip_ownership",
        "payment_terms",
    ]

    lines = [
        "# Sample pack — answer key",
        "",
        "Generated by `samples/build_samples.py`. Every contract here is synthetic,",
        "so the answers below are not opinions: they are what was written into the",
        "document. **Not present** means the contract genuinely does not address the",
        "question, and the honest answer in the grid is *Not found*. Those are the",
        "cells worth watching — an answer there is the model inventing one.",
        "",
        "Liability caps are written as bare percentages: `100` means 100% of the fees",
        "paid. Terms read as the generator wrote them, so `one (1) years` is what the",
        "contract actually says.",
        "",
        "## Documents",
        "",
        "| File | What it is for |",
        "|---|---|",
    ]
    for _, new in golden:
        lines.append(f"| `{new}` | Three pages. Answered from the whole document. |")
    lines.append(
        "| `07-master-services-agreement.docx` | The DOCX branch of the parser. No answer key. |"
    )
    lines.append(
        "| `08-nda-scanned-no-text-layer.pdf` | Images only. Exercises OCR; the UI should flag it as scanned. |"
    )
    lines.append(
        "| `09-framework-agreement-long.pdf` | Long enough to cross the full-context threshold, so retrieval runs instead. |"
    )
    lines.append("")

    for original, new in golden:
        lines.append(f"## {new}")
        lines.append("")
        lines.append("| Question | Answer |")
        lines.append("|---|---|")
        for key in shown:
            value = expected[original].get(key, "")
            answer = "**Not present**" if value == "not present" else value
            lines.append(f"| {by_key[key]['question']} | {answer} |")
        lines.append("")

    lines.append("## 09-framework-agreement-long.pdf")
    lines.append("")
    lines.append(f"{pages} pages, about {tokens:,} tokens, most of it schedules and statements")
    lines.append("of work. That is past the 12,000-token threshold, so the grid cannot send the")
    lines.append("whole document: it retrieves passages instead, and the answers below are only")
    lines.append("right if it retrieved the right ones.")
    lines.append("")
    lines.append("| Question | Answer |")
    lines.append("|---|---|")
    for question, answer in LONG_ANSWERS.items():
        shown_answer = f"**{answer}**" if answer == "Not present" else answer
        lines.append(f"| {question} | {shown_answer} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    HERE.mkdir(exist_ok=True)

    golden = pick_golden()
    if len(golden) < WANTED:
        print(
            f"only {len(golden)} distinct golden contracts found: "
            "run tests/eval/golden/build_golden.py first",
            file=sys.stderr,
        )
        raise SystemExit(2)

    for original, new in golden:
        shutil.copyfile(GOLDEN / original, HERE / new)
    for original, new in FROM_FIXTURES:
        shutil.copyfile(FIXTURES / original, HERE / new)

    body = long_msa()
    write_pdf(HERE / "09-framework-agreement-long.pdf", body)

    # Measured from the rendered PDF with the pipeline's own estimator, so the
    # answer key cannot claim a size the router disagrees with.
    with pymupdf.open(HERE / "09-framework-agreement-long.pdf") as pdf:
        pages = pdf.page_count
        tokens = estimate_tokens("\n".join(page.get_text() for page in pdf))

    (HERE / "ANSWER-KEY.md").write_text(
        answer_key(golden, pages, tokens), encoding="utf-8", newline="\n"
    )

    print(f"wrote {len(golden) + len(FROM_FIXTURES) + 2} files to {HERE}")
    print(f"long agreement: {pages} pages, {tokens:,} tokens (threshold is 12,000)")


if __name__ == "__main__":
    main()
