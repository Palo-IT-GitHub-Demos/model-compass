"""Build the generic-screen-v3 quality suite and its use-case catalog.

This script is the source of ``data/prompts/quality_prompts_v3.json`` and
``data/catalog/model_compass_use_cases_v3.json``: change an item here, never
in the JSON. Kept v2 items are copied verbatim; every new item's expected value
is computed here, and every code item's reference solution must pass its own
tests in the real sandbox before anything is written. Changing an item changes
``quality_suite_id`` and therefore run comparability.

Usage
-----
    python scripts/build_quality_suite_v3.py           # rewrite both files
    python scripts/build_quality_suite_v3.py --check   # exit 1 if a committed file differs
"""

from __future__ import annotations

import argparse
import calendar
import itertools
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluators.code_sandbox import find_policy_violation, run_python_tests  # noqa: E402

SUITE_PATH = ROOT / "data/prompts/quality_prompts_v3.json"
CATALOG_PATH = ROOT / "data/catalog/model_compass_use_cases_v3.json"

V2 = {
    item["item_id"]: item
    for item in json.loads((ROOT / "data/prompts/quality_prompts_v2.json").read_text(encoding="utf-8"))
}
COMMON = {
    "language": "en",
    "difficulty_status": "draft",
    "license_status": "internal_original",
    "contamination_status": "internal_unscreened",
}
IMPORTS = (
    "You may import only from these standard-library modules: collections, datetime, functools, itertools, "
    "math, re, string and typing."
)
CODE_TAIL = " Return the raw source code with no markdown code fences, no explanation and no other text. " + IMPORTS


def keep(item_id: str) -> dict:
    return dict(V2[item_id])


def exact(item_id, use_case, construct, difficulty, prompt, answer, *, category="exact_answer", dimension):
    return {
        "prompt": prompt,
        "category": category,
        "quality_dimension": dimension,
        "accepted_answers": [answer],
        "strict_output": True,
        "item_id": item_id,
        "use_case_id": use_case,
        "construct": construct,
        "task_type": "free_response",
        "difficulty": difficulty,
        "evaluator": "exact_match",
        **COMMON,
    }


def json_item(item_id, construct, difficulty, prompt, expected):
    return {
        "prompt": prompt,
        "category": "json_output",
        "quality_dimension": "structured_output",
        "expected_json": expected,
        "strict_output": True,
        "item_id": item_id,
        "use_case_id": "structured_extraction",
        "construct": construct,
        "task_type": "json",
        "difficulty": difficulty,
        "evaluator": "json_exact",
        **COMMON,
    }


def code_item(item_id, construct, difficulty, prompt, function, parameters, reference, calls, criteria):
    namespace: dict = {}
    exec(reference, namespace)  # noqa: S102 - our own reference solution
    cases = [{"args": list(args), "expected": namespace[function](*args)} for args in calls]
    assert find_policy_violation(reference) is None, (item_id, find_policy_violation(reference))
    outcome = run_python_tests(reference, function, cases)
    assert outcome.status == "ok" and outcome.passed == outcome.total, (item_id, outcome)
    return {
        "prompt": prompt + CODE_TAIL,
        "category": "code_execution",
        "quality_dimension": "code_correctness",
        "required_function": function,
        "required_parameters": parameters,
        "strict_output": True,
        "test_cases": cases,
        "judge_criteria": criteria,
        "reference_answer": reference.strip(),
        "item_id": item_id,
        "use_case_id": "code_generation",
        "construct": construct,
        "task_type": "programmatic",
        "difficulty": difficulty,
        "evaluator": "sandbox_tests",
        **COMMON,
    }


def judged(item_id, use_case, dimension, construct, difficulty, prompt, criteria, reference, anchors):
    return {
        "prompt": prompt,
        "category": "generic_judgment",
        "quality_dimension": dimension,
        "judge_criteria": criteria,
        "reference_answer": reference,
        "item_id": item_id,
        "use_case_id": use_case,
        "construct": construct,
        "task_type": "free_response",
        "difficulty": difficulty,
        "evaluator": "rubric_panel",
        **COMMON,
        "rubric_version": "rubric-v2",
        "rubric_anchors": {"1": anchors[0], "3": anchors[1], "5": anchors[2]},
    }


CODE_CRITERIA = [
    "The response is a Python function with the required name and parameters.",
    "The function returns the specified result for every example in the description and for the stated edge cases.",
    "The response contains source code only and imports only the allowed modules.",
]

items: list[dict] = []

# ── Structured extraction ────────────────────────────────────────────────────
items += [keep("structured_extraction-01"), keep("structured_extraction-04")]
# OpenRouter guardrails mask "JSON array" as an address; the item must reach the models as written.
items[1]["prompt"] = items[1]["prompt"].replace("exactly one JSON array", "exactly one array in JSON format")
# The v3.0 items -05, -06 and -07 were answered perfectly by every model of the 2 November run: they are
# replaced by longer tasks that track state, derive values or aggregate, with partial credit per field.
# Product words, not codes: the gateway masked the code "P-412" as an address.
ORDER_LOG = [
    ("add", "lamp", 3),
    ("add", "cable", 2),
    ("add", "stand", 1),
    ("set", "lamp", 5),
    ("remove", "cable", 0),
    ("add", "cable", 4),
    ("add", "lamp", 2),
    ("undo", 6, 0),
    ("add", "mouse", 2),
    ("set", "mouse", 0),
]
STEP_TEXT = {
    "add": "Add {qty} x {target}.",
    "set": "Change the quantity of {target} to {qty}.",
    "remove": "Remove {target} from the order.",
    "undo": "Undo step {target}.",
}


