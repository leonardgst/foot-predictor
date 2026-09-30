# Étape 10 : sélection du modèle H1, test scellé et entraînement final (jalon J6)

Mode d'emploi de la sélection du modèle MVP, du test scellé (phase B) et de l'entraînement final. Décisions : ADR-0037 (règle de décision), ADR-0038 (structure), **ADR-0039 (modèle MVP H1, liste du test scellé)**. Résultats : [`docs/resultats/ablations.md`](../../resultats/ablations.md).

## En bref

- **Modèle MVP H1** : M3 (Poisson par équipe) sur G0 + G1 + G2, demi-vie choisie par validation interne, appris sur le top 5 ; même modèle en rejeu et en live (G3 non retenu).
- **Liste figée** : `experiments/scelle_h1.yaml` (modèle retenu, B0, B1, marché avant clôture, marché à la clôture).
- **Tag `pre-scelle-h1`** : posé sur la fusion de la sous-étape 4.14, après l'écriture du code du test scellé ; ensuite, plus aucun changement sous `src/foot_predictor/modeling/`, `src/foot_predictor/features/`, `experiments/` avant le test.
- **Test scellé** : une seule fois, en phase B, après le gel ; résultat publié tel quel.

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

## Ce que fait chaque commande

| Commande | Effet | Garde-fous |
|---|---|---|
| `features build --sealed-test` | jeu avec les matchs scellés (variables sur l'historique antérieur à chaque match), phase `scelle`, dans `data/datasets_scelles/` | `--experiment` obligatoire ; lecture journalisée dans `reports/sealed_tests.md` |
| `evaluate --sealed-test` | pli unique : apprentissage 2015-16 à 2024-25, validation interne sur 2024-25, test sur toutes les saisons suivantes ; rapport JSON et ligne de résultat au journal | fichier `sealed_test: true` ; tag `pre-scelle-h1` présent et code inchangé ; aucune évaluation terminée au journal |
| `train --final` | apprentissage selon la procédure du fichier, `models/<version>/` (modèle et carte), carte copiée dans `reports/model_cards/` | jamais d'écrasement ; `--include-sealed` refusé tant que le test scellé n'est pas terminé |

## Carte d'identité (`modeling/model_card.py`)

Version, horizon, classe et hyperparamètres retenus (avec les scores de la validation interne), variables requises et matrice (groupes, demi-vie, colonnes retirées), période et population d'apprentissage (lignes, matchs, exclusions, matchs scellés ou non), jeu de données (version, sha256 du manifeste et du registre, chargement), révision Alembic **du jeu de données**, commit, coefficients, métriques de validation du rapport de référence, limites connues. Première carte : `reports/model_cards/scelle-h1-m3_g0g2-20260930-3c92fc80.json` (apprentissage 2015-16 à 2024-25, 35 996 lignes, demi-vie 240 jours).

## Limites connues

- La carte reprend les métriques de validation glissante (2021-22 à 2024-25) ; celles du test scellé viendront en phase B.
- En live, G2 lira les tirs de football-data seulement (ADR-0035).
