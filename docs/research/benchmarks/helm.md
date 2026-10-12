# Dossier benchmark — HELM

**Famille :** Holistic Evaluation of Language Models
**Sources gelées :** papier arXiv `2211.09110v2`, dépôt `stanford-crfm/helm` release `v0.5.16`, commit `63754d0` observé le 2026-09-09
**Statut de la source :** framework de référence ; non importé comme score Model Compass

## 1. Résumé exécutif

HELM est un framework d'évaluation holistique créé par le Stanford Center for
Research on Foundation Models. Sa contribution principale n'est pas une liste
unique de questions, mais une architecture qui sépare :

- les **scénarios** ou cas d'usage ;
- les **adapters** qui rendent les modèles accessibles de manière uniforme ;
- les **métriques** qui décrivent plusieurs dimensions du comportement ;
- les **résultats et la provenance** qui permettent d'inspecter les prompts et
  les complétions.

Le papier décrit 16 scénarios centraux évalués avec 7 métriques lorsque cela est
possible, soit une couverture multi-métrique annoncée à 87,5 %, ainsi que 7
évaluations ciblées basées sur 26 scénarios ciblés. L'étude historique a évalué
30 modèles sur 42 scénarios. Le dépôt actuel est annoncé en maintenance depuis
le 1er juin 2026 : cela ne diminue pas sa valeur méthodologique, mais impose de
figer une release plutôt que de traiter `main` comme une cible mouvante.

## 2. Construct et décision supportée

HELM cherche à améliorer la transparence d'évaluation des modèles de fondation
sur les capacités et les risques, plutôt qu'à répondre à une seule question
métier. Il rend visibles les compromis entre précision, sécurité, robustesse,
biais, toxicité, calibration et efficacité.

Le construct est donc **multidimensionnel**. Il mesure à la fois la réponse à
un scénario et certains attributs transversaux du modèle. Il ne produit pas,
par lui-même, une décision d'achat spécifique à un client.

Pour Model Compass, l'enseignement le plus important est architectural : une
recommandation doit pouvoir conserver les métriques séparément avant d'appliquer
un éventuel filtre ou classement.

## 3. Taxonomie et unité d'évaluation

HELM formalise un espace de scénarios et de métriques, puis sélectionne un sous-
ensemble selon la couverture et la faisabilité. Les scénarios peuvent couvrir
la génération, la question-réponse, le raisonnement, la robustesse, la sécurité,
la langue ou des domaines spécialisés.

L'unité de base est généralement une interaction modèle sur un scénario, avec
un prompt et une complétion. Le framework peut aussi représenter des scénarios
plus spécifiques et des métriques adaptées. La taxonomie n'est pas présentée
comme une liste plate de catégories métier : elle relie un scénario à plusieurs
métriques.

## 4. Protocoles et exécution

Le framework fournit :

- des datasets et benchmarks dans un format standardisé ;
- des interfaces unifiées pour des modèles de fournisseurs différents ;
- des adapters pour les API et formats de modèles ;
- des commandes de run et de résumé ;
- une interface d'inspection des prompts, réponses et résultats.

La commande documentée est de la forme `helm-run --run-entries ...`, puis
`helm-summarize --suite ...`. Les détails comme le nombre de shots, la
 température, le contexte, les métriques disponibles et l'adapter sont donc
attachés au scénario ou à la configuration, pas supposés universels.

## 5. Métriques et agrégation

Le papier met en avant sept métriques transversales :

- accuracy ;
- calibration ;
- robustness ;
- fairness ;
- bias ;
- toxicity ;
- efficiency.

Le point méthodologique essentiel est que ces métriques ne sont pas obligées de
se réduire à une moyenne universelle. Les tableaux et leaderboards exposent les
compromis. Une même réponse peut donc être correcte mais coûteuse, robuste mais
biaisée, ou efficace mais moins performante.

HELM fournit une structure de synthèse et de comparaison ; il ne justifie pas
qu'un produit interne utilise un score unique sans discuter les unités, les
échelles et les pondérations.

