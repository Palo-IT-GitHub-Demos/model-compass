# Report reading guide

This guide is for the person who chooses one or more models for a call for
tender from the HTML report (`results/dashboard_<timestamp>.html`). It needs no
knowledge of the pipeline. The page titles of the report are quoted as they
appear below.

## What the report answers, and what it does not

The report answers: **"which models are technically relevant for this kind of
generic use case, and how certain is that?"**

It does not answer "which model should this client adopt". It knows neither the
call for tender, nor the client's data, nor their compliance requirements (data
location, certification, SLA). Matching the generic use cases to the tender
remains your job.

## 1. Check the banner first

An orange **"Not reference-grade evidence"** banner at the top of the page means
the run does not follow the standard path: simulated data, an older methodology,
fewer than three attempts per prompt, security skipped or a non-standard probe
set, or incomplete coverage. The figures stay readable, but **do not base a
recommendation on this run alone**. If security was skipped, models are ranked
without it: do not use this report for a tender where prompt injection or data
disclosure matters.

A blue note under the banner flags a limit that does not disqualify the run: a
few answers lost to a technical error, or security probes left unanswered for a
model (its RSI then rests on fewer attempts; the `Security` page names them).

The grey line "Compare runs only when all of these match" lists the methodology
version, prompt suite, catalog, probe set, weights and workload profile. Two
reports are comparable only when all of these values are identical.

## 2. Read the decision summary (`Decision summary`)

Each card is one generic use case (structured extraction, code generation,
summarisation, and so on) and shows, in order:

| Element | Meaning | What to do |
| --- | --- | --- |
| **Recommended** | Best decision score among the models that pass the use case's quality threshold with complete evidence. Several names (*too close to call*) = exact ties, or models that a 10 % change of one weight or of the threshold would put first, from the best score down. | Starting point of the choice; between several names, decide on the tender's criteria. |
| **fragile** badge | The ranking or the eligibility changes if one weight, or the threshold, moves by 10 %. | Treat the next model as a serious alternative. |
| **judge-sensitive** badge | Without the judge from the model's own provider (for example the Claude judge for an Anthropic model), the recommended model would change; the card names the alternative. | Treat the recommendation as unconfirmed and compare the two named models. |
| **weight-profile-sensitive** badge | The recommended model changes with the weight profile (`quality-first`, `balanced`, `cost-sensitive`); the card names the leader of each profile. | Keep the leader of the profile that fits the tender: `quality-first` for critical answers, `cost-sensitive` for high volume or a tight budget, `balanced` otherwise. |
| **same leader** badge | The recommended model is the same under all three weight profiles. | The recommendation does not depend on the weighting. |
| **disputed key** badge | On one prompt of the use case, most models give the same answer, which the answer key rejects. | Have that prompt reviewed before relying on the ranking. |
| **Also eligible** | Passes the threshold but scores lower. | Alternative if a constraint rules out the leaders. |
| **cannot be ranked (missing evidence)** | Quality is sufficient, but a security, cost or performance measurement is missing. | Do not select it without completing the measurement. |
| **Below the quality threshold** | Quality too low for this use case, whatever its price. **borderline**: the confidence interval overlaps the threshold. | Do not select it; a *borderline* model may deserve a test on client data. |
| **No model can be recommended** | No evaluated model fits this use case. | Widen the set of models or revisit the need. |

## 3. Go further when needed

| Page | Open it when… |
| --- | --- |
| `Use cases in detail` | you want the detail of the components (quality, security, cost, performance), the confidence interval, the rank range under ±10 %, the rank under each weight profile and the *Format respected* column (compliance with the required format, scored apart from quality). The *Weight profiles* table turns each profile into concrete trade-offs, for example "1 quality point is worth a 75-fold price gap". |
| `Security` | security is a strong criterion of the tender. The RSI only measures resistance to disclosing a secret; the *Scored probes measured* column shows how many attempts it rests on, and the "Observations — not scored" section lists what is **not** measured. |
| `Cost` | you need to budget: the TCO is a monthly projection for a workload profile, not the cost of the test. |
| `Performance` | latency matters for the intended use (p95 = response time of the slow cases). |
| `Prompts & responses` | you want to read the prompts, the answers and each judge's reasoning. Filters show one model's failed prompts, or several models side by side on one prompt. |
| `Quality × cost` | you want an overview. **Do not choose from this page**: it ignores the per-use-case thresholds and security. |
| `Glossary` | a term or an acronym is unclear. |

## 4. Before deciding

- The warning banner is absent, or its reasons are acceptable for the intended
  use.
- Every use case of the tender has been matched to a card of the report.
- A **fragile** or *too close to call* recommendation has been settled on an
  explicit criterion of the tender.
- Out-of-scope requirements (compliance, hosting, contract) have been checked
  separately.
- If a client-specific dataset exists, the final choice is confirmed with
  `gen-e2-eval`.
