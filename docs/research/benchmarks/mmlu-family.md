# Dossier benchmark — MMLU et MMLU-Pro

**Famille :** Massive Multitask Language Understanding
**Sources gelées :** MMLU arXiv `2009.03300v3` et dépôt `hendrycks/test` commit `4450500`; MMLU-Pro arXiv `2406.01574v6` et dépôt `TIGER-AI-Lab/MMLU-Pro` commit `f418b11`
**Statut de la source :** référence pour la couverture académique et le QCM ; non importée comme score Model Compass

## 1. Résumé exécutif

MMLU mesure la connaissance et la compréhension dans 57 tâches couvrant des
matières académiques et professionnelles. Son unité de test est une question à
choix multiple et sa métrique principale est l'accuracy.

MMLU-Pro est une évolution plus difficile et plus orientée raisonnement :

- plus de 12 000 questions annoncées ;
- 14 domaines : Biology, Business, Chemistry, Computer Science, Economics,
  Engineering, Health, History, Law, Math, Philosophy, Physics, Psychology et
  Others ;
- 10 choix par question au lieu de 4 ;
- élimination de questions jugées triviales ou bruitées ;
- 24 styles de prompt étudiés ;
- baisse rapportée de 16 à 33 points par rapport à MMLU selon les modèles ;
- sensibilité aux variations de prompt annoncée autour de 2 % pour MMLU-Pro
  contre 4–5 % pour MMLU dans l'étude.

MMLU et MMLU-Pro sont utiles pour étudier les connaissances et le raisonnement
académique. Ils ne mesurent pas directement la réussite d'un workflow de
consulting, la qualité d'une réponse documentaire client, la sécurité ou le coût.

## 2. Construct et décision supportée

Le construct principal est une combinaison de :

- connaissances générales et spécialisées ;
- compréhension de questions ;
- raisonnement nécessaire pour choisir une option ;
- parfois calibration implicite via les probabilités des choix, selon le protocole.

La décision supportée est une comparaison de maîtrise académique/professionnelle
sur les matières couvertes. Ce n'est pas une décision d'adoption d'un modèle
pour un cas d'usage métier.

Pour Model Compass, MMLU-Pro est surtout une source pour :

- la granularité par domaine ;
- la séparation du score global et des scores de matière ;
- le contrôle de la difficulté et de la sensibilité au prompt ;
- le rappel qu'une question à choix multiple est une mesure différente d'une
  tâche ouverte ou d'une sortie structurée.

## 3. Taxonomie et composition

### MMLU original

Le benchmark original couvre 57 tâches, incluant notamment mathématiques,
sciences, histoire, droit, médecine, économie, informatique et éthique. Les
sujets sont organisés en ensembles de matières, mais le nombre de questions et
la difficulté ne doivent pas être supposés identiques entre sujets.

Le dépôt fournit un code d'évaluation et des fichiers de données. La structure
historique distingue typiquement exemples de démonstration, validation et test,
avec un protocole few-shot selon l'étude.

### MMLU-Pro

MMLU-Pro conserve l'idée de matières mais réorganise et nettoie davantage le
contenu. Le dépôt et le papier indiquent 14 domaines, plus de 12 000 questions
et 10 choix de réponses. Le benchmark étudie aussi plusieurs styles de prompt
et observe que le CoT améliore davantage les performances que dans MMLU,
cohérent avec des questions plus exigeantes en raisonnement.

La catégorie n'est pas une catégorie d'usage Model Compass. Une question de
Business ou Computer Science mesure une connaissance/question-réponse dans un
format fermé, pas toute la compétence « conseil » ou « développement ».

## 4. Protocole de test

Les protocoles historiques utilisent des questions à choix multiple, avec un
format de réponse qui doit être extrait et comparé à l'option correcte. La
comparaison doit toujours préciser :

- zero-shot ou nombre de shots ;
- template exact du prompt ;
- présence ou absence de CoT ;
- méthode d'extraction de la lettre/réponse ;
- température et paramètres de génération ;
- modèle d'API ou modèle local ;
- séparation des questions de démonstration et d'évaluation.

MMLU-Pro documente plusieurs styles de prompt et propose des scripts API et
locaux, avec gestion des retries, du nombre de workers et de la longueur
maximale. La méthode d'extraction des réponses est également étudiée.

## 5. Notation et agrégation

La métrique principale est l'accuracy par question : une réponse correcte vaut
1, une réponse incorrecte vaut 0. La synthèse doit ensuite distinguer :

- accuracy par sujet/domaine ;
- moyenne macro des sujets ;
- éventuelle moyenne micro par nombre de questions ;
- baseline de hasard : 25 % pour quatre choix dans MMLU, environ 10 % pour
  dix choix dans MMLU-Pro ;
