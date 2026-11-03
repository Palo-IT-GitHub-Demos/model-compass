"""The candidate pilot scores answers itself and says which candidates no model misses."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "pilot_quality_items.py"


@pytest.fixture(scope="module")
def pilot() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pilot_quality_items", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_committed_candidate_has_a_deterministic_check(pilot: ModuleType) -> None:
    candidates = pilot.load_candidates()
    assert candidates
    assert all(item["category"] in pilot.CHECKS for item in candidates)


def test_a_candidate_that_needs_the_judges_is_refused(pilot: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps([{"item_id": "x-1", "category": "generic_judgment", "prompt": "Summarize."}]))
    with pytest.raises(ValueError, match="x-1"):
        pilot.load_candidates(path)


def test_the_summary_marks_saturated_items_and_names_the_models_that_miss(pilot: ModuleType) -> None:
    details = pd.DataFrame(
        [
            {"item_id": "easy", "model": "a/strong", "attempt": 0, "score": 5.0},
            {"item_id": "easy", "model": "b/weak", "attempt": 0, "score": 5.0},
            {"item_id": "hard", "model": "a/strong", "attempt": 0, "score": 5.0},
            {"item_id": "hard", "model": "b/weak", "attempt": 0, "score": 1.0},
            {"item_id": "hard", "model": "b/weak", "attempt": 1, "score": 5.0},
        ]
    )

    summary = pilot.summarize(details)

    assert summary.loc["easy", "status"] == "saturated"
    assert summary.loc["hard", "status"] == "missed by 1: weak"
    assert summary.loc["hard", "b/weak"] == 3.0


def test_without_live_the_pilot_only_lists_the_candidates(
    pilot: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert pilot.main([]) == 0
    assert "add --live to pilot them (paid)" in capsys.readouterr().out


def test_an_unknown_item_is_refused_before_any_call(pilot: ModuleType) -> None:
    with pytest.raises(SystemExit):
        pilot.main(["--live", "--items", "no-such-item"])
