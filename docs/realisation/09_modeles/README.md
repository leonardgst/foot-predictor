# Étape 09 : modèles M1 à M6 (jalon J6, première moitié)

Mode d'emploi des modèles du MVP et de leurs expériences. Protocole : [étape 08](../08_protocole_et_references/README.md) et ADR-0037 (tag `protocole-v1`). Résultats lisibles : [`docs/resultats/modeles.md`](../../resultats/modeles.md). Équations : chapitre « Modèles » de [`docs/latex/mathematiques/`](../../latex/mathematiques/). Décision : ADR-0038 (structure retenue).

## En bref

- Les structures se comparent avec les variables **G0 + G1** (décision 5), sur les 4 plis, par la règle de l'ADR-0037.
- Parcours : M1 (linéaire) → M2 (Poisson sur le total) → **M3 (Poisson par équipe, retenu)** → M4 (binomiale négative, non justifiée) → M5 (Dixon-Coles, sans gain) → M6 (Poisson régularisé, G0 à G3).
- Chaque modèle suit l'interface `fit(lignes)` puis `predict(lignes sans cible)` ; tout ce qui s'ajuste (standardisation, régularisation, ρ de Dixon-Coles) s'ajuste dans le pli.

## Commandes

```bash
uv run python -m foot_predictor.modeling evaluate experiments/m1_m2.yaml   # environ 5 s
uv run python -m foot_predictor.modeling evaluate experiments/m3.yaml      # environ 7 s (diagnostic de M4 compris)
uv run python -m foot_predictor.modeling evaluate experiments/m5.yaml      # environ 7 s
uv run python -m foot_predictor.modeling evaluate experiments/m6.yaml      # environ 12 min (élastique net)
uv run python -m foot_predictor.modeling summary reports/experiments/<id>.json --output <fichier.md>
```

## Modèles (`modeling/models/`)

| Nom dans le YAML | Classe | Module | Paramètres |
|---|---|---|---|
| `b0`, `b1` | B0, B1 | `references.py` | `window` (B1) |
| `m1`, `m2` | M1, M2 | `total.py` | `groups` (G0, G1) |
| `m3`, `m4` | M3, M4 | `team.py` | `groups`, `half_life` ; `check_dispersion` (M3) |
| `m5` | M5 | `dependence.py` | `groups`, `half_life` |
| `m6` | M6 | `regularized.py` | `groups`, `half_life`, `alpha`, `penalty` (`l2`, `elasticnet`), `l1_ratio` |
| `market` | marché | `market.py` | `version` (`avant_cloture`, `cloture`) |

Matrice des variables : `modeling/design.py` (groupes G0 à G3, standardisation dans le pli, colonnes constantes retirées). Diagnostics : `modeling/diagnostics.py` (φ, Cameron-Trivedi, rapport de vraisemblance au bord), `modeling/nonlinearity.py` (buts observés contre attendus par décile de l'écart d'Elo).

## Ajouter un modèle

1. Une classe `Model` dans `modeling/models/` : `features` (colonnes requises), `fit`, `predict` → `MatchPredictions`, `describe`.
2. Son nom dans `MODELS` (`modeling/models/__init__.py`).
3. Ses tests, propriétés théoriques d'abord (données simulées : `tests/modeling/synthetic.py`).
4. Une expérience `experiments/<nom>.yaml` ; mesurer la durée avec `n_resamples: 200` sur un pli si la grille est grande.
5. Une section dans `docs/resultats/modeles.md` et dans le chapitre LaTeX.

## Limites connues

- Tous les modèles supposent l'indépendance conditionnelle des deux équipes, sauf M5 (qui ne gagne rien).
- Légère sous-dispersion des buts par équipe (φ ≈ 0,98) : non modélisée.
- Le critère (iii) de la règle (pente de calibration) est fragile pour des prévisions peu dispersées (constat de B1).
