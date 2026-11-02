# Model Compass — scope et logique de décision

Cette page formalise le changement de positionnement décidé les 8 et 9
septembre 2026. Le dépôt ne se limite plus à produire un signal de screening
avant une autre évaluation : il produit un rapport de recommandation technique
générique, organisé par cas d'usage, pour aider un humain à répondre à des
appels d'offres.

## Mission

**Model Compass** évalue les modèles LLM accessibles via OpenRouter sur un
catalogue stable de cas d'usage génériques. Il mesure la qualité fonctionnelle,
la sécurité, le coût du modèle et la performance, puis fournit pour chaque cas
d'usage :

- une note détaillée pour chaque modèle évalué ;
- un seuil minimal de qualité adapté au cas d'usage ;
- un classement des modèles qui franchissent ce seuil ;
- un ou plusieurs modèles recommandés ;
- les preuves, limites et dimensions manquantes qui expliquent le résultat.

Le rapport est une **recommandation technique**. La sélection finale appartient
à un humain qui connaît l'appel d'offres, son contexte et ses contraintes.

## Principe de stabilité

Le pipeline est volontairement générique et réutilisable :

- il ne reçoit pas le contenu d'un appel d'offres ;
- il ne reçoit pas de critères propres à un client ;
- il n'utilise pas de dataset client ou de données métier confidentielles ;
- il utilise un catalogue versionné de cas d'usage et de prompts génériques ;
- il produit le même type de rapport à chaque exécution ;
- il peut évoluer entre deux versions du catalogue, mais ne doit pas être
  reconfiguré pour chaque appel d'offres.

L'humain fait ensuite correspondre les résultats génériques aux besoins du
dossier qu'il connaît.

## Catalogue actif

Le catalogue par défaut est `data/catalog/model_compass_use_cases_v2.json`
(`model-compass-use-cases-v2.1`, suite `generic-screen-v2`). Il relie les 34
prompts qualité à huit cas d'usage :

| Cas d'usage | Prompts | Seuil |
| --- | ---: | ---: |
| Structured extraction | 0-4 | 4,0 / 5 |
| Code generation | 5-9 | 4,0 / 5 |
| Contextual question answering | 10-14 | 4,0 / 5 |
| Reasoning and analysis | 15-19 | 4,0 / 5 |
| Classification and routing | 20-23 | 4,0 / 5 |
| Summarization | 24-26 | 3,5 / 5 |
| Concise communication | 27-29 | 3,5 / 5 |
| Instruction following | 30-33 | 4,0 / 5 |

### Catalogue v1 (référence historique)

Le catalogue `data/catalog/model_compass_use_cases.json`
(`model-compass-use-cases-v1.1`) reste utilisé avec `QUALITY_SUITE=v1`. Il
relie les 16 prompts de la suite v1 à six cas d'usage :

| Cas d'usage | Prompts | Seuil initial |
| --- | ---: | ---: |
| Structured extraction | 0-2 | 4,0 / 5 |
| Code generation | 3 | 4,0 / 5 |
| Factual question answering | 4-6 | 4,0 / 5 |
| Reasoning and analysis | 7-9 | 4,0 / 5 |
| Instruction following | 10-12, 15 | 4,0 / 5 |
| Concise communication | 13-14 | 3,5 / 5 |

Ces seuils sont des **valeurs de démarrage provisoires**. Ils doivent être
calibrés après la définition précise des catégories, des critères de réussite
et de la difficulté des tâches. Modifier le catalogue change la version du
benchmark et doit être visible dans les résultats.

## Logique de décision

La décision comporte deux niveaux indépendants.

### 1. Éligibilité qualité

Pour chaque couple `cas d'usage / modèle`, les scores de **contenu** des prompts
du catalogue sont moyennés par prompt. Les lignes de conformité de format
(`output_format_compliance`) n'y entrent pas : elles sont publiées à part, dans
la colonne `format_compliance_rate`, pour qu'une bonne réponse qui ne respecte
pas le format « réponse seule » ne fasse jamais baisser la qualité du cas
d'usage. La couverture indique la proportion de prompts du cas d'usage
réellement scorés.

