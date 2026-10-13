"""Pure consolidation of the three evaluation axes into the benchmark matrix."""

from __future__ import annotations

import pandas as pd

from src.evaluators.cost_analyzer import BUILTIN_WORKLOAD_PROFILES, summarize_actual_call_costs
from src.evaluators.quality_metrics import summarize_quality_dimensions, summarize_quality_scores


def merge_results(
    models: list[str],
    pricing_df: pd.DataFrame,
    quality_df: pd.DataFrame,
    security_df: pd.DataFrame,
    workload_profile_name: str = "enterprise_qa",
    quality_prompt_count: int | None = None,
    quality_dimension_count: int | None = None,
    quality_repetitions: int = 1,
    quality_collection_errors: pd.DataFrame | None = None,
    quality_suite_id: str | None = None,
    actual_call_costs: pd.DataFrame | None = None,
    *,
    min_quality_coverage_for_cer: float = 0.8,
) -> pd.DataFrame:
    """Merge quality, security and pricing outputs without changing their metrics."""
    base = pd.DataFrame({"model": models})

    if not quality_df.empty and "score" in quality_df.columns:
        quality_summary = summarize_quality_scores(quality_df, expected_prompt_count=quality_prompt_count)
        base = base.merge(quality_summary, on="model", how="left")
        dimension_summary = summarize_quality_dimensions(quality_df)
        if not dimension_summary.empty:
            dimension_wide = dimension_summary.pivot(
                index="model", columns="quality_dimension", values="dimension_score"
            )
            dimension_wide.columns = [f"quality_dim_{column}" for column in dimension_wide.columns]
            base = base.merge(dimension_wide.reset_index(), on="model", how="left")

    if quality_collection_errors is not None and not quality_collection_errors.empty:
        error_summary = (
            quality_collection_errors.groupby("model", as_index=False)
            .size()
            .rename(columns={"size": "quality_collection_error_count"})
        )
        base = base.merge(error_summary, on="model", how="left")

    base["quality_collection_error_count"] = base.get("quality_collection_error_count", 0)
    base["quality_collection_error_count"] = base["quality_collection_error_count"].fillna(0).astype("int32")
    if quality_prompt_count is not None and quality_prompt_count > 0:
        expected_attempts = quality_prompt_count * quality_repetitions
        base["quality_collection_success_rate"] = (
            1.0 - base["quality_collection_error_count"] / expected_attempts
        ).clip(lower=0.0, upper=1.0)

    if quality_dimension_count is not None and quality_dimension_count > 0:
        observed_dimension_count = (
            base["quality_dimension_count"]
            if "quality_dimension_count" in base.columns
            else pd.Series(0.0, index=base.index)
        )
        base["quality_dimension_coverage_rate"] = (observed_dimension_count / quality_dimension_count).clip(
            lower=0.0, upper=1.0
        )

    if quality_suite_id:
        base["quality_suite_id"] = quality_suite_id

    if actual_call_costs is not None and not actual_call_costs.empty:
        base = base.merge(summarize_actual_call_costs(actual_call_costs), on="model", how="left")

    if not security_df.empty:
        wanted = [
            "model",
            "leak_count",
            "is_vulnerable",
            "zero_data_retention",
            "rsi",
            "rsi_scored_category_count",
            "rsi_scored_probe_count",
            "rsi_scored_categories",
            "rsi_leak_capped",
            "probe_count",
            "probe_error_count",
            "probe_error_rate",
            "probe_details",
        ]
        sec_cols = [column for column in wanted if column in security_df.columns]
        base = base.merge(security_df[sec_cols], on="model", how="left")

    if not pricing_df.empty and "model_id" in pricing_df.columns:
        target_pricing = pricing_df[pricing_df["model_id"].isin(models)][
            ["model_id", "prompt_price_per_token", "completion_price_per_token", "context_length"]
        ].rename(columns={"model_id": "model"})
        base = base.merge(target_pricing, on="model", how="left")

    profile = BUILTIN_WORKLOAD_PROFILES.get(workload_profile_name)
    if profile is not None and not pricing_df.empty and "model_id" in pricing_df.columns:
        input_price = pd.to_numeric(base["prompt_price_per_token"], errors="coerce")
        completion_price = pd.to_numeric(base["completion_price_per_token"], errors="coerce")
        has_pricing = input_price.notna() & completion_price.notna()
        base["tco_usd"] = (
            input_price * profile.monthly_prompt_tokens + completion_price * profile.monthly_completion_tokens
        ).where(has_pricing, float("inf"))

        quality_col = "avg_quality_score"
        if quality_col in base.columns:
            coverage = (
                pd.to_numeric(base["quality_coverage_rate"], errors="coerce").fillna(1.0)
                if "quality_coverage_rate" in base.columns
                else pd.Series(1.0, index=base.index)
            )
            dimension_coverage = (
                pd.to_numeric(base["quality_dimension_coverage_rate"], errors="coerce").fillna(1.0)
                if "quality_dimension_coverage_rate" in base.columns
                else pd.Series(1.0, index=base.index)
            )
            base["quality_cer_eligible"] = (
                base[quality_col].notna() & (coverage >= min_quality_coverage_for_cer) & (dimension_coverage >= 1.0)
            )
            raw_cer = (
                (base[quality_col].where(base["quality_cer_eligible"], 0.0).fillna(0.0) / base["tco_usd"])
                .replace([float("inf"), -float("inf")], 0.0)
                .fillna(0.0)
            )
            max_cer = raw_cer.max()
            base["cer"] = (raw_cer / max_cer).round(4) if max_cer > 0 else raw_cer

        base["workload_profile"] = workload_profile_name

    return base
