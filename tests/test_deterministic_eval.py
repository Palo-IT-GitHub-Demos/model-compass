"""Unit tests for src/evaluators/deterministic_eval.py."""

from __future__ import annotations

import pytest

from src.evaluators.deterministic_eval import (
    CHECKS,
    RECOVERED_ANSWER_SCORE,
    ExactAnswerCheck,
    ExactFormatCheck,
    JsonValidityCheck,
    PythonSyntaxCheck,
    _strip_code_fences,
)


class TestJsonValidityCheck:
    def test_valid_json_passes(self) -> None:
        check = JsonValidityCheck()
        result = check.run("", '{"key": "value"}')
        assert result.passed is True
        assert result.score == 5

    def test_invalid_json_fails(self) -> None:
        check = JsonValidityCheck()
        result = check.run("", "not json at all")
        assert result.passed is False
        assert result.score == 1

    def test_markdown_fenced_json_passes(self) -> None:
        check = JsonValidityCheck()
        result = check.run("", '```json\n{"key": "value"}\n```')
        assert result.passed is True
        assert result.score == 5

    def test_empty_object_passes(self) -> None:
        check = JsonValidityCheck()
        result = check.run("", "{}")
        assert result.passed is True

    def test_reason_is_non_empty(self) -> None:
        check = JsonValidityCheck()
        result = check.run("", "bad")
        assert len(result.reason) > 0

    def test_expected_json_must_match_content(self) -> None:
        check = JsonValidityCheck()
        result = check.run(
            "",
            '{"status": "wrong"}',
            {"expected_json": {"status": "ok"}, "strict_output": True},
        )
        assert result.passed is False
        assert result.score == 1

    def test_strict_json_reports_markdown_fences_as_format_failure(self) -> None:
        check = JsonValidityCheck()
        result = check.run(
            "",
            '```json\n{"status": "ok"}\n```',
            {"expected_json": {"status": "ok"}, "strict_output": True},
        )
        assert result.passed is True
        assert result.score == 5
        assert result.format_score == 1

    def test_strict_json_invalid_syntax_fails_content_and_format(self) -> None:
        result = JsonValidityCheck().run(
            "",
            "[urgent, billing]",
            {"expected_json": ["urgent", "billing"], "strict_output": True},
        )
        assert result.passed is False
        assert result.score == 1
        assert result.format_score == 1
        assert "not syntactically valid JSON" in result.format_reason

    def test_strict_json_fenced_invalid_syntax_still_fails_format(self) -> None:
        result = JsonValidityCheck().run("", "```json\n[urgent, billing]\n```", {"strict_output": True})
        assert result.score == 1
        assert result.format_score == 1

    def test_strict_json_wrong_root_type_fails_format(self) -> None:
        result = JsonValidityCheck().run("", '["ok"]', {"expected_json": {"status": "ok"}, "strict_output": True})
        assert result.score == 1
        assert result.format_score == 1
        assert "wrong JSON root type" in result.format_reason

    def test_strict_json_wrong_value_preserves_valid_format(self) -> None:
        result = JsonValidityCheck().run(
            "", '{"status": "wrong"}', {"expected_json": {"status": "ok"}, "strict_output": True}
        )
        assert result.score == 1
        assert result.format_score == 5

    def test_strict_json_without_fences_is_format_compliant(self) -> None:
        check = JsonValidityCheck()
        result = check.run(
            "",
            '{"status": "ok"}',
            {"expected_json": {"status": "ok"}, "strict_output": True},
        )
        assert result.passed is True
        assert result.score == 5
        assert result.format_score == 5

    def test_non_strict_json_has_no_format_score(self) -> None:
        check = JsonValidityCheck()
        result = check.run("", '```json\n{"status": "ok"}\n```', {"expected_json": {"status": "ok"}})
        assert result.format_score is None

    def test_non_strict_invalid_json_has_no_format_score(self) -> None:
        result = JsonValidityCheck().run("", "[urgent, billing]", {"expected_json": ["urgent", "billing"]})
        assert result.score == 1
        assert result.format_score is None

    def test_correct_json_after_working_gets_partial_credit(self) -> None:
        response = 'Replaying the log:\n1. lamp = 3 [step 1]\n8. undo step 6\n\n```json\n{"lamp": 7, "stand": 1}\n```'
        result = JsonValidityCheck().run(
            "", response, {"expected_json": {"lamp": 7, "stand": 1}, "strict_output": True}
        )
        assert (result.passed, result.score, result.format_score) == (False, RECOVERED_ANSWER_SCORE, 1)

    def test_json_after_working_scales_its_partial_credit_to_the_recovered_cap(self) -> None:
        result = JsonValidityCheck().run(
            "", 'Counting: {"lamp": 7, "stand": 2}', {"expected_json": {"lamp": 7, "stand": 1}, "strict_output": True}
        )
        assert result.score == 2.0

    def test_text_whose_only_brackets_hold_another_json_type_scores_one(self) -> None:
        result = JsonValidityCheck().run(
            "", "Undo step [6] first.", {"expected_json": {"lamp": 7}, "strict_output": True}
        )
        assert result.score == 1


