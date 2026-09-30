# Modèles M1 à M6 (jalon J6, lot 2)

*Partie 4, lot 2. Protocole figé par l'ADR-0037 (tag `protocole-v1`). Jeu `ds-2026-09-30-ba2b91f7`, 4 plis (2021-22 à 2024-25), matchs de championnat du top 5. Structures comparées avec les variables **G0 + G1** (décision 5). Chaque section donne le concept, les hypothèses, ce que le modèle apporte et ce qu'il rate ; les tableaux sont générés depuis les rapports (`modeling summary`). Équations : chapitre « Modèles » de `docs/latex/mathematiques/`.*

## Tableau des structures (4 plis poolés, 7 156 matchs)

| Modèle | Variables | Log-loss du total | RPS | Brier P(T > 2,5) | Pente de calibration poolée | Rôle |
|---|---|---|---|---|---|---|
| B0 | aucune | 1,9029 | 0,1320 | 0,2491 | n. d. | référence |
| B1 | championnat × côté | 1,8984 | 0,1313 | 0,2478 | 0,69 | référence (objectif du MVP : la battre) |
| M1 | G0 + G1 | 1,9092 | 0,1309 | 0,2471 | 0,95 | pédagogique |
| M2 | G0 + G1 | 1,8930 | 0,1305 | 0,2460 | 0,97 | pédagogique |
| **M3** | G0 + G1 | **1,8897** | 0,1301 | 0,2450 | 1,01 | **structure retenue** (ADR-0038) |
| M4 | G0 + G1 | non évalué | | | | binomiale négative non justifiée |
| M5 | G0 + G1 | 1,8897 | 0,1301 | 0,2450 | 1,01 | sans gain |
| M3 | G0 à G3 | 1,8806 | 0,1287 | 0,2416 | 0,95 | préfigure les ablations du lot 3 |
| M6 ridge | G0 à G3 | 1,8804 | 0,1287 | 0,2416 | 1,01 | sans gain sur M3 à variables égales |
| M6 élastique net | G0 à G3 | 1,8805 | 0,1287 | 0,2416 | 0,96 | idem |

| Question (rapport I.4) | Comparaison A − B (log-loss) | Écart [IC 95 %] | Plis où B gagne | Réponse |
|---|---|---|---|---|
| La linéaire suffit-elle ? | B1 − M1 | −0,0108 [−0,0166 ; −0,0049] | 0 sur 4 | non : la forme de la loi est fausse |
| Une loi de comptage fait-elle mieux ? | M1 − M2 | +0,0162 [+0,0115 ; +0,0208] | 4 sur 4 | oui |
| Faut-il décomposer par équipe ? | M2 − M3 | +0,0033 [+0,0014 ; +0,0052] | 4 sur 4 | oui : **M3 remplace M2** |
| La loi de Poisson est-elle adéquate ? | diagnostic M3 → M4 | φ ≈ 0,98, LR = 0 | — | oui (légère sous-dispersion) : pas de NB |
| La corrélation change-t-elle la loi du total ? | M3 − M5 | +0,00002 [−0,0009 ; +0,0010] | 2 sur 4 | la forme sur 0 et 1 but, pas le log-loss |
| Plus de variables sans surapprendre ? | M3 (G0 à G3) − M6 ridge | +0,0002 [−0,0004 ; +0,0008] | 3 sur 4 | la régularisation n'apporte rien ; les variables, si (+0,0091) |
| M3 bat-il la référence ? | B1 − M3 | +0,0087 [+0,0048 ; +0,0126] | 4 sur 4 | oui : objectif du MVP atteint dès G0 + G1 |

**Ce que le parcours enseigne** : la forme de la loi compte (M1 → M2), la structure attaque × défense aussi (M2 → M3) ; ni la dispersion, ni la dépendance, ni la régularisation ne changent la loi du total de façon mesurable. Le gain suivant viendra des **variables** (G2, G3 : lot 3). Essais à cette date : **7**, dont 2 mesures de durée, 0 échec (`reports/experiments/INDEX.md`).

## M1 et M2 : modèles du total (étapes pédagogiques)

Rapport `reports/experiments/m1-m2-20260930T083847.json`, expérience `experiments/m1_m2.yaml`.

- **M1, régression linéaire** (moindres carrés ordinaires) : T = xᵀβ + ε, loi prédictive normale N(xᵀβ̂, σ̂² + se²), discrétisée sur 0..9 et « 10 et plus » (la masse sous −½ rabattue sur 0). Hypothèses de Gauss-Markov : linéarité, exogénéité, variance constante, erreurs non corrélées.
- **M2, GLM de Poisson sur le total** : T ~ Poisson(μ), log μ = xᵀβ (lien log, maximum de vraisemblance par IRLS), déviance, dispersion.
- Variables (G0 + G1, niveau match) : effets fixes de championnat, huis clos, Elo de l'équipe à domicile et de l'équipe à l'extérieur. Ni M1 ni M2 ne sont candidats au choix final (ADR-0009).

Rapport `m1-m2-20260930T083847` : jeu `ds-2026-09-30-ba2b91f7`, commit `1acb924`, graine 20260930, 10000 rééchantillonnages.

