# Méthodologie de la suite de qualité

Cette page formalise la manière dont la suite de prompts de qualité doit être
comprise, validée et utilisée dans ce projet.

## 1. Objectif

La suite de qualité est un outil de **mesure générique** utilisé par Model
Compass pour comparer les modèles par cas d'usage standardisés.

Elle ne remplace pas une évaluation fonctionnelle client dans
[gen-e2-eval](https://github.com/GLOBAL-PALO-IT/gen-e2-eval). Son rôle est de
fournir le composant qualité d'une recommandation technique et de répondre à la
question :

> « Quels modèles franchissent le seuil de qualité d'un cas d'usage générique ? »

Le catalogue qui relie les prompts aux cas d'usage et fixe les seuils se trouve
dans `data/catalog/model_compass_use_cases.json`.
Les seuils de cette version sont provisoires : ils doivent être recalibrés après
la définition des critères de réussite et de la difficulté de chaque tâche.

## 2. Origine et mode de correction des prompts

Les 16 prompts sont **rédigés en interne par l'équipe du projet** ; ils ne
proviennent pas d'un jeu de données de benchmark public. Chacun est rattaché à
exactement une dimension (`quality_dimension`) et une catégorie (`category`)
définies dans
[data/prompts/quality_prompts.json](https://github.com/Palo-IT-GitHub-Demos/model-compass/blob/main/data/prompts/quality_prompts.json).

La catégorie détermine le mode de correction :

- si la catégorie est enregistrée dans `CHECKS`
  ([deterministic_eval.py](https://github.com/Palo-IT-GitHub-Demos/model-compass/blob/main/src/evaluators/deterministic_eval.py)),
  la réponse est corrigée en Python pur (JSON, syntaxe, réponse exacte), sans
  aucun appel à un modèle ;
- sinon (`generic_judgment`), le prompt doit fournir des `judge_criteria`
  explicites et est envoyé au panel de juges à l'aveugle (alias A/B/C… pour
  neutraliser le biais de position), selon le protocole de
  Zheng, Chiang, Sheng et al., *Judging LLM-as-a-Judge with MT-Bench and
  Chatbot Arena*, NeurIPS 2023 —
  [arXiv:2306.05685](https://arxiv.org/abs/2306.05685), déjà cité dans
  l'[audit du 2026-08-21](audit-2026-08-21.md).

Sans mitigation, cette étude mesure un biais de position marqué et variable
selon le juge : 23,8 % de verdicts cohérents après inversion de l'ordre des
deux réponses pour Claude-v1, 46,2 % pour GPT-3.5, 65,0 % pour GPT-4 (leur
Table 2 ; un verdict « cohérent » signifie que le juge garde le même avis une
fois l'ordre inversé). **Ce chiffre de référence inclut déjà, dans leur prompt
« default », une instruction explicite du type « évite tout biais de
position »** — comparable à la règle « Do NOT favour the first response you
read » de notre propre prompt système — et cette seule instruction ne suffit
pas à supprimer le biais (65 % de cohérence pour GPT-4, donc encore 35 %
d'inconsistance).

**Ce qui est réellement prouvé par ce papier, et ce qui ne l'est pas :**

- Prouvé : le biais de position est réel et significatif, y compris avec une
  instruction anti-biais dans le prompt.
- Prouvé (Table 13) : rejouer le jugement en inversant l'ordre et ne compter
  une victoire que si elle est confirmée dans les deux sens (« conservative
  swap ») est la méthode que les auteurs ont effectivement utilisée et
  mesurée dans toutes leurs expériences.
- **Non chiffré par le papier** : « assigner les positions aléatoirement » est
  seulement mentionné comme une alternative plausible (« can be effective at a
  large scale with the correct expectations »), sans table de résultats
  dédiée — les auteurs précisent explicitement qu'ils ont utilisé l'approche
  conservative, pas celle-ci, pour leurs mesures.
- **Écart avec notre pipeline** : leurs chiffres portent sur une comparaison
  à 2 réponses (A vs B). `quality_judge.py` fait noter **N réponses
  anonymisées simultanément** dans un seul appel (voir le prompt système :
  *"score multiple model responses"*), un cadre que ce papier ne mesure pas.

`_blind_alias_map` dans `quality_judge.py` implémente la variante « position
aléatoire » : l'association lettre ↔ modèle est re-mélangée par un tirage
pseudo-aléatoire propre à chaque prompt et chaque tentative (seed dérivée de
`quality_suite_id`, de l'index et du texte du prompt). C'est un choix
théoriquement motivé et cohérent avec la littérature, **mais non validé
empiriquement dans ce projet** : aucun test interne ne mesure à ce jour si nos
3 juges (Claude, GPT, Gemini) restent cohérents quand on rejoue le même
prompt avec un autre tirage d'alias. Tant que ce test n'est pas fait, la
mitigation doit être présentée comme une précaution documentée, pas comme une
preuve d'efficacité.

Ce contrat (référence objective **ou** critères de jugement explicites) est
imposé à l'entrée par le schéma Pydantic `QualityPrompt` — voir la décision
**D9** de l'[ADR 0001](adr/0001-architecture-initiale.md).

### Dimensions couvertes

| Dimension | Prompts | Catégorie(s) | Mode de correction |
| --- | --- | --- | --- |
| structured_output | 3 | json_output | déterministe (JSON strict) |
| code_correctness | 1 | code_generation | déterministe (syntaxe Python + contrat de fonction, non exécuté) |
| factual_sanity | 3 | factual_sanity | déterministe (réponse exacte) |
| elementary_reasoning | 3 | exact_answer, logical_reasoning | déterministe (réponse exacte) |
| instruction_reliability | 4 | instruction_following (3), generic_judgment (1) | 3 déterministes + 1 jugé |
| concise_communication | 2 | generic_judgment | jugé à l'aveugle |
| output_format_compliance | dérivée | tout prompt `strict_output` | déterministe (respect littéral du format) |

13 prompts sur 16 sont donc corrigés sans aucun appel à un juge externe ; les
3 prompts restants suivent le protocole de jugement à l'aveugle ci-dessus.

### Contenu et format sont notés séparément

Un prompt marqué `strict_output` produit **deux lignes** : son score de contenu
(la réponse est-elle juste ?) dans sa dimension d'origine, et un score de
respect du format dans la dimension dérivée `output_format_compliance`.

Avant cette séparation, une réponse correcte encadrée par des ` ``` ` était
notée 1/5 sur `code_contract` : la dimension mesurait le formatage tout en
étant lue comme une compétence de codage. Les deux signaux sont désormais
lisibles indépendamment.

### Deux échelles, publiées séparément

`avg_quality_score` agrège deux échelles qui ne sont pas équivalentes : les
contrôles déterministes sont du succès/échec rendu en **1 ou 5**, tandis que
les juges notent en continu de 1 à 5. Comme 13 prompts sur 16 sont
déterministes, le chiffre global est dominé par du binaire.

`avg_quality_score_deterministic` et `avg_quality_score_judged` sont donc
publiés côte à côte dans le CSV et les deux dashboards, pour voir laquelle des
deux échelles fait le classement. De même, `quality_pass_rate` (part des
prompts ≥ 4/5) peut être **identique pour plusieurs modèles** — c'est un
indicateur de couverture, pas un classement.

### Prompts écartés pour corruption d'entrée suspectée

Quand **tous** les modèles d'un run manquent un prompt dont la réponse de
référence est connue et fixe, la cause commune est bien plus probablement la
requête réellement arrivée chez le fournisseur (redaction par un proxy,
substitution de gabarit, troncature) qu'une défaillance simultanée de modèles
sans lien entre eux.

Le prompt est alors retiré des agrégats **et de leur dénominateur** (il n'est
donc pas non plus compté comme un trou de couverture), et compté dans
`quality_excluded_prompt_count`. La détection est volontairement étroite : elle
ne considère que les prompts à réponse de référence et au moins deux modèles,
de sorte qu'un prompt simplement difficile, ou mal formaté par tout le monde,
n'est jamais écarté.

Conformément à l'invariant de préservation des preuves, **ni la réponse ni le
score brut ne sont réécrits** : la ligne reste consultable dans
`results/quality_details/` avec
`verification_status=suspected_input_corruption`.

## 3. Fiabilité et biais du panel de juges

### Biais d'auto-préférence

Le panel compte 3 juges Copilot, chacun adossé à un fournisseur (Claude/Anthropic,
GPT-4o/OpenAI, Gemini/Google) qui est aussi l'un des fournisseurs potentiellement
présents dans `TARGET_MODELS`. Un juge peut donc, sans le savoir, noter une
réponse produite par un modèle de son propre fournisseur.

**Ce que l'aveuglement par alias couvre** : le juge ne reçoit jamais `alias_map`
ni l'identifiant du modèle — seulement une lettre (A/B/C…) et le texte de la
réponse (voir `.github/agents/judge-*.agent.md`, "Blind evaluation").

**Ce que l'aveuglement par alias ne couvre pas** : une réponse qui se
présente elle-même ("As an AI developed by Anthropic…") réintroduit l'indice
que l'alias devait masquer. Depuis 2026-09-03, `quality_judge.py::_scrub_self_identification`
retire, de manière best-effort, les tournures explicites d'auto-présentation
(cf. `I'm <vendor>`, `As <vendor>`, `developed/created/trained/made by <vendor>`)
avant que le texte n'atteigne le fichier `judging_{ts}.json` — la copie brute
reste intacte dans `pending_{ts}.json` pour l'évidence/l'audit, conformément à
l'invariant "ne jamais réécrire une réponse". Cette détection est **best-effort,
pas une garantie** : une divulgation paraphrasée ou indirecte n'est pas
interceptée.

**Aucune correction de biais n'est appliquée après coup** (pas de pondération
différente par juge, pas d'exclusion d'un juge sur ses propres modèles) : le
panel reste 3 juges symétriques. Si un futur audit constate un biais
systématique mesurable (ex. un juge note significativement plus haut les
réponses de son propre fournisseur une fois l'alias percé), la mitigation à
envisager est un pool de juges dédié, distinct des fournisseurs évalués — non
implémenté à ce jour.

### Désaccord inter-juges

`judge_disagreement` (colonne du CSV principal et de `results/quality_details/`)
est l'étendue (max − min) des 3 scores bruts avant moyenne, par
(modèle, prompt, tentative). `quality_judge_disagreement_rate` résume, par
modèle, la part des prompts jugés dont l'étendue est ≥ 2 — un désaccord de 2
points ou plus sur une échelle 1-5 avec 3 juges signifie que le panel n'est pas
d'accord sur le palier de qualité de la réponse (ex. 3 vs 5), pas seulement sur
un point d'arrondi (ex. 4 vs 5).

Exemple réel observé (run du 2026-09-02, prompt 15) : OpenAI = 3
("lacks concrete success criteria"), Anthropic = 4, Google = 5
("meets all criteria") sur la même réponse — moyenne 4.0, mais
`judge_disagreement = 2`. La moyenne seule masquait ce désaccord de sévérité
systématique par juge.

**Choix retenu : conserver la moyenne, publier le désaccord.** L'alternative
envisagée était de remplacer la moyenne par la médiane. Avec exactement 3
juges, la médiane revient à choisir le score du juge du milieu et à ignorer
totalement les deux autres — ce n'est pas nécessairement plus juste qu'une
moyenne, et cela aurait silencieusement redéfini chaque score déjà publié.
`judge_disagreement`/`quality_judge_disagreement_rate` rendent le désaccord
visible sans changer la sémantique historique du score.

### Ancrage de la rubrique 1-5

Le désaccord ci-dessus venait d'une rubrique 1-5 insuffisamment ancrée : rien
n'indiquait explicitement ce qui sépare un 3 d'un 4 d'un 5 quand une réponse
remplit les `judge_criteria` mais qu'un juge aurait, par préférence
personnelle, préféré une formulation différente. Depuis 2026-09-03, les 3
fichiers `.github/agents/judge-*.agent.md` demandent explicitement au juge de
compter combien de `judge_criteria` sont remplis avant de noter, avec une règle
de décision fondée sur ce compte (5 = tous remplis, 3 = au moins un partiellement
rempli, etc.) et l'interdiction explicite de baisser une note pour une
préférence subjective absente des critères listés.

### Accord inter-juges et analyse des items (sidecars)

`make merge` écrit sous `results/quality_analysis/` deux fichiers qui décrivent
la fiabilité de l'écran qualité sans jamais modifier les scores bruts :

- `benchmark_<ts>_judge_agreement` : alpha de Krippendorff (intervalle) du
  panel et par dimension, taux d'accord exact et à ±1 point, score moyen par
  juge et écart moyen d'un juge par rapport à la moyenne des autres
  (indulgence/sévérité). `agreement_status = low_agreement` sous
  alpha = 0,667 (seuil conventionnel « conclusions provisoires »).
  L'alpha est `NaN` quand tous les scores sont identiques.
- `benchmark_<ts>_item_analysis` : par prompt, moyenne, écart-type entre
  modèles et corrélation item-total corrigée (`discrimination`). Statuts :
  `saturated` (tous les modèles ≥ 4), `floor` (aucun modèle > 2),
  `low_variance` (écart-type < 0,25), `negative_discrimination` (< −0,1),
  `insufficient_models` (< 3 modèles) et `suspected_input_corruption`.

Un item `saturated`, `floor` ou `low_variance` ne départage pas les modèles :
il est candidat à un durcissement ou à un retrait lors de la prochaine version
du catalogue. Ces statuts n'excluent aucun prompt des agrégats.

Les exemples ancrés (réponses types à 1, 3 et 5) ne sont pas encore ajoutés à
la rubrique : ils changeraient le comportement des juges et doivent être
validés sur le jeu de calibration humain prévu à l'étape 4 du plan 02.

### Validation stricte de la couverture avant fusion

Avant 2026-09-03, un juge qui omettait de noter un alias (erreur de frappe,
alias halluciné, réponse simplement oubliée) réduisait silencieusement la
moyenne à 1 ou 2 juges au lieu de 3, sans aucun signal. `MergePipeline._rebuild_quality_df`
vérifie désormais, pour chaque juge dont un fichier `scores_*.json` est chargé,
qu'il a noté 100 % des (prompt_id, tentative, alias) attendus dont la réponse
n'est pas vide — sinon la fusion échoue immédiatement (`ValueError`) en nommant
le juge et les tuples manquants, avec l'instruction de relancer ce juge. C'est
volontairement plus strict qu'un score individuel malformé (qui reste ignoré
avec un avertissement) : une couverture partielle change silencieusement le
sens du score moyen, une valeur isolée invalide ne fait que le priver d'une
contribution.

## 3 bis. Suite `generic-screen-v2` et exécution de code

### Pourquoi la v1 ne suffit pas

Diagnostic sur 12 runs et 3 modèles (2026-09-01 à 2026-09-04) :

- 9 prompts sur 16 valent 5,00 pour tous les modèles à chaque run : ils sont
  saturés et ne départagent rien tout en pesant dans la couverture ;
- les prompts 4 et 6 (« capitale de l'Australie », « plus grande planète du
  système solaire ») échouent parce que les modèles reçoivent `[ADDRESS]` à la
  place du lieu : le fournisseur masque les noms de lieux, le texte local est
  intact. C'est le cas `suspected_input_corruption`, pas un défaut de capacité ;
- les échecs du prompt 3 des premiers runs viennent d'un barème antérieur à la
  séparation contenu/format (balises markdown comptées comme erreur de contenu) ;
- seul le prompt 8 (syllogisme répondu `NO`) reflète une vraie erreur de modèle.

### Contenu de la v2

`QUALITY_SUITE=v2` (ou `--quality-suite v2`, à répéter pour `merge`) charge
`data/prompts/quality_prompts_v2.json` et
`data/catalog/model_compass_use_cases_v2.json`. La v2 est une suite
indépendante (identifiant et hash propres, `generic-screen-v1` inchangé et
conservé comme référence historique ; la v2 est le défaut depuis le basculement
de `QUALITY_SUITE`, sans run pilote réel préalable). Elle ne reprend
aucun prompt v1 et vise les cas d'usage prioritaires de
`docs/research/benchmark-to-use-case-mapping.md` :

| Cas d'usage | Items | Évaluateur |
|---|---:|---|
| Extraction structurée | 5 | JSON exact |
| Code court | 5 | tests exécutés dans le sandbox |
| Question-réponse avec contexte | 5 | réponse exacte (dont abstention) |
| Raisonnement borné | 5 | réponse exacte |
| Classification et routage | 4 | réponse exacte (dont `UNCLEAR`) |
| Résumé | 3 | rubrique, panel de juges |
| Communication concise | 3 | rubrique, panel de juges |
| Suivi d'instruction | 4 | réponse exacte, 1 rubrique |

Chaque item déclare le blueprint de l'ADR 0002 : `item_id`, `use_case_id`,
`construct`, `task_type`, `difficulty` (facile, moyen, difficile) et son statut
(`draft`), `language`, `evaluator`, `rubric_version` pour les items jugés,
`license_status` et `contamination_status`. Le chargement échoue si un champ
manque ou si un `item_id` est dupliqué. Les difficultés sont des hypothèses
d'auteur jusqu'à la calibration sur run réel (étape 5 du plan 02) ;
`contamination_status = internal_unscreened` signifie que les items sont
originaux mais pas comparés à des corpus publics. Les items évitent noms de
lieux, de personnes, adresses et courriels, que les fournisseurs masquent.

Les seuils du catalogue v2 (4,0 ; 3,5 pour résumé et communication) sont des
valeurs provisoires, au même titre que ceux de la v1.

### Contrat du sandbox de code

L'ADR 0002 exige un sandbox, des limites de ressources, des logs et une
attribution avant toute exécution de code généré. Contrat appliqué par
`src/evaluators/code_sandbox.py` :

- **Opt-in** : rien ne s'exécute sans `QUALITY_CODE_EXECUTION=true`. Sinon les
  réponses `code_execution` sont envoyées au panel de juges (critères fournis).
  `quality_metadata.code_execution` indique ce qui a été utilisé.
- **Avant exécution** : analyse AST ; imports limités à une liste blanche de la
  bibliothèque standard, appels (`open`, `eval`, `exec`, `getattr`…) et attributs
  dunder dangereux refusés. Un refus est un échec de la réponse (score 1, raison
  explicite).
- **Exécution** : sous-processus Python isolé (`-I -S`), environnement vide,
  répertoire temporaire, timeout de 5 s, limite CPU et taille de fichier
  (plus la mémoire sous Linux), sortie de l'utilisateur supprimée.
- **Notation** : 5 si tous les cas passent, sinon 1 ; la raison indique
  `x/y` cas passés. Si le sandbox est indisponible, la réponse est renvoyée
  aux juges et non comptée comme échec du modèle.
- **Logs** : hash du code, fonction, statut, cas passés, durée ; jamais le code.
- **Limite assumée** : défense en profondeur, pas une frontière de sécurité. Le
  réseau n'est bloqué que par la liste blanche d'imports et la mémoire n'est pas
  limitée sous macOS. À réserver aux réponses de modèles évalués.

## 4. Couverture du périmètre

Le module de correction déterministe résume lui-même sa limite :

> « The screen deliberately measures only provider-neutral fundamentals:
> structured output, factual sanity, elementary reasoning and instruction
> reliability. It is not a substitute for domain-specific task evaluation. »
> — [deterministic_eval.py](https://github.com/Palo-IT-GitHub-Demos/model-compass/blob/main/src/evaluators/deterministic_eval.py)

| Capacité | État |
| --- | --- |
| respect de format | couvert |
| suivi d'instructions | couvert |
| factualité simple | couvert |
| raisonnement simple | couvert |
| code minimal | partiellement couvert (une seule signature de fonction) |
| communication concise | couvert |
| long contexte | non couvert |
| tâches métier | non couvert |
| exécution réelle de code | non couvert (vérification syntaxique seulement) |
| évaluation de domaine spécialisé | non couvert |

Cette limitation doit être explicitement communiquée à chaque utilisation du
score qualité.

## 5. Validation de la suite

La qualité de la suite doit être validée selon trois niveaux.

### 5.1 Validation du contenu

Chaque prompt doit être revu par au moins une personne connaissant le projet et
vérifier :

- le prompt est non ambigu ;
- la réponse attendue est correcte ;
- la capacité testée est pertinente pour le screening ;
- le prompt n'introduit pas de biais artificiel ;
- le prompt reste provider-neutral.

Le document de revue initiale se trouve dans
[quality-validation/review-v1.md](quality-validation/review-v1.md).

### 5.2 Validation technique (déjà appliquée par le code)

Le schéma `QualityPrompt` et le pipeline garantissent, à l'entrée et à
l'export :

- chaque prompt a un type de correction défini (déterministe ou
  `judge_criteria` non vide) — décision D9 de l'[ADR 0001](adr/0001-architecture-initiale.md) ;
- `avg_quality_score` est une macro-moyenne par dimension, pas une moyenne
  plate sur tous les prompts — décision D10 du même ADR ;
- la suite est identifiée par `quality_suite_id` (hash du fichier de prompts),
  ce qui lie chaque résultat à une version exacte de la suite ;
- la couverture (`quality_coverage_rate`, `quality_dimension_coverage_rate`) et
  les erreurs de collecte (`quality_collection_error_count`) sont exportées
  séparément du score qualité.

Le détail de toutes les colonnes exportées est dans
[workflow.md](workflow.md) (section *Métriques de qualité exportées*).

### 5.3 Validation empirique (à la charge de l'opérateur du run)

- **Répétitions** : `QUALITY_REPETITIONS=1` par défaut, donc
  `quality_stability_score` reste `null` tant que cette variable n'est pas
  relevée à ≥ 2. Tout résultat utilisé pour une décision de shortlist doit être
  produit avec `QUALITY_REPETITIONS≥2` — limite déjà identifiée dans
  l'[audit du 2026-08-21](audit-2026-08-21.md) (section 3.5).
- vérifier que les scores ne sont pas tous identiques entre modèles ;
- comparer les classements obtenus sur plusieurs modèles ;
- noter les prompts qui ne discriminent pas assez et les revoir en priorité.

#### Interprétation de `QUALITY_REPETITIONS`

Pour un modèle et un prompt donnés, le taux de réussite observé est :

$$
r = \frac{\text{tentatives correctes}}{k}
$$

- $r=1$ : succès stable sur les tentatives observées ;
- $r=0$ : échec reproductible sur les tentatives observées ;
- $0<r<1$ : résultat instable.

Le score agrégé moyenne d'abord les tentatives d'un même prompt, puis les
prompts d'une dimension, puis les dimensions. Une répétition ne donne donc pas
plus de poids au prompt dans la note finale. `quality_stability_score` résume la
dispersion inter-tentatives et doit être lu avec les réponses détaillées.

### Intervalles bootstrap 95 % et sensibilité (A4/C2)

La fusion publie `avg_quality_score_ci95_low/high` dans le benchmark et
`quality_score_ci95_low/high` pour chaque cas d'usage dans les recommandations.
Sur 2 000 tirages reproductibles (graine locale dérivée du modèle, et du cas
d'usage le cas échéant), le bootstrap rééchantillonne les prompts **dans chaque
dimension**, puis les tentatives de chaque prompt avec remise. Il recalcule
la moyenne pondérée par dimension, puis la macro-moyenne ; pour un cas d'usage,
il recalcule la moyenne plate de ses prompts. Les bornes sont les quantiles
2,5 % et 97,5 % des tirages. Les scores et les rangs publiés restent inchangés.

Il faut au moins **3 tentatives distinctes sur chaque prompt scoré** et la
couverture complète des prompts attendus ; sinon les bornes sont `null`.
Dans le benchmark global, les exclusions pour corruption d'entrée suspectée
sont aussi retirées du dénominateur, conformément au score existant. Ces IC
reflètent le rééchantillonnage de cette suite et de ces tentatives, **pas** une garantie
de généralisation aux tâches métier. `quality_ci95_overlaps_leader` indique
le chevauchement des IC de qualité avec au moins un premier du classement,
pour les modèles éligibles avec IC disponible. Un chevauchement n'est pas
une preuve d'égalité statistique : les ex æquo restent définis uniquement
par l'égalité des scores de recommandation.

`recommendation_sensitivity_rank_min/max` et `recommendation_fragile`
décrivent 10 scénarios déterministes par cas d'usage : chacun des quatre
poids effectifs varie séparément de ±10 % **relatifs**, avec renormalisation
des quatre poids à 1 ; le seuil qualité varie également de ±10 % relatifs,
borné à l'échelle 1–5. Les autres poids et seuils restent fixes à chaque
scénario. `recommendation_fragile=true` si l'éligibilité ou le rang diffère
du scénario de référence ; les bornes de rang ignorent les scénarios où le
modèle n'a pas de rang. Une preuve de décision incomplète produit `null`
pour cette alerte, pas une fausse stabilité. Cette analyse locale ne remplace
ni la calibration humaine des seuils provisoires ni un test de toutes les
combinaisons de poids.

Pour `k=1`, une mauvaise réponse objective porte
`verification_status=optional_openrouter_recheck`. Une commande manuelle peut
envoyer deux rechecks supplémentaires au même modèle via OpenRouter. Pour
`k>1`, le statut `run_repetitions_available` indique que les données du run
suffisent déjà pour évaluer la reproductibilité ; la commande refuse alors de
générer des appels et des coûts supplémentaires.

Cette vérification ne recherche pas un responsable. Sans accès au payload reçu
par l'upstream exact et sans comparaison directe avec ce même upstream, elle ne
peut pas séparer un comportement du modèle, du fournisseur d'inférence ou du
routage OpenRouter. Ses conclusions sont volontairement limitées à
`confirmed_failure`, `not_reproduced`, `unstable` et `inconclusive`.

Les rapports sous `results/verification/` sont des preuves secondaires : les
dashboards les associent au benchmark, mais ils ne modifient ni la réponse ni
la note du run historique.

## 6. Éligibilité Model Compass et comparaison avec gen-e2-eval

Pour chaque cas d'usage du catalogue, les prompts associés sont agrégés par
modèle. Un modèle est qualité-éligible lorsque sa couverture est complète et
que sa moyenne atteint le seuil du cas d'usage. Le score qualité n'est jamais
abaissé artificiellement pour compenser un coût ou une latence favorable.

Les modèles éligibles sont ensuite classés dans
`results/recommendations/` avec les composantes suivantes :

- qualité du cas d'usage : 50 % par défaut ;
- RSI de sécurité générique : 25 % ;
- score de coût du modèle seul : 20 % ;
- score de performance : 5 %.

Les poids peuvent être remplacés par `MODEL_COMPASS_WEIGHTS`, mais les poids
effectifs et la version du catalogue sont toujours écrits dans le rapport. Une
preuve manquante produit un statut explicite et aucun rang, plutôt qu'une
valeur de remplacement optimiste. Les scores égaux restent ex æquo.

## 7. Comparaison avec gen-e2-eval

Le score qualité de ce projet et la validation métier de `gen-e2-eval` ne sont
pas directement comparables, car ils ne mesurent pas le même objet.

La bonne pratique est de comparer leur **capacité à sélectionner les mêmes
modèles pertinents**.

### Protocole recommandé

1. exécuter Model Compass sur les mêmes modèles ;
2. exécuter `gen-e2-eval` sur les mêmes modèles ;
3. comparer le top 3 et les classements globaux ;
4. noter les désaccords et les raisons possibles ;
5. conserver le résultat dans un fichier de comparaison.

Le template est dans
[quality-validation/gen-e2-eval-comparison-template.md](quality-validation/gen-e2-eval-comparison-template.md).

## 8. Critères d'acceptation

La suite est considérée comme correctement justifiée si elle remplit au moins
les règles suivantes :

- 100 % des prompts ont un mode de correction défini (déterministe ou
  `judge_criteria`) — déjà imposé par le schéma `QualityPrompt` ;
- le run utilisé pour une décision de shortlist a `quality_coverage_rate ≥ 0.8`
  et `quality_dimension_coverage_rate = 1.0` — seuils déjà appliqués par le
  pipeline pour activer `quality_cer_eligible` (décision D12 de
  l'[ADR 0001](adr/0001-architecture-initiale.md)) ;
- le run a été exécuté avec `QUALITY_REPETITIONS≥2` si son résultat sert de
  base à une décision d'exclusion ou de shortlist ;
- la couverture et les limites du périmètre (§4) sont rappelées à côté du
  score dans tout livrable ;
- le score générique et la recommandation par cas d'usage ne sont jamais
  interprétés comme une décision finale d'adoption.

## Voir aussi

- [workflow.md](workflow.md) — déroulé complet du pipeline et détail des
  colonnes exportées ;
- [ADR 0001](adr/0001-architecture-initiale.md) — décisions D9, D10, D12 ;
- [audit du 2026-08-21](audit-2026-08-21.md) — limites connues, dont
  l'absence de répétitions par défaut ;
- [README.md](https://github.com/Palo-IT-GitHub-Demos/model-compass/blob/main/README.md)
  et [index.md](index.md) — périmètre et positionnement vs `gen-e2-eval`.
