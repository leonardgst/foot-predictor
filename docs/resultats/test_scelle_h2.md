Rapport `scelle-h2-20261101T153604` : jeu `ds-2026-11-01-9b5f2f2c`, commit `9c326ab`, graine 20260930, 10000 rééchantillonnages.

| Pli | Matchs d'évaluation | Intersection | Écartés | Avec cote | Hyperparamètres retenus |
|---|---|---|---|---|---|
| scellé depuis 2025-26 | 2092 | 1923 | 169 | 1855 | M3_G0G2 : {'groups': ['G0', 'G1', 'G2'], 'half_life': 240}; M3_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'half_life': 240}; B1 : {'window': 3} |

| Modèle | Pli | Log-loss | RPS | Brier P(T > 2,5) | Calibration : écart moyen | Pente | Couverture observée | Couverture annoncée | Log-loss score exact | Brier 1N2 | MAE E[T] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M3_G0G2 | scellé depuis 2025-26 | 1.8741 | 0.1270 | 0.2419 | 0.0258 | 0.97 | 87.7 % | 87.4 % | 2.9033 | 0.5892 | 1.304 |
| M3_H2 | scellé depuis 2025-26 | 1.8728 | 0.1268 | 0.2415 | 0.0219 | 0.99 | 87.7 % | 87.5 % | 2.8988 | 0.5876 | 1.302 |
| B1 | scellé depuis 2025-26 | 1.8905 | 0.1290 | 0.2457 | 0.0288 | 0.93 | 88.7 % | 88.0 % | 3.0164 | 0.6471 | 1.320 |

| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |
|---|---|---|---|---|---|---|---|
| M3_G0G2 | 1923 | 1.8741 | 0.1270 | 0.2419 | 0.0258 | 0.97 | +0.069 |
| M3_H2 | 1923 | 1.8728 | 0.1268 | 0.2415 | 0.0219 | 0.99 | +0.068 |
| B1 | 1923 | 1.8905 | 0.1290 | 0.2457 | 0.0288 | 0.93 | +0.037 |

Petits totaux, calibration poolée sur le pli unique :

| Modèle | k | P(T = k) prédite | observée | Brier | Écart moyen par décile | Pente |
|---|---|---|---|---|---|---|
| M3_G0G2 | 0 | 6.5 % | 6.4 % | 0.0598 | 0.0092 | 1.04 |
| M3_G0G2 | 1 | 17.3 % | 16.8 % | 0.1393 | 0.0195 | 0.76 |
| M3_G0G2 | 2 | 23.6 % | 22.5 % | 0.1736 | 0.0260 | 1.39 |
| M3_H2 | 0 | 6.5 % | 6.4 % | 0.0599 | 0.0098 | 1.01 |
| M3_H2 | 1 | 17.4 % | 16.8 % | 0.1391 | 0.0134 | 0.83 |
| M3_H2 | 2 | 23.6 % | 22.5 % | 0.1735 | 0.0258 | 1.44 |
| B1 | 0 | 6.1 % | 6.4 % | 0.0605 | 0.0159 | 0.20 |
| B1 | 1 | 16.8 % | 16.8 % | 0.1394 | 0.0278 | 1.09 |
| B1 | 2 | 23.5 % | 22.5 % | 0.1742 | 0.0290 | 1.33 |

Événement plus/moins 2,5, sur les matchs de l'intersection qui ont une cote :

| Modèle | Pli | Matchs | Brier | Log-loss binaire | Calibration : écart moyen |
|---|---|---|---|---|---|
| M3_G0G2 | scellé depuis 2025-26 | 1855 | 0.2423 | 0.6773 | 0.0283 |
| M3_G0G2 | **poolé** | | **0.2423** | | |
| M3_H2 | scellé depuis 2025-26 | 1855 | 0.2418 | 0.6763 | 0.0204 |
| M3_H2 | **poolé** | | **0.2418** | | |
| B1 | scellé depuis 2025-26 | 1855 | 0.2459 | 0.6848 | 0.0293 |
| B1 | **poolé** | | **0.2459** | | |
| marche_avant_cloture | scellé depuis 2025-26 | 1855 | 0.2405 | 0.6736 | 0.0296 |
| marche_avant_cloture | **poolé** | | **0.2405** | | |

Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :

| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |
|---|---|---|---|---|---|---|---|
| M3_G0G2 | M3_H2 | log-loss du total | +0.00129 | [-0.00035 ; +0.00289] | 1 sur 1 | 0.1210 | 2025 : +0.0013 |
| M3_G0G2 | M3_H2 | RPS | +0.00024 | [-0.00000 ; +0.00048] | 1 sur 1 | 0.0509 | 2025 : +0.0002 |
| M3_G0G2 | M3_H2 | Brier plus/moins 2,5 | +0.00045 | [-0.00017 ; +0.00105] | 1 sur 1 | 0.1488 | 2025 : +0.0005 |
| M3_G0G2 | M3_H2 | Brier P(T = 0) | -0.00003 | [-0.00009 ; +0.00003] | 0 sur 1 | 0.3155 | 2025 : -0.0000 |
| M3_G0G2 | M3_H2 | Brier P(T = 1) | +0.00022 | [+0.00001 ; +0.00043] | 1 sur 1 | 0.0421 | 2025 : +0.0002 |
| M3_G0G2 | M3_H2 | Brier P(T = 2) | +0.00005 | [-0.00009 ; +0.00020] | 1 sur 1 | 0.4828 | 2025 : +0.0001 |
| | | règle de décision | non applicable : 1 pli, la règle de sélection en demande au moins 3 (ADR-0037, E-060) | | | | |
| B1 | M3_H2 | log-loss du total | +0.01768 | [+0.00894 ; +0.02678] | 1 sur 1 | 0.0001 | 2025 : +0.0177 |
| B1 | M3_H2 | RPS | +0.00227 | [+0.00104 ; +0.00353] | 1 sur 1 | 0.0004 | 2025 : +0.0023 |
| B1 | M3_H2 | Brier plus/moins 2,5 | +0.00402 | [+0.00084 ; +0.00715] | 1 sur 1 | 0.0120 | 2025 : +0.0040 |
| B1 | M3_H2 | Brier P(T = 0) | +0.00059 | [+0.00018 ; +0.00104] | 1 sur 1 | 0.0067 | 2025 : +0.0006 |
| B1 | M3_H2 | Brier P(T = 1) | +0.00027 | [-0.00089 ; +0.00144] | 1 sur 1 | 0.6454 | 2025 : +0.0003 |
| B1 | M3_H2 | Brier P(T = 2) | +0.00064 | [-0.00009 ; +0.00136] | 1 sur 1 | 0.0829 | 2025 : +0.0006 |
| | | règle de décision | non applicable : 1 pli, la règle de sélection en demande au moins 3 (ADR-0037, E-060) | | | | |
| M3_H2 | marche_avant_cloture | Brier plus/moins 2,5 | +0.00137 | [-0.00036 ; +0.00307] | 1 sur 1 | 0.1169 | 2025 : +0.0014 |

Écart apparié du log-loss du total par tranche de journées (A − B, positif : B meilleur ; descriptif, hors de la règle de décision) :

| A | B | Tranche | Matchs | Écart poolé | IC 95 % |
|---|---|---|---|---|---|
| M3_G0G2 | M3_H2 | 1-5 | 414 | +0.00149 | [-0.00264 ; +0.00541] |
| M3_G0G2 | M3_H2 | 6-10 | 311 | +0.00240 | [-0.00303 ; +0.00777] |
| M3_G0G2 | M3_H2 | 11-19 | 421 | +0.00100 | [-0.00191 ; +0.00396] |
| M3_G0G2 | M3_H2 | 20-99 | 777 | +0.00089 | [-0.00122 ; +0.00300] |
| B1 | M3_H2 | 1-5 | 414 | +0.01781 | [+0.00204 ; +0.03399] |
| B1 | M3_H2 | 6-10 | 311 | +0.03950 | [+0.01144 ; +0.07661] |
| B1 | M3_H2 | 11-19 | 421 | +0.01192 | [-0.00742 ; +0.03188] |
| B1 | M3_H2 | 20-99 | 777 | +0.01200 | [+0.00119 ; +0.02297] |
