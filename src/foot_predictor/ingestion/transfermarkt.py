"""
Ingestion raw -> staging pour Transfermarkt (compositions + valeurs marchandes).

Hypothèses sur le format des payloads jsonb (à produire par le futur scraper) :

raw.transfermarkt_lineup.raw_payload :
    {
        "match_date": "2024-08-17",
        "home_team": "Manchester United FC",   # libellé brut Transfermarkt
        "away_team": "Fulham FC",
        "lineups": {
            "home": [
                {"player_name": "André Onana", "birth_date": "1996-04-02",
                 "started": true, "position": "Goalkeeper"},
                ...
            ],
            "away": [...]
        }
    }

raw.transfermarkt_valuation.raw_payload :
    {
        "player_name": "Marcus Rashford",
        "birth_date": "2000-10-31",
        "value_date": "2024-07-01",
        "value_eur": 70000000
    }

Prérequis : le match doit déjà exister en staging (créé par l'ingestion
football-data). Si ce n'est pas le cas, la ligne est ignorée et journalisée
(à ré-ingérer plus tard, une fois football-data passé sur la période concernée).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import Lineup, PlayerValuation, TransfermarktLineup, TransfermarktValuation
from foot_predictor.ingestion.common import (
    get_or_create_player,
    get_or_create_team,
    load_yaml_mapping,
    resolve_match_cross_source,
)

SOURCE_NAME = "transfermarkt"


def _upsert_lineup_entry(session: Session, *, match_id: int, team_id: int, player_id: int, started: bool, position: str | None) -> None:
    existing = session.scalar(
        select(Lineup).where(
            Lineup.match_id == match_id, Lineup.team_id == team_id, Lineup.player_id == player_id
        )
    )
    if existing is not None:
        existing.started = started
        existing.position = position
        session.flush()
        return
    session.add(Lineup(match_id=match_id, team_id=team_id, player_id=player_id, started=started, position=position))
    session.flush()


def ingest_transfermarkt_lineups(session: Session) -> tuple[int, int]:
    """Renvoie (nb_lignes_traitees, nb_lignes_ignorees_match_introuvable)."""
    teams_mapping = load_yaml_mapping("transfermarkt_teams.yaml")

    rows = session.scalars(select(TransfermarktLineup)).all()
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

        for side, team in (("home", home_team), ("away", away_team)):
            for player_entry in payload["lineups"][side]:
                birth_date = (
                    dt.date.fromisoformat(player_entry["birth_date"])
                    if player_entry.get("birth_date")
                    else None
                )
                player = get_or_create_player(
                    session,
                    SOURCE_NAME,
                    f"{player_entry['player_name']}|{player_entry.get('birth_date', '')}",
                    full_name=player_entry["player_name"],
                    birth_date=birth_date,
                )
                _upsert_lineup_entry(
                    session,
                    match_id=match.id,
                    team_id=team.id,
                    player_id=player.id,
                    started=player_entry["started"],
                    position=player_entry.get("position"),
                )
        processed += 1

    session.commit()
    return processed, skipped


def ingest_transfermarkt_valuations(session: Session) -> int:
    rows = session.scalars(select(TransfermarktValuation)).all()
    processed = 0

    for row in rows:
        payload = row.raw_payload
        birth_date = (
            dt.date.fromisoformat(payload["birth_date"]) if payload.get("birth_date") else None
        )
        player = get_or_create_player(
            session,
            SOURCE_NAME,
            f"{payload['player_name']}|{payload.get('birth_date', '')}",
            full_name=payload["player_name"],
            birth_date=birth_date,
        )
        value_date = dt.date.fromisoformat(payload["value_date"])

        existing = session.scalar(
            select(PlayerValuation).where(
                PlayerValuation.player_id == player.id, PlayerValuation.value_date == value_date
            )
        )
        if existing is not None:
            existing.value_eur = payload["value_eur"]
        else:
            session.add(
                PlayerValuation(player_id=player.id, value_date=value_date, value_eur=payload["value_eur"])
            )
        session.flush()
        processed += 1

    session.commit()
    return processed


if __name__ == "__main__":
    from foot_predictor.db.session import get_session

    with get_session() as session:
        n_lineups, n_skipped = ingest_transfermarkt_lineups(session)
        print(f"{n_lineups} compositions traitées, {n_skipped} ignorées (match introuvable).")

    with get_session() as session:
        n_valuations = ingest_transfermarkt_valuations(session)
        print(f"{n_valuations} valeurs marchandes traitées.")
