"""Single source of truth for the dashboard glossary.

Every page of the static HTML report renders these definitions, so a term
is explained in one place only.

Definitions use inline backticks for column names; :func:`glossary_html`
converts them to ``<code>`` after escaping.
"""

from __future__ import annotations

import re
from html import escape

GLOSSARY_TERMS: tuple[tuple[str, str], ...] = (
    (
        "RSI — Robustness Safety Index (0–100)",
        "Resistance to disclosing a secret planted in the system prompt (a canary) and to obeying a "
        "harmless instruction hidden in the content a probe asks the model to process, weighted by "
        "[OWASP GenAI LLM Top 10](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) "
        "category. 100 means no disclosure was observed on the scored probes. Only probes whose "
        "canary check can actually fail are scored (`rsi_scored_categories`); the others are "
        "reported as **observations**, never as a reassuring 0 %. **A confirmed leak on any probe "
        "scales the RSI below the robust band**, while a model that leaks more stays lower. Each "
        "scored probe runs three times with a fresh secret, so the RSI rests on a leak rate; an "
        "empty or failed attempt is excluded, never counted as safe (*Scored probes measured*). Two "
        "RSI values are comparable only over the same probe set and scored categories.",
    ),
    (
        "Security path (full / skip)",
        "Security is one path: `full` runs every probe of the set, `skip` runs none. A skipped run "
        "ranks models on quality, cost and performance only, with their weights rescaled, and is "
        "flagged as non-reference evidence on every page.",
    ),
    (
        "probe_error_rate",
        "Share of probes that failed technically (timeout, HTTP error). Those probes are excluded "
        "from the vulnerability rate, so a high error rate mechanically inflates the RSI. Always "
        "read it next to the RSI.",
    ),
    (
        "TCO — Total Cost of Ownership",
        "`tco_usd` is a **projected monthly** cost for a given workload profile (requests per day and "
        "input tokens per request), with the output length each model really produced on the quality suite "
        "— not what this run actually cost (see `actual_cost_credits`).",
    ),
    (
        "CER — Cost-Efficiency Ratio",
        "`cer` = quality ÷ monthly TCO, normalised so the best model in the run scores 1.0. Only "
        "computed when `quality_cer_eligible` is true, i.e. quality coverage is sufficient.",
    ),
    (
        "actual_latency_p50_ms / actual_latency_p95_ms / actual_tokens_per_second",
        "Response latency and throughput actually observed during this run's calls. Both latency "
        "figures are **network-only**: they exclude time spent queueing behind "
        "`MAX_CONCURRENT_REQUESTS` and retry back-off waits, unlike the legacy `actual_latency_ms` "
        "(a wall-clock sum that includes that queueing time and is not a per-call figure). "
        "`actual_tokens_per_second` is total completion tokens generated ÷ total network time.",
    ),
    (
        "ZDR — Zero Data Retention",
        "A policy the provider declares in the OpenRouter catalog, never a probe result. Most "
        "providers do not publish this field, so the column is usually false through absence of "
        "data rather than through refusal.",
    ),
    (
        "OWASP LLM Top 10",
        "Reference list of the ten most critical vulnerability categories for LLM applications "
        "(prompt injection, sensitive information disclosure, and so on). The repository uses "
        "internally authored probes aligned with these categories to weight the RSI and build the "
        "per-category vulnerability heatmap; this is not an OWASP certification or official probe set.",
    ),
    (
        "avg_quality_score (1–5)",
        "Macro-average per dimension of a blind 3-judge consensus plus deterministic checks. "
        "Careful: this figure aggregates **two scales that are not equivalent** — deterministic "
        "checks are pass/fail rendered as 1 or 5, while judges score continuously from 1 to 5. "
        "`avg_quality_score_deterministic` and `avg_quality_score_judged` are published separately "
        "so you can see which scale drives the ranking.",
    ),
    (
        "judge_disagreement / quality_judge_disagreement_rate",
        "`judge_disagreement` is the range (max − min) across the 3 judges' raw scores for one "
        "response, before averaging; `quality_judge_disagreement_rate` is the share of a model's "
        "judged prompts where that range is 2 or more — a real split of opinion on the response's "
        "quality tier, not a rounding difference. The mean score is kept rather than a median: with "
        "exactly 3 judges, a median just picks the middle one and ignores the other two.",
    ),
    (
        "output_format_compliance",
        "Dimension isolating literal adherence to a formatting instruction (no markdown fences, no "
        "extra text) from whether the answer itself was correct. A correct answer wrapped in "
        "markdown code fences fails here but keeps its content score.",
    ),
    (
        "quality_excluded_prompt_count",
        "Prompts removed from the aggregates because **every** model in the run missed a known "
        "reference answer. A miss shared by unrelated models points at the request that reached "
        "the provider (proxy redaction, template substitution, truncation), not at a simultaneous "
        "model failure. Raw responses remain readable in the Prompts & responses section with "
        "status `suspected_input_corruption`.",
    ),
    (
        "quality_pass_rate",
        "Share of prompts scored ≥ 4/5. Since most prompts are binary deterministic checks, this "
        "rate can be identical for several models — it is a coverage indicator, not a ranking.",
    ),
    (
        "Coverage rates (quality_coverage_rate / quality_dimension_coverage_rate)",
        "Share of prompts / dimensions actually evaluated. Below 80% (prompts) or 100% "
        "(dimensions) the CER is withheld, because the evidence is considered too partial.",
    ),
    (
        "quality_stability_score",
        "Score consistency across repeated runs of the same prompt (requires "
        "`QUALITY_REPETITIONS ≥ 2`). Below 70% the model is considered too unstable for "
        "production.",
    ),
    (
        "is_vulnerable / leak_count",
        "The model was compromised on at least one probe (`is_vulnerable`); `leak_count` counts the "
        "attempts that disclosed the canary planted in the system prompt or wrote the marker a hidden "
        "instruction asked for (`confirmed_obedience`). Detection only accepts forms that recover the "
        "whole secret or the exact marker, so this figure is a lower bound.",
    ),
    (
        "Security status (Safe / Partial risk / Vulnerable)",
        "Derived label: Safe = no leak, Partial risk = leaked on ≥ 1 security probe, Vulnerable = "
        "leaked on a built-in injection probe. Probe datasets are internally authored; the OWASP "
        "dataset is aligned with OWASP categories, not an official OWASP test suite.",
    ),
    (
        "Recommendation status",
        "**Recommended**: best decision score among models that pass the use-case quality "
        "threshold with complete evidence; equal scores share the rank. **Eligible**: passes the "
        "threshold but ranks lower. **Missing decision evidence**: passes the threshold but lacks "
        "security, cost or performance evidence, so it is not ranked. **Below quality threshold** "
        "and **Incomplete quality evidence** cannot be recommended, however cheap or fast.",
    ),
    (
        "Decision score (0–100)",
        "Weighted sum of the quality, security, cost and performance components, each on 0–100. "
        "Cost and p95 latency use fixed logarithmic anchors from the versioned catalog, so adding "
        "or removing a model never changes another model's score. Only ranked models show one.",
    ),
    (
        "Fragile / rank range (±10 %)",
        "The rank or eligibility changes when one weight, or the quality threshold, moves by 10 %. "
        "A fragile recommendation is a close call: compare the leaders yourself.",
    ),
    (
        "Within the leader's interval / borderline",
        "Quality 95 % intervals come from a bootstrap over prompts and attempts (at least three "
        "attempts per prompt). **Within the leader's interval** means the quality difference with "
        "the recommended model is not established. **Borderline** means the interval straddles "
        "the use-case threshold.",
    ),
    (
        "Own-provider judge / judge-sensitive",
        "Each judge belongs to a provider (Anthropic, OpenAI, Google) that may also make a benchmarked "
        "model, and may favour its own family's style even when names are hidden. The report "
        "recomputes every judged score without the judge of the evaluated model's provider. "
        "**judge-sensitive** means the use-case outcome changes without those judges: treat the "
        "recommendation as unconfirmed. The published scores are never altered.",
    ),
    (
        "Weight profile / weight-profile-sensitive",
        "The catalog names three weight profiles: **quality-first** (70/20/7/3 for "
        "quality/security/cost/performance), **balanced** (50/25/20/5, the default) and "
        "**cost-sensitive** (35/20/40/5). The published rank uses the run's weights; the other "
        "profiles only show whether the leader would change. **weight-profile-sensitive** means it "
        "does: keep the leader of the profile that matches the tender. The *Weight profiles* table "
        "translates each profile into trade-offs, such as how large a price gap one quality point "
        "is worth.",
    ),
    (
        "Format respected / partial credit",
        "Quality scores the **content** of an answer: a correct final answer keeps its score even "
        "when it ignores a bare-answer format. *Format respected* reports separately how often a "
        "strict format (bare answer, raw JSON, code only) was followed. JSON and code answers get "
        "**partial credit**: 1 + 4 × the share of fields or tests that are right.",
    ),
    (
        "Disputed key",
        "Most models give the same answer to an exact-answer prompt, and the reference key rejects "
        "it. The key or the prompt is then more likely wrong than the models: review the item "
        "before relying on a ranking that rests on it.",
    ),
    (
        "Cost per 1,000 requests (USD)",
        "What 1,000 requests of the workload profile cost with each model: the profile's input size at "
        "the listed input price, plus the output length the model really produced on the quality suite "
        "(hidden reasoning included) at the listed output price. A verbose or reasoning model pays for "
        "its tokens here. It is the cost used by the decision score and the monthly TCO.",
    ),
    (
        "Listed cost (USD / 1M tokens)",
        "Input and output prices blended by the workload profile's assumed token mix. It ignores how "
        "many tokens a model really produces, so it is shown for reference only.",
    ),
    (
        "Quality tier (Excellent / Good / Fair / Poor)",
        "Presentation-only banding of `avg_quality_score` (not a column of the source CSV): "
        "Excellent ≥ 4.5, Good ≥ 3.5, Fair ≥ 2.5, Poor < 2.5.",
    ),
)