| Pli | Matchs d'évaluation | Intersection | Écartés | Avec cote | Hyperparamètres retenus |
|---|---|---|---|---|---|
| 2021-22 | 1826 | 1826 | 0 | n. d. | B1 : {'window': 1}; M1 : {'groups': ['G0', 'G1']}; M2 : {'groups': ['G0', 'G1']} |
| 2022-23 | 1826 | 1826 | 0 | n. d. | B1 : {'window': 3}; M1 : {'groups': ['G0', 'G1']}; M2 : {'groups': ['G0', 'G1']} |
| 2023-24 | 1752 | 1752 | 0 | n. d. | B1 : {'window': 1}; M1 : {'groups': ['G0', 'G1']}; M2 : {'groups': ['G0', 'G1']} |
| 2024-25 | 1752 | 1752 | 0 | n. d. | B1 : {'window': 1}; M1 : {'groups': ['G0', 'G1']}; M2 : {'groups': ['G0', 'G1']} |

| Modèle | Pli | Log-loss | RPS | Brier P(T > 2,5) | Calibration : écart moyen | Pente | Couverture observée | Couverture annoncée | Log-loss score exact | Brier 1N2 | MAE E[T] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 | 2021-22 | 1.9099 | 0.1336 | 0.2477 | 0.0286 | 0.86 | 86.2 % | 87.1 % | 3.0658 | 0.6530 | 1.368 |
| B1 | 2022-23 | 1.8850 | 0.1293 | 0.2503 | 0.0445 | 0.36 | 87.1 % | 87.1 % | 3.0218 | 0.6437 | 1.322 |
| B1 | 2023-24 | 1.9120 | 0.1328 | 0.2446 | 0.0450 | 1.16 | 87.2 % | 88.2 % | 3.0703 | 0.6519 | 1.354 |
| B1 | 2024-25 | 1.8866 | 0.1295 | 0.2484 | 0.0401 | 0.56 | 89.6 % | 89.1 % | 3.0450 | 0.6542 | 1.342 |
| M1 | 2021-22 | 1.9185 | 0.1333 | 0.2484 | 0.0485 | 0.87 | 88.8 % | 89.7 % | n. d. | n. d. | 1.364 |
| M1 | 2022-23 | 1.9028 | 0.1289 | 0.2491 | 0.0423 | 0.82 | 89.3 % | 89.6 % | n. d. | n. d. | 1.310 |
| M1 | 2023-24 | 1.9238 | 0.1329 | 0.2446 | 0.0248 | 1.03 | 87.8 % | 89.3 % | n. d. | n. d. | 1.352 |
| M1 | 2024-25 | 1.8915 | 0.1285 | 0.2461 | 0.0539 | 1.08 | 89.3 % | 89.3 % | n. d. | n. d. | 1.311 |
| M2 | 2021-22 | 1.9062 | 0.1330 | 0.2469 | 0.0345 | 0.90 | 86.1 % | 87.3 % | n. d. | n. d. | 1.365 |
| M2 | 2022-23 | 1.8766 | 0.1281 | 0.2473 | 0.0280 | 0.84 | 87.4 % | 87.3 % | n. d. | n. d. | 1.310 |
| M2 | 2023-24 | 1.9126 | 0.1329 | 0.2449 | 0.0289 | 1.05 | 86.5 % | 87.3 % | n. d. | n. d. | 1.353 |
| M2 | 2024-25 | 1.8767 | 0.1281 | 0.2449 | 0.0441 | 1.10 | 88.1 % | 87.4 % | n. d. | n. d. | 1.311 |

| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |
|---|---|---|---|---|---|---|---|
| B1 | 7156 | 1.8984 | 0.1313 | 0.2478 | 0.0228 | 0.69 | +0.041 |
| M1 | 7156 | 1.9092 | 0.1309 | 0.2471 | 0.0337 | 0.95 | -0.125 |
| M2 | 7156 | 1.8930 | 0.1305 | 0.2460 | 0.0195 | 0.97 | +0.039 |

Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :

| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |
|---|---|---|---|---|---|---|---|
| B1 | M1 | log-loss du total | -0.01079 | [-0.01659 ; -0.00493] | 0 sur 4 | 0.0003 | 2021 : -0.0085 ; 2022 : -0.0177 ; 2023 : -0.0117 ; 2024 : -0.0050 |
| B1 | M1 | RPS | +0.00040 | [-0.00013 ; +0.00093] | 3 sur 4 | 0.1348 | 2021 : +0.0003 ; 2022 : +0.0004 ; 2023 : -0.0000 ; 2024 : +0.0011 |
| | | règle de décision | (i) non, (ii) non, (iii) non | **M1 ne remplace pas B1** | | | |
| B1 | M2 | log-loss du total | +0.00540 | [+0.00181 ; +0.00896] | 3 sur 4 | 0.0032 | 2021 : +0.0037 ; 2022 : +0.0084 ; 2023 : -0.0005 ; 2024 : +0.0099 |
| B1 | M2 | RPS | +0.00075 | [+0.00025 ; +0.00126] | 3 sur 4 | 0.0038 | 2021 : +0.0005 ; 2022 : +0.0011 ; 2023 : -0.0001 ; 2024 : +0.0015 |
| | | règle de décision | (i) oui, (ii) oui, (iii) oui | **M2 remplace B1** | | | |
| M1 | M2 | log-loss du total | +0.01619 | [+0.01151 ; +0.02083] | 4 sur 4 | 0.0000 | 2021 : +0.0123 ; 2022 : +0.0262 ; 2023 : +0.0112 ; 2024 : +0.0149 |
| M1 | M2 | RPS | +0.00035 | [+0.00012 ; +0.00058] | 3 sur 4 | 0.0031 | 2021 : +0.0003 ; 2022 : +0.0008 ; 2023 : -0.0000 ; 2024 : +0.0004 |
| | | règle de décision | (i) oui, (ii) oui, (iii) oui | **M2 remplace M1** | | | |


