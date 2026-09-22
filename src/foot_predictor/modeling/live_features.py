"""Calcul EN DIRECT du vecteur z (état d'une équipe avant un match) pour un
match qui n'a PAS encore été joué -- contrairement à
`features/build_team_match_features.py`, qui calcule et persiste ces mêmes
variables pour des matchs déjà joués.

Réutilise volontairement les mêmes fonctions que le pipeline features
(`compute_rolling_form`, `compute_rolling_xg`, `compute_standings_before_date`)
plutôt que de dupliquer leur logique : elles prennent déjà `before_date` en
paramètre et n'exigent pas que le match lui-même existe en base, donc
fonctionnent à l'identique pour un match futur (anti-fuite déjà garanti par
la clause `Match.match_date < before_date` de ces fonctions).

Seules z1-z8 (`Z1_Z8_FEATURE_COLUMNS`) sont calculables ici. z9-z11
(`squad_avg_age`, `squad_stability_score_season`, agrégat MVS) dépendent de
`staging.lineup`, vide tant que le backfill API-Football n'est pas terminé --
demander une de ces colonnes lève une erreur explicite plutôt que de renvoyer
une valeur inventée.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from foot_predictor.features.rolling_form import compute_rolling_form
from foot_predictor.features.rolling_xg import compute_rolling_xg
from foot_predictor.features.standing import compute_standings_before_date
from foot_predictor.modeling.features_config import Z1_Z8_FEATURE_COLUMNS

SUPPORTED_FEATURE_COLUMNS = frozenset(Z1_Z8_FEATURE_COLUMNS)


def compute_live_z_features(
    session: Session,
    *,
    team_id: int,
    is_home: bool,
    before_date: dt.datetime,
    competition_id: int,
    season_id: int,
    feature_columns: list[str],
) -> dict[str, float | int | None]:
    """Vecteur z de `team_id`, à jour au `before_date` donné (strictement
    antérieur, comme le reste du pipeline). Une valeur `None` signifie que
    l'équipe n'a pas assez d'historique sur cette fenêtre (ex. tout début de
    saison ou équipe promue) -- à charge de l'appelant (`predict_service.py`)
    de décider s'il refuse la prédiction plutôt que de l'utiliser telle
    quelle (comme `dataset.py` le fait à l'entraînement via `dropna`)."""
    unsupported = [c for c in feature_columns if c not in SUPPORTED_FEATURE_COLUMNS]
    if unsupported:
        raise NotImplementedError(
            f"Features non calculables en direct (nécessitent staging.lineup, "
            f"vide pour l'instant) : {unsupported}"
        )

    form = compute_rolling_form(session, team_id, is_home, before_date)
    xg = compute_rolling_xg(session, team_id, is_home, before_date)
    standing = compute_standings_before_date(session, competition_id, season_id, before_date).get(team_id)

    values: dict[str, float | int | None] = {
        "form_points_last10": form.form_points_last10,
        "goals_for_last10": form.goals_for_last10,
        "goals_against_last10": form.goals_against_last10,
        "xg_for_last5": xg.xg_for_last5,
        "xg_against_last5": xg.xg_against_last5,
        "standing_position": standing.position if standing is not None else None,
        "standing_points": standing.points if standing is not None else None,
        "standing_goal_diff": standing.goal_diff if standing is not None else None,
    }
    return {col: values[col] for col in feature_columns}
