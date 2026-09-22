"""
Téléchargement API-Football (v3.football.api-sports.io) -> raw.api_football_injuries.

Endpoint /injuries?league={id}&season={year} : un appel par (league, season)
suffit (contrairement au backfill des fixtures qui paginait match par match),
la réponse couvrant toute la saison en une fois. Coût quota négligeable :
5 championnats x 10 saisons = 50 requêtes au total.

Chaque entrée de la réponse représente un match où un joueur a été signalé
absent (blessure/suspension) -- PAS une période de blessure explicite : il
n'existe aucun événement "retour de blessure" dans cet endpoint. cf.
injuries.py pour la conséquence sur le mapping staging (end_date toujours NULL).

Header x-apisports-key. Clé API via la variable d'environnement API_FOOTBALL_KEY.
"""
from __future__ import annotations

import os

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import ApiFootballInjuries, SourceIngestionLog

BASE_URL = "https://v3.football.api-sports.io"


def _headers() -> dict:
    api_key = os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        raise RuntimeError("Variable d'environnement API_FOOTBALL_KEY manquante.")
    return {"x-apisports-key": api_key}


def fetch_injuries(league_id: int, season: int) -> list[dict]:
    """Liste des entrées "joueur absent pour blessure/suspension sur ce match"
    pour un championnat et une saison donnés."""
    response = requests.get(
        f"{BASE_URL}/injuries",
        headers=_headers(),
        params={"league": league_id, "season": season},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("response", [])


def _injury_already_ingested(session: Session, player_id: int, fixture_id: int) -> bool:
    """Vrai si cette entrée (joueur, fixture) est déjà en raw.api_football_injuries.

    Pas d'identifiant naturel fourni par l'API pour une entrée d'/injuries
    (contrairement au fixture_id seul pour /fixtures?id=) : la combinaison
    player.id + fixture.id est la clé la plus fiable disponible dans le payload."""
    existing = session.scalar(
        select(ApiFootballInjuries).where(
            ApiFootballInjuries.raw_payload["player"]["id"].astext == str(player_id),
            ApiFootballInjuries.raw_payload["fixture"]["id"].astext == str(fixture_id),
        )
    )
    return existing is not None


def ingest_league_season_injuries(session: Session, league_id: int, season: int) -> dict:
    log = SourceIngestionLog(
        source_name="api-football",
        payload_ref=f"injuries;league={league_id};season={season}",
        status="pending",
    )
    session.add(log)
    session.flush()

    counts = {"created": 0, "already_ingested": 0}
    try:
        entries = fetch_injuries(league_id, season)
        for entry in entries:
            player_id = entry["player"]["id"]
            fixture_id = entry["fixture"]["id"]
            if _injury_already_ingested(session, player_id, fixture_id):
                counts["already_ingested"] += 1
                continue

            session.add(ApiFootballInjuries(ingestion_id=log.id, raw_payload=entry))
            counts["created"] += 1
        log.status = "success"
    except requests.RequestException as exc:
        log.status = "failed"
        counts = {"error": str(exc)}

    session.commit()
    return counts


if __name__ == "__main__":
    from foot_predictor.db.session import get_session
    from foot_predictor.ingestion.common import load_yaml_mapping

    competitions = load_yaml_mapping("api_football_competitions.yaml")

    # Mêmes 10 saisons que le backfill des fixtures (api_football_scraper.py),
    # pour une couverture cohérente entre les deux sources.
    SEASON_START_YEARS = range(2015, 2025)  # saisons 2015-2016 à 2024-2025

    with get_session() as session:
        for start_year in SEASON_START_YEARS:
            for league_code, info in competitions.items():
                counts = ingest_league_season_injuries(session, info["api_football_league_id"], start_year)
                print(f"{start_year}-{start_year + 1} / {league_code}: {counts}")
