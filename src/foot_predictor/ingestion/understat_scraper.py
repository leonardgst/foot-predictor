"""
Téléchargement understat.com (niveau équipe) -> raw.understat_match_stats.

Un seul appel par championnat/saison :
    league.get_match_data(season) -> tous les matchs du championnat, avec le xG
    équipe (home/away) déjà agrégé par Understat.

Contrairement à understat_player_scraper.py (qui fait 1 appel/joueur), ce
script est très peu coûteux en requêtes : c'est le scraper "bon marché" du
pipeline, à lancer en premier pour Understat.

Format du payload stocké en raw (raw_payload jsonb), conforme à l'hypothèse
documentée en tête de ingestion/understat.py :
    {
        "match_date": "2024-08-17",
        "home_team": "Manchester_United",   # libellé brut Understat
        "away_team": "Fulham",
        "home_xg": 1.85,
        "away_xg": 0.62
    }
"""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session
from understatapi import UnderstatClient

from foot_predictor.db.models import SourceIngestionLog, UnderstatMatchStats

REQUEST_DELAY_SECONDS = 1


def fetch_league_matches(client: UnderstatClient, league_code: str, season: str) -> list[dict]:
    """league_code Understat : 'EPL', 'La_liga', 'Bundesliga', 'Serie_A', 'Ligue_1'."""
    return client.league(league=league_code).get_match_data(season=season)


def _build_payload(match_entry: dict) -> dict | None:
    # Un match pas encore joué n'a pas de xG exploitable -> on l'ignore, il sera
    # récupéré via football-data pour le calendrier, Understat ne fait que
    # compléter le xG de matchs déjà joués (cf. understat.py : "ne crée jamais").
    if not match_entry.get("isResult"):
        return None

    datetime_raw = match_entry.get("datetime")
    if not datetime_raw:
        return None

    xg = match_entry.get("xG") or {}
    home_xg = xg.get("h")
    away_xg = xg.get("a")
    if home_xg is None or away_xg is None:
        return None

    return {
        "match_date": datetime_raw[:10],
        "home_team": match_entry["h"]["title"],
        "away_team": match_entry["a"]["title"],
        "home_xg": round(float(home_xg), 2),
        "away_xg": round(float(away_xg), 2),
    }


def _upsert_raw_row(session: Session, ingestion_id: int, payload: dict) -> str:
    existing = session.scalar(
        select(UnderstatMatchStats).where(
            UnderstatMatchStats.raw_payload["match_date"].astext == payload["match_date"],
            UnderstatMatchStats.raw_payload["home_team"].astext == payload["home_team"],
            UnderstatMatchStats.raw_payload["away_team"].astext == payload["away_team"],
        )
    )
    if existing is None:
        session.add(UnderstatMatchStats(ingestion_id=ingestion_id, raw_payload=payload))
        return "created"
    if existing.raw_payload != payload:
        existing.raw_payload = payload
        existing.ingestion_id = ingestion_id
        return "updated"
    return "unchanged"


def ingest_league_matches(session: Session, client: UnderstatClient, league_code: str, season: str) -> dict:
    log = SourceIngestionLog(
        source_name="understat", payload_ref=f"matches/{league_code}/{season}", status="pending"
    )
    session.add(log)
    session.flush()

    counts = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    try:
        matches = fetch_league_matches(client, league_code, season)
        for match_entry in matches:
            payload = _build_payload(match_entry)
            if payload is None:
                counts["skipped"] += 1
                continue
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

    LEAGUES = ["EPL", "La_Liga", "Bundesliga", "Serie_A", "Ligue_1"]

    # Backfill des 10 dernières saisons, même logique que football_data_scraper.py
    # (season Understat = année de début, ex. "2024" pour 2024-2025).
    SEASON_START_YEARS = range(2015, 2025)

    with get_session() as session:
        with UnderstatClient() as client:
            for start_year in SEASON_START_YEARS:
                season = str(start_year)
                for league_code in LEAGUES:
                    counts = ingest_league_matches(session, client, league_code, season)
                    print(f"{season} / {league_code}: {counts}")