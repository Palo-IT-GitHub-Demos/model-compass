"""Deterministic pre-evaluation layer for the generic LLM quality screen.

The screen deliberately measures only provider-neutral fundamentals: structured
output, factual sanity, elementary reasoning and instruction reliability. It is
not a substitute for domain-specific task evaluation.

Checks run in pure Python before any external judge is used. A check either
produces a definitive pass/fail score or returns ``None`` to route the response
to the blind Copilot judge panel.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from src.evaluators.code_sandbox import find_policy_violation, run_python_tests


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a single deterministic evaluation."""

    passed: bool | None
    """True = definitive pass, False = definitive fail, None = undecidable (forward to LLM judge)."""

    score: float | None
    """Score on a 1–5 scale, or None when undecidable.

    Structured checks give partial credit (``1 + 4 × share correct``): a JSON
    answer with three of four fields right, or code passing four of five
    tests, scores between 1 and 5 instead of failing like an empty answer.
    """

    reason: str
    """Human-readable explanation of the result."""

    format_score: int | None = None
    """Output-format compliance on a 1–5 scale, or None when the prompt sets no strict contract.

    Scored separately from :attr:`score` so that a correct answer wrapped in
    markdown fences is reported as a formatting failure rather than as a
    content failure.
    """

    format_reason: str = ""
    """Human-readable explanation of :attr:`format_score`."""


@runtime_checkable
class DeterministicCheck(Protocol):
    """Protocol satisfied by all deterministic check classes."""

    category: str

    def run(
        self,
        prompt: str,
        response: str,
        evaluation: Mapping[str, Any] | None = None,
    ) -> CheckResult:
        """Evaluate *response* against *prompt* and optional metadata."""
        ...


# ── Concrete checks ────────────────────────────────────────────────────────────


class JsonValidityCheck:
    """Verify JSON syntax and, when configured, exact JSON content."""

    category = "json_output"

    def run(
        self,
        prompt: str,
        response: str,
        evaluation: Mapping[str, Any] | None = None,
    ) -> CheckResult:
        """Evaluate JSON content, reporting markdown fences as a formatting failure."""
        del prompt
        content = _strip_code_fences(response)
        fmt = _format_compliance(evaluation, response, content, "raw JSON")
        try:
            parsed = json.loads(content)
            expected_json = _get_context_value(evaluation, "expected_json")
            if fmt and isinstance(expected_json, dict | list) and not isinstance(parsed, type(expected_json)):
                fmt = {
                    "format_score": 1,
                    "format_reason": "Response has the wrong JSON root type for the required object or array.",
                }
            if expected_json is not None and parsed != expected_json:
                share = json_agreement(parsed, expected_json)
                return CheckResult(
                    passed=False,
                    score=partial_credit(share),
                    reason=(
                        "Response is valid JSON but does not match the required JSON value "
                        f"({share:.0%} of the expected fields or items are correct)."
                    ),
                    **fmt,
                )
            return CheckResult(
                passed=True,
                score=5,
                reason=(
                    "Response is valid JSON and matches the required JSON value."
                    if expected_json is not None
                    else "Response is syntactically valid JSON."
                ),
                **fmt,
            )
        except json.JSONDecodeError as exc:
            if fmt:
                fmt = {"format_score": 1, "format_reason": "Response is not syntactically valid JSON."}
            expected_json = _get_context_value(evaluation, "expected_json")
            embedded = _last_embedded_json(content, expected_json)
            if embedded is not _NOT_FOUND:
                share = json_agreement(embedded, expected_json) if expected_json is not None else 1.0
                return CheckResult(
                    passed=False,
                    score=round(1.0 + (RECOVERED_ANSWER_SCORE - 1.0) * share, 2),
                    reason=(
                        "Extra text surrounds the JSON value; the last JSON value in the response gets "
                        f"{share:.0%} of the expected fields or items right, scored at most {RECOVERED_ANSWER_SCORE}."
                    ),
                    **fmt,
                )
            return CheckResult(
                passed=False,
                score=1,
                reason=f"Invalid JSON: {exc.msg} (line {exc.lineno}, col {exc.colno}).",
                **fmt,
            )