class TestPythonSyntaxCheck:
    def test_valid_function_passes(self) -> None:
        check = PythonSyntaxCheck()
        code = "def add(a: int, b: int) -> int:\n    return a + b"
        result = check.run("", code)
        assert result.passed is True
        assert result.score == 5

    def test_syntax_error_fails(self) -> None:
        check = PythonSyntaxCheck()
        result = check.run("", "def broken(:\n    pass")
        assert result.passed is False
        assert result.score == 1
        assert "SyntaxError" in result.reason

    def test_fenced_code_block_passes(self) -> None:
        check = PythonSyntaxCheck()
        result = check.run("", "```python\nx = 1 + 1\n```")
        assert result.passed is True

    def test_empty_string_fails(self) -> None:
        check = PythonSyntaxCheck()
        result = check.run("", "")
        assert result.passed is False
        assert result.score == 1

    def test_required_function_contract_passes_without_execution(self) -> None:
        check = PythonSyntaxCheck()
        result = check.run(
            "",
            "def add(a: int, b: int) -> int:\n    return a + b",
            {"required_function": "add", "required_parameters": ["a", "b"]},
        )
        assert result.passed is True
        assert result.score == 5

    def test_required_function_contract_rejects_wrong_parameters(self) -> None:
        check = PythonSyntaxCheck()
        result = check.run(
            "",
            "def add(left: int, right: int) -> int:\n    return left + right",
            {"required_function": "add", "required_parameters": ["a", "b"]},
        )
        assert result.passed is False
        assert result.score == 1


class TestExactFormatCheck:
    def test_always_undecidable(self) -> None:
        check = ExactFormatCheck()
        result = check.run("any prompt", "any response")
        assert result.passed is None
        assert result.score is None

    def test_reason_is_non_empty(self) -> None:
        check = ExactFormatCheck()
        result = check.run("", "")
        assert len(result.reason) > 0

    def test_exact_answer_accepts_normalized_whitespace_and_case(self) -> None:
        check = ExactAnswerCheck()
        result = check.run("", "  canberra\n", {"accepted_answers": ["Canberra"]})
        assert result.passed is True
        assert result.score == 5

    def test_exact_answer_scores_the_final_answer_and_leaves_extra_text_to_format(self) -> None:
        check = ExactAnswerCheck()
        result = check.run("", "The answer is Canberra.", {"accepted_answers": ["Canberra"]})
        assert (result.passed, result.score) == (True, 5)

        strict = check.run(
            "", "5 x 8 = 40 and 3 + 7 + 9 + 11 = 30.\n\n**10**", {"accepted_answers": ["10"], "strict_output": True}
        )
        assert (strict.score, strict.format_score) == (5, 1)

    @pytest.mark.parametrize(
        ("response", "accepted"),
        [
            ("**11:25**\n\nThe first booking ends at 11:15, so the slot runs 11:25 to 12:35.", ["11:25"]),
            ("3/5 * 2/4 = 6/20 = 3/10", ["3/10"]),
            ("Q4 is not published.\n\nSo the answer is: NOT STATED.", ["NOT STATED"]),
            (
                "We cannot add an estimate.\n\nThe correct answer would be NOT STATED, as Q4 is not provided.",
                ["NOT STATED"],
            ),
        ],
        ids=["alone-on-first-line", "assigned-on-last-line", "labelled-on-last-line", "stated-with-a-clause"],
    )
    def test_exact_answer_recovers_answer_before_or_after_explanation(self, response: str, accepted: list[str]) -> None:
        result = ExactAnswerCheck().run("", response, {"accepted_answers": accepted, "strict_output": True})

        assert (result.passed, result.score, result.format_score) == (True, 5, 1)

    @pytest.mark.parametrize(
        ("response", "accepted"),
        [
            ("This could be P1.\nFinal answer: P2", ["P1"]),
            ("3 x 24 + 5 = 77\nWait, two boxes came back: 77 - 48 = 29\n\n29", ["77"]),
            ("P1\n\nOn reflection, a workaround exists.\n\nP2", ["P1"]),
            ("**11:25** is tempting, but the buffer pushes the start.\n\nThe earliest start is 11:30.", ["11:25"]),
            ("The answer is not P1.", ["P1"]),
        ],
        ids=[
            "considered-then-another",
            "intermediate-value",
            "first-line-then-corrected",
            "same-line-mention",
            "negated",
        ],
    )
    def test_exact_answer_never_takes_a_value_the_response_does_not_settle_on(
        self, response: str, accepted: list[str]
    ) -> None:
        result = ExactAnswerCheck().run("", response, {"accepted_answers": accepted, "strict_output": True})

        assert (result.passed, result.score) == (False, 1)

    @pytest.mark.parametrize(
        ("response", "accepted"),
        [("I think 10, not 12", ["10"]), ("TECHNICAL", ["UNCLEAR"]), ("Canberra or Sydney", ["Canberra"])],
    )
    def test_exact_answer_still_fails_a_wrong_or_hedged_final_answer(self, response: str, accepted: list[str]) -> None:
        assert ExactAnswerCheck().run("", response, {"accepted_answers": accepted}).score == 1

    def test_exact_format_instruction_still_rejects_extra_text(self) -> None:
        result = ExactFormatCheck().run("", "Sure: READY:5", {"accepted_answers": ["READY:5"]})
        assert (result.passed, result.score) == (False, 1)

    def test_exact_format_gives_partial_credit_to_a_correct_final_line_after_working(self) -> None:
        result = ExactFormatCheck().run(
            "",
            "Vowels: i, e, i, e = 4. Removing them leaves p-p-l-n.\n\n**ppln-4**",
            {"accepted_answers": ["ppln-4"], "strict_output": True},
        )
        assert (result.passed, result.score, result.format_score) == (False, RECOVERED_ANSWER_SCORE, 1)

    def test_exact_format_does_not_credit_a_wrong_final_line_after_working(self) -> None:
        result = ExactFormatCheck().run(
            "", "Vowels removed.\n\nppln-3", {"accepted_answers": ["ppln-4"], "strict_output": True}
        )
        assert result.score == 1

    def test_wrong_numeric_value_does_not_imply_format_failure(self) -> None:
        result = ExactFormatCheck().run("", "READY:4", {"accepted_answers": ["READY:5"], "strict_output": True})
        assert result.passed is False
        assert result.score == 1
        assert result.format_score == 5
        assert "value is incorrect" in result.format_reason

    def test_wrong_value_with_extra_text_fails_format(self) -> None:
        result = ExactFormatCheck().run("", "READY:4 extra", {"accepted_answers": ["READY:5"], "strict_output": True})
        assert result.score == 1
        assert result.format_score == 1

    def test_case_change_fails_strict_format_even_if_content_matches(self) -> None:
        result = ExactFormatCheck().run("", "ready:5", {"accepted_answers": ["READY:5"], "strict_output": True})
        assert result.score == 5
        assert result.format_score == 1


