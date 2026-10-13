# Cartographie benchmark → cas d'usage Model Compass

**Phase :** 2 — synthèse comparative et décisions méthodologiques
**Statut :** cartographie de conception v2 ; aucun score externe importé
**Date :** 2026-09-10

Cette cartographie relie les construits observés dans les cinq benchmarks aux
cas d'usage génériques que Model Compass pourrait évaluer. Elle ne signifie pas
que les tâches ou données publiques seront copiées. Les références servent à
justifier un construit et une méthode ; les prompts de production seront
internes, versionnés et revus.

## Légende des transferts

- **ADAPT** : le principe est utile après adaptation au contrat OpenRouter et au
  scope générique.
- **DIAGNOSTIC** : utile pour analyser une capacité, mais pas suffisant pour
  autoriser une recommandation métier.
- **SEPARATE** : nécessite un système, un environnement ou un coût différent du
  pipeline qualité actuel.
- **DEFER** : hors première version ou dépend d'une décision future.

## Matrice de cartographie

| Cas d'usage Model Compass | Construct interne | Références utiles | Décision | Méthode interne à concevoir |
|---|---|---|---|---|
| Conversation et assistance générale | Réponse utile, cohérente et sûre à une demande ouverte | HELM, MT-Bench, BIG-bench `topical_chat`/`dialogue system` | ADAPT | Plusieurs prompts ouverts, rubric contenu/sécurité/utilité, un item de clarification |
| Communication et rédaction | Produire un texte adapté à une audience, un ton et une contrainte | MT-Bench `writing`, BIG-bench summarization/writing style, HELM | ADAPT | Familles de rédaction, contraintes explicites, revue humaine d'exemples, longueur séparée du contenu |
| Question-réponse avec contexte fourni | Répondre à partir d'un contexte sans inventer | HELM, BIG-bench contextual QA/reading comprehension, MMLU-Pro comme diagnostic fermé | ADAPT | Contexte synthétique interne, réponses de référence, détection d'absence d'information, grounding séparé |
| Extraction structurée | Transformer un texte en schéma valide et fidèle | HELM, BIG-bench JSON/extraction, MT-Bench extraction | ADAPT | JSON schema, validation déterministe, exactitude des champs, champs manquants et hallucinations distincts |
| Résumé et synthèse | Préserver les faits importants et respecter le format demandé | BIG-bench summarization/truthfulness, MT-Bench writing, HELM | ADAPT | Corpus interne non confidentiel, critères de couverture/factualité, longueur séparée |
| Classification et routage | Attribuer une classe ou une intention selon une taxonomie | BIG-bench intent recognition/multiple choice, MMLU-Pro comme diagnostic de domaine | ADAPT | Labels définis, matrice de confusion, classes ambiguës et abstention explicites |
| Traduction et transformation multilingue | Préserver le sens et les contraintes entre langues | BIG-bench translation/multilingual/low-resource, HELM multilingual | ADAPT LATER | Version linguistique séparée, critères de sens et de forme, revue native avant agrégation |
| Raisonnement et planification bornés | Décomposer et résoudre une tâche avec résultat vérifiable | MMLU-Pro, BIG-bench logical reasoning/multi-step, MT-Bench reasoning/math | ADAPT | Items référence-réponse, preuves intermédiaires optionnelles, validation du résultat final |
| Analyse de données et tableaux | Lire, calculer et expliquer à partir d'une représentation structurée | BIG-bench table/structured tasks, HELM domain scenarios, MT-Bench reasoning | ADAPT LATER | Tables synthétiques, calculs déterministes, distinction lecture/calcul/explication |
| Génération et transformation de code court | Produire ou modifier du code selon un contrat borné | BIG-bench `computer code`/programmatic, MT-Bench coding, SWE-bench comme référence de limite | ADAPT | Syntaxe + tests sûrs pour petits artefacts, pas d'exécution non sandboxée, complexité explicite |
| Débogage et test de code | Identifier une cause et proposer une correction vérifiable | BIG-bench auto-debugging, MT-Bench coding, SWE-bench | ADAPT LATER / SEPARATE | Fixtures contrôlées, tests fail/pass, statut environnement séparé |
| Repository-level engineering | Résoudre une issue dans un dépôt réel | SWE-bench | SEPARATE | Projet agentique séparé, Docker/sandbox, run ID, budget et attribution système |
| Dialogue multi-tour borné | Maintenir le contexte et satisfaire une contrainte successive | MT-Bench, BIG-bench repeated interaction, HELM scenarios | ADAPT | Deux ou trois tours maximum, `turn_index`, rubric par tour et trajectoire |
| RAG et sources | Utiliser des documents récupérés et citer/limiter les sources | HELM scenario/metric separation, BIG-bench contextual QA | DEFER / ADAPT LATER | Corpus générique versionné, retriever fixe, grounding et retrieval séparés |
| Tool-use et agents | Choisir et utiliser des outils pour atteindre un objectif | BIG-bench programmatic/repeated interaction, SWE-bench | DEFER / SEPARATE | Contrat d'outil, sandbox, budget et critères de sécurité avant toute inclusion |
| Sécurité et robustesse | Résister aux demandes adversariales et ne pas divulguer | HELM robustness/toxicity/bias, BIG-bench pro-social, scanner Model Compass actuel | SEPARATE AXIS | Conserver les probes RSI/canary et ne jamais les fusionner dans la qualité fonctionnelle |

