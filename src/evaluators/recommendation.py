"""Deterministic Model Compass recommendation calculations.

The recommendation report is deliberately separate from the one-row-per-model
benchmark summary. It preserves every model for every generic use case and
records why a model is recommended, eligible, below threshold, or lacks enough
evidence for a decision.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from src.core.methodology import METHODOLOGY_VERSION
from src.evaluators.quality_metrics import bootstrap_quality_interval
from src.evaluators.security_scanner import RSI_CONFIRMED_LEAK_CEILING

DEFAULT_USE_CASE_CATALOG_PATH: Final[Path] = Path("data/catalog/model_compass_use_cases.json")
_QUALITY_MINIMUM: Final[float] = 1.0
_QUALITY_MAXIMUM: Final[float] = 5.0
_REQUIRED_COMPONENTS: Final[tuple[str, ...]] = ("quality", "security", "cost", "performance")
_FORMAT_DIMENSION: Final[str] = "output_format_compliance"
_FORMAT_PASS_SCORE: Final[float] = 4.0


def _content_rows(quality_df: pd.DataFrame) -> pd.DataFrame:
    """Drop the derived output-format rows: a use case's quality score measures content only.

    Format compliance stays a separate signal (``format_compliance_rate``), so
    a correct answer that ignores a bare-answer instruction never lowers the
    use-case quality score that decides eligibility.
    """
    if "quality_dimension" not in quality_df.columns:
        return quality_df
    return quality_df.loc[quality_df["quality_dimension"].ne(_FORMAT_DIMENSION)]


def _format_compliance_by_use_case(quality_df: pd.DataFrame, use_case: UseCaseDefinition) -> pd.Series:
    """Share of a use case's strict-format responses that respect the format, per model."""
    if quality_df.empty or not {"model", "prompt_id", "score", "quality_dimension"}.issubset(quality_df.columns):
        return pd.Series(dtype="float64")
    rows = quality_df.loc[
        quality_df["quality_dimension"].eq(_FORMAT_DIMENSION)
        & pd.to_numeric(quality_df["prompt_id"], errors="coerce").isin(use_case.prompt_ids)
    ]
    if rows.empty:
        return pd.Series(dtype="float64")
    return pd.to_numeric(rows["score"], errors="coerce").ge(_FORMAT_PASS_SCORE).groupby(rows["model"]).mean()


class RecommendationWeights(BaseModel):
    """Configurable weights used for the recommendation score."""

    model_config = ConfigDict(extra="forbid")

    quality: float = Field(gt=0.0)
    security: float = Field(gt=0.0)
    cost: float = Field(gt=0.0)
    performance: float = Field(gt=0.0)

    @model_validator(mode="after")
    def validate_sum(self) -> RecommendationWeights:
        """Require a normalized weight vector."""
        if not math.isclose(sum(self.model_dump().values()), 1.0, abs_tol=1e-9):
            raise ValueError("Recommendation weights must sum to 1.0.")
        return self


