# ADR 0002 — Méthodologie d'évaluation informée par cinq benchmarks

**Statut :** Accepté pour la conception de la méthodologie v2
**Date :** 2026-09-10
**Décideurs :** équipe Model Compass — Palo IT Singapore
**Remplace :** aucune décision historique ; complète ADR 0001

---

## Contexte

Model Compass doit recommander des modèles LLM par cas d'usage générique pour
un humain qui connaît un appel d'offres. Le dépôt possède déjà une suite de 16
prompts, un pipeline qualité déterministe + juges Copilot, un scanner de
sécurité et une couche de recommandation. Les cas d'usage et seuils actuels
sont toutefois provisoires.

La Phase 1 a étudié cinq familles reconnues :

- HELM, qui sépare scénarios, métriques, adapters et provenance ;
- MMLU/MMLU-Pro, qui mesurent des connaissances et raisonnements fermés par
  matières ;
- BIG-bench, qui propose un catalogue hétérogène de tâches et un schéma riche ;
- MT-Bench, qui étudie le dialogue multi-tour et le LLM-as-a-Judge ;
- SWE-bench, qui mesure la résolution d'issues dans un système agentique et un
  environnement d'exécution.

Ces familles ne mesurent pas le même construit et ne partagent ni la même
unité, ni la même métrique, ni le même protocole. Une moyenne de leurs
leaderboards serait donc une précision artificielle.

Références détaillées :