```text
qualité éligible =
    qualité du cas d'usage >= seuil du cas d'usage
    et couverture qualité = 100 %
```

Un modèle sous le seuil n'est pas recommandé pour ce cas, même s'il est moins
cher ou plus rapide. Tous les modèles restent toutefois visibles dans le
rapport avec leur score et leur statut.

### 2. Classement pondéré

Le score de décision utilise quatre composantes normalisées sur 0-100 :

| Composante | Poids par défaut | Source |
| --- | ---: | --- |
| Qualité fonctionnelle | 50 % | Score qualité du cas d'usage, échelle 1-5 normalisée |
| Sécurité générique | 25 % | RSI, échelle 0-100 |
| Coût du modèle seul | 20 % | Coût de 1 000 requêtes du profil avec la longueur de sortie mesurée du modèle ; bornes logarithmiques fixes dans le catalogue |
| Performance | 5 % | Latence p95 ; bornes logarithmiques fixes dans le catalogue |

```text
score_decision =
    poids_qualité × qualité
  + poids_sécurité × sécurité
  + poids_coût × coût
  + poids_performance × performance
```

Les poids par défaut viennent du catalogue. Ils peuvent être remplacés sans
modifier le code avec `MODEL_COMPASS_WEIGHTS`, par exemple :

```bash
MODEL_COMPASS_WEIGHTS='{"quality":0.60,"security":0.20,"cost":0.15,"performance":0.05}' make merge
```

Les poids doivent être positifs et leur somme doit être égale à `1.0`. Le
rapport et le manifeste enregistrent toujours les poids effectivement utilisés.
Un run collecté avec `SECURITY=skip` met le poids sécurité à 0 et remet les
trois autres à l'échelle (par défaut 0,67 / 0,27 / 0,07) ; le rapport le
signale sur chaque page.

### Pourquoi ces poids

Un poids ne se justifie pas seul : ce qui compte est l'arbitrage qu'il impose
entre deux composantes, sur les ancres fixes du catalogue. Un point de qualité
sur l'échelle 1-5 vaut 25 points de la composante qualité. Le coût perd
33,3 points par décade de coût (ancres 0,05–50 USD pour 1 000 requêtes, trois décades), la
performance 67,7 points par décade de latence p95 (ancres 1–30 s), et la
sécurité un point par point de RSI. `implied_tradeoffs`
(`src/evaluators/recommendation.py`) calcule ces arbitrages ; le rapport les
affiche dans la page *Use cases in detail*.

| Profil | Qualité | Sécurité | Coût | Perf. | 1 point de qualité vaut | Un prix 10 fois plus bas vaut | Une fuite confirmée coûte |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| `quality_first` | 70 % | 20 % | 7 % | 3 % | plus que tout écart de prix | 0,13 point | ≥ 0,4 point |
| `balanced` (défaut) | 50 % | 25 % | 20 % | 5 % | un écart de prix de 75 fois | 0,53 point | ≥ 0,7 point |
| `cost_sensitive` | 35 % | 20 % | 40 % | 5 % | un écart de prix de 4,5 fois | 1,52 point | ≥ 0,8 point |

« Une fuite confirmée coûte » est un minimum : le RSI d'un modèle qui fuit est
ramené sous 65, soit au moins 35 points de RSI perdus.

**Le défaut `balanced` (50/25/20/5).**

- **Qualité 50 %.** Un modèle d'un point meilleur l'emporte sur un modèle
  75 fois moins cher ; pour un demi-point, l'écart de prix doit rester sous
  9 fois. C'est l'ordre de grandeur qui sépare un modèle de pointe d'un modèle
  économique : un demi-point d'écart justifie de payer le modèle de pointe, un
  dixième de point non. Quand la qualité des modèles éligibles est à égalité
  statistique, comme dans le run de référence 0.4.0, le coût décide, et c'est
  voulu : à qualité indiscernable, payer plus n'a pas de justification
  générique.