def replay(log: list[tuple[str, object, int]]) -> dict[str, int]:
    undone = {target for op, target, _ in log if op == "undo"}
    basket: dict[str, int] = {}
    for step, (op, target, qty) in enumerate(log, start=1):
        if step in undone or op == "undo":
            continue
        sku = str(target)
        if op == "add":
            basket[sku] = basket.get(sku, 0) + qty
        elif op == "set":
            basket[sku] = qty
        else:
            basket.pop(sku, None)
    return {sku: qty for sku, qty in sorted(basket.items()) if qty > 0}


items.append(
    json_item(
        "structured_extraction-09",
        "state_tracking_over_edits",
        "hard",
        "Replay this order log and return exactly one JSON object, with no markdown or extra text, that maps each "
        "product still in the order to its final quantity (integer). An undone step has no effect at all, as if it "
        "had never been written. Leave out products whose final quantity is zero or that were removed.\nOrder log:\n"
        + "\n".join(
            f"{step}. " + STEP_TEXT[op].format(target=target, qty=qty)
            for step, (op, target, qty) in enumerate(ORDER_LOG, start=1)
        ),
        replay(ORDER_LOG),
    )
)
INVOICE = [("Widget", 3, "4.50", 0), ("Cable", 2, "12.00", 10), ("Adapter", 5, "0.99", 0), ("Stand", 1, "25.00", 20)]
line_cents = {name: qty * Fraction(price) * 100 * (100 - off) / 100 for name, qty, price, off in INVOICE}
assert all(value.denominator == 1 for value in line_cents.values())
invoice_total = {name: int(value) for name, value in line_cents.items()}
invoice_total["total"] = sum(invoice_total.values())
items.append(
    json_item(
        "structured_extraction-10",
        "derived_values_from_table",
        "hard",
        "Return exactly one JSON object, with no markdown or extra text, whose keys are the product names and whose "
        "values are each line's total in cents after its discount (integer), plus a key `total` with the sum of the "
        "lines in cents.\nInvoice lines (product | quantity | unit price in dollars | discount on the line):\n"
        + "\n".join(
            f"{name} | {qty} | {price} | " + (f"{off}% off" if off else "none") for name, qty, price, off in INVOICE
        ),
        invoice_total,
    )
)
TICKETS = [
    ("T1", "web", "open"),
    ("T2", "api", "closed"),
    ("T3", "web", "closed"),
    ("T4", "data", "open"),
    ("T5", "api", "reopened"),
    ("T6", "web", "open"),
    ("T7", "data", "closed"),
    ("T8", "api", "closed"),
    ("T9", "web", "cancelled"),
    ("T10", "data", "reopened"),
]
team_counts: dict[str, dict[str, int]] = {}
for _, team, status in TICKETS:
    if status == "cancelled":
        continue
    counts = team_counts.setdefault(team, {"open": 0, "closed": 0})
    counts["closed" if status == "closed" else "open"] += 1
items.append(
    json_item(
        "structured_extraction-11",
        "grouped_counts_with_rules",
        "hard",
        "Return exactly one JSON object, with no markdown or extra text, with one key per team and, for each team, an "
        "object with the integer keys `open` and `closed`. A reopened ticket counts as open; a cancelled ticket is "
        "ignored.\nTickets (id | team | status):\n"
        + "\n".join(f"{ticket} | {team} | {status}" for ticket, team, status in TICKETS),
        team_counts,
    )
)
weights = [("A-17", 1.2 * 1000), ("B-03", 350), ("C-88", 0.05 * 1000)]
items.append(
    json_item(
        "structured_extraction-08",
        "unit_normalisation",
        "medium",
        "Return exactly one array in JSON format, with no markdown or extra text, with one object per line of the "
        "packing list, "
        "in the same order, with the keys `sku` (string) and `weight_g` (integer, in grams).\nPacking list:\n"
        "A-17 | 1.2 kg\nB-03 | 350 g\nC-88 | 0.05 kg",
        [{"sku": sku, "weight_g": round(grams)} for sku, grams in weights],
    )
)

# ── Code generation ──────────────────────────────────────────────────────────
for item_id in ("code_generation-01", "code_generation-02"):
    item = keep(item_id)
    item["prompt"] = item["prompt"].replace("Only the Python standard library may be imported.", IMPORTS)
    items.append(item)
