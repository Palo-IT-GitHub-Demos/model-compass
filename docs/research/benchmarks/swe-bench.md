# Dossier benchmark — SWE-bench

**Famille :** résolution d'issues GitHub par des systèmes de code
**Sources gelées :** papier arXiv `2310.06770v3`, dépôt `SWE-bench/SWE-bench` commit `02e7a74`, site original et page Verified consultés le 2026-09-09
**Statut de la source :** référence pour les évaluations d'ingénierie logicielle en environnement ; non importée dans le benchmark chat générique

## 1. Résumé exécutif

SWE-bench évalue la capacité d'un système à résoudre des issues GitHub réelles.
La tâche ne consiste pas à générer une fonction isolée : le système reçoit une
base de code et une description d'issue, modifie le dépôt, puis doit passer des
tests d'évaluation.

La version originale comprend 2 294 instances issues de 12 dépôts Python. Chaque
instance est associée à un pull request et à une issue. Le signal principal est
le passage des tests **fail-to-pass** : les tests qui échouent avant le patch et
réussissent après le patch.

L'écosystème publie plusieurs variantes :

- original/full : 2 294 instances ;
- Lite : 300 instances ;
- Verified : 500 instances filtrées par des humains ;
- Multilingual : 300 instances et 42 dépôts dans 9 langues, selon le site ;
- Multimodal : 480 instances dans la version consultée.

Verified précise que les humains ont contrôlé la clarté du problème, la validité
des patches de test et la solvabilité avec les informations disponibles. La vue
Bash-only utilise mini-SWE-agent dans un environnement minimal pour faciliter une
comparaison plus proche entre modèles.

## 2. Construct et décision supportée

Le construct est la **résolution opérationnelle d'un problème logiciel réel**
par un système combinant :

- modèle de langage ;
- boucle d'agent ;
- outils shell/édition ;
- contexte de dépôt ;
- environnement d'exécution ;
- tests et dépendances.

Le score supporte une décision sur un système de code ou un agent, pas sur un
modèle de chat isolé. Cette distinction est essentielle pour Model Compass : un
prompt de génération de fonction ne peut pas revendiquer une performance
SWE-bench.

## 3. Composition des instances

Une instance associe généralement :

- identifiant du dépôt et état de base ;
- issue textuelle ;
- snapshot installable du repository ;
- patch de référence ou commit de pull request ;
- tests avant/après et métadonnées d'évaluation ;
- environnement Docker correspondant au dépôt.

Le système doit modifier le code sans accès au patch de référence pendant la
résolution. L'évaluation lance ensuite les tests dans une image construite pour
l'instance.

Le dépôt et les issues proviennent de projets réels, ce qui donne une bonne
écologie de travail mais introduit des biais de langage, de projet, de version et
de qualité de tests.

## 4. Protocole d'exécution

Le protocole complet comporte deux étapes :

1. **inférence** : donner l'issue et le dépôt au système, qui génère un patch ;
2. **évaluation** : appliquer le patch dans l'environnement et exécuter les
   tests.

SWE-bench utilise Docker pour la reproductibilité. La documentation actuelle
recommande un environnement important : environ 120 GB d'espace libre, 16 GB de
RAM et 8 CPU pour une exécution locale typique. Les architectures ARM restent
expérimentales dans la documentation consultée.

La vue Verified Bash-only standardise davantage l'agent : mini-SWE-agent, boucle
ReAct minimale et shell basique, sans outils ou scaffolding spécifiques. Cette
vue est plus proche d'une comparaison de modèles, mais reste une évaluation
modèle + agent + shell.

## 5. Notation

Le résultat principal est la **résolution** : proportion d'instances dont les
tests de validation réussissent. Les tests fail-to-pass sont le signal central,
mais une évaluation complète doit également surveiller :

- tests préexistants qui régressent ;
- patch non applicable ;
- erreur de compilation ou installation ;
- timeout ;
- environnement indisponible ;
- test flaky ;
- instance sans test réellement discriminant.

Un score « resolved » n'est pas une note de qualité rédactionnelle. Il indique
que le système a produit un changement accepté par la suite de tests de
l'instance.

