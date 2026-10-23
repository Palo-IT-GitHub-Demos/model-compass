"""Tests for deterministic Model Compass recommendation calculations."""

from __future__ import annotations

import pandas as pd
import pytest

from src.core.methodology import METHODOLOGY_VERSION
from src.evaluators.recommendation import (
    DEFAULT_USE_CASE_CATALOG_PATH,
    LogScaleBounds,
    _normalize_lower_log_score,
    build_recommendation_report,
    load_use_case_catalog,
    parse_recommendation_weights,
)


def _benchmark(*, complete: bool = True) -> pd.DataFrame:
    rows = [
        {
            "model": "model-a",
            "tco_usd": 1.0,
            "cost_usd_per_1m_tokens": 0.1,
            "rsi": 90.0,
            "actual_latency_p95_ms": 100.0,
        },
        {
            "model": "model-b",
            "tco_usd": 2.0,
            "cost_usd_per_1m_tokens": 1.0,
            "rsi": 80.0,
            "actual_latency_p95_ms": 200.0,
        },
        {
            "model": "model-c",
            "tco_usd": 3.0,
            "cost_usd_per_1m_tokens": 10.0,
            "rsi": 70.0,
            "actual_latency_p95_ms": 300.0,
        },
    ]
    if not complete:
        rows[0].pop("rsi")
    return pd.DataFrame(rows)


def _quality() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    scores = {"model-a": 5.0, "model-b": 4.0, "model-c": 3.0}
    for model, score in scores.items():
        for prompt_id in (0, 1, 2):
            rows.append(
                {
                    "model": model,
                    "prompt_id": prompt_id,
                    "score": score,
                }
            )
    return pd.DataFrame(rows)


class TestModelCompassCatalog:
    def test_catalog_is_versioned_and_has_normalized_weights(self) -> None:
        catalog = load_use_case_catalog(DEFAULT_USE_CASE_CATALOG_PATH)

        assert catalog.catalog_version == "model-compass-use-cases-v1.1"
        assert len(catalog.use_cases) == 6
        assert sum(catalog.weights.model_dump().values()) == pytest.approx(1.0)
        assert catalog.score_scales.cost_usd_per_1m_tokens.best == pytest.approx(0.1)
        assert catalog.score_scales.cost_usd_per_1m_tokens.worst == pytest.approx(100.0)
        assert catalog.score_scales.actual_latency_p95_ms.best == pytest.approx(1000.0)
        assert catalog.score_scales.actual_latency_p95_ms.worst == pytest.approx(30000.0)

    def test_log_scale_bounds_require_positive_increasing_anchors(self) -> None:
        with pytest.raises(ValueError, match="best < worst"):
            LogScaleBounds(best=1.0, worst=1.0)

        with pytest.raises(ValueError):
            LogScaleBounds(best=0.0, worst=1.0)

    def test_cost_log_scale_uses_fixed_anchors_and_preserves_missing_values(self) -> None:
        scores = _normalize_lower_log_score(
            pd.Series([0.0, 0.1, 1.0, 10.0, 100.0, 200.0, -1.0, float("nan")]),
            LogScaleBounds(best=0.1, worst=100.0),
            zero_is_best=True,
        )

        assert scores.iloc[:6].tolist() == pytest.approx([100.0, 100.0, 200.0 / 3.0, 100.0 / 3.0, 0.0, 0.0])
        assert pd.isna(scores.iloc[6])
        assert pd.isna(scores.iloc[7])

    def test_latency_log_scale_uses_fixed_anchors_and_rejects_zero(self) -> None:
        scores = _normalize_lower_log_score(
            pd.Series([1000.0, 30000.0, 60000.0, 0.0]),
            LogScaleBounds(best=1000.0, worst=30000.0),
        )

        assert scores.iloc[:3].tolist() == [100.0, 0.0, 0.0]
        assert pd.isna(scores.iloc[3])

    def test_accepts_a_valid_weight_override(self) -> None:
        weights = parse_recommendation_weights('{"quality":0.6,"security":0.2,"cost":0.15,"performance":0.05}')

        assert weights is not None
        assert weights.quality == pytest.approx(0.6)

    def test_rejects_weights_that_do_not_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="MODEL_COMPASS_WEIGHTS"):
            parse_recommendation_weights('{"quality":1,"security":1,"cost":1,"performance":1}')


