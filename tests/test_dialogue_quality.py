"""Independent, deterministic two-turn quality contracts and offline integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from pydantic import ValidationError

from src.dialogue_cli import run_dialogue_command
from src.evaluators.dialogue_quality import (
    DialogueCase,
    DialogueCheck,
    check_response,
    load_dialogue_cases,
    run_dialogue_suite,
    score_dialogue,
    summarize_dialogues,
)
from src.evaluators.scenario_runner import ScenarioExecution, ScenarioOutcome, TurnExecution


def test_catalog_is_bounded_and_content_addressed(tmp_path: Path) -> None:
    cases, suite_id = load_dialogue_cases()
    assert len(cases) == 9
    assert len({case.scenario_id for case in cases}) == 9
    assert {case.construct_id for case in cases} == {
        "clarification_then_action",
        "format_re_attack",
        "negative_instruction_persistence",
    }
    assert all(len(case.scenario().turns) == 2 and case.scenario().limits.max_turns == 2 for case in cases)
    assert suite_id == load_dialogue_cases()[1]
    source = Path("data/prompts/dialogue_scenarios_v1.json")
    modified = json.loads(source.read_text())
    modified[0]["checks"][1][0]["value"] = "USD"
    alternate = tmp_path / "alternate.json"
    alternate.write_text(json.dumps(modified))
    assert load_dialogue_cases(alternate)[1] != suite_id
    modified[1]["scenario_id"] = modified[0]["scenario_id"]
    alternate.write_text(json.dumps(modified))
    with pytest.raises(ValueError, match="unique"):
        load_dialogue_cases(alternate)


def test_rejects_bad_rules_and_missing_second_turn() -> None:
    with pytest.raises(ValidationError):
        DialogueCheck(kind="contains")
    with pytest.raises(ValidationError):
        DialogueCase.model_validate(
            {
                "scenario_id": "bad",
                "use_case_id": "test",
                "construct": "format_re_attack",
                "turns": ["one"],
                "checks": [[{"kind": "question"}], [{"kind": "question"}]],
                "dry_run_responses": ["one", "two"],
            }
        )


def test_rules_reject_markdown_around_json_and_extra_fields() -> None:
    rule = DialogueCheck(kind="json_object", keys=["region"], values={"region": "eu"})
    assert check_response('{"region":"eu"}', rule)
    assert not check_response('```json\n{"region":"eu"}\n```', rule)
    assert not check_response('{"region":"eu","extra":true}', rule)
    assert not check_response("{not json}", rule)
    assert check_response("Which region?", DialogueCheck(kind="question"))
    assert not check_response("Which? Where?", DialogueCheck(kind="question"))
    assert check_response("No launch approved here", DialogueCheck(kind="forbidden", value="approved launch"))


def test_t2_drift_and_omission_are_conditional_on_t1_success() -> None:
    case = next(case for case in load_dialogue_cases()[0] if case.scenario_id == "negative_unverified_claim")
    good = TurnExecution("turn-1", 0, "Launch is pending review")
    bad = TurnExecution("turn-2", 1, "Launch approved")
    execution = ScenarioExecution(case.scenario_id, "a", (good, bad), ScenarioOutcome.SAFE_REFUSAL)
    row = score_dialogue(case, execution, "v1")
    assert row["t1_pass"] is True
    assert row["t2_pass"] is False
    assert row["drift"] is True and row["omission"] is True

    failed_t1 = TurnExecution("turn-1", 0, "Launch approved")
    row = score_dialogue(
        case, ScenarioExecution(case.scenario_id, "a", (failed_t1, bad), ScenarioOutcome.SAFE_REFUSAL), "v1"
    )
    assert row["t1_pass"] is False
    assert row["drift"] is None and row["omission"] is None


def test_aborted_and_empty_trajectories_do_not_count_as_pass_or_drift() -> None:
    case = load_dialogue_cases()[0][0]
    partial = ScenarioExecution(
        case.scenario_id,
        "a",
        (TurnExecution("turn-1", 0, "Which currency?"),),
        ScenarioOutcome.SCENARIO_ABORTED,
        error="TimeoutError",
    )
    row = score_dialogue(case, partial, "v1")
    assert row["t1_pass"] is True
    assert row["t2_pass"] is None and row["drift"] is None
    empty = ScenarioExecution(
        case.scenario_id,
        "a",
        (TurnExecution("turn-1", 0, ""), TurnExecution("turn-2", 1, "EUR")),
        ScenarioOutcome.INCONCLUSIVE,
    )
    assert score_dialogue(case, empty, "v1")["t1_pass"] is None


def test_summary_excludes_failed_turns_from_drift_denominator() -> None:
    case = load_dialogue_cases()[0][0]
    complete = score_dialogue(
        case,
        ScenarioExecution(
            case.scenario_id,
            "a",
            (TurnExecution("turn-1", 0, "Which currency?"), TurnExecution("turn-2", 1, "EUR")),
            ScenarioOutcome.SAFE_REFUSAL,
        ),
        "v1",
    )
    aborted = score_dialogue(
        case,
        ScenarioExecution(
            case.scenario_id, "a", (TurnExecution("turn-1", 0, "Which currency?"),), ScenarioOutcome.SCENARIO_ABORTED
        ),
        "v1",
    )
    summary = summarize_dialogues(pd.DataFrame([complete, aborted])).iloc[0]
    assert summary["completion_rate"] == 0.5
    assert summary["drift_eligible_count"] == 1
    assert summary["drift_rate"] == 0.0
    assert summary["omission_rate"] == 0.0


async def test_runner_retains_model_reply_and_aggregates_independently() -> None:
    cases, suite_id = load_dialogue_cases()
    seen: list[list[dict[str, str]]] = []

    async def complete(model: str, case: DialogueCase, messages: list[dict[str, str]]) -> str:
        seen.append(messages)
        if model == "unstable" and case.scenario_id == "format_json_status" and len(messages) == 4:
            return "```json\n{}\n```"
        return case.dry_run_responses[(len(messages) - 2) // 2]

    details, summary = await run_dialogue_suite(cases, suite_id, ["stable", "unstable"], complete)
    assert len(details) == 18
    assert len(seen) == 36
    assert any(len(messages) == 4 and messages[2]["role"] == "assistant" for messages in seen)
    assert details.loc[
        (details["model"] == "unstable") & (details["scenario_id"] == "format_json_status"), "drift"
    ].iloc[0]
    assert summary.set_index("model").loc["stable", "drift_rate"] == 0
    assert summary.set_index("model").loc["unstable", "drift_rate"] == pytest.approx(1 / 9)
    assert summary.set_index("model").loc["unstable", "omission_rate"] == pytest.approx(1 / 9)


async def test_offline_command_never_instantiates_network_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.dialogue_cli as cli

    monkeypatch.setattr(cli, "AsyncOpenRouterClient", MagicMock(side_effect=AssertionError("network")))
    stem = await run_dialogue_command(live=False, models_arg=None, output_dir=tmp_path)
    details = pd.read_json(f"{stem}_details.json")
    summary = pd.read_json(f"{stem}_summary.json")
    assert len(details) == 9 and len(summary) == 1
    assert summary.iloc[0]["drift_rate"] == 0.0
    assert summary.iloc[0]["evidence_source"] == "synthetic_offline"
    assert details["evidence_source"].eq("synthetic_offline").all()
    assert "response" not in details.columns
    assert not list(tmp_path.glob("benchmark_*"))


async def test_live_command_requires_explicit_opt_in_and_preserves_turn_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.dialogue_cli as cli

    cases, _ = load_dialogue_cases()
    client = MagicMock()
    client.chat_completion = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    seen: list[dict[str, object]] = []

    async def respond(**kwargs: object) -> MagicMock:
        seen.append(kwargs)
        case = next(case for case in cases if case.scenario_id == kwargs["scenario_id"])
        reply = MagicMock()
        reply.choices[0].message.content = case.dry_run_responses[kwargs["turn_index"]]
        return reply

    client.chat_completion.side_effect = respond
    monkeypatch.setattr(cli, "get_settings", lambda: MagicMock(target_models_list=["model-a"]))
    monkeypatch.setattr(cli, "AsyncOpenRouterClient", lambda settings: client)
    stem = await run_dialogue_command(live=True, models_arg=None, output_dir=tmp_path)
    assert len(seen) == 18
    assert {item["turn_index"] for item in seen} == {0, 1}
    assert all(item["usage_context"] == "dialogue_quality" for item in seen)
    assert pd.read_json(f"{stem}_summary.json").iloc[0]["evidence_source"] == "openrouter"