### Pourquoi M1 ne suffit pas (chiffré)

| Défaut attendu (rapport I.4) | Mesure (4 plis) |
|---|---|
| Prédictions négatives | aucune moyenne négative (la plus petite vaut 2,13), mais **2,5 %** de la masse de probabilité sur des totaux « négatifs », rabattue sur 0 |
| Loi continue pour un comptage | P(T = 0) surestimée (8,6 à 8,8 % prédits contre 5,8 à 7,0 % observés), P(T = 1) sous-estimée (13,4 à 13,7 % contre 15,2 à 17,4 %) |
| Variance constante | la variance des résidus croît avec la valeur ajustée, de 2,48 à 3,13 du premier au dernier quintile ; Breusch-Pagan p < 10⁻⁵ dans chaque pli |
| Intervalle symétrique | l'intervalle normal à 80 % (μ ± 1,28 s) ne descend jamais sous 0 ici (μ ≥ 2,13, s ≈ 1,65) : ce défaut n'est pas atteint sur ces données, mais l'intervalle ignore l'asymétrie à droite d'un comptage |
| Pouvoir explicatif | R² d'apprentissage de 2,1 % : le total est très bruité (rapport C.2) |

Résultat : **M1 est moins bon que B1** (−0,0108 [−0,0166 ; −0,0049], 0 pli sur 4), alors même que ses variables (Elo) sont plus riches. Au RPS, il fait jeu égal (+0,0004 [−0,0001 ; +0,0009]) : la moyenne est bonne, c'est la **forme** de la loi qui est fausse, et le log-loss la sanctionne.

### Ce que M2 enseigne

- **Dispersion** : φ = 0,987 à 0,991 et Cameron-Trivedi α̂ ≈ −0,004 (t ≈ −1, p > 0,29) dans chaque pli : une fois le championnat et l'Elo connus, la variance du total est celle d'une loi de Poisson. Pas de surdispersion à corriger.
- **Calibration** : P(T = 0), P(T = 1), P(T = 2) à moins de 2,2 points des fréquences observées ; PIT proche de l'uniforme (de 8,7 à 11,5 % par décile) ; pente poolée 0,97.
- **Gain** : M2 bat M1 de +0,0162 [+0,0115 ; +0,0208] et **B1 de +0,0054 [+0,0018 ; +0,0090]** (3 plis sur 4 ; les trois critères de la règle sont remplis). C'est le premier modèle qui bat la référence : l'Elo apporte de l'information sur le total, au-delà du championnat. M2 reste une étape : il ne sait pas « qui marque ».

## M3 : Poisson par équipe (structure de référence)

Rapport `reports/experiments/m3-20260930T084658.json`, expérience `experiments/m3.yaml`.

- **Concept** : une ligne par (match, équipe), Y ~ Poisson(λ), log λ = xᵀβ, x contenant les variables de l'équipe **et** de l'adversaire ; λ domicile et λ extérieur, total Poisson(λ_dom + λ_ext) (indépendance conditionnelle), loi jointe pour le score exact et le 1N2.
- **Hypothèses** : loi de Poisson (variance = moyenne), log λ linéaire dans les variables, indépendance des deux équipes sachant les variables (testée par M5).
- **Erreurs standard groupées par match** : de 0,97 à 1,00 fois les erreurs naïves ; les deux lignes d'un match, sachant les variables, sont presque indépendantes (très légère corrélation négative).

Rapport `m3-20260930T084658` : jeu `ds-2026-09-30-ba2b91f7`, commit `1fc8290`, graine 20260930, 10000 rééchantillonnages.

| Pli | Matchs d'évaluation | Intersection | Écartés | Avec cote | Hyperparamètres retenus |
|---|---|---|---|---|---|
| 2021-22 | 1826 | 1826 | 0 | n. d. | B1 : {'window': 1}; M2 : {'groups': ['G0', 'G1']}; M3 : {'groups': ['G0', 'G1'], 'check_dispersion': True} |
| 2022-23 | 1826 | 1826 | 0 | n. d. | B1 : {'window': 3}; M2 : {'groups': ['G0', 'G1']}; M3 : {'groups': ['G0', 'G1'], 'check_dispersion': True} |
| 2023-24 | 1752 | 1752 | 0 | n. d. | B1 : {'window': 1}; M2 : {'groups': ['G0', 'G1']}; M3 : {'groups': ['G0', 'G1'], 'check_dispersion': True} |
| 2024-25 | 1752 | 1752 | 0 | n. d. | B1 : {'window': 1}; M2 : {'groups': ['G0', 'G1']}; M3 : {'groups': ['G0', 'G1'], 'check_dispersion': True} |