items.append(
    code_item(
        "code_generation-10",
        "precedence_rules_with_prerelease",
        "hard",
        "Write only a Python function `compare_versions(a: str, b: str) -> int` that returns -1, 0 or 1 as version `a` "
        "is lower than, equal to or higher than version `b`. A version is one to three dot-separated integers, "
        "missing parts count as 0 (so '1.2' equals '1.2.0'), optionally followed by a hyphen and a pre-release made of "
        "dot-separated identifiers, such as '2.0.0-rc.1'. Numbers compare numerically. When the numbers are equal, a "
        "version with a pre-release is lower than the same version without one; two pre-releases compare identifier "
        "by identifier, numerically when both are digits, alphabetically when both are not, a numeric identifier is "
        "lower than a non-numeric one, and when all shared identifiers are equal the pre-release with fewer "
        "identifiers is lower.",
        "compare_versions",
        ["a", "b"],
        """
def compare_versions(a, b):
    def parse(version):
        core, _, pre = version.partition("-")
        numbers = [int(part) for part in core.split(".")]
        numbers += [0] * (3 - len(numbers))
        return numbers, pre.split(".") if pre else []

    numbers_a, pre_a = parse(a)
    numbers_b, pre_b = parse(b)
    if numbers_a != numbers_b:
        return -1 if numbers_a < numbers_b else 1
    if not pre_a or not pre_b:
        return (len(pre_b) > 0) - (len(pre_a) > 0)
    for left, right in zip(pre_a, pre_b):
        if left == right:
            continue
        if left.isdigit() and right.isdigit():
            return -1 if int(left) < int(right) else 1
        if left.isdigit() != right.isdigit():
            return -1 if left.isdigit() else 1
        return -1 if left < right else 1
    return (len(pre_a) > len(pre_b)) - (len(pre_a) < len(pre_b))
""",
        [
            ("1.2.0", "1.10.0"),
            ("1.2", "1.2.0"),
            ("2.0.0-rc.1", "2.0.0"),
            ("2.0.0-rc.2", "2.0.0-rc.10"),
            ("1.0.0-alpha", "1.0.0-1"),
            ("1.0.0-alpha", "1.0.0-alpha.1"),
            ("1.0.0-beta", "1.0.0-alpha.9"),
            ("3.1.4", "3.1.4"),
            ("0.10.1", "0.9"),
            ("2", "1.99.99"),
        ],
        CODE_CRITERIA,
    )
)
items.append(
    code_item(
        "code_generation-07",
        "validation_of_canonical_form",
        "hard",
        "Write only a Python function `roman_to_int(numeral: str) -> int` that converts an uppercase Roman numeral in "
        "standard form, between 1 and 3999, to an integer, and returns -1 for any text that is not a standard-form "
        "numeral, such as 'IIII', 'IC', 'VX', 'MMMM' or an empty string.",
        "roman_to_int",
        ["numeral"],
        r"""
import re

_FORM = re.compile(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})")
_VALUES = {"M": 1000, "D": 500, "C": 100, "L": 50, "X": 10, "V": 5, "I": 1}

def roman_to_int(numeral):
    if not numeral or not _FORM.fullmatch(numeral):
        return -1
    total = 0
    for index, letter in enumerate(numeral):
        value = _VALUES[letter]
        following = _VALUES[numeral[index + 1]] if index + 1 < len(numeral) else 0
        total += -value if value < following else value
    return total
""",
        [("MCMXCIV",), ("XLII",), ("MMXXVI",), ("IIII",), ("IC",), ("VX",), ("",), ("MMMM",), ("MMMCMXCIX",)],
        CODE_CRITERIA,
    )
)
items.append(
    code_item(
        "code_generation-11",
        "sweep_line_with_boundaries",
        "hard",
        "Write only a Python function `max_overlap(sessions: list[list[int]]) -> int` that returns the largest number "
        "of sessions active at the same moment. Each session is [start, end] with the end excluded, so a session "
        "ending at 5 and one starting at 5 never overlap; a session whose end is not after its start is ignored; an "
        "empty list returns 0.",
        "max_overlap",
        ["sessions"],
        """
def max_overlap(sessions):
    events = []
    for start, end in sessions:
        if end > start:
            events.append((start, 1))
            events.append((end, -1))
    best = current = 0
    for _, delta in sorted(events):
        current += delta
        best = max(best, current)
    return best
""",
        [
            ([[1, 5], [2, 6], [5, 7]],),
            ([[1, 2], [2, 3], [3, 4]],),
            ([],),
            ([[3, 3], [1, 4]],),
            ([[0, 10], [1, 9], [2, 8], [8, 9]],),
            ([[5, 1], [1, 2]],),
            ([[4, 6], [1, 5], [5, 9], [6, 7], [5, 6]],),
        ],
        CODE_CRITERIA,
    )
)
items.append(
    code_item(
        "code_generation-09",
        "frequency_ranking_with_ties",
        "medium",
        "Write only a Python function `top_k_words(text: str, k: int) -> list[str]` that counts the words of `text` "
        "case-insensitively (a word is a run of letters a to z), and returns the `k` most frequent words in lowercase, "
        "most frequent first, breaking ties alphabetically; it returns fewer words when the text has fewer than `k`.",
        "top_k_words",
        ["text", "k"],
        r"""
import re
from collections import Counter

def top_k_words(text, k):
    counts = Counter(re.findall(r"[a-z]+", text.lower()))
    return [word for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:k]]
""",
        [
            ("the cat and the hat and THE bat", 2),
            ("b a b a c", 3),
            ("Delta, alpha; delta! Alpha? beta", 2),
            ("", 3),
            ("one two three", 5),
        ],
        CODE_CRITERIA,
    )
)

