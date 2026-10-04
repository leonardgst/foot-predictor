# Répétition du live sur la période de développement — 2026-10-04

Produit par `python -m foot_predictor.inference check --only live` (sous-étape 5.10, ADR-0042). Gel simulé au 2024-02-15, « aujourd'hui » simulé 2024-03-09 : les CSV historiques de football-data de la saison, coupés aux matchs d'avant ce jour, complètent la table gelée (superposition en mémoire).

- Matchs des 10 championnats entre le gel et ce jour : 335 ; résultats rétablis par football-data : **335** ; scores différents de l'API : **0**.
- Lignes inutilisables (jamais devinées) : 0.
- Lignes des matchs du 2024-03-09 : 104 ; buts et Elo identiques à ceux de la vraie table : **oui**.
- Statuts de disponibilité des matchs du jour : available 20, out_of_scope 52.
- Durée de la superposition : 0.3 s.

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
