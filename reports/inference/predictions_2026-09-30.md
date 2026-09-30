# Prédictions de rejeu sur des journées réelles — 2026-09-30

Produit par `python -m foot_predictor.inference check` (ADR-0040). `predict_day` en rejeu (lignes d'inférence, matrice de disponibilité, modèle du pli) contre l'expérience ablations-20260930T110352 (A2_G0G2) pour les mêmes matchs.

**Verdict : reproduites.**

| Jour | Matchs (toutes compétitions) | Statuts | Prédits | Écart max. λ | Log-loss rejeu | Log-loss évaluation | Durée (s) |
|---|---|---|---|---|---|---|---|
| 2022-03-13 | 75 | available 26, out_of_scope 49 | 26 | 4.4e-16 | 1.8650 | 1.8650 | 2.4 |
| 2021-08-06 | 14 | available 1, out_of_scope 13 | 1 | 0.0e+00 | 1.4296 | 1.4296 | 2.2 |
| 2023-04-08 | 80 | available 27, out_of_scope 53 | 27 | 4.4e-16 | 1.7196 | 1.7196 | 2.5 |
| 2022-08-05 | 26 | available 3, out_of_scope 23 | 3 | 2.2e-16 | 2.0772 | 2.0772 | 2.0 |
| 2024-05-19 | 77 | available 33, out_of_scope 44 | 33 | 8.9e-16 | 1.8479 | 1.8479 | 2.8 |
| 2023-08-11 | 19 | available 4, out_of_scope 15 | 4 | 4.4e-16 | 1.4698 | 1.4698 | 2.2 |
| 2025-05-10 | 87 | available 27, out_of_scope 60 | 27 | 4.4e-16 | 1.8676 | 1.8676 | 2.8 |
| 2024-08-15 | 40 | available 2, out_of_scope 38 | 2 | 2.2e-16 | 1.4101 | 1.4101 | 2.2 |

Raisons rencontrées (matchs non prédits) :

- hors périmètre du modèle H1 (championnat hors du top 5) : pas de prédiction
- hors périmètre du modèle H1 (coupe) : pas de prédiction
