# Horizon H2 : quelle structure pour le modèle ? (jalon J9, sous-étape 6.8)

*2026-11-01. Variables, grilles et chemin de décision écrits avant toute mesure : ADR-0049 (commit `4ae284f`). Protocole inchangé (ADR-0037, tag `protocole-v1`) : 4 plis 2021-22 à 2024-25, top 5, 10 000 rééchantillonnages, graine 20260930. Jeu `ds-2026-11-01-e0defb32`. Rapport : `reports/experiments/structures-h2-20261101T134102.json`, sur arbre propre (`dirty: false`). Essais à cette date : **16**, 0 échec (dont deux de la sous-étape : une mesure de durée de 200 rééchantillonnages et le lancement de référence ; leurs prédictions sont identiques).*

## Réponse en bref

Les trois modèles lisent les mêmes variables (G0 + G1 + G2 + G5, le modèle H2 retenu en 6.7) : seule la structure change. La règle de l'ADR-0037, appliquée mécaniquement sur le chemin écrit d'avance, donne :

| Étape | Comparaison | Gain de log-loss du total [IC 95 %] | Plis gagnés | (i) | (ii) | (iii) | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | M3 → M6 (ridge) | +0,00014 [−0,00044 ; +0,00072] | 3 sur 4 | non | oui | oui | **M6 ne remplace pas M3** |
| 2 | M3 → M7 (boosting) | −0,00235 [−0,00444 ; −0,00025] | 0 sur 4 | non | non | oui | **M7 ne remplace pas M3** |

**La structure du modèle H2 reste M3** : le modèle H2 retenu est inchangé, M3 sur G0 + G1 + G2 + G5. Le résultat est nul pour la régularisation et négatif pour le boosting. Il avait été annoncé d'avance (ADR-0049, « Attendu »).

**À lire avec ce résultat** (tout est dans les tableaux générés plus bas) :

