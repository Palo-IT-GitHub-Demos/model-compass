# Guide de lecture du rapport

Ce guide s'adresse à la personne qui doit choisir un ou plusieurs modèles pour
un appel d'offres à partir du rapport HTML (`results/dashboard_<timestamp>.html`).
Il ne demande aucune connaissance du pipeline. Les pages du rapport sont en
anglais ; leurs titres sont cités tels quels ci-dessous.

## Ce que le rapport répond, et ce qu'il ne répond pas

Le rapport répond à : **« quels modèles sont techniquement pertinents pour ce
type de cas d'usage générique, et avec quelle certitude ? »**

Il ne répond pas à : « quel modèle adopter pour ce client ». Il ne connaît ni
l'appel d'offres, ni les données du client, ni ses exigences de conformité
(localisation des données, certification, SLA). Faire correspondre les cas
d'usage génériques au dossier reste votre travail.

## 1. Vérifier d'abord le bandeau

Un bandeau orange **« Not reference-grade evidence »** en haut de page signifie
que le run ne suit pas le parcours standard : données simulées, ancienne
méthodologie, moins de trois essais par prompt, sécurité sautée ou jeu de
sondes non standard, ou couverture incomplète. Les chiffres restent lisibles,
mais **ne fondez pas une recommandation sur ce run seul**. Si la sécurité a été
sautée, les modèles sont classés sans elle : n'utilisez pas ce rapport pour un
dossier où l'injection de prompt ou la divulgation de données compte.

Une note bleue, sous le bandeau, signale une limite qui ne disqualifie pas le
run : quelques réponses perdues sur une erreur technique, ou des sondes de
sécurité restées sans réponse pour un modèle (son RSI repose alors sur moins
d'essais ; la page `Security` les nomme).

La ligne grise « Compare runs only when all of these match » liste la version
de méthodologie, la suite de prompts, le catalogue, le jeu de sondes, les poids
et le profil de charge. Deux rapports ne se comparent que si toutes ces valeurs
sont identiques.

## 2. Lire la synthèse décisionnelle (`Decision summary`)

Chaque carte correspond à un cas d'usage générique (extraction structurée,
génération de code, synthèse, etc.) et indique, dans l'ordre :

| Élément | Signification | Que faire |
| --- | --- | --- |
| **Recommended** | Meilleur score de décision parmi les modèles qui franchissent le seuil qualité du cas d'usage avec des preuves complètes. Plusieurs noms = ex æquo exacts. | Point de départ du choix. |
| Badge **fragile** | Le classement ou l'éligibilité change si un poids, ou le seuil, bouge de 10 %. | Considérer le modèle suivant comme une alternative sérieuse. |
| Badge **judge-sensitive** | Sans le juge du même fournisseur que le modèle (par exemple le juge Claude pour un modèle Anthropic), le recommandé changerait ; la carte nomme l'alternative. | Traiter la recommandation comme non confirmée et comparer les deux modèles nommés. |
| Badge **weight-profile-sensitive** | Le recommandé change selon le profil de poids (`quality-first`, `balanced`, `cost-sensitive`) ; la carte nomme le leader de chaque profil. | Retenir le leader du profil qui correspond au dossier : `quality-first` pour des réponses critiques, `cost-sensitive` pour un fort volume ou un budget serré, `balanced` sinon. |
| Badge **same leader** | Le recommandé est le même sous les trois profils de poids. | La recommandation ne dépend pas de la pondération retenue. |
| Badge **disputed key** | Sur un prompt du cas d'usage, la plupart des modèles donnent la même réponse, que le corrigé rejette. | Faire relire ce prompt avant de s'appuyer sur le classement. |
| **within uncertainty** | La qualité de ces modèles ne se distingue pas statistiquement de celle du recommandé. | Départager sur un critère du dossier : coût, fournisseur, conformité. |
| **Also eligible** | Franchit le seuil mais obtient un score plus bas. | Alternative si une contrainte exclut les premiers. |
| **cannot be ranked (missing evidence)** | Qualité suffisante, mais il manque une mesure de sécurité, de coût ou de performance. | Ne pas retenir sans compléter la mesure. |
| **Below the quality threshold** | Qualité insuffisante pour ce cas d'usage, quel que soit son prix. **borderline** : l'intervalle de confiance chevauche le seuil. | Ne pas retenir ; un modèle *borderline* peut mériter un test sur données client. |
| **No model can be recommended** | Aucun modèle évalué ne convient à ce cas d'usage. | Élargir le panel de modèles ou revoir le besoin. |

## 3. Approfondir si nécessaire

| Page | À consulter quand… |
| --- | --- |
| `Use cases in detail` | vous voulez le détail des composantes (qualité, sécurité, coût, performance), l'intervalle de confiance, la plage de rang sous ±10 %, le rang sous chaque profil de poids et la colonne *Format respected* (respect du format exigé, noté à part de la qualité). Le tableau *Weight profiles* traduit chaque profil en arbitrages concrets, par exemple « 1 point de qualité vaut un écart de prix de 75 fois ». |
| `Security` | la sécurité est un critère fort du dossier. Le RSI ne mesure que la résistance à la divulgation d'un secret ; la colonne *Scored probes measured* indique sur combien d'essais il repose, et la section « Observations — not scored » liste ce qui n'est **pas** mesuré. |
| `Cost` | vous devez chiffrer un budget : le TCO est une projection mensuelle pour un profil de charge, pas le coût du test. |
| `Performance` | la latence compte pour l'usage visé (p95 = temps de réponse des cas lents). |
| `Prompts & responses` | vous voulez lire les questions posées, les réponses et la justification de chaque juge. |
| `Quality × cost` | vous voulez une vue d'ensemble. **Ne pas choisir depuis cette page** : elle ignore les seuils par cas d'usage et la sécurité. |
| `Glossary` | un terme ou un acronyme n'est pas clair. |

## 4. Avant de décider

- Le bandeau d'avertissement est absent, ou ses raisons sont acceptables pour
  l'usage visé.
- Chaque cas d'usage du dossier a été rapproché d'une carte du rapport.
- Une recommandation **fragile** ou entourée de modèles *within uncertainty* a
  été départagée sur un critère explicite du dossier.
- Les exigences hors périmètre (conformité, hébergement, contrat) ont été
  vérifiées à part.
- Si un jeu de données propre au client existe, le choix final est confirmé avec
  `gen-e2-eval`.