| Modèle | Pli | Log-loss | RPS | Brier P(T > 2,5) | Calibration : écart moyen | Pente | Couverture observée | Couverture annoncée | Log-loss score exact | Brier 1N2 | MAE E[T] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 | 2021-22 | 1.9099 | 0.1336 | 0.2477 | 0.0286 | 0.86 | 86.2 % | 87.1 % | 3.0658 | 0.6530 | 1.368 |
| B1 | 2022-23 | 1.8850 | 0.1293 | 0.2503 | 0.0445 | 0.36 | 87.1 % | 87.1 % | 3.0218 | 0.6437 | 1.322 |
| B1 | 2023-24 | 1.9120 | 0.1328 | 0.2446 | 0.0450 | 1.16 | 87.2 % | 88.2 % | 3.0703 | 0.6519 | 1.354 |
| B1 | 2024-25 | 1.8866 | 0.1295 | 0.2484 | 0.0401 | 0.56 | 89.6 % | 89.1 % | 3.0450 | 0.6542 | 1.342 |
| M2 | 2021-22 | 1.9062 | 0.1330 | 0.2469 | 0.0345 | 0.90 | 86.1 % | 87.3 % | n. d. | n. d. | 1.365 |
| M2 | 2022-23 | 1.8766 | 0.1281 | 0.2473 | 0.0280 | 0.84 | 87.4 % | 87.3 % | n. d. | n. d. | 1.310 |
| M2 | 2023-24 | 1.9126 | 0.1329 | 0.2449 | 0.0289 | 1.05 | 86.5 % | 87.3 % | n. d. | n. d. | 1.353 |
| M2 | 2024-25 | 1.8767 | 0.1281 | 0.2449 | 0.0441 | 1.10 | 88.1 % | 87.4 % | n. d. | n. d. | 1.311 |
| M3 | 2021-22 | 1.9043 | 0.1328 | 0.2463 | 0.0291 | 0.89 | 86.4 % | 87.3 % | 2.9341 | 0.5920 | 1.364 |
| M3 | 2022-23 | 1.8721 | 0.1275 | 0.2458 | 0.0277 | 0.96 | 87.4 % | 87.2 % | 2.9091 | 0.5876 | 1.305 |
| M3 | 2023-24 | 1.9078 | 0.1322 | 0.2435 | 0.0392 | 1.18 | 86.3 % | 87.3 % | 2.9461 | 0.5832 | 1.348 |
| M3 | 2024-25 | 1.8747 | 0.1278 | 0.2445 | 0.0300 | 1.02 | 87.9 % | 87.3 % | 2.9235 | 0.5885 | 1.312 |

| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |
|---|---|---|---|---|---|---|---|
| B1 | 7156 | 1.8984 | 0.1313 | 0.2478 | 0.0228 | 0.69 | +0.041 |
| M2 | 7156 | 1.8930 | 0.1305 | 0.2460 | 0.0195 | 0.97 | +0.039 |
| M3 | 7156 | 1.8897 | 0.1301 | 0.2450 | 0.0143 | 1.01 | +0.047 |

Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :

| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |
|---|---|---|---|---|---|---|---|
| B1 | M3 | log-loss du total | +0.00869 | [+0.00477 ; +0.01262] | 4 sur 4 | 0.0000 | 2021 : +0.0056 ; 2022 : +0.0129 ; 2023 : +0.0043 ; 2024 : +0.0119 |
| B1 | M3 | RPS | +0.00120 | [+0.00064 ; +0.00177] | 4 sur 4 | 0.0000 | 2021 : +0.0008 ; 2022 : +0.0017 ; 2023 : +0.0006 ; 2024 : +0.0017 |
| | | règle de décision | (i) oui, (ii) oui, (iii) oui | **M3 remplace B1** | | | |
| M2 | M3 | log-loss du total | +0.00329 | [+0.00140 ; +0.00520] | 4 sur 4 | 0.0006 | 2021 : +0.0019 ; 2022 : +0.0045 ; 2023 : +0.0048 ; 2024 : +0.0020 |
| M2 | M3 | RPS | +0.00045 | [+0.00017 ; +0.00073] | 4 sur 4 | 0.0018 | 2021 : +0.0002 ; 2022 : +0.0006 ; 2023 : +0.0007 ; 2024 : +0.0003 |
| | | règle de décision | (i) oui, (ii) oui, (iii) oui | **M3 remplace M2** | | | |

### Ce que M3 enseigne