- **Le ridge égale M3 sans le battre** : +0,00014 par match, intervalle centré sur 0, 3 plis sur 4. Sa calibration poolée est un peu meilleure (écart moyen par décile 0,86 point contre 1,42, pente 1,02 contre 0,97), mais ce n'est pas un critère de remplacement, seulement de non-dégradation (iii). La règle garde le plus simple.
- **Le boosting est significativement moins bon** : −0,00235 [−0,00444 ; −0,00025], dans les 4 plis (−0,0021, −0,0038, −0,0033, −0,0002). Il perd surtout au début de saison (journées 1 à 5 : −0,0072 [−0,0128 ; −0,0017]) et en fin de saison (journée 20 et au-delà : −0,0040 [−0,0071 ; −0,0009]). Aucune tranche ne le favorise de façon significative. Contre M6, la calibration (iii) se dégrade aussi (écart moyen 1,37 point contre 0,86). C'est ce qu'on attend d'une structure flexible sur un signal si petit : elle ajuste du bruit. Le diagnostic de non-linéarité de la partie 4 (p = 0,36) n'avait pas trouvé de courbure à capter.
- **L'apport de G5 ne dépend pas de la structure, mais ne devient pas significatif** : à fenêtre égale (dès 2016-17), G5 vaut +0,00062 [−0,00004 ; +0,00126] sous M6 (4 plis sur 4) et +0,00145 [−0,00007 ; +0,00299] sous M7 (4 plis sur 4), contre +0,00061 [−0,00010 ; +0,00130] sous M3 en 6.7. Le signe est le même partout, aucun intervalle n'exclut 0. Une régularisation ou un boosting ne changent donc pas le jugement sur G5 (qui recoupe l'Elo à 0,83), c'est la limite que 6.7 laissait ouverte. Ces deux comparaisons sont des diagnostics : elles ne décident rien.

## Hyperparamètres et bord de grille

Choisis par la validation interne du pli ; la saison de test n'est jamais lue pour choisir. Selon l'ADR-0049, un hyperparamètre au bord de sa grille dans trois plis ou plus est **publié sans que la grille soit étendue** :

| Hyperparamètre | Valeurs retenues (2021-22, 2022-23, 2023-24, 2024-25) | Bord |
|---|---|---|
| Demi-vie de G2, M3 | 240, 120, 240, 240 jours | 240 (haut de la grille) dans 3 plis |
| Demi-vie de G2, M6 | 240, 120, 240, 240 jours | idem |
| Demi-vie de G2, M7 | 240, 240, 240, 120 jours | idem |
| α de M6 | 0,1 ; 0,1 ; 0,0001 ; 0,1 | **0,1 (haut de la grille) dans 3 plis** |
| Profondeur de M7 | 2, 2, 4, 4 | un bord de chaque côté, 2 plis chacun |
| Itérations de M7 | 100, 200, 200, 100 | 100 (bas de la grille) dans 2 plis |

- **La demi-vie de 240 jours au bord** est un constat ancien : la grille (60, 120, 240) est figée par l'ADR-0037 et l'ADR-0039 l'avait déjà publié pour H1.
- **L'α de M6 est au bord haut dans 3 plis** : le critère interne préfère le rétrécissement le plus fort de la grille, et un α plus grand aurait peut-être fait un peu mieux. La grille n'est pas étendue (elle serait choisie en ayant vu les plis de test). Elle ne change pas la conclusion : même au bord, M6 ne bat pas M3, et un α de 0,1 sur 25 000 lignes est déjà un rétrécissement marqué.
- Les hyperparamètres de M7 ne sont au bord dans trois plis pour aucun réglage : la grille n'était pas trop étroite pour lui.

## Ce qui a été écarté ou compté

| Quantité | Valeur |
|---|---|
| Matchs d'évaluation | 7 156 (1 826, 1 826, 1 752, 1 752) |
| Matchs écartés par l'intersection | 11, 8, 2 et 0 par pli, soit 21 (0,29 %), tous venant de valeurs G5 manquantes à la veille du match (moins qu'en 6.7, où G4 en écartait aussi) |
| Lignes de rodage écartées (G5, 2015-16) | 3 652 par pli, pour les cinq modèles |
| Lignes d'apprentissage à valeur manquante | 646, 668, 684 et 688 (modèles avec G5) ; 10 par pli (modèles sans G5) |

## Limites

- Un seul jeu de plis, quatre saisons : les intervalles sont larges devant des gains de cet ordre. L'absence de gain de M6 se lit « pas de différence détectable », pas « pas de différence ».
- Une seule grille de M7, dite d'avance : d'autres réglages (arbres plus profonds avec un pas plus petit, échantillonnage des lignes, contraintes de monotonie) n'ont pas été essayés, et ne le seront pas sur ces plis. Le boosting n'est donc pas « mauvais » en général, il est moins bon que M3 **ici**, avec cette grille.
- Cinq comparaisons dont trois de décision (deux sur le chemin), seize essais au total : le protocole ne corrige pas les comparaisons multiples, il publie le nombre.
- Les variables H2 ne sont pas disponibles en live : ce modèle ne servira qu'en rejeu (ADR-0010, ADR-0011).

## Tableaux générés

Générés par `uv run python -m foot_predictor.modeling summary reports/experiments/structures-h2-20261101T134102.json` : ils ne sont pas recopiés à la main. Les verdicts « remplace » des lignes de décision sont ceux de la règle ; seuls ceux de l'étape 1 et de l'étape 2 qui suivent le chemin décident (ADR-0049). Les deux dernières comparaisons (G5 sous M6 et sous M7) sont des diagnostics.

### Expérience de décision : `structures_h2.yaml`

Rapport `structures-h2-20261101T134102` : jeu `ds-2026-11-01-e0defb32`, commit `99102af`, graine 20260930, 10000 rééchantillonnages.

