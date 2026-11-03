# Model Compass

Pipeline de **recommandation technique, comparative et reproductible** des
modèles disponibles sur OpenRouter. Model Compass compare les modèles sur des
critères transverses de qualité, sécurité, coût du modèle et performance, puis
les classe par cas d'usage générique pour aider un humain à répondre à
différents appels d'offres.

Le [scope détaillé](model-compass-scope.md) formalise les décisions prises, les
limites et les seuils du catalogue, calibrés sur le run de référence 0.7.0.

## Par où commencer

Le parcours standard tient en sept étapes, détaillées dans le Quick Start du
`README.md` et dans le [workflow](workflow.md) :

```bash
make select                                                         # choix des modèles, $0
make verify MODELS=selection    # clé et modèles, $0
make collect MODELS=selection   # seule étape payante
# Copilot Chat : @judge-coordinator                                 # jugement aveugle
make merge && make export-html                                      # résultats et rapport
```

Chaque rapport affiche sa version de méthodologie (la release qui a fixé les
règles de calcul, actuellement `0.3.0`), sa suite qualité, son catalogue, son
jeu de sondes, ses poids et son profil de charge. Deux runs ne se comparent que
si toutes ces valeurs sont identiques.

## Quatre dimensions de mesure

| Axe | Ce que ça mesure | Sortie clé |
| --- | --- | --- |
| **Qualité** | 40 prompts versionnés (suite `generic-screen-v3`, 5 par cas d'usage), 8 dimensions + conformité de format notée à part, crédit partiel pour le JSON et le code testé dans le sandbox, score macro-moyen 1-5, couverture, stabilité et IC 95 % à partir de 3 essais | `avg_quality_score`, `quality_coverage_rate`, `quality_stability_score` |
| **Sécurité** | Un seul parcours de 66 sondes internes (50 notées, rejouées trois fois, dont 8 injections indirectes, 7 sondes d'obéissance à une consigne cachée et 3 scénarios multi-tours), exécuté en entier ou sauté, aligné sur l'[OWASP GenAI LLM Top 10 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/), score RSI 0-100 (pondération interne, non publiée par OWASP — cf. `_RSI_WEIGHTS` dans `security_scanner.py`), vérification ZDR | `rsi`, `leak_count`, `zero_data_retention` |
| **Coût** | Tarif OpenRouter × taille d'entrée du profil + longueur de sortie mesurée du modèle → coût pour 1 000 requêtes et TCO mensuel projeté + coût réel par appel (`response.usage.cost`) | `cost_usd_per_1k_requests`, `tco_usd`, `actual_cost_credits`, `cer` |
| **Performance** | Latence P50/P95 et tokens/seconde mesurés après acquisition du semaphore | `actual_latency_p50_ms`, `actual_latency_p95_ms`, `actual_tokens_per_second` |
| **Recommandation** | Catalogue versionné, seuil qualité par cas d'usage et score pondéré configurable | `results/recommendations/` |

## Voir les résultats

| Besoin | Action |
| --- | --- |
| Consulter le dernier rapport partageable | Ouvrir `results/dashboard_<timestamp>.html` ; sa navigation mène aux pages Qualité, Preuves, Sécurité et Coûts. |
| Générer le rapport HTML du dernier benchmark fusionné | Lancer `make export-html`. |
| Comprendre le rapport avant de décider | Lire le [guide de lecture du rapport](guide-lecture-rapport.md). |
| Choisir les modèles avant un run | Lancer `make select`, répondre aux filtres, puis utiliser `MODELS=selection`. |

Le [workflow du pipeline](workflow.md) indique les commandes dans l'ordre,
depuis la vérification gratuite jusqu'au rapport final.

## Parcours recommandés

- **Exécuter une évaluation** : suivre le [workflow du pipeline](workflow.md),
  de la configuration au tableau de bord.
- **Défendre ou auditer le score qualité** : consulter la
  [méthodologie qualité](quality-methodology.md) — provenance des prompts,
  couverture, validation et comparaison avec `gen-e2-eval`.
- **Comprendre le code** : consulter la [référence API Python](reference/api.md),
  générée directement depuis les docstrings du projet.
- **Comprendre les décisions** : lire les [Architecture Decision Records](adr/0001-architecture-initiale.md).
- **Contribuer** : suivre le [guide de contribution](https://github.com/Palo-IT-GitHub-Demos/model-compass/blob/main/.github/CONTRIBUTING.md).

## Positionnement par rapport à gen-e2-eval

Les deux projets répondent à des questions différentes et ne produisent pas
le même type de décision :

```text
Model Compass                gen-e2-eval
──────────────────────────   ────────────────────────────────
Tous les modèles évalués     Modèles testés sur les tâches métier

Question : « quel modèle      Question : « réussit-il
est pertinent par cas ? »    mes tâches métier ? »

→ recommandation technique    → acceptation métier
```

L'export `make export-gen-e2` génère un YAML injectable dans le registry
quadrant de gen-e2-eval avec les colonnes sécurité et TCO.

### Périmètre et règle de décision

Model Compass inclut :

- la comparaison à grande échelle de modèles accessibles via OpenRouter ;
- un screen de qualité générique, provider-neutral et versionné ;
- les mesures de coût, de latence et de sécurité ;
- la production d'un classement et d'un ou plusieurs modèles recommandés par
  cas d'usage générique ;
- un rapport de preuves sous `results/recommendations/`.

Model Compass n'inclut pas :

- la validation d'un workflow métier ou d'une golden dataset client ;
- la mesure de la réussite fonctionnelle sur un use case ;
- l'analyse automatique d'un appel d'offres ou l'extraction de ses exigences ;
- la recommandation finale d'adoption pour une application ;
- le remplacement de l'évaluation métier dans `gen-e2-eval`.

La règle de décision est donc la suivante : tous les modèles restent visibles,
le seuil qualité filtre l'éligibilité par cas d'usage, puis le score pondéré
classe les modèles dont les preuves sont complètes. Les égalités sont
conservées. Toute décision d'adoption reste humaine et peut être confirmée
dans `gen-e2-eval` sur les tâches métier concernées.

## Structure de la documentation

| Espace | Contenu | Source de vérité |
| --- | --- | --- |
| Guide du pipeline | Exécution, entrées, sorties et interprétation | `docs/workflow.md` |
| Scope Model Compass | Mission, logique de décision, limites et calibrations restantes | `docs/model-compass-scope.md` |
| Présentation | Deux slides : ce qui est mesuré, comment un modèle est recommandé | `docs/assets/model-compass/model-compass-overview.pptx` |
| Méthodologie qualité | Provenance des prompts, couverture, validation, comparaison `gen-e2-eval` | `docs/quality-methodology.md` |
| Référence API | Classes, fonctions et signatures publiques | Docstrings dans `src/` et `dashboard/` |
| ADR | Décisions d'architecture et compromis | `docs/adr/` |
| Historique du projet | Briefs, audit, plans et recherche ayant mené à la méthodologie actuelle ; ne décrivent pas forcément l'état courant | `docs/plans/`, `docs/implementation-plans/`, `docs/research/` |

## Documentation vivante

La référence API est construite à la volée par `mkdocstrings` à partir du code
courant. Une modification de docstring est visible au prochain build sans
synchronisation manuelle.

Chaque pull request qui modifie les documents ou les sources Python lance une
validation stricte (`make docs-build --strict`). Après une fusion sur `main`,
GitHub Actions reconstruit et publie le site sur GitHub Pages.