# ── Contextual question answering ────────────────────────────────────────────
QA = "contextual_qa"
# The v3.0 items -06 to -10 were answered by every model of the 2 November run; each replacement keeps a
# construct but adds state to track, a rule that overrides another, or a tempting value that is not stated.
rooms = {"design review": "2.10", "budget meeting": "3.01"}
rooms["design review"] = "3.01"
rooms["budget meeting"] = "2.10"
rooms = {meeting: "1.05" if room == "2.10" else room for meeting, room in rooms.items()}
rooms["design review"], rooms["budget meeting"] = rooms["budget meeting"], rooms["design review"]
items.append(
    exact(
        "contextual_qa-12",
        QA,
        "state_tracking_over_updates",
        "hard",
        "Context: Booking log, in order. 1) The design review is booked in room 2.10. 2) The budget meeting is booked "
        "in room 3.01. 3) The design review moves to room 3.01. 4) Because of the clash, the budget meeting moves to "
        "room 2.10. 5) Room 2.10 closes for repairs; every meeting booked there moves to room 1.05. 6) Room 2.10 "
        "reopens, but meetings stay where they are. 7) The design review and the budget meeting swap rooms.\n"
        "Question: In which room is the budget meeting now? Reply with the room number only.",
        rooms["budget meeting"],
        dimension="contextual_accuracy",
    )
)
items.append(
    exact(
        "contextual_qa-13",
        QA,
        "overriding_exception",
        "hard",
        "Context: Refunds are allowed within 30 days of delivery. Exception A: downloaded digital products are not "
        "refundable. Exception B, which takes precedence over exception A: a defective product is refundable within 90 "
        "days of delivery.\nCase: a digital product, already downloaded, found defective, delivered 45 days ago.\n"
        "Question: Is the customer entitled to a refund? Reply with YES or NO only.",
        "YES" if 45 <= 90 else "NO",
        dimension="contextual_accuracy",
    )
)
activation = (2025, 8)
months = 18 + 2
expiry_month = activation[1] - 1 + months
expiry = f"{activation[0] + expiry_month // 12}-{expiry_month % 12 + 1:02d}-15"
items.append(
    exact(
        "contextual_qa-14",
        QA,
        "date_arithmetic_with_extension",
        "hard",
        "Context: A licence expires exactly 18 months after its activation, on the same day of the month. This licence "
        "was activated on 15 August 2025. It was later suspended for 2 months, and a suspension extends the expiry by "
        "the same number of months.\nQuestion: On what date does the licence expire? Reply with the date only, as "
        "YYYY-MM-DD.",
        expiry,
        dimension="contextual_accuracy",
    )
)
items.append(
    exact(
        "contextual_qa-15",
        QA,
        "abstention_against_estimate",
        "hard",
        "Context: The annual report gives revenue for the first three quarters of 2025: 4.1, 3.8 and 4.4 million. The "
        "fourth-quarter figure will be published in March. Analysts expect a fourth quarter similar to the third.\n"
        "Question: What was the total revenue for 2025, in millions? If the context does not give it, reply exactly "
        "NOT STATED.",
        "NOT STATED",
        dimension="contextual_accuracy",
    )
)
APPLICANTS = [(2023, 12, None), (2025, 8, None), (2019, 50, 2018), (2020, 49, 2023), (2022, 30, 2022), (2010, 5, 2024)]
eligible = sum(
    founded <= 2024 and staff < 50 and (grant is None or grant < 2024) for founded, staff, grant in APPLICANTS
)
items.append(
    exact(
        "contextual_qa-16",
        QA,
        "multi_condition_count",
        "hard",
        "Context: A grant requires all of the following: the company was founded in 2024 or earlier, it has fewer than "
        "50 employees, and it has not received a grant in 2024 or later.\nApplicants:\n"
        + "\n".join(
            f"Applicant {index}: founded in {founded}, {staff} employees, "
            + ("no previous grant." if grant is None else f"previous grant in {grant}.")
            for index, (founded, staff, grant) in enumerate(APPLICANTS, start=1)
        )
        + "\nQuestion: How many applicants are eligible? Reply with the number only.",
        str(eligible),
        dimension="contextual_accuracy",
    )
)
items.append(
    exact(
        "contextual_qa-11",
        QA,
        "aggregation_with_exclusions",
        "hard",
        "Context: Warehouse stock: W1 holds 1,200 units; W2 holds 950 units; W3 holds 2 pallets of 400 units each; W4 "
        "is closed and holds 300 units awaiting transfer to another warehouse.\nQuestion: How many units can be "
        "shipped today from the "
        "open warehouses? Reply with the number only, without separators.",
        str(1200 + 950 + 2 * 400),
        dimension="contextual_accuracy",
    )
)

