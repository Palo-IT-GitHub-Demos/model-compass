# Model Compass

A **technical, comparative and reproducible recommendation** pipeline for the
models available on OpenRouter. Model Compass compares models on cross-cutting
criteria of quality, security, model cost and performance, then ranks them for
each generic use case to help a human answer different calls for tender.

The [detailed scope](model-compass-scope.md) sets out the decisions taken, the
limits and the catalog thresholds, calibrated on the 0.8.0 reference run.

## Where to start

The standard path takes seven steps, detailed in the Quick Start of
`README.md` and in the [workflow](workflow.md):

```bash
make select                     # choose the models, $0
make verify MODELS=selection    # key and models, $0
make collect MODELS=selection   # the only paid step
# Copilot Chat: @judge-coordinator   # blind judging
make merge && make export-html  # results and report
```

Every report shows its methodology version (the release that set the scoring
rules, currently `0.8.0`), its quality suite, catalog, probe set, weights and
workload profile. Two runs are comparable only when all of these values are
identical.

## Four measurement axes

| Axis | What it measures | Key output |
| --- | --- | --- |
| **Quality** | 40 versioned prompts (suite `generic-screen-v3`, 5 per use case), 8 dimensions + format compliance scored apart, partial credit for JSON and for code tested in the sandbox, macro-averaged 1–5 score, coverage, stability and 95 % CI from 3 attempts | `avg_quality_score`, `quality_coverage_rate`, `quality_stability_score` |
| **Security** | A single path of 66 internal probes (50 scored and run three times, including 8 indirect injections, 7 probes of obedience to a hidden instruction and 3 multi-turn scenarios), run whole or skipped, aligned with the [OWASP GenAI LLM Top 10 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/), RSI score 0–100 (internal weighting, not published by OWASP — see `_RSI_WEIGHTS` in `security_scanner.py`), ZDR check | `rsi`, `leak_count`, `zero_data_retention` |
| **Cost** | OpenRouter price × input size of the profile + the model's measured output length → cost per 1,000 requests and projected monthly TCO + actual cost per call (`response.usage.cost`) | `cost_usd_per_1k_requests`, `tco_usd`, `actual_cost_credits`, `cer` |
| **Performance** | P50/P95 latency and tokens per second, measured after the semaphore is acquired | `actual_latency_p50_ms`, `actual_latency_p95_ms`, `actual_tokens_per_second` |
| **Recommendation** | Versioned catalog, quality threshold per use case and configurable weighted score | `results/recommendations/` |

## Seeing the results

| Need | Action |
| --- | --- |
| Read the latest shareable report | Open `results/dashboard_<timestamp>.html`; its navigation leads to the Quality, Evidence, Security and Cost pages. |
| Build the HTML report of the latest merged benchmark | Run `make export-html`. |
| Understand the report before deciding | Read the [report reading guide](report-reading-guide.md). |
| Choose the models before a run | Run `make select`, answer the filters, then use `MODELS=selection`. |

The [pipeline workflow](workflow.md) gives the commands in order, from the free
check to the final report.

## Suggested paths

- **Run an evaluation**: follow the [pipeline workflow](workflow.md), from
  configuration to the report.
- **Defend or audit the quality score**: read the
  [quality methodology](quality-methodology.md) — prompt provenance, coverage,
  validation and comparison with `gen-e2-eval`.
- **Understand the code**: read the [Python API reference](reference/api.md),
  generated directly from the project's docstrings.
- **Understand the decisions**: read the [Architecture Decision Records](adr/0001-architecture-initiale.md).
- **Contribute**: follow the [contribution guide](https://github.com/Palo-IT-GitHub-Demos/model-compass/blob/main/.github/CONTRIBUTING.md).

## Positioning against gen-e2-eval

The two projects answer different questions and do not produce the same kind of
decision:

```text
Model Compass                    gen-e2-eval
──────────────────────────────   ────────────────────────────────
All evaluated models             Models tested on business tasks

Question: "which model is        Question: "does it pass
relevant for each use case?"     my business tasks?"

→ technical recommendation       → business acceptance
```

The `make export-gen-e2` export writes a YAML file that can be loaded into the
gen-e2-eval quadrant registry, with the security and TCO columns.

### Scope and decision rule

Model Compass includes:

- large-scale comparison of models available through OpenRouter;
- a generic, provider-neutral and versioned quality screen;
- cost, latency and security measurements;
- a ranking and one or more recommended models per generic use case;
- an evidence report under `results/recommendations/`.

Model Compass does not include:

- validation of a business workflow or of a client golden dataset;
- measuring functional success on a use case;
- automatic analysis of a call for tender or extraction of its requirements;
- the final adoption recommendation for an application;
- replacing the business evaluation in `gen-e2-eval`.

The decision rule is therefore: every model stays visible, the quality
threshold filters eligibility per use case, then the weighted score ranks the
models with complete evidence. Ties are kept. Any adoption decision remains
human and can be confirmed in `gen-e2-eval` on the business tasks concerned.

## Documentation structure

| Space | Content | Source of truth |
| --- | --- | --- |
| Pipeline guide | Running, inputs, outputs and interpretation | `docs/workflow.md` |
| Model Compass scope | Mission, decision logic, limits and remaining calibrations | `docs/model-compass-scope.md` |
| Presentation | Two slides: what is measured, how a model is recommended | `docs/assets/model-compass/model-compass-overview.pptx` |
| Quality methodology | Prompt provenance, coverage, validation, `gen-e2-eval` comparison | `docs/quality-methodology.md` |
| API reference | Public classes, functions and signatures | Docstrings in `src/` and `dashboard/` |
| ADR | Architecture decisions and trade-offs (in French) | `docs/adr/` |
| Project history | Briefs, audit, plans and research that led to the current methodology; they do not necessarily describe the current state and keep their original language (French) | `docs/plans/`, `docs/implementation-plans/`, `docs/research/` |

## Living documentation

The API reference is built on the fly by `mkdocstrings` from the current code. A
docstring change shows up at the next build without manual synchronisation.

Every pull request and every merge into `main` runs a strict build
(`make docs-build`). The site is not published online: `make docs-serve` serves
it locally.
