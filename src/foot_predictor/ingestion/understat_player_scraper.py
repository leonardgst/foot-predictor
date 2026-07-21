"""
Téléchargement understat.com (niveau joueur) -> raw.understat_player_match.

Deux appels par championnat/saison :
  1. league.get_player_data(season) -> liste des joueurs du championnat (1 appel)
  2. player.get_match_data() par joueur -> stats par match (1 appel/joueur)

Le 2e type d'appel est le plus coûteux : pas de limite publiée par Understat,
mais on reste raisonnable (délai entre appels).
"""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session
from understatapi import UnderstatClient

from foot_predictor.db.models import SourceIngestionLog, UnderstatPlayerMatch

REQUEST_DELAY_SECONDS = 1


def fetch_league_players(client: UnderstatClient, league_code: str, season: str) -> list[dict]:
    """league_code Understat : 'EPL', 'La_liga', 'Bundesliga', 'Serie_A', 'Ligue_1'."""
    return client.league(league=league_code).get_player_data(season=season)


def fetch_player_matches(client: UnderstatClient, player_id: str) -> list[dict]:
    return client.player(player=player_id).get_match_data()


def _build_payload(player_name: str, match_entry: dict) -> dict:
    return {
        "player_name": player_name,
        "match_date": match_entry["date"][:10],
        "home_team": match_entry["h_team"],
        "away_team": match_entry["a_team"],
        "xg": round(float(match_entry.get("xG", 0) or 0), 2),
        "xa": round(float(match_entry.get("xA", 0) or 0), 2),
        "npxg": round(float(match_entry.get("npxG", 0) or 0), 2),
        "minutes": int(match_entry.get("time", 0) or 0),
    }


def _upsert_raw_row(session: Session, ingestion_id: int, payload: dict) -> str:
    existing = session.scalar(
        select(UnderstatPlayerMatch).where(
            UnderstatPlayerMatch.raw_payload["player_name"].astext == payload["player_name"],
            UnderstatPlayerMatch.raw_payload["match_date"].astext == payload["match_date"],
            UnderstatPlayerMatch.raw_payload["home_team"].astext == payload["home_team"],
            UnderstatPlayerMatch.raw_payload["away_team"].astext == payload["away_team"],
        )
    )
    if existing is None:
        session.add(UnderstatPlayerMatch(ingestion_id=ingestion_id, raw_payload=payload))
        return "created"
    if existing.raw_payload != payload:
        existing.raw_payload = payload
        existing.ingestion_id = ingestion_id
        return "updated"
    return "unchanged"


def ingest_league_players(session: Session, client: UnderstatClient, league_code: str, season: str) -> dict:
    log = SourceIngestionLog(
        source_name="understat", payload_ref=f"players/{league_code}/{season}", status="pending"
    )
    session.add(log)
    session.flush()

    counts = {"created": 0, "updated": 0, "unchanged": 0}
    try:
        players = fetch_league_players(client, league_code, season)
        for player in players:
            time.sleep(REQUEST_DELAY_SECONDS)
            matches = fetch_player_matches(client, player["id"])
            for match_entry in matches:
                if not match_entry.get("date"):
                    continue
                payload = _build_payload(player["player_name"], match_entry)
                result = _upsert_raw_row(session, log.id, payload)
                counts[result] += 1
        log.status = "success"
    except Exception as exc:  # noqa: BLE001
        log.status = "failed"
        counts = {"error": str(exc)}

    session.commit()
    return counts


if __name__ == "__main__":
    from foot_predictor.db.session import get_session

    LEAGUES = ["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1"]
    SEASON = "2024"

    with get_session() as session:
        with UnderstatClient() as client:
            for league_code in LEAGUES:
                counts = ingest_league_players(session, client, league_code, SEASON)
                print(f"{league_code}: {counts}")
