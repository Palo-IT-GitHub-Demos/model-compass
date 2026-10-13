# Dossier benchmark — MT-Bench

**Famille :** Multi-turn benchmark for chat assistants
**Sources gelées :** papier arXiv `2306.05685v4`, FastChat question file commit `b494d0c`, LLM-judge directory commit `925fb82`, `gen_judgment.py` commit `312d85c`
**Statut de la source :** référence pour le dialogue multi-tour et l'évaluation par rubric/judge ; non importée comme score Model Compass

## 1. Résumé exécutif

MT-Bench évalue des assistants conversationnels sur des questions ouvertes et
multi-tour. La question set consultée contient 80 questions organisées en huit
catégories :

- writing ;
- roleplay ;
- reasoning ;
- math ;
- coding ;
- extraction ;
- stem ;
- humanities.

Chaque question contient deux tours. Le second tour demande souvent une
révision, une extension, une critique ou une contrainte supplémentaire. Le
benchmark utilise un LLM fort comme juge et produit un score sur 10 par tour,
puis une moyenne sur les tours. FastChat documente aussi deux modes de
comparaison pairwise en plus de la notation single-answer recommandée.

Le papier étudie l'accord entre juges humains et GPT-4, ainsi que plusieurs
biais du LLM-as-a-Judge : position, verbosité, auto-préférence et capacité du
juge. La documentation FastChat indique 3,3K annotations humaines sur 80
questions et 6 modèles, et un accord humain/juge supérieur à 80 % dans cette
expérience.

## 2. Construct et décision supportée

Le construct est la qualité perçue d'un assistant dans une interaction ouverte,
avec prise en compte du contexte du premier tour au second. Il mesure mieux la
cohérence conversationnelle, la transformation d'une réponse et le respect de
contraintes successives qu'un QCM ou une vérification exacte.

La décision supportée est une comparaison de réponses conversationnelles, pas
une preuve de factualité absolue ou de réussite métier. Les questions de coding
ou de math peuvent révéler une compétence, mais la notation par juge reste une
approximation ouverte.

## 3. Taxonomie et unité

La taxonomie en huit catégories couvre un spectre proche de plusieurs cas
Model Compass : communication, raisonnement, mathématiques, code, extraction et
sciences humaines. Chaque unité est une conversation de deux tours, avec les
réponses conservées et évaluées.

L'utilisation de catégories permet de publier des profils plutôt qu'un score
unique. La structure `turns` est particulièrement importante : une réponse peut
sembler correcte au premier tour mais échouer lorsque l'utilisateur demande une
modification précise au second.

## 4. Protocole de génération

FastChat génère les réponses modèle puis les stocke dans des fichiers JSONL
avant de lancer le jugement. Le protocole doit préciser :

- le template de conversation ;
- les tours et leur ordre ;
- le modèle et sa version ;
- la température et les paramètres de génération ;
- les retries et les erreurs API ;
- la présence d'une réponse de référence pour les catégories de math ;
- le judge utilisé et sa version de prompt.

Le benchmark peut être exécuté en local ou via des endpoints compatibles
OpenAI. Cette séparation génération/jugement rend les réponses réutilisables,
mais augmente le besoin de provenance.

## 5. Notation

Le mode single-answer recommandé demande au juge d'attribuer une note de 1 à 10
à chaque tour. Le score d'un modèle est la moyenne des scores disponibles sur
les tours/questions. Le système possède aussi :

- un mode pairwise contre un modèle baseline ;
- un mode pairwise entre toutes les paires ;
- des juges spécifiques pour certaines catégories math avec référence.

Les modes pairwise produisent des win rates, tandis que le mode single-answer
produit une note continue. Ils ne doivent pas être mélangés sans méthode de
calibration.

La note ouverte exige une rubrique claire. Une moyenne de 7,5/10 n'a de sens
que si le rubric du juge, sa version, le nombre de tours valides et les erreurs
sont conservés.

## 6. Accord humain et biais du juge

Le papier rapporte un accord élevé entre GPT-4 et les préférences humaines dans
les expériences étudiées, mais il documente également des limites :

- **position bias** : l'ordre des réponses peut influencer le résultat ;
- **verbosity bias** : une réponse plus longue peut être jugée meilleure ;
- **self-enhancement bias** : un juge peut préférer ses propres sorties ou son
  style de fournisseur ;