- nombre de réponses non extractibles et erreurs techniques.

La moyenne globale masque les écarts de matières. Un modèle peut être très bon en
Computer Science et faible en Law ou en Health. Pour Model Compass, la métrique
par domaine doit donc rester visible et ne doit pas être transformée sans
justification en une qualité fonctionnelle universelle.

Les scores publiés ne fournissent pas nécessairement une incertitude suffisante
pour décider qu'une différence de quelques dixièmes est significative. Nous
devons calculer nos propres intervalles ou utiliser un test de différence
appariée si nous réutilisons une structure similaire.

## 6. Baselines, robustesse et contamination

Les baselines historiques incluent le hasard et des modèles de référence. Elles
sont utiles pour contrôler la difficulté mais ne valent pas baseline humaine
pour un contexte de consulting.

Risques à documenter :

- questions publiques potentiellement présentes dans les données d'entraînement ;
- contamination par mémorisation plutôt que raisonnement ;
- dépendance au template de prompt et à l'extraction de lettre ;
- matières et cultures sous-représentées ;
- mélange de connaissances déclaratives et raisonnement ;
- déséquilibre de difficulté entre sujets ;
- benchmark principalement anglophone et académique.

MMLU-Pro réduit certains effets de hasard et de questions triviales, mais ne
supprime pas les risques de contamination ou le décalage avec un besoin client.

## 7. Coût, reproduction et compatibilité OpenRouter

Le protocole QCM est compatible avec le client OpenRouter si :

- le prompt exact et les options sont envoyés comme texte ;
- la réponse est récupérée et parsée ;
- le modèle ne renvoie pas une sortie hors format ;
- les retries et erreurs de transport sont séparés des erreurs de réponse.

La suite complète peut devenir coûteuse avec plusieurs modèles et répétitions.
Un sous-ensemble interne inspiré des domaines, mais réécrit par l'équipe et
versionné, est plus compatible avec le budget et la gouvernance Model Compass.

La redistribution des questions originales doit être vérifiée. La Phase 1 ne
copie aucune question MMLU dans le dépôt.

## 8. Transfert provisoire vers Model Compass

### À adapter

1. Reporting par domaine et par famille de capacité.
2. Baseline hasard et compte des réponses non parsables.
3. Test de sensibilité au template de prompt.
4. Multi-choice comme évaluateur déterministe pour certains concepts fermés.
5. Séparation entre connaissance, raisonnement et tâche métier.

### À observer

- MMLU-Pro comme signal de difficulté et de robustesse au prompt.
- Différence entre CoT et réponse directe.
- Effet de l'augmentation du nombre de choix sur la discrimination.
- Domaines Business, Economics, Computer Science et Engineering comme sources
  d'idées, pas comme validation de cas d'usage.

### À rejeter pour l'instant

- Utiliser l'accuracy MMLU/MMLU-Pro comme qualité fonctionnelle globale.
- Importer leurs questions publiques sans revue de licence et de contamination.
- Déduire qu'un bon score en matière académique garantit la réussite d'un
  workflow document, RAG, code ou agent.

## 9. Implications pour nos prompts et rubriques

- Ajouter au blueprint `answer_format`, `choice_count`, `extraction_rule` et
  `chance_baseline` pour tout item fermé.
- Publier les résultats par domaine et non seulement un score global.
- Tester plusieurs formulations du prompt sur un échantillon avant de geler la
  suite.
- Conserver les réponses brutes et les réponses qui ne contiennent pas une
  option identifiable.
- Ne pas afficher une accuracy sans indiquer le nombre de questions, le domaine,
  la version et le protocole.
- Ajouter des tâches ouvertes parallèles lorsque la capacité visée est une
  pratique professionnelle et pas une connaissance scolaire.
- Utiliser la difficulté comme métadonnée à calibrer, pas comme intuition de
  l'auteur du prompt.

## 10. Questions ouvertes

- MMLU-Pro ou une suite interne inspirée de ses 14 domaines pour la première
  version ?
- Quelle part de connaissance académique est réellement utile à Palo IT
  Singapore ?
- Faut-il une catégorie « knowledge diagnostic » séparée de la recommandation ?
- Comment contrôler la langue et les références culturelles si la suite doit
  couvrir l'anglais et le français ?
- Quelle règle de confiance appliquer lorsqu'un domaine contient peu d'items ?

## Décision provisoire

**Transfert : ADAPT.** Nous reprenons le reporting par domaine, la correction
QCM déterministe et l'analyse de robustesse au prompt. Nous ne reprenons ni les
scores publics ni les questions publiques comme composants directs du score
Model Compass.