class PythonSyntaxCheck:
    """Verify Python syntax and an optional, non-executed function contract."""

    category = "code_generation"

    def run(
        self,
        prompt: str,
        response: str,
        evaluation: Mapping[str, Any] | None = None,
    ) -> CheckResult:
        """Check syntax and function shape without executing untrusted code."""
        del prompt
        code = _strip_code_fences(response)
        fmt = _format_compliance(evaluation, response, code, "raw Python")
        if not code:
            return CheckResult(
                passed=False,
                score=1,
                reason="Response is empty; expected Python source code.",
                **fmt,
            )
        try:
            tree = ast.parse(code, filename="<model-response>", mode="exec")
        except SyntaxError as exc:
            return CheckResult(
                passed=False,
                score=1,
                reason=f"Python SyntaxError: {exc.msg} (line {exc.lineno}).",
                **fmt,
            )

        required_function = _get_context_str(evaluation, "required_function")
        required_parameters = _get_context_strings(evaluation, "required_parameters")
        if required_function is None:
            return CheckResult(
                passed=True,
                score=5,
                reason="Response contains syntactically valid Python.",
                **fmt,
            )

        function = next(
            (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == required_function),
            None,
        )
        if function is None:
            return CheckResult(
                passed=False,
                score=1,
                reason=f"Required function '{required_function}' was not found.",
                **fmt,
            )

        actual_parameters = [arg.arg for arg in (*function.args.posonlyargs, *function.args.args)]
        if required_parameters and actual_parameters != required_parameters:
            return CheckResult(
                passed=False,
                score=1,
                reason=(
                    f"Function '{required_function}' parameters must be {required_parameters}, got {actual_parameters}."
                ),
                **fmt,
            )

        return CheckResult(
            passed=True,
            score=5,
            reason=f"Response satisfies the '{required_function}' Python function contract.",
            **fmt,
        )


class PythonExecutionCheck:
    """Run generated Python against test cases in the restricted sandbox.

    Undecidable (routed to the judge panel) unless the run opted in with
    ``execute_code`` or when the sandbox itself is unavailable, so an
    infrastructure problem is never scored as a model failure.
    """

    category = "code_execution"

    def run(
        self,
        prompt: str,
        response: str,
        evaluation: Mapping[str, Any] | None = None,
    ) -> CheckResult:
        """Score the response 5 when every test case passes, otherwise 1."""
        del prompt
        code = _strip_code_fences(response)
        fmt = _format_compliance(evaluation, response, code, "raw Python")
        if _get_context_value(evaluation, "execute_code") is not True:
            return CheckResult(
                passed=None,
                score=None,
                reason="Code execution is disabled; routed to the judge panel.",
                **fmt,
            )
        if not code:
            return CheckResult(passed=False, score=1, reason="Response is empty; expected Python source.", **fmt)

        function_name = _get_context_str(evaluation, "required_function")
        cases = _get_context_value(evaluation, "test_cases")
        if function_name is None or not isinstance(cases, list) or not cases:
            return CheckResult(
                passed=None, score=None, reason="No executable test contract; routed to the judge panel.", **fmt
            )

        violation = find_policy_violation(code)
        if violation is not None:
            return CheckResult(passed=False, score=1, reason=f"Rejected before execution: {violation}.", **fmt)

        expected_parameters = _get_context_strings(evaluation, "required_parameters")
        tree = ast.parse(code)
        function = next(
            (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function_name),
            None,
        )
        if function is None:
            return CheckResult(
                passed=False, score=1, reason=f"Required function '{function_name}' was not found.", **fmt
            )
        actual_parameters = [arg.arg for arg in (*function.args.posonlyargs, *function.args.args)]
        if expected_parameters and actual_parameters != expected_parameters:
            return CheckResult(
                passed=False,
                score=1,
                reason=f"Function '{function_name}' parameters must be {expected_parameters}, got {actual_parameters}.",
                **fmt,
            )

        result = run_python_tests(code, function_name, cases)
        if not result.is_model_failure:
            return CheckResult(passed=None, score=None, reason=f"Sandbox unavailable: {result.detail}", **fmt)
        if result.status == "ok" and result.passed == result.total:
            return CheckResult(passed=True, score=5, reason=f"Passed {result.passed}/{result.total} test cases.", **fmt)
        if result.status == "ok":
            return CheckResult(
                passed=False,
                score=partial_credit(result.passed / result.total if result.total else 0.0),
                reason=f"Passed {result.passed}/{result.total} test cases.",
                **fmt,
            )
        return CheckResult(passed=False, score=1, reason=f"Execution {result.status}: {result.detail}", **fmt)


