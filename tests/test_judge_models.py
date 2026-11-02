"""Tests for the judge model preflight and one-command judge switch."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import check_judging, judge_models
from scripts.judge_models import CopilotModel, enabled_models, expected_judge_id, preflight, set_judge_model

PLAN = [
    CopilotModel("claude-opus-5.5", "Claude Opus 5.5", "Anthropic"),
    CopilotModel("claude-sonnet-5", "Claude Sonnet 5", "Anthropic"),
    CopilotModel("gpt-6-sol", "GPT-6 Sol", "OpenAI"),
    CopilotModel("gemini-3.8-flash", "Gemini 3.8 Flash", "Google"),
]


@pytest.fixture
def agents(tmp_path: Path) -> Path:
    target = tmp_path / "agents"
    target.mkdir()
    for provider in check_judging.PROVIDERS:
        shutil.copy(check_judging.AGENTS_DIR / f"judge-{provider}.agent.md", target)
    # Pin a known panel so the tests do not depend on the repository's current judge choice.
    set_judge_model(target, "anthropic", "Claude Opus 5.5 (copilot)")
    return target


def test_repository_judges_are_ready_on_the_reference_plan(agents: Path) -> None:
    lines, errors = preflight(agents, PLAN, {"gemini-3.8-flash", "gpt-6.1-sol"})

    assert errors == []
    assert "also benchmarked" in next(line for line in lines if "judge-google" in line)
    assert "also benchmarked" not in next(line for line in lines if "judge-openai" in line)


def test_a_model_missing_from_the_plan_blocks_and_lists_vendor_candidates(agents: Path) -> None:
    plan = [model for model in PLAN if model.id != "claude-opus-5.5"]

    _, errors = preflight(agents, plan, set())

    assert len(errors) == 1
    assert "judge-anthropic: `Claude Opus 5.5 (copilot)` is not enabled" in errors[0]
    assert "Enabled Anthropic models: Claude Sonnet 5 (copilot)" in errors[0]


def test_set_switches_model_and_identifier_together(agents: Path) -> None:
    path = set_judge_model(agents, "anthropic", "Claude Sonnet 5 (copilot)")

    text = path.read_text()
    assert "model: Claude Sonnet 5 (copilot)" in text
    assert '"judge": "copilot-claudesonnet5-anthropic"' in text
    assert "You are running as **Claude Sonnet 5 (Anthropic)**" in text
    assert preflight(agents, PLAN, set())[1] == []


def test_a_model_change_without_a_new_identifier_is_stale(agents: Path) -> None:
    path = agents / "judge-anthropic.agent.md"
    path.write_text(path.read_text().replace("model: Claude Opus 5.5 (copilot)", "model: Claude Sonnet 5 (copilot)"))

    _, errors = preflight(agents, PLAN, set())

    assert errors == [
        "judge-anthropic: identifier `copilot-claudeopus55-anthropic` does not match `Claude Sonnet 5 (copilot)`; "
        "expected `copilot-claudesonnet5-anthropic` (use --set to change both)"
    ]


def test_enabled_models_reads_the_latest_plan_and_drops_disabled_entries(tmp_path: Path) -> None:
    session = tmp_path / "logs" / "s1"
    session.mkdir(parents=True)
    (session / "models.json").write_text(
        json.dumps(
            [
                {
                    "id": "gpt-6-sol",
                    "name": "GPT-6 Sol",
                    "vendor": "OpenAI",
                    "policy": {"state": "enabled"},
                    "model_picker_enabled": True,
                },
                {"id": "grok-4.7", "name": "Grok 4.7", "vendor": "xAI", "policy": None, "model_picker_enabled": True},
                {
                    "id": "gpt-4.1",
                    "name": "GPT-4.1",
                    "vendor": "Azure OpenAI",
                    "policy": {"state": "enabled"},
                    "model_picker_enabled": False,
                },
            ]
        )
    )

    assert enabled_models([tmp_path / "logs"]) == [CopilotModel("gpt-6-sol", "GPT-6 Sol", "OpenAI")]
    assert enabled_models([tmp_path / "empty"]) is None


def test_benchmarked_ids_strip_the_openrouter_prefix(tmp_path: Path) -> None:
    selection = tmp_path / "model_selection.json"
    selection.write_text(json.dumps({"models": ["google/gemini-3.8-flash", "openai/gpt-6-luna:free"]}))

    assert judge_models.benchmarked_ids(selection) == {"gemini-3.8-flash", "gpt-6-luna"}


def test_identifier_convention_matches_the_current_agents() -> None:
    for provider in check_judging.PROVIDERS:
        spec = check_judging.judge_spec(provider)
        assert spec.judge_id == expected_judge_id(spec.model, provider)
