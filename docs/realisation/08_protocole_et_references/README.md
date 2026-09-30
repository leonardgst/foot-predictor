# Étape 08 : protocole d'évaluation et références (jalon J5)

Mode d'emploi du protocole, de l'exécuteur d'expériences, des métriques et des références B0, B1 et marché. Décisions : ADR-0035 (source des tirs), ADR-0036 (cotes, référence de marché), **ADR-0037 (protocole et règle de décision, figés au tag `protocole-v1`)**. Résultats : [`docs/resultats/references.md`](../../resultats/references.md).

## En bref

- **Plis** : 4 plis à fenêtre croissante, test sur 2021-22, 2022-23, 2023-24, 2024-25 ; apprentissage depuis 2015-16 ; hyperparamètres par validation interne sur la dernière saison d'apprentissage.
- **Évaluation** : matchs de championnat du top 5, sur l'intersection des matchs prédits par tous les modèles comparés.
- **Métrique principale** : log-loss du total ; écarts appariés avec intervalle à 95 % par bootstrap par blocs de journées (10 000 tirages, graine 20260930).
- **Règle de décision** (ADR-0037) : B remplace A si le gain poolé exclut 0, s'il est positif dans 3 plis sur 4 et si la calibration poolée ne se dégrade pas.
- **Scellé** : aucun match à partir du 1er juillet 2025, ni dans les plis ni dans les cotes lues ; `--sealed-test` est réservé au test scellé de la phase B.

## Commandes

```bash
uv run python -m foot_predictor.modeling evaluate experiments/references.yaml   # une expérience
uv run python -m foot_predictor.modeling index                                  # régénère reports/experiments/INDEX.md
PYTHONIOENCODING=utf-8 uv run python -m foot_predictor.modeling summary reports/experiments/<id>.json   # tableaux Markdown
```

Durée mesurée : environ 8 s pour les références (4 plis, 10 000 rééchantillonnages). Mesurer toute nouvelle expérience avec `n_resamples: 200` avant de la lancer en entier ; l'essai de mesure est conservé comme les autres.

Une expérience écrit :

| Fichier | Contenu | Versionné |
|---|---|---|
| `reports/experiments/<nom>-<date>.json` | spécification, jeu de données, commit, plis, hyperparamètres retenus, métriques par pli et poolées, comparaisons, décision | oui |
| `reports/experiments/INDEX.md` | tous les essais, réussis ou non, et leur nombre | oui |
| `data/experiments/<id>/predictions.parquet` | λ et loi du total par match et par modèle | non (`data/`) |

## Écrire une expérience

```yaml
name: references                 # préfixe de l'identifiant
dataset: ds-2026-09-30-ba2b91f7  # vide : la version la plus récente
folds: [2021, 2022, 2023, 2024]
population: top5                 # ou top5_d2 (apprentissage seulement)
seed: 20260930
n_resamples: 10000
models:
  - {id: B0, model: b0}
  - {id: B1, model: b1, grid: {window: [1, 2, 3, 6]}}   # grille : validation interne
  - {id: marche, model: market, params: {version: avant_cloture}}
comparisons:
  - [B0, B1]                     # écart A − B : positif si B est meilleur
```

## Modules

| Module | Rôle |
|---|---|
| `modeling/distributions.py` | lois de Poisson et binomiale négative, convolution, loi jointe, repli sur « 10 et plus » |
| `modeling/metrics.py` | log-loss, RPS, Brier, calibration, PIT, couverture, score exact, 1N2 (fonctions pures) |
| `modeling/protocol.py` | plis, validation interne, lignes utilisables, intersection, garde-fous anti-fuite |
| `modeling/bootstrap.py` | blocs, bootstrap stratifié par pli, Diebold-Mariano |
| `modeling/experiment.py` | lecture du YAML, exécution, rapport JSON, règle de décision, index |
| `modeling/summary.py` | tableaux Markdown d'un rapport (pages de `docs/resultats/`, jamais recopiées à la main) |
| `modeling/models/` | interface commune (`fit`, `predict`), B0 et B1 (`references.py`), marché (`market.py`) ; M1 à M6 au lot 2 |
| `modeling/legacy/` | anciens modules (modèles A et B de 2025), remplacés, retrait en partie 5 |

## Contrôles anti-fuite (tests)

- Aucun pli ne contient une ligne de sa saison de test dans l'apprentissage, ni un match scellé (`protocol._guard`).
- La validation interne ne lit jamais la saison de test.
- Les cibles sont retirées des lignes passées à `predict` ; changer le résultat d'un match de test ne change pas sa prédiction.
- Les lignes à valeur manquante sont exclues et comptées, jamais remplies.

## Références (4.5)

| Comparaison | Métrique | Écart A − B | IC 95 % |
|---|---|---|---|
| B0 − B1 | log-loss du total | +0,0046 | [+0,0010 ; +0,0080] |
| B1 − marché avant clôture | Brier P(T > 2,5) | +0,0091 | [+0,0073 ; +0,0110] |

Détails et lecture : [`docs/resultats/references.md`](../../resultats/references.md). La pente de calibration poolée de B1 (0,69) fait échouer le critère (iii) : verdict informatif (B1 n'est pas candidat), signe que la pente est fragile pour des prévisions peu dispersées.

## Limites connues

- Le marché ne donne que P(T > 2,5) : il n'est comparé que sur cet événement.
- Pas de cote de clôture avant 2019-20 ; « moyenne de marché » de nature différente avant et après 2019-20 (ADR-0036).
