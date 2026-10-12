# Matrice comparative des cinq benchmarks

**Phase :** 1 — synthèse descriptive
**Statut :** comparaison structurée ; les décisions finales d'adoption sont
réservées à la Phase 2

Cette matrice met les cinq références sur les mêmes axes. Elle ne compare pas
leurs scores numériques : leurs construits, protocoles et unités ne sont pas
équivalents.

## Matrice principale

| Axe | HELM | MMLU / MMLU-Pro | BIG-bench | MT-Bench | SWE-bench |
|---|---|---|---|---|---|
| Construct principal | Évaluation holistique de capacités et risques | Connaissance académique et raisonnement fermé | Exploration large de capacités et limites | Qualité d'assistant conversationnel ouvert | Résolution de problèmes logiciels réels |
| Unité | Scénario × modèle × métrique | Question QCM × modèle | Tâche/exemple, parfois interaction | Conversation de 2 tours × modèle × juge | Issue + dépôt + patch + tests |
| Catégories | Scénarios et métriques, couverture/feasibility | 57 tâches originales ; 14 domaines MMLU-Pro | Mots-clés chevauchants, 214 tâches dans la révision consultée | 8 catégories, 80 questions dans la révision consultée | Dépôts, familles d'issues, variantes de dataset |
| Type de réponse | Dépend du scénario | Choix parmi 4 puis 10 options | Texte, QCM, log-probabilité ou interaction | Texte libre multi-tour | Modification de repository |
| Protocoles | Adapters et configurations par scénario | Zero/few-shot, templates et extraction | Zero/one/many-shot, JSON/programmatic, interactions | Deux tours, génération puis jugement | Agent/outils, Docker, exécution de tests |
| Métrique principale | Plusieurs : accuracy, calibration, robustesse, fairness, bias, toxicity, efficacité | Accuracy par sujet/domaine | Métrique déclarée par tâche, `preferred_score` | Score juge 1–10, moyenne des tours ; modes pairwise alternatifs | Résolution = tests fail-to-pass réussis |
| Agrégation | Métriques séparées et leaderboards ciblés | Accuracy par sujet puis agrégats | Exemple → sous-tâche → tâche → groupe possible | Moyenne des tours/questions ou win rate pairwise | Pourcentage d'instances résolues |
| Baseline | Selon scénario ; couverture et comparabilité | Hasard, modèles de référence ; humain variable | Baselines humaines dans les analyses, selon tâche | 3,3K annotations humaines documentées ; accord GPT-4/humains >80 % dans l'étude | Baselines RAG/agents et filtres humains Verified |
| Incertitude | À étudier par scénario/métrique | Généralement score avec taille d'échantillon ; CI à compléter | Variance par tâche et baselines | Désaccord et biais du juge à mesurer | Variation par issue, agent, tests et environnement |
| Coût | Framework + scénarios, potentiellement large | API/appels proportionnels aux questions | Full coûteux ; Lite = 24 tâches | Génération 2 tours + jugement | Très élevé : Docker, builds, tests, espace et CPU |
| Reproductibilité | Forte si release, adapter et config figés | Bonne via code/data, mais contamination et extraction à contrôler | Bonne via schéma/harness, dépôt archivé | Bonne avec fichiers/rubriques, juge à versionner | Forte avec Docker/run ID, dépendances et cache à contrôler |
| Risque principal | Agrégat holistique trop large ou métriques incomparables | Knowledge ≠ réussite métier ; contamination | Hétérogénéité et agrégation arbitraire | Biais du LLM-as-a-Judge | Attribution modèle vs agent/environnement |
| Transfert provisoire | Adapt | Adapt | Adapt | Adapt | Adapt/Observe |

## Lecture par dimension

### Construct

Les références couvrent cinq niveaux différents :

1. **HELM** : cadre de description et d'évaluation multi-métrique ;
2. **MMLU** : compétence de connaissance/réponse fermée ;
3. **BIG-bench** : catalogue de capacités hétérogènes ;
4. **MT-Bench** : qualité ouverte de dialogue ;
5. **SWE-bench** : résultat opérationnel d'un système agentique.

