# ruff: noqa: E501 -- contract clauses are long sentences by nature
"""Generate the golden evaluation set: 20 contracts with known answers.

    uv run python tests/eval/golden/build_golden.py

Each contract is assembled from a template with controlled variation
(governing law, term, cap, which clauses are present), so every expected
answer in ``expected.yaml`` is known exactly, including which questions have
NO answer in the document — those are what the hallucination rate measures.

These are synthetic. They exercise the pipeline and the questions honestly,
but they do not exercise the formatting quirks of real agreements. Before
trusting the numbers for a pilot, add real public contracts (SEC EDGAR EX-10
exhibits are free): drop the PDF next to these, add its answers to
``expected.yaml`` by hand, and rerun ``make eval``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2]))
from tests.fixtures.build_fixtures import write_pdf  # noqa: E402

NOT_PRESENT = "not present"

QUESTIONS: list[dict[str, str]] = [
    {
        "key": "governing_law",
        "name": "Governing law",
        "output_type": "text",
        "question": "Which law governs this agreement?",
    },
    {
        "key": "term",
        "name": "Initial term",
        "output_type": "text",
        "question": "What is the initial term of the agreement?",
    },
    {
        "key": "termination_for_convenience",
        "name": "Termination for convenience",
        "output_type": "boolean",
        "question": "Can either party terminate the agreement for convenience, without cause?",
    },
    {
        "key": "liability_cap",
        "name": "Liability cap",
        "output_type": "text",
        "question": "What is the cap on each party's aggregate liability?",
    },
    {
        "key": "indemnity",
        "name": "Indemnity",
        "output_type": "text",
        "question": "Who indemnifies whom, and for what?",
    },
    {
        "key": "assignment",
        "name": "Assignment",
        "output_type": "boolean",
        "question": "May a party assign the agreement without the other party's consent?",
    },
    {
        "key": "change_of_control",
        "name": "Change of control",
        "output_type": "boolean",
        "question": "Does a change of control give either party a right to terminate?",
    },
    {
        "key": "confidentiality_term",
        "name": "Confidentiality term",
        "output_type": "text",
        "question": "How long do the confidentiality obligations last after termination or expiry?",
    },
    {
        "key": "non_compete",
        "name": "Non-compete",
        "output_type": "boolean",
        "question": "Is there a non-compete restriction on either party?",
    },
    {
        "key": "payment_terms",
        "name": "Payment terms",
        "output_type": "text",
        "question": "Within how many days of invoice must payment be made?",
    },
    {
        "key": "auto_renewal",
        "name": "Auto-renewal",
        "output_type": "boolean",
        "question": "Does the agreement renew automatically after the initial term?",
    },
    {
        "key": "exclusivity",
        "name": "Exclusivity",
        "output_type": "boolean",
        "question": "Does the agreement contain an exclusivity obligation?",
    },
    {
        "key": "ip_ownership",
        "name": "IP ownership",
        "output_type": "text",
        "question": "Who owns the intellectual property in the deliverables or platform?",
    },
    {
        "key": "data_protection",
        "name": "Data protection",
        "output_type": "boolean",
        "question": "Does the agreement contain data protection obligations?",
    },
    {
        "key": "dispute_resolution",
        "name": "Dispute resolution",
        "output_type": "text",
        "question": "How are disputes resolved (courts, arbitration, expert determination)?",
    },
]


@dataclass
class Spec:
    slug: str
    kind: str  # msa | saas | nda | services
    customer: str
    supplier: str
    law: str  # "England and Wales" | "New York" | "Scotland" | ...
    courts: str  # e.g. "the courts of England and Wales"
    term_years: int | None
    convenience_months: int | None  # None -> no termination for convenience clause
    cap_pct: int | None  # None -> no cap clause
    payment_days: int | None
    confidentiality_years: int | None
    auto_renew_months: int | None
    indemnity: bool
    assignment_consent: bool | None  # True -> consent required; False -> free; None -> silent
    change_of_control: bool | None
    non_compete_months: int | None
    exclusivity: bool | None
    ip_owner: str | None  # "Supplier" | "Customer"
    data_protection: bool
    dispute: str  # "courts" | "arbitration" | "expert"
    expected: dict[str, str] = field(default_factory=dict)


def _num(n: int) -> str:
    words = {
        1: "one",
        2: "two",
        3: "three",
        5: "five",
        6: "six",
        9: "nine",
        12: "twelve",
        14: "fourteen",
        24: "twenty-four",
        30: "thirty",
        45: "forty-five",
        60: "sixty",
        90: "ninety",
        100: "one hundred",
        125: "one hundred and twenty-five",
        150: "one hundred and fifty",
        200: "two hundred",
    }
    return f"{words.get(n, str(n))} ({n})"


def render(spec: Spec) -> str:
    c, s = spec.customer, spec.supplier
    title = {
        "msa": "MASTER SERVICES AGREEMENT",
        "saas": "SOFTWARE AS A SERVICE AGREEMENT",
        "nda": "MUTUAL NON-DISCLOSURE AGREEMENT",
        "services": "PROFESSIONAL SERVICES AGREEMENT",
    }[spec.kind]
    parts = [
        title,
        f'This agreement (the "Agreement") is made between {c} ("Customer") and {s} ("Supplier").',
    ]
    n = 0

    def clause(heading: str, *sentences: str) -> None:
        nonlocal n
        n += 1
        parts.append(f"{n}. {heading}")
        for i, sentence in enumerate(sentences, start=1):
            parts.append(f"{n}.{i} {sentence}")

    clause(
        "Definitions and Interpretation",
        '"Confidential Information" means all information disclosed by one party to the other that is marked confidential or would reasonably be understood to be confidential.',
        "Clause headings are for convenience only and do not affect interpretation.",
    )

    if spec.kind != "nda":
        clause(
            "Services",
            "Supplier shall provide the Services described in each Statement of Work with reasonable skill and care.",
            "Supplier shall comply with all applicable laws in performing the Services.",
        )

    if spec.term_years is not None:
        sentences = [
            f'This Agreement commences on the Effective Date and continues for an initial term of {_num(spec.term_years)} years (the "Initial Term").'
        ]
        if spec.auto_renew_months:
            sentences.append(
                f"Following the Initial Term this Agreement shall renew automatically for successive periods of {_num(spec.auto_renew_months)} months unless either party gives not less than ninety (90) days' written notice of non-renewal."
            )
            spec.expected["auto_renewal"] = "yes"
        else:
            sentences.append(
                "This Agreement shall expire at the end of the Initial Term unless the parties agree in writing to extend it."
            )
            spec.expected["auto_renewal"] = "no"
        if spec.convenience_months:
            sentences.append(
                f"Either party may terminate this Agreement for convenience on {_num(spec.convenience_months)} months' written notice to the other."
            )
            spec.expected["termination_for_convenience"] = "yes"
        else:
            spec.expected["termination_for_convenience"] = NOT_PRESENT
        sentences.append(
            "Either party may terminate this Agreement immediately on written notice if the other party commits a material breach which is not remedied within thirty (30) days of notice."
        )
        clause("Term and Termination", *sentences)
        spec.expected["term"] = f"{_num(spec.term_years)} years"
    else:
        spec.expected["term"] = NOT_PRESENT
        spec.expected["auto_renewal"] = NOT_PRESENT
        spec.expected["termination_for_convenience"] = NOT_PRESENT

    if spec.payment_days is not None:
        clause(
            "Fees and Payment",
            f"Customer shall pay each valid invoice within {_num(spec.payment_days)} days of receipt.",
            "All sums are exclusive of VAT, which shall be payable in addition at the applicable rate.",
        )
        spec.expected["payment_terms"] = f"{_num(spec.payment_days)} days"
    else:
        spec.expected["payment_terms"] = NOT_PRESENT

    conf = [
        "Each party shall keep the other party's Confidential Information confidential and shall not disclose it except as permitted by this clause."
    ]
    if spec.confidentiality_years is not None:
        conf.append(
            f"The obligations in this clause survive termination or expiry of this Agreement for a period of {_num(spec.confidentiality_years)} years."
        )
        spec.expected["confidentiality_term"] = f"{_num(spec.confidentiality_years)} years"
    else:
        spec.expected["confidentiality_term"] = NOT_PRESENT
    clause("Confidentiality", *conf)

    if spec.data_protection:
        clause(
            "Data Protection",
            "Each party shall comply with applicable Data Protection Laws in connection with this Agreement.",
            "Supplier shall process Customer Personal Data only on Customer's documented instructions and shall implement appropriate technical and organisational measures.",
        )
        spec.expected["data_protection"] = "yes"
    else:
        spec.expected["data_protection"] = NOT_PRESENT

    if spec.indemnity:
        clause(
            "Indemnities",
            "Supplier shall indemnify Customer against all losses arising from any claim that the Services infringe a third party's intellectual property rights.",
            "The indemnified party shall notify the indemnifying party promptly of any claim.",
        )
        spec.expected["indemnity"] = "Supplier shall indemnify Customer"
    else:
        spec.expected["indemnity"] = NOT_PRESENT

    if spec.cap_pct is not None:
        clause(
            "Limitation of Liability",
            "Nothing in this Agreement limits liability for death or personal injury caused by negligence, for fraud, or for any liability which cannot be limited by law.",
            f"Subject to the preceding sub-clause, each party's total aggregate liability under or in connection with this Agreement in any Contract Year shall not exceed {_num(spec.cap_pct)} per cent of the Fees paid or payable in that Contract Year.",
            "Neither party shall be liable for any indirect or consequential loss.",
        )
        spec.expected["liability_cap"] = f"{spec.cap_pct}"
    else:
        spec.expected["liability_cap"] = NOT_PRESENT

    if spec.ip_owner is not None:
        if spec.ip_owner == "Supplier":
            clause(
                "Intellectual Property",
                "Supplier retains all intellectual property rights in the Services, the Platform and any deliverables.",
                "Customer receives a non-exclusive licence to use the deliverables for its internal business purposes.",
            )
            spec.expected["ip_ownership"] = "Supplier retains"
        else:
            clause(
                "Intellectual Property",
                "All intellectual property rights in the deliverables created under this Agreement shall vest in Customer on creation.",
                "Supplier assigns to Customer, with full title guarantee, all such rights.",
            )
            spec.expected["ip_ownership"] = "vest in Customer"
    else:
        spec.expected["ip_ownership"] = NOT_PRESENT

    if spec.exclusivity is not None:
        if spec.exclusivity:
            clause(
                "Exclusivity",
                "During the Term, Customer shall not procure services substantially similar to the Services from any third party in the Territory.",
            )
            spec.expected["exclusivity"] = "yes"
        else:
            clause(
                "Non-Exclusivity",
                "Nothing in this Agreement prevents Customer from procuring similar services from third parties, and this Agreement is non-exclusive.",
            )
            spec.expected["exclusivity"] = "no"
    else:
        spec.expected["exclusivity"] = NOT_PRESENT

    if spec.non_compete_months is not None:
        clause(
            "Restrictive Covenants",
            f"For {_num(spec.non_compete_months)} months after termination, Supplier shall not provide competing services to any Restricted Customer.",
            "Supplier acknowledges that these restrictions are reasonable and necessary to protect Customer's legitimate business interests.",
        )
        spec.expected["non_compete"] = "yes"
    else:
        spec.expected["non_compete"] = NOT_PRESENT

    if spec.assignment_consent is not None:
        if spec.assignment_consent:
            sentences = [
                "Neither party may assign this Agreement without the prior written consent of the other, such consent not to be unreasonably withheld."
            ]
            spec.expected["assignment"] = "no"
        else:
            sentences = [
                "Either party may assign this Agreement to any person on written notice to the other party."
            ]
            spec.expected["assignment"] = "yes"
        if spec.change_of_control is not None:
            if spec.change_of_control:
                sentences.append(
                    "Either party may terminate this Agreement on thirty (30) days' notice if the other party undergoes a Change of Control."
                )
                spec.expected["change_of_control"] = "yes"
            else:
                sentences.append(
                    "A Change of Control of either party shall not of itself give rise to any right of termination."
                )
                spec.expected["change_of_control"] = "no"
        else:
            spec.expected["change_of_control"] = NOT_PRESENT
        clause("Assignment", *sentences)
    else:
        spec.expected["assignment"] = NOT_PRESENT
        spec.expected["change_of_control"] = NOT_PRESENT

    if spec.dispute == "arbitration":
        dispute = f"Any dispute arising out of this Agreement shall be finally resolved by arbitration under the LCIA Rules, seated in London. This Agreement is governed by the laws of {spec.law}."
        spec.expected["dispute_resolution"] = "arbitration"
    elif spec.dispute == "expert":
        dispute = f"Any dispute as to sums payable shall be referred to an independent expert whose determination shall be final and binding; all other disputes shall be determined by {spec.courts}. This Agreement is governed by the laws of {spec.law}."
        spec.expected["dispute_resolution"] = "expert"
    else:
        dispute = f"This Agreement and any dispute arising out of it shall be governed by the laws of {spec.law}, and {spec.courts} shall have exclusive jurisdiction."
        spec.expected["dispute_resolution"] = spec.courts
    clause("Governing Law and Disputes", dispute)
    spec.expected["governing_law"] = spec.law

    parts.append("IN WITNESS WHEREOF the parties have executed this Agreement.")
    return "\n\n".join(parts)


LAWS = [
    ("England and Wales", "the courts of England and Wales"),
    ("the State of New York", "the courts located in New York County"),
    ("Scotland", "the Scottish courts"),
    ("Ireland", "the courts of Ireland"),
    ("Singapore", "the courts of Singapore"),
]

PARTIES = [
    ("Aurora Holdings Limited", "Boreal Software GmbH"),
    ("Tessellate Retail Limited", "Lumen Cloud Pty Ltd"),
    ("Kestrel Analytics Inc.", "Harrow & Vane LLP"),
    ("Meridian Logistics plc", "Coppice Systems Limited"),
    ("Threadneedle Estates Limited", "Salter Row Consulting Limited"),
]


def specs() -> list[Spec]:
    out: list[Spec] = []
    kinds = ["msa", "saas", "services", "msa", "saas"]
    for i in range(20):
        law, courts = LAWS[i % len(LAWS)]
        customer, supplier = PARTIES[i % len(PARTIES)]
        out.append(
            Spec(
                slug=f"golden_{i + 1:02d}",
                kind=kinds[i % len(kinds)],
                customer=customer,
                supplier=supplier,
                law=law,
                courts=courts,
                term_years=[1, 2, 3, 5, None][i % 5],
                convenience_months=[3, 6, None, 9, None][i % 5],
                cap_pct=[100, 125, 150, None, 200][i % 5],
                payment_days=[30, 45, 60, 14, None][i % 5],
                confidentiality_years=[2, 3, 5, None, 5][(i + 1) % 5],
                auto_renew_months=[12, None, 12, 24, None][i % 5],
                indemnity=i % 3 != 2,
                assignment_consent=[True, False, None, True, True][i % 5],
                change_of_control=[True, None, None, False, True][i % 5],
                non_compete_months=[None, 12, None, None, 6][i % 5],
                exclusivity=[True, False, None, None, True][(i + 2) % 5],
                ip_owner=["Supplier", "Customer", None, "Supplier", "Customer"][(i + 1) % 5],
                data_protection=i % 4 != 3,
                dispute=["courts", "arbitration", "courts", "expert", "courts"][i % 5],
            )
        )
    return out


def main() -> None:
    expected: dict[str, dict[str, str]] = {}
    for spec in specs():
        body = render(spec)
        write_pdf(HERE / f"{spec.slug}.pdf", body)
        expected[f"{spec.slug}.pdf"] = {q["key"]: spec.expected[q["key"]] for q in QUESTIONS}
    (HERE / "questions.yaml").write_text(
        yaml.safe_dump(QUESTIONS, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )
    (HERE / "expected.yaml").write_text(
        yaml.safe_dump(expected, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {len(expected)} contracts, {len(QUESTIONS)} questions to {HERE}")


if __name__ == "__main__":
    main()
