"""Quality-suite diagnostics: item discrimination and inter-judge agreement.

These are sidecar measurements. They describe how trustworthy the quality
screen is (does each prompt separate models? do the judges agree?) and never
rewrite the raw scores that feed ``avg_quality_score``.
"""

from __future__ import annotations

import json

import pandas as pd

from src.evaluators.quality_metrics import INPUT_CORRUPTION_STATUS, flag_suspected_input_corruption

ITEM_ANALYSIS_COLUMNS = [
    "prompt_id",
    "quality_dimension",
    "model_count",
    "mean_score",
    "min_score",
    "max_score",
    "score_stddev",
    "discrimination",
    "item_status",
]

JUDGE_AGREEMENT_COLUMNS = [
    "scope",
    "response_count",
    "krippendorff_alpha",
    "exact_agreement_rate",
    "within_one_rate",
    "mean_score",
    "mean_offset_vs_panel",
    "agreement_status",
]

MIN_MODELS_FOR_ITEM_ANALYSIS = 3
SATURATION_MIN_SCORE = 4.0
"""Item is saturated when every model scores at least this value."""
FLOOR_MAX_SCORE = 2.0
"""Item is at the floor when no model scores above this value."""
LOW_VARIANCE_STDDEV = 0.25
NEGATIVE_DISCRIMINATION = -0.1
LOW_AGREEMENT_ALPHA = 0.667
"""Krippendorff's lowest conventionally tolerable alpha for tentative conclusions."""
_MIN_JUDGES_PER_RESPONSE = 2
_MIN_RESPONSES_FOR_ALPHA = 2


def _item_status(frame: pd.DataFrame) -> pd.Series:
    """Classify each item; the first matching rule wins."""
    status = pd.Series("ok", index=frame.index, dtype="object")
    status[frame["discrimination"] < NEGATIVE_DISCRIMINATION] = "negative_discrimination"
    status[frame["score_stddev"] < LOW_VARIANCE_STDDEV] = "low_variance"
    status[frame["max_score"] <= FLOOR_MAX_SCORE] = "floor"
    status[frame["min_score"] >= SATURATION_MIN_SCORE] = "saturated"
    status[frame["model_count"] < MIN_MODELS_FOR_ITEM_ANALYSIS] = "insufficient_models"
    return status


def analyze_items(quality_df: pd.DataFrame) -> pd.DataFrame:
    """Measure how well each prompt separates the evaluated models.

    ``discrimination`` is the Pearson correlation between the item score and
    each model's mean score on the *other* items (corrected item-total
    correlation). A saturated, floor or near-constant item cannot rank models;
    a negative correlation means strong models fail it more often than weak
    ones, which points to a faulty prompt or reference answer.

    Args:
        quality_df: Long-format scores with ``model``, ``prompt_id`` and
            ``score``; ``quality_dimension`` and the reference-answer metadata
            are optional.

    Returns:
        One row per prompt. Empty (with the expected columns) when there are
        no usable scores. Prompts flagged as suspected input corruption keep
        their row with that status.
    """
    if quality_df.empty or not {"model", "prompt_id", "score"}.issubset(quality_df.columns):
        return pd.DataFrame(columns=ITEM_ANALYSIS_COLUMNS)

    work_df = quality_df.copy()
    work_df["score"] = pd.to_numeric(work_df["score"], errors="coerce")
    work_df["quality_dimension"] = (
        work_df["quality_dimension"].fillna("legacy") if "quality_dimension" in work_df.columns else "legacy"
    )
    corrupted_prompts = set(work_df.loc[flag_suspected_input_corruption(work_df), "prompt_id"])
    work_df = work_df.dropna(subset=["model", "prompt_id", "score"])
    if work_df.empty:
        return pd.DataFrame(columns=ITEM_ANALYSIS_COLUMNS)

    per_model_df = work_df.groupby(["prompt_id", "model"], as_index=False).agg(score=("score", "mean"))
    matrix = per_model_df.pivot(index="model", columns="prompt_id", values="score")

    observed = matrix.notna()
    row_sum = matrix.sum(axis=1)
    rest_count = observed.sum(axis=1).to_numpy()[:, None] - observed.to_numpy().astype(int)
    rest_mean = pd.DataFrame(
        (row_sum.to_numpy()[:, None] - matrix.fillna(0.0).to_numpy()) / rest_count.clip(min=1),
        index=matrix.index,
        columns=matrix.columns,
    ).where(rest_count > 0)
    discrimination = matrix.corrwith(rest_mean, axis=0)

    stats_df = per_model_df.groupby("prompt_id").agg(
        model_count=("model", "nunique"),
        mean_score=("score", "mean"),
        min_score=("score", "min"),
        max_score=("score", "max"),
        score_stddev=("score", lambda s: s.std(ddof=0)),
    )
    stats_df["discrimination"] = discrimination.reindex(stats_df.index)
    dimension_df = work_df.groupby("prompt_id")["quality_dimension"].first()
    stats_df.insert(0, "quality_dimension", dimension_df.reindex(stats_df.index))
    stats_df["item_status"] = _item_status(stats_df)
    stats_df.loc[stats_df.index.isin(corrupted_prompts), "item_status"] = INPUT_CORRUPTION_STATUS
    return stats_df.reset_index()[ITEM_ANALYSIS_COLUMNS].sort_values("prompt_id").reset_index(drop=True)