## 6. Données, provenance et reproductibilité

Le framework met l'accent sur la transparence et annonce la publication des
prompts et complétions brutes pour l'étude. Le dépôt contient aussi des
métadonnées de scénarios, de métriques et de résultats.

Les points à contrôler avant toute réutilisation sont :

- la version du scénario ;
- le dataset et sa licence ;
- l'adapter et le fournisseur ;
- le prompt exact ;
- les paramètres de génération ;
- la définition de la métrique ;
- la version du code et du modèle.

La maintenance mode annoncée en 2026 implique de distinguer la release
reproductible (`v0.5.16`) des évolutions historiques de `main`.

## 7. Limites et risques de validité

- La couverture multi-métrique peut être incomplète pour certains scénarios.
- Les métriques de fairness, bias ou toxicity dépendent fortement des datasets,
  langues et définitions opérationnelles.
- Les scénarios ne sont pas tous des cas d'usage entreprise.
- Un leaderboard HELM reste dépendant des scénarios sélectionnés et des
  adapters.
- Une métrique d'efficacité n'est pas un coût total de solution.
- Le framework ne supprime pas les risques de contamination ou de
  représentativité ; il les rend surtout plus visibles.
- Une comparaison entre deux releases ne doit pas être présentée comme
  temporellement homogène sans vérifier les scénarios et métriques communs.

## 8. Transfert provisoire vers Model Compass

### À adapter

1. **Séparer scénario, métrique et recommandation.** Le catalogue Model Compass
   devrait déclarer le construct testé, les évaluateurs applicables et les
   métriques produites avant la pondération.
2. **Publier un manifeste de provenance.** Chaque run doit conserver suite,
   catalogue, rubrique, modèle, fournisseur, paramètres et artefacts.
3. **Afficher les compromis.** Les dashboards doivent montrer les scores par
   cas d'usage et par dimension avant le score de décision.
4. **Conserver une table d'évidence.** Le rapport doit permettre de remonter de
   la recommandation au prompt et à la réponse.

### À observer

- Métriques de calibration et intervalles d'incertitude.
- Scénarios spécialisés et multilingues.
- Méthodes d'efficacité reproductibles avec OpenRouter.
- Évolution de HELM après la maintenance mode.

### À rejeter pour l'instant

- Importer un score HELM global directement dans `recommendation_score`.
- Traiter les leaderboards HELM comme une vérité métier pour Palo IT.
- Copier des scénarios/datasets externes avant revue juridique et de
  contamination.

## 9. Implications concrètes pour nos prompts et rubriques

- Chaque famille de prompts doit avoir un `construct` unique et une liste de
  métriques autorisées.
- Un prompt de qualité ne doit pas mélanger exactitude, style et sécurité dans
  une note opaque.
- La configuration doit permettre plusieurs métriques par scénario sans
  obliger à produire un score global.
- Le catalogue doit enregistrer les dimensions non scorées, et pas les remplir
  avec des zéros.
- L'efficacité doit rester séparée de la qualité fonctionnelle et reposer sur
  les mesures de latence/coût déjà capturées par le dépôt.
- La version du scénario doit apparaître dans les exports et les manifestes.

## 10. Questions ouvertes

- Quelle partie des métriques de robustesse ou fairness est pertinente pour un
  modèle uniquement appelé via OpenRouter sans contexte client ?
- Quelles métriques d'efficacité sont comparables avec notre semaphore,
  retries et ledger de coût ?
- Faut-il créer une table `scenario_metrics` dédiée ou enrichir le catalogue
  JSON actuel ?
- Quelle release HELM doit rester la référence si le framework évolue après sa
  mise en maintenance ?

## Décision provisoire

**Transfert : ADAPT.** Model Compass doit reprendre la séparation
scénario/métrique/provenance et la restitution multi-dimensionnelle, mais ne doit
pas importer le score global ni la totalité du framework.
