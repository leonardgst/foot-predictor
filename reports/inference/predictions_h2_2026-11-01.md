# Prédictions de rejeu (H2) sur des journées réelles — 2026-11-01

Produit par `python -m foot_predictor.inference check` (ADR-0040). `predict_day` en rejeu (lignes d'inférence, matrice de disponibilité, modèle du pli) contre l'expérience structures-h2-20261101T134102 (M3_H2) pour les mêmes matchs.

**Verdict : reproduites.**

| Jour | Matchs (toutes compétitions) | Statuts | Prédits | Écart max. λ | Log-loss rejeu | Log-loss évaluation | Durée (s) |
|---|---|---|---|---|---|---|---|
| 2022-03-13 | 75 | available 25, out_of_scope 49, unavailable 1 | 25 | 4.4e-16 | 1.8168 | 1.8168 | 38.8 |
| 2021-08-06 | 14 | available 1, out_of_scope 13 | 1 | 0.0e+00 | 1.4301 | 1.4301 | 17.2 |
| 2023-04-08 | 80 | available 27, out_of_scope 53 | 27 | 4.4e-16 | 1.7185 | 1.7185 | 20.5 |
| 2022-08-05 | 26 | available 3, out_of_scope 23 | 3 | 4.4e-16 | 2.0616 | 2.0616 | 18.9 |
| 2024-05-19 | 77 | available 33, out_of_scope 44 | 33 | 8.9e-16 | 1.8552 | 1.8552 | 24.0 |
| 2023-08-11 | 19 | available 4, out_of_scope 15 | 4 | 2.2e-16 | 1.4678 | 1.4678 | 20.6 |
| 2025-05-10 | 87 | available 27, out_of_scope 60 | 27 | 4.4e-16 | 1.8677 | 1.8677 | 24.9 |
| 2024-08-15 | 40 | available 2, out_of_scope 38 | 2 | 4.4e-16 | 1.4032 | 1.4032 | 22.8 |

Raisons rencontrées (matchs non prédits) :

- hors périmètre du modèle H2 (championnat hors du top 5) : pas de prédiction
- hors périmètre du modèle H2 (coupe) : pas de prédiction
- opp_xi_quality (exterieur) manquante : qualité du onze de l'adversaire incalculable : onze incomplet ou absent de la feuille de match, ou titulaire sans poste ni note antérieure
- xi_quality (domicile) manquante : qualité du onze de l'équipe incalculable : onze incomplet ou absent de la feuille de match, ou titulaire sans poste ni note antérieure
