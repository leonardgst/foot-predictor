"""
Ingestion raw -> staging pour la source football-data.co.uk.

Hypothèse sur le format du payload jsonb dans raw.football_data_match
(à produire par le futur script de scraping/téléchargement CSV) :

    {
        "div": "E0",                  # code championnat football-data
        "season_label": "2024-2025",  # ajouté à l'ingestion raw (absent du CSV brut)
        "date": "2024-08-17",         # ISO, normalisé à l'ingestion raw
        "home_team": "Man United",    # libellé brut football-data
        "away_team": "Fulham",
        "fthg": 1,                    # full time home goals ; null si pas encore joué
        "ftag": 0,
    }

Idempotent : peut être relancé plusieurs fois sans créer de doublons
(les entités sont retrouvées via les tables *_source_mapping, la clé
naturelle du match étant (div, date, home_team, away_team)).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import FootballDataMatch
from foot_predictor.ingestion.common import (
    get_or_create_competition,
    get_or_create_match,
    get_or_create_season,
    get_or_create_team,
    get_or_create_team_match,
    load_yaml_mapping,
)

SOURCE_NAME = "football-data"


def _build_match_source_ref(div: str, date: str, home_team: str, away_team: str) -> str:
    return f"{div}|{date}|{home_team}|{away_team}"


def _resolve_status(fthg, ftag) -> str:
    return "played" if fthg is not None and ftag is not None else "scheduled"


def ingest_football_data(session: Session) -> int:
    """Traite toutes les lignes de raw.football_data_match. Renvoie le nombre de lignes traitées."""
    competitions_mapping = load_yaml_mapping("football_data_competitions.yaml")
    teams_mapping = load_yaml_mapping("football_data_teams.yaml")

    rows = session.scalars(select(FootballDataMatch)).all()

    processed = 0
    for row in rows:
        payload = row.raw_payload

        div = payload["div"]
        season_label = payload["season_label"]
        date_str = payload["date"]
        home_team_name = payload["home_team"]
        away_team_name = payload["away_team"]
        home_goals = payload.get("fthg")
        away_goals = payload.get("ftag")

        match_date = dt.datetime.fromisoformat(date_str)

        competition = get_or_create_competition(session, SOURCE_NAME, div, competitions_mapping)
        season = get_or_create_season(session, competition.id, season_label)
        home_team = get_or_create_team(session, SOURCE_NAME, home_team_name, teams_mapping)
        away_team = get_or_create_team(session, SOURCE_NAME, away_team_name, teams_mapping)

        match_source_ref = _build_match_source_ref(div, date_str, home_team_name, away_team_name)
        status = _resolve_status(home_goals, away_goals)

        match = get_or_create_match(
            session,
            SOURCE_NAME,
            match_source_ref,
            competition_id=competition.id,
            season_id=season.id,
            match_date=match_date,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            home_goals=home_goals,
            away_goals=away_goals,
            status=status,
        )

        get_or_create_team_match(
            session,
            match_id=match.id,
            team_id=home_team.id,
            is_home=True,
            goals_for=home_goals,
            goals_against=away_goals,
        )
        get_or_create_team_match(
            session,
            match_id=match.id,
            team_id=away_team.id,
            is_home=False,
            goals_for=away_goals,
            goals_against=home_goals,
        )

        processed += 1

    session.commit()
    return processed


if __name__ == "__main__":
    from foot_predictor.db.session import get_session  # à adapter à ta config de session existante

    with get_session() as session:
        n = ingest_football_data(session)
        print(f"{n} lignes raw.football_data_match traitées.")