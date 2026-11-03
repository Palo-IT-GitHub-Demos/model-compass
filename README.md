# Model Compass — LLM decision-support pipeline

> Evidence-based, reproducible evaluation of large language models available on
> [OpenRouter](https://openrouter.ai/) across four axes: **Quality**,
> **Security**, **Cost**, and **Performance**.
>
> Built at **Palo IT Singapore** to support technical model selection for enterprise calls for tender.

---

## Overview

Model Compass evaluates the selected models through the OpenRouter API and
recommends models for each of eight generic enterprise use cases. Results are
exported as CSV/JSON and presented in a static, multi-page HTML report that
works offline.

It answers **"Which models are technically relevant for each generic enterprise
use case?"**, not **"Which model must be adopted for this specific client?"**
The report does not ingest a tender, client criteria or a client dataset: a
human who knows the tender makes the final choice, and `gen-e2-eval` checks a
model on the client's own tasks when a dataset exists.
[`docs/model-compass-scope.md`](docs/model-compass-scope.md) is the complete
decision contract.

### Latest release: 0.8.0

- **Reference run** of 3 November 2026: six models (Claude Sonnet 5.5,
  GPT-6.1 Sol, GPT-6 Luna, Gemini 3.8 Flash, DeepSeek V4.1 Flash, Llama 3.3
  70B). GPT-6 Luna is recommended in all eight use cases, and GPT-6.1 Sol is
  also recommended for instruction following.
- The [v0.8.0 release](https://github.com/Palo-IT-GitHub-Demos/model-compass/releases/tag/v0.8.0)
  attaches the full run: HTML report, benchmark, recommendations, judge scores
  and run manifest.
- [Two slides](docs/presentation-model-compass.md) summarise what is measured
  and how a model is recommended.
- The quality thresholds are calibrated on this run
  ([scope, "Calibration on the reference run"](docs/model-compass-scope.md)).
  [`CHANGELOG.md`](CHANGELOG.md) lists every change.

### Evaluation axes

| Axis | Method | Key metric |
| --- | --- | --- |
| **Quality** | 40 versioned generic prompts (suite `generic-screen-v3`, five per use case, three attempts): deterministic checks, generated code tested in a sandbox, blind judging by three LLMs for the rest | Score 1–5 per use case, coverage, stability |
| **Security** | 66 internal probes aligned with the OWASP GenAI LLM Top 10 2026: canary disclosure and obedience to a harmless hidden instruction; the 50 scored probes run three times; Zero Data Retention check | RSI 0–100, leak count, ZDR flag |
| **Cost** | Live OpenRouter pricing × workload input size + each model's measured output length; actual cost of every call | Cost per 1,000 requests, monthly TCO, actual credits |
| **Performance** | Latency and throughput measured once a call is in flight | P50/P95 latency, tokens/second |

### How a model is recommended

1. **Quality is a gate.** A model below a use case's quality threshold is
   never recommended there, however cheap or fast.
2. **Eligible models are ranked** by a weighted score: quality 50 %,
   security 25 %, cost 20 %, performance 5 % (the *balanced* profile). Cost and
   latency are scored on fixed logarithmic anchors, so adding a model never
   changes another model's score.
3. **The ranking is stress-tested.** A ±10 % change of one weight or of the
   threshold flags a *fragile* result, and a model that such a change would put
   first is recommended too. The *quality-first* and *cost-sensitive* profiles
   are shown beside the published rank without changing it.

Equal scores stay tied; nothing breaks a tie arbitrarily.

---

## Quick Start — the standard evaluation path

Follow these seven steps in order. Their defaults are the reference
methodology, so runs produced this way with the same release can be compared.

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
- VS Code with GitHub Copilot Chat, for the three judge agents (Claude
  Sonnet 5, GPT-6 Sol, Gemini 3.8 Flash) of step 6.

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
model missing from the live catalog or a malformed probe file, and prints an
upper estimate of the run's OpenRouter cost.

### 5. Collect

```bash
make collect MODELS=selection
```

The only paid step. Each model receives the 40 quality prompts three times
(120 calls) and the security path (about 180 requests). `make collect` first
checks, for less than a cent, what the OpenRouter gateway really forwards: a
rewritten quality item stops the run, and a rewritten probe is not sent and
leaves the RSI. Raising `MAX_CONCURRENT_REQUESTS` in `.env` (for example to 6)
shortens the run if your account allows it.

### 6. Judge

In VS Code Copilot Chat, send:

```text
@judge-coordinator
```

The coordinator dispatches the three blind judges (models appear as aliases A,
B, C…) until `make check-judging` accepts every score file. Wait for
**"N/N parts judged and verified"**; if it stops earlier, relaunch it, as it
resumes from the accepted files. Never merge before that.
[`docs/workflow.md`](docs/workflow.md) ("Phase 2") covers the split into parts,
the audit of the model each judge ran on, and how to change a judge model.

### 7. Merge and publish

```bash
make merge         # benchmark + recommendations under results/
make export-html   # shareable report: results/dashboard_<ts>.html
make inspect-run   # checks the run manifest and artifact checksums
```

Open `results/dashboard_<ts>.html` from disk. It opens on the **decision
summary**, one card per use case with the recommended model(s), the other
eligible models and the exclusions with their reason. Every page shows the
methodology version, quality suite, use-case catalog, security probe set,
decision weights and workload profile of the run. **Compare two runs only when
all of these match.** The [report reading guide](docs/report-reading-guide.md)
explains each page for a decision-maker.

---

## Advanced options

None of these is needed for the standard path. Anything that changes the
methodology makes a run incomparable with standard runs, and the report flags
it on every page.

| Need | Command | Details |
| --- | --- | --- |
| Rehearse the whole pipeline offline | `make dry-run` | Fake client and synthetic judges; report under `data/dry_run/` |
| Use a named model set | `make models`, then `MODELS=paid_flagship` | [Workflow, §1](docs/workflow.md) |
| Filter the catalog without prompts | `make select PAID_ONLY=1 LIMIT=4 MAX_OUTPUT_PRICE=3` | [Workflow, "Dynamic selection"](docs/workflow.md) |
| Quality-only exploration (not a reference run) | `make collect MODELS=selection SECURITY=skip` | [Security methodology](docs/security-methodology.md) |
| Recheck a failed objective answer of a `k=1` run (paid) | `make verify-quality ARGS='...'` | [Workflow, §4](docs/workflow.md) |
| Two-turn dialogue screen, separate from the benchmark | `make dialogue`, `make dialogue-live` (paid) | [Multi-probe methodology](docs/multiprobe-system.md) |
| Try a candidate quality item (maintainers, paid) | `make pilot-items LIVE=1 MODELS=selection` | [Workflow, §4](docs/workflow.md) |
| Export to the gen-e2-eval registry | `make export-gen-e2` | [Workflow, §7](docs/workflow.md) |

Free `:free` models are capped at 50 requests a day on accounts with less than
10 USD of credits: a default run on two of them sends about 600. `make verify`
and `make collect` warn before any call. First-run errors are listed in
[Workflow, §12 "Troubleshooting"](docs/workflow.md).

---

## Configuration

All settings are loaded from environment variables (`.env`). Settings marked
**M** change scores or ranks: runs made with different values are not
comparable, even under the same methodology version.

| Variable | Default | Description |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | — | **Required.** OpenRouter API key |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API base URL |
| `TARGET_MODELS` | 3 built-in free models | Comma-separated model list, a preset (`make models`) or `selection` saved by `make select` |
| `MAX_CONCURRENT_REQUESTS` | `3` | Concurrent calls (conservative default for free-tier) |
| `REQUEST_TIMEOUT` | `60.0` | Per-request HTTP timeout, in seconds |
| `MAX_RETRIES` | `3` | Retry attempts on HTTP 429/5xx, with exponential back-off |
| `MLFLOW_TRACKING_URI` | `sqlite:///results/mlflow/mlruns.db` | MLflow tracking database |
| `SECURITY_MODE` | `full` | `full` runs the 66 probes, `skip` leaves security out (**M**). Per run: `SECURITY=` |
| `SECURITY_PROBES_PATH` | — | Replacement probe file, for experiments only (**M**) |
| `MAX_SECURITY_PROBE_ERROR_RATE` | `0.15` | Abort when security transport failures exceed this ratio |
| `QUALITY_REPETITIONS` | `3` | Attempts per quality prompt; three give stability and confidence intervals (**M**) |
| `MAX_QUALITY_COLLECTION_ERROR_RATE` | `0.15` | Abort when quality transport failures exceed this ratio |
| `QUALITY_SUITE` | `v3` | `v3` (40 prompts, five per use case), `v2` (34) or `v1` (16, legacy); same value for `collect` and `merge` (**M**) |
| `QUALITY_CODE_EXECUTION` | `true` | Test generated code in the sandbox; `false` sends it to the judges (**M**) |
| `QUALITY_MAX_TOKENS` | `16384` | Ceiling on a quality answer, hidden reasoning included (**M**) |
| `PROMPT_DELIVERY_AUDIT` | `true` | Check what reaches the models before collecting; `false` flags the run as non-reference |
| `WORKLOAD_PROFILE` | `enterprise_qa` | Input size and monthly volume for cost and TCO: `enterprise_qa`, `code_assistant`, `document_analysis`, `chatbot_high_volume` (**M**) |
| `MODEL_COMPASS_WEIGHTS` | catalog defaults | JSON override of the quality/security/cost/performance weights, summing to `1.0` (**M**) |

---

## Architecture

```text
src/
├── core/            # Settings, methodology version, model presets and selector, run manifest
├── api/             # OpenRouter client (retries, concurrency, cost ledger) + offline fake client
├── evaluators/      # Deterministic checks, code sandbox, judging batches, quality metrics,
│                    # security scanner and leak oracle, cost, recommendation
├── observability/   # MLflow tracker + content-free JSON log events
├── pipeline_*.py    # CLI parsing, concurrent collection, merge, result artifacts
└── main.py          # CLI entry point: collect / merge / dry-run / verify / select

dashboard/           # Report data prep, glossary and charts
scripts/             # HTML report export, suite and probe builders, judging checks, exporters
data/prompts/        # Quality suites (v3 default), security probes, dialogue scenarios
data/catalog/        # Use-case catalogs: thresholds, weights and weight profiles
.github/agents/      # @judge-coordinator and the three blind judges
docs/                # MkDocs site: workflow, methodologies, scope, ADRs, history
results/             # Timestamped run outputs (benchmark, recommendations, evidence, report)
```

The [workflow](docs/workflow.md) describes each stage, the
[ADRs](docs/adr/0001-architecture-initiale.md) the design decisions, and the
[API reference](docs/reference/api.md) every public function.

---

## Development

```bash
make dev           # install with development dependencies
make test          # pytest, with no real API call
make lint          # ruff
make type-check    # mypy
make docs-build    # strict MkDocs build
make docs-serve    # local preview at http://127.0.0.1:8000
```

- **Conventional Commits**, validated by the local `commit-msg` pre-commit hook
- Every user-visible change gets an entry under `[Unreleased]` in
  [`CHANGELOG.md`](CHANGELOG.md); CI fails a pull request that changes code,
  prompts or the catalog without one
- [`AGENTS.md`](AGENTS.md) holds the methodology invariants that every change
  must keep, and [the documentation guide](docs/documentation.md) the update
  checklist
- CI builds the documentation site strictly but does not publish it: read it
  with `make docs-serve`

---

## Security

Vulnerabilities should be reported privately — see [.github/SECURITY.md](.github/SECURITY.md).

- API keys are never logged or committed (`.env` is gitignored; `SecretStr` prevents accidental prints)
- MLflow only logs token counts and model IDs, never prompt content
- Model output is untrusted: generated code runs only in the sandbox, and the report escapes every response
- The security probes are for authorised red-team testing only

---

## Usage and distribution

Model Compass is an internal Palo IT tool. The code, prompts, probes and
reports are proprietary and intended for internal use only; no open-source
licence is granted. Ask the project owner before sharing the repository or a
report outside Palo IT.
