"""Tests for quality-suite diagnostics (item analysis, judge agreement)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.evaluators.quality_diagnostics import (
    analyze_items,
    krippendorff_alpha_interval,
    summarize_judge_agreement,
)


def _scores(per_prompt: dict[int, dict[str, float]]) -> pd.DataFrame:
    rows = [
        {"model": model, "prompt_id": pid, "attempt": 0, "score": score, "quality_dimension": "d"}
        for pid, by_model in per_prompt.items()
        for model, score in by_model.items()
    ]
    return pd.DataFrame(rows)


class TestAnalyzeItems:
    def test_flags_saturated_floor_and_discriminating_items(self) -> None:
        df = _scores(
            {
                0: {"a": 5, "b": 5, "c": 5, "d": 5},
                1: {"a": 1, "b": 1, "c": 2, "d": 1},
                2: {"a": 5, "b": 4, "c": 2, "d": 1},
                3: {"a": 5, "b": 4, "c": 3, "d": 1},
            }
        )
        items = analyze_items(df).set_index("prompt_id")
        assert items.loc[0, "item_status"] == "saturated"
        assert items.loc[1, "item_status"] == "floor"
        assert items.loc[2, "item_status"] == "ok"
        assert items.loc[2, "discrimination"] > 0.5

    def test_negative_discrimination_when_strong_models_fail(self) -> None:
        df = _scores(
            {
                0: {"a": 5, "b": 4, "c": 2, "d": 1},
                1: {"a": 5, "b": 4, "c": 3, "d": 1},
                2: {"a": 1, "b": 3, "c": 4, "d": 5},
            }
        )
        items = analyze_items(df).set_index("prompt_id")
        assert items.loc[2, "item_status"] == "negative_discrimination"

    def test_too_few_models_is_reported_not_scored(self) -> None:
        items = analyze_items(_scores({0: {"a": 5, "b": 2}, 1: {"a": 4, "b": 3}}))
        assert set(items["item_status"]) == {"insufficient_models"}

    def test_empty_input_returns_expected_columns(self) -> None:
        assert analyze_items(pd.DataFrame()).empty


def _ratings(units: list[list[int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"unit": u, "score": s} for u, scores in enumerate(units) for s in scores],
    )


class TestKrippendorffAlpha:
    def test_perfect_agreement_is_one(self) -> None:
        assert krippendorff_alpha_interval(_ratings([[1, 1, 1], [3, 3, 3], [5, 5, 5]])) == 1.0

    def test_matches_reference_value(self) -> None:
        # Hand-computed: n=12, sum=36, sum_sq=140 -> De=768/132, Do=24/12 -> alpha=0.65625
        ratings = _ratings([[1, 1, 1], [3, 3, 3], [5, 5, 5], [1, 3, 5]])
        assert abs(krippendorff_alpha_interval(ratings) - 0.65625) < 1e-9

    def test_random_disagreement_is_not_high(self) -> None:
        assert krippendorff_alpha_interval(_ratings([[1, 5, 3], [5, 1, 3], [3, 5, 1], [1, 3, 5]])) < 0.2

    def test_no_variance_or_single_unit_is_nan(self) -> None:
        assert np.isnan(krippendorff_alpha_interval(_ratings([[4, 4, 4], [4, 4, 4]])))
        assert np.isnan(krippendorff_alpha_interval(_ratings([[1, 5, 3]])))
        assert np.isnan(krippendorff_alpha_interval(pd.DataFrame(columns=["unit", "score"])))


def _verdict_df(units: list[dict[str, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "model": [f"m{i}" for i in range(len(units))],
            "quality_dimension": "d",
            "judge_verdicts": [
                json.dumps([{"judge_id": j, "score": s, "reasoning": ""} for j, s in u.items()]) for u in units
            ],
        }
    )


class TestSummarizeJudgeAgreement:
    def test_reports_panel_judge_and_dimension_rows(self) -> None:
        df = _verdict_df(
            [
                {"a": 5, "b": 5, "c": 5},
                {"a": 1, "b": 1, "c": 2},
                {"a": 3, "b": 3, "c": 3},
            ]
        )
        summary = summarize_judge_agreement(df).set_index("scope")
        assert {"panel", "judge:a", "judge:c", "dimension:d"} <= set(summary.index)
        panel = summary.loc["panel"]
        assert panel["agreement_status"] == "acceptable"
        assert abs(panel["exact_agreement_rate"] - 2 / 3) < 1e-9
        assert panel["within_one_rate"] == 1.0
        assert summary.loc["judge:c", "mean_offset_vs_panel"] > 0

    def test_flags_low_agreement(self) -> None:
        df = _verdict_df([{"a": 1, "b": 5, "c": 3}, {"a": 5, "b": 1, "c": 3}, {"a": 3, "b": 5, "c": 1}])
        assert summarize_judge_agreement(df).set_index("scope").loc["panel", "agreement_status"] == "low_agreement"

    def test_legacy_or_deterministic_rows_yield_empty_frame(self) -> None:
        assert summarize_judge_agreement(pd.DataFrame({"model": ["a"]})).empty
        blank = pd.DataFrame({"model": ["a"], "judge_verdicts": [""]})
        assert summarize_judge_agreement(blank).empty

    def test_malformed_verdict_json_is_skipped(self) -> None:
        df = pd.DataFrame({"model": ["a"], "judge_verdicts": ["not json"]})
        assert summarize_judge_agreement(df).empty
