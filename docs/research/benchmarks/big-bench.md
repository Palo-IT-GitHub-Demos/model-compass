# Dossier benchmark — BIG-bench

**Famille :** Beyond the Imitation Game Benchmark
**Sources gelées :** papier arXiv `2206.04615v3`, dépôt `google/BIG-bench` archivé le 2026-04-17, README task catalog commit `092b196`, keyword map commit `95308e1`, documentation schema commit `71ebc2e`
**Statut de la source :** référence de conception de tâches et de métadonnées ; non importée comme score Model Compass

## 1. Résumé exécutif

BIG-bench est un benchmark collaboratif conçu pour sonder des capacités variées
et des limites de modèles de langage. Le papier décrit 204 tâches contribuées
par 450 auteurs de 132 institutions. Le dépôt actuel liste 214 tâches dans le
répertoire de tâches, ce qui confirme l'importance de figer une révision lorsque
l'on cite un nombre.

Le dépôt distingue deux familles de tâches :

- tâches JSON, avec entrées, sorties cibles ou scores de choix ;
- tâches programmatiques, qui peuvent interroger le modèle de manière plus
  riche et calculer un score personnalisé.

BIG-bench Lite est un sous-ensemble de 24 tâches JSON destiné à fournir une
évaluation moins coûteuse. Le repository a été archivé le 17 avril 2026 : il
reste une source méthodologique riche, mais son état de maintenance doit être
pris en compte.

## 2. Construct et décision supportée

BIG-bench ne mesure pas une capacité unique. Il cherche à explorer un espace de
capacités parfois au-delà des benchmarks traditionnels : langage, raisonnement,
mathématiques, code, compréhension sociale, biais, langues peu dotées, tâches
non linguistiques, interaction répétée et problèmes hors distribution.

La décision supportée est plutôt une cartographie des capacités et de leurs
seuils de difficulté qu'un classement unique. La diversité est une force pour
la recherche, mais une contrainte pour Model Compass : les tâches ne sont pas
nécessairement commensurables.

## 3. Taxonomie et composition

Le catalogue de mots-clés organise les tâches dans des ensembles tels que :

- traditional NLP : contextual QA, summarization, translation, grammar ;
- logic, math, code : algorithms, logical reasoning, mathematics, computer code ;
- understanding the world : causal reasoning, common sense, context length ;
- understanding humans : theory of mind, emotional understanding, social reasoning ;
- scientific and technical understanding : biology, physics, medicine ;
- mechanics of interaction : multiple choice, free response, repeated interaction ;
- common technical limitations : multi-step, out-of-distribution, instructions,
  tokenization ;
- pro-social behavior : alignment, social bias, toxicity, truthfulness ;
- other : creativity, multilingual, low-resource language, sufficient information.

La taxonomie est descriptive et peut être chevauchante : une tâche peut avoir
plusieurs mots-clés. Le README du dépôt décrit 214 tâches dans la révision
consultée ; le papier historique parle de 204 tâches. Les deux nombres sont
conservés avec leur contexte et ne doivent pas être confondus.

BIG-bench Lite contient 24 tâches JSON retenues comme sous-ensemble opérationnel.
Il ne s'agit pas d'un échantillon statistiquement neutre de toutes les
capacités : c'est un compromis de coût et de couverture.

## 4. Format des tâches

### Tâche JSON

Le schéma demande notamment :

- `name` ;
- `description` ;
- `keywords` ;
- `metrics` ;
- `preferred_score` ;
- une chaîne `canary` pour limiter la fuite des données de benchmark ;
- `examples` avec `input` et `target`, ou `target_scores` pour un format de
  choix/probabilités.

Le format permet :

- plusieurs cibles acceptées pour une sortie texte ;
- des scores par cible pour un QCM ;
- des sous-tâches avec agrégation séparée ;
- des préfixes, shots, choix, stop strings et regex d'extraction.

### Tâche programmatique

Une tâche Python implémente une interface qui retourne des `ScoreData` avec une
ou plusieurs métriques, un score préféré, le nombre de shots et les bornes du
score. Elle peut appeler `generate_text` ou `cond_log_prob`, voire interagir
plusieurs fois avec le modèle.

Cette séparation est directement pertinente pour le blueprint Model Compass :
le contrat d'une tâche doit déclarer son évaluateur plutôt que laisser
l'agrégation deviner la sémantique.

## 5. Protocoles et métriques

BIG-bench autorise des protocoles zéro-shot, one-shot et many-shot. Les mots-clés
indiquent aussi `multiple choice`, `free response`, `programmatic`, `repeated
interaction`, `context length`, `multi-step` et autres propriétés.

Les métriques JSON incluent notamment :

- `exact_str_match` pour les sorties texte ;
- BLEU, ROUGE ou BLEURT pour certaines sorties texte ;
- `multiple_choice_grade` ;
- Brier score multi-catégorie pour la calibration des choix.