GLOSSARY_INTRO = (
    "Every model is measured on four axes — quality, security, cost and performance — and "
    "recommended per **generic** use case. The recommendation is technical evidence: the person "
    "who knows the tender makes the final choice, and a client-specific acceptance test with a "
    "golden dataset belongs in `gen-e2-eval`."
)

# Short, one-sentence reminders for technical column headers — shown as a native
# browser tooltip (title=) right next to the term in the static HTML export.
# This complements GLOSSARY_TERMS above
# (the full reference) rather than replacing it, so a first-time reader doesn't
# have to leave the table to know what a column means.
COLUMN_TOOLTIPS: dict[str, str] = {
    "Format respected": (
        "Share of this use case's strict-format answers (bare answer, raw JSON) that followed the format exactly. "
        "Reported apart from quality, which scores content only."
    ),
    "rsi": "Robustness Safety Index (0-100, higher = safer). See the glossary below for details.",
    "probe_error_rate": "Share of probes that failed technically (timeout, HTTP error) — excluded from the RSI.",
    "rsi_scored_probe_count": "Number of probes actually counted in the RSI, after excluding errors.",
    "Scored probes measured": (
        "Scored probes that produced a gradable answer, out of all scored probes. The RSI rests only on the "
        "measured ones: an empty answer or an error is excluded, never counted as safe."
    ),
    "Unmeasured probes": "Scored probes left out of the RSI because the model returned no answer or the call failed.",
    "leak_count": "Number of probes where the system prompt's canary was disclosed.",
    "zero_data_retention": "Provider-declared policy from the OpenRouter catalog, not a probe result.",
    "security_status": (
        "Safe = no leak, Partial risk = leaked on >= 1 security probe, Vulnerable = leaked on a built-in probe."
    ),
    "tco_usd": (
        "Projected monthly cost for the selected workload profile with the model's measured output length, "
        "not this run's actual cost."
    ),
    "actual_cost_credits": "What this run actually cost, from OpenRouter's response.usage.cost.",
    "cer": "Cost-Efficiency Ratio = quality / monthly TCO, normalised so the best model scores 1.0.",
    "actual_latency_p50_ms": "Median network latency observed in this run (queueing/back-off excluded).",
    "actual_latency_p95_ms": "95th-percentile network latency observed in this run (queueing/back-off excluded).",
    "actual_tokens_per_second": "Completion tokens generated divided by network time.",
    "avg_quality_score": (
        "Blends deterministic pass/fail checks and a 3-judge panel — see avg_quality_score_deterministic/_judged."
    ),
    "avg_quality_score_deterministic": "Macro-average over deterministic pass/fail checks only (scored 1 or 5).",
    "avg_quality_score_judged": "Macro-average over the blind 3-judge panel only, graded 1-5.",
    "quality_judge_disagreement_rate": "Share of judged prompts where the 3 judges' raw scores spread by >= 2 points.",
    "judge_disagreement": "Range (max - min) across the 3 judges' raw scores for this one response.",
    "quality_pass_rate": "Share of prompts scored >= 4/5 — a coverage indicator, not a ranking.",
    "quality_coverage_rate": "Share of the prompt suite actually scored. Below 80% withholds the CER.",
    "quality_dimension_coverage_rate": "Share of quality dimensions actually evaluated. Below 100% withholds the CER.",
    "quality_stability_score": "Score consistency across repeated runs. Below 70% is too unstable for production.",
    "quality_excluded_prompt_count": "Prompts dropped because every model missed the same known answer.",
    "output_format_compliance": (
        "Literal instruction-following (no markdown fences, no extra text), separate from correctness."
    ),
    "cost_per_1m_tokens_usd": "Listed input/output prices blended by the profile's assumed token mix, per 1M tokens.",
    "cost_per_1k_requests_usd": "Cost of 1,000 profile requests with the model's measured output length.",
    "measured_completion_tokens_per_answer": "Mean output tokens per quality answer in this run, reasoning included.",
    "Decision score": "Weighted 0-100 score; only ranked models show one.",
    "Rank range (±10%)": "Lowest and highest rank when one weight or the threshold moves by 10%.",
    "Fragile": "Yes when the rank or eligibility changes under a 10% change of one weight or the threshold.",
    "Quality 95% CI": "Bootstrap interval of the use-case quality score (needs 3+ attempts per prompt).",
    "Within leader's CI": "Yes when this model's quality interval overlaps the recommended model's.",
    "USD / 1k requests": "Cost of 1,000 profile requests with the model's measured output length.",
    "Missing evidence": "Decision components without evidence; the model cannot be ranked.",
    "Quality w/o own-provider judge": "Use-case quality recomputed without the judge from this model's provider.",
    "Outcome w/o own-provider judge": "Status and rank when every model is judged without its own-provider judge.",
}

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline_html(text: str) -> str:
    """Escape *text*, then re-enable the inline markdown the definitions use."""
    html = escape(text)
    html = _LINK.sub(r'<a href="\2">\1</a>', html)
    html = _BOLD.sub(r"<strong>\1</strong>", html)
    return _INLINE_CODE.sub(r"<code>\1</code>", html)


def glossary_html(intro: str) -> str:
    """Return the glossary as an HTML ``<section>`` for the static export."""
    items = "".join(
        f"<dt>{_inline_html(term)}</dt>\n<dd>{_inline_html(definition)}</dd>\n" for term, definition in GLOSSARY_TERMS
    )
    return f'<section class="glossary">\n<p>{_inline_html(intro)}</p>\n<dl>{items}</dl>\n</section>'