class TestModelCompassRecommendations:
    def test_every_row_records_the_methodology_version(self) -> None:
        report = build_recommendation_report(_benchmark(), _quality())

        assert set(report["methodology_version"]) == {METHODOLOGY_VERSION}

    def test_sensitivity_flags_weight_rank_reversal_without_changing_baseline(self) -> None:
        benchmark = _benchmark().iloc[:2].copy()
        benchmark["tco_usd"] = 1.0
        benchmark["cost_usd_per_1m_tokens"] = 0.1
        benchmark["actual_latency_p95_ms"] = 100.0
        benchmark["rsi"] = [70.8, 90.0]
        quality = _quality().loc[lambda frame: frame["model"] != "model-c"].copy()
        quality.loc[quality["model"] == "model-a", "score"] = 4.9
        quality.loc[quality["model"] == "model-b", "score"] = 4.5

        report = build_recommendation_report(benchmark, quality)
        structured = report.loc[report["use_case_id"] == "structured_extraction"].set_index("model")

        assert structured.loc["model-a", "recommendation_rank"] == 1
        assert structured.loc["model-b", "recommendation_rank"] == 2
        assert structured.loc["model-a", "recommendation_fragile"]
        assert structured.loc["model-a", "recommendation_sensitivity_rank_max"] == 2
        assert structured.loc["model-b", "recommendation_sensitivity_rank_min"] == 1
        assert pd.isna(structured.loc["model-a", "quality_score_ci95_low"])
        assert pd.isna(structured.loc["model-a", "quality_ci95_overlaps_leader"])

    def test_weighted_score_uses_four_components_on_the_same_scale(self) -> None:
        benchmark = _benchmark().iloc[:2].copy()
        benchmark["tco_usd"] = 1.0
        benchmark["cost_usd_per_1m_tokens"] = 0.1
        benchmark["actual_latency_p95_ms"] = 100.0
        benchmark["rsi"] = [50.0, 90.0]
        quality = _quality().loc[lambda frame: frame["model"] != "model-c"]

        report = build_recommendation_report(benchmark, quality)
        structured = report.loc[report["use_case_id"] == "structured_extraction"].set_index("model")

        assert structured.loc["model-a", "quality_score"] == pytest.approx(5.0)
        assert structured.loc["model-a", "quality_score_100"] == pytest.approx(100.0)
        assert structured.loc["model-b", "quality_score_100"] == pytest.approx(75.0)
        assert structured.loc["model-a", "recommendation_score"] == pytest.approx(
            0.5 * 100 + 0.25 * 50 + 0.2 * 100 + 0.05 * 100
        )
        assert structured.loc["model-b", "recommendation_score"] == pytest.approx(
            0.5 * 75 + 0.25 * 90 + 0.2 * 100 + 0.05 * 100
        )
        assert structured.loc["model-a", "recommendation_rank"] == 1
        assert structured.loc["model-b", "recommendation_rank"] == 2

    def test_custom_weights_apply_to_normalized_quality(self) -> None:
        benchmark = _benchmark().iloc[:2].copy()
        benchmark["tco_usd"] = 1.0
        benchmark["cost_usd_per_1m_tokens"] = 0.1
        benchmark["actual_latency_p95_ms"] = 100.0
        benchmark["rsi"] = [50.0, 90.0]
        quality = _quality().loc[lambda frame: frame["model"] != "model-c"]
        weights = parse_recommendation_weights('{"quality":0.6,"security":0.2,"cost":0.15,"performance":0.05}')

        report = build_recommendation_report(benchmark, quality, weights=weights)
        structured = report.loc[report["use_case_id"] == "structured_extraction"].set_index("model")

        assert structured.loc["model-a", "recommendation_score"] == pytest.approx(90.0)
        assert structured.loc["model-b", "recommendation_score"] == pytest.approx(83.0)

    def test_threshold_variation_flags_newly_ineligible_model(self) -> None:
        quality = _quality()
        quality.loc[quality["model"] == "model-b", "score"] = 4.0
        report = build_recommendation_report(_benchmark(), quality)
        structured = report.loc[report["use_case_id"] == "structured_extraction"].set_index("model")

        assert structured.loc["model-b", "recommendation_status"] == "eligible"
        assert structured.loc["model-b", "recommendation_fragile"]
        assert structured.loc["model-b", "recommendation_rank"] == 2

    def test_reports_overlapping_and_disjoint_quality_intervals_without_forced_tie(self) -> None:
        benchmark = _benchmark()
        scores = {"model-a": [5, 5, 5], "model-b": [4, 5, 5], "model-c": [1, 1, 1]}
        quality = pd.DataFrame(
            {"model": model, "prompt_id": prompt, "attempt": attempt, "score": score}
            for model, attempts in scores.items()
            for prompt in (0, 1, 2)
            for attempt, score in enumerate(attempts)
        )
        report = build_recommendation_report(benchmark, quality)
        structured = report.loc[report["use_case_id"] == "structured_extraction"].set_index("model")

        assert structured.loc["model-a", "quality_score_ci95_low"] == pytest.approx(5.0)
        assert structured.loc["model-b", "quality_score_ci95_high"] == pytest.approx(5.0)
        assert structured.loc["model-b", "quality_ci95_overlaps_leader"]
        assert structured.loc["model-a", "quality_ci95_overlaps_leader"]
        assert pd.isna(structured.loc["model-c", "quality_ci95_overlaps_leader"])
        assert structured.loc["model-a", "recommendation_rank"] == 1
        assert structured.loc["model-b", "recommendation_rank"] == 2

    def test_applies_use_case_threshold_before_ranking(self) -> None:
        report = build_recommendation_report(_benchmark(), _quality())
        structured = report.loc[report["use_case_id"] == "structured_extraction"].set_index("model")

        assert structured.loc["model-a", "quality_score"] == pytest.approx(5.0)
        assert structured.loc["model-a", "recommendation_status"] == "recommended"
        assert structured.loc["model-a", "recommendation_rank"] == 1
        assert structured.loc["model-b", "recommendation_status"] == "eligible"
        assert structured.loc["model-b", "recommendation_rank"] == 2
        assert structured.loc["model-c", "recommendation_status"] == "below_quality_threshold"
        assert pd.isna(structured.loc["model-c", "recommendation_rank"])

    def test_preserves_dense_ties_without_a_tiebreak_rule(self) -> None:
        benchmark = _benchmark()
        benchmark.loc[benchmark["model"] == "model-b", ["tco_usd", "rsi", "actual_latency_p95_ms"]] = [
            1.0,
            90.0,
            100.0,
        ]
        benchmark.loc[benchmark["model"] == "model-b", "cost_usd_per_1m_tokens"] = 0.1
        quality = _quality()
        quality.loc[quality["model"] == "model-b", "score"] = 5.0

        report = build_recommendation_report(benchmark, quality)
        structured = report.loc[report["use_case_id"] == "structured_extraction"].set_index("model")

        assert structured.loc["model-a", "recommendation_rank"] == 1
        assert structured.loc["model-b", "recommendation_rank"] == 1
        assert structured.loc["model-a", "recommendation_status"] == "recommended"
        assert structured.loc["model-b", "recommendation_status"] == "recommended"

    def test_does_not_recommend_when_decision_evidence_is_incomplete(self) -> None:
        report = build_recommendation_report(_benchmark(complete=False), _quality())
        structured = report.loc[report["use_case_id"] == "structured_extraction"].set_index("model")

        assert structured.loc["model-a", "quality_eligible"]
        assert not structured.loc["model-a", "decision_evidence_complete"]
        assert structured.loc["model-a", "recommendation_status"] == "insufficient_decision_evidence"
        assert "security" in structured.loc["model-a", "evidence_missing"]
        assert pd.isna(structured.loc["model-a", "recommendation_rank"])
        assert pd.isna(structured.loc["model-a", "recommendation_fragile"])
        assert pd.isna(structured.loc["model-a", "recommendation_sensitivity_rank_min"])

    def test_fixed_cost_and_latency_scores_do_not_depend_on_model_cohort(self) -> None:
        baseline = _benchmark().iloc[:2].copy()
        baseline_quality = _quality().loc[lambda frame: frame["model"] != "model-c"]
        expanded = _benchmark().copy()
        expanded.loc[expanded["model"] == "model-c", "cost_usd_per_1m_tokens"] = 1000.0
        expanded.loc[expanded["model"] == "model-c", "actual_latency_p95_ms"] = 60000.0

        baseline_report = build_recommendation_report(baseline, baseline_quality)
        expanded_report = build_recommendation_report(expanded, _quality())
        baseline_ab = baseline_report.set_index("model").loc[["model-a", "model-b"]]
        expanded_ab = expanded_report.set_index("model").loc[["model-a", "model-b"]]

        pd.testing.assert_frame_equal(
            baseline_ab[["cost_score", "performance_score", "recommendation_score", "recommendation_rank"]],
            expanded_ab[["cost_score", "performance_score", "recommendation_score", "recommendation_rank"]],
        )

    def test_performance_requires_p95_latency_not_throughput_fallback(self) -> None:
        benchmark = _benchmark().drop(columns="actual_latency_p95_ms")
        benchmark["actual_tokens_per_second"] = [100.0, 200.0, 300.0]

        report = build_recommendation_report(benchmark, _quality())

        assert set(report["performance_basis"]) == {"unavailable"}
        assert report["performance_score"].isna().all()
        assert report["evidence_missing"].str.contains("performance").all()

    def test_emits_one_row_for_each_model_and_use_case(self) -> None:
        report = build_recommendation_report(_benchmark(), _quality())

        assert len(report) == 18
        assert report[["use_case_id", "model"]].drop_duplicates().shape == (18, 2)

    def test_records_custom_weights_in_the_report(self) -> None:
        weights = parse_recommendation_weights('{"quality":0.6,"security":0.2,"cost":0.15,"performance":0.05}')
        report = build_recommendation_report(_benchmark(), _quality(), weights=weights)

        assert report["recommendation_weights"].nunique() == 1
        assert '"quality": 0.6' in report["recommendation_weights"].iloc[0]
