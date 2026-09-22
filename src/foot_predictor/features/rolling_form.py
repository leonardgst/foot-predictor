"""Calcul de la forme récente et des buts (staging.team_match/match ->
features.team_match_features).

Fenêtre glissante des 10 derniers matchs, filtrés sur le même contexte
domicile/extérieur que le match à prédire, toutes compétitions confondues --
cf. recap_etape2_schema_tables.md section 4 (règles de calcul actées).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import Match, TeamMatch

FORM_WINDOW = 10


@dataclass
class RollingFormSnapshot:
    form_points_last10: int
    form_matches_count: int
    goals_for_last10: float | None
    goals_against_last10: float | None


def compute_rolling_form(
    session: Session,
    team_id: int,
    is_home: bool,
    before_date: dt.datetime,
) -> RollingFormSnapshot:
    """Forme récente sur les FORM_WINDOW derniers matchs de `team_id`, dans le
    même contexte domicile/extérieur (`is_home`), toutes compétitions
    confondues, strictement avant `before_date` (anti-leakage)."""
    rows = session.execute(
        select(TeamMatch, Match)
        .join(Match, Match.id == TeamMatch.match_id)
        .where(
            TeamMatch.team_id == team_id,
            TeamMatch.is_home == is_home,
            Match.match_date < before_date,
            Match.status == "played",
        )
        .order_by(Match.match_date.desc())
        .limit(FORM_WINDOW)
    ).all()

    n = len(rows)
    if n == 0:
        return RollingFormSnapshot(
            form_points_last10=0,
            form_matches_count=0,
            goals_for_last10=None,
            goals_against_last10=None,
        )

    points = 0
    goals_for_total = 0
    goals_against_total = 0
    for team_match, _match in rows:
        gf = team_match.goals_for or 0
        ga = team_match.goals_against or 0
        points += 3 if gf > ga else (1 if gf == ga else 0)
        goals_for_total += gf
        goals_against_total += ga

    return RollingFormSnapshot(
        form_points_last10=points,
        form_matches_count=n,
        goals_for_last10=round(goals_for_total / n, 2),
        goals_against_last10=round(goals_against_total / n, 2),
    )