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
uv run python -m foot_predictor.modeling evaluate experiments/ablations.yaml  # environ 1 min : G0 à G3 sur M3 (4.12)
uv run python -m foot_predictor.modeling evaluate experiments/population.yaml # environ 15 s : top 5 contre top 5 et D2
uv run python -m foot_predictor.modeling summary reports/experiments/<id>.json --output <fichier.md>
```

Ablations (4.12) : `docs/resultats/ablations.md` ; courbe d'apport et analyses descriptives par `modeling/analysis.py` (`contribution_table`, `plot_contribution`, `gain_by_group`, `closed_doors_effect`), figure `docs/resultats/figures/courbe_apport.png`. Résultat : G0 + G1 + G2 retenus, G3 et les D2 sans gain.

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

## Partie 6 : modèles de l'horizon H2 (sous-étape 6.7, 2026-11-01)

Spécification et liste des expériences écrites avant toute mesure : **ADR-0048** (commit `402ffd0`). Résultats lisibles et tableaux générés : [`docs/resultats/h2_ablations.md`](../../resultats/h2_ablations.md).

- **Modèle** : toujours M3 (Poisson par équipe). `Design` accepte maintenant G4 (entraîneur), G5 (qualité du XI) et G6 (stabilité), colonnes de l'équipe et de l'adversaire, standardisées dans le pli ; G6 exige une variante de cohésion (`cohesion` : `h3`, `h5`, `h10`, `h20`, `hinf`, `reset`, `win10` ou `overlap_only`). La description et les paramètres d'un modèle H1 ne changent pas (garde H1 : rejeu et prédictions reproduits).
- **Rodage (D3)** : `first_training_season` (G5 : 2016-17, G4 : 2017-18) s'applique à la validation interne et à l'ajustement ; les lignes écartées sont comptées dans le rapport (`run_in_rows`). `train_from` (paramètre de M3) donne un témoin de fenêtre sans variable H2.
- **Hyperparamètres** : la demi-vie de G2 et la variante de cohésion se choisissent ensemble par validation interne (15 candidats avec G6).
- **Écart par tranche de journées** : chaque comparaison d'un rapport porte `by_round` (écart poolé et intervalle par bootstrap de blocs dans les tranches 1-5, 6-10, 11-19, 20 et plus), descriptif, hors de la règle de décision. `modeling summary` en fait un tableau.
- **Lancer** (arbre propre, sinon le rapport note `dirty: true`) :

```bash
uv run python -m foot_predictor.modeling evaluate experiments/ablations_h2_mesure_duree.yaml   # 83 s
uv run python -m foot_predictor.modeling evaluate experiments/ablations_h2.yaml                # environ 2 min, décision
uv run python -m foot_predictor.modeling evaluate experiments/stabilite_h2.yaml                # environ 2 min, diagnostic
uv run python -m foot_predictor.modeling summary reports/experiments/<id>.json                 # tableaux
```

- **Résultat** : en suivant le chemin écrit d'avance (G6, puis G5, puis G4), **G6 n'est pas retenu** (+0,00035 [−0,00022 ; +0,00091]), **G5 l'est** (+0,00078 [+0,00003 ; +0,00151], 4 plis sur 4, borne basse à 0,00003) et **G4 ne l'est pas** (−0,00090 [−0,00158 ; −0,00022]). Modèle H2 retenu : M3 sur G0 + G1 + G2 + G5. Gain minuscule et fragile (à fenêtre égale, il n'est plus significatif) ; aucune variante de stabilité ne se distingue de la base.

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
