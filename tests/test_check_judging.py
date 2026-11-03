"""Tests for the blind judging score check run before `make merge`."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import check_judging
from scripts.check_judging import JudgeSpec, check_batch, judge_spec, validate_scores

TS = "20260101_000000"
SPEC = JudgeSpec("openai", "gpt-6-sol", "copilot-gpt6sol-openai")


def _part(tmp_path: Path, name: str = f"judging_{TS}_part01of01.json") -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "timestamp": TS,
                "pending_judgments": [
                    {"prompt_id": 7, "attempt": 0, "responses": {"A": "yes", "B": "no", "C": ""}},
                    {"prompt_id": 7, "attempt": 1, "responses": {"A": "yes", "B": "no"}},
                ],
            }
        )
    )
    return path


def _scores(judge: str = SPEC.judge_id, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "timestamp": TS,
        "judge": judge,
        "scores": [
            {
                "prompt_id": 7,
                "attempt": attempt,
                "judgments": [{"alias": alias, "reasoning": "2/2 criteria met.", "score": 5} for alias in "AB"],
            }
            for attempt in (0, 1)
        ],
    }
    payload.update(overrides)
    return payload


def _write_scores(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / f"scores_{TS}_openai_part01of01.json"
    path.write_text(json.dumps(payload))
    return path


def _debug_log(
    logs: Path, model: str, *, reads: tuple[str, ...] = (), writes: tuple[str, ...] = (), name: str = "a"
) -> None:
    session = logs / "session"
    session.mkdir(parents=True, exist_ok=True)
    records = [
        {"type": "session_start", "name": "session_start", "ts": 1000, "attrs": {}},
        {
            "type": "user_message",
            "name": "user_message",
            "ts": 1000,
            "attrs": {"content": f"Batch timestamp: `{TS}`. Read `data/intermediate/judging_{TS}_part01of01.json`"},
        },
        {"type": "llm_request", "name": f"chat:{model}", "ts": 1001, "attrs": {"model": model}},
        *(
            {"type": "tool_call", "name": "read_file", "ts": 1002, "attrs": {"args": json.dumps({"filePath": path})}}
            for path in reads
        ),
        *(
            {"type": "tool_call", "name": "create_file", "ts": 1003, "attrs": {"args": json.dumps({"filePath": path})}}
            for path in writes
        ),
    ]
    (session / f"runSubagent-judge-openai-{name}.jsonl").write_text("\n".join(json.dumps(r) for r in records))


def test_repository_judges_declare_distinct_single_models_and_ids() -> None:
    specs = [judge_spec(provider) for provider in check_judging.PROVIDERS]

    assert [spec.model for spec in specs] == ["claude-sonnet-5", "gpt-6-sol", "gemini-3.8-flash"]
    assert len({spec.judge_id for spec in specs}) == 3
    assert all(spec.judge_id.endswith(f"-{spec.provider}") for spec in specs)


@pytest.mark.parametrize(
    ("model_line", "expected_model"),
    [
        ("Gemini 4 Argon (copilot)", "gemini-4-argon"),
        ("['GPT-6 Sol (copilot)', 'GPT-6 Luna (copilot)']", "gpt-6-sol"),
    ],
)
def test_judge_spec_maps_the_qualified_name_to_the_logged_model_id(
    tmp_path: Path, model_line: str, expected_model: str
) -> None:
    (tmp_path / "judge-google.agent.md").write_text(f'---\nmodel: {model_line}\n---\n"judge": "copilot-x-google"\n')
    spec = judge_spec("google", tmp_path)
    assert (spec.model, spec.judge_id) == (expected_model, "copilot-x-google")


@pytest.mark.parametrize("model_line", ["gemini-3.8-flash", "['gemini-3.8-flash', 'Gemini 3.8 Flash (copilot)']"])
def test_judge_spec_refuses_a_bare_model_id(tmp_path: Path, model_line: str) -> None:
    (tmp_path / "judge-google.agent.md").write_text(f'---\nmodel: {model_line}\n---\n"judge": "copilot-x-google"\n')
    with pytest.raises(ValueError, match="qualified name"):
        judge_spec("google", tmp_path)


def test_valid_scores_cover_exactly_the_non_empty_responses(tmp_path: Path) -> None:
    _part(tmp_path)
    (part,) = check_judging.batch_parts(tmp_path, TS)
    assert validate_scores(_scores(), SPEC, TS, part.expected) == []


@pytest.mark.parametrize(
    ("mutate", "expected_problem"),
    [
        (lambda p: p["scores"][0]["judgments"].pop(), "1 missing: prompt 7 attempt 0 alias B"),
        (lambda p: p["scores"][1]["judgments"].append(dict(p["scores"][1]["judgments"][0])), "1 scored twice"),
        (lambda p: p["scores"][0]["judgments"][0].update(score=6), "score 6 outside 1–5"),
        (lambda p: p["scores"][0]["judgments"][0].update(reasoning="[DRY-RUN] x"), "synthetic dry-run"),
        (lambda p: p["scores"][0]["judgments"].append({"alias": "C", "reasoning": "r", "score": 1}), "1 unexpected"),
        (lambda p: p.update(timestamp="2026-01-01"), "timestamp is '2026-01-01'"),
        (lambda p: p.update(judge="copilot-gpt61terra-openai"), "judge is 'copilot-gpt61terra-openai'"),
    ],
)
def test_invalid_scores_are_reported(tmp_path: Path, mutate: object, expected_problem: str) -> None:
    _part(tmp_path)
    (part,) = check_judging.batch_parts(tmp_path, TS)
    payload = _scores()
    mutate(payload)  # type: ignore[operator]

    problems = validate_scores(payload, SPEC, TS, part.expected)

    assert any(expected_problem in problem for problem in problems), problems


def test_model_audit_accepts_the_declared_model(tmp_path: Path) -> None:
    part = _part(tmp_path)
    scores = _write_scores(tmp_path, _scores())
    _debug_log(tmp_path / "logs", "gpt-6-sol", reads=(str(part),), writes=(str(scores),))

    (status,) = check_batch(tmp_path, TS, [SPEC], [tmp_path / "logs"])

    assert (status.state, status.problems) == ("ok", [])


def test_model_audit_rejects_a_silent_model_fallback(tmp_path: Path) -> None:
    part = _part(tmp_path)
    scores = _write_scores(tmp_path, _scores())
    _debug_log(tmp_path / "logs", "gpt-6-luna", reads=(str(part),), writes=(str(scores),))

    (status,) = check_batch(tmp_path, TS, [SPEC], [tmp_path / "logs"])

    assert status.state == "invalid"
    assert status.problems == ["ran on gpt-6-luna, expected gpt-6-sol"]


def test_model_audit_rejects_a_judge_that_read_the_alias_map(tmp_path: Path) -> None:
    part = _part(tmp_path)
    scores = _write_scores(tmp_path, _scores())
    _debug_log(
        tmp_path / "logs", "gpt-6-sol", reads=(str(part), str(tmp_path / f"pending_{TS}.json")), writes=(str(scores),)
    )

    (status,) = check_batch(tmp_path, TS, [SPEC], [tmp_path / "logs"])

    assert status.state == "invalid"
    assert "read files other than its part" in status.problems[0]


def test_audit_uses_the_run_that_wrote_the_file(tmp_path: Path) -> None:
    part = _part(tmp_path)
    scores = _write_scores(tmp_path, _scores())
    _debug_log(tmp_path / "logs", "gpt-6-luna", reads=(str(part),), name="failed-first-try")
    _debug_log(tmp_path / "logs", "gpt-6-sol", reads=(str(part),), writes=(str(scores),), name="writer")

    (status,) = check_batch(tmp_path, TS, [SPEC], [tmp_path / "logs"])

    assert status.state == "ok"


def test_scores_without_a_debug_log_stay_unverified_unless_the_audit_is_skipped(tmp_path: Path) -> None:
    _part(tmp_path)
    _write_scores(tmp_path, _scores())

    assert check_batch(tmp_path, TS, [SPEC], [tmp_path / "logs"])[0].state == "unverified"
    assert check_batch(tmp_path, TS, [SPEC], None)[0].state == "ok"


def test_unsplit_batch_uses_the_single_file_names(tmp_path: Path) -> None:
    _part(tmp_path, f"judging_{TS}.json")

    (status,) = check_batch(tmp_path, TS, [SPEC], None)

    assert (status.state, status.score_path.name) == ("missing", f"scores_{TS}_openai.json")


def test_main_quarantines_invalid_files_and_prints_the_delegations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    intermediate = tmp_path / "intermediate"
    intermediate.mkdir()
    (intermediate / f"judging_{TS}.json").write_text("{}")
    _part(intermediate)
    _write_scores(intermediate, _scores(judge="copilot-gpt61terra-openai"))
    monkeypatch.setattr(check_judging, "INTERMEDIATE_DIR", intermediate)
    monkeypatch.setattr(check_judging, "PROVIDERS", ("openai",))
    monkeypatch.setitem(os.environ, check_judging.DEBUG_LOGS_ENV, str(tmp_path / "logs"))

    assert check_judging.main(["--quarantine"]) == 0

    output = capsys.readouterr().out
    assert (intermediate / "rejected_scores" / f"scores_{TS}_openai_part01of01.json").exists()
    assert "0/1 parts judged and verified." in output
    assert output.rstrip().endswith("STATUS: INCOMPLETE — do not run `make merge`")
    part_path = (intermediate / f"judging_{TS}_part01of01.json").as_posix()
    assert f"TODO judge-openai | Batch timestamp: `{TS}`. Read `{part_path}`" in output


def test_strict_mode_fails_while_the_batch_is_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    intermediate = tmp_path / "intermediate"
    intermediate.mkdir()
    (intermediate / f"judging_{TS}.json").write_text("{}")
    _part(intermediate)
    monkeypatch.setattr(check_judging, "INTERMEDIATE_DIR", intermediate)
    monkeypatch.setattr(check_judging, "PROVIDERS", ("openai",))

    assert check_judging.main(["--skip-model-audit", "--strict"]) == 2
    _write_scores(intermediate, _scores())
    assert check_judging.main(["--skip-model-audit", "--strict"]) == 0
