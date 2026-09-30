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
