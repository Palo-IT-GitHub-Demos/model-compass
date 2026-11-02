"""Data-prep helpers for the static HTML report.

The HTML export (scripts/export_dashboard_html.py) imports from here, so every
derived column (cost/1M tokens, security status, TCO, CER, quality tier...) is
computed by pure, unit-tested functions rather than inline in the page code.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd

from src.core.methodology import METHODOLOGY_VERSION
from src.evaluators.cost_analyzer import (
    BUILTIN_WORKLOAD_PROFILES,
    WorkloadProfile,
    effective_cost_per_1k_requests,
)
from src.evaluators.quality_diagnostics import KEY_DISPUTED_STATUS, analyze_items

DEFAULT_WORKLOAD_PROFILE = "enterprise_qa"
"""Profile used to blend input/output prices when a run did not record one."""

STANDARD_SECURITY_PROFILE = "full"
STANDARD_QUALITY_REPETITIONS = 3


def numeric_series(df: pd.DataFrame, column: str, default: float = float("nan")) -> pd.Series:
    """Return a numeric column or a same-index fallback series."""
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def short_name(model_id: object) -> str:
    """Return the trailing slug of an OpenRouter model id, e.g. 'gpt-4o-mini'."""
    return str(model_id).split("/")[-1]


def best_models(frame: pd.DataFrame, column: str, ascending: bool = False) -> tuple[list[str], float | None]:
    """Return every model sharing the best value of *column*, and that value.

    Ties are returned together on purpose: picking the first row would be an
    arbitrary tie-breaker that presents one model as better than its equals.
    """
    if column not in frame.columns or "model" not in frame.columns or frame.empty:
        return [], None
    values = pd.to_numeric(frame[column], errors="coerce").replace([float("inf"), -float("inf")], float("nan"))
    if values.notna().sum() == 0:
        return [], None
    best = float(values.min() if ascending else values.max())
    winners = frame.loc[values.round(6).eq(round(best, 6)), "model"].astype(str)
    return sorted(winners.unique()), best


def leaders_label(models: list[str]) -> str:
    """Name a single leader, or state how many models are tied."""
    if not models:
        return "—"
    if len(models) == 1:
        return short_name(models[0])
    return f"{len(models)} models tied"


def safest_summary(frame: pd.DataFrame) -> tuple[str, str]:
    """Return a (headline, detail) pair describing the safest models or overall exposure."""
    models, rsi = best_models(frame, "rsi")
    if rsi is not None:
        detail = f"RSI {rsi:.0f} / 100"
        if len(models) > 1:
            detail += ": " + ", ".join(short_name(model) for model in models)
        return leaders_label(models), detail
    safe_count = int((frame["security_status"] == "Safe").sum())
    return f"{safe_count} / {len(frame)} safe", "No probe leaked the system prompt"


def quality_tier(score: float) -> str:
    """Bucket avg_quality_score into a coarse, dashboard-only readability band."""
    if pd.isna(score):
        return "—"
    if score >= 4.5:
        return "Excellent"
    if score >= 3.5:
        return "Good"
    if score >= 2.5:
        return "Fair"
    return "Poor"


# Shared across the quality-tier and security-status columns so both use one visual language.
STATUS_STYLES = {
    "Safe": "background-color: #d4edda; color: #155724",
    "Excellent": "background-color: #d4edda; color: #155724",
    "Good": "background-color: #d1ecf1; color: #0c5460",
    "Partial risk": "background-color: #fff3cd; color: #856404",
    "Fair": "background-color: #fff3cd; color: #856404",
    "Vulnerable": "background-color: #f8d7da; color: #721c24",
    "Poor": "background-color: #f8d7da; color: #721c24",
    "recommended": "background-color: #d4edda; color: #155724",
    "eligible": "background-color: #d1ecf1; color: #0c5460",
    "below_quality_threshold": "background-color: #f8d7da; color: #721c24",
    "insufficient_quality_evidence": "background-color: #fff3cd; color: #856404",
    "insufficient_decision_evidence": "background-color: #fff3cd; color: #856404",
}

RECOMMENDATION_STATUS_LABELS = {
    "recommended": "Recommended",
    "eligible": "Eligible",
    "insufficient_decision_evidence": "Missing decision evidence",
    "below_quality_threshold": "Below quality threshold",
    "insufficient_quality_evidence": "Incomplete quality evidence",
}
"""Reader-facing names of the recommendation statuses, in display order."""

STATUS_STYLES.update({label: STATUS_STYLES[status] for status, label in RECOMMENDATION_STATUS_LABELS.items()})


def tint_status(value: object) -> str:
    """Return the CSS rule tinting a status/tier cell, or '' for an unknown value."""
    return STATUS_STYLES.get(str(value), "")


def parse_probe_details(raw: object) -> list[dict[str, object]]:
    """Parse the serialized probe details produced by the scanner safely.

    The scanner emits JSON (``json.dumps``), but older/foreign data may use a
    Python ``repr`` instead — try both rather than guessing from a prefix.
    """
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed: object = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        try:
            parsed = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def parse_judge_verdicts(raw: object) -> list[dict[str, object]]:
    """Parse the per-judge score and reasoning stored in quality details."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed: object = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def format_judge_verdicts(raw: object) -> str:
    """Render each judge's score and full reasoning on its own line, or ``""`` when none."""
    return "\n".join(
        f"{verdict.get('judge_id', 'Unknown judge')} · {verdict.get('score', '—')} / 5 — "
        f"{verdict.get('reasoning', 'No reasoning provided.')}"
        for verdict in parse_judge_verdicts(raw)
    )


