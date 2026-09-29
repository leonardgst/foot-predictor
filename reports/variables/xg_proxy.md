# xg_proxy : estimation et contrôle — 2026-09-29

Produit par `python -m foot_predictor.features.xg_proxy_estimation` (ADR-0032). Chiffres seulement.

## Estimation (figée)

- `xg_proxy = 0.3033 · tirs cadrés + 0.0000 · tirs non cadrés` (moindres carrés sans constante, coefficients positifs ou nuls, tirs de football-data).
- Estimation libre (sans la contrainte), pour information : 0.3215 · cadrés -0.0126 · non cadrés. **Non retenue** : un tir ne peut pas retirer de but attendu.
- Saisons 2015-16 à 2020-21, 10 championnats des échelles, 40394 lignes (match, équipe) avec tirs et buts. Aucune saison de validation n'est lue.
- Sensibilité, sans la Serie A de 2018-19 à 2020-21 (rupture de série, ADR-0029), avec la contrainte : 0.3074 · cadrés + 0.0000 · non cadrés (38114 lignes). **Non retenu** : sensibilité seulement.

## Qualité sur 2022-23 à 2024-25, contre l'xG d'API-FOOTBALL (par équipe et par match)

| Championnat | Lignes | Corrélation | Écart moyen absolu | Biais (proxy − xG) | xG moyen |
|---|---|---|---|---|---|
| Premier League | 1906 | 0.692 | 0.515 | -0.098 | 1.514 |
| Ligue 1 | 1604 | 0.675 | 0.510 | -0.056 | 1.445 |
| Bundesliga | 1564 | 0.725 | 0.482 | -0.051 | 1.498 |
| Serie A | 1918 | 0.631 | 0.482 | -0.005 | 1.248 |
| La Liga | 1942 | 0.676 | 0.488 | -0.042 | 1.314 |
| Total | 8934 | 0.685 | 0.495 | -0.050 | 1.398 |

L'xG d'API-FOOTBALL couvre environ la moitié des matchs de 2022-23, puis de 99 à 100 % (ADR-0023).

## Effet de la rupture de série de la Serie A (2018-19 à 2020-21)

Mêmes coefficients, appliqués aux tirs de football-data puis aux tirs d'API-FOOTBALL, sur 2278 lignes communes : biais +0.265 xG par équipe et par match, écart moyen absolu 0.292.
