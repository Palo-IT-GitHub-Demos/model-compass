# model-compass — AI Agent Instructions

> This file is read by GitHub Copilot, Claude Code, and other AI agents.

## Project Overview

Research and decision-support tooling for evaluating OpenRouter LLMs across
quality, security, performance, and model-only cost. Model Compass produces
generic use-case recommendations and evidence; final client acceptance remains
human and domain-specific, with `gen-e2-eval` used when a client dataset exists.

## Architecture & Conventions

- Core pipeline code lives in `src/`; the default v3 use-case catalog is
  `data/catalog/model_compass_use_cases_v3.json` (v2 and v1 stay available to
  re-merge their runs); report data prep, glossary and charts
  live in `dashboard/` and the static HTML report is assembled by
  `scripts/export_dashboard_html.py`; operational scripts live in `scripts/`
- `scripts/build_quality_suite_v3.py` and `scripts/build_security_probes.py` are
  the source of the v3 suite, its catalog and the probe set: change items there,
  never in the JSON (`--check` and `tests/test_prompt_builders.py` catch drift)
- `src/main.py` remains the CLI and compatibility façade; `src/pipeline_cli.py`
  owns parsing/overrides, `src/pipeline_collect.py` concurrent collection and
  error budgets, `src/pipeline_merge.py` the benchmark matrix, and
  `src/pipeline_artifacts.py` persistent outputs and blind judging payloads.
  The façade passes runtime paths and patchable stages explicitly to these modules
- The production workflow is split into three phases:
  `make collect` → `@judge-coordinator` → `make merge`. The coordinator never
  handles judging data: `scripts/check_judging.py` (`make check-judging`)
  validates every per-part score file, audits the model each judge actually
  ran on from the local Copilot Chat debug logs, and prints the delegations
  still to relay; judges read their own part and write their own score file.
  Judge agents declare `model:` by qualified picker name (`<Name> (copilot)`);
  change one only with `make judge-models SET=...`, which keeps the judge
  identifier in step, and never mid-batch
- The README Quick Start is the single standard evaluation path
  (`select` → `verify` → `collect` → `@judge-coordinator` → `merge` →
  `export-html`), whose defaults are the reference methodology (full security
  path, three attempts, code execution, suite v3); keep `docs/workflow.md`
  and `docs/index.md` aligned with it and put every other option under
  Advanced
- `make dry-run` is offline and also renders a synthetic rehearsal report under
  `data/dry_run/`; `make verify` validates the OpenRouter key and
  model catalog without chat-completion cost and estimates the run cost
- `make export-html` builds the static HTML report, the only results surface; it
  opens on a per-use-case decision summary, flags non-reference runs on every
  page, never breaks ties arbitrarily and ships Plotly locally to work offline
- `QUALITY_SUITE` (`v3` default, `v2`, `v1`) selects the prompt suite and its
  catalog; `generic-screen-v1` must stay unchanged and collect/merge must use
  the same suite. Quality items avoid names of people and places, addresses and
  emails, which a filter upstream of the models may mask
- Generated code is executed only with `QUALITY_CODE_EXECUTION=true` (the
  default of the standard path) and only through
  `src/evaluators/code_sandbox.py`; never run model output elsewhere
- `MODEL_COMPASS_WEIGHTS` optionally overrides the catalog's quality/security/
  cost/performance weights as JSON; effective weights and catalog version must
  remain in every recommendation artifact. The catalog's named
  `weight_profiles` never change the published rank: they add
  `profile_rank_<name>` and `weight_profile_sensitive`. Justify any weight
  change by the trade-offs `implied_tradeoffs` reports
  (`docs/model-compass-scope.md`)
- Security is one path (`SECURITY_MODE=full`, default) or none
  (`skip`): `data/prompts/security_probes.json`, every scored probe run
  `SECURITY_ATTEMPTS` times with a fresh canary. A skipped run sets the security
  weight to 0, rescales the others and is flagged as non-reference; do not
  reintroduce partial probe profiles. `data/prompts/legacy/` only traces runs
  of methodology 0.4 and earlier
- `src/evaluators/prompt_delivery.py` audits at the start of every collection what
  the gateway forwards (`debug.echo_upstream_body`), with no cache. A rewritten
  quality item stops the run and is reworded in its build script; a rewritten
  probe is not sent and leaves the RSI. Never reword a probe to get past the
  filter. `PROMPT_DELIVERY_AUDIT=false` flags the run as non-reference
