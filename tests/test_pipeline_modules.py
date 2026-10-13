"""Compatibility contracts across the pipeline facade and extracted modules."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import src.main as facade
from src.evaluators.quality_judge import CollectResult
from src.pipeline_cli import build_arg_parser
from src.pipeline_merge import merge_results


def test_facade_merge_matches_extracted_aggregation() -> None:
    models = ["model-a", "model-b"]
    pricing = pd.DataFrame(
        {
            "model_id": models,
            "prompt_price_per_token": [0.001, 0.002],
            "completion_price_per_token": [0.001, 0.002],
            "context_length": [4000, 8000],
        }
    )
    quality = pd.DataFrame({"model": models, "prompt_id": [0, 0], "score": [5, 3], "quality_dimension": ["a", "a"]})
    security = pd.DataFrame({"model": models, "rsi": [80, 60]})
    pd.testing.assert_frame_equal(
        facade._merge_results(models, pricing, quality, security, quality_prompt_count=1),
        merge_results(models, pricing, quality, security, quality_prompt_count=1),
    )


def test_facade_export_respects_patched_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(facade, "_RESULTS_DIR", tmp_path)
    stem = facade._export(pd.DataFrame({"model": ["example"]}))
    assert stem.parent == tmp_path
    assert json.loads(Path(f"{stem}.json").read_text())[0]["model"] == "example"


def test_facade_pending_respects_patched_catalog_and_preserves_blindness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "catalog_version": "test",
                "description": "test",
                "weights": {
                    "quality": 0.5,
                    "security": 0.25,
                    "cost": 0.2,
                    "performance": 0.05,
                },
                "use_cases": [
                    {
                        "id": "test",
                        "name": "Test",
                        "description": "Test",
                        "prompt_ids": [0],
                        "minimum_quality_score": 3.0,
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(facade, "_INTERMEDIATE_DIR", tmp_path)
    monkeypatch.setattr(facade, "_USE_CASE_CATALOG", catalog)
    result = CollectResult()
    result.pending_judgments = [
        {
            "prompt_id": 0,
            "prompt": "prompt",
            "alias_map": {"A": "model-a"},
            "responses": {"A": "raw"},
            "responses_for_judging": {"A": "redacted"},
        }
    ]
    path = facade._save_pending(["model-a"], pd.DataFrame(), pd.DataFrame(), result, pd.DataFrame())
    pending = json.loads(path.read_text())
    judging = json.loads((tmp_path / path.name.replace("pending_", "judging_")).read_text())
    assert pending["use_case_catalog_version"] == "test"
    assert pending["pending_judgments"][0]["responses"]["A"] == "raw"
    assert judging["pending_judgments"][0]["responses"]["A"] == "redacted"
    assert "alias_map" not in judging["pending_judgments"][0]


def test_cli_keeps_free_form_subcommand_and_facade_choices() -> None:
    parser = build_arg_parser({"basic": None}, {"v2": None})
    assert parser.parse_args(["unknown"]).subcommand == "unknown"
    assert facade._build_arg_parser().parse_args(["--quality-suite", "v2"]).quality_suite == "v2"
