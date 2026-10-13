# Principes de conception Model Compass

**Phase :** 2 — synthèse comparative et décisions méthodologiques
**Statut :** accepté pour la conception de la méthodologie v2
**Date :** 2026-09-10

Ce document transforme l'étude de HELM, MMLU/MMLU-Pro, BIG-bench,
MT-Bench et SWE-bench en règles de conception pour Model Compass. Il ne
recommande pas de copier les benchmarks ni d'importer leurs scores.

## Décisions de transfert

| Benchmark | Décision | Ce qui est retenu | Ce qui est explicitement exclu |
|---|---|---|---|
| HELM | **ADAPT** | Séparation scénario/métrique/provenance, évaluation multidimensionnelle, inspection des preuves | Score HELM global, copie du framework complet, fusion de métriques incompatibles |
| MMLU / MMLU-Pro | **ADAPT** | Reporting par domaine, QCM déterministe, baseline de hasard, analyse de sensibilité au prompt | Questions publiques, score de connaissance utilisé comme qualité métier globale |
| BIG-bench | **ADAPT** | Task blueprint, mots-clés, métriques déclaratives, sous-tâches, revue de qualité des items | Import de 200+ tâches, moyenne arbitraire de tâches hétérogènes, contenu public copié |
| MT-Bench | **ADAPT** | Petites trajectoires multi-tour, rubriques atomiques, verdicts individuels, désaccord inter-juges | Score publié, juge unique comme vérité, confusion entre préférence et exactitude |
| SWE-bench | **ADAPT / OBSERVE** | Distinction modèle/système, validation par tests, statuts d'environnement, filtrage humain des tâches | Exécution de SWE-bench dans `make collect`, attribution au modèle seul, code généré exécuté sans sandbox |

## Principes obligatoires

### P1 — Un benchmark externe informe la conception, pas le score

Les scores publiés par HELM, MMLU-Pro, BIG-bench, MT-Bench ou SWE-bench restent
une **évidence externe**. Ils ne sont pas injectés dans
`recommendation_score`.

Une fusion ne serait défendable que si le construit, l'unité, le protocole,
l'échelle, la population de modèles et le niveau de preuve étaient comparables.
Ce n'est pas le cas entre un QCM, un jugement conversationnel et un taux de
patchs qui passent des tests.

**Règle d'implémentation :** les résultats externes vivent dans les dossiers de
recherche et, plus tard, dans une table d'évidence séparée. Le benchmark
principal ne reçoit aucune colonne externe silencieuse.

### P2 — Un item possède un construit principal

Chaque tâche doit déclarer ce qu'elle mesure principalement : extraction,
factualité, raisonnement, communication, code, etc. Le format de sortie, le
contenu, la sécurité et le style sont des dimensions séparées lorsqu'ils sont
évalués.

Un prompt ne peut pas être présenté à la fois comme test de code, de style et de
factualité sans préciser les sous-métriques correspondantes.

**Règle d'implémentation :** ajouter au blueprint `construct`, `evaluator` et
`metric_ids`. Les rubriques doivent interdire au juge de noter une préférence
qui n'appartient pas au construit déclaré.

### P3 — Le scénario, la métrique et la recommandation sont trois objets

Un scénario décrit une situation et une tâche. Une métrique décrit comment la
réponse est évaluée. La recommandation combine ensuite des preuves compatibles.

Cette séparation suit l'idée centrale de HELM et évite de rendre un prompt
responsable d'une pondération globale qu'il ne justifie pas.

**Règle d'implémentation :** conserver au minimum `use_case_id`, `item_id`,
`metric_id`, `score_scale`, `evaluator`, `rubric_version` et
`methodology_version` dans les preuves.

### P4 — Les preuves brutes précèdent tous les agrégats

Une ligne de classement doit être traçable jusqu'au prompt, aux messages, à la
réponse, au résultat de l'évaluateur et à la version de la suite. Une erreur de
transport reste une erreur technique ; une réponse incorrecte reste une erreur
qualité.

**Règle d'implémentation :** ne jamais réécrire les réponses historiques ;
utiliser des sidecars pour vérification, calibration et reproductibilité. Les
benchmarks de référence renforcent ce principe par leurs exports de réponses,
leurs manifestes ou leurs harnesses versionnés.

### P5 — La couverture par catégorie est obligatoire avant l'agrégat global

Model Compass publie d'abord les résultats par item, famille et cas d'usage. Le
score global n'est autorisé que lorsque les dimensions nécessaires sont
couvertes et comparables.

Une catégorie vide n'est pas un zéro. Une catégorie non exercée est `not_scored`
ou `insufficient_evidence` selon le contrat.

**Règle d'implémentation :** aucun rang de recommandation si la qualité du cas
d'usage ou une composante décisionnelle obligatoire est incomplète.

### P6 — Les seuils sont calibrés, jamais déduits d'une intuition

Les seuils actuels du catalogue sont provisoires. Un seuil final doit s'appuyer
sur :

- la difficulté observée des items ;
- la distribution des scores sur un panel de modèles ;
- la répétabilité ;
- la revue humaine des erreurs ;
- la sensibilité à une variation raisonnable du seuil ;
- la relation éventuelle avec `gen-e2-eval` lorsqu'un dataset client existe.

**Règle d'implémentation :** les seuils portent un `threshold_status` (`draft`,
`calibration_pending`, `calibrated`, `deprecated`) et une version de
méthodologie. Aucun seuil `draft` ne doit être décrit comme une certification.

