# ADR-0049 — Structures du modèle H2 (M6 ridge, M7 boosting) : spécification et chemin de décision fixés avant toute mesure

- **Statut** : acceptée
- **Date** : 2026-11-01
- **Référence** : ADR-0037 (tag `protocole-v1`), ADR-0038 (critère de révision), ADR-0039, ADR-0047 (D4), ADR-0048 ; rapport de cadrage, I.4, I.7 ; cadrage de la partie 6, sections 6 (point 7) et 9 (D4) ; `docs/resultats/h2_ablations.md`

## Contexte

La sous-étape 6.7 a retenu, par la règle de l'ADR-0037 suivie dans l'ordre G6, G5, G4, le modèle H2 **M3 sur G0 + G1 + G2 + G5** (jeu `ds-2026-11-01-e0defb32`). L'ADR-0047 (D4) prévoit alors deux comparaisons de structure, une chacune : M3 contre M6 (Poisson ridge), puis la structure retenue contre M7 (boosting à perte de Poisson). L'ADR-0038 avait prévu de refaire la comparaison de la régularisation si de nouvelles variables H2 rendaient le nombre de coefficients bien plus grand : G5 en ajoute six (trois pour l'équipe, trois pour l'adversaire) à une vingtaine de coefficients, ce qui ne change guère l'ordre de grandeur.

**Ce qui a déjà été vu à la date de cette ADR** (la règle du protocole veut qu'on le dise) :

- **Les résultats de 6.7** : G5 retenu de justesse (+0,00078 [+0,00003 ; +0,00151]), G4 et G6 non retenus, aucun modèle H2 plus gros que G0 + G1 + G2 + G5 n'est en jeu ici.
- **M6 sur les variables H1** (ADR-0038) : M3 − M6 ridge, +0,0002 [−0,0004 ; +0,0008] sur G0 à G3, M6 ne remplace pas M3. Rien de M6 n'a été mesuré avec G5.
- **M7 n'a jamais été évalué** sur un pli, avec ou sans variable H2. Il n'a été vu que sur données synthétiques (tests de `tests/modeling/test_boosting.py`, qui contrôlent la structure, pas une performance), et pour sa **durée d'ajustement** sur le vrai jeu (0,2 à 0,6 s pour 25 000 lignes, selon la grille) : aucune métrique de modèle.

## Options envisagées

1. **Choisir les hyperparamètres de M7 et le chemin de comparaison au fil des résultats.** Rejetée : c'est ce que le protocole interdit, et un boosting a assez de réglages pour toujours trouver quelque chose.
2. **Fixer ici les variables, les grilles, le chemin de décision et ce que l'on publie.** Retenue.

## Décision

### Ce qui change, et ce qui ne change pas

Seule la **structure** change. Les trois modèles lisent les mêmes variables, **G0 + G1 + G2 + G5**, sur le même jeu, la même population (top 5), les mêmes plis, le même rodage de G5 (apprentissage à partir de 2016-17, lignes écartées comptées) et la même matrice (`Design`, standardisée dans le pli). Le protocole est celui de l'ADR-0037, sans exception : 4 plis, 10 000 rééchantillonnages, graine 20260930, règle de décision à trois conditions, intersection des matchs, aucun remplissage.

### Structures et hyperparamètres

Chaque hyperparamètre se choisit par la **validation interne** du pli (ADR-0037 : apprentissage 2015-16 à s − 2, rodage compris, mesure sur s − 1, critère : log-loss du total du top 5), **ensemble** avec la demi-vie de G2. La saison de test n'est jamais lue pour choisir.

| Modèle | Structure | Grille (chaque combinaison est un candidat) | Fixé |
|---|---|---|---|
| `M3_H2` | M3, Poisson par équipe, maximum de vraisemblance | demi-vie ∈ {60, 120, 240} : **3** candidats | |
| `M6_H2` | M6, Poisson ridge (`PoissonRegressor`) | demi-vie ∈ {60, 120, 240} × α ∈ {10⁻⁴, 10⁻³, 10⁻², 10⁻¹} : **12** | pénalité L2, constante non pénalisée |
| `M7_H2` | M7, `HistGradientBoostingRegressor(loss="poisson")` | demi-vie ∈ {60, 120, 240} × profondeur ∈ {2, 3, 4} × itérations ∈ {100, 200, 400} : **27** | pas d'apprentissage 0,05 ; au moins 200 lignes par feuille ; L2 de 1,0 ; pas d'arrêt précoce |

- La grille de M6 est celle du ridge de la partie 4 (`experiments/m6.yaml`). L'élastique net n'est pas rejoué : l'ADR-0038 ne lui avait trouvé aucun gain et D4 ne parle que du ridge.
- M7 : arbres peu profonds, grandes feuilles et pas d'apprentissage faible, parce que le signal est ténu (log-loss d'environ 1,88, gains de l'ordre de 10⁻³) et que les buts sont très bruités. L'**arrêt précoce est coupé** : celui de scikit-learn tire un échantillon de validation au hasard dans l'apprentissage, sans respecter le temps ; le nombre d'itérations est choisi par la validation interne du protocole.
- **Bord de grille** : si le meilleur candidat d'un hyperparamètre est à l'extrémité de sa grille dans trois plis ou plus, on le **publie**, sans étendre la grille après coup (elle serait choisie en ayant vu les plis de test). Une extension passerait par une nouvelle ADR qui dit ce qui avait déjà été évalué.

### Chemin de décision

À gain non significatif, on garde le plus simple. Ordre de complexité : **M3 < M6 < M7** (l'ADR-0037 plaçait M6 en dernier ; M7 s'y ajoute).

1. **Étape 1** : `M3_H2` → `M6_H2`. La règle de l'ADR-0037 décide : M6 remplace M3 si et seulement si (i), (ii) et (iii) sont vraies.
2. **Étape 2** : la structure retenue après l'étape 1 → `M7_H2`. Si M3 est resté, la comparaison est `M3_H2` → `M7_H2` ; si M6 l'a remplacé, c'est `M6_H2` → `M7_H2`. Les deux sont écrites dans le fichier, parce que la suite dépend de l'issue de l'étape 1 ; le chemin suivi est celui que la règle dicte, et lui seul décide.

**La structure du modèle H2 retenu est celle où le chemin s'arrête.** Si aucune des deux comparaisons ne retient la structure plus complexe, le modèle H2 reste **M3 sur G0 + G1 + G2 + G5**, et ce résultat nul est publié.

### Diagnostics publiés, sans pouvoir de décision

- **G5 sous chaque structure** : `M6_sans_G5` → `M6_H2` et `M7_sans_G5` → `M7_H2`, les modèles « sans G5 » étant appris sur la **même fenêtre** (dès 2016-17, paramètre `train_from`), pour séparer l'apport de G5 de l'effet de la fenêtre. C'est la limite que `h2_ablations.md` laissait ouverte : une régularisation ou un boosting pourraient changer le jugement sur G5, qui recoupe l'Elo (corrélation de 0,83).
- Ceux de 6.7 : écart par pli et poolé, plis gagnés, calibration poolée, **écart par tranche de journées**, lignes exclues et matchs écartés par l'intersection, **hyperparamètres retenus par pli** (profondeur et nombre d'itérations de M7, α de M6).
- Les cinq modèles sont dans la même expérience : l'intersection des matchs est celle des modèles à variables G5 (les modèles « sans G5 » prédisent un peu plus de matchs, qui sont écartés), donc les comparaisons de décision portent sur les mêmes matchs que dans 6.7.