| Pli | Matchs d'évaluation | Intersection | Écartés | Avec cote | Hyperparamètres retenus |
|---|---|---|---|---|---|
| 2021-22 | 1826 | 1815 | 11 | n. d. | M3_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'half_life': 240}; M6_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'penalty': 'l2', 'alpha': 0.1, 'half_life': 240}; M7_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'learning_rate': 0.05, 'min_samples_leaf': 200, 'l2_regularization': 1.0, 'half_life': 240, 'max_depth': 2, 'max_iter': 100}; M6_sans_G5 : {'groups': ['G0', 'G1', 'G2'], 'penalty': 'l2', 'train_from': 2016, 'alpha': 0.1, 'half_life': 240}; M7_sans_G5 : {'groups': ['G0', 'G1', 'G2'], 'learning_rate': 0.05, 'min_samples_leaf': 200, 'l2_regularization': 1.0, 'train_from': 2016, 'half_life': 240, 'max_depth': 2, 'max_iter': 100} |
| 2022-23 | 1826 | 1818 | 8 | n. d. | M3_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'half_life': 120}; M6_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'penalty': 'l2', 'alpha': 0.1, 'half_life': 120}; M7_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'learning_rate': 0.05, 'min_samples_leaf': 200, 'l2_regularization': 1.0, 'half_life': 240, 'max_depth': 2, 'max_iter': 200}; M6_sans_G5 : {'groups': ['G0', 'G1', 'G2'], 'penalty': 'l2', 'train_from': 2016, 'alpha': 0.1, 'half_life': 120}; M7_sans_G5 : {'groups': ['G0', 'G1', 'G2'], 'learning_rate': 0.05, 'min_samples_leaf': 200, 'l2_regularization': 1.0, 'train_from': 2016, 'half_life': 120, 'max_depth': 2, 'max_iter': 100} |
| 2023-24 | 1752 | 1750 | 2 | n. d. | M3_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'half_life': 240}; M6_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'penalty': 'l2', 'alpha': 0.0001, 'half_life': 240}; M7_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'learning_rate': 0.05, 'min_samples_leaf': 200, 'l2_regularization': 1.0, 'half_life': 240, 'max_depth': 4, 'max_iter': 200}; M6_sans_G5 : {'groups': ['G0', 'G1', 'G2'], 'penalty': 'l2', 'train_from': 2016, 'alpha': 0.0001, 'half_life': 240}; M7_sans_G5 : {'groups': ['G0', 'G1', 'G2'], 'learning_rate': 0.05, 'min_samples_leaf': 200, 'l2_regularization': 1.0, 'train_from': 2016, 'half_life': 240, 'max_depth': 3, 'max_iter': 400} |
| 2024-25 | 1752 | 1752 | 0 | n. d. | M3_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'half_life': 240}; M6_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'penalty': 'l2', 'alpha': 0.1, 'half_life': 240}; M7_H2 : {'groups': ['G0', 'G1', 'G2', 'G5'], 'learning_rate': 0.05, 'min_samples_leaf': 200, 'l2_regularization': 1.0, 'half_life': 120, 'max_depth': 4, 'max_iter': 100}; M6_sans_G5 : {'groups': ['G0', 'G1', 'G2'], 'penalty': 'l2', 'train_from': 2016, 'alpha': 0.1, 'half_life': 240}; M7_sans_G5 : {'groups': ['G0', 'G1', 'G2'], 'learning_rate': 0.05, 'min_samples_leaf': 200, 'l2_regularization': 1.0, 'train_from': 2016, 'half_life': 240, 'max_depth': 4, 'max_iter': 100} |