Il serait méthodologiquement incorrect de les considérer comme cinq tests de la
même variable « qualité ».

### Unité de réussite

- MMLU et une partie de BIG-bench peuvent être corrigés au niveau de l'item.
- MT-Bench exige une interprétation de réponse et de trajectoire.
- SWE-bench exige une exécution externe et des tests.
- HELM rend la métrique dépendante du scénario.

Model Compass doit donc conserver une unité et une méthode d'évaluation par
famille avant toute agrégation.

### Protocoles

Le protocole détermine une grande partie du résultat :

- few-shot et CoT changent MMLU/MMLU-Pro ;
- shots et prefixes changent BIG-bench ;
- ordre, rubric et juge changent MT-Bench ;
- agent, outils, retrieval et environnement changent SWE-bench ;
- adapters et métriques changent HELM.

Le plan de recherche doit enregistrer les paramètres, pas seulement le nom du
benchmark.

### Métriques

Les cinq références illustrent un continuum :

```text
exactitude fermée -> métrique déclarée par tâche -> jugement ouvert
                   -> préférence pairwise -> tests d'exécution
```

Ces métriques ne sont pas convertibles sur une échelle commune sans hypothèse
forte et non démontrée. Model Compass conservera donc des scores de catégorie,
des statuts et une incertitude explicite.

## Correspondance préliminaire avec les besoins Model Compass

| Besoin générique | Références informatives | Ce qu'on peut en tirer | Ce qui reste à concevoir |
|---|---|---|---|
| Communication et rédaction | MT-Bench, BIG-bench | Rubriques, multi-tour, contraintes de style explicites | Critères humains/entreprise et langue |
| Extraction structurée | HELM, BIG-bench, MT-Bench | Schéma, exact match, format séparé du contenu | Documents représentatifs sans dataset client |
| QA et connaissance | MMLU-Pro, BIG-bench, HELM | Domaine, QCM, factualité et couverture | Factualité en contexte et abstention |
| Raisonnement | MMLU-Pro, BIG-bench, MT-Bench | Difficulté, multi-step, réponses de référence | Calibration et robustesse à la reformulation |
| Code court | BIG-bench, MT-Bench, SWE-bench | Validation par tests, séparation modèle/système | Sandbox et attribution |
| Repository engineering | SWE-bench | Fail-to-pass, environnement, tests | Hors première version générique probable |
| Long contexte/RAG | HELM, BIG-bench | Scénarios et métriques dédiés | Harness documentaire et corpus générique |
| Sécurité/robustesse | HELM, BIG-bench, pipeline actuel | Métriques séparées, probes et limites | Ne pas confondre sécurité et qualité |

## Synthèse des décisions à préparer en Phase 2

1. **Architecture de catalogue :** adopter la séparation HELM entre scénario,
   métrique et résultat.
2. **Méta-tâches :** adopter le schéma BIG-bench `keywords`/`metrics`/
   `preferred_score`, en l'enrichissant de difficulté, langue et risque.
3. **Données fermées :** utiliser MMLU/MMLU-Pro comme inspiration pour les
   diagnostics de domaine, sans importer les questions dans le score produit.
4. **Dialogue ouvert :** adapter MT-Bench pour quelques trajectoires
   multi-tour, avec rubric versionné et désaccord publié.
5. **Code :** garder la génération simple dans Model Compass et traiter
   repository-level/SWE-bench comme une piste séparée tant que le sandbox n'est
   pas défini.
6. **Agrégation :** publier les familles séparément avant d'autoriser un score
   de recommandation.
7. **External evidence :** créer un tableau de références externes, séparé des
   observations collectées par Model Compass.

## Limites de cette synthèse

- Les chiffres sont ceux des versions et pages consultées le 2026-09-09.
- Certaines informations de licence portent sur les dépôts de code, pas
  nécessairement sur chaque dataset ou question.
- Les résultats de leaderboards ne sont pas une preuve de comparabilité.
- Les transferts indiqués sont des hypothèses de Phase 1 ; la Phase 2 doit les
  approuver dans un ADR après revue de l'équipe.