def security_long_frame(results_df: pd.DataFrame) -> pd.DataFrame:
    """Convert serialized probe rows into heatmap-friendly long format."""
    if "probe_details" not in results_df.columns:
        return pd.DataFrame()

    details_df = results_df[["model", "probe_details"]].copy()
    details_df["details"] = details_df["probe_details"].map(parse_probe_details)
    details_df = details_df.explode("details").dropna(subset=["details"]).reset_index(drop=True)
    if details_df.empty:
        return pd.DataFrame()

    details = pd.json_normalize(details_df["details"]).reset_index(drop=True)
    details["model"] = details_df["model"].to_numpy()
    if "category_id" not in details.columns:
        details["category_id"] = "LLM00"
    if "category_name" not in details.columns:
        details["category_name"] = "Uncategorized"
    leaked = details["leaked"] if "leaked" in details.columns else pd.Series(False, index=details.index)
    probe_error = details["probe_error"] if "probe_error" in details.columns else pd.Series(False, index=details.index)
    details["probe_error"] = probe_error.fillna(False).astype(bool)
    scored = details["scored"] if "scored" in details.columns else pd.Series(True, index=details.index)
    details["scored"] = scored.fillna(True).astype(bool)
    details["vulnerability_rate"] = leaked.astype("float32").mask(details["probe_error"])
    return details[["model", "category_id", "category_name", "vulnerability_rate", "probe_error", "scored"]]


def security_probe_details_frame(results_df: pd.DataFrame) -> pd.DataFrame:
    """Convert serialized probe rows into a full transcript: prompt + response per probe.

    Unlike :func:`security_long_frame` (heatmap-only columns), this keeps the
    probe's actual prompt text and the model's full response for a
    "Security prompts" drill-down. Scans predating these fields (or a custom
    probes file missing ``category_id``/``category_name``) default to an
    empty string / catch-all category rather than raising.
    """
    if "probe_details" not in results_df.columns:
        return pd.DataFrame()

    details_df = results_df[["model", "probe_details"]].copy()
    details_df["details"] = details_df["probe_details"].map(parse_probe_details)
    details_df = details_df.explode("details").dropna(subset=["details"]).reset_index(drop=True)
    if details_df.empty:
        return pd.DataFrame()

    details = pd.json_normalize(details_df["details"]).reset_index(drop=True)
    details["model"] = details_df["model"].to_numpy()
    defaults: dict[str, object] = {
        "probe": "",
        "category_id": "LLM00",
        "category_name": "Uncategorized",
        "prompt": "",
        "response": "",
        "preview": "",
        "leaked": False,
        "probe_error": False,
        "outcome": "legacy_unverified",
        "scored": True,
        "not_scored_reason": "",
    }
    for column, default in defaults.items():
        if column not in details.columns:
            details[column] = default
        else:
            details[column] = details[column].fillna(default)
    return details[["model", *defaults]]


