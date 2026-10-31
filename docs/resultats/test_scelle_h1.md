# Test scellé du MVP, horizon H1 (jalon J6)

*Sous-étape 4.16, 2026-10-22. Liste figée : `experiments/scelle_h1.yaml`, tag `pre-scelle-h1` (ADR-0039). Règle : un seul test, résultat publié tel quel (ADR-0012, règle 5). Deux lancements : le premier en échec technique sans aucun résultat (E-059), puis la relance unique décidée par l'ADR-0043, dont le résultat **est** le résultat du test. Journal des usages du scellé : `reports/sealed_tests.md` (6 lignes).*

## Résultat : le modèle retenu bat B1 sur les matchs scellés

| Élément | Valeur |
|---|---|
| Rapport | `reports/experiments/scelle-h1-20261022T120542.json`, statut `ok` |
| Lancement | `uv run python -m foot_predictor.sealed_rerun`, 2026-10-22 12:05 UTC, commit `7d4f453` (arbre propre), 50 s |
| Jeu | `ds-2026-10-22-94969da0` (le même qu'au premier lancement, aucun nouveau `build`) |
| Prédictions | sha256 `14b103d3292cef4b3055034b8aea88a368f0b37b99fd77e66c9c1f2cdd560e44`, **identique** à celui du premier lancement : la relance a refait exactement le même calcul |
| Valeurs écrites sous forme de texte | aucune (seules les dates passent par le nouvel encodeur) |
| Apprentissage | 2015-16 à 2024-25 : 35 996 lignes (17 998 matchs), 26 lignes exclues pour valeur manquante ; demi-vie 240 jours et fenêtre de B1 de 3 saisons, choisies par validation interne sur 2024-25 |
| Test | matchs de championnat du top 5 joués depuis le 1er juillet 2025 (2025-26 et 2026-27 jusqu'au 2026-10-18) : 2 092 matchs, tous prédits par les trois modèles ; 2 001 avec une cote |

Lecture selon les critères fixés **avant** le test :

- **Critère du test scellé** (ADR-0039, critère de révision : « le modèle retenu ne bat pas B1 » si l'intervalle contient 0 ou est négatif). Écart de log-loss du total B1 − M3_G0G2 : **+0,0189 [+0,0102 ; +0,0282]**, sur 2 092 matchs. L'intervalle exclut 0 : **le modèle retenu bat B1.** En validation glissante, l'écart était de +0,0179 [+0,0133 ; +0,0226] sur 7 156 matchs (ADR-0039). Le gain se maintient sur des matchs jamais vus ; l'intervalle est plus large parce que les matchs sont trois fois et demie moins nombreux.
- **Couverture de [q10 ; q90]** (objectif du MVP, ADR-0037 : à ±3 points de la couverture annoncée) : observée 87,3 %, annoncée 87,5 %, soit 0,2 point d'écart. **Rempli.**
- **Calibration de P(T > 2,5)** (diagnostic, non bloquant) : écart absolu moyen par décile de 2,5 points (B1 : 2,9 ; B0 : 4,4), pente 1,00 (en validation : 0,95). Le détail par décile est dans le rapport.
- **Autres métriques** : M3_G0G2 bat B1 en RPS (+0,00243 [+0,00119 ; +0,00373]) et en Brier de P(T > 2,5) (+0,00406 [+0,00086 ; +0,00723]). Il bat B0 sur les trois métriques principales.
- **Marché** (référence, ADR-0036), Brier de l'événement plus/moins 2,5 sur les 2 001 matchs avec une cote : modèle 0,2418, marché avant clôture 0,2397, marché à la clôture 0,2383. Le marché avant clôture reste meilleur que le modèle : M3_G0G2 − marché avant clôture = +0,00204 [+0,00037 ; +0,00367]. Le modèle comble environ les deux tiers de l'écart qui sépare B1 (0,2458) du marché avant clôture.

**À lire avec les tableaux : la ligne « règle de décision ».** Les tableaux générés écrivent « (i) oui, (ii) non, (iii) oui | **M3_G0G2 ne remplace pas B1** », et de même pour B0. Ces lignes sont publiées telles quelles, mais elles ne disent pas que le modèle perd :

- elles viennent du code figé, qui applique à chaque comparaison du fichier la **règle de sélection** de l'ADR-0037 ;
- son critère (ii) demande un gain positif dans au moins 3 plis sur 4 (`MIN_POSITIVE_FOLDS = 3`). Le test scellé n'a qu'un pli : (ii) est donc faux par construction, même quand ce pli unique est gagné (« 1 sur 1 ») ;
- cette règle sert à choisir entre modèles en validation glissante. Le test scellé ne choisit rien : aucun modèle n'est modifié ensuite. Son critère de lecture est celui de l'ADR-0039, cité plus haut ;
- ce défaut d'affichage n'avait pas été repéré avant le test (E-060). Il est signalé ici, sans correction : le code est figé. Il est à corriger pour le test de H2 (voir « Limites »).

## Tableaux (générés)

Sortie de `uv run python -m foot_predictor.modeling summary reports/experiments/scelle-h1-20261022T120542.json`, sans retouche. L'intitulé « sur les 4 plis » des petits totaux est générique : ici, il s'agit du pli scellé unique.

Rapport `scelle-h1-20261022T120542` : jeu `ds-2026-10-22-94969da0`, commit `7d4f453`, graine 20260930, 10000 rééchantillonnages.

| Pli | Matchs d'évaluation | Intersection | Écartés | Avec cote | Hyperparamètres retenus |
|---|---|---|---|---|---|
| scellé depuis 2025-26 | 2092 | 2092 | 0 | 2001 | M3_G0G2 : {'groups': ['G0', 'G1', 'G2'], 'half_life': 240}; B1 : {'window': 3} |

| Modèle | Pli | Log-loss | RPS | Brier P(T > 2,5) | Calibration : écart moyen | Pente | Couverture observée | Couverture annoncée | Log-loss score exact | Brier 1N2 | MAE E[T] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M3_G0G2 | scellé depuis 2025-26 | 1.8805 | 0.1281 | 0.2414 | 0.0254 | 1.00 | 87.3 % | 87.5 % | 2.9090 | 0.5879 | 1.312 |
| B0 | scellé depuis 2025-26 | 1.9063 | 0.1316 | 0.2484 | 0.0443 | n. d. | 87.1 % | 87.4 % | 3.0528 | 0.6567 | 1.344 |
| B1 | scellé depuis 2025-26 | 1.8994 | 0.1305 | 0.2457 | 0.0286 | 0.93 | 88.3 % | 88.0 % | 3.0275 | 0.6474 | 1.332 |

| Modèle | Matchs | Log-loss | RPS | Brier P(T > 2,5) | Calibration poolée : écart moyen | Pente | Ordonnée |
|---|---|---|---|---|---|---|---|
| M3_G0G2 | 2092 | 1.8805 | 0.1281 | 0.2414 | 0.0254 | 1.00 | +0.066 |
| B0 | 2092 | 1.9063 | 0.1316 | 0.2484 | 0.0443 | n. d. | +0.064 |
| B1 | 2092 | 1.8994 | 0.1305 | 0.2457 | 0.0286 | 0.93 | +0.044 |

Petits totaux, calibration poolée sur les 4 plis :

| Modèle | k | P(T = k) prédite | observée | Brier | Écart moyen par décile | Pente |
|---|---|---|---|---|---|---|
| M3_G0G2 | 0 | 6.5 % | 6.5 % | 0.0600 | 0.0082 | 0.97 |
| M3_G0G2 | 1 | 17.3 % | 16.6 % | 0.1373 | 0.0225 | 0.86 |
| M3_G0G2 | 2 | 23.6 % | 22.7 % | 0.1745 | 0.0272 | 1.41 |
| B0 | 0 | 6.2 % | 6.5 % | 0.0604 | 0.0215 | n. d. |
| B0 | 1 | 17.2 % | 16.6 % | 0.1384 | 0.0263 | n. d. |
| B0 | 2 | 23.9 % | 22.7 % | 0.1757 | 0.0302 | n. d. |
| B1 | 0 | 6.1 % | 6.5 % | 0.0605 | 0.0139 | 0.31 |
| B1 | 1 | 16.9 % | 16.6 % | 0.1378 | 0.0206 | 0.96 |
| B1 | 2 | 23.6 % | 22.7 % | 0.1751 | 0.0245 | 1.44 |

Événement plus/moins 2,5, sur les matchs de l'intersection qui ont une cote :

| Modèle | Pli | Matchs | Brier | Log-loss binaire | Calibration : écart moyen |
|---|---|---|---|---|---|
| M3_G0G2 | scellé depuis 2025-26 | 2001 | 0.2418 | 0.6761 | 0.0262 |
| M3_G0G2 | **poolé** | | **0.2418** | | |
| B0 | scellé depuis 2025-26 | 2001 | 0.2487 | 0.6905 | 0.0472 |
| B0 | **poolé** | | **0.2487** | | |
| B1 | scellé depuis 2025-26 | 2001 | 0.2458 | 0.6847 | 0.0254 |
| B1 | **poolé** | | **0.2458** | | |
| marche_avant_cloture | scellé depuis 2025-26 | 2001 | 0.2397 | 0.6720 | 0.0346 |
| marche_avant_cloture | **poolé** | | **0.2397** | | |
| marche_cloture | scellé depuis 2025-26 | 2001 | 0.2383 | 0.6691 | 0.0346 |
| marche_cloture | **poolé** | | **0.2383** | | |

Écarts appariés A − B (positif : B meilleur), intervalle à 95 % par bootstrap par blocs :

| A | B | Métrique | Écart poolé | IC 95 % | Plis où B gagne | DM (p) | Par pli |
|---|---|---|---|---|---|---|---|
| B1 | M3_G0G2 | log-loss du total | +0.01893 | [+0.01022 ; +0.02825] | 1 sur 1 | 0.0000 | 2025 : +0.0189 |
| B1 | M3_G0G2 | RPS | +0.00243 | [+0.00119 ; +0.00373] | 1 sur 1 | 0.0002 | 2025 : +0.0024 |
| B1 | M3_G0G2 | Brier plus/moins 2,5 | +0.00406 | [+0.00086 ; +0.00723] | 1 sur 1 | 0.0127 | 2025 : +0.0041 |
| B1 | M3_G0G2 | Brier P(T = 0) | +0.00050 | [+0.00012 ; +0.00092] | 1 sur 1 | 0.0138 | 2025 : +0.0005 |
| B1 | M3_G0G2 | Brier P(T = 1) | +0.00049 | [-0.00063 ; +0.00161] | 1 sur 1 | 0.3952 | 2025 : +0.0005 |
| B1 | M3_G0G2 | Brier P(T = 2) | +0.00059 | [-0.00016 ; +0.00132] | 1 sur 1 | 0.1165 | 2025 : +0.0006 |
| | | règle de décision | (i) oui, (ii) non, (iii) oui | **M3_G0G2 ne remplace pas B1** | | | |
| B0 | M3_G0G2 | log-loss du total | +0.02584 | [+0.01540 ; +0.03633] | 1 sur 1 | 0.0000 | 2025 : +0.0258 |
| B0 | M3_G0G2 | RPS | +0.00352 | [+0.00203 ; +0.00503] | 1 sur 1 | 0.0000 | 2025 : +0.0035 |
| B0 | M3_G0G2 | Brier plus/moins 2,5 | +0.00694 | [+0.00309 ; +0.01079] | 1 sur 1 | 0.0003 | 2025 : +0.0069 |
| B0 | M3_G0G2 | Brier P(T = 0) | +0.00042 | [-0.00007 ; +0.00095] | 1 sur 1 | 0.1047 | 2025 : +0.0004 |
| B0 | M3_G0G2 | Brier P(T = 1) | +0.00106 | [-0.00026 ; +0.00236] | 1 sur 1 | 0.1177 | 2025 : +0.0011 |
| B0 | M3_G0G2 | Brier P(T = 2) | +0.00113 | [+0.00032 ; +0.00194] | 1 sur 1 | 0.0061 | 2025 : +0.0011 |
| | | règle de décision | (i) oui, (ii) non, (iii) oui | **M3_G0G2 ne remplace pas B0** | | | |
| M3_G0G2 | marche_avant_cloture | Brier plus/moins 2,5 | +0.00204 | [+0.00037 ; +0.00367] | 1 sur 1 | 0.0162 | 2025 : +0.0020 |
| marche_avant_cloture | marche_cloture | Brier plus/moins 2,5 | +0.00138 | [+0.00011 ; +0.00271] | 1 sur 1 | 0.0333 | 2025 : +0.0014 |

## Comptage des essais

- **Test scellé H1 : deux lancements**, un échec technique sans résultat puis la relance (ADR-0043). Aucun troisième lancement n'est possible : le journal contient désormais « évaluation terminée », et `evaluate --sealed-test` comme le lanceur refusent un second test.
- `reports/experiments/INDEX.md` : **10 essais**, 0 en échec. Il ne compte que la relance, puisque le premier lancement n'a laissé aucun rapport.

## Premier lancement : échec technique, aucun résultat (2026-10-22)

| Étape | Date (UTC) | Commit | Issue |
|---|---|---|---|
| `features build --sealed-test --experiment experiments/scelle_h1.yaml` | 2026-10-22 08:02 | `9724829` | jeu `ds-2026-10-22-94969da0` : 205 216 lignes, dont 9 118 scellées (2025-26 et 2026-27 jusqu'au 2026-10-18) |
| `evaluate experiments/scelle_h1.yaml --sealed-test --dataset ds-2026-10-22-94969da0` | 2026-10-22 08:03 | `70f9766` | **échec** au bout de 8 s : `TypeError: <class 'datetime.date'>` à l'écriture du rapport |

- **Cause** (E-059) : la clé descriptive `test_from: 2025-07-01` du fichier d'expérience est lue comme une date par YAML. Le rapport recopie le fichier, et son encodeur JSON n'accepte pas les dates.
- **Ce qui existait** : un fichier de prédictions par match, écrit avant le plantage, **jamais ouvert** (`data/experiments/scelle-h1-20261022T080319/predictions.parquet`, hors Git ; sha256 `14b103d3…cdd560e44`, relevé avant toute décision), et les lignes de lecture du journal.
- **Ce qui n'existait pas** : aucun rapport, aucune métrique, aucun chiffre affiché. Personne n'avait vu de résultat du test scellé avant la relance.
- **Suite** : non relancé sur le moment (consigne : erreur technique, on écrit et on s'arrête). Décision de l'utilisateur : **ADR-0043**, une relance unique, code figé inchangé, contrôlée par le sha256 des prédictions du premier lancement. Les règles de lecture de son résultat ont été fixées dans l'ADR, avant la relance. Les deux fichiers de prédictions ont le même sha256 : leur contenu n'a pas eu besoin d'être comparé.

## Limites

- **Un seul pli, une saison et demie** : 2 092 matchs, contre 7 156 en validation glissante. L'intervalle est donc plus large. Le résultat vaut pour cette période et ces cinq championnats.
- **Ligne « règle de décision »** : non applicable à un pli unique (voir plus haut). Pour le test de H2 : soit le fichier du test ne demande pas cette règle, soit le code écrit « non applicable » quand le nombre de plis est inférieur au seuil. Même chose pour l'intitulé « sur les 4 plis » des petits totaux. *Ajout du 2026-10-31 : corrigé dans le code (E-060). Régénérés, ces tableaux écriraient « non applicable : 1 pli » et « calibration poolée sur le pli unique » ; ils restent ici tels que publiés le 2026-10-22.*
- **Marché** : évalué sur l'événement plus/moins 2,5 seulement, sur 2 001 matchs ; 91 matchs sans cote en sont exclus.
- **Après ce test** : aucun modèle H1 n'est modifié (ADR-0012, règle 5). La sous-étape 4.17 réentraîne le modèle retenu avec les matchs scellés (ADR-0039), sans changer sa structure ni ses variables.