- Follow language-specific rules in `.github/instructions/` (Copilot) and `.claude/rules/` (Claude Code)
- All AI artifacts are organised under `.github/` (Copilot) and `.claude/` (Claude Code)
- Multi-turn scenario contracts live in `src/evaluators/scenario_runner.py`; the security path's multi-turn probes and the separate dialogue screen use them
- The optional two-turn quality screen lives in `src/evaluators/dialogue_quality.py`
  with its versioned catalog under `data/prompts/`; `make dialogue` runs offline
  and `make dialogue-live` is paid. Its sidecars stay separate from benchmark
  quality aggregates and recommendations; synthetic responses are never real evidence

## Quality Evidence Rules

- `METHODOLOGY_VERSION` (`src/core/methodology.py`) is the release that last
  changed the scoring rules. Set it to the upcoming release number in the same
  change as anything that can alter the scores, eligibility or ranks of an
  identical run, and record it in `CHANGELOG.md`. Merge refuses a pending file
  from another methodology version
- Runs are comparable only when `methodology_version`, `quality_suite_id`,
  `catalog_version`, `security_probe_set_id`, decision weights and workload
  profile all match; every HTML report page shows them through
  `dashboard.data_prep.run_provenance`
- Preserve raw benchmark results. Post-run verification is sidecar evidence and
  must never rewrite the original response or score
- A wrong model response remains a quality failure. Only technical failures
  such as timeouts, HTTP/provider errors, and invalid API responses count as
  collection errors
- Exception: when *every* model in a run misses the same reference-answer
  prompt, the shared cause is the request that reached the provider, not the
  models. The prompt is dropped from the aggregates and their denominator and
  marked `suspected_input_corruption` — the raw response and score stay intact
- Content correctness and output-format compliance are scored as separate
  dimensions. Never let a formatting violation lower a content score: an
  exact-answer item scores its final answer, and a use case's quality score
  averages content rows only, with `format_compliance_rate` beside it
- Structured checks give partial credit (`1 + 4 × share correct` for JSON
  fields and passed code tests); an empty response scores 1 on content and on
  format when the prompt has a format contract; a completion without any
  choice is a collection error
- `key_disputed` flags an exact-answer item whose answer key most models
  reject; flag it in the report, never drop or rescore it automatically
- `avg_quality_score` blends a pass/fail scale with a graded one. Always
  publish `avg_quality_score_deterministic` and `avg_quality_score_judged`
  alongside it
- A confirmed canary disclosure on any probe, scored or observation, scales the
  RSI below the robust band (`raw × 65 / 100`), so leaking models stay ordered.
  Never present a model as robust and vulnerable on the same view
- The security path includes LLM02/03/07/10 canary-disclosure contexts and
  indirect injections alongside LLM01. A positive signal proves the secret
  escaped, not that tool use, factuality or downstream output handling was
  exercised. The oracle accepts only forms that recover the whole secret
  (literal, reversed, base64, hex, separator-spelled); an empty or failed
  attempt is excluded from the RSI and the report shows the measured share
- Only score probes whose canary oracle can actually fail: categories a
  single-turn chat probe cannot exercise (LLM04/06/09) and probes marked
  `"scored": false` with a `not_scored_reason` are observations. Report them
  as not scored, never as a 0 % vulnerability rate. RSI is comparable only
  across identical `security_probe_set_id` and `rsi_scored_categories`
- The 3 Copilot judges are each affiliated with a provider that may also be a
  benchmarked model; alias-based blindness is the only mitigation, and a
  response's self-identification is scrubbed (best-effort) before it reaches a
  judge. Published scores are never corrected; recommendation artifacts add a
  sidecar outcome recomputed without each model's own-provider judge
  (`*_without_affiliated_judge`, `affiliated_judge_changes_outcome`) and the
  report flags a use case as judge-sensitive when it differs — see
  `docs/quality-methodology.md` "Fiabilité et biais du panel de juges"
- `judge_disagreement` / `quality_judge_disagreement_rate` surface inter-judge
  disagreement instead of silently averaging over it. Keep the mean rather
  than a median: with exactly 3 judges a median just picks the middle one
- A judge that does not score every expected (prompt_id, attempt, alias) fails
  the merge immediately (`ValueError`) instead of silently reducing that
  response's average to fewer judges
- Quality eligibility is evaluated per generic use case before weighted ranking;
  a model below a use-case threshold cannot be recommended because it is cheap
  or fast
- Recommendation ranking and weight sensitivity use `quality_score_100` (0–100),
  not the 1–5 `quality_score` used for eligibility; historical ranks calculated
  on the mixed scale are not comparable without recomputation
