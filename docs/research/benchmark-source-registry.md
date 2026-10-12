# Registre des sources de benchmarks

**Phase :** 1 — étude des cinq benchmarks
**Date d'accès :** 2026-09-09
**Statut :** sources primaires collectées ; décisions de transfert encore provisoires

Ce registre fixe les sources utilisées pour les cinq dossiers. Une source est
qualifiée avant d'être utilisée :

- **normative** : elle définit le benchmark, son protocole ou son schéma de données ;
- **descriptive** : elle explique le benchmark ou ses résultats sans être le contrat d'exécution ;
- **leaderbord** : elle montre des résultats publiés, mais ne suffit pas à définir la méthode.

Les versions ou commits sont gelés dans les dossiers. Aucun score externe n'est
copié dans les résultats Model Compass pendant cette phase.

## Sources HELM

| ID | Source | Révision utilisée | Nature | Licence / réutilisation |
|---|---|---|---|---|
| `helm-paper` | [Holistic Evaluation of Language Models](https://arxiv.org/abs/2211.09110) | arXiv v2, 2023 ; publication TMLR 2023 | normative/descriptive | Article académique ; citer, ne pas recopier les données sans vérifier les droits |
| `helm-repo` | [stanford-crfm/helm](https://github.com/stanford-crfm/helm) | release `v0.5.16` ; commit `63754d0` observé sur `main` | normative | Dépôt Apache-2.0 |
| `helm-docs` | [HELM documentation](https://crfm-helm.readthedocs.io/) et [maintenance policy](https://crfm-helm.readthedocs.io/en/latest/maintenance_mode/) | documentation consultée le 2026-09-09 | normative opérationnelle | Documentation du projet ; HELM est annoncé en maintenance depuis le 2026-06-01 |

## Sources MMLU et MMLU-Pro

| ID | Source | Révision utilisée | Nature | Licence / réutilisation |
|---|---|---|---|---|
| `mmlu-paper` | [Measuring Massive Multitask Language Understanding](https://arxiv.org/abs/2009.03300) | arXiv v3, ICLR 2021 | normative/descriptive | Article académique ; vérifier les droits des données avant toute adaptation |
| `mmlu-repo` | [hendrycks/test](https://github.com/hendrycks/test) | commit `4450500` observé sur `master` | normative pour le code fourni | Dépôt MIT ; la licence des jeux de données doit être vérifiée séparément |
| `mmlu-pro-paper` | [MMLU-Pro](https://arxiv.org/abs/2406.01574) | arXiv v6, NeurIPS 2024 | normative/descriptive | Article académique ; ne pas recopier les questions dans Model Compass sans vérification |
| `mmlu-pro-repo` | [TIGER-AI-Lab/MMLU-Pro](https://github.com/TIGER-AI-Lab/MMLU-Pro) | commit `f418b11` observé sur `main` | normative pour le code et le protocole | Dépôt Apache-2.0 ; vérifier la licence du dataset Hugging Face avant réutilisation |
| `mmlu-pro-data` | [Dataset MMLU-Pro](https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro) | dataset référencé par le dépôt, consulté le 2026-09-09 | normative pour les données | Licence et conditions de redistribution à confirmer avant ingestion |

## Sources BIG-bench

| ID | Source | Révision utilisée | Nature | Licence / réutilisation |
|---|---|---|---|---|
| `bigbench-paper` | [Beyond the Imitation Game](https://arxiv.org/abs/2206.04615) | arXiv v3, TMLR 2023 | normative/descriptive | Article académique ; citer la source originale |
| `bigbench-repo` | [google/BIG-bench](https://github.com/google/BIG-bench) | dépôt archivé le 2026-04-17 ; README commit `092b196` observé | normative pour le framework | Dépôt Apache-2.0 |
| `bigbench-task-catalog` | [task catalog](https://github.com/google/BIG-bench/blob/main/bigbench/benchmark_tasks/README.md) et [keyword map](https://github.com/google/BIG-bench/blob/main/bigbench/benchmark_tasks/keywords_to_tasks.md) | keyword-map commit `95308e1` observé ; 214 tâches listées dans le README | normative pour les métadonnées | Les tâches individuelles peuvent avoir des conditions propres ; vérifier avant adaptation |
| `bigbench-docs` | [task schema and metrics](https://github.com/google/BIG-bench/blob/main/docs/doc.md) | commit `71ebc2e` observé | normative | Le schéma indique les canary strings ; ne pas importer les données publiques dans un nouveau corpus |

## Sources MT-Bench

| ID | Source | Révision utilisée | Nature | Licence / réutilisation |
|---|---|---|---|---|
| `mtbench-paper` | [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685) | arXiv v4, NeurIPS 2023 | normative/descriptive | Article académique ; citer les résultats de biais et d'accord humain |
| `mtbench-questions` | [FastChat MT-Bench questions](https://github.com/lm-sys/FastChat/blob/main/fastchat/llm_judge/data/mt_bench/question.jsonl) | commit `b494d0c` observé ; fichier de 80 questions, IDs 81–160 dans la révision consultée | normative pour la question set | Dépôt FastChat ; vérifier les conditions de réutilisation des questions |
| `mtbench-judge` | [FastChat LLM judge](https://github.com/lm-sys/FastChat/tree/main/fastchat/llm_judge) | commit `925fb82` observé ; `gen_judgment.py` commit `312d85c` | normative pour l'implémentation | Dépôt FastChat Apache-2.0 ; la réutilisation du corpus reste à vérifier |
| `mtbench-human` | [MT-Bench human judgments](https://huggingface.co/datasets/lmsys/mt_bench_human_judgments) | dataset référencé par la documentation FastChat, consulté le 2026-09-09 | descriptive/validation | À utiliser comme référence d'accord, pas comme nouvelle vérité terrain sans audit |

## Sources SWE-bench

| ID | Source | Révision utilisée | Nature | Licence / réutilisation |
|---|---|---|---|---|
| `swebench-paper` | [SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://arxiv.org/abs/2310.06770) | arXiv v3, ICLR 2024 | normative/descriptive | Article académique ; citer le protocole original |
| `swebench-repo` | [SWE-bench/SWE-bench](https://github.com/SWE-bench/SWE-bench) | commit `02e7a74` observé sur `main` | normative pour le harness | Dépôt MIT ; les dépôts/tâches sources ont leurs propres licences |
| `swebench-original` | [SWE-bench original](https://www.swebench.com/original.html) | page consultée le 2026-09-09 | normative descriptive | Confirme 2 294 instances, 12 dépôts Python et le signal fail-to-pass |
| `swebench-verified` | [SWE-bench Verified](https://www.swebench.com/verified.html) | page consultée le 2026-09-09 | normative descriptive | Confirme 500 instances filtrées par des humains et le protocole bash-only |

## Règles de citation et d'utilisation

1. Citer d'abord le papier et le dépôt officiel ; ne pas s'appuyer uniquement
   sur un leaderboard ou un article de blog.
2. Enregistrer la révision exacte dans chaque résultat de recherche.
3. Ne pas copier de questions, réponses ou patches publics dans
   `data/prompts/` sans vérifier licence, contamination et droit de
   redistribution.
4. Utiliser les benchmarks externes pour comprendre des méthodes et des
   construits ; ne pas appeler une adaptation interne « MMLU », « MT-Bench » ou
   « SWE-bench ».
5. Toute réutilisation de données externes doit avoir un statut juridique
   explicite : `approved`, `reference_only` ou `blocked_pending_review`.
6. Les résultats des cinq benchmarks restent une table d'évidence externe. Ils
   n'entrent pas dans le score pondéré Model Compass tant que la Phase 2 n'a pas
   approuvé une comparabilité précise.