class ExactFormatCheck:
    """Evaluate exact output when accepted answers are supplied.

    The exact output is the construct here, so a correct final line after
    extra text (shown working, a preamble) scores :data:`RECOVERED_ANSWER_SCORE`,
    not 5. Without reference answers, the response remains undecidable and is
    sent to the blind judge panel. This preserves support for open-ended prompts.
    """

    category = "instruction_following"

    def run(
        self,
        prompt: str,
        response: str,
        evaluation: Mapping[str, Any] | None = None,
    ) -> CheckResult:
        """Compare a response to normalized accepted answers when available."""
        del prompt
        accepted_answers = _get_context_strings(evaluation, "accepted_answers")
        if accepted_answers:
            normalized_response = _normalize_exact_text(response)
            normalized_answers = {_normalize_exact_text(answer) for answer in accepted_answers}
            matches = normalized_response in normalized_answers
            fmt: dict[str, Any] = {}
            if _is_strict_output(evaluation):
                literal = response.strip() in {answer.strip() for answer in accepted_answers}
                bare_answer_shape = not matches and _matches_bare_answer_shape(response.strip(), accepted_answers)
                fmt = {
                    "format_score": 5 if literal or bare_answer_shape else 1,
                    "format_reason": (
                        "Response is exactly the accepted answer, with no extra text."
                        if literal
                        else (
                            "Response follows the required bare-answer format, but its value is incorrect."
                            if bare_answer_shape
                            else "Response differs from the required bare-answer format or value."
                        )
                    ),
                }
            if matches:
                return CheckResult(
                    passed=True,
                    score=5,
                    reason="Response matches an accepted answer.",
                    **fmt,
                )
            if final_answer_matches(response, accepted_answers):
                return CheckResult(
                    passed=False,
                    score=RECOVERED_ANSWER_SCORE,
                    reason="The final line is an accepted answer, but extra text breaks the exact-output instruction.",
                    **fmt,
                )
            return CheckResult(
                passed=False,
                score=1,
                reason="Response does not match any accepted answer exactly.",
                **fmt,
            )
        return CheckResult(
            passed=None,
            score=None,
            reason="Instruction-following format requires LLM judgement.",
        )


class ExactAnswerCheck(ExactFormatCheck):
    """Exact-answer check for factual-sanity, classification and elementary-reasoning probes.

    Content is the final answer: a correct answer that also shows its working,
    or wraps the value in markdown emphasis, keeps its content score and fails
    only output-format compliance. Exact-format instruction prompts
    (:class:`ExactFormatCheck`) cap that case at :data:`RECOVERED_ANSWER_SCORE`,
    since there the exact output is the construct being measured.
    """

    category = "exact_answer"

    def run(
        self,
        prompt: str,
        response: str,
        evaluation: Mapping[str, Any] | None = None,
    ) -> CheckResult:
        """Score the final answer, keeping the strict format verdict separate."""
        result = super().run(prompt, response, evaluation)
        accepted_answers = _get_context_strings(evaluation, "accepted_answers")
        if result.passed is not False or not final_answer_matches(response, accepted_answers):
            return result
        return CheckResult(
            passed=True,
            score=5,
            reason="Final answer matches an accepted answer; the extra text is scored under output format only.",
            format_score=result.format_score,
            format_reason=result.format_reason,
        )


EXACT_ANSWER_CATEGORIES = frozenset({"exact_answer", "factual_sanity", "logical_reasoning"})
"""Categories whose content is the final answer, scored by :class:`ExactAnswerCheck`."""

_ANSWER_LABEL = re.compile(r"^(?:final answer|answer|result|label|the answer is)\s*[:=-]?\s*", re.IGNORECASE)
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def final_answer(response: str, accepted_answers: list[str]) -> str:
    """Return the final answer a response commits to, or ``""``.

    The final answer is the last non-empty line, without markdown emphasis,
    quotes, an ``Answer:``-style label or trailing punctuation. When every
    accepted answer is a number, it is the last number on that line, so
    ``3 * 24 + 5 = 77`` answers ``77``.
    """
    lines = [line for line in _strip_code_fences(response).splitlines() if line.strip()]
    if not lines:
        return ""
    last = re.sub(r"[*_`]+", "", lines[-1]).strip()
    last = _ANSWER_LABEL.sub("", last).strip().strip("\"'“”‘’").rstrip(".!").strip()
    if accepted_answers and all(_NUMBER.fullmatch(answer.strip()) for answer in accepted_answers):
        numbers = _NUMBER.findall(last)
        return numbers[-1] if numbers else ""
    return last


def final_answer_matches(response: str, accepted_answers: list[str]) -> bool:
    """Return whether the response's final answer is one of *accepted_answers*."""
    answer = final_answer(response, accepted_answers)
    if not answer:
        return False
    return _normalize_exact_text(answer) in {_normalize_exact_text(item) for item in accepted_answers}


