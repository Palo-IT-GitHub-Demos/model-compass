"""Restricted execution of generated Python for the deterministic code checks.

This is defence in depth, not a security boundary. Untrusted model output is
(1) rejected up front when it uses imports or constructs outside a small
allowlist, then (2) run in a separate interpreter with an empty environment, a
throw-away working directory, a wall-clock timeout and, where the OS enforces
them, CPU/file-size/memory limits. It does not block network access beyond the
import allowlist and must not be pointed at code that is not model output
under evaluation. It is disabled unless ``QUALITY_CODE_EXECUTION`` is set.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "bisect",
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "fractions",
        "functools",
        "heapq",
        "itertools",
        "json",
        "math",
        "operator",
        "re",
        "statistics",
        "string",
        "typing",
    }
)
FORBIDDEN_CALLS = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "eval",
        "exec",
        "exit",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "quit",
        "setattr",
        "vars",
    }
)
ALLOWED_DUNDERS = frozenset({"__init__", "__name__"})
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_SOURCE_CHARS = 20_000
_CPU_LIMIT_SECONDS = 4
_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
_RESULT_MARKER = "@@SANDBOX_RESULT@@"

_HARNESS = r"""
import io, json, resource, sys

payload = json.loads(sys.stdin.read())
limits = [("RLIMIT_CPU", payload["cpu"]), ("RLIMIT_FSIZE", 0)]
if sys.platform.startswith("linux"):
    limits.append(("RLIMIT_AS", payload["memory"]))
for name, value in limits:
    try:
        resource.setrlimit(getattr(resource, name), (value, value))
    except (ValueError, OSError):
        pass


class _Null(io.TextIOBase):
    def write(self, text):
        return len(text)


real_stdout = sys.stdout
sys.stdout = _Null()
out = {"loaded": False, "results": [], "error": ""}
try:
    namespace = {"__name__": "generated_solution"}
    exec(compile(payload["code"], "<model-response>", "exec"), namespace)
    function = namespace[payload["function"]]
    out["loaded"] = True
except BaseException as exc:
    out["error"] = (type(exc).__name__ + ": " + str(exc))[:200]
else:
    for case in payload["cases"]:
        try:
            actual = json.dumps(function(*case["args"]), sort_keys=True)
            out["results"].append(actual == json.dumps(case["expected"], sort_keys=True))
        except BaseException:
            out["results"].append(False)
sys.stdout = real_stdout
print("\n" + payload["marker"] + json.dumps(out))
"""


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of running generated code against test cases."""

    status: str
    """``ok``, ``load_error``, ``timeout``, ``crashed`` or ``unavailable``."""

    passed: int
    total: int
    detail: str
    duration_seconds: float

    @property
    def is_model_failure(self) -> bool:
        """Whether the outcome is attributable to the response rather than the harness."""
        return self.status != "unavailable"


def find_policy_violation(code: str) -> str | None:
    """Return why *code* is outside the sandbox policy, or ``None`` when allowed."""
    if len(code) > MAX_SOURCE_CHARS:
        return f"source exceeds {MAX_SOURCE_CHARS} characters"
    try:
        tree = ast.parse(code, filename="<model-response>", mode="exec")
    except SyntaxError as exc:
        return f"SyntaxError: {exc.msg}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORT_ROOTS:
                    return f"import of '{alias.name}' is not allowed"
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in ALLOWED_IMPORT_ROOTS:
                return f"import from '{'.' * node.level}{node.module or ''}' is not allowed"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            return f"call to '{node.func.id}' is not allowed"
        elif isinstance(node, ast.Attribute) and _is_blocked_dunder(node.attr):
            return f"access to attribute '{node.attr}' is not allowed"
        elif isinstance(node, ast.Name) and _is_blocked_dunder(node.id):
            return f"use of name '{node.id}' is not allowed"
    return None


def _is_blocked_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__") and name not in ALLOWED_DUNDERS


def run_python_tests(
    code: str,
    function: str,
    cases: Sequence[dict[str, object]],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> SandboxResult:
    """Run ``function`` from *code* against ``{"args": [...], "expected": ...}`` cases.

    The caller must already have checked :func:`find_policy_violation`. Only
    the code hash, status and counts are logged, never the source itself.
    """
    code_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]
    total = len(cases)
    payload = json.dumps(
        {
            "code": code,
            "function": function,
            "cases": list(cases),
            "cpu": _CPU_LIMIT_SECONDS,
            "memory": _MEMORY_LIMIT_BYTES,
            "marker": _RESULT_MARKER,
        }
    )
    started = time.monotonic()
    result = _execute(payload, total, timeout)
    duration = time.monotonic() - started
    result = SandboxResult(result.status, result.passed, result.total, result.detail, duration)
    logger.info(
        "[sandbox] code_sha256=%s function=%s status=%s passed=%d/%d duration=%.2fs",
        code_sha,
        function,
        result.status,
        result.passed,
        result.total,
        duration,
    )
    return result


def _execute(payload: str, total: int, timeout: float) -> SandboxResult:
    try:
        with tempfile.TemporaryDirectory(prefix="model-compass-sandbox-") as workdir:
            completed = subprocess.run(  # noqa: S603 - fixed argv, payload on stdin, no shell
                [sys.executable, "-I", "-S", "-c", _HARNESS],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
                env={},
                check=False,
            )
    except subprocess.TimeoutExpired:
        return SandboxResult("timeout", 0, total, f"Exceeded the {timeout:g}s time limit.", 0.0)
    except OSError as exc:
        return SandboxResult("unavailable", 0, total, f"Sandbox could not start: {exc}", 0.0)

    marked = [line for line in completed.stdout.splitlines() if line.startswith(_RESULT_MARKER)]
    if not marked:
        if completed.returncode < 0:
            return SandboxResult("crashed", 0, total, f"Process killed by signal {-completed.returncode}.", 0.0)
        return SandboxResult("unavailable", 0, total, "Sandbox produced no result.", 0.0)
    try:
        outcome = json.loads(marked[-1][len(_RESULT_MARKER) :])
    except json.JSONDecodeError:
        return SandboxResult("unavailable", 0, total, "Sandbox result was not valid JSON.", 0.0)
    if not outcome.get("loaded"):
        return SandboxResult("load_error", 0, total, str(outcome.get("error", "")), 0.0)
    passed = sum(1 for item in outcome.get("results", []) if item is True)
    return SandboxResult("ok", passed, total, "", 0.0)
