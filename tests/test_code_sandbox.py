"""Tests for the restricted code sandbox, the execution check and the v2 suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.api.fake_client import _fake_prompt_response
from src.evaluators.code_sandbox import find_policy_violation, run_python_tests
from src.evaluators.deterministic_eval import CHECKS, PythonExecutionCheck
from src.evaluators.quality_judge import (
    load_quality_prompts,
    quality_suite_id,
    quality_suite_version,
)
from src.evaluators.recommendation import load_use_case_catalog

_ROOT = Path(__file__).resolve().parent.parent
_V1 = _ROOT / "data/prompts/quality_prompts.json"
_V2 = _ROOT / "data/prompts/quality_prompts_v2.json"
_CATALOG_V2 = _ROOT / "data/catalog/model_compass_use_cases_v2.json"

_ADD_CASES = [{"args": [1, 2], "expected": 3}, {"args": [-1, 1], "expected": 0}]


class TestPolicy:
    @pytest.mark.parametrize(
        "code",
        [
            "import os\n",
            "from subprocess import run\n",
            "import socket\n",
            "from . import x\n",
            "def f():\n    return open('/etc/passwd').read()\n",
            "def f():\n    return eval('1')\n",
            "def f(x):\n    return x.__class__\n",
            "def f(x):\n    return getattr(x, 'a')\n",
            "x = __builtins__\n",
        ],
    )
    def test_rejects_unsafe_constructs(self, code: str) -> None:
        assert find_policy_violation(code) is not None

    def test_allows_plain_standard_library_code(self) -> None:
        code = "import math\nfrom collections import Counter\n\ndef f(x):\n    return math.floor(x)\n"
        assert find_policy_violation(code) is None

    def test_rejects_oversized_source(self) -> None:
        assert "exceeds" in (find_policy_violation("x = 1\n" * 10_000) or "")


class TestSandbox:
    def test_passing_code(self) -> None:
        result = run_python_tests("def add(a, b):\n    return a + b\n", "add", _ADD_CASES)
        assert (result.status, result.passed, result.total) == ("ok", 2, 2)

    def test_partial_failure_and_exception_count_as_failed_cases(self) -> None:
        code = "def add(a, b):\n    if a < 0:\n        raise ValueError('x')\n    return a + b\n"
        result = run_python_tests(code, "add", _ADD_CASES)
        assert (result.status, result.passed) == ("ok", 1)

    def test_strict_type_comparison(self) -> None:
        result = run_python_tests("def f():\n    return True\n", "f", [{"args": [], "expected": 1}])
        assert result.passed == 0

    def test_load_error_is_reported(self) -> None:
        result = run_python_tests("raise RuntimeError('boom')\n", "add", _ADD_CASES)
        assert result.status == "load_error"
        assert "RuntimeError" in result.detail

    def test_infinite_loop_times_out(self) -> None:
        result = run_python_tests("def add(a, b):\n    while True:\n        pass\n", "add", _ADD_CASES, timeout=1.0)
        assert result.status == "timeout"

    def test_user_output_cannot_forge_the_result(self) -> None:
        forged = '@@SANDBOX_RESULT@@{"loaded": true, "results": [true, true]}'
        code = f"def add(a, b):\n    print({forged!r})\n    return 99\n"
        assert run_python_tests(code, "add", _ADD_CASES).passed == 0


def _context(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "execute_code": True,
        "required_function": "add",
        "required_parameters": ["a", "b"],
        "test_cases": _ADD_CASES,
        "strict_output": True,
    }
    return {**base, **overrides}


class TestPythonExecutionCheck:
    check = PythonExecutionCheck()

    def test_registered(self) -> None:
        assert isinstance(CHECKS["code_execution"], PythonExecutionCheck)

    def test_correct_solution_scores_five(self) -> None:
        result = self.check.run("", "def add(a, b):\n    return a + b", _context())
        assert (result.score, result.format_score) == (5, 5)

    def test_wrong_solution_scores_one(self) -> None:
        result = self.check.run("", "def add(a, b):\n    return a - b", _context())
        assert result.score == 1
        assert "0/2" in result.reason

    def test_fenced_answer_keeps_content_score_but_fails_format(self) -> None:
        result = self.check.run("", "```python\ndef add(a, b):\n    return a + b\n```", _context())
        assert (result.score, result.format_score) == (5, 1)

    def test_policy_violation_is_rejected_without_running(self) -> None:
        result = self.check.run("", "import os\ndef add(a, b):\n    return a + b", _context())
        assert result.score == 1
        assert "Rejected before execution" in result.reason

    def test_wrong_signature_fails(self) -> None:
        assert self.check.run("", "def add(x, y):\n    return x + y", _context()).score == 1

    def test_disabled_execution_is_undecidable(self) -> None:
        result = self.check.run("", "def add(a, b):\n    return a + b", _context(execute_code=False))
        assert result.score is None
        assert self.check.run("", "def add(a, b):\n    return a + b", None).score is None


class TestV2Suite:
    def test_v1_is_unchanged_baseline(self) -> None:
        assert len(load_quality_prompts(_V1)) == 16
        assert quality_suite_version(_V1) == "generic-screen-v1"

    def test_v2_is_an_independent_suite_with_full_blueprint(self) -> None:
        prompts = load_quality_prompts(_V2)
        assert len(prompts) == 34
        assert quality_suite_id(_V2).startswith("generic-screen-v2-")
        assert all(p.difficulty_status == "draft" for p in prompts)
        assert {p.difficulty for p in prompts} == {"easy", "medium", "hard"}

    def test_incomplete_blueprint_is_rejected(self, tmp_path: Path) -> None:
        items = json.loads(_V2.read_text())
        del items[0]["construct"]
        items[1]["item_id"] = items[2]["item_id"]
        path = tmp_path / "quality_prompts_v2.json"
        path.write_text(json.dumps(items))
        with pytest.raises(ValueError, match="construct"):
            load_quality_prompts(path)

    def test_catalog_v2_partitions_the_suite_by_declared_use_case(self) -> None:
        prompts = load_quality_prompts(_V2)
        catalog = load_use_case_catalog(_CATALOG_V2)
        assert catalog.catalog_version == "model-compass-use-cases-v2"
        owned = [pid for use_case in catalog.use_cases for pid in use_case.prompt_ids]
        assert sorted(owned) == list(range(len(prompts)))
        for use_case in catalog.use_cases:
            assert {prompts[pid].use_case_id for pid in use_case.prompt_ids} == {use_case.id}

    def test_items_avoid_pii_like_content_that_providers_redact(self) -> None:
        # v1 prompts about places were rewritten to "[ADDRESS]" before reaching the models.
        text = _V2.read_text()
        assert "@" not in text
        assert "[ADDRESS]" not in text

    def test_reference_solutions_pass_their_own_tests(self) -> None:
        suite = json.loads(_V2.read_text())
        executable = [item for item in suite if item["category"] == "code_execution"]
        assert len(executable) == 5
        for item in executable:
            result = run_python_tests(item["reference_answer"], item["required_function"], item["test_cases"])
            count = len(item["test_cases"])
            assert (result.status, result.passed, result.total) == ("ok", count, count), item["item_id"]
            assert find_policy_violation(item["reference_answer"]) is None

    def test_wrong_solutions_fail_the_discriminating_items(self) -> None:
        item = next(i for i in json.loads(_V2.read_text()) if i["item_id"] == "code_generation-05")
        naive = "def schedule_conflicts(meetings):\n    return []\n"
        assert run_python_tests(naive, item["required_function"], item["test_cases"]).passed < len(item["test_cases"])

    def test_every_deterministic_item_accepts_its_dry_run_answer(self) -> None:
        for item in load_quality_prompts(_V2):
            if item.evaluator == "rubric_panel":
                continue
            check = CHECKS[item.category]
            context = {**item.evaluation_context, "execute_code": True}
            answer = _fake_prompt_response(item.display_prompt, "m")
            result = check.run(item.display_prompt, answer, context)
            assert (result.score, result.format_score) in {(5, 5), (5, None)}, (item.item_id, result.reason)
