"""
Ingestion raw -> staging pour Understat (xG par match).

Hypothèse sur le format du payload jsonb :
    {
        "match_date": "2024-08-17",
        "home_team": "Manchester_United",   # libellé brut Understat
        "away_team": "Fulham",
        "home_xg": 1.85,
        "away_xg": 0.62
    }

Prérequis : le match ET les lignes staging.team_match (home/away) doivent déjà
exister (créés par football-data). Understat ne fait que compléter le xG sur
des team_match existants, il n'en crée jamais.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import UnderstatMatchStats
from foot_predictor.ingestion.common import (
    get_or_create_team,
    load_yaml_mapping,
    resolve_match_cross_source,
    upsert_team_match_xg,
)

SOURCE_NAME = "understat"


def ingest_understat_match_stats(session: Session) -> tuple[int, int]:
    """Renvoie (nb_lignes_traitees, nb_lignes_ignorees_match_introuvable)."""
    teams_mapping = load_yaml_mapping("understat_teams.yaml")

    rows = session.scalars(select(UnderstatMatchStats)).all()
    processed, skipped = 0, 0

    for row in rows:
        payload = row.raw_payload
        match_date = dt.datetime.fromisoformat(payload["match_date"])
        home_team_name = payload["home_team"]
        away_team_name = payload["away_team"]

        home_team = get_or_create_team(session, SOURCE_NAME, home_team_name, teams_mapping)
        away_team = get_or_create_team(session, SOURCE_NAME, away_team_name, teams_mapping)

        match_source_ref = f"{payload['match_date']}|{home_team_name}|{away_team_name}"
        match = resolve_match_cross_source(
            session,
            SOURCE_NAME,
            match_source_ref,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            match_date=match_date,
        )
        if match is None:
            skipped += 1
            continue

        home_xg = payload["home_xg"]
        away_xg = payload["away_xg"]

        updated_home = upsert_team_match_xg(
            session, match_id=match.id, team_id=home_team.id, xg_for=home_xg, xg_against=away_xg
        )
        updated_away = upsert_team_match_xg(
            session, match_id=match.id, team_id=away_team.id, xg_for=away_xg, xg_against=home_xg
        )
        if updated_home is None or updated_away is None:
            skipped += 1
            continue

        processed += 1

    session.commit()
    return processed, skipped


if __name__ == "__main__":
    from foot_predictor.db.session import get_session

    with get_session() as session:
        n, n_skipped = ingest_understat_match_stats(session)
        print(f"{n} lignes de xG traitées, {n_skipped} ignorées (match/team_match introuvable).")
