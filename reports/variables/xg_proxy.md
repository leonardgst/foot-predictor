# xg_proxy : estimation et contrôle — 2026-09-30

Produit par `python -m foot_predictor.features.xg_proxy_estimation` (ADR-0032 ; source des tirs : ADR-0035). Chiffres seulement, période de développement.

## Estimation (figée)

- `xg_proxy = 0.3076 · tirs cadrés + 0.0000 · tirs non cadrés` (moindres carrés sans constante, coefficients positifs ou nuls).
- **Tirs retenus** (ADR-0035) : API-FOOTBALL pour un match joué depuis 2015-16 où elle a les tirs et les tirs cadrés des deux équipes ; sinon football-data. Choix par match.
- Estimation libre (sans la contrainte), pour information : 0.3312 · cadrés -0.0156 · non cadrés. **Non retenue** : un tir ne peut pas retirer de but attendu.
- Ancienne règle (tirs de football-data seuls, ADR-0029), avec la contrainte : 0.3033 · cadrés + 0.0000 · non cadrés (40394 lignes). **Remplacée.**
- Saisons 2015-16 à 2020-21, 10 championnats des échelles, 44334 lignes (match, équipe) avec tirs et buts. Aucune saison de validation n'est lue.

## Source retenue, part des matchs de championnat

| Période | Niveau | API | football-data | aucune |
|---|---|---|---|---|
| 2015-16 à 2020-21 | D2 | 88.5% | 0.6% | 10.9% |
| 2015-16 à 2020-21 | top 5 | 99.9% | 0.0% | 0.0% |
| 2021-22 à 2024-25 | D2 | 99.9% | 0.0% | 0.1% |
| 2021-22 à 2024-25 | top 5 | 100.0% | 0.0% | 0.0% |

## Qualité sur 2022-23 à 2024-25, contre l'xG d'API-FOOTBALL (par équipe et par match)

Avec les tirs retenus (ceux de l'API sur cette période) :

| Championnat | Lignes | Corrélation | Écart moyen absolu | Biais (proxy − xG) | xG moyen |
|---|---|---|---|---|---|
| Premier League | 1906 | 0.693 | 0.516 | -0.077 | 1.514 |
| Ligue 1 | 1604 | 0.677 | 0.511 | -0.035 | 1.445 |
| Bundesliga | 1566 | 0.730 | 0.477 | -0.057 | 1.498 |
| Serie A | 1920 | 0.636 | 0.483 | +0.014 | 1.248 |
| La Liga | 1942 | 0.677 | 0.490 | -0.028 | 1.314 |
| Total | 8938 | 0.687 | 0.495 | -0.036 | 1.398 |

Avec les seuls tirs de football-data, **situation des matchs joués après le gel** (ADR-0011) :

| Championnat | Lignes | Corrélation | Écart moyen absolu | Biais (proxy − xG) | xG moyen |
|---|---|---|---|---|---|
| Premier League | 1906 | 0.692 | 0.516 | -0.078 | 1.514 |
| Ligue 1 | 1604 | 0.675 | 0.512 | -0.037 | 1.445 |
| Bundesliga | 1564 | 0.725 | 0.485 | -0.030 | 1.498 |
| Serie A | 1918 | 0.631 | 0.485 | +0.013 | 1.248 |
| La Liga | 1942 | 0.676 | 0.491 | -0.024 | 1.314 |
| Total | 8934 | 0.685 | 0.498 | -0.031 | 1.398 |

L'xG d'API-FOOTBALL couvre environ la moitié des matchs de 2022-23, puis de 99 à 100 % (ADR-0023).

## Accord des deux sources, matchs communs du top 5 (2015-16 à 2024-25)

Part de matchs aux quatre valeurs identiques, et écart d'`xg_proxy` (football-data − API, par équipe et par match) avec les coefficients figés. Après le gel, seuls les tirs de football-data existent : c'est l'écart que subiront les glissants.

| Championnat | Matchs | Identiques | Biais (fd − API) | Écart moyen absolu |
|---|---|---|---|---|
| Premier League | 3799 | 90.9% | -0.001 | 0.006 |
| Ligue 1 | 3550 | 80.9% | +0.001 | 0.011 |
| Bundesliga | 3058 | 42.1% | +0.018 | 0.050 |
| Serie A | 3798 | 56.2% | +0.081 | 0.099 |
| La Liga | 3798 | 84.4% | +0.001 | 0.011 |
| Total | 18003 | 72.0% | +0.020 | 0.035 |

## Rupture de série de la Serie A (2018-19 à 2020-21), corrigée

Mêmes coefficients, tirs de football-data (ancienne règle) contre tirs retenus (API), sur 2280 lignes : biais +0.268 xG par équipe et par match, écart moyen absolu 0.296. Avec la nouvelle règle, ces trois saisons lisent les tirs de l'API.