| Modèle | Pli | Log-loss | RPS | Brier P(T > 2,5) | Calibration : écart moyen | Pente | Couverture observée | Couverture annoncée | Log-loss score exact | Brier 1N2 | MAE E[T] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M3_H2 | 2021-22 | 1.8963 | 0.1316 | 0.2441 | 0.0371 | 0.86 | 87.1 % | 87.7 % | 2.9217 | 0.5884 | 1.345 |
| M3_H2 | 2022-23 | 1.8654 | 0.1264 | 0.2423 | 0.0180 | 1.03 | 87.8 % | 87.3 % | 2.8968 | 0.5840 | 1.293 |
| M3_H2 | 2023-24 | 1.8917 | 0.1299 | 0.2376 | 0.0355 | 1.23 | 87.2 % | 87.6 % | 2.9274 | 0.5816 | 1.322 |
| M3_H2 | 2024-25 | 1.8659 | 0.1266 | 0.2416 | 0.0208 | 0.86 | 89.4 % | 88.2 % | 2.9095 | 0.5851 | 1.302 |
| M6_H2 | 2021-22 | 1.8956 | 0.1315 | 0.2438 | 0.0275 | 0.93 | 86.8 % | 87.5 % | 2.9230 | 0.5895 | 1.345 |
| M6_H2 | 2022-23 | 1.8665 | 0.1266 | 0.2428 | 0.0311 | 1.07 | 87.8 % | 87.3 % | 2.9005 | 0.5861 | 1.295 |
| M6_H2 | 2023-24 | 1.8917 | 0.1299 | 0.2376 | 0.0355 | 1.23 | 87.2 % | 87.6 % | 2.9274 | 0.5816 | 1.322 |
| M6_H2 | 2024-25 | 1.8649 | 0.1264 | 0.2414 | 0.0307 | 0.94 | 89.0 % | 87.9 % | 2.9066 | 0.5854 | 1.300 |
| M7_H2 | 2021-22 | 1.8984 | 0.1319 | 0.2447 | 0.0236 | 0.92 | 87.2 % | 87.3 % | 2.9315 | 0.5921 | 1.351 |
| M7_H2 | 2022-23 | 1.8692 | 0.1269 | 0.2431 | 0.0278 | 1.03 | 87.8 % | 87.4 % | 2.9065 | 0.5881 | 1.297 |
| M7_H2 | 2023-24 | 1.8950 | 0.1303 | 0.2386 | 0.0419 | 1.10 | 87.1 % | 87.8 % | 2.9334 | 0.5835 | 1.326 |
| M7_H2 | 2024-25 | 1.8661 | 0.1266 | 0.2415 | 0.0198 | 0.95 | 89.2 % | 88.0 % | 2.9089 | 0.5846 | 1.304 |
| M6_sans_G5 | 2021-22 | 1.8959 | 0.1315 | 0.2436 | 0.0348 | 0.94 | 86.9 % | 87.5 % | 2.9275 | 0.5923 | 1.346 |
| M6_sans_G5 | 2022-23 | 1.8670 | 0.1267 | 0.2430 | 0.0196 | 1.06 | 87.8 % | 87.4 % | 2.9040 | 0.5883 | 1.296 |
| M6_sans_G5 | 2023-24 | 1.8920 | 0.1299 | 0.2377 | 0.0326 | 1.19 | 87.3 % | 87.7 % | 2.9297 | 0.5829 | 1.323 |
| M6_sans_G5 | 2024-25 | 1.8662 | 0.1266 | 0.2419 | 0.0246 | 0.92 | 89.3 % | 87.9 % | 2.9099 | 0.5865 | 1.303 |
| M7_sans_G5 | 2021-22 | 1.8986 | 0.1319 | 0.2446 | 0.0341 | 0.90 | 87.1 % | 87.4 % | 2.9339 | 0.5930 | 1.350 |
| M7_sans_G5 | 2022-23 | 1.8730 | 0.1275 | 0.2445 | 0.0292 | 1.00 | 87.7 % | 87.4 % | 2.9120 | 0.5890 | 1.305 |
| M7_sans_G5 | 2023-24 | 1.8967 | 0.1306 | 0.2391 | 0.0305 | 1.04 | 87.3 % | 87.8 % | 2.9404 | 0.5864 | 1.330 |
| M7_sans_G5 | 2024-25 | 1.8661 | 0.1265 | 0.2413 | 0.0296 | 0.92 | 89.2 % | 88.1 % | 2.9120 | 0.5865 | 1.303 |

| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |
|---|---|---|---|---|---|---|---|
| M3_H2 | 7135 | 1.8798 | 0.1286 | 0.2415 | 0.0142 | 0.97 | +0.038 |
| M6_H2 | 7135 | 1.8797 | 0.1286 | 0.2414 | 0.0086 | 1.02 | +0.028 |
| M7_H2 | 7135 | 1.8822 | 0.1289 | 0.2420 | 0.0137 | 0.99 | +0.035 |
| M6_sans_G5 | 7135 | 1.8803 | 0.1287 | 0.2416 | 0.0121 | 1.01 | +0.017 |
| M7_sans_G5 | 7135 | 1.8836 | 0.1291 | 0.2424 | 0.0156 | 0.95 | +0.030 |

Petits totaux, calibration poolée sur les 4 plis :

| Modèle | k | P(T = k) prédite | observée | Brier | Écart moyen par décile | Pente |
|---|---|---|---|---|---|---|
| M3_H2 | 0 | 6.6 % | 6.3 % | 0.0587 | 0.0112 | 0.87 |
| M3_H2 | 1 | 17.5 % | 16.3 % | 0.1352 | 0.0136 | 0.98 |
| M3_H2 | 2 | 23.6 % | 24.2 % | 0.1826 | 0.0101 | 1.06 |
| M6_H2 | 0 | 6.5 % | 6.3 % | 0.0587 | 0.0091 | 0.91 |
| M6_H2 | 1 | 17.4 % | 16.3 % | 0.1352 | 0.0160 | 1.04 |
| M6_H2 | 2 | 23.6 % | 24.2 % | 0.1826 | 0.0136 | 1.13 |
| M7_H2 | 0 | 6.5 % | 6.3 % | 0.0587 | 0.0082 | 0.92 |
| M7_H2 | 1 | 17.5 % | 16.3 % | 0.1353 | 0.0114 | 0.99 |
| M7_H2 | 2 | 23.6 % | 24.2 % | 0.1827 | 0.0128 | 1.10 |
| M6_sans_G5 | 0 | 6.4 % | 6.3 % | 0.0587 | 0.0101 | 0.86 |
| M6_sans_G5 | 1 | 17.3 % | 16.3 % | 0.1352 | 0.0131 | 1.03 |
| M6_sans_G5 | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0134 | 1.12 |
| M7_sans_G5 | 0 | 6.5 % | 6.3 % | 0.0587 | 0.0063 | 0.85 |
| M7_sans_G5 | 1 | 17.4 % | 16.3 % | 0.1354 | 0.0141 | 0.94 |
| M7_sans_G5 | 2 | 23.6 % | 24.2 % | 0.1826 | 0.0111 | 1.10 |

Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :

| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |
|---|---|---|---|---|---|---|---|
| M3_H2 | M6_H2 | log-loss du total | +0.00014 | [-0.00044 ; +0.00072] | 3 sur 4 | 0.6322 | 2021 : +0.0007 ; 2022 : -0.0010 ; 2023 : +0.0000 ; 2024 : +0.0010 |
| M3_H2 | M6_H2 | RPS | +0.00002 | [-0.00007 ; +0.00011] | 3 sur 4 | 0.6172 | 2021 : +0.0001 ; 2022 : -0.0002 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| M3_H2 | M6_H2 | Brier P(T = 0) | -0.00000 | [-0.00004 ; +0.00003] | 2 sur 4 | 0.8711 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : -0.0000 |
| M3_H2 | M6_H2 | Brier P(T = 1) | +0.00002 | [-0.00006 ; +0.00009] | 3 sur 4 | 0.6673 | 2021 : +0.0002 ; 2022 : -0.0002 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| M3_H2 | M6_H2 | Brier P(T = 2) | +0.00000 | [-0.00005 ; +0.00006] | 3 sur 4 | 0.8702 | 2021 : +0.0000 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **M6_H2 ne remplace pas M3_H2** | | | |
| M3_H2 | M7_H2 | log-loss du total | -0.00235 | [-0.00444 ; -0.00025] | 0 sur 4 | 0.0298 | 2021 : -0.0021 ; 2022 : -0.0038 ; 2023 : -0.0033 ; 2024 : -0.0002 |
| M3_H2 | M7_H2 | RPS | -0.00032 | [-0.00063 ; -0.00002] | 1 sur 4 | 0.0432 | 2021 : -0.0003 ; 2022 : -0.0005 ; 2023 : -0.0005 ; 2024 : +0.0000 |
| M3_H2 | M7_H2 | Brier P(T = 0) | +0.00002 | [-0.00009 ; +0.00013] | 3 sur 4 | 0.6898 | 2021 : +0.0001 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| M3_H2 | M7_H2 | Brier P(T = 1) | -0.00016 | [-0.00045 ; +0.00014] | 1 sur 4 | 0.2826 | 2021 : -0.0002 ; 2022 : -0.0004 ; 2023 : +0.0001 ; 2024 : -0.0001 |
| M3_H2 | M7_H2 | Brier P(T = 2) | -0.00006 | [-0.00027 ; +0.00014] | 2 sur 4 | 0.5402 | 2021 : -0.0002 ; 2022 : +0.0001 ; 2023 : -0.0002 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **M7_H2 ne remplace pas M3_H2** | | | |
| M6_H2 | M7_H2 | log-loss du total | -0.00250 | [-0.00444 ; -0.00053] | 0 sur 4 | 0.0128 | 2021 : -0.0028 ; 2022 : -0.0027 ; 2023 : -0.0033 ; 2024 : -0.0011 |
| M6_H2 | M7_H2 | RPS | -0.00034 | [-0.00063 ; -0.00006] | 0 sur 4 | 0.0190 | 2021 : -0.0004 ; 2022 : -0.0003 ; 2023 : -0.0005 ; 2024 : -0.0001 |
| M6_H2 | M7_H2 | Brier P(T = 0) | +0.00003 | [-0.00007 ; +0.00013] | 3 sur 4 | 0.6237 | 2021 : +0.0001 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| M6_H2 | M7_H2 | Brier P(T = 1) | -0.00018 | [-0.00043 ; +0.00009] | 1 sur 4 | 0.1837 | 2021 : -0.0004 ; 2022 : -0.0002 ; 2023 : +0.0001 ; 2024 : -0.0002 |
| M6_H2 | M7_H2 | Brier P(T = 2) | -0.00007 | [-0.00026 ; +0.00012] | 2 sur 4 | 0.4801 | 2021 : -0.0002 ; 2022 : +0.0001 ; 2023 : -0.0002 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) non, (iii) non | **M7_H2 ne remplace pas M6_H2** | | | |
| M6_sans_G5 | M6_H2 | log-loss du total | +0.00062 | [-0.00004 ; +0.00126] | 4 sur 4 | 0.0656 | 2021 : +0.0003 ; 2022 : +0.0006 ; 2023 : +0.0003 ; 2024 : +0.0013 |
| M6_sans_G5 | M6_H2 | RPS | +0.00009 | [-0.00001 ; +0.00019] | 4 sur 4 | 0.0789 | 2021 : +0.0000 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : +0.0002 |
| M6_sans_G5 | M6_H2 | Brier P(T = 0) | +0.00003 | [-0.00000 ; +0.00005] | 4 sur 4 | 0.0710 | 2021 : +0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| M6_sans_G5 | M6_H2 | Brier P(T = 1) | +0.00001 | [-0.00007 ; +0.00008] | 2 sur 4 | 0.8813 | 2021 : -0.0001 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| M6_sans_G5 | M6_H2 | Brier P(T = 2) | +0.00002 | [-0.00004 ; +0.00009] | 3 sur 4 | 0.5114 | 2021 : -0.0000 ; 2022 : +0.0001 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **M6_H2 ne remplace pas M6_sans_G5** | | | |
| M7_sans_G5 | M7_H2 | log-loss du total | +0.00145 | [-0.00007 ; +0.00299] | 4 sur 4 | 0.0707 | 2021 : +0.0003 ; 2022 : +0.0038 ; 2023 : +0.0016 ; 2024 : +0.0001 |
| M7_sans_G5 | M7_H2 | RPS | +0.00021 | [-0.00001 ; +0.00043] | 3 sur 4 | 0.0722 | 2021 : +0.0000 ; 2022 : +0.0005 ; 2023 : +0.0003 ; 2024 : -0.0000 |
| M7_sans_G5 | M7_H2 | Brier P(T = 0) | +0.00004 | [-0.00004 ; +0.00012] | 2 sur 4 | 0.2792 | 2021 : -0.0000 ; 2022 : +0.0001 ; 2023 : -0.0000 ; 2024 : +0.0001 |
| M7_sans_G5 | M7_H2 | Brier P(T = 1) | +0.00012 | [-0.00007 ; +0.00032] | 4 sur 4 | 0.2451 | 2021 : +0.0001 ; 2022 : +0.0002 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| M7_sans_G5 | M7_H2 | Brier P(T = 2) | -0.00001 | [-0.00016 ; +0.00013] | 2 sur 4 | 0.8592 | 2021 : -0.0001 ; 2022 : +0.0001 ; 2023 : +0.0001 ; 2024 : -0.0002 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **M7_H2 ne remplace pas M7_sans_G5** | | | |

