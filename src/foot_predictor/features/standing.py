"""Calcul du classement (staging.team_match/match -> features.team_match_features).

Classement calculé automatiquement à partir de staging.team_match, snapshot
strictement avant la date du match concerné (pas de data leakage) -- cf.
recap_decisions_projet.md section 6 et recap_etape2_schema_tables.md section 2
(décision : standing retiré de staging, calculé en features).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import Match, TeamMatch


@dataclass
class StandingSnapshot:
    team_id: int
    points: int
    goal_diff: int
    position: int


def compute_standings_before_date(
    session: Session,
    competition_id: int,
    season_id: int,
    before_date: dt.datetime,
) -> dict[int, StandingSnapshot]:
    """Classement de la compétition/saison, calculé à partir des matchs
    strictement antérieurs à `before_date` (anti-leakage)."""
    rows = session.execute(
        select(TeamMatch, Match)
        .join(Match, Match.id == TeamMatch.match_id)
        .where(
            Match.competition_id == competition_id,
            Match.season_id == season_id,
            Match.match_date < before_date,
            Match.status == "played",
        )
    ).all()

    totals: dict[int, dict[str, int]] = {}
    for team_match, _match in rows:
        team_id = team_match.team_id
        gf = team_match.goals_for or 0
        ga = team_match.goals_against or 0
        pts = 3 if gf > ga else (1 if gf == ga else 0)

        acc = totals.setdefault(team_id, {"points": 0, "goal_diff": 0})
        acc["points"] += pts
        acc["goal_diff"] += gf - ga

    # Tri : points desc, puis goal_diff desc (départage simplifié -- pas de
    # confrontations directes ni de "plus de buts marqués" en tie-break
    # secondaire pour l'instant ; à raffiner plus tard si besoin)
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1]["points"], -kv[1]["goal_diff"]))

    return {
        team_id: StandingSnapshot(
            team_id=team_id,
            points=vals["points"],
            goal_diff=vals["goal_diff"],
            position=rank,
        )
        for rank, (team_id, vals) in enumerate(ranked, start=1)
    }