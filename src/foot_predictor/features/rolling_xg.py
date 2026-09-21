"""Calcul du xG glissant (staging.team_match/match -> features.team_match_features).

Fenêtre glissante des 5 derniers matchs (plus courte que la forme/buts car le
xG est plus volatile -- fenêtre de 10 serait moins réactive), même contexte
domicile/extérieur, toutes compétitions confondues -- cf.
recap_etape2_schema_tables.md section 4.

Les matchs dont xg_for/xg_against sont encore NULL (Understat pas encore
ingéré) sont exclus de la fenêtre plutôt que comptés comme 0.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import Match, TeamMatch

XG_WINDOW = 5


@dataclass
class RollingXgSnapshot:
    xg_for_last5: float | None
    xg_against_last5: float | None
    xg_matches_count_last5: int


def compute_rolling_xg(
    session: Session,
    team_id: int,
    is_home: bool,
    before_date: dt.datetime,
) -> RollingXgSnapshot:
    """xG sur les XG_WINDOW derniers matchs avec xG renseigné, dans le même
    contexte domicile/extérieur, toutes compétitions confondues, strictement
    avant `before_date` (anti-leakage)."""
    rows = session.execute(
        select(TeamMatch)
        .join(Match, Match.id == TeamMatch.match_id)
        .where(
            TeamMatch.team_id == team_id,
            TeamMatch.is_home == is_home,
            Match.match_date < before_date,
            Match.status == "played",
            TeamMatch.xg_for.isnot(None),
            TeamMatch.xg_against.isnot(None),
        )
        .order_by(Match.match_date.desc())
        .limit(XG_WINDOW)
    ).scalars().all()

    n = len(rows)
    if n == 0:
        return RollingXgSnapshot(xg_for_last5=None, xg_against_last5=None, xg_matches_count_last5=0)

    xg_for_total = sum(float(tm.xg_for) for tm in rows)
    xg_against_total = sum(float(tm.xg_against) for tm in rows)

    return RollingXgSnapshot(
        xg_for_last5=round(xg_for_total / n, 2),
        xg_against_last5=round(xg_against_total / n, 2),
        xg_matches_count_last5=n,
    )