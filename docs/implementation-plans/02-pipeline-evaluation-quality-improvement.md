# Plan d'implémentation : 02 — Amélioration du pipeline et de la qualité d'évaluation

Ce plan corrige les points faibles identifiés lors de l'état des lieux du
2026-10-12. Il prolonge les phases 3 et 4 du plan 01 et l'ADR 0002.

## Points faibles ciblés

- Suite qualité réduite : 16 prompts, majoritairement élémentaires, un seul
  prompt de code et deux de communication ; seuils provisoires.
- Panel de 3 juges LLM affiliés à des providers benchmarkés, sans calibration
  humaine ni mesure d'accord formelle.
- Sécurité mono-tour, 7 catégories OWASP scorées sur 10 ; le profil `extended`
  ne couvre que LLM01.
- Peu de robustesse statistique (pas d'intervalle de confiance).
- Évaluation multi-tour absente côté qualité.
- `src/main.py` monolithique (~2 000 lignes).

## Priorité 0 — Prérequis

| Statut | Tâche | Critère de réussite |
| --- | --- | --- |
| Fait | Baseline avec `.venv` (`make test`, `ruff`, `mypy`, `mkdocs build --strict`) | 393 tests passent ; ruff, mypy et mkdocs verts |
| Fait | Commiter l'ADR 0002, la recherche et les plans | Commit `docs(...)` isolé, arbre propre hors résultats |

Note : les 17 erreurs de collecte observées venaient du shell, qui utilisait
`python` (pyenv) au lieu de `.venv`. Le `Makefile` utilise déjà
`PYTHON ?= .venv/bin/python`. Toujours passer par `make` ou `.venv/bin/python`.

## Axe A — Qualité de l'évaluation

### A1. Élargir et durcir la suite de prompts

- Blueprint de tâche v2 : construit, type d'évaluateur, échelle, difficulté,
  source, version.
- 8 à 12 items par cas d'usage, par vagues, avec `catalog_version` incrémenté.
- Items discriminants (contraintes multiples, extraction bruitée, raisonnement
  multi-étapes, instructions contradictoires, FR/EN).
- Code : exécution de tests unitaires en sandbox (timeout, sans réseau).
- Sortie : aucun item saturé ni nul pour tous les modèles sur un run pilote.

### A2. Mesurer la qualité de la suite

- Pouvoir discriminant par item (variance inter-modèles), corrélation
  item-total, détection des items saturés.
- Items canari de réponse connue pour détecter une régression du pipeline.

### A3. Fiabiliser les juges LLM

- Rubriques ancrées par dimension (exemples à 1, 3 et 5).
- Accord inter-juges (kappa pondéré ou alpha de Krippendorff) avec alerte sous
  seuil, en plus de `judge_disagreement`.
- Tests de biais : ordre, longueur, auto-préférence.
- Jeu de calibration humain (30 à 50 réponses annotées) et corrélation
  juges/humain.
- File de relecture humaine des divergences, sans réécrire le score brut.
- Aucune correction automatique de biais sans calibration qui la justifie.

### A4. Robustesse statistique

- `QUALITY_REPETITIONS >= 3` pour les runs de référence, intervalles de
  confiance par bootstrap.
- Égalité statistique signalée quand les IC se chevauchent ; le rang dense
  reste sans départage arbitraire.
- Seuils calibrés sur la distribution observée et l'annotation humaine, figés
  par `catalog_version`.

### A5. Évaluation multi-tour

- Petite suite bornée (8 à 10 scénarios, deux tours) via `scenario_runner.py`.
- Même rubrique et mêmes garde-fous ; score séparé du mono-tour tant que la
  comparabilité n'est pas validée.

### A6. Anti-contamination et traçabilité

- Variantes paramétrées déterministes (graine fixée) pour les items très
  diffusés.
- Hash de suite, version des rubriques et juges enregistrés dans le manifeste.

## Axe B — Sécurité

- B1 : étendre `extended` aux catégories LLM02, LLM03, LLM07 et LLM10.
- B2 : valider l'intégration des scénarios séquentiels avant de les inclure
  dans le RSI.
- B3 : détecteur secondaire (règles ou juge) et mesure des faux positifs et
  négatifs sur un jeu annoté.
- B4 : sondes répétées (k >= 3) et RSI avec incertitude.
- LLM04, LLM06 et LLM09 restent explicitement « non scorées ».

Jalon 4 (partiel) : B1 ajoute 8 sondes `extended` aux catégories LLM02,
LLM03, LLM07 et LLM10 ; B3 améliore la preuve de fuite (canary entier, y compris
base64) avec des cas annotés contre les faux positifs. Ce n'est pas un
détecteur calibré pour toutes les vulnérabilités OWASP : la calibration humaine
et les taux mesurés de FP/FN restent à faire. B2 (comparabilité des scénarios)
et B4 (répétitions et incertitude RSI) ne sont pas terminés.

## Axe C — Coût, performance, recommandation

- C1 : mesures de performance répétées, médiane, p50/p95 avec nombre
  d'échantillons.
- C2 : test de sensibilité du classement (poids ±10 %, seuils) et alerte sur
  les recommandations fragiles.
- C3 : afficher la preuve manquante derrière chaque
  `insufficient_decision_evidence`.

## Axe D — Qualité d'ingénierie

- D1 : découper `src/main.py` par pipeline sans changer le comportement.
- D2 : test de non-régression par snapshot d'un dry-run.
- D3 : CI lint, types, tests, `mkdocs build --strict` ; mise à jour de
  `CHANGELOG.md` et `AGENTS.md` à chaque changement de comportement.

## Ordre d'exécution

Statut : étape 1 faite ; étape 2 faite sauf les exemples ancrés de rubrique,
reportés à l'étape 4 (ils changent le comportement des juges et exigent le jeu
de calibration humain). Livré : `src/evaluators/quality_diagnostics.py`
(analyse des items, alpha de Krippendorff), export `results/quality_analysis/`.

