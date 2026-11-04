# Model Compass presentation

Two slides that summarise methodology 0.8.0: what Model Compass measures, and
how it recommends a model for each use case. They are marked PALO IT
confidential: do not share them outside the organisation.

[Download the PowerPoint file](assets/model-compass/model-compass-overview.pptx)
(the speaker notes detail each slide).

## What we measure

![Every model gets the same four measurements: quality, security, cost and speed](assets/model-compass/slide-1.png)

Every model runs the same 40 generic tasks (5 per use case, 3 attempts) and the
same 66 security probes. See the [quality methodology](quality-methodology.md)
and the [security methodology](security-methodology.md).

## How we recommend

![No model recommended below the quality bar: gate, rank, stress-test](assets/model-compass/slide-2.png)

Quality is a gate: a model below a use case's threshold is never recommended.
Eligible models are ranked with the *balanced* profile (50 / 25 / 20 / 5); the
*quality-first* (70 / 20 / 7 / 3) and *cost-sensitive* (35 / 20 / 40 / 5)
profiles are shown beside it without changing the published rank. The
thresholds are calibrated on the reference run of 3 November 2026 (see
[the scope](model-compass-scope.md)).

## Updating the slides

The source file is `docs/assets/model-compass/model-compass-overview.pptx`.
After a change, export the two images `slide-1.png` and `slide-2.png` again
(1600 pixels wide) from PowerPoint, so that this page stays true to the file.
