---
applyTo: "src/**,scripts/**,dashboard/**,data/prompts/**,data/catalog/**,Makefile,.github/**"
---

Every change to these files must update `CHANGELOG.md` in the same change, before
reporting the task as done:

- Add a short entry under `## [Unreleased]`, in the matching `### Added`,
  `### Changed — methodology <version>` or `### Fixed` subsection (create it if missing).
- Write for a user of the pipeline: what changed and its visible effect, not how
  it was coded. No test counts.
- A change that can alter scores, eligibility or ranks of an identical run also bumps
  `METHODOLOGY_VERSION` (`src/core/methodology.py`) and goes under the methodology heading.
- A refactor with no visible effect still gets a one-line entry under `### Changed`.

CI fails a pull request that touches code, prompts or the catalog without a
`CHANGELOG.md` change.