class TestChecksRegistry:
    def test_json_output_registered(self) -> None:
        assert "json_output" in CHECKS
        assert isinstance(CHECKS["json_output"], JsonValidityCheck)

    def test_code_generation_registered(self) -> None:
        assert "code_generation" in CHECKS
        assert isinstance(CHECKS["code_generation"], PythonSyntaxCheck)

    def test_instruction_following_registered(self) -> None:
        assert "instruction_following" in CHECKS

    def test_exact_answer_registered(self) -> None:
        assert "exact_answer" in CHECKS


class TestStripCodeFences:
    def test_strips_fenced_block(self) -> None:
        raw = "```json\n{}\n```"
        assert _strip_code_fences(raw) == "{}"

    def test_no_fences_unchanged(self) -> None:
        raw = '{"key": 1}'
        assert _strip_code_fences(raw) == raw


class TestPartialCredit:
    def test_json_object_with_one_wrong_field_gets_partial_credit(self) -> None:
        from src.evaluators.deterministic_eval import JsonValidityCheck

        result = JsonValidityCheck().run(
            "", '{"a": 1, "b": 2, "c": 9, "d": 4}', {"expected_json": {"a": 1, "b": 2, "c": 3, "d": 4}}
        )

        assert (result.passed, result.score) == (False, 4.0)
        assert "75%" in result.reason

    def test_an_invented_field_counts_against_the_answer(self) -> None:
        from src.evaluators.deterministic_eval import json_agreement

        assert json_agreement({"a": 1, "b": 2, "extra": 0}, {"a": 1, "b": 2}) == pytest.approx(2 / 3)
        assert json_agreement([1, 2], [1, 2, 3]) == pytest.approx(2 / 3)
        assert json_agreement("x", {"a": 1}) == 0.0

    def test_code_passing_some_tests_gets_partial_credit(self) -> None:
        from src.evaluators.deterministic_eval import PythonExecutionCheck

        code = "def double(n):\n    return n * 2 if n < 3 else 0"
        result = PythonExecutionCheck().run(
            "",
            code,
            {
                "execute_code": True,
                "required_function": "double",
                "required_parameters": ["n"],
                "test_cases": [{"args": [n], "expected": n * 2} for n in range(5)],
            },
        )

        assert (result.passed, result.score) == (False, 1 + 4 * 3 / 5)
