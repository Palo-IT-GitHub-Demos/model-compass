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
enterprise use case. Results are exported as CSV/JSON and visualised in a local
Streamlit dashboard and a static HTML report.

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
| **Security** | Internal prompt-injection probes aligned with selected OWASP categories + Zero Data Retention policy check | Leak count / RSI / ZDR flag |
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
│   ├── code_sandbox.py        # Opt-in restricted execution of generated code
│   ├── quality_judge.py       # Response collection + blind judging batch (judging is external)
│   ├── quality_metrics.py     # Aggregation, coverage, stability, bootstrap intervals
│   ├── quality_diagnostics.py # Item analysis and inter-judge agreement
│   ├── security_scanner.py    # Canary-based injection probes, RSI, ZDR check
│   ├── leak_detection.py      # Canary leak detection
│   ├── scenario_runner.py     # Bounded multi-turn scenarios (extended profile)
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

dashboard/                     # Streamlit app + data prep and charts shared with the static export
scripts/                       # Static HTML export, quality recheck, gen-e2-eval export

data/prompts/
├── quality_prompts_v2.json    # generic-screen-v2: 34 prompts (default)
├── quality_prompts.json       # generic-screen-v1: 16 prompts (legacy baseline)
├── owasp_probes.json          # 30 probes aligned with the OWASP GenAI LLM Top 10 2026
├── extended_probes.json       # 23 single-turn probes + 2 bounded LLM01 scenarios
└── dialogue_scenarios_v1.json # Optional two-turn dialogue screen

data/catalog/
├── model_compass_use_cases_v2.json # 8 use cases, thresholds and weights (default)
└── model_compass_use_cases.json    # 6 use cases of the v1 suite

results/                       # Timestamped exports: benchmark, recommendations, evidence, report
docs/                          # MkDocs site: workflow, methodology, ADRs, project history