# ── Reasoning and analysis ───────────────────────────────────────────────────
RA = "reasoning_analysis"
items.append(keep("reasoning_analysis-01"))
BOOKINGS = [(9 * 60 + 40, 11 * 60 + 15), (13 * 60 + 5, 14 * 60 + 50)]
slot = next(
    start
    for start in range(9 * 60, 15 * 60 - 70 + 1, 5)
    if all(start + 70 <= begin - 10 or start >= end + 10 for begin, end in BOOKINGS)
)
items.append(
    exact(
        "reasoning_analysis-11",
        RA,
        "scheduling_with_buffers",
        "hard",
        "A room is booked from 09:40 to 11:15 and from 13:05 to 14:50. A team needs a 70-minute slot between 09:00 and "
        "15:00 that starts on a multiple of 5 minutes and keeps at least 10 minutes free before every booking starts "
        "and after every booking ends. What is the earliest possible start time? Reply with the time only, as HH:MM.",
        f"{slot // 60:02d}:{slot % 60:02d}",
        category="logical_reasoning",
        dimension="elementary_reasoning",
    )
)


def truth_tellers() -> str:
    solutions = []
    for a, b, c in itertools.product([True, False], repeat=3):
        statements = (not b, not c, (not a) and (not b))
        if all(said == honest for said, honest in zip(statements, (a, b, c), strict=True)):
            solutions.append("".join(name for name, honest in zip("ABC", (a, b, c), strict=True) if honest))
    assert len(solutions) == 1, solutions
    return solutions[0]


items.append(
    exact(
        "reasoning_analysis-07",
        RA,
        "consistency_reasoning",
        "hard",
        "Each of A, B and C either always tells the truth or always lies. A says: 'B is a liar.' B says: 'C is a "
        "liar.' C says: 'A and B are both liars.' Who tells the truth? Reply with the letter only.",
        truth_tellers(),
        category="logical_reasoning",
        dimension="elementary_reasoning",
    )
)
PROJECTS = [8, 14, 17]
EXAM = 12
kept = sorted(PROJECTS)[1:] if EXAM >= 12 else PROJECTS
grade = Fraction(4, 10) * EXAM + Fraction(6, 10) * Fraction(sum(kept), len(kept))
assert (grade * 10).denominator == 1
items.append(
    exact(
        "reasoning_analysis-12",
        RA,
        "conditional_weighted_average",
        "hard",
        "A course grade out of 20 is 40% exam and 60% projects. The project mark is the average of the project marks, "
        "but the lowest project mark is dropped when the exam mark is at least 12. A student has an exam mark of 12 "
        "and project marks of 8, 14 and 17. What is the course grade? Reply with the number only, with one decimal.",
        f"{float(grade):.1f}",
        category="logical_reasoning",
        dimension="elementary_reasoning",
    )
)
items.append(
    exact(
        "reasoning_analysis-09",
        RA,
        "combinatorial_counting",
        "medium",
        "How many three-digit numbers have digits that add up to 5? Reply with the number only.",
        str(sum(1 for n in range(100, 1000) if sum(map(int, str(n))) == 5)),
        category="logical_reasoning",
        dimension="elementary_reasoning",
    )
)
probability = Fraction(3, 5) * Fraction(2, 4)
items.append(
    exact(
        "reasoning_analysis-10",
        RA,
        "probability_without_replacement",
        "medium",
        "A bag holds 3 red balls and 2 blue balls. Two balls are drawn without replacement. What is the probability "
        "that both are red? Reply with a simplified fraction such as 1/4, and nothing else.",
        f"{probability.numerator}/{probability.denominator}",
        category="logical_reasoning",
        dimension="elementary_reasoning",
    )
)

