"""Separate, deterministic two-turn dialogue quality screen (not legacy quality)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.evaluators.scenario_runner import (
    ScenarioDefinition,
    ScenarioExecution,
    ScenarioLimits,
    ScenarioTurn,
    execute_scenario,
)

DEFAULT_DIALOGUE_CATALOG = Path("data/prompts/dialogue_scenarios_v1.json")


class DialogueCheck(BaseModel):
    """A rule verified on one full assistant response without an LLM judge."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["question", "exact", "json_object", "contains", "forbidden"]
    value: str | None = None
    keys: list[str] | None = None
    values: dict[str, str | int | float | bool] | None = None

    @model_validator(mode="after")
    def validate_rule(self) -> DialogueCheck:
        """Reject rules whose expected behavior cannot be evaluated."""
        if self.kind in {"exact", "contains", "forbidden"} and not (self.value and self.value.strip()):
            raise ValueError(f"{self.kind} requires a non-empty value")
        if self.kind == "json_object" and (not self.keys or self.values is None or set(self.keys) != set(self.values)):
            raise ValueError("json_object requires matching keys and values")
        return self


class DialogueCase(BaseModel):
    """Versioned two-turn task and a pair of deterministic response contracts."""

    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(min_length=1)
    use_case_id: str = Field(min_length=1)
    construct_id: Literal["clarification_then_action", "format_re_attack", "negative_instruction_persistence"] = Field(
        alias="construct"
    )
    turns: tuple[str, str]
    checks: tuple[list[DialogueCheck], list[DialogueCheck]]
    dry_run_responses: tuple[str, str]

    @model_validator(mode="after")
    def validate_case(self) -> DialogueCase:
        """Keep both requests and both rubrics non-empty."""
        if any(not turn.strip() for turn in self.turns) or any(not rules for rules in self.checks):
            raise ValueError("both turns and their rule sets must be non-empty")
        return self

    def scenario(self) -> ScenarioDefinition:
        """Build the same bounded conversation contract used by the security scanner."""
        return ScenarioDefinition(
            scenario_id=self.scenario_id,
            name=self.scenario_id,
            turns=(ScenarioTurn(self.turns[0], "turn-1"), ScenarioTurn(self.turns[1], "turn-2")),
            category_id=self.use_case_id,
            mode="sequential_multi_turn",
            limits=ScenarioLimits(max_turns=2, max_total_tokens=2048),
        )


def load_dialogue_cases(path: Path = DEFAULT_DIALOGUE_CATALOG) -> tuple[list[DialogueCase], str]:
    """Validate the entire suite and return its content-addressed version hash."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Dialogue catalog must be a non-empty list")
    cases = [DialogueCase.model_validate(item) for item in raw]
    ids = [case.scenario_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Dialogue scenario IDs must be unique")
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return cases, f"dialogue-v1-{hashlib.sha256(canonical.encode()).hexdigest()[:12]}"


def check_response(response: str, rule: DialogueCheck) -> bool:
    """Apply a bounded literal/JSON rule; never treat a format failure as correct."""
    if not response.strip():
        return False
    if rule.kind == "question":
        return response.strip().endswith("?") and response.count("?") == 1
    if rule.kind == "json_object":
        try:
            value = json.loads(response)
        except (ValueError, TypeError):
            return False
        return isinstance(value, dict) and set(value) == set(rule.keys or ()) and value == rule.values
    if rule.kind == "exact":
        return response.strip() == rule.value
    assert rule.value is not None
    phrase = r"(?<!\w)" + re.escape(rule.value) + r"(?!\w)"
    present = re.search(phrase, response, flags=re.IGNORECASE) is not None
    return present if rule.kind == "contains" else not present


def score_dialogue(case: DialogueCase, execution: ScenarioExecution, suite_id: str) -> dict[str, object]:
    """Score each turn independently; leave drift undefined on failed trajectories."""
    complete = execution.completed_turn_count == 2 and all(turn.response.strip() for turn in execution.turns)
    first_ok = (
        all(check_response(execution.turns[0].response, rule) for rule in case.checks[0])
        if execution.turns and execution.turns[0].response.strip()
        else None
    )
    second_ok = all(check_response(execution.turns[1].response, rule) for rule in case.checks[1]) if complete else None
    # Omission: a positively required T2 rule disappears after T1 success.
    required = [rule for rule in case.checks[1] if rule.kind in {"exact", "contains", "json_object"}]
    omitted = (
        any(not check_response(execution.turns[1].response, rule) for rule in required)
        if complete and first_ok
        else None
    )
    return {
        "model": execution.model,
        "scenario_id": case.scenario_id,
        "use_case_id": case.use_case_id,
        "construct": case.construct_id,
        "suite_id": suite_id,
        "outcome": execution.outcome.value,
        "turn_count": execution.completed_turn_count,
        "t1_pass": first_ok,
        "t2_pass": second_ok,
        "drift": (not second_ok) if complete and first_ok else None,
        "omission": omitted,
    }


def summarize_dialogues(details: pd.DataFrame) -> pd.DataFrame:
    """Report completion, turn integrity and conditional T1→T2 drift per model."""
    if details.empty:
        return pd.DataFrame()
    result = details.assign(
        complete=details["turn_count"].eq(2) & details["t1_pass"].notna() & details["t2_pass"].notna(),
        eligible=details["drift"].notna(),
    )
    summary = result.groupby("model", as_index=False).agg(
        suite_id=("suite_id", "first"),
        scenario_count=("scenario_id", "size"),
        completion_rate=("complete", "mean"),
        t1_integrity_rate=("t1_pass", "mean"),
        t2_integrity_rate=("t2_pass", "mean"),
        drift_eligible_count=("eligible", "sum"),
        drift_rate=("drift", "mean"),
        omission_rate=("omission", "mean"),
    )
    return summary


async def run_dialogue_suite(
    cases: list[DialogueCase],
    suite_id: str,
    models: list[str],
    completion: Callable[[str, DialogueCase, list[dict[str, str]]], Awaitable[str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Execute each two-turn trajectory in isolation; return separate detail and summary."""
    rows: list[dict[str, object]] = []
    for model in models:
        for case in cases:

            async def complete(messages: list[dict[str, str]], _model: str = model, _case: DialogueCase = case) -> str:
                return await completion(_model, _case, messages)

            execution = await execute_scenario(
                case.scenario(),
                model=model,
                system_prompt="Follow the user's task while retaining valid constraints from earlier turns.",
                completion=complete,
            )
            rows.append(score_dialogue(case, execution, suite_id))
    details = pd.DataFrame(rows)
    return details, summarize_dialogues(details)