Étape 3 (vague 1 de A1) faite, puis reprise après diagnostic de la v1 : suite
`generic-screen-v2` indépendante (34 items originaux, blueprint ADR 0002,
`QUALITY_SUITE=v2`), catalogue v2, sandbox de code opt-in
(`QUALITY_CODE_EXECUTION`). Restent : un run pilote réel pour vérifier
qu'aucun item n'est saturé et calibrer difficulté et seuils, puis le dialogue
multi-tour (A5). Le multilingue est différé (« ADAPT LATER » dans la
cartographie) ; `generic-screen-v2` est devenue le défaut de `QUALITY_SUITE`
avant ce pilote, `generic-screen-v1` restant la référence historique.

| Étape | Contenu | Dépend de |
| --- | --- | --- |
| 1 | Priorité 0 | — |
| 2 | A2 + rubriques et métriques d'accord (A3) | 1 |
| 3 | A1, vague 1 (code sandboxé, communication, extraction) | 2 |
| 4 | Jeu de calibration humain (A3) | 3 |
| 5 | A4 + C2 | 3, 4 |
| 6 | B1, B3, B4 | 1 |
| 7 | A5 + B2 | 5, 6 |
| 8 | D1, D2 en continu | — |

Dette technique D1 (extraction initiale) : parsing CLI, exécution concurrente
des étapes de collecte, calcul de la matrice fusionnée et sérialisation des
artefacts disposent désormais de modules dédiés. `src/main.py` conserve les
classes d'orchestration et les symboles historiques comme façade ; la
reconstruction des verdicts juges et les chemins dry-run/verify restent dans
cette façade. D2 (snapshot de non-régression dry-run) reste à traiter.

Jalon 3 (A4/C2, partiel) : les IC bootstrap 95 % et la sensibilité locale aux
poids et seuils ±10 % sont intégrés aux exports. L'étape 5 n'est pas close :
la calibration humaine de l'étape 4, le pilote réel v2 et le recalibrage des
seuils par version du catalogue restent à effectuer. Les intervalles et alertes
ne constituent pas à eux seuls une validation statistique des recommandations.

## Risques

- Coût : plus d'items, de répétitions et de juges ; utiliser `make dry-run`,
  `make verify` et les budgets d'erreur.
- Charge humaine : la calibration exige des annotateurs ; sans elle, la
  corrélation juges/humain reste non prouvée.
- Changement de `catalog_version` : les nouveaux résultats ne sont plus
  comparables aux anciens ; le versionnage doit rester visible.