# ── Classification and routing ───────────────────────────────────────────────
CR = "classification_routing"
LABELS = "Classify the message into exactly one label from BILLING, TECHNICAL, ACCOUNT, OTHER. "
# The v3.0 items -07 to -10 and -12 were answered by every model of the 2 November run; each replacement
# makes an explicit rule decide against the most obvious keyword.
BATCH = [
    ("I see error 500 when I open my invoice.", "BILLING"),
    ("How do I change the phone number on my profile?", "ACCOUNT"),
    ("The password reset page shows error 403.", "TECHNICAL"),
    ("Do you have offices abroad?", "OTHER"),
    ("Please refund the charge from the failed payment; the app froze during checkout.", "BILLING"),
]
batch_labels = [label for _, label in BATCH]
item = exact(
    "classification_routing-13",
    CR,
    "batch_routing_with_precedence",
    "hard",
    "Route each message to one queue from BILLING, TECHNICAL, ACCOUNT, OTHER with these rules, in order: a message "
    "about a charge, an invoice or a refund is BILLING even if it also reports an error; a message about login, "
    "password or profile is ACCOUNT, unless it reports an error code, then it is TECHNICAL; any other error is "
    "TECHNICAL; anything else is OTHER. Reply with the five labels in order, separated by a comma and a space, and "
    "nothing else.\n" + "\n".join(f"{index}. '{text}'" for index, (text, _) in enumerate(BATCH, start=1)),
    ", ".join(batch_labels),
    dimension="classification_accuracy",
)
item["accepted_answers"] = [", ".join(batch_labels), ",".join(batch_labels)]
items.append(item)
items.append(
    exact(
        "classification_routing-14",
        CR,
        "scope_of_sentiment",
        "hard",
        "Classify the review as POSITIVE, NEGATIVE or MIXED. MIXED means the review both clearly praises and clearly "
        "criticises the product itself; complaints about delivery or the courier do not count. Reply with the label "
        "only.\nReview: 'Shipping took two weeks, which is the courier's fault, but the blender itself is excellent "
        "and surprisingly quiet.'",
        "POSITIVE",
        dimension="classification_accuracy",
    )
)
items.append(
    exact(
        "classification_routing-15",
        CR,
        "rule_overrides_count",
        "hard",
        "Assign a priority with these rules: P1 if more than 100 users are affected or if any payment fails; P2 if 10 "
        "to 100 users are affected; P3 otherwise. Reply with the label only.\nTicket: 'About 40 users cannot export "
        "reports since this morning. One of them adds that a card payment failed twice today.'",
        "P1",
        dimension="classification_accuracy",
    )
)
items.append(
    exact(
        "classification_routing-16",
        CR,
        "intent_over_keyword",
        "medium",
        LABELS + "Reply with the label only.\nMessage: 'A colleague says your billing page takes a full minute to "
        "load. Our bills are correct; we only want to know whether this slowness is a known bug.'",
        "TECHNICAL",
        dimension="classification_accuracy",
    )
)
items.append(
    exact(
        "classification_routing-17",
        CR,
        "abstention_on_tie",
        "hard",
        "Route the message to exactly one queue: BILLING, TECHNICAL, ACCOUNT or UNCLEAR. Use UNCLEAR when the message "
        "raises issues for two or more queues and does not say which one matters more. Reply with the label only.\n"
        "Message: 'I was charged twice this month and I can no longer log in to my account.'",
        "UNCLEAR",
        dimension="classification_accuracy",
    )
)
items.append(
    exact(
        "classification_routing-11",
        CR,
        "rule_based_priority",
        "hard",
        "Assign a priority using these rules: P1 = the service is down for all users; P2 = a feature is broken for "
        "some users and a workaround exists; P3 = a question or a cosmetic issue. Reply with the label only.\nTicket: "
        "'Since this morning nobody in the company can log in; meanwhile we use the old portal.'",
        "P1",
        dimension="classification_accuracy",
    )
)

# ── Summarization ────────────────────────────────────────────────────────────
SU = "summarization"
items += [keep("summarization-01"), keep("summarization-02"), keep("summarization-03")]
items.append(
    judged(
        "summarization-04",
        SU,
        "summarization_quality",
        "latest_information_wins",
        "hard",
        "Write a status summary of at most two sentences for the steering committee, using the most recent "
        "information.\nMessage 1 (Monday): 'Migration on track for 15 May; budget 120k.'\nMessage 2 (Thursday): "
        "'Vendor delay: the migration moves to 29 May; the budget is unchanged; the testing team needs two extra "
        "people.'",
        [
            "Gives 29 May as the migration date and does not present 15 May as current.",
            "States that the budget is unchanged at 120k.",
            "Mentions that testing needs two extra people.",
            "Uses at most two sentences.",
        ],
        "Because of a vendor delay, the migration moves to 29 May with the budget unchanged at 120k; the testing team "
        "needs two extra people.",
        (
            "The migration is on track for 15 May.",
            "The migration is delayed to 29 May because of the vendor.",
            "A vendor delay moves the migration to 29 May; the 120k budget is unchanged, and testing needs two more "
            "people.",
        ),
    )
)
items.append(
    judged(
        "summarization-05",
        SU,
        "summarization_quality",
        "numeric_fidelity",
        "hard",
        "Summarize the incident report in at most 50 words for the support team.\nReport: 'Between 09:12 and 09:47 "
        "UTC, 18% of payment requests in the EU region failed with timeout errors. The cause was a misconfigured "
        "load-balancer rule deployed at 09:05. The rule was rolled back at 09:44. No payment was charged twice. A "
        "post-mortem is scheduled for Friday.'",
        [
            "States the 09:12 to 09:47 UTC window and the 18% of EU payment requests that failed.",
            "Names the misconfigured load-balancer rule as the cause and its rollback.",
            "States that no payment was charged twice.",
            "Uses at most 50 words and adds no fact absent from the report.",
        ],
        "From 09:12 to 09:47 UTC, 18% of EU payment requests timed out because of a misconfigured load-balancer rule, "
        "rolled back at 09:44. No payment was charged twice; a post-mortem is planned for Friday.",
        (
            "Payments failed this morning because of a database outage, and some customers were charged twice.",
            "Some EU payments failed this morning because of a load-balancer rule, now rolled back.",
            "From 09:12 to 09:47 UTC, 18% of EU payment requests timed out due to a misconfigured load-balancer rule, "
            "rolled back at 09:44; no double charges; post-mortem on Friday.",
        ),
    )
)
items.append(
    judged(
        "summarization-06",
        SU,
        "summarization_quality",
        "structured_summary_constraint",
        "medium",
        "Summarize the policy change for employees in exactly three bullet points.\nText: 'From 1 January, travel "
        "above 500 EUR needs manager approval in the new travel tool instead of by email. Train travel is mandatory "
        "for trips under four hours. Hotel limits stay unchanged. Receipts must be uploaded within 10 days, down "
        "from 30.'",
        [
            "Uses exactly three bullet points.",
            "States that travel above 500 EUR needs manager approval in the new tool from 1 January.",
            "States the train rule for trips under four hours and the 10-day receipt deadline.",
            "Does not claim that hotel limits change.",
        ],
        "- From 1 January, trips above 500 EUR need manager approval in the new travel tool.\n- Take the train for "
        "trips under four hours.\n- Upload receipts within 10 days (previously 30).",
        (
            "- Hotel limits are lower from 1 January.\n- Travel is now free.",
            "- Approval above 500 EUR now goes through the new tool.\n- Trains are encouraged.\n- Receipts are due "
            "sooner.",
            "- From 1 January, manager approval for trips above 500 EUR is given in the new travel tool.\n- Train is "
            "mandatory for trips under four hours.\n- Receipts are due within 10 days instead of 30.",
        ),
    )
)