.github/agents/
├── judge-coordinator.agent.md # Phase 2 entry point: runs the 3 judges in parallel
├── judge-anthropic.agent.md   # Blind judge — claude-sonnet-5
├── judge-openai.agent.md      # Blind judge — gpt-4o
└── judge-google.agent.md      # Blind judge — gemini-2.5-pro
```

### Key design decisions

- **`openai` SDK** pointed at OpenRouter via `base_url` — native compatibility, no custom HTTP client
- **`asyncio.gather`** across all three evaluation stages — total runtime ≈ slowest model, not sum
- **`asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)`** — defaults to `3` to avoid free-tier rate-limit errors
- **`tenacity.AsyncRetrying`** — exponential back-off on 429 / 5xx, releases semaphore during wait
- **Deterministic pre-eval** — JSON / Python syntax checked in pure code before calling a judge (saves cost)
- **Blind judging via Copilot agents** — no OpenRouter LLM-judge call. Undecidable responses are
  written to a `judging_*.json` file with model identities stripped, then scored by 3 Copilot
  agents (Claude/GPT-4o/Gemini) running in parallel. Scores are averaged per model — zero extra
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
- **MLflow** — local SQLite tracking (`sqlite:///mlruns.db`) by default, no external service required
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
- VS Code with GitHub Copilot Chat. Step 6 runs three judge agents on
  `claude-sonnet-5`, `gpt-4o` and `gemini-2.5-pro` (set in
  `.github/agents/judge-*.agent.md`). Check that all three models are available
  in your Copilot model picker before step 5: `make merge` stops without the
  three score files.

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
make verify MODELS=selection SECURITY=owasp
```

Free: it only calls `GET /key` and `GET /models`. It stops on an invalid key, a
model slug missing from the live catalog or a malformed probe file.

### 5. Collect

```bash
make collect MODELS=selection SECURITY=owasp QUALITY_REPETITIONS=3
```

This is the only paid step. Each model receives the 34 quality prompts three
times (102 calls) and the 30 `owasp` security probes. Three attempts per prompt
produce the stability score and the 95% confidence intervals; `owasp` probes the
ten OWASP categories, seven of which a chat probe can score in the RSI.

### 6. Judge

In VS Code Copilot Chat, send:

```text
@judge-coordinator
```

The coordinator gives the anonymised answers (aliases A, B, C…) to the three
judges and writes `data/intermediate/scores_<ts>_{anthropic,openai,google}.json`.
Wait until it confirms that the three files are valid. If a judge fails, run
the coordinator again; never merge with missing scores.

### 7. Merge and publish

```bash
make merge         # benchmark + recommendations under results/
make export-html   # shareable report: results/dashboard_<ts>.html
make inspect-run   # checks the run manifest and artifact checksums
```

Open `results/dashboard_<ts>.html` directly from disk, or run `make dashboard`
for the interactive view (<http://localhost:8501>). Every page shows the
methodology version, quality suite, use-case catalog, security probe set,
decision weights and workload profile of the run. **Compare two runs only when
all of these match.**

---

## Advanced options

None of these options is needed for the standard path. A different security
profile, number of attempts or any setting listed under *Settings that change
the methodology* makes a run incomparable with standard runs.

### Model presets and selector options

Instead of `make select`, use a named preset — either in `.env`
(`TARGET_MODELS=paid_flagship`) or per run, without touching `.env`:

```bash
make models                          # list every preset + the models it contains
make verify MODELS=paid_flagship     # $0 — check a preset against the live catalog
make collect MODELS=paid_flagship SECURITY=owasp
```

The `free_general` preset contains two free models. With the default v2 suite
and the `basic` probes, one run sends about 78 requests (2 × 34 quality
prompts + 2 × 5 probes): above the 50 requests/day that OpenRouter allows
accounts with less than 10 USD of credits (1,000/day above that). `make verify`
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
models. Press **Enter** or enter `skip` to keep the default for any filter. The
result shows a numbered preselection of the cheapest matches and additional
models that also satisfy the filters. `LIMIT` controls the size of the
preselection; it does not prevent other matching models from being shown. The
numbered list accepts `0` (the complete recommendation) or comma-separated
numbers such as `2,7`, including models outside the preselection. The chosen IDs are saved locally as `selection`, so the
next commands can use the same selection without copying model names:

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

### Security profiles

`SECURITY=` picks the probe set for that run only: `basic` (5 built-in probes,
default), `owasp` (30 internally authored probes aligned with the OWASP GenAI
LLM Top 10 2026 categories — required for the dashboard's RSI/heatmap), or
`extended` (25 red-team entries across LLM01/02/03/07/10, including two
bounded LLM01 scenarios). These are not official OWASP probe files or an OWASP certification.
The profiles serve different purposes:

| Profile | Scope | Recommended use |
| --- | --- | --- |
| `basic` | 5 built-in, single-turn injection probes | Fast smoke test and low-cost screening |
| `owasp` | 30 internal probes aligned with 10 OWASP categories, 3 per category | Standard path: broad, repeatable security baseline and heatmap |
| `extended` | 23 single-turn probes across LLM01/02/03/07/10 and two bounded LLM01 scenarios | Canary-disclosure stress test across contexts |

`extended` is not a full OWASP security certification: it deepens `LLM01` with techniques
such as encoding, Unicode smuggling, jailbreak framing, typoglycemia, few-shot
authority spoofing and bounded multi-turn escalation (see
[`docs/multiprobe-system.md`](docs/multiprobe-system.md) for the scenario
contract) and adds canary-disclosure probes for four more categories. It does
not verify tool access, factuality or HTML safety. Do not compare its RSI directly with an `owasp` RSI; compare runs
only when their scored category set and probe profile/version are the same.
The Streamlit dashboard's **"Plan a new run"** panel exposes the same profiles
visually and prints the ready-to-run command.

### Offline smoke test

```bash
make dry-run   # 100% offline: fake client and synthetic judges, nothing billed
```

It runs the whole pipeline with fake answers and writes only under
`data/dry_run/`, so it can never be merged as a real run. Use it after changing
prompts, probes or settings. For a cheap first contact with real models, run
step 5 with the defaults (`basic` probes, one attempt per prompt): about a third
of the calls, but no confidence intervals and only five security probes, so do
not use it for a recommendation.

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

`QUALITY_SUITE=v1` (legacy 16-prompt suite), `QUALITY_CODE_EXECUTION=true`
(sandboxed execution of generated code instead of judging it),
`MODEL_COMPASS_WEIGHTS` and `WORKLOAD_PROFILE` change scores or ranks. Runs made
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
| `MLFLOW_TRACKING_URI`     | `sqlite:///mlruns.db`          | MLflow tracking database (SQLite)                                                                                                                                                  |
| `SECURITY_MODE`           | `basic`                        | Internal probe set: `basic` (5 built-in), `owasp` (30 probes aligned with the 10 OWASP GenAI LLM Top 10 2026 categories), `extended` (23 single-turn probes + 2 LLM01 scenarios). Also settable per run: `--security`/`SECURITY=` |
| `SECURITY_PROBES_PATH`    | —                               | Path to a custom probe JSON file (overrides`SECURITY_MODE` above)                                                                                                                |
| `MAX_SECURITY_PROBE_ERROR_RATE` | `0.15`                    | Abort a run when security-probe transport failures exceed this ratio                                                                                                             |
| `QUALITY_REPETITIONS`     | `1`                            | Repeats per generic quality prompt; use`2`–`5` only for shortlist stability checks                                                                                            |
| `MAX_QUALITY_COLLECTION_ERROR_RATE` | `0.15`                | Abort a run when quality-collection transport failures exceed this ratio                                                                                                         |
| `QUALITY_SUITE`           | `v2`                           | Quality suite and catalog: `v2` (34 prompts, 8 use cases, default) or `v1` (16 prompts, legacy baseline). Also `--quality-suite`; use the same value for `merge`                    |
| `QUALITY_CODE_EXECUTION`  | `false`                        | Execute generated code of v2 `code_execution` prompts in the restricted sandbox; when off they are judged by the panel                                                             |
| `WORKLOAD_PROFILE`        | `enterprise_qa`                | TCO/CER workload profile: `enterprise_qa` \| `code_assistant` \| `document_analysis` \| `chatbot_high_volume`                                                              |
| `MODEL_COMPASS_WEIGHTS`   | catalog defaults               | Optional JSON override for quality/security/cost/performance weights; values must sum to `1.0`                                                                                  |

