# Référence API

Cette page est générée directement depuis les docstrings des modules Python du
pipeline via le plugin `mkdocstrings`. Toute modification de docstring dans le
code source est reflétée ici au prochain `make docs-build` — aucune synchronisation
manuelle n'est nécessaire.

## Configuration

::: src.core.config

## Client OpenRouter

::: src.api.openrouter_client

## Évaluateurs

### Coût

::: src.evaluators.cost_analyzer

### Qualité — pré-évaluation déterministe

::: src.evaluators.deterministic_eval

### Qualité — collecte et fusion des scores

::: src.evaluators.quality_judge

### Qualité — agrégation des métriques

::: src.evaluators.quality_metrics

### Model Compass — recommandations

::: src.evaluators.recommendation

### Sécurité

::: src.evaluators.security_scanner

## Observabilité

::: src.observability.tracker

## Orchestrateur du pipeline

::: src.main

## Tableau de bord

### Frontière de Pareto

::: dashboard.pareto

### Visualisations de sécurité

::: dashboard.security_viz