_MEASURED_OUTCOMES = frozenset({"safe_refusal", "confirmed_leak"})
"""Probe outcomes the canary oracle can grade; the RSI ignores every other outcome."""


def security_probe_coverage(probe_details_df: pd.DataFrame) -> pd.DataFrame:
    """Per model, how many scored probes produced an answer the RSI could grade.

    A probe that returned nothing (``inconclusive``, typically a reasoning
    model that spent its whole token budget before answering) or failed
    (``execution_error``) is left out of the RSI rather than counted as safe,
    so a model's RSI may rest on fewer probes than another's. This makes that
    visible instead of leaving a robust-looking score unqualified.
    """
    columns = ["model", "scored_probes", "measured_scored_probes", "unmeasured_probes"]
    if probe_details_df.empty or not {"model", "scored", "outcome", "probe"}.issubset(probe_details_df.columns):
        return pd.DataFrame(columns=columns)
    scored = probe_details_df.loc[probe_details_df["scored"].astype(bool)]
    if scored.empty:
        return pd.DataFrame(columns=columns)
    measured = scored["outcome"].isin(_MEASURED_OUTCOMES)
    return (
        scored.assign(measured=measured, unmeasured=scored["probe"].where(~measured))
        .groupby("model", as_index=False, sort=False)
        .agg(
            scored_probes=("probe", "size"),
            measured_scored_probes=("measured", "sum"),
            unmeasured_probes=("unmeasured", lambda names: ", ".join(sorted(names.dropna().astype(str)))),
        )[columns]
    )


def security_observations_frame(probe_details_df: pd.DataFrame) -> pd.DataFrame:
    """Summarise the probes excluded from the RSI, one row per OWASP category.

    *probe_details_df* is the output of :func:`security_probe_details_frame`.
    Each row keeps the reason the canary oracle cannot score the category and
    the number of confirmed leaks, which still cap the RSI when they occur.
    """
    if probe_details_df.empty or "scored" not in probe_details_df.columns:
        return pd.DataFrame()
    observations = probe_details_df.loc[~probe_details_df["scored"].astype(bool)]
    if observations.empty:
        return pd.DataFrame()
    return (
        observations.assign(leaked=observations["leaked"].astype(bool))
        .groupby(["category_id", "category_name"], as_index=False)
        .agg(
            reason=("not_scored_reason", "first"),
            probes=("probe", "nunique"),
            confirmed_leaks=("leaked", "sum"),
        )
        .sort_values("category_id")
        .reset_index(drop=True)
    )


def quality_dimension_table(df: pd.DataFrame) -> pd.DataFrame:
    """Return a model x quality-dimension score table (wide), for exact numbers.

    Complements :func:`dashboard.quality_viz.build_quality_dimension_heatmap`
    (visual) with a sortable table of the same ``dimension_score`` values.
    """
    long_df = quality_dimension_long_frame(df)
    if long_df.empty:
        return pd.DataFrame()
    return long_df.pivot(index="model", columns="quality_dimension", values="dimension_score").reset_index()


def security_category_table(security_long_df: pd.DataFrame) -> pd.DataFrame:
    """Return a model x OWASP-category vulnerability-rate table (wide).

    Complements :func:`dashboard.security_viz.build_owasp_heatmap` (visual)
    with a sortable table of the same ``vulnerability_rate`` values, over the
    probes counted in the RSI only (see :func:`security_observations_frame`).
    """
    required = {"model", "category_id", "vulnerability_rate"}
    if security_long_df.empty or not required.issubset(security_long_df.columns):
        return pd.DataFrame()
    work_df = security_long_df
    if "scored" in work_df.columns:
        work_df = work_df.loc[work_df["scored"].astype(bool)]
    if work_df.empty:
        return pd.DataFrame()
    return work_df.pivot_table(
        index="model", columns="category_id", values="vulnerability_rate", aggfunc="mean"
    ).reset_index()