Les variantes et agents doivent rester séparés : un score Full avec un agent
riche, un score Verified Bash-only et un score Lite ne sont pas interchangeables.

## 6. Validation des données et des tests

Le benchmark original construit l'environnement au commit avant le pull request
et vérifie que les tests pertinents échouent avant et passent après le patch. La
sélection Verified ajoute un filtre humain sur :

- clarté de l'énoncé ;
- correction des tests ;
- solvabilité avec l'information disponible.

C'est une pratique de validation des tâches particulièrement utile pour Model
Compass. Elle montre qu'un item ne doit pas seulement avoir une réponse attendue
: il doit aussi posséder un test qui discrimine réellement les comportements.

## 7. Risques de validité et coûts

- Le système évalué inclut l'agent, les outils, le contexte, les dépendances et
  l'environnement ; l'attribution au modèle seul est impossible sans ablation.
- Les tests peuvent être incomplets, flakys ou trop proches du patch de référence.
- Les dépôts Python et leurs conventions limitent la généralisation.
- La difficulté des issues varie fortement.
- Le retrieval, le budget de tours et le nombre de rollouts influencent fortement
  le score.
- Docker, builds, stockage et temps CPU rendent l'évaluation coûteuse.
- Le cache du harness peut réutiliser un résultat si le même `run_id` et le même
  `instance_id` sont utilisés ; les run IDs doivent être uniques pour un nouveau
  patch.
- Les licences des dépôts sources et des données doivent être respectées.

## 8. Transfert provisoire vers Model Compass

### À adapter

1. La séparation entre génération, exécution et validation.
2. Les statuts techniques explicites : patch invalide, timeout, test failure,
   environnement indisponible.
3. Le principe d'un test de validation indépendant du modèle et contrôlé avant
   utilisation.
4. La distinction entre une capacité modèle simple et un système agentique.
5. Les sous-ensembles humains filtrés et leur version.

### À observer

- Les taux de résolution par famille de dépôt et difficulté.
- L'effet des outils, du retrieval, du nombre de tours et du budget.
- La pertinence d'un futur benchmark de code séparé pour Model Compass.
- Les variantes multilingues et multimodales, hors scope actuel.

### À rejeter pour l'instant

- Exécuter SWE-bench complet dans `make collect` sur OpenRouter.
- Présenter `code_correctness` actuel comme un proxy SWE-bench.
- Agréger un score SWE-bench avec la qualité conversationnelle.
- Ajouter de l'exécution de code non isolée dans le pipeline générique.

## 9. Implications pour nos prompts, tests et rubriques

- Séparer dans le catalogue `code_generation`, `code_debugging`, `test_writing`
  et `repository_change`.
- Pour les tâches exécutables, enregistrer l'image, le runtime, les limites,
  les tests et le statut de sécurité.
- Définir le statut d'un échec technique avant de définir le score qualité.
- Ajouter des tests qui vérifient à la fois la réussite attendue et l'absence de
  régression.
- Ne pas exécuter du code généré par un modèle dans le pipeline actuel sans
  sandbox dédiée et auditée.
- Utiliser la réussite de tests comme une mesure séparée du jugement de style ou
  de qualité d'explication.
- Prévoir une suite de code « lightweight » maintenant et une suite agentique
  indépendante plus tard.

## 10. Questions ouvertes

- Le futur benchmark code doit-il rester dans Model Compass ou devenir un
  projet frère spécialisé ?
- Quel sandbox, budget et image reproductible seraient acceptables sur macOS et
  CI ?
- Peut-on mesurer une tâche de patch simple sans attribuer à tort le résultat au
  modèle seul ?
- Quelle taille de subset donne une estimation utile sans les coûts de SWE-bench
  complet ?
- Faut-il comparer seulement des modèles avec le même agent et les mêmes outils,
  comme la vue Bash-only ?

## Décision provisoire

**Transfert : ADAPT/OBSERVE.** Nous reprenons la séparation des systèmes, la
validation par tests et les statuts d'environnement. Le repository-level code et
SWE-bench restent une piste séparée tant qu'un sandbox et un contrat d'attribution
ne sont pas approuvés.