- **Sécurité 25 %.** Une fuite confirmée coûte au moins 0,7 point de qualité,
  soit l'équivalent d'un prix 20 fois plus élevé : un modèle qui divulgue son
  contexte caché doit être nettement meilleur pour rester premier. La sécurité
  reste compensatoire, car le RSI ne mesure qu'un périmètre étroit (la
  divulgation d'un secret) ; un dossier où la sécurité est éliminatoire doit
  l'appliquer comme critère d'exclusion, hors de l'outil.
- **Coût 20 %.** Il départage les modèles de qualité proche sans pouvoir
  racheter un écart de qualité réel : sur toute la plage des ancres (un facteur
  1 000), il ne vaut que 1,6 point de qualité.
- **Performance 5 %.** Une latence p95 dix fois plus élevée ne vaut que
  0,27 point de qualité : le profil de charge par défaut (`enterprise_qa`)
  traite des questions où quelques secondes n'invalident pas une réponse. Une
  application interactive doit passer par un autre profil ou par
  `MODEL_COMPASS_WEIGHTS`.

**Les deux autres profils.**

- `quality_first` : sur toute la plage des ancres, le coût ne vaut que
  0,4 point de qualité ; il ne départage que des modèles déjà proches. Pour des
  réponses critiques (juridique, médical, décision engageante).
- `cost_sensitive` : un point de qualité vaut un prix 4,5 fois plus bas. Pour
  un fort volume ou un budget contraint, quand un modèle légèrement moins bon
  mais beaucoup moins cher reste acceptable.

Les profils ne changent jamais le rang publié, qui suit les poids du run. Ils
montrent si la recommandation résiste au profil qui correspond à l'appel
d'offres : une carte marquée *weight-profile-sensitive* nomme le leader de
chaque profil, et l'humain retient celui du profil qui correspond au dossier.
La plage de rang sous ±10 % (*fragile*) complète cette lecture pour de petites
variations autour du profil retenu.

### Pourquoi ces seuils

Le seuil d'un cas d'usage est **non compensatoire** : un modèle sous le seuil
est exclu, quel que soit son prix. Avec six items par cas d'usage :

- **4,0 / 5 pour les cas d'usage à contrôle déterministe.** Un item réussi vaut
  5, un échec 1, et le crédit partiel donne une valeur intermédiaire. Un échec
  complet sur six donne (5 × 5 + 1) / 6 = 4,33 et reste éligible ; deux échecs
  donnent 3,67 et excluent. Le seuil tolère donc une erreur sur six, pas deux.
- **3,5 / 5 pour la synthèse et la communication concise**, notées par les
  juges sur une échelle graduée : 3 veut dire qu'un critère n'est que
  partiellement rempli, 4 qu'il reste un défaut mineur hors critère. 3,5 exige
  qu'en moyenne la réponse soit plus proche de « défaut mineur » que de
  « critère partiel », ce qui laisse de la place à la sévérité variable des juges
  sur des critères en partie subjectifs.

Ces seuils restent `draft`. Ils passent à `calibrated` après un run de
référence de la suite v3 et une relecture humaine d'environ 50 réponses jugées
(voir le [plan de livraison](plans/plan-livraison-v0.4.md)).

Les catalogues `model-compass-use-cases-v1.2`, `v2.2` et `v3.1` fixent les
bornes du calcul : 0,05–50 USD pour 1 000 requêtes du profil et 1–30
secondes pour la latence p95. Le coût d'une requête est la taille d'entrée du
profil au prix d'entrée, plus la longueur de sortie que le modèle a réellement
produite sur la suite qualité au prix de sortie : le prix affiché seul ignore
qu'un modèle peu cher au token peut en produire dix fois plus. Les anciennes
ancres (0,10–100 USD par million de tokens) couvraient aussi trois décades, donc
les arbitrages ci-dessus ne changent pas. En dessous de la borne meilleure le score est 100 ;
au-dessus de la borne moins bonne il est 0 ; entre les deux l'échelle est
logarithmique. Un coût nul (modèle gratuit) vaut 100. Ces scores ne sont pas
recalculés relativement aux modèles du run. Si la latence p95 manque, la preuve
de performance est absente ; le débit tokens/s ne la remplace pas.