- limites de raisonnement et de calibration du juge.

Le protocole d'alias Model Compass réduit la fuite d'identité, mais ne prouve pas
que les juges sont neutres. Le projet doit continuer à publier `judge_disagreement`
et à conserver les verdicts individuels.

## 7. Données, reproductibilité et coût

La question set est publique et les réponses/jugements pré-générés peuvent être
consultés. La réutilisation directe des questions nécessite toutefois une
vérification de licence et crée un risque de contamination si elles sont
réintroduites dans un nouveau benchmark public.

Le coût de MT-Bench vient de deux côtés :

1. génération de deux tours pour chaque modèle ;
2. appel au modèle juge pour chaque réponse/tour ou paire.

Dans Model Compass, les trois juges Copilot n'ajoutent pas de coût OpenRouter,
mais cela ne reproduit pas exactement GPT-4 judge : le modèle, la rubrique et la
configuration sont différents et doivent être traités comme une nouvelle
méthode.

## 8. Limites et risques de validité

- Deux tours ne représentent pas tous les workflows multi-tour.
- Les catégories et questions sont centrées sur un assistant généraliste, pas
  sur des données d'entreprise.
- Les notes de juge sont subjectives et sensibles au prompt.
- L'accord humain observé ne garantit pas la validité sur toutes les langues,
  domaines ou populations.
- La moyenne par tour peut donner trop de poids à des questions faciles ou
  homogènes.
- Le juge peut noter le style plutôt que l'exactitude quand la rubrique est
  ambiguë.
- Les réponses publiques peuvent contaminer les futurs modèles.

## 9. Transfert provisoire vers Model Compass

### À adapter

1. Une petite suite multi-tour pour les cas où le second tour est un vrai
   construct : correction, clarification, transformation ou contrainte.
2. Un rubric explicite par catégorie avec critères atomiques.
3. Un stockage séparé des réponses par tour et des verdicts par juge.
4. Une calibration humaine sur un échantillon avant d'utiliser les notes pour
   un seuil.
5. Une comparaison séparée entre single-answer et pairwise, sans les fusionner
   automatiquement.

### À observer

- Accord humain/judge lorsque nos trois juges sont utilisés.
- Influence de la longueur, du style et de l'ordre des réponses.
- Catégories les plus proches des usages de consulting : writing, extraction,
  coding, reasoning et STEM.
- Effet d'une réponse de référence sur le jugement mathématique ou factuel.

### À rejeter pour l'instant

- Présenter le score MT-Bench comme exactitude objective.
- Utiliser un unique juge fournisseur-affilié pour une recommandation.
- Copier le score publié dans le score qualité Model Compass.
- Déduire qu'un bon dialogue général garantit une réponse RAG ou métier.

## 10. Implications pour nos prompts et rubriques

- Ajouter `turn_index`, `conversation_id` et `requires_previous_context` au
  blueprint.
- Écrire les deux tours comme une trajectoire intentionnelle, pas comme deux
  questions indépendantes.
- Définir des critères vérifiables : exactitude, respect de la contrainte,
  cohérence avec le premier tour, absence d'information inventée.
- Séparer les critères de contenu, sécurité, format et style.
- Évaluer la longueur comme une contrainte explicite uniquement lorsqu'elle est
  exigée par le cas d'usage.
- Ajouter des exemples de réponses 1/5, 3/5 et 5/5 pour calibrer les juges.
- Tester le même prompt avec des alias et ordres différents avant de considérer
  la mitigation comme efficace.

## 11. Questions ouvertes

- Quel nombre de tours est justifié pour les cas d'usage Model Compass sans
  transformer le pipeline en agent benchmark ?
- Faut-il une note absolue, une préférence pairwise, ou conserver les deux
  sorties séparément ?
- Comment obtenir un échantillon humain raisonnable à Singapour pour calibrer
  les critères de communication ?
- Quand une tâche ouverte doit-elle être convertie en vérification déterministe ?
- Quelle stratégie de langue utiliser pour les conversations en anglais et en
  français ?

## Décision provisoire

**Transfert : ADAPT.** Nous reprenons les trajectoires multi-tour, les catégories,
les rubriques explicites et les preuves de désaccord. Nous conservons une
séparation stricte entre jugement ouvert et correction objective, et nous ne
reprenons ni le score publié ni le juge GPT-4 comme vérité de référence.
