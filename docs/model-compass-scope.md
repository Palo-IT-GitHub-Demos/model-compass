# Model Compass — scope and decision logic

This page sets out the change of positioning decided on 8 and 9 September
2026. The repository no longer only produces a screening signal ahead of
another evaluation: it produces a generic technical recommendation report,
organised by use case, to help a human answer calls for tender.

## Mission

**Model Compass** evaluates the LLMs available through OpenRouter on a stable
catalog of generic use cases. It measures functional quality, security, model
cost and performance, then gives for each use case:

- a detailed score for every evaluated model;
- a minimum quality threshold suited to the use case;
- a ranking of the models that pass this threshold;
- one or more recommended models;
- the evidence, limits and missing dimensions that explain the result.

The report is a **technical recommendation**. The final selection belongs to a
human who knows the call for tender, its context and its constraints.

## Stability principle

The pipeline is deliberately generic and reusable:

- it does not receive the content of a call for tender;
- it does not receive client-specific criteria;
- it uses no client dataset or confidential business data;
- it uses a versioned catalog of generic use cases and prompts;
- it produces the same kind of report on every run;
- it can change between two catalog versions, but must not be reconfigured for
  each call for tender.

The human then matches the generic results to the needs of the tender they
know.

## Active catalog

The default catalog is `data/catalog/model_compass_use_cases_v3.json`
(`model-compass-use-cases-v3.2`, suite `generic-screen-v3`). It maps the 40
quality prompts to eight use cases, five prompts each:

| Use case | Prompts | Threshold |
| --- | ---: | ---: |
| Structured extraction | 0-4 | 4.0 / 5 |
| Code generation | 5-9 | 4.0 / 5 |
| Contextual question answering | 10-14 | 4.0 / 5 |
| Reasoning and analysis | 15-19 | 4.0 / 5 |
| Classification and routing | 20-24 | 4.0 / 5 |
| Summarization | 25-29 | 3.5 / 5 |
| Concise communication | 30-34 | 3.5 / 5 |
| Instruction following | 35-39 | 4.0 / 5 |

