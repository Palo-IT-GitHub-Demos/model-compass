"""Persist benchmark, recommendation and blind-judging artifacts."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.evaluators.quality_judge import CollectResult
from src.evaluators.recommendation import RecommendationWeights, load_use_case_catalog

logger = logging.getLogger("src.main")


def recommendation_stem(benchmark_stem: Path) -> Path:
    """Return the sibling artifact stem for a benchmark's recommendations."""
    return benchmark_stem.parent / "recommendations" / f"{benchmark_stem.name}_recommendations"


def write_recommendation_artifact(recommendations: pd.DataFrame, benchmark_stem: Path) -> Path:
    """Write the one-row-per-use-case/model recommendation artifact."""
    stem = recommendation_stem(benchmark_stem)
    stem.parent.mkdir(exist_ok=True)
    recommendations.to_csv(f"{stem}.csv", index=False)
    recommendations.to_json(f"{stem}.json", orient="records", indent=2)
    return stem


def export_results(
    df: pd.DataFrame,
    results_dir: Path,
    timestamp_format: str,
    actual_call_costs: pd.DataFrame | None = None,
    quality_details: pd.DataFrame | None = None,
    quality_diagnostics: pd.DataFrame | None = None,
    recommendations: pd.DataFrame | None = None,
    quality_analysis: dict[str, pd.DataFrame] | None = None,
    *,
    log: logging.Logger = logger,
) -> Path:
    """Export summary results and available audit artifacts."""
    results_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime(timestamp_format)
    stem = results_dir / f"benchmark_{timestamp}"
    df.to_csv(f"{stem}.csv", index=False)
    df.to_json(f"{stem}.json", orient="records", indent=2)
    log.info("Results exported to '%s.{csv,json}'", stem)
    if actual_call_costs is not None and not actual_call_costs.empty:
        call_costs_dir = results_dir / "call_costs"
        call_costs_dir.mkdir(exist_ok=True)
        call_costs_stem = call_costs_dir / f"benchmark_{timestamp}_call_costs"
        actual_call_costs.to_csv(f"{call_costs_stem}.csv", index=False)
        actual_call_costs.to_json(f"{call_costs_stem}.json", orient="records", indent=2)
        log.info("Actual call-cost ledger exported to '%s.{csv,json}'", call_costs_stem)
    if quality_details is not None and not quality_details.empty:
        details_dir = results_dir / "quality_details"
        details_dir.mkdir(exist_ok=True)
        details_stem = details_dir / f"benchmark_{timestamp}_quality_details"
        quality_details.to_csv(f"{details_stem}.csv", index=False)
        quality_details.to_json(f"{details_stem}.json", orient="records", indent=2)
        log.info("Quality prompt/response detail exported to '%s.{csv,json}'", details_stem)
    if quality_diagnostics is not None and not quality_diagnostics.empty:
        diagnostics_dir = results_dir / "quality_diagnostics"
        diagnostics_dir.mkdir(exist_ok=True)
        diagnostics_stem = diagnostics_dir / f"benchmark_{timestamp}_quality_diagnostics"
        quality_diagnostics.to_csv(f"{diagnostics_stem}.csv", index=False)
        quality_diagnostics.to_json(f"{diagnostics_stem}.json", orient="records", indent=2)
        log.info("Quality collection diagnostics exported to '%s.{csv,json}'", diagnostics_stem)
    for name, analysis_df in (quality_analysis or {}).items():
        if analysis_df.empty:
            continue
        analysis_dir = results_dir / "quality_analysis"
        analysis_dir.mkdir(exist_ok=True)
        analysis_stem = analysis_dir / f"benchmark_{timestamp}_{name}"
        analysis_df.to_csv(f"{analysis_stem}.csv", index=False)
        analysis_df.to_json(f"{analysis_stem}.json", orient="records", indent=2)
        log.info("Quality suite analysis exported to '%s.{csv,json}'", analysis_stem)
    if recommendations is not None and not recommendations.empty:
        recommendation_stem = write_recommendation_artifact(recommendations, stem)
        log.info("Model Compass recommendations exported to '%s.{csv,json}'", recommendation_stem)
    return stem


def save_pending(
    models: list[str],
    pricing_df: pd.DataFrame,
    security_df: pd.DataFrame,
    collect_result: CollectResult,
    actual_call_costs: pd.DataFrame,
    intermediate_dir: Path,
    catalog_path: Path,
    timestamp_format: str,
    max_intermediate_file_bytes: int,
    recommendation_weights: RecommendationWeights | None = None,
    *,
    log: logging.Logger = logger,
) -> Path:
    """Persist the collect payload and the blind copy sent to judges."""
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(timestamp_format)
    path = intermediate_dir / f"pending_{timestamp}.json"
    payload = {
        "timestamp": timestamp,
        "use_case_catalog_version": load_use_case_catalog(catalog_path).catalog_version,
        "model_compass_weights": recommendation_weights.model_dump() if recommendation_weights else None,
        "models": models,
        "pricing": pricing_df.to_dict(orient="records") if not pricing_df.empty else [],
        "security": security_df.to_dict(orient="records") if not security_df.empty else [],
        "actual_call_costs": actual_call_costs.to_dict(orient="records") if not actual_call_costs.empty else [],
        "deterministic_scores": collect_result.deterministic_rows,
        "quality_collection_errors": collect_result.collection_errors,
        "quality_metadata": {
            "prompt_count": collect_result.prompt_count,
            "dimension_count": collect_result.dimension_count,
            "repetitions": collect_result.repetitions,
            "suite_id": collect_result.quality_suite_id,
            "code_execution": collect_result.code_execution,
        },
        "pending_judgments": collect_result.pending_judgments,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    size_bytes = path.stat().st_size
    if size_bytes > max_intermediate_file_bytes:
        log.warning(
            "Intermediate file '%s' is %.1f MB (> %.0f MB) — consider reducing "
            "TARGET_MODELS, quality prompt count, or QUALITY_REPETITIONS to avoid disk pressure.",
            path,
            size_bytes / (1024 * 1024),
            max_intermediate_file_bytes / (1024 * 1024),
        )
    log.info("Intermediate file saved → '%s'", path)
    judging_path = intermediate_dir / f"judging_{timestamp}.json"
    judging_payload = {
        "timestamp": timestamp,
        "pending_judgments": [
            {
                "prompt_id": pj["prompt_id"],
                "prompt": pj["prompt"],
                "attempt": pj.get("attempt", 0),
                "quality_dimension": pj.get("quality_dimension", "legacy"),
                "weight": pj.get("weight", 1.0),
                "judge_criteria": pj.get("judge_criteria", []),
                "reference_answer": pj.get("reference_answer"),
                "rubric_version": pj.get("rubric_version"),
                "rubric_anchors": pj.get("rubric_anchors"),
                "prompt_preview": pj.get("prompt_preview", ""),
                "category": pj.get("category"),
                "responses": pj.get("responses_for_judging", pj["responses"]),
            }
            for pj in collect_result.pending_judgments
        ],
    }
    judging_path.write_text(json.dumps(judging_payload, indent=2, ensure_ascii=False))
    log.info("Blind judging file saved → '%s'", judging_path)
    return path
