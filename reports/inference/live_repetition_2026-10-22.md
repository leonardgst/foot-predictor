# Répétition du live sur la période de développement — 2026-10-22

Produit par `python -m foot_predictor.inference check --only live` (sous-étape 5.10, ADR-0042). Gel simulé au 2024-02-15, « aujourd'hui » simulé 2024-03-09 : les CSV historiques de football-data de la saison, coupés aux matchs d'avant ce jour, complètent la table gelée (superposition en mémoire).

- Matchs des 10 championnats entre le gel et ce jour : 335 ; résultats rétablis par football-data : **335** ; scores différents de l'API : **0**.
- Lignes inutilisables (jamais devinées) : 0.
- Lignes des matchs du 2024-03-09 : 104 ; buts et Elo identiques à ceux de la vraie table : **oui**.
- Statuts de disponibilité des matchs du jour : available 20, out_of_scope 52.
- Durée de la superposition : 1.1 s.

| Variable en écart (tirs de football-data au lieu de ceux de l'API) | Lignes |
|---|---|
| `opp_xgp_against_ewm_h120` | 61 |
| `opp_xgp_against_ewm_h240` | 61 |
| `opp_xgp_against_ewm_h60` | 61 |
| `opp_xgp_for_ewm_h120` | 60 |
| `opp_xgp_for_ewm_h240` | 60 |
| `opp_xgp_for_ewm_h60` | 60 |
| `xgp_against_ewm_h120` | 61 |
| `xgp_against_ewm_h240` | 61 |
| `xgp_against_ewm_h60` | 61 |
| `xgp_for_ewm_h120` | 60 |
| `xgp_for_ewm_h240` | 60 |
| `xgp_for_ewm_h60` | 60 |

Fraîcheur par championnat (identifiant API : complet jusqu'au) : 135 : 2024-03-08, 136 : 2024-03-08, 140 : 2024-03-08, 141 : 2024-03-08, 39 : 2024-03-08, 40 : 2024-03-08, 61 : 2024-03-08, 62 : 2024-03-08, 78 : 2024-03-08, 79 : 2024-03-08.

**Jours suivants, sans leurs résultats (fraîcheur par équipe, ADR-0046)** : comparaison avec la même superposition complétée des résultats manquants ; Elo identique attendu, écart de λ au plus 0.005 et de P(T > 2,5) au plus 0.002 : **conforme**.

| Jour | Matchs du top 5 | Disponibles (par championnat) | Disponibles (par équipe) | Elo identique | Écart max. G2 | Écart max. λ | Écart max. P(T > 2,5) |
|---|---|---|---|---|---|---|---|
| 2024-03-10 | 21 | 0 | 21 | 21 | 3.9e-04 | 5.3e-04 | 1.5e-04 |
| 2024-03-11 | 3 | 0 | 3 | 3 | 1.9e-04 | 1.2e-04 | 4.5e-05 |
| 2024-03-13 | 1 | 0 | 0 | 0 | 0.0e+00 | — | — |
| 2024-03-15 | 4 | 0 | 0 | 0 | 0.0e+00 | — | — |
| 2024-03-16 | 19 | 0 | 0 | 0 | 0.0e+00 | — | — |