- **Décomposer par équipe paie** : M3 bat M2 de +0,0033 [+0,0014 ; +0,0052] dans les 4 plis, avec les **mêmes variables** (G0 + G1). La règle de décision s'applique : M3 remplace M2 (et B1).
- **Objectif du MVP déjà atteint par M3** : +0,0087 [+0,0048 ; +0,0126] sur B1 ; pente de calibration poolée 1,01 ; couverture observée à 1,0 point au plus de l'annoncée, par pli.
- **Coefficients lisibles** (pli 2024-25) : domicile +0,25 (×1,28 buts) ; à huis clos, −0,15 (l'avantage tombe à ×1,11) ; Elo de l'équipe +0,24 par écart-type, Elo de l'adversaire −0,18.
- **Continuité avec les modèles de 2025** : log-loss du score exact de 2,91 à 2,95 et Brier du 1N2 de 0,583 à 0,592 selon le pli (repères historiques : 2,933 et 0,59 sur 2024-25).
- **Ce qu'il rate** : P(T = 1) reste surestimée (17,3 à 17,7 % prédits contre 15,2 à 17,4 % observés) ; la dépendance entre les deux équipes est la question de M5.

## M4 : binomiale négative, non retenue (constat)

La binomiale négative NB2 (Var = μ + α μ²) n'est évaluée que si la surdispersion est établie (sous-étape 4.8). Diagnostic sur l'apprentissage de chaque pli (M3, G0 + G1) :

| Pli | φ (Pearson) | Cameron-Trivedi α̂ | t | p | α̂ de la NB2 | LR | p (au bord) |
|---|---|---|---|---|---|---|---|
| 2021-22 | 0,980 | −0,016 | −2,39 | 0,017 | 2,5 · 10⁻⁷ | 0,000 | 0,50 |
| 2022-23 | 0,979 | −0,014 | −2,41 | 0,016 | 1,8 · 10⁻⁷ | 0,000 | 0,49 |
| 2023-24 | 0,979 | −0,014 | −2,57 | 0,010 | 2,9 · 10⁻⁷ | 0,000 | 0,50 |
| 2024-25 | 0,976 | −0,017 | −3,21 | 0,001 | 6,0 · 10⁻⁷ | 0,000 | 0,50 |

**Lecture** : une fois le championnat, le terrain et l'Elo connus, les buts d'une équipe sont légèrement **sous**-dispersés (φ < 1, α̂ < 0 significatif). La NB2 ne peut qu'ajouter de la variance : son α tombe au bord (0), le rapport de vraisemblance est nul. **M4 n'est pas évalué sur les plis** (aucun essai ajouté) ; M3 reste la structure de référence. Une sous-dispersion de cet ordre (2 %) coûte peu ; une loi sous-dispersée (Conway-Maxwell-Poisson, par exemple) serait une piste de la version avancée, pas du MVP. Dans le pli 2023-24, l'optimiseur de la NB2 signale une non-convergence, au bord α = 0 : sans effet sur le constat.

## M5 : dépendance entre les équipes (Dixon-Coles)

Rapport `reports/experiments/m5-20260930T085337.json`, expérience `experiments/m5.yaml`.

- **Concept** : M3, puis correction τ des scores 0-0, 1-0, 0-1 et 1-1 (Dixon et Coles, 1997), ρ estimé dans le pli à λ fixés ; loi du total tirée de la loi jointe corrigée.
- **Question** (rapport I.2) : la corrélation change-t-elle la loi du total sur les petites valeurs ? Mesurée par la calibration de P(T = 0), P(T = 1), P(T = 2).
- ρ̂ par pli : −0,060 (2021-22), −0,061 (2022-23), −0,055 (2023-24), −0,058 (2024-25) ; bornes τ > 0 : environ [−0,25 ; +0,37].

| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |
|---|---|---|---|---|---|---|---|
| M3 | 7156 | 1.8897 | 0.1301 | 0.2450 | 0.0143 | 1.01 | +0.047 |
| M5 | 7156 | 1.8897 | 0.1301 | 0.2450 | 0.0143 | 1.01 | +0.047 |

Petits totaux, calibration poolée sur les 4 plis :

| Modèle | k | P(T = k) prédite | observée | Brier | Écart moyen par décile | Pente |
|---|---|---|---|---|---|---|
| M3 | 0 | 6.5 % | 6.3 % | 0.0587 | 0.0047 | 0.93 |
| M3 | 1 | 17.6 % | 16.3 % | 0.1362 | 0.0129 | 0.94 |
| M3 | 2 | 23.9 % | 24.2 % | 0.1829 | 0.0102 | 1.17 |
| M5 | 0 | 7.1 % | 6.3 % | 0.0588 | 0.0086 | 0.97 |
| M5 | 1 | 16.3 % | 16.3 % | 0.1360 | 0.0073 | 0.96 |
| M5 | 2 | 24.6 % | 24.2 % | 0.1829 | 0.0082 | 1.14 |

Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :

| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |
|---|---|---|---|---|---|---|---|
| M3 | M5 | log-loss du total | +0.00002 | [-0.00091 ; +0.00098] | 2 sur 4 | 0.9709 | 2021 : +0.0006 ; 2022 : -0.0011 ; 2023 : +0.0008 ; 2024 : -0.0002 |
| M3 | M5 | RPS | +0.00001 | [-0.00000 ; +0.00003] | 3 sur 4 | 0.1367 | 2021 : +0.0000 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| M3 | M5 | Brier P(T = 0) | -0.00007 | [-0.00015 ; +0.00000] | 0 sur 4 | 0.0614 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : -0.0000 ; 2024 : -0.0001 |
| M3 | M5 | Brier P(T = 1) | +0.00018 | [-0.00006 ; +0.00041] | 3 sur 4 | 0.1367 | 2021 : +0.0003 ; 2022 : -0.0001 ; 2023 : +0.0005 ; 2024 : +0.0001 |
| M3 | M5 | Brier P(T = 2) | +0.00001 | [-0.00013 ; +0.00014] | 3 sur 4 | 0.9142 | 2021 : +0.0000 ; 2022 : +0.0000 ; 2023 : -0.0001 ; 2024 : +0.0001 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **M5 ne remplace pas M3** | | | |

### Ce que M5 enseigne

- **Oui, la corrélation change la forme de la loi** : ρ < 0 rend 0-0 et 1-1 plus probables. P(T = 1) passe de 17,6 % à 16,3 %, exactement la fréquence observée ; mais P(T = 0) passe de 6,5 % à 7,1 %, au-delà des 6,3 % observés. La correction répare un défaut de M3 et en crée un autre.
- **Non, cela ne se voit pas globalement** : log-loss du total +0,00002 [−0,0009 ; +0,0010], 2 plis sur 4 ; Brier de P(T = 0) légèrement moins bon (−0,00007 [−0,00015 ; 0,00000]), de P(T = 1) légèrement meilleur (+0,00018 [−0,00006 ; +0,00041]), aucun des deux significatif.
- **Décision** (règle de l'ADR-0037) : (i) non, (ii) non, (iii) oui : **M5 ne remplace pas M3**. On garde le plus simple.
- Le score exact gagne un peu (log-loss de 2,9443 contre 2,9461 en 2023-24, par exemple) : c'est ce que visait Dixon-Coles, pas notre métrique.
- Le Poisson bivarié (option facultative) n'est pas estimé : sa covariance commune positive va dans le même sens que ρ < 0 (dépendance positive sur les petits scores), dont on vient de voir qu'elle n'apporte rien au total. Les forces latentes et le Dixon-Coles dynamique (M8) restent hors périmètre.

## M6 : Poisson régularisé, variables G0 à G3

Rapport `reports/experiments/m6-20260930T090747.json`, expérience `experiments/m6.yaml` (durée : 12 min, dont l'essentiel pour l'élastique net ; mesure préalable sur un pli : `reports/experiments/m6-mesure-duree-20260930T090147.json`).

- **Concept** : Poisson par équipe avec toutes les variables candidates (G0 à G3 : une trentaine de coefficients, dont beaucoup corrélés), coefficients rétrécis par une pénalité. **Ridge** (L2, `PoissonRegressor`) et **élastique net** (L1 + L2, `statsmodels`), variables standardisées dans le pli, constante non pénalisée. α et la demi-vie (60, 120, 240 jours) choisis par validation interne.
- **Comparaisons** : contre M3 avec G0 + G1 (gain de l'ensemble), et contre **M3 non régularisé avec les mêmes variables G0 à G3** (`M3_G0G3`), qui isole l'apport de la régularisation.
- 26 lignes d'apprentissage exclues par pli (`xg_proxy` vide), aucun match de test perdu.

| Pli | Matchs d'évaluation | Intersection | Écartés | Avec cote | Hyperparamètres retenus |
|---|---|---|---|---|---|
| 2021-22 | 1826 | 1826 | 0 | n. d. | M3 : {'groups': ['G0', 'G1']}; M3_G0G3 : {'groups': ['G0', 'G1', 'G2', 'G3'], 'half_life': 240}; M6_ridge : {'groups': ['G0', 'G1', 'G2', 'G3'], 'penalty': 'l2', 'alpha': 0.1, 'half_life': 240}; M6_en : {'groups': ['G0', 'G1', 'G2', 'G3'], 'penalty': 'elasticnet', 'l1_ratio': 0.5, 'alpha': 0.0001, 'half_life': 240} |
| 2022-23 | 1826 | 1826 | 0 | n. d. | M3 : {'groups': ['G0', 'G1']}; M3_G0G3 : {'groups': ['G0', 'G1', 'G2', 'G3'], 'half_life': 120}; M6_ridge : {'groups': ['G0', 'G1', 'G2', 'G3'], 'penalty': 'l2', 'alpha': 0.1, 'half_life': 120}; M6_en : {'groups': ['G0', 'G1', 'G2', 'G3'], 'penalty': 'elasticnet', 'l1_ratio': 0.5, 'alpha': 0.001, 'half_life': 120} |
| 2023-24 | 1752 | 1752 | 0 | n. d. | M3 : {'groups': ['G0', 'G1']}; M3_G0G3 : {'groups': ['G0', 'G1', 'G2', 'G3'], 'half_life': 240}; M6_ridge : {'groups': ['G0', 'G1', 'G2', 'G3'], 'penalty': 'l2', 'alpha': 0.0001, 'half_life': 240}; M6_en : {'groups': ['G0', 'G1', 'G2', 'G3'], 'penalty': 'elasticnet', 'l1_ratio': 0.5, 'alpha': 0.001, 'half_life': 240} |
| 2024-25 | 1752 | 1752 | 0 | n. d. | M3 : {'groups': ['G0', 'G1']}; M3_G0G3 : {'groups': ['G0', 'G1', 'G2', 'G3'], 'half_life': 240}; M6_ridge : {'groups': ['G0', 'G1', 'G2', 'G3'], 'penalty': 'l2', 'alpha': 0.1, 'half_life': 240}; M6_en : {'groups': ['G0', 'G1', 'G2', 'G3'], 'penalty': 'elasticnet', 'l1_ratio': 0.5, 'alpha': 0.0001, 'half_life': 240} |

| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |
|---|---|---|---|---|---|---|---|
| M3 | 7156 | 1.8897 | 0.1301 | 0.2450 | 0.0143 | 1.01 | +0.047 |
| M3_G0G3 | 7156 | 1.8806 | 0.1287 | 0.2416 | 0.0110 | 0.95 | +0.029 |
| M6_ridge | 7156 | 1.8804 | 0.1287 | 0.2416 | 0.0112 | 1.01 | +0.019 |
| M6_en | 7156 | 1.8805 | 0.1287 | 0.2416 | 0.0106 | 0.96 | +0.021 |

Petits totaux, calibration poolée sur les 4 plis :

| Modèle | k | P(T = k) prédite | observée | Brier | Écart moyen par décile | Pente |
|---|---|---|---|---|---|---|
| M3 | 0 | 6.5 % | 6.3 % | 0.0587 | 0.0047 | 0.93 |
| M3 | 1 | 17.6 % | 16.3 % | 0.1362 | 0.0129 | 0.94 |
| M3 | 2 | 23.9 % | 24.2 % | 0.1829 | 0.0102 | 1.17 |
| M3_G0G3 | 0 | 6.5 % | 6.3 % | 0.0586 | 0.0075 | 0.81 |
| M3_G0G3 | 1 | 17.4 % | 16.3 % | 0.1353 | 0.0129 | 0.97 |
| M3_G0G3 | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0159 | 1.06 |
| M6_ridge | 0 | 6.5 % | 6.3 % | 0.0586 | 0.0081 | 0.85 |
| M6_ridge | 1 | 17.3 % | 16.3 % | 0.1353 | 0.0132 | 1.03 |
| M6_ridge | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0141 | 1.14 |
| M6_en | 0 | 6.5 % | 6.3 % | 0.0586 | 0.0076 | 0.83 |
| M6_en | 1 | 17.3 % | 16.3 % | 0.1353 | 0.0115 | 0.97 |
| M6_en | 2 | 23.5 % | 24.2 % | 0.1826 | 0.0146 | 1.05 |

Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :

| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |
|---|---|---|---|---|---|---|---|
| M3 | M6_ridge | log-loss du total | +0.00926 | [+0.00606 ; +0.01247] | 4 sur 4 | 0.0000 | 2021 : +0.0081 ; 2022 : +0.0058 ; 2023 : +0.0150 ; 2024 : +0.0084 |
| M3 | M6_ridge | RPS | +0.00138 | [+0.00092 ; +0.00185] | 4 sur 4 | 0.0000 | 2021 : +0.0012 ; 2022 : +0.0009 ; 2023 : +0.0022 ; 2024 : +0.0012 |
| M3 | M6_ridge | Brier P(T = 0) | +0.00015 | [-0.00003 ; +0.00033] | 3 sur 4 | 0.1068 | 2021 : +0.0002 ; 2022 : -0.0002 ; 2023 : +0.0002 ; 2024 : +0.0004 |
| M3 | M6_ridge | Brier P(T = 1) | +0.00085 | [+0.00043 ; +0.00128] | 4 sur 4 | 0.0001 | 2021 : +0.0007 ; 2022 : +0.0009 ; 2023 : +0.0013 ; 2024 : +0.0006 |
| M3 | M6_ridge | Brier P(T = 2) | +0.00030 | [+0.00000 ; +0.00060] | 3 sur 4 | 0.0559 | 2021 : +0.0001 ; 2022 : +0.0005 ; 2023 : +0.0006 ; 2024 : -0.0000 |
| | | règle de décision | (i) oui, (ii) oui, (iii) oui | **M6_ridge remplace M3** | | | |
| M3_G0G3 | M6_ridge | log-loss du total | +0.00019 | [-0.00044 ; +0.00080] | 3 sur 4 | 0.5501 | 2021 : +0.0008 ; 2022 : -0.0010 ; 2023 : +0.0000 ; 2024 : +0.0010 |
| M3_G0G3 | M6_ridge | RPS | +0.00003 | [-0.00006 ; +0.00013] | 3 sur 4 | 0.4867 | 2021 : +0.0001 ; 2022 : -0.0002 ; 2023 : +0.0000 ; 2024 : +0.0002 |
| M3_G0G3 | M6_ridge | Brier P(T = 0) | +0.00000 | [-0.00003 ; +0.00003] | 2 sur 4 | 0.9667 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : -0.0000 |
| M3_G0G3 | M6_ridge | Brier P(T = 1) | +0.00002 | [-0.00007 ; +0.00010] | 3 sur 4 | 0.6775 | 2021 : +0.0001 ; 2022 : -0.0001 ; 2023 : +0.0000 ; 2024 : +0.0001 |
| M3_G0G3 | M6_ridge | Brier P(T = 2) | +0.00001 | [-0.00005 ; +0.00006] | 3 sur 4 | 0.7779 | 2021 : +0.0000 ; 2022 : -0.0000 ; 2023 : +0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) oui, (iii) oui | **M6_ridge ne remplace pas M3_G0G3** | | | |
| M3_G0G3 | M6_en | log-loss du total | +0.00014 | [-0.00011 ; +0.00040] | 2 sur 4 | 0.2812 | 2021 : -0.0000 ; 2022 : -0.0005 ; 2023 : +0.0011 ; 2024 : +0.0000 |
| M3_G0G3 | M6_en | RPS | +0.00002 | [-0.00002 ; +0.00006] | 2 sur 4 | 0.3115 | 2021 : -0.0000 ; 2022 : -0.0001 ; 2023 : +0.0002 ; 2024 : +0.0000 |
| M3_G0G3 | M6_en | Brier P(T = 0) | +0.00002 | [+0.00000 ; +0.00003] | 2 sur 4 | 0.0106 | 2021 : -0.0000 ; 2022 : +0.0000 ; 2023 : +0.0000 ; 2024 : -0.0000 |
| M3_G0G3 | M6_en | Brier P(T = 1) | +0.00002 | [-0.00002 ; +0.00005] | 3 sur 4 | 0.2801 | 2021 : +0.0000 ; 2022 : -0.0001 ; 2023 : +0.0001 ; 2024 : +0.0000 |
| M3_G0G3 | M6_en | Brier P(T = 2) | -0.00002 | [-0.00004 ; +0.00001] | 1 sur 4 | 0.1890 | 2021 : -0.0000 ; 2022 : -0.0000 ; 2023 : -0.0000 ; 2024 : +0.0000 |
| | | règle de décision | (i) non, (ii) non, (iii) oui | **M6_en ne remplace pas M3_G0G3** | | | |
| M3 | M3_G0G3 | log-loss du total | +0.00907 | [+0.00558 ; +0.01256] | 4 sur 4 | 0.0000 | 2021 : +0.0072 ; 2022 : +0.0068 ; 2023 : +0.0150 ; 2024 : +0.0074 |
| M3 | M3_G0G3 | RPS | +0.00135 | [+0.00084 ; +0.00186] | 4 sur 4 | 0.0000 | 2021 : +0.0011 ; 2022 : +0.0011 ; 2023 : +0.0022 ; 2024 : +0.0010 |
| M3 | M3_G0G3 | Brier P(T = 0) | +0.00015 | [-0.00005 ; +0.00034] | 3 sur 4 | 0.1463 | 2021 : +0.0003 ; 2022 : -0.0002 ; 2023 : +0.0002 ; 2024 : +0.0004 |
| M3 | M3_G0G3 | Brier P(T = 1) | +0.00084 | [+0.00036 ; +0.00131] | 4 sur 4 | 0.0005 | 2021 : +0.0005 ; 2022 : +0.0010 ; 2023 : +0.0013 ; 2024 : +0.0005 |
| M3 | M3_G0G3 | Brier P(T = 2) | +0.00029 | [-0.00003 ; +0.00061] | 3 sur 4 | 0.0821 | 2021 : +0.0001 ; 2022 : +0.0005 ; 2023 : +0.0006 ; 2024 : -0.0001 |
| | | règle de décision | (i) oui, (ii) oui, (iii) oui | **M3_G0G3 remplace M3** | | | |

### Ce que M6 enseigne

- **Les variables G2 et G3 apportent beaucoup** : M3 sur G0 à G3 bat M3 sur G0 + G1 de +0,0091 [+0,0056 ; +0,0126], 4 plis sur 4, autant que tout le chemin de B1 à M3. Le détail (G2 d'abord, puis G3) est l'objet des ablations du lot 3.
- **La régularisation n'apporte rien de plus** : ridge contre Poisson non régularisé, mêmes variables : +0,0002 [−0,0004 ; +0,0008] ; élastique net : +0,0001 [−0,0001 ; +0,0004]. Avec environ 33 000 lignes pour une trentaine de coefficients, l'estimation est déjà stable : il y a peu de surapprentissage à corriger. Par la règle, **M6 ne remplace pas M3** ; M6 bat bien M3 (G0 + G1), mais par ses variables, pas par sa pénalité.
- **α au bord de la grille** : le ridge retient α = 0,1, la plus forte valeur de la grille, dans 3 plis sur 4. La grille n'est pas étendue après coup (pas d'essais supplémentaires) : le gain de la régularisation est nul de toute façon. Effet secondaire : la pénalité frappe aussi les indicatrices non standardisées (domicile, championnat), et le coefficient du domicile tombe de 0,25 à 0,18 à log-loss égal.
- **Élastique net** : un seul coefficient sur 23 annulé (2024-25) ; aucune variable n'est franchement inutile une fois toutes présentes, mais leurs coefficients se partagent l'information (buts et `xg_proxy` corrélés) et ne s'interprètent pas un par un.
- **Demi-vie** : 240 jours retenus dans 3 plis sur 4 (120 jours en 2022-23), pour M3 comme pour M6 : la mémoire longue l'emporte.
- **Splines** : non justifiées. Diagnostic sur 2015-16 à 2020-21 (jamais une saison de test), buts observés contre attendus de M3 par décile de l'écart d'Elo :

| Décile de l'écart d'Elo | Lignes | Écart d'Elo moyen | Buts observés | Buts attendus (M3) | O/E | z |
|---|---|---|---|---|---|---|
| 1 | 2171 | -320 | 1770 | 1753.1 | 1.010 | +0.40 |
| 2 | 2171 | -181 | 2207 | 2145.5 | 1.029 | +1.33 |
| 3 | 2171 | -111 | 2288 | 2359.4 | 0.970 | -1.47 |
| 4 | 2171 | -61 | 2547 | 2559.2 | 0.995 | -0.24 |
| 5 | 2171 | -20 | 2676 | 2715.6 | 0.985 | -0.76 |
| 6 | 2171 | +20 | 2967 | 2906.1 | 1.021 | +1.13 |
| 7 | 2171 | +61 | 3064 | 3118.3 | 0.983 | -0.97 |
| 8 | 2171 | +111 | 3363 | 3418.1 | 0.984 | -0.94 |
| 9 | 2171 | +181 | 3990 | 3901.3 | 1.023 | +1.42 |
| 10 | 2171 | +320 | 5074 | 5069.3 | 1.001 | +0.07 |

Σ z² = 9.86, 9 degrés de liberté, p = 0.362.

  Rapports O/E entre 0,97 et 1,03, sans forme (ni courbure aux extrémités) : la relation log-linéaire à l'Elo suffit.