class UseCaseDefinition(BaseModel):
    """Versioned generic use-case definition."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    prompt_ids: list[int] = Field(min_length=1)
    minimum_quality_score: float = Field(ge=_QUALITY_MINIMUM, le=_QUALITY_MAXIMUM)


class LogScaleBounds(BaseModel):
    """Fixed lower-is-better score anchors for a logarithmic component."""

    model_config = ConfigDict(extra="forbid")

    best: float = Field(gt=0.0)
    worst: float = Field(gt=0.0)

    @model_validator(mode="after")
    def validate_order(self) -> LogScaleBounds:
        """Require a positive, increasing range for the log transform."""
        if self.best >= self.worst:
            raise ValueError("Log scale bounds require best < worst.")
        return self


class RecommendationScales(BaseModel):
    """Fixed normalization anchors stored with the use-case catalog."""

    model_config = ConfigDict(extra="forbid")

    # Artifacts before methodology 0.6 name the cost anchor by listed price per 1M tokens.
    cost_usd_per_1k_requests: LogScaleBounds = Field(
        validation_alias=AliasChoices("cost_usd_per_1k_requests", "cost_usd_per_1m_tokens")
    )
    actual_latency_p95_ms: LogScaleBounds


class UseCaseCatalog(BaseModel):
    """Validated Model Compass use-case catalog."""

    model_config = ConfigDict(extra="forbid")

    catalog_version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    weights: RecommendationWeights
    weight_profiles: dict[str, RecommendationWeights] = Field(default_factory=dict)
    """Named alternatives to ``weights`` (e.g. ``quality_first``); the report shows each one's leader."""
    score_scales: RecommendationScales
    use_cases: list[UseCaseDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_use_cases(self) -> UseCaseCatalog:
        """Reject duplicate IDs and overlapping prompt ownership."""
        ids = [use_case.id for use_case in self.use_cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Use-case IDs must be unique.")
        prompt_owners: dict[int, str] = {}
        for use_case in self.use_cases:
            for prompt_id in use_case.prompt_ids:
                previous_owner = prompt_owners.get(prompt_id)
                if previous_owner is not None:
                    raise ValueError(f"Prompt ID {prompt_id} belongs to both '{previous_owner}' and '{use_case.id}'.")
                prompt_owners[prompt_id] = use_case.id
        return self


def load_use_case_catalog(path: Path = DEFAULT_USE_CASE_CATALOG_PATH) -> UseCaseCatalog:
    """Load and validate a Model Compass use-case catalog."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return UseCaseCatalog.model_validate(payload)
    except FileNotFoundError as exc:
        raise ValueError(f"Use-case catalog not found: '{path}'.") from exc
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid use-case catalog '{path}': {exc}") from exc


def parse_recommendation_weights(raw: str | None) -> RecommendationWeights | None:
    """Parse an optional JSON weight override from ``MODEL_COMPASS_WEIGHTS``."""
    if raw is None or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
        return RecommendationWeights.model_validate(payload)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(
            "Invalid MODEL_COMPASS_WEIGHTS: provide JSON with positive quality, security, cost, "
            f"and performance weights summing to 1.0 ({exc})."
        ) from exc


def _normalize_quality_score(series: pd.Series) -> pd.Series:
    """Map the quality scale 1-5 to the common 0-100 component scale."""
    return ((pd.to_numeric(series, errors="coerce") - _QUALITY_MINIMUM) / 4.0 * 100.0).clip(0.0, 100.0)


def _normalize_lower_log_score(
    series: pd.Series,
    bounds: LogScaleBounds,
    *,
    zero_is_best: bool = False,
) -> pd.Series:
    """Map a non-negative lower-is-better metric to fixed 0-100 log anchors."""
    values = pd.to_numeric(series, errors="coerce")
    finite = values.where(values.map(math.isfinite))
    valid = finite.ge(0.0) if zero_is_best else finite.gt(0.0)
    positive = finite.where(valid & finite.gt(0.0))
    scores = pd.Series(float("nan"), index=series.index, dtype="float64")
    scores.loc[positive.notna()] = (
        100.0
        * (math.log10(bounds.worst) - np.log10(positive.loc[positive.notna()]))
        / (math.log10(bounds.worst) - math.log10(bounds.best))
    )
    scores.loc[valid & finite.le(bounds.best)] = 100.0
    scores.loc[valid & finite.ge(bounds.worst)] = 0.0
    if zero_is_best:
        scores.loc[valid & finite.eq(0.0)] = 100.0
    return scores.clip(0.0, 100.0)


def _quality_by_use_case(
    quality_df: pd.DataFrame,
    models: list[str],
    use_case: UseCaseDefinition,
) -> pd.DataFrame:
    """Calculate per-model quality and coverage for one use case."""
    columns = ["model", "quality_score", "quality_coverage_rate", "quality_prompt_count"]
    if quality_df.empty or not {"model", "prompt_id", "score"}.issubset(quality_df.columns):
        return pd.DataFrame(
            {
                "model": models,
                "quality_score": float("nan"),
                "quality_coverage_rate": 0.0,
                "quality_prompt_count": 0,
            },
            columns=columns,
        )

    work = quality_df.loc[:, ["model", "prompt_id", "score"]].copy()
    work["prompt_id"] = pd.to_numeric(work["prompt_id"], errors="coerce")
    work = work.loc[work["prompt_id"].isin(use_case.prompt_ids)]
    if work.empty:
        return pd.DataFrame(
            {
                "model": models,
                "quality_score": float("nan"),
                "quality_coverage_rate": 0.0,
                "quality_prompt_count": 0,
            },
            columns=columns,
        )

    work["score"] = pd.to_numeric(work["score"], errors="coerce")
    work = work.dropna(subset=["model", "prompt_id", "score"])
    prompt_scores = work.groupby(["model", "prompt_id"], as_index=False)["score"].mean()
    summary = prompt_scores.groupby("model", as_index=False).agg(
        quality_score=("score", "mean"),
        quality_prompt_count=("prompt_id", "nunique"),
    )
    summary["quality_coverage_rate"] = summary["quality_prompt_count"] / len(use_case.prompt_ids)
    model_frame = pd.DataFrame({"model": models})
    merged = model_frame.merge(summary, on="model", how="left")
    merged["quality_prompt_count"] = (
        pd.to_numeric(merged["quality_prompt_count"], errors="coerce").fillna(0).astype("int32")
    )
    merged["quality_coverage_rate"] = pd.to_numeric(merged["quality_coverage_rate"], errors="coerce").fillna(0.0)
    return merged[columns]


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric frame column or a same-index missing series."""
    if column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _performance_component(frame: pd.DataFrame, bounds: LogScaleBounds) -> tuple[pd.Series, str]:
    """Return the fixed-scale p95 latency component and its evidence metric."""
    latency = _numeric_column(frame, "actual_latency_p95_ms")
    if latency.notna().any():
        return _normalize_lower_log_score(latency, bounds), "actual_latency_p95_ms"
    return pd.Series(float("nan"), index=frame.index, dtype="float64"), "unavailable"


def _missing_components(row: pd.Series, components: tuple[str, ...] = _REQUIRED_COMPONENTS) -> str:
    """Render missing decision dimensions in a stable, human-readable order."""
    return ", ".join(component for component in components if pd.isna(row[f"{component}_score"]))


def implied_tradeoffs(weights: dict[str, float], scales: RecommendationScales) -> dict[str, float]:
    """Exchange rates that a weight vector implies between the components, on the catalog's fixed anchors.

    One quality point on the 1–5 scale is 25 points of the 0–100 quality
    component. Cost and latency score 100 / log10(worst / best) points per
    tenfold change, the RSI one point per point. Dividing each weighted
    swing by the weighted quality point gives the trade-off the weights
    actually encode, which is what their justification must defend.
    """
    quality_point = 25.0 * weights["quality"]
    cost_per_decade = 100.0 / math.log10(scales.cost_usd_per_1k_requests.worst / scales.cost_usd_per_1k_requests.best)
    latency_per_decade = 100.0 / math.log10(scales.actual_latency_p95_ms.worst / scales.actual_latency_p95_ms.best)
    cost_swing = cost_per_decade * weights["cost"]
    return {
        "price_factor_per_quality_point": 10 ** (quality_point / cost_swing) if cost_swing else math.inf,
        "quality_points_per_10x_price": cost_swing / quality_point,
        "quality_points_per_10x_latency": latency_per_decade * weights["performance"] / quality_point,
        "quality_points_per_10_rsi_points": 10.0 * weights["security"] / quality_point,
        "quality_points_per_confirmed_leak": (100.0 - RSI_CONFIRMED_LEAK_CEILING) * weights["security"] / quality_point,
    }


def security_evaluated(benchmark_df: pd.DataFrame) -> bool:
    """Return whether the run evaluated security, i.e. was not collected with ``SECURITY=skip``."""
    if "security_profile" not in benchmark_df.columns or benchmark_df.empty:
        return True
    return not benchmark_df["security_profile"].astype(str).eq("skip").all()


def effective_weights(weights: RecommendationWeights, *, with_security: bool = True) -> dict[str, float]:
    """Return the weights applied to a run: without security, the other three are rescaled to sum to one."""
    values = weights.model_dump()
    if with_security:
        return values
    values["security"] = 0.0
    total = sum(values.values())
    return {component: value / total for component, value in values.items()}


def _add_sensitivity(
    report: pd.DataFrame,
    weight_values: dict[str, float],
    threshold: float,
    components: tuple[str, ...] = _REQUIRED_COMPONENTS,
) -> None:
    """Annotate rank/eligibility changes across one-at-a-time ±10% scenarios.

    Perturb one weight by 10% relative to its effective value and rescale the
    other three proportionally to sum to one. Also probe the threshold at
    ±10% relative (clipped to the 1–5 scale). Baseline ranks stay untouched.
    """
    columns = [f"{name}_score" if name != "quality" else "quality_score_100" for name in components]
    component_values = report[columns].to_numpy(dtype="float64")
    weights = np.array([weight_values[name] for name in components])
    eligible = report["quality_eligible"].to_numpy(dtype=bool)
    complete = report["decision_evidence_complete"].to_numpy(dtype=bool)
    quality = report["quality_score"].to_numpy(dtype="float64")
    coverage = report["quality_coverage_rate"].to_numpy(dtype="float64")
    scenarios = []
    for index in range(len(weights)):
        for factor in (0.9, 1.1):
            changed = weights.copy()
            changed[index] *= factor
            changed /= changed.sum()
            scenarios.append((changed, threshold))
    for factor in (0.9, 1.1):
        scenarios.append((weights, float(np.clip(threshold * factor, _QUALITY_MINIMUM, _QUALITY_MAXIMUM))))

    scenario_ranks = []
    scenario_eligibility = []
    for candidate_weights, candidate_threshold in scenarios:
        candidate_eligible = (quality >= candidate_threshold) & (coverage >= 1.0)
        scores = np.round(component_values @ candidate_weights, 4)
        ranked = pd.Series(np.where(candidate_eligible & complete, scores, np.nan))
        scenario_ranks.append(ranked.rank(method="dense", ascending=False).to_numpy())
        scenario_eligibility.append(candidate_eligible)
    ranks = np.stack(scenario_ranks, axis=1)
    eligible_variants = np.stack(scenario_eligibility, axis=1)
    baseline = report["recommendation_rank"].to_numpy(dtype="float64", na_value=np.nan)
    valid = np.isfinite(ranks).any(axis=1)
    # nanmin/nanmax would warn for rows with no eligible scenario.
    low = np.where(valid, np.min(np.where(np.isnan(ranks), np.inf, ranks), axis=1), np.nan)
    high = np.where(valid, np.max(np.where(np.isnan(ranks), -np.inf, ranks), axis=1), np.nan)
    report["recommendation_sensitivity_rank_min"] = pd.array(low, dtype="Int64")
    report["recommendation_sensitivity_rank_max"] = pd.array(high, dtype="Int64")
    changed_rank = np.any(~np.isclose(ranks, baseline[:, None], equal_nan=True), axis=1)
    changed_eligibility = np.any(eligible_variants != eligible[:, None], axis=1)
    report["recommendation_fragile"] = pd.array(changed_rank | changed_eligibility, dtype="boolean")
    report.loc[~complete, "recommendation_fragile"] = pd.NA


def _judge_provider(judge_id: object) -> str:
    """Return the provider suffix of a judge ID such as ``copilot-gpt4o-openai``."""
    return str(judge_id).rsplit("-", 1)[-1].strip().lower()


def _model_provider(model: object) -> str:
    """Return the provider prefix of an OpenRouter model ID such as ``openai/gpt-6-luna``."""
    return str(model).split("/", 1)[0].strip().lower()


def exclude_affiliated_judges(quality_df: pd.DataFrame) -> pd.DataFrame:
    """Return *quality_df* with each judged score re-averaged without the model's own-provider judge.

    A judge may favour responses from its own model family even when names are
    masked. This sidecar view drops, for every judged response, the verdicts of
    judges sharing the evaluated model's provider, as long as another judge
    remains. Deterministic scores and the published scores are left untouched.
    """
    if quality_df.empty or not {"model", "score", "judge_verdicts"}.issubset(quality_df.columns):
        return quality_df
    adjusted = quality_df.copy()
    scores: list[object] = []
    for model, score, raw in zip(adjusted["model"], adjusted["score"], adjusted["judge_verdicts"], strict=True):
        try:
            verdicts = json.loads(raw) if isinstance(raw, str) and raw.strip() else []
        except json.JSONDecodeError:
            verdicts = []
        kept = [
            float(verdict["score"])
            for verdict in verdicts
            if isinstance(verdict, dict)
            and "score" in verdict
            and _judge_provider(verdict.get("judge_id")) != _model_provider(model)
        ]
        scores.append(round(sum(kept) / len(kept), 2) if kept and len(kept) < len(verdicts) else score)
    adjusted["score"] = scores
    return adjusted


def build_recommendation_report(
    benchmark_df: pd.DataFrame,
    quality_df: pd.DataFrame,
    catalog_path: Path = DEFAULT_USE_CASE_CATALOG_PATH,
    weights: RecommendationWeights | None = None,
) -> pd.DataFrame:
    """Build one recommendation row for every use-case/model pair.

    Quality eligibility is evaluated before the weighted score. A model that
    misses the use-case threshold is never marked recommended because of a low
    cost or fast response. A complete decision score requires all four default
    components; incomplete runs remain visible with an evidence status rather
    than receiving a misleading partial recommendation. Every ranked model
    that a ±10% change of one weight or of the threshold would put first is
    ``recommended`` beside the leader, its rank unchanged: a gap that small is
    not a decision.

    Each row also carries the outcome recomputed without own-provider judges
    (see :func:`exclude_affiliated_judges`); it never replaces the baseline
    score, rank or status.
    """
    report = _build_report(benchmark_df, quality_df, catalog_path, weights)
    if report.empty:
        return report
    report = _add_profile_ranks(report, benchmark_df, quality_df, catalog_path)
    unaffiliated = _build_report(
        benchmark_df, exclude_affiliated_judges(quality_df), catalog_path, weights, intervals=False
    )
    alternative = unaffiliated[
        ["use_case_id", "model", "quality_score", "recommendation_rank", "recommendation_status"]
    ].rename(
        columns={
            "quality_score": "quality_score_without_affiliated_judge",
            "recommendation_rank": "recommendation_rank_without_affiliated_judge",
            "recommendation_status": "recommendation_status_without_affiliated_judge",
        }
    )
    report = report.merge(alternative, on=["use_case_id", "model"], how="left")
    same_rank = (
        report["recommendation_rank"]
        .astype("Float64")
        .fillna(-1)
        .eq(report["recommendation_rank_without_affiliated_judge"].astype("Float64").fillna(-1))
    )
    same_status = (
        report["recommendation_status"]
        .astype(str)
        .eq(report["recommendation_status_without_affiliated_judge"].astype(str))
    )
    report["affiliated_judge_changes_outcome"] = (~(same_rank & same_status)).astype(bool)
    return report


def _add_profile_ranks(
    report: pd.DataFrame, benchmark_df: pd.DataFrame, quality_df: pd.DataFrame, catalog_path: Path
) -> pd.DataFrame:
    """Add each named weight profile's rank, and flag use cases whose leader depends on the profile.

    The profiles never change the published rank: they show the human who
    matches the tender to a profile whether the recommendation survives it.
    """
    catalog = load_use_case_catalog(catalog_path)
    profiles = catalog.weight_profiles
    leaders: dict[str, set[frozenset[str]]] = {}
    for name, profile_weights in profiles.items():
        alternative = _build_report(benchmark_df, quality_df, catalog_path, profile_weights, intervals=False)
        column = f"profile_rank_{name}"
        report = report.merge(
            alternative[["use_case_id", "model", "recommendation_rank"]].rename(
                columns={"recommendation_rank": column}
            ),
            on=["use_case_id", "model"],
            how="left",
        )
        for use_case_id, rows in alternative.groupby("use_case_id"):
            leaders.setdefault(str(use_case_id), set()).add(
                frozenset(rows.loc[rows["recommendation_rank"].eq(1), "model"].astype(str))
            )
    if profiles:
        with_security = security_evaluated(benchmark_df)
        report["weight_profiles"] = json.dumps(
            {name: effective_weights(weights, with_security=with_security) for name, weights in profiles.items()},
            sort_keys=False,
        )
        report["score_scales"] = catalog.score_scales.model_dump_json()
        baseline = {
            str(use_case_id): frozenset(rows.loc[rows["recommendation_rank"].eq(1), "model"].astype(str))
            for use_case_id, rows in report.groupby("use_case_id")
        }
        report["weight_profile_sensitive"] = report["use_case_id"].map(
            lambda use_case_id: any(seen != baseline[str(use_case_id)] for seen in leaders[str(use_case_id)])
        )
    return report


def _build_report(
    benchmark_df: pd.DataFrame,
    quality_df: pd.DataFrame,
    catalog_path: Path,
    weights: RecommendationWeights | None,
    *,
    intervals: bool = True,
) -> pd.DataFrame:
    """Compute the baseline recommendation rows for one quality frame.

    ``intervals=False`` skips the bootstrap: the sidecar recomputations (other
    weight profiles, no own-provider judge) only need ranks and statuses.
    """
    catalog = load_use_case_catalog(catalog_path)
    if weights is not None:
        catalog = catalog.model_copy(update={"weights": weights})
    if benchmark_df.empty or "model" not in benchmark_df.columns:
        return pd.DataFrame()

    model_frame = benchmark_df[["model"]].drop_duplicates().reset_index(drop=True)
    security_score = _numeric_column(benchmark_df, "rsi").groupby(benchmark_df["model"]).first()
    cost_score = _normalize_lower_log_score(
        _numeric_column(benchmark_df, "cost_usd_per_1k_requests"),
        catalog.score_scales.cost_usd_per_1k_requests,
        zero_is_best=True,
    )
    performance_score, performance_basis = _performance_component(
        benchmark_df, catalog.score_scales.actual_latency_p95_ms
    )
    metric_frame = benchmark_df[["model"]].copy()
    metric_frame["security_score"] = metric_frame["model"].map(security_score)
    metric_frame["cost_score"] = cost_score.to_numpy()
    metric_frame["cost_usd_per_1k_requests"] = _numeric_column(benchmark_df, "cost_usd_per_1k_requests").to_numpy()
    metric_frame["performance_score"] = performance_score.to_numpy()
    metric_frame = metric_frame.drop_duplicates("model")

    with_security = security_evaluated(benchmark_df)
    components = _REQUIRED_COMPONENTS if with_security else tuple(c for c in _REQUIRED_COMPONENTS if c != "security")
    weight_values = effective_weights(catalog.weights, with_security=with_security)
    weight_json = json.dumps(weight_values, sort_keys=True)
    reports: list[pd.DataFrame] = []
    content_df = _content_rows(quality_df)
    for use_case in catalog.use_cases:
        quality_frame = _quality_by_use_case(content_df, model_frame["model"].tolist(), use_case)
        report = model_frame.merge(quality_frame, on="model", how="left")
        report["format_compliance_rate"] = report["model"].map(_format_compliance_by_use_case(quality_df, use_case))
        if intervals and {"model", "prompt_id", "score"}.issubset(content_df.columns):
            case_rows = content_df.loc[
                pd.to_numeric(content_df["prompt_id"], errors="coerce").isin(use_case.prompt_ids)
            ]
            bounds = [
                (model, *bootstrap_quality_interval(group, seed_key=f"{use_case.id}:{model}", macro_dimensions=False))
                for model, group in case_rows.groupby("model", sort=True)
            ]
            interval_frame = pd.DataFrame(
                bounds, columns=["model", "quality_score_ci95_low", "quality_score_ci95_high"]
            )
            report = report.merge(interval_frame, on="model", how="left")
        else:
            report["quality_score_ci95_low"] = float("nan")
            report["quality_score_ci95_high"] = float("nan")
        report = report.merge(metric_frame, on="model", how="left")
        report["use_case_id"] = use_case.id
        report["use_case_name"] = use_case.name
        report["use_case_description"] = use_case.description
        report["catalog_version"] = catalog.catalog_version
        report["methodology_version"] = METHODOLOGY_VERSION
        report["prompt_ids"] = json.dumps(use_case.prompt_ids)
        report["quality_threshold"] = use_case.minimum_quality_score
        report["quality_score_100"] = _normalize_quality_score(report["quality_score"])
        report["quality_eligible"] = (
            report["quality_score"].ge(use_case.minimum_quality_score) & report["quality_coverage_rate"].ge(1.0)
        ).fillna(False)
        report.loc[report["quality_coverage_rate"].lt(1.0), ["quality_score_ci95_low", "quality_score_ci95_high"]] = (
            float("nan")
        )

        # The eligibility threshold stays on the 1–5 quality scale, but all
        # four components of the weighted decision score must use 0–100.
        component_columns = {
            component: "quality_score_100" if component == "quality" else f"{component}_score"
            for component in components
        }
        available = report[list(component_columns.values())].notna()
        available_weight = sum(
            available[component_columns[component]].astype(float) * weight_values[component] for component in components
        )
        weighted_total = sum(
            pd.to_numeric(report[component_columns[component]], errors="coerce").fillna(0.0) * weight_values[component]
            for component in components
        )
        report["recommendation_score_coverage"] = available_weight.round(4)
        report["recommendation_score"] = (weighted_total / available_weight.replace(0.0, float("nan"))).round(4)
        report["recommendation_weights"] = weight_json
        report["performance_basis"] = performance_basis
        report["decision_evidence_complete"] = available.all(axis=1)
        report["evidence_missing"] = report.apply(_missing_components, axis=1, components=components)
        report["security_evaluated"] = with_security

        ranked_scores = report["recommendation_score"].where(
            report["quality_eligible"] & report["decision_evidence_complete"]
        )
        report["recommendation_rank"] = ranked_scores.rank(method="dense", ascending=False, na_option="keep")
        report["recommendation_rank"] = report["recommendation_rank"].round().astype("Int64")
        status = pd.Series("insufficient_quality_evidence", index=report.index, dtype="string")
        quality_complete = report["quality_coverage_rate"].ge(1.0) & report["quality_score"].notna()
        status.loc[quality_complete & report["quality_score"].lt(use_case.minimum_quality_score)] = (
            "below_quality_threshold"
        )
        status.loc[report["quality_eligible"] & ~report["decision_evidence_complete"]] = (
            "insufficient_decision_evidence"
        )
        status.loc[report["recommendation_rank"].notna() & report["recommendation_rank"].gt(1)] = "eligible"
        status.loc[report["recommendation_rank"].eq(1)] = "recommended"
        report["recommendation_status"] = status
        _add_sensitivity(report, weight_values, use_case.minimum_quality_score, components)
        # A ranked model that leads under one ±10% scenario is too close to the leader to call: co-recommended.
        can_lead = report["recommendation_rank"].notna() & report["recommendation_sensitivity_rank_min"].eq(1)
        report.loc[can_lead.fillna(False).astype(bool), "recommendation_status"] = "recommended"
        leaders = report.loc[report["recommendation_rank"].eq(1)]
        available_ci = report["quality_score_ci95_low"].notna() & report["quality_score_ci95_high"].notna()
        report["quality_ci95_overlaps_leader"] = pd.array([pd.NA] * len(report), dtype="boolean")
        valid_leaders = leaders.dropna(subset=["quality_score_ci95_low", "quality_score_ci95_high"])
        if not valid_leaders.empty:
            overlap = (
                (
                    report["quality_score_ci95_low"].to_numpy(dtype="float64")[:, None]
                    <= valid_leaders["quality_score_ci95_high"].to_numpy(dtype="float64")
                )
                & (
                    report["quality_score_ci95_high"].to_numpy(dtype="float64")[:, None]
                    >= valid_leaders["quality_score_ci95_low"].to_numpy(dtype="float64")
                )
            ).any(axis=1)
            report.loc[available_ci & report["quality_eligible"], "quality_ci95_overlaps_leader"] = overlap[
                (available_ci & report["quality_eligible"]).to_numpy()
            ]
        reports.append(report)

    columns = [
        "use_case_id",
        "use_case_name",
        "use_case_description",
        "catalog_version",
        "methodology_version",
        "prompt_ids",
        "model",
        "quality_score",
        "quality_score_ci95_low",
        "quality_score_ci95_high",
        "quality_ci95_overlaps_leader",
        "quality_score_100",
        "quality_coverage_rate",
        "quality_prompt_count",
        "quality_threshold",
        "quality_eligible",
        "format_compliance_rate",
        "security_score",
        "cost_score",
        "cost_usd_per_1k_requests",
        "performance_score",
        "performance_basis",
        "recommendation_score",
        "recommendation_score_coverage",
        "recommendation_weights",
        "security_evaluated",
        "decision_evidence_complete",
        "evidence_missing",
        "recommendation_rank",
        "recommendation_status",
        "recommendation_sensitivity_rank_min",
        "recommendation_sensitivity_rank_max",
        "recommendation_fragile",
    ]
    records = [record for report in reports for record in report[columns].to_dict(orient="records")]
    return pd.DataFrame.from_records(records, columns=columns)