### Attendu, dit d'avance

Je n'attends pas de gain. M6 n'a rien apporté sur G0 à G3 (ADR-0038) et le modèle linéaire est déjà bien calibré (pente de 0,97 dans 6.7). Pour M7, le diagnostic de non-linéarité de la partie 4 n'a rien trouvé : buts observés contre attendus de M3 par décile de l'écart d'Elo, Σz² = 9,86 pour 9 degrés de liberté, p = 0,36 (`docs/resultats/modeles.md`). Un boosting sur environ 25 000 lignes et une trentaine de variables corrélées, avec un signal aussi petit, a plutôt tendance à surapprendre. **Un résultat nul est un résultat** : on garde M3, et on le publie avec les intervalles.

## Conséquences

- **Code** : nouveau `modeling/models/boosting.py` (M7, dans `MODELS` sous le nom `m7`) ; M6 gagne le rodage des groupes H2 (`first_training_season`) et `train_from`, M7 aussi. Aucun de ces ajouts ne change un modèle H1 : la description et les paramètres d'un M6 sur G0 à G3 sont identiques (testé), et le rejeu et les prédictions du modèle final H1 sont reproduits (garde H1, ADR-0044). Aucune nouvelle dépendance : scikit-learn est déjà un groupe du projet.
- **Expériences** : `experiments/structures_h2_mesure_duree.yaml` (200 rééchantillonnages, mesure de durée, ne décide rien, un essai de plus dans l'index) puis `experiments/structures_h2.yaml` (10 000 rééchantillonnages, la décision). Cinq comparaisons : trois de décision (deux sur le chemin), deux de diagnostic. Le nombre d'essais est celui de l'index.
- **Mesure de durée vue avant le lancement de référence** : seuls les intervalles diffèrent des estimations ponctuelles (qui sont identiques) ; la règle s'applique aux 10 000 rééchantillonnages, comme en 6.7. Les prédictions des deux lancements sont comparées.
- **Si M7 était retenu**, la sous-étape 6.9 devrait vérifier que la sérialisation d'un modèle de rejeu et la carte de modèle savent décrire un boosting ; ce n'est pas fait ici.
- **Gel** : à `pre-scelle-h2` (6.9), ces fichiers et ceux de `modeling/` et `features/` ne bougent plus jusqu'au test scellé.
- **Hors périmètre** : élastique net, M8, réglages de M7 autres que ceux de la grille.
- **Critère de révision** : si le chemin de décision ne tient pas dans les comparaisons écrites, ou si un candidat de M7 échoue à converger ou produit un λ non fini, une nouvelle ADR dit ce qui avait déjà été évalué.

---

*Règle : une ADR acceptée ne se réécrit pas. Si la décision change, on crée une nouvelle ADR qui la remplace, et on met à jour le statut de l'ancienne.*