Si une composante manque, le modèle reste visible mais reçoit le statut
`insufficient_decision_evidence` et aucun rang de recommandation. Le pipeline
ne remplace pas silencieusement une preuve absente par une valeur favorable.

## Égalités et statuts

Le classement utilise un rang dense. Il n'existe pas de règle artificielle de
départage : plusieurs modèles ayant exactement le même score conservent le
même rang et peuvent tous être `recommended`.

Les statuts sont :

- `recommended` : meilleur rang parmi les modèles éligibles et suffisamment
  documentés ;
- `eligible` : dépasse le seuil et possède les preuves nécessaires, mais n'a
  pas le meilleur rang ;
- `below_quality_threshold` : qualité insuffisante pour ce cas d'usage ;
- `insufficient_quality_evidence` : couverture ou score qualité manquant ;
- `insufficient_decision_evidence` : qualité éligible, mais sécurité, coût ou
  performance manquant.

Le nombre de modèles évalués ou affichés n'est pas limité artificiellement.

## Sécurité, conformité et coût

La sécurité est générique et comparable entre les modèles : prompt injection,
fuite de secrets, demandes dangereuses, respect des instructions et politiques
de rétention disponibles via OpenRouter.

Le pipeline ne décide pas automatiquement de la conformité à une exigence
client comme la localisation des données, HDS, SecNumCloud, une certification
particulière ou un SLA contractuel. Ces points sont vérifiés par l'humain.

Le coût couvre uniquement le modèle : tokens d'entrée, tokens de sortie, TCO
projeté et coût réel observé lorsque disponible. Il exclut l'infrastructure,
le RAG, le stockage, l'orchestration, l'intégration, la supervision et la
licence d'une solution complète.

## Artefacts et surfaces

Le benchmark résumé reste une ligne par modèle :

```text
results/benchmark_<timestamp>.{csv,json}
```

Le détail de recommandation est séparé pour conserver plusieurs lignes par
modèle :

```text
results/recommendations/benchmark_<timestamp>_recommendations.{csv,json}
```

Chaque ligne de cet artefact correspond à un couple `use_case_id / model` et
contient le seuil, la couverture, les quatre composantes, le score pondéré, le
rang, le statut et les preuves manquantes. Le rapport HTML (`make export-html`)
affiche ce même artefact.

## Hors périmètre

Model Compass ne réalise pas :

- l'analyse automatique d'un DCE, CCTP ou cahier des charges ;
- l'extraction d'exigences propres à un client ;
- la personnalisation automatique des prompts pour un appel d'offres ;
- l'évaluation sur des données confidentielles ou un workflow métier réel ;
- la recommandation d'une architecture complète ;
- le calcul du coût total d'une solution ;
- la sélection automatique d'un fournisseur final ;
- la certification réglementaire ;
- la décision finale d'adoption ;
- la génération automatique d'une réponse commerciale.

## Travail méthodologique restant

Le contrat logiciel est en place, mais la méthodologie doit encore être
renforcée :

1. confirmer la liste des cas d'usage de la première version ;
2. définir les critères de réussite propres à chaque cas ;
3. calibrer les seuils sur des tâches représentatives ;
4. vérifier la stabilité des catégories et des pondérations ;
5. comparer les recommandations génériques à `gen-e2-eval` sur les mêmes
   modèles, sans confondre les deux types de preuve.

Les seuils et le catalogue ne doivent donc pas être présentés comme une
certification de pertinence métier.