### P7 — Les métriques fermées et ouvertes sont publiées séparément

Les réponses exactes, les sorties JSON et les tests exécutables peuvent être
corrigés de manière déterministe. Les réponses ouvertes sont évaluées par une
rubrique et un juge. Les deux familles n'ont pas la même incertitude.

MMLU-Pro et une partie de BIG-bench illustrent les scores fermés. MT-Bench
illustre la nécessité de publier les verdicts et les biais du juge.

**Règle d'implémentation :** publier séparément les composantes déterministe et
jugée, ainsi que le désaccord, la couverture et la provenance du juge.

### P8 — Un juge LLM produit une preuve incertaine

Un juge LLM n'est ni un oracle ni une mesure directe de vérité. Il peut être
sensible à l'ordre, à la longueur, à l'identité implicite du fournisseur et à
son propre style.

**Règle d'implémentation :** conserver l'aliasing, le scrub d'auto-identification,
les critères atomiques, les verdicts individuels et `judge_disagreement`. Une
calibration humaine doit précéder l'utilisation d'un seuil fondé sur une note
ouverte.

### P9 — Les systèmes agentiques et les modèles seuls sont séparés

SWE-bench mesure un système comprenant un modèle, un agent, des outils, un
repository, un environnement et des tests. Model Compass actuel mesure des
appels de modèle via OpenRouter.

**Règle d'implémentation :** ne pas appeler `code_correctness` une mesure
SWE-bench. Une future suite repository/tool-use aura un contrat, un sandbox,
un budget et une attribution séparés.

### P10 — La sécurité n'est pas absorbée par la qualité

Une réponse fonctionnellement correcte peut être dangereuse ou divulguer un
secret. Les probes de sécurité et le RSI restent une évidence distincte.

**Règle d'implémentation :** une fuite confirmée, une erreur de probe et une
mauvaise réponse qualité gardent des statuts distincts. L'agrégat de
recommandation peut utiliser une composante sécurité, mais ne doit pas effacer
le détail.

### P11 — Les variantes et les versions sont des identités différentes

`MMLU` et `MMLU-Pro`, `BIG-bench` et `BIG-bench Lite`, `SWE-bench` et
`SWE-bench Verified`, ou un MT-Bench modifié ne sont pas le même benchmark.

**Règle d'implémentation :** chaque référence porte `family`, `variant`,
`revision`, `accessed_at` et, quand possible, un commit/tag. Les résultats ne
sont comparés qu'à protocole et variante identiques.

### P12 — La représentativité entreprise doit être démontrée

Une tâche académique, ludique ou publique peut être utile comme diagnostic sans
être représentative d'un usage de consulting. La sélection des tâches Model
Compass doit relier chaque construct à un besoin générique explicite, sans
inventer de dataset client.

**Règle d'implémentation :** chaque cas d'usage du catalogue inclut `business_intent`,
`construct`, `benchmark_influences` et une justification de sa pertinence.

### P13 — L'incertitude influence la décision, pas seulement le dashboard

Une différence de score inférieure à l'incertitude observée ne doit pas être
présentée comme une victoire nette. Les égalités sont conservées et les
near-ties doivent être visibles.

**Règle d'implémentation :** étudier bootstrap, répétitions, intervalles et
bande de tie avant de figer le rang. Aucun départage par nom de fournisseur ou
identifiant modèle.

### P14 — Le coût évalué reste le coût du modèle seul

Le coût du modèle, l'infrastructure, le RAG, l'orchestration et le coût humain
sont des objets différents. Le scope Model Compass retient le coût OpenRouter du
modèle et ses projections génériques.

**Règle d'implémentation :** conserver `actual_cost_credits`, `tco_usd` et les
profils de workload séparés. Une extension au coût total nécessitera une nouvelle
décision de scope.

## Décisions de périmètre pour la suite v2

### Inclure dans le premier cycle de conception

- conversation et communication structurée ;
- extraction et sorties schématisées ;
- question-réponse générique avec contexte fourni ;
- résumé et transformation ;
- classification/routage ;
- raisonnement et planification bornés ;
- code court avec validation statique ou tests sûrs ;
- une petite trajectoire multi-tour.

### Garder comme diagnostics ou pistes séparées

- connaissance académique de type MMLU-Pro ;
- tâches BIG-bench hors distribution, jeux et tâches non linguistiques ;
- repository-level code et SWE-bench ;
- tool-use et agents autonomes ;
- multimodalité ;
- fairness/toxicity comme score fonctionnel universel.

### Exclure du premier cycle

- copie de questions publiques des cinq benchmarks ;
- fusion des leaderboards externes ;
- exécution de code non sandboxée ;
- seuils définitifs avant calibration ;
- analyse automatique de l'appel d'offres ;
- données client ou confidentielles.

## Conséquence sur le catalogue actuel

`model-compass-use-cases-v1` reste lisible et sert de baseline technique. Il ne
faut pas le présenter comme la taxonomie finale : ses six cas d'usage et ses
seuils sont provisoires.

La prochaine suite doit être une nouvelle version, avec :

- un blueprint d'item plus riche ;
- des familles de prompts plutôt que des prompts isolés ;
- des rubriques et références versionnées ;
- des niveaux de difficulté ;
- une distinction langue/contexte/protocole ;
- une procédure de calibration et de revue.

## Statut et prochaine décision

Ces principes sont **adoptés pour la conception de la méthodologie v2**. Les
seuils précis, le nombre d'items et la taxonomie finale restent des décisions de
la Phase 3 et de la calibration empirique.