Le calcul de choix peut utiliser la probabilité/log-probabilité des cibles, ce
qui n'est pas toujours disponible via une API de chat comme OpenRouter. Le
format libre et le format QCM ne doivent donc pas être traités comme deux
variantes de la même métrique.

Les résultats peuvent être agrégés à plusieurs niveaux : exemple, sous-tâche,
tâche, groupe de mots-clés et ensemble. Le champ `preferred_score` explicite
quel score est présenté comme principal pour une tâche, mais cela ne constitue
pas une justification automatique d'un agrégat global BIG-bench.

## 6. Revue de qualité et baselines

Les critères de soumission du dépôt sont instructifs pour Model Compass :

1. correction technique et tests ;
2. format lisible et interaction compréhensible ;
3. spécificité du construit ;
4. robustesse et contrôle des facteurs confondants ;
5. difficulté suffisante mais pas totalement hors d'atteinte ;
6. impossibilité raisonnable de résoudre par simple mémorisation, sauf tâche
   explicitement dédiée à la mémorisation ;
7. nouveauté/couverture d'un manque ;
8. justification claire ;
9. au moins 32 exemples recommandés par tâche ;
10. coût de calcul acceptable.

Le benchmark a aussi utilisé des évaluations humaines comme point de référence
pour certaines analyses. La présence d'un baseline humain ne rend toutefois pas
chaque tâche comparable à un cas d'usage professionnel.

## 7. Limites et risques de validité

- Une collection collaborative produit une grande diversité, mais aussi une
  hétérogénéité de difficulté et de qualité.
- Les mots-clés peuvent se chevaucher et ne sont pas une hiérarchie de
  compétences stable.
- Les métriques et protocoles diffèrent fortement entre tâches.
- Les tâches publiques sont exposées à la contamination ; les canary strings
  protègent surtout le corpus contre certaines fuites de données, pas contre
  toute mémorisation préalable.
- Les tâches programmatiques peuvent nécessiter des dépendances, des sorties
  non disponibles par OpenRouter ou des environnements spécifiques.
- Un résultat Lite ne résume pas nécessairement le full benchmark.
- Le dépôt archivé ne garantit pas une maintenance ou une actualisation future.

## 8. Transfert provisoire vers Model Compass

### À adapter

1. **Task blueprint riche.** Adopter `description`, `keywords`, `metrics`,
   `preferred_score`, difficulté, protocole et sous-tâches.
2. **Métrique déclarative.** Chaque item doit nommer son évaluateur et son échelle.
3. **Sous-tâches et reporting.** Garder les scores par famille avant tout
   agrégat global.
4. **Review criteria.** Introduire une revue de correction, spécificité,
   difficulté, contamination, coût et lisibilité avant d'ajouter un item.
5. **Réponses multiples.** Permettre une liste de réponses acceptées ou une
   validation structurée.

### À observer

- Calibration Brier si un fournisseur permet d'obtenir des probabilités fiables.
- Tâches hors distribution et long contexte.
- Tâches multilingues et faible ressource pertinentes pour Singapour.
- Tâches interactives et auto-évaluation, qui pourraient inspirer une suite
  séparée.

### À rejeter pour l'instant

- Importer les 200+ tâches sans sélection par construit.
- Moyenne unique de tâches dont les métriques, difficultés et unités diffèrent.
- Copier les exemples publics dans le corpus Model Compass.
- Déduire la réussite entreprise d'une tâche ludique ou hors distribution.

## 9. Implications pour nos prompts et rubriques

- Ajouter à chaque cas un `task_type` : JSON, QCM, texte libre, programme,
  interaction ou environnement.
- Ajouter `metrics` et `preferred_score` au catalogue interne.
- Définir des tailles minimales d'échantillon par famille ; les 16 prompts
  actuels ne suffisent pas pour prétendre à une calibration robuste.
- Séparer les tâches diagnostiques de celles qui peuvent alimenter une
  recommandation.
- Ajouter des tests de non-régression de composition du prompt : shots,
  préfixes, choix et regex d'extraction.
- Déclarer les catégories chevauchantes sans double-compter silencieusement un
  item dans plusieurs scores.
- Préserver un canary interne et une politique de non-publication pour les
  futurs items sensibles.

## 10. Questions ouvertes

- Quel sous-ensemble de capacités BIG-bench correspond réellement à une
  entreprise de conseil technologique ?
- Faut-il une suite Lite interne de 24 familles, ou moins de familles avec
  plusieurs items par famille ?
- Quelles métriques de texte libre sont défendables sans reproduire un
  leaderboard externe ?
- Peut-on utiliser les tâches comme inspiration sans reprendre leur contenu et
  sans contamination croisée ?
- Quelle taille par famille permet de calculer un seuil plutôt qu'un simple
  indicateur exploratoire ?

## Décision provisoire

**Transfert : ADAPT.** Nous reprenons le contrat de tâche, les métadonnées, la
séparation JSON/programmatique, les critères de revue et le reporting par tâche.
Nous ne reprenons ni le catalogue complet ni son éventuelle moyenne globale.