def blended_cost_per_1m_tokens(df: pd.DataFrame) -> pd.Series:
    """Return the workload-blended listed USD price per million tokens for every row.

    This listed price ignores how many tokens a model really produces; the
    recommendation scores :func:`cost_per_1k_requests` instead. Older runs
    that lack ``cost_usd_per_1m_tokens`` are blended here from their input
    and output prices with the recorded workload profile.
    """
    recorded = numeric_series(df, "cost_usd_per_1m_tokens")
    profile_names = (
        df["workload_profile"].fillna(DEFAULT_WORKLOAD_PROFILE).astype(str)
        if "workload_profile" in df.columns
        else pd.Series(DEFAULT_WORKLOAD_PROFILE, index=df.index)
    )
    profiles = profile_names.map(
        lambda name: BUILTIN_WORKLOAD_PROFILES.get(name, BUILTIN_WORKLOAD_PROFILES[DEFAULT_WORKLOAD_PROFILE])
    )
    prompt_share = profiles.map(
        lambda profile: profile.avg_prompt_tokens / (profile.avg_prompt_tokens + profile.avg_completion_tokens)
    ).astype("float64")
    input_price = numeric_series(df, "prompt_price_per_token", 0.0).fillna(0.0)
    output_price = numeric_series(df, "completion_price_per_token")
    output_price = output_price.fillna(input_price)
    derived = (input_price * prompt_share + output_price * (1.0 - prompt_share)) * 1_000_000
    return recorded.where(recorded.notna(), derived)


def cost_per_1k_requests(df: pd.DataFrame, profile: WorkloadProfile) -> pd.Series:
    """USD per 1,000 requests of *profile* with each model's measured output length.

    Runs collected before the measurement fall back to the profile's assumed
    output length, i.e. to the listed price; they rank nothing anyway.
    """
    measured = numeric_series(df, "measured_completion_tokens_per_answer")
    return effective_cost_per_1k_requests(
        numeric_series(df, "prompt_price_per_token"),
        numeric_series(df, "completion_price_per_token"),
        measured.fillna(float(profile.avg_completion_tokens)),
        profile,
    )


def enrich_benchmark(df: pd.DataFrame) -> pd.DataFrame:
    """Add the derived columns every view relies on: cost/1M tokens + security_status.

    Expects *df* to already contain ``prompt_price_per_token``. Missing
    security columns default to a leak-free/no-ZDR baseline.
    """
    df = df.copy()
    df["cost_per_1m_tokens_usd"] = blended_cost_per_1m_tokens(df)
    profile_name = (
        str(df["workload_profile"].dropna().iloc[0])
        if "workload_profile" in df.columns and df["workload_profile"].notna().any()
        else DEFAULT_WORKLOAD_PROFILE
    )
    profile = BUILTIN_WORKLOAD_PROFILES.get(profile_name, BUILTIN_WORKLOAD_PROFILES[DEFAULT_WORKLOAD_PROFILE])
    recorded = numeric_series(df, "cost_usd_per_1k_requests")
    df["cost_per_1k_requests_usd"] = recorded.where(recorded.notna(), cost_per_1k_requests(df, profile))
    for column, default in (("is_vulnerable", False), ("leak_count", 0), ("zero_data_retention", False)):
        if column not in df.columns:
            df[column] = default
    vulnerable = df["is_vulnerable"].fillna(False).astype(bool)
    leak_count = pd.to_numeric(df["leak_count"], errors="coerce").fillna(0)
    df["security_status"] = (
        pd.Series("Safe", index=df.index).mask(leak_count > 0, "Partial risk").mask(vulnerable, "Vulnerable")
    )
    return df


def compute_cost_columns(df: pd.DataFrame, profile: WorkloadProfile) -> pd.DataFrame:
    """Add ``tco_usd`` and a run-normalized ``cer`` for *profile*.

    CER is re-derived against *this* profile's TCO rather than trusting any
    ``cer`` baked into the CSV at collect time, so switching profiles never
    leaves a stale value behind.
    """
    cost_df = df.copy()
    cost_df["tco_usd"] = cost_per_1k_requests(cost_df, profile) / 1_000 * profile.monthly_requests

    if "quality_cer_eligible" in cost_df.columns:
        eligible = cost_df["quality_cer_eligible"].fillna(False).astype(bool)
        eligible_quality = numeric_series(cost_df, "avg_quality_score").where(eligible, 0.0).fillna(0.0)
        raw_cer = (eligible_quality / cost_df["tco_usd"]).replace([float("inf"), -float("inf")], 0.0).fillna(0.0)
        max_cer = raw_cer.max()
        cost_df["cer"] = (raw_cer / max_cer).round(4) if max_cer > 0 else raw_cer

    return cost_df


