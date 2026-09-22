"""Orchestration : assemble standing + rolling_form + rolling_xg pour chaque
staging.team_match joué, et upsert le résultat dans features.team_match_features.

Chaque ligne est calculée en se plaçant strictement AVANT la date du match
concerné (anti-leakage) -- cf. recap_decisions_projet.md section 6.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import Match, TeamMatch, TeamMatchFeatures
from foot_predictor.features.rolling_form import compute_rolling_form
from foot_predictor.features.rolling_xg import compute_rolling_xg
from foot_predictor.features.standing import compute_standings_before_date


def build_all_team_match_features(session: Session) -> tuple[int, int]:
    """Renvoie (nb_crees, nb_mis_a_jour)."""
    rows = session.execute(
        select(TeamMatch, Match)
        .join(Match, Match.id == TeamMatch.match_id)
        .where(Match.status == "played")
    ).all()

    # Cache des classements par (competition_id, season_id) -- évite de
    # recalculer le classement complet de la compétition à chaque ligne alors
    # que la plupart des team_match d'une même journée partagent la même date
    # de référence.
    standings_cache: dict[tuple[int, int], dict] = {}

    created, updated = 0, 0
    for team_match, match in rows:
        cache_key = (match.competition_id, match.season_id, match.match_date)
        if cache_key not in standings_cache:
            standings_cache[cache_key] = compute_standings_before_date(
                session, match.competition_id, match.season_id, match.match_date
            )
        standing = standings_cache[cache_key].get(team_match.team_id)

        form = compute_rolling_form(session, team_match.team_id, team_match.is_home, match.match_date)
        xg = compute_rolling_xg(session, team_match.team_id, team_match.is_home, match.match_date)

        existing = session.scalar(
            select(TeamMatchFeatures).where(TeamMatchFeatures.team_match_id == team_match.id)
        )
        if existing is None:
            existing = TeamMatchFeatures(
                team_match_id=team_match.id,
                match_id=match.id,
                team_id=team_match.team_id,
            )
            session.add(existing)
            created += 1
        else:
            updated += 1

        existing.form_points_last10 = form.form_points_last10
        existing.form_matches_count = form.form_matches_count
        existing.goals_for_last10 = form.goals_for_last10
        existing.goals_against_last10 = form.goals_against_last10

        existing.xg_for_last5 = xg.xg_for_last5
        existing.xg_against_last5 = xg.xg_against_last5
        existing.xg_matches_count_last5 = xg.xg_matches_count_last5

        if standing is not None:
            existing.standing_position = standing.position
            existing.standing_points = standing.points
            existing.standing_goal_diff = standing.goal_diff

        session.flush()

    return created, updated


if __name__ == "__main__":
    from foot_predictor.db.session import get_session

    with get_session() as session:
        n_created, n_updated = build_all_team_match_features(session)
        print(f"{n_created} lignes créées, {n_updated} lignes mises à jour dans features.team_match_features.")