def _expand_judge_verdicts(quality_df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per (response, judge) from the ``judge_verdicts`` JSON column."""
    records: list[dict[str, object]] = []
    for unit, raw in enumerate(quality_df["judge_verdicts"].fillna("").astype(str)):
        if not raw.strip():
            continue
        try:
            verdicts = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(verdicts, list):
            continue
        for verdict in verdicts:
            if not isinstance(verdict, dict):
                continue
            records.append({"unit": unit, "judge_id": verdict.get("judge_id"), "score": verdict.get("score")})
    ratings = pd.DataFrame(records, columns=["unit", "judge_id", "score"])
    ratings["score"] = pd.to_numeric(ratings["score"], errors="coerce")
    ratings = ratings.dropna(subset=["judge_id", "score"])
    if "quality_dimension" in quality_df.columns:
        dimensions = quality_df["quality_dimension"].fillna("legacy").reset_index(drop=True)
    else:
        dimensions = pd.Series("legacy", index=range(len(quality_df)))
    ratings["quality_dimension"] = ratings["unit"].map(dimensions)
    return ratings


def krippendorff_alpha_interval(ratings: pd.DataFrame) -> float:
    """Krippendorff's alpha for interval data over units rated by 2+ judges.

    Args:
        ratings: Long frame with ``unit`` and numeric ``score`` columns.

    Returns:
        Alpha in ``(-inf, 1]``; ``NaN`` when fewer than two usable units exist
        or when every rating is identical (no variance to disagree about).
    """
    if ratings.empty:
        return float("nan")
    counts = ratings.groupby("unit")["score"].transform("size")
    pairable = ratings.loc[counts >= _MIN_JUDGES_PER_RESPONSE]
    if pairable["unit"].nunique() < _MIN_RESPONSES_FOR_ALPHA:
        return float("nan")

    scores = pairable["score"].astype(float)
    total_count = float(len(scores))
    expected_disagreement = (
        2.0 * (total_count * (scores**2).sum() - scores.sum() ** 2) / (total_count * (total_count - 1))
    )
    if expected_disagreement <= 0:
        return float("nan")

    per_unit = (
        pairable.assign(score_squared=scores**2)
        .groupby("unit")
        .agg(m=("score", "size"), s1=("score", "sum"), s2=("score_squared", "sum"))
    )
    unit_disagreement = 2.0 * (per_unit["m"] * per_unit["s2"] - per_unit["s1"] ** 2) / (per_unit["m"] - 1)
    observed_disagreement = float(unit_disagreement.sum()) / total_count
    return float(1.0 - observed_disagreement / expected_disagreement)


def _agreement_rates(ratings: pd.DataFrame) -> tuple[float, float]:
    """Return (exact-agreement rate, within-one-point rate) across rated units."""
    spread = ratings.groupby("unit")["score"].agg(lambda s: s.max() - s.min())
    multi = ratings.groupby("unit")["score"].transform("size") >= _MIN_JUDGES_PER_RESPONSE
    spread = spread.loc[ratings.loc[multi, "unit"].unique()]
    if spread.empty:
        return float("nan"), float("nan")
    return float((spread == 0).mean()), float((spread <= 1).mean())


def summarize_judge_agreement(quality_df: pd.DataFrame) -> pd.DataFrame:
    """Quantify inter-judge agreement and per-judge leniency.

    Rows: one ``panel`` row (alpha, exact/within-one agreement), one row per
    ``judge:<id>`` (mean score and offset against the other judges' mean) and
    one per ``dimension:<name>`` (alpha within that quality dimension).
    ``agreement_status`` is ``low_agreement`` when alpha is under
    :data:`LOW_AGREEMENT_ALPHA`; scores are never altered by it.

    Args:
        quality_df: Long-format scores with the ``judge_verdicts`` JSON column
            produced by the merge step. Deterministic rows are ignored.

    Returns:
        The summary frame, or an empty frame with the expected columns for
        legacy runs without per-judge verdicts.
    """
    if quality_df.empty or "judge_verdicts" not in quality_df.columns:
        return pd.DataFrame(columns=JUDGE_AGREEMENT_COLUMNS)
    ratings = _expand_judge_verdicts(quality_df)
    if ratings.empty:
        return pd.DataFrame(columns=JUDGE_AGREEMENT_COLUMNS)

    def status_for(alpha: float) -> str:
        if pd.isna(alpha):
            return "insufficient_data"
        return "low_agreement" if alpha < LOW_AGREEMENT_ALPHA else "acceptable"

    rows: list[dict[str, object]] = []
    exact, within_one = _agreement_rates(ratings)
    panel_alpha = krippendorff_alpha_interval(ratings)
    rows.append(
        {
            "scope": "panel",
            "response_count": int(ratings["unit"].nunique()),
            "krippendorff_alpha": panel_alpha,
            "exact_agreement_rate": exact,
            "within_one_rate": within_one,
            "mean_score": float(ratings["score"].mean()),
            "mean_offset_vs_panel": 0.0,
            "agreement_status": status_for(panel_alpha),
        }
    )

    unit_sum = ratings.groupby("unit")["score"].transform("sum")
    unit_size = ratings.groupby("unit")["score"].transform("size")
    others_mean = (unit_sum - ratings["score"]) / (unit_size - 1).where(unit_size > 1)
    ratings = ratings.assign(offset=ratings["score"] - others_mean)
    for judge_id, judge_df in ratings.groupby("judge_id"):
        rows.append(
            {
                "scope": f"judge:{judge_id}",
                "response_count": int(judge_df["unit"].nunique()),
                "krippendorff_alpha": float("nan"),
                "exact_agreement_rate": float("nan"),
                "within_one_rate": float("nan"),
                "mean_score": float(judge_df["score"].mean()),
                "mean_offset_vs_panel": float(judge_df["offset"].mean()),
                "agreement_status": "",
            }
        )

    for dimension, dimension_df in ratings.groupby("quality_dimension"):
        alpha = krippendorff_alpha_interval(dimension_df)
        dim_exact, dim_within_one = _agreement_rates(dimension_df)
        rows.append(
            {
                "scope": f"dimension:{dimension}",
                "response_count": int(dimension_df["unit"].nunique()),
                "krippendorff_alpha": alpha,
                "exact_agreement_rate": dim_exact,
                "within_one_rate": dim_within_one,
                "mean_score": float(dimension_df["score"].mean()),
                "mean_offset_vs_panel": float("nan"),
                "agreement_status": status_for(alpha),
            }
        )
    return pd.DataFrame(rows, columns=JUDGE_AGREEMENT_COLUMNS)
