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
items += [keep("structured_extraction-01"), keep("structured_extraction-04"), keep("structured_extraction-05")]
# OpenRouter guardrails mask "JSON array" as an address; the item must reach the models as written.
items[1]["prompt"] = items[1]["prompt"].replace("exactly one JSON array", "exactly one array in JSON format")
items.append(
    json_item(
        "structured_extraction-06",
        "null_for_missing_fields",
        "hard",
        "Extract the keys `product`, `version`, `release_date` and `license` from the note. Use null for any field the "
        "note does not state explicitly; do not infer it. Return exactly one JSON object, with no markdown or extra "
        "text.\nNote: 'Product: Atlas toolkit. Version 4.2 adds a faster importer. Pricing is unchanged; the release "
        "schedule is on the vendor portal.'",
        {"product": "Atlas toolkit", "version": "4.2", "release_date": None, "license": None},
    )
)
items.append(
    json_item(
        "structured_extraction-07",
        "correction_supersedes_value",
        "hard",
        "Return exactly one JSON object, with no markdown or extra text, with the keys `meeting_date` (ISO 8601, "
        "YYYY-MM-DD) and `room` (string). When the text corrects a value, use the corrected one.\nText: 'The kickoff "
        "is on 4 March 2027 in room 2.14. Correction from the facilities team: it moves to 11 March 2027, same time, "
        "room 3.02.'",
        {"meeting_date": "2027-03-11", "room": "3.02"},
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
        "code_generation-06",
        "interval_merging_edge_cases",
        "medium",
        "Write only a Python function `merge_intervals(intervals: list[list[int]]) -> list[list[int]]` that merges "
        "overlapping intervals and intervals that touch (such as [1, 3] and [3, 5]), accepts the intervals in any "
        "order, and returns the merged intervals sorted by start; an empty list returns an empty list.",
        "merge_intervals",
        ["intervals"],
        """
def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
""",
        [
            ([[1, 3], [2, 6], [8, 10], [15, 18]],),
            ([[1, 4], [4, 5]],),
            ([],),
            ([[5, 7], [1, 2]],),
            ([[1, 10], [2, 3], [4, 8]],),
            ([[6, 8], [1, 3], [3, 4], [9, 9]],),
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
        "code_generation-08",
        "calendar_arithmetic",
        "hard",
        "Write only a Python function `business_days_between(start: str, end: str, holidays: list[str]) -> int` that "
        "counts the weekdays (Monday to Friday) from `start` included to `end` excluded, both ISO dates such as "
        "'2026-11-02', skipping every date listed in `holidays`; it returns 0 when `end` is not after `start`.",
        "business_days_between",
        ["start", "end", "holidays"],
        """
import datetime

def business_days_between(start, end, holidays):
    first = datetime.date.fromisoformat(start)
    last = datetime.date.fromisoformat(end)
    skipped = {datetime.date.fromisoformat(day) for day in holidays}
    count = 0
    day = first
    while day < last:
        if day.weekday() < 5 and day not in skipped:
            count += 1
        day += datetime.timedelta(days=1)
    return count
""",
        [
            ("2026-11-02", "2026-11-09", []),
            ("2026-11-02", "2026-11-16", ["2026-11-11"]),
            ("2026-11-07", "2026-11-09", []),
            ("2026-12-24", "2027-01-04", ["2026-12-25", "2027-01-01"]),
            ("2026-11-09", "2026-11-02", []),
            ("2026-11-06", "2026-11-06", []),
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
item = exact(
    "contextual_qa-06",
    QA,
    "multi_hop_with_stale_fact",
    "hard",
    "Context: Team A leads the north branch, which reports to the central hub. Until March, the central hub was led "
    "by Team K; since April it has been led by Team R. Team K now leads the south branch.\nQuestion: Which team "
    "currently leads the hub that the north branch reports to? Reply with the team name only.",
    "Team R",
    dimension="contextual_accuracy",
)
item["accepted_answers"] = ["Team R", "R"]
items.append(item)
items.append(
    exact(
        "contextual_qa-07",
        QA,
        "reinstated_earlier_value",
        "hard",
        "Context: Notice of 2 May: the deadline is 15 June. Notice of 14 May: the deadline is moved to 30 June. Notice "
        "of 21 May: the change announced on 14 May is cancelled and the deadline of 2 May applies again.\nQuestion: "
        "What is the current deadline? Reply with the date only, exactly as written in the context.",
        "15 June",
        dimension="contextual_accuracy",
    )
)
items.append(
    exact(
        "contextual_qa-08",
        QA,
        "abstention_with_near_miss",
        "medium",
        "Context: The audit covered the north and south sites. The north site had 3 findings, all closed. The south "
        "site report is still being written.\nQuestion: How many findings did the south site have? If the context does "
        "not say, reply exactly NOT STATED.",
        "NOT STATED",
        dimension="contextual_accuracy",
    )
)
items.append(
    exact(
        "contextual_qa-09",
        QA,
        "conditional_arithmetic",
        "hard",
        "Context: Shipping costs 6 EUR per parcel. For orders above 50 EUR, one parcel ships free. An order of 64 EUR "
        "is sent in 3 parcels.\nQuestion: What is the total shipping cost of this order, in euros? Reply with the "
        "number only.",
        str(6 * (3 - 1)),
        dimension="contextual_accuracy",
    )
)
items.append(
    exact(
        "contextual_qa-10",
        QA,
        "exception_to_inherited_rule",
        "medium",
        "Context: All plans include email support. Only the Pro and Enterprise plans include phone support. The "
        "Enterprise plan also includes a dedicated manager. The Team plan includes everything in Pro except phone "
        "support.\nQuestion: Does the Team plan include phone support? Reply with YES or NO only.",
        "NO",
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
best = min(4 * packs + (15 - 6 * packs) for packs in range(0, 3))
items.append(
    exact(
        "reasoning_analysis-06",
        RA,
        "optimisation_under_constraint",
        "medium",
        "Pens are sold in packs of 6 for 4 EUR or individually for 1 EUR each. What is the lowest cost, in euros, to "
        "buy exactly 15 pens? Reply with the number only.",
        str(best),
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
minutes = 30 + (500 - 120 * 0.5) / (120 + 80) * 60
assert minutes == int(minutes)
items.append(
    exact(
        "reasoning_analysis-08",
        RA,
        "rate_with_staggered_start",
        "hard",
        "Machine A fills 120 bottles per hour. Machine B fills 80 bottles per hour and starts 30 minutes after A. Both "
        "stop as soon as 500 bottles have been filled in total. How many minutes after A starts do they stop? Reply "
        "with the number only.",
        str(int(minutes)),
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
items.append(
    exact(
        "classification_routing-07",
        CR,
        "priority_rule_for_mixed_intents",
        "hard",
        LABELS + "When a message raises several issues, pick the label of the issue the customer asks to resolve "
        "first. Reply with the label only.\nMessage: 'The app crashes on login, but first please refund the duplicate "
        "charge from yesterday.'",
        "BILLING",
        dimension="classification_accuracy",
    )
)
items.append(
    exact(
        "classification_routing-08",
        CR,
        "sarcasm_detection",
        "medium",
        "Classify the sentiment of the review as POSITIVE, NEGATIVE or MIXED. Reply with the label only.\nReview: "
        "'Great, another update that deletes my saved filters. Really helpful.'",
        "NEGATIVE",
        dimension="classification_accuracy",
    )
)
items.append(
    exact(
        "classification_routing-09",
        CR,
        "abstention_under_explicit_rule",
        "hard",
        "Route the message to exactly one queue: BILLING, TECHNICAL, ACCOUNT or UNCLEAR. Use UNCLEAR only when the "
        "message gives no clue at all about its topic. Reply with the label only.\nMessage: 'Can someone call me back "
        "about this?'",
        "UNCLEAR",
        dimension="classification_accuracy",
    )
)
items.append(
    exact(
        "classification_routing-10",
        CR,
        "non_english_with_distractor",
        "medium",
        LABELS + "Reply with the label only.\nMessage: 'Hallo, bitte schliessen Sie mein Konto zum Monatsende. Die "
        "Rechnung bezahle ich noch.'",
        "ACCOUNT",
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
items.append(
    exact(
        "classification_routing-12",
        CR,
        "negated_keyword",
        "medium",
        LABELS + "Reply with the label only.\nMessage: 'This is not about my invoice: I only want to know your opening "
        "hours on public holidays.'",
        "OTHER",
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
thirty_day_months = ",".join(
    calendar.month_name[m].upper() for m in range(1, 13) if calendar.monthrange(2027, m)[1] == 30
)
items.append(
    exact(
        "instruction_following-05",
        IF,
        "multi_constraint_listing",
        "medium",
        "Write the names of the months that have exactly 30 days, in calendar order, in uppercase, separated by commas "
        "with no spaces, and nothing else.",
        thirty_day_months,
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