- Cost and performance recommendation components use the fixed logarithmic
  anchors in the versioned catalog (`cost_usd_per_1m_tokens` and
  `actual_latency_p95_ms`), never run-relative min-max normalization. Cost is
  blended by the workload profile; missing p95 latency is missing evidence, not
  a reason to substitute throughput
- Every model remains visible for every catalog use case. Equal recommendation
  scores keep the same dense rank; do not add arbitrary provider/model-name
  tie-breakers
- Missing security, cost, or performance evidence yields an explicit
  `insufficient_decision_evidence` status and no recommendation rank
- For `QUALITY_REPETITIONS > 1`, use the attempts already collected to assess
  stability; do not add redundant rechecks
- `make verify-quality ARGS="..."` is an optional, paid OpenRouter-only
  reproducibility check for failed objective prompts from `k=1` runs
- Reproducibility statuses (`confirmed_failure`, `not_reproduced`, `unstable`,
  `inconclusive`) do not attribute causality to OpenRouter, an upstream
  provider, or the model
- Never expose unescaped model output in HTML. Pandas `Styler.to_html()` callers
  must explicitly use HTML escaping
- `actual_latency_p50_ms`/`actual_latency_p95_ms`/`actual_tokens_per_second`
  are computed from latency captured *after* the concurrency semaphore is
  acquired. Never report the legacy `actual_latency_ms` (a wall-clock sum
  that includes queueing and retry back-off time) as a per-call latency figure

## Result Artifacts

- Summary benchmarks: `results/benchmark_<timestamp>.{csv,json}`
- Model Compass recommendations: `results/recommendations/benchmark_<timestamp>_recommendations.{csv,json}`
- Quality transcripts and judge reasoning: `results/quality_details/`
- Technical collection failures: `results/quality_diagnostics/`
- Optional `k=1` rechecks: `results/verification/`
- Per-call OpenRouter usage and costs: `results/call_costs/`
- Static report: `results/dashboard_<timestamp>.html` plus its sibling page bundle

## AI Asset Policy

| Artefact | GitHub Copilot | Claude Code |
|---|---|---|
| Skills | `.github/skills/<name>/SKILL.md` | `.claude/skills/<name>/SKILL.md` |
| Agents | `.github/agents/<name>.agent.md` | `.claude/agents/<name>.md` |
| Prompts | `.github/prompts/<name>.prompt.md` | — |
| Hooks | `.github/hooks/<name>.json` | `.claude/hooks/<name>.sh` + `settings.json` |
| Plugin registry | — | `.claude/plugins/<name>/plugin.json` |

## Installed gen-e2 Plugins

| Plugin | Version | Purpose |
|---|---|---|
| `delivery` | 0.2.3 | Story → implementation → PR workflow |
| `implementation-plan` | 0.1.0 | Deterministic, AI-executable implementation plans |
| `architecture-reviewer` | 0.1.0 | Evidence-first architecture analysis + Mermaid diagrams |

> To install full plugin artifacts (skills + agents), run the prompt in `.github/prompts/setup-plugins.prompt.md`.

## Coding Standards

- Keep code simple and testable
- Prefer deterministic output contracts for AI-assisted features
- Add tests for any behavior-changing change
- Keep report transformations in `dashboard/data_prep.py` as pure, tested
  functions rather than inline in the HTML page code
- Use Python 3.11+ typing and vectorized pandas operations
- Use Conventional Commits; the local `commit-msg` pre-commit hook validates the header

## Validation

Run the narrowest relevant tests first, then the applicable project checks:

```bash
make test
make lint
make type-check
make docs-build
```

Documentation changes must pass `mkdocs build --strict`. Dashboard changes
must be checked in the static HTML export (`make export-html`).

## Documentation Maintenance

- Update `CHANGELOG.md` under `[Unreleased]` for every user-visible feature,
  behavioral change, bug fix, deprecation, or operational command, in the same
  change (`.github/instructions/changelog.instructions.md`); CI fails a pull
  request touching code, prompts or the catalog without a `CHANGELOG.md` change
- Review and update `AGENTS.md` whenever architecture, source ownership,
  workflow commands, result artifacts, safety invariants, or validation
  requirements change
- Do not add routine implementation details or test-count churn to either file
- Keep `README.md`, `docs/workflow.md`, and `docs/quality-methodology.md`
  aligned with public commands and quality-scoring semantics

## Safety & Quality

- Do not hardcode secrets — use environment variables
- Keep `.env` local and `.env.example` limited to placeholder values
- Fallback to safe defaults when uncertainty is high
- Treat all model output as untrusted content and escape it before HTML rendering