> **Note:** `JUDGE_MODEL` no longer exists. Quality judging for undecidable
> responses is done by 3 GitHub Copilot agents (`@judge-anthropic`,
> `@judge-openai`, `@judge-google`), not an OpenRouter model — zero extra
> API cost.

### Interpreting the quality result

`avg_quality_score` is a **generic quality component**, not a claim that a model is best for a
specific client workflow. It is macro-averaged across the six quality dimensions so that a large
number of easy formatting prompts cannot dominate the result. Model Compass then evaluates the
score per catalog use case before producing a recommendation. Read it together with:

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

Recheck reports are sidecar evidence under `results/verification/`. They are shown in Streamlit
and `evidence.html`, but never rewrite the original benchmark score. For recommendation decisions,
prefer `QUALITY_REPETITIONS>=2`; the optional recheck mainly exists for diagnosing a `k=1` run.

The cost-efficiency ratio (`cer`) is withheld when the result does not cover the required dimensions.
Model Compass recommendation rows are exported under `results/recommendations/` and include the
use-case threshold, quality eligibility, weighted decision score, rank and missing evidence. Set
`MODEL_COMPASS_WEIGHTS` to override the default `50/25/20/5` weights without changing the code.
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
streamlit run dashboard/app.py   # dashboard
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
  ├── dashboard/                # Streamlit app and shared report transformations
  ├── data/                     # Versioned prompts, probes and use-case catalogs
  ├── docs/                      # User guides, methodology, ADRs and history
  ├── scripts/                   # Exporters and small repository tools
  ├── src/                       # Pipeline and evaluation code
  └── tests/                     # Python test suite
```

GitHub also recognizes contribution and security policies inside `.github/`.
