# Références : B0, B1 et marché (jalon J5)

*Sous-étape 4.5, 2026-09-30. Protocole figé par l'ADR-0037 (tag `protocole-v1`), posé **avant** ces évaluations. Rapport : `reports/experiments/references-20260930T080623.json` ; expérience : `experiments/references.yaml`. Nombre d'essais à cette date : **2** (une mesure de durée à 200 rééchantillonnages, puis l'expérience ; voir `reports/experiments/INDEX.md`).*

## Pourquoi des références

Un log-loss de 1,90 ne veut rien dire seul. Les références donnent le **niveau zéro** : ce que l'on obtient sans rien savoir des équipes (B0), en sachant seulement le championnat et le terrain (B1), et ce que sait le marché des paris. Un modèle n'a d'intérêt que s'il bat B1 (objectif du MVP, ADR-0037) ; le marché dit jusqu'où l'on pourrait aller.

| Référence | Concept | Ce qu'elle apprend | Ce qu'elle rate |
|---|---|---|---|
| **B0** | Chaque équipe marque selon Poisson(μ), μ = moyenne des buts par équipe et par match d'apprentissage ; donc T ~ Poisson(2μ), la **même loi pour tous les matchs** | le niveau moyen de buts | tout : championnat, terrain, équipes |
| **B1** | λ_dom = moyenne des buts à domicile du championnat du match, λ_ext de même à l'extérieur, sur les `w` dernières saisons (w ∈ {1, 2, 3, 6}, choisi par validation interne) ; T ~ Poisson(λ_dom + λ_ext) | l'avantage du terrain, le niveau de buts de chaque championnat et sa tendance récente | les équipes |
| **Marché** | P(T > 2,5) = q₊ / (q₊ + q₋), q = 1 / cote, moyenne de marché de football-data (ADR-0036) | tout ce que savent les bookmakers avant le match | ne donne pas de loi complète : comparé sur l'événement plus/moins 2,5 seulement |

Deux versions du marché : **avant clôture** (référence de l'horizon H1) et **clôture** (borne haute : la cote de clôture intègre l'information du jour du match, compositions comprises ; elle n'est jamais une référence de H1).

## Résultats

Rapport `references-20260930T080623` : jeu `ds-2026-09-30-ba2b91f7`, commit `3696caa`, graine 20260930, 10000 rééchantillonnages.

| Pli | Matchs d'évaluation | Intersection | Écartés | Avec cote | Hyperparamètres retenus |
|---|---|---|---|---|---|
| 2021-22 | 1826 | 1826 | 0 | 1825 | B1 : {'window': 1} |
| 2022-23 | 1826 | 1826 | 0 | 1826 | B1 : {'window': 3} |
| 2023-24 | 1752 | 1752 | 0 | 1752 | B1 : {'window': 1} |
| 2024-25 | 1752 | 1752 | 0 | 1752 | B1 : {'window': 1} |

| Modèle | Pli | Log-loss | RPS | Brier P(T > 2,5) | Calibration : écart moyen | Pente | Couverture observée | Couverture annoncée | Log-loss score exact | Brier 1N2 | MAE E[T] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | 2021-22 | 1.9147 | 0.1343 | 0.2495 | 0.0413 | n. d. | 86.2 % | 87.5 % | 3.0807 | 0.6583 | 1.379 |
| B0 | 2022-23 | 1.8868 | 0.1294 | 0.2495 | 0.0521 | n. d. | 87.1 % | 87.5 % | 3.0433 | 0.6545 | 1.322 |
| B0 | 2023-24 | 1.9218 | 0.1344 | 0.2483 | 0.0669 | n. d. | 85.8 % | 87.5 % | 3.0941 | 0.6597 | 1.370 |
| B0 | 2024-25 | 1.8886 | 0.1299 | 0.2489 | 0.0451 | n. d. | 87.6 % | 87.5 % | 3.0496 | 0.6563 | 1.332 |
| B1 | 2021-22 | 1.9099 | 0.1336 | 0.2477 | 0.0286 | 0.86 | 86.2 % | 87.1 % | 3.0658 | 0.6530 | 1.368 |
| B1 | 2022-23 | 1.8850 | 0.1293 | 0.2503 | 0.0445 | 0.36 | 87.1 % | 87.1 % | 3.0218 | 0.6437 | 1.322 |
| B1 | 2023-24 | 1.9120 | 0.1328 | 0.2446 | 0.0450 | 1.16 | 87.2 % | 88.2 % | 3.0703 | 0.6519 | 1.354 |
| B1 | 2024-25 | 1.8866 | 0.1295 | 0.2484 | 0.0401 | 0.56 | 89.6 % | 89.1 % | 3.0450 | 0.6542 | 1.342 |

| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |
|---|---|---|---|---|---|---|---|
| B0 | 7156 | 1.9029 | 0.1320 | 0.2491 | 0.0227 | 1.84 | -0.040 |
| B1 | 7156 | 1.8984 | 0.1313 | 0.2478 | 0.0228 | 0.69 | +0.041 |

Événement plus/moins 2,5, sur les matchs de l'intersection qui ont une cote :

| Modèle | Pli | Matchs | Brier | Log-loss binaire | Calibration : écart moyen |
|---|---|---|---|---|---|
| B0 | 2021-22 | 1825 | 0.2495 | 0.6921 | 0.0416 |
| B0 | 2022-23 | 1826 | 0.2495 | 0.6922 | 0.0521 |
| B0 | 2023-24 | 1752 | 0.2483 | 0.6898 | 0.0669 |
| B0 | 2024-25 | 1752 | 0.2489 | 0.6910 | 0.0451 |
| B0 | **poolé** | | **0.2491** | | |
| B1 | 2021-22 | 1825 | 0.2477 | 0.6886 | 0.0278 |
| B1 | 2022-23 | 1826 | 0.2503 | 0.6938 | 0.0445 |
| B1 | 2023-24 | 1752 | 0.2446 | 0.6822 | 0.0450 |
| B1 | 2024-25 | 1752 | 0.2484 | 0.6900 | 0.0401 |
| B1 | **poolé** | | **0.2478** | | |
| marche_avant_cloture | 2021-22 | 1825 | 0.2411 | 0.6749 | 0.0200 |
| marche_avant_cloture | 2022-23 | 1826 | 0.2406 | 0.6741 | 0.0208 |
| marche_avant_cloture | 2023-24 | 1752 | 0.2348 | 0.6620 | 0.0400 |
| marche_avant_cloture | 2024-25 | 1752 | 0.2381 | 0.6688 | 0.0297 |
| marche_avant_cloture | **poolé** | | **0.2387** | | |
| marche_cloture | 2021-22 | 1825 | 0.2397 | 0.6721 | 0.0323 |
| marche_cloture | 2022-23 | 1826 | 0.2402 | 0.6733 | 0.0230 |
| marche_cloture | 2023-24 | 1752 | 0.2331 | 0.6585 | 0.0332 |
| marche_cloture | 2024-25 | 1752 | 0.2363 | 0.6652 | 0.0262 |
| marche_cloture | **poolé** | | **0.2374** | | |

Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :

| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |
|---|---|---|---|---|---|---|---|
| B0 | B1 | log-loss du total | +0.00455 | [+0.00104 ; +0.00799] | 4 sur 4 | 0.0098 | 2021 : +0.0048 ; 2022 : +0.0018 ; 2023 : +0.0097 ; 2024 : +0.0020 |
| B0 | B1 | RPS | +0.00070 | [+0.00020 ; +0.00120] | 4 sur 4 | 0.0060 | 2021 : +0.0007 ; 2022 : +0.0002 ; 2023 : +0.0015 ; 2024 : +0.0004 |
| B0 | B1 | Brier plus/moins 2,5 | +0.00129 | [-0.00001 ; +0.00256] | 3 sur 4 | 0.0476 | 2021 : +0.0017 ; 2022 : -0.0008 ; 2023 : +0.0038 ; 2024 : +0.0005 |
| | | règle de décision | (i) oui, (ii) oui, (iii) non | **B1 ne remplace pas B0** | | | |
| B0 | marche_avant_cloture | Brier plus/moins 2,5 | +0.01039 | [+0.00834 ; +0.01243] | 4 sur 4 | 0.0000 | 2021 : +0.0084 ; 2022 : +0.0089 ; 2023 : +0.0136 ; 2024 : +0.0108 |
| B1 | marche_avant_cloture | Brier plus/moins 2,5 | +0.00909 | [+0.00725 ; +0.01098] | 4 sur 4 | 0.0000 | 2021 : +0.0067 ; 2022 : +0.0097 ; 2023 : +0.0098 ; 2024 : +0.0103 |
| marche_avant_cloture | marche_cloture | Brier plus/moins 2,5 | +0.00129 | [+0.00066 ; +0.00190] | 4 sur 4 | 0.0000 | 2021 : +0.0014 ; 2022 : +0.0004 ; 2023 : +0.0017 ; 2024 : +0.0018 |


## Ce qu'enseignent ces chiffres

1. **B1 bat B0 sur le log-loss du total** : +0,0046 nat par match, intervalle [+0,0010 ; +0,0080], dans les 4 plis ; même sens pour le RPS. Connaître le championnat et le terrain aide, mais peu : 0,0046 sur 1,90, soit 0,24 %. C'est l'ordre de grandeur annoncé par le rapport (C.2) : le total est très bruité.
2. **Et pourtant, la règle de décision dirait « B1 ne remplace pas B0 »** : le critère (iii) échoue, car la **pente de calibration poolée de B1 vaut 0,69** (hors de [0,9 ; 1,1]). B1 ne donne que 5 valeurs différentes de P(T ≥ 3) par saison (une par championnat, λ_dom + λ_ext), très proches les unes des autres : la pente d'une régression logistique sur si peu de dispersion est mal estimée (de 0,36 à 1,16 selon le pli). B1 est une référence, pas un candidat : ce verdict est **informatif**. Il signale une fragilité du critère (iii) pour des modèles aux prédictions peu dispersées ; la règle n'est pas modifiée (ADR-0037), et le constat sera rappelé si un modèle échoue au lot 2 **par sa seule pente**.
3. **Le marché est loin devant** : Brier de P(T > 2,5) de 0,2387 contre 0,2491 pour B0 (écart +0,0104 [+0,0083 ; +0,0124]) et 0,2478 pour B1 (+0,0091 [+0,0073 ; +0,0110]), dans les 4 plis. Contrôle de cohérence demandé : **le marché bat B0**, nettement.
4. **La clôture fait encore mieux que l'avant-clôture** : +0,0013 [+0,0007 ; +0,0019] de Brier. De l'information arrive jusqu'au coup d'envoi : c'est la raison pour laquelle la clôture n'est jamais une référence de l'horizon H1.
5. **Contrôle de cohérence de B0** : sur les 7 156 matchs d'évaluation, la moyenne des totaux est 2,821 et leur variance 2,836 (pas de surdispersion visible sur la loi marginale). L'entropie de Poisson(2,821), repliée sur « 10 et plus », vaut **1,8973** ; le log-loss de cette même loi sur les totaux observés (connue a posteriori) vaut 1,9024 ; celui de B0, **1,9029**. B0 perd donc presque tout ce qu'il peut perdre face à la meilleure loi constante, ce qui est attendu : ses λ (de 2,759 à 2,779) sont un peu en dessous des moyennes observées des saisons de test (de 2,766 à 2,885).
6. **Couverture de [q10 ; q90]** : à moins de 2 points de la couverture annoncée par pli pour B0 (de −1,7 à +0,1) et B1 (de −1,0 à +0,5). L'intervalle discret couvre environ 87 % des matchs, pas 80 % : c'est la couverture **annoncée** qui compte (ADR-0009).
7. **Fenêtre de B1** : 1 saison dans trois plis, 3 saisons dans un pli (2022-23). La validation interne préfère la saison la plus récente : le niveau de buts d'un championnat bouge d'une saison à l'autre.

## Limites

- La calibration par décile d'une prévision **constante** (B0 dans un pli) n'a pas de sens : ses déciles sont formés par ordre arbitraire ; sa pente n'est pas définie (« n. d. »). La pente poolée de B0 (1,84) ne repose que sur 4 valeurs distinctes.
- Le marché n'est comparé que sur plus/moins 2,5 ; un match des plis (2021-22) n'a pas de cote et est écarté de cette comparaison.
- Nombre d'essais : 2 à cette date. Les comparaisons du lot 2 s'ajouteront à l'index.
