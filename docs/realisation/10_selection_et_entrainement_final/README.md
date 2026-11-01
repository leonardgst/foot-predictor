# Étape 10 : sélection du modèle H1, test scellé et entraînement final (jalon J6)

Mode d'emploi de la sélection du modèle MVP, du test scellé (phase B) et de l'entraînement final. Décisions : ADR-0037 (règle de décision), ADR-0038 (structure), **ADR-0039 (modèle MVP H1, liste du test scellé)**. Résultats : [`docs/resultats/ablations.md`](../../resultats/ablations.md).

## En bref

- **Modèle MVP H1** : M3 (Poisson par équipe) sur G0 + G1 + G2, demi-vie choisie par validation interne, appris sur le top 5 ; même modèle en rejeu et en live (G3 non retenu).
- **Liste figée** : `experiments/scelle_h1.yaml` (modèle retenu, B0, B1, marché avant clôture, marché à la clôture).
- **Tag `pre-scelle-h1`** : posé sur la fusion de la sous-étape 4.14, après l'écriture du code du test scellé ; ensuite, plus aucun changement sous `src/foot_predictor/modeling/`, `src/foot_predictor/features/`, `experiments/` avant le test.
- **Test scellé** : une seule fois, en phase B, après le gel ; résultat publié tel quel.
- **Modèle final H1** (4.17, ADR-0044) : `scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle`, appris avec les matchs scellés, jusqu'au 2026-10-18 ; jalon J6, tag `v0.5.0`.
- **Modèle H2 et test scellé H2** (partie 6, sous-étape 6.9, **ADR-0050**) : M3 sur G0 + G1 + G2 + G5. Liste figée `experiments/scelle_h2.yaml` ; le tag `pre-scelle-h2` gèle aussi `seal.py`. Voir la section [Test scellé H2](#test-scellé-h2-liste-figée-69).

## Commandes

Entraînement final sur les données de développement (permis à tout moment ; fait le 2026-09-30) :

```bash
uv run python -m foot_predictor.modeling train --final experiments/scelle_h1.yaml --model M3_G0G2 \
    --dataset ds-2026-09-30-ba2b91f7 \
    --validation-report reports/experiments/ablations-20260930T110352.json --validation-model A2_G0G2
```

Phase B seulement (préconditions dans `ETAT_PROJET.md` : gel fait, `v0.3.0`, `v0.4.0`, verrou libre, `git diff pre-scelle-h1..HEAD -- src/foot_predictor/modeling src/foot_predictor/features experiments` vide) :

```bash
uv run python -m foot_predictor.features build --sealed-test --experiment experiments/scelle_h1.yaml   # 4.16, 1 ligne au journal
uv run python -m foot_predictor.modeling evaluate experiments/scelle_h1.yaml --sealed-test --dataset <version scellée>   # 4.16, UNE fois
uv run python -m foot_predictor.modeling train --final experiments/scelle_h1.yaml --model M3_G0G2 \
    --include-sealed --dataset <version scellée>                                                        # 4.17, après le test
```

**4.16, 2026-10-22** : `build --sealed-test` fait (`ds-2026-10-22-94969da0`) ; premier `evaluate --sealed-test` en **échec technique** à l'écriture du rapport, sans aucun résultat produit (E-059, [`docs/resultats/test_scelle_h1.md`](../../resultats/test_scelle_h1.md)). Ces deux commandes ne se relancent plus pour H1. Suite décidée par l'**ADR-0043** : une relance unique, code figé inchangé, contrôlée par le sha256 des prédictions du premier lancement :

```bash
uv run python -m foot_predictor.sealed_rerun   # une seule fois, depuis main, arbre propre ; refuse sinon
uv run python -m foot_predictor.modeling summary reports/experiments/<id de la relance>.json --output <fichier>
```

| Le lanceur refuse si… | Pourquoi |
|---|---|
| les garde-fous de `evaluate --sealed-test` refusent | tag, chemins figés, évaluation déjà terminée |
| des modifications suivies sont en attente | le rapport doit nommer un commit exact |
| le journal n'a pas exactement les 3 lignes du premier lancement | une seule relance, même en cas de nouvel échec |
| les prédictions du premier lancement manquent ou ont changé | elles servent au contrôle par sha256 |

**Relance faite le 2026-10-22 à 12:05 UTC** (commit `7d4f453`) : rapport `scelle-h1-20261022T120542`, statut `ok`, sha256 des prédictions identique à celui du premier lancement. **Le modèle retenu bat B1 sur les matchs scellés** : +0,0189 [+0,0102 ; +0,0282] de log-loss du total, sur 2 092 matchs. Résultat complet, lecture et limites (dont E-060, ligne « règle de décision » non applicable à un pli unique) : [`docs/resultats/test_scelle_h1.md`](../../resultats/test_scelle_h1.md). Le journal contient « évaluation terminée » : aucun autre test scellé H1 n'est possible, et `train --final --include-sealed` (4.17) est désormais permis.

### Résultats de 4.17 : entraînement final avec les matchs scellés (2026-10-22)

Commande, lancée une fois à 12:51 UTC depuis `c6d9454` (branche `feat/10-modele-final`, arbre propre), en 4 s :

```bash
uv run python -m foot_predictor.modeling train --final experiments/scelle_h1.yaml --model M3_G0G2 --include-sealed \
    --dataset ds-2026-10-22-94969da0 --validation-report reports/experiments/scelle-h1-20261022T120542.json
```

| Élément | Valeur |
|---|---|
| Version | `scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle` |
| Carte | `reports/model_cards/scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle.json` (copie de `models/<version>/model_card.json`) |
| Modèle | `models/<version>/model.joblib`, hors Git, 28,6 Mo, sha256 `b121f30bb33faabe52ff64b3d4a983130277bb9f8aeabfda40c3dc9beff33840` ; chargé sans erreur par `inference.models.load_model` |
| Apprentissage | 2015-16 à 2026-27, du 2015-08-07 au 2026-10-18 : 40 180 lignes (20 090 matchs), dont les 4 184 lignes scellées du top 5 ; 26 exclues, toutes antérieures au scellé |
| Demi-vie | **240 jours**, par la procédure figée : validation interne sur le début de 2026-27 (341 matchs), log-loss 1,9754 (60 j), 1,9702 (120 j), 1,9695 (240 j) |
| Coefficients | proches de ceux de la carte du 2026-09-30 (sans matchs scellés) : écart absolu maximal 0,009 (constante de la Bundesliga) |
| Métriques de la carte | celles du test scellé (rapport `scelle-h1-20261022T120542`, 2 092 matchs) |
| Journal du scellé | 7 lignes : une lecture du jeu (9 118 lignes scellées) ajoutée |

- **Choix de la procédure** : la commande figée valide la demi-vie sur la dernière saison présente, ici incomplète (341 matchs). Ce point a été relevé avant le lancement. L'utilisateur a choisi d'appliquer la procédure telle quelle plutôt que de l'adapter après avoir vu le résultat scellé (ADR-0044, options).
- **`code.dirty: true` dans la carte** : faux positif. La ligne du journal est écrite avant la lecture de l'état Git (E-061). La même cause explique `git_dirty: true` dans le manifeste du jeu `94969da0`. Corrigé dans le code le 2026-10-31 (PR #93) ; la carte et le manifeste déjà écrits restent tels quels.
- **Pas encore en service** : le modèle actif de l'inférence reste celui du 2026-09-30 jusqu'à la sous-étape 5.13.

## Test scellé H2 : liste figée (6.9)

Décision : **ADR-0050** (modèle H2 retenu, liste, contrôles et règles de lecture fixés avant le test), en application de l'ADR-0047 (D5, D6).

| Identifiant | Modèle | Rôle |
|---|---|---|
| `M3_G0G2` | M3, G0 + G1 + G2 | référence : la procédure H1 du premier test, même ligne que `scelle_h1.yaml` |
| `M3_H2` | M3, G0 + G1 + G2 + G5 (G5 appris dès 2016-17) | modèle H2 retenu (6.7 et 6.8) |
| `B1`, `marche_avant_cloture` | | contexte, sans décision |

La seule comparaison de décision est `[M3_G0G2, M3_H2]`. Elle est placée en premier, parce que la ligne de résultat du journal recopie la première comparaison.

**Garde-fous** (`modeling/sealed.py`) : le nom du fichier `experiments/scelle_<v>.yaml` désigne la version, et donc son tag `pre-scelle-<v>` et ses chemins gelés :

| Version | Tag | Chemins gelés jusqu'au test |
|---|---|---|
| H1 (fait) | `pre-scelle-h1` | `modeling/`, `features/`, `experiments/` |
| H2 | `pre-scelle-h2` | les mêmes, plus `src/foot_predictor/seal.py` |

**Répétition avant le tag** (`tests/test_scelle_h2.py`, sans base ni scellé) :

- le vrai fichier passe de bout en bout sur des données synthétiques avec les colonnes H2, avec 10 000 rééchantillonnages et le marché ;
- les tableaux se relisent (« non applicable : 1 pli »), et le journal porte `M3_G0G2 − M3_H2` ;
- deux exécutions donnent des prédictions identiques ;
- `M3_G0G2` prédit au bit près comme celui de `scelle_h1.yaml`.

Prévention d'E-059 : chaque fichier d'`experiments/` passe par l'encodeur du rapport (`tests/modeling/test_experiment.py`).

Phase B seulement (6.12, une fois ; `git diff --stat pre-scelle-h2 -- src/foot_predictor/modeling src/foot_predictor/features src/foot_predictor/seal.py experiments` vide) :

```bash
uv run python -m foot_predictor.features build --horizon H2 --sealed-test --experiment experiments/scelle_h2.yaml   # 3 lignes au journal
uv run python -m foot_predictor.sealed_check_h2 --h1 data/datasets_scelles/ds-2026-10-22-94969da0 --h2 data/datasets_scelles/<version scellée H2>   # contrôle 1 de l'ADR-0050 (verdict seulement), sinon arrêt
uv run python -m foot_predictor.modeling evaluate experiments/scelle_h2.yaml --sealed-test --dataset <version scellée H2>   # UNE fois
uv run python -m foot_predictor.modeling summary reports/experiments/<id>.json --output docs/resultats/test_scelle_h2.md
```

Pas d'entraînement final H2 avec les matchs scellés (ADR-0047, D6). La commande `train --final --include-sealed` l'accepterait techniquement après le test : c'est la règle qui l'interdit.

### Résultats de 6.12 : test scellé H2 (2026-11-01)

Tableaux générés : [`docs/resultats/test_scelle_h2.md`](../../resultats/test_scelle_h2.md) (rapport `scelle-h2-20261101T153604`, commit `9c326ab`, arbre propre, jeu `ds-2026-11-01-9b5f2f2c`). Un seul lancement, sans échec technique, publié tel quel.

- **Contrôle 1** (avant l'évaluation) : 68 colonnes communes, 205 216 lignes, **identiques au bit près** à `ds-2026-10-22-94969da0` (outil `foot_predictor.sealed_check_h2`, verdict seul).
- **Contrôle 2** : 2 092 matchs scellés ; **169 écartés** par l'intersection (au moins une variable de G5 vide, surtout `xi_mean_age` : 93 et 88 matchs pour chacune des deux équipes ; `xi_quality` vide pour 9 et 5) ; **1 923 matchs** évalués, dont 1 855 avec une cote.
- **Décision** (seule comparaison de décision) : M3_H2 contre M3_G0G2, log-loss du total **+0,00129 [−0,00035 ; +0,00289]**, Diebold-Mariano p = 0,12. **Non significatif**, sans qu'on puisse conclure à l'absence d'effet : le test ne détecte qu'un écart d'environ 0,007, le gain attendu est de 0,0008 (ADR-0050). La validation glissante donnait +0,00078 [+0,00003 ; +0,00151] ; le scellé donne le même signe et le même ordre de grandeur.
- **Lecture** (ADR-0050, contrôle 4) : conclusion principale inchangée (validation glissante, 7 156 matchs) ; un écart non significatif est le résultat attendu et **ne retire pas G5**. Les cinq autres métriques de la même comparaison ne sont ni corrigées pour les comparaisons multiples ni dans la règle de décision : le Brier de P(T = 1) a une borne basse à +0,00001 (p = 0,04) ; ne pas en tirer de conclusion.
- **Contexte** : B1 − M3_H2 = +0,0177 [+0,0089 ; +0,0268] (le modèle H2 bat B1 ; le test H1 donnait +0,0189 pour M3_G0G2 sur 2 092 matchs) ; Brier plus/moins 2,5 : le marché avant clôture reste meilleur que M3_H2 (+0,00137 [−0,00036 ; +0,00307], non significatif). Calibration de M3_H2 : pente 0,99, couverture observée 87,7 % pour 87,5 % annoncée.
- **Contrôle 5** : les prédictions de `M3_G0G2` sont **identiques au bit près** (14 colonnes, 1 923 matchs communs, écart maximal nul) à celles de la relance du test H1 (`scelle-h1-20261022T120542`) ; les hyperparamètres retenus sont les mêmes (demi-vie 240).
- **Pas de modèle final H2** appris avec les matchs scellés (ADR-0047, D6).

## Ce que fait chaque commande

| Commande | Effet | Garde-fous |
|---|---|---|
| `features build --sealed-test` | jeu avec les matchs scellés (variables sur l'historique antérieur à chaque match), phase `scelle`, dans `data/datasets_scelles/` ; avec `--horizon H2`, compositions et feuilles de match scellées lues de même | `--experiment` obligatoire ; chaque lecture journalisée dans `reports/sealed_tests.md` |
| `evaluate --sealed-test` | pli unique : apprentissage 2015-16 à 2024-25, validation interne sur 2024-25, test sur toutes les saisons suivantes ; rapport JSON et ligne de résultat au journal | fichier `experiments/scelle_<v>.yaml` avec `sealed_test: true` ; tag `pre-scelle-<v>` présent et chemins gelés inchangés ; aucune évaluation terminée au journal |
| `train --final` | apprentissage selon la procédure du fichier, `models/<version>/` (modèle et carte), carte copiée dans `reports/model_cards/` | jamais d'écrasement ; `--include-sealed` refusé tant que le test scellé n'est pas terminé |

## Carte d'identité (`modeling/model_card.py`)

Version, horizon, classe et hyperparamètres retenus (avec les scores de la validation interne), variables requises et matrice (groupes, demi-vie, colonnes retirées), période et population d'apprentissage (lignes, matchs, exclusions, matchs scellés ou non), jeu de données (version, sha256 du manifeste et du registre, chargement), révision Alembic **du jeu de données**, commit, coefficients, métriques de validation du rapport de référence, limites connues. Première carte : `reports/model_cards/scelle-h1-m3_g0g2-20260930-3c92fc80.json` (apprentissage 2015-16 à 2024-25, 35 996 lignes, demi-vie 240 jours). Carte du modèle final : `reports/model_cards/scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle.json` (4.17).

## Limites connues

- La première carte reprend les métriques de validation glissante (2021-22 à 2024-25) ; celle du modèle final reprend celles du test scellé.
- Modèle final : demi-vie choisie sur 341 matchs (début de 2026-27) ; 120 et 240 jours sont presque équivalents (ADR-0044).
- En live, G2 lira les tirs de football-data seulement (ADR-0035).