# ── Concise communication ────────────────────────────────────────────────────
CC = "concise_communication"
items.append(keep("concise_communication-01"))
items.append(
    judged(
        "concise_communication-04",
        CC,
        "concise_communication",
        "declining_without_promise",
        "hard",
        "Write a reply of at most 50 words telling a customer that the feature they asked for will not be built this "
        "year. Do not promise any date, and offer one alternative: the existing CSV export.",
        [
            "States clearly that the feature will not be built this year.",
            "Gives no date and makes no promise about the feature.",
            "Offers the existing CSV export as the alternative.",
            "Uses at most 50 words and stays polite.",
        ],
        "Thank you for the suggestion. We will not build this feature this year, so I cannot give you a date. In the "
        "meantime, the existing CSV export lets you get the same data today.",
        (
            "Great idea, we will ship it next month!",
            "We are not planning this feature right now, sorry.",
            "Thanks for the idea. It will not be built this year and we have no date to share, but the existing CSV "
            "export gives you the same data now.",
        ),
    )
)
items.append(
    judged(
        "concise_communication-05",
        CC,
        "concise_communication",
        "jargon_removal_with_fact_retention",
        "hard",
        "Rewrite this for a non-technical executive in at most two sentences: 'p95 latency "
        "regressed from 180 ms to 420 ms after the ORM upgrade; we are reverting tonight and expect baseline by "
        "08:00.'",
        [
            "Explains that the slowest responses became more than twice as slow after a software update.",
            "States that the update is being undone tonight.",
            "States that normal speed is expected by 08:00.",
            "Uses no unexplained jargon such as p95 or ORM, in at most two sentences.",
        ],
        "After a software update, our slowest responses became more than twice as slow. We are undoing the update "
        "tonight and expect normal speed by 8:00.",
        (
            "p95 latency regressed after the ORM upgrade.",
            "A recent update slowed the system down; we are fixing it.",
            "Since a software update, the slowest pages take more than twice as long; we roll it back "
            "tonight and expect "
            "normal speed by 8:00.",
        ),
    )
)
items.append(
    judged(
        "concise_communication-06",
        CC,
        "concise_communication",
        "scope_control",
        "medium",
        "A client writes in a chat: 'Can you also redo our logo while you are at it? Same budget.' Write a reply of at "
        "most 45 words that declines the logo work within the current budget and proposes a separate quote.",
        [
            "Declines doing the logo within the current budget.",
            "Proposes a separate quote for the logo.",
            "Stays positive and professional.",
            "Uses at most 45 words.",
        ],
        "Happy to help with the logo, but it is outside the current scope and budget. I can send you a separate quote "
        "for it this week.",
        (
            "Sure, we will add the logo at no extra cost.",
            "The logo is not included, sorry.",
            "Glad you asked! The logo is outside the current budget, so I will send you a separate quote for it this "
            "week.",
        ),
    )
)
items.append(
    judged(
        "concise_communication-07",
        CC,
        "concise_communication",
        "subject_line_density",
        "medium",
        "Write an email subject line of at most 8 words announcing that the office is closed on 14 July and that "
        "support stays available by phone. Reply with the subject line only.",
        [
            "Mentions the office closure.",
            "Mentions 14 July.",
            "Mentions that phone support remains available.",
            "Uses at most 8 words and contains only the subject line.",
        ],
        "Office closed 14 July, phone support stays open",
        (
            "Important information about the summer",
            "Office closed on 14 July",
            "Office closed 14 July; phone support still available",
        ),
    )
)
items.append(
    judged(
        "concise_communication-08",
        CC,
        "concise_communication",
        "acknowledgement_completeness",
        "hard",
        "A customer sends a long, angry email about three late deliveries, a wrong invoice and no reply from support. "
        "Write a one-sentence acknowledgement of at most 35 words that names all three problems and says that the "
        "delivery team will reply by tomorrow.",
        [
            "Names the late deliveries, the wrong invoice and the missing support reply.",
            "Says that the delivery team will reply by tomorrow.",
            "Is a single sentence of at most 35 words.",
            "Acknowledges the frustration without blaming the customer.",
        ],
        "I am sorry about the three late deliveries, the wrong invoice and our missing reply; the delivery team will "
        "get back to you by tomorrow.",
        (
            "Please calm down, we are doing our best.",
            "Sorry for the late deliveries; someone will contact you soon.",
            "I am sorry for the three late deliveries, the incorrect invoice and our silence; the delivery team will "
            "reply to you by tomorrow.",
        ),
    )
)

