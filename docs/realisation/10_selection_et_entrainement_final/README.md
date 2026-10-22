# Étape 10 : sélection du modèle H1, test scellé et entraînement final (jalon J6)

Mode d'emploi de la sélection du modèle MVP, du test scellé (phase B) et de l'entraînement final. Décisions : ADR-0037 (règle de décision), ADR-0038 (structure), **ADR-0039 (modèle MVP H1, liste du test scellé)**. Résultats : [`docs/resultats/ablations.md`](../../resultats/ablations.md).

## En bref

- **Modèle MVP H1** : M3 (Poisson par équipe) sur G0 + G1 + G2, demi-vie choisie par validation interne, appris sur le top 5 ; même modèle en rejeu et en live (G3 non retenu).
- **Liste figée** : `experiments/scelle_h1.yaml` (modèle retenu, B0, B1, marché avant clôture, marché à la clôture).
- **Tag `pre-scelle-h1`** : posé sur la fusion de la sous-étape 4.14, après l'écriture du code du test scellé ; ensuite, plus aucun changement sous `src/foot_predictor/modeling/`, `src/foot_predictor/features/`, `experiments/` avant le test.
- **Test scellé** : une seule fois, en phase B, après le gel ; résultat publié tel quel.
- **Modèle final H1** (4.17, ADR-0044) : `scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle`, appris avec les matchs scellés, jusqu'au 2026-10-18 ; jalon J6, tag `v0.5.0`.

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
- **`code.dirty: true` dans la carte** : faux positif. La ligne du journal est écrite avant la lecture de l'état Git (E-061). La même cause explique `git_dirty: true` dans le manifeste du jeu `94969da0`.
- **Pas encore en service** : le modèle actif de l'inférence reste celui du 2026-09-30 jusqu'à la sous-étape 5.13.

## Ce que fait chaque commande

| Commande | Effet | Garde-fous |
|---|---|---|
| `features build --sealed-test` | jeu avec les matchs scellés (variables sur l'historique antérieur à chaque match), phase `scelle`, dans `data/datasets_scelles/` | `--experiment` obligatoire ; lecture journalisée dans `reports/sealed_tests.md` |
| `evaluate --sealed-test` | pli unique : apprentissage 2015-16 à 2024-25, validation interne sur 2024-25, test sur toutes les saisons suivantes ; rapport JSON et ligne de résultat au journal | fichier `sealed_test: true` ; tag `pre-scelle-h1` présent et code inchangé ; aucune évaluation terminée au journal |
| `train --final` | apprentissage selon la procédure du fichier, `models/<version>/` (modèle et carte), carte copiée dans `reports/model_cards/` | jamais d'écrasement ; `--include-sealed` refusé tant que le test scellé n'est pas terminé |

## Carte d'identité (`modeling/model_card.py`)

Version, horizon, classe et hyperparamètres retenus (avec les scores de la validation interne), variables requises et matrice (groupes, demi-vie, colonnes retirées), période et population d'apprentissage (lignes, matchs, exclusions, matchs scellés ou non), jeu de données (version, sha256 du manifeste et du registre, chargement), révision Alembic **du jeu de données**, commit, coefficients, métriques de validation du rapport de référence, limites connues. Première carte : `reports/model_cards/scelle-h1-m3_g0g2-20260930-3c92fc80.json` (apprentissage 2015-16 à 2024-25, 35 996 lignes, demi-vie 240 jours). Carte du modèle final : `reports/model_cards/scelle-h1-m3_g0g2-20261022-c6d94541-avec-scelle.json` (4.17).

## Limites connues

- La première carte reprend les métriques de validation glissante (2021-22 à 2024-25) ; celle du modèle final reprend celles du test scellé.
- Modèle final : demi-vie choisie sur 341 matchs (début de 2026-27) ; 120 et 240 jours sont presque équivalents (ADR-0044).
- En live, G2 lira les tirs de football-data seulement (ADR-0035).
