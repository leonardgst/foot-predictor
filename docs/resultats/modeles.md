# Modèles M1 à M6 (jalon J6, lot 2)

*Partie 4, lot 2. Protocole figé par l'ADR-0037 (tag `protocole-v1`). Jeu `ds-2026-09-30-ba2b91f7`, 4 plis (2021-22 à 2024-25), matchs de championnat du top 5. Structures comparées avec les variables **G0 + G1** (décision 5). Chaque section donne le concept, les hypothèses, ce que le modèle apporte et ce qu'il rate ; les tableaux sont générés depuis les rapports (`modeling summary`). Équations : chapitre « Modèles » de `docs/latex/mathematiques/`.*

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