- [registre des sources](../research/benchmark-source-registry.md) ;
- dossiers des cinq benchmarks sous `docs/research/benchmarks/` ;
- [matrice comparative](../research/benchmark-comparison.md) ;
- [principes de conception](../research/model-compass-design-principles.md) ;
- [cartographie benchmark → cas d'usage](../research/benchmark-to-use-case-mapping.md).

## Décision

### 1. Ne pas fusionner les scores externes

Les scores HELM, MMLU/MMLU-Pro, BIG-bench, MT-Bench et SWE-bench restent des
evidences externes. Ils ne participent pas à `recommendation_score`.

Ils peuvent être utilisés pour :

- justifier le choix d'un construit ou d'une catégorie ;
- comparer des tendances au niveau d'une famille ;
- identifier des risques et des méthodes à tester ;
- documenter une validation convergente après avoir prouvé la comparabilité.

Toute utilisation future d'un score externe dans un classement nécessitera une
nouvelle décision documentant le construit, la version, l'unité, le protocole,
l'échelle et l'incertitude.

### 2. Adopter une architecture scénario → métrique → recommandation

Le catalogue v2 doit séparer :

1. le **scénario/cas d'usage** et son intention ;
2. la **tâche/item** et son construit principal ;
3. la **métrique/évaluateur** et son échelle ;
4. la **preuve brute** et ses métadonnées ;
5. l'**agrégation par cas d'usage** ;
6. la **recommandation** appliquée seulement après vérification de l'éligibilité.

Cette architecture reprend le principe HELM sans adopter son framework complet.

### 3. Utiliser un blueprint de tâche inspiré de BIG-bench

Chaque item v2 devra déclarer au minimum :

- `item_id` et `use_case_id` ;
- `construct` ;
- `task_type` (`json`, `multiple_choice`, `free_response`, `programmatic`,
  `multi_turn`, `environment`) ;
- `difficulty` et son statut (`draft`, `pilot`, `calibrated`) ;
- `language` ;
- `prompt` ou `messages` ;
- `evaluator` et `metric_ids` ;
- `reference_answer` ou `rubric_id` ;
- `suite_version`, `rubric_version` et `methodology_version` ;
- `license_status` et `contamination_status`.

La suite interne ne copiera pas les exemples publics des benchmarks étudiés.

### 4. Retenir MMLU-Pro comme diagnostic, pas comme qualité métier

La prochaine recherche privilégiera MMLU-Pro pour étudier la difficulté, les
domaines et la sensibilité au prompt, tout en gardant MMLU original comme
point historique de comparaison.

Aucune question MMLU/MMLU-Pro ne sera copiée dans la suite Model Compass avant
revue de licence, contamination et pertinence. Une éventuelle suite interne de
questions fermées sera réécrite, versionnée et présentée comme interne.

### 5. Adapter MT-Bench pour une petite suite multi-tour contrôlée

Model Compass pourra inclure une suite limitée de conversations à deux ou trois
tours pour les construits où le contexte précédent est nécessaire : correction,
clarification, transformation et respect d'une contrainte successive.

Les règles sont :

- rubriques atomiques et versionnées ;
- réponses et verdicts conservés par tour ;
- juge et version de prompt enregistrés ;
- `judge_disagreement` publié ;
- calibration humaine avant d'utiliser une note ouverte comme seuil ;
- aucune prétention d'exactitude objective pour un score de préférence.

Le mode single-answer rubricé sera le mode principal de conception. Le pairwise
reste une méthode de recherche et ne sera pas mélangé au score absolu sans
étude de calibration.

### 6. Garder SWE-bench hors du pipeline chat générique

Le code court peut entrer dans Model Compass avec une validation statique ou un
test contrôlé. La résolution d'une issue repository-level est une évaluation
séparée, car elle dépend d'un agent, d'outils, du retrieval, d'une image Docker
et d'une suite de tests.

Aucune exécution de code généré ne sera ajoutée au pipeline actuel sans sandbox,
limites de ressources, logs et contrat d'attribution approuvés.

### 7. Préserver l'éligibilité avant le classement

Les principes actuels restent valides et sont confirmés pour la v2 :

```text
qualité du cas d'usage >= seuil calibré
    et couverture suffisante
    -> modèle éligible

preuves sécurité/coût/performance complètes
    -> score de recommandation calculable

score calculé
    -> rang dense ; égalités conservées
```

Un modèle ne peut pas remonter dans le classement parce qu'il est moins cher,
plus rapide ou mieux normalisé s'il ne satisfait pas le seuil qualité.

## Alternatives considérées

| Alternative | Décision | Motif |
|---|---|---|
| Moyenne des cinq benchmarks externes | Rejetée | Construits, unités et protocoles incompatibles |
| Import direct de MMLU-Pro dans le score qualité | Rejetée pour v2 | Connaissance académique différente d'un usage métier ; licences/contamination à vérifier |
| Import de BIG-bench Lite complet | Rejetée pour v2 | Hétérogénéité et coût ; on reprend le schéma de tâche, pas le catalogue |
| Copier MT-Bench et utiliser le même score | Rejetée | Questions publiques, juge et échelle non identiques à Model Compass |
| Inclure SWE-bench dans `make collect` | Rejetée | Mesure modèle + agent + environnement et exige un sandbox coûteux |
| Maintenir uniquement la suite de 16 prompts | Rejetée comme cible finale | Insuffisante pour les cas d'usage et la calibration, mais conservée comme baseline v1 |
| Supprimer la couche de recommandation | Rejetée | Contradicting scope; la recommandation technique reste l'objectif produit |

## Conséquences positives

- Les recommandations seront plus auditables et moins dépendantes d'un score
  global opaque.
- Les décisions de conception peuvent être comparées à des méthodes reconnues
  sans prétendre les reproduire.
- Les catégories, les métriques et les environnements pourront évoluer sans
  réécrire les résultats historiques.
- La suite multi-tour et la future suite code auront des contrats explicites.
- Le pipeline actuel reste utilisable pendant la recherche.

## Conséquences négatives et compromis

- La v2 nécessitera davantage de métadonnées et de revues humaines.
- Les résultats Model Compass ne seront pas directement comparables aux scores
  des leaderboards externes.
- La calibration des seuils exigera des runs répétés et un budget OpenRouter.
- Les cas RAG, agentiques et repository-level seront différés, même s'ils sont
  importants pour certains clients.
- La coexistence de plusieurs métriques rendra le dashboard plus riche mais
  moins résumable par un seul chiffre.

## Contrats imposés pour l'implémentation future

1. `generic-screen-v1` reste lisible et immuable.
2. Toute nouvelle suite possède un identifiant et un hash propres.
3. `catalog_version`, `rubric_version` et `methodology_version` survivent dans
   les artefacts de collect, merge, recommendation et manifest.
4. Les scores externes restent dans une table d'évidence distincte.
5. Les erreurs techniques sont séparées des erreurs de réponse.
6. Les juges doivent couvrir tous les éléments attendus ou le merge échoue.
7. Les résultats sans preuves suffisantes restent visibles mais n'obtiennent
   pas de rang.
8. Les égalités conservent le même rang et ne sont pas départagées par le nom.
9. Les dashboards exposent les dimensions et les limites avant le score global.
10. Toute modification de prompt, rubrique, seuil ou agrégation déclenche une
    nouvelle version et une entrée de changelog.

## Statut de suivi

Cette ADR clôt la décision de transfert de la Phase 2. Elle autorise la Phase 3
(taxonomie et blueprint) mais ne fixe pas encore :

- la liste finale des cas d'usage ;
- le nombre d'items par catégorie ;
- les seuils numériques ;
- la première langue de production ;
- la taille du pilote ;
- l'intégration éventuelle d'un sandbox code.

Ces points doivent être décidés à partir de la calibration et non par intuition.
