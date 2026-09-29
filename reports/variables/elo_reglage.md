# Réglage de l'Elo — 2026-09-29

Produit par `python -m foot_predictor.features.elo_tuning` (ADR-0031). Chiffres seulement.

- Fenêtre d'évaluation : saisons 2005-06 à 2014-15, matchs de saison régulière du top 5 : **18259** matchs. Amorçage depuis 2000-01 ; aucune saison après 2014-15 n'est lue.
- Grille : 576 combinaisons (`k` ∈ {10, 15, 20, 25, 30, 40}, `home_advantage` ∈ {40, 60, 80, 100}, `season_regression` ∈ {0.0, 0.1, 0.2, 0.33}, `goal_multiplier` ∈ {False, True}, `initial_gap` ∈ {0, 100, 200}) ; durée 217 s.
- Critère : log-loss du 1N2 d'une logistique ordonnée sur (R_dom + H − R_ext) / 400, ajustée sur la fenêtre.
- Référence sans note (fréquences de 1, N, 2) : **1.0622**.
- Meilleure combinaison : **0.9936** (gain 0.0686).

## 15 meilleures combinaisons

| Rang | K | H | r | Multiplicateur | Δ | Log-loss |
|---|---|---|---|---|---|---|
| 1 | 15 | 40 | 0.0 | oui | 100 | 0.9936 |
| 2 | 15 | 60 | 0.0 | oui | 100 | 0.9937 |
| 3 | 10 | 40 | 0.1 | oui | 100 | 0.9937 |
| 4 | 15 | 80 | 0.0 | oui | 100 | 0.9937 |
| 5 | 15 | 40 | 0.0 | oui | 200 | 0.9937 |
| 6 | 15 | 40 | 0.0 | oui | 0 | 0.9937 |
| 7 | 15 | 100 | 0.0 | oui | 100 | 0.9937 |
| 8 | 10 | 60 | 0.1 | oui | 100 | 0.9937 |
| 9 | 15 | 60 | 0.0 | oui | 200 | 0.9938 |
| 10 | 15 | 60 | 0.0 | oui | 0 | 0.9938 |
| 11 | 15 | 80 | 0.0 | oui | 200 | 0.9938 |
| 12 | 10 | 40 | 0.1 | oui | 0 | 0.9938 |
| 13 | 15 | 80 | 0.0 | oui | 0 | 0.9938 |
| 14 | 10 | 80 | 0.1 | oui | 100 | 0.9938 |
| 15 | 10 | 40 | 0.2 | oui | 100 | 0.9938 |

## Sensibilité (meilleure log-loss par valeur, les autres paramètres libres)

- `k` : 10 → 0.9937 ; 15 → 0.9936 ; 20 → 0.9944 ; 25 → 0.9955 ; 30 → 0.9968 ; 40 → 0.9995
- `home_advantage` : 40 → 0.9936 ; 60 → 0.9937 ; 80 → 0.9937 ; 100 → 0.9937
- `season_regression` : 0.0 → 0.9936 ; 0.1 → 0.9937 ; 0.2 → 0.9938 ; 0.33 → 0.9946
- `goal_multiplier` : False → 0.9947 ; True → 0.9936
- `initial_gap` : 0 → 0.9937 ; 100 → 0.9936 ; 200 → 0.9937

Écart entre la meilleure et la pire combinaison : 0.0097.