_QUALITY_DIM_PREFIX = "quality_dim_"


def quality_dimension_long_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Melt the wide ``quality_dim_<dimension>`` columns back into long format.

    Returns:
        DataFrame with ``model``, ``quality_dimension``, ``dimension_score``
        columns (rows with a missing score are dropped), ready for
        :func:`dashboard.quality_viz.build_quality_dimension_heatmap`.
    """
    dimension_columns = [c for c in df.columns if c.startswith(_QUALITY_DIM_PREFIX)]
    if not dimension_columns or "model" not in df.columns:
        return pd.DataFrame(columns=["model", "quality_dimension", "dimension_score"])

    long_df = df[["model", *dimension_columns]].melt(
        id_vars="model", var_name="quality_dimension", value_name="dimension_score"
    )
    long_df["quality_dimension"] = long_df["quality_dimension"].str.removeprefix(_QUALITY_DIM_PREFIX)
    return long_df.dropna(subset=["dimension_score"]).reset_index(drop=True)


def load_quality_details(benchmark_path: Path) -> pd.DataFrame:
    """Load scored quality details and collection diagnostics for a benchmark.

    Mirrors the ``results/call_costs/benchmark_<ts>_call_costs.csv`` naming
    convention: ``results/quality_details/benchmark_<ts>_quality_details.csv``.
    Returns an empty DataFrame (not an error) for runs predating this export,
    or when no prompt/response detail was collected.
    """
    details_path = benchmark_path.parent / "quality_details" / f"{benchmark_path.stem}_quality_details.csv"
    diagnostics_path = benchmark_path.parent / "quality_diagnostics" / f"{benchmark_path.stem}_quality_diagnostics.csv"
    frames: list[pd.DataFrame] = []
    if details_path.exists():
        details_df = pd.read_csv(details_path)
        if not details_df.empty:
            details_df["evidence_status"] = "Scored"
            frames.append(details_df)
    if diagnostics_path.exists():
        diagnostics_df = pd.read_csv(diagnostics_path)
        if not diagnostics_df.empty:
            diagnostics_df["evidence_status"] = "Collection anomaly"
            diagnostics_df["source"] = "collection_error"
            diagnostics_df["reasoning"] = diagnostics_df.get("error", "")
            frames.append(diagnostics_df)
    if not frames:
        return pd.DataFrame()
    details_df = pd.concat(frames, ignore_index=True, sort=False)
    if details_df.empty or "model" not in details_df.columns:
        return pd.DataFrame()
    defaults: dict[str, object] = {
        "quality_dimension": "legacy",
        "prompt": "",
        "response": "",
        "score": pd.NA,
        "reasoning": "",
        "judge_verdicts": "",
        "source": "legacy",
        "evidence_status": "Scored",
        "generation_id": "",
        "resolved_model": "",
        "request_sha256": "",
        "error": "",
        "expected_answers_json": "[]",
        "verification_status": "not_required",
    }
    for column, default in defaults.items():
        if column not in details_df.columns:
            details_df[column] = default
    verification_dir = benchmark_path.parent / "verification"
    verification_reports: dict[tuple[str, int], str] = {}
    for report_path in verification_dir.glob(f"{benchmark_path.stem}_*_prompt_*.json"):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            model = report.get("model")
            prompt_id = report.get("prompt_id")
            verification = report.get("verification")
            if isinstance(model, str) and isinstance(prompt_id, int) and isinstance(verification, str):
                verification_reports[(model, prompt_id)] = verification
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    if verification_reports and "prompt_id" in details_df.columns:
        prompt_ids = pd.to_numeric(details_df["prompt_id"], errors="coerce")
        resolved_verification = pd.Series(
            [
                verification_reports.get((str(model), int(prompt_id))) if pd.notna(prompt_id) else None
                for model, prompt_id in zip(details_df["model"], prompt_ids, strict=False)
            ],
            index=details_df.index,
            dtype="string",
        )
        details_df["verification_status"] = resolved_verification.fillna(details_df["verification_status"])
    return details_df


def load_recommendations(benchmark_path: Path) -> pd.DataFrame:
    """Load the Model Compass recommendation artifact beside a benchmark.

    Runs created before the recommendation contract return an empty frame so
    the HTML report can explain that the artifact is unavailable without
    breaking historical result browsing.
    """
    recommendations_path = benchmark_path.parent / "recommendations" / f"{benchmark_path.stem}_recommendations.csv"
    if not recommendations_path.exists():
        return pd.DataFrame()
    recommendations_df = pd.read_csv(recommendations_path)
    return recommendations_df if "model" in recommendations_df.columns else pd.DataFrame()


def run_provenance(benchmark_df: pd.DataFrame, recommendations_df: pd.DataFrame) -> dict[str, str]:
    """Return the identifiers two runs must share before their results are compared."""

    def recorded(frame: pd.DataFrame, column: str) -> str:
        values = sorted(frame[column].dropna().astype(str).unique()) if column in frame.columns else []
        return ", ".join(values) or "not recorded"

    weights = recorded(recommendations_df, "recommendation_weights")
    try:
        shares = json.loads(weights)
        weights = " · ".join(f"{name} {shares[name]:.0%}" for name in ("quality", "security", "cost", "performance"))
    except (ValueError, KeyError, TypeError):
        pass
    return {
        "Methodology": recorded(benchmark_df, "methodology_version"),
        "Quality suite": recorded(benchmark_df, "quality_suite_id"),
        "Use-case catalog": recorded(recommendations_df, "catalog_version"),
        "Security probe set": recorded(benchmark_df, "security_probe_set_id"),
        "Decision weights": weights,
        "Workload profile": recorded(benchmark_df, "workload_profile"),
    }


def run_warnings(benchmark_df: pd.DataFrame, source_name: str) -> list[str]:
    """List why a run must not be used as reference-grade recommendation evidence.

    A reference run follows the README standard path with the current
    methodology: ``owasp`` probes, at least three attempts per prompt and full
    quality coverage. Anything else stays readable but is flagged on every page.
    """
    warnings: list[str] = []
    if source_name.startswith("benchmark_preview_"):
        warnings.append("Synthetic dry-run data: responses, judges and prices are simulated, not model evidence.")
    methodologies = (
        sorted(benchmark_df["methodology_version"].dropna().astype(str).unique())
        if "methodology_version" in benchmark_df.columns
        else []
    )
    if not methodologies:
        warnings.append(
            "Methodology version not recorded: this run predates the frozen scoring rules, so its scores "
            "may use superseded formulas."
        )
    elif methodologies != [METHODOLOGY_VERSION]:
        warnings.append(
            f"Scored with methodology {', '.join(methodologies)}; the current version is {METHODOLOGY_VERSION}. "
            "Do not compare it with current runs."
        )
    # The run's configured attempt count is the most any model got; a model below
    # it lost attempts to technical collection errors, which is a separate issue.
    repetitions = numeric_series(benchmark_df, "quality_repetitions_observed")
    if repetitions.isna().all() or repetitions.max() < STANDARD_QUALITY_REPETITIONS:
        warnings.append(
            f"Fewer than {STANDARD_QUALITY_REPETITIONS} attempts per quality prompt: no confidence intervals and "
            "eligibility can hinge on a single response."
        )
    probe_sets = (
        benchmark_df["security_probe_set_id"].dropna().astype(str).unique()
        if "security_probe_set_id" in benchmark_df.columns
        else []
    )
    skipped = (
        "security_profile" in benchmark_df.columns
        and not benchmark_df.empty
        and benchmark_df["security_profile"].astype(str).eq("skip").all()
    )
    if skipped:
        warnings.append(
            "Security was skipped (SECURITY=skip): the recommendations rank models on quality, cost and "
            "performance only. Do not use them where prompt injection or data disclosure matters."
        )
    elif not any(probe_set.startswith(f"{STANDARD_SECURITY_PROFILE}-") for probe_set in probe_sets):
        warnings.append(
            "Security was not probed with the standard security path, so the RSI is not comparable with reference runs."
        )
    if "prompt_delivery_verified" in benchmark_df.columns and benchmark_df["prompt_delivery_verified"].eq(False).any():
        warnings.append(
            "Prompt delivery was not checked (PROMPT_DELIVERY_AUDIT=false): a gateway may have rewritten prompts "
            "before they reached the models, without any error."
        )
    coverage = numeric_series(benchmark_df, "quality_coverage_rate")
    incomplete = benchmark_df.loc[coverage.lt(1.0), "model"].astype(str) if "model" in benchmark_df else []
    if len(incomplete):
        warnings.append("Incomplete quality coverage for " + ", ".join(short_name(model) for model in incomplete) + ".")
    return warnings


def run_notices(benchmark_df: pd.DataFrame) -> list[str]:
    """List limits of a run that do not stop it from being reference-grade evidence.

    A few quality responses lost to technical collection errors (timeouts,
    provider errors) are excluded from the scores; the run stays usable, but
    the reader should know which models are affected.
    """
    notices: list[str] = []
    collection_errors = numeric_series(benchmark_df, "quality_collection_error_count").fillna(0)
    if collection_errors.gt(0).any() and "model" in benchmark_df:
        affected = ", ".join(
            f"{short_name(str(model))} ({int(count)})"
            for model, count in zip(benchmark_df["model"], collection_errors, strict=True)
            if count > 0
        )
        notices.append(
            f"Quality responses lost to technical collection errors: {affected}. Those attempts are excluded; "
            "the scores and intervals use the attempts collected."
        )
    if "undelivered_security_probes" in benchmark_df.columns and not benchmark_df.empty:
        undelivered = str(benchmark_df["undelivered_security_probes"].fillna("").iloc[0])
        if undelivered:
            notices.append(
                f"A gateway filter would have rewritten {len(undelivered.split(', '))} security probe(s), so they "
                f"were not sent and the RSI excludes them: {undelivered}. The RSI is comparable only with runs "
                "that have the same security_probe_set_id."
            )
    coverage = security_probe_coverage(security_probe_details_frame(benchmark_df))
    partial = coverage.loc[coverage["measured_scored_probes"] < coverage["scored_probes"]]
    if not partial.empty:
        affected = ", ".join(
            f"{short_name(str(row.model))} ({int(row.measured_scored_probes)}/{int(row.scored_probes)})"
            for row in partial.itertuples()
        )
        notices.append(
            f"Some scored security probes returned no gradable answer, so these RSIs rest on fewer probes: "
            f"{affected}. The missing probes are listed on the Security page."
        )
    return notices


PROFILE_RANK_PREFIX = "profile_rank_"


def weight_profile_leaders(rows: pd.DataFrame) -> dict[str, list[str]]:
    """Leaders of one use case under each named weight profile, from its ``profile_rank_*`` columns.

    Profiles keep their catalog order; a profile that ranks no model maps to
    an empty list.
    """
    leaders: dict[str, list[str]] = {}
    for column in rows.columns:
        if column.startswith(PROFILE_RANK_PREFIX):
            ranks = pd.to_numeric(rows[column], errors="coerce")
            leaders[column.removeprefix(PROFILE_RANK_PREFIX)] = [
                short_name(model) for model in rows.loc[ranks.eq(1), "model"]
            ]
    return leaders


def weight_profile_table(recommendations_df: pd.DataFrame) -> pd.DataFrame:
    """One row per named weight profile: its weights and the trade-offs they imply on the fixed anchors.

    Reads the ``weight_profiles`` and ``score_scales`` the recommendation
    artifact records, so the report explains the exact weights it ranked with.
    """
    from src.evaluators.recommendation import RecommendationScales, implied_tradeoffs

    if recommendations_df.empty or not {"weight_profiles", "score_scales"}.issubset(recommendations_df.columns):
        return pd.DataFrame()
    try:
        profiles = json.loads(str(recommendations_df["weight_profiles"].dropna().iloc[0]))
        scales = RecommendationScales.model_validate_json(str(recommendations_df["score_scales"].dropna().iloc[0]))
    except (IndexError, ValueError, json.JSONDecodeError):
        return pd.DataFrame()
    rows = []
    for name, weights in profiles.items():
        tradeoffs = implied_tradeoffs(weights, scales)
        factor = tradeoffs["price_factor_per_quality_point"]
        rows.append(
            {
                "Profile": profile_label(name),
                "Quality": weights["quality"],
                "Security": weights["security"],
                "Cost": weights["cost"],
                "Performance": weights["performance"],
                "1 quality point is worth": (
                    "more than any price gap" if factor > 1000 else f"a {factor:.0f}× price gap"
                ),
                "10× cheaper is worth": f"{tradeoffs['quality_points_per_10x_price']:.2f} quality point",
                "A confirmed leak costs": f"{tradeoffs['quality_points_per_confirmed_leak']:.1f} quality point",
            }
        )
    return pd.DataFrame(rows)


def profile_label(name: str) -> str:
    """Readable name of a weight profile, e.g. ``quality_first`` → ``quality-first``."""
    return name.replace("_", "-")


def disputed_prompt_ids(quality_details_df: pd.DataFrame) -> set[int]:
    """Prompts whose answer key most models reject, from the run's quality details.

    Content rows only: the derived output-format rows carry no answer of their
    own. A recommendation resting on such a prompt needs the item reviewed.
    """
    if quality_details_df.empty or "prompt_id" not in quality_details_df.columns:
        return set()
    content = quality_details_df
    if "quality_dimension" in content.columns:
        content = content.loc[content["quality_dimension"].ne("output_format_compliance")]
    items = analyze_items(content)
    disputed = items.loc[items["item_status"].eq(KEY_DISPUTED_STATUS), "prompt_id"]
    return {int(prompt_id) for prompt_id in pd.to_numeric(disputed, errors="coerce").dropna()}


def use_case_prompt_ids(rows: pd.DataFrame) -> set[int]:
    """Prompt IDs of a use case, from the JSON ``prompt_ids`` column of its recommendation rows."""
    if rows.empty or "prompt_ids" not in rows.columns:
        return set()
    try:
        return {int(prompt_id) for prompt_id in json.loads(str(rows["prompt_ids"].iloc[0]))}
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()


def ordered_use_case_recommendations(recommendations_df: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    """Return each use case's rows sorted for reading: by status, then rank, then score.

    Use cases keep their catalog order; within one, recommended models come
    first and models that cannot be ranked come last.
    """
    key = next((column for column in ("use_case_id", "use_case_name") if column in recommendations_df.columns), None)
    if recommendations_df.empty or key is None or "model" not in recommendations_df.columns:
        return []
    status_order = {status: index for index, status in enumerate(RECOMMENDATION_STATUS_LABELS)}
    groups: list[tuple[str, pd.DataFrame]] = []
    for use_case_id in recommendations_df[key].drop_duplicates():
        rows = recommendations_df.loc[recommendations_df[key] == use_case_id].copy()
        if "use_case_name" not in rows.columns:
            rows["use_case_name"] = use_case_id
        rows["_status_order"] = rows["recommendation_status"].map(status_order).fillna(len(status_order))
        rows["_rank"] = numeric_series(rows, "recommendation_rank")
        rows["_score"] = numeric_series(rows, "quality_score")
        rows = rows.sort_values(
            ["_status_order", "_rank", "_score", "model"],
            ascending=[True, True, False, True],
            na_position="last",
        ).drop(columns=["_status_order", "_rank", "_score"])
        groups.append((str(use_case_id), rows.reset_index(drop=True)))
    return groups


def quality_threshold_borderline(rows: pd.DataFrame) -> pd.Series:
    """Flag rows whose quality 95 % interval straddles the use-case threshold."""
    low = numeric_series(rows, "quality_score_ci95_low")
    high = numeric_series(rows, "quality_score_ci95_high")
    threshold = numeric_series(rows, "quality_threshold")
    return (low < threshold) & (high >= threshold)