Écart apparié du log-loss du total par tranche de journées (A − B, positif : B meilleur ; descriptif, hors de la règle de décision) :

| A | B | Tranche | Matchs | Écart poolé | IC 95 % |
|---|---|---|---|---|---|
| M3_H2 | M6_H2 | 1-5 | 967 | -0.00060 | [-0.00265 ; +0.00137] |
| M3_H2 | M6_H2 | 6-10 | 965 | +0.00027 | [-0.00117 ; +0.00169] |
| M3_H2 | M6_H2 | 11-19 | 1745 | +0.00120 | [+0.00014 ; +0.00227] |
| M3_H2 | M6_H2 | 20-99 | 3458 | -0.00022 | [-0.00103 ; +0.00060] |
| M3_H2 | M7_H2 | 1-5 | 967 | -0.00718 | [-0.01275 ; -0.00172] |
| M3_H2 | M7_H2 | 6-10 | 965 | -0.00042 | [-0.00596 ; +0.00548] |
| M3_H2 | M7_H2 | 11-19 | 1745 | +0.00248 | [-0.00163 ; +0.00644] |
| M3_H2 | M7_H2 | 20-99 | 3458 | -0.00398 | [-0.00712 ; -0.00089] |
| M6_H2 | M7_H2 | 1-5 | 967 | -0.00659 | [-0.01141 ; -0.00179] |
| M6_H2 | M7_H2 | 6-10 | 965 | -0.00069 | [-0.00570 ; +0.00460] |
| M6_H2 | M7_H2 | 11-19 | 1745 | +0.00128 | [-0.00261 ; +0.00507] |
| M6_H2 | M7_H2 | 20-99 | 3458 | -0.00377 | [-0.00674 ; -0.00087] |
| M6_sans_G5 | M6_H2 | 1-5 | 967 | +0.00172 | [+0.00003 ; +0.00344] |
| M6_sans_G5 | M6_H2 | 6-10 | 965 | -0.00093 | [-0.00259 ; +0.00076] |
| M6_sans_G5 | M6_H2 | 11-19 | 1745 | +0.00041 | [-0.00104 ; +0.00181] |
| M6_sans_G5 | M6_H2 | 20-99 | 3458 | +0.00085 | [-0.00008 ; +0.00179] |
| M7_sans_G5 | M7_H2 | 1-5 | 967 | -0.00082 | [-0.00526 ; +0.00380] |
| M7_sans_G5 | M7_H2 | 6-10 | 965 | +0.00641 | [+0.00187 ; +0.01101] |
| M7_sans_G5 | M7_H2 | 11-19 | 1745 | +0.00075 | [-0.00212 ; +0.00363] |
| M7_sans_G5 | M7_H2 | 20-99 | 3458 | +0.00105 | [-0.00110 ; +0.00331] |