# ── Instruction following ────────────────────────────────────────────────────
IF = "instruction_following"
six_letter_days = [day.lower() for day in calendar.day_name if len(day) == 6][::-1]
items.append(
    exact(
        "instruction_following-10",
        IF,
        "filter_then_reverse",
        "hard",
        "Take the English names of the days of the week from Monday to Sunday, keep only the names that have exactly "
        "six letters, then write them in reverse order, in lowercase, separated by single spaces, and nothing else.",
        " ".join(six_letter_days),
        category="instruction_following",
        dimension="instruction_reliability",
    )
)
word = "pipeline"
stripped = "".join(letter for letter in word if letter not in "aeiou")
items.append(
    exact(
        "instruction_following-06",
        IF,
        "transformation_with_count",
        "medium",
        "Reply with the word 'pipeline' with all its vowels removed, then a hyphen, then the number of vowels you "
        "removed, and nothing else.",
        f"{stripped}-{len(word) - len(stripped)}",
        category="instruction_following",
        dimension="instruction_reliability",
    )
)
words = ["delta", "ox", "alpha", "be", "cat", "ant"]
items.append(
    exact(
        "instruction_following-07",
        IF,
        "sort_with_tie_rule",
        "hard",
        "Sort these words by length, shortest first, keeping words of the same length in alphabetical order, and "
        "output them separated by single spaces and nothing else: delta, ox, alpha, be, cat, ant",
        " ".join(sorted(words, key=lambda w: (len(w), w))),
        category="instruction_following",
        dimension="instruction_reliability",
    )
)


def roman(number: int) -> str:
    out = ""
    for value, letters in (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ):
        while number >= value:
            out += letters
            number -= value
    return out


items.append(
    exact(
        "instruction_following-08",
        IF,
        "dual_encoding",
        "hard",
        "Write the number 2026 in Roman numerals, then one space, then the same number in binary, and nothing else.",
        f"{roman(2026)} {2026:b}",
        category="instruction_following",
        dimension="instruction_reliability",
    )
)
fruit = "banana"
items.append(
    exact(
        "instruction_following-09",
        IF,
        "filter_reverse_count",
        "hard",
        "Take the letters of 'banana' that are not 'a', write them in the reverse of their order of appearance, then "
        "a colon, then the number of letters 'a' in the word, and nothing else.",
        "".join(letter for letter in fruit if letter != "a")[::-1] + f":{fruit.count('a')}",
        category="instruction_following",
        dimension="instruction_reliability",
    )
)
items.append(keep("instruction_following-04"))

# ── Write and validate ───────────────────────────────────────────────────────
ORDER = [
    "structured_extraction",
    "code_generation",
    "contextual_qa",
    "reasoning_analysis",
    "classification_routing",
    "summarization",
    "concise_communication",
    "instruction_following",
]
items.sort(key=lambda item: ORDER.index(item["use_case_id"]))
ids = [item["item_id"] for item in items]
assert len(ids) == len(set(ids)) == 48, len(ids)

catalog = json.loads((ROOT / "data/catalog/model_compass_use_cases_v2.json").read_text(encoding="utf-8"))
names = {use_case["id"]: use_case for use_case in catalog["use_cases"]}
catalog["catalog_version"] = "model-compass-use-cases-v3.1"
catalog["description"] = (
    "Use-case catalog for the generic-screen-v3 suite: six items per generic use case. Thresholds stay draft "
    "until calibrated on a reference run; weights and profiles are justified in docs/model-compass-scope.md. "
    "Recommendation component scores use the fixed logarithmic anchors below."
)
catalog["weight_profiles"] = {
    "quality_first": {"quality": 0.70, "security": 0.20, "cost": 0.07, "performance": 0.03},
    "balanced": dict(catalog["weights"]),
    "cost_sensitive": {"quality": 0.35, "security": 0.20, "cost": 0.40, "performance": 0.05},
}
use_cases = []
for use_case_id in ORDER:
    definition = dict(names[use_case_id])
    definition["prompt_ids"] = [index for index, item in enumerate(items) if item["use_case_id"] == use_case_id]
    use_cases.append(definition)
catalog["use_cases"] = use_cases
OUTPUTS = {
    SUITE_PATH: json.dumps(items, indent=2, ensure_ascii=False) + "\n",
    CATALOG_PATH: json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
}
SUMMARY = "Use cases (first prompt index, items, threshold): " + str(
    {
        use_case["id"]: (use_case["prompt_ids"][0], len(use_case["prompt_ids"]), use_case["minimum_quality_score"])
        for use_case in use_cases
    }
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="Fail if a committed file differs from the build")
    args = parser.parse_args(argv)
    stale = [path for path, text in OUTPUTS.items() if not path.exists() or path.read_text(encoding="utf-8") != text]
    if args.check:
        for path in stale:
            print(f"OUT OF DATE: {path.relative_to(ROOT)} — run this script without --check")
        return 1 if stale else 0
    for path, text in OUTPUTS.items():
        path.write_text(text, encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")
    print(SUMMARY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
