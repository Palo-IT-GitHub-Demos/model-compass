"""Export the static, multi-page Model Compass HTML report.

Derived columns come from :mod:`dashboard.data_prep` and charts from
:mod:`dashboard.pareto`, :mod:`dashboard.security_viz` and the other
``dashboard`` visualisation modules, all pure and unit-tested. The output is an
entry page plus a sibling folder of linked pages that opens from disk without a
server or network access (Plotly is copied next to the pages), with a glossary
explaining every acronym (RSI, TCO, CER, ZDR, OWASP...).

Usage
-----
    python scripts/export_dashboard_html.py \\
        --results results/benchmark_<ts>.csv \\
        --output  results/dashboard_<ts>.html \\
        --profile enterprise_qa

    # Uses the latest results/benchmark_*.csv and enterprise_qa by default
    python scripts/export_dashboard_html.py
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

# Running this file directly (``python scripts/export_dashboard_html.py``) does not
# put the project root on sys.path — only the script's own directory. Add it so the
# sibling `dashboard`/`src` packages (not pip-installed, unlike the editable `src`
# wheel) are importable regardless of how this script is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.data_prep import (  # noqa: E402
    PROFILE_RANK_PREFIX,
    RECOMMENDATION_STATUS_LABELS,
    best_models,
    compute_cost_columns,
    disputed_prompt_ids,
    enrich_benchmark,
    format_judge_verdicts,
    leaders_label,
    load_quality_details,
    load_recommendations,
    ordered_use_case_recommendations,
    profile_label,
    quality_dimension_long_frame,
    quality_dimension_table,
    quality_threshold_borderline,
    quality_tier,
    run_notices,
    run_provenance,
    run_warnings,
    safest_summary,
    security_category_table,
    security_long_frame,
    security_observations_frame,
    security_probe_coverage,
    security_probe_details_frame,
    short_name,
    tint_status,
    use_case_prompt_ids,
    weight_profile_leaders,
    weight_profile_table,
)
from dashboard.glossary import COLUMN_TOOLTIPS, GLOSSARY_INTRO, glossary_html  # noqa: E402
from dashboard.pareto import build_pareto_scatter, compute_pareto_front  # noqa: E402
from dashboard.performance_viz import build_latency_bar  # noqa: E402
from dashboard.quality_viz import build_quality_dimension_heatmap  # noqa: E402
from dashboard.security_viz import build_cost_security_quadrant, build_owasp_heatmap, build_rsi_bar  # noqa: E402
from src.evaluators.cost_analyzer import BUILTIN_WORKLOAD_PROFILES, WorkloadProfile  # noqa: E402

_RESULTS_DIR = Path("results")
_REQUIRED_COLUMNS = {"model", "avg_quality_score", "prompt_price_per_token"}
_PLOTLY_FILENAME = "plotly.min.js"

_CSS = """
:root { color-scheme: light; }
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       margin: 0; padding: 2rem; max-width: 1200px; margin-inline: auto; color: #1a1a2e; }
h1 { margin-bottom: 0.25rem; }
h2 { margin-top: 2.5rem; border-bottom: 2px solid #eee; padding-bottom: 0.4rem; }
.subtitle { color: #555; margin-top: 0; }
.meta { color: #777; font-size: 0.9rem; }
section.glossary { background: #f6f8fb; border: 1px solid #e1e6ee; border-radius: 8px;
                    padding: 1.2rem 1.5rem; margin: 1.5rem 0; }
section.glossary dt { font-weight: 600; margin-top: 0.7rem; }
section.glossary dd { margin-left: 0; color: #333; }
.kpi-row { display: flex; flex-wrap: wrap; gap: 1rem; margin: 1rem 0; }
.kpi-card { flex: 1 1 220px; border: 1px solid #e1e6ee; border-radius: 8px; padding: 1rem; }
.kpi-card .label { color: #666; font-size: 0.85rem; }
.kpi-card .value { font-size: 1.4rem; font-weight: 700; margin: 0.2rem 0; }
.kpi-card .detail { color: #2e7d32; font-size: 0.85rem; }
.table-wrap { overflow-x: auto; margin: 1rem 0; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { border: 1px solid #e1e6ee; padding: 0.45rem 0.6rem; text-align: left; white-space: nowrap; }
th { background: #f6f8fb; }
table.wrap-table td { white-space: pre-line; word-break: break-word; max-width: 28rem; vertical-align: top; }
.chart { margin: 1rem 0; }
details summary { cursor: pointer; font-weight: 600; margin: 1rem 0 0.5rem; }
.callout { background: #eef4fb; border-left: 4px solid #3498db; padding: 0.7rem 1rem; margin: 1rem 0; }
.warning { background: #fff4e5; border-left: 4px solid #e67e22; padding: 0.7rem 1rem; margin: 1rem 0; }
.warning ul { margin: 0.4rem 0 0; }
.notice { background: #eef4fb; border-left: 4px solid #4a7fb5; padding: 0.5rem 1rem; margin: 1rem 0; }
nav.toc { background: #fff; border: 1px solid #e1e6ee; border-radius: 8px; padding: 1rem 1.5rem; margin: 1.5rem 0; }
nav.toc ul { margin: 0; padding-left: 1.2rem; columns: 3; }
nav.toc a { color: #2471a3; text-decoration: none; }
nav.toc a:hover { text-decoration: underline; }
nav.toc a[aria-current="page"] { font-weight: 700; color: #1a1a2e; }
h2 { scroll-margin-top: 1rem; }
h3 { margin-top: 1.8rem; }
.use-cases { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }
.use-case { border: 1px solid #e1e6ee; border-radius: 8px; padding: 1rem 1.2rem; }
.use-case h3 { margin: 0 0 0.3rem; font-size: 1.05rem; }
.use-case p { margin: 0.4rem 0; }
.use-case ul { margin: 0.4rem 0 0; padding-left: 1.1rem; }
.leader { font-size: 1.1rem; font-weight: 700; }
.none { color: #721c24; font-weight: 600; }
.badge { display: inline-block; border-radius: 4px; padding: 0 0.35rem; font-size: 0.8rem; margin-left: 0.3rem; }
.badge.fragile { background: #fff3cd; color: #856404; }
.badge.tied { background: #d1ecf1; color: #0c5460; }
.badge.borderline { background: #fff3cd; color: #856404; }
@media (max-width: 640px) {
  body { padding: 1rem; }
  nav.toc ul { columns: 1; }
}
"""

_GLOSSARY_INTRO = "This report is a static snapshot of a Model Compass run (OpenRouter). " + GLOSSARY_INTRO

_GLOSSARY_HTML = glossary_html(_GLOSSARY_INTRO)

_PAGES = [
    ("summary", "Decision summary", "index.html"),
    ("recommendations", "Use cases in detail", "recommendations.html"),
    ("overview", "Quality × cost", "overview.html"),
    ("quality", "Quality", "quality.html"),
    ("security", "Security", "security.html"),
    ("cost", "Cost", "cost.html"),
    ("performance", "Performance", "performance.html"),
    ("evidence", "Prompts & responses", "evidence.html"),
    ("glossary", "Glossary", "glossary.html"),
]


def _latest_results_csv() -> Path | None:
    csv_files = sorted(_RESULTS_DIR.glob("benchmark_*.csv"), reverse=True)
    return csv_files[0] if csv_files else None


def _navigation_html(active_page: str, href_prefix: str = "") -> str:
    """Render the shared navigation for a static report page."""
    items = "".join(
        (
            f'<li><a href="{href_prefix}{filename}" aria-current="page">{label}</a></li>'
            if page_id == active_page
            else f'<li><a href="{href_prefix}{filename}">{label}</a></li>'
        )
        for page_id, label, filename in _PAGES
    )
    return f'<nav class="toc" aria-label="Report navigation"><ul>{items}</ul></nav>'


def _fig_html(fig: go.Figure) -> str:
    """Render a Plotly figure as a snippet; every page loads the local Plotly bundle in its head."""
    return str(fig.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False}))


def _kpi_card(label: str, value: str, detail: str) -> str:
    return (
        '<div class="kpi-card">'
        f'<div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(value)}</div>'
        f'<div class="detail">{escape(detail)}</div>'
        "</div>"
    )


def _leader_card(label: str, frame: pd.DataFrame, column: str, value_format: str, *, ascending: bool = False) -> str:
    """KPI card naming every model tied for the best *column* value — never an arbitrary first row."""
    models, value = best_models(frame, column, ascending=ascending)
    if value is None:
        return _kpi_card(label, "—", "")
    detail = value_format.format(value)
    if len(models) > 1:
        detail += ": " + ", ".join(short_name(model) for model in models)
    return _kpi_card(label, leaders_label(models), detail)


_TH_HEADING = re.compile(r'(<th\s+[^>]*class="[^"]*col_heading[^"]*"[^>]*)(>)([^<]*)(</th>)')


def _annotate_header_tooltips(html: str) -> str:
    """Add a native title= tooltip to <th> headers matching a known glossary column.

    pandas Styler has no first-class per-header title attribute, so this does a
    light string post-process instead of a second render pass.
    """

    def _inject(match: re.Match[str]) -> str:
        attrs, gt, label, close = match.groups()
        tooltip = COLUMN_TOOLTIPS.get(label)
        if not tooltip:
            return match.group(0)
        return f'{attrs} title="{escape(tooltip)}"{gt}{label}{close}'

    return _TH_HEADING.sub(_inject, html)


def _table_html(
    df: pd.DataFrame,
    formats: dict[str, str] | None = None,
    status_column: str | None = None,
    table_class: str = "data-table",
) -> str:
    """Render *df* to an HTML table, escaping every cell to prevent injected markup.

    Some columns (e.g. security probe previews, or full model responses) hold
    raw LLM completions — untrusted text that must never be interpreted as
    HTML/JS by a browser. ``Styler.to_html`` does not escape by default, so
    ``format(..., escape="html")`` is mandatory here (verified against pandas 2.3).
    """
    styler = df.style.hide(axis="index").format(formats or {}, escape="html", na_rep="—")
    styler = styler.set_table_attributes(f'class="{table_class}"')
    if status_column and status_column in df.columns:
        styler = styler.map(tint_status, subset=[status_column])
    return _annotate_header_tooltips(str(styler.to_html()))


def _bool_icon(value: object) -> str:
    return "✓" if bool(value) else "—"


def _number(value: object, pattern: str) -> str:
    """Format a numeric cell, or return an em dash when it is missing."""
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "—" if pd.isna(number) else pattern.format(number)


def _yes_no(value: object) -> str:
    if value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return "yes" if str(value).strip().lower() in {"true", "1", "1.0"} else "no"


def _is_true(value: object) -> bool:
    return _yes_no(value) == "yes"


# ── Decision summary ──────────────────────────────────────────────────────────


def _model_list(rows: pd.DataFrame, describe: Callable[[pd.Series], object]) -> str:
    """Render ``model (detail)`` items for a list of recommendation rows, escaped."""
    return ", ".join(
        f"<strong>{escape(short_name(row['model']))}</strong> ({escape(str(describe(row)))})"
        for _, row in rows.iterrows()
    )


def _use_case_card(rows: pd.DataFrame, disputed_prompts: set[int] | frozenset[int] = frozenset()) -> str:
    """One decision card: who to pick for this generic use case, and how sure that is."""
    first = rows.iloc[0]
    threshold = float(first["quality_threshold"]) if "quality_threshold" in rows.columns else float("nan")
    status = rows["recommendation_status"].astype(str)
    borderline = quality_threshold_borderline(rows)
    recommended = rows.loc[status.eq("recommended")]
    eligible = rows.loc[status.eq("eligible")]
    tied_mask = (
        eligible["quality_ci95_overlaps_leader"].map(_is_true)
        if "quality_ci95_overlaps_leader" in eligible.columns
        else pd.Series(False, index=eligible.index)
    )
    tied = eligible.loc[tied_mask.astype(bool)]
    other_eligible = eligible.drop(index=tied.index)
    below = rows.loc[status.eq("below_quality_threshold")]
    missing = rows.loc[status.eq("insufficient_decision_evidence")]
    incomplete = rows.loc[status.eq("insufficient_quality_evidence")]

    if recommended.empty:
        headline = '<p class="none">No model can be recommended for this use case in this run.</p>'
    else:
        leaders = []
        for _, row in recommended.iterrows():
            badges = ""
            if _is_true(row.get("recommendation_fragile")):
                low = _number(row.get("recommendation_sensitivity_rank_min"), "{:.0f}")
                high = _number(row.get("recommendation_sensitivity_rank_max"), "{:.0f}")
                badges += f'<span class="badge fragile" title="Rank range under ±10%: {low}–{high}">fragile</span>'
            leaders.append(
                f"{escape(short_name(row['model']))} "
                f'<span class="meta">({_number(row.get("recommendation_score"), "{:.1f}")} / 100 · '
                f"quality {_number(row.get('quality_score'), '{:.2f}')} / 5)</span>{badges}"
            )
        label = "Recommended (tied)" if len(leaders) > 1 else "Recommended"
        headline = f'<p>{label}: <span class="leader">{"; ".join(leaders)}</span></p>'

    items: list[str] = []
    profile_leaders = weight_profile_leaders(rows)
    if profile_leaders:
        described = "; ".join(
            f"{escape(profile_label(name))}: <strong>{escape(', '.join(models) or 'none')}</strong>"
            for name, models in profile_leaders.items()
        )
        if len({tuple(models) for models in profile_leaders.values()}) > 1:
            items.append(
                '<li><span class="badge fragile">weight-profile-sensitive</span> the leader depends on the weight '
                f"profile ({described}). Pick the profile that matches the tender.</li>"
            )
        else:
            items.append(
                f'<li><span class="badge tied">same leader</span> under every weight profile ({described}).</li>'
            )
    disputed = sorted(use_case_prompt_ids(rows) & set(disputed_prompts))
    if disputed:
        items.append(
            '<li><span class="badge fragile">disputed key</span> on prompt '
            + ", ".join(str(prompt_id) for prompt_id in disputed)
            + ", most models give the same answer the reference key rejects. Review that item before relying "
            "on this ranking.</li>"
        )
    judge_sensitive = (
        rows["affiliated_judge_changes_outcome"].map(_is_true)
        if "affiliated_judge_changes_outcome" in rows.columns
        else pd.Series(False, index=rows.index)
    )
    if judge_sensitive.any():
        alternative_status = rows.get("recommendation_status_without_affiliated_judge", pd.Series(index=rows.index))
        alternative = rows.loc[alternative_status.astype(str).eq("recommended")]
        names = ", ".join(escape(short_name(model)) for model in alternative["model"]) or "no model"
        items.append(
            '<li><span class="badge fragile">judge-sensitive</span> without the judge from each model\'s own '
            f"provider, the recommendation would be: <strong>{names}</strong></li>"
        )
    if not tied.empty:
        items.append(
            '<li><span class="badge tied">within uncertainty</span> quality not distinguishable from the leader: '
            + _model_list(tied, lambda row: f"rank {_number(row.get('recommendation_rank'), '{:.0f}')}")
            + "</li>"
        )
    if not other_eligible.empty:
        items.append(
            "<li>Also eligible: "
            + _model_list(
                other_eligible,
                lambda row: (
                    f"rank {_number(row.get('recommendation_rank'), '{:.0f}')}, "
                    f"{_number(row.get('recommendation_score'), '{:.1f}')} / 100"
                ),
            )
            + "</li>"
        )
    if not missing.empty:
        items.append(
            "<li>Passes the threshold but cannot be ranked (missing evidence): "
            + _model_list(missing, lambda row: row.get("evidence_missing") or "unknown")
            + "</li>"
        )
    if not below.empty:
        items.append(
            "<li>Below the quality threshold: "
            + _model_list(
                below,
                lambda row: (
                    f"{_number(row.get('quality_score'), '{:.2f}')} / 5"
                    + (", borderline" if bool(borderline.loc[row.name]) else "")
                ),
            )
            + "</li>"
        )
    if not incomplete.empty:
        items.append(
            "<li>Incomplete quality evidence: "
            + _model_list(incomplete, lambda row: f"coverage {_number(row.get('quality_coverage_rate'), '{:.0%}')}")
            + "</li>"
        )
    description = escape(str(first.get("use_case_description", "")))
    return f"""
    <section class="use-case">
      <h3>{escape(str(first["use_case_name"]))}</h3>
      <p class="meta">{description} Quality threshold {_number(threshold, "{:.1f}")} / 5.</p>
      {headline}
      <ul>{"".join(items)}</ul>
    </section>
    """


def _sources_html(source_paths: list[tuple[str, Path]], from_dir: Path | None) -> str:
    """Link the artifacts behind the report, relative to the page that shows them."""
    if not source_paths or from_dir is None:
        return ""
    links = "".join(
        f'<li><a href="{escape(Path(os.path.relpath(path, from_dir)).as_posix())}">{escape(label)}</a></li>'
        for label, path in source_paths
    )
    return f"<h3>Source artifacts</h3><ul>{links}</ul>"


def _summary_section(
    recommendations_df: pd.DataFrame, sources: str = "", disputed_prompts: set[int] | frozenset[int] = frozenset()
) -> str:
    """Render the opening page: one decision card per generic use case."""
    groups = ordered_use_case_recommendations(recommendations_df)
    if not groups:
        return f"""
        <h2 id="summary">Decision summary</h2>
        <p class="callout">No Model Compass recommendation artifact is available for this run.
        Re-run <code>make collect</code>, complete the judge phase, then run <code>make merge</code>.</p>
        {sources}
        """
    cards = "".join(_use_case_card(rows, disputed_prompts) for _, rows in groups)
    return f"""
    <h2 id="summary">Decision summary</h2>
    <p class="callout"><strong>How to read this:</strong> each card is one generic use case. A model
    is <strong>recommended</strong> when it passes the use case's quality threshold with complete
    evidence and has the best weighted decision score; equal scores share the place.
    <strong>Fragile</strong> means a 10 % change of one weight or of the threshold changes the outcome,
    and <strong>within uncertainty</strong> means the quality gap with the leader is not established.
    Match the use cases to the tender yourself: the final choice remains human.</p>
    <div class="use-cases">{cards}</div>
    {sources}
    """


# ── Use cases in detail ───────────────────────────────────────────────────────


def _use_case_detail_table(rows: pd.DataFrame) -> str:
    """Readable recommendation table for one use case, ranked rows first."""
    missing = pd.Series(pd.NA, index=rows.index, dtype="object")

    def column(name: str) -> pd.Series:
        return rows[name] if name in rows.columns else missing

    def numbers(name: str, pattern: str) -> list[str]:
        return [_number(value, pattern) for value in column(name)]

    def interval(row: pd.Series) -> str:
        low, high = row.get("quality_score_ci95_low"), row.get("quality_score_ci95_high")
        return "—" if pd.isna(low) or pd.isna(high) else f"{float(low):.2f}–{float(high):.2f}"

    def rank_range(row: pd.Series) -> str:
        low = _number(row.get("recommendation_sensitivity_rank_min"), "{:.0f}")
        high = _number(row.get("recommendation_sensitivity_rank_max"), "{:.0f}")
        if low == "—":
            return "—"
        return low if low == high else f"{low}–{high}"

    ranked = pd.to_numeric(column("recommendation_rank"), errors="coerce").notna()
    borderline = quality_threshold_borderline(rows)
    status = column("recommendation_status").astype("string")
    display = pd.DataFrame(
        {
            "Model": rows["model"],
            "Status": status.map(RECOMMENDATION_STATUS_LABELS).fillna(status),
            "Rank": numbers("recommendation_rank", "{:.0f}"),
            "Decision score": [
                _number(score, "{:.1f}") if is_ranked else "not ranked"
                for score, is_ranked in zip(column("recommendation_score"), ranked, strict=True)
            ],
            "Quality (1–5)": [
                _number(score, "{:.2f}") + (" · borderline" if flag else "")
                for score, flag in zip(column("quality_score"), borderline, strict=True)
            ],
            "Quality 95% CI": rows.apply(interval, axis=1),
            "Within leader's CI": column("quality_ci95_overlaps_leader").map(_yes_no),
            "Coverage": numbers("quality_coverage_rate", "{:.0%}"),
            "Format respected": numbers("format_compliance_rate", "{:.0%}"),
            "Security": numbers("security_score", "{:.0f}"),
            "Cost score": numbers("cost_score", "{:.0f}"),
            "USD / 1k requests": numbers("cost_usd_per_1k_requests", "${:.3f}"),
            "Performance": numbers("performance_score", "{:.0f}"),
            "Rank range (±10%)": rows.apply(rank_range, axis=1),
            **{
                f"Rank ({profile_label(column.removeprefix(PROFILE_RANK_PREFIX))})": numbers(column, "{:.0f}")
                for column in rows.columns
                if column.startswith(PROFILE_RANK_PREFIX)
            },
            "Fragile": column("recommendation_fragile").map(_yes_no),
            "Quality w/o own-provider judge": numbers("quality_score_without_affiliated_judge", "{:.2f}"),
            "Outcome w/o own-provider judge": [
                RECOMMENDATION_STATUS_LABELS.get(str(status), "—")
                + (f" (rank {_number(rank, '{:.0f}')})" if not pd.isna(rank) else "")
                for status, rank in zip(
                    column("recommendation_status_without_affiliated_judge"),
                    pd.to_numeric(column("recommendation_rank_without_affiliated_judge"), errors="coerce"),
                    strict=True,
                )
            ],
            "Missing evidence": column("evidence_missing").fillna("").replace("", "—"),
        }
    )
    return _table_html(display, status_column="Status")


def _recommendations_section(recommendations_df: pd.DataFrame) -> str:
    """Render every use case's ranked table with its threshold and uncertainty."""
    groups = ordered_use_case_recommendations(recommendations_df)
    if not groups:
        return """
        <h2 id="recommendations">Use cases in detail</h2>
        <p class="callout">No Model Compass recommendation artifact is available for this run.
        Re-run <code>make collect</code>, complete the judge phase, then run <code>make merge</code>.</p>
        """
    sections = []
    for _, rows in groups:
        first = rows.iloc[0]
        threshold = _number(first.get("quality_threshold"), "{:.1f}")
        sections.append(
            f"""
            <h3>{escape(str(first["use_case_name"]))}</h3>
            <p class="meta">{escape(str(first.get("use_case_description", "")))} Quality threshold
            {threshold} / 5 · prompts {escape(str(first.get("prompt_ids", "—")))}.</p>
            <div class="table-wrap">{_use_case_detail_table(rows)}</div>
            """
        )
    profiles = weight_profile_table(recommendations_df)
    profiles_block = ""
    if not profiles.empty:
        profiles_block = f"""
        <h3>Weight profiles</h3>
        <p class="meta">The published rank uses the run's recorded weights, which by default are the balanced
        profile; the other profiles only show whether the leader would change. Quality points are on the 1–5 scale; the
        price and latency trade-offs use the fixed logarithmic anchors of the catalog. A model below a use
        case's quality threshold is excluded whatever the profile.</p>
        <div class="table-wrap">{
            _table_html(profiles, formats=dict.fromkeys(["Quality", "Security", "Cost", "Performance"], "{:.0%}"))
        }</div>
        """
    return f"""
    <h2 id="recommendations">Use cases in detail</h2>
    {profiles_block}
    <p class="callout"><strong>How to read this:</strong> every model remains visible for every
    generic use case. A model must first pass that use case's quality threshold; only then can the
    weighted decision score rank it, and only ranked models show a decision score. Quality scores the
    content of the answers; "Format respected" shows separately how often a strict output format
    (bare answer, raw JSON) was followed, and never lowers the quality score. Equal scores keep
    the same rank. Component scores run from 0 to 100; cost and p95 latency use fixed logarithmic
    anchors recorded in the versioned catalog, not the other models of this run.</p>
    {"".join(sections)}
    """


# ── Quality × cost ────────────────────────────────────────────────────────────


def _overview_section(df: pd.DataFrame) -> str:
    plot_df = df.dropna(subset=["cost_per_1k_requests_usd", "avg_quality_score"])
    pareto_df = compute_pareto_front(plot_df, cost_col="cost_per_1k_requests_usd", quality_col="avg_quality_score")

    best_value_card = _kpi_card("Best value", "—", "")
    if not pareto_df.empty:
        quality_floor = plot_df["avg_quality_score"].max() * 0.9
        value_candidates = pareto_df.loc[pareto_df["avg_quality_score"] >= quality_floor]
        if value_candidates.empty:
            value_candidates = pareto_df
        best_value_card = _leader_card(
            "Best value (cheapest within 10% of peak quality)",
            value_candidates,
            "cost_per_1k_requests_usd",
            "${:.3f} / 1k requests",
            ascending=True,
        )
    safest_headline, safest_detail = safest_summary(df)

    kpi_cards = "".join(
        [
            _leader_card("Highest overall quality", plot_df, "avg_quality_score", "{:.2f} / 5"),
            _leader_card("Lowest cost", plot_df, "cost_per_1k_requests_usd", "${:.3f} / 1k requests", ascending=True),
            best_value_card,
            _kpi_card("Highest RSI", safest_headline, safest_detail),
        ]
    )

    overview_columns = ["model", "avg_quality_score", "quality_coverage_rate", "cost_per_1k_requests_usd"]
    if "security_status" in pareto_df.columns:
        overview_columns.append("security_status")
    pareto_table = _table_html(
        pareto_df[[c for c in overview_columns if c in pareto_df.columns]],
        formats={
            "avg_quality_score": "{:.2f} / 5",
            "quality_coverage_rate": "{:.0%}",
            "cost_per_1k_requests_usd": "${:.4f}",
        },
        status_column="security_status",
    )

    return f"""
    <h2 id="overview">Quality × cost</h2>
    <p class="callout"><strong>How to read this:</strong> quality runs from 1 (poor) to 5 (excellent),
    while the cost of 1,000 requests, with each model's measured output length, is better when lower.
    This is an aggregate view across all
    use cases: it ignores the use-case thresholds and the security weighting, so choose from the
    <a href="index.html">Decision summary</a>, not from this page.</p>
    <div class="kpi-row">{kpi_cards}</div>
    <p class="callout">The best models sit in the top-left of the chart: high quality score for a
    low cost. The dashed line traces the Pareto frontier — no model on it is beaten on both cost
    <em>and</em> quality by another one.</p>
    <div class="chart">{_fig_html(build_pareto_scatter(plot_df, pareto_df))}</div>
    <h3>Pareto-optimal models</h3>
    <div class="table-wrap">{pareto_table}</div>
    """


# ── Quality ───────────────────────────────────────────────────────────────────


def _quality_section(df: pd.DataFrame) -> str:
    quality_columns = [
        "model",
        "avg_quality_score",
        "quality_tier",
        "avg_quality_score_deterministic",
        "avg_quality_score_judged",
        "quality_judge_disagreement_rate",
        "quality_pass_rate",
        "quality_coverage_rate",
        "quality_dimension_coverage_rate",
        "quality_stability_score",
        "quality_collection_success_rate",
        "quality_collection_error_count",
        "quality_excluded_prompt_count",
        "quality_cer_eligible",
    ]
    quality_display = df[[c for c in quality_columns if c in df.columns]].copy()
    quality_display["quality_tier"] = df["avg_quality_score"].map(quality_tier)
    quality_display = quality_display[[c for c in quality_columns if c in quality_display.columns]]
    quality_display = quality_display.sort_values("avg_quality_score", ascending=False, na_position="last")
    if "quality_cer_eligible" in quality_display.columns:
        quality_display["quality_cer_eligible"] = quality_display["quality_cer_eligible"].map(_bool_icon)

    table = _table_html(
        quality_display,
        formats={
            "avg_quality_score": "{:.2f} / 5",
            "avg_quality_score_deterministic": "{:.2f} / 5",
            "avg_quality_score_judged": "{:.2f} / 5",
            "quality_judge_disagreement_rate": "{:.0%}",
            "quality_pass_rate": "{:.0%}",
            "quality_coverage_rate": "{:.0%}",
            "quality_dimension_coverage_rate": "{:.0%}",
            "quality_stability_score": "{:.0%}",
            "quality_collection_success_rate": "{:.0%}",
            "quality_collection_error_count": "{:.0f}",
            "quality_excluded_prompt_count": "{:.0f}",
        },
        status_column="quality_tier",
    )

    dimension_long_df = quality_dimension_long_frame(df)
    heatmap = ""
    if not dimension_long_df.empty:
        dimension_table = quality_dimension_table(df)
        numeric_columns = [column for column in dimension_table.columns if column != "model"]
        heatmap = f"""
        <div class="chart">{_fig_html(build_quality_dimension_heatmap(dimension_long_df))}</div>
        <details>
          <summary>Show the exact score per quality dimension</summary>
          <div class="table-wrap">{_table_html(dimension_table, formats=dict.fromkeys(numeric_columns, "{:.2f}"))}</div>
        </details>
        """

    return f"""
    <h2 id="quality">Quality screen</h2>
    <p class="callout"><strong>How to read this:</strong> the quality score is an average from 1 (poor)
    to 5 (excellent). Coverage tells you how much of the test was completed; stability tells you whether
    repeated tests agree; CER eligibility means there is enough evidence to compare value.</p>
    <p class="callout">These are aggregates over every generic use case. Recommendations apply each use
    case's own threshold — see the <a href="recommendations.html">use cases in detail</a>. A
    client-specific acceptance test on a golden dataset belongs in <code>gen-e2-eval</code>.</p>
    <div class="table-wrap">{table}</div>
    {heatmap}
    """


# ── Prompts & responses ───────────────────────────────────────────────────────


def _prompts_responses_section(quality_details_df: pd.DataFrame, security_probe_df: pd.DataFrame) -> str:
    quality_block = """
    <p class="callout">No prompt/response detail file for this run — available under
    <code>results/quality_details/</code> for runs merged after this feature was added.</p>
    """
    if not quality_details_df.empty:
        evidence_status = quality_details_df.get("evidence_status", pd.Series("Scored", index=quality_details_df.index))
        scored_df = quality_details_df.loc[evidence_status == "Scored"]
        anomalies_df = quality_details_df.loc[evidence_status == "Collection anomaly"]
        quality_parts: list[str] = []
        if not scored_df.empty:
            transcript_columns = [
                "model",
                "quality_dimension",
                "prompt",
                "response",
                "score",
                "judge_disagreement",
                "verification_status",
                "source",
                "reasoning",
            ]
            transcript_df = scored_df[[c for c in transcript_columns if c in scored_df.columns]].copy()
            if "judge_verdicts" in scored_df.columns and "reasoning" in transcript_df.columns:
                # The merged reasoning truncates each judge; show every score and full rationale instead.
                verdicts = scored_df["judge_verdicts"].map(format_judge_verdicts)
                transcript_df["reasoning"] = verdicts.where(verdicts.ne(""), transcript_df["reasoning"])
            quality_table = _table_html(
                transcript_df,
                formats={"score": "{:.1f} / 5", "judge_disagreement": "{:.0f}"},
                table_class="data-table wrap-table",
            )
            quality_parts.append(
                f"""
                <details>
                  <summary>Show the {len(scored_df)} scored quality evaluation(s)</summary>
                  <div class="table-wrap">{quality_table}</div>
                </details>
                """
            )
        if not anomalies_df.empty:
            diagnostic_columns = [
                "model",
                "quality_dimension",
                "prompt",
                "response",
                "error",
                "verification_status",
                "generation_id",
                "resolved_model",
                "request_sha256",
            ]
            diagnostics_table = _table_html(
                anomalies_df[[c for c in diagnostic_columns if c in anomalies_df.columns]],
                table_class="data-table wrap-table",
            )
            quality_parts.append(
                f"""
                <p class="callout"><strong>{len(anomalies_df)} collection anomaly/anomalies excluded
                from the quality score.</strong> These attempts failed technically (for example a
                timeout or an HTTP/provider error); the identifiers let you investigate the call.</p>
                <details open>
                  <summary>Show collection diagnostics</summary>
                  <div class="table-wrap">{diagnostics_table}</div>
                </details>
                """
            )
        quality_block = "".join(quality_parts)

    security_block = """
    <p class="callout">No per-probe detail in this run (<code>probe_details</code> column missing or
    empty) — re-run <code>make collect</code> then <code>make merge</code>.</p>
    """
    if not security_probe_df.empty:
        probe_columns = ["model", "category_name", "probe", "scored", "outcome", "prompt", "response", "leaked"]
        security_probe_display = security_probe_df[[c for c in probe_columns if c in security_probe_df.columns]].copy()
        for flag in ("leaked", "scored"):
            if flag in security_probe_display.columns:
                security_probe_display[flag] = security_probe_display[flag].map(_bool_icon)
        for column in ("prompt", "response"):
            if column in security_probe_display.columns:
                # Scans predating these fields default to "" (see security_probe_details_frame),
                # not NaN, so na_rep alone wouldn't render the usual "—" placeholder here.
                security_probe_display[column] = security_probe_display[column].replace("", "—")
        security_table = _table_html(security_probe_display, table_class="data-table wrap-table")
        security_block = f"""
        <details>
          <summary>Show the {len(security_probe_df)} security probe(s)</summary>
          <div class="table-wrap">{security_table}</div>
        </details>
        """

    return f"""
    <h2 id="prompts-responses">Prompts &amp; responses</h2>
    <p class="callout">Exactly what was sent to each model and what it replied — for the quality
    prompts scored in this run, and for every security probe sent.</p>
    <h3>Quality</h3>
    {quality_block}
    <h3>Security</h3>
    {security_block}
    """


# ── Security ──────────────────────────────────────────────────────────────────


def _security_section(df: pd.DataFrame) -> str:
    charts = ""
    if "rsi" in df.columns:
        rsi_columns = [c for c in ("model", "rsi", "leak_count") if c in df.columns]
        charts += f'<div class="chart">{_fig_html(build_rsi_bar(df[rsi_columns].drop_duplicates("model")))}</div>'

    security_long = security_long_frame(df)
    category_table = security_category_table(security_long)
    if not category_table.empty:
        charts += f'<div class="chart">{_fig_html(build_owasp_heatmap(security_long))}</div>'
        rate_columns = [column for column in category_table.columns if column != "model"]
        charts += f"""
        <details>
          <summary>Show the exact disclosure rate per scored category</summary>
          <div class="table-wrap">{_table_html(category_table, formats=dict.fromkeys(rate_columns, "{:.0%}"))}</div>
        </details>
        """

    summary_columns = [
        "model",
        "security_status",
        "rsi",
        "leak_count",
        "probe_error_rate",
        "zero_data_retention",
    ]
    summary = df[[c for c in summary_columns if c in df.columns]].drop_duplicates("model").copy()
    coverage = security_probe_coverage(security_probe_details_frame(df))
    if not coverage.empty:
        coverage["scored_probes_measured"] = [
            f"{int(row.measured_scored_probes)}/{int(row.scored_probes)}" for row in coverage.itertuples()
        ]
        summary = summary.merge(
            coverage[["model", "scored_probes_measured", "unmeasured_probes"]].rename(
                columns={"scored_probes_measured": "Scored probes measured", "unmeasured_probes": "Unmeasured probes"}
            ),
            on="model",
            how="left",
        )
    if "zero_data_retention" in summary.columns:
        summary["zero_data_retention"] = summary["zero_data_retention"].map(_bool_icon)
    table = _table_html(
        summary,
        formats={
            "rsi": "{:.0f}",
            "leak_count": "{:.0f}",
            "probe_error_rate": "{:.0%}",
        },
        status_column="security_status",
    )

    perimeter = ""
    if "rsi_scored_categories" in df.columns:
        scored = df["rsi_scored_categories"].dropna()
        if not scored.empty and str(scored.iloc[0]):
            perimeter = f" This run scores the RSI over <code>{escape(str(scored.iloc[0]))}</code>."

    observations = security_observations_frame(security_probe_details_frame(df))
    observations_block = ""
    if not observations.empty:
        observations_table = _table_html(
            observations.rename(
                columns={
                    "category_id": "Category",
                    "category_name": "Name",
                    "reason": "Why it is not scored",
                    "probes": "Probes",
                    "confirmed_leaks": "Confirmed leaks (all models)",
                }
            ),
            formats={"Probes": "{:.0f}", "Confirmed leaks (all models)": "{:.0f}"},
            table_class="data-table wrap-table",
        )
        observations_block = f"""
        <h3>Observations — not scored</h3>
        <p class="callout">These probes are sent and their responses kept, but the canary check cannot
        fail on them, so a missing leak proves nothing about these risks. Read the responses on the
        <a href="evidence.html">Prompts &amp; responses</a> page. A canary leak here still counts as a
        confirmed disclosure and lowers the RSI.</p>
        <div class="table-wrap">{observations_table}</div>
        """

    return f"""
    <h2 id="security">Security</h2>
    <p class="callout"><strong>How to read this:</strong> RSI is a safety score from 0 to 100, where
    higher is safer. A leak means a probe made the model disclose a secret planted in its hidden
    instructions. Probe errors are technical failures, not safe answers, so read the error rate beside
    RSI. ZDR is a provider data-retention policy, not a probe result.</p>
    <p class="callout">Internally authored probes aligned with OWASP GenAI LLM Top 10 categories — a
    generic robustness screen, not a penetration test. Only probes whose canary check can fail count in
    the RSI.{perimeter} A confirmed leak on any probe scales the RSI below the robust band.</p>
    {charts}
    <h3>Security summary by model</h3>
    <div class="table-wrap">{table}</div>
    {observations_block}
    """


# ── Cost ──────────────────────────────────────────────────────────────────────


def _cost_section(df: pd.DataFrame, profile_name: str, profile: WorkloadProfile) -> str:
    cost_df = compute_cost_columns(df, profile)

    cer_card = _kpi_card("Best cost-efficiency (CER)", "—", "")
    if "cer" in cost_df.columns and cost_df.get("quality_cer_eligible", pd.Series(dtype=bool)).fillna(False).any():
        cer_card = _leader_card("Best cost-efficiency (CER)", cost_df, "cer", "{:.4f}")

    kpi_cards = "".join(
        [
            _leader_card("Cheapest monthly TCO", cost_df, "tco_usd", "${:.2f}/mo", ascending=True),
            _leader_card("Priciest monthly TCO", cost_df, "tco_usd", "${:.2f}/mo"),
            cer_card,
        ]
    )

    cost_columns = [
        "model",
        "prompt_price_per_token",
        "completion_price_per_token",
        "cost_per_1m_tokens_usd",
        "measured_completion_tokens_per_answer",
        "tco_usd",
        "actual_cost_credits",
        "avg_quality_score",
        "cer",
        "rsi",
    ]
    cost_display = cost_df[[c for c in cost_columns if c in cost_df.columns]]
    table = _table_html(
        cost_display,
        formats={
            "prompt_price_per_token": "${:.8f}",
            "completion_price_per_token": "${:.8f}",
            "cost_per_1m_tokens_usd": "${:.2f}",
            "measured_completion_tokens_per_answer": "{:.0f}",
            "tco_usd": "${:.2f}",
            "actual_cost_credits": "${:.8f}",
            "avg_quality_score": "{:.2f} / 5",
            "cer": "{:.4f}",
            "rsi": "{:.0f}",
        },
    )

    quadrant = ""
    if "rsi" in cost_df.columns:
        quadrant = f"""
        <div class="chart">{_fig_html(build_cost_security_quadrant(cost_df))}</div>
        <p class="callout">Every model is priced on the <strong>same</strong> assumed monthly workload
        above ({profile.daily_requests} requests/day, {profile.avg_prompt_tokens} input +
        {profile.avg_completion_tokens} output tokens/request) — so a cheaper <code>tco_usd</code> here
        means cheaper for identical usage. <code>avg_completion_tokens</code> is a workload assumption,
        not each model's actual reply length, so real spend will differ from this projection.</p>
        """

    return f"""
    <h2 id="cost">Cost intelligence</h2>
    <p class="callout"><strong>How to read this:</strong> TCO is the estimated monthly bill for the
    selected usage pattern, not the cost of this benchmark. CER is quality per dollar, normalised so
    1.0 is the best eligible model in this comparison. Actual run cost is what OpenRouter reported.</p>
    <p class="meta">Workload profile: <strong>{escape(profile_name)}</strong> —
    {profile.daily_requests} requests/day · {profile.avg_prompt_tokens} input tokens/request ·
    {profile.avg_completion_tokens} output tokens/request · {profile.working_days_per_month}
    working days/month. Re-run with <code>--profile</code> for another profile.</p>
    <div class="kpi-row">{kpi_cards}</div>
    <div class="table-wrap">{table}</div>
    {quadrant}
    """


# ── Performance ───────────────────────────────────────────────────────────────


def _performance_section(df: pd.DataFrame) -> str:
    performance_columns = [
        "model",
        "actual_latency_p50_ms",
        "actual_latency_p95_ms",
        "actual_tokens_per_second",
        "actual_cost_call_count",
    ]
    performance_df = df[[c for c in performance_columns if c in df.columns]].copy()
    has_latency_data = (
        "actual_latency_p50_ms" in performance_df.columns
        and pd.to_numeric(performance_df["actual_latency_p50_ms"], errors="coerce").notna().any()
    )

    if not has_latency_data:
        return """
        <h2 id="performance">Performance</h2>
        <p class="callout"><strong>How to read this:</strong> p50 is the typical response time, p95 is a
        slower-case response time, and tokens/second is how quickly the model generated its answer. Lower
        latency and higher throughput are generally better.</p>
        <p class="callout">No per-call latency data in this run — expected for a legacy result
        predating this metric. Run a new <code>make collect</code> and <code>make merge</code>.</p>
        """

    kpi_cards = "".join(
        [
            _leader_card(
                "Fastest median response", performance_df, "actual_latency_p50_ms", "{:.0f} ms", ascending=True
            ),
            _leader_card(
                "Fastest worst-case response", performance_df, "actual_latency_p95_ms", "{:.0f} ms", ascending=True
            ),
            _leader_card("Highest throughput", performance_df, "actual_tokens_per_second", "{:.1f} tok/s"),
        ]
    )

    table = _table_html(
        performance_df.sort_values("actual_latency_p50_ms", na_position="last"),
        formats={
            "actual_latency_p50_ms": "{:.0f} ms",
            "actual_latency_p95_ms": "{:.0f} ms",
            "actual_tokens_per_second": "{:.1f}",
            "actual_cost_call_count": "{:.0f}",
        },
    )
    chart = f'<div class="chart">{_fig_html(build_latency_bar(performance_df))}</div>'

    return f"""
    <h2 id="performance">Performance</h2>
    <p class="callout"><strong>How to read this:</strong> p50 is the typical response time, p95 is a
    slower-case response time, and tokens/second is how quickly the model generated its answer. Lower
    latency and higher throughput are generally better.</p>
    <p class="callout">Response latency and throughput observed during this specific run — not a
    synthetic benchmark. Latency excludes time spent queueing behind <code>MAX_CONCURRENT_REQUESTS</code>
    and retry back-off waits, so it reflects the model/provider's actual response time.</p>
    <div class="kpi-row">{kpi_cards}</div>
    <div class="table-wrap">{table}</div>
    {chart}
    """


def _raw_data_section(df: pd.DataFrame) -> str:
    # probe_details holds raw model completions from injection probes — never trust it as HTML.
    safe_columns = [c for c in df.columns if c != "probe_details"]
    table = _table_html(df[safe_columns])
    return f"""
    <h2 id="raw-data">Raw data</h2>
    <details>
      <summary>
        Show all columns ({len(safe_columns)} columns; probe_details omitted, see the source CSV)
      </summary>
      <div class="table-wrap">{table}</div>
    </details>
    """


def _glossary_section() -> str:
    return f'<h2 id="glossary">Glossary</h2>{_GLOSSARY_HTML}'


# ── Page assembly ─────────────────────────────────────────────────────────────


def _warnings_html(warnings: list[str]) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{escape(warning)}</li>" for warning in warnings)
    return (
        '<div class="warning" role="note"><strong>Not reference-grade evidence — do not base a '
        f"recommendation on this run alone.</strong><ul>{items}</ul></div>"
    )


def _notices_html(notices: list[str]) -> str:
    return "".join(f'<p class="notice" role="note">{escape(notice)}</p>' for notice in notices)


def build_page(
    df: pd.DataFrame,
    profile_name: str,
    profile: WorkloadProfile,
    source_label: str,
    page_title: str,
    active_page: str,
    page_body: str,
    href_prefix: str = "",
    provenance: dict[str, str] | None = None,
    warnings: list[str] | None = None,
    notices: list[str] | None = None,
) -> str:
    """Assemble one standalone page of the static report."""
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    provenance_items = " · ".join(
        f"{escape(label)}: <strong>{escape(value)}</strong>" for label, value in (provenance or {}).items()
    )
    provenance_html = (
        f'<p class="meta">Compare runs only when all of these match — {provenance_items}</p>'
        if provenance_items
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Model Compass — {escape(page_title)}</title>
<style>{_CSS}</style>
<script src="{href_prefix}{_PLOTLY_FILENAME}"></script>
</head>
<body>
<h1>Model Compass report</h1>
<p class="subtitle">Technical recommendation of OpenRouter models by generic use case. The final choice
for a specific tender remains human.</p>
<p class="meta">Source: {escape(source_label)} — generated on {generated_at}</p>
{provenance_html}
{_warnings_html(warnings or [])}
{_notices_html(notices or [])}
{_navigation_html(active_page, href_prefix)}
{page_body}
</body>
</html>"""


def build_reports(
    df: pd.DataFrame,
    profile_name: str,
    profile: WorkloadProfile,
    source_label: str,
    quality_details_df: pd.DataFrame | None = None,
    recommendations_df: pd.DataFrame | None = None,
    source_paths: list[tuple[str, Path]] | None = None,
    bundle_dir: Path | None = None,
) -> dict[str, str]:
    """Build the named pages that form one static report bundle."""
    security_probe_df = security_probe_details_frame(df)
    quality_details = quality_details_df if quality_details_df is not None else pd.DataFrame()
    recommendations = recommendations_df if recommendations_df is not None else pd.DataFrame()
    provenance = run_provenance(df, recommendations)
    warnings = run_warnings(df, source_label)
    notices = run_notices(df)
    sources = _sources_html(source_paths or [], bundle_dir)
    pages = {
        "index.html": (
            "Decision summary",
            "summary",
            _summary_section(recommendations, sources, disputed_prompt_ids(quality_details)),
        ),
        "recommendations.html": ("Use cases in detail", "recommendations", _recommendations_section(recommendations)),
        "overview.html": ("Quality × cost", "overview", _overview_section(df)),
        "quality.html": ("Quality", "quality", _quality_section(df)),
        "security.html": ("Security", "security", _security_section(df)),
        "cost.html": ("Cost", "cost", _cost_section(df, profile_name, profile)),
        "performance.html": ("Performance", "performance", _performance_section(df)),
        "evidence.html": (
            "Prompts & responses",
            "evidence",
            f"{_prompts_responses_section(quality_details, security_probe_df)}{_raw_data_section(df)}",
        ),
        "glossary.html": ("Glossary", "glossary", _glossary_section()),
    }
    return {
        filename: build_page(
            df,
            profile_name,
            profile,
            source_label,
            page_title,
            active_page,
            page_body,
            provenance=provenance,
            warnings=warnings,
            notices=notices,
        )
        for filename, (page_title, active_page, page_body) in pages.items()
    }


def _source_paths(results_path: Path) -> list[tuple[str, Path]]:
    """Return the existing artifacts of a run, in reading order."""
    stem = results_path.stem
    candidates = [
        ("Benchmark matrix (CSV)", results_path),
        ("Recommendations (CSV)", results_path.parent / "recommendations" / f"{stem}_recommendations.csv"),
        ("Quality details (CSV)", results_path.parent / "quality_details" / f"{stem}_quality_details.csv"),
        ("Call costs (CSV)", results_path.parent / "call_costs" / f"{stem}_call_costs.csv"),
    ]
    return [(label, path) for label, path in candidates if path.exists()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the static Model Compass HTML report.")
    parser.add_argument("--results", type=Path, default=None, help="Benchmark CSV (default: latest in results/)")
    parser.add_argument(
        "--output", type=Path, default=None, help="Output HTML path (default: results/dashboard_<ts>.html)"
    )
    parser.add_argument("--profile", default="enterprise_qa", help="Workload profile for the Cost section")
    args = parser.parse_args(argv)

    results_path = args.results or _latest_results_csv()
    if results_path is None or not results_path.exists():
        print("No benchmark CSV found. Pass --results or run `make collect` + `make merge` first.", file=sys.stderr)
        return 1

    profile = BUILTIN_WORKLOAD_PROFILES.get(args.profile)
    if profile is None:
        print(f"Unknown profile '{args.profile}'. Available: {list(BUILTIN_WORKLOAD_PROFILES)}", file=sys.stderr)
        return 1

    df = pd.read_csv(results_path)
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        print(f"Missing required columns in {results_path}: {sorted(missing)}", file=sys.stderr)
        return 1
    df = enrich_benchmark(df)

    output_path = args.output
    if output_path is None:
        suffix = results_path.stem.removeprefix("benchmark_")
        output_path = _RESULTS_DIR / f"dashboard_{suffix}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    quality_details_df = load_quality_details(results_path)
    recommendations_df = load_recommendations(results_path)
    source_paths = _source_paths(results_path)
    bundle_dir = output_path.with_suffix("")
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / _PLOTLY_FILENAME).write_text(get_plotlyjs(), encoding="utf-8")
    reports = build_reports(
        df,
        args.profile,
        profile,
        results_path.name,
        quality_details_df,
        recommendations_df,
        source_paths=source_paths,
        bundle_dir=bundle_dir,
    )
    for filename, html_doc in reports.items():
        (bundle_dir / filename).write_text(html_doc, encoding="utf-8")

    # Keep the requested output path as the opening page, while linked pages and
    # the Plotly bundle live in a sibling directory that can be copied as a whole.
    output_path.write_text(
        build_page(
            df,
            args.profile,
            profile,
            results_path.name,
            "Decision summary",
            "summary",
            _summary_section(
                recommendations_df,
                _sources_html(source_paths, output_path.parent),
                disputed_prompt_ids(quality_details_df),
            ),
            href_prefix=f"{bundle_dir.name}/",
            provenance=run_provenance(df, recommendations_df),
            warnings=run_warnings(df, results_path.name),
            notices=run_notices(df),
        ),
        encoding="utf-8",
    )
    print(f"Wrote {output_path} and navigable pages in {bundle_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
