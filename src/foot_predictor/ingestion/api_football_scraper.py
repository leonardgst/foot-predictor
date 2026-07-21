"""
Téléchargement API-Football (v3.football.api-sports.io) -> raw.api_football_fixture_detail.

Remplace l'ancien api_football_scraper.py (qui ne récupérait que les lineups via
/fixtures/lineups). Utilise désormais /fixtures?id={id}, qui renvoie en un seul
appel : compositions (lineups) + statistiques par joueur (players) + événements.
Coût quota divisé par ~2 par rapport à des appels séparés.

Contrairement à l'ancienne version, le payload stocké en raw est la réponse
API quasi verbatim (fidèle au principe raw = copie brute sans transformation,
cf. recap_decisions_projet.md section 6) : toute l'extraction (lineups d'un
côté, stats joueurs de l'autre) se fait dans api_football.py (staging).

Plan gratuit : 100 requêtes/jour, reset 00:00 UTC. Header x-apisports-key.
Clé API à fournir via la variable d'environnement API_FOOTBALL_KEY.
"""
from __future__ import annotations

import os
import time

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from foot_predictor.db.models import ApiFootballFixtureDetail, SourceIngestionLog

BASE_URL = "https://v3.football.api-sports.io"
REQUEST_DELAY_SECONDS = 1


def _headers() -> dict:
    api_key = os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        raise RuntimeError("Variable d'environnement API_FOOTBALL_KEY manquante.")
    return {"x-apisports-key": api_key}


def fetch_fixtures(league_id: int, season: int, date_from: str, date_to: str) -> list[dict]:
    """Liste les fixtures d'un championnat sur une période (pour récupérer les
    fixture_id et filtrer sur les matchs terminés)."""
    response = requests.get(
        f"{BASE_URL}/fixtures",
        headers=_headers(),
        params={"league": league_id, "season": season, "from": date_from, "to": date_to},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("response", [])


def fetch_fixture_detail(fixture_id: int) -> dict | None:
    """Renvoie la réponse complète (fixture + teams + lineups + players + events)
    pour un fixture_id donné, ou None si absent."""
    response = requests.get(
        f"{BASE_URL}/fixtures", headers=_headers(), params={"id": fixture_id}, timeout=30
    )
    response.raise_for_status()
    data = response.json().get("response", [])
    return data[0] if data else None


def _upsert_fixture_detail(session: Session, ingestion_id: int, fixture_detail: dict) -> str:
    """Upsert sur l'identifiant de fixture API-Football (fiable, contrairement
    à une clé naturelle date+équipes) -> évite la croissance illimitée de raw."""
    fixture_id = fixture_detail["fixture"]["id"]
    existing = session.scalar(
        select(ApiFootballFixtureDetail).where(
            ApiFootballFixtureDetail.raw_payload["fixture"]["id"].astext == str(fixture_id)
        )
    )
    if existing is None:
        session.add(ApiFootballFixtureDetail(ingestion_id=ingestion_id, raw_payload=fixture_detail))
        return "created"
    if existing.raw_payload != fixture_detail:
        existing.raw_payload = fixture_detail
        existing.ingestion_id = ingestion_id
        return "updated"
    return "unchanged"


def ingest_league_fixture_details(
    session: Session, league_id: int, season: int, date_from: str, date_to: str
) -> dict:
    log = SourceIngestionLog(
        source_name="api-football",
        payload_ref=f"league={league_id};season={season};{date_from}..{date_to}",
        status="pending",
    )
    session.add(log)
    session.flush()

    counts = {"created": 0, "updated": 0, "unchanged": 0, "not_finished": 0}
    try:
        fixtures = fetch_fixtures(league_id, season, date_from, date_to)
        for fixture in fixtures:
            if fixture["fixture"]["status"]["short"] != "FT":
                counts["not_finished"] += 1
                continue
            time.sleep(REQUEST_DELAY_SECONDS)
            detail = fetch_fixture_detail(fixture["fixture"]["id"])
            if detail is None:
                continue
            result = _upsert_fixture_detail(session, log.id, detail)
            counts[result] += 1
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
    CURRENT_SEASON = 2024
    DATE_FROM = "2024-08-01"
    DATE_TO = "2024-08-31"  # à élargir progressivement, cf. quota 100 req/jour

    with get_session() as session:
        for league_code, info in competitions.items():
            counts = ingest_league_fixture_details(
                session, info["api_football_league_id"], CURRENT_SEASON, DATE_FROM, DATE_TO
            )
            print(f"{league_code}: {counts}")