## Décisions par famille de benchmark

### HELM

HELM influence l'architecture du catalogue : un cas d'usage doit déclarer ses
métriques et ses dimensions plutôt que produire directement une note globale.
Les scénarios de sécurité, robustesse et efficacité restent des axes ou des
evidences séparés lorsque leur unité de mesure diffère de la qualité fonctionnelle.

### MMLU / MMLU-Pro

MMLU-Pro devient une référence de **diagnostic de connaissance et de domaine**.
Il ne devient pas une catégorie « qualité métier » et ses questions publiques ne
sont pas copiées. Une future suite interne peut reprendre le principe de sujets,
de choix multiples, de baseline de hasard et de sensibilité au template.

### BIG-bench

BIG-bench influence le blueprint d'item : mots-clés, type de tâche, métriques,
sous-tâches, niveau de difficulté et revue de qualité. Une sélection Model
Compass doit rester petite, cohérente et orientée par construit ; elle ne doit
pas être un échantillon arbitraire de la collection BIG-bench.

### MT-Bench

MT-Bench influence les cas de communication et de dialogue multi-tour. Nous
adoptons des rubriques atomiques et la conservation des verdicts, mais nous
calibrons nos juges Copilot séparément. Les notes ouvertes restent incertaines
et ne doivent pas masquer les erreurs déterministes.

### SWE-bench

SWE-bench influence la frontière de périmètre du code : génération d'une
fonction et résolution d'une issue dans un dépôt ne sont pas le même construit.
Le second nécessite une piste agentique avec sandbox et tests. Il n'entre pas
dans le pipeline générique tant que cette architecture n'est pas approuvée.

## Première version recommandée

Pour le prochain cycle de conception, les cas suivants sont prioritaires :

1. communication/rédaction ;
2. question-réponse avec contexte fourni ;
3. extraction structurée ;
4. résumé/synthèse ;
5. classification/routage ;
6. raisonnement borné ;
7. code court avec validation statique ou test contrôlé ;
8. dialogue multi-tour borné.

Les cas traduction/multilingue et analyse de données nécessitent une conception
linguistique ou de représentation plus précise. RAG, repository engineering et
tool-use restent des extensions séparées.

## Règles de non-surinterprétation

- Une influence benchmark ne signifie pas une réutilisation de données.
- Une catégorie académique ne prouve pas la réussite d'un workflow professionnel.
- Une note de juge ne prouve pas l'exactitude factuelle.
- Un test de syntaxe ne prouve pas la correction fonctionnelle du code.
- Un score SWE-bench ne doit pas être attribué au modèle sans préciser l'agent,
  les outils et l'environnement.
- Une catégorie absente ou non testable doit rester explicitement non scorée.