RECOVERED_ANSWER_SCORE = 3
"""Content score of a correct answer that breaks the exact-output contract of a JSON or exact-format item.

Better than a wrong answer (1), worse than following the contract (5): there
the contract is part of what the item measures. Output-format compliance still
fails separately.
"""

_NOT_FOUND = object()


def _last_embedded_json(text: str, expected: object) -> object:
    """Return the last top-level JSON value in *text*, of the expected root type when one is given.

    Recovers the answer of a response that shows its working before the JSON
    value; returns ``_NOT_FOUND`` when no such value parses.
    """
    decoder = json.JSONDecoder()
    found: object = _NOT_FOUND
    resume = 0
    for match in re.finditer(r"[{\[]", text):
        if match.start() < resume:
            continue
        try:
            value, end = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        resume = end
        if expected is None or isinstance(value, type(expected)):
            found = value
    return found


def partial_credit(share: float) -> float:
    """Map the share of a structured answer that is correct to the 1–5 scale (1 + 4 × share)."""
    return round(1.0 + 4.0 * min(max(share, 0.0), 1.0), 2)


def json_agreement(actual: object, expected: object) -> float:
    """Share of an expected JSON value the answer gets right, from 0 to 1.

    Objects compare their top-level fields: an extra field counts against the
    answer like a missing or wrong one, since inventing fields is an error.
    Arrays compare position by position over the longer of the two. Any other
    value is all or nothing.
    """
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return 0.0
        fields = set(expected) | set(actual)
        correct = sum(1 for key in expected if key in actual and actual[key] == expected[key])
        return correct / len(fields) if fields else 1.0
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return 0.0
        size = max(len(expected), len(actual))
        return sum(1 for got, want in zip(actual, expected, strict=False) if got == want) / size if size else 1.0
    return 1.0 if actual == expected else 0.0


# ── Registry ───────────────────────────────────────────────────────────────────

CHECKS: dict[str, DeterministicCheck] = {
    "json_output": JsonValidityCheck(),
    "code_generation": PythonSyntaxCheck(),
    "code_execution": PythonExecutionCheck(),
    "instruction_following": ExactFormatCheck(),
    "exact_answer": ExactAnswerCheck(),
    "factual_sanity": ExactAnswerCheck(),
    "logical_reasoning": ExactAnswerCheck(),
}


# ── Helpers ────────────────────────────────────────────────────────────────────


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences (e.g. ```json ... ```) if present."""
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _get_context_value(evaluation: Mapping[str, Any] | None, key: str) -> Any | None:
    """Return a metadata value when *evaluation* is available."""
    return evaluation.get(key) if evaluation is not None else None


def _get_context_str(evaluation: Mapping[str, Any] | None, key: str) -> str | None:
    """Return a string metadata value, otherwise ``None``."""
    value = _get_context_value(evaluation, key)
    return value if isinstance(value, str) else None


def _get_context_strings(evaluation: Mapping[str, Any] | None, key: str) -> list[str]:
    """Return a validated list of string metadata values."""
    value = _get_context_value(evaluation, key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return value


def _is_strict_output(evaluation: Mapping[str, Any] | None) -> bool:
    """Return whether the response must not include markdown or extra text."""
    return _get_context_value(evaluation, "strict_output") is True


def _format_compliance(
    evaluation: Mapping[str, Any] | None,
    response: str,
    content: str,
    expected_form: str,
) -> dict[str, Any]:
    """Return the ``CheckResult`` format fields for a strict-output prompt.

    Empty when the prompt sets no strict contract, so non-strict prompts keep
    reporting content only.
    """
    if not _is_strict_output(evaluation):
        return {}
    compliant = content == response.strip()
    return {
        "format_score": 5 if compliant else 1,
        "format_reason": (
            f"Response contains {expected_form} only, as instructed."
            if compliant
            else f"Response must contain {expected_form} only, without markdown fences or extra text."
        ),
    }


def _normalize_exact_text(value: str) -> str:
    """Normalize whitespace and casing while preserving meaningful punctuation."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _matches_bare_answer_shape(response: str, accepted_answers: list[str]) -> bool:
    """Keep the required punctuation, spacing and case while allowing a wrong value."""
    for answer in accepted_answers:
        tokens = re.findall(r"[A-Z]+[a-z]*|[a-z]+|\d+|[^A-Za-z0-9]+", answer.strip())
        pattern = "".join(
            r"[A-Z]+"
            if token.isupper()
            else r"[A-Z][a-z]*"
            if token.istitle()
            else r"[a-z]+"
            if token.islower()
            else r"\d+"
            if token.isdecimal()
            else re.escape(token)
            for token in tokens
        )
        if re.fullmatch(pattern, response):
            return True
    return False
