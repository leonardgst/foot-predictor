"""Liste explicite des features utilisées par les modèles de score exact.

cf. docs/MODELE_MATHEMATIQUE.md section 2.2 (vecteur z). Chaque nom doit être
une colonne de `features.team_match_features`. z_9 (squad_avg_age), z_10
(squad_stability_score_season) et z_11 (agrégat MVS) sont bloquées tant que
l'ingestion API-Football (lineup) n'a pas alimenté ces colonnes -- voir
docs/RECAP_PROJET.md section 11. Passer explicitement une liste enrichie à
`build_dataset()` (dataset.py) une fois ces colonnes disponibles, sans modifier
le pipeline d'entraînement lui-même.
"""
from __future__ import annotations

# z1 .. z8 : réellement calculables aujourd'hui (voir RECAP_PROJET.md section 6.3/8).
Z1_Z8_FEATURE_COLUMNS: list[str] = [
    "form_points_last10",
    "goals_for_last10",
    "goals_against_last10",
    "xg_for_last5",
    "xg_against_last5",
    "standing_position",
    "standing_points",
    "standing_goal_diff",
]

# Bloquées pour l'instant (nécessitent staging.lineup) -- gardées ici en
# documentation, à ajouter à une liste de features passée à build_dataset()
# une fois calculées, jamais en les codant en dur ailleurs dans le pipeline.
Z9_Z11_BLOCKED_FEATURE_COLUMNS: list[str] = [
    "squad_avg_age",
    "squad_stability_score_season",
    # z11 (agrégat MVS des titulaires) : nom de colonne non encore défini.
]

DEFAULT_FEATURE_COLUMNS = Z1_Z8_FEATURE_COLUMNS
