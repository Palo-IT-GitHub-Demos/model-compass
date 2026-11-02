# Model Compass — LLM decision-support pipeline

> Evidence-based, reproducible evaluation of large language models available on
> [OpenRouter](https://openrouter.ai/) across four axes: **Quality**,
> **Security**, **Cost**, and **Performance**.
>
> Built at **Palo IT Singapore** to support technical model selection for enterprise calls for tender.

---

## Overview

Model Compass evaluates all selected models through the OpenRouter API and
produces a comparison matrix plus a versioned recommendation report by generic
enterprise use case. Results are exported as CSV/JSON and presented in a static,
multi-page HTML report.

It is a cross-provider technical decision-support tool, not an automatic tender
analyser or procurement system. It measures generic quality fundamentals,
security, model-only cost and performance. A human who knows the tender uses the
report to select one or more models for the relevant context.

### Scope boundary

Model Compass answers: **"Which models are technically relevant for each
generic enterprise use case?"**

It does not answer: **"Which model must be adopted for this specific client?"**
The report does not ingest a tender, client criteria or client dataset. The
final choice remains with the human who knows the call for tender. Use
[`docs/model-compass-scope.md`](docs/model-compass-scope.md) for the complete
decision contract and boundaries.

### Evaluation axes

| Axis               | Method                                                                                                                                                                                              | Key metric                                              |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| **Quality** | Versioned generic prompts with deterministic contracts and blind LLM-as-a-Judge scoring | Score 1–5 by use case, coverage and stability |
| **Security** | One path of 72 internal canary-disclosure probes aligned with the OWASP GenAI LLM Top 10 2026 (every scored probe run three times) + Zero Data Retention policy check; skippable as a whole | Leak count / RSI / ZDR flag |
| **Cost** | Live OpenRouter pricing and actual usage ledger | Model-only TCO + actual credits per call |
| **Performance** | Network latency and completion throughput captured after semaphore acquisition | P50/P95 latency + tokens/second |
| **Recommendation** | Versioned use-case catalog, quality thresholds and configurable weights | Ranked eligible models and one or more tied recommendations |

---

## Architecture

```text
src/
├── core/
│   ├── config.py              # Pydantic-settings (env vars, target models)
│   ├── methodology.py         # METHODOLOGY_VERSION recorded in every run artifact
│   ├── model_presets.py       # Named TARGET_MODELS sets (free/paid/mixed)
│   ├── model_selector.py      # `make select` catalog filters and saved selection
│   └── run_manifest.py        # Run manifest and checksums (`make inspect-run`)
├── api/
│   ├── openrouter_client.py   # Sync + async OpenAI SDK wrapper (retries, semaphore, cost ledger)
│   └── fake_client.py         # Offline client used by `make dry-run`
├── evaluators/
│   ├── deterministic_eval.py  # JSON / exact-answer / code checks (no LLM call)
│   ├── code_sandbox.py        # Restricted execution of generated code against test cases
│   ├── quality_judge.py       # Response collection + blind judging batch (judging is external)
│   ├── quality_metrics.py     # Aggregation, coverage, stability, bootstrap intervals
│   ├── quality_diagnostics.py # Item analysis and inter-judge agreement
│   ├── security_scanner.py    # Canary-based injection probes, RSI, ZDR check
│   ├── leak_detection.py      # Canary leak detection
│   ├── scenario_runner.py     # Bounded multi-turn scenarios of the security path
│   ├── dialogue_quality.py    # Optional two-turn dialogue screen
│   ├── cost_analyzer.py       # Pricing, TCO/CER, actual call costs
│   └── recommendation.py      # Use-case eligibility, weighted ranking, sensitivity
├── observability/             # MLflow tracker + content-free JSON log events
├── pipeline_cli.py            # CLI parsing and per-run overrides
├── pipeline_collect.py        # Concurrent collection + error budgets
├── pipeline_merge.py          # Benchmark matrix consolidation
├── pipeline_artifacts.py      # Result exports + blind judging files
├── dialogue_cli.py            # `make dialogue` / `make dialogue-live`
└── main.py                    # CLI entry point: collect / merge / dry-run / verify / select

dashboard/                     # Data prep, glossary and charts used by the static HTML report
scripts/                       # Static HTML export, quality recheck, gen-e2-eval export

data/prompts/
├── quality_prompts_v3.json    # generic-screen-v3: 48 prompts, 6 per use case (default)
├── quality_prompts_v2.json    # generic-screen-v2: 34 prompts (kept to re-merge its runs)
├── quality_prompts.json       # generic-screen-v1: 16 prompts (legacy baseline)
├── security_probes.json       # The security path: 72 probes, 51 scored, 3 multi-turn
├── legacy/                    # Probe sets of methodology 0.4 and earlier, for traceability only
└── dialogue_scenarios_v1.json # Optional two-turn dialogue screen

data/catalog/
├── model_compass_use_cases_v3.json # 8 use cases, thresholds, weights and weight profiles (default)
├── model_compass_use_cases_v2.json # Catalog of the v2 suite
└── model_compass_use_cases.json    # 6 use cases of the v1 suite

results/                       # Timestamped exports: benchmark, recommendations, evidence, report
docs/                          # MkDocs site: workflow, methodology, ADRs, project history

.github/agents/
├── judge-coordinator.agent.md # Phase 2 entry point: dispatches the 3 judges until make check-judging passes
├── judge-anthropic.agent.md   # Blind judge — Claude Sonnet 5
├── judge-openai.agent.md      # Blind judge — GPT-6 Sol
└── judge-google.agent.md      # Blind judge — Gemini 3.8 Flash
```

### Key design decisions

- **`openai` SDK** pointed at OpenRouter via `base_url` — native compatibility, no custom HTTP client
- **`asyncio.gather`** across all three evaluation stages — total runtime ≈ slowest model, not sum
- **`asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)`** — defaults to `3` to avoid free-tier rate-limit errors
- **`tenacity.AsyncRetrying`** — exponential back-off on 429 / 5xx, releases semaphore during wait
- **Deterministic pre-eval** — JSON / Python syntax checked in pure code before calling a judge (saves cost)
- **Blind judging via Copilot agents** — no OpenRouter LLM-judge call. Undecidable responses are
  written to a `judging_*.json` file with model identities stripped, then scored by 3 Copilot
  agents (Claude Sonnet 5 / GPT-6 Sol / Gemini 3.8 Flash) running in parallel. Scores are averaged per model — zero extra
  API cost, three providers instead of one (their own bias is discussed in the
  [quality methodology](docs/quality-methodology.md))
- **Generic quality screen** — versioned, provider-neutral prompts test structured output, code
  correctness, contextual accuracy, reasoning, classification, instruction reliability,
  summarization and concise communication.
  The aggregate is macro-averaged by dimension; coverage and optional repeat-run stability are exported
  alongside the score. The Model Compass catalog maps these prompts to generic use cases and applies
  a per-use-case quality threshold before ranking models.
- **Model Compass recommendation layer** — every model remains visible for every catalog use case;
  quality eligibility is evaluated first, then quality, security, model-only cost and performance are
  combined with configurable weights. Cost and p95 latency use fixed logarithmic anchors in the
  versioned catalog, so adding or removing a model cannot change another model's component scores.
  Equal scores remain tied and the final choice stays human.
- **MLflow** — local SQLite tracking (`sqlite:///results/mlflow/mlruns.db`) by default, no external service required
- **Actual call-cost ledger** — every successful OpenRouter completion records the provider-returned
  `usage.cost`, token usage, resolved model, latency and evaluation stage. The raw ledger contains no
  prompts or responses and is exported under `results/call_costs/`.

---

## Quick Start — the standard evaluation path

Follow these seven steps in order. Runs produced this way with the same release
of the repository can be compared with each other.

| Step | Action | Cost |
| --- | --- | --- |
| 1 | Install | $0 |
| 2 | Add your OpenRouter key | $0 |
| 3 | Choose the models — `make select` | $0 |
| 4 | Check key, models and probes — `make verify` | $0 |
| 5 | Collect the answers — `make collect` | **Paid** |
| 6 | Blind judging — `@judge-coordinator` in Copilot Chat | $0 on OpenRouter |
| 7 | Merge and publish — `make merge`, `make export-html` | $0 |

### Prerequisites

- Python 3.11+ and an [OpenRouter API key](https://openrouter.ai/keys) with credits.
- VS Code with GitHub Copilot Chat. Step 6 runs three judge agents on Claude
  Sonnet 5, GPT-6 Sol and Gemini 3.8 Flash, each set in the `model:` field of
  `.github/agents/judge-*.agent.md` by the qualified name the Copilot Chat model
  picker shows (`Claude Opus 5.5 (copilot)`). VS Code silently runs an agent on
  the chat's current model when that name does not resolve, including for a
  bare ID such as `claude-opus-5.5`, so `make check-judging` refuses bare IDs,
  reads Copilot Chat's local debug logs and rejects scores produced by any
  other model. Gemini 3.8 Flash is also benchmarked (no other Google
  model is enabled on the plan): the report's outcome without the own-provider
  judge is the check against self-preference.

### 1. Install

```bash
git clone <repo> && cd model-compass
python3 -m venv .venv && source .venv/bin/activate  # the Makefile uses .venv/bin/python
pip install -e .                                    # contributors: make dev
```

### 2. Configure

```bash
cp .env.example .env   # then set OPENROUTER_API_KEY=sk-or-...
```

Keep the other settings at their defaults: they are part of the reference
methodology.

### 3. Choose the models

```bash
make select   # asks for model type, prices and context, then saves the choice as "selection"
```

### 4. Check before spending

```bash
make verify MODELS=selection
```

Free: it only calls `GET /key` and `GET /models`. It stops on an invalid key, a
model slug missing from the live catalog or a malformed probe file.

### 5. Collect

```bash
make collect MODELS=selection
```

This is the only paid step, and its defaults are the reference methodology:

- **Quality:** each model receives the 48 prompts of the v3 suite three times
  (144 calls). Three attempts give the stability score and the 95% confidence
  intervals. Generated code runs against its test cases in the restricted
  sandbox (`src/evaluators/code_sandbox.py`) instead of going to the judges.
- **Security:** the single security path sends the 72 probes of
  `data/prompts/security_probes.json` (about 190 requests per model). The 51
  probes whose canary check can fail run three times, each with a fresh secret,
  and form the RSI; the other 21 are reported as observations.

`make collect` first checks what the OpenRouter path really forwards for every
prompt, for less than a cent. A security probe that a gateway filter would rewrite
is not sent and leaves the RSI, and the report lists it. A rewritten quality item,
or too few delivered probes, stops the run before any scored call.

`make select` and `make verify` print a rough upper estimate of the run's
OpenRouter cost before you start. Raising `MAX_CONCURRENT_REQUESTS` in `.env`
(for example to 6) shortens the run if your OpenRouter account allows it.

### 6. Judge

In VS Code Copilot Chat, send:

```text
@judge-coordinator
```

The coordinator first runs `make judge-models`, which stops it when a judge
agent's model is not enabled on your Copilot plan (see "Changing a judge
model" below). It then runs `make check-judging QUARANTINE=1`, which lists every
(part, judge) pair still to score, and launches all of them at once. Each judge
reads its anonymised part (aliases A, B, C…) and writes its own
`data/intermediate/scores_<ts>_<provider>[_partNNofMM].json`. The coordinator
then runs the check again and relaunches only what failed, for up to three
rounds. `make check-judging` accepts a score file only when it covers exactly
the expected responses, carries the declared judge identifier, and the Copilot
debug log shows the declared model reading nothing but its part. Invalid files
are moved to `data/intermediate/rejected_scores/`. Wait for "N/N parts judged
and verified"; if the coordinator stops earlier, relaunch it, as it resumes
from the files already accepted. Never merge before that.

`make collect` splits a large batch into `judging_<ts>_partNNofMM.json` files of
at most 30 KB and 36 responses, the most a judge has returned complete in one
answer, and `make merge` combines the per-part score files (a response scored
twice by the same judge fails the merge). For a batch collected before this
split existed, run `make split-judging` first; `make split-judging REPLACE=1`
re-splits a batch none of whose parts is scored. Without access to Copilot's
debug logs (for instance inside the dev container), point
`COPILOT_DEBUG_LOGS_DIR` at them or pass `SKIP_MODEL_AUDIT=1`, which leaves the
judge models unverified.

**Changing a judge model.** When Copilot retires or adds a model, run
`make judge-models`. It reads the plan's model list from Copilot Chat's local
debug logs and, for each judge, says whether its model is enabled, whether it is
also benchmarked in the saved selection (it would score itself), and which
models of the same vendor are enabled instead. Switch a judge with
`make judge-models SET="anthropic=Claude Sonnet 5 (copilot)"`: it rewrites the
agent's `model:` line and judge identifier together. Prefer a model that is not
benchmarked. A batch must be judged by one panel: switch judges only between
runs, never halfway through a batch.

### 7. Merge and publish

```bash
make merge         # benchmark + recommendations under results/
make export-html   # shareable report: results/dashboard_<ts>.html
make inspect-run   # checks the run manifest and artifact checksums
```

Open `results/dashboard_<ts>.html` directly from disk; it works offline. The
report opens on the **decision summary**: one card per generic use case with the
recommended model(s), the models whose quality cannot be told apart from the
leader, the exclusions and their reason, and a *fragile* badge when a 10 %
change of one weight or of the threshold changes the outcome. Every page shows
the methodology version, quality suite, use-case catalog, security probe set,
decision weights and workload profile of the run, and a warning when the run
does not follow this standard path. **Compare two runs only when all of these
match.** The [report reading guide](docs/guide-lecture-rapport.md) explains each
page for a decision-maker.

---

## Advanced options

None of these options is needed for the standard path. Skipping security, a
different number of attempts or any setting listed under *Settings that change
the methodology* makes a run incomparable with standard runs.

### Model presets and selector options

Instead of `make select`, use a named preset — either in `.env`
(`TARGET_MODELS=paid_flagship`) or per run, without touching `.env`:

```bash
make models                          # list every preset + the models it contains
make verify MODELS=paid_flagship     # $0 — check a preset against the live catalog
make collect MODELS=paid_flagship
```

The `free_general` preset contains two free models. With the defaults, one run
sends about 670 requests (2 × 144 quality calls + 2 × about 190 security
requests): far above the 50 requests/day that OpenRouter allows accounts with
less than 10 USD of credits (1,000/day above that). `make verify`
and `make collect` warn before any call when a run exceeds this cap. Use
`make select FREE_ONLY=1 LIMIT=1` when you want one recommended free model.

For a current, price-aware selection without typing model IDs manually, use
the dynamic selector. It only reads the OpenRouter catalog and prints ready-to-
copy commands; it does not start a benchmark:

```bash
make select PAID_ONLY=1 LIMIT=4 MAX_OUTPUT_PRICE=3 MIN_CONTEXT=32000
```

The selector displays the selected models, current input/output prices,
context length, estimated monthly cost, and estimated request count. Run the
printed `make verify` command before the printed `make collect` command.

When run from a terminal, `make select` asks for the model type, maximum input
and output prices per 1M tokens, minimum context length, and maximum number of
models. At filter prompts, press **Enter** or enter `skip` to keep the default;
for model type, that means no paid/free filter. The result shows a numbered
preselection of the cheapest matches and up to 20 additional matching models.
`LIMIT` controls the size of the preselection, not the total number of matches.
At the final choice, **Enter**, `skip`, or `all` selects every matching model
with usable pricing, including matches not shown in the numbered list. The
selector reports the total, estimated request count, and cost, then asks for
explicit confirmation; declining keeps the recommendation instead. Enter `0`
to use only the recommendations, or enter comma-separated numbers such as
`2,7` to choose from the displayed models. The chosen IDs are saved locally as
`selection`, so the next commands can use the same selection without copying
model names:

```bash
make verify MODELS=selection
make collect MODELS=selection
```

The saved selection is local runtime state under `data/intermediate/` and is
ignored by Git. Run `make select` again whenever you want to replace it.

### Two-turn dialogue screen (separate from the benchmark)

The optional two-turn dialogue screen is **separate from the main benchmark**:
`make dialogue` runs nine bounded scenarios offline with synthetic answers;
`make dialogue-live MODELS=paid_flagship` makes 18 billable calls per model.
Its versioned drift and omission metrics are written to separate dialogue
artifacts, not included in the single-turn scores or recommendations. See
[the multi-probe methodology](docs/multiprobe-system.md).

### Skipping security

Security is one path, run whole or not at all:

```bash
make collect MODELS=selection SECURITY=skip
```

`SECURITY=skip` sends no probe. The recommendation then ranks models on
quality, cost and performance only, with their weights rescaled to sum to one,
and every report page carries a warning that the run is not reference evidence.
Use it for a quality-only exploration, never for a decision where prompt
injection or data disclosure matters. `SECURITY_PROBES_PATH` replaces the probe
set for an experiment; its RSI is not comparable with the standard path. The
probe sets of methodology 0.4 and earlier (`basic`, `owasp`, `extended`) are
kept under `data/prompts/legacy/` only to trace those runs. See
[`docs/security-methodology.md`](docs/security-methodology.md) for the probe
set, the attempts and the leak oracle.

### Offline smoke test

```bash
make dry-run   # 100% offline: fake client and synthetic judges, nothing billed
```

It runs the whole pipeline with fake answers and simulated latency, then writes
a full rehearsal report (`data/dry_run/dashboard_preview_<ts>.html`, flagged as
synthetic on every page). Everything stays under `data/dry_run/`, so it can
never be merged as a real run. Use it after changing
prompts, probes or settings. For a cheap first contact with real models,
`make collect MODELS=selection QUALITY_REPETITIONS=1 SECURITY=skip` sends about
a sixth of the calls, but gives no confidence intervals and no security
evidence, so the report flags it and it must not support a recommendation.

### Optional reproducibility recheck (`k=1` runs only)

For an objective failure from a run with `QUALITY_REPETITIONS=1`, an optional
paid OpenRouter-only recheck can measure whether the failure is reproducible:

```bash
make verify-quality ARGS='--results results/benchmark_<timestamp>.csv \
  --model openai/gpt-4o-mini --prompt-id 4'
```

This sends the same prompt to the same OpenRouter model twice. It reports
`confirmed_failure`, `not_reproduced`, `unstable`, or `inconclusive`; it does
**not** identify whether OpenRouter, its upstream provider, or the model caused
the result. The command rejects correct responses, subjective prompts, and
runs where the selected prompt already has `k > 1` attempts.

### Settings that change the methodology

`QUALITY_SUITE=v2` or `v1` (earlier suites), `QUALITY_CODE_EXECUTION=false`
(generated code judged instead of tested), `QUALITY_MAX_TOKENS`,
`SECURITY_PROBES_PATH`, `MODEL_COMPASS_WEIGHTS` and `WORKLOAD_PROFILE` change
scores or ranks. Runs made
with different values are not comparable, even under the same methodology
version. See [Configuration](#configuration).

---

## Configuration

All settings are loaded from environment variables (`.env`).

| Variable                    | Default                          | Description                                                                                                                                                                        |
| --------------------------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `OPENROUTER_API_KEY`      | —                               | **Required.** OpenRouter API key                                                                                                                                             |
| `OPENROUTER_BASE_URL`     | `https://openrouter.ai/api/v1` | API base URL                                                                                                                                                                       |
| `TARGET_MODELS`           | 3 built-in free models           | Comma-separated model list, a named preset (`free_general` / `paid_flagship` / `budget_paid` / `mixed_value`, see `make models`), or `selection` saved by `make select` |
| `MAX_CONCURRENT_REQUESTS` | `3`                            | `asyncio.Semaphore` cap (conservative default for free-tier)                                                                                                                     |
| `REQUEST_TIMEOUT`         | `60.0`                         | Per-request HTTP timeout, in seconds                                                                                                                                              |
| `MAX_RETRIES`             | `3`                            | Retry attempts on HTTP 429/5xx, with exponential back-off                                                                                                                        |
| `MLFLOW_TRACKING_URI`     | `sqlite:///results/mlflow/mlruns.db`          | MLflow tracking database (SQLite)                                                                                                                                                  |
| `SECURITY_MODE`           | `full`                         | The security path: `full` runs the 72 probes of `data/prompts/security_probes.json` (51 scored, three attempts each), `skip` leaves security out of the run. Also settable per run: `--security`/`SECURITY=` |
| `SECURITY_PROBES_PATH`    | —                               | Custom probe JSON file replacing the probe set, for experiments only (ignored with `skip`)                                                                                       |
| `MAX_SECURITY_PROBE_ERROR_RATE` | `0.15`                    | Abort a run when security-probe transport failures exceed this ratio                                                                                                             |
| `QUALITY_REPETITIONS`     | `3`                            | Attempts per quality prompt; three give the stability score and confidence intervals of the reference path                                                                     |
| `MAX_QUALITY_COLLECTION_ERROR_RATE` | `0.15`                | Abort a run when quality-collection transport failures exceed this ratio                                                                                                         |
| `QUALITY_SUITE`           | `v3`                           | Quality suite and catalog: `v3` (48 prompts, 6 per use case, default), `v2` (34 prompts) or `v1` (16 prompts, legacy baseline). Also `--quality-suite`; use the same value for `merge` |
| `QUALITY_CODE_EXECUTION`  | `true`                         | Run generated code of `code_execution` prompts against their tests in the restricted sandbox, with partial credit; `false` sends them to the judge panel                         |
| `QUALITY_MAX_TOKENS`      | `16384`                        | Ceiling on a quality answer, hidden reasoning included; bounds a model that loops until its maximum output                                                                       |
| `PROMPT_DELIVERY_AUDIT`   | `true`                         | Check before each collection what reaches the models; `false` flags the run as non-reference |
| `WORKLOAD_PROFILE`        | `enterprise_qa`                | TCO/CER workload profile: `enterprise_qa` \| `code_assistant` \| `document_analysis` \| `chatbot_high_volume`                                                              |
| `MODEL_COMPASS_WEIGHTS`   | catalog defaults               | Optional JSON override for quality/security/cost/performance weights; values must sum to `1.0`                                                                                  |

> **Note:** `JUDGE_MODEL` no longer exists. Quality judging for undecidable
> responses is done by 3 GitHub Copilot agents (`@judge-anthropic`,
> `@judge-openai`, `@judge-google`), not an OpenRouter model — zero extra
> API cost.

### Interpreting the quality result

`avg_quality_score` is a **generic quality component**, not a claim that a model is best for a
specific client workflow. It is macro-averaged across the quality dimensions so that a large
number of easy formatting prompts cannot dominate the result. Model Compass then evaluates the
content score per catalog use case before producing a recommendation; output-format compliance
is reported beside it and never lowers a use case's quality score. Read it together with:

- `quality_coverage_rate` — fraction of configured prompts successfully scored;
- `quality_dimension_coverage_rate` — fraction of quality dimensions represented in the score;
- `quality_stability_score` — repeatability signal when `QUALITY_REPETITIONS >= 2`;
- `quality_collection_error_count` — API/transport failures, kept separate from model failures.

For objective checks, `verification_status` in the evidence detail distinguishes:

- `not_required` — the response passed;
- `optional_openrouter_recheck` — a failed objective response from a `k=1` run;
- `run_repetitions_available` — use the attempts already collected with `k>1`;
- `confirmed_failure`, `not_reproduced`, `unstable`, `inconclusive` — result of an optional
  OpenRouter recheck associated with the benchmark.

Recheck reports are sidecar evidence under `results/verification/`. They are shown in
`evidence.html`, but never rewrite the original benchmark score. For recommendation decisions,
prefer `QUALITY_REPETITIONS>=2`; the optional recheck mainly exists for diagnosing a `k=1` run.

The cost-efficiency ratio (`cer`) is withheld when the result does not cover the required dimensions.
Model Compass recommendation rows are exported under `results/recommendations/` and include the
use-case threshold, quality eligibility, weighted decision score, rank and missing evidence, plus
the rank under each named weight profile of the catalog (`quality_first`, `balanced`,
`cost_sensitive`). Set `MODEL_COMPASS_WEIGHTS` to override the default `50/25/20/5` weights without
changing the code; [`docs/model-compass-scope.md`](docs/model-compass-scope.md) justifies the
defaults and the profiles by the trade-offs they imply.
Use `gen-e2-eval` when a client-specific golden dataset is available and a domain acceptance decision
is required.
See [docs/quality-methodology.md](docs/quality-methodology.md) for prompt provenance, coverage
limits, the validation protocol and the comparison procedure with `gen-e2-eval`.

For recommendations, the catalog fixes logarithmic score anchors: blended cost
is scored from USD 0.10 to USD 100 per million tokens, and p95 latency from 1 to
30 seconds. A free model receives 100 for cost; missing p95 is missing evidence.
Unlike run-relative min-max scoring, adding or removing models does not change
another model's component score. The workload profile remains part of run
provenance because it determines the input/output token mix used for the blend.

### Actual cost versus TCO projection

- `actual_cost_credits` is the amount returned by OpenRouter in `response.usage.cost` for the calls
  made during the benchmark. `actual_cost_coverage_rate` indicates how many calls supplied this value.
  A free model is correctly represented by **0 credits with 100% coverage**.
- `tco_usd` is a forward-looking monthly estimate based on the selected workload profile and the
  pricing snapshot from `/models`; it is not the charge for the current benchmark run.
- Calls issued by Copilot judge agents are outside OpenRouter and therefore are not present in the
  OpenRouter call-cost ledger.

### Troubleshooting first runs

| Symptom                                                                | Likely cause                                                                                                        | Fix                                                                                                                                                         |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make verify` fails with "API key check failed" / HTTP 401           | `OPENROUTER_API_KEY` in `.env` is missing, wrong, or the shell has a stale exported env var overriding `.env` | Check`openrouter.ai/keys`; run `env \| grep OPENROUTER_API_KEY` — if it's set in the shell, `unset OPENROUTER_API_KEY` so `.env` takes effect again |
| `make verify` lists model ID(s) "not in the live OpenRouter catalog" | Typo or a discontinued/renamed`:free` slug in `TARGET_MODELS`                                                   | Check[openrouter.ai/models](https://openrouter.ai/models) for the current slug                                                                               |
| `Unknown model preset '...'`                                         | Typo in`MODELS=`/`TARGET_MODELS=<preset>`                                                                       | Run`make models` to list valid preset names                                                                                                               |
| `make collect` warns about the free-tier request cap                 | `TARGET_MODELS` uses `:free` models and the account has < 10 USD lifetime credits                               | Buy ≥ 10 USD credits (raises the cap from 50 to 1000 req/day) or reduce`TARGET_MODELS` / `QUALITY_REPETITIONS`                                         |
| `make merge` errors with "Missing Copilot judge scores"              | `@judge-coordinator` (Phase 2) was never run, or was run before the current `make collect`                      | Run`@judge-coordinator` in Copilot chat against the latest `data/intermediate/judging_*.json`, then retry `make merge`                                |
| `make verify-quality` says the evidence is not eligible | The response passed, is not an objective check, or does not come from a `k=1` run | Inspect `verification_status` in Prompts & responses; use existing stability evidence for `k>1` |
| `make verify-quality` cannot find accepted answers | The benchmark predates reproducibility metadata | Produce a new run; historical results remain readable but cannot be rechecked automatically |

---

## Development

```bash
pytest --tb=short          # run the test suite
ruff check src/            # lint
mypy src/ --strict         # type-check
make docs-build            # validate the documentation site
make docs-serve            # preview it locally with live reload
make export-html           # static report from the latest benchmark
mlflow ui                  # view experiment runs
```

### Project conventions

- **Conventional Commits** validated by the local `commit-msg` pre-commit hook
  (`scripts/check_commit_message.py`)
- **ruff** for linting + import sorting; **mypy strict** for type safety
- Every new public method must have a docstring
- Tests live in `tests/` and use `pytest` + `unittest.mock` (no real API calls in CI)

## Documentation

The documentation site is built with MkDocs. Its navigation keeps the operational
workflow, ADRs, implementation plans, and the Python reference in one place.
The API reference is rendered directly from the docstrings in `src/` and
`dashboard/`, so it always reflects the source code at build time.

```bash
make docs-build  # strict validation of pages, navigation, and API references
make docs-serve  # local preview at http://127.0.0.1:8000
```

Pull requests that change documentation or Python sources run the same strict
build. A push to `main` publishes the resulting site to GitHub Pages. Before the
first deployment, enable **GitHub Pages → Build and deployment → GitHub Actions**
in the repository settings.

See [the documentation maintenance guide](docs/documentation.md) for the source
of truth and the update checklist.

---

## Security

Vulnerabilities should be reported privately — see [.github/SECURITY.md](.github/SECURITY.md).

- API keys are never logged or committed (`.env` is gitignored; `SecretStr` prevents accidental prints)
- MLflow only logs token counts and model IDs — never prompt content
- The security scanner probes are for authorised red-team testing only

---

## Repository Layout

```text
repo/
  ├── .github/                  # CI, policies, Copilot instructions and judge agents
  │   ├── CONTRIBUTING.md
  │   ├── SECURITY.md
  │   └── workflows/ci.yml      # Python lint, type-check, tests and strict docs build
  ├── .devcontainer/            # Optional VS Code Python development container
  ├── .pre-commit-config.yaml   # Python lint/format, file checks and commit-message hook
  ├── AGENTS.md                 # Shared agent instructions
  ├── CHANGELOG.md
  ├── Makefile                  # Install, test, lint, collect, merge and dashboard commands
  ├── mkdocs.yml                # Documentation site
  ├── pyproject.toml            # Python package, dependencies and tooling
  ├── README.md
  ├── dashboard/                # Report data prep, glossary and charts
  ├── data/                     # Versioned prompts, probes and use-case catalogs
  ├── docs/                      # User guides, methodology, ADRs and history
  ├── scripts/                   # Exporters and small repository tools
  ├── src/                       # Pipeline and evaluation code
  └── tests/                     # Python test suite
```

GitHub also recognizes contribution and security policies inside `.github/`.

---

## Usage and distribution

Model Compass is an internal Palo IT tool. The code, prompts, probes and
reports are proprietary and intended for internal use only; no open-source
licence is granted. Ask the project owner before sharing the repository or a
report outside Palo IT.