The thresholds are calibrated on the reference run (see
[Why these thresholds](#why-these-thresholds)). Changing the catalog changes the
benchmark version and must be visible in the results.

### Earlier catalogs

The v2 catalog (`model_compass_use_cases_v2.json`, 34 prompts, eight use cases)
and the v1 catalog (`model_compass_use_cases.json`, 16 prompts, six use cases)
stay available with `QUALITY_SUITE=v2` or `v1`, only to merge again the runs
collected with them. Their thresholds were provisional starting values.

## Decision logic

The decision has two independent levels.

### 1. Quality eligibility

For each `use case / model` pair, the **content** scores of the catalog's
prompts are averaged per prompt. Format compliance rows
(`output_format_compliance`) are left out: they are published apart, in the
`format_compliance_rate` column, so that a correct answer that breaks the
"answer only" format never lowers the use case's quality. Coverage gives the
share of the use case's prompts actually scored.

```text
quality eligible =
    use case quality >= use case threshold
    and quality coverage = 100 %
```

A model below the threshold is not recommended for this use case, even if it is
cheaper or faster. Every model nevertheless stays visible in the report with its
score and status.

### 2. Weighted ranking

The decision score uses four components normalised to 0-100:

| Component | Default weight | Source |
| --- | ---: | --- |
| Functional quality | 50 % | Quality score of the use case, 1-5 scale normalised |
| Generic security | 25 % | RSI, 0-100 scale |
| Model-only cost | 20 % | Cost of 1,000 profile requests with the model's measured output length; fixed logarithmic anchors in the catalog |
| Performance | 5 % | p95 latency; fixed logarithmic anchors in the catalog |

```text
decision_score =
    quality_weight × quality
  + security_weight × security
  + cost_weight × cost
  + performance_weight × performance
```

The default weights come from the catalog. `MODEL_COMPASS_WEIGHTS` replaces
them without a code change, for example:

```bash
MODEL_COMPASS_WEIGHTS='{"quality":0.60,"security":0.20,"cost":0.15,"performance":0.05}' make merge
```

Weights must be positive and sum to `1.0`. The report and the manifest always
record the weights actually used. A run collected with `SECURITY=skip` sets the
security weight to 0 and rescales the other three (0.67 / 0.27 / 0.07 by
default); the report flags it on every page.

### Why these weights

A weight is not justified on its own: what matters is the trade-off it imposes
between two components, on the catalog's fixed anchors. One quality point on the
1-5 scale is worth 25 points of the quality component. Cost loses 33.3 points
per decade of cost (anchors 0.05–50 USD per 1,000 requests, three decades),
performance 67.7 points per decade of p95 latency (anchors 1–30 s), and security
one point per RSI point. `implied_tradeoffs`
(`src/evaluators/recommendation.py`) computes these trade-offs; the report shows
them on the *Use cases in detail* page.

| Profile | Quality | Security | Cost | Perf. | 1 quality point is worth | A 10× lower price is worth | A confirmed leak costs |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| `quality_first` | 70 % | 20 % | 7 % | 3 % | more than any price gap | 0.13 point | ≥ 0.4 point |
| `balanced` (default) | 50 % | 25 % | 20 % | 5 % | a 75-fold price gap | 0.53 point | ≥ 0.7 point |
| `cost_sensitive` | 35 % | 20 % | 40 % | 5 % | a 4.5-fold price gap | 1.52 points | ≥ 0.8 point |

"A confirmed leak costs" is a minimum: the RSI of a leaking model is brought
below 65, so at least 35 RSI points are lost.

**The `balanced` default (50/25/20/5).**

- **Quality 50 %.** A model one point better beats a model 75 times cheaper;
  for half a point, the price gap must stay below 9 times. That is the order of
  magnitude between a frontier model and an economy model: half a point of
  difference justifies paying for the frontier model, a tenth of a point does
  not. When the eligible models are statistically tied on quality, as in the
  0.4.0 reference run, cost decides, and that is intended: at indistinguishable
  quality, paying more has no generic justification.
- **Security 25 %.** A confirmed leak costs at least 0.7 quality points, the
  equivalent of a 20 times higher price: a model that discloses its hidden
  context must be clearly better to stay first. Security stays compensatory,
  because the RSI only measures a narrow scope (disclosing a secret); a tender
  where security is eliminatory must apply it as an exclusion criterion,
  outside the tool.
- **Cost 20 %.** It separates models of close quality without being able to buy
  back a real quality gap: over the whole anchor range (a factor of 1,000), it
  is worth only 1.6 quality points.
- **Performance 5 %.** A ten times higher p95 latency is worth only 0.27
  quality points: the default workload profile (`enterprise_qa`) handles
  questions where a few seconds do not invalidate an answer. An interactive
  application should use another profile or `MODEL_COMPASS_WEIGHTS`.

**The other two profiles.**

- `quality_first`: over the whole anchor range, cost is worth only 0.4 quality
  points; it only separates models that are already close. For critical answers
  (legal, medical, binding decisions).
- `cost_sensitive`: one quality point is worth a 4.5 times lower price. For high
  volume or a tight budget, when a slightly weaker but much cheaper model is
  still acceptable.

The profiles never change the published rank, which follows the run's weights.
They show whether the recommendation holds under the profile that fits the call
for tender: a card marked *weight-profile-sensitive* names the leader of each
profile, and the human keeps the one whose profile fits the tender. The rank
range under ±10 % (*fragile*) completes this reading for small changes around
the chosen profile.

### Why these thresholds

A use case's threshold is **non-compensatory**: a model below it is excluded,
whatever its price. With five items per use case:

- **4.0 / 5 for the use cases with a deterministic check.** A passed item is
  worth 5, a failure 1, and partial credit gives a value in between. One full
  failure out of five gives (4 × 5 + 1) / 5 = 4.2 and stays eligible; two
  failures give 3.4 and exclude. The threshold therefore tolerates one error out
  of five, not two. A correct answer outside the format contract (3) on two
  items gives 4.2: eligible, but on three items 3.8 excludes.
- **3.5 / 5 for summarization and concise communication**, scored by the judges
  on a graded scale: 3 means a criterion is only partly met, 4 that a minor
  defect outside the criteria remains. 3.5 requires the answer to be, on
  average, closer to "minor defect" than to "partial criterion", which leaves
  room for the varying severity of judges on partly subjective criteria.

**Calibration on the reference run.** The run collected on 3 November 2026
(`run_20261103_121614`) is the reference. Collected under 0.7.0, it was merged
again under 0.8.0 (`results/benchmark_20261103_154602`): 0.8.0 only changes how
exact answers are read, applied at merge to the stored raw responses, so a new
collection would have sent the same requests. The manifest records both
versions (`collected_methodology_version`). Identifiers: `quality_suite_id`
`generic-screen-v3-be713fff517f`, catalog `v3.2`, `security_probe_set_id`
`full-fafdd3e07f92`, default weights, profile `enterprise_qa`, six models. The
thresholds separate the models without ambiguity:

| Use case | Threshold | Lowest eligible | Best excluded |
|---|---:|---|---|
| Structured extraction | 4.0 | 4.20 (Claude Sonnet 5.5) | 2.23 (Llama 3.3 70B) |
| Code generation | 4.0 | 4.44 (GPT-6 Luna) | 3.74 (Llama 3.3 70B) |
| Contextual question answering | 4.0 | 4.73 (GPT-6 Luna) | 1.80 (Llama 3.3 70B) |
| Reasoning and analysis | 4.0 | 4.20 (Llama 3.3 70B) | none |
| Classification and routing | 4.0 | 4.20 (Claude Sonnet 5.5) | 3.13 (Llama 3.3 70B) |
| Summarization | 3.5 | 4.60 (Gemini 3.8 Flash) | 3.16 (Llama 3.3 70B) |
| Concise communication | 3.5 | 4.09 (Claude Sonnet 5.5) | 3.40 (Llama 3.3 70B) |
| Instruction following | 4.0 | 4.36 (GPT-6 Luna) | 3.27 (Claude Sonnet 5.5) |

The lowest eligible models are at 4.20, exactly one failed item out of five; no
model falls between 3.75 and 4.0, where a single attempt would flip eligibility.
The 4.0 thresholds of the deterministic use cases are therefore **calibrated**
without change. Under 0.7.0, Llama 3.3 70B was excluded from reasoning at 3.40
because its correct `= 3/10` answers were not read; under 0.8.0 it is eligible,
at the limit of one error out of five.

**Review of the judged answers.** The 3.5 thresholds of summarization and
concise communication rest on the judge panel. To calibrate them, 50 judged
answers of this run were reviewed and scored with the same rubric (criteria and
anchors of each item): the 11 judged items, the six models, with more weight on
judge disagreements and intermediate scores. The review was done **blind**
(model name and judge scores hidden) by **Claude (Anthropic)**, then **checked
and approved by a human**, the project maintainer, who read the scores and their
reasons. The reviewer belongs to the same family as one evaluated model and one
of the three judges; the human approval covers its scores, it does not replace
an independent human scoring.

| Measure | Result |
|---|---|
| Scores equal to the panel mean | 27 / 50 |
| Gap of at most 1 point | 48 / 50 |
| Mean gap (reviewer − panel) | +0.26: the panel is slightly stricter |
| Order of the models on the sample | identical, except GPT-6 Luna and Gemini 3.8 Flash (0.04 point apart) |

The two gaps above one point concern a 50-word answer for a 45-word limit,
which the three judges score 2 and the reviewer 4, and an answer that two
judges find imprecise about "the slowest responses". Each judge has blind spots
that the mean offsets: the Google judge accepts an answer that promises an
immediate refund, which the criteria forbid; the OpenAI judge accepts double
questions where a single one is asked, but it is the only one to notice that a
summary says marketing "was moved" when the text says it was informed. The
reviewer had missed it and corrected these three scores after unblinding. Even
with the reviewer's lower severity, Llama 3.3 70B stays below 3.5 on the sample
(3.0 in concise communication, 3.4 in summarization) and the other five models
stay above 4.0.

The 3.5 thresholds are therefore **calibrated** without change, with two
caveats: the scores come from an AI reviewer approved by a human, not from an
independent human scoring, and the exclusion of Llama 3.3 70B in summarization
(3.16 for the panel, 3.4 for the reviewer) rests on a small margin. The detail
of the 50 scores is kept locally in
`results/calibration/judged_review_20261103_143403.csv`.
A run is comparable with this reference only when its identifiers are identical
(see [the quality methodology](quality-methodology.md)).

The catalogs `model-compass-use-cases-v1.2`, `v2.2`, `v3.1` and `v3.2` set the
bounds of the computation: 0.05–50 USD per 1,000 profile requests and 1–30
seconds for p95 latency. The cost of a request is the profile's input size at
the input price, plus the output length the model really produced on the
quality suite at the output price: the listed price alone ignores that a model
cheap per token can produce ten times more of them. The former anchors
(0.10–100 USD per million tokens) also covered three decades, so the trade-offs
above do not change. Below the better bound the score is 100; above the worse
bound it is 0; in between the scale is logarithmic. A zero cost (free model) is
worth 100. These scores are not recomputed relative to the run's models. If p95
latency is missing, the performance evidence is absent; tokens per second do not
replace it.

If a component is missing, the model stays visible but gets the
`insufficient_decision_evidence` status and no recommendation rank. The pipeline
never silently replaces missing evidence with a favourable value.

## Ties and statuses

The ranking uses a dense rank. There is no artificial tie-breaking rule: several
models with exactly the same score keep the same rank and can all be
`recommended`.

The statuses are:

- `recommended`: best rank among the eligible and sufficiently documented
  models, or a ranked model that a ±10 % change of one weight or of the
  threshold would put first (`recommendation_sensitivity_rank_min = 1`, rank
  unchanged): the card then shows *Recommended (too close to call)*;
- `eligible`: passes the threshold and has the required evidence, but not the
  best rank;
- `below_quality_threshold`: quality too low for this use case;
- `insufficient_quality_evidence`: quality coverage or score missing;
- `insufficient_decision_evidence`: quality eligible, but security, cost or
  performance missing.

The number of evaluated or displayed models is not artificially limited.

## Security, compliance and cost

Security is generic and comparable across models: prompt injection, secret
disclosure, obedience to hidden instructions and the retention policies
available through OpenRouter.

The pipeline does not decide automatically on compliance with a client
requirement such as data location, HDS, SecNumCloud, a specific certification or
a contractual SLA. A human checks these points.

Cost covers the model only: input tokens, output tokens, projected TCO and the
actual cost observed when available. It excludes infrastructure, RAG, storage,
orchestration, integration, monitoring and the licence of a complete solution.

## Artifacts and surfaces

The summary benchmark stays one row per model:

```text
results/benchmark_<timestamp>.{csv,json}
```

The recommendation detail is kept apart to hold several rows per model:

```text
results/recommendations/benchmark_<timestamp>_recommendations.{csv,json}
```

Each row of this artifact is a `use_case_id / model` pair and holds the
threshold, the coverage, the four components, the weighted score, the rank, the
status and the missing evidence. The HTML report (`make export-html`) shows this
same artifact.

## Out of scope

Model Compass does not perform:

- automatic analysis of tender documents or specifications;
- extraction of client-specific requirements;
- automatic customisation of the prompts for a call for tender;
- evaluation on confidential data or a real business workflow;
- recommendation of a complete architecture;
- computing the total cost of a solution;
- automatic selection of a final provider;
- regulatory certification;
- the final adoption decision;
- automatic generation of a commercial response.

## Remaining methodological work

The thresholds of the eight use cases are calibrated on the 0.8.0 reference
run. Still open:

1. score the judged items independently by a human, beyond the approved AI
   review;
2. check that the thresholds and weights stay stable on the next runs and on
   other sets of models;
3. compare the generic recommendations with `gen-e2-eval` on the same models,
   without mixing the two kinds of evidence.

The thresholds and the catalog must therefore not be presented as a
certification of business relevance.